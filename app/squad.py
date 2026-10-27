"""SquadUp: balanced team matching, team cards and invite codes.

Placement rules for a new participant:
  1. Referral priority — if they came through a teammate's invite link and that
     team still has an open seat, they join it.
  2. Otherwise score every open team:
        +100  the team is missing this participant's role (complementary skills)
        -40   per member who already holds this role (prevents skill silos)
        +10   per current member (near-full teams fill first)
     The best team wins if its score is positive; otherwise a new team is opened.
"""
from __future__ import annotations

import secrets
import sqlite3
from typing import Any

ROLES: tuple[str, ...] = ("developer", "designer", "domain_expert", "presenter")
ROLE_LABELS: dict[str, str] = {
    "developer": "Developer",
    "designer": "Designer",
    "domain_expert": "Domain expert",
    "presenter": "Presenter",
}
EXPERIENCE_LEVELS: tuple[str, ...] = ("first_time", "some", "veteran")

MISSING_ROLE_BONUS = 100
DUPLICATE_ROLE_PENALTY = 40
FILL_BONUS = 10


def new_invite_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")


def _active_members(conn: sqlite3.Connection, team_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, name, role, experience, status FROM participants
           WHERE team_id = ? AND status != 'withdrawn' ORDER BY id""",
        (team_id,),
    ).fetchall()


def _open_new_team(conn: sqlite3.Connection, event_id: int) -> int:
    next_number = conn.execute(
        "SELECT COALESCE(MAX(number), 0) + 1 FROM teams WHERE event_id = ?", (event_id,)
    ).fetchone()[0]
    cur = conn.execute("INSERT INTO teams (event_id, number) VALUES (?, ?)", (event_id, next_number))
    return int(cur.lastrowid)


def score_team(roles_in_team: list[str], role: str) -> int:
    dupes = roles_in_team.count(role)
    score = MISSING_ROLE_BONUS if dupes == 0 else -DUPLICATE_ROLE_PENALTY * dupes
    return score + FILL_BONUS * len(roles_in_team)


def assign_team(
    conn: sqlite3.Connection,
    event_id: int,
    role: str,
    team_size: int,
    referrer_id: int | None = None,
) -> tuple[int, str]:
    """Pick (or create) a team for a participant. Returns (team_id, reason)."""
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")

    if referrer_id:
        ref = conn.execute(
            "SELECT team_id FROM participants WHERE id = ? AND event_id = ? AND status != 'withdrawn'",
            (referrer_id, event_id),
        ).fetchone()
        if ref and ref["team_id"] and len(_active_members(conn, ref["team_id"])) < team_size:
            return int(ref["team_id"]), "referral"

    teams = conn.execute(
        "SELECT id, number FROM teams WHERE event_id = ? ORDER BY number", (event_id,)
    ).fetchall()

    best: tuple[int, int, int] | None = None  # (score, -number, team_id)
    for team in teams:
        roles_in_team = [m["role"] for m in _active_members(conn, team["id"])]
        if len(roles_in_team) >= team_size:
            continue
        candidate = (score_team(roles_in_team, role), -team["number"], team["id"])
        if best is None or candidate > best:
            best = candidate

    if best is not None and best[0] > 0:
        return int(best[2]), "balanced"
    return _open_new_team(conn, event_id), "new_team"


def _needing_phrase(missing: list[str]) -> str:
    labels = [ROLE_LABELS[r].lower() for r in missing]
    if not labels:
        return "ready to go"
    article = "an" if labels[0][0] in "aeiou" else "a"
    if len(labels) == 1:
        return f"needing {article} {labels[0]}"
    return f"needing {article} {', '.join(labels[:-1])} and {labels[-1]}"


def team_card(conn: sqlite3.Connection, team_id: int) -> dict[str, Any] | None:
    team = conn.execute(
        """SELECT t.id, t.number, t.event_id, e.team_size, e.name AS event_name
           FROM teams t JOIN events e ON e.id = t.event_id WHERE t.id = ?""",
        (team_id,),
    ).fetchone()
    if team is None:
        return None
    members = _active_members(conn, team_id)
    size = team["team_size"]
    present_roles = {m["role"] for m in members}
    missing = [r for r in ROLES if r not in present_roles] if len(members) < size else []
    filled = len(members)

    # First names only: the card is designed to be forwarded into peer groups.
    public_members = [
        {
            "id": m["id"],
            "first_name": (m["name"].split() or ["Member"])[0],
            "role": m["role"],
            "role_label": ROLE_LABELS[m["role"]],
            "experience": m["experience"],
            "confirmed": m["status"] == "confirmed",
        }
        for m in members
    ]
    return {
        "team_id": team["id"],
        "number": team["number"],
        "event_id": team["event_id"],
        "event_name": team["event_name"],
        "size": size,
        "filled": filled,
        "is_full": filled >= size,
        "members": public_members,
        "missing_roles": missing,
        "missing_role_labels": [ROLE_LABELS[r] for r in missing],
        "confirmed": sum(1 for m in members if m["status"] == "confirmed"),
        "label": f"Team {team['number']}: {filled}/{size} filled, {_needing_phrase(missing)}",
    }


def event_team_cards(conn: sqlite3.Connection, event_id: int) -> list[dict[str, Any]]:
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM teams WHERE event_id = ? ORDER BY number", (event_id,)
    ).fetchall()]
    cards = [team_card(conn, tid) for tid in ids]
    # Hide teams emptied entirely by withdrawals.
    return [c for c in cards if c and c["filled"] > 0]
