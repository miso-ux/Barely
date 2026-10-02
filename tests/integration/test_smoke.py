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


def test_static_assets_are_referenced_relatively(client: TestClient) -> None:
    """Behind an HTTPS reverse proxy absolute http:// asset URLs are blocked as mixed content."""
    html = client.get("/login").text
    assert 'href="/static/pico.min.css"' in html
    assert 'src="/static/htmx.min.js"' in html
    assert "http://testserver/static" not in html
    assert client.get("/static/pico.min.css").status_code == 200


def test_forwarded_proto_is_trusted_for_redirects(client: TestClient) -> None:
    """Uvicorn's proxy-headers middleware is configured in entrypoint.sh; the app itself must
    not hard-code a scheme anywhere, so redirects stay relative."""
    response = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
