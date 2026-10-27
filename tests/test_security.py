"""Authentication, validation, limits, headers and production configuration."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.conftest import ADMIN, SERVICE


def future(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_health_is_public_and_minimal(make_client):
    with make_client() as c:
        r = c.get("/api/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.parametrize("method,path", [
    ("get", "/api/events"), ("get", "/api/config"), ("get", "/api/communities"),
    ("post", "/api/events/1/radar/run"), ("get", "/api/events/1/stats"), ("delete", "/api/events/1"),
])
def test_admin_routes_need_the_access_key(make_client, method, path):
    with make_client() as c:
        assert getattr(c, method)(path).status_code == 401
        assert getattr(c, method)(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
        # The service key must not unlock organiser routes.
        assert getattr(c, method)(path, headers={"X-Service-Key": SERVICE}).status_code == 401


def test_service_routes_accept_service_key_or_admin(make_client):
    with make_client() as c:
        event = c.post("/api/events", json={"name": "Hack Night", "city": "Pune"},
                       headers={"Authorization": f"Bearer {ADMIN}"}).json()
        body = {"event_id": event["id"], "name": "Riya", "role": "designer"}
        assert c.post("/api/register", json=body).status_code == 401
        registered = c.post("/api/register", json=body, headers={"X-Service-Key": SERVICE})
        assert registered.status_code == 200
        assert c.get(f"/api/participants/{registered.json()['id']}",
                     headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 200


def test_repeated_bad_keys_get_blocked(make_client):
    with make_client(AUTH_FAILURES_PER_15MIN="3") as c:
        codes = [c.get("/api/events", headers={"Authorization": "Bearer nope"}).status_code for _ in range(5)]
        assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
        # Even the right key is refused from a blocked address until the window passes.
        assert c.get("/api/events", headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 429


def test_rate_limit(make_client):
    with make_client(RATE_LIMIT_PER_MINUTE="10") as c:
        h = {"Authorization": f"Bearer {ADMIN}"}
        codes = [c.get("/api/events", headers=h).status_code for _ in range(12)]
        assert codes.count(429) == 2 and "Retry-After" in c.get("/api/events", headers=h).headers


@pytest.mark.parametrize("body,field", [
    ({"name": "<script>alert(1)</script>", "city": "Pune"}, "name"),
    ({"name": "Hack", "city": "12345"}, "city"),
    ({"name": "Hack", "city": "Pune", "start_date": "2001-01-01"}, "start_date"),
    ({"name": "Hack", "city": "Pune", "start_date": future(5000)}, "start_date"),
    ({"name": "Hack", "city": "Pune", "tags": ["DROP TABLE;"]}, "tags.0"),
    ({"name": "Hack", "city": "Pune", "team_size": 50}, "team_size"),
    ({"name": "Hack", "city": "Pune", "is_admin": True}, "is_admin"),
    ({"name": "x" * 500, "city": "Pune"}, "name"),
])
def test_event_validation(client, body, field):
    r = client.post("/api/events", json=body)
    assert r.status_code == 422, r.text
    assert any(e["field"] == field for e in r.json()["errors"]), r.json()
    assert "<script>" not in r.text  # never echo input back


def test_text_is_cleaned(client):
    r = client.post("/api/events", json={"name": "  Hack‮  Night\x00 ", "city": "Pune", "start_date": future()})
    assert r.status_code == 201 and r.json()["name"] == "Hack Night"


def test_hindi_names_are_allowed(client, service_headers):
    ev = client.post("/api/events", json={"name": "Hack Night", "city": "Pune"}).json()
    r = client.post("/api/register", headers=service_headers,
                    json={"event_id": ev["id"], "name": "मीरा शर्मा", "role": "designer"})
    assert r.status_code == 200 and r.json()["name"] == "मीरा शर्मा"


@pytest.mark.parametrize("body", [
    {"name": "A", "role": "hacker"},
    {"name": "A", "role": "developer", "experience": "too-many"},
    {"name": "A", "role": "developer", "ref_payload": "o_'; DROP--"},
    {"name": "", "role": "developer"},
    {"name": "A", "role": "developer", "language": "fr"},
])
def test_registration_validation(client, service_headers, body):
    ev = client.post("/api/events", json={"name": "Hack Night", "city": "Pune"}).json()
    body = {"event_id": ev["id"], **body}
    assert client.post("/api/register", json=body, headers=service_headers).status_code == 422


def test_path_and_query_validation(client):
    assert client.get("/api/events/0").status_code == 422
    assert client.get("/api/events/99999999999").status_code == 422
    assert client.get("/api/ref/resolve", params={"payload": "../etc"}).status_code == 422
    assert client.get("/api/events/1/outreach", params={"status": "all; drop"}).status_code == 422


def test_approval_requires_tracked_link(client):
    ev = client.post("/api/events", json={"name": "AI Hack", "city": "Pune", "tags": ["ai"]}).json()
    o = client.post(f"/api/events/{ev['id']}/radar/run").json()["outreach"][0]
    client.patch(f"/api/outreach/{o['id']}", json={"draft": "Hello, please share our event with your group!"})
    r = client.post(f"/api/outreach/{o['id']}/approve")
    assert r.status_code == 422 and "tracked link" in r.json()["detail"]


def test_body_size_limit(client):
    r = client.post("/api/events", content=b"{" + b" " * 70_000 + b"}", headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_security_headers(make_client):
    with make_client() as c:
        api = c.get("/api/health")
        assert api.headers["X-Content-Type-Options"] == "nosniff"
        assert api.headers["Cache-Control"] == "no-store"
        assert api.headers["X-Frame-Options"] == "DENY"
        page = c.get("/")
        assert page.status_code == 200
        csp = page.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp


def test_no_inline_scripts_or_styles_in_pages(make_client):
    with make_client() as c:
        for path in ("/", "/app/", "/submit/", "/track/", "/join/"):
            html = c.get(path).text
            assert "<script>" not in html and "style=" not in html and "<style" not in html, path


def test_simulator_can_be_disabled(make_client):
    with make_client(ENABLE_SIMULATOR="0") as c:
        h = {"Authorization": f"Bearer {ADMIN}"}
        ev = c.post("/api/events", json={"name": "Hack Night", "city": "Pune"}, headers=h).json()
        assert c.post(f"/api/events/{ev['id']}/simulate", headers=h).status_code == 404


def test_production_refuses_weak_config(monkeypatch, tmp_path):
    from app.config import ConfigError, load_settings
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    monkeypatch.setenv("SERVICE_API_KEY", "b" * 40)
    with pytest.raises(ConfigError):
        load_settings()
    monkeypatch.setenv("ADMIN_TOKEN", "b" * 40)
    with pytest.raises(ConfigError):
        load_settings()  # same value as the service key
    monkeypatch.setenv("ADMIN_TOKEN", "a" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ConfigError):
        load_settings()
    monkeypatch.setenv("CORS_ORIGINS", "https://radar.example.org")
    s = load_settings()
    assert s.is_production and not s.enable_docs and not s.enable_simulator and not s.seed_demo_event


def test_docs_hidden_in_production(make_client):
    with make_client(APP_ENV="production", ENABLE_DOCS="0", SEED_DIRECTORY="0") as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
