from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config.settings import BotSettings  # noqa: E402
from models.state import BotState, TrackedSubmission  # noqa: E402
from services.tracker import SubmissionTrackerService  # noqa: E402


class FakeTag:
    def __init__(self, tag_id: int):
        self.id = tag_id


class FakeMessage:
    def __init__(self, message_id: int, content: str = ""):
        self.id = message_id
        self.content = content
        self.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        self.reactions: list[Any] = []
        self.deleted = False
        self.pinned = False

    async def delete(self) -> None:
        self.deleted = True

    async def add_reaction(self, _emoji: str) -> None:
        return None

    async def pin(self) -> None:
        self.pinned = True

    async def edit(self, *, content: str, allowed_mentions: object = None) -> None:
        self.content = content


class FakeThread:
    def __init__(self, thread_id: int, name: str, tag_ids: list[int] | None = None):
        self.id = thread_id
        self.name = name
        self.applied_tags = [FakeTag(tag_id) for tag_id in tag_ids or []]
        self.jump_url = f"https://discord.com/channels/1/{thread_id}"
        self.sent: list[str] = []

    async def send(self, content: str, allowed_mentions: object = None) -> FakeMessage:
        self.sent.append(content)
        return FakeMessage(900000 + len(self.sent), content)

    async def edit(self, *, name: str) -> None:
        self.name = name


class FakeTextChannel:
    def __init__(self):
        self.messages: list[FakeMessage] = []
        self.created_threads: list[FakeThread] = []
        self.next_id = 2000

    async def pins(self) -> list[FakeMessage]:
        return []

    async def history(self, *, limit: int | None = None, oldest_first: bool = False):
        for message in list(self.messages):
            yield message

    async def fetch_message(self, message_id: int) -> FakeMessage:
        for message in self.messages:
            if message.id == message_id:
                return message
        raise RuntimeError(f"missing message {message_id}")

    async def create_thread(self, *, name: str, type: object = None) -> FakeThread:
        self.next_id += 1
        thread = FakeThread(self.next_id, name)
        self.created_threads.append(thread)
        return thread

    def get_partial_message(self, message_id: int) -> FakeMessage:
        return FakeMessage(message_id)

    async def send(self, content: str, allowed_mentions: object = None) -> FakeMessage:
        self.next_id += 1
        message = FakeMessage(self.next_id, content)
        self.messages.append(message)
        return message


class FakeForumChannel:
    def __init__(
        self,
        threads: list[FakeThread] | None = None,
        archived: list[FakeThread] | None = None,
    ):
        self.threads = threads or []
        self._archived = archived or []

    async def archived_threads(self, *, limit: int | None = None):
        for thread in self._archived:
            yield thread


class FakeBot:
    def __init__(self, channels: dict[int, object]):
        self.channels = channels
        self.guilds: list[Any] = []
        self.user = None

    def get_channel(self, channel_id: int) -> object | None:
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int) -> object | None:
        return self.channels.get(channel_id)


class FakeStateService:
    def __init__(self, state: BotState | None = None):
        self.state = state or BotState()

    async def get(self) -> BotState:
        return self.state

    async def upsert_submission(self, submission: TrackedSubmission) -> None:
        self.state.tracked_submissions[str(submission.submission_thread_id)] = submission

    async def remove_submission(self, submission_thread_id: int) -> None:
        self.state.tracked_submissions.pop(str(submission_thread_id), None)

    async def set_tracker_summary_messages(self, message_ids: list[int]) -> None:
        self.state.tracker_summary_message_ids = message_ids

    async def set_accepted_submission_entries(self, entries: list[str]) -> None:
        self.state.accepted_submission_entries = entries


class FakeAudit:
    async def log(self, *_args: object, **_kwargs: object) -> None:
        return None


class TrackerSyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = BotSettings(token="", data_dir=Path("data"))
        self.type_patchers: list[Any] = [
            patch("services.tracker.discord.TextChannel", FakeTextChannel),
            patch("services.tracker.discord.ForumChannel", FakeForumChannel),
            patch("services.tracker.discord.Thread", FakeThread),
        ]
        for patcher in self.type_patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.type_patchers):
            patcher.stop()

    def service(
        self,
        submissions: FakeForumChannel,
        tracker: FakeTextChannel,
        state: BotState | None = None,
        extra_channels: dict[int, object] | None = None,
    ) -> tuple[SubmissionTrackerService, FakeStateService]:
        channels: dict[int, object] = {
            self.settings.channels.submissions: submissions,
            self.settings.channels.submissions_tracker: tracker,
        }
        channels.update(extra_channels or {})
        state_service = FakeStateService(state)
        service = SubmissionTrackerService(
            cast(Any, FakeBot(channels)),
            self.settings,
            cast(Any, state_service),
            cast(Any, FakeAudit()),
        )
        service.rebuild_summary = AsyncMock()  # type: ignore[method-assign]
        return service, state_service

    async def test_dry_run_reports_missing_tracker_without_mutating_state(self) -> None:
        thread = FakeThread(111111111111111, "Pending Submission")
        tracker = FakeTextChannel()
        service, state = self.service(FakeForumChannel([thread]), tracker)

        result = await service.sync_all(dry_run=True)

        self.assertEqual(result.created, ["Pending Submission"])
        self.assertEqual(state.state.tracked_submissions, {})
        self.assertEqual(tracker.messages, [])

    async def test_apply_creates_tracker_for_unresolved_submission(self) -> None:
        thread = FakeThread(111111111111111, "Pending Submission")
        tracker = FakeTextChannel()
        service, state = self.service(FakeForumChannel([thread]), tracker)

        result = await service.sync_all(dry_run=False)

        self.assertEqual(result.created, ["Pending Submission"])
        self.assertIn(str(thread.id), state.state.tracked_submissions)
        self.assertTrue(any(thread.jump_url in message.content for message in tracker.messages))

    async def test_accepted_submission_finalizes_tracker(self) -> None:
        thread = FakeThread(
            111111111111111,
            "Accepted Submission",
            [self.settings.tags.accepted],
        )
        message = FakeMessage(
            222222222222222,
            f"## [Accepted Submission]({thread.jump_url})\nhttps://discord.com/channels/1/333333333333333",
        )
        tracker = FakeTextChannel()
        tracker.messages.append(message)
        service, state = self.service(FakeForumChannel([thread]), tracker)

        result = await service.sync_all(dry_run=False)

        self.assertEqual(result.finalized, ["accepted: Accepted Submission"])
        self.assertTrue(message.deleted)
        self.assertNotIn(str(thread.id), state.state.tracked_submissions)

    async def test_include_archived_controls_archived_thread_scan(self) -> None:
        active = FakeThread(111111111111111, "Active")
        archived = FakeThread(222222222222222, "Archived Pending")
        tracker = FakeTextChannel()
        service, _state = self.service(FakeForumChannel([active], [archived]), tracker)

        active_only = await service.sync_all(dry_run=True, include_archived=False)
        with_archived = await service.sync_all(dry_run=True, include_archived=True)

        self.assertEqual(active_only.created, ["Active"])
        self.assertEqual(with_archived.created, ["Active", "Archived Pending"])

    async def test_duplicate_tracker_messages_are_reported_without_deleting_votes(self) -> None:
        thread = FakeThread(111111111111111, "Pending Submission")
        first = FakeMessage(
            222222222222222,
            f"## [Pending Submission]({thread.jump_url})\nhttps://discord.com/channels/1/333333333333333",
        )
        duplicate = FakeMessage(
            444444444444444,
            f"## [Pending Submission]({thread.jump_url})\nhttps://discord.com/channels/1/555555555555555",
        )
        tracker = FakeTextChannel()
        tracker.messages.extend([first, duplicate])
        service, _state = self.service(FakeForumChannel([thread]), tracker)

        result = await service.sync_all(dry_run=False)

        self.assertEqual(len(result.duplicates), 1)
        self.assertFalse(duplicate.deleted)

    async def test_terminal_state_only_record_is_removed(self) -> None:
        thread = FakeThread(
            111111111111111,
            "Rejected Submission",
            [self.settings.tags.rejected],
        )
        state = BotState()
        state.tracked_submissions[str(thread.id)] = TrackedSubmission(
            submission_thread_id=thread.id,
            title=thread.name,
            status="pending",
            tracker_message_id=None,
            tracker_thread_id=None,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            submission_url=thread.jump_url,
        )
        tracker = FakeTextChannel()
        service, state_service = self.service(FakeForumChannel([thread]), tracker, state)

        result = await service.sync_all(dry_run=False)

        self.assertEqual(result.finalized, ["rejected: Rejected Submission"])
        self.assertNotIn(str(thread.id), state_service.state.tracked_submissions)

    async def test_missing_tracker_discussion_is_recreated(self) -> None:
        thread = FakeThread(111111111111111, "Pending Submission")
        message = FakeMessage(
            222222222222222,
            f"## [Pending Submission]({thread.jump_url})\nhttps://discord.com/channels/1/333333333333333",
        )
        tracker = FakeTextChannel()
        tracker.messages.append(message)
        service, state = self.service(FakeForumChannel([thread]), tracker)

        result = await service.sync_all(dry_run=False)

        self.assertEqual(result.updated, ["Recreated missing tracker discussion for Pending Submission"])
        record = state.state.tracked_submissions[str(thread.id)]
        self.assertIsNotNone(record.tracker_thread_id)
        self.assertIn(str(record.tracker_thread_id), message.content)

    async def test_stale_state_only_tracker_message_id_is_recreated(self) -> None:
        thread = FakeThread(111111111111111, "Pending Submission")
        state = BotState()
        state.tracked_submissions[str(thread.id)] = TrackedSubmission(
            submission_thread_id=thread.id,
            title=thread.name,
            status="pending",
            tracker_message_id=222222222222222,
            tracker_thread_id=333333333333333,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            submission_url=thread.jump_url,
            tracker_thread_url="https://discord.com/channels/1/333333333333333",
        )
        tracker = FakeTextChannel()
        service, state_service = self.service(FakeForumChannel([thread]), tracker, state)

        result = await service.sync_all(dry_run=False)

        self.assertEqual(result.created, ["Pending Submission"])
        record = state_service.state.tracked_submissions[str(thread.id)]
        self.assertNotEqual(record.tracker_message_id, 222222222222222)
        self.assertTrue(any(thread.jump_url in message.content for message in tracker.messages))

    async def test_dry_run_does_not_mutate_state_record_status(self) -> None:
        thread = FakeThread(111111111111111, "Pending Submission")
        state = BotState()
        state.tracked_submissions[str(thread.id)] = TrackedSubmission(
            submission_thread_id=thread.id,
            title=thread.name,
            status="accepted",
            tracker_message_id=222222222222222,
            tracker_thread_id=333333333333333,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            submission_url=thread.jump_url,
            tracker_thread_url="https://discord.com/channels/1/333333333333333",
        )
        tracker = FakeTextChannel()
        service, state_service = self.service(FakeForumChannel([thread]), tracker, state)

        result = await service.sync_all(dry_run=True)

        self.assertEqual(result.created, ["Pending Submission"])
        self.assertEqual(
            state_service.state.tracked_submissions[str(thread.id)].status,
            "accepted",
        )
