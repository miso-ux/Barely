from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    MovementReason,
    Order,
    OrderKind,
    OrderStatus,
    PumpProduct,
    PumpStockMovement,
    User,
)
from app.services import dates, stock
from app.services import notifications as notifications_service
from app.services import orders as orders_service
from app.services import pumps as pumps_service
from app.services.errors import (
    AlreadyPaid,
    InvalidOrderTransition,
    InvalidPrice,
    NotEnoughFree,
    ProductInactive,
    ProductNameTaken,
)
from tests.conftest import login

TODAY = dates.today_local()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _product(db: Session) -> PumpProduct:
    db.expire_all()
    return db.scalar(select(PumpProduct).order_by(PumpProduct.id))


def _pump_order(db: Session) -> Order:
    db.expire_all()
    return db.scalar(select(Order).where(Order.kind == OrderKind.PUMP).order_by(Order.id.desc()))


# --- seed and catalogue -----------------------------------------------------


def test_seed_pump_stock_and_reservation(db: Session) -> None:
    product = _product(db)
    assert product.name == "Ručná pumpa na barel"
    assert product.price == Decimal("12.50")
    assert product.stock == 15
    assert pumps_service.reserved(db, product.id) == 1
    assert pumps_service.free(db, product) == 14
    # Pump reservations never count against barrel stock.
    assert stock.reserved_count(db) == 5


def test_catalogue_views_by_role(client: TestClient) -> None:
    login(client, "user")
    page = client.get("/pumps")
    assert page.status_code == 200
    assert "Kúpiť pumpu" in page.text and "Nový typ pumpy" not in page.text
    client.post("/logout")
    login(client, "warehouse")
    page = client.get("/pumps")
    assert "Nový typ pumpy" in page.text and "Rezervované" in page.text


def test_warehouse_creates_and_updates_product(client: TestClient, db: Session) -> None:
    login(client, "warehouse")
    response = client.post("/pumps/new", data={"name": "Elektrická pumpa", "price": "29,90"})
    assert response.status_code == 303
    product = db.scalar(select(PumpProduct).where(PumpProduct.name == "Elektrická pumpa"))
    assert product.price == Decimal("29.90") and product.stock == 0 and product.is_active
    duplicate = client.post("/pumps/new", data={"name": "Elektrická pumpa", "price": "1"})
    assert duplicate.status_code == 400 and "už existuje" in duplicate.text
    bad_price = client.post("/pumps/new", data={"name": "X", "price": "abc"})
    assert bad_price.status_code == 400

    client.post(f"/pumps/{product.id}", data={"name": "Elektrická pumpa", "price": "31.00"})
    db.refresh(product)
    assert product.price == Decimal("31.00")
    assert product.is_active is False  # checkbox not sent -> deactivated
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "pump.updated"))
    assert audit.before["price"] == "29.90" and audit.after["price"] == "31.00"


def test_receive_stock_writes_movement(client: TestClient, db: Session) -> None:
    product = _product(db)
    login(client, "warehouse")
    client.post(f"/pumps/{product.id}/receive", data={"quantity": "5", "note": "Dodávka"})
    db.refresh(product)
    assert product.stock == 20
    movement = db.scalar(
        select(PumpStockMovement)
        .where(PumpStockMovement.product_id == product.id)
        .order_by(PumpStockMovement.id.desc())
    )
    assert movement.delta == 5 and movement.reason == MovementReason.RECEIVED
    assert movement.note == "Dodávka" and movement.actor.username == "warehouse"
    client.post(f"/pumps/{product.id}/receive", data={"quantity": "0"})
    db.refresh(product)
    assert product.stock == 20


# --- ordering -------------------------------------------------------------------


def test_user_orders_pump_and_warehouse_is_notified(client: TestClient, db: Session) -> None:
    product = _product(db)
    warehouse = _user(db, "warehouse")
    before = notifications_service.unread_count(db, warehouse)
    login(client, "user")
    response = client.post(
        "/pumps/order",
        data={"product_id": str(product.id), "quantity": "2", "requested_date": TOMORROW},
    )
    assert response.status_code == 303, response.text
    order = _pump_order(db)
    assert order.kind is OrderKind.PUMP and order.product_id == product.id
    assert order.status is OrderStatus.PENDING and order.unit_price is None
    assert pumps_service.free(db, product) == 12
    assert notifications_service.unread_count(db, warehouse) == before + 1
    page = client.get(f"/orders/{order.id}")
    assert page.status_code == 200 and "Ručná pumpa na barel" in page.text


def test_pump_order_respects_availability_and_rules(client: TestClient, db: Session) -> None:
    product = _product(db)
    login(client, "user")
    too_many = client.post(
        "/pumps/order",
        data={"product_id": str(product.id), "quantity": "15", "requested_date": TOMORROW},
    )
    assert too_many.status_code == 400 and "Voľných je 14" in too_many.text
    past = client.post(
        "/pumps/order",
        data={
            "product_id": str(product.id),
            "quantity": "1",
            "requested_date": (TODAY - timedelta(days=1)).isoformat(),
        },
    )
    assert past.status_code == 400
    # No per-order limit for pumps (Q-06): 14 pieces is fine.
    ok = client.post(
        "/pumps/order",
        data={"product_id": str(product.id), "quantity": "14", "requested_date": TOMORROW},
    )
    assert ok.status_code == 303


def test_inactive_product_cannot_be_ordered(db: Session) -> None:
    product = _product(db)
    pumps_service.update_product(
        db,
        actor=_user(db, "warehouse"),
        product=product,
        name=product.name,
        price=product.price,
        is_active=False,
    )
    with pytest.raises(ProductInactive):
        pumps_service.place_order(
            db, user=_user(db, "user"), product=product, quantity=1, requested_date=TODAY
        )


# --- issue and payment ----------------------------------------------------------


def test_issue_decrements_stock_and_freezes_price(client: TestClient, db: Session) -> None:
    order = _pump_order(db)  # seeded, 1 piece, pending
    product = _product(db)
    login(client, "warehouse")
    # Must be prepared first.
    client.post(f"/orders/{order.id}/issue")
    assert _pump_order(db).status is OrderStatus.PENDING
    client.post(f"/orders/{order.id}/ready")
    assert client.post(f"/orders/{order.id}/issue").status_code == 303
    order = _pump_order(db)
    assert order.status is OrderStatus.ISSUED
    assert order.unit_price == Decimal("12.50")
    assert order.total_price == Decimal("12.50")
    db.refresh(product)
    assert product.stock == 14
    movement = db.scalar(select(PumpStockMovement).where(PumpStockMovement.order_id == order.id))
    assert movement.delta == -1 and movement.reason == MovementReason.ISSUED

    # A later price change does not touch the issued order (FR-EX-03).
    pumps_service.update_product(
        db,
        actor=_user(db, "warehouse"),
        product=product,
        name=product.name,
        price=Decimal("99.00"),
        is_active=True,
    )
    assert _pump_order(db).unit_price == Decimal("12.50")
    page = client.get(f"/orders/{order.id}")
    assert "Nezaplatené" in page.text and "Zaplatené na mieste" in page.text


def test_payment_closes_pump_order(client: TestClient, db: Session) -> None:
    order = _pump_order(db)
    warehouse = _user(db, "warehouse")
    orders_service.mark_ready(db, actor=warehouse, order=order)
    pumps_service.issue_order(db, actor=warehouse, order=order)
    login(client, "warehouse")
    assert client.post(f"/orders/{order.id}/pay", data={"note": "karta"}).status_code == 303
    order = _pump_order(db)
    assert order.status is OrderStatus.CLOSED
    assert order.paid_at is not None and order.paid_by == warehouse.id
    assert order.payment_note == "karta"
    with pytest.raises((AlreadyPaid, InvalidOrderTransition)):
        pumps_service.record_payment(db, actor=warehouse, order=order)
    assert notifications_service.unread_count(db, _user(db, "peter.horvath")) >= 1


def test_payment_requires_issued_order_and_permission(client: TestClient, db: Session) -> None:
    order = _pump_order(db)
    with pytest.raises(InvalidOrderTransition):
        pumps_service.record_payment(db, actor=_user(db, "warehouse"), order=order)
    login(client, "user")
    assert client.post(f"/orders/{order.id}/pay").status_code == 403
    barrel_order = db.scalar(select(Order).where(Order.kind == OrderKind.BARREL))
    client.post("/logout")
    login(client, "warehouse")
    assert client.post(f"/orders/{barrel_order.id}/pay").status_code == 404


def test_issue_fails_when_stock_is_gone(db: Session) -> None:
    order = _pump_order(db)
    warehouse = _user(db, "warehouse")
    orders_service.mark_ready(db, actor=warehouse, order=order)
    product = _product(db)
    product.stock = 0
    db.commit()
    with pytest.raises(NotEnoughFree):
        pumps_service.issue_order(db, actor=warehouse, order=order)
    assert _pump_order(db).status is OrderStatus.READY


def test_cancel_pump_order_releases_reservation(client: TestClient, db: Session) -> None:
    order = _pump_order(db)
    login(client, "peter.horvath")
    assert client.post(f"/orders/{order.id}/cancel").status_code == 303
    assert _pump_order(db).status is OrderStatus.CANCELLED
    assert pumps_service.free(db, _product(db)) == 15


def test_pump_reservation_expires_like_barrels(db: Session) -> None:
    order = _pump_order(db)
    far = dates.add_working_days(order.requested_date, 3) + timedelta(days=1)
    expired = orders_service.expire_reservations(db, today=far)
    assert order.id in {o.id for o in expired}


# --- report and dashboards --------------------------------------------------------


def test_sales_report_counts_issued_pumps(client: TestClient, db: Session) -> None:
    order = _pump_order(db)
    warehouse = _user(db, "warehouse")
    orders_service.mark_ready(db, actor=warehouse, order=order)
    pumps_service.issue_order(db, actor=warehouse, order=order)
    report = pumps_service.sales_report(db, date_from=TODAY, date_to=TODAY)
    assert report.pieces == 1 and report.revenue == Decimal("12.50")
    empty = pumps_service.sales_report(
        db, date_from=TODAY - timedelta(days=10), date_to=TODAY - timedelta(days=1)
    )
    assert empty.pieces == 0 and empty.revenue == Decimal("0.00")
    login(client, "warehouse")
    page = client.get(f"/pumps/report?from={TODAY.isoformat()}&to={TODAY.isoformat()}")
    assert page.status_code == 200 and "12.50 €" in page.text
    login(client, "user")
    assert client.get("/pumps/report").status_code == 200  # pumps.read covers the report


def test_dashboards_show_pump_counts(client: TestClient) -> None:
    login(client, "user")
    assert "Pumpy na predaj" in client.get("/").text
    client.post("/logout")
    login(client, "warehouse")
    page = client.get("/warehouse")
    assert "Pumpy na sklade" in page.text and "Voľných na predaj: 14" in page.text


def test_supervisor_reads_pumps_without_forms(client: TestClient, db: Session) -> None:
    login(client, "supervisor")
    assert client.get("/pumps").status_code == 200
    detail = client.get(f"/pumps/{_product(db).id}")
    assert detail.status_code == 200 and "Príjem na sklad" not in detail.text


def test_parse_price() -> None:
    assert pumps_service.parse_price("12,5") == Decimal("12.50")
    with pytest.raises(InvalidPrice):
        pumps_service.parse_price("-1")
    with pytest.raises(InvalidPrice):
        pumps_service.parse_price("free")


def test_duplicate_name_rejected_at_service_level(db: Session) -> None:
    with pytest.raises(ProductNameTaken):
        pumps_service.create_product(
            db, actor=_user(db, "warehouse"), name=" Ručná pumpa na barel ", price=Decimal("1")
        )
