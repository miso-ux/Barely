"""Barrel orders: reservation, preparation and issue with automatic barrel selection
(FR-OB, BR-07..13).

Issue runs in one transaction with row locks so the same barrel can never go to two people.
"""

from datetime import date, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.models import (
    Barrel,
    BarrelStatus,
    Loan,
    LoanStatus,
    Order,
    OrderKind,
    OrderStatus,
    User,
)
from app.services import audit, barrel_state, dates, debtors, notifications, stock
from app.services import settings as settings_service
from app.services.barrel_state import Reason
from app.services.errors import (
    DateInPast,
    DateTooFar,
    DebtorBlocked,
    InvalidOrderTransition,
    InvalidQuantity,
    NotEnoughFree,
    OverOrderLimit,
)

ORDER_TRANSITIONS: Final[dict[OrderStatus, frozenset[OrderStatus]]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.READY, OrderStatus.CANCELLED}),
    OrderStatus.READY: frozenset({OrderStatus.ISSUED, OrderStatus.CANCELLED}),
    OrderStatus.ISSUED: frozenset({OrderStatus.CLOSED}),
    OrderStatus.CLOSED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


class CancelReason:
    BY_USER: Final = "by_user"
    BY_WAREHOUSE: Final = "by_warehouse"
    EXPIRED: Final = "expired"


def _check_transition(order: Order, to_status: OrderStatus) -> None:
    if to_status not in ORDER_TRANSITIONS[order.status]:
        raise InvalidOrderTransition(from_status=order.status.value, to_status=to_status.value)


def validate_barrel_order(
    db: Session,
    *,
    user: User,
    quantity: int,
    requested_date: date,
    allow_over_limit: bool = False,
    today: date | None = None,
) -> None:
    """All checks of FR-OB-03 and Q-03. Raises a DomainError describing the first failure."""
    if quantity < 1:
        raise InvalidQuantity()
    max_items = settings_service.get_int(db, "max_items_per_order")
    if quantity > max_items and not allow_over_limit:
        raise OverOrderLimit(max=max_items)
    today = today or dates.today_local()
    horizon = settings_service.get_int(db, "order_horizon_days")
    if requested_date < today:
        raise DateInPast()
    if requested_date > today + timedelta(days=horizon):
        raise DateTooFar(days=horizon)
    if settings_service.get_bool(db, "block_debtors") and debtors.is_debtor(db, user):
        raise DebtorBlocked()
    free = stock.free_count(db)
    if quantity > free:
        raise NotEnoughFree(free=free)


def _order_params(order: Order) -> dict[str, object]:
    return {
        "order_id": order.id,
        "username": order.user.username,
        "quantity": order.quantity,
        "date": dates.format_date(order.requested_date),
    }


def create_order(
    db: Session,
    *,
    actor: User,
    user: User,
    quantity: int,
    requested_date: date,
    note: str | None = None,
    allow_over_limit: bool = False,
) -> Order:
    """Add a pending order to the current transaction (reservation of `quantity` pieces).

    `actor` is who created it (the user, or the warehouse worker approving an exception).
    The caller commits, so exception approval can create the order atomically.
    """
    validate_barrel_order(
        db,
        user=user,
        quantity=quantity,
        requested_date=requested_date,
        allow_over_limit=allow_over_limit,
    )
    order = Order(
        user_id=user.id,
        kind=OrderKind.BARREL,
        quantity=quantity,
        requested_date=requested_date,
        status=OrderStatus.PENDING,
        note=(note or "").strip() or None,
        created_by=actor.id,
    )
    db.add(order)
    db.flush()
    db.refresh(order)
    audit.record(
        db,
        actor=actor,
        action="order.created",
        entity_type="order",
        entity_id=order.id,
        after={
            "user": user.username,
            "quantity": quantity,
            "requested_date": requested_date.isoformat(),
        },
    )
    notifications.notify_permission_holders(
        db,
        Perm.ORDERS_MANAGE,
        "notification.order.new",
        _order_params(order),
        link=f"/orders/{order.id}",
    )
    return order


def place_order(
    db: Session, *, user: User, quantity: int, requested_date: date, note: str | None = None
) -> Order:
    """FR-OB-02: a user orders for themselves."""
    order = create_order(
        db, actor=user, user=user, quantity=quantity, requested_date=requested_date, note=note
    )
    db.commit()
    return order


def cancel_order(db: Session, *, actor: User | None, order: Order, reason: str) -> Order:
    """FR-OB-05: cancel before issue. The reservation is released by the status change."""
    _check_transition(order, OrderStatus.CANCELLED)
    before = order.status
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = dates.now_utc()
    order.cancelled_by = actor.id if actor else None
    order.cancel_reason = reason
    audit.record(
        db,
        actor=actor,
        action="order.cancelled",
        entity_type="order",
        entity_id=order.id,
        before={"status": before.value},
        after={"status": order.status.value, "reason": reason},
    )
    link = f"/orders/{order.id}"
    if reason == CancelReason.BY_USER:
        notifications.notify_permission_holders(
            db,
            Perm.ORDERS_MANAGE,
            "notification.order.cancelled_by_user",
            _order_params(order),
            link,
        )
    elif reason == CancelReason.BY_WAREHOUSE:
        notifications.notify(
            db, order.user, "notification.order.cancelled_by_warehouse", _order_params(order), link
        )
    else:
        notifications.notify(
            db, order.user, "notification.order.expired", _order_params(order), link
        )
        notifications.notify_permission_holders(
            db,
            Perm.ORDERS_MANAGE,
            "notification.order.expired_warehouse",
            _order_params(order),
            link,
        )
    db.commit()
    return order


def mark_ready(db: Session, *, actor: User, order: Order) -> Order:
    _check_transition(order, OrderStatus.READY)
    order.status = OrderStatus.READY
    order.ready_at = dates.now_utc()
    order.ready_by = actor.id
    audit.record(
        db,
        actor=actor,
        action="order.ready",
        entity_type="order",
        entity_id=order.id,
        before={"status": OrderStatus.PENDING.value},
        after={"status": OrderStatus.READY.value},
    )
    notifications.notify(
        db, order.user, "notification.order.ready", _order_params(order), f"/orders/{order.id}"
    )
    db.commit()
    return order


def select_barrels_for_issue(db: Session, quantity: int, loan_limit: int) -> list[Barrel]:
    """BR-12: highest loan count below the limit first, then oldest. Rows are locked so a
    concurrent issue skips them (SKIP LOCKED) instead of handing out the same barrel twice."""
    stmt = (
        select(Barrel)
        .where(Barrel.status == BarrelStatus.IN_STOCK, Barrel.loan_count < loan_limit)
        .order_by(Barrel.loan_count.desc(), Barrel.added_at.asc(), Barrel.id.asc())
        .limit(quantity)
        .with_for_update(skip_locked=True)
    )
    return list(db.scalars(stmt))


def issue_order(db: Session, *, actor: User, order: Order) -> list[Loan]:
    """FR-OB-06..09: assign barrels, create loans, freeze due date and price. One transaction."""
    # Re-read the order with a row lock so two warehouse workers cannot issue it twice.
    # `of=Order` locks only the orders row; the eager-joined user row must not be locked.
    locked = db.execute(
        select(Order).where(Order.id == order.id).with_for_update(of=Order)
    ).scalar_one()
    _check_transition(locked, OrderStatus.ISSUED)

    loan_limit = settings_service.get_int(db, "loan_limit")
    loan_price = settings_service.get_decimal(db, "loan_price")
    barrels = select_barrels_for_issue(db, locked.quantity, loan_limit)
    if len(barrels) < locked.quantity:
        db.rollback()
        raise NotEnoughFree(free=len(barrels))

    issued_at = dates.now_utc()
    due_date = dates.due_date_for(issued_at)
    loans: list[Loan] = []
    for barrel in barrels:
        barrel.loan_count += 1  # BR-09: counter grows at issue confirmation
        loan = Loan(
            order_id=locked.id,
            barrel_id=barrel.id,
            user_id=locked.user_id,
            loan_sequence=barrel.loan_count,
            issued_at=issued_at,
            issued_by=actor.id,
            due_date=due_date,
            loan_price=loan_price,
            status=LoanStatus.ON_LOAN,
        )
        db.add(loan)
        db.flush()
        barrel_state.transition(
            db, barrel, BarrelStatus.ON_LOAN, actor=actor, reason=Reason.ISSUED, loan_id=loan.id
        )
        loans.append(loan)

    locked.status = OrderStatus.ISSUED
    locked.issued_at = issued_at
    locked.issued_by = actor.id
    codes = [barrel.code for barrel in barrels]
    audit.record(
        db,
        actor=actor,
        action="order.issued",
        entity_type="order",
        entity_id=locked.id,
        before={"status": OrderStatus.READY.value},
        after={
            "status": OrderStatus.ISSUED.value,
            "barrels": codes,
            "due_date": due_date.isoformat(),
            "loan_price": str(loan_price),
        },
    )
    notifications.notify(
        db,
        locked.user,
        "notification.order.issued",
        {
            **_order_params(locked),
            "codes": ", ".join(codes),
            "due_date": dates.format_date(due_date),
        },
        f"/orders/{locked.id}",
    )
    db.commit()
    db.refresh(order)
    return loans


def expire_reservations(db: Session, *, today: date | None = None) -> list[Order]:
    """Q-03: open orders not picked up within N working days after the requested date are
    cancelled automatically and the pieces are released. Run by the daily job."""
    today = today or dates.today_local()
    validity = settings_service.get_int(db, "reservation_validity_days")
    open_orders = db.scalars(
        select(Order).where(
            Order.kind == OrderKind.BARREL, Order.status.in_(stock.RESERVING_STATUSES)
        )
    ).all()
    expired = [
        order
        for order in open_orders
        if dates.add_working_days(order.requested_date, validity) < today
    ]
    for order in expired:
        cancel_order(db, actor=None, order=order, reason=CancelReason.EXPIRED)
    return expired


def list_orders(
    db: Session,
    *,
    user_id: int | None = None,
    status: OrderStatus | None = None,
    username: str | None = None,
    requested_date: date | None = None,
) -> list[Order]:
    stmt = select(Order).where(Order.kind == OrderKind.BARREL)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if username:
        stmt = stmt.join(User, User.id == Order.user_id).where(
            User.username.ilike(f"%{username.strip()}%")
        )
    if requested_date is not None:
        stmt = stmt.where(Order.requested_date == requested_date)
    stmt = stmt.order_by(Order.requested_date, Order.id)
    return list(db.scalars(stmt))


def open_orders_by_date(db: Session) -> list[tuple[date, int, int]]:
    """FR-SK-03: (pickup date, number of orders, pieces) for orders still to be issued."""
    rows: dict[date, list[int]] = {}
    for order in list_orders(db):
        if order.status in stock.RESERVING_STATUSES:
            bucket = rows.setdefault(order.requested_date, [0, 0])
            bucket[0] += 1
            bucket[1] += order.quantity
    return [(day, counts[0], counts[1]) for day, counts in sorted(rows.items())]
