---
name: datacore-data
description: |
  Manage data engineering using open-source trusted sources only.
  USE WHEN user says:
  - "Database design..."
  - "Data migration..."
  - "SQL query..."
  - "Data model..."
  - "Backup strategy..."
  - Any data engineering or database request.
---

# Workflow Routing (SYSTEM PROMPT)

Route data work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| Data modeling | This skill (datacore-data) | Design data model |
| Data migration | This skill (datacore-data) | Plan and execute migration |
| Data for implementation | development-lifecycle | Delegate to lifecycle |
| Data for compliance | manage-atlas-platform | Delegate to platform management |

---

# When to Activate This Skill

Activate this skill when:
1. User requests data modeling or design.
2. User needs data migration or transformation.
3. User asks for database optimization or queries.
4. User needs backup or recovery strategies.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for platform management (use manage-atlas-platform).

---

# DataCore Data Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI data handling guidelines (openai.com)
- Government data protection standards (NIST, ISO, GDPR, CCPA)
- Official database standards (SQL, NoSQL, NewSQL)
- Published compliance requirements for data (SOC 2, ISO 27001, NIST CSF, HIPAA)
- Official standards bodies (IEEE, W3C, IETF)
- Open-source database systems (PostgreSQL, MySQL, SQLite, MongoDB)
- Open-source data tools (dbt, Airflow, Great Expectations)

**NEVER use:**
- Unverified data practices from social media
- Paid data tools or services
- Anonymous or unattributed data standards
- Any source requiring payment

## Data Procedure

1. **Data Model:** Design data model and schema.
2. **Migration Plan:** Plan data migration strategy.
3. **Backup Check:** Verify backup and recovery procedures.
4. **Migration Test:** Test migration in non-production.
5. **Approval:** Get approval for production migration.
6. **Execute:** Execute migration with rollback plan.
7. **Integrity Verify:** Verify data integrity post-migration.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: Data request
- INTERPRETATION: Data scope and requirements
- EVIDENCE: Data standards and sources
- ACTION_TAKEN: Data operation performed
- VERIFICATION: Data integrity verified
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** Data operation summary with integrity status.

## Cross-Skill Delegation

When delegating to another skill:
1. Include the data request.
2. Include data model and migration plan.
3. State data integrity and backup requirements.
