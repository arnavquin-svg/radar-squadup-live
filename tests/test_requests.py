"""Event hosts submit requests publicly; the organiser accepts or declines them in the desk."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.conftest import ADMIN


def request_body(**overrides):
    body = {
        "contact_name": "Kavya Rao",
        "contact_email": "Kavya.Rao@Example.org",
        "contact_phone": "+91 98765 43210",
        "organisation": "Synthetic Institute Coding Club",
        "event_name": "Campus AI Hack",
        "city": "Pune",
        "start_date": (date.today() + timedelta(days=40)).isoformat(),
        "venue": "Main hall",
        "description": "A beginner-friendly 24-hour AI hackathon for first and second year students.",
        "tags": ["ai", "hackathon", "beginner"],
        "expected_participants": 120,
        "consent": True,
    }
    body.update(overrides)
    return body


def test_full_request_lifecycle(make_client):
    with make_client() as c:
        r = c.post("/api/requests", json=request_body())
        assert r.status_code == 201, r.text
        ref, token = r.json()["reference"], r.json()["token"]
        assert ref.startswith("RQ-") and len(token) >= 32

        status = c.post("/api/requests/status", json={"token": token}).json()
        assert status["status"] == "new" and status["progress"] is None
        assert "contact_email" not in str(status) and "98765" not in str(status)

        admin = {"Authorization": f"Bearer {ADMIN}"}
        listed = c.get("/api/requests", headers=admin).json()
        assert listed[0]["contact_email"] == "kavya.rao@example.org" and "token_hash" not in listed[0]

        accepted = c.post(f"/api/requests/{listed[0]['id']}/accept", headers=admin).json()
        event = c.get(f"/api/events/{accepted['event_id']}", headers=admin).json()
        assert event["name"] == "Campus AI Hack" and "ai" in event["tags"]
        assert c.post(f"/api/requests/{listed[0]['id']}/accept", headers=admin).status_code == 409

        c.post(f"/api/events/{event['id']}/radar/run", headers=admin)
        progress = c.post("/api/requests/status", json={"token": token}).json()["progress"]
        assert progress["groups_found"] > 0 and progress["registrations"] == 0


def test_decline_with_note(make_client):
    with make_client() as c:
        token = c.post("/api/requests", json=request_body()).json()["token"]
        admin = {"Authorization": f"Bearer {ADMIN}"}
        rid = c.get("/api/requests", headers=admin).json()[0]["id"]
        c.post(f"/api/requests/{rid}/decline", json={"note": "Dates clash with another event we run."}, headers=admin)
        s = c.post("/api/requests/status", json={"token": token}).json()
        assert s["status"] == "declined" and "clash" in s["decision_note"]


def test_request_admin_routes_are_protected(make_client):
    with make_client() as c:
        assert c.get("/api/requests").status_code == 401
        assert c.post("/api/requests/1/accept").status_code == 401


@pytest.mark.parametrize("override,field", [
    ({"contact_email": "not-an-email"}, "contact_email"),
    ({"contact_email": "a@b"}, "contact_email"),
    ({"contact_phone": "call me"}, "contact_phone"),
    ({"contact_phone": "123"}, "contact_phone"),
    ({"consent": False}, "consent"),
    ({"description": "too short"}, "description"),
    ({"start_date": "2000-01-01"}, "start_date"),
    ({"expected_participants": 3}, "expected_participants"),
    ({"event_name": "<img src=x>"}, "event_name"),
    ({"organisation": "!!!"}, "organisation"),
    ({"role": "admin"}, "role"),
])
def test_request_validation(make_client, override, field):
    with make_client() as c:
        r = c.post("/api/requests", json=request_body(**override))
        assert r.status_code == 422, r.text
        assert any(e["field"] == field for e in r.json()["errors"])


def test_honeypot_stores_nothing(make_client):
    with make_client() as c:
        r = c.post("/api/requests", json=request_body(website="http://spam.example"))
        assert r.status_code == 201
        assert c.get("/api/requests", headers={"Authorization": f"Bearer {ADMIN}"}).json() == []


def test_duplicates_and_flood_limits(make_client):
    with make_client() as c:
        assert c.post("/api/requests", json=request_body()).status_code == 201
        assert c.post("/api/requests", json=request_body()).status_code == 409
        codes = [c.post("/api/requests", json=request_body(event_name=f"Hack Night {i}")).status_code for i in range(6)]
        assert codes.count(429) >= 2


def test_bad_or_unknown_tokens(make_client):
    with make_client() as c:
        assert c.post("/api/requests/status", json={"token": "short"}).status_code == 422
        assert c.post("/api/requests/status", json={"token": "x" * 43}).status_code == 404
