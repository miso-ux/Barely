from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission, require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import Invoice, InvoiceItem, InvoiceStatus, User
from app.services import invoice_pdf
from app.services import invoices as invoices_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter(prefix="/invoices")

STAFF_READ = (Perm.INVOICES_READ, Perm.INVOICES_DRAFT)
ANY_READ = (*STAFF_READ, Perm.ORDERS_READ_OWN)


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return invoice


def _sees_all(actor: User) -> bool:
    return actor.has_any_permission(*STAFF_READ)


def _ensure_can_view(actor: User, invoice: Invoice) -> None:
    if invoice.customer_id != actor.id and not _sees_all(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN)


def _parse_refs(raw: list[str]) -> list:
    return [invoices_service.parse_ref(item) for item in raw if item]


@router.get("")
def list_invoices(
    request: Request,
    actor: User = Depends(require_any_permission(*ANY_READ)),
    db: Session = Depends(get_db),
):
    see_all = _sees_all(actor)
    params = request.query_params
    raw = params.get("status")
    selected = InvoiceStatus(raw) if raw in InvoiceStatus.__members__.values() else None
    return render(
        request,
        "invoices/list.html",
        {
            "invoices": invoices_service.list_invoices(
                db,
                status=selected,
                customer_id=None if see_all else actor.id,
                username=params.get("user") if see_all else None,
            ),
            "see_all": see_all,
            "statuses": list(InvoiceStatus),
            "selected": selected,
            "filter_user": params.get("user", ""),
            "can_draft": actor.has_permission(Perm.INVOICES_DRAFT),
        },
    )


@router.get("/new")
def new_invoice_form(
    request: Request,
    actor: User = Depends(require_permission(Perm.INVOICES_DRAFT)),
    db: Session = Depends(get_db),
):
    """FR-FA-10: not yet invoiced records grouped by customer; each group becomes one draft."""
    groups: dict[int, dict] = {}
    for item in invoices_service.billable_items(db):
        group = groups.setdefault(item.customer.id, {"customer": item.customer, "items": []})
        group["items"].append(item)
    return render(request, "invoices/new.html", {"groups": list(groups.values())})


@router.post("/new")
def create_draft(
    request: Request,
    customer_id: Annotated[int, Form()],
    refs: Annotated[list[str] | None, Form()] = None,
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.INVOICES_DRAFT)),
    db: Session = Depends(get_db),
):
    customer = db.get(User, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        invoice = invoices_service.create_draft(
            db, actor=actor, customer=customer, refs=_parse_refs(refs or []), note=note
        )
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
        return RedirectResponse("/invoices/new", status.HTTP_303_SEE_OTHER)
    flash(request, t("invoice.created", id=invoice.id), "success")
    return RedirectResponse(f"/invoices/{invoice.id}", status.HTTP_303_SEE_OTHER)


@router.get("/{invoice_id}")
def invoice_detail(
    request: Request,
    invoice_id: int,
    actor: User = Depends(require_any_permission(*ANY_READ)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    _ensure_can_view(actor, invoice)
    can_draft = actor.has_permission(Perm.INVOICES_DRAFT)
    can_issue = actor.has_permission(Perm.INVOICES_ISSUE)
    return render(
        request,
        "invoices/detail.html",
        {
            "invoice": invoice,
            "credit_notes": invoices_service.list_invoices(db, customer_id=invoice.customer_id),
            "can_edit": can_draft and invoice.is_draft,
            "can_issue": can_issue and invoice.is_draft,
            "can_send": can_issue and invoice.status is InvoiceStatus.ISSUED,
            "can_cancel": can_issue and invoice.is_active and invoice.kind.value == "invoice",
            "can_pay": actor.has_permission(Perm.INVOICES_RECORD_PAYMENT)
            and invoice.status in (InvoiceStatus.ISSUED, InvoiceStatus.SENT)
            and invoice.paid_at is None,
            "billable": invoices_service.billable_items(db, customer_id=invoice.customer_id)
            if can_draft and invoice.is_draft
            else [],
        },
    )


@router.get("/{invoice_id}/pdf")
def invoice_pdf_view(
    invoice_id: int,
    actor: User = Depends(require_any_permission(*ANY_READ)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    _ensure_can_view(actor, invoice)
    filename = f"invoice-{invoice.number or invoice.id}.pdf"
    return Response(
        content=invoice_pdf.render(invoice),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/{invoice_id}/items")
def add_items(
    request: Request,
    invoice_id: int,
    refs: Annotated[list[str] | None, Form()] = None,
    actor: User = Depends(require_permission(Perm.INVOICES_DRAFT)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    try:
        invoices_service.add_items(db, actor=actor, invoice=invoice, refs=_parse_refs(refs or []))
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("invoice.items_added"), "success")
    return RedirectResponse(f"/invoices/{invoice.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{invoice_id}/items/{item_id}/remove")
def remove_item(
    request: Request,
    invoice_id: int,
    item_id: int,
    actor: User = Depends(require_permission(Perm.INVOICES_DRAFT)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    item = db.get(InvoiceItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        invoices_service.remove_item(db, actor=actor, invoice=invoice, item=item)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("invoice.item_removed"), "success")
    return RedirectResponse(f"/invoices/{invoice.id}", status.HTTP_303_SEE_OTHER)


def _action(request: Request, db: Session, invoice: Invoice, fn, success_key: str, **kwargs):
    try:
        fn(db, invoice=invoice, **kwargs)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t(success_key), "success")
    return RedirectResponse(f"/invoices/{invoice.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{invoice_id}/issue")
def issue(
    request: Request,
    invoice_id: int,
    actor: User = Depends(require_permission(Perm.INVOICES_ISSUE)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    return _action(request, db, invoice, invoices_service.issue, "invoice.issued", actor=actor)


@router.post("/{invoice_id}/send")
def send(
    request: Request,
    invoice_id: int,
    actor: User = Depends(require_permission(Perm.INVOICES_ISSUE)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    return _action(request, db, invoice, invoices_service.send, "invoice.sent", actor=actor)


@router.post("/{invoice_id}/cancel")
def cancel(
    request: Request,
    invoice_id: int,
    reason: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.INVOICES_ISSUE)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    return _action(
        request,
        db,
        invoice,
        invoices_service.cancel,
        "invoice.cancelled",
        actor=actor,
        reason=reason,
    )


@router.post("/{invoice_id}/pay")
def pay(
    request: Request,
    invoice_id: int,
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.INVOICES_RECORD_PAYMENT)),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    return _action(
        request,
        db,
        invoice,
        invoices_service.record_payment,
        "invoice.paid",
        actor=actor,
        note=note,
    )
