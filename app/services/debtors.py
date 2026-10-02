"""Debtors (BR-15, FR-VR-08): anyone with an overdue loan or an unpaid penalty.

A loan counts as overdue once the daily job has marked it (FR-VR-04); that is also when the
penalty is created, so both signals appear together.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Loan, LoanStatus, Penalty, PenaltyStatus, User
from app.services import dates


@dataclass
class DebtorRow:
    user: User
    overdue_loans: int
    unpaid_amount: Decimal
    days_overdue: int


def is_debtor(db: Session, user: User) -> bool:
    overdue = db.scalar(
        select(Loan.id).where(Loan.user_id == user.id, Loan.status == LoanStatus.OVERDUE).limit(1)
    )
    if overdue is not None:
        return True
    unpaid = db.scalar(
        select(Penalty.id)
        .where(Penalty.user_id == user.id, Penalty.status == PenaltyStatus.UNPAID)
        .limit(1)
    )
    return unpaid is not None


def list_debtors(db: Session, *, today: date | None = None) -> list[DebtorRow]:
    today = today or dates.today_local()
    rows: dict[int, DebtorRow] = {}

    def row(user: User) -> DebtorRow:
        if user.id not in rows:
            rows[user.id] = DebtorRow(
                user=user, overdue_loans=0, unpaid_amount=Decimal("0.00"), days_overdue=0
            )
        return rows[user.id]

    for loan in db.scalars(select(Loan).where(Loan.status == LoanStatus.OVERDUE)):
        entry = row(loan.user)
        entry.overdue_loans += 1
        entry.days_overdue = max(entry.days_overdue, (today - loan.due_date).days)
    for penalty in db.scalars(select(Penalty).where(Penalty.status == PenaltyStatus.UNPAID)):
        entry = row(penalty.user)
        entry.unpaid_amount += penalty.amount

    return sorted(rows.values(), key=lambda r: (-r.days_overdue, -r.unpaid_amount, r.user.username))
