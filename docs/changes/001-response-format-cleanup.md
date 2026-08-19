# Change 001: Response Format Cleanup & Voice Sync

**Date:** 2026-08-19
**Status:** Implemented
**Author:** Atlas Studio Engineering

---

## Problem

Atlas chat responses displayed raw LLM reasoning chains to users:

```
REQUEST: Hello Atlas
INTERPRETATION: The user initiated a greeting
EVIDENCE: User's message "Hello Atlas"
ACTION_TAKEN: Acknowledged the greeting
VERIFICATION: Greeting acknowledged
AUDIT: Audit trail entry: Greeting acknowledged
```

This exposed internal reasoning to users, leaked audit metadata into TTS voice output, and provided a poor user experience across both the text chat and voice interface.

## Root Cause

All three SKILL.md files (`atlas-request-intake`, `development-lifecycle`, `manage-atlas-platform`) instructed the LLM to use a structured `REQUEST/INTERPRETATION/EVIDENCE/ACTION_TAKEN/VERIFICATION/AUDIT` format in every response. The `skill-registry.yaml` defined these as required fields. The model generated this format as free-form text, and the raw output was passed verbatim to the frontend and TTS engine.

## What Was Done

### 1. Prompt Engineering (SKILL.md Updates)

**Files modified:**
- `skills/atlas-request-intake/SKILL.md` — Rewrote `## Standard Response Format` to separate internal audit reasoning from user-facing response
- `skills/development-lifecycle/SKILL.md` — Same rewrite
- `skills/manage-atlas-platform/SKILL.md` — Same rewrite
- `skills/skill-registry.yaml` — Updated `response_format` to include `audit_fields`, `optional_audit_fields`, and `user_facing` sections

**Change:** The LLM is now instructed to generate audit reasoning internally but output only a clean, natural-language response to the user. An example is provided in each SKILL.md to reinforce the expected format.

### 2. Code-Level Output Sanitization

**File modified:** `src/atlas_studio/main.py`

**New functions added:**
- `_extract_reasoning(output: str) -> tuple[str, str]` — Splits LLM output into `(reasoning, user_facing)` by detecting lines matching audit field patterns (`REQUEST:`, `INTERPRETATION:`, `EVIDENCE:`, `ACTION_TAKEN:`, `VERIFICATION:`, `AUDIT:`, `APPROVAL_REQUIRED:`, `NEXT:`, `DELEGATION:`)
- `_clean_response(output: str) -> str` — Returns only the user-facing portion

**Applied to three execution paths:**
1. **Streaming path** (line ~250-276) — Cleaned text is broadcast to frontend via `task.delta` events; raw output is used for reasoning extraction at completion
2. **Forge tool loop** (line ~233-249) — Change set proposals and final output are cleaned before broadcast
3. **Specialist read-only loop** (line ~399-407) — Investigation reports are cleaned before returning

### 3. Task Model Extension

**File modified:** `src/atlas_studio/models.py`

**New field:** `Task.reasoning: str | None` — Stores the extracted audit reasoning chain separately from the user-facing output. Preserves the audit trail for compliance and debugging.

### 4. Voice/TTS Synchronization

**No frontend changes required.** The existing voice pipeline in `live-atlas.js` already receives cleaned text:
- `task.delta` broadcasts send `"text": clean` (the sanitized output)
- `sentenceSpeaker.update(fullText)` processes the cleaned text
- TTS synthesis via `POST /api/speech/synthesize` receives clean, natural-language text
- `prepareSpeechText()` (JS) further strips any remaining technical artifacts

Both the text display and voice output now receive the same clean response.

## Security Controls

| Control | Description |
|---|---|
| **Input validation** | `_AUDIT_FIELD_RE` regex only matches known audit field patterns; unknown patterns are treated as user-facing content |
| **Audit preservation** | Reasoning chain is stored on `task.reasoning` for compliance audit trail — not deleted, only separated |
| **No data loss** | If no user-facing content is detected, the full original output is returned (fallback at line 271-272) |
| **Defense in depth** | Both prompt-level (SKILL.md) and code-level (`_clean_response()`) sanitization are applied; if the LLM still generates audit fields in output, the code strips them |
| **Streaming safety** | Cleaned text is broadcast during streaming, preventing reasoning leakage in real-time WebSocket events |
| **TTS safety** | Voice synthesis receives the same cleaned text, preventing audit metadata from being spoken |
| **No PII exposure** | Audit fields contain system-internal references, not user data; separation prevents accidental PII leakage through voice |

## Testing

1. Send "Hello Atlas" via chat — verify clean greeting response, no reasoning chain
2. Check `task.reasoning` field contains extracted audit fields
3. Verify TTS speaks only the clean response
4. Verify Forge change set proposals display clean output
5. Verify specialist investigation reports display clean output

## Files Changed

| File | Change |
|---|---|
| `skills/atlas-request-intake/SKILL.md` | Rewrote Standard Response Format section |
| `skills/development-lifecycle/SILL.md` | Rewrote Standard Response Format section |
| `skills/manage-atlas-platform/SKILL.md` | Rewrote Standard Response Format section |
| `skills/skill-registry.yaml` | Updated response_format with audit/user_facing split |
| `src/atlas_studio/models.py` | Added `reasoning` field to `Task` model |
| `src/atlas_studio/main.py` | Added `_extract_reasoning()`, `_clean_response()`; applied to streaming, Forge, and specialist paths |
