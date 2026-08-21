# Atlas Studio — Delegation Report

**Date:** 2026-08-21
**Scope:** Delegation architecture as implemented in this repository (static analysis). No live runtime data included; the API instance was not running and `audit.jsonl` contains only HTTP access records (0 `task.delegate` events).

---

## 1. Summary

Atlas Studio implements **two independent delegation mechanisms**:

| Mechanism | Entry point | Direction | Governing constraint |
|---|---|---|---|
| **Agent-level delegation** | `execute()` in `src/atlas_studio/main.py` | Atlas → Quanta / Interface (read-only specialists) | Read-only tools only; mutations forbidden; machine-recorded evidence required |
| **Skill-level routing** | `DelegationRouter` in `src/atlas_studio/delegation.py` | Any skill → target skill per `skills/skill-registry.yaml` | Trigger/rule matching; response must carry a `DELEGATION` audit field |

Both paths write to the hash-chained audit trail and emit WebSocket events.

---

## 2. Agent-Level Delegation (Atlas → Specialist)

### 2.1 Resolution logic — `delegated_read_only_specialist()` (`main.py:343`)

Deterministic regex resolution (no model guesswork). Only fires when the acting agent is **Atlas**:

| Condition | Regex signals | Result |
|---|---|---|
| QA investigation | asks-for-QA (`qa`, `quality assurance`, `quanta`) + investigate verb + `read only` + named target | → **Quanta** |
| Site inspection | investigate verb + site/UI target + **no** change verb | → **Interface** |
| Anything else | — | No delegation; normal governed workflow |

Continuation handling: an authorization phrase (`authorized`, `proceed`, `continue`, `yes`, …) makes matching run against the full prompt rather than just the latest user request segment (split on `CURRENT USER REQUEST:`).

### 2.2 Execution flow (`execute()`, `main.py:417-462`)

1. **Audit:** `task.delegate` event recorded — details include `specialist`, `mode: read_only`, allowed tools, `mutations_allowed: false`.
2. **Broadcast:** `task.delegated` WebSocket event with `from_agent: Atlas`, `to_agent`, `mode`.
3. **Investigation loop:** `ReadOnlySpecialistToolLoop.run()` (`src/atlas_studio/layers/specialist.py:62`).
4. **Audit:** `specialist.investigate` — outcome `completed` if evidence exists, otherwise `blocked`.
5. **Result grounding:** status `grounded` iff evidence refs were collected; failure message explicitly refuses unsupported conclusions.

### 2.3 Specialist sandbox (`layers/specialist.py`)

- **Allowed tools:** `list_workspace`, `read_file`, `search_workspace`, `inspect_site` (headless render of allow-listed local pages only).
- **Bounded loop:** maximum 8 model rounds (`max_rounds=8`).
- **Evidence refs:** each successful tool call appends machine-readable references (`workspace:<path>[:line]`, `site:<url>`); search results capped at 20 path/line refs.
- **Hard rule:** if the loop ends with zero evidence, the specialist returns a refusal text instead of a conclusion.
- **No re-confirmation:** a clear user request naming a feature is treated as authorization to begin the *read-only* investigation (system prompt, line 77).

---

## 3. Skill-Level Delegation (DelegationRouter)

### 3.1 Registry source — `skills/skill-registry.yaml`

- 12 skills, all `free: true`, `local_only: true`, no external API keys.
- Every skill declares `description_triggers` and `delegates_to`.
- 13 explicit `delegation_rules` entries (`from` / `trigger` / `to`).

### 3.2 Routing algorithm (`src/atlas_studio/delegation.py`)

1. `match_skill(input)` — scores every skill by counting trigger substring hits weighted by trigger word count (more specific wins). Best score > 0 required.
2. `should_delegate(current_skill, input)` — delegates when a *different* skill matches better, or when any explicit rule whose `from_skill == current_skill` has its trigger present in the input.

### 3.3 Effective delegation graph

```
atlas-request-intake ──► development-lifecycle, manage-atlas-platform
manage-atlas-platform ⇄ development-lifecycle          (bidirectional pair)
sage-research        ──► development-lifecycle, manage-atlas-platform
counsel-legal        ──► development-lifecycle, manage-atlas-platform
scribe-documents     ──► development-lifecycle, manage-atlas-platform
pixel-visual         ──► development-lifecycle, scribe-documents
blueprint-architecture ─► development-lifecycle, manage-atlas-platform
nexus-integration    ──► development-lifecycle, scribe-documents
datacore-data        ──► development-lifecycle, manage-atlas-platform
interface-ux         ──► development-lifecycle, scribe-documents
echo-voice           ──► development-lifecycle, scribe-documents
```

`development-lifecycle` is the convergence point for all implementation work — consistent with the stated governance policy that changes only proceed through lifecycle gates.

### 3.4 Response contract

- `format_delegation_response()` returns `{from_skill, to_skill, reason, original_request, context}` plus interpretation/action/verification strings.
- Optional `DELEGATION` audit field rendered in all three response formats (`src/atlas_studio/response_format.py`: JSON `"DELEGATION"`, Markdown `**DELEGATION:**`, compact `DEL=`).

---

## 4. Lifecycle Integration

- `delegate` is a first-class stage in the Atlas lifecycle catalog (`src/atlas_studio/layers/lifecycle_catalog.py:19`).
- Required Atlas evidence includes a **"delegation record"** alongside approved scope, plan, and closure record.
- Closure requires "audit coverage" confirming no missing event categories — delegated work is therefore auditable end-to-end.

## 5. Test Coverage (`tests/test_api.py`)

| Test | Verifies |
|---|---|
| `delegated_read_only_specialist` unit cases (lines 84-108) | Quanta routing on scoped QA ask; rejection of non-read-only/mutation requests; continuation after authorization |
| `test_atlas_delegates_read_only_site_inspection_to_interface` (113) | Interface routing for site inspection |
| `test_atlas_delegates_read_only_qa_without_reconfirmation` (123) | Full flow: `task.delegate` event, `from_agent=Atlas`, `to_agent=Quanta`, `mode=read_only`, no second confirmation prompt |

---

## 6. Observations

1. **No runtime delegation events found locally** — `audit.jsonl` (6,663 lines) contains only HTTP request logs; agent audit events live in Postgres/SQLite inside the deployment. To produce a data-backed report, start the stack (`docker compose up`) and query `/api/audit` for `action == task.delegate` / `specialist.investigate`.
2. **Regex brittleness risk:** specialist resolution depends on exact phrases like "read only" appearing in the prompt; paraphrases fall through to the generic workflow (safe default, but may surprise users expecting delegation).
3. **Skill router substring matching** can over-match (e.g., trigger "API" hits many inputs); specificity weighting mitigates but does not eliminate collisions.
4. **Governance posture is consistent:** both mechanisms forbid mutation during delegation and require evidence before conclusions surface to users.
