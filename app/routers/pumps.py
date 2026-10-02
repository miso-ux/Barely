from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import PumpProduct, User
from app.services import dates
from app.services import pumps as pumps_service
from app.services import settings as settings_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter(prefix="/pumps")


def _get_product_or_404(db: Session, product_id: int) -> PumpProduct:
    product = db.get(PumpProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return product


def _catalogue(db: Session, actor: User) -> list[dict]:
    products = pumps_service.list_products(
        db, active_only=not actor.has_permission(Perm.PUMPS_MANAGE)
    )
    return [
        {
            "product": p,
            "free": pumps_service.free(db, p),
            "reserved": pumps_service.reserved(db, p.id),
        }
        for p in products
    ]


@router.get("")
def list_pumps(
    request: Request,
    actor: User = Depends(require_permission(Perm.PUMPS_READ)),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "pumps/list.html",
        {
            "rows": _catalogue(db, actor),
            "can_manage": actor.has_permission(Perm.PUMPS_MANAGE),
            "can_buy": actor.has_permission(Perm.ORDERS_CREATE),
        },
    )


@router.get("/new")
def new_product_form(
    request: Request, actor: User = Depends(require_permission(Perm.PUMPS_MANAGE))
):
    return render(request, "pumps/new.html")


@router.post("/new")
def create_product(
    request: Request,
    name: Annotated[str, Form()],
    price: Annotated[str, Form()],
    actor: User = Depends(require_permission(Perm.PUMPS_MANAGE)),
    db: Session = Depends(get_db),
):
    try:
        product = pumps_service.create_product(
            db, actor=actor, name=name, price=pumps_service.parse_price(price)
        )
    except DomainError as exc:
        return render(
            request,
            "pumps/new.html",
            {"error": t(exc.message_key, **exc.params), "form": {"name": name, "price": price}},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    flash(request, t("pumps.created", name=product.name), "success")
    return RedirectResponse(f"/pumps/{product.id}", status.HTTP_303_SEE_OTHER)


def _order_form_context(db: Session, actor: User) -> dict:
    today = dates.today_local()
    horizon = settings_service.get_int(db, "order_horizon_days")
    return {
        "rows": [row for row in _catalogue(db, actor) if row["product"].is_active],
        "min_date": today.isoformat(),
        "max_date": (today + timedelta(days=horizon)).isoformat(),
        "default_date": (today + timedelta(days=1)).isoformat(),
    }


@router.get("/order")
def order_form(
    request: Request,
    actor: User = Depends(require_permission(Perm.ORDERS_CREATE)),
    db: Session = Depends(get_db),
):
    return render(request, "pumps/order.html", _order_form_context(db, actor))


@router.post("/order")
def place_order(
    request: Request,
    product_id: Annotated[int, Form()],
    quantity: Annotated[int, Form()],
    requested_date: Annotated[date, Form()],
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.ORDERS_CREATE)),
    db: Session = Depends(get_db),
):
    product = _get_product_or_404(db, product_id)
    try:
        order = pumps_service.place_order(
            db,
            user=actor,
            product=product,
            quantity=quantity,
            requested_date=requested_date,
            note=note,
        )
    except DomainError as exc:
        return render(
            request,
            "pumps/order.html",
            {
                **_order_form_context(db, actor),
                "error": t(exc.message_key, **exc.params),
                "form": {
                    "product_id": product_id,
                    "quantity": quantity,
                    "requested_date": requested_date.isoformat(),
                    "note": note,
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    flash(request, t("pumps.ordered", id=order.id), "success")
    return RedirectResponse(f"/orders/{order.id}", status.HTTP_303_SEE_OTHER)


@router.get("/report")
def sales_report(
    request: Request,
    actor: User = Depends(require_permission(Perm.PUMPS_READ)),
    db: Session = Depends(get_db),
):
    today = dates.today_local()
    params = request.query_params
    date_from = date.fromisoformat(params["from"]) if params.get("from") else today.replace(day=1)
    date_to = date.fromisoformat(params["to"]) if params.get("to") else today
    report = pumps_service.sales_report(db, date_from=date_from, date_to=date_to)
    return render(request, "pumps/report.html", {"report": report})


@router.get("/{product_id}")
def product_detail(
    request: Request,
    product_id: int,
    actor: User = Depends(require_permission(Perm.PUMPS_READ)),
    db: Session = Depends(get_db),
):
    product = _get_product_or_404(db, product_id)
    return render(
        request,
        "pumps/detail.html",
        {
            "product": product,
            "free": pumps_service.free(db, product),
            "reserved": pumps_service.reserved(db, product.id),
            "can_manage": actor.has_permission(Perm.PUMPS_MANAGE),
        },
    )


@router.post("/{product_id}")
def update_product(
    request: Request,
    product_id: int,
    name: Annotated[str, Form()],
    price: Annotated[str, Form()],
    is_active: Annotated[str, Form()] = "0",
    actor: User = Depends(require_permission(Perm.PUMPS_MANAGE)),
    db: Session = Depends(get_db),
):
    product = _get_product_or_404(db, product_id)
    try:
        pumps_service.update_product(
            db,
            actor=actor,
            product=product,
            name=name,
            price=pumps_service.parse_price(price),
            is_active=is_active == "1",
        )
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("pumps.updated"), "success")
    return RedirectResponse(f"/pumps/{product.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{product_id}/receive")
def receive_stock(
    request: Request,
    product_id: int,
    quantity: Annotated[int, Form()],
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.PUMPS_MANAGE)),
    db: Session = Depends(get_db),
):
    product = _get_product_or_404(db, product_id)
    try:
        pumps_service.receive_stock(db, actor=actor, product=product, quantity=quantity, note=note)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("pumps.received", quantity=quantity, stock=product.stock), "success")
    return RedirectResponse(f"/pumps/{product.id}", status.HTTP_303_SEE_OTHER)
