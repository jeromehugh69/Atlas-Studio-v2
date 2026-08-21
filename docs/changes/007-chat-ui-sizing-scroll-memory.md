# Change 007 - Chat UI Sizing, Scroll Fix, and Session Memory

**Date:** 2026-08-21
**Status:** Completed

## Summary

Chat screen resized to industry-standard typography with user-controlled sizing
(drag-to-resize + maximize), the dashboard body now scrolls as one page while the
chat stays docked, and Atlas now persists and recalls 40 messages of conversation
until the engineer starts a new session.

## Changes

### 1. Chat panel sizing (`static/atlas-chat-panel.css`)
- Message text `.74rem` -> `.875rem` (14px), line-height 1.6; bubbles capped at
  `min(92%, 760px)` for readability
- Markdown headings/code/table fonts bumped ~+0.08rem to match
- Composer textarea font -> `.875rem`; transcript padding `13px 15px` -> `16px 20px`
- Tool buttons 27px -> 34px tall, send button 29px -> 36px (touch-target guidance)
- Embedded header min-height 70px -> 60px; feed min-height 170px -> 240px

### 2. Voice dock collapse (`atlas-chat-panel.html`, `live-atlas.js`)
- New "Voice" toggle in the composer heading (`aria-expanded`/`aria-controls`);
  voice-test panel hidden by default so the transcript + composer get full width
- Dock collapses to a single column when hidden; preference persisted in
  localStorage key `atlasVoiceDock`

### 3. Dashboard scroll fix (`static/dashboard-widgets.css`)
- `body.command-active > .app-main` scrolls naturally (`overflow-y: auto`) instead
  of clipping at `100vh`
- Card rail rows changed from fractional viewport heights to natural size; removed
  the rail's internal scrollbar and the DEV TASKS nested scroll cap, so all cards
  flow and scroll together as one page body
- Chat column is `position: sticky` at full viewport height - chat stays visible
  while cards scroll beside it
- New <=1400px breakpoint shrinks the card rail 302px -> 270px giving chat more
  width on mid-size screens; <=900px layout un-pins the sticky chat as before

### 4. User-controlled chat size (`index.html`, `app.js`, CSS)
- Chat panel is drag-resizable vertically via native `resize: vertical`
  (min 540px)
- New maximize button (top-right of the chat panel, Escape restores) toggles a
  fixed full-viewport overlay for full-screen conversations

### 5. Session memory until new session (`live-atlas.js`, `config.py`, `main.py`)
- Restored history is now rendered into the feed on reload (previously only fed
  back to the model invisibly) - last 40 stored messages appear as normal bubbles
- Context depth raised from 8 turns (client) / 10 turns (server) to 40 both sides;
  new setting `ATLAS_STUDIO_CHAT_CONTEXT_MESSAGES` (default 40, range 1-200)
- "Clear feed" button replaced by "New session": clears the transcript, deletes the
  server-side JSONL history, and mints a fresh session id - conversations persist
  across reloads and server restarts until explicitly reset

## Verification

- pytest: 80 passed (4 pre-existing failures deselected, unchanged on clean tree)
- `node --check` clean for `app.js` and `live-atlas.js`
- Live smoke test: `/api/chat` round-trip stores user+assistant JSONL entries,
  history GET returns them, DELETE returns 200
- Static serving confirmed for updated HTML/CSS/JS (voiceToggle, "New session",
  chatMaximize, sticky rules all present over HTTP)
