from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_any_permission, require_permission
from app.auth.permissions import Perm
from app.db import get_db
from app.i18n import t
from app.models import Penalty, PenaltyStatus, User
from app.services import debtors as debtors_service
from app.services import penalties as penalties_service
from app.services.errors import DomainError
from app.web import flash, render

router = APIRouter()

PENALTY_READ_ALL = (Perm.PENALTIES_MANAGE, Perm.DEBTORS_READ, Perm.ORDERS_READ_ALL)


def _get_penalty_or_404(db: Session, penalty_id: int) -> Penalty:
    penalty = db.get(Penalty, penalty_id)
    if penalty is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return penalty


@router.get("/penalties")
def list_penalties(
    request: Request,
    actor: User = Depends(require_any_permission(Perm.ORDERS_READ_OWN, *PENALTY_READ_ALL)),
    db: Session = Depends(get_db),
):
    see_all = actor.has_any_permission(*PENALTY_READ_ALL)
    raw = request.query_params.get("status")
    selected = PenaltyStatus(raw) if raw in PenaltyStatus.__members__.values() else None
    return render(
        request,
        "penalties/list.html",
        {
            "penalties": penalties_service.list_penalties(
                db, user_id=None if see_all else actor.id, status=selected
            ),
            "see_all": see_all,
            "statuses": list(PenaltyStatus),
            "selected": selected,
            "can_pay": actor.has_permission(Perm.PAYMENTS_RECORD_ONSITE),
            "can_cancel": actor.has_permission(Perm.PENALTIES_MANAGE),
            "unpaid_total": penalties_service.unpaid_total(db, actor.id),
        },
    )


@router.post("/penalties/{penalty_id}/pay")
def pay_penalty(
    request: Request,
    penalty_id: int,
    note: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.PAYMENTS_RECORD_ONSITE)),
    db: Session = Depends(get_db),
):
    penalty = _get_penalty_or_404(db, penalty_id)
    try:
        penalties_service.record_payment(db, actor=actor, penalty=penalty, note=note)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("penalties.paid"), "success")
    return RedirectResponse("/penalties", status.HTTP_303_SEE_OTHER)


@router.post("/penalties/{penalty_id}/cancel")
def cancel_penalty(
    request: Request,
    penalty_id: int,
    reason: Annotated[str, Form()] = "",
    actor: User = Depends(require_permission(Perm.PENALTIES_MANAGE)),
    db: Session = Depends(get_db),
):
    penalty = _get_penalty_or_404(db, penalty_id)
    try:
        penalties_service.cancel_penalty(db, actor=actor, penalty=penalty, reason=reason)
    except DomainError as exc:
        flash(request, t(exc.message_key, **exc.params), "error")
    else:
        flash(request, t("penalties.cancelled"), "success")
    return RedirectResponse("/penalties", status.HTTP_303_SEE_OTHER)


@router.get("/debtors")
def list_debtors(
    request: Request,
    actor: User = Depends(require_permission(Perm.DEBTORS_READ)),
    db: Session = Depends(get_db),
):
    return render(request, "debtors/list.html", {"rows": debtors_service.list_debtors(db)})
