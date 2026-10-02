from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.services import users as users_service
from tests.conftest import login


def _audit_actions(db: Session, entity_id: int) -> list[str]:
    return list(
        db.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_type == "user", AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.id)
        )
    )


def test_admin_creates_user_with_role(admin_client: TestClient, db: Session) -> None:
    response = admin_client.post(
        "/users/new",
        data={
            "username": "Nova.Osoba",
            "display_name": "Nová Osoba",
            "password": "Password1",
            "customer_type": "external",
            "roles": ["warehouse"],
        },
    )
    assert response.status_code == 303, response.text
    user = users_service.get_by_username(db, "nova.osoba")
    assert user is not None
    assert user.role_codes == ["warehouse"]
    assert user.customer_type.value == "external"
    assert user.must_change_password is True
    assert _audit_actions(db, user.id) == ["user.created"]


def test_create_user_rejects_duplicate_and_missing_role(admin_client: TestClient) -> None:
    duplicate = admin_client.post(
        "/users/new",
        data={"username": "user", "display_name": "X", "password": "Password1", "roles": ["user"]},
    )
    assert duplicate.status_code == 400
    assert "obsadené" in duplicate.text
    no_role = admin_client.post(
        "/users/new",
        data={"username": "someone", "display_name": "X", "password": "Password1"},
    )
    assert no_role.status_code == 400
    assert "aspoň jednu rolu" in no_role.text


def test_super_admin_cannot_change_own_role(admin_client: TestClient, db: Session) -> None:
    admin = users_service.get_by_username(db, "admin")
    response = admin_client.post(f"/users/{admin.id}/roles", data={"roles": ["user"]})
    assert response.status_code == 303
    db.expire_all()
    assert users_service.get_by_username(db, "admin").role_codes == ["super_admin"]
    assert "user.roles_changed" not in _audit_actions(db, admin.id)
    page = admin_client.get(f"/users/{admin.id}")
    assert "Vlastnú rolu nie je možné meniť" in page.text


def test_forbidden_role_combination_is_rejected(admin_client: TestClient, db: Session) -> None:
    target = users_service.get_by_username(db, "warehouse")
    response = admin_client.post(
        f"/users/{target.id}/roles", data={"roles": ["warehouse", "invoicing"]}
    )
    assert response.status_code == 303
    db.expire_all()
    assert users_service.get_by_username(db, "warehouse").role_codes == ["warehouse"]
    page = admin_client.get(f"/users/{target.id}")
    assert "nie je povolená" in page.text


def test_role_change_is_audited_with_before_and_after(
    admin_client: TestClient, db: Session
) -> None:
    target = users_service.get_by_username(db, "user")
    admin_client.post(f"/users/{target.id}/roles", data={"roles": ["invoicing"]})
    entry = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "user.roles_changed", AuditLog.entity_id == str(target.id)
        )
    )
    assert entry is not None
    assert entry.before == {"roles": ["user"]}
    assert entry.after == {"roles": ["invoicing"]}
    assert entry.actor.username == "admin"


def test_deactivate_and_reactivate_are_audited(admin_client: TestClient, db: Session) -> None:
    target = users_service.get_by_username(db, "user")
    admin_client.post(f"/users/{target.id}/active", data={"active": "0"})
    admin_client.post(f"/users/{target.id}/active", data={"active": "1"})
    assert _audit_actions(db, target.id)[-2:] == ["user.deactivated", "user.activated"]
    db.expire_all()
    assert db.get(User, target.id).is_active is True


def test_admin_cannot_deactivate_own_account(admin_client: TestClient, db: Session) -> None:
    admin = users_service.get_by_username(db, "admin")
    admin_client.post(f"/users/{admin.id}/active", data={"active": "0"})
    db.expire_all()
    assert db.get(User, admin.id).is_active is True


def test_password_reset_forces_change_on_next_login(admin_client: TestClient, db: Session) -> None:
    target = users_service.get_by_username(db, "user")
    admin_client.post(f"/users/{target.id}/reset-password")
    page = admin_client.get(f"/users/{target.id}")
    assert "Dočasné heslo:" in page.text
    db.expire_all()
    assert db.get(User, target.id).must_change_password is True
    assert "user.password_reset" in _audit_actions(db, target.id)
    # Audit must never contain the password itself.
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.password_reset"))
    assert entry.after is None and entry.before is None


def test_warehouse_sees_users_read_only(client: TestClient, db: Session) -> None:
    login(client, "warehouse")
    page = client.get("/users")
    assert page.status_code == 200
    assert "Nový používateľ" not in page.text
    assert client.get("/users/new").status_code == 403
    target = users_service.get_by_username(db, "user")
    assert (
        client.post(f"/users/{target.id}/roles", data={"roles": ["warehouse"]}).status_code == 403
    )
    assert client.post(f"/users/{target.id}/active", data={"active": "0"}).status_code == 403
    assert client.post(f"/users/{target.id}/reset-password").status_code == 403


def test_plain_user_cannot_see_user_list(client: TestClient) -> None:
    login(client, "user")
    assert client.get("/users").status_code == 403
