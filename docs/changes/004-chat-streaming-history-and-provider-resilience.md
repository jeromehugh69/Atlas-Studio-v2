# Change 004 — Chat Streaming, History Persistence, and Provider Resilience

**Date:** 2026-08-21
**Status:** Completed
**Related:** [06-chat-pipeline-progress.md](../implementation/06-chat-pipeline-progress.md) "Next Steps" items 2–5

## Summary

Implements four of the six documented next steps from the chat pipeline progress doc:

1. Ollama auto-reconnect with retry/backoff
2. Separate thinking token budget for qwen3
3. Server-side chat history persistence
4. Streaming responses in the chat panel (SSE)

## Changes

### 1. Ollama Auto-Reconnect (`src/atlas_studio/providers.py`)

**Problem:** When the Ollama server was down or briefly unresponsive, the direct
stream call failed immediately with "Local model unavailable: Ollama direct call failed".

**Solution:**
- Connection-phase errors (`ConnectError`, `ConnectTimeout`, `ReadTimeout`) now retry
  up to `connect_retries` times (default 3) with exponential backoff (1s → 2s → 4s, capped 5s)
- Non-connection errors still fail fast and fall through to fallback models
- LiteLLM's built-in `num_retries` is now actually passed to all three `acompletion`
  call sites (generate / stream / chat_with_tools); previously it was configured but never used

### 2. Separate Thinking Token Budget (`providers.py`, `config.py`)

**Problem:** qwen3's reasoning phase consumed tokens from the same tiny budget as the
visible response (`num_predict: 256`), truncating answers on longer prompts.

**Solution:**
- Direct Ollama calls now use `"think": true` so reasoning is returned in
  `message.thinking` (ignored by the stream parser) instead of leaking into content
- Completion budget is now `max_tokens + thinking_tokens` (defaults: 384 + 4096),
  giving reasoning its own allocation without shrinking the response budget
- New settings:
  - `ATLAS_STUDIO_MODEL_THINKING_TOKENS` (default 4096)
  - `ATLAS_STUDIO_MODEL_CONNECT_RETRIES` (default 3)
- `_strip_thinking()` tag-stripping safety net in `main.py` remains in place

### 3. Chat History Persistence (`src/atlas_studio/main.py`)

**Problem:** Chat context was lost on page reload; history only lived in browser memory
(capped at 8 turns for prompt context).

**Solution:**
- New `ChatHistoryStore`: durable JSONL files under `data/chat_history/<session_id>.jsonl`
  (gitignored), capped at 200 messages per session, sanitized session ids
- `/api/chat` accepts optional `session_id`; if absent one is generated and returned so
  the client can persist it; user + assistant turns are appended after each exchange
- New endpoints:
  - `GET /api/chat/history/{session_id}` — read persisted messages
  - `DELETE /api/chat/history/{session_id}` — clear a session

### 4. Streaming Responses in Chat Panel (`main.py`, `static/live-atlas.js`)

**Problem:** Backend broadcast `task.delta` WebSocket events during generation, but the
chat panel used a blocking fetch and rendered nothing until the full response arrived.

**Solution:**
- New `POST /api/chat/stream` endpoint emitting SSE events:
  - `start` — task/session ids before generation begins
  - `delta` — cumulative output text after each chunk
  - `done` — final cleaned response, delegation payload, session id
  - `error` — sanitized failure detail
- `requestAtlas()` consumes the stream via `ReadableStream` and feeds every delta to the
  existing `onUpdate` callback, which live-renders into the pending message bubble and
  drives sentence-by-sentence TTS
- Automatic fallback to blocking `/api/chat` when streaming is unavailable
- Session id stored in `localStorage` (`atlasChatSession`); prior history restored into
  conversation context on load; Clear button also clears server-side history

## Files Modified

| File | Change |
|------|--------|
| `src/atlas_studio/providers.py` | Connect retry loop, think:true + separate budget, litellm num_retries wiring |
| `src/atlas_studio/config.py` | `model_thinking_tokens`, `model_connect_retries`, `chat_history_dir` settings |
| `src/atlas_studio/main.py` | `ChatHistoryStore`, shared chat helpers, `/api/chat/stream`, history endpoints |
| `src/atlas_studio/static/live-atlas.js` | SSE consumption with fallback, session persistence, history restore/clear |
| `.env.example` | Documented new settings |

## Verification

- Full test suite: 80 passed; the 4 failing tests in `tests/test_api.py` fail identically
  on the clean tree (pre-existing, unrelated to this change)
- Module import smoke test passes with new settings loaded

## Remaining Next Steps (from progress doc)

- Female voice for Atlas (ChatterboxTTS reference audio or Piper/Kokoro)
- End-to-end theme toggle verification with hard refresh
