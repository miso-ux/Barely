from datetime import datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.user import User


class PumpProduct(Base):
    """A pump type for sale (FR-PU-01). One type in the demo, the model allows more (Q-06).
    Products are deactivated, never deleted."""

    __tablename__ = "pump_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    movements: Mapped[list["PumpStockMovement"]] = relationship(
        back_populates="product",
        order_by="PumpStockMovement.created_at.desc(), PumpStockMovement.id.desc()",
    )


class MovementReason:
    RECEIVED: Final = "received"
    ISSUED: Final = "issued"
    CORRECTION: Final = "correction"


class PumpStockMovement(Base):
    """Every stock change (FR-PU-05): receipt, issue, correction."""

    __tablename__ = "pump_stock_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("pump_products.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(50))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[PumpProduct] = relationship(back_populates="movements")
    actor: Mapped[User | None] = relationship(lazy="joined")
