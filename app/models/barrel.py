import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.user import User


class BarrelStatus(enum.StrEnum):
    IN_STOCK = "in_stock"
    ON_LOAN = "on_loan"
    DAMAGED = "damaged"
    LOST = "lost"
    RETIRED = "retired"  # reached the loan limit
    WRITTEN_OFF = "written_off"  # final


def barrel_status_type() -> Enum:
    return Enum(BarrelStatus, name="barrel_status", values_callable=lambda e: [m.value for m in e])


class Barrel(Base):
    """One physical barrel. Never deleted (BR-11); a database trigger rejects DELETE."""

    __tablename__ = "barrels"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[BarrelStatus] = mapped_column(barrel_status_type(), index=True)
    loan_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    written_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    history: Mapped[list["BarrelStatusHistory"]] = relationship(
        back_populates="barrel",
        order_by="BarrelStatusHistory.created_at, BarrelStatusHistory.id",
        lazy="selectin",
    )


class BarrelStatusHistory(Base):
    """Every status change: who, when, why. Written only through services.barrel_state."""

    __tablename__ = "barrel_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    barrel_id: Mapped[int] = mapped_column(ForeignKey("barrels.id"), index=True)
    from_status: Mapped[BarrelStatus | None] = mapped_column(barrel_status_type())
    to_status: Mapped[BarrelStatus] = mapped_column(barrel_status_type())
    reason: Mapped[str] = mapped_column(String(50))  # machine code, translated in UI
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Related loan; the foreign key is added in phase 3 together with the loans table.
    loan_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    barrel: Mapped[Barrel] = relationship(back_populates="history")
    actor: Mapped[User | None] = relationship(lazy="joined")
