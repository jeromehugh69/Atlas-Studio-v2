"""Security middleware for SOC 2, ISO 27001, and NIST CSF compliance.

Note: BaseHTTPMiddleware breaks streaming responses and WebSockets.
This module provides ASGI-native middleware and FastAPI dependencies instead.
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ws: wss: http://localhost:11434 http://127.0.0.1:11434; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all responses.

    WARNING: Do not use with streaming endpoints or WebSockets.
    For those, add headers manually to each response.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


class SecurityHeadersASGI:
    """ASGI-native security headers middleware that works with streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                for header, value in SECURITY_HEADERS.items():
                    headers.append((header.encode(), value.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    """In-memory rate limiter as a FastAPI dependency.

    Usage:
        rate_limiter = RateLimitMiddleware(max_requests=100, window_seconds=60)

        @app.get("/api/example")
        async def example(request: Request):
            rate_limiter.check(request)
            return {"status": "ok"}
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        client_id = self._get_client_id(request)
        now = time.time()
        cutoff = now - self.window_seconds

        self.requests[client_id] = [
            t for t in self.requests[client_id] if t > cutoff
        ]

        if len(self.requests[client_id]) >= self.max_requests:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"
            )

        self.requests[client_id].append(now)

    def get_remaining(self, request: Request) -> int:
        client_id = self._get_client_id(request)
        now = time.time()
        cutoff = now - self.window_seconds
        recent = [t for t in self.requests[client_id] if t > cutoff]
        return max(0, self.max_requests - len(recent))


class RateLimitExceeded(Exception):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        self.message = message
        super().__init__(self.message)
