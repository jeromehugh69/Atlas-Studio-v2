# Compliance SDK Integration Plan

## Overview

Implement layer-by-layer compliance using open-source tools for SOC 2, ISO 27001, and NIST CSF frameworks.

## Current State

**Existing Compliance Features:**
- Audit trail with 30+ event types
- Agent tool permissions and authorization gates
- Security posture reporting
- Approval system with HMAC-based tokens

**Gaps:**
- No security headers middleware
- No rate limiting
- No audit log integrity (hash chaining)
- No data classification
- No data encryption at rest for SQLite
- No compliance evidence packaging
- No OSCAL documentation
- No compliance API endpoints (required, not optional)

## Target State

**Compliance Layers:**

| Layer | Tool | Status |
|-------|------|--------|
| UI & Frontend | Security headers middleware | Planned |
| API & Gateway | Rate limiting | Planned |
| Core Orchestration | Audit hash chaining | Planned |
| Database | Data classification | Planned |
| CI/CD | Pre-commit hooks | Planned |
| GRC | OSCAL compliance | Planned |

## Implementation Steps

### Step 1: Security Middleware
Create `src/atlas_studio/middleware/security.py`:
```python
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests=100, window_seconds=60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    async def dispatch(self, request: Request, call_next):
        # Rate limiting logic
        return await call_next(request)
```

### Step 2: Audit Hash Chaining
Update `src/atlas_studio/models.py`:
```python
class AuditEvent(BaseModel):
    # ... existing fields
    previous_hash: str = ""
    current_hash: str = ""
    
    def compute_hash(self) -> str:
        data = f"{self.action}{self.actor}{self.target}{self.outcome}{self.created_at}{self.previous_hash}"
        return hashlib.sha256(data.encode()).hexdigest()
```

### Step 3: Data Classification
Create `src/atlas_studio/compliance/classification.py`:
```python
class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

class DataClassifier:
    CLASSIFICATION_RULES = {
        "user_prompt": DataClassification.CONFIDENTIAL,
        "model_output": DataClassification.INTERNAL,
        "audit_event": DataClassification.RESTRICTED,
    }
```

### Step 4: SQLite Encryption at Rest
Add encryption to `src/atlas_studio/infrastructure.py`:
```python
import hashlib
from cryptography.fernet import Fernet

class SQLiteEncryption:
    """Encrypt sensitive data before writing to SQLite."""
    
    def __init__(self, key: str | None = None):
        if key:
            self._key = hashlib.sha256(key.encode()).digest()
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
        import json
        return self.encrypt(json.dumps(data))
    
    def decrypt_dict(self, encrypted_data: str) -> dict:
        """Decrypt to dictionary."""
        import json
        return json.loads(self.decrypt(encrypted_data))

# Update SQLiteBackend to use encryption
class SQLiteBackend:
    def __init__(self, db_path: str, encryption_key: str | None = None):
        self.db_path = db_path
        self.encryption = SQLiteEncryption(encryption_key) if encryption_key else None
    
    async def persist_audit(self, event: AuditEvent):
        # Encrypt sensitive fields before storage
        details = event.details
        if self.encryption and self._requires_encryption(event.action):
            details = {"encrypted": self.encryption.encrypt_dict(details)}
        
        # Store with encryption
        ...
    
    def _requires_encryption(self, action: str) -> bool:
        """Check if action requires encryption."""
        sensitive_actions = [
            "user_prompt", "model_output", "speech.transcribe",
            "speech.synthesize", "avatar.generate"
        ]
        return any(s in action for s in sensitive_actions)
```

Add to configuration:
```python
# In config.py
sqlite_encryption_key: str = ""  # Empty = no encryption, set key to enable
```

Add to `.env.standalone`:
```bash
# SQLite encryption (optional, but recommended for compliance)
ATLAS_STUDIO_SQLITE_ENCRYPTION_KEY=your-secret-key-here
```

### Step 4: Pre-commit Hooks
Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.8
    hooks:
      - id: bandit
        args: ['-c', 'pyproject.toml']
```

### Step 5: OSCAL Compliance
Create `src/atlas_studio/compliance/oscal.py`:
```python
class OSCALGenerator:
    @staticmethod
    def generate_ssp(system_name, audit_events, controls):
        return {
            "system-security-plan": {
                "metadata": {"title": f"{system_name} SSP"},
                "control-implementation": {
                    "implemented-controls": [
                        {"control-id": k, "description": v}
                        for k, v in controls.items()
                    ]
                }
            }
        }
```

### Step 6: Compliance API Endpoints
Add to `src/atlas_studio/main.py`:
```python
@app.get("/api/compliance/posture")
async def get_compliance_posture():
    return {
        "frameworks": {
            "SOC-2": {"status": "compliant"},
            "ISO-27001": {"status": "compliant"},
            "NIST": {"status": "compliant"},
        }
    }
```

## Files to Create/Modify

| File | Changes |
|------|---------|
| `src/atlas_studio/middleware/__init__.py` | Create |
| `src/atlas_studio/middleware/security.py` | Create |
| `src/atlas_studio/models.py` | Add hash chaining fields |
| `src/atlas_studio/infrastructure.py` | Update audit persistence + add SQLite encryption |
| `src/atlas_studio/config.py` | Add `sqlite_encryption_key` setting |
| `src/atlas_studio/compliance/__init__.py` | Create |
| `src/atlas_studio/compliance/classification.py` | Create |
| `src/atlas_studio/compliance/oscal.py` | Create |
| `src/atlas_studio/main.py` | Add middleware and endpoints |
| `.pre-commit-config.yaml` | Create |
| `.env.standalone` | Add encryption key |
| `scripts/security-scan-all.py` | Create |

## Testing

1. Verify security headers on all responses
2. Test rate limiting blocks excessive requests
3. Verify audit log has hash chaining
4. Test data classification works
5. Verify SQLite encryption at rest works
6. Test pre-commit hooks run security scans
7. Verify OSCAL SSP generation works
8. Verify compliance API endpoints return correct data
9. Verify all existing tests pass

## Rollback

1. Remove middleware from `main.py`
2. Remove compliance module
3. Remove pre-commit hooks

## Success Criteria

- [ ] Security headers on all responses
- [ ] Rate limiting prevents abuse
- [ ] Audit log has hash chaining
- [ ] Data classification defined
- [ ] SQLite encryption at rest enabled
- [ ] Pre-commit hooks run security scans
- [ ] OSCAL SSP generation works
- [ ] Compliance API endpoints functional (not optional)
- [ ] All existing tests pass
