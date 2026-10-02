from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import User
from app.services import audit as audit_service
from app.services import reports as reports_service
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
    params = request.query_params
    date_from = date.fromisoformat(params["from"]) if params.get("from") else None
    date_to = date.fromisoformat(params["to"]) if params.get("to") else None
    exported = params.get("format") == "csv"
    entries = audit_service.list_entries(
        db,
        entity_types=visible_entity_types(actor),
        actor=params.get("actor", ""),
        action=params.get("action", ""),
        entity_type=params.get("entity", ""),
        date_from=date_from,
        date_to=date_to,
        limit=0 if exported else 500,
    )
    if exported:
        if actor.has_permission(Perm.REPORTS_READ_ALL):
            audit_service.record(
                db, actor=actor, action="report.exported", entity_type="report", entity_id="audit"
            )
            db.commit()
        table = reports_service.Table(
            "audit",
            [
                ("when", "audit.when"),
                ("who", "audit.who"),
                ("action", "audit.action"),
                ("entity", "audit.entity"),
                ("before", "audit.before"),
                ("after", "audit.after"),
            ],
            [
                {
                    "when": e.created_at,
                    "who": e.actor.username if e.actor else t("audit.system"),
                    "action": t(f"audit.action.{e.action}"),
                    "entity": f"{e.entity_type} {e.entity_id or ''}".strip(),
                    "before": e.before or "",
                    "after": e.after or "",
                }
                for e in entries
            ],
        )
        return Response(
            content=table.csv().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
        )
    return render(
        request,
        "admin/audit.html",
        {
            "entries": entries,
            "filters": {
                "actor": params.get("actor", ""),
                "action": params.get("action", ""),
                "entity": params.get("entity", ""),
                "from": params.get("from", ""),
                "to": params.get("to", ""),
            },
            "query": str(request.query_params),
        },
    )
