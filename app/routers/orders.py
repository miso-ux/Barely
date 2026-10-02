from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission, require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import Order, OrderKind, OrderStatus, User
from app.services import dates, notifications, stock
from app.services import orders as orders_service
from app.services import penalties as penalties_service
from app.services import pumps as pumps_service
from app.services import returns as returns_service
from app.services import settings as settings_service
from app.services.errors import DomainError
from app.services.orders import CancelReason
from app.web import flash, render

router = APIRouter(prefix="/orders")


def _get_order_or_404(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return order


def _ensure_can_view(actor: User, order: Order) -> None:
    if order.user_id != actor.id and not actor.has_permission(Perm.ORDERS_READ_ALL):
        raise HTTPException(status.HTTP_403_FORBIDDEN)


def _parse_status(raw: str | None) -> OrderStatus | None:
    return OrderStatus(raw) if raw in OrderStatus.__members__.values() else None


@router.get("")
def list_orders(
    request: Request,
    actor: User = Depends(require_any_permission(Perm.ORDERS_READ_OWN, Perm.ORDERS_READ_ALL)),
    db: Session = Depends(get_db),
):
    see_all = actor.has_permission(Perm.ORDERS_READ_ALL)
    params = request.query_params
    selected = _parse_status(params.get("status"))
    requested_date = date.fromisoformat(params["date"]) if params.get("date") else None
    kind_raw = params.get("kind")
    kind = OrderKind(kind_raw) if kind_raw in OrderKind.__members__.values() else None
    rows = orders_service.list_orders(
        db,
        user_id=None if see_all else actor.id,
        status=selected,
        username=params.get("user") if see_all else None,
        requested_date=requested_date,
        kind=kind,
    )
    return render(
        request,
        "orders/list.html",
        {
            "orders": rows,
            "see_all": see_all,
            "statuses": list(OrderStatus),
            "selected": selected,
            "filter_user": params.get("user", ""),
            "filter_date": params.get("date", ""),
            "filter_kind": kind_raw or "",
            "kinds": list(OrderKind),
            "can_create": actor.has_permission(Perm.ORDERS_CREATE),
            "free": stock.free_count(db),
        },
    )


def _new_order_context(db: Session) -> dict:
    today = dates.today_local()
    horizon = settings_service.get_int(db, "order_horizon_days")
    return {
        "free": stock.free_count(db),
        "max_items": settings_service.get_int(db, "max_items_per_order"),
        "min_date": today.isoformat(),
        "max_date": (today + timedelta(days=horizon)).isoformat(),
        "default_date": (today + timedelta(days=1)).isoformat(),
    }


@router.get("/new")
def new_order_form(
    request: Request,
    actor: User = Depends(require_permission(Perm.ORDERS_CREATE)),
    db: Session = Depends(get_db),
):
    return render(request, "orders/new.html", _new_order_context(db))


@router.post("/new")
def create_order(
    request: Request,
    quantity: Annotated[int, Form()],
    requested_date: Annotated[date, Form()],
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.ORDERS_CREATE)),
    db: Session = Depends(get_db),
):
    try:
        order = orders_service.place_order(
            db, user=actor, quantity=quantity, requested_date=requested_date, note=note
        )
    except DomainError as exc:
        return render(
            request,
            "orders/new.html",
            {
                **_new_order_context(db),
                "error": t(exc.message_key, **exc.params),
                "form": {
                    "quantity": quantity,
                    "requested_date": requested_date.isoformat(),
                    "note": note,
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    flash(request, t("orders.created", id=order.id), "success")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)


@router.get("/{order_id}")
def order_detail(
    request: Request,
    order_id: int,
    actor: User = Depends(require_any_permission(Perm.ORDERS_READ_OWN, Perm.ORDERS_READ_ALL)),
    db: Session = Depends(get_db),
):
    order = _get_order_or_404(db, order_id)
    _ensure_can_view(actor, order)
    can_manage = actor.has_permission(Perm.ORDERS_MANAGE)
    is_owner = order.user_id == actor.id
    return render(
        request,
        "orders/detail.html",
        {
            "order": order,
            "can_manage": can_manage,
            "can_cancel": order.status in (OrderStatus.PENDING, OrderStatus.READY)
            and (can_manage or (is_owner and actor.has_permission(Perm.ORDERS_CREATE))),
            "can_prepare": can_manage and order.status is OrderStatus.PENDING,
            "can_issue": can_manage and order.status is OrderStatus.READY,
            "outstanding": returns_service.outstanding_loans(order),
            "can_return": can_manage and order.status is OrderStatus.ISSUED and not order.is_pump,
            "can_pay": order.is_pump
            and order.status is OrderStatus.ISSUED
            and order.paid_at is None
            and actor.has_permission(Perm.PAYMENTS_RECORD_ONSITE),
            "penalties": [
                p
                for p in penalties_service.list_penalties(db, user_id=order.user_id)
                if p.loan.order_id == order.id
            ],
            "notifications": notifications.for_link(db, f"/orders/{order.id}"),
        },
    )


@router.post("/{order_id}/cancel")
def cancel_order(
    request: Request,
    order_id: int,
    actor: User = Depends(require_any_permission(Perm.ORDERS_CREATE, Perm.ORDERS_MANAGE)),
    db: Session = Depends(get_db),
):
    order = _get_order_or_404(db, order_id)
    can_manage = actor.has_permission(Perm.ORDERS_MANAGE)
    if order.user_id != actor.id and not can_manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    reason = CancelReason.BY_USER if order.user_id == actor.id else CancelReason.BY_WAREHOUSE
    try:
        orders_service.cancel_order(db, actor=actor, order=order, reason=reason)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("orders.cancelled"), "success")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{order_id}/ready")
def mark_ready(
    request: Request,
    order_id: int,
    actor: User = Depends(require_permission(Perm.ORDERS_MANAGE)),
    db: Session = Depends(get_db),
):
    order = _get_order_or_404(db, order_id)
    try:
        orders_service.mark_ready(db, actor=actor, order=order)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("orders.marked_ready"), "success")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{order_id}/return")
async def return_barrels(
    request: Request,
    order_id: int,
    actor: User = Depends(require_permission(Perm.ORDERS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Form fields: condition_<loan_id> = ok | damaged | lost, plus an optional note."""
    order = _get_order_or_404(db, order_id)
    form = await request.form()
    conditions = {
        int(key.removeprefix("condition_")): str(value)
        for key, value in form.items()
        if key.startswith("condition_") and value
    }
    try:
        processed = returns_service.return_barrels(
            db, actor=actor, order=order, conditions=conditions, note=str(form.get("note", ""))
        )
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("orders.returned", count=len(processed)), "success")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{order_id}/issue")
def issue_order(
    request: Request,
    order_id: int,
    actor: User = Depends(require_permission(Perm.ORDERS_MANAGE)),
    db: Session = Depends(get_db),
):
    order = _get_order_or_404(db, order_id)
    try:
        if order.is_pump:
            pumps_service.issue_order(db, actor=actor, order=order)
            flash(request, t("orders.issued_pump", total=f"{order.total_price:.2f}"), "success")
        else:
            loans = orders_service.issue_order(db, actor=actor, order=order)
            codes = ", ".join(loan.barrel.code for loan in loans)
            flash(request, t("orders.issued", codes=codes), "success")
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{order_id}/pay")
def pay_order(
    request: Request,
    order_id: int,
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.PAYMENTS_RECORD_ONSITE)),
    db: Session = Depends(get_db),
):
    order = _get_order_or_404(db, order_id)
    if not order.is_pump:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        pumps_service.record_payment(db, actor=actor, order=order, note=note)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("orders.paid"), "success")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)
