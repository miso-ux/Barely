"""BR-22 / NFR-11: the supervisor reads everything and can change nothing."""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login

WRITE_METHODS = {"post", "put", "patch", "delete"}
# Endpoints every signed-in person may use for their own session.
ALLOWED_FOR_EVERYONE = {"/login", "/logout", "/password", "/register"}


def _write_endpoints() -> list[tuple[str, str]]:
    """Every (method, path) that can change data, taken from the OpenAPI schema so new routers
    are swept automatically. Path parameters get a plausible value."""
    endpoints = []
    for path, operations in app.openapi()["paths"].items():
        if path in ALLOWED_FOR_EVERYONE:
            continue
        for method in operations:
            if method in WRITE_METHODS:
                concrete = path
                while "{" in concrete:
                    start, end = concrete.index("{"), concrete.index("}")
                    concrete = concrete[:start] + "1" + concrete[end + 1 :]
                endpoints.append((method, concrete))
    return endpoints


def test_write_endpoints_exist_to_sweep() -> None:
    assert len(_write_endpoints()) >= 5


def test_supervisor_is_rejected_on_every_write_endpoint(client: TestClient) -> None:
    login(client, "supervisor")
    rejected = {}
    for method, path in _write_endpoints():
        response = client.request(
            method, path, data={"value": "1", "roles": ["user"], "active": "0"}
        )
        rejected[f"{method.upper()} {path}"] = response.status_code
    assert all(code == 403 for code in rejected.values()), rejected


def test_supervisor_can_read(client: TestClient) -> None:
    login(client, "supervisor")
    assert client.get("/").status_code == 200
    assert client.get("/users").status_code == 200
    settings_page = client.get("/admin/settings")
    assert settings_page.status_code == 200
    main_part = settings_page.text.split("<main")[1].split("</main>")[0]
    assert "<button" not in main_part
    assert client.get("/admin/audit").status_code == 200
