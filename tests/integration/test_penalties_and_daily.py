from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import daily
from app.models import (
    BarrelStatus,
    Loan,
    LoanStatus,
    Notification,
    Order,
    OrderStatus,
    Penalty,
    PenaltyReason,
    PenaltyStatus,
    User,
)
from app.services import dates, debtors
from app.services import loans as loans_service
from app.services import notifications as notifications_service
from app.services import orders as orders_service
from app.services import penalties as penalties_service
from app.services import settings as settings_service
from app.services.errors import DebtorBlocked, InvalidPenaltyTransition, ReasonRequired
from tests.conftest import login

TODAY = dates.today_local()


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _backdated_loan(db: Session) -> Loan:
    db.expire_all()
    return db.scalar(select(Loan).where(Loan.due_date < TODAY))


# --- daily job: overdue -------------------------------------------------------


def test_daily_job_marks_overdue_creates_penalty_once_and_notifies(db: Session) -> None:
    loan = _backdated_loan(db)
    assert loan.status is LoanStatus.ON_LOAN
    user = _user(db, "user")
    warehouse = _user(db, "warehouse")
    user_unread = notifications_service.unread_count(db, user)
    warehouse_unread = notifications_service.unread_count(db, warehouse)

    summary = daily.run_with_session(db, today=TODAY)
    assert summary["overdue_loans"] == 1
    db.expire_all()
    loan = db.get(Loan, loan.id)
    assert loan.status is LoanStatus.OVERDUE
    penalties = db.scalars(select(Penalty).where(Penalty.loan_id == loan.id)).all()
    assert len(penalties) == 1
    assert penalties[0].reason is PenaltyReason.OVERDUE
    assert penalties[0].amount == Decimal("10.00")
    assert notifications_service.unread_count(db, user) == user_unread + 2  # overdue + penalty
    assert notifications_service.unread_count(db, warehouse) == warehouse_unread + 1
    assert debtors.is_debtor(db, user) is True

    # Idempotent: a second run on the same day does nothing more.
    summary = daily.run_with_session(db, today=TODAY)
    assert summary["overdue_loans"] == 0
    assert len(db.scalars(select(Penalty).where(Penalty.loan_id == loan.id)).all()) == 1


def test_daily_job_does_not_touch_loans_due_today(db: Session) -> None:
    loan = _backdated_loan(db)
    loan.due_date = TODAY
    db.commit()
    assert daily.run_with_session(db, today=TODAY)["overdue_loans"] == 0
    assert daily.run_with_session(db, today=TODAY + timedelta(days=1))["overdue_loans"] == 1


def test_daily_job_sends_reminder_once_before_due_date(db: Session) -> None:
    loan = _backdated_loan(db)
    loan.due_date = TODAY + timedelta(days=5)  # within the default 7-day window
    db.commit()
    assert loans_service.send_due_reminders(db, today=TODAY) == [loan]
    db.refresh(loan)
    assert loan.reminder_sent_at is not None
    reminder = db.scalar(
        select(Notification).where(Notification.kind == "notification.loan.due_soon")
    )
    assert reminder.user_id == loan.user_id
    assert loans_service.send_due_reminders(db, today=TODAY) == []


def test_reminder_window_respects_setting(db: Session) -> None:
    loan = _backdated_loan(db)
    loan.due_date = TODAY + timedelta(days=5)
    db.commit()
    settings_service.update(db, actor=_user(db, "admin"), key="due_reminder_days", raw="3")
    assert loans_service.send_due_reminders(db, today=TODAY) == []


# --- debtors ------------------------------------------------------------------


def test_debtor_is_blocked_from_ordering_until_setting_disabled(db: Session) -> None:
    daily.run_with_session(db, today=TODAY)
    user = _user(db, "user")
    with pytest.raises(DebtorBlocked):
        orders_service.place_order(db, user=user, quantity=1, requested_date=TODAY)
    settings_service.update(db, actor=_user(db, "admin"), key="block_debtors", raw="false")
    assert orders_service.place_order(db, user=user, quantity=1, requested_date=TODAY)


def test_debtor_list_shows_counts_and_days(client: TestClient, db: Session) -> None:
    daily.run_with_session(db, today=TODAY)
    rows = debtors.list_debtors(db, today=TODAY)
    assert [row.user.username for row in rows] == ["user"]
    assert rows[0].overdue_loans == 1
    assert rows[0].unpaid_amount == Decimal("10.00")
    assert rows[0].days_overdue == (TODAY - _backdated_loan(db).due_date).days > 0
    login(client, "warehouse")
    page = client.get("/debtors")
    assert page.status_code == 200 and "Používateľ Demo" in page.text
    login(client, "user")
    assert client.get("/debtors").status_code == 403
    dashboard = client.get("/")
    assert "Nové objednávky sú blokované" in dashboard.text


# --- payments and BR-06 -------------------------------------------------------


def test_paying_overdue_penalty_marks_barrel_lost_and_closes_loan(
    client: TestClient, db: Session
) -> None:
    daily.run_with_session(db, today=TODAY)
    penalty = db.scalar(select(Penalty).where(Penalty.reason == PenaltyReason.OVERDUE))
    login(client, "warehouse")
    response = client.post(f"/penalties/{penalty.id}/pay", data={"note": "hotovosť"})
    assert response.status_code == 303
    db.expire_all()
    penalty = db.get(Penalty, penalty.id)
    assert penalty.status is PenaltyStatus.PAID
    assert penalty.paid_by == _user(db, "warehouse").id
    assert penalty.payment_note == "hotovosť"
    loan = db.get(Loan, penalty.loan_id)
    assert loan.status is LoanStatus.LOST
    assert loan.barrel.status is BarrelStatus.LOST
    assert loan.barrel.history[-1].reason == "penalty_paid"
    assert loan.barrel.history[-1].loan_id == loan.id
    assert debtors.is_debtor(db, _user(db, "user")) is False
    # The other loan of the order is still out, so the order stays issued.
    assert db.get(Order, loan.order_id).status is OrderStatus.ISSUED


def test_paying_damage_penalty_does_not_touch_barrel(db: Session) -> None:
    from app.services import returns

    warehouse = _user(db, "warehouse")
    order = orders_service.place_order(
        db, user=_user(db, "peter.horvath"), quantity=1, requested_date=TODAY
    )
    orders_service.mark_ready(db, actor=warehouse, order=order)
    orders_service.issue_order(db, actor=warehouse, order=order)
    db.expire_all()
    order = db.get(Order, order.id)
    loan = order.loans[0]
    returns.return_barrels(db, actor=warehouse, order=order, conditions={loan.id: "damaged"})
    penalty = db.scalar(select(Penalty).where(Penalty.loan_id == loan.id))
    penalties_service.record_payment(db, actor=warehouse, penalty=penalty)
    db.expire_all()
    assert db.get(Loan, loan.id).barrel.status is BarrelStatus.DAMAGED
    assert db.get(Order, order.id).status is OrderStatus.CLOSED


def test_cancel_penalty_requires_reason_and_keeps_record(client: TestClient, db: Session) -> None:
    daily.run_with_session(db, today=TODAY)
    penalty = db.scalar(select(Penalty).where(Penalty.status == PenaltyStatus.UNPAID))
    warehouse = _user(db, "warehouse")
    with pytest.raises(ReasonRequired):
        penalties_service.cancel_penalty(db, actor=warehouse, penalty=penalty, reason="  ")
    login(client, "warehouse")
    client.post(f"/penalties/{penalty.id}/cancel", data={"reason": "Barel sa našiel v kuchynke"})
    db.expire_all()
    penalty = db.get(Penalty, penalty.id)
    assert penalty.status is PenaltyStatus.CANCELLED
    assert penalty.cancel_reason == "Barel sa našiel v kuchynke"
    assert penalty.cancelled_by == warehouse.id
    with pytest.raises(InvalidPenaltyTransition):
        penalties_service.record_payment(db, actor=warehouse, penalty=penalty)
    # A new overdue penalty may be created again later (unique index excludes cancelled rows).
    loan = db.get(Loan, penalty.loan_id)
    assert penalties_service.create_penalty(db, loan=loan, reason=PenaltyReason.OVERDUE, actor=None)


def test_user_sees_own_penalties_only(client: TestClient, db: Session) -> None:
    daily.run_with_session(db, today=TODAY)
    penalty = db.scalar(select(Penalty).where(Penalty.status == PenaltyStatus.UNPAID))
    login(client, "user")
    page = client.get("/penalties")
    assert page.status_code == 200
    assert "10.00 €" in page.text
    assert "Zaplatené na mieste" not in page.text
    assert client.post(f"/penalties/{penalty.id}/pay").status_code == 403
    assert client.post(f"/penalties/{penalty.id}/cancel", data={"reason": "x"}).status_code == 403
    client.post("/logout")
    login(client, "jana.novakova")
    assert "10.00 €" not in client.get("/penalties").text


def test_warehouse_runs_daily_job_from_dashboard(client: TestClient, db: Session) -> None:
    login(client, "warehouse")
    assert client.post("/warehouse/run-daily").status_code == 303
    page = client.get("/warehouse")
    assert "Denná úloha prebehla" in page.text
    assert "1 výpožičiek po lehote" in page.text
    assert db.scalar(select(Loan).where(Loan.status == LoanStatus.OVERDUE)) is not None


def test_supervisor_reads_penalties_and_debtors(client: TestClient, db: Session) -> None:
    daily.run_with_session(db, today=TODAY)
    login(client, "supervisor")
    assert client.get("/penalties").status_code == 200
    assert client.get("/debtors").status_code == 200
    assert client.post("/warehouse/run-daily").status_code == 403
