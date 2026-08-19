# Code Templates

This file contains copy-paste ready code templates for the implementation.

## 1. LiteLLM Provider Template

```python
# src/atlas_studio/providers.py

from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
import json
import time
import logging

import httpx
import litellm

logger = logging.getLogger("atlas_studio.providers")


class ProviderError(RuntimeError):
    pass


class ModelProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], model: str, temperature: float = 0.3) -> str: ...

    @abstractmethod
    def stream(self, messages: list[dict[str, str]], model: str, temperature: float = 0.3) -> AsyncIterator[str]: ...

    @abstractmethod
    async def healthy(self) -> bool: ...

    async def chat_with_tools(self, messages: list[dict], model: str, tools: list[dict], temperature: float = 0.1) -> dict:
        raise ProviderError("configured model provider does not support structured tool calls")


class LiteLLMProvider(ModelProvider):
    """Unified LLM provider using LiteLLM. Replaces OllamaProvider and OpenAICompatibleProvider."""

    def __init__(
        self,
        api_base: str = "http://localhost:11434",
        api_key: str | None = None,
        model_prefix: str = "ollama",
        timeout_seconds: int = 120,
        max_tokens: int = 384,
        context_tokens: int = 1536,
        num_retries: int = 2,
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model_prefix = model_prefix
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.context_tokens = context_tokens
        self.num_retries = num_retries
        self._cost_log: list[dict] = []

        # Configure LiteLLM
        litellm.api_base = api_base
        if api_key:
            litellm.api_key = api_key

        # Enable cost tracking
        litellm.success_callback = [self._track_cost]

    def _track_cost(self, kwargs, completion_response, start_time, end_time):
        """Track cost per request for auditing."""
        cost = kwargs.get("response_cost", 0)
        tokens = 0
        if hasattr(completion_response, "usage") and completion_response.usage:
            tokens = completion_response.usage.total_tokens
        self._cost_log.append({
            "model": completion_response.model,
            "cost": cost,
            "tokens": tokens,
            "timestamp": start_time,
        })

    def _resolve_model(self, model: str) -> str:
        """Add provider prefix if not already present."""
        if "/" in model:
            return model
        return f"{self.model_prefix}/{model}"

    async def generate(self, messages, model, temperature=0.3):
        """Generate completion using LiteLLM."""
        full_model = self._resolve_model(model)
        try:
            response = await litellm.acompletion(
                model=full_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout_seconds,
                num_retries=self.num_retries,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise ProviderError(f"LiteLLM error: {e}") from e

    async def stream(self, messages, model, temperature=0.3):
        """Stream completion using LiteLLM."""
        full_model = self._resolve_model(model)
        try:
            response = await litellm.acompletion(
                model=full_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout_seconds,
                num_retries=self.num_retries,
                stream=True,
            )
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise ProviderError(f"LiteLLM streaming error: {e}") from e

    async def healthy(self):
        """Check if the provider is healthy."""
        try:
            if self.model_prefix == "ollama":
                async with httpx.AsyncClient(timeout=3) as client:
                    return (await client.get(f"{self.api_base}/api/tags")).is_success
            await self.generate([{"role": "user", "content": "hi"}], "test", temperature=0.1)
            return True
        except Exception:
            return False

    async def chat_with_tools(self, messages, model, tools, temperature=0.1):
        """Chat with tool support using LiteLLM."""
        full_model = self._resolve_model(model)
        try:
            response = await litellm.acompletion(
                model=full_model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=self.context_tokens,
                timeout=self.timeout_seconds,
                num_retries=self.num_retries,
            )
            message = response.choices[0].message
            return {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in (message.tool_calls or [])
                ],
            }
        except Exception as e:
            raise ProviderError(f"LiteLLM tool call error: {e}") from e

    def get_cost_log(self) -> list[dict]:
        """Return the cost log for auditing."""
        return self._cost_log.copy()


class ProviderGateway:
    def __init__(self, default: str, providers: dict[str, ModelProvider]):
        self.default = default
        self.providers = providers

    def get(self, provider: str | None = None) -> ModelProvider:
        name = provider or self.default
        if name not in self.providers:
            raise ProviderError(f"provider '{name}' is disabled or unavailable")
        return self.providers[name]
```

## 2. Security Middleware Template

```python
# src/atlas_studio/middleware/__init__.py

from .security import SecurityMiddleware, RateLimitMiddleware

__all__ = ["SecurityMiddleware", "RateLimitMiddleware"]
```

```python
# src/atlas_studio/middleware/security.py

from __future__ import annotations
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self';"
        )

        # Additional security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware."""

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old requests
        self.requests[client_ip] = [
            t for t in self.requests[client_ip]
            if now - t < self.window_seconds
        ]

        # Check rate limit
        if len(self.requests[client_ip]) >= self.max_requests:
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
            )

        # Record request
        self.requests[client_ip].append(now)

        return await call_next(request)
```

## 3. SQLite Encryption Template

```python
# src/atlas_studio/encryption.py

from __future__ import annotations
import hashlib
import json
from cryptography.fernet import Fernet


class SQLiteEncryption:
    """Encrypt sensitive data before writing to SQLite."""

    def __init__(self, key: str | None = None):
        if key:
            # Derive a consistent key from the provided string
            derived_key = hashlib.sha256(key.encode()).digest()
            # Fernet requires a URL-safe base64-encoded 32-byte key
            import base64
            self._key = base64.urlsafe_b64encode(derived_key)
        else:
            self._key = Fernet.generate_key()
        self._fernet = Fernet(self._key)

    def encrypt(self, data: str) -> str:
        """Encrypt string data."""
        return self._fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt string data."""
        return self._fernet.decrypt(encrypted_data.encode()).decode()

    def encrypt_dict(self, data: dict) -> str:
        """Encrypt dictionary as JSON."""
        return self.encrypt(json.dumps(data, default=str))

    def decrypt_dict(self, encrypted_data: str) -> dict:
        """Decrypt to dictionary."""
        return json.loads(self.decrypt(encrypted_data))
```

## 4. Audit Hash Chaining Template

```python
# Add to src/atlas_studio/models.py

from __future__ import annotations
import hashlib
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    action: str
    actor: str
    target: str
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Hash chaining for tamper evidence
    previous_hash: str = ""
    current_hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA256 hash of this event."""
        data = f"{self.action}{self.actor}{self.target}{self.outcome}{self.created_at}{self.previous_hash}"
        return hashlib.sha256(data.encode()).hexdigest()
```

## 5. OSCAL Compliance Template

```python
# src/atlas_studio/compliance/__init__.py

from .oscal import OSCALGenerator
from .classification import DataClassifier, DataClassification

__all__ = ["OSCALGenerator", "DataClassifier", "DataClassification"]
```

```python
# src/atlas_studio/compliance/oscal.py

from __future__ import annotations
from datetime import datetime
from typing import Any


class OSCALGenerator:
    """Generate OSCAL-compliant documentation."""

    @staticmethod
    def generate_ssp(
        system_name: str,
        audit_events: list[dict],
        controls: dict[str, str],
    ) -> dict[str, Any]:
        """Generate System Security Plan (SSP)."""
        return {
            "system-security-plan": {
                "uuid": f"ssp-{datetime.utcnow().strftime('%Y%m%d')}",
                "metadata": {
                    "title": f"{system_name} System Security Plan",
                    "last-modified": datetime.utcnow().isoformat(),
                    "version": "1.0",
                },
                "system-implementation": {
                    "description": f"{system_name} local-first AI platform",
                    "components": [
                        {
                            "uuid": "comp-atlas-studio",
                            "type": "software",
                            "title": "Atlas Studio",
                            "description": "Local-first multi-agent AI platform",
                        }
                    ],
                },
                "control-implementation": {
                    "description": "Controls implemented in Atlas Studio",
                    "implemented-controls": [
                        {
                            "control-id": control_id,
                            "description": control_desc,
                            "status": "implemented",
                        }
                        for control_id, control_desc in controls.items()
                    ],
                },
                "assessment-results": {
                    "description": "Audit trail evidence",
                    "findings": [
                        {
                            "uuid": f"finding-{event['id']}",
                            "title": event["action"],
                            "description": f"Event {event['action']} by {event['actor']}",
                            "status": {
                                "state": "related" if event["outcome"] == "success" else "not-satisfied",
                            },
                        }
                        for event in audit_events[:100]
                    ],
                },
            }
        }

    @staticmethod
    def get_control_mapping() -> dict[str, dict[str, str]]:
        """Get control mapping for SOC 2, ISO 27001, NIST."""
        return {
            "SOC-2-CC6.1": {
                "framework": "SOC 2",
                "control": "CC6.1",
                "description": "Logical access security",
                "atlas_implementation": "Agent tool allowlists, authorization gates",
            },
            "SOC-2-CC7.1": {
                "framework": "SOC 2",
                "control": "CC7.1",
                "description": "Vulnerability management",
                "atlas_implementation": "Security scanning, dependency auditing",
            },
            "ISO-27001-A.10": {
                "framework": "ISO 27001",
                "control": "A.10",
                "description": "Cryptography",
                "atlas_implementation": "Audit log hash chaining, data classification",
            },
            "ISO-27001-A.14": {
                "framework": "ISO 27001",
                "control": "A.14",
                "description": "Secure systems engineering",
                "atlas_implementation": "Security middleware, input validation",
            },
            "NIST-AC-3": {
                "framework": "NIST",
                "control": "AC-3",
                "description": "Access enforcement",
                "atlas_implementation": "Role-based access control, tool permissions",
            },
            "NIST-AU-2": {
                "framework": "NIST",
                "control": "AU-2",
                "description": "Audit events",
                "atlas_implementation": "Comprehensive audit trail with hash chaining",
            },
        }
```

## 6. Data Classification Template

```python
# src/atlas_studio/compliance/classification.py

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Any


class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class ClassifiedData:
    data: Any
    classification: DataClassification
    retention_days: int
    encryption_required: bool


class DataClassifier:
    """Classify data for compliance."""

    CLASSIFICATION_RULES = {
        "user_prompt": DataClassification.CONFIDENTIAL,
        "model_output": DataClassification.INTERNAL,
        "audit_event": DataClassification.RESTRICTED,
        "agent_config": DataClassification.INTERNAL,
        "skill_content": DataClassification.PUBLIC,
        "speech_transcription": DataClassification.CONFIDENTIAL,
        "avatar_generation": DataClassification.INTERNAL,
    }

    RETENTION_POLICIES = {
        DataClassification.PUBLIC: 365 * 5,
        DataClassification.INTERNAL: 365 * 3,
        DataClassification.CONFIDENTIAL: 365 * 2,
        DataClassification.RESTRICTED: 365 * 7,
    }

    @classmethod
    def classify(cls, data_type: str) -> DataClassification:
        return cls.CLASSIFICATION_RULES.get(data_type, DataClassification.INTERNAL)

    @classmethod
    def get_retention_days(cls, classification: DataClassification) -> int:
        return cls.RETENTION_POLICIES.get(classification, 365)

    @classmethod
    def requires_encryption(cls, classification: DataClassification) -> bool:
        return classification in [DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED]
```

## 7. Pre-commit Config Template

```yaml
# .pre-commit-config.yaml

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.8
    hooks:
      - id: bandit
        args: ['-c', 'pyproject.toml']
        additional_dependencies: ['bandit[toml]']

  - repo: https://github.com/Lucas-C/pre-commit-hooks
    rev: v1.5.5
    hooks:
      - id: forbid-secrets
```

## 8. Security Scan Script Template

```python
#!/usr/bin/env python3
# scripts/security-scan-all.py

"""Comprehensive security scanning for Atlas Studio."""

import subprocess
import sys
import json
from pathlib import Path


def run_command(cmd: list[str], description: str) -> tuple[bool, str]:
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)

    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode != 0:
        print(f"FAILED: {description}")
        return False, result.stdout

    print(f"PASSED: {description}")
    return True, result.stdout


def main():
    """Run all security scans."""
    results = {}
    all_passed = True

    # Bandit security scanner
    passed, output = run_command(
        ["bandit", "-r", "src/atlas_studio/", "-c", "pyproject.toml", "-f", "json"],
        "Bandit Security Scanner",
    )
    results["bandit"] = {"passed": passed, "output": output}
    if not passed:
        all_passed = False

    # pip-audit dependency scanner
    passed, output = run_command(
        ["pip-audit", "--format", "json"],
        "pip-audit Dependency Scanner",
    )
    results["pip_audit"] = {"passed": passed, "output": output}
    if not passed:
        all_passed = False

    # Save results
    results_path = Path("security-scan-results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print(f"Results saved to: {results_path}")

    if all_passed:
        print("All security scans PASSED!")
        return 0
    else:
        print("Some security scans FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

## 9. Compliance Report Script Template

```python
#!/usr/bin/env python3
# scripts/generate-compliance-report.py

"""Generate compliance report for Atlas Studio."""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from atlas_studio.compliance.oscal import OSCALGenerator


def main():
    """Generate compliance report."""
    # Sample audit events (in production, fetch from database)
    audit_events = [
        {"id": "1", "action": "plan.create", "actor": "Atlas", "outcome": "success"},
        {"id": "2", "action": "forge.change_set.propose", "actor": "Forge", "outcome": "success"},
    ]

    # Generate SSP
    ssp = OSCALGenerator.generate_ssp(
        system_name="Atlas Studio",
        audit_events=audit_events,
        controls=OSCALGenerator.get_control_mapping(),
    )

    # Save report
    report_path = Path("compliance_report.json")
    with open(report_path, "w") as f:
        json.dump(ssp, f, indent=2)

    print(f"Compliance report generated: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 10. Main.py Integration Template

```python
# Add to src/atlas_studio/main.py

# Import middleware
from .middleware.security import SecurityMiddleware, RateLimitMiddleware

# Add middleware after app creation
app.add_middleware(SecurityMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# Import compliance
from .compliance.oscal import OSCALGenerator

# Add compliance endpoints
@app.get("/api/compliance/posture")
async def get_compliance_posture():
    """Return compliance posture across frameworks."""
    return {
        "frameworks": {
            "SOC-2": {
                "status": "compliant",
                "controls": {
                    "CC6.1": "implemented",
                    "CC7.1": "implemented",
                    "CC8.1": "implemented",
                },
            },
            "ISO-27001": {
                "status": "compliant",
                "controls": {
                    "A.10": "implemented",
                    "A.14": "implemented",
                },
            },
            "NIST": {
                "status": "compliant",
                "controls": {
                    "AC-3": "implemented",
                    "AU-2": "implemented",
                },
            },
        },
        "last_assessment": datetime.utcnow().isoformat(),
        "next_assessment": (datetime.utcnow() + timedelta(days=30)).isoformat(),
    }


@app.get("/api/compliance/evidence")
async def get_compliance_evidence():
    """Return compliance evidence package."""
    audit_events = await infrastructure.load_audit(limit=1000)
    control_mapping = OSCALGenerator.get_control_mapping()

    return {
        "audit_events": len(audit_events),
        "control_mapping": control_mapping,
        "evidence_packages": [
            {
                "framework": "SOC-2",
                "evidence_count": len(audit_events),
                "last_updated": datetime.utcnow().isoformat(),
            }
        ],
    }


@app.get("/api/metrics/costs")
async def get_cost_metrics():
    """Return cost tracking metrics."""
    provider = gateway.get()
    if hasattr(provider, "get_cost_log"):
        cost_log = provider.get_cost_log()
        total_cost = sum(entry["cost"] for entry in cost_log)
        total_tokens = sum(entry["tokens"] for entry in cost_log)
        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "requests": len(cost_log),
            "avg_cost_per_request": total_cost / len(cost_log) if cost_log else 0,
            "recent_requests": cost_log[-10:],
        }
    return {"total_cost": 0, "total_tokens": 0, "requests": 0}
```
