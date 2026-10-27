"""Request bodies, with strict validation.

Every model rejects unknown fields. Text is normalised (control and invisible
direction characters removed, whitespace collapsed) before length checks, and
single-line fields refuse angle brackets as a second layer of XSS defence on
top of output escaping.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["developer", "designer", "domain_expert", "presenter"]
Experience = Literal["first_time", "some", "veteran"]
Language = Literal["en", "hi", "mr"]
Platform = Literal["whatsapp", "telegram", "instagram", "discord", "other"]

MAX_ID = 2_147_483_647
PAYLOAD_RE = re.compile(r"^(o|r|e)_[A-Za-z0-9]{1,40}$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9 \-]{0,29}$")
# C0/C1 controls, zero-width characters and bidirectional overrides (used for spoofing).
_INVISIBLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤⁦-⁩﻿]")


def clean_line(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = _INVISIBLE.sub("", value)
    return re.sub(r" {2,}", " ", value).strip()


def clean_block(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    value = _INVISIBLE.sub("", value)
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def has_letter(value: str) -> bool:
    return any(unicodedata.category(ch).startswith("L") for ch in value)


def Line(min_len: int, max_len: int, *, letter: bool = True):  # noqa: N802 — reads like a type
    def check(value: str) -> str:
        value = clean_line(value)
        if len(value) < min_len:
            raise ValueError("is required" if min_len == 1 else f"must be at least {min_len} characters")
        if len(value) > max_len:
            raise ValueError(f"must be at most {max_len} characters")
        if "<" in value or ">" in value:
            raise ValueError("must not contain < or >")
        if value and letter and not has_letter(value):
            raise ValueError("must contain at least one letter")
        return value

    return Annotated[str, Field(max_length=max_len * 2), AfterValidator(check)]


def Block(min_len: int, max_len: int):  # noqa: N802
    def check(value: str) -> str:
        value = clean_block(value)
        if len(value) < min_len:
            raise ValueError(f"must be at least {min_len} characters")
        if len(value) > max_len:
            raise ValueError(f"must be at most {max_len} characters")
        return value

    return Annotated[str, Field(max_length=max_len * 2), AfterValidator(check)]


def _tag(value: str) -> str:
    value = clean_line(value).lower()
    if not TAG_RE.match(value):
        raise ValueError("topics use lowercase letters, numbers, spaces or hyphens (max 30 characters)")
    return value


Tag = Annotated[str, Field(max_length=60), AfterValidator(_tag)]
Payload = Annotated[str, Field(max_length=64, pattern=PAYLOAD_RE.pattern)]


def _unique(items: list) -> list:
    seen: list = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EventCreate(StrictModel):
    name: Line(3, 120)
    city: Line(2, 60)
    description: Block(0, 2000) = ""
    tags: list[Tag] = Field(default_factory=list, max_length=15)
    start_date: Optional[date] = None
    venue: Line(0, 160, letter=False) = ""
    team_size: int = Field(default=4, ge=2, le=6)

    @field_validator("tags")
    @classmethod
    def dedupe_tags(cls, v: list[str]) -> list[str]:
        return _unique(v)

    @field_validator("start_date")
    @classmethod
    def sensible_date(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return v
        today = date.today()
        if v < today:
            raise ValueError("must be today or later")
        if v > today + timedelta(days=3 * 365):
            raise ValueError("must be within the next three years")
        return v


class CommunityCreate(StrictModel):
    name: Line(3, 120)
    kind: Line(0, 40) = "club"
    platform: Platform = "whatsapp"
    city: Line(2, 60)
    tags: list[Tag] = Field(default_factory=list, max_length=12)
    size: int = Field(default=100, ge=1, le=10_000_000)
    languages: list[Language] = Field(default_factory=lambda: ["en"], min_length=1, max_length=3)
    admin_name: Line(0, 60) = ""

    @field_validator("tags", "languages")
    @classmethod
    def dedupe(cls, v: list) -> list:
        return _unique(v)


class RadarRun(StrictModel):
    limit: int = Field(default=12, ge=1, le=50)


class OutreachUpdate(StrictModel):
    draft: Optional[Block(10, 4000)] = None
    language: Optional[Language] = None

    @model_validator(mode="after")
    def something_to_change(self) -> "OutreachUpdate":
        if self.draft is None and self.language is None:
            raise ValueError("Send a new draft, a language, or both")
        return self


class RegistrationCreate(StrictModel):
    event_id: Optional[int] = Field(default=None, gt=0, le=MAX_ID)
    name: Line(1, 80)
    role: Role
    experience: Experience = "first_time"
    language: Language = "en"
    ref_payload: Optional[Payload] = None
    college: Line(0, 120) = ""

    @model_validator(mode="after")
    def needs_event(self) -> "RegistrationCreate":
        if self.event_id is None and self.ref_payload is None:
            raise ValueError("Provide event_id or ref_payload")
        return self


class ParticipantUpdate(StrictModel):
    language: Optional[Language] = None
    college: Optional[Line(0, 120)] = None

    @model_validator(mode="after")
    def something_to_change(self) -> "ParticipantUpdate":
        if self.language is None and self.college is None:
            raise ValueError("Send a language, a college, or both")
        return self


class SimulateRequest(StrictModel):
    count: int = Field(default=12, ge=1, le=50)


# --------------------------------------------------------------------------- #
# Event requests (public website)
# --------------------------------------------------------------------------- #
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _email(value: str) -> str:
    value = clean_line(value).lower()
    if len(value) > 254 or not EMAIL_RE.match(value) or ".." in value:
        raise ValueError("enter a valid email address")
    return value


def _phone(value: str) -> str:
    value = clean_line(value)
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    if not PHONE_RE.match(value) or not 7 <= len(digits) <= 15:
        raise ValueError("enter a valid phone number (7 to 15 digits, optional +)")
    return value


Email = Annotated[str, Field(max_length=320), AfterValidator(_email)]
Phone = Annotated[str, Field(max_length=40), AfterValidator(_phone)]


class EventRequestCreate(StrictModel):
    contact_name: Line(2, 80)
    contact_email: Email
    contact_phone: Phone = ""
    organisation: Line(2, 120)
    event_name: Line(3, 120)
    city: Line(2, 60)
    start_date: date
    venue: Line(0, 160, letter=False) = ""
    description: Block(20, 2000)
    tags: list[Tag] = Field(default_factory=list, max_length=15)
    expected_participants: Optional[int] = Field(default=None, ge=10, le=100_000)
    consent: bool
    website: str = Field(default="", max_length=200)  # honeypot: humans never see or fill this

    @field_validator("tags")
    @classmethod
    def dedupe_tags(cls, v: list[str]) -> list[str]:
        return _unique(v)

    @field_validator("start_date")
    @classmethod
    def sensible_date(cls, v: date) -> date:
        today = date.today()
        if v < today:
            raise ValueError("must be today or later")
        if v > today + timedelta(days=3 * 365):
            raise ValueError("must be within the next three years")
        return v

    @field_validator("consent")
    @classmethod
    def must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("please agree to be contacted about this event")
        return v


class RequestDecision(StrictModel):
    note: Line(0, 500, letter=False) = ""


class TrackRequest(StrictModel):
    token: str = Field(min_length=32, max_length=64, pattern=TOKEN_RE.pattern)
