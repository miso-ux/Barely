import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.barrel import Barrel
from app.models.order import Loan
from app.models.user import User


class PenaltyReason(enum.StrEnum):
    OVERDUE = "overdue"
    DAMAGED = "damaged"
    LOST = "lost"


class PenaltyStatus(enum.StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"
    CANCELLED = "cancelled"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Penalty(Base):
    """A fine for one loan (BR-04..06, BR-16). Amount is frozen at creation. Never deleted."""

    __tablename__ = "penalties"
    __table_args__ = (
        # One active penalty per loan and reason; the daily job can therefore run repeatedly.
        Index(
            "uq_penalties_loan_reason_active",
            "loan_id",
            "reason",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)
    barrel_id: Mapped[int] = mapped_column(ForeignKey("barrels.id"))
    reason: Mapped[PenaltyReason] = mapped_column(_enum(PenaltyReason, "penalty_reason"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[PenaltyStatus] = mapped_column(
        _enum(PenaltyStatus, "penalty_status"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    payment_note: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    loan: Mapped[Loan] = relationship(lazy="joined")
    barrel: Mapped[Barrel] = relationship(lazy="joined")
    payer: Mapped[User | None] = relationship(foreign_keys=[paid_by])
    canceller: Mapped[User | None] = relationship(foreign_keys=[cancelled_by])
