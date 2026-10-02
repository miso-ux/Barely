from fastapi.testclient import TestClient


def test_health_reports_database_connection(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_in_slovak(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Evidencia barelov" in response.text
