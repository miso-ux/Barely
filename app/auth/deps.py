"""Authentication and authorization dependencies.

Sessions are signed cookies holding only the user id. Swapping the login mechanism later
(Entra ID / Google via OIDC) only needs to call `login_user` after the external login succeeds.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

SESSION_USER_KEY = "user_id"
# Paths a user may visit while a password change is being enforced.
PASSWORD_CHANGE_ALLOWED_PATHS = frozenset({"/password", "/logout"})


class NotAuthenticated(Exception):
    pass


class PasswordChangeRequired(Exception):
    pass


def login_user(request: Request, user: User) -> None:
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        return None
    request.state.user = user
    return user


def require_user(request: Request, user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise NotAuthenticated()
    if user.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise PasswordChangeRequired()
    return user


def require_permission(code: str) -> Callable[..., User]:
    """Dependency factory: the signed-in user must hold `code`, otherwise 403."""

    def dependency(user: User = Depends(require_user)) -> User:
        if not user.has_permission(code):
            raise HTTPException(status.HTTP_403_FORBIDDEN)
        return user

    return dependency


def require_any_permission(*codes: str) -> Callable[..., User]:
    def dependency(user: User = Depends(require_user)) -> User:
        if not user.has_any_permission(*codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN)
        return user

    return dependency
