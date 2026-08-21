# Change 005 — Atlas Female Voice

**Date:** 2026-08-21
**Status:** Completed
**Related:** [06-chat-pipeline-progress.md](../implementation/06-chat-pipeline-progress.md) Known Issue #3 / Next Step #1

## Summary

Atlas now speaks with a female voice by default. ChatterboxTTS voice-clones a bundled
CC0 female reference clip instead of using its engine-default (male-leaning) voice.

## Root Cause

`/api/speech/synthesize` called `ChatterboxTTS.generate()` without `audio_prompt_path`,
so synthesis used the model's default voice. The Kokoro/Piper female settings documented
in `.env.example` (`ATLAS_SPEECH_*`) belong to the separate avatar runtime and are not
read by the chat-panel voice path.

## Changes

### 1. Bundled female reference voice (`models/voice/atlas-female-ref.wav`)
- Built from five public-domain LJSpeech clips (female speaker, CC0), concatenated with
  short silence gaps and trimmed to 20s at 22.05 kHz mono PCM16 — Chatterbox's
  recommended reference length

### 2. Voice resolution (`src/atlas_studio/tts.py`)
- New `resolve_audio_prompt(explicit)`:
  - `"none"` / `"default"` / `"off"` → disable cloning (engine default voice)
  - explicit path → used when the file exists (warns + falls back otherwise)
  - empty → auto-detects the bundled reference from repo root or package-relative path
- `synthesize_speech()` accepts `audio_prompt_path` and passes it to `model.generate()`

### 3. Endpoint wiring (`src/atlas_studio/main.py`)
- `/api/speech/synthesize` resolves the configured prompt and passes it through;
  audit events now record which voice prompt was used (`voice_prompt` detail)

### 4. Configuration
- New setting `ATLAS_STUDIO_TTS_AUDIO_PROMPT` (default empty = bundled female voice),
  documented in `.env.example`

## Verification

- Resolution matrix smoke-tested: empty → bundled clip, `none` → None, missing path →
  warn + bundled fallback, explicit valid path → honored
- Full test suite: 80 passed (4 pre-existing failures unrelated, see change 004)

## Notes

- To clone a different speaker: set `ATLAS_STUDIO_TTS_AUDIO_PROMPT` to a clean ~20s WAV
  of that speaker.
- First synthesis after startup still pays the Chatterbox CPU model-load cost; the
  reference clip adds negligible latency (single conditioning pass).
