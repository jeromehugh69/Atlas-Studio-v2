---
name: pixel-visual
description: |
  Generate visual assets using open-source tools and trusted sources only.
  USE WHEN user says:
  - "Generate an image..."
  - "Create a visual..."
  - "Design a logo..."
  - "Make a diagram..."
  - "Create an icon..."
  - Any visual asset generation request.
---

# Workflow Routing (SYSTEM PROMPT)

Route visual work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| Image generation | This skill (pixel-visual) | Generate visual assets |
| Visual for implementation | development-lifecycle | Delegate to lifecycle |
| Visual for documentation | scribe-documents | Delegate to documentation |

---

# When to Activate This Skill

Activate this skill when:
1. User requests image, icon, or visual generation.
2. User needs diagrams or charts.
3. User asks for visual design assistance.
4. User needs visual assets for documentation.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for documentation (use scribe-documents).

---

# Pixel Visual Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI DALL-E documentation and guidelines (openai.com)
- Government visual accessibility standards (Section 508, WCAG)
- Official design standards (Material Design, Apple HIG, Carbon Design)
- Published compliance requirements for visual assets
- Official licensing bodies for visual content
- Open-source image generation tools (Stable Diffusion, ComfyUI)
- Open-source design tools (Figma community files, Inkscape, Penpot)

**NEVER use:**
- Unverified image sources from social media
- Paid stock photo services
- Anonymous or unattributed visual assets
- Any source requiring payment or login

## Visual Generation Procedure

1. **Requirements:** Identify visual requirements and constraints.
2. **Rights Check:** Verify usage rights and licensing.
3. **Generation:** Create visual using open-source tools.
4. **Review:** Quality and accessibility review.
5. **User Approval:** Get user approval before publishing.
6. **Publish:** Store visual asset with metadata.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: Visual generation request
- INTERPRETATION: Visual requirements and constraints
- EVIDENCE: Tool and source references
- ACTION_TAKEN: Visual generated
- VERIFICATION: Quality and rights verified
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** Visual asset with usage information.

## Rights and Licensing

- Verify all visual assets have appropriate licenses
- Document usage rights for each asset
- Flag any potential licensing issues
- Prefer CC0, CC-BY, or open-source licenses

## Cross-Skill Delegation

When delegating to another skill:
1. Include the visual generation request.
2. Include visual requirements and constraints.
3. State usage rights and licensing information.
