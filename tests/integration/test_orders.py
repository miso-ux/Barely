from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    AuditLog,
    Barrel,
    BarrelStatus,
    Loan,
    LoanStatus,
    Notification,
    Order,
    OrderStatus,
    User,
)
from app.services import dates, stock
from app.services import notifications as notifications_service
from app.services import orders as orders_service
from app.services import settings as settings_service
from app.services.errors import InvalidOrderTransition, NotEnoughFree
from app.services.orders import CancelReason
from tests.conftest import login

TODAY = dates.today_local()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _order(db: Session, order_id: int) -> Order:
    db.expire_all()
    return db.get(Order, order_id)


def _latest_order(db: Session) -> Order:
    db.expire_all()
    return db.scalar(select(Order).order_by(Order.id.desc()).limit(1))


def _post_order(client: TestClient, quantity: int, date: str = TOMORROW, note: str = ""):
    return client.post(
        "/orders/new", data={"quantity": str(quantity), "requested_date": date, "note": note}
    )


# --- seed ---------------------------------------------------------------------


def test_seed_orders_and_reservations(db: Session) -> None:
    statuses = sorted(o.status.value for o in db.scalars(select(Order)))
    assert statuses == ["issued", "pending", "pending"]
    assert stock.reserved_count(db) == 5
    # 26 in stock before seed orders, 2 issued -> 24 in stock, 5 reserved -> 19 free
    assert stock.in_stock_count(db) == 24
    assert stock.free_count(db) == 19


# --- creating orders ----------------------------------------------------------


def test_user_creates_order_and_warehouse_is_notified(client: TestClient, db: Session) -> None:
    login(client, "user")
    before = notifications_service.unread_count(db, _user(db, "warehouse"))
    response = _post_order(client, 2, note="Ďakujem")
    assert response.status_code == 303, response.text
    order = _latest_order(db)
    assert order.status is OrderStatus.PENDING
    assert order.quantity == 2
    assert order.note == "Ďakujem"
    assert order.created_by == order.user_id
    assert stock.reserved_count(db) == 7
    assert notifications_service.unread_count(db, _user(db, "warehouse")) == before + 1
    # The supervisor has no orders.manage permission and must not be notified.
    assert notifications_service.unread_count(db, _user(db, "supervisor")) == 0
    page = client.get(f"/orders/{order.id}")
    assert page.status_code == 200 and "Čaká" in page.text


def test_order_limit_is_enforced(client: TestClient) -> None:
    login(client, "user")
    response = _post_order(client, 6)
    assert response.status_code == 400
    assert "najviac 5 kusov" in response.text
    assert _post_order(client, 0).status_code == 400


def test_order_cannot_exceed_free_barrels(client: TestClient, db: Session) -> None:
    login(client, "user")
    settings_service.update(db, actor=_user(db, "admin"), key="max_items_per_order", raw="50")
    response = _post_order(client, 20)  # 19 free
    assert response.status_code == 400
    assert "Voľných je 19" in response.text
    assert _post_order(client, 19).status_code == 303
    assert stock.free_count(db) == 0


def test_order_date_rules(client: TestClient) -> None:
    login(client, "user")
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    assert _post_order(client, 1, yesterday).status_code == 400
    too_far = (TODAY + timedelta(days=31)).isoformat()
    assert _post_order(client, 1, too_far).status_code == 400
    assert _post_order(client, 1, TODAY.isoformat()).status_code == 303
    assert _post_order(client, 1, (TODAY + timedelta(days=30)).isoformat()).status_code == 303


def test_user_cancels_own_order_and_reservation_is_released(
    client: TestClient, db: Session
) -> None:
    login(client, "user")
    _post_order(client, 3)
    order = _latest_order(db)
    reserved_before = stock.reserved_count(db)
    assert client.post(f"/orders/{order.id}/cancel").status_code == 303
    order = _order(db, order.id)
    assert order.status is OrderStatus.CANCELLED
    assert order.cancel_reason == CancelReason.BY_USER
    assert order.cancelled_by == order.user_id
    assert stock.reserved_count(db) == reserved_before - 3
    # Cancelling again is not a valid transition.
    client.post(f"/orders/{order.id}/cancel")
    assert "nie je pre aktuálny stav" in client.get(f"/orders/{order.id}").text


def test_users_only_see_their_own_orders(client: TestClient, db: Session) -> None:
    login(client, "user")
    page = client.get("/orders")
    assert page.status_code == 200
    assert "jana.novakova" not in page.text
    jana_order = db.scalar(
        select(Order).join(User, User.id == Order.user_id).where(User.username == "jana.novakova")
    )
    assert client.get(f"/orders/{jana_order.id}").status_code == 403
    assert client.post(f"/orders/{jana_order.id}/cancel").status_code == 403


# --- warehouse flow -----------------------------------------------------------


def test_prepare_then_issue_assigns_barrels_by_rule(client: TestClient, db: Session) -> None:
    login(client, "user")
    _post_order(client, 3)
    order = _latest_order(db)
    client.post("/logout")

    login(client, "warehouse")
    # Cannot issue before preparing.
    client.post(f"/orders/{order.id}/issue")
    assert _order(db, order.id).status is OrderStatus.PENDING
    assert client.post(f"/orders/{order.id}/ready").status_code == 303
    assert _order(db, order.id).status is OrderStatus.READY
    assert notifications_service.unread_count(db, _user(db, "user")) >= 1

    expected = orders_service.select_barrels_for_issue(db, 3, 10)
    expected_codes = [b.code for b in expected]
    db.rollback()  # release the FOR UPDATE locks taken by the preview query

    assert client.post(f"/orders/{order.id}/issue").status_code == 303
    order = _order(db, order.id)
    assert order.status is OrderStatus.ISSUED
    assert order.issued_by == _user(db, "warehouse").id
    assert [loan.barrel.code for loan in order.loans] == expected_codes
    counts = [loan.barrel.loan_count for loan in order.loans]
    assert counts == sorted(counts, reverse=True)
    for loan in order.loans:
        assert loan.barrel.status is BarrelStatus.ON_LOAN
        assert loan.loan_sequence == loan.barrel.loan_count
        assert loan.status is LoanStatus.ON_LOAN
        assert loan.due_date == dates.due_date_for(loan.issued_at)
        assert loan.loan_price == Decimal("0.00")
        history = loan.barrel.history[-1]
        assert history.to_status is BarrelStatus.ON_LOAN and history.loan_id == loan.id
    page = client.get(f"/orders/{order.id}")
    assert "Pridelené barely" in page.text
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "order.issued", AuditLog.entity_id == str(order.id)
        )
    )
    assert audit.after["barrels"] == expected_codes


def test_issue_prefers_highest_loan_count_then_oldest(db: Session) -> None:
    # Make the stock predictable: every seeded barrel drops to zero loans, so the new ones
    # with higher counts must be chosen first.
    db.execute(update(Barrel).values(loan_count=0))
    barrels = []
    for code, count in (("Z-1", 2), ("Z-2", 2), ("Z-3", 1), ("Z-4", 3)):
        barrel = Barrel(code=code, status=BarrelStatus.IN_STOCK, loan_count=count)
        db.add(barrel)
        barrels.append(barrel)
    db.commit()
    picked = orders_service.select_barrels_for_issue(db, 3, loan_limit=3)
    db.rollback()
    codes = [b.code for b in picked]
    # Z-4 has reached the limit and is skipped; Z-1 wins the tie against Z-2 by age (id).
    assert codes[:2] == ["Z-1", "Z-2"]
    assert codes[2] == "Z-3"
    assert "Z-4" not in codes


def test_issue_skips_non_issuable_statuses(db: Session) -> None:
    picked = orders_service.select_barrels_for_issue(db, 100, loan_limit=10)
    db.rollback()
    assert all(b.status is BarrelStatus.IN_STOCK for b in picked)
    assert all(b.loan_count < 10 for b in picked)


def test_loan_price_is_frozen_at_issue(client: TestClient, db: Session) -> None:
    admin = _user(db, "admin")
    settings_service.update(db, actor=admin, key="loan_price", raw="1.50")
    login(client, "user")
    _post_order(client, 1)
    order = _latest_order(db)
    client.post("/logout")
    login(client, "warehouse")
    client.post(f"/orders/{order.id}/ready")
    client.post(f"/orders/{order.id}/issue")
    loan = _order(db, order.id).loans[0]
    assert loan.loan_price == Decimal("1.50")
    settings_service.update(db, actor=admin, key="loan_price", raw="9.99")
    db.expire_all()
    assert db.get(Loan, loan.id).loan_price == Decimal("1.50")


def test_issue_fails_cleanly_when_stock_vanished(db: Session) -> None:
    warehouse = _user(db, "warehouse")
    order = orders_service.place_order(
        db, user=_user(db, "peter.horvath"), quantity=4, requested_date=TODAY
    )
    orders_service.mark_ready(db, actor=warehouse, order=order)
    # Everything in stock disappears before pickup.
    for barrel in db.scalars(select(Barrel).where(Barrel.status == BarrelStatus.IN_STOCK)):
        barrel.status = BarrelStatus.LOST
    db.commit()
    with pytest.raises(NotEnoughFree):
        orders_service.issue_order(db, actor=warehouse, order=order)
    assert _order(db, order.id).status is OrderStatus.READY
    assert db.scalar(select(Loan).where(Loan.order_id == order.id)) is None


def test_concurrent_issues_never_share_a_barrel(db: Session) -> None:
    """Two warehouse workers issue two orders at the same time. SKIP LOCKED must hand each
    transaction distinct barrels."""
    warehouse = _user(db, "warehouse")
    order_ids = []
    for username in ("jana.novakova", "peter.horvath"):
        order = orders_service.place_order(
            db, user=_user(db, username), quantity=5, requested_date=TODAY
        )
        orders_service.mark_ready(db, actor=warehouse, order=order)
        order_ids.append(order.id)

    def issue(order_id: int) -> list[int]:
        with SessionLocal() as session:
            actor = session.scalar(select(User).where(User.username == "warehouse"))
            order = session.get(Order, order_id)
            loans = orders_service.issue_order(session, actor=actor, order=order)
            return [loan.barrel_id for loan in loans]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, order_ids))

    first, second = results
    assert len(first) == 5 and len(second) == 5
    assert not set(first) & set(second)
    for order_id in order_ids:
        assert _order(db, order_id).status is OrderStatus.ISSUED


def test_warehouse_can_cancel_any_open_order(client: TestClient, db: Session) -> None:
    login(client, "warehouse")
    pending = db.scalar(select(Order).where(Order.status == OrderStatus.PENDING))
    assert client.post(f"/orders/{pending.id}/cancel").status_code == 303
    order = _order(db, pending.id)
    assert order.status is OrderStatus.CANCELLED
    assert order.cancel_reason == CancelReason.BY_WAREHOUSE
    owner_unread = db.scalars(
        select(Notification).where(
            Notification.user_id == order.user_id,
            Notification.kind == "notification.order.cancelled_by_warehouse",
        )
    ).all()
    assert len(owner_unread) == 1


def test_order_transition_table() -> None:
    T = orders_service.ORDER_TRANSITIONS
    assert T[OrderStatus.PENDING] == {OrderStatus.READY, OrderStatus.CANCELLED}
    assert T[OrderStatus.READY] == {OrderStatus.ISSUED, OrderStatus.CANCELLED}
    assert T[OrderStatus.ISSUED] == {OrderStatus.CLOSED}
    assert not T[OrderStatus.CLOSED] and not T[OrderStatus.CANCELLED]


def test_issued_order_cannot_be_cancelled(db: Session) -> None:
    issued = db.scalar(select(Order).where(Order.status == OrderStatus.ISSUED))
    with pytest.raises(InvalidOrderTransition):
        orders_service.cancel_order(
            db, actor=_user(db, "warehouse"), order=issued, reason=CancelReason.BY_WAREHOUSE
        )


# --- reservation expiry (Q-03) ------------------------------------------------


def test_stale_reservations_expire_after_working_days(db: Session) -> None:
    pending = db.scalars(select(Order).where(Order.status == OrderStatus.PENDING)).all()
    assert pending
    latest_pickup = max(o.requested_date for o in pending)
    # Day after the validity window of the latest pickup: everything open expires.
    far_future = dates.add_working_days(latest_pickup, 3) + timedelta(days=1)
    expired = orders_service.expire_reservations(db, today=far_future)
    assert {o.id for o in expired} == {o.id for o in pending}
    db.expire_all()
    for order in pending:
        refreshed = db.get(Order, order.id)
        assert refreshed.status is OrderStatus.CANCELLED
        assert refreshed.cancel_reason == CancelReason.EXPIRED
        assert refreshed.cancelled_by is None
    assert stock.reserved_count(db) == 0
    # Running it on the pickup day itself changes nothing.
    assert orders_service.expire_reservations(db, today=latest_pickup) == []


# --- dashboards ---------------------------------------------------------------


def test_warehouse_dashboard_lists_pickups_by_date(client: TestClient) -> None:
    login(client, "warehouse")
    page = client.get("/warehouse")
    assert page.status_code == 200
    assert "Objednávky na vyzdvihnutie podľa dátumu" in page.text
    assert "Žiadosti o výnimku (1)" in page.text


def test_user_dashboard_shows_free_count_and_loans(client: TestClient) -> None:
    login(client, "user")
    page = client.get("/")
    assert page.status_code == 200
    assert "Voľné barely" in page.text
    assert "Požičané barely" in page.text
    assert "Vrátiť do" in page.text
