"""Pumps: catalogue, stock, purchase orders and on-site payment (FR-PU-01..06, BR-01).

A pump order reuses the Order table with kind = pump. It is reserved at creation, stock is
decremented and the unit price frozen at issue (FR-EX-03), and the order closes once paid.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.models import (
    MovementReason,
    Order,
    OrderKind,
    OrderStatus,
    PumpProduct,
    PumpStockMovement,
    User,
)
from app.services import audit, dates, notifications, orders, stock
from app.services.errors import (
    AlreadyPaid,
    InvalidOrderTransition,
    InvalidPrice,
    InvalidProductName,
    InvalidQuantity,
    NotEnoughFree,
    ProductInactive,
    ProductNameTaken,
)

# --- catalogue ------------------------------------------------------------------


def list_products(db: Session, *, active_only: bool = False) -> list[PumpProduct]:
    stmt = select(PumpProduct).order_by(PumpProduct.name)
    if active_only:
        stmt = stmt.where(PumpProduct.is_active.is_(True))
    return list(db.scalars(stmt))


def parse_price(raw: str) -> Decimal:
    try:
        price = Decimal(raw.strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise InvalidPrice() from exc
    if price < 0:
        raise InvalidPrice()
    return price.quantize(Decimal("0.01"))


def _check_name(db: Session, name: str, *, exclude_id: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise InvalidProductName()
    existing = db.scalar(select(PumpProduct).where(PumpProduct.name == name))
    if existing is not None and existing.id != exclude_id:
        raise ProductNameTaken(name=name)
    return name


def create_product(db: Session, *, actor: User, name: str, price: Decimal) -> PumpProduct:
    product = PumpProduct(name=_check_name(db, name), price=price, stock=0, is_active=True)
    db.add(product)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="pump.created",
        entity_type="pump",
        entity_id=product.id,
        after={"name": product.name, "price": str(product.price)},
    )
    db.commit()
    return product


def update_product(
    db: Session, *, actor: User, product: PumpProduct, name: str, price: Decimal, is_active: bool
) -> PumpProduct:
    before = {"name": product.name, "price": str(product.price), "is_active": product.is_active}
    product.name = _check_name(db, name, exclude_id=product.id)
    product.price = price
    product.is_active = is_active
    after = {"name": product.name, "price": str(product.price), "is_active": product.is_active}
    if before != after:
        audit.record(
            db,
            actor=actor,
            action="pump.updated",
            entity_type="pump",
            entity_id=product.id,
            before=before,
            after=after,
        )
    db.commit()
    return product


# --- stock ------------------------------------------------------------------------


def receive_stock(
    db: Session, *, actor: User, product: PumpProduct, quantity: int, note: str = ""
) -> PumpProduct:
    if quantity < 1:
        raise InvalidQuantity()
    product.stock += quantity
    db.add(
        PumpStockMovement(
            product_id=product.id,
            delta=quantity,
            reason=MovementReason.RECEIVED,
            actor_id=actor.id,
            note=note.strip() or None,
        )
    )
    audit.record(
        db,
        actor=actor,
        action="pump_stock.received",
        entity_type="pump_stock",
        entity_id=product.id,
        after={"quantity": quantity, "stock": product.stock},
    )
    db.commit()
    return product


def reserved(db: Session, product_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Order.quantity), 0)).where(
                Order.kind == OrderKind.PUMP,
                Order.product_id == product_id,
                Order.status.in_(stock.RESERVING_STATUSES),
            )
        )
        or 0
    )


def free(db: Session, product: PumpProduct) -> int:
    return max(product.stock - reserved(db, product.id), 0)


def total_free(db: Session) -> int:
    return sum(free(db, p) for p in list_products(db, active_only=True))


def total_stock(db: Session) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(PumpProduct.stock), 0))) or 0)


# --- orders -----------------------------------------------------------------------


def place_order(
    db: Session,
    *,
    user: User,
    product: PumpProduct,
    quantity: int,
    requested_date: date,
    note: str | None = None,
) -> Order:
    """FR-PU-02/03: reserve `quantity` pumps for pickup. Debtor and date rules as for barrels."""
    if not product.is_active:
        raise ProductInactive()
    orders.validate_common(db, user=user, quantity=quantity, requested_date=requested_date)
    available = free(db, product)
    if quantity > available:
        raise NotEnoughFree(free=available)
    order = Order(
        user_id=user.id,
        kind=OrderKind.PUMP,
        product_id=product.id,
        quantity=quantity,
        requested_date=requested_date,
        status=OrderStatus.PENDING,
        note=(note or "").strip() or None,
        created_by=user.id,
    )
    db.add(order)
    db.flush()
    db.refresh(order)
    audit.record(
        db,
        actor=user,
        action="order.created",
        entity_type="order",
        entity_id=order.id,
        after={
            "kind": "pump",
            "product": product.name,
            "quantity": quantity,
            "requested_date": requested_date.isoformat(),
        },
    )
    notifications.notify_permission_holders(
        db,
        Perm.PUMPS_MANAGE,
        "notification.order.new_pump",
        {**orders.order_params(order), "product": product.name},
        link=f"/orders/{order.id}",
    )
    db.commit()
    return order


def issue_order(db: Session, *, actor: User, order: Order) -> Order:
    """FR-PU-03/04: hand over the pumps, decrement stock, freeze the price."""
    locked = db.execute(
        select(Order).where(Order.id == order.id).with_for_update(of=Order)
    ).scalar_one()
    if locked.status is not OrderStatus.READY:
        raise InvalidOrderTransition(
            from_status=locked.status.value, to_status=OrderStatus.ISSUED.value
        )
    product = db.execute(
        select(PumpProduct).where(PumpProduct.id == locked.product_id).with_for_update()
    ).scalar_one()
    if product.stock < locked.quantity:
        db.rollback()
        raise NotEnoughFree(free=product.stock)

    now = dates.now_utc()
    product.stock -= locked.quantity
    db.add(
        PumpStockMovement(
            product_id=product.id,
            delta=-locked.quantity,
            reason=MovementReason.ISSUED,
            order_id=locked.id,
            actor_id=actor.id,
        )
    )
    locked.unit_price = product.price
    locked.status = OrderStatus.ISSUED
    locked.issued_at = now
    locked.issued_by = actor.id
    audit.record(
        db,
        actor=actor,
        action="order.issued",
        entity_type="order",
        entity_id=locked.id,
        before={"status": OrderStatus.READY.value},
        after={
            "status": OrderStatus.ISSUED.value,
            "product": product.name,
            "quantity": locked.quantity,
            "unit_price": str(locked.unit_price),
            "total": str(locked.total_price),
        },
    )
    notifications.notify(
        db,
        locked.user,
        "notification.order.issued_pump",
        {
            **orders.order_params(locked),
            "product": product.name,
            "total": f"{locked.total_price:.2f}",
        },
        f"/orders/{locked.id}",
    )
    db.commit()
    db.refresh(order)
    return order


def record_payment(
    db: Session, *, actor: User, order: Order, note: str = "", commit: bool = True
) -> Order:
    """FR-PU-04 / BR-17: payment recorded on site or through an invoice. Closes the order."""
    if order.status is not OrderStatus.ISSUED:
        raise InvalidOrderTransition(
            from_status=order.status.value, to_status=OrderStatus.CLOSED.value
        )
    if order.paid_at is not None:
        raise AlreadyPaid()
    now = dates.now_utc()
    order.paid_at = now
    order.paid_by = actor.id
    order.payment_note = note.strip() or None
    order.status = OrderStatus.CLOSED
    order.closed_at = now
    audit.record(
        db,
        actor=actor,
        action="order.paid",
        entity_type="order",
        entity_id=order.id,
        before={"status": OrderStatus.ISSUED.value, "paid": False},
        after={"status": OrderStatus.CLOSED.value, "paid": True, "total": str(order.total_price)},
    )
    notifications.notify(
        db,
        order.user,
        "notification.order.paid",
        {**orders.order_params(order), "total": f"{order.total_price:.2f}"},
        f"/orders/{order.id}",
    )
    if commit:
        db.commit()
    return order


# --- report (FR-PU-06) ------------------------------------------------------------


@dataclass
class SalesReport:
    date_from: date
    date_to: date
    orders: list[Order]
    pieces: int
    revenue: Decimal


def sales_report(db: Session, *, date_from: date, date_to: date) -> SalesReport:
    rows = list(
        db.scalars(
            select(Order)
            .where(
                Order.kind == OrderKind.PUMP,
                Order.status.in_([OrderStatus.ISSUED, OrderStatus.CLOSED]),
                Order.issued_at.is_not(None),
            )
            .order_by(Order.issued_at)
        )
    )
    selected = [o for o in rows if date_from <= dates.local_date(o.issued_at) <= date_to]
    pieces = sum(o.quantity for o in selected)
    revenue = sum((o.total_price or Decimal("0")) for o in selected) or Decimal("0.00")
    return SalesReport(
        date_from=date_from,
        date_to=date_to,
        orders=selected,
        pieces=pieces,
        revenue=Decimal(revenue).quantize(Decimal("0.01")),
    )
