from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import daily
from app.models import AuditLog, Notification, Order, OrderStatus, User
from app.services import dates, stock
from app.services import notifications as notifications_service
from app.services import orders as orders_service
from app.services import reports as reports_service
from app.services import settings as settings_service
from tests.conftest import login

TODAY = dates.today_local()


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _filters(**overrides) -> reports_service.Filters:
    base = {"date_from": TODAY - timedelta(days=60), "date_to": TODAY}
    base.update(overrides)
    return reports_service.Filters(**base)


# --- report contents ------------------------------------------------------------


def test_movements_report_lists_seed_changes_with_filters(db: Session) -> None:
    table = reports_service.movements(db, _filters())
    reasons = {row["reason"] for row in table.rows}
    assert {"Zaradenie do evidencie", "Vydanie", "Strata", "Odpis"} <= reasons
    only_issued = reports_service.movements(db, _filters(reason="issued"))
    assert len(only_issued.rows) == 3  # two seed barrels + the retired demo barrel
    by_barrel = reports_service.movements(db, _filters(barrel="B-0030"))
    assert all(row["barrel"] == "B-0030" for row in by_barrel.rows)
    by_customer = reports_service.movements(db, _filters(user="user", reason="issued"))
    assert len(by_customer.rows) == 2


def test_environmental_report(db: Session) -> None:
    table = reports_service.environmental(db, _filters())
    statuses = sorted(row["status"] for row in table.rows)
    assert statuses == ["Odpísaný", "Stratený", "Vyradený"]
    nothing = reports_service.environmental(
        db, _filters(date_from=TODAY - timedelta(days=10), date_to=TODAY - timedelta(days=5))
    )
    assert nothing.rows == []


def test_stock_and_debtors_reports(db: Session) -> None:
    table = reports_service.stock(db, _filters(status="in_stock"))
    assert len(table.rows) == 24 and all(r["age_days"] >= 0 for r in table.rows)
    daily.run_with_session(db, today=TODAY)
    debtors = reports_service.debtors_table(db, _filters())
    assert [r["user"] for r in debtors.rows] == ["user"]
    assert str(debtors.totals["unpaid_amount"]) == "10.00"


def test_roles_report_counts_warehouse_work(db: Session) -> None:
    table = reports_service.roles_work(db, _filters())
    row = next(r for r in table.rows if r["actor"] == "warehouse")
    assert row["prepared"] == 1 and row["issued"] == 1
    assert row["avg_issue_hours"] != ""


def test_csv_export_format(db: Session) -> None:
    table = reports_service.stock(db, _filters())
    text = table.csv()
    assert text.startswith("﻿")
    lines = text.splitlines()
    assert lines[0].lstrip("﻿") == "Kód;Stav;Výpožičky;Zaradený;Vek (dni);Zmien stavu"
    assert lines[1].startswith("B-0001;")
    assert len(lines) == 1 + 30 + 1  # header, rows, totals


# --- access and auditing -------------------------------------------------------------


def test_report_access_by_role(client: TestClient) -> None:
    login(client, "warehouse")
    assert client.get("/reports").status_code == 200
    assert client.get("/reports/movements").status_code == 200
    assert client.get("/reports/roles").status_code == 403
    assert client.get("/reports/invoices").status_code == 403
    client.post("/logout")
    login(client, "invoicing")
    assert client.get("/reports/invoices").status_code == 200
    assert client.get("/reports/movements").status_code == 403
    client.post("/logout")
    login(client, "user")
    assert client.get("/reports").status_code == 403
    assert client.get("/reports/stock").status_code == 403
    assert client.get("/reports/nonsense").status_code == 404


def test_supervisor_access_is_audited_and_export_works(client: TestClient, db: Session) -> None:
    login(client, "supervisor")
    assert client.get("/reports/roles").status_code == 200
    response = client.get("/reports/movements?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "Zaradenie do evidencie" in response.text
    actions = list(
        db.scalars(
            select(AuditLog.action).where(AuditLog.entity_type == "report").order_by(AuditLog.id)
        )
    )
    assert actions == ["report.viewed", "report.exported"]
    # Warehouse access is not logged (FR-SV-08 is about the supervisor).
    client.post("/logout")
    login(client, "warehouse")
    client.get("/reports/movements")
    assert (
        db.scalar(
            select(AuditLog).where(
                AuditLog.action == "report.viewed", AuditLog.actor_id == _user(db, "warehouse").id
            )
        )
        is None
    )


def test_audit_filters_and_export(client: TestClient, db: Session) -> None:
    login(client, "supervisor")
    page = client.get("/admin/audit?action=order.created")
    assert page.status_code == 200
    assert "Objednávka vytvorená" in page.text and "Barel zaradený" not in page.text
    page = client.get("/admin/audit?actor=jana")
    assert "jana.novakova" in page.text
    export = client.get("/admin/audit?format=csv")
    assert export.status_code == 200 and export.text.startswith("﻿Kedy;Kto;Akcia")
    assert db.scalar(select(AuditLog).where(AuditLog.entity_id == "audit")) is not None


# --- notifications added in phase 7 -------------------------------------------------


def test_order_confirmation_notification(db: Session) -> None:
    jana = _user(db, "jana.novakova")
    before = notifications_service.unread_count(db, jana)
    orders_service.place_order(db, user=jana, quantity=1, requested_date=TODAY)
    assert notifications_service.unread_count(db, jana) == before + 1
    latest = db.scalar(
        select(Notification).where(Notification.user_id == jana.id).order_by(Notification.id.desc())
    )
    assert latest.kind == "notification.order.confirmed"


def test_low_stock_alert_once_per_day(db: Session) -> None:
    assert stock.notify_low_stock(db) is False  # 19 free, threshold 10
    settings_service.update(db, actor=_user(db, "admin"), key="low_stock_threshold", raw="25")
    warehouse = _user(db, "warehouse")
    before = notifications_service.unread_count(db, warehouse)
    assert stock.notify_low_stock(db) is True
    assert stock.notify_low_stock(db) is False
    assert notifications_service.unread_count(db, warehouse) == before + 1
    summary = daily.run_with_session(db, today=TODAY)
    assert summary["low_stock_alerts"] == 0


# --- timeline -------------------------------------------------------------------------


def test_order_timeline_shows_steps_and_deltas(client: TestClient, db: Session) -> None:
    issued = db.scalar(select(Order).where(Order.status == OrderStatus.ISSUED))
    login(client, "supervisor")
    page = client.get(f"/orders/{issued.id}")
    assert page.status_code == 200
    for label in ("Vytvorená", "Pripravená", "Vydaná", "Notifikácia", "Od predchádzajúceho kroku"):
        assert label in page.text
    assert " min" in page.text
