import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditLog, Barrel, BarrelStatus, BarrelStatusHistory, User
from app.services import barrel_state, stock
from app.services import barrels as barrels_service
from app.services.barrel_state import TRANSITIONS, Reason
from app.services.errors import InvalidBarrelTransition
from tests.conftest import login

S = BarrelStatus


@pytest.fixture
def warehouse(client: TestClient) -> TestClient:
    login(client, "warehouse")
    return client


def _barrel(db: Session, code: str) -> Barrel:
    barrel = barrels_service.get_by_code(db, code)
    assert barrel is not None
    db.refresh(barrel)
    return barrel


# --- seed and listing -------------------------------------------------------


def test_seed_provides_demo_stock_in_every_status(db: Session) -> None:
    counts = barrels_service.status_counts(db)
    assert sum(counts.values()) == 30
    assert counts[S.DAMAGED] == 1
    assert counts[S.LOST] == 1
    assert counts[S.RETIRED] == 1
    assert counts[S.WRITTEN_OFF] == 1
    # Seed orders issue two barrels and reserve five more pieces (see test_orders).
    assert counts[S.ON_LOAN] == 2
    assert counts[S.IN_STOCK] == 24
    assert stock.free_count(db) == 19


def test_list_and_filter(warehouse: TestClient) -> None:
    page = warehouse.get("/barrels")
    assert page.status_code == 200
    assert "B-0001" in page.text and "B-0030" in page.text
    lost_only = warehouse.get("/barrels?status=lost")
    assert "B-0028" in lost_only.text
    assert "B-0001" not in lost_only.text


def test_warehouse_dashboard_shows_counts_and_near_limit(warehouse: TestClient) -> None:
    page = warehouse.get("/warehouse")
    assert page.status_code == 200
    assert "Voľné barely" in page.text
    # loan_count 8 is within 2 of the limit 10 (FR-BA-11); the two seed-issued barrels sit at
    # 10 / 10 on loan and will retire when returned.
    assert "8 / 10" in page.text and "10 / 10" in page.text


# --- adding barrels ---------------------------------------------------------


def test_bulk_add_generates_sequential_codes(warehouse: TestClient, db: Session) -> None:
    response = warehouse.post("/barrels/new", data={"count": "3"})
    assert response.status_code == 303
    for code in ("B-0031", "B-0032", "B-0033"):
        barrel = _barrel(db, code)
        assert barrel.status is S.IN_STOCK
        assert barrel.loan_count == 0
        assert [h.reason for h in barrel.history] == [Reason.CREATED]
    assert db.scalar(select(func.count()).select_from(Barrel)) == 33
    created_entries = db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "barrel.created")
    )
    assert created_entries == 33


def test_single_add_with_custom_code(warehouse: TestClient, db: Session) -> None:
    response = warehouse.post("/barrels/new", data={"count": "1", "code": "SN-2026/17"})
    assert response.status_code == 303
    assert _barrel(db, "SN-2026/17").status is S.IN_STOCK


def test_custom_code_rules(warehouse: TestClient) -> None:
    duplicate = warehouse.post("/barrels/new", data={"count": "1", "code": "B-0001"})
    assert duplicate.status_code == 400 and "už existuje" in duplicate.text
    bulk_with_code = warehouse.post("/barrels/new", data={"count": "2", "code": "X-1"})
    assert bulk_with_code.status_code == 400
    bad_shape = warehouse.post("/barrels/new", data={"count": "1", "code": "has space"})
    assert bad_shape.status_code == 400
    too_many = warehouse.post("/barrels/new", data={"count": "501"})
    assert too_many.status_code == 400


# --- manual status changes --------------------------------------------------


def test_marking_lost_requires_a_reason(warehouse: TestClient, db: Session) -> None:
    barrel = _barrel(db, "B-0001")
    warehouse.post(f"/barrels/{barrel.id}/status", data={"to_status": "lost", "note": "  "})
    assert _barrel(db, "B-0001").status is S.IN_STOCK
    page = warehouse.get(f"/barrels/{barrel.id}")
    assert "Zadajte dôvod" in page.text


def test_lost_then_found_round_trip_with_history(warehouse: TestClient, db: Session) -> None:
    barrel = _barrel(db, "B-0002")
    warehouse.post(
        f"/barrels/{barrel.id}/status", data={"to_status": "lost", "note": "Chýba po inventúre"}
    )
    assert _barrel(db, "B-0002").status is S.LOST
    warehouse.post(f"/barrels/{barrel.id}/status", data={"to_status": "in_stock", "note": ""})
    barrel = _barrel(db, "B-0002")
    assert barrel.status is S.IN_STOCK
    assert [(h.from_status, h.to_status, h.reason) for h in barrel.history] == [
        (None, S.IN_STOCK, Reason.CREATED),
        (S.IN_STOCK, S.LOST, Reason.LOST),
        (S.LOST, S.IN_STOCK, Reason.FOUND),
    ]
    assert barrel.history[1].note == "Chýba po inventúre"
    assert barrel.history[1].actor.username == "warehouse"


def test_written_off_is_final_in_ui_and_service(warehouse: TestClient, db: Session) -> None:
    barrel = _barrel(db, "B-0003")
    warehouse.post(
        f"/barrels/{barrel.id}/status", data={"to_status": "written_off", "note": "Zlomený"}
    )
    barrel = _barrel(db, "B-0003")
    assert barrel.status is S.WRITTEN_OFF
    assert barrel.written_off_at is not None
    assert barrels_service.manual_targets(barrel) == []
    page = warehouse.get(f"/barrels/{barrel.id}")
    assert "konečnom stave" in page.text
    warehouse.post(f"/barrels/{barrel.id}/status", data={"to_status": "in_stock", "note": "x"})
    assert _barrel(db, "B-0003").status is S.WRITTEN_OFF


def test_manual_change_cannot_issue_or_retire(warehouse: TestClient, db: Session) -> None:
    barrel = _barrel(db, "B-0004")
    for target in ("on_loan", "retired", "bogus"):
        warehouse.post(f"/barrels/{barrel.id}/status", data={"to_status": target, "note": "x"})
        assert _barrel(db, "B-0004").status is S.IN_STOCK


def test_found_is_only_for_lost_barrels(db: Session) -> None:
    actor = db.scalar(select(User).where(User.username == "warehouse"))
    in_stock = _barrel(db, "B-0005")
    with pytest.raises(InvalidBarrelTransition):
        barrels_service.change_status_manually(
            db, actor=actor, barrel=in_stock, to_status=S.IN_STOCK, note=""
        )


# --- state machine at service level -----------------------------------------


@pytest.mark.parametrize("from_status", list(S))
@pytest.mark.parametrize("to_status", list(S))
def test_every_transition_is_enforced(db: Session, from_status: S, to_status: S) -> None:
    barrel = Barrel(code=f"T-{from_status.value}-{to_status.value}", status=from_status)
    db.add(barrel)
    db.flush()
    if to_status in TRANSITIONS[from_status]:
        barrel_state.transition(db, barrel, to_status, actor=None, reason="test")
        db.flush()
        assert barrel.status is to_status
        history = db.scalars(
            select(BarrelStatusHistory).where(BarrelStatusHistory.barrel_id == barrel.id)
        ).all()
        assert [(h.from_status, h.to_status) for h in history] == [(from_status, to_status)]
        if to_status is S.RETIRED:
            assert barrel.retired_at is not None
    else:
        with pytest.raises(InvalidBarrelTransition):
            barrel_state.transition(db, barrel, to_status, actor=None, reason="test")
        assert barrel.status is from_status
    db.rollback()


# --- nothing is ever deleted -------------------------------------------------


@pytest.mark.parametrize("table", ["barrels", "barrel_status_history", "users"])
def test_database_rejects_deletes(db: Session, table: str) -> None:
    with pytest.raises(DBAPIError, match="never deleted"):
        db.execute(text(f"DELETE FROM {table}"))
    db.rollback()
    assert db.scalar(text(f"SELECT count(*) FROM {table}")) > 0


# --- permissions ------------------------------------------------------------


def test_plain_user_has_no_access_to_stock_pages(client: TestClient, db: Session) -> None:
    login(client, "user")
    assert client.get("/warehouse").status_code == 403
    assert client.get("/barrels").status_code == 403
    barrel = _barrel(db, "B-0001")
    assert client.get(f"/barrels/{barrel.id}").status_code == 403


def test_supervisor_reads_stock_without_action_forms(client: TestClient, db: Session) -> None:
    login(client, "supervisor")
    assert client.get("/warehouse").status_code == 200
    page = client.get("/barrels")
    assert page.status_code == 200 and "Pridať barely" not in page.text
    barrel = _barrel(db, "B-0001")
    detail = client.get(f"/barrels/{barrel.id}")
    assert detail.status_code == 200 and "Zmena stavu" not in detail.text


def test_warehouse_sees_barrel_audit(warehouse: TestClient) -> None:
    page = warehouse.get("/admin/audit")
    assert page.status_code == 200
    assert "Barel zaradený" in page.text
    assert "Zmena konfigurácie" not in page.text
