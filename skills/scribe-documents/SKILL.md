---
name: scribe-documents
description: |
  Create and manage documentation using open-source trusted sources only.
  USE WHEN user says:
  - "Write documentation..."
  - "Create a guide..."
  - "Update the docs..."
  - "Document this feature..."
  - "Write a README..."
  - Any documentation creation or update request.
---

# Workflow Routing (SYSTEM PROMPT)

Route documentation work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| Documentation creation | This skill (scribe-documents) | Create documentation |
| Documentation update | This skill (scribe-documents) | Update existing documentation |
| Documentation for implementation | development-lifecycle | Delegate to lifecycle |
| Documentation for compliance | manage-atlas-platform | Delegate to platform management |

---

# When to Activate This Skill

Activate this skill when:
1. User requests documentation creation or updates.
2. User needs user guides, READMEs, or technical docs.
3. User asks for documentation standards or templates.
4. User needs documentation review or improvement.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for platform management (use manage-atlas-platform).

---

# Scribe Documents Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI documentation standards (openai.com)
- Government documentation requirements (NIST, ISO)
- Official style guides (Google Developer Documentation Style Guide, Microsoft Writing Style Guide)
- Published compliance documentation requirements (SOC 2, ISO 27001)
- Official technical writing standards (IEEE, W3C)
- Open-source documentation projects (MkDocs, Docusaurus, Sphinx)
- Open-source community forums (Write the Docs, GitHub Discussions)

**NEVER use:**
- Unverified style guides from social media
- Paid writing courses or tools
- Anonymous documentation standards
- Any source requiring payment

## Documentation Procedure

1. **Requirements:** Identify documentation scope and audience.
2. **Structure:** Plan documentation structure and outline.
3. **Draft:** Write documentation using approved style guide.
4. **Review:** Technical accuracy review.
5. **Publish:** Publish to appropriate location.
6. **Maintain:** Set up maintenance schedule.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: Documentation request
- INTERPRETATION: Documentation scope and audience
- EVIDENCE: Style guide and source references
- ACTION_TAKEN: Documentation created/updated
- VERIFICATION: Technical accuracy verified
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** Documentation summary with location.

## Documentation Standards

- Use Markdown for all documentation
- Follow Google Developer Documentation Style Guide
- Include code examples where applicable
- Use consistent formatting and structure
- Include version history and last updated date

## Cross-Skill Delegation

When delegating to another skill:
1. Include the documentation request.
2. Include documentation standards used.
3. State documentation location and maintenance requirements.
