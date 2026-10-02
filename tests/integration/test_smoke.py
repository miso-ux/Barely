from fastapi.testclient import TestClient


def test_health_reports_database_connection(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_anonymous_is_redirected_to_login(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_login_page_renders_in_slovak(client: TestClient) -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "Prihlásenie" in response.text
