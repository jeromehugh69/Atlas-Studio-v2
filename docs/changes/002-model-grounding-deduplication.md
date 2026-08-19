# Change 002: Model Grounding (Agent Roster) + Response Deduplication + Personalized Greetings

**Date:** 2026-08-19
**Status:** Implemented
**Author:** Atlas Studio Engineering

---

## Problem

### 1. Model Hallucination (Grounding)
When users asked "What agents are available?", the LLM fabricated agent names and descriptions that don't exist in Atlas Studio. The model had no factual data about the 15 named agents — only the agent being addressed was visible in the system prompt.

### 2. Response Repetition (Deduplication)
The `qwen3:1.7b` model repeated its response 2-3 times, producing output like:
```
Hey there! Atlas is online...Hey there! Atlas is online...Hey there! Atlas is online...
```

### 3. No Personalized Greetings
Atlas had no knowledge of the user's name and could not address them personally.

## Root Cause

1. **Grounding:** The system prompt only contained the current agent's name/role/description. No roster of available agents was injected, so the model had no factual basis to answer agent-related questions.

2. **Deduplication:** Small quantized models (1.7B parameters) have limited coherence and tend to repeat content, especially for simple prompts.

3. **Personalization:** No user identity was stored or injected into the LLM context. The platform used a hardcoded `"local-user"` string for all audit events.

## What Was Done

### 1. Agent Roster Injection

**File modified:** `src/atlas_studio/main.py`

**New function:** `render_agent_context(exclude_name: str = "") -> str`

Builds a formatted roster from `store.agents`:
```
AVAILABLE AGENTS IN THIS PLATFORM:
- Atlas (Platform Intelligence Orchestrator): Receives the user's direction...
- Forge (Platform Development AI): Primary implementation assistant...
[...all 15 agents, excluding the current agent]
```

**Injected into three system prompt assembly points:**
1. `run_model_step()` — main LLM streaming path (line ~204)
2. `ForgeToolLoop.run()` — Forge implementation path (line ~109 in forge.py)
3. `ReadOnlySpecialistToolLoop.run()` — specialist investigation path (line ~81 in specialist.py)

**Design decision:** The current agent is excluded from the roster (`exclude_name`) to avoid the model listing itself. The context is passed as a parameter to Forge and Specialist to avoid circular imports.

### 2. Response Deduplication

**File modified:** `src/atlas_studio/main.py`

**New function:** `_deduplicate_response(output: str) -> str`

Algorithm:
1. Split output into paragraphs (double-newline separated)
2. Detect consecutive identical paragraphs (normalized by stripping whitespace)
3. Remove duplicate occurrences, keeping only the first

**Applied to three output paths:**
1. Streaming path — after `_extract_reasoning()`, before `evaluate_grounding()`
2. Forge path — after `_extract_reasoning()`, before broadcast/return
3. Specialist path — after `_extract_reasoning()`, before returning result

### 3. Personalized Greetings

**Files modified:**
- `src/atlas_studio/config.py` — Added `owner_name: str = "Platform Owner"` setting
- `.env` — Added `ATLAS_STUDIO_OWNER_NAME=Jerome`
- `src/atlas_studio/main.py` — Injected `owner_context` into system prompt: "The platform owner's name is {name}. Address them by name when greeting..."
- `skills/atlas-request-intake/SKILL.md` — Added greeting pattern: "Hello Jerome! I'm Atlas, your AI engineering assistant..."

**Design:** The owner name is a simple config setting backed by an environment variable. It's injected into the LLM system prompt so Atlas can use it for personalized greetings. No database migration, new models, or authentication changes required.

## Security Controls

| Control | Description |
|---|---|
| **No PII in roster** | Agent roster contains only system-internal names, roles, and descriptions — no user data |
| **Exclusion prevents self-reference** | Current agent is excluded from roster to prevent circular references |
| **Parameter passing avoids circular imports** | `agent_context` is passed as a string parameter to Forge/Specialist, not imported from main.py |
| **Deduplication is non-destructive** | Only consecutive identical paragraphs are removed; unique content is preserved |
| **Fallback safety** | If deduplication produces empty output, the original is returned |

## Files Changed

| File | Change |
|---|---|
| `src/atlas_studio/main.py` | Added `render_agent_context()`, `_deduplicate_response()`; injected agent_context into system prompt; applied dedup to all three output paths |
| `src/atlas_studio/layers/forge.py` | Added `agent_context` parameter to `run()` method; appended to system prompt |
| `src/atlas_studio/layers/specialist.py` | Added `agent_context` parameter to `run()` method; appended to system prompt |

## Testing

1. Send "What agents are available?" — verify model lists actual 15 agents with correct roles
2. Send "Hello Atlas" — verify no response repetition
3. Verify Forge change set proposals include agent context
4. Verify specialist investigation reports include agent context
