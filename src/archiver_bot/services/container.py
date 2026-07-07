from __future__ import annotations

from dataclasses import dataclass

from archiver_bot.services.audit import AuditLogService
from archiver_bot.services.state import StateService


@dataclass
class ServiceContainer:
    audit: AuditLogService
    state: StateService
    approvals: object | None = None
    tracker: object | None = None
    archive: object | None = None
    moderation: object | None = None
    parser: object | None = None
    maintenance: object | None = None
