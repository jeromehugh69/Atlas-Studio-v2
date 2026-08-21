# Change 009 - OpenCode Dark Console Tabs + Non-Cloud Atlas-Synced Routing

**Date:** 2026-08-21
**Status:** Completed
**Related:** [008-opencode-terminal-embed.md](008-opencode-terminal-embed.md)

## Summary

The OpenCode console gets a persistent top-navigation tab alongside Build and a
tabbed Terminal view (OpenCode Console vs Legacy Terminal), rendered through a
dark-theme/monospace reverse proxy. OpenCode's model traffic is now routed
through Atlas Studio's own gateway (`/v1` OpenAI-compatible adapter) - fully
local, no cloud providers.

## Changes

### 1. Persistent navigation tab (`static/index.html`, `terminal.css`)
- New `OpenCode` button in the top navigation beside the Build category with an
  online status dot; clicking it opens the Terminal view with the OpenCode tab
  pre-selected

### 2. Tabbed Terminal view (`index.html`, `terminal.js`, `terminal.css`)
- Terminal page now has two tabs: "OpenCode Console" (default when online) and
  "Legacy Terminal" - only the active pane renders
- Status label shows OPENCODE ONLINE / OFFLINE; offline strip keeps the Start
  button

### 3. Dark-theme monospace proxy (`scripts/opencode_dark_proxy.py`)
- Stdlib HTTP reverse proxy (port 8096 -> 4096) that injects into HTML:
  - localStorage bootstrap pinning `opencode-color-scheme=dark` before the app
    preload script runs
  - stylesheet forcing ui-monospace/Cascadia on code/diff surfaces
- Needed because the iframe is cross-origin (localStorage unreachable from the
  parent) and the SPA reads theme only from localStorage

### 4. Launch orchestration (`main.py`, `config.py`)
- `POST /api/opencode/launch` now also spawns the dark proxy; `/api/opencode/status`
  returns `proxy_online` + `embed_url` (proxied URL when available)
- New setting: `opencode_proxy_url` (default `http://127.0.0.1:8096`)

### 5. Non-cloud synced model routing (`opencode.json`, `openai_compat.py`)
- `atlas-local` provider points OpenCode at Atlas's `/v1` adapter
  (`baseURL http://127.0.0.1:8080/v1`, models qwen3:1.7b / qwen3:4b) - every
  OpenCode inference call flows through Atlas's gateway (audit events, connect
  retries, thinking budget); nothing leaves the machine except the one-time
  provider-SDK install performed by OpenCode itself
- `/v1/chat/completions` no longer injects the Atlas system prompt when the
  client supplies its own system message - OpenCode's agent prompts pass through
  untouched while existing consumers keep current behavior

## Verification

- Proxied HTML contains both injections; `/api/health` through proxy returns 200
- Headless proof: `opencode run --model atlas-local/qwen3:1.7b` returned the
  expected reply and Atlas logged `POST /v1/chat/completions 200`
- pytest: 80 passed (4 pre-existing failures deselected)
- `node --check` clean for `terminal.js`
