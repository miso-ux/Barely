from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import User
from app.services import settings as settings_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter(prefix="/admin/settings")


@router.get("")
def list_settings(
    request: Request,
    actor: User = Depends(require_permission(Perm.SETTINGS_READ)),
    db: Session = Depends(get_db),
):
    rows = settings_service.get_all(db)
    return render(
        request,
        "admin/settings.html",
        {
            "rows": rows,
            "kinds": {row.key: settings_service.value_type(row.key) for row in rows},
            "can_manage": actor.has_permission(Perm.SETTINGS_MANAGE),
        },
    )


@router.post("/{key}")
def update_setting(
    request: Request,
    key: str,
    value: Annotated[str, Form()],
    actor: User = Depends(require_permission(Perm.SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    try:
        settings_service.update(db, actor=actor, key=key, raw=value)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("settings.saved", key=t(f"setting.{key}.label")), "success")
    return RedirectResponse("/admin/settings", status.HTTP_303_SEE_OTHER)
