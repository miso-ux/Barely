"""Loan lifecycle run by the daily job: overdue marking with penalties and due-date reminders
(FR-VR-04, FR-VR-09, NFR-06). Both steps are idempotent."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.models import Loan, LoanStatus, PenaltyReason
from app.services import audit, dates, notifications, penalties
from app.services import settings as settings_service


def _loan_params(loan: Loan, today: date) -> dict[str, object]:
    return {
        "code": loan.barrel.code,
        "order_id": loan.order_id,
        "due_date": dates.format_date(loan.due_date),
        "username": loan.user.username,
        "days": (today - loan.due_date).days,
    }


def mark_overdue(db: Session, *, today: date | None = None) -> list[Loan]:
    """Day after the due date: loan -> overdue, penalty created, user and warehouse notified."""
    today = today or dates.today_local()
    due = db.scalars(
        select(Loan).where(Loan.status == LoanStatus.ON_LOAN, Loan.due_date < today)
    ).all()
    for loan in due:
        loan.status = LoanStatus.OVERDUE
        audit.record(
            db,
            actor=None,
            action="loan.overdue",
            entity_type="loan",
            entity_id=loan.id,
            before={"status": LoanStatus.ON_LOAN.value},
            after={"status": LoanStatus.OVERDUE.value, "due_date": loan.due_date.isoformat()},
        )
        penalties.create_penalty(db, loan=loan, reason=PenaltyReason.OVERDUE, actor=None)
        params = _loan_params(loan, today)
        notifications.notify(
            db, loan.user, "notification.loan.overdue", params, f"/orders/{loan.order_id}"
        )
        notifications.notify_permission_holders(
            db, Perm.DEBTORS_READ, "notification.debtor.new", params, "/debtors"
        )
    db.commit()
    return list(due)


def send_due_reminders(db: Session, *, today: date | None = None) -> list[Loan]:
    """FR-VR-09: one reminder per loan, `due_reminder_days` before the due date."""
    today = today or dates.today_local()
    horizon = today + timedelta(days=settings_service.get_int(db, "due_reminder_days"))
    upcoming = db.scalars(
        select(Loan).where(
            Loan.status == LoanStatus.ON_LOAN,
            Loan.reminder_sent_at.is_(None),
            Loan.due_date >= today,
            Loan.due_date <= horizon,
        )
    ).all()
    now = dates.now_utc()
    for loan in upcoming:
        loan.reminder_sent_at = now
        notifications.notify(
            db,
            loan.user,
            "notification.loan.due_soon",
            _loan_params(loan, today),
            f"/orders/{loan.order_id}",
        )
    db.commit()
    return list(upcoming)
