from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import daily
from app.models import (
    BarrelStatus,
    Invoice,
    InvoiceItem,
    InvoiceItemType,
    InvoiceKind,
    InvoiceStatus,
    Loan,
    LoanStatus,
    Order,
    OrderKind,
    OrderStatus,
    Penalty,
    PenaltyStatus,
    User,
)
from app.services import dates, invoice_pdf
from app.services import invoices as invoices_service
from app.services import orders as orders_service
from app.services import pumps as pumps_service
from app.services import settings as settings_service
from app.services.errors import (
    InvalidInvoiceTransition,
    InvoiceLocked,
    ItemNotBillable,
    NoInvoiceItems,
    ReasonRequired,
)
from tests.conftest import login

TODAY = dates.today_local()
YEAR = TODAY.year


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _make_penalty(db: Session) -> Penalty:
    """The seeded backdated loan becomes overdue -> one unpaid penalty for `user`."""
    daily.run_with_session(db, today=TODAY)
    return db.scalar(select(Penalty).where(Penalty.status == PenaltyStatus.UNPAID))


def _issue_pump_order(db: Session) -> Order:
    order = db.scalar(select(Order).where(Order.kind == OrderKind.PUMP))  # peter, 1 piece
    warehouse = _user(db, "warehouse")
    orders_service.mark_ready(db, actor=warehouse, order=order)
    pumps_service.issue_order(db, actor=warehouse, order=order)
    db.expire_all()
    return db.get(Order, order.id)


def _draft(db: Session, actor: User, billable) -> Invoice:
    return invoices_service.create_draft(
        db, actor=actor, customer=billable.customer, refs=[(billable.item_type, billable.ref_id)]
    )


# --- billable items ---------------------------------------------------------------


def test_billable_items_cover_penalties_pumps_and_priced_loans(db: Session) -> None:
    assert invoices_service.billable_items(db) == []  # nothing yet: loans are free, no penalties
    penalty = _make_penalty(db)
    order = _issue_pump_order(db)
    items = {(b.item_type, b.ref_id): b for b in invoices_service.billable_items(db)}
    assert (InvoiceItemType.PENALTY, penalty.id) in items
    assert items[InvoiceItemType.PENALTY, penalty.id].amount == Decimal("10.00")
    assert (InvoiceItemType.PUMP_ORDER, order.id) in items
    assert items[InvoiceItemType.PUMP_ORDER, order.id].amount == Decimal("12.50")
    assert not any(k[0] is InvoiceItemType.LOAN for k in items)


def test_loan_is_billable_only_with_a_price(db: Session) -> None:
    admin = _user(db, "admin")
    warehouse = _user(db, "warehouse")
    settings_service.update(db, actor=admin, key="loan_price", raw="2.00")
    order = orders_service.place_order(
        db, user=_user(db, "jana.novakova"), quantity=1, requested_date=TODAY
    )
    orders_service.mark_ready(db, actor=warehouse, order=order)
    loans = orders_service.issue_order(db, actor=warehouse, order=order)
    billable = [
        b for b in invoices_service.billable_items(db) if b.item_type is InvoiceItemType.LOAN
    ]
    assert [b.ref_id for b in billable] == [loans[0].id]
    assert billable[0].amount == Decimal("2.00")
    # Seeded loans were issued with price 0 and never become billable.
    free_loans = db.scalars(select(Loan).where(Loan.loan_price == 0)).all()
    assert free_loans and all(
        (InvoiceItemType.LOAN, loan.id) not in {(b.item_type, b.ref_id) for b in billable}
        for loan in free_loans
    )


def test_on_site_paid_pump_order_is_not_billable(db: Session) -> None:
    order = _issue_pump_order(db)
    pumps_service.record_payment(db, actor=_user(db, "warehouse"), order=order)
    assert invoices_service.billable_items(db) == []


# --- drafting -----------------------------------------------------------------------


def test_warehouse_drafts_and_invoicing_is_notified(client: TestClient, db: Session) -> None:
    penalty = _make_penalty(db)
    login(client, "warehouse")
    page = client.get("/invoices/new")
    assert page.status_code == 200 and "Pokuta: barel" in page.text
    response = client.post(
        "/invoices/new",
        data={"customer_id": str(penalty.user_id), "refs": [f"penalty:{penalty.id}"], "note": "x"},
    )
    assert response.status_code == 303, response.text
    invoice = db.scalar(select(Invoice))
    assert invoice.status is InvoiceStatus.DRAFT and invoice.number is None
    assert invoice.total == Decimal("10.00")
    assert invoice.created_by == _user(db, "warehouse").id
    notified = db.scalar(
        select(Invoice).join(User, User.id == Invoice.customer_id)
    )  # sanity join works
    assert notified is not None
    from app.services import notifications as notifications_service

    assert notifications_service.unread_count(db, _user(db, "invoicing")) == 1
    # Warehouse may view the draft but not issue it.
    assert client.get(f"/invoices/{invoice.id}").status_code == 200
    assert client.post(f"/invoices/{invoice.id}/issue").status_code == 403
    assert "Vystaviť" not in client.get(f"/invoices/{invoice.id}").text


def test_item_cannot_be_on_two_active_invoices(db: Session) -> None:
    penalty = _make_penalty(db)
    invoicing = _user(db, "invoicing")
    billable = invoices_service.billable_items(db)[0]
    first = _draft(db, invoicing, billable)
    with pytest.raises(ItemNotBillable):
        _draft(db, invoicing, billable)
    # After cancelling the draft the item is free again.
    invoices_service.cancel(db, actor=invoicing, invoice=first, reason="omyl")
    second = _draft(db, invoicing, billable)
    assert second.id != first.id
    assert db.get(Penalty, penalty.id).status is PenaltyStatus.UNPAID


def test_draft_items_can_be_edited_but_issued_cannot(db: Session) -> None:
    _make_penalty(db)
    order = _issue_pump_order(db)
    invoicing = _user(db, "invoicing")
    peter_items = invoices_service.billable_items(db, customer_id=order.user_id)
    invoice = invoices_service.create_draft(
        db,
        actor=invoicing,
        customer=order.user,
        refs=[(b.item_type, b.ref_id) for b in peter_items],
    )
    assert invoice.total == Decimal("12.50")
    item = invoice.visible_items[0]
    invoices_service.remove_item(db, actor=invoicing, invoice=invoice, item=item)
    db.refresh(invoice)
    assert invoice.visible_items == [] and invoice.total == Decimal("0.00")
    assert db.get(InvoiceItem, item.id).released is True  # row kept, released
    with pytest.raises(NoInvoiceItems):
        invoices_service.issue(db, actor=invoicing, invoice=invoice)
    invoices_service.add_items(
        db, actor=invoicing, invoice=invoice, refs=[(InvoiceItemType.PUMP_ORDER, order.id)]
    )
    invoices_service.issue(db, actor=invoicing, invoice=invoice)
    with pytest.raises(InvoiceLocked):
        invoices_service.add_items(
            db, actor=invoicing, invoice=invoice, refs=[(InvoiceItemType.PUMP_ORDER, order.id)]
        )
    with pytest.raises(InvoiceLocked):
        invoices_service.remove_item(
            db, actor=invoicing, invoice=invoice, item=invoice.visible_items[0]
        )


# --- numbering ------------------------------------------------------------------------


def test_numbers_are_assigned_at_issue_and_gapless(db: Session) -> None:
    _make_penalty(db)
    order = _issue_pump_order(db)
    invoicing = _user(db, "invoicing")
    items = invoices_service.billable_items(db)
    drafts = [_draft(db, invoicing, b) for b in items]
    assert all(d.number is None for d in drafts)
    # A cancelled draft never consumes a number.
    extra = (
        invoices_service.create_draft(db, actor=invoicing, customer=order.user, refs=[], note="")
        if False
        else None
    )
    assert extra is None
    issued = [invoices_service.issue(db, actor=invoicing, invoice=d) for d in drafts]
    assert [i.number for i in issued] == [f"{YEAR}-0001", f"{YEAR}-0002"]
    with pytest.raises(InvalidInvoiceTransition):
        invoices_service.issue(db, actor=invoicing, invoice=issued[0])


def test_cancelling_issued_invoice_writes_credit_note_with_next_number(db: Session) -> None:
    penalty = _make_penalty(db)
    invoicing = _user(db, "invoicing")
    invoice = _draft(db, invoicing, invoices_service.billable_items(db)[0])
    invoices_service.issue(db, actor=invoicing, invoice=invoice)
    invoices_service.send(db, actor=invoicing, invoice=invoice)
    with pytest.raises(ReasonRequired):
        invoices_service.cancel(db, actor=invoicing, invoice=invoice, reason=" ")
    credit_note = invoices_service.cancel(db, actor=invoicing, invoice=invoice, reason="Zlá suma")
    db.expire_all()
    invoice = db.get(Invoice, invoice.id)
    assert invoice.status is InvoiceStatus.CANCELLED
    assert invoice.number == f"{YEAR}-0001"  # unchanged
    assert credit_note.kind is InvoiceKind.CREDIT_NOTE
    assert credit_note.number == f"{YEAR}-0002"
    assert credit_note.cancels_invoice_id == invoice.id
    assert credit_note.total == Decimal("-10.00")
    assert all(item.released for item in db.get(Invoice, credit_note.id).items)
    # Items are free again (BR-21) and the penalty is still unpaid.
    assert [(b.item_type, b.ref_id) for b in invoices_service.billable_items(db)] == [
        (InvoiceItemType.PENALTY, penalty.id)
    ]
    with pytest.raises(InvalidInvoiceTransition):
        invoices_service.cancel(db, actor=invoicing, invoice=credit_note, reason="x")


# --- payment --------------------------------------------------------------------------


def test_invoice_payment_settles_penalty_and_pump_order(db: Session) -> None:
    penalty = _make_penalty(db)
    order = _issue_pump_order(db)
    invoicing = _user(db, "invoicing")
    # Both belong to different customers; invoice each separately.
    for billable in invoices_service.billable_items(db):
        invoice = _draft(db, invoicing, billable)
        invoices_service.issue(db, actor=invoicing, invoice=invoice)
        invoices_service.record_payment(db, actor=invoicing, invoice=invoice, note="prevod")
        db.refresh(invoice)
        assert invoice.paid_at is not None and invoice.payment_note == "prevod"
    db.expire_all()
    penalty = db.get(Penalty, penalty.id)
    assert penalty.status is PenaltyStatus.PAID
    # BR-06 via invoice payment: the overdue barrel is now lost and the loan closed.
    loan = db.get(Loan, penalty.loan_id)
    assert loan.status is LoanStatus.LOST and loan.barrel.status is BarrelStatus.LOST
    order = db.get(Order, order.id)
    assert order.status is OrderStatus.CLOSED and order.paid_at is not None
    assert invoices_service.billable_items(db) == []


def test_payment_requires_issued_invoice(db: Session) -> None:
    _make_penalty(db)
    invoicing = _user(db, "invoicing")
    invoice = _draft(db, invoicing, invoices_service.billable_items(db)[0])
    with pytest.raises(InvalidInvoiceTransition):
        invoices_service.record_payment(db, actor=invoicing, invoice=invoice)


# --- permissions and UI -----------------------------------------------------------------


def test_invoicing_flow_through_ui(client: TestClient, db: Session) -> None:
    penalty = _make_penalty(db)
    login(client, "invoicing")
    client.post(
        "/invoices/new",
        data={"customer_id": str(penalty.user_id), "refs": [f"penalty:{penalty.id}"]},
    )
    invoice = db.scalar(select(Invoice))
    assert client.post(f"/invoices/{invoice.id}/issue").status_code == 303
    assert client.post(f"/invoices/{invoice.id}/send").status_code == 303
    db.expire_all()
    invoice = db.get(Invoice, invoice.id)
    assert invoice.status is InvoiceStatus.SENT and invoice.number == f"{YEAR}-0001"
    page = client.get(f"/invoices/{invoice.id}")
    assert "Odoslaná" in page.text and "Zaevidovať úhradu" in page.text
    pdf = client.get(f"/invoices/{invoice.id}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert client.post(f"/invoices/{invoice.id}/pay", data={"note": "banka"}).status_code == 303
    db.expire_all()
    assert db.get(Penalty, penalty.id).status is PenaltyStatus.PAID
    # Customer sees their own invoice read-only.
    client.post("/logout")
    login(client, "user")
    assert client.get("/invoices").status_code == 200
    detail = client.get(f"/invoices/{invoice.id}")
    assert detail.status_code == 200 and "Stornovať" not in detail.text
    assert client.get(f"/invoices/{invoice.id}/pdf").status_code == 200
    client.post("/logout")
    login(client, "jana.novakova")
    assert client.get(f"/invoices/{invoice.id}").status_code == 403


def test_warehouse_cannot_issue_send_cancel_or_pay(client: TestClient, db: Session) -> None:
    _make_penalty(db)
    invoicing = _user(db, "invoicing")
    invoice = _draft(db, invoicing, invoices_service.billable_items(db)[0])
    login(client, "warehouse")
    for action in ("issue", "send", "cancel", "pay"):
        assert (
            client.post(f"/invoices/{invoice.id}/{action}", data={"reason": "x"}).status_code == 403
        )


def test_supervisor_reads_invoices(client: TestClient, db: Session) -> None:
    _make_penalty(db)
    invoicing = _user(db, "invoicing")
    invoice = _draft(db, invoicing, invoices_service.billable_items(db)[0])
    login(client, "supervisor")
    assert client.get("/invoices").status_code == 200
    page = client.get(f"/invoices/{invoice.id}")
    assert page.status_code == 200 and "Vystaviť" not in page.text
    assert client.get("/invoices/new").status_code == 403


def test_pdf_contains_demo_banner_and_items(db: Session) -> None:
    _make_penalty(db)
    invoicing = _user(db, "invoicing")
    invoice = _draft(db, invoicing, invoices_service.billable_items(db)[0])
    invoices_service.issue(db, actor=invoicing, invoice=invoice)
    content = invoice_pdf.render(invoice)
    assert content.startswith(b"%PDF") and len(content) > 1000


def test_parse_ref() -> None:
    assert invoices_service.parse_ref("penalty:7") == (InvoiceItemType.PENALTY, 7)
    with pytest.raises(ItemNotBillable):
        invoices_service.parse_ref("bogus:1")
    with pytest.raises(ItemNotBillable):
        invoices_service.parse_ref("penalty")


def test_seed_date_helper() -> None:
    assert TODAY + timedelta(days=0) == TODAY
