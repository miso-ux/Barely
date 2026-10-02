"""Stock availability (FR-SK-02, BR-08): free = in stock minus pieces reserved by open orders."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Barrel, BarrelStatus, Order, OrderKind, OrderStatus

RESERVING_STATUSES = (OrderStatus.PENDING, OrderStatus.READY)


def in_stock_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Barrel).where(Barrel.status == BarrelStatus.IN_STOCK)
        )
        or 0
    )


def reserved_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Order.quantity), 0)).where(
                Order.kind == OrderKind.BARREL, Order.status.in_(RESERVING_STATUSES)
            )
        )
        or 0
    )


def free_count(db: Session) -> int:
    return max(in_stock_count(db) - reserved_count(db), 0)


def notify_low_stock(db: Session) -> bool:
    """FR-SK-05: warn the warehouse when free barrels drop below the threshold, at most once a
    day. Run by the daily job; returns True when a notification was created."""
    from app.auth.permissions import Perm
    from app.models import Notification
    from app.services import dates, notifications
    from app.services import settings as settings_service

    free = free_count(db)
    threshold = settings_service.get_int(db, "low_stock_threshold")
    if free >= threshold:
        return False
    today = dates.today_local()
    already = db.scalar(
        select(Notification.id)
        .where(Notification.kind == "notification.stock.low")
        .order_by(Notification.id.desc())
        .limit(1)
    )
    if already is not None:
        last = db.get(Notification, already)
        if last is not None and dates.local_date(last.created_at) == today:
            return False
    notifications.notify_permission_holders(
        db,
        Perm.ORDERS_MANAGE,
        "notification.stock.low",
        {"free": free, "threshold": threshold},
        "/warehouse",
    )
    db.commit()
    return True
