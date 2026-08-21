# Manual Test Plan — Chat Pipeline Features

One command per test. Server must be running (setup below).

## Setup

```powershell
$env:PYTHONPATH="src"; $env:ATLAS_STUDIO_DEFAULT_MODEL="qwen3:1.7b"
.\.venv\Scripts\python.exe -m uvicorn atlas_studio.main:app --host 127.0.0.1 --port 8080
```

Requires local Ollama on 11434 with a qwen3 model pulled.

## Tests

### TC1 — Streaming chat
```powershell
curl.exe -N -X POST http://127.0.0.1:8080/api/chat/stream -H "Content-Type: application/json" -d "{\"message\":\"Say hi\"}"
```
**Pass:** multiple `event: delta` lines arrive one-by-one, then `event: done`. No `<think>` text.

### TC2 — Chat history persistence
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/chat/history/MYSESSION"   # read
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/chat/history/MYSESSION" -Method DELETE   # clear
```
Chat normally in the UI first, then: **Pass:** history returns your messages; survives a server restart; DELETE empties it.

### TC3 — Thinking budget (no truncation)
```powershell
# Ask for a multi-sentence answer via /api/chat or the chat panel
```
**Pass:** complete answer, no mid-sentence cutoff, no leaked reasoning.

### TC4 — Ollama auto-reconnect
Quit Ollama → send any chat message → watch the server log → restart Ollama → send again.
**Pass:** log shows `retrying in 1s/2s/4s` before failing; recovers after Ollama restarts, no app restart needed.

### TC5 — Female voice
```powershell
$body = @{ text = "Hello, I am Atlas." } | ConvertTo-Json
$r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/speech/synthesize" -Method POST -ContentType "application/json" -Body $body
[System.IO.File]::WriteAllBytes("$env:TEMP\atlas.wav", $r.Content); Invoke-Item "$env:TEMP\atlas.wav"
```
**Pass:** audible female voice; audit (`GET /api/audit`) shows `voice_prompt: models\voice\atlas-female-ref.wav`.

## Results (2026-08-21)

| Test | Result |
|------|--------|
| pytest regression | 80 passed |
| TC1 streaming | PASS |
| TC2 history | PASS |
| TC3 thinking budget | PASS |
| TC4 auto-reconnect | PASS |
| TC5 female voice | PASS (owner-approved; reference = owner recording, tuned delivery) |
