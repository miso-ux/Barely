from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services import settings as settings_service
from app.services import users as users_service
from tests.conftest import DEMO_PASSWORD, login, login_admin


def test_login_with_valid_credentials_opens_dashboard(client: TestClient, db: Session) -> None:
    assert login(client, "warehouse").status_code == 303
    page = client.get("/")
    assert page.status_code == 200
    assert "Skladník Demo" in page.text
    actions = list(db.scalars(select(AuditLog.action).where(AuditLog.action == "auth.login")))
    assert actions == ["auth.login"]


def test_login_with_wrong_password_is_rejected_and_audited(client: TestClient, db: Session) -> None:
    response = login(client, "warehouse", "wrong")
    assert response.status_code == 400
    assert "Nesprávne meno alebo heslo" in response.text
    assert client.get("/").status_code == 303
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.login_failed")) is not None


def test_deactivated_user_cannot_log_in(admin_client: TestClient, db: Session) -> None:
    user = users_service.get_by_username(db, "user")
    admin_client.post(f"/users/{user.id}/active", data={"active": "0"})
    admin_client.post("/logout")
    assert login(admin_client, "user").status_code == 400


def test_logout_ends_session(client: TestClient) -> None:
    login(client, "user")
    assert client.post("/logout").status_code == 303
    assert client.get("/").status_code == 303


def test_admin_is_forced_to_change_password_first(client: TestClient) -> None:
    response = login(client, "admin")
    assert response.headers["location"] == "/password"
    # Any other page redirects back to the password form until the change is done.
    assert client.get("/users").headers["location"] == "/password"
    new_password = login_admin(client)
    assert client.get("/users").status_code == 200
    client.post("/logout")
    assert login(client, "admin", DEMO_PASSWORD).status_code == 400
    assert login(client, "admin", new_password).status_code == 303


def test_password_change_requires_matching_and_strong_password(client: TestClient) -> None:
    login(client, "user")
    mismatch = client.post(
        "/password",
        data={
            "current_password": DEMO_PASSWORD,
            "new_password": "Something123",
            "new_password_confirm": "Other123",
        },
    )
    assert mismatch.status_code == 400
    weak = client.post(
        "/password",
        data={
            "current_password": DEMO_PASSWORD,
            "new_password": "short",
            "new_password_confirm": "short",
        },
    )
    assert weak.status_code == 400
    wrong_current = client.post(
        "/password",
        data={
            "current_password": "nope",
            "new_password": "Something123",
            "new_password_confirm": "Something123",
        },
    )
    assert wrong_current.status_code == 400


def test_registration_is_disabled_by_default(client: TestClient) -> None:
    assert client.get("/register").status_code == 404
    assert (
        client.post(
            "/register",
            data={
                "username": "newbie",
                "display_name": "New",
                "password": "Password1",
                "password_confirm": "Password1",
            },
        ).status_code
        == 404
    )


def test_registration_creates_plain_user_when_enabled(
    admin_client: TestClient, db: Session
) -> None:
    admin_client.post("/admin/settings/registration_enabled", data={"value": "true"})
    admin_client.post("/logout")
    assert settings_service.get_bool(db, "registration_enabled") is True

    response = admin_client.post(
        "/register",
        data={
            "username": "newbie",
            "display_name": "New User",
            "password": "Password1",
            "password_confirm": "Password1",
        },
    )
    assert response.status_code == 303
    user = users_service.get_by_username(db, "newbie")
    assert user is not None
    assert user.role_codes == ["user"]
    assert user.must_change_password is False
    assert admin_client.get("/").status_code == 200
