from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExceptionRequest, ExceptionRequestStatus, Order, OrderStatus, User
from app.services import dates, stock
from app.services import exceptions as exceptions_service
from app.services import notifications as notifications_service
from tests.conftest import login

TOMORROW = (dates.today_local() + timedelta(days=1)).isoformat()


def _user(db: Session, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _pending(db: Session) -> ExceptionRequest:
    db.expire_all()
    return db.scalar(
        select(ExceptionRequest).where(ExceptionRequest.status == ExceptionRequestStatus.PENDING)
    )


def test_request_below_limit_is_redirected_to_a_normal_order(client: TestClient) -> None:
    login(client, "user")
    response = client.post(
        "/exceptions/new",
        data={"quantity": "5", "requested_date": TOMORROW, "justification": "x"},
    )
    assert response.status_code == 400
    assert "stačí bežná objednávka" in response.text


def test_request_requires_justification(client: TestClient) -> None:
    login(client, "user")
    response = client.post(
        "/exceptions/new",
        data={"quantity": "7", "requested_date": TOMORROW, "justification": "   "},
    )
    assert response.status_code == 400
    assert "odôvodnenie" in response.text


def test_user_submits_request_and_warehouse_is_notified(client: TestClient, db: Session) -> None:
    login(client, "user")
    before = notifications_service.unread_count(db, _user(db, "warehouse"))
    response = client.post(
        "/exceptions/new",
        data={"quantity": "7", "requested_date": TOMORROW, "justification": "Teambuilding"},
    )
    assert response.status_code == 303, response.text
    assert notifications_service.unread_count(db, _user(db, "warehouse")) == before + 1
    # A request reserves nothing until it is approved.
    assert stock.reserved_count(db) == 5
    page = client.get("/exceptions")
    assert "Teambuilding" not in page.text  # list shows summary only
    assert "jana.novakova" not in page.text  # other people's requests are hidden


def test_approve_creates_order_with_reservation(client: TestClient, db: Session) -> None:
    request = _pending(db)  # seeded: jana, 8 pieces
    login(client, "warehouse")
    response = client.post(f"/exceptions/{request.id}/approve", data={"note": "OK"})
    assert response.status_code == 303
    request = db.get(ExceptionRequest, request.id)
    db.refresh(request)
    assert request.status is ExceptionRequestStatus.APPROVED
    assert request.decided_by == _user(db, "warehouse").id
    assert request.decision_note == "OK"
    order = db.get(Order, request.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.quantity == 8
    assert order.user_id == request.user_id
    assert order.created_by == _user(db, "warehouse").id
    assert stock.reserved_count(db) == 13
    assert notifications_service.unread_count(db, _user(db, "jana.novakova")) >= 1
    # Deciding twice is refused.
    client.post(f"/exceptions/{request.id}/reject")
    db.refresh(request)
    assert request.status is ExceptionRequestStatus.APPROVED


def test_approve_fails_without_enough_stock_and_stays_pending(db: Session) -> None:
    request = _pending(db)
    request.quantity = 500
    db.commit()
    warehouse = _user(db, "warehouse")
    try:
        exceptions_service.approve(db, actor=warehouse, request=request)
    except Exception as exc:  # noqa: BLE001 - we assert on the type below
        assert type(exc).__name__ == "NotEnoughFree"
    else:
        raise AssertionError("approval should fail")
    db.expire_all()
    assert db.get(ExceptionRequest, request.id).status is ExceptionRequestStatus.PENDING
    assert stock.reserved_count(db) == 5


def test_reject_notifies_user(client: TestClient, db: Session) -> None:
    request = _pending(db)
    login(client, "warehouse")
    assert (
        client.post(f"/exceptions/{request.id}/reject", data={"note": "Málo zásob"}).status_code
        == 303
    )
    db.expire_all()
    request = db.get(ExceptionRequest, request.id)
    assert request.status is ExceptionRequestStatus.REJECTED
    assert request.order_id is None
    client.post("/logout")
    login(client, "jana.novakova")
    page = client.get("/notifications")
    assert "zamietnutá" in page.text and "Málo zásob" in page.text


def test_plain_user_cannot_decide(client: TestClient, db: Session) -> None:
    request = _pending(db)
    login(client, "user")
    assert client.post(f"/exceptions/{request.id}/approve").status_code == 403
    assert client.get(f"/exceptions/{request.id}").status_code == 403


def test_supervisor_reads_requests(client: TestClient, db: Session) -> None:
    request = _pending(db)
    login(client, "supervisor")
    assert client.get("/exceptions").status_code == 200
    page = client.get(f"/exceptions/{request.id}")
    assert page.status_code == 200 and "Schváliť" not in page.text
