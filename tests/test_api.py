"""End-to-end API tests: event -> radar -> approval gate -> registration -> teams -> stats."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


def make_event(client, **overrides):
    body = {
        "name": "Test AI Hackathon",
        "city": "Pune",
        "description": "A beginner-friendly AI hackathon for students. Mentors on site.",
        "tags": ["AI", "hackathon", "beginner"],
        "start_date": (date.today() + timedelta(days=30)).isoformat(),
        "venue": "Test Hall",
    }
    body.update(overrides)
    r = client.post("/api/events", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_seed(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/communities").json()) >= 30


def test_profile_and_ranking(client):
    ev = make_event(client)
    assert {"ai", "hackathon", "beginner"} <= set(ev["profile"]["themes"])
    assert ev["profile"]["skill_level"] == "beginner-friendly"
    assert "mr" in ev["profile"]["languages"]

    run = client.post(f"/api/events/{ev['id']}/radar/run").json()
    ranking = run["ranking"]
    assert ranking and ranking[0]["community"]["name"] == "Pune AI Circle"
    top = ranking[0]
    assert top["score"] == pytest.approx(22 * len(top["overlaps"]) + 25 + top["size_factor"])
    assert all(r["score"] >= ranking[i + 1]["score"] for i, r in enumerate(ranking[:-1]))
    assert all(o["status"] == "pending" for o in run["outreach"])
    assert len(run["outreach"]) == len(ranking)


def test_approval_gate_and_language_switch(client):
    ev = make_event(client)
    outreach = client.post(f"/api/events/{ev['id']}/radar/run").json()["outreach"]
    o = outreach[0]
    assert o["link_active"] is False

    # Unapproved links still let people in but are not attributed.
    info = client.get("/api/ref/resolve", params={"payload": f"o_{o['ref_code']}"}).json()
    assert info["kind"] == "direct"

    hi = client.patch(f"/api/outreach/{o['id']}", json={"language": "hi"}).json()
    assert "नमस्ते" in hi["draft"] and o["link"] in hi["draft"]

    approved = client.post(f"/api/outreach/{o['id']}/approve").json()
    assert approved["status"] == "approved" and approved["link_active"]
    assert client.patch(f"/api/outreach/{o['id']}", json={"draft": "x" * 20}).status_code == 409

    info = client.get("/api/ref/resolve", params={"payload": f"o_{o['ref_code']}"}).json()
    assert info["kind"] == "community"
    assert client.post("/api/ref/click", params={"payload": f"o_{o['ref_code']}"}).json()["tracked"]


def test_team_balancing_and_referrals(client):
    ev = make_event(client)
    o = client.post(f"/api/events/{ev['id']}/radar/run").json()["outreach"][0]
    client.post(f"/api/outreach/{o['id']}/approve")
    payload = f"o_{o['ref_code']}"

    roles = ["developer", "designer", "domain_expert", "presenter"]
    people = [client.post("/api/register", json={"name": f"P{i}", "role": r, "ref_payload": payload}).json()
              for i, r in enumerate(roles)]
    assert len({p["team_id"] for p in people}) == 1
    assert people[-1]["team"]["is_full"]

    # A second developer must not join a dev-heavy team when a balanced option is missing.
    d2 = client.post("/api/register", json={"name": "Dev Two", "role": "developer",
                                            "ref_payload": payload}).json()
    assert d2["team_id"] != people[0]["team_id"]
    assert d2["source_outreach_id"] == o["id"]

    # Referral gets priority placement into the referrer's team, even with a duplicate role.
    friend = client.post("/api/register", json={"name": "Friend", "role": "developer",
                                                "ref_payload": f"r_{d2['invite_code']}"}).json()
    assert friend["team_id"] == d2["team_id"] and friend["referrer_id"] == d2["id"]

    card = client.get(f"/api/teams/{d2['team_id']}/card").json()
    assert card["filled"] == 2 and "designer" in card["label"]

    # Withdrawing frees the seat; confirmation updates status.
    client.post(f"/api/participants/{friend['id']}/withdraw")
    assert client.get(f"/api/teams/{d2['team_id']}/card").json()["filled"] == 1
    assert client.post(f"/api/participants/{d2['id']}/confirm").json()["status"] == "confirmed"


def test_college_feeds_directory_and_stats(client):
    ev = make_event(client)
    o = client.post(f"/api/events/{ev['id']}/radar/run").json()["outreach"][0]
    client.post(f"/api/outreach/{o['id']}/approve")
    p = client.post("/api/register", json={"name": "Meera", "role": "designer", "event_id": ev["id"],
                                           "ref_payload": f"o_{o['ref_code']}"}).json()
    client.patch(f"/api/participants/{p['id']}", json={"college": "Synthetic Institute of Design"})
    names = [c["name"] for c in client.get("/api/communities").json()]
    assert "Synthetic Institute of Design" in names

    sim = client.post(f"/api/events/{ev['id']}/simulate", json={"count": 20}).json()
    assert sim["created"] == 20
    stats = client.get(f"/api/events/{ev['id']}/stats").json()
    assert stats["kpis"]["registrations"] == 21
    assert stats["kpis"]["discovered_communities"] == 1
    assert sum(stats["roles"].values()) == 21
    teams = client.get(f"/api/events/{ev['id']}/teams").json()
    assert all(t["filled"] <= t["size"] for t in teams)


def test_simulate_requires_approval(client):
    ev = make_event(client)
    client.post(f"/api/events/{ev['id']}/radar/run")
    assert client.post(f"/api/events/{ev['id']}/simulate").status_code == 400
