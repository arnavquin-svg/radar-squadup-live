"""Runtime configuration, read once from environment variables and validated.

Production (APP_ENV=production) refuses to start without strong secrets, so a
misconfigured deploy fails loudly instead of running open to the internet.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("radar.config")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "radar.db"
BOT_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
MIN_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """Raised when the environment is not safe to run in."""


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}, got {value}")
    return value


def _csv(name: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in os.getenv(name, "").split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    env: str
    admin_token: str
    bot_api_key: str
    bot_username: str
    db_path: str
    cors_origins: tuple[str, ...] = field(default_factory=tuple)
    trusted_hosts: tuple[str, ...] = field(default_factory=tuple)
    seed_directory: bool = False
    seed_demo_event: bool = False
    enable_simulator: bool = False
    enable_docs: bool = False
    trust_proxy: bool = False
    rate_limit_per_minute: int = 120
    auth_failures_per_15min: int = 10
    max_body_bytes: int = 64 * 1024
    generated_secrets: bool = False

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def load_settings() -> Settings:
    env = os.getenv("APP_ENV", "development").strip().lower()
    if env not in {"development", "production", "test"}:
        raise ConfigError("APP_ENV must be development, production or test")
    prod = env == "production"

    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    bot_api_key = os.getenv("BOT_API_KEY", "").strip()
    generated = False
    if prod:
        for name, value in (("ADMIN_TOKEN", admin_token), ("BOT_API_KEY", bot_api_key)):
            if len(value) < MIN_SECRET_LENGTH:
                raise ConfigError(
                    f"{name} must be set to a random value of at least {MIN_SECRET_LENGTH} characters in "
                    "production. Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
        if admin_token == bot_api_key:
            raise ConfigError("ADMIN_TOKEN and BOT_API_KEY must be different")
    else:
        if not admin_token:
            admin_token = secrets.token_urlsafe(24)
            generated = True
        if not bot_api_key:
            bot_api_key = secrets.token_urlsafe(24)
            generated = True

    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "" if prod else "RadarSquadUpBot").strip().lstrip("@")
    if not BOT_USERNAME_RE.match(bot_username):
        raise ConfigError("TELEGRAM_BOT_USERNAME must be your bot's username (5-32 letters, digits or _)")

    settings = Settings(
        env=env,
        admin_token=admin_token,
        bot_api_key=bot_api_key,
        bot_username=bot_username,
        db_path=os.getenv("RADAR_DB_PATH", str(DEFAULT_DB_PATH)),
        cors_origins=_csv("CORS_ORIGINS"),
        trusted_hosts=_csv("TRUSTED_HOSTS"),
        seed_directory=_bool("SEED_DIRECTORY", not prod),
        seed_demo_event=_bool("SEED_DEMO_EVENT", not prod),
        enable_simulator=_bool("ENABLE_SIMULATOR", not prod),
        enable_docs=_bool("ENABLE_DOCS", not prod),
        trust_proxy=_bool("TRUST_PROXY", False),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 120, 10, 10_000),
        auth_failures_per_15min=_int("AUTH_FAILURES_PER_15MIN", 10, 3, 1_000),
        max_body_bytes=_int("MAX_BODY_BYTES", 64 * 1024, 4 * 1024, 5 * 1024 * 1024),
        generated_secrets=generated,
    )
    if "*" in settings.cors_origins and prod:
        raise ConfigError("CORS_ORIGINS=* is not allowed in production; list the exact origins instead")
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings() -> None:
    """Forget cached settings (used by tests that change the environment)."""
    get_settings.cache_clear()
