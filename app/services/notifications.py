"""In-app notifications (FR-NO). `kind` is an i18n key; params are rendered at display time."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Notification, Permission, RolePermission, User, UserRole
from app.services.dates import now_utc


def notify(
    db: Session,
    user: User,
    kind: str,
    params: dict[str, Any] | None = None,
    link: str | None = None,
) -> Notification:
    """Queue a notification in the current transaction. The caller commits."""
    notification = Notification(user_id=user.id, kind=kind, params=params or {}, link=link)
    db.add(notification)
    return notification


def users_with_permission(db: Session, permission_code: str) -> list[User]:
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == permission_code, User.is_active.is_(True))
        .distinct()
    )
    return list(db.scalars(stmt))


def notify_permission_holders(
    db: Session,
    permission_code: str,
    kind: str,
    params: dict[str, Any] | None = None,
    link: str | None = None,
    *,
    exclude: User | None = None,
) -> list[Notification]:
    return [
        notify(db, user, kind, params, link)
        for user in users_with_permission(db, permission_code)
        if exclude is None or user.id != exclude.id
    ]


def unread_count(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )


def list_for(db: Session, user: User, limit: int = 100) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def mark_read(db: Session, user: User, notification_id: int) -> Notification | None:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        return None
    if notification.read_at is None:
        notification.read_at = now_utc()
        db.commit()
    return notification


def mark_all_read(db: Session, user: User) -> int:
    unread = db.scalars(
        select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).all()
    now = now_utc()
    for notification in unread:
        notification.read_at = now
    db.commit()
    return len(unread)


def for_link(db: Session, link: str) -> list[Notification]:
    """Notifications pointing at one record, for order timelines (BR-23)."""
    stmt = (
        select(Notification)
        .where(Notification.link == link)
        .order_by(Notification.created_at, Notification.id)
    )
    return list(db.scalars(stmt))
