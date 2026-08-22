# Atlas Studio — End-to-End Verification Record (2026-08-21)

## Scope
Live verification of the delegated read-only QA pipeline (Atlas → Quanta) against a
local Ollama backend, following the security hardening and history-purge work.

## Environment
- App: SQLite fallback store, artifact root `./data/artifacts`, server on 127.0.0.1:8080
- Ollama: shared daemon (`localhost:11434`), also used by another project on this machine
- Models available: `phi4:latest`, `qwen3:1.7b`

## Results

### Grounding gate — VERIFIED CORRECT
Every attempt that failed to collect workspace evidence produced:
- `status=failed`, `grounding_status=blocked`
- Header preserved: "Quanta read-only QA report"
- Issue: "The delegated QA investigation produced no machine-recorded workspace evidence."
- Audit chain complete: `task.create → workflow.started → task.delegate → specialist.investigate(blocked) → grounding.evaluate(blocked) → task.execute(failed)`

The system refused to present unsupported conclusions in all failure modes.

### Live grounded completion — BLOCKED BY SHARED INFRASTRUCTURE
| Attempt | Model | Outcome |
|---|---|---|
| 1 | qwen3:1.7b | Loop exhausted 8 rounds; model emitted **no tool calls** even when Ollama idle (direct probe: reply in 11.5s, `tool_calls=[]`) |
| 2 | phi4 | litellm timeout: `Timeout passed=300, retried 2 times` while Ollama was busy with the other project |
| 3 | phi4 | Ran >10 min without terminal state under renewed contention |

Root cause is resource contention on the single shared Ollama daemon, not application logic.
Per-request parameters do not leak between projects; queueing, model eviction, and
daemon-wide limits (`OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_KEEP_ALIVE`) do.

## Recommendations for completing live verification later
1. **Isolate**: second Ollama instance (`OLLAMA_HOST=:11435`) with `ATLAS_STUDIO_OLLAMA_URL=http://localhost:11435`
2. Or raise daemon parallelism / keep-alive so models stay resident across clients
3. Or increase provider tolerance: `ATLAS_STUDIO_LITELLM_TIMEOUT`, `ATLAS_STUDIO_LITELLM_NUM_RETRIES` (config.py)
4. Use `phi4` for the evidence loop — qwen3:1.7b does not reliably emit tool calls

## Related commits
- `dd79cb7` security hardening · `4d260fa` test fixes · `9a386ec` lock file + gitleaks hook
- `b44310b` cross-platform font resolution (portability scan: zero machine-specific paths remain in tracked files)

## Test suite status at time of writing
86/86 passing after dependency upgrades (transformers 5.15.1, diffusers 0.40.0, pip 26.2).
One deferred advisory: pytest PYSEC-2026-1845 (dev-only; blocked by `pytest>=8,<9` pin in pyproject.toml).
