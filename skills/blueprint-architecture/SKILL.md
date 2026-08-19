---
name: blueprint-architecture
description: |
  Create architecture blueprints using open-source trusted sources only.
  USE WHEN user says:
  - "Design the architecture..."
  - "Create a blueprint..."
  - "Plan the system design..."
  - "Architecture review..."
  - Any architecture or system design request.
---

# Workflow Routing (SYSTEM PROMPT)

Route architecture work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| Architecture design | This skill (blueprint-architecture) | Create architecture blueprint |
| Architecture for implementation | development-lifecycle | Delegate to lifecycle |
| Architecture for compliance | manage-atlas-platform | Delegate to platform management |

---

# When to Activate This Skill

Activate this skill when:
1. User requests architecture design or review.
2. User needs system design or blueprints.
3. User asks for architectural patterns or best practices.
4. User needs data flow or component diagrams.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for platform management (use manage-atlas-platform).

---

# Blueprint Architecture Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI architecture guidelines (openai.com)
- Government architecture standards (NIST, ISO, IEEE)
- Official cloud provider reference architectures (AWS, Azure, GCP)
- Published compliance frameworks (SOC 2, ISO 27001, NIST CSF)
- Official standards bodies (IEEE, W3C, IETF)
- Open-source architecture tools (Draw.io, Mermaid, PlantUML)
- Open-source reference architectures (CNCF, cloud-provider open samples)

**NEVER use:**
- Unverified architecture blogs from social media
- Paid architecture frameworks or tools
- Anonymous or unattributed architecture patterns
- Any source requiring payment

## Architecture Procedure

1. **Constraints:** Identify constraints and requirements.
2. **Current State:** Document current architecture.
3. **Options:** Generate architecture options.
4. **Selection:** Select best option based on requirements.
5. **Documentation:** Create architecture documentation.
6. **Risk Review:** Identify and mitigate architectural risks.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: Architecture request
- INTERPRETATION: Architecture scope and constraints
- EVIDENCE: Architecture patterns and sources
- ACTION_TAKEN: Architecture designed
- VERIFICATION: Architecture review completed
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** Architecture summary with diagrams.

## Cross-Skill Delegation

When delegating to another skill:
1. Include the architecture request.
2. Include architecture constraints and requirements.
3. State architectural decisions and rationale.
