from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, User

# Entity types grouped by which audit permission may see them (FR-AU-02). Supervisor report
# access ("report") is visible to the super admin so the oversight itself can be overseen.
USER_MANAGEMENT_ENTITIES = frozenset({"user", "setting", "report", "job"})
OPERATIONS_ENTITIES = frozenset(
    {"barrel", "order", "exception_request", "loan", "penalty", "pump", "pump_stock"}
)
INVOICING_ENTITIES = frozenset({"invoice"})


def record(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit entry to the current transaction. The caller commits."""
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
    )
    db.add(entry)
    return entry


def list_entries(
    db: Session,
    *,
    entity_types: frozenset[str] | None = None,
    limit: int = 200,
    actor: str = "",
    action: str = "",
    entity_type: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if entity_types is not None:
        stmt = stmt.where(AuditLog.entity_type.in_(entity_types))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if actor:
        stmt = stmt.join(User, User.id == AuditLog.actor_id).where(
            User.username.ilike(f"%{actor.strip()}%")
        )
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= _start_of_day(date_from))
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at < _start_of_day(date_to + timedelta(days=1)))
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(get_settings().timezone))
