import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.barrel import Barrel
from app.models.user import User


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class OrderKind(enum.StrEnum):
    BARREL = "barrel"
    PUMP = "pump"  # phase 5


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    READY = "ready"
    ISSUED = "issued"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ExceptionRequestStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LoanStatus(enum.StrEnum):
    ON_LOAN = "on_loan"
    RETURNED = "returned"
    RETURNED_DAMAGED = "returned_damaged"
    OVERDUE = "overdue"
    LOST = "lost"


class Order(Base):
    """Reservation of `quantity` pieces for a pickup date. Every step keeps who and when (BR-23)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[OrderKind] = mapped_column(_enum(OrderKind, "order_kind"))
    quantity: Mapped[int] = mapped_column(Integer)
    requested_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus, "order_status"), index=True)
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(50))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    ready_actor: Mapped[User | None] = relationship(foreign_keys=[ready_by])
    issue_actor: Mapped[User | None] = relationship(foreign_keys=[issued_by])
    cancel_actor: Mapped[User | None] = relationship(foreign_keys=[cancelled_by])
    loans: Mapped[list["Loan"]] = relationship(
        back_populates="order", order_by="Loan.id", lazy="selectin"
    )
    exception_request: Mapped["ExceptionRequest | None"] = relationship(
        back_populates="order", uselist=False
    )


class ExceptionRequest(Base):
    """Request to borrow more than the per-order limit (FR-ZV)."""

    __tablename__ = "exception_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    requested_date: Mapped[date] = mapped_column(Date)
    justification: Mapped[str] = mapped_column(Text)
    status: Mapped[ExceptionRequestStatus] = mapped_column(
        _enum(ExceptionRequestStatus, "exception_request_status"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by])
    order: Mapped[Order | None] = relationship(back_populates="exception_request")


class Loan(Base):
    """One barrel lent to one person. Due date and price are frozen at issue time (BR-03, BR-18)."""

    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    barrel_id: Mapped[int] = mapped_column(ForeignKey("barrels.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    loan_sequence: Mapped[int] = mapped_column(Integer)  # barrel's loan_count after this issue
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    loan_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[LoanStatus] = mapped_column(_enum(LoanStatus, "loan_status"), index=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    return_note: Mapped[str | None] = mapped_column(Text)
    # Set once the due-date reminder has gone out, so the daily job never sends it twice.
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="loans")
    barrel: Mapped[Barrel] = relationship(lazy="joined")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class Notification(Base):
    """In-app notification. `kind` is an i18n key rendered with `params`. Read time is kept
    as evidence (FR-NO-05)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    link: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
