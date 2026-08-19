# Compliance Controls Mapping

## Overview

Atlas Studio implements compliance controls for SOC 2 Type 2, ISO 27001, and NIST CSF frameworks. All platform changes must go through the necessary agents to satisfy these compliance requirements.

## Mandatory Compliance Workflow

```
User Request → Atlas (Intake) → Forge (Plan) → User (Authorize) → Forge (Implement)
    ↓
Review Stage (MANDATORY):
    ├── Quanta (Quality Verification)
    ├── Sentinel (Security Review) ← MANDATORY
    └── Verity (Compliance Review) ← MANDATORY
    ↓
Verify → Release (Promote) → Production
```

## Agent Responsibilities

### Sentinel (Security Engineering)
- **Role:** Threat modeling and security review
- **Required for:** All platform changes before production promotion
- **Evidence collected:** Security scans, threat assessments, vulnerability reports
- **Controls verified:** CC6.1, CC6.2, A.14.2.5, PR.AC-1, PR.AC-4

### Verity (GRC and Compliance)
- **Role:** Governance, risk, and compliance review
- **Required for:** All platform changes before production promotion
- **Evidence collected:** Control mappings, compliance assessments, audit trails
- **Controls verified:** CC7.2, CC7.3, CC8.1, A.12.1.4, A.12.4.1, PR.DS-1, DE.CM-1, DE.AE-2

## SOC 2 Type 2 Controls

| Control | Name | Atlas Implementation | Agent |
|---------|------|---------------------|-------|
| CC6.1 | Logical Access Security | Agent tool permissions, authorization gates | Sentinel |
| CC6.2 | Access Authentication | HMAC-based approval challenges, one-time codes | Sentinel |
| CC7.2 | Monitoring | Audit trail with 30+ event types, security scans | Sentinel, Verity |
| CC7.3 | Incident Response | Security posture reporting, threat detection | Sentinel |
| CC8.1 | Change Management | 9-stage lifecycle, approval gates, evidence collection | Verity |

## ISO 27001 Controls

| Control | Name | Atlas Implementation | Agent |
|---------|------|---------------------|-------|
| A.9.2.1 | User Registration/Authorization | Approval challenges, user authorization | Sentinel |
| A.12.1.4 | Control of Operational Software | Change sets, approvals, lifecycle stages | Verity |
| A.12.4.1 | Event Logging | Audit trail with hash chaining | Verity |
| A.14.2.5 | Secure System Engineering | Security scans, agent permissions, sandbox config | Sentinel |

## NIST CSF Controls

| Control | Name | Atlas Implementation | Agent |
|---------|------|---------------------|-------|
| PR.DS-1 | Data-at-rest Protection | SQLite encryption, data classification | Verity |
| PR.AC-1 | Identity Management | Approval challenges, user authorization | Sentinel |
| PR.AC-4 | Access Permissions | Agent permissions, approval tokens | Sentinel |
| DE.CM-1 | Network Monitoring | Security scans, system health | Sentinel |
| DE.AE-2 | Anomaly Analysis | Audit events, security scans | Sentinel, Verity |
| RS.AN-1 | Incident Investigation | Audit events, incident reports | Sentinel |
| RC.RP-1 | Recovery Plan Execution | Lifecycle stages, deployment records | Verity |

## Compliance API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/compliance/posture` | Current compliance posture across all frameworks |
| `GET /api/compliance/evidence?framework=SOC-2` | Evidence package for specified framework |
| `GET /api/compliance/ssp` | System Security Plan (OSCAL format) |
| `GET /api/compliance/classification/{action}` | Data classification for action |
| `GET /api/compliance/controls` | List all compliance controls |

## Evidence Collection

Evidence is collected automatically during the lifecycle:

1. **Audit Events:** Every action logged with hash chaining
2. **Change Sets:** File changes with SHA-256 hashes
3. **Approvals:** One-time approval tokens with HMAC verification
4. **Security Scans:** Sentinel security assessments
5. **Test Results:** Quanta quality verification
6. **Lifecycle Stages:** Stage transitions with evidence

## Data Classification

| Classification | Retention | Examples |
|---------------|-----------|----------|
| PUBLIC | 90 days | Public documentation |
| INTERNAL | 365 days | Model outputs, test results |
| CONFIDENTIAL | 730 days | User prompts, change sets, agent requests |
| RESTRICTED | 2555 days | Audit events, approval tokens, API keys |

## Audit Hash Chaining

All audit events are linked via SHA-256 hash chaining:
- Each event includes `previous_hash` and `current_hash`
- Tampering with any event breaks the chain
- Provides tamper-evident audit trail for compliance
