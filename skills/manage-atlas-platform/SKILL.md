---
name: manage-atlas-platform
description: |
  Manage Atlas Studio platform records and navigation with the smallest safe change.
  USE WHEN user says:
  - "Update my profile"
  - "Change agent permissions"
  - "Add a new knowledge source"
  - "Modify the library"
  - "Update settings"
  - "Change workspace configuration"
  - "Inspect a skill"
  - "View analytics"
  - "Manage projects"
  - Profile updates, agent metadata or permissions, library items, knowledge-source changes, project management, plugin or skill inspection, tool access, workspace changes, settings, analytics drill-down, and requests to make Atlas administration editable.
---

# Workflow Routing (SYSTEM PROMPT)

Route platform management work to the correct procedure based on the record type and user intent:

| Record Type | User Intent | Handler | Action |
|-------------|-------------|---------|--------|
| Profile display | Update profile | This skill | Edit in Settings (local-only) |
| Library | View or manage library | This skill | Open the owning collection (index only) |
| Agent metadata | Update agent | This skill | One-time approval required |
| Agent permissions | Change tool access | This skill | One-time approval; Atlas mutating tools prohibited |
| Knowledge source | Add or modify source | This skill | Provenance review required |
| Tool | Request access | This skill | Security review; no silent grant |
| Project | View or manage | This skill | Plan and lifecycle gates |
| Environment placement | Move to environment | This skill | User reason, exact one-time approval, and override audit required |
| Plugin | Inspect skill | This skill | Workspace is read-only to Atlas; edit through Forge |
| Workspace file | Edit file | development-lifecycle | Route to Forge change set |
| Analytics | View analytics | This skill | Computed; never directly editable |
| Runtime setting | Change setting | This skill | Restart and validation may be required |

**Delegation Rule:** When delegating to another skill, include the original request, context, and any constraints.

---

# When to Activate This Skill

Activate this skill when:
1. The user wants to update a profile, settings, or configuration.
2. The user wants to manage agent metadata or permissions.
3. The user wants to inspect or manage library items, skills, or plugins.
4. The user wants to view analytics or drill into metrics.
5. The user wants to manage projects or workspace configuration.

Do NOT activate this skill when:
- The request is about code implementation, testing, or deployment (use development-lifecycle).
- The request is about receiving and scoping a new request (use atlas-request-intake).

---

# Manage Atlas Platform

Use existing Atlas APIs and shared UI components before adding endpoints or page-specific code.

## Source Policy (MANDATORY)

When conducting platform management or configuration, ONLY use trusted sources:
- OpenAI documentation and guidelines (openai.com)
- Government publications (NIST, ISO, CISA, FTC, SEC)
- Official policy documents (IEEE, W3C, IETF RFCs)
- Published compliance standards (SOC 2, ISO 27001, NIST CSF)
- Official platform documentation and release notes
- Open-source project repositories (GitHub, GitLab, Codeberg)
- Open-source community forums (GitHub Discussions, Stack Overflow)

## Workflow

1. Identify the exact record and current stored value. Never infer a missing ID, permission, path, or desired value.
2. Open the record's owning page and detail view.
3. Classify the change using [references/record-policy.md](references/record-policy.md).
4. For protected changes, show the proposed values and obtain a one-time approval before calling the mutation endpoint.
5. Apply the smallest scoped change. Keep Atlas read-only and route workspace writes through Forge change sets.
6. Refresh the owning page, verify the stored result, and confirm that an audit event exists.

## Reuse Rules

- Use the shared record-detail dialog for drill-down.
- Use Library as an index over existing tools, skills, knowledge, and projects; do not duplicate their records.
- Derive Projects from plans, workspaces, and lifecycle records; do not create a duplicate project store.
- Treat bundled skills as local plugins; open their `SKILL.md` for exact configuration.
- Use agent tool assignments for permissions; do not create a parallel permission registry.
- Treat analytics as computed evidence. Navigate to its source record rather than editing a metric.
- Treat approved sources as governed records. Submit changes for provenance review instead of silently rewriting authority metadata.
- Treat drag-and-drop environment moves as explicit lifecycle overrides. Require the exact target, a user-supplied reason, the one-time code, and a `lifecycle.override` audit event; never present an override as test evidence.
- Ask the user when the intended value, target record, evidence, or authorization is missing.

## Completion

Report the record changed, approval used, audit event, and verification result. Do not claim completion from a model response alone.

## Standard Response Format

Your output has two parts: internal audit reasoning and a user-facing response.

**1. Internal Audit Reasoning** — Think these through but they will be stripped from user output:
- REQUEST: What was asked
- INTERPRETATION: How you understood it
- EVIDENCE: Sources, citations, test results
- ACTION_TAKEN: What was done
- VERIFICATION: How the result was confirmed
- AUDIT: Audit trail entry reference

**2. User-Facing Response** — This is what the user sees. Write a clean, direct, natural-language answer. Do NOT include the field labels above. Simply describe what was done or answer the question in plain language.

## Cross-Skill Delegation

When delegating to another skill:
1. Include the original user request verbatim.
2. Include relevant context (workspace, conversation history, attachments).
3. State the reason for delegation.
4. Preserve the user's wording in the lifecycle record.

**Available Delegation Targets:**
- `atlas-request-intake`: For request intake and scoping
- `development-lifecycle`: For code changes, implementation, testing, deployment

## References

- [references/record-policy.md](references/record-policy.md) - Record protection policies
