from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, User
from app.services import notifications as notifications_service
from tests.conftest import login


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def test_bell_shows_unread_count_and_reading_records_time(client: TestClient, db: Session) -> None:
    warehouse = _user(db, "warehouse")
    unread = notifications_service.unread_count(db, warehouse)
    assert unread >= 3  # seed: 3 new orders + 1 exception request
    login(client, "warehouse")
    page = client.get("/")
    assert f'<span class="pill">{unread}</span>' in page.text

    notification = db.scalar(
        select(Notification).where(
            Notification.user_id == warehouse.id, Notification.read_at.is_(None)
        )
    )
    response = client.post(f"/notifications/{notification.id}/read")
    assert response.status_code == 303
    assert response.headers["location"] == notification.link
    db.refresh(notification)
    assert notification.read_at is not None
    assert notifications_service.unread_count(db, warehouse) == unread - 1

    client.post("/notifications/read-all")
    assert notifications_service.unread_count(db, warehouse) == 0


def test_users_cannot_read_each_others_notifications(client: TestClient, db: Session) -> None:
    warehouse = _user(db, "warehouse")
    notification = db.scalar(select(Notification).where(Notification.user_id == warehouse.id))
    login(client, "user")
    client.post(f"/notifications/{notification.id}/read")
    db.refresh(notification)
    assert notification.read_at is None
    page = client.get("/notifications")
    assert "Nová objednávka" not in page.text


def test_order_timeline_lists_notifications_with_read_time(client: TestClient, db: Session) -> None:
    login(client, "warehouse")
    client.post("/notifications/read-all")
    notification = db.scalar(
        select(Notification).where(Notification.kind == "notification.order.new")
    )
    page = client.get(notification.link)
    assert page.status_code == 200
    assert "Notifikácia" in page.text and "prečítané" in page.text
