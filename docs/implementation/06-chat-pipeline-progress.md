# Chat Pipeline Implementation Progress

## Overview

Documenting progress on the Atlas Studio conversational chat pipeline, including Ollama qwen3:4b integration, thinking leak fixes, dashboard activity filtering, terminal console, and navigation fixes.

## Current State

**Date:** 2026-08-21
**Status:** Core functionality working — streaming chat with 40-message session memory, female voice, status report cards, industry-standard chat sizing, and the OpenCode agent console embedded in the Terminal view

## Recent Updates (2026-08-21)

- **Change 004** — SSE streaming, JSONL history persistence, Ollama auto-reconnect, separate thinking budget
- **Change 005** — Atlas female voice (ChatterboxTTS voice cloning, owner-recorded reference)
- **Change 006** — Status reports render as structured cards in the chat feed
- **Change 007** — Chat UI resized to industry standards (14px messages, resizable/maximizable panel), dashboard scrolls as one page with docked sticky chat, restored history renders on reload, "New session" button resets feed + storage + session id
- **Change 008** — OpenCode agent console embedded in Terminal view with permission gating (`opencode.json`: edit/bash ask)
- **Change 009** — OpenCode tab in top navigation + tabbed Terminal view; dark/monospace proxy; non-cloud routing through Atlas's `/v1` gateway (verified headless)

See [`docs/changes/`](../changes/) for details.

## What Was Completed

### 1. Token Auth Removal
- Removed token authentication from WebSocket (`main.py:2691-2694`)
- Removed token auth from middleware (`security/mitm.py:375-378`)
- Simplified `auth.js` to minimal fetch patch (13 lines)

### 2. Ollama Model Validation Fix
- Updated regex in `providers.py:127` to allow colons in model names
- Supports `qwen2.5-coder:7b` format

### 3. Theme Toggle CSS
- Added comprehensive light-mode overrides in `developer-features.css`
- All dark-themed elements now support light mode via `html.light-mode` selectors

### 4. POST /api/chat Endpoint
- Created lightweight chat endpoint (`main.py:2157`)
- System prompt moved server-side with engineering-focused instructions
- Delegation detection via `[DELEGATE:AgentName:prompt]` regex
- WebSocket broadcast for real-time updates

### 5. POST /api/chat/delegate Endpoint
- Created delegation endpoint (`main.py:2197`)
- Security policy check and audit logging
- Task creation for specialist agents

### 6. live-atlas.js Updates
- Removed direct Ollama calls (`OLLAMA_URL`, `OLLAMA_MODEL` removed)
- `requestAtlas()` now calls `POST /api/chat`
- Delegation handling calls `POST /api/chat/delegate`

### 7. qwen3:4b Thinking Leak Fix
**Problem:** Ollama's `think: false` dumps all reasoning as plain text in `content`

**Solution:** Use `think: true` so Ollama properly separates:
- `message.thinking` → chain-of-thought (ignored by stream handler)
- `message.content` → clean response (what we read)

**Changes:**
- `providers.py:185` - Changed `"think": False` to `"think": True`
- Removed `/no_think` system message prefix
- Increased token budget to 8192 (`providers.py:186`)

### 8. Thinking Tag Stripping (Safety Net)
- Added `_THINKING_OPEN` and `_THINKING_CLOSE` constants (`main.py:141-142`)
- Updated `_strip_thinking()` to handle orphaned `</think>` tags (`main.py:144-151`)
- Handles truncated thinking blocks

### 9. System Prompt Update
**Before:**
```
You are Atlas, the AI assistant for Atlas Studio, a local-first platform. You help {owner_name} develop and manage the platform. Be conversational, helpful, and direct...
```

**After:**
```
You are Atlas, a senior platform engineer AI for Atlas Studio. Respond in 1-3 sentences using engineering terminology (refactor, implement, test, deploy, optimize, etc). You are read-only — delegate implementation via [DELEGATE:Forge:task], QA via [DELEGATE:Quanta:task], security via [DELEGATE:Sentinel:task]. Skip pleasantries. Be direct and technical.
```

### 10. Dashboard Activity Filtering
**Problem:** Dashboard showed all audit events (auth, security, etc.)

**Solution:** Filter to development-related events only

**Changes:**
- `app.js:28` - Updated `renderAudit()` to filter by dev actions
- `app.js:62` - Updated `addEvent()` to filter by dev actions
- `index.html:138` - Changed "ACTIVE TASKS" to "DEV TASKS"
- `index.html:386` - Changed "Platform activity" to "Development activity"

**Filtered actions:**
- `task.create`, `task.execute`, `chat.message`
- `forge.change_set`, `lifecycle.transition`, `grounding.evaluate`
- `worker.code_execute`, `worker.test_execute`, `dev.activity`

### 11. Terminal Console View
**New Build view** providing an interactive console for viewing dev workflow data.

**Features:**
- Interactive command input with history (up/down arrows, Ctrl+L clear)
- Commands: `changesets`, `show`, `diff`, `plans`, `plan`, `tasks`, `task`, `lifecycle`, `status`, `refresh`, `help`
- Monospace terminal styling with dark/light theme support
- Real-time WebSocket event display
- ID prefix matching (type first 8 chars of UUID)

**Files:**
- `static/terminal.css` — Monospace styling, scrollback buffer, status badges
- `static/terminal.js` — Command parser, data fetchers, renderers
- `index.html` — Terminal section, sidebar button, Build dropdown entry

**Backend:**
- `POST /api/dev/log` endpoint for logging CLI dev activity to audit trail

### 12. Navigation Dropdown Fix
**Problem:** Dropdown menus in top nav disappeared when moving mouse from summary to menu items.

**Root cause:** Gap between `<details>` bottom edge and `.nav-menu` top created a dead zone where `:hover` was lost.

**Fix:** Extended `.nav-category` hover zone with `padding-bottom: 16px; margin-bottom: -16px` and removed `margin-top` gap on `.nav-menu`.

**File:** `developer-features.css:553-570`

### 13. Back Button
**Added** back navigation button in page header (`index.html:97`).

**Features:**
- Tracks view navigation history
- Returns to previous view on click
- Styled to match existing UI theme
- `window.viewHistory` array tracks navigation stack

**Files:**
- `index.html` — Back button in page header
- `developer-features.css` — Back button styling
- `app.js` — Navigation history tracking

### 14. Dev Activity Logging
**Problem:** CLI file changes (via opencode) weren't captured in dashboard dev activity.

**Solution:**
- Added `POST /api/dev/log` endpoint (`main.py:2308`) that logs to audit trail + broadcasts via WebSocket
- Added `window.logDevActivity()` function in `app.js` for browser console logging
- Added `dev.activity` to filtered dev actions in `addEvent()` and `renderAudit()`
- Terminal initialization auto-logs completed dev tasks

## Files Modified

| File | Changes |
|------|---------|
| `src/atlas_studio/main.py` | Chat endpoints, thinking strip, system prompt, dev activity endpoint |
| `src/atlas_studio/providers.py` | Ollama direct call, think:true, token budget |
| `src/atlas_studio/static/app.js` | Audit filtering, event filtering, nav history, back button, dev activity logger |
| `src/atlas_studio/static/index.html` | Dashboard labels, terminal section, sidebar/nav buttons, back button |
| `src/atlas_studio/static/auth.js` | Simplified auth |
| `src/atlas_studio/static/live-atlas.js` | Chat panel updates |
| `src/atlas_studio/static/terminal.css` | Terminal view styling (new) |
| `src/atlas_studio/static/terminal.js` | Terminal view logic (new) |
| `src/atlas_studio/static/developer-features.css` | Light mode, nav dropdown fix, back button |
| `src/atlas_studio/static/developer-features.js` | Terminal view activation |

## Known Issues

### 1. Ollama Connection Timeout
**Symptom:** "Local model unavailable: Ollama direct call failed"
**Cause:** Ollama server not running or crashed
**Fix:** Restart Ollama service

### 2. Longer Prompts Timeout
**Symptom:** Requests timeout after 180s
**Cause:** qwen3 thinking phase consumes tokens from same budget
**Workaround:** Increase PowerShell timeout to 300s
**Future Fix:** Separate thinking token budget

### 3. Voice Gender
**Symptom:** Atlas voice is male, user wants female
**Cause:** ChatterboxTTS uses default voice without reference audio
**Fix:** Add female voice reference audio file and configure `audio_prompt_path`
**Resolved 2026-08-21:** see [`docs/changes/005-atlas-female-voice.md`](../changes/005-atlas-female-voice.md) — bundled female reference voice is now the default

## Testing

### Chat Endpoint Test
```powershell
$body = @{ message = "Say hi" } | ConvertTo-Json
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/chat" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 180
```

**Expected Response:**
```json
{
  "response": "Hello, Platform Owner!",
  "task_id": "...",
  "delegation": null
}
```

### Delegation Test
```powershell
$body = @{ message = "Write me a test case for the chat endpoint" } | ConvertTo-Json
```

**Expected:** Response includes `[DELEGATE:Quanta:...]` and delegation JSON

### Dev Activity Log Test
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/dev/log" -Method POST -ContentType "application/json" -Body '{"message":"Test activity","status":"completed","task_id":"test-1"}'
```

**Expected:** `{"status":"logged","message":"Test activity"}`

## Next Steps

1. ~~**Investigate female voice** for Atlas~~ — Done 2026-08-21 (change 005)
2. ~~**Fix Ollama connection timeout** with auto-reconnect~~ — Done 2026-08-21 (change 004)
3. ~~**Separate thinking token budget** for qwen3~~ — Done 2026-08-21 (change 004)
4. ~~**Add chat history persistence**~~ — Done 2026-08-21 (change 004)
5. ~~**Implement streaming responses** in chat panel~~ — Done 2026-08-21 (change 004)
6. **Verify theme toggle** end-to-end with hard refresh

## Git History

```
4677bef Fix qwen3 thinking leak, update chat system prompt, filter dashboard activity
5fa6354 Add terminal console view, navigation back button, dev activity logging
256c794 Fix dropdown menu hover persistence
28a832c Update docs and progress tracking
```

Pushed to: https://github.com/jeromehugh69/Atlas-Studio-v2
