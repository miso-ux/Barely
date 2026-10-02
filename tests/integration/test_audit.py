import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests.conftest import login


def test_audit_log_rejects_update_and_delete(db: Session) -> None:
    entry = db.scalar(select(AuditLog).limit(1))
    assert entry is not None, "seed should have produced audit entries"

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE audit_log SET action = 'tampered' WHERE id = :id"), {"id": entry.id}
        )
    db.rollback()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})
    db.rollback()

    assert db.get(AuditLog, entry.id).action == entry.action


def test_admin_sees_user_management_audit_only(admin_client: TestClient) -> None:
    page = admin_client.get("/admin/audit")
    assert page.status_code == 200
    assert "Používateľ vytvorený" in page.text


def test_roles_without_audit_permission_are_rejected(client: TestClient) -> None:
    login(client, "user")
    assert client.get("/admin/audit").status_code == 403
