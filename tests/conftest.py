from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ADMIN = "test-admin-token-0123456789abcdefghijkl"
BOT = "test-bot-key-0123456789abcdefghijklmnopq"


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    """Build a fresh app against a throwaway database; extra env vars can be overridden per test."""

    def factory(**env: str) -> TestClient:
        base = {
            "APP_ENV": "test",
            "ADMIN_TOKEN": ADMIN,
            "BOT_API_KEY": BOT,
            "RADAR_DB_PATH": str(tmp_path / "test.db"),
            "SEED_DIRECTORY": "1",
            "SEED_DEMO_EVENT": "0",
            "ENABLE_SIMULATOR": "1",
            "TELEGRAM_BOT_USERNAME": "RadarSquadUpBot",
        }
        base.update(env)
        for key, value in base.items():
            monkeypatch.setenv(key, value)
        from app.config import reset_settings
        from app.security import limiter
        reset_settings()
        limiter.reset()
        from app.main import create_app
        return TestClient(create_app())

    yield factory
    from app.config import reset_settings
    reset_settings()


@pytest.fixture()
def client(make_client):
    with make_client() as c:
        c.headers.update({"Authorization": f"Bearer {ADMIN}"})
        yield c


@pytest.fixture()
def bot_headers():
    return {"X-Service-Key": BOT}
