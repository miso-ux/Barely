"""Invoices (FR-FA-01..11, BR-13, BR-18..21).

Billable records: unpaid penalties, issued pump orders not paid on site, and loans with a
non-zero price. A record may sit on one active invoice at a time (partial unique index on
invoice_items). Numbers come from a locked per-year sequence at issue time, so they have no
gaps. Issued invoices are never edited; cancellation marks the original and writes a credit
note that points at it.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.i18n import t
from app.models import (
    Invoice,
    InvoiceItem,
    InvoiceItemType,
    InvoiceKind,
    InvoiceNumberSequence,
    InvoiceStatus,
    Loan,
    Order,
    OrderKind,
    OrderStatus,
    Penalty,
    PenaltyStatus,
    User,
)
from app.services import audit, dates, notifications, penalties, pumps
from app.services.errors import (
    AlreadyPaid,
    InvalidInvoiceTransition,
    InvoiceLocked,
    ItemNotBillable,
    NoInvoiceItems,
    ReasonRequired,
)

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Billable:
    item_type: InvoiceItemType
    ref_id: int
    customer: User
    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal

    @property
    def ref(self) -> str:
        return f"{self.item_type.value}:{self.ref_id}"


def parse_ref(raw: str) -> tuple[InvoiceItemType, int]:
    try:
        kind, number = raw.split(":", 1)
        return InvoiceItemType(kind), int(number)
    except (ValueError, AttributeError) as exc:
        raise ItemNotBillable(ref=raw) from exc


def _blocked_refs(db: Session) -> set[tuple[InvoiceItemType, int]]:
    rows = db.execute(
        select(InvoiceItem.item_type, InvoiceItem.ref_id).where(InvoiceItem.released.is_(False))
    ).all()
    return {(item_type, ref_id) for item_type, ref_id in rows}


def billable_items(db: Session, *, customer_id: int | None = None) -> list[Billable]:
    """FR-FA-10: everything that can still go on an invoice."""
    blocked = _blocked_refs(db)
    items: list[Billable] = []

    for penalty in db.scalars(select(Penalty).where(Penalty.status == PenaltyStatus.UNPAID)):
        if (InvoiceItemType.PENALTY, penalty.id) in blocked:
            continue
        items.append(
            Billable(
                InvoiceItemType.PENALTY,
                penalty.id,
                penalty.user,
                t(
                    "invoice.item.penalty",
                    code=penalty.barrel.code,
                    reason=t(f"penalty.reason.{penalty.reason.value}"),
                ),
                1,
                penalty.amount,
                penalty.amount,
            )
        )

    pump_orders = db.scalars(
        select(Order).where(
            Order.kind == OrderKind.PUMP,
            Order.status == OrderStatus.ISSUED,
            Order.paid_at.is_(None),
        )
    )
    for order in pump_orders:
        if (InvoiceItemType.PUMP_ORDER, order.id) in blocked or order.unit_price is None:
            continue
        items.append(
            Billable(
                InvoiceItemType.PUMP_ORDER,
                order.id,
                order.user,
                t("invoice.item.pump_order", product=order.product.name, order_id=order.id),
                order.quantity,
                order.unit_price,
                order.total_price or ZERO,
            )
        )

    for loan in db.scalars(select(Loan).where(Loan.loan_price > 0)):
        if (InvoiceItemType.LOAN, loan.id) in blocked:
            continue
        items.append(
            Billable(
                InvoiceItemType.LOAN,
                loan.id,
                loan.user,
                t(
                    "invoice.item.loan",
                    code=loan.barrel.code,
                    issued=dates.format_date(dates.local_date(loan.issued_at)),
                ),
                1,
                loan.loan_price,
                loan.loan_price,
            )
        )

    if customer_id is not None:
        items = [item for item in items if item.customer.id == customer_id]
    return sorted(items, key=lambda b: (b.customer.username, b.item_type.value, b.ref_id))


def _recalculate(invoice: Invoice) -> None:
    invoice.total = sum((item.amount for item in invoice.visible_items), ZERO).quantize(
        Decimal("0.01")
    )


def _add_items(
    db: Session, invoice: Invoice, refs: list[tuple[InvoiceItemType, int]]
) -> list[InvoiceItem]:
    candidates = {
        (b.item_type, b.ref_id): b for b in billable_items(db, customer_id=invoice.customer_id)
    }
    added: list[InvoiceItem] = []
    for ref in refs:
        billable = candidates.get(ref)
        if billable is None:
            raise ItemNotBillable(ref=f"{ref[0].value}:{ref[1]}")
        item = InvoiceItem(
            invoice_id=invoice.id,
            item_type=billable.item_type,
            ref_id=billable.ref_id,
            description=billable.description,
            quantity=billable.quantity,
            unit_price=billable.unit_price,
            amount=billable.amount,
        )
        db.add(item)
        added.append(item)
    db.flush()
    db.refresh(invoice)
    _recalculate(invoice)
    return added


def create_draft(
    db: Session,
    *,
    actor: User,
    customer: User,
    refs: list[tuple[InvoiceItemType, int]],
    note: str = "",
) -> Invoice:
    """FR-FA-03/04, BR-19: warehouse and invoicing may both draft."""
    if not refs:
        raise NoInvoiceItems()
    invoice = Invoice(
        kind=InvoiceKind.INVOICE,
        status=InvoiceStatus.DRAFT,
        customer_id=customer.id,
        note=note.strip() or None,
        total=ZERO,
        created_by=actor.id,
    )
    db.add(invoice)
    db.flush()
    _add_items(db, invoice, refs)
    audit.record(
        db,
        actor=actor,
        action="invoice.created",
        entity_type="invoice",
        entity_id=invoice.id,
        after={
            "customer": customer.username,
            "items": [f"{r[0].value}:{r[1]}" for r in refs],
            "total": str(invoice.total),
        },
    )
    if not actor.has_permission(Perm.INVOICES_ISSUE):
        notifications.notify_permission_holders(
            db,
            Perm.INVOICES_ISSUE,
            "notification.invoice.draft",
            {
                "invoice_id": invoice.id,
                "customer": customer.username,
                "total": f"{invoice.total:.2f}",
            },
            f"/invoices/{invoice.id}",
            exclude=actor,
        )
    db.commit()
    return invoice


def _ensure_draft(invoice: Invoice) -> None:
    if not invoice.is_draft:
        raise InvoiceLocked(status=invoice.status.value)


def add_items(
    db: Session, *, actor: User, invoice: Invoice, refs: list[tuple[InvoiceItemType, int]]
) -> Invoice:
    _ensure_draft(invoice)
    if not refs:
        raise NoInvoiceItems()
    added = _add_items(db, invoice, refs)
    audit.record(
        db,
        actor=actor,
        action="invoice.items_added",
        entity_type="invoice",
        entity_id=invoice.id,
        after={
            "items": [f"{i.item_type.value}:{i.ref_id}" for i in added],
            "total": str(invoice.total),
        },
    )
    db.commit()
    return invoice


def remove_item(db: Session, *, actor: User, invoice: Invoice, item: InvoiceItem) -> Invoice:
    """Drafts only. The row stays (nothing is deleted) but is released for re-invoicing."""
    _ensure_draft(invoice)
    if item.invoice_id != invoice.id or item.removed_at is not None:
        raise ItemNotBillable(ref=f"{item.item_type.value}:{item.ref_id}")
    item.removed_at = dates.now_utc()
    item.released = True
    db.flush()
    db.refresh(invoice)
    _recalculate(invoice)
    audit.record(
        db,
        actor=actor,
        action="invoice.item_removed",
        entity_type="invoice",
        entity_id=invoice.id,
        after={"item": f"{item.item_type.value}:{item.ref_id}", "total": str(invoice.total)},
    )
    db.commit()
    return invoice


def next_number(db: Session, year: int) -> str:
    """Take the next number of the year under a row lock. Call inside the issuing transaction."""
    db.execute(
        pg_insert(InvoiceNumberSequence)
        .values(year=year, last_number=0)
        .on_conflict_do_nothing(index_elements=["year"])
    )
    row = db.execute(
        select(InvoiceNumberSequence).where(InvoiceNumberSequence.year == year).with_for_update()
    ).scalar_one()
    row.last_number += 1
    return f"{year}-{row.last_number:04d}"


def issue(db: Session, *, actor: User, invoice: Invoice) -> Invoice:
    """FR-FA-05: assign the number and lock the document. Only the invoicing role (BR-19)."""
    locked = db.execute(
        select(Invoice).where(Invoice.id == invoice.id).with_for_update(of=Invoice)
    ).scalar_one()
    if locked.status is not InvoiceStatus.DRAFT:
        raise InvalidInvoiceTransition(
            from_status=locked.status.value, to_status=InvoiceStatus.ISSUED.value
        )
    if not locked.visible_items:
        raise NoInvoiceItems()
    now = dates.now_utc()
    locked.number = next_number(db, dates.local_date(now).year)
    locked.status = InvoiceStatus.ISSUED
    locked.issued_at = now
    locked.issued_by = actor.id
    audit.record(
        db,
        actor=actor,
        action="invoice.issued",
        entity_type="invoice",
        entity_id=locked.id,
        before={"status": InvoiceStatus.DRAFT.value},
        after={
            "status": InvoiceStatus.ISSUED.value,
            "number": locked.number,
            "total": str(locked.total),
        },
    )
    db.commit()
    db.refresh(invoice)
    return invoice


def send(db: Session, *, actor: User, invoice: Invoice) -> Invoice:
    """FR-FA-08: in the demo a status change plus a notification, no integration (Q-09)."""
    if invoice.status is not InvoiceStatus.ISSUED:
        raise InvalidInvoiceTransition(
            from_status=invoice.status.value, to_status=InvoiceStatus.SENT.value
        )
    invoice.status = InvoiceStatus.SENT
    invoice.sent_at = dates.now_utc()
    invoice.sent_by = actor.id
    audit.record(
        db,
        actor=actor,
        action="invoice.sent",
        entity_type="invoice",
        entity_id=invoice.id,
        before={"status": InvoiceStatus.ISSUED.value},
        after={"status": InvoiceStatus.SENT.value},
    )
    notifications.notify(
        db,
        invoice.customer,
        "notification.invoice.sent",
        {"number": invoice.number, "total": f"{invoice.total:.2f}"},
        f"/invoices/{invoice.id}",
    )
    db.commit()
    return invoice


def cancel(db: Session, *, actor: User, invoice: Invoice, reason: str) -> Invoice | None:
    """FR-FA-06, BR-20/21: cancel. Issued or sent invoices get a credit note that references
    them; items are released so they can be invoiced again. Returns the credit note, if any."""
    if not reason.strip():
        raise ReasonRequired()
    if not invoice.is_active or invoice.kind is InvoiceKind.CREDIT_NOTE:
        raise InvalidInvoiceTransition(
            from_status=invoice.status.value, to_status=InvoiceStatus.CANCELLED.value
        )
    now = dates.now_utc()
    was_draft = invoice.is_draft
    previous = invoice.status
    for item in invoice.items:
        item.released = True
    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_at = now
    invoice.cancelled_by = actor.id
    invoice.cancel_reason = reason.strip()

    credit_note: Invoice | None = None
    if not was_draft:
        credit_note = Invoice(
            kind=InvoiceKind.CREDIT_NOTE,
            status=InvoiceStatus.ISSUED,
            customer_id=invoice.customer_id,
            note=invoice.cancel_reason,
            total=-invoice.total,
            created_by=actor.id,
            issued_at=now,
            issued_by=actor.id,
            cancels_invoice_id=invoice.id,
            number=next_number(db, dates.local_date(now).year),
        )
        db.add(credit_note)
        db.flush()
        for item in invoice.visible_items:
            db.add(
                InvoiceItem(
                    invoice_id=credit_note.id,
                    item_type=item.item_type,
                    ref_id=item.ref_id,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    amount=-item.amount,
                    released=True,
                )
            )
    audit.record(
        db,
        actor=actor,
        action="invoice.cancelled",
        entity_type="invoice",
        entity_id=invoice.id,
        before={"status": previous.value, "number": invoice.number},
        after={
            "status": InvoiceStatus.CANCELLED.value,
            "reason": invoice.cancel_reason,
            "credit_note": credit_note.number if credit_note else None,
        },
    )
    if previous is InvoiceStatus.SENT:
        notifications.notify(
            db,
            invoice.customer,
            "notification.invoice.cancelled",
            {"number": invoice.number, "credit_note": credit_note.number if credit_note else ""},
            f"/invoices/{invoice.id}",
        )
    db.commit()
    return credit_note


def record_payment(db: Session, *, actor: User, invoice: Invoice, note: str = "") -> Invoice:
    """FR-FA-11: paying the invoice settles every penalty and pump order on it (BR-06, BR-17)."""
    if invoice.status not in (InvoiceStatus.ISSUED, InvoiceStatus.SENT):
        raise InvalidInvoiceTransition(from_status=invoice.status.value, to_status="paid")
    if invoice.paid_at is not None:
        raise AlreadyPaid()
    now = dates.now_utc()
    invoice.paid_at = now
    invoice.paid_by = actor.id
    invoice.payment_note = note.strip() or None
    settled: list[str] = []
    for item in invoice.visible_items:
        if item.item_type is InvoiceItemType.PENALTY:
            penalty = db.get(Penalty, item.ref_id)
            if penalty is not None and penalty.status is PenaltyStatus.UNPAID:
                penalties.record_payment(
                    db, actor=actor, penalty=penalty, note=f"invoice {invoice.number}", commit=False
                )
                settled.append(f"penalty:{penalty.id}")
        elif item.item_type is InvoiceItemType.PUMP_ORDER:
            order = db.get(Order, item.ref_id)
            if order is not None and order.paid_at is None and order.status is OrderStatus.ISSUED:
                pumps.record_payment(
                    db, actor=actor, order=order, note=f"invoice {invoice.number}", commit=False
                )
                settled.append(f"pump_order:{order.id}")
    audit.record(
        db,
        actor=actor,
        action="invoice.paid",
        entity_type="invoice",
        entity_id=invoice.id,
        after={"number": invoice.number, "total": str(invoice.total), "settled": settled},
    )
    notifications.notify(
        db,
        invoice.customer,
        "notification.invoice.paid",
        {"number": invoice.number, "total": f"{invoice.total:.2f}"},
        f"/invoices/{invoice.id}",
    )
    db.commit()
    return invoice


def list_invoices(
    db: Session,
    *,
    status: InvoiceStatus | None = None,
    customer_id: int | None = None,
    username: str | None = None,
) -> list[Invoice]:
    stmt = select(Invoice)
    if status is not None:
        stmt = stmt.where(Invoice.status == status)
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if username:
        stmt = stmt.join(User, User.id == Invoice.customer_id).where(
            User.username.ilike(f"%{username.strip()}%")
        )
    return list(db.scalars(stmt.order_by(Invoice.created_at.desc(), Invoice.id.desc())))
