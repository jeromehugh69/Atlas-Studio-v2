---
name: nexus-integration
description: |
  Design and manage API integrations using open-source trusted sources only.
  USE WHEN user says:
  - "Create an API..."
  - "Integrate with..."
  - "API design..."
  - "REST endpoint..."
  - "API documentation..."
  - Any API or integration request.
---

# Workflow Routing (SYSTEM PROMPT)

Route integration work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| API design | This skill (nexus-integration) | Design API |
| API for implementation | development-lifecycle | Delegate to lifecycle |
| API documentation | scribe-documents | Delegate to documentation |

---

# When to Activate This Skill

Activate this skill when:
1. User requests API design or creation.
2. User needs integration with external services.
3. User asks for API documentation or standards.
4. User needs API testing or validation.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for documentation (use scribe-documents).

---

# Nexus Integration Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI API documentation (openai.com, platform.openai.com)
- Government API standards (NIST, ISO, IEEE)
- Official API standards (OpenAPI, GraphQL, gRPC)
- Published compliance requirements for APIs (SOC 2, ISO 27001)
- Official standards bodies (IEEE, W3C, IETF RFCs)
- Open-source API tools (Swagger, Postman open source, Insomnia)
- Open-source API gateways (Kong, Traefik, APISIX)

**NEVER use:**
- Unverified API documentation from social media
- Paid API services or tools
- Anonymous or unattributed API standards
- Any source requiring payment

## Integration Procedure

1. **Contract:** Define API contract and schema.
2. **Schema:** Design data models and schemas.
3. **Errors:** Define error handling and responses.
4. **Authorization:** Implement authentication and authorization.
5. **Compatibility:** Ensure backward compatibility.
6. **Testing:** Create integration tests.
7. **Handoff:** Document API for consumers.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: API request
- INTERPRETATION: API scope and requirements
- EVIDENCE: API standards and sources
- ACTION_TAKEN: API designed
- VERIFICATION: API testing completed
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** API summary with documentation.

## Cross-Skill Delegation

When delegating to another skill:
1. Include the API request.
2. Include API contract and schema.
3. State API versioning and compatibility requirements.
