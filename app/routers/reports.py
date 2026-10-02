from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.auth.permissions import Perm
from app.db import get_db
from app.models import BarrelStatus, User
from app.services import audit, dates
from app.services import reports as reports_service
from app.services.barrel_state import Reason
from app.web import render

router = APIRouter(prefix="/reports")


def _filters(request: Request) -> reports_service.Filters:
    params = request.query_params
    today = dates.today_local()
    date_from = (
        date.fromisoformat(params["from"]) if params.get("from") else today - timedelta(days=30)
    )
    date_to = date.fromisoformat(params["to"]) if params.get("to") else today
    return reports_service.Filters(
        date_from=date_from,
        date_to=date_to,
        user=params.get("user", "").strip(),
        actor=params.get("actor", "").strip(),
        barrel=params.get("barrel", "").strip(),
        status=params.get("status", "").strip(),
        reason=params.get("reason", "").strip(),
    )


def _log_access(db: Session, actor: User, key: str, exported: bool, filters) -> None:
    """FR-SV-08: the supervisor's report views and exports are audited."""
    if not actor.has_permission(Perm.REPORTS_READ_ALL):
        return
    audit.record(
        db,
        actor=actor,
        action="report.exported" if exported else "report.viewed",
        entity_type="report",
        entity_id=key,
        after={"from": filters.date_from.isoformat(), "to": filters.date_to.isoformat()},
    )
    db.commit()


@router.get("")
def index(request: Request, actor: User = Depends(require_user)):
    available = reports_service.available_for(actor)
    if not available:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return render(request, "reports/index.html", {"reports": available})


@router.get("/{key}")
def report(
    request: Request,
    key: str,
    actor: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    perms = reports_service.REPORT_PERMISSIONS.get(key)
    if perms is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not actor.has_any_permission(*perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    filters = _filters(request)
    table = reports_service.build(db, key, filters)
    exported = request.query_params.get("format") == "csv"
    _log_access(db, actor, key, exported, filters)
    if exported:
        filename = f"{key}-{filters.date_from.isoformat()}-{filters.date_to.isoformat()}.csv"
        return Response(
            content=table.csv().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return render(
        request,
        "reports/table.html",
        {
            "table": table,
            "filters": filters,
            "statuses": [s.value for s in BarrelStatus],
            "reasons": [
                v for k, v in vars(Reason).items() if not k.startswith("_") and isinstance(v, str)
            ],
            "query": str(request.query_params),
        },
    )
