# End-to-End Lifecycle Automation Plan

## Overview

Ensure the platform code change process operates successfully from user input (speech, text, files, screenshots) through to deployment. Atlas should convert any input into a request and execute the full lifecycle automatically.

**MITM (Man-in-the-Middle) Security Layer**: All requests, responses, and agent actions pass through a controlled middleware layer that validates, sanitizes, logs, and enforces policies before reaching any component.

## Current State Analysis

### What Works
- ✅ Request intake via text (`POST /api/atlas/intake`)
- ✅ Change request classification (regex-based)
- ✅ Approval workflow with HMAC challenge codes
- ✅ Plan creation and specialist reviews
- ✅ Forge tool loop for code implementation
- ✅ Change set creation with SHA-256 tracking
- ✅ Lifecycle transitions (development → test → sandbox → production)
- ✅ Audit trail with evidence collection

### Critical Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| No multi-modal input (speech, files, screenshots) | Users can only type requests | P0 |
| No automated stage progression | Manual API calls needed at each gate | P0 |
| No deployment execution | Lifecycle completes but nothing deploys | P0 |
| No rollback mechanism | Cannot revert failed deployments | P1 |
| DelegationRouter not wired | Cross-skill routing is prompt-based only | P1 |
| Approval codes lost on restart | Pending approvals become unusable | P2 |

## Target State

### MITM Security Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER LAYER                                        │
│  (Browser, CLI, API Client)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MITM SECURITY MIDDLEWARE                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   Input     │  │   Policy    │  │   Audit     │  │   Output    │       │
│  │  Validator  │  │   Engine    │  │   Logger    │  │  Sanitizer  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   Rate      │  │   Auth      │  │   Encrypt   │  │   Throttle  │       │
│  │  Limiter    │  │  Checker    │  │   Layer     │  │   Queue     │       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INPUT PROCESSING PIPELINE                              │
│  ┌──────────┐       ┌──────────┐      ┌──────────┐      ┌──────────┐      │
│  │  Speech   │       │  Vision  │      │   Text   │      │   File   │      │
│  │  (STT)   │       │ (OCR)    │      │ (Parse)  │      │ (Extract)│      │
│  └──────────┘       └──────────┘      └──────────┘      └──────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ATLAS REQUEST INTAKE                                      │
│         (Classification, Scoping, Routing)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  AUTOMATED LIFECYCLE ENGINE                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Development │→│   Test   │→│ Sandbox  │→│Production │→│ Complete  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                     ↑              │              │                         │
│                     │              ▼              ▼                         │
│                     │        ┌──────────┐  ┌──────────┐                   │
│                     └────────│ Rollback │  │ Deploy   │                   │
│                              └──────────┘  └──────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT                                          │
│              (Sandbox → Production → Git Commit)                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Multi-Modal Input Pipeline

```
User Input (any format)
    │
    ├── Text ──────────────┐
    ├── Speech ────────────┤
    ├── File Upload ───────┤
    ├── Screenshot ────────┤
    │                      ▼
    │              ┌───────────────┐
    │              │ Input Router  │
    │              └───────────────┘
    │                      │
    │    ┌─────────────────┼─────────────────┐
    │    ▼                 ▼                 ▼
    │ ┌──────┐       ┌──────────┐      ┌──────────┐
    │ │ STT  │       │ OCR/Vision│      │  Parser  │
    │ └──────┘       └──────────┘      └──────────┘
    │    │                 │                 │
    │    └─────────────────┼─────────────────┘
    │                      ▼
    │              ┌───────────────┐
    │              │ Unified Request│
    │              └───────────────┘
    │                      │
    ▼                      ▼
┌─────────────────────────────────────────┐
│         Atlas Request Intake            │
│   (classifies, scopes, routes)          │
└─────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│      Automated Lifecycle Engine         │
│   (drives all stages automatically)     │
└─────────────────────────────────────────┘
                      │
                      ▼
              Deployment Complete
```

## Implementation Plan

### Phase 1: MITM Security Middleware (Week 1)

#### Ticket 1.1: MITM Security Middleware Core
**File:** `src/atlas_studio/security/mitm.py`

```python
from __future__ import annotations
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from typing import Any, Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class MITMSecurityMiddleware(BaseHTTPMiddleware):
    """Man-in-the-Middle security layer for all requests."""
    
    def __init__(
        self,
        app,
        secret_key: str,
        rate_limit: int = 100,
        rate_window: int = 60,
        audit_log_path: str = "audit.jsonl",
    ):
        super().__init__(app)
        self.secret_key = secret_key
        self.rate_limit = rate_limit
        self.rate_window = rate_window
        self.audit_log_path = audit_log_path
        self.request_counts: dict[str, list[float]] = {}
        self.policy_engine = PolicyEngine()
        self.audit_logger = AuditLogger(audit_log_path)
        self.input_validator = InputValidator()
        self.output_sanitizer = OutputSanitizer()
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        
        # 1. Rate limiting
        if self._is_rate_limited(client_ip):
            return Response(
                content=json.dumps({"error": "Rate limit exceeded"}),
                status_code=429,
                headers={"Content-Type": "application/json"},
            )
        
        # 2. Authentication check
        auth_result = await self._check_auth(request)
        if not auth_result["valid"]:
            await self.audit_logger.log({
                "event": "auth_failed",
                "client": client_ip,
                "path": str(request.url.path),
                "reason": auth_result["reason"],
            })
            return Response(
                content=json.dumps({"error": "Authentication failed"}),
                status_code=401,
                headers={"Content-Type": "application/json"},
            )
        
        # 3. Input validation
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            validation_result = self.input_validator.validate(body, request.headers.get("content-type"))
            if not validation_result["valid"]:
                await self.audit_logger.log({
                    "event": "input_validation_failed",
                    "client": client_ip,
                    "path": str(request.url.path),
                    "reason": validation_result["reason"],
                })
                return Response(
                    content=json.dumps({"error": "Invalid input"}),
                    status_code=400,
                    headers={"Content-Type": "application/json"},
                )
        
        # 4. Policy enforcement
        policy_result = self.policy_engine.evaluate(request, auth_result.get("user"))
        if not policy_result["allowed"]:
            await self.audit_logger.log({
                "event": "policy_violation",
                "client": client_ip,
                "path": str(request.url.path),
                "policy": policy_result["policy"],
                "reason": policy_result["reason"],
            })
            return Response(
                content=json.dumps({"error": "Policy violation"}),
                status_code=403,
                headers={"Content-Type": "application/json"},
            )
        
        # 5. Process request
        response = await call_next(request)
        
        # 6. Output sanitization
        if response.status_code == 200:
            body = await response.body()
            sanitized = self.output_sanitizer.sanitize(body)
            response = Response(
                content=sanitized,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        
        # 7. Audit logging
        duration = time.time() - start_time
        await self.audit_logger.log({
            "event": "request_completed",
            "client": client_ip,
            "method": request.method,
            "path": str(request.url.path),
            "status": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user": auth_result.get("user"),
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # 8. Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Request-ID"] = hashlib.sha256(
            f"{client_ip}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        return response
    
    def _is_rate_limited(self, client_ip: str) -> bool:
        """Check if client is rate limited."""
        now = time.time()
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []
        
        # Clean old requests
        self.request_counts[client_ip] = [
            t for t in self.request_counts[client_ip]
            if now - t < self.rate_window
        ]
        
        # Check limit
        if len(self.request_counts[client_ip]) >= self.rate_limit:
            return True
        
        # Record request
        self.request_counts[client_ip].append(now)
        return False
    
    async def _check_auth(self, request: Request) -> dict[str, Any]:
        """Check authentication."""
        auth_header = request.headers.get("authorization", "")
        
        if not auth_header:
            # Check for session cookie
            session = request.cookies.get("atlas_session")
            if session:
                # Validate session
                return {"valid": True, "user": "local-user", "method": "session"}
            return {"valid": False, "reason": "No authentication provided"}
        
        # Validate Bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Validate token (placeholder - implement your auth logic)
            if token == "atlas-local-worker":
                return {"valid": True, "user": "worker", "method": "token"}
            return {"valid": False, "reason": "Invalid token"}
        
        return {"valid": False, "reason": "Invalid auth format"}
```

#### Ticket 1.2: Policy Engine
**File:** `src/atlas_studio/security/policy.py`

```python
from __future__ import annotations
from typing import Any
from fastapi import Request

class PolicyEngine:
    """Enforce security policies on all requests."""
    
    # Paths that require specific permissions
    PROTECTED_PATHS = {
        "/api/agents": {"method": "POST", "required_role": "admin"},
        "/api/agents": {"method": "DELETE", "required_role": "admin"},
        "/api/change-sets": {"method": "POST", "required_role": "developer"},
        "/api/change-sets": {"method": "DELETE", "required_role": "admin"},
        "/api/lifecycles": {"method": "POST", "required_role": "developer"},
        "/api/lifecycles": {"method": "PATCH", "required_role": "developer"},
    }
    
    # Paths that are read-only (no auth required for local)
    PUBLIC_PATHS = {
        "/api/health/live",
        "/api/health/ready",
        "/api/config",
        "/static/*",
    }
    
    def evaluate(self, request: Request, user: str | None) -> dict[str, Any]:
        """Evaluate if request is allowed."""
        path = str(request.url.path)
        method = request.method
        
        # Check public paths
        for public_path in self.PUBLIC_PATHS:
            if path.startswith(public_path.replace("*", "")):
                return {"allowed": True, "policy": "public"}
        
        # Check protected paths
        for protected_path, rules in self.PROTECTED_PATHS.items():
            if path.startswith(protected_path) and method == rules["method"]:
                # Check user role
                if user and self._has_role(user, rules["required_role"]):
                    return {"allowed": True, "policy": "protected"}
                return {
                    "allowed": False,
                    "policy": "protected",
                    "reason": f"Requires {rules['required_role']} role",
                }
        
        # Default: allow for local user
        return {"allowed": True, "policy": "default"}
    
    def _has_role(self, user: str, role: str) -> bool:
        """Check if user has required role."""
        # Placeholder - implement your role logic
        if user == "local-user":
            return True  # Local user has all roles
        return False
```

#### Ticket 1.3: Input Validator
**File:** `src/atlas_studio/security/validator.py`

```python
from __future__ import annotations
import json
import re
from typing import Any

class InputValidator:
    """Validate all inputs before processing."""
    
    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # XSS
        r"javascript:",  # JavaScript protocol
        r"on\w+\s*=",  # Event handlers
        r"\.\./",  # Path traversal
        r"union\s+select",  # SQL injection
        r"drop\s+table",  # SQL injection
        r"exec\s*\(",  # Code execution
        r"eval\s*\(",  # Code execution
    ]
    
    def validate(self, body: bytes, content_type: str | None) -> dict[str, Any]:
        """Validate request body."""
        try:
            if content_type and "json" in content_type:
                data = json.loads(body)
                return self._validate_json(data)
            elif content_type and "form" in content_type:
                return self._validate_form(body)
            else:
                return self._validate_raw(body)
        except Exception as e:
            return {"valid": False, "reason": f"Validation error: {e}"}
    
    def _validate_json(self, data: dict) -> dict[str, Any]:
        """Validate JSON data."""
        # Check for dangerous patterns in string values
        for key, value in data.items():
            if isinstance(value, str):
                if self._contains_dangerous_patterns(value):
                    return {
                        "valid": False,
                        "reason": f"Dangerous pattern detected in field: {key}",
                    }
            elif isinstance(value, dict):
                result = self._validate_json(value)
                if not result["valid"]:
                    return result
        
        return {"valid": True}
    
    def _validate_form(self, body: bytes) -> dict[str, Any]:
        """Validate form data."""
        try:
            body_str = body.decode("utf-8")
            if self._contains_dangerous_patterns(body_str):
                return {"valid": False, "reason": "Dangerous pattern in form data"}
            return {"valid": True}
        except Exception:
            return {"valid": True}
    
    def _validate_raw(self, body: bytes) -> dict[str, Any]:
        """Validate raw body."""
        try:
            body_str = body.decode("utf-8", errors="ignore")
            if self._contains_dangerous_patterns(body_str):
                return {"valid": False, "reason": "Dangerous pattern in request body"}
            return {"valid": True}
        except Exception:
            return {"valid": True}
    
    def _contains_dangerous_patterns(self, text: str) -> bool:
        """Check if text contains dangerous patterns."""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
```

#### Ticket 1.4: Audit Logger
**File:** `src/atlas_studio/security/audit.py`

```python
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any

class AuditLogger:
    """Log all requests and responses for compliance."""
    
    def __init__(self, log_path: str = "audit.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def log(self, event: dict[str, Any]):
        """Log an audit event."""
        event["timestamp"] = datetime.utcnow().isoformat()
        
        with open(self.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")
    
    async def log_request(self, request_data: dict[str, Any]):
        """Log a request."""
        await self.log({
            "event_type": "request",
            **request_data,
        })
    
    async def log_response(self, response_data: dict[str, Any]):
        """Log a response."""
        await self.log({
            "event_type": "response",
            **response_data,
        })
    
    async def log_agent_action(self, action_data: dict[str, Any]):
        """Log an agent action."""
        await self.log({
            "event_type": "agent_action",
            **action_data,
        })
    
    async def log_security_event(self, security_data: dict[str, Any]):
        """Log a security event."""
        await self.log({
            "event_type": "security",
            **security_data,
        })
```

#### Ticket 1.5: Output Sanitizer
**File:** `src/atlas_studio/security/sanitizer.py`

```python
from __future__ import annotations
import json
import re
from typing import Any

class OutputSanitizer:
    """Sanitize all outputs before sending to client."""
    
    # Patterns to remove or mask
    SENSITIVE_PATTERNS = [
        (r"api[_-]?key\s*[=:]\s*['\"]?([a-zA-Z0-9]{20,})['\"]?", "api_key: ***REDACTED***"),
        (r"password\s*[=:]\s*['\"]?([^\s'\"]+)['\"]?", "password: ***REDACTED***"),
        (r"secret\s*[=:]\s*['\"]?([a-zA-Z0-9]{20,})['\"]?", "secret: ***REDACTED***"),
        (r"token\s*[=:]\s*['\"]?([a-zA-Z0-9]{20,})['\"]?", "token: ***REDACTED***"),
    ]
    
    def sanitize(self, body: bytes) -> bytes:
        """Sanitize response body."""
        try:
            body_str = body.decode("utf-8")
            
            # Check if JSON
            if body_str.strip().startswith("{") or body_str.strip().startswith("["):
                data = json.loads(body_str)
                sanitized = self._sanitize_dict(data)
                return json.dumps(sanitized).encode("utf-8")
            else:
                # Plain text
                return self._sanitize_text(body_str).encode("utf-8")
        except Exception:
            return body
    
    def _sanitize_dict(self, data: dict) -> dict:
        """Sanitize dictionary values."""
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = self._sanitize_text(value)
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_dict(item) if isinstance(item, dict)
                    else self._sanitize_text(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized
    
    def _sanitize_text(self, text: str) -> str:
        """Sanitize text content."""
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text
```

### Phase 2: Multi-Modal Input (Week 1-2)

#### Ticket 1.1: Input Router Module
**File:** `src/atlas_studio/input/__init__.py`

```python
from .router import InputRouter
from .text import TextProcessor
from .speech import SpeechProcessor
from .vision import VisionProcessor

__all__ = ["InputRouter", "TextProcessor", "SpeechProcessor", "VisionProcessor"]
```

**File:** `src/atlas_studio/input/router.py`

```python
from __future__ import annotations
from typing import Any
from .text import TextProcessor
from .speech import SpeechProcessor
from .vision import VisionProcessor

class InputRouter:
    """Route multi-modal inputs to appropriate processors."""
    
    def __init__(self):
        self.text = TextProcessor()
        self.speech = SpeechProcessor()
        self.vision = VisionProcessor()
    
    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process any input format into a unified request."""
        input_type = input_data.get("type", "text")
        
        if input_type == "text":
            return await self.text.process(input_data)
        elif input_type == "speech":
            return await self.speech.process(input_data)
        elif input_type == "file":
            return await self.text.process_file(input_data)
        elif input_type == "screenshot":
            return await self.vision.process(input_data)
        else:
            raise ValueError(f"Unsupported input type: {input_type}")
```

#### Ticket 1.2: Text Processor
**File:** `src/atlas_studio/input/text.py`

```python
from __future__ import annotations
import re
from typing import Any

class TextProcessor:
    """Process text input into structured requests."""
    
    CHANGE_VERBS = r"add|build|change|configure|create|delete|fix|implement|modify|update|upgrade|wire"
    FEATURE_TARGETS = r"agent|approval|button|code|dashboard|feature|file|interface|page|permission|platform|setting|skill|tool|workflow"
    
    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process text input."""
        text = input_data.get("text", "")
        context = input_data.get("context", {})
        
        return {
            "type": "text",
            "content": text,
            "is_change_request": self._is_change_request(text),
            "extracted_intent": self._extract_intent(text),
            "context": context,
        }
    
    async def process_file(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process file upload."""
        file_path = input_data.get("file_path", "")
        file_content = input_data.get("file_content", "")
        file_type = input_data.get("file_type", "")
        
        # Extract text from file
        text = self._extract_text(file_content, file_type)
        
        return {
            "type": "file",
            "file_path": file_path,
            "content": text,
            "is_change_request": self._is_change_request(text),
            "extracted_intent": self._extract_intent(text),
        }
    
    def _is_change_request(self, text: str) -> bool:
        """Detect if text is a change request."""
        change_pattern = rf"\b({self.CHANGE_VERBS})\b"
        target_pattern = rf"\b({self.FEATURE_TARGETS})\b"
        
        has_change_verb = bool(re.search(change_pattern, text, re.IGNORECASE))
        has_target = bool(re.search(target_pattern, text, re.IGNORECASE))
        
        return has_change_verb and has_target
    
    def _extract_intent(self, text: str) -> dict[str, Any]:
        """Extract structured intent from text."""
        return {
            "verbs": re.findall(self.CHANGE_VERBS, text, re.IGNORECASE),
            "targets": re.findall(self.FEATURE_TARGETS, text, re.IGNORECASE),
            "confidence": 0.8,
        }
    
    def _extract_text(self, content: str, file_type: str) -> str:
        """Extract text from file content."""
        if file_type == "text/plain":
            return content
        elif file_type == "text/markdown":
            return content
        elif file_type == "application/json":
            import json
            try:
                data = json.loads(content)
                return json.dumps(data, indent=2)
            except:
                return content
        return content
```

#### Ticket 1.3: Speech Processor
**File:** `src/atlas_studio/input/speech.py`

```python
from __future__ import annotations
from typing import Any

class SpeechProcessor:
    """Process speech input via STT service."""
    
    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process speech input."""
        audio_data = input_data.get("audio_data", "")
        audio_format = input_data.get("audio_format", "wav")
        
        # Transcribe via existing speech service
        transcription = await self._transcribe(audio_data, audio_format)
        
        # Process as text
        from .text import TextProcessor
        text_processor = TextProcessor()
        
        return await text_processor.process({
            "text": transcription,
            "context": input_data.get("context", {}),
        })
    
    async def _transcribe(self, audio_data: str, audio_format: str) -> str:
        """Transcribe audio to text."""
        # Use existing speech service or local Whisper
        # This is a placeholder - actual implementation depends on your speech service
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "http://localhost:8091/transcribe",
                    content=audio_data,
                    headers={"Content-Type": f"audio/{audio_format}"},
                )
                if response.status_code == 200:
                    return response.json().get("text", "")
        except Exception:
            pass
        
        return "[Speech transcription unavailable]"
```

#### Ticket 1.4: Vision Processor
**File:** `src/atlas_studio/input/vision.py`

```python
from __future__ import annotations
from typing import Any

class VisionProcessor:
    """Process screenshots and images via vision model."""
    
    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process screenshot/image input."""
        image_data = input_data.get("image_data", "")
        image_format = input_data.get("image_format", "png")
        user_context = input_data.get("context", {})
        
        # Analyze image with vision model
        analysis = await self._analyze_image(image_data, image_format)
        
        # Combine with user context
        combined_text = self._combine_analysis(analysis, user_context)
        
        # Process as text
        from .text import TextProcessor
        text_processor = TextProcessor()
        
        return await text_processor.process({
            "text": combined_text,
            "context": user_context,
        })
    
    async def _analyze_image(self, image_data: str, image_format: str) -> str:
        """Analyze image with vision model."""
        import httpx
        import base64
        
        # Use LiteLLM vision model
        try:
            from litellm import completion
            
            response = await completion(
                model="ollama/llava",  # or any vision model
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this screenshot and describe what you see. Identify any UI elements, code, errors, or instructions. Be specific about what the user might want to change or fix."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500,
            )
            
            return response.choices[0].message.content
        except Exception as e:
            return f"[Vision analysis failed: {e}]"
    
    def _combine_analysis(self, analysis: str, context: dict) -> str:
        """Combine vision analysis with user context."""
        parts = [analysis]
        
        if context.get("instruction"):
            parts.append(f"\nUser instruction: {context['instruction']}")
        
        if context.get("target"):
            parts.append(f"\nTarget: {context['target']}")
        
        return "\n".join(parts)
```

### Phase 2: Automated Lifecycle Engine (Week 2)

#### Ticket 2.1: Lifecycle Engine Module
**File:** `src/atlas_studio/lifecycle/engine.py`

```python
from __future__ import annotations
import asyncio
from typing import Any
from datetime import datetime

class LifecycleEngine:
    """Automated lifecycle progression engine."""
    
    STAGES = ["development", "test", "sandbox", "production"]
    
    def __init__(self, infrastructure, provider):
        self.infrastructure = infrastructure
        self.provider = provider
        self.running = False
    
    async def start(self):
        """Start the lifecycle engine."""
        self.running = True
        while self.running:
            await self._process_pending_lifecycles()
            await asyncio.sleep(10)  # Check every 10 seconds
    
    def stop(self):
        """Stop the lifecycle engine."""
        self.running = False
    
    async def _process_pending_lifecycles(self):
        """Process all lifecycles that can be advanced."""
        lifecycles = await self.infrastructure.load_lifecycles(status="active")
        
        for lifecycle in lifecycles:
            try:
                await self._advance_lifecycle(lifecycle)
            except Exception as e:
                print(f"Error advancing lifecycle {lifecycle.id}: {e}")
    
    async def _advance_lifecycle(self, lifecycle):
        """Attempt to advance a lifecycle to the next stage."""
        current_stage = lifecycle.stage
        
        if current_stage == "development":
            await self._check_development_complete(lifecycle)
        elif current_stage == "test":
            await self._check_test_complete(lifecycle)
        elif current_stage == "sandbox":
            await self._check_sandbox_complete(lifecycle)
        elif current_stage == "production":
            await self._check_production_complete(lifecycle)
    
    async def _check_development_complete(self, lifecycle):
        """Check if development stage is complete."""
        # Check if all change sets are applied and tested
        change_sets = await self.infrastructure.load_change_sets(lifecycle_id=lifecycle.id)
        
        if not change_sets:
            return
        
        all_applied = all(cs.status in ["applied", "tests_passed", "committed"] for cs in change_sets)
        all_tested = all(cs.status in ["tests_passed", "committed"] for cs in change_sets)
        
        if all_applied and all_tested:
            # Automatically transition to test
            await self._transition(lifecycle, "test", {
                "type": "development_complete",
                "source": "lifecycle-engine",
                "status": "passed",
                "recorded_at": datetime.utcnow().isoformat(),
            })
    
    async def _check_test_complete(self, lifecycle):
        """Check if test stage is complete."""
        # Check for test evidence
        test_evidence = [
            e for e in lifecycle.evidence
            if e.get("stage") == "test" and e.get("type") == "test"
        ]
        
        if test_evidence:
            # Check if any test passed
            passed = any(e.get("status") == "passed" for e in test_evidence)
            if passed:
                # Automatically transition to sandbox
                await self._transition(lifecycle, "sandbox", {
                    "type": "test_complete",
                    "source": "lifecycle-engine",
                    "status": "passed",
                    "recorded_at": datetime.utcnow().isoformat(),
                })
    
    async def _check_sandbox_complete(self, lifecycle):
        """Check if sandbox stage is complete."""
        # Sandbox is an evidence-gating stage
        # Check for sandbox evidence
        sandbox_evidence = [
            e for e in lifecycle.evidence
            if e.get("stage") == "sandbox" and e.get("status") == "passed"
        ]
        
        if sandbox_evidence:
            # Sandbox complete - requires user approval for production
            # Emit event for UI to show approval prompt
            await self._emit_production_approval_required(lifecycle)
    
    async def _check_production_complete(self, lifecycle):
        """Check if production stage is complete."""
        # Production is the final stage
        # Check for deployment evidence
        deploy_evidence = [
            e for e in lifecycle.evidence
            if e.get("stage") == "production" and e.get("type") == "deployment"
        ]
        
        if deploy_evidence:
            # Mark lifecycle as completed
            lifecycle.status = "completed"
            await self.infrastructure.persist_lifecycle(lifecycle)
    
    async def _transition(self, lifecycle, to_stage, evidence):
        """Transition lifecycle to next stage."""
        from ..models import AuditEvent
        
        # Record transition evidence
        lifecycle.evidence.append(evidence)
        lifecycle.stage = to_stage
        
        # Update lifecycle
        await self.infrastructure.persist_lifecycle(lifecycle)
        
        # Create audit event
        event = AuditEvent(
            action=f"lifecycle.transition.{to_stage}",
            actor="lifecycle-engine",
            target=lifecycle.id,
            outcome="success",
            details={
                "from_stage": lifecycle.stage,
                "to_stage": to_stage,
                "evidence": evidence,
            },
        )
        await self.infrastructure.persist_audit(event)
        
        # Broadcast lifecycle update
        # (WebSocket broadcast would go here)
    
    async def _emit_production_approval_required(self, lifecycle):
        """Emit event requiring user approval for production."""
        from ..models import AuditEvent
        
        event = AuditEvent(
            action="lifecycle.production_approval_required",
            actor="lifecycle-engine",
            target=lifecycle.id,
            outcome="pending",
            details={"lifecycle_id": lifecycle.id},
        )
        await self.infrastructure.persist_audit(event)
```

#### Ticket 2.2: Deployment Executor Module
**File:** `src/atlas_studio/lifecycle/deployment.py`

```python
from __future__ import annotations
from typing import Any
from pathlib import Path

class DeploymentExecutor:
    """Execute deployments for completed lifecycles."""
    
    def __init__(self, infrastructure, worker):
        self.infrastructure = infrastructure
        self.worker = worker
    
    async def deploy(self, lifecycle_id: str, environment: str) -> dict[str, Any]:
        """Deploy to specified environment."""
        lifecycle = await self.infrastructure.load_lifecycle(lifecycle_id)
        if not lifecycle:
            return {"error": "Lifecycle not found"}
        
        # Get the change sets
        change_sets = await self.infrastructure.load_change_sets(lifecycle_id=lifecycle_id)
        
        if environment == "sandbox":
            return await self._deploy_to_sandbox(lifecycle, change_sets)
        elif environment == "production":
            return await self._deploy_to_production(lifecycle, change_sets)
        else:
            return {"error": f"Unknown environment: {environment}"}
    
    async def _deploy_to_sandbox(self, lifecycle, change_sets) -> dict[str, Any]:
        """Deploy to sandbox environment."""
        # Execute the change sets in the sandbox workspace
        results = []
        
        for cs in change_sets:
            if cs.status == "applied":
                # Re-apply the change set
                result = await self.worker.execute({
                    "action": "file_write",
                    "path": cs.file_path,
                    "content": cs.after_content,
                })
                results.append(result)
        
        # Record sandbox deployment evidence
        await self._record_evidence(lifecycle, "sandbox", "deployment", "passed", {
            "results": results,
            "change_sets": [cs.id for cs in change_sets],
        })
        
        return {"status": "deployed", "environment": "sandbox", "results": results}
    
    async def _deploy_to_production(self, lifecycle, change_sets) -> dict[str, Any]:
        """Deploy to production environment."""
        # This would integrate with your actual deployment mechanism
        # Options: Docker, systemd, git push, etc.
        
        results = []
        
        for cs in change_sets:
            # For now, just commit the changes
            result = await self.worker.execute({
                "action": "git_commit",
                "message": f"Deploy {cs.title} to production",
                "files": [cs.file_path],
            })
            results.append(result)
        
        # Record production deployment evidence
        await self._record_evidence(lifecycle, "production", "deployment", "passed", {
            "results": results,
            "change_sets": [cs.id for cs in change_sets],
        })
        
        return {"status": "deployed", "environment": "production", "results": results}
    
    async def rollback(self, lifecycle_id: str) -> dict[str, Any]:
        """Rollback a deployment."""
        lifecycle = await self.infrastructure.load_lifecycle(lifecycle_id)
        if not lifecycle:
            return {"error": "Lifecycle not found"}
        
        # Get the change sets
        change_sets = await self.infrastructure.load_change_sets(lifecycle_id=lifecycle_id)
        
        results = []
        
        for cs in change_sets:
            if cs.before_sha256 and cs.before_content:
                # Restore original file
                result = await self.worker.execute({
                    "action": "file_write",
                    "path": cs.file_path,
                    "content": cs.before_content,
                })
                results.append(result)
        
        # Record rollback evidence
        await self._record_evidence(lifecycle, lifecycle.stage, "rollback", "executed", {
            "results": results,
            "change_sets": [cs.id for cs in change_sets],
        })
        
        return {"status": "rolled_back", "results": results}
    
    async def _record_evidence(self, lifecycle, stage, evidence_type, status, details):
        """Record deployment evidence."""
        from ..models import AuditEvent
        
        evidence = {
            "stage": stage,
            "type": evidence_type,
            "status": status,
            "source": "deployment-executor",
            "recorded_at": datetime.utcnow().isoformat(),
            **details,
        }
        
        lifecycle.evidence.append(evidence)
        await self.infrastructure.persist_lifecycle(lifecycle)
        
        event = AuditEvent(
            action=f"deployment.{evidence_type}.{status}",
            actor="deployment-executor",
            target=lifecycle.id,
            outcome="success" if status == "passed" else status,
            details=details,
        )
        await self.infrastructure.persist_audit(event)
```

#### Ticket 2.3: Integrate Multi-Modal Input with Intake
**File:** `src/atlas_studio/main.py` (modifications)

```python
# Add import at top
from .input import InputRouter

# Add input router initialization
input_router = InputRouter()

# New endpoint: POST /api/intake/multi-modal
@app.post("/api/intake/multi-modal")
async def intake_multi_modal(request: Request):
    """Process multi-modal input (text, speech, files, screenshots)."""
    body = await request.json()
    
    # Process through input router
    try:
        processed = await input_router.process(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Input processing failed: {e}")
    
    # Create intake request
    intake_request = AtlasIntakeRequest(
        prompt=processed.get("content", ""),
        title=processed.get("extracted_intent", {}).get("targets", ["request"])[0],
    )
    
    # Route to existing intake logic
    # ... (reuse existing intake code)
```

### Phase 3: Approval Persistence (Week 2)

#### Ticket 3.1: Persist Approval Challenges
**File:** `src/atlas_studio/layers/approvals.py` (modifications)

```python
class ApprovalService:
    def __init__(self, store, infrastructure):
        self.store = store
        self.infrastructure = infrastructure
        self._challenges: dict[str, dict] = {}
    
    async def issue_challenge(self, approval_id: str, actor: str) -> dict:
        """Issue a challenge code and persist it."""
        import hashlib
        import hmac
        import secrets
        
        code = f"{secrets.randbelow(1000000):06d}"
        
        # Compute HMAC
        message = f"{approval_id}:{actor}:{code}"
        signature = hmac.new(
            self.worker_token.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        challenge = {
            "approval_id": approval_id,
            "actor": actor,
            "code": code,
            "signature": signature,
            "attempts": 0,
            "max_attempts": 5,
            "expires_at": datetime.utcnow() + timedelta(minutes=15),
        }
        
        # Store in memory
        self._challenges[approval_id] = challenge
        
        # Persist to database
        await self.infrastructure.persist_challenge(approval_id, challenge)
        
        return {"code": code, "approval_id": approval_id}
    
    async def load_challenges(self):
        """Load challenges from database on startup."""
        challenges = await self.infrastructure.load_challenges()
        for challenge in challenges:
            if challenge["expires_at"] > datetime.utcnow():
                self._challenges[challenge["approval_id"]] = challenge
```

### Phase 4: Wire DelegationRouter (Week 2)

#### Ticket 4.1: Integrate DelegationRouter
**File:** `src/atlas_studio/main.py` (modifications)

```python
# Add import
from .delegation import DelegationRouter

# Initialize delegation router
delegation_router = DelegationRouter(Path("skills/skill-registry.yaml"))

# Modify execute() to use delegation router
async def execute(request: TaskExecutionRequest) -> Task:
    # ... existing code ...
    
    # Check for delegation
    delegation_target = delegation_router.should_delegate("atlas-request-intake", prompt)
    if delegation_target:
        # Route to delegated skill
        system = f"{system}\n\n[DELEGATED TO: {delegation_target}]"
    
    # ... rest of existing code ...
```

## Files to Create/Modify

| File | Changes |
|------|---------|
| `src/atlas_studio/security/__init__.py` | Create |
| `src/atlas_studio/security/mitm.py` | Create - MITM Security Middleware |
| `src/atlas_studio/security/policy.py` | Create - Policy Engine |
| `src/atlas_studio/security/validator.py` | Create - Input Validator |
| `src/atlas_studio/security/audit.py` | Create - Audit Logger |
| `src/atlas_studio/security/sanitizer.py` | Create - Output Sanitizer |
| `src/atlas_studio/input/__init__.py` | Create |
| `src/atlas_studio/input/router.py` | Create |
| `src/atlas_studio/input/text.py` | Create |
| `src/atlas_studio/input/speech.py` | Create |
| `src/atlas_studio/input/vision.py` | Create |
| `src/atlas_studio/lifecycle/engine.py` | Create |
| `src/atlas_studio/lifecycle/deployment.py` | Create |
| `src/atlas_studio/main.py` | Add MITM middleware, endpoints, integrate components |
| `src/atlas_studio/layers/approvals.py` | Add challenge persistence |
| `src/atlas_studio/infrastructure.py` | Add challenge persistence methods |

## Testing

1. Verify text input creates intake request
2. Test speech input transcribes and creates request
3. Test file upload extracts text and creates request
4. Test screenshot analysis creates request
5. Verify lifecycle engine advances stages automatically
6. Test deployment executor deploys to sandbox
7. Test deployment executor deploys to production
8. Test rollback mechanism restores previous state
9. Verify approval challenges persist across restarts
10. Test delegation router routes to correct skill

## Success Criteria

- [ ] Multi-modal input (text, speech, files, screenshots) works
- [ ] All inputs are converted to unified request format
- [ ] Lifecycle engine automatically advances stages
- [ ] Deployment executes automatically when stages complete
- [ ] Rollback mechanism works
- [ ] Approval challenges persist across restarts
- [ ] DelegationRouter routes correctly
- [ ] Full audit trail at each gate
- [ ] All existing tests pass
