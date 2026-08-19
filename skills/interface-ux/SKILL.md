---
name: interface-ux
description: |
  Design user experiences using open-source trusted sources only.
  USE WHEN user says:
  - "UI design..."
  - "User interface..."
  - "UX review..."
  - "Accessibility..."
  - "Frontend design..."
  - Any UX or frontend design request.
---

# Workflow Routing (SYSTEM PROMPT)

Route UX work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| UX design | This skill (interface-ux) | Design user experience |
| UX for implementation | development-lifecycle | Delegate to lifecycle |
| UX documentation | scribe-documents | Delegate to documentation |

---

# When to Activate This Skill

Activate this skill when:
1. User requests UI/UX design.
2. User needs accessibility review or improvements.
3. User asks for frontend design patterns.
4. User needs user flow or wireframe design.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for documentation (use scribe-documents).

---

# Interface UX Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI UX guidelines (openai.com)
- Government accessibility standards (Section 508, WCAG 2.1)
- Official design systems (Material Design, Apple HIG, Carbon Design)
- Published compliance requirements for UX (SOC 2, ISO 27001)
- Official standards bodies (W3C, IEEE)
- Open-source design tools (Figma community, Penpot, Inkscape)
- Open-source component libraries (Bootstrap, Tailwind, Bulma)

**NEVER use:**
- Unverified UX blogs from social media
- Paid design tools or courses
- Anonymous or unattributed UX standards
- Any source requiring payment

## UX Procedure

1. **User Flow:** Design user flow and navigation.
2. **Design:** Create visual design and components.
3. **Accessibility:** Ensure WCAG compliance.
4. **Implementation:** Get approval for implementation.
5. **Browser Test:** Test in multiple browsers.
6. **Review:** UX review and improvements.
7. **Handoff:** Document design for developers.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: UX request
- INTERPRETATION: UX scope and requirements
- EVIDENCE: UX patterns and sources
- ACTION_TAKEN: UX designed
- VERIFICATION: Accessibility verified
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** UX summary with accessibility status.

## Accessibility Requirements

- WCAG 2.1 AA compliance minimum
- Keyboard navigation support
- Screen reader compatibility
- Color contrast compliance
- Responsive design for all devices

## Cross-Skill Delegation

When delegating to another skill:
1. Include the UX request.
2. Include user flows and design specifications.
3. State accessibility requirements and compliance status.
