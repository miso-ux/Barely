from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.models import User
from app.services import audit as audit_service
from app.web import render

router = APIRouter(prefix="/admin/audit")

AUDIT_PERMISSIONS = (
    Perm.AUDIT_READ_ALL,
    Perm.AUDIT_READ_USERS,
    Perm.AUDIT_READ_OPERATIONS,
    Perm.AUDIT_READ_INVOICING,
)


def visible_entity_types(user: User) -> frozenset[str] | None:
    """None means everything; otherwise the union of entity groups the user may see."""
    if user.has_permission(Perm.AUDIT_READ_ALL):
        return None
    visible: frozenset[str] = frozenset()
    if user.has_permission(Perm.AUDIT_READ_USERS):
        visible |= audit_service.USER_MANAGEMENT_ENTITIES
    if user.has_permission(Perm.AUDIT_READ_OPERATIONS):
        visible |= audit_service.OPERATIONS_ENTITIES
    if user.has_permission(Perm.AUDIT_READ_INVOICING):
        visible |= audit_service.INVOICING_ENTITIES
    return visible


@router.get("")
def list_audit(
    request: Request,
    actor: User = Depends(require_any_permission(*AUDIT_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "admin/audit.html",
        {"entries": audit_service.list_entries(db, entity_types=visible_entity_types(actor))},
    )
