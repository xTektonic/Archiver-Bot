from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from models.state import BotState

T = TypeVar("T")


class StateStore:
    """Small JSON state store with atomic writes and in-process locking."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.state_path = data_dir / "state.json"
        self.backup_dir = data_dir / "backups"
        self.parsed_dir = data_dir / "parsed"
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            await self.save(self._load_legacy_state())
            return
        state = await self.load()
        if state.version != 1:
            await self._backup_existing("pre-migration")
            await self.save(state)

    def _load_legacy_state(self) -> BotState:
        state = BotState()
        legacy_blacklist = Path("blacklist.json")
        legacy_messages = Path("messages.json")
        legacy_accepted = Path("accepted.json")
        state.blocked_dm_users = self._load_int_list(legacy_blacklist)
        state.tracker_summary_message_ids = self._load_int_list(legacy_messages)
        state.accepted_submission_entries = self._load_str_list(legacy_accepted)
        return state

    def _load_int_list(self, path: Path) -> list[int]:
        values = self._load_json_list(path)
        result: list[int] = []
        for value in values:
            if not isinstance(value, int | str):
                continue
            try:
                result.append(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def _load_str_list(self, path: Path) -> list[str]:
        return [str(value) for value in self._load_json_list(path)]

    def _load_json_list(self, path: Path) -> list[object]:
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                content = file.read().strip()
            if not content:
                return []
            raw = json.loads(content)
            return raw if isinstance(raw, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    async def load(self) -> BotState:
        async with self._lock:
            return self._load_unlocked()

    async def save(self, state: BotState) -> None:
        async with self._lock:
            self._save_unlocked(state)

    async def update(self, mutator: Callable[[BotState], T]) -> T:
        async with self._lock:
            state = self._load_unlocked()
            result = mutator(state)
            self._save_unlocked(state)
            return result

    def _load_unlocked(self) -> BotState:
        if not self.state_path.exists():
            return BotState()
        try:
            with self.state_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                raise ValueError("state root must be an object")
            return BotState.from_dict(raw)
        except Exception as exc:
            raise RuntimeError(f"Could not load runtime state from {self.state_path}: {exc}") from exc

    def _save_unlocked(self, state: BotState) -> None:
        raw = state.to_dict()
        BotState.from_dict(raw)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(raw, file, indent=2, sort_keys=True)
            file.write("\n")
        os.replace(temp_path, self.state_path)

    async def _backup_existing(self, reason: str) -> None:
        if not self.state_path.exists():
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = self.backup_dir / f"state-{reason}-{stamp}.json"
        shutil.copy2(self.state_path, destination)
