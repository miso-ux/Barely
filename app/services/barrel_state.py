"""The single place where a barrel changes status (CLAUDE.md ch. 6).

Every transition validates against the allowed-transition table, writes a history row and an
audit entry. Callers commit; this lets phase 3 run issue/return inside one transaction.
"""

from datetime import UTC, datetime
from typing import Final

from sqlalchemy.orm import Session

from app.models import Barrel, BarrelStatus, BarrelStatusHistory, User
from app.services import audit
from app.services.errors import InvalidBarrelTransition

S = BarrelStatus

TRANSITIONS: Final[dict[BarrelStatus, frozenset[BarrelStatus]]] = {
    S.IN_STOCK: frozenset({S.ON_LOAN, S.DAMAGED, S.LOST, S.WRITTEN_OFF}),
    S.ON_LOAN: frozenset({S.IN_STOCK, S.DAMAGED, S.LOST, S.RETIRED}),
    S.DAMAGED: frozenset({S.WRITTEN_OFF}),
    S.LOST: frozenset({S.IN_STOCK, S.WRITTEN_OFF}),
    S.RETIRED: frozenset({S.WRITTEN_OFF}),
    S.WRITTEN_OFF: frozenset(),
}

# Statuses that are never picked for issuing (BR-14).
NOT_ISSUABLE: Final[frozenset[BarrelStatus]] = frozenset(
    {S.DAMAGED, S.LOST, S.RETIRED, S.WRITTEN_OFF}
)


class Reason:
    """History reason codes; translated in the UI as `barrel.reason.<code>`."""

    CREATED: Final = "created"
    ISSUED: Final = "issued"
    RETURNED: Final = "returned"
    RETURNED_DAMAGED: Final = "returned_damaged"
    DAMAGED: Final = "damaged"
    LOST: Final = "lost"
    FOUND: Final = "found"
    WRITTEN_OFF: Final = "written_off"
    RETIRED: Final = "retired"
    PENALTY_PAID: Final = "penalty_paid"


def can_transition(from_status: BarrelStatus, to_status: BarrelStatus) -> bool:
    return to_status in TRANSITIONS[from_status]


def record_creation(db: Session, barrel: Barrel, *, actor: User | None) -> None:
    db.add(
        BarrelStatusHistory(
            barrel=barrel,
            from_status=None,
            to_status=barrel.status,
            reason=Reason.CREATED,
            actor_id=actor.id if actor else None,
        )
    )
    audit.record(
        db,
        actor=actor,
        action="barrel.created",
        entity_type="barrel",
        entity_id=barrel.id,
        after={"code": barrel.code, "status": barrel.status.value},
    )


def transition(
    db: Session,
    barrel: Barrel,
    to_status: BarrelStatus,
    *,
    actor: User | None,
    reason: str,
    note: str | None = None,
    loan_id: int | None = None,
) -> Barrel:
    from_status = barrel.status
    if not can_transition(from_status, to_status):
        raise InvalidBarrelTransition(from_status=from_status.value, to_status=to_status.value)

    now = datetime.now(UTC)
    barrel.status = to_status
    if to_status is S.RETIRED:
        barrel.retired_at = now
    if to_status is S.WRITTEN_OFF:
        barrel.written_off_at = now

    db.add(
        BarrelStatusHistory(
            barrel=barrel,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            note=(note or "").strip() or None,
            actor_id=actor.id if actor else None,
            loan_id=loan_id,
        )
    )
    audit.record(
        db,
        actor=actor,
        action="barrel.status_changed",
        entity_type="barrel",
        entity_id=barrel.id,
        before={"status": from_status.value},
        after={"status": to_status.value, "reason": reason, "loan_id": loan_id},
    )
    return barrel
