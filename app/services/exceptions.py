"""Exception requests for orders above the per-order limit (FR-ZV-01..04)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.models import ExceptionRequest, ExceptionRequestStatus, User
from app.services import audit, dates, notifications, orders
from app.services import settings as settings_service
from app.services.errors import (
    InvalidExceptionTransition,
    JustificationRequired,
    NotAnException,
    NotEnoughFree,
)


def _params(request: ExceptionRequest) -> dict[str, object]:
    return {
        "request_id": request.id,
        "username": request.user.username,
        "quantity": request.quantity,
        "date": dates.format_date(request.requested_date),
    }


def create_request(
    db: Session, *, user: User, quantity: int, requested_date: date, justification: str
) -> ExceptionRequest:
    max_items = settings_service.get_int(db, "max_items_per_order")
    if quantity <= max_items:
        raise NotAnException(max=max_items)
    if not justification.strip():
        raise JustificationRequired()
    # Same date and debtor rules as a normal order; availability is checked at approval.
    orders.validate_barrel_order(
        db, user=user, quantity=quantity, requested_date=requested_date, allow_over_limit=True
    )
    request = ExceptionRequest(
        user_id=user.id,
        quantity=quantity,
        requested_date=requested_date,
        justification=justification.strip(),
        status=ExceptionRequestStatus.PENDING,
    )
    db.add(request)
    db.flush()
    db.refresh(request)
    audit.record(
        db,
        actor=user,
        action="exception.created",
        entity_type="exception_request",
        entity_id=request.id,
        after={"quantity": quantity, "requested_date": requested_date.isoformat()},
    )
    notifications.notify_permission_holders(
        db,
        Perm.EXCEPTIONS_DECIDE,
        "notification.exception.new",
        _params(request),
        f"/exceptions/{request.id}",
    )
    db.commit()
    return request


def _ensure_pending(request: ExceptionRequest, to_status: ExceptionRequestStatus) -> None:
    if request.status is not ExceptionRequestStatus.PENDING:
        raise InvalidExceptionTransition(
            from_status=request.status.value, to_status=to_status.value
        )


def approve(db: Session, *, actor: User, request: ExceptionRequest, note: str = "") -> None:
    """FR-ZV-04: approval creates the order with its reservation, or fails without changes."""
    _ensure_pending(request, ExceptionRequestStatus.APPROVED)
    try:
        order = orders.create_order(
            db,
            actor=actor,
            user=request.user,
            quantity=request.quantity,
            requested_date=request.requested_date,
            note=request.justification,
            allow_over_limit=True,
        )
    except NotEnoughFree:
        db.rollback()
        raise
    request.status = ExceptionRequestStatus.APPROVED
    request.decided_by = actor.id
    request.decided_at = dates.now_utc()
    request.decision_note = note.strip() or None
    request.order_id = order.id
    audit.record(
        db,
        actor=actor,
        action="exception.approved",
        entity_type="exception_request",
        entity_id=request.id,
        after={"order_id": order.id, "note": request.decision_note},
    )
    notifications.notify(
        db,
        request.user,
        "notification.exception.approved",
        {**_params(request), "order_id": order.id},
        f"/orders/{order.id}",
    )
    db.commit()


def reject(db: Session, *, actor: User, request: ExceptionRequest, note: str = "") -> None:
    _ensure_pending(request, ExceptionRequestStatus.REJECTED)
    request.status = ExceptionRequestStatus.REJECTED
    request.decided_by = actor.id
    request.decided_at = dates.now_utc()
    request.decision_note = note.strip() or None
    audit.record(
        db,
        actor=actor,
        action="exception.rejected",
        entity_type="exception_request",
        entity_id=request.id,
        after={"note": request.decision_note},
    )
    notifications.notify(
        db,
        request.user,
        "notification.exception.rejected",
        {**_params(request), "note": request.decision_note or ""},
        f"/exceptions/{request.id}",
    )
    db.commit()


def list_requests(
    db: Session, *, user_id: int | None = None, status: ExceptionRequestStatus | None = None
) -> list[ExceptionRequest]:
    stmt = select(ExceptionRequest)
    if user_id is not None:
        stmt = stmt.where(ExceptionRequest.user_id == user_id)
    if status is not None:
        stmt = stmt.where(ExceptionRequest.status == status)
    stmt = stmt.order_by(
        ExceptionRequest.status, ExceptionRequest.requested_date, ExceptionRequest.id
    )
    return list(db.scalars(stmt))


def pending_count(db: Session) -> int:
    return len(list_requests(db, status=ExceptionRequestStatus.PENDING))
