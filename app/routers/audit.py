from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.models import User
from app.services import audit as audit_service
from app.web import render

router = APIRouter(prefix="/admin/audit")


@router.get("")
def list_audit(
    request: Request,
    actor: User = Depends(require_any_permission(Perm.AUDIT_READ_USERS, Perm.AUDIT_READ_ALL)),
    db: Session = Depends(get_db),
):
    entity_types = (
        None
        if actor.has_permission(Perm.AUDIT_READ_ALL)
        else audit_service.USER_MANAGEMENT_ENTITIES
    )
    return render(
        request,
        "admin/audit.html",
        {"entries": audit_service.list_entries(db, entity_types=entity_types)},
    )
