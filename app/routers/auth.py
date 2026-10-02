from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, login_user, logout_user, require_user
from app.db import get_db
from app.i18n import t
from app.models import User
from app.services import settings as settings_service
from app.services import users as users_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter()


def _safe_next(target: str) -> str:
    return target if target.startswith("/") and not target.startswith("//") else "/"


@router.get("/login")
def login_form(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status.HTTP_303_SEE_OTHER)
    return render(request, "auth/login.html", {"next": request.query_params.get("next", "/")})


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/",
    db: Session = Depends(get_db),
):
    try:
        user = users_service.authenticate(db, username, password)
    except DomainError as exc:
        return render(
            request,
            "auth/login.html",
            {"error": t(exc.message_key), "username": username, "next": next},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    login_user(request, user)
    if user.must_change_password:
        flash(request, t("auth.password_change_required"), "warning")
        return RedirectResponse("/password", status.HTTP_303_SEE_OTHER)
    return RedirectResponse(_safe_next(next), status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status.HTTP_303_SEE_OTHER)


@router.get("/password")
def password_form(request: Request, user: User = Depends(require_user)):
    return render(request, "auth/password.html", {"forced": user.must_change_password})


@router.post("/password")
def change_password(
    request: Request,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    new_password_confirm: Annotated[str, Form()],
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    error: str | None = None
    if new_password != new_password_confirm:
        error = t("error.password_mismatch")
    else:
        try:
            users_service.change_own_password(
                db, user=user, current_password=current_password, new_password=new_password
            )
        except DomainError as exc:
            error = t(exc.message_key, **exc.params)
    if error:
        return render(
            request,
            "auth/password.html",
            {"forced": user.must_change_password, "error": error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    flash(request, t("auth.password_changed"), "success")
    return RedirectResponse("/", status.HTTP_303_SEE_OTHER)


def _ensure_registration_enabled(db: Session) -> None:
    if not settings_service.get_bool(db, "registration_enabled"):
        raise HTTPException(status.HTTP_404_NOT_FOUND)


@router.get("/register")
def register_form(request: Request, db: Session = Depends(get_db)):
    _ensure_registration_enabled(db)
    return render(request, "auth/register.html")


@router.post("/register")
def register(
    request: Request,
    username: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirm: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    _ensure_registration_enabled(db)
    error: str | None = None
    if password != password_confirm:
        error = t("error.password_mismatch")
    else:
        try:
            user = users_service.register(
                db, username=username, display_name=display_name, password=password
            )
        except DomainError as exc:
            error = t(exc.message_key, **exc.params)
    if error:
        return render(
            request,
            "auth/register.html",
            {"error": error, "username": username, "display_name": display_name},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    login_user(request, user)
    flash(request, t("auth.registered"), "success")
    return RedirectResponse("/", status.HTTP_303_SEE_OTHER)
