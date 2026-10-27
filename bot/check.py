"""Check that the bot can start: run  python -m bot.check

Tests, in order: your .env values, the connection to Telegram, the bot token,
the connection to your website, and the shared BOT_API_KEY. Prints what to fix.
"""
from __future__ import annotations

import os
import re
import sys

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

OK, BAD = "  OK ", "  FIX"


def line(ok: bool, text: str) -> None:
    print(f"{OK if ok else BAD}  {text}")


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    api_url = os.getenv("RADAR_API_URL", "").strip().rstrip("/")
    bot_key = os.getenv("BOT_API_KEY", "").strip()
    problems = 0

    print("\n1. Settings in .env")
    checks = [
        (bool(re.match(r"^\d{5,16}:[A-Za-z0-9_-]{30,64}$", token)), "TELEGRAM_BOT_TOKEN looks like a BotFather token"),
        (bool(re.match(r"^[A-Za-z][A-Za-z0-9_]{4,31}$", username)), "TELEGRAM_BOT_USERNAME is set (no @)"),
        (api_url.startswith(("http://", "https://")), "RADAR_API_URL starts with https://"),
        (len(bot_key) >= 16, "BOT_API_KEY is set"),
    ]
    for ok, text in checks:
        line(ok, text)
        problems += not ok
    if problems:
        print("\nFill in the missing values in the .env file in this folder, save it, and run this again.\n")
        return 1

    print("\n2. Telegram")
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
        if r.status_code == 401:
            line(False, "Telegram rejected the token. Copy it again from @BotFather (or /revoke for a new one).")
            return 1
        me = r.json().get("result", {})
        line(True, f"Reached Telegram; the token belongs to @{me.get('username')}")
        if me.get("username", "").lower() != username.lower():
            line(False, f"TELEGRAM_BOT_USERNAME is '{username}' but the token is for '{me.get('username')}'. "
                        "Use the same name in .env and in Render's Environment tab.")
            problems += 1
    except httpx.TimeoutException:
        line(False, "Timed out reaching api.telegram.org. This network is probably blocking or slowing Telegram. "
                    "Try your phone's hotspot, or a different Wi-Fi.")
        return 1
    except httpx.HTTPError as exc:
        line(False, f"Couldn't reach api.telegram.org ({type(exc).__name__}). Check your internet connection or try a hotspot.")
        return 1

    print("\n3. Your website")
    try:
        print("       (a sleeping free Render site can take up to a minute to answer…)")
        r = httpx.get(f"{api_url}/api/health", timeout=90)
        line(r.status_code == 200, f"{api_url} answered ({r.status_code})")
        if r.status_code != 200:
            return 1
    except httpx.HTTPError as exc:
        line(False, f"Couldn't reach {api_url} ({type(exc).__name__}). Open it in your browser to check the address, "
                    "and make sure it's the plain address without /app/ or /submit/.")
        return 1

    r = httpx.get(f"{api_url}/api/reminders", headers={"X-Service-Key": bot_key}, timeout=30)
    if r.status_code == 200:
        line(True, "BOT_API_KEY matches the website")
    else:
        line(False, "BOT_API_KEY doesn't match. Copy it again from Render → radar-squadup → Environment.")
        problems += 1

    print("\nAll good. Start the bot with:  python -m bot.telegram_bot\n" if not problems
          else "\nFix the lines marked FIX, save .env, and run this again.\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
