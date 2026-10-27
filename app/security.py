"""Authentication, rate limiting, request size limits and security headers.

Two credentials exist:
  * ADMIN_TOKEN  - the organiser's access key, sent as `Authorization: Bearer <token>`
                   by the organiser desk. Grants everything.
  * SERVICE_API_KEY - the internal service key, sent as `X-Service-Key`.
                   Grants only the participant-facing endpoints.
"""
from __future__ import annotations

import hmac
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import get_settings

log = logging.getLogger("radar.security")

AUTH_WINDOW_SECONDS = 15 * 60


# --------------------------------------------------------------------------- #
# Sliding-window rate limiter (in-process). Behind several workers or hosts,
# also rate-limit at the reverse proxy; this layer is the last line, not the only one.
# --------------------------------------------------------------------------- #
class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def hit(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, seconds_until_retry)."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, max(1, int(window - (now - bucket[0])) + 1)
            bucket.append(now)
            self._sweep(now, window)
            return True, 0

    def count(self, key: str, window: float) -> int:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.get(key)
            if not bucket:
                return 0
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            return len(bucket)

    def _sweep(self, now: float, window: float) -> None:
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        for key in [k for k, b in self._hits.items() if not b or now - b[-1] > max(window, AUTH_WINDOW_SECONDS)]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy:
        # The right-most entry is the one added by our own proxy; entries to its left come from
        # the client and can be forged, so they're never used for rate limiting.
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()[:64]
    return request.client.host if request.client else "unknown"


def _matches(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token else None


def is_admin(request: Request) -> bool:
    return _matches(_bearer(request), get_settings().admin_token)


def is_service(request: Request) -> bool:
    return _matches(request.headers.get("x-service-key"), get_settings().service_api_key)


def _reject(request: Request) -> None:
    """Count a failed attempt and block the IP once it has guessed too often."""
    settings = get_settings()
    ip = client_ip(request)
    allowed, retry = limiter.hit(f"authfail:{ip}", settings.auth_failures_per_15min, AUTH_WINDOW_SECONDS)
    if not allowed:
        log.warning("Blocking %s after repeated failed sign-ins", ip)
        raise HTTPException(429, "Too many failed attempts. Try again later.", headers={"Retry-After": str(retry)})
    raise HTTPException(401, "A valid access key is required.", headers={"WWW-Authenticate": "Bearer"})


def _guard_blocked(request: Request) -> None:
    settings = get_settings()
    if limiter.count(f"authfail:{client_ip(request)}", AUTH_WINDOW_SECONDS) >= settings.auth_failures_per_15min:
        raise HTTPException(429, "Too many failed attempts. Try again later.", headers={"Retry-After": "900"})


def require_admin(request: Request) -> None:
    """Dependency: the organiser's access key."""
    _guard_blocked(request)
    if not is_admin(request):
        _reject(request)


def require_service(request: Request) -> None:
    """Dependency: the internal service key, or the organiser's access key."""
    _guard_blocked(request)
    if not (is_service(request) or is_admin(request)):
        _reject(request)


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP request budget for /api. Internal services can proxy users from one IP, so authenticated service calls get a larger budget."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/health":
            return await call_next(request)
        settings = get_settings()
        if is_service(request):
            key, limit = "service", settings.rate_limit_per_minute * 25
        else:
            key, limit = f"ip:{client_ip(request)}", settings.rate_limit_per_minute
        allowed, retry = limiter.hit(key, limit, 60)
        if not allowed:
            return JSONResponse({"detail": "Too many requests. Slow down and try again shortly."},
                                status_code=429, headers={"Retry-After": str(retry)})
        return await call_next(request)


CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id", "")
        if not (0 < len(request_id) <= 64 and request_id.replace("-", "").isalnum()):
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)

        h = response.headers
        h["X-Request-ID"] = request_id
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        path = request.url.path
        if path.startswith("/api/"):
            h["Cache-Control"] = "no-store"
            h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        else:
            # /docs loads Swagger UI from a CDN, so it keeps FastAPI's defaults (and is off in production).
            if not path.startswith(("/docs", "/redoc", "/openapi.json")):
                h["Content-Security-Policy"] = CSP
            h.setdefault("Cache-Control", "public, max-age=3600" if path.startswith("/assets/") else "no-cache")
        forwarded_proto = request.headers.get("x-forwarded-proto") if get_settings().trust_proxy else None
        if (forwarded_proto or request.url.scheme) == "https":
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        if path.startswith("/api/"):
            log.info("%s %s %s %.0fms id=%s", request.method, path, response.status_code,
                     (time.perf_counter() - started) * 1000, request_id)
        return response


class BodySizeLimitMiddleware:
    """Reject request bodies over MAX_BODY_BYTES, whether or not Content-Length is honest."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = get_settings().max_body_bytes
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_big = int(value) > limit
                except ValueError:
                    too_big = True
                if too_big:
                    await JSONResponse({"detail": "Request body is too large."}, status_code=413)(scope, receive, send)
                    return

        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            if exceeded:
                await JSONResponse({"detail": "Request body is too large."}, status_code=413)(scope, receive, send)


class _BodyTooLarge(Exception):
    pass
