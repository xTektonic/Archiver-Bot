from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.audit import AuditLogService
from services.state import StateService

if TYPE_CHECKING:
    from services.approvals import ApprovalService
    from services.archive import ArchivePublishingService
    from services.maintenance import MaintenanceJobService
    from services.moderation import ModerationService
    from services.parser_service import ParserService
    from services.tracker import SubmissionTrackerService


@dataclass
class ServiceContainer:
    audit: AuditLogService
    state: StateService
    approvals: ApprovalService
    tracker: SubmissionTrackerService
    archive: ArchivePublishingService
    moderation: ModerationService
    parser: ParserService
    maintenance: MaintenanceJobService
