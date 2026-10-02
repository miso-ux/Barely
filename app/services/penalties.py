"""Penalties (FR-VR-03..07, BR-04..06, BR-16). Amount is taken from configuration at creation."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BarrelStatus,
    Loan,
    LoanStatus,
    Penalty,
    PenaltyReason,
    PenaltyStatus,
    User,
)
from app.services import audit, barrel_state, dates, notifications
from app.services import settings as settings_service
from app.services.barrel_state import Reason
from app.services.errors import InvalidPenaltyTransition, ReasonRequired

OUTSTANDING_LOAN_STATUSES = (LoanStatus.ON_LOAN, LoanStatus.OVERDUE)


def active_penalty(db: Session, loan: Loan, reason: PenaltyReason) -> Penalty | None:
    return db.scalar(
        select(Penalty).where(
            Penalty.loan_id == loan.id,
            Penalty.reason == reason,
            Penalty.status != PenaltyStatus.CANCELLED,
        )
    )


def _params(penalty: Penalty) -> dict[str, object]:
    return {
        "penalty_id": penalty.id,
        "code": penalty.barrel.code,
        "amount": f"{penalty.amount:.2f}",
        "reason": penalty.reason.value,
        "username": penalty.user.username,
    }


def create_penalty(
    db: Session, *, loan: Loan, reason: PenaltyReason, actor: User | None
) -> Penalty | None:
    """Add a penalty to the current transaction; returns None when one already exists.
    The caller commits."""
    if active_penalty(db, loan, reason) is not None:
        return None
    penalty = Penalty(
        user_id=loan.user_id,
        loan_id=loan.id,
        barrel_id=loan.barrel_id,
        reason=reason,
        amount=settings_service.get_decimal(db, "penalty_amount"),
        status=PenaltyStatus.UNPAID,
    )
    db.add(penalty)
    db.flush()
    db.refresh(penalty)
    audit.record(
        db,
        actor=actor,
        action="penalty.created",
        entity_type="penalty",
        entity_id=penalty.id,
        after={
            "user": penalty.user.username,
            "barrel": penalty.barrel.code,
            "reason": reason.value,
            "amount": str(penalty.amount),
            "loan_id": loan.id,
        },
    )
    notifications.notify(
        db, penalty.user, "notification.penalty.created", _params(penalty), "/penalties"
    )
    return penalty


def _close_order_if_done(db: Session, loan: Loan) -> None:
    # Local import: orders imports this module's siblings, avoid a cycle at import time.
    from app.services import orders

    orders.close_if_all_returned(db, loan.order)


def record_payment(db: Session, *, actor: User, penalty: Penalty, note: str = "") -> Penalty:
    """FR-VR-05/06: mark paid. Paying for a barrel that is still out marks it lost (BR-06)."""
    if penalty.status is not PenaltyStatus.UNPAID:
        raise InvalidPenaltyTransition(status=penalty.status.value)
    penalty.status = PenaltyStatus.PAID
    penalty.paid_at = dates.now_utc()
    penalty.paid_by = actor.id
    penalty.payment_note = note.strip() or None
    audit.record(
        db,
        actor=actor,
        action="penalty.paid",
        entity_type="penalty",
        entity_id=penalty.id,
        before={"status": PenaltyStatus.UNPAID.value},
        after={"status": PenaltyStatus.PAID.value, "note": penalty.payment_note},
    )

    loan = penalty.loan
    if penalty.reason is PenaltyReason.OVERDUE and loan.status in OUTSTANDING_LOAN_STATUSES:
        # The user no longer has to return the barrel.
        loan.status = LoanStatus.LOST
        loan.returned_at = penalty.paid_at
        loan.returned_by = actor.id
        barrel_state.transition(
            db,
            loan.barrel,
            BarrelStatus.LOST,
            actor=actor,
            reason=Reason.PENALTY_PAID,
            note=f"penalty #{penalty.id}",
            loan_id=loan.id,
        )
        _close_order_if_done(db, loan)
    notifications.notify(
        db, penalty.user, "notification.penalty.paid", _params(penalty), "/penalties"
    )
    db.commit()
    return penalty


def cancel_penalty(db: Session, *, actor: User, penalty: Penalty, reason: str) -> Penalty:
    """FR-VR-07: cancellation with a mandatory reason. The original record stays."""
    if penalty.status is not PenaltyStatus.UNPAID:
        raise InvalidPenaltyTransition(status=penalty.status.value)
    if not reason.strip():
        raise ReasonRequired()
    penalty.status = PenaltyStatus.CANCELLED
    penalty.cancelled_at = dates.now_utc()
    penalty.cancelled_by = actor.id
    penalty.cancel_reason = reason.strip()
    audit.record(
        db,
        actor=actor,
        action="penalty.cancelled",
        entity_type="penalty",
        entity_id=penalty.id,
        before={"status": PenaltyStatus.UNPAID.value},
        after={"status": PenaltyStatus.CANCELLED.value, "reason": penalty.cancel_reason},
    )
    notifications.notify(
        db,
        penalty.user,
        "notification.penalty.cancelled",
        {**_params(penalty), "note": penalty.cancel_reason},
        "/penalties",
    )
    db.commit()
    return penalty


def list_penalties(
    db: Session, *, user_id: int | None = None, status: PenaltyStatus | None = None
) -> list[Penalty]:
    stmt = select(Penalty)
    if user_id is not None:
        stmt = stmt.where(Penalty.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Penalty.status == status)
    return list(db.scalars(stmt.order_by(Penalty.status, Penalty.created_at.desc())))


def unpaid_total(db: Session, user_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Penalty.amount), 0)).where(
            Penalty.user_id == user_id, Penalty.status == PenaltyStatus.UNPAID
        )
    )
    return Decimal(str(total or 0)).quantize(Decimal("0.01"))
