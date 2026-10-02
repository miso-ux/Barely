from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission, require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import ExceptionRequest, ExceptionRequestStatus, User
from app.services import dates, stock
from app.services import exceptions as exceptions_service
from app.services import settings as settings_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter(prefix="/exceptions")

READ_PERMISSIONS = (Perm.EXCEPTIONS_CREATE, Perm.EXCEPTIONS_DECIDE, Perm.ORDERS_READ_ALL)


def _get_request_or_404(db: Session, request_id: int) -> ExceptionRequest:
    item = db.get(ExceptionRequest, request_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return item


def _sees_all(actor: User) -> bool:
    return actor.has_any_permission(Perm.EXCEPTIONS_DECIDE, Perm.ORDERS_READ_ALL)


@router.get("")
def list_requests(
    request: Request,
    actor: User = Depends(require_any_permission(*READ_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    see_all = _sees_all(actor)
    return render(
        request,
        "exceptions/list.html",
        {
            "requests": exceptions_service.list_requests(db, user_id=None if see_all else actor.id),
            "see_all": see_all,
            "can_create": actor.has_permission(Perm.EXCEPTIONS_CREATE),
        },
    )


def _form_context(db: Session) -> dict:
    today = dates.today_local()
    horizon = settings_service.get_int(db, "order_horizon_days")
    return {
        "max_items": settings_service.get_int(db, "max_items_per_order"),
        "free": stock.free_count(db),
        "min_date": today.isoformat(),
        "max_date": (today + timedelta(days=horizon)).isoformat(),
        "default_date": (today + timedelta(days=1)).isoformat(),
    }


@router.get("/new")
def new_request_form(
    request: Request,
    actor: User = Depends(require_permission(Perm.EXCEPTIONS_CREATE)),
    db: Session = Depends(get_db),
):
    return render(request, "exceptions/new.html", _form_context(db))


@router.post("/new")
def create_request(
    request: Request,
    quantity: Annotated[int, Form()],
    requested_date: Annotated[date, Form()],
    justification: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.EXCEPTIONS_CREATE)),
    db: Session = Depends(get_db),
):
    try:
        item = exceptions_service.create_request(
            db,
            user=actor,
            quantity=quantity,
            requested_date=requested_date,
            justification=justification,
        )
    except DomainError as exc:
        return render(
            request,
            "exceptions/new.html",
            {
                **_form_context(db),
                "error": t(exc.message_key, **exc.params),
                "form": {
                    "quantity": quantity,
                    "requested_date": requested_date.isoformat(),
                    "justification": justification,
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    flash(request, t("exceptions.created"), "success")
    return RedirectResponse(f"/exceptions/{item.id}", status.HTTP_303_SEE_OTHER)


@router.get("/{request_id}")
def request_detail(
    request: Request,
    request_id: int,
    actor: User = Depends(require_any_permission(*READ_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    item = _get_request_or_404(db, request_id)
    if item.user_id != actor.id and not _sees_all(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return render(
        request,
        "exceptions/detail.html",
        {
            "item": item,
            "can_decide": actor.has_permission(Perm.EXCEPTIONS_DECIDE)
            and item.status is ExceptionRequestStatus.PENDING,
        },
    )


@router.post("/{request_id}/approve")
def approve(
    request: Request,
    request_id: int,
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.EXCEPTIONS_DECIDE)),
    db: Session = Depends(get_db),
):
    item = _get_request_or_404(db, request_id)
    try:
        exceptions_service.approve(db, actor=actor, request=item, note=note)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("exceptions.approved"), "success")
    return RedirectResponse(f"/exceptions/{item.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{request_id}/reject")
def reject(
    request: Request,
    request_id: int,
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.EXCEPTIONS_DECIDE)),
    db: Session = Depends(get_db),
):
    item = _get_request_or_404(db, request_id)
    try:
        exceptions_service.reject(db, actor=actor, request=item, note=note)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("exceptions.rejected"), "success")
    return RedirectResponse(f"/exceptions/{item.id}", status.HTTP_303_SEE_OTHER)
