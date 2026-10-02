from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.services import notifications as notifications_service
from app.web import render

router = APIRouter(prefix="/notifications")


@router.get("")
def list_notifications(
    request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    return render(
        request,
        "notifications/list.html",
        {"notifications": notifications_service.list_for(db, user)},
    )


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Marks the reader's own notification as read; the read time is evidence (FR-NO-05)."""
    notification = notifications_service.mark_read(db, user, notification_id)
    target = notification.link if notification and notification.link else "/notifications"
    return RedirectResponse(target, status.HTTP_303_SEE_OTHER)


@router.post("/read-all")
def mark_all_read(user: User = Depends(require_user), db: Session = Depends(get_db)):
    notifications_service.mark_all_read(db, user)
    return RedirectResponse("/notifications", status.HTTP_303_SEE_OTHER)
