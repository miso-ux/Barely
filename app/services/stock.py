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
