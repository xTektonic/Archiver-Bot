from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def utc_after_iso(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def is_expired(iso_timestamp: str) -> bool:
    return datetime.fromisoformat(iso_timestamp) <= datetime.now(UTC)
