"""Returning barrels (FR-VR-01..03, BR-09/10, BR-16, Q-04, Q-05)."""

from typing import Final

from sqlalchemy.orm import Session

from app.models import BarrelStatus, Loan, LoanStatus, Order, OrderStatus, PenaltyReason, User
from app.services import audit, barrel_state, dates, notifications, orders, penalties
from app.services import settings as settings_service
from app.services.barrel_state import Reason
from app.services.errors import InvalidReturnCondition, NothingToReturn


class Condition:
    OK: Final = "ok"
    DAMAGED: Final = "damaged"
    LOST: Final = "lost"


CONDITIONS: Final[frozenset[str]] = frozenset({Condition.OK, Condition.DAMAGED, Condition.LOST})
OUTSTANDING: Final = (LoanStatus.ON_LOAN, LoanStatus.OVERDUE)


def outstanding_loans(order: Order) -> list[Loan]:
    return [loan for loan in order.loans if loan.status in OUTSTANDING]


def return_barrels(
    db: Session,
    *,
    actor: User,
    order: Order,
    conditions: dict[int, str],
    note: str = "",
) -> list[Loan]:
    """Process the loans named in `conditions` (loan id -> ok / damaged / lost).

    ok      -> barrel back in stock, or retired when it has reached the loan limit (BR-09).
    damaged -> barrel damaged + penalty right away (BR-05); always written off later (Q-04).
    lost    -> barrel lost + penalty (BR-16).
    An overdue penalty that already exists stays (Q-05). The order closes when nothing is out.
    """
    if order.status is not OrderStatus.ISSUED:
        raise NothingToReturn()
    by_id = {loan.id: loan for loan in outstanding_loans(order)}
    selected = {loan_id: cond for loan_id, cond in conditions.items() if loan_id in by_id}
    if not selected:
        raise NothingToReturn()
    for cond in selected.values():
        if cond not in CONDITIONS:
            raise InvalidReturnCondition(condition=cond)

    loan_limit = settings_service.get_int(db, "loan_limit")
    now = dates.now_utc()
    note = note.strip() or None
    processed: list[Loan] = []
    new_penalties: list[PenaltyReason] = []

    for loan_id, cond in selected.items():
        loan = by_id[loan_id]
        loan.returned_at = now
        loan.returned_by = actor.id
        loan.return_note = note
        if cond == Condition.OK:
            loan.status = LoanStatus.RETURNED
            if loan.barrel.loan_count >= loan_limit:
                barrel_state.transition(
                    db,
                    loan.barrel,
                    BarrelStatus.RETIRED,
                    actor=actor,
                    reason=Reason.RETIRED,
                    note=note,
                    loan_id=loan.id,
                )
            else:
                barrel_state.transition(
                    db,
                    loan.barrel,
                    BarrelStatus.IN_STOCK,
                    actor=actor,
                    reason=Reason.RETURNED,
                    note=note,
                    loan_id=loan.id,
                )
        elif cond == Condition.DAMAGED:
            loan.status = LoanStatus.RETURNED_DAMAGED
            barrel_state.transition(
                db,
                loan.barrel,
                BarrelStatus.DAMAGED,
                actor=actor,
                reason=Reason.RETURNED_DAMAGED,
                note=note,
                loan_id=loan.id,
            )
            if penalties.create_penalty(db, loan=loan, reason=PenaltyReason.DAMAGED, actor=actor):
                new_penalties.append(PenaltyReason.DAMAGED)
        else:
            loan.status = LoanStatus.LOST
            barrel_state.transition(
                db,
                loan.barrel,
                BarrelStatus.LOST,
                actor=actor,
                reason=Reason.LOST,
                note=note,
                loan_id=loan.id,
            )
            if penalties.create_penalty(db, loan=loan, reason=PenaltyReason.LOST, actor=actor):
                new_penalties.append(PenaltyReason.LOST)
        audit.record(
            db,
            actor=actor,
            action="loan.returned",
            entity_type="loan",
            entity_id=loan.id,
            after={"condition": cond, "barrel": loan.barrel.code, "status": loan.status.value},
        )
        processed.append(loan)

    closed = orders.close_if_all_returned(db, order)
    notifications.notify(
        db,
        order.user,
        "notification.loan.returned",
        {
            "order_id": order.id,
            "codes": ", ".join(loan.barrel.code for loan in processed),
            "count": len(processed),
            "closed": "1" if closed else "0",
        },
        f"/orders/{order.id}",
    )
    db.commit()
    return processed
