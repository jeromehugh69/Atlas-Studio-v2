# Change 008 - OpenCode Agent Console Terminal Embed

**Date:** 2026-08-21
**Status:** Completed

## Summary

The Terminal view now embeds the OpenCode coding agent (plan/build modes) as the
development console. OpenCode runs rooted at the Atlas Studio codebase and is
permission-gated so every edit or shell command requires explicit owner approval.

## Changes

### 1. Launch + status endpoints (`src/atlas_studio/main.py`)
- `GET /api/opencode/status` - probes whether the OpenCode web UI is reachable
- `POST /api/opencode/launch` - spawns `opencode web --port 4096 --hostname
  127.0.0.1` (cwd = configured workspace) and waits up to 30s for readiness;
  resolves the CLI via `shutil.which` with a `cmd /c` wrapper for Windows npm
  `.cmd` shims

### 2. Configuration (`src/atlas_studio/config.py`)
- `opencode_web_url` (default `http://127.0.0.1:4096`)
- `opencode_cwd` (default repo root) - the codebase OpenCode operates on

### 3. Permission gate (`opencode.json`, repo root)
- `edit: ask`, `bash: { "*": "ask" }` with read-only exceptions for
  `git status*`, `git diff*`, `git log*`
- Combined with OpenCode's built-in plan/build agents: plan cannot edit or run
  commands without asking; build prompts per the glob rules above

### 4. Terminal view UI (`static/index.html`, `terminal.js`, `terminal.css`)
- Embedded iframe of the OpenCode web UI (verified embeddable: no
  X-Frame-Options / frame-ancestors restrictions)
- Offline strip with a "Start OpenCode" button that calls the launch endpoint;
  probes status on page load
- Legacy atlas console retained below as a fallback

## Verification

- Live test: `POST /api/opencode/launch` returned `{"started":true}`; web UI
  answers 200 on port 4096; framing headers allow embedding
- pytest: 80 passed (4 pre-existing failures deselected)
- `node --check` clean for `terminal.js`
