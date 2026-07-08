from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SubmissionStatus = Literal[
    "pending",
    "awaiting_testing",
    "accepted",
    "archived",
    "rejected",
    "unknown",
]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "failed"]
ApprovalType = Literal["delete_message", "delete_thread", "edit_thread_title"]


@dataclass
class TrackedSubmission:
    submission_thread_id: int
    title: str
    status: SubmissionStatus
    tracker_message_id: int | None
    tracker_thread_id: int | None
    created_at: str
    updated_at: str
    submission_url: str | None = None
    tracker_thread_url: str | None = None


@dataclass
class PendingApproval:
    approval_id: str
    type: ApprovalType
    requester_id: int
    status: ApprovalStatus
    created_at: str
    expires_at: str
    approval_message_id: int | None = None
    approval_channel_id: int | None = None
    target_channel_id: int | None = None
    target_message_id: int | None = None
    target_thread_id: int | None = None
    proposed_title: str | None = None
    approver_id: int | None = None
    result_log_url: str | None = None


@dataclass
class CommandChange:
    old_command: str
    old_description: str
    new_command: str
    new_description: str
    reason: str
    safe_to_revert: bool


@dataclass
class BotState:
    version: int = 1
    blocked_dm_users: list[int] = field(default_factory=list)
    tracker_summary_message_ids: list[int] = field(default_factory=list)
    accepted_submission_entries: list[str] = field(default_factory=list)
    last_archive_thread_id: int | None = None
    tracked_submissions: dict[str, TrackedSubmission] = field(default_factory=dict)
    pending_approvals: dict[str, PendingApproval] = field(default_factory=dict)
    command_change_log: list[CommandChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BotState:
        tracked = {
            str(key): TrackedSubmission(**value)
            for key, value in raw.get("tracked_submissions", {}).items()
        }
        approvals = {
            str(key): PendingApproval(**value)
            for key, value in raw.get("pending_approvals", {}).items()
        }
        changes = [CommandChange(**value) for value in raw.get("command_change_log", [])]
        return cls(
            version=int(raw.get("version", 1)),
            blocked_dm_users=[int(x) for x in raw.get("blocked_dm_users", [])],
            tracker_summary_message_ids=[
                int(x) for x in raw.get("tracker_summary_message_ids", [])
            ],
            accepted_submission_entries=[
                str(x) for x in raw.get("accepted_submission_entries", [])
            ],
            last_archive_thread_id=raw.get("last_archive_thread_id"),
            tracked_submissions=tracked,
            pending_approvals=approvals,
            command_change_log=changes,
        )
