from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import discord
from discord.ext import commands

from config.settings import BotSettings
from parser.core import slugify
from parser.legacy import (
    message_parse,
    reset_contributor_username_lookup,
    set_contributor_username_lookup,
)


@dataclass
class ParseDiagnostic:
    thread_id: int
    thread_name: str
    error: str


@dataclass
class ParseResult:
    total: int
    errors: list[ParseDiagnostic]


class ParserService:
    def __init__(self, bot: commands.Bot, settings: BotSettings):
        self.bot = bot
        self.settings = settings
        self.output_dir = settings.data_dir / "parsed"

    async def parse_thread(self, thread: discord.Thread) -> ParseResult:
        errors = await self._parse_and_write(thread)
        return ParseResult(total=1, errors=errors)

    async def parse_channel(self, channel: discord.ForumChannel) -> ParseResult:
        total = 0
        errors: list[ParseDiagnostic] = []
        async for thread in self.iter_all_threads(channel):
            total += 1
            errors.extend(await self._parse_and_write(thread))
        return ParseResult(total=total, errors=errors)

    async def parse_archive(self, guild: discord.Guild) -> ParseResult:
        total = 0
        errors = self.clear_output_dir()
        for channel in guild.channels:
            if (
                isinstance(channel, discord.ForumChannel)
                and channel.category_id in self.settings.categories.main_archive
            ):
                result = await self.parse_channel(channel)
                total += result.total
                errors.extend(result.errors)
        return ParseResult(total=total, errors=errors)

    async def iter_all_threads(self, channel: discord.ForumChannel):
        for thread in channel.threads:
            yield thread
        async for thread in channel.archived_threads(limit=None):
            yield thread

    async def _parse_and_write(self, thread: discord.Thread) -> list[ParseDiagnostic]:
        try:
            messages = []
            async for message in thread.history(limit=None, oldest_first=True):
                if message.content and message.type == discord.MessageType.default:
                    messages.append(message.content)
            username_lookup = await self.build_username_lookup_from_messages(messages)
            lookup_token = set_contributor_username_lookup(username_lookup)
            try:
                parsed = self.parse_text("\n".join(messages))
            finally:
                reset_contributor_username_lookup(lookup_token)
            payload = {
                "parsed_at": datetime.now(UTC).isoformat(),
                "channel_id": str(thread.parent_id),
                "thread_id": str(thread.id),
                "slug": slugify(thread.name),
                "title": thread.name,
                "tags": [{"id": tag.id, "name": tag.name} for tag in thread.applied_tags],
                "post_data": parsed,
            }
            self.output_dir.mkdir(parents=True, exist_ok=True)
            final_path = self.output_dir / f"{thread.id}.json"
            temp_path = final_path.with_suffix(".json.tmp")
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
                file.write("\n")
            temp_path.replace(final_path)
            return []
        except Exception as exc:
            return [ParseDiagnostic(thread.id, thread.name, f"{type(exc).__name__}: {exc}")]

    def clear_output_dir(self) -> list[ParseDiagnostic]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        errors: list[ParseDiagnostic] = []
        for path in self.output_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError as exc:
                errors.append(
                    ParseDiagnostic(
                        thread_id=0,
                        thread_name=path.name,
                        error=f"Could not remove old parsed file: {exc}",
                    )
                )
        return errors

    def parse_text(self, text: str) -> dict[str, Any]:
        return cast(dict[str, Any], message_parse(text.split("\n")))

    async def build_username_lookup_from_messages(self, messages: list[str]) -> dict[int, str]:
        import re

        user_ids: set[int] = set()
        for message in messages:
            for match in re.finditer(r"<@!?(\d+)>", message):
                user_ids.add(int(match.group(1)))

        lookup: dict[int, str] = {}
        for user_id in user_ids:
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue
            lookup[user_id] = getattr(user, "display_name", user.name)
        return lookup
