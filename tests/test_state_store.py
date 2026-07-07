from __future__ import annotations

import json
import unittest

from models.state import PendingApproval, TrackedSubmission
from storage.state_store import StateStore


class StateStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_creates_default_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            store = StateStore(tmp_path)

            await store.initialize()

            state_path = tmp_path / "state.json"
            self.assertTrue(state_path.exists())
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["version"], 1)
            self.assertEqual(raw["blocked_dm_users"], [])
            self.assertEqual(raw["tracked_submissions"], {})

    async def test_update_writes_atomically_readable_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            store = StateStore(tmp_path)
            await store.initialize()

            await store.update(lambda state: state.blocked_dm_users.append(123))
            state = await store.load()

            self.assertEqual(state.blocked_dm_users, [123])
            self.assertFalse((tmp_path / "state.json.tmp").exists())

    async def test_state_round_trips_nested_records(self):
        with TemporaryDirectoryPath() as tmp_path:
            store = StateStore(tmp_path)
            await store.initialize()

            def mutate(state):
                state.tracked_submissions["1"] = TrackedSubmission(
                    submission_thread_id=1,
                    title="Farm",
                    status="pending",
                    tracker_message_id=2,
                    tracker_thread_id=3,
                    created_at="2026-07-06T00:00:00+00:00",
                    updated_at="2026-07-06T00:00:00+00:00",
                )
                state.pending_approvals["a"] = PendingApproval(
                    approval_id="a",
                    type="delete_message",
                    requester_id=10,
                    status="pending",
                    created_at="2026-07-06T00:00:00+00:00",
                    expires_at="2026-07-06T01:00:00+00:00",
                    target_channel_id=20,
                    target_message_id=30,
                )

            await store.update(mutate)
            state = await store.load()

            self.assertEqual(state.tracked_submissions["1"].title, "Farm")
            self.assertEqual(state.pending_approvals["a"].target_message_id, 30)


class TemporaryDirectoryPath:
    def __enter__(self):
        import tempfile
        from pathlib import Path

        self._directory = tempfile.TemporaryDirectory()
        return Path(self._directory.__enter__())

    def __exit__(self, exc_type, exc, traceback):
        return self._directory.__exit__(exc_type, exc, traceback)
