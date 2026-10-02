from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User

# Entity types grouped by which audit permission may see them (FR-AU-02).
USER_MANAGEMENT_ENTITIES = frozenset({"user", "setting"})
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
    db: Session, *, entity_types: frozenset[str] | None = None, limit: int = 200
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    if entity_types is not None:
        stmt = stmt.where(AuditLog.entity_type.in_(entity_types))
    return list(db.scalars(stmt))
