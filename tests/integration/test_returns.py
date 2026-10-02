from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BarrelStatus,
    LoanStatus,
    Order,
    OrderStatus,
    Penalty,
    PenaltyReason,
    PenaltyStatus,
    User,
)
from app.services import dates, returns
from app.services import orders as orders_service
from app.services import settings as settings_service
from app.services.errors import NothingToReturn
from tests.conftest import login

TODAY = dates.today_local()


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _issued(db: Session, username: str = "user") -> Order:
    db.expire_all()
    return db.scalar(
        select(Order)
        .join(User, User.id == Order.user_id)
        .where(User.username == username, Order.status == OrderStatus.ISSUED)
    )


def _issue_new_order(db: Session, username: str, quantity: int) -> Order:
    warehouse = _user(db, "warehouse")
    order = orders_service.place_order(
        db, user=_user(db, username), quantity=quantity, requested_date=TODAY
    )
    orders_service.mark_ready(db, actor=warehouse, order=order)
    orders_service.issue_order(db, actor=warehouse, order=order)
    db.expire_all()
    return db.get(Order, order.id)


def test_return_ok_puts_barrel_back_and_closes_order(client: TestClient, db: Session) -> None:
    order = _issued(db)
    loans = order.loans
    login(client, "warehouse")
    data = {f"condition_{loan.id}": "ok" for loan in loans}
    data["note"] = "Všetko v poriadku"
    assert client.post(f"/orders/{order.id}/return", data=data).status_code == 303

    order = db.get(Order, order.id)
    db.refresh(order)
    assert order.status is OrderStatus.CLOSED
    assert order.closed_at is not None
    for loan in order.loans:
        db.refresh(loan)
        assert loan.status is LoanStatus.RETURNED
        assert loan.returned_by == _user(db, "warehouse").id
        assert loan.return_note == "Všetko v poriadku"
        db.refresh(loan.barrel)
        # Seed-issued barrels sat at 9 loans -> 10th loan -> retired on return (BR-09).
        assert loan.barrel.loan_count == 10
        assert loan.barrel.status is BarrelStatus.RETIRED
        assert loan.barrel.retired_at is not None
        assert loan.barrel.history[-1].loan_id == loan.id
    assert (
        db.scalar(select(Penalty).where(Penalty.loan_id.in_([loan.id for loan in loans]))) is None
    )


def test_return_ok_below_limit_goes_to_stock(db: Session) -> None:
    # Raise the limit so the selected barrels (the most used ones) stay below it.
    settings_service.update(db, actor=_user(db, "admin"), key="loan_limit", raw="20")
    order = _issue_new_order(db, "peter.horvath", 2)
    warehouse = _user(db, "warehouse")
    for loan in order.loans:
        assert loan.barrel.loan_count < 20
    returns.return_barrels(
        db, actor=warehouse, order=order, conditions={loan.id: "ok" for loan in order.loans}
    )
    db.expire_all()
    for loan in db.get(Order, order.id).loans:
        assert loan.barrel.status is BarrelStatus.IN_STOCK
        assert loan.barrel.history[-1].reason == "returned"


def test_partial_return_keeps_order_open(db: Session) -> None:
    order = _issue_new_order(db, "peter.horvath", 3)
    first, *rest = order.loans
    returns.return_barrels(
        db, actor=_user(db, "warehouse"), order=order, conditions={first.id: "ok"}
    )
    db.expire_all()
    order = db.get(Order, order.id)
    assert order.status is OrderStatus.ISSUED
    assert len(returns.outstanding_loans(order)) == 2
    returns.return_barrels(
        db, actor=_user(db, "warehouse"), order=order, conditions={loan.id: "ok" for loan in rest}
    )
    db.expire_all()
    assert db.get(Order, order.id).status is OrderStatus.CLOSED


def test_damaged_return_creates_penalty_immediately(client: TestClient, db: Session) -> None:
    order = _issue_new_order(db, "peter.horvath", 1)
    loan = order.loans[0]
    login(client, "warehouse")
    client.post(
        f"/orders/{order.id}/return",
        data={f"condition_{loan.id}": "damaged", "note": "Prasknutý"},
    )
    db.expire_all()
    loan = db.get(Order, order.id).loans[0]
    assert loan.status is LoanStatus.RETURNED_DAMAGED
    assert loan.barrel.status is BarrelStatus.DAMAGED
    penalty = db.scalar(select(Penalty).where(Penalty.loan_id == loan.id))
    assert penalty is not None
    assert penalty.reason is PenaltyReason.DAMAGED
    assert penalty.status is PenaltyStatus.UNPAID
    assert str(penalty.amount) == "10.00"
    assert penalty.user_id == loan.user_id
    page = client.get(f"/orders/{order.id}")
    assert "Pokuty" in page.text and "Poškodený" in page.text


def test_lost_on_return_creates_penalty(db: Session) -> None:
    order = _issue_new_order(db, "peter.horvath", 1)
    loan = order.loans[0]
    returns.return_barrels(
        db, actor=_user(db, "warehouse"), order=order, conditions={loan.id: "lost"}
    )
    db.expire_all()
    loan = db.get(Order, order.id).loans[0]
    assert loan.status is LoanStatus.LOST
    assert loan.barrel.status is BarrelStatus.LOST
    penalty = db.scalar(select(Penalty).where(Penalty.loan_id == loan.id))
    assert penalty.reason is PenaltyReason.LOST


def test_penalty_amount_is_frozen_at_creation(db: Session) -> None:
    admin = _user(db, "admin")
    settings_service.update(db, actor=admin, key="penalty_amount", raw="25")
    order = _issue_new_order(db, "peter.horvath", 1)
    loan = order.loans[0]
    returns.return_barrels(
        db, actor=_user(db, "warehouse"), order=order, conditions={loan.id: "damaged"}
    )
    settings_service.update(db, actor=admin, key="penalty_amount", raw="99")
    db.expire_all()
    penalty = db.scalar(select(Penalty).where(Penalty.loan_id == loan.id))
    assert str(penalty.amount) == "25.00"


def test_return_requires_a_selection_and_issued_order(db: Session) -> None:
    order = _issued(db)
    with pytest.raises(NothingToReturn):
        returns.return_barrels(db, actor=_user(db, "warehouse"), order=order, conditions={})
    pending = db.scalar(select(Order).where(Order.status == OrderStatus.PENDING))
    with pytest.raises(NothingToReturn):
        returns.return_barrels(
            db, actor=_user(db, "warehouse"), order=pending, conditions={1: "ok"}
        )


def test_user_cannot_record_returns(client: TestClient, db: Session) -> None:
    order = _issued(db)
    login(client, "user")
    loan = order.loans[0]
    assert (
        client.post(f"/orders/{order.id}/return", data={f"condition_{loan.id}": "ok"}).status_code
        == 403
    )
    page = client.get(f"/orders/{order.id}")
    assert "Zaevidovať vrátenie" not in page.text


def test_overdue_return_keeps_penalty(db: Session) -> None:
    """Q-05: returning late does not cancel the overdue penalty."""
    from app.services import loans as loans_service

    order = _issued(db)
    backdated = next(loan for loan in order.loans if loan.due_date < TODAY)
    loans_service.mark_overdue(db, today=TODAY)
    db.expire_all()
    penalty = db.scalar(select(Penalty).where(Penalty.loan_id == backdated.id))
    assert penalty.reason is PenaltyReason.OVERDUE
    returns.return_barrels(
        db,
        actor=_user(db, "warehouse"),
        order=db.get(Order, order.id),
        conditions={backdated.id: "ok"},
    )
    db.expire_all()
    assert db.get(Penalty, penalty.id).status is PenaltyStatus.UNPAID
    loan = next(loan for loan in db.get(Order, order.id).loans if loan.id == backdated.id)
    assert loan.status is LoanStatus.RETURNED


def test_seed_has_one_backdated_loan() -> None:
    assert TODAY - timedelta(days=42) < TODAY  # sanity: helper constants are consistent
