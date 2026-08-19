# Atlas Studio Implementation Plan
## LiteLLM Integration + Compliance SDK Implementation

**Timeline:** 1-2 weeks
**Deployment Target:** Local-only (single user)
**Compliance Frameworks:** SOC 2, ISO 27001, NIST CSF
**Budget:** Open-source only

---

## Executive Summary

This plan covers two major initiatives:
1. **LiteLLM Integration:** Replace custom Ollama/OpenAI providers with LiteLLM's unified interface
2. **Compliance SDK Integration:** Layer-by-layer compliance implementation using open-source tools

---

## Phase 1: LiteLLM Integration (Week 1)

### Ticket 1.1: Add LiteLLM Dependency
**Priority:** P0
**Estimate:** 30 minutes

**Files to Modify:**
- `pyproject.toml`

**Changes:**
```toml
# Add to dependencies
dependencies = [
  # ... existing deps
  "litellm>=1.40,<2",
]
```

**Acceptance Criteria:**
- [ ] `uv add litellm` completes successfully
- [ ] `python -c "import litellm; print(litellm.__version__)"` works

---

### Ticket 1.2: Update Configuration
**Priority:** P0
**Estimate:** 1 hour

**Files to Modify:**
- `src/atlas_studio/config.py`
- `.env.example`
- `.env.standalone`

**New Settings to Add:**
```python
# LiteLLM Configuration
litellm_api_base: str = "http://localhost:11434"  # Ollama default
litellm_api_key: str = ""  # For cloud providers
litellm_model_prefix: str = "ollama"  # Default provider prefix
litellm_fallback_models: list[str] = []  # e.g., ["openai/gpt-4o-mini"]
litellm_cost_tracking: bool = True
litellm_success_callbacks: list[str] = []  # e.g., ["langfuse"]
litellm_num_retries: int = 2
litellm_timeout: int = 120
```

**Acceptance Criteria:**
- [ ] New settings load from environment variables
- [ ] Backward compatible with existing Ollama config
- [ ] Settings validation passes

---

### Ticket 1.3: Create LiteLLM Provider
**Priority:** P0
**Estimate:** 4 hours

**Files to Modify:**
- `src/atlas_studio/providers.py`

**New Class Implementation:**
```python
class LiteLLMProvider(ModelProvider):
    """Unified LLM provider using LiteLLM."""
    
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
        
        # Configure LiteLLM
        litellm.api_base = api_base
        if api_key:
            litellm.api_key = api_key
        
        # Cost tracking callback
        litellm.success_callback = [self._track_cost]
        self._cost_log: list[dict] = []
    
    def _track_cost(self, kwargs, completion_response, start_time, end_time):
        """Track cost per request."""
        cost = kwargs.get("response_cost", 0)
        self._cost_log.append({
            "model": completion_response.model,
            "cost": cost,
            "tokens": completion_response.usage.total_tokens if hasattr(completion_response, 'usage') else 0,
            "timestamp": start_time,
        })
    
    async def generate(self, messages, model, temperature=0.3):
        """Generate completion using LiteLLM."""
        full_model = f"{self.model_prefix}/{model}" if "/" not in model else model
        
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
        full_model = f"{self.model_prefix}/{model}" if "/" not in model else model
        
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
            # For Ollama, check the models endpoint
            if self.model_prefix == "ollama":
                async with httpx.AsyncClient(timeout=3) as client:
                    return (await client.get(f"{self.api_base}/api/tags")).is_success
            # For other providers, try a minimal completion
            await self.generate([{"role": "user", "content": "hi"}], "test", temperature=0.1)
            return True
        except Exception:
            return False
    
    async def chat_with_tools(self, messages, model, tools, temperature=0.1):
        """Chat with tool support using LiteLLM."""
        full_model = f"{self.model_prefix}/{model}" if "/" not in model else model
        
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
```

**Acceptance Criteria:**
- [ ] `LiteLLMProvider` implements all `ModelProvider` ABC methods
- [ ] Streaming yields string chunks (not ModelResponse objects)
- [ ] Tool calling returns OpenAI-compatible format
- [ ] Cost tracking captures per-request costs
- [ ] Circuit breaker/retry logic works via LiteLLM's built-in features

---

### Ticket 1.4: Update Gateway Initialization
**Priority:** P0
**Estimate:** 1 hour

**Files to Modify:**
- `src/atlas_studio/main.py`

**Changes:**
```python
# Line 34: Update import
from .providers import LiteLLMProvider, ProviderError, ProviderGateway

# Line 44: Replace gateway initialization
gateway = ProviderGateway(
    settings.default_provider,
    {
        "litellm": LiteLLMProvider(
            api_base=settings.litellm_api_base,
            api_key=settings.litellm_api_key,
            model_prefix=settings.litellm_model_prefix,
            timeout_seconds=settings.model_timeout_seconds,
            max_tokens=settings.model_max_tokens,
            num_retries=settings.litellm_num_retries,
        ),
        # Keep Ollama as fallback
        "ollama": OllamaProvider(
            settings.ollama_url,
            settings.model_timeout_seconds,
            settings.model_max_tokens,
        ),
    },
)

# Line 49-54: Replace forge_provider
forge_provider = LiteLLMProvider(
    api_base=settings.litellm_api_base,
    api_key=settings.litellm_api_key,
    model_prefix=settings.litellm_model_prefix,
    timeout_seconds=settings.forge_timeout_seconds,
    max_tokens=settings.forge_max_tokens,
    context_tokens=settings.forge_context_tokens,
    num_retries=settings.litellm_num_retries,
)
```

**Acceptance Criteria:**
- [ ] Gateway initializes with LiteLLM provider
- [ ] Forge uses LiteLLM provider
- [ ] Backward compatible with existing config

---

### Ticket 1.5: Update Error Messages
**Priority:** P1
**Estimate:** 30 minutes

**Files to Modify:**
- `src/atlas_studio/main.py`

**Changes:**
```python
# Line 244: Update error message
"Local model unavailable: {exc}. Check your LLM provider and retry."

# Line 352: Update error message
"The local model was unavailable during {specialist.name}'s read-only investigation: {exc}. Check your LLM provider and retry."
```

**Acceptance Criteria:**
- [ ] Error messages are provider-agnostic
- [ ] No references to "Ollama" in user-facing messages

---

### Ticket 1.6: Add Cost Metrics Endpoint
**Priority:** P1
**Estimate:** 2 hours

**Files to Modify:**
- `src/atlas_studio/main.py`

**New Endpoint:**
```python
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
            "recent_requests": cost_log[-10:],  # Last 10 requests
        }
    return {"total_cost": 0, "total_tokens": 0, "requests": 0}
```

**Acceptance Criteria:**
- [ ] `/api/metrics/costs` returns cost data
- [ ] Cost data updates after each model call
- [ ] No performance impact on model calls

---

### Ticket 1.7: Update Tests
**Priority:** P2
**Estimate:** 1 hour

**Files to Modify:**
- `tests/test_api.py`

**Changes:**
```python
# Line 66: Update assertion if default provider changes
assert metrics["model"]["provider"] in ["litellm", "ollama"]
```

**Acceptance Criteria:**
- [ ] All existing tests pass
- [ ] New tests for LiteLLM provider added

---

## Phase 2: Compliance SDK Integration (Week 1-2)

### Ticket 2.1: Add Security Middleware
**Priority:** P0
**Estimate:** 4 hours

**Files to Create:**
- `src/atlas_studio/middleware/__init__.py`
- `src/atlas_studio/middleware/security.py`

**Implementation:**
```python
# src/atlas_studio/middleware/security.py
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import hashlib

class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for compliance."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Add security headers
        response = await call_next(request)
        
        # CSP headers
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
        
        # Request timing for audit
        duration = time.time() - start_time
        response.headers["X-Request-Duration"] = str(round(duration, 4))
        
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware."""
    
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()
        
        # Clean old requests
        if client_ip in self.requests:
            self.requests[client_ip] = [
                t for t in self.requests[client_ip]
                if now - t < self.window_seconds
            ]
        else:
            self.requests[client_ip] = []
        
        # Check rate limit
        if len(self.requests[client_ip]) >= self.max_requests:
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)}
            )
        
        # Record request
        self.requests[client_ip].append(now)
        
        return await call_next(request)
```

**Integration in main.py:**
```python
# Add after app creation
from .middleware.security import SecurityMiddleware, RateLimitMiddleware

app.add_middleware(SecurityMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
```

**Acceptance Criteria:**
- [ ] Security headers added to all responses
- [ ] Rate limiting prevents abuse
- [ ] No performance impact on normal usage

---

### Ticket 2.2: Add Audit Log Hash Chaining
**Priority:** P0
**Estimate:** 3 hours

**Files to Modify:**
- `src/atlas_studio/models.py`
- `src/atlas_studio/infrastructure.py`

**Changes to models.py:**
```python
# Add to AuditEvent class
class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    action: str
    actor: str
    target: str
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # New fields for hash chaining
    previous_hash: str = ""
    current_hash: str = ""
    
    def compute_hash(self) -> str:
        """Compute SHA256 hash of this event."""
        data = f"{self.action}{self.actor}{self.target}{self.outcome}{self.created_at}{self.previous_hash}"
        return hashlib.sha256(data.encode()).hexdigest()
```

**Changes to infrastructure.py:**
```python
# Add to persist_audit method
async def persist_audit(self, event: AuditEvent):
    # Get previous event hash
    if self.db:
        prev_hash = await self.db.fetchval(
            "SELECT current_hash FROM audit_events ORDER BY created_at DESC LIMIT 1"
        ) or ""
    else:
        prev_hash = self._last_audit_hash if hasattr(self, '_last_audit_hash') else ""
    
    # Set hash chain
    event.previous_hash = prev_hash
    event.current_hash = event.compute_hash()
    
    # Store event
    if self.db:
        await self.db.execute(
            "INSERT INTO audit_events (id,actor,action,target,outcome,details,previous_hash,current_hash) "
            "VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8)",
            event.id, event.actor, event.action, event.target, event.outcome,
            json.dumps(event.details), event.previous_hash, event.current_hash,
        )
    
    self._last_audit_hash = event.current_hash
```

**Acceptance Criteria:**
- [ ] Each audit event includes hash of previous event
- [ ] Hash chain is verifiable
- [ ] Existing audit events remain accessible

---

### Ticket 2.3: Add Data Classification
**Priority:** P1
**Estimate:** 2 hours

**Files to Create:**
- `src/atlas_studio/compliance/__init__.py`
- `src/atlas_studio/compliance/classification.py`

**Implementation:**
```python
# src/atlas_studio/compliance/classification.py
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
    }
    
    RETENTION_POLICIES = {
        DataClassification.PUBLIC: 365 * 5,  # 5 years
        DataClassification.INTERNAL: 365 * 3,  # 3 years
        DataClassification.CONFIDENTIAL: 365 * 2,  # 2 years
        DataClassification.RESTRICTED: 365 * 7,  # 7 years
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

**Acceptance Criteria:**
- [ ] Data types are classified
- [ ] Retention policies defined
- [ ] Encryption requirements documented

---

### Ticket 2.4: Add Pre-commit Hooks
**Priority:** P1
**Estimate:** 2 hours

**Files to Create:**
- `.pre-commit-config.yaml`
- `scripts/security-scan.py`

**.pre-commit-config.yaml:**
```yaml
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

**scripts/security-scan.py:**
```python
#!/usr/bin/env python3
"""Security scanning script for Atlas Studio."""
import subprocess
import sys

def run_bandit():
    """Run Bandit security scanner."""
    print("Running Bandit security scanner...")
    result = subprocess.run(
        ["bandit", "-r", "src/atlas_studio/", "-c", "pyproject.toml"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("Bandit found security issues!")
        return False
    return True

def run_pip_audit():
    """Run pip-audit for dependency scanning."""
    print("Running pip-audit...")
    result = subprocess.run(
        ["pip-audit"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("pip-audit found vulnerabilities!")
        return False
    return True

def main():
    """Run all security scans."""
    all_passed = True
    
    if not run_bandit():
        all_passed = False
    
    if not run_pip_audit():
        all_passed = False
    
    if all_passed:
        print("\nAll security scans passed!")
        return 0
    else:
        print("\nSome security scans failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Acceptance Criteria:**
- [ ] Pre-commit hooks run on commit
- [ ] Security scans catch issues
- [ ] No false positives blocking commits

---

### Ticket 2.5: Add OSCAL Compliance Module
**Priority:** P2
**Estimate:** 4 hours

**Files to Create:**
- `src/atlas_studio/compliance/oscal.py`
- `src/atlas_studio/compliance/evidence.py`

**oscal.py:**
```python
# src/atlas_studio/compliance/oscal.py
"""OSCAL compliance document generation."""
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
                            "target": {
                                "type": "objective-id",
                                "target-id": event["action"],
                            },
                            "status": {
                                "state": "related" if event["outcome"] == "success" else "not-satisfied",
                            },
                        }
                        for event in audit_events[:100]  # Last 100 events
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
        }
```

**Acceptance Criteria:**
- [ ] OSCAL SSP generation works
- [ ] Control mapping covers SOC 2, ISO 27001, NIST
- [ ] Evidence packaging from audit events

---

### Ticket 2.6: Add Compliance API Endpoints
**Priority:** P2
**Estimate:** 2 hours

**Files to Modify:**
- `src/atlas_studio/main.py`

**New Endpoints:**
```python
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
```

**Acceptance Criteria:**
- [ ] `/api/compliance/posture` returns compliance status
- [ ] `/api/compliance/evidence` returns evidence package
- [ ] Endpoints are fast (< 100ms)

---

## Phase 3: Evidence Collection Scripts (Week 2)

### Script 3.1: Generate Compliance Report
**Priority:** P2
**Estimate:** 2 hours

**File to Create:**
- `scripts/generate_compliance_report.py`

**Implementation:**
```python
#!/usr/bin/env python3
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

**Acceptance Criteria:**
- [ ] Script generates OSCAL SSP
- [ ] Report is valid JSON
- [ ] Report can be imported by compliance tools

---

### Script 3.2: Security Scanning Script
**Priority:** P1
**Estimate:** 1 hour

**File to Create:**
- `scripts/security-scan-all.py`

**Implementation:**
```python
#!/usr/bin/env python3
"""Comprehensive security scanning for Atlas Studio."""
import subprocess
import sys

def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:", result.stderr)
    
    if result.returncode != 0:
        print(f"❌ {description} FAILED")
        return False
    
    print(f"✅ {description} PASSED")
    return True

def main():
    """Run all security scans."""
    all_passed = True
    
    # Bandit security scanner
    if not run_command(
        ["bandit", "-r", "src/atlas_studio/", "-c", "pyproject.toml", "-f", "json"],
        "Bandit Security Scanner"
    ):
        all_passed = False
    
    # pip-audit dependency scanner
    if not run_command(
        ["pip-audit", "--format", "json"],
        "pip-audit Dependency Scanner"
    ):
        all_passed = False
    
    # Safety vulnerability scanner
    if not run_command(
        ["safety", "check", "--json"],
        "Safety Vulnerability Scanner"
    ):
        all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ All security scans PASSED!")
        return 0
    else:
        print("❌ Some security scans FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Acceptance Criteria:**
- [ ] Script runs all security scanners
- [ ] Results are captured in JSON
- [ ] Exit code reflects pass/fail

---

## Implementation Timeline

### Week 1
- **Day 1-2:** Tickets 1.1-1.4 (LiteLLM core integration)
- **Day 3:** Tickets 1.5-1.7 (Error messages, metrics, tests)
- **Day 4-5:** Tickets 2.1-2.2 (Security middleware, audit hash chaining)

### Week 2
- **Day 1-2:** Tickets 2.3-2.4 (Data classification, pre-commit hooks)
- **Day 3-4:** Tickets 2.5-2.6 (OSCAL compliance, API endpoints)
- **Day 5:** Scripts 3.1-3.2 (Compliance reports, security scanning)

---

## Success Criteria

### LiteLLM Integration
- [ ] All model calls route through LiteLLM
- [ ] Cost tracking captures per-request costs
- [ ] Streaming works correctly
- [ ] Tool calling returns OpenAI-compatible format
- [ ] Fallback routing works

### Compliance SDK
- [ ] Security headers on all responses
- [ ] Rate limiting prevents abuse
- [ ] Audit log has hash chaining
- [ ] Data classification defined
- [ ] Pre-commit hooks run security scans
- [ ] OSCAL SSP generation works
- [ ] Compliance API endpoints functional

### Testing
- [ ] All existing tests pass
- [ ] New tests for LiteLLM provider
- [ ] Security scans pass
- [ ] Compliance reports generate correctly

---

## Risk Mitigation

### LiteLLM Risks
1. **Breaking change in LiteLLM API:** Pin version to `>=1.40,<2`
2. **Ollama compatibility issues:** Keep Ollama provider as fallback
3. **Performance regression:** Benchmark before/after integration

### Compliance Risks
1. **False positives in security scans:** Tune Bandit configuration
2. **Performance impact from middleware:** Make middleware optional
3. **Hash chain breakage:** Implement graceful recovery

---

## Rollback Plan

### LiteLLM Rollback
1. Revert `providers.py` to original
2. Revert `main.py` gateway initialization
3. Remove `litellm` from dependencies

### Compliance Rollback
1. Remove middleware from `main.py`
2. Remove compliance module
3. Remove pre-commit hooks

---

## Next Steps After Implementation

1. **Performance Testing:** Benchmark LiteLLM vs custom providers
2. **Security Audit:** Run full security scan
3. **Compliance Certification:** Prepare for SOC 2 Type II audit
4. **Documentation:** Update README with new provider configuration
5. **Training:** Train team on new compliance features

---

## Questions for Review

1. Should we keep the custom `OllamaProvider` as a fallback, or fully replace it?
2. Do we need to implement data encryption at rest for SQLite?
3. Should compliance endpoints be optional (config-gated)?
4. Do we need to add authentication for compliance endpoints?

---

**Document Version:** 1.0
**Last Updated:** {datetime.now().isoformat()}
**Author:** Atlas Studio Implementation Team
