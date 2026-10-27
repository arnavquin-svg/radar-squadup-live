"""RadiUp.ai API and website.

Run (development):  uvicorn app.main:app --reload
Production:         APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import radar, squad
from .config import Settings, get_settings
from .db import connect, dumps, init_db, row_to_dict, rows_to_dicts
from .schemas import (
    MAX_ID,
    MAX_TELEGRAM_ID,
    PAYLOAD_RE,
    CommunityCreate,
    EventCreate,
    EventRequestCreate,
    OutreachUpdate,
    ParticipantUpdate,
    RadarRun,
    RegistrationCreate,
    RequestDecision,
    SimulateRequest,
    TrackRequest,
)
from .security import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    client_ip,
    limiter,
    require_admin,
    require_service,
)
from .seed import SYNTHETIC_NAMES, seed_communities, seed_demo_event

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
log = logging.getLogger("radar.api")

Id = Annotated[int, PathParam(gt=0, le=MAX_ID)]
admin = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])
service = APIRouter(prefix="/api", dependencies=[Depends(require_service)])
public = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def tracked_link(payload: str) -> str:
    base = (os.getenv("SITE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/")
    return f"{base}/join/?start={payload}"


def get_event_or_404(conn: sqlite3.Connection, event_id: int) -> dict[str, Any]:
    event = row_to_dict(conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
    if not event:
        raise HTTPException(404, f"Event {event_id} not found")
    return event


def latest_event(conn: sqlite3.Connection) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 1").fetchone())


def serialize_outreach(row: dict[str, Any]) -> dict[str, Any]:
    row["link"] = tracked_link(f"o_{row['ref_code']}")
    row["link_active"] = row["status"] == "approved"
    row["edited"] = bool(row.get("edited"))
    row["language_name"] = radar.LANGUAGE_NAMES.get(row["language"], row["language"])
    return row


_OUTREACH_FILTERS = {
    "id": "o.id = ?",
    "event": "o.event_id = ?",
    "event_status": "o.event_id = ? AND o.status = ?",
}


def outreach_with_community(conn: sqlite3.Connection, where: str, params: tuple) -> list[dict[str, Any]]:
    where = _OUTREACH_FILTERS[where]  # only fixed, internal clauses; values are always bound parameters
    rows = conn.execute(
        f"""SELECT o.*, c.name AS community_name, c.platform, c.city AS community_city, c.size AS community_size,
                   c.kind AS community_kind, c.admin_name, c.languages AS community_languages
            FROM outreach o JOIN communities c ON c.id = o.community_id
            WHERE {where} ORDER BY o.score DESC, c.name""",
        params,
    ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["community_languages"] = _json_list(d.get("community_languages"))
        out.append(serialize_outreach(d))
    return out


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    try:
        return json.loads(value or "[]")
    except (TypeError, ValueError):
        return []


def get_outreach_or_404(conn: sqlite3.Connection, outreach_id: int) -> dict[str, Any]:
    rows = outreach_with_community(conn, "id", (outreach_id,))
    if not rows:
        raise HTTPException(404, f"Outreach draft {outreach_id} not found")
    return rows[0]


def resolve_payload(conn: sqlite3.Connection, payload: Optional[str]) -> dict[str, Any]:
    """Turn a Telegram /start payload into attribution: community link, referral, or direct."""
    payload = (payload or "").strip()
    if payload and not PAYLOAD_RE.match(payload):
        payload = ""
    kind, _, code = payload.partition("_")

    if kind == "o" and code:
        o = conn.execute(
            """SELECT o.id, o.event_id, o.status, c.name AS community_name
               FROM outreach o JOIN communities c ON c.id = o.community_id WHERE o.ref_code = ?""",
            (code,),
        ).fetchone()
        if o:
            event = get_event_or_404(conn, o["event_id"])
            if o["status"] == "approved":
                return {"kind": "community", "event": event, "outreach_id": o["id"],
                        "community_name": o["community_name"], "referrer": None, "payload": payload}
            # Link leaked before approval: allow sign-up, but do not attribute it.
            return {"kind": "direct", "event": event, "outreach_id": None,
                    "community_name": None, "referrer": None, "payload": payload}

    if kind == "r" and code:
        p = conn.execute(
            """SELECT p.id, p.name, p.event_id, p.team_id, p.status, t.number AS team_number
               FROM participants p LEFT JOIN teams t ON t.id = p.team_id WHERE p.invite_code = ?""",
            (code,),
        ).fetchone()
        if p:
            return {
                "kind": "referral",
                "event": get_event_or_404(conn, p["event_id"]),
                "outreach_id": None,
                "community_name": None,
                "referrer": {"id": p["id"], "first_name": p["name"].split()[0],
                             "team_number": p["team_number"], "active": p["status"] != "withdrawn"},
                "payload": payload,
            }

    if kind == "e" and code.isdigit():
        event = row_to_dict(conn.execute("SELECT * FROM events WHERE id = ?", (int(code),)).fetchone())
        if event:
            return {"kind": "direct", "event": event, "outreach_id": None,
                    "community_name": None, "referrer": None, "payload": payload}

    event = latest_event(conn)
    if not event:
        raise HTTPException(404, "No events are open for registration yet")
    return {"kind": "direct", "event": event, "outreach_id": None,
            "community_name": None, "referrer": None, "payload": payload}


def record_discovered_community(conn: sqlite3.Connection, college: str, event: dict[str, Any],
                                language: str) -> None:
    """SquadUp -> Radar feedback loop: unknown colleges/clubs join the directory."""
    name = college.strip()
    if len(name) < 3:
        return
    exists = conn.execute("SELECT 1 FROM communities WHERE lower(name) = lower(?)", (name,)).fetchone()
    if exists:
        return
    tags = [radar.normalise_tag(t) for t in event.get("tags", [])][:4]
    conn.execute(
        """INSERT INTO communities (name, kind, platform, city, tags, size, languages, admin_name, discovered_via)
           VALUES (?, 'discovered via SquadUp', 'other', ?, ?, 50, ?, '', 'squadup_referral')""",
        (name, event["city"], dumps(tags), dumps(sorted({language, "en"}))),
    )


def participant_view(conn: sqlite3.Connection, participant_id: int) -> dict[str, Any]:
    row = conn.execute(
        """SELECT p.*, e.name AS event_name, e.start_date, e.city AS event_city, t.number AS team_number
           FROM participants p JOIN events e ON e.id = p.event_id
           LEFT JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
        (participant_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Participant {participant_id} not found")
    data = dict(row)
    data["invite_link"] = tracked_link(f"r_{data['invite_code']}")
    data["team"] = squad.team_card(conn, data["team_id"]) if data["team_id"] else None
    data["is_synthetic"] = bool(data["is_synthetic"])
    return data


def register_participant(conn: sqlite3.Connection, body: RegistrationCreate,
                         synthetic: bool = False) -> tuple[dict[str, Any], bool]:
    """Core registration used by the API, the bot and the simulator. Returns (participant, created)."""
    attribution = resolve_payload(conn, body.ref_payload) if body.ref_payload or not body.event_id else None
    if body.event_id:
        event = get_event_or_404(conn, body.event_id)
        if attribution and attribution["event"]["id"] != event["id"]:
            attribution = None
    else:
        event = attribution["event"]  # type: ignore[index]

    if body.telegram_id is not None:
        existing = conn.execute(
            "SELECT id, status FROM participants WHERE event_id = ? AND telegram_id = ?",
            (event["id"], body.telegram_id),
        ).fetchone()
        if existing:
            if existing["status"] == "withdrawn":
                # Coming back after withdrawing: re-run matching with their (possibly new) role.
                team_id, _ = squad.assign_team(conn, event["id"], body.role, event["team_size"])
                conn.execute(
                    """UPDATE participants SET status = 'registered', role = ?, experience = ?, language = ?,
                       team_id = ? WHERE id = ?""",
                    (body.role, body.experience, body.language, team_id, existing["id"]),
                )
                return participant_view(conn, existing["id"]), True
            return participant_view(conn, existing["id"]), False

    outreach_id = attribution["outreach_id"] if attribution and attribution["kind"] == "community" else None
    referrer_id = (attribution["referrer"]["id"]
                   if attribution and attribution["kind"] == "referral" and attribution["referrer"]["active"]
                   else None)

    team_id, _reason = squad.assign_team(conn, event["id"], body.role, event["team_size"], referrer_id)
    cur = conn.execute(
        """INSERT INTO participants (event_id, name, telegram_id, language, role, experience,
                                     source_outreach_id, referrer_id, team_id, invite_code, college, is_synthetic)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event["id"], body.name.strip(), body.telegram_id, body.language, body.role, body.experience,
         outreach_id, referrer_id, team_id, squad.new_invite_code(), body.college.strip(), int(synthetic)),
    )
    if body.college:
        record_discovered_community(conn, body.college, event, body.language)
    return participant_view(conn, int(cur.lastrowid)), True


# --------------------------------------------------------------------------- #
# Health & config
# --------------------------------------------------------------------------- #
@public.get("/health", tags=["meta"])
def health() -> dict[str, Any]:
    with connect() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@admin.get("/config", tags=["meta"])
def config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "bot_username": settings.bot_username,
        "environment": settings.env,
        "simulator_enabled": settings.enable_simulator,
        "roles": [{"id": r, "label": squad.ROLE_LABELS[r]} for r in squad.ROLES],
        "languages": [{"id": k, "label": v} for k, v in radar.LANGUAGE_NAMES.items()],
        "themes": [{"id": k, "label": v} for k, v in radar.THEME_LABELS.items()],
    }


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
@admin.post("/events", status_code=201, tags=["events"])
def create_event(body: EventCreate) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO events (name, city, description, tags, start_date, venue, team_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.name.strip(), body.city.strip(), body.description.strip(), dumps(body.tags),
             body.start_date.isoformat() if body.start_date else None, body.venue.strip(), body.team_size),
        )
        event = get_event_or_404(conn, int(cur.lastrowid))
    event["profile"] = radar.build_profile(event)
    event["direct_link"] = tracked_link(f"e_{event['id']}")
    return event


@admin.get("/events", tags=["events"])
def list_events() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = rows_to_dicts(conn.execute(
            """SELECT e.*,
                      (SELECT COUNT(*) FROM participants p WHERE p.event_id = e.id AND p.status != 'withdrawn')
                        AS registrations
               FROM events e ORDER BY e.id DESC"""
        ).fetchall())
    for e in rows:
        e["direct_link"] = tracked_link(f"e_{e['id']}")
    return rows


@admin.get("/events/{event_id}", tags=["events"])
def get_event(event_id: Id) -> dict[str, Any]:
    with connect() as conn:
        event = get_event_or_404(conn, event_id)
    event["profile"] = radar.build_profile(event)
    event["direct_link"] = tracked_link(f"e_{event['id']}")
    return event


@admin.delete("/events/{event_id}", status_code=204, tags=["events"])
def delete_event(event_id: Id) -> None:
    with connect() as conn:
        get_event_or_404(conn, event_id)
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


@admin.get("/events/{event_id}/profile", tags=["radar"])
def event_profile(event_id: Id) -> dict[str, Any]:
    with connect() as conn:
        return radar.build_profile(get_event_or_404(conn, event_id))


# --------------------------------------------------------------------------- #
# Communities directory
# --------------------------------------------------------------------------- #
@admin.get("/communities", tags=["radar"])
def list_communities(city: Optional[str] = Query(None, min_length=2, max_length=60)) -> list[dict[str, Any]]:
    with connect() as conn:
        if city:
            rows = conn.execute("SELECT * FROM communities WHERE lower(city) = lower(?) ORDER BY name", (city,))
        else:
            rows = conn.execute("SELECT * FROM communities ORDER BY city, name")
        return rows_to_dicts(rows.fetchall())


@admin.post("/communities", status_code=201, tags=["radar"])
def create_community(body: CommunityCreate) -> dict[str, Any]:
    with connect() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO communities (name, kind, platform, city, tags, size, languages, admin_name, discovered_via)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'organizer')""",
                (body.name.strip(), body.kind.strip() or "club", body.platform, body.city.strip(),
                 dumps([radar.normalise_tag(t) for t in body.tags]), body.size, dumps(body.languages),
                 body.admin_name.strip()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"A community named '{body.name}' already exists")
        return row_to_dict(conn.execute("SELECT * FROM communities WHERE id = ?", (cur.lastrowid,)).fetchone())


# --------------------------------------------------------------------------- #
# Radar: rank + draft (nothing is ever sent automatically)
# --------------------------------------------------------------------------- #
@admin.post("/events/{event_id}/radar/run", tags=["radar"])
def run_radar(event_id: Id, body: Optional[RadarRun] = None) -> dict[str, Any]:
    limit = body.limit if body else 12
    with connect() as conn:
        event = get_event_or_404(conn, event_id)
        profile = radar.build_profile(event)
        communities = rows_to_dicts(conn.execute("SELECT * FROM communities").fetchall())
        ranked = radar.rank_communities(event, communities, limit=limit)
        ranked_ids = {r["community"]["id"] for r in ranked}

        # Drop stale, untouched drafts from earlier runs; keep anything a human edited or decided on.
        existing = conn.execute(
            "SELECT id, community_id, status, edited FROM outreach WHERE event_id = ?", (event_id,)
        ).fetchall()
        for row in existing:
            if row["community_id"] not in ranked_ids and row["status"] == "pending" and not row["edited"]:
                conn.execute("DELETE FROM outreach WHERE id = ?", (row["id"],))
        existing_by_cid = {r["community_id"]: r for r in existing}

        created = refreshed = 0
        for item in ranked:
            c = item["community"]
            prior = existing_by_cid.get(c["id"])
            if prior is None:
                ref_code = secrets.token_hex(4)
                lang = radar.pick_draft_language(profile, c)
                draft = radar.draft_message(event, c, item["overlaps"], lang, tracked_link(f"o_{ref_code}"))
                conn.execute(
                    """INSERT INTO outreach (event_id, community_id, score, overlaps, rationale, language, draft, ref_code)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event_id, c["id"], item["score"], dumps(item["overlaps"]), item["rationale"], lang, draft, ref_code),
                )
                created += 1
            else:
                conn.execute(
                    "UPDATE outreach SET score = ?, overlaps = ?, rationale = ? WHERE id = ?",
                    (item["score"], dumps(item["overlaps"]), item["rationale"], prior["id"]),
                )
                if prior["status"] == "pending" and not prior["edited"]:
                    o = conn.execute("SELECT language, ref_code FROM outreach WHERE id = ?", (prior["id"],)).fetchone()
                    draft = radar.draft_message(event, c, item["overlaps"], o["language"],
                                                tracked_link(f"o_{o['ref_code']}"))
                    conn.execute("UPDATE outreach SET draft = ? WHERE id = ?", (draft, prior["id"]))
                refreshed += 1

        ranking = [
            {
                "rank": i + 1,
                "community": item["community"],
                "score": item["score"],
                "overlaps": item["overlaps"],
                "overlap_labels": [radar.THEME_LABELS.get(o, o) for o in item["overlaps"]],
                "is_local": item["is_local"],
                "size_factor": item["size_factor"],
                "rationale": item["rationale"],
            }
            for i, item in enumerate(ranked)
        ]
        outreach = outreach_with_community(conn, "event", (event_id,))

    return {
        "event_id": event_id,
        "profile": profile,
        "formula": "Score = 22 × topic overlaps + 25 (if local) + size factor (≤15)",
        "scanned": len(communities),
        "ranking": ranking,
        "drafts_created": created,
        "drafts_refreshed": refreshed,
        "outreach": outreach,
    }


@admin.get("/events/{event_id}/radar", tags=["radar"])
def get_ranking(event_id: Id, limit: int = Query(12, ge=1, le=50)) -> dict[str, Any]:
    """Read-only ranking preview (does not create drafts)."""
    with connect() as conn:
        event = get_event_or_404(conn, event_id)
        communities = rows_to_dicts(conn.execute("SELECT * FROM communities").fetchall())
    ranked = radar.rank_communities(event, communities, limit=limit)
    return {
        "event_id": event_id,
        "profile": radar.build_profile(event),
        "scanned": len(communities),
        "ranking": [
            {"rank": i + 1, "community": r["community"], "score": r["score"], "overlaps": r["overlaps"],
             "overlap_labels": [radar.THEME_LABELS.get(o, o) for o in r["overlaps"]],
             "is_local": r["is_local"], "size_factor": r["size_factor"], "rationale": r["rationale"]}
            for i, r in enumerate(ranked)
        ],
    }


# --------------------------------------------------------------------------- #
# Outreach: human approval gate
# --------------------------------------------------------------------------- #
@admin.get("/events/{event_id}/outreach", tags=["outreach"])
def list_outreach(event_id: Id, status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$")
                  ) -> list[dict[str, Any]]:
    with connect() as conn:
        get_event_or_404(conn, event_id)
        if status:
            return outreach_with_community(conn, "event_status", (event_id, status))
        return outreach_with_community(conn, "event", (event_id,))


@admin.patch("/outreach/{outreach_id}", tags=["outreach"])
def update_outreach(outreach_id: Id, body: OutreachUpdate) -> dict[str, Any]:
    with connect() as conn:
        o = get_outreach_or_404(conn, outreach_id)
        if o["status"] == "approved":
            raise HTTPException(409, "This draft is already approved. Move it back to pending to edit it.")
        if body.language and body.draft is None:
            event = get_event_or_404(conn, o["event_id"])
            community = row_to_dict(conn.execute(
                "SELECT * FROM communities WHERE id = ?", (o["community_id"],)).fetchone())
            draft = radar.draft_message(event, community, o["overlaps"], body.language, o["link"])
            conn.execute("UPDATE outreach SET language = ?, draft = ?, edited = 0 WHERE id = ?",
                         (body.language, draft, outreach_id))
        elif body.draft is not None:
            conn.execute("UPDATE outreach SET draft = ?, edited = 1, language = COALESCE(?, language) WHERE id = ?",
                         (body.draft.strip(), body.language, outreach_id))
        return get_outreach_or_404(conn, outreach_id)


def _set_outreach_status(outreach_id: Id, status: str) -> dict[str, Any]:
    with connect() as conn:
        get_outreach_or_404(conn, outreach_id)
        conn.execute(
            """UPDATE outreach SET status = ?,
                      approved_at = CASE WHEN ? = 'approved' THEN datetime('now') ELSE NULL END
               WHERE id = ?""",
            (status, status, outreach_id),
        )
        return get_outreach_or_404(conn, outreach_id)


@admin.post("/outreach/{outreach_id}/approve", tags=["outreach"])
def approve_outreach(outreach_id: Id) -> dict[str, Any]:
    with connect() as conn:
        o = get_outreach_or_404(conn, outreach_id)
    if o["link"] not in o["draft"]:
        raise HTTPException(422, "The message must include its tracked link, or sign-ups can't be counted. "
                                 "Put the link back in and try again.")
    return _set_outreach_status(outreach_id, "approved")


@admin.post("/outreach/{outreach_id}/reject", tags=["outreach"])
def reject_outreach(outreach_id: Id) -> dict[str, Any]:
    return _set_outreach_status(outreach_id, "rejected")


@admin.post("/outreach/{outreach_id}/reset", tags=["outreach"])
def reset_outreach(outreach_id: Id) -> dict[str, Any]:
    return _set_outreach_status(outreach_id, "pending")


# --------------------------------------------------------------------------- #
# Tracked links
# --------------------------------------------------------------------------- #
@service.get("/ref/resolve", tags=["squadup"])
def resolve(payload: Optional[str] = Query(None, max_length=64, pattern=PAYLOAD_RE.pattern)) -> dict[str, Any]:
    with connect() as conn:
        return resolve_payload(conn, payload)


@service.post("/ref/click", tags=["squadup"])
def track_click(payload: str = Query(..., max_length=64, pattern=PAYLOAD_RE.pattern)) -> dict[str, Any]:
    with connect() as conn:
        info = resolve_payload(conn, payload)
        if info["kind"] == "community":
            conn.execute("UPDATE outreach SET clicks = clicks + 1 WHERE id = ?", (info["outreach_id"],))
    return {"tracked": info["kind"] == "community", "kind": info["kind"], "event_id": info["event"]["id"]}


# Browser join flow. These public endpoints intentionally expose only the data
# needed to register; RateLimitMiddleware applies the normal per-IP API budget.
@public.get("/join/resolve", tags=["join"])
def public_resolve(payload: Optional[str] = Query(None, max_length=64, pattern=PAYLOAD_RE.pattern)) -> dict[str, Any]:
    with connect() as conn:
        info = resolve_payload(conn, payload)
        return {key: info[key] for key in ("kind", "event", "community_name", "referrer", "payload")}


@public.post("/join/click", tags=["join"])
def public_track_click(payload: str = Query(..., max_length=64, pattern=PAYLOAD_RE.pattern)) -> dict[str, Any]:
    with connect() as conn:
        info = resolve_payload(conn, payload)
        if info["kind"] == "community":
            conn.execute("UPDATE outreach SET clicks = clicks + 1 WHERE id = ?", (info["outreach_id"],))
    return {"tracked": info["kind"] == "community"}


@public.post("/join/register", tags=["join"])
def public_register(body: RegistrationCreate) -> dict[str, Any]:
    with connect() as conn:
        participant, created = register_participant(conn, body)
    return {key: participant[key] for key in ("id", "name", "event_id", "event_name", "start_date",
                                                "event_city", "team_number", "team", "invite_link", "status")} | {
        "created": created,
    }


# --------------------------------------------------------------------------- #
# SquadUp: registration, teams, confirmation
# --------------------------------------------------------------------------- #
@service.post("/register", tags=["squadup"])
def register(body: RegistrationCreate) -> dict[str, Any]:
    with connect() as conn:
        participant, created = register_participant(conn, body)
    participant["created"] = created
    return participant


@service.get("/participants/lookup", tags=["squadup"])
def lookup_participant(telegram_id: int = Query(..., gt=0, le=MAX_TELEGRAM_ID),
                       event_id: Optional[int] = Query(None, gt=0, le=MAX_ID)) -> dict[str, Any]:
    with connect() as conn:
        if event_id:
            row = conn.execute(
                "SELECT id FROM participants WHERE telegram_id = ? AND event_id = ?", (telegram_id, event_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM participants WHERE telegram_id = ? ORDER BY id DESC LIMIT 1", (telegram_id,)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Not registered")
        return participant_view(conn, row["id"])


@service.get("/participants/{participant_id}", tags=["squadup"])
def get_participant(participant_id: Id) -> dict[str, Any]:
    with connect() as conn:
        return participant_view(conn, participant_id)


@service.patch("/participants/{participant_id}", tags=["squadup"])
def update_participant(participant_id: Id, body: ParticipantUpdate) -> dict[str, Any]:
    with connect() as conn:
        p = participant_view(conn, participant_id)
        if body.language:
            conn.execute("UPDATE participants SET language = ? WHERE id = ?", (body.language, participant_id))
        if body.college is not None:
            conn.execute("UPDATE participants SET college = ? WHERE id = ?", (body.college.strip(), participant_id))
            if body.college.strip():
                event = get_event_or_404(conn, p["event_id"])
                record_discovered_community(conn, body.college, event, body.language or p["language"])
        return participant_view(conn, participant_id)


@service.post("/participants/{participant_id}/confirm", tags=["squadup"])
def confirm_participant(participant_id: Id) -> dict[str, Any]:
    with connect() as conn:
        p = participant_view(conn, participant_id)
        if p["status"] == "withdrawn":
            raise HTTPException(409, "This registration was withdrawn. Register again to rejoin.")
        conn.execute("UPDATE participants SET status = 'confirmed' WHERE id = ?", (participant_id,))
        return participant_view(conn, participant_id)


@service.post("/participants/{participant_id}/withdraw", tags=["squadup"])
def withdraw_participant(participant_id: Id) -> dict[str, Any]:
    """Frees the seat immediately so the balancer can hand it to the next person."""
    with connect() as conn:
        participant_view(conn, participant_id)
        conn.execute("UPDATE participants SET status = 'withdrawn', team_id = NULL WHERE id = ?", (participant_id,))
        return participant_view(conn, participant_id)


@admin.get("/events/{event_id}/teams", tags=["squadup"])
def list_teams(event_id: Id) -> list[dict[str, Any]]:
    with connect() as conn:
        get_event_or_404(conn, event_id)
        return squad.event_team_cards(conn, event_id)


@service.get("/teams/{team_id}/card", tags=["squadup"])
def get_team_card(team_id: Id) -> dict[str, Any]:
    with connect() as conn:
        card = squad.team_card(conn, team_id)
    if not card:
        raise HTTPException(404, f"Team {team_id} not found")
    return card


@service.get("/reminders", tags=["squadup"])
def reminder_targets(event_id: Optional[int] = Query(None, gt=0, le=MAX_ID)) -> list[dict[str, Any]]:
    """Everyone the bot should nudge: Telegram users who haven't withdrawn."""
    sql = """SELECT p.id AS participant_id, p.telegram_id, p.language, p.name, p.status, p.event_id,
                    e.name AS event_name, e.start_date, t.number AS team_number
             FROM participants p JOIN events e ON e.id = p.event_id LEFT JOIN teams t ON t.id = p.team_id
             WHERE p.telegram_id IS NOT NULL AND p.status != 'withdrawn'"""
    params: tuple = ()
    if event_id:
        sql += " AND p.event_id = ?"
        params = (event_id,)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
@admin.get("/events/{event_id}/stats", tags=["stats"])
def event_stats(event_id: Id) -> dict[str, Any]:
    with connect() as conn:
        event = get_event_or_404(conn, event_id)
        o = conn.execute(
            """SELECT COUNT(*) AS drafts,
                      SUM(status = 'approved') AS approved,
                      SUM(status = 'pending') AS pending,
                      SUM(status = 'rejected') AS rejected,
                      COALESCE(SUM(clicks), 0) AS clicks
               FROM outreach WHERE event_id = ?""",
            (event_id,),
        ).fetchone()
        p = conn.execute(
            """SELECT SUM(status != 'withdrawn') AS registrations,
                      SUM(status = 'confirmed') AS confirmed,
                      SUM(status = 'withdrawn') AS withdrawn,
                      SUM(status != 'withdrawn' AND referrer_id IS NOT NULL) AS via_referral,
                      SUM(status != 'withdrawn' AND source_outreach_id IS NOT NULL) AS via_community,
                      SUM(is_synthetic) AS synthetic
               FROM participants WHERE event_id = ?""",
            (event_id,),
        ).fetchone()

        teams = squad.event_team_cards(conn, event_id)
        by_source = [
            dict(r) for r in conn.execute(
                """SELECT c.name AS label, c.platform, o.clicks,
                          (SELECT COUNT(*) FROM participants p WHERE p.source_outreach_id = o.id
                             AND p.status != 'withdrawn') AS registrations
                   FROM outreach o JOIN communities c ON c.id = o.community_id
                   WHERE o.event_id = ? AND o.status = 'approved'
                   ORDER BY registrations DESC, o.clicks DESC""",
                (event_id,),
            ).fetchall()
        ]
        registrations = p["registrations"] or 0
        via_referral = p["via_referral"] or 0
        direct = registrations - via_referral - (p["via_community"] or 0)
        if via_referral:
            by_source.append({"label": "Teammate invites (SquadUp loop)", "platform": "referral",
                              "clicks": None, "registrations": via_referral})
        if direct > 0:
            by_source.append({"label": "Direct / unattributed", "platform": "direct",
                              "clicks": None, "registrations": direct})

        roles = {r: 0 for r in squad.ROLES}
        for r in conn.execute(
            "SELECT role, COUNT(*) AS n FROM participants WHERE event_id = ? AND status != 'withdrawn' GROUP BY role",
            (event_id,),
        ).fetchall():
            roles[r["role"]] = r["n"]

        recent = [
            {**dict(r), "first_name": r["name"].split()[0]}
            for r in conn.execute(
                """SELECT p.id, p.name, p.role, p.status, p.created_at, t.number AS team_number,
                          c.name AS source, CASE WHEN p.referrer_id IS NOT NULL THEN 1 ELSE 0 END AS via_referral
                   FROM participants p LEFT JOIN teams t ON t.id = p.team_id
                   LEFT JOIN outreach o ON o.id = p.source_outreach_id
                   LEFT JOIN communities c ON c.id = o.community_id
                   WHERE p.event_id = ? ORDER BY p.id DESC LIMIT 8""",
                (event_id,),
            ).fetchall()
        ]
        discovered = conn.execute(
            "SELECT COUNT(*) FROM communities WHERE discovered_via = 'squadup_referral'"
        ).fetchone()[0]

    seeded = registrations - via_referral
    return {
        "event_id": event_id,
        "event_name": event["name"],
        "kpis": {
            "drafts": o["drafts"] or 0,
            "pending": o["pending"] or 0,
            "approved": o["approved"] or 0,
            "rejected": o["rejected"] or 0,
            "clicks": o["clicks"] or 0,
            "registrations": registrations,
            "confirmed": p["confirmed"] or 0,
            "withdrawn": p["withdrawn"] or 0,
            "via_referral": via_referral,
            "synthetic": p["synthetic"] or 0,
            "teams": len(teams),
            "full_teams": sum(1 for t in teams if t["is_full"]),
            "open_seats": sum(t["size"] - t["filled"] for t in teams),
            "viral_coefficient": round(via_referral / seeded, 2) if seeded else 0.0,
            "confirmation_rate": round((p["confirmed"] or 0) / registrations, 2) if registrations else 0.0,
            "discovered_communities": discovered,
        },
        "funnel": [
            {"stage": "Drafts written", "value": o["drafts"] or 0},
            {"stage": "Human-approved", "value": o["approved"] or 0},
            {"stage": "Link clicks", "value": o["clicks"] or 0},
            {"stage": "Registered", "value": registrations},
            {"stage": "Confirmed", "value": p["confirmed"] or 0},
        ],
        "by_source": by_source,
        "roles": roles,
        "recent": recent,
    }


# --------------------------------------------------------------------------- #
# Demo simulator — synthetic participants only, clearly flagged
# --------------------------------------------------------------------------- #
@admin.post("/events/{event_id}/simulate", tags=["demo"])
def simulate(event_id: Id, body: Optional[SimulateRequest] = None) -> dict[str, Any]:
    if not get_settings().enable_simulator:
        raise HTTPException(404, "Not found")
    count = body.count if body else 12
    rng = random.Random()
    with connect() as conn:
        get_event_or_404(conn, event_id)
        approved = conn.execute(
            "SELECT id, ref_code, score FROM outreach WHERE event_id = ? AND status = 'approved'", (event_id,)
        ).fetchall()
        if not approved:
            raise HTTPException(400, "Approve at least one outreach draft first — simulated sign-ups arrive "
                                     "through approved community links.")
        created = []
        for _ in range(count):
            invite = None
            if rng.random() < 0.3:
                invite = conn.execute(
                    """SELECT invite_code FROM participants WHERE event_id = ? AND status != 'withdrawn'
                       ORDER BY RANDOM() LIMIT 1""",
                    (event_id,),
                ).fetchone()
            if invite:
                payload = f"r_{invite['invite_code']}"
            else:
                pick = rng.choices(approved, weights=[max(r["score"], 1) for r in approved])[0]
                conn.execute("UPDATE outreach SET clicks = clicks + ? WHERE id = ?", (rng.randint(1, 3), pick["id"]))
                payload = f"o_{pick['ref_code']}"
            role = rng.choices(squad.ROLES, weights=[40, 20, 20, 20])[0]
            name = f"{rng.choice(SYNTHETIC_NAMES)} {rng.choice('ABCDEGHKMNPRSTV')}."
            participant, _ = register_participant(
                conn,
                RegistrationCreate(event_id=event_id, name=name, role=role,
                                   experience=rng.choice(squad.EXPERIENCE_LEVELS),
                                   language=rng.choice(["en", "en", "hi"]), ref_payload=payload),
                synthetic=True,
            )
            if rng.random() < 0.45:
                conn.execute("UPDATE participants SET status = 'confirmed' WHERE id = ?", (participant["id"],))
            created.append(participant["id"])
    return {"created": len(created), "participant_ids": created, "synthetic": True}


# --------------------------------------------------------------------------- #
# Event requests: hosts submit their event on the public website
# --------------------------------------------------------------------------- #
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I lookalikes
SUBMITS_PER_IP_PER_HOUR = 5
SUBMITS_PER_HOUR_TOTAL = 300
STATUS_CHECKS_PER_IP_PER_HOUR = 120


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_reference() -> str:
    return "RQ-" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))


def _request_row(row: sqlite3.Row) -> dict[str, Any]:
    data = row_to_dict(row) or {}
    data.pop("token_hash", None)
    return data


def _throttle(request: Request, bucket: str, limit: int, window: int, message: str) -> None:
    allowed, retry = limiter.hit(f"{bucket}:{client_ip(request)}", limit, window)
    if not allowed:
        raise HTTPException(429, message, headers={"Retry-After": str(retry)})


@public.post("/requests", status_code=201, tags=["requests"])
def submit_event_request(body: EventRequestCreate, request: Request) -> dict[str, Any]:
    """Public: an event host asks for help reaching people. Returns a private tracking token once."""
    _throttle(request, "submit", SUBMITS_PER_IP_PER_HOUR, 3600,
              "You've sent several requests already. Please try again in an hour.")
    allowed, _ = limiter.hit("submit:all", SUBMITS_PER_HOUR_TOTAL, 3600)
    if not allowed:
        raise HTTPException(503, "We're getting a lot of requests right now. Please try again later.")

    token = secrets.token_urlsafe(32)
    if body.website:  # honeypot filled in: a bot. Answer like a success, store nothing.
        log.info("Dropped a bot submission from %s", client_ip(request))
        return {"reference": _new_reference(), "token": token}

    with connect() as conn:
        duplicate = conn.execute(
            """SELECT 1 FROM event_requests WHERE contact_email = ? AND lower(event_name) = lower(?)
               AND status = 'new' AND created_at > datetime('now', '-1 day')""",
            (body.contact_email, body.event_name),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "We already have a request for this event from this email. "
                                     "Use the tracking link you were given, or reply to our email.")
        for _ in range(5):
            reference = _new_reference()
            try:
                conn.execute(
                    """INSERT INTO event_requests (reference, token_hash, contact_name, contact_email, contact_phone,
                           organisation, event_name, city, start_date, venue, description, tags, expected_participants)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (reference, _hash_token(token), body.contact_name, body.contact_email, body.contact_phone,
                     body.organisation, body.event_name, body.city, body.start_date.isoformat(), body.venue,
                     body.description, dumps(body.tags), body.expected_participants),
                )
                break
            except sqlite3.IntegrityError:
                continue
        else:
            raise HTTPException(500, "Couldn't save your request. Please try again.")
    log.info("New event request %s", reference)
    return {"reference": reference, "token": token}


@public.post("/requests/status", tags=["requests"])
def event_request_status(body: TrackRequest, request: Request) -> dict[str, Any]:
    """Public, but only with the private token from submission. Shares progress numbers, never personal data."""
    _throttle(request, "track", STATUS_CHECKS_PER_IP_PER_HOUR, 3600, "Too many checks. Try again later.")
    with connect() as conn:
        row = conn.execute("SELECT * FROM event_requests WHERE token_hash = ?", (_hash_token(body.token),)).fetchone()
        if not row:
            raise HTTPException(404, "We couldn't find a request for this link.")
        req = _request_row(row)
        progress = None
        if req["status"] == "accepted" and req["event_id"]:
            o = conn.execute(
                """SELECT COUNT(*) AS drafts, SUM(status = 'approved') AS approved, COALESCE(SUM(clicks), 0) AS clicks
                   FROM outreach WHERE event_id = ?""", (req["event_id"],)).fetchone()
            p = conn.execute(
                """SELECT SUM(status != 'withdrawn') AS registrations, SUM(status = 'confirmed') AS confirmed
                   FROM participants WHERE event_id = ?""", (req["event_id"],)).fetchone()
            teams = squad.event_team_cards(conn, req["event_id"])
            progress = {
                "groups_found": o["drafts"] or 0,
                "groups_contacted": o["approved"] or 0,
                "link_clicks": o["clicks"] or 0,
                "registrations": p["registrations"] or 0,
                "confirmed": p["confirmed"] or 0,
                "teams": len(teams),
                "full_teams": sum(1 for t in teams if t["is_full"]),
            }
    return {
        "reference": req["reference"],
        "status": req["status"],
        "decision_note": req["decision_note"],
        "submitted_at": req["created_at"],
        "event": {k: req[k] for k in ("event_name", "organisation", "city", "start_date", "venue")},
        "progress": progress,
    }


@admin.get("/requests", tags=["requests"])
def list_event_requests(status: Optional[str] = Query(None, pattern="^(new|accepted|declined)$")) -> list[dict[str, Any]]:
    with connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM event_requests WHERE status = ? ORDER BY id DESC LIMIT 500", (status,))
        else:
            rows = conn.execute("SELECT * FROM event_requests ORDER BY id DESC LIMIT 500")
        return [_request_row(r) for r in rows.fetchall()]


def _get_request_or_404(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM event_requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Request not found")
    return _request_row(row)


@admin.post("/requests/{request_id}/accept", tags=["requests"])
def accept_event_request(request_id: Id) -> dict[str, Any]:
    """Turn a host's request into an event in the desk, ready for Radar."""
    with connect() as conn:
        req = _get_request_or_404(conn, request_id)
        if req["status"] != "new":
            raise HTTPException(409, f"This request was already {req['status']}.")
        cur = conn.execute(
            """INSERT INTO events (name, city, description, tags, start_date, venue, team_size)
               VALUES (?, ?, ?, ?, ?, ?, 4)""",
            (req["event_name"], req["city"], req["description"], dumps(req["tags"]), req["start_date"], req["venue"]),
        )
        event_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE event_requests SET status = 'accepted', event_id = ?, decided_at = datetime('now') WHERE id = ?",
            (event_id, request_id),
        )
        return {"request": _get_request_or_404(conn, request_id), "event_id": event_id}


@admin.post("/requests/{request_id}/decline", tags=["requests"])
def decline_event_request(request_id: Id, body: Optional[RequestDecision] = None) -> dict[str, Any]:
    with connect() as conn:
        req = _get_request_or_404(conn, request_id)
        if req["status"] != "new":
            raise HTTPException(409, f"This request was already {req['status']}.")
        conn.execute(
            "UPDATE event_requests SET status = 'declined', decision_note = ?, decided_at = datetime('now') WHERE id = ?",
            ((body.note if body else ""), request_id),
        )
        return _get_request_or_404(conn, request_id)


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def _validation_message(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Readable, input-free validation errors (never echo what the client sent)."""
    out = []
    for err in errors:
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        msg = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        out.append({"field": ".".join(loc) or "request", "message": msg})
    return out


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        if settings.seed_directory:
            seed_communities()
        if settings.seed_demo_event:
            seed_demo_event()
        if settings.generated_secrets:
            log.warning("ADMIN_TOKEN was not set, so a temporary one was generated for this run.")
            log.warning("Organiser access key for this run: %s", settings.admin_token)
            log.warning("Set ADMIN_TOKEN and BOT_API_KEY in .env to keep them stable between restarts.")
        log.info("RadiUp.ai started in %s mode", settings.env)
        yield

    app = FastAPI(
        title="RadiUp.ai API",
        version="1.1.0",
        description="Radar brings people in. SquadUp makes each person bring more.",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = _validation_message(exc.errors())
        summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors[:3])
        return JSONResponse({"detail": summary, "errors": errors}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        log.exception("Unhandled error on %s %s (id=%s)", request.method, request.url.path, request_id)
        return JSONResponse({"detail": f"Something went wrong on our side. Reference: {request_id}"}, status_code=500)

    app.include_router(public)
    app.include_router(service)
    app.include_router(admin)

    # Order matters: the last added runs first.
    app.add_middleware(RateLimitMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Service-Key", "X-Request-ID"],
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
    app.add_middleware(BodySizeLimitMiddleware)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
