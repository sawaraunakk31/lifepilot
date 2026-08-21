"""Security middleware: hardening headers, CSP, and a lightweight rate limiter.

All local, no external services. The CSP intentionally restricts `connect-src`
to 'self', so the page can never send user data anywhere except this backend.
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Content-Security-Policy.
# NOTE: 'unsafe-eval' is required ONLY by the Tailwind Play CDN's runtime JIT.
# For production you would precompile Tailwind to a static .css and drop it.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])

_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory sliding-window limiter for /api/* endpoints (per client IP)."""

    def __init__(self, app, limit: int = 120, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            with self._lock:
                dq = self._hits.setdefault(ip, deque())
                while dq and now - dq[0] > self.window:
                    dq.popleft()
                if len(dq) >= self.limit:
                    retry = int(self.window - (now - dq[0])) + 1
                    return JSONResponse(
                        {"detail": "Too many requests. Please slow down."},
                        status_code=429,
                        headers={"Retry-After": str(retry)},
                    )
                dq.append(now)
        return await call_next(request)


def add_security(app, *, rate_limit: int = 120, rate_window: int = 60) -> None:
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, limit=rate_limit, window_seconds=rate_window)
