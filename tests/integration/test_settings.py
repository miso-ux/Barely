from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services import settings as settings_service
from tests.conftest import login


def test_defaults_are_seeded(db: Session) -> None:
    assert settings_service.get_int(db, "max_items_per_order") == 5
    assert settings_service.get_decimal(db, "penalty_amount") == Decimal("10.00")
    assert settings_service.get_int(db, "loan_limit") == 10
    assert settings_service.get_decimal(db, "loan_price") == Decimal("0.00")
    assert settings_service.get_bool(db, "block_debtors") is True
    assert settings_service.get_bool(db, "registration_enabled") is False


def test_admin_change_is_applied_and_audited(admin_client: TestClient, db: Session) -> None:
    response = admin_client.post("/admin/settings/penalty_amount", data={"value": "12,5"})
    assert response.status_code == 303
    assert settings_service.get_decimal(db, "penalty_amount") == Decimal("12.50")
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "setting.changed"))
    assert entry is not None
    assert entry.entity_id == "penalty_amount"
    assert entry.before == {"value": "10.00"}
    assert entry.after == {"value": "12.50"}


def test_invalid_value_is_rejected_without_change(admin_client: TestClient, db: Session) -> None:
    admin_client.post("/admin/settings/loan_limit", data={"value": "ten"})
    assert settings_service.get_int(db, "loan_limit") == 10
    admin_client.post("/admin/settings/loan_limit", data={"value": "-1"})
    assert settings_service.get_int(db, "loan_limit") == 10
    admin_client.post("/admin/settings/forbidden_role_combinations", data={"value": "{}"})
    assert len(settings_service.get_list(db, "forbidden_role_combinations")) == 3
    assert db.scalar(select(AuditLog).where(AuditLog.action == "setting.changed")) is None


def test_unknown_key_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.post("/admin/settings/does_not_exist", data={"value": "1"})
    assert response.status_code == 303
    page = admin_client.get("/admin/settings")
    assert "Neznáme nastavenie" in page.text


def test_warehouse_cannot_read_or_change_settings(client: TestClient) -> None:
    login(client, "warehouse")
    assert client.get("/admin/settings").status_code == 403
    assert client.post("/admin/settings/loan_limit", data={"value": "3"}).status_code == 403
