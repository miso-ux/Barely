import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.user import User


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class InvoiceStatus(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    SENT = "sent"
    CANCELLED = "cancelled"


class InvoiceKind(enum.StrEnum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"  # the cancellation record pointing at the original (BR-20)


class InvoiceItemType(enum.StrEnum):
    PENALTY = "penalty"
    PUMP_ORDER = "pump_order"
    LOAN = "loan"


ACTIVE_INVOICE_STATUSES = (InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.SENT)


class Invoice(Base):
    """Demo invoice (FR-FA). Number is assigned at issue; issued invoices never change."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(30), unique=True)
    kind: Mapped[InvoiceKind] = mapped_column(_enum(InvoiceKind, "invoice_kind"))
    status: Mapped[InvoiceStatus] = mapped_column(
        _enum(InvoiceStatus, "invoice_status"), index=True
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancels_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    payment_note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[User] = relationship(foreign_keys=[customer_id], lazy="joined")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    issuer: Mapped[User | None] = relationship(foreign_keys=[issued_by])
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", order_by="InvoiceItem.id", lazy="selectin"
    )
    cancels: Mapped["Invoice | None"] = relationship(
        remote_side=[id], foreign_keys=[cancels_invoice_id]
    )

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_INVOICE_STATUSES

    @property
    def is_draft(self) -> bool:
        return self.status is InvoiceStatus.DRAFT

    @property
    def visible_items(self) -> list["InvoiceItem"]:
        return [item for item in self.items if item.removed_at is None]


class InvoiceItem(Base):
    """One billable record on an invoice. `released` = no longer blocks re-invoicing (BR-21)."""

    __tablename__ = "invoice_items"
    __table_args__ = (
        Index(
            "uq_invoice_items_active_ref",
            "item_type",
            "ref_id",
            unique=True,
            postgresql_where=text("released = false"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    item_type: Mapped[InvoiceItemType] = mapped_column(_enum(InvoiceItemType, "invoice_item_type"))
    ref_id: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    released: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class InvoiceNumberSequence(Base):
    """Gapless per-year numbering (BR-20). The row is locked while a number is taken."""

    __tablename__ = "invoice_number_sequence"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)
