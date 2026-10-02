from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import Barrel, BarrelStatus, User
from app.services import barrels as barrels_service
from app.services import settings as settings_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter()


def _get_barrel_or_404(db: Session, barrel_id: int) -> Barrel:
    barrel = db.get(Barrel, barrel_id)
    if barrel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return barrel


@router.get("/warehouse")
def warehouse_dashboard(
    request: Request,
    actor: User = Depends(require_permission(Perm.BARRELS_READ)),
    db: Session = Depends(get_db),
):
    free = barrels_service.free_count(db)
    threshold = settings_service.get_int(db, "low_stock_threshold")
    return render(
        request,
        "warehouse/dashboard.html",
        {
            "counts": barrels_service.status_counts(db),
            "free": free,
            "reserved": barrels_service.reserved_count(db),
            "low_stock": free < threshold,
            "threshold": threshold,
            "near_limit": barrels_service.near_limit(db),
            "loan_limit": settings_service.get_int(db, "loan_limit"),
            "statuses": list(BarrelStatus),
        },
    )


@router.get("/barrels")
def list_barrels(
    request: Request,
    actor: User = Depends(require_permission(Perm.BARRELS_READ)),
    db: Session = Depends(get_db),
):
    raw = request.query_params.get("status")
    selected = BarrelStatus(raw) if raw in BarrelStatus.__members__.values() else None
    return render(
        request,
        "barrels/list.html",
        {
            "barrels": barrels_service.list_barrels(db, status=selected),
            "statuses": list(BarrelStatus),
            "selected": selected,
            "loan_limit": settings_service.get_int(db, "loan_limit"),
            "can_manage": actor.has_permission(Perm.BARRELS_MANAGE),
        },
    )


@router.get("/barrels/new")
def new_barrels_form(
    request: Request,
    actor: User = Depends(require_permission(Perm.BARRELS_MANAGE)),
):
    return render(request, "barrels/new.html")


@router.post("/barrels/new")
def create_barrels(
    request: Request,
    count: Annotated[int, Form()] = 1,
    code: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.BARRELS_MANAGE)),
    db: Session = Depends(get_db),
):
    try:
        created = barrels_service.create_barrels(db, actor=actor, count=count, code=code)
    except DomainError as exc:
        return render(
            request,
            "barrels/new.html",
            {"error": t(exc.message_key, **exc.params), "form": {"count": count, "code": code}},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(created) == 1:
        flash(request, t("barrels.created_one", code=created[0].code), "success")
        return RedirectResponse(f"/barrels/{created[0].id}", status.HTTP_303_SEE_OTHER)
    flash(
        request,
        t("barrels.created_many", count=len(created), first=created[0].code, last=created[-1].code),
        "success",
    )
    return RedirectResponse("/barrels", status.HTTP_303_SEE_OTHER)


@router.get("/barrels/{barrel_id}")
def barrel_detail(
    request: Request,
    barrel_id: int,
    actor: User = Depends(require_permission(Perm.BARRELS_READ)),
    db: Session = Depends(get_db),
):
    barrel = _get_barrel_or_404(db, barrel_id)
    return render(
        request,
        "barrels/detail.html",
        {
            "barrel": barrel,
            "loan_limit": settings_service.get_int(db, "loan_limit"),
            "targets": barrels_service.manual_targets(barrel),
            "can_manage": actor.has_permission(Perm.BARRELS_MANAGE),
        },
    )


@router.post("/barrels/{barrel_id}/status")
def change_status(
    request: Request,
    barrel_id: int,
    to_status: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.BARRELS_MANAGE)),
    db: Session = Depends(get_db),
):
    barrel = _get_barrel_or_404(db, barrel_id)
    try:
        target = BarrelStatus(to_status)
        barrels_service.change_status_manually(
            db, actor=actor, barrel=barrel, to_status=target, note=note
        )
    except ValueError:
        flash(request, t("error.invalid_barrel_transition"), "error")
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(
            request,
            t("barrels.status_changed", status=t(f"barrel.status.{target.value}")),
            "success",
        )
    return RedirectResponse(f"/barrels/{barrel.id}", status.HTTP_303_SEE_OTHER)
