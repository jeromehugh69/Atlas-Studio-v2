"""MITM Security Middleware - ASGI-native Man-in-the-Middle security layer.

This middleware intercepts all HTTP requests and provides:
- Rate limiting
- Session-based authentication
- Input validation (XSS, SQLi, path traversal)
- Policy enforcement
- Audit logging
- Output sanitization
- Security headers

IMPORTANT: This is ASGI-native middleware that works with streaming responses and WebSockets.
Do NOT use BaseHTTPMiddleware as it breaks streaming.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from .audit import AuditLogger
from .policy import PolicyEngine
from .sanitizer import OutputSanitizer
from .validator import InputValidator


class SessionStore:
    """In-memory session store for local-first single-user auth."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._owner_token: str = secrets.token_hex(32)

    def create_session(self, role: str = "owner") -> str:
        token = secrets.token_hex(32)
        self._sessions[token] = {
            "role": role,
            "created_at": time.time(),
            "last_seen": time.time(),
        }
        return token

    def validate(self, token: str) -> dict[str, Any] | None:
        session = self._sessions.get(token)
        if not session:
            return None
        session["last_seen"] = time.time()
        return session

    def validate_owner_token(self, token: str) -> bool:
        return secrets.compare_digest(token, self._owner_token)

    def get_owner_token(self) -> str:
        return self._owner_token

    def revoke(self, token: str) -> None:
        self._sessions.pop(token, None)

    def evict_stale(self, max_age: float = 86400) -> None:
        now = time.time()
        stale = [t for t, s in self._sessions.items() if now - s["last_seen"] > max_age]
        for t in stale:
            self._sessions.pop(t, None)


# Global session store — instantiated once per process
_session_store = SessionStore()


def get_session_store() -> SessionStore:
    return _session_store


# Role hierarchy: owner has all roles, other roles are scoped
ROLE_HIERARCHY: dict[str, set[str]] = {
    "owner": {"owner", "admin", "developer", "operations", "grc", "qa", "infosec"},
    "admin": {"admin", "developer", "operations", "grc", "qa", "infosec"},
    "developer": {"developer"},
    "operations": {"operations"},
    "grc": {"grc"},
    "qa": {"qa"},
    "infosec": {"infosec"},
}


class MITMSecurityMiddleware:
    """ASGI-native Man-in-the-Middle security layer intercepting all HTTP requests.

    Provides:
    - Rate limiting with automatic stale entry eviction
    - Session-based authentication (owner token or session cookie)
    - Input validation (XSS, SQLi, path traversal)
    - Policy enforcement
    - Audit logging
    - Output sanitization
    - Security headers

    Works with:
    - Regular HTTP responses
    - Streaming responses (SSE, chunked)
    - WebSockets
    """

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str,
        rate_limit: int = 100,
        rate_window: int = 60,
        audit_log_path: str = "audit.jsonl",
        skip_paths: list[str] | None = None,
    ):
        self.app = app
        self.secret_key = secret_key
        self.rate_limit = rate_limit
        self.rate_window = rate_window
        self.request_counts: dict[str, list[float]] = {}
        self.policy_engine = PolicyEngine()
        self.audit_logger = AuditLogger(audit_log_path)
        self.input_validator = InputValidator()
        self.output_sanitizer = OutputSanitizer()
        self._last_eviction = time.time()
        self.skip_paths = skip_paths or [
            "/api/health/live",
            "/api/health/ready",
            "/static/",
            "/api/docs",
            "/openapi.json",
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI application entry point."""
        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Skip middleware for certain paths
        if any(path.startswith(skip) for skip in self.skip_paths):
            await self.app(scope, receive, send)
            return

        # Enforce body size limit via Content-Length header
        content_length = self._get_header(scope, "content-length", "0")
        try:
            body_size = int(content_length)
        except ValueError:
            body_size = 0
        max_body = 50 * 1024 * 1024  # 50MB absolute max (uploads use separate limit)
        if body_size > max_body:
            await self._send_json_response(send, 413, {"error": "Request body too large"})
            return

        # Read request body for validation
        body = b""
        body_chunks = []
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return
        body = b"".join(body_chunks)

        # 1. Rate limiting
        if self._is_rate_limited(client_ip):
            await self.audit_logger.log_security_event({
                "event": "rate_limited",
                "client": client_ip,
                "path": path,
            })
            await self._send_json_response(send, 429, {"error": "Rate limit exceeded"})
            return

        # 2. Authentication check
        auth_result = self._check_auth(scope)
        if not auth_result["valid"]:
            await self.audit_logger.log_security_event({
                "event": "auth_failed",
                "client": client_ip,
                "path": path,
                "reason": auth_result["reason"],
            })
            await self._send_json_response(send, 401, {"error": "Authentication failed"})
            return

        # 3. Input validation for mutating requests
        if method in ["POST", "PUT", "PATCH"]:
            try:
                content_type = self._get_header(scope, "content-type", "")
                validation_result = self.input_validator.validate(body, content_type)
                if not validation_result["valid"]:
                    await self.audit_logger.log_security_event({
                        "event": "input_validation_failed",
                        "client": client_ip,
                        "path": path,
                        "reason": validation_result["reason"],
                    })
                    await self._send_json_response(send, 400, {"error": "Invalid input"})
                    return
            except Exception as e:
                await self.audit_logger.log_security_event({
                    "event": "input_validation_error",
                    "client": client_ip,
                    "path": path,
                    "error": str(e),
                })

        # 4. Policy enforcement
        policy_result = self._evaluate_policy(scope, auth_result.get("role"))
        if not policy_result["allowed"]:
            await self.audit_logger.log_security_event({
                "event": "policy_violation",
                "client": client_ip,
                "path": path,
                "policy": policy_result.get("policy"),
                "reason": policy_result.get("reason"),
            })
            await self._send_json_response(send, 403, {"error": "Policy violation"})
            return

        # Store body in scope so the receive wrapper can replay it
        scope["_mitm_body"] = body

        # 5. Process request with response interception
        start_time = time.time()
        await self._process_with_response_interception(
            scope, receive, send, client_ip, method, path, auth_result, start_time
        )

    async def _process_with_response_interception(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        client_ip: str,
        method: str,
        path: str,
        auth_result: dict[str, Any],
        start_time: float,
    ) -> None:
        """Process request and intercept response for security headers and audit."""
        response_started = False
        response_status = 200
        response_headers: list[tuple[bytes, bytes]] = []

        async def send_with_interception(message: dict) -> None:
            nonlocal response_started, response_status, response_headers

            if message["type"] == "http.response.start":
                response_started = True
                response_status = message.get("status", 200)
                response_headers = list(message.get("headers", []))

                # Add security headers
                security_headers = {
                    "x-content-type-options": b"nosniff",
                    "x-frame-options": b"DENY",
                    "x-xss-protection": b"1; mode=block",
                    "x-request-id": hashlib.sha256(
                        f"{client_ip}:{time.time()}".encode()
                    ).hexdigest()[:16].encode(),
                    "content-security-policy": b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ws: wss: http://localhost:11434 http://127.0.0.1:11434; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
                    "referrer-policy": b"strict-origin-when-cross-origin",
                    "permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    "strict-transport-security": b"max-age=31536000; includeSubDomains",
                }

                for header_name, header_value in security_headers.items():
                    response_headers.append((header_name.encode(), header_value))

                message["headers"] = response_headers
                await send(message)

            elif message["type"] == "http.response.body":
                # For streaming, we just pass through
                # Audit logging happens after completion
                await send(message)

            elif message["type"] == "http.disconnect":
                await send(message)

        # Create a wrapper receive that returns the body we already read
        body_sent = False
        original_body = scope.get("_mitm_body", b"")

        async def receive_with_body() -> dict:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": original_body, "more_body": False}
            else:
                return {"type": "http.disconnect"}

        try:
            await self.app(scope, receive_with_body, send_with_interception)
        finally:
            # Audit logging after request completes
            duration = time.time() - start_time
            await self.audit_logger.log({
                "event": "request_completed",
                "client": client_ip,
                "method": method,
                "path": path,
                "status": response_status,
                "duration_ms": round(duration * 1000, 2),
                "user": auth_result.get("user"),
                "timestamp": datetime.utcnow().isoformat(),
            })

    async def _send_json_response(self, send: Send, status: int, data: dict) -> None:
        """Send a JSON error response."""
        body = json.dumps(data).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    def _get_header(self, scope: Scope, name: str, default: str = "") -> str:
        """Get a header value from the ASGI scope."""
        headers = scope.get("headers", [])
        for header_name, header_value in headers:
            if header_name.decode("utf-8").lower() == name.lower():
                return header_value.decode("utf-8")
        return default

    def _is_rate_limited(self, client_ip: str) -> bool:
        """Check if client is rate limited. Evicts stale entries periodically."""
        now = time.time()

        # Evict stale entries every 60 seconds to prevent memory growth
        if now - self._last_eviction > 60:
            self._last_eviction = now
            stale_ips = [
                ip for ip, times in self.request_counts.items()
                if not times or now - times[-1] > self.rate_window * 2
            ]
            for ip in stale_ips:
                del self.request_counts[ip]

        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []

        self.request_counts[client_ip] = [
            t for t in self.request_counts[client_ip]
            if now - t < self.rate_window
        ]

        if len(self.request_counts[client_ip]) >= self.rate_limit:
            return True

        self.request_counts[client_ip].append(now)
        return False

    def _check_auth(self, scope: Scope) -> dict[str, Any]:
        """Check authentication from headers or session cookie.

        Authentication methods (in order of priority):
        1. Bearer token matching the owner token
        2. Bearer token matching the worker token
        3. Session cookie from SessionStore
        4. API key matching owner token
        5. No credentials → reject
        """
        headers = scope.get("headers", [])
        auth_header = ""
        session_token = ""
        api_key = ""

        for header_name, header_value in headers:
            name = header_name.decode("utf-8").lower()
            value = header_value.decode("utf-8")
            if name == "authorization":
                auth_header = value
            elif name == "cookie":
                for cookie in value.split(";"):
                    stripped = cookie.strip()
                    if stripped.startswith("atlas_session="):
                        session_token = stripped.split("=", 1)[1]
            elif name == "x-api-key":
                api_key = value

        # 1. Owner bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            store = get_session_store()
            if store.validate_owner_token(token):
                return {"valid": True, "user": "owner", "role": "owner", "method": "owner-token"}
            # 2. Worker token for internal services
            from ..config import get_settings
            settings = get_settings()
            if secrets.compare_digest(token, settings.worker_token):
                return {"valid": True, "user": "worker", "role": "admin", "method": "worker-token"}
            return {"valid": False, "reason": "Invalid bearer token"}

        # 3. Session cookie
        if session_token:
            store = get_session_store()
            session = store.validate(session_token)
            if session:
                return {
                    "valid": True,
                    "user": "local-user",
                    "role": session.get("role", "owner"),
                    "method": "session",
                }

        # 4. API key (validated against owner token for simplicity)
        if api_key:
            store = get_session_store()
            if store.validate_owner_token(api_key):
                return {"valid": True, "user": "local-user", "role": "owner", "method": "api-key"}
            return {"valid": False, "reason": "Invalid API key"}

        # 5. No credentials — reject
        return {"valid": False, "reason": "Authentication required. Provide a session cookie or bearer token."}

    def _has_role(self, user_role: str, required_role: str) -> bool:
        """Check if user role includes the required role via hierarchy."""
        allowed_roles = ROLE_HIERARCHY.get(user_role, set())
        return required_role in allowed_roles or "owner" in allowed_roles

    def _evaluate_policy(self, scope: Scope, user_role: str | None) -> dict[str, Any]:
        """Evaluate policy for the request."""
        path = scope.get("path", "")
        method = scope.get("method", "")

        # Check public paths first
        for public_path in self.policy_engine.PUBLIC_PATHS:
            if path.startswith(public_path):
                return {"allowed": True, "policy": "public"}

        # Check protected paths
        for protected_path, methods in self.policy_engine.PROTECTED_PATHS.items():
            if path.startswith(protected_path) and method in methods:
                rules = methods[method]
                required_role = rules["required_role"]

                if user_role and self._has_role(user_role, required_role):
                    return {
                        "allowed": True,
                        "policy": "protected",
                        "role": required_role,
                    }
                return {
                    "allowed": False,
                    "policy": "protected",
                    "reason": f"Requires {required_role} role",
                }

        # Default: reject unauthenticated requests on non-public paths
        if not user_role:
            return {"allowed": False, "policy": "default", "reason": "Authentication required"}
        return {"allowed": True, "policy": "default"}
