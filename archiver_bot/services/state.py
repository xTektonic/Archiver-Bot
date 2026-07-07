from __future__ import annotations

from archiver_bot.models.state import BotState, PendingApproval, TrackedSubmission
from archiver_bot.storage.state_store import StateStore


class StateService:
    def __init__(self, store: StateStore):
        self.store = store

    async def initialize(self) -> None:
        await self.store.initialize()

    async def get(self) -> BotState:
        return await self.store.load()

    async def is_dm_blocked(self, user_id: int) -> bool:
        state = await self.store.load()
        return user_id in state.blocked_dm_users

    async def block_dm_user(self, user_id: int) -> bool:
        def mutate(state: BotState) -> bool:
            if user_id in state.blocked_dm_users:
                return False
            state.blocked_dm_users.append(user_id)
            state.blocked_dm_users.sort()
            return True

        return await self.store.update(mutate)

    async def set_last_archive_thread(self, thread_id: int | None) -> None:
        def mutate(state: BotState) -> None:
            state.last_archive_thread_id = thread_id

        await self.store.update(mutate)

    async def upsert_submission(self, submission: TrackedSubmission) -> None:
        def mutate(state: BotState) -> None:
            state.tracked_submissions[str(submission.submission_thread_id)] = submission

        await self.store.update(mutate)

    async def remove_submission(self, submission_thread_id: int) -> None:
        def mutate(state: BotState) -> None:
            state.tracked_submissions.pop(str(submission_thread_id), None)

        await self.store.update(mutate)

    async def set_tracker_summary_messages(self, message_ids: list[int]) -> None:
        def mutate(state: BotState) -> None:
            state.tracker_summary_message_ids = message_ids

        await self.store.update(mutate)

    async def put_approval(self, approval: PendingApproval) -> None:
        def mutate(state: BotState) -> None:
            state.pending_approvals[approval.approval_id] = approval

        await self.store.update(mutate)

    async def update_approval(self, approval: PendingApproval) -> None:
        await self.put_approval(approval)
