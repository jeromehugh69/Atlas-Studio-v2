# Change 010 - OpenCode Governance Mirror + Deep-Link Console Entry

**Date:** 2026-08-21
**Status:** Completed
**Related:** [009-opencode-dark-console-synced-routing.md](009-opencode-dark-console-synced-routing.md)

## Summary

Activity performed through the OpenCode agent console now feeds Atlas Studio's
governance pipeline automatically. Each OpenCode session files a governed
intake (which becomes an approved Plan with one click), and permission asks,
tool results, and session summaries land in the audit trail. The embedded
console also deep-links straight into the workspace (no session-picker
portal) and no longer sticks on a stale OFFLINE banner.

## Changes

### 1. Mirror endpoint (`models.py`, `main.py`)
- New `OpenCodeMirrorEvent` model (`session_id`, `kind`, optional `title`,
  sanitized `detail`)
- New `POST /api/opencode/mirror` - logs `AuditEvent(action="opencode.<kind>",
  actor="opencode")`; string values truncated to 500 chars, max 20 keys, so
  console payloads cannot bloat the audit log

### 2. Governance plugin (`.opencode/plugin/atlas-governance.js`, new)
Plain-JS plugin using native `fetch` (no SDK install). Best-effort only:
Atlas outages never block OpenCode.
- First user message per session -> `POST /api/atlas/intake`
  - Change-style prompts create the governed `plan_intake` approval shown on
    the dashboard; conversational prompts fall through to intake's existing
    task mode
  - Role correlation via `message.updated` (`info.role`) because parts carry
    no role; per-session dedup prevents duplicate intakes
  - Unwraps the literal quote characters the `opencode run` CLI adds around
    argv text, which otherwise defeated the change-request detector
- `permission.asked/replied`, tool success/failure, `session.idle` ->
  mirror endpoint as audit entries

### 3. Deep-link embed URL (`main.py`)
- `/api/opencode/status` and `/launch` return
  `embed_url = {proxy}/?directory={urlencoded repo path}` - OpenCode's SPA
  reads `?directory=` and opens straight into the workspace console instead
  of its settings/session portal

### 4. Stale OFFLINE banner fix (`static/index.html`, `static/terminal.js`)
- Status probe ran only once per page load; a transient failure (e.g. Atlas
  restarting) pinned OFFLINE forever. Selecting the OpenCode tab or nav
  button now re-probes before rendering, and an 8-second interval re-probes
  whenever the OFFLINE strip is visible so recovery is automatic
- `terminal.js` script tag cache-busted (`?v=010`) since static responses
  carry no Cache-Control header

## Verification

- pytest: 82 passed (4 pre-existing failures deselected); new tests cover
  mirror audit logging/sanitization and unknown-kind rejection
- Live: headless `opencode run --model atlas-local/qwen3:1.7b "Say hello"`
  created a completed Atlas task; `"Add a status badge..."` created a pending
  `plan_intake` approval ("Begin governed review for: Add a status badge...")
- Audit shows `opencode.session_idle` entries for real sessions
- `node --check` clean for `terminal.js` and the plugin

## Notes

- OpenCode sessions remain gated by OpenCode's own permission prompts
  (mirror-only approvals by design); full Atlas gating is a future option
