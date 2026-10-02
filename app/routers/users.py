from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import CustomerType, User
from app.services import users as users_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter(prefix="/users")


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return user


@router.get("")
def list_users(
    request: Request,
    actor: User = Depends(require_permission(Perm.USERS_READ)),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "users/list.html",
        {
            "users": users_service.list_users(db),
            "can_manage": actor.has_permission(Perm.USERS_MANAGE),
        },
    )


@router.get("/new")
def new_user_form(
    request: Request,
    actor: User = Depends(require_permission(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "users/form.html",
        {"roles": users_service.list_roles(db), "customer_types": list(CustomerType)},
    )


@router.post("/new")
def create_user(
    request: Request,
    username: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    customer_type: Annotated[str, Form()] = CustomerType.INTERNAL.value,
    roles: Annotated[list[str] | None, Form()] = None,
    actor: User = Depends(require_permission(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    try:
        user = users_service.create_user(
            db,
            actor=actor,
            username=username,
            display_name=display_name,
            password=password,
            role_codes=roles or [],
            customer_type=CustomerType(customer_type),
        )
    except (DomainError, ValueError) as exc:
        message = t(exc.message_key, **exc.params) if isinstance(exc, DomainError) else str(exc)
        return render(
            request,
            "users/form.html",
            {
                "roles": users_service.list_roles(db),
                "customer_types": list(CustomerType),
                "error": message,
                "form": {
                    "username": username,
                    "display_name": display_name,
                    "roles": roles or [],
                    "customer_type": customer_type,
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    flash(request, t("users.created", username=user.username), "success")
    return RedirectResponse(f"/users/{user.id}", status.HTTP_303_SEE_OTHER)


@router.get("/{user_id}")
def user_detail(
    request: Request,
    user_id: int,
    actor: User = Depends(require_permission(Perm.USERS_READ)),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    return render(
        request,
        "users/detail.html",
        {
            "user": user,
            "roles": users_service.list_roles(db),
            "can_manage": actor.has_permission(Perm.USERS_MANAGE),
            "is_self": actor.id == user.id,
        },
    )


@router.post("/{user_id}/roles")
def change_roles(
    request: Request,
    user_id: int,
    roles: Annotated[list[str] | None, Form()] = None,
    actor: User = Depends(require_permission(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    try:
        users_service.set_roles(db, actor=actor, user=user, role_codes=roles or [])
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("users.roles_changed"), "success")
    return RedirectResponse(f"/users/{user.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/active")
def change_active(
    request: Request,
    user_id: int,
    active: Annotated[str, Form()],
    actor: User = Depends(require_permission(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    try:
        users_service.set_active(db, actor=actor, user=user, active=active == "1")
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        key = "users.activated" if user.is_active else "users.deactivated"
        flash(request, t(key), "success")
    return RedirectResponse(f"/users/{user.id}", status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/reset-password")
def reset_password(
    request: Request,
    user_id: int,
    actor: User = Depends(require_permission(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    temporary = users_service.reset_password(db, actor=actor, user=user)
    flash(request, t("users.password_reset", password=temporary), "warning")
    return RedirectResponse(f"/users/{user.id}", status.HTTP_303_SEE_OTHER)
