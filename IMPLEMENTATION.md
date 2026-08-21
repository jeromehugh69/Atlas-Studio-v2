# Atlas Studio standalone implementation guide

This guide describes how the standalone platform is assembled, how requests move through it, and how to progress from the current single-node Community deployment to a hardened production installation. It is intentionally specific to this repository and has no dependency on another Atlas Studio or Atlas Studio project.

## 1. System architecture

```mermaid
flowchart TB
    User["User"] --> Web["Atlas Studio Web Client"]
    Web -->|"REST operations"| API["Local API Gateway"]
    Web <-->|"WebSocket progress"| API

    subgraph Runtime["Atlas Studio Runtime"]
        API --> Orchestrator["Agent Orchestrator"]
        Orchestrator --> Permissions["Agent Tool and Permission Policy"]
        Orchestrator --> Gateway["Provider-neutral Model Gateway"]
        Orchestrator --> Queue["Task and Event Coordinator"]
        Orchestrator --> Artifacts["Artifact Service"]
        Orchestrator --> Memory["Semantic Memory Manager"]
    end

    Gateway --> Ollama["Ollama â€” default"]
    Gateway -.-> LlamaCpp["llama.cpp â€” optional"]
    Gateway -.-> VLLM["vLLM â€” optional"]
    Gateway -.-> Transformers["Transformers server â€” optional"]

    Queue --> Redis["Redis"]
    Memory --> Postgres["PostgreSQL and pgvector"]
    API --> Postgres
    Artifacts --> Filesystem["Local filesystem â€” default"]
    Artifacts -.-> MinIO["MinIO â€” optional profile"]
    Permissions --> Sandbox["Rootless isolated sandbox"]
    Sandbox --> Workspace["Explicitly approved workspace"]
```

Solid lines are Community-mode dependencies. Dotted lines are optional integrations and never prevent the Community platform from starting.

## 2. Repository map

```text
atlas-studio/
â”œâ”€â”€ src/atlas_studio/
â”‚   â”œâ”€â”€ main.py               REST, WebSocket, orchestration, kill switch
â”‚   â”œâ”€â”€ config.py             validated local-first configuration
â”‚   â”œâ”€â”€ providers.py          Ollama and OpenAI-compatible provider contracts
â”‚   â”œâ”€â”€ infrastructure.py     PostgreSQL and Redis runtime adapters
â”‚   â”œâ”€â”€ models.py             API and domain models
â”‚   â”œâ”€â”€ store.py              agent seeds, read cache, artifact validation
â”‚   â””â”€â”€ static/               branded browser interface
â”œâ”€â”€ database/migrations/      pgvector schema and named-agent seeds
â”œâ”€â”€ models/manifests/         model references; no bundled weights
â”œâ”€â”€ runtime/policies/         sandbox and agent isolation policy
â”œâ”€â”€ scripts/                  local model setup
â”œâ”€â”€ tests/                    API, safety, and configuration tests
â”œâ”€â”€ compose.yaml              isolated one-command deployment
â”œâ”€â”€ Dockerfile                unprivileged application image
â””â”€â”€ .env.example              no required external credentials
```

## 3. Step-by-step implementation process

### Phase 1 â€” establish the isolated deployment boundary

1. Create a dedicated project directory, Compose project name, container network, volumes, ports, environment prefix, and database.
2. Use `ATLAS_STUDIO_` for all platform settings and `atlas-studio` as the Compose project name.
3. Keep persistent volumes (`atlas_studio_postgres`, `atlas_studio_redis`, `atlas_studio_models`, and `atlas_studio_artifacts`) separate from every other project.
4. Bind only the web/API and Ollama ports required for local operation.
5. Keep additional self-hosted services such as MinIO and the local avatar worker behind explicit Compose profiles.

Validation checkpoint: `docker compose --env-file .env.example config --quiet` must succeed without a vendor key.

### Phase 2 â€” configure local-first behavior

1. Copy `.env.example` to `.env`.
2. Leave `ATLAS_STUDIO_MODE=community` and `ATLAS_STUDIO_DEFAULT_PROVIDER=ollama` selected.
3. Validate configuration at application startup.
4. Reject enabled external integrations in Community mode instead of silently contacting an external service.
5. Report a missing model as degraded health; do not terminate the application.

Configuration decision flow:

```mermaid
flowchart TD
    Start["Load Atlas Studio settings"] --> Mode{"Deployment mode?"}
    Mode -->|"community"| Local["Enable local core services"]
    Local --> External{"Any external adapter enabled?"}
    External -->|"yes"| Reject["Reject invalid configuration"]
    External -->|"no"| Boot["Start local platform"]
    Mode -->|"integrations"| Core["Start local core services"]
    Core --> Enabled["Load only explicitly enabled adapters"]
    Enabled --> Credentials{"Required credential present?"}
    Credentials -->|"yes"| Adapter["Expose optional adapter"]
    Credentials -->|"no"| Disabled["Mark adapter unavailable; keep core running"]
    Adapter --> Boot
    Disabled --> Boot
```

### Phase 3 â€” initialize durable and transient storage

1. Start PostgreSQL using the pgvector image.
2. Run `001_initial.sql` to create workspaces, agents, tasks, memories, artifacts, and append-oriented audit events.
3. Create the HNSW cosine index for semantic memory retrieval.
4. Run `002_seed.sql` to create the isolated local workspace and all named agents.
5. Start Redis with append-only persistence and bounded memory.
6. Use PostgreSQL for durable task, permission, memory, artifact, and audit records.
7. Use Redis for task snapshots, coordination messages, cache entries, and kill-switch broadcasts.

Data ownership map:

```mermaid
flowchart LR
    API["API and Orchestrator"] -->|"durable records"| PG["PostgreSQL"]
    API -->|"semantic vectors"| Vector["pgvector"]
    API -->|"short-lived task state"| Redis["Redis"]
    API -->|"files and generated output"| Artifact["Filesystem or MinIO"]

    PG --> Tasks["tasks"]
    PG --> Agents["agents and permissions"]
    PG --> Audit["audit_events"]
    Vector --> Memories["memories"]
    Artifact --> Metadata["artifact metadata in PostgreSQL"]
```

### Phase 4 â€” register local model providers

1. Implement the `ModelProvider` interface for generation and health checks.
2. Register native Ollama as the default provider.
3. Use the OpenAI-compatible adapter boundary for llama.cpp, vLLM, and compatible Transformers servers.
5. Keep provider selection in the gateway; task and agent logic must never call a vendor SDK directly.
6. Pull model weights separately using the model manifests or `scripts/pull-models.ps1`.

Model request data flow:

```mermaid
sequenceDiagram
    actor User
    participant UI as Web Client
    participant API as API Gateway
    participant Agent as Agent Orchestrator
    participant Policy as Permission Policy
    participant Gateway as Model Gateway
    participant Ollama as Local Ollama
    participant DB as PostgreSQL

    User->>UI: Submit task and select named agent
    UI->>API: POST /api/plans
    API->>DB: Persist plan awaiting approval
    UI->>API: Approve plan with local passcode
    API->>Agent: Create isolated plan workspace
    UI->>API: POST /api/tasks with plan and workspace
    API->>DB: Persist queued task and audit event
    API->>Queue: Add durable priority record
    API-->>UI: 202 Accepted
    Queue->>Agent: Dispatch highest-priority task
    Agent->>Policy: Resolve allowed tools and read-only state
    Policy-->>Agent: Approved capabilities
    Agent->>Gateway: Generate with selected local model
    Gateway->>Ollama: POST /api/chat
    Ollama-->>Gateway: Generated response
    Gateway-->>Agent: Provider-neutral result
    Agent->>DB: Persist output, status, and audit event
    Agent-->>UI: WebSocket task.progress event
```

### Phase 5 â€” implement named agents and tool controls

1. Seed every agent with a name, role, description, and initial tool set.
2. Keep Atlas continuously connected to diagnostics, research, investigation, memory-read, and file-read tools.
3. Mark Atlas read-only in both the database and domain model.
4. Reject `files_write` or `code_execute` for Atlas at the API boundary, even if a modified client sends the request.
5. Assign implementation tools to Forge.
6. Let users enable or disable non-prohibited tools for each agent through the Agents tab.
7. Write every permission change to the audit trail.

Permission workflow:

```mermaid
flowchart TD
    Change["User changes an agent tool"] --> Request["PATCH /api/agents/{id}"]
    Request --> Exists{"Agent exists?"}
    Exists -->|"no"| NotFound["Return 404"]
    Exists -->|"yes"| Atlas{"Is agent Atlas?"}
    Atlas -->|"no"| Save["Persist approved tool set"]
    Atlas -->|"yes"| Impl{"Includes write or execution tool?"}
    Impl -->|"yes"| Deny["Return 422 and preserve read-only policy"]
    Impl -->|"no"| Save
    Save --> Audit["Record audit event"]
    Audit --> UI["Refresh agent card"]
```

### Phase 6 â€” isolate tool execution

1. Run execution in a separate worker; never expose the host Docker or Podman socket to the web application.
2. Use rootless Docker or Podman.
3. Start every sandbox with no network, no Linux capabilities, `no-new-privileges`, a read-only root filesystem, and an unprivileged user.
4. Apply CPU, memory, PID, disk, and execution-time limits from `runtime/policies/sandbox.json`.
5. Create one workspace boundary per user or tenant.
6. Mount only the explicitly approved workspace.
7. Default the mount to read-only; Forge may receive a read-write mount only after explicit authorization.
8. Stream sanitized progress events to the API rather than granting the sandbox direct browser access.
9. Subscribe the worker to the Redis kill-switch channel and terminate active sandboxes when `kill` is received.

Sandbox trust boundary:

```mermaid
flowchart LR
    subgraph Trusted["Trusted control plane"]
        API["Atlas Studio API"] --> Policy["Permission policy"]
        Policy --> Worker["Sandbox worker"]
    end
    subgraph Untrusted["Untrusted execution boundary"]
        Worker --> Container["Rootless sandbox container"]
        Container --> Temp["Ephemeral read-only root"]
        Container --> Work["Approved workspace mount"]
    end
    Container -.-x Network["External network denied"]
    Container -.-x Host["Host filesystem denied"]
    Container -.-x Socket["Container socket denied"]
```

### Phase 7 â€” handle artifacts safely

1. Read no more than the configured upload limit plus one byte.
2. Reduce the submitted name to a basename and reject any mismatch to prevent path traversal.
3. Allow only the documented extension set.
4. Resolve the final path and confirm it remains inside the artifact root.
5. Store the payload locally by default.
6. Record size, media type, hash, workspace, and storage key in PostgreSQL in the production artifact adapter.
7. Use MinIO only when Integrations mode and its Compose profile are enabled.

```mermaid
flowchart TD
    Upload["Upload request"] --> Limit{"Within size limit?"}
    Limit -->|"no"| Reject["Reject with 422"]
    Limit -->|"yes"| Name{"Safe basename and allowed type?"}
    Name -->|"no"| Reject
    Name -->|"yes"| Resolve["Resolve canonical destination"]
    Resolve --> Inside{"Inside workspace artifact root?"}
    Inside -->|"no"| Reject
    Inside -->|"yes"| Store["Store file"]
    Store --> Record["Persist metadata and audit event"]
```

### Phase 8 â€” stream task progress

1. The client opens `/api/ws` after loading.
2. The API confirms the active deployment mode.
3. Task creation returns immediately with `202 Accepted`.
4. The orchestrator emits `queued`, `running`, and terminal task states.
5. The interface prepends events to Live Activity.
6. A production worker publishes the same event contract through Redis so multiple API replicas can relay it.

```mermaid
sequenceDiagram
    participant Browser
    participant API
    participant Redis
    participant Worker
    Browser->>API: WebSocket connect
    API-->>Browser: connected and deployment mode
    Browser->>API: Create task over REST
    API->>Redis: Save transient task state
    API-->>Browser: queued
    Worker->>Redis: running progress event
    Redis->>API: progress event
    API-->>Browser: task.progress
    Worker->>Redis: completed or failed event
    Redis->>API: terminal event
    API-->>Browser: final task.progress
```

### Phase 9 â€” integrate local speech and avatars

1. Keep STT, TTS, and avatar services disabled until configured.
2. Point `ATLAS_STUDIO_STT_URL` to a local Whisper-compatible service.
3. Point `ATLAS_STUDIO_TTS_URL` to a local Piper or Kokoro service.
4. Serve approved `.glb` or `.gltf` assets from local artifact storage.
5. Drive avatar listening, thinking, speaking, and idle states from WebSocket events.
6. Never require hosted speech credentials for text interaction.

```mermaid
flowchart LR
    Mic["Microphone"] -.-> STT["Local Whisper-compatible STT"]
    STT -.-> Task["Atlas Studio task input"]
    Task --> Model["Local model response"]
    Model -.-> TTS["Local Piper or Kokoro TTS"]
    TTS -.-> Audio["Audio playback"]
    Model --> Events["WebSocket avatar state"]
    Events --> GLB["Local GLB avatar runtime"]
```

### Phase 10 â€” implement operational safety

1. Expose liveness independently from dependency readiness.
2. Report PostgreSQL, Redis, and the model gateway separately.
3. Keep the interface accessible in degraded mode so operators can diagnose missing local services.
4. Store task creation, execution, permission changes, cancellation, uploads, and kill-switch transitions as audit events.
5. When the kill switch is engaged, reject new tasks, cancel queued/running state, publish `kill`, and terminate worker sandboxes.
6. Do not label ordinary local storage, access control, or transport features as â€œencryption.â€ Describe the actual protection instead.

Kill-switch workflow:

```mermaid
flowchart TD
    Operator["Operator selects Stop all agents"] --> API["POST /api/control/kill-switch"]
    API --> Lock["Set execution lock"]
    Lock --> Cancel["Mark active task state cancelled"]
    Lock --> Redis["Publish kill on Redis control channel"]
    Redis --> Workers["Workers terminate active sandboxes"]
    Lock --> Audit["Persist kill-switch audit event"]
    Lock --> WS["Broadcast control event"]
    WS --> UI["Show stopped state"]
```

### Phase 11 â€” deploy and verify

1. Copy the example configuration.
2. Build and start the local services.
3. Pull referenced model weights separately.
4. Confirm API liveness and readiness.
5. Open the web client and inspect Community mode.
6. Confirm Atlas cannot be assigned implementation tools.
7. Submit a task to Forge and watch WebSocket progress.
8. Upload one permitted document and confirm an executable is rejected.
9. Engage the kill switch and confirm task creation returns `423`.
10. Review the audit trail.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
./scripts/pull-models.ps1
docker compose ps
Invoke-RestMethod http://localhost:8080/api/health/live
Invoke-RestMethod http://localhost:8080/api/health/ready
```

Expected readiness after models and dependencies initialize:

```json
{
  "status": "ready",
  "components": {
    "api": "ok",
    "model_gateway": "ok",
    "postgres": "ok",
    "redis": "ok"
  },
  "core_available_without_cloud": true
}
```

## 4. End-to-end task lifecycle

```mermaid
stateDiagram-v2
    [*] --> Queued: task accepted
    Queued --> Running: worker claims task
    Queued --> Cancelled: user or kill switch
    Running --> Completed: local model or tool succeeds
    Running --> Failed: provider or tool error
    Running --> Cancelled: user, timeout, or kill switch
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
```

Every transition updates durable task state, refreshes the Redis snapshot, emits a WebSocket event, and records an audit event where appropriate.

## 5. Semantic memory flow

The database schema reserves 1,024-dimensional embeddings for the default local embedding profile. If another embedding model uses a different dimension, create a migration rather than coercing vector sizes.

```mermaid
sequenceDiagram
    participant Agent
    participant Memory as Memory Manager
    participant Embed as Local Embedding Model
    participant PG as PostgreSQL and pgvector
    Agent->>Memory: Store approved memory
    Memory->>Embed: Generate local embedding
    Embed-->>Memory: 1024-dimensional vector
    Memory->>PG: Insert content, vector, metadata, workspace
    Agent->>Memory: Retrieve relevant context
    Memory->>Embed: Embed query
    Embed-->>Memory: Query vector
    Memory->>PG: Cosine nearest-neighbor query scoped to workspace
    PG-->>Memory: Ranked memories
    Memory-->>Agent: Sanitized context
```

Workspace scoping must be part of every memory query. Retrieval must never rely on post-query filtering.

## 6. Production hardening sequence

Implement these increments in order:

1. Scale the durable Redis priority dispatcher into separate model-execution worker processes.
2. Add multi-user local authentication and workspace-aware role-based access controls.
3. Add a reverse proxy with locally managed TLS for any network-exposed deployment.
4. Add content hashing and optional malware scanning to the artifact service.
5. Implement rootless Docker and Podman sandbox adapters against the committed worker policy.
6. Add a local embedding provider and workspace-scoped pgvector retrieval endpoints.
7. Add MinIO, Whisper-compatible STT, Piper/Kokoro TTS, and browser/search adapters one at a time behind feature flags.
8. Add backup/restore, audit retention, dependency license scanning, model provenance verification, and disaster-recovery tests.
9. Run concurrency, cancellation, timeout, path traversal, cross-workspace access, and kill-switch integration tests.
10. Document the exact version and license of every selected model and local avatar asset.

## 7. Verification matrix

| Area | Verification | Expected result |
|---|---|---|
| Community startup | Start with `.env.example` values | No vendor credential required |
| Provider outage | Stop Ollama | API remains live; readiness is degraded |
| Database outage | Stop PostgreSQL after startup | UI remains diagnosable; persistence reports unavailable |
| Atlas policy | Attempt to add `files_write` | API returns `422` |
| Tool control | Toggle an allowed tool | Agent updates and audit event is created |
| Upload safety | Upload `../payload.exe` | API returns `422` |
| Workspace boundary | Resolve a path outside artifact root | Request is rejected |
| Kill switch | Stop all agents, then create a task | API returns `423` |
| WebSocket | Execute a local task | Client receives queued/running/terminal events |
| Optional adapters | Omit cloud keys | Core services continue to operate |
| Telemetry | Run Community mode | Telemetry remains disabled |
| Model licensing | Inspect manifests | Weights are referenced, not bundled |

## 8. Definition of done

A standalone increment is complete only when:

- it runs inside the isolated Atlas Studio Compose project;
- Community mode works without external keys;
- configuration validation fails safely and clearly;
- the API, UI, persistence, audit, and progress contracts agree;
- Atlas remains read-only and Forge remains the implementation agent;
- permissions are enforced on the server, not only displayed in the UI;
- resource, workspace, upload, and network boundaries have tests;
- degraded optional services do not cause a hard application failure;
- documentation and diagrams are updated with the implementation; and
- model weights or assets are not redistributed without verified permission.

## 9. Recent Progress

### OpenCode Governance Mirror + Deep-Link Console (2026-08-21)

**Document:** [`docs/changes/010-opencode-governance-mirror.md`](docs/changes/010-opencode-governance-mirror.md)

**Summary:**
- New `.opencode/plugin/atlas-governance.js`: first user message per session files a governed intake (`POST /api/atlas/intake` -> one-click Plan approval); permission asks, tool results, and idle summaries mirror into the audit trail via new `POST /api/opencode/mirror` (sanitized, truncated)
- Console `embed_url` now deep-links with `?directory=<repo>` — skips OpenCode's session-picker portal entirely
- Terminal tab / nav clicks re-probe `/api/opencode/status`, fixing the stale OFFLINE banner after transient failures
- Verified live: change-style prompt produced a pending `plan_intake` approval; conversational prompt produced a completed Atlas task

**Status:** Completed

### OpenCode Dark Console Tabs + Atlas-Synced Routing (2026-08-21)

**Document:** [`docs/changes/009-opencode-dark-console-synced-routing.md`](docs/changes/009-opencode-dark-console-synced-routing.md)

**Summary:**
- Persistent "OpenCode" tab in the top navigation (beside Build); Terminal view now tabbed: OpenCode Console vs Legacy Terminal
- Dark-theme/monospace reverse proxy (:8096) injects forced dark scheme + mono fonts into the embedded console
- Non-cloud model routing: OpenCode's `atlas-local` provider points at Atlas's `/v1` adapter — all inference flows through Atlas's gateway (audit, retries); verified headless (`SYNC-OK` via `/v1/chat/completions 200`)
- `/v1/chat/completions` passes client system prompts through untouched

**Status:** Completed

### OpenCode Agent Console Terminal Embed (2026-08-21)

**Document:** [`docs/changes/008-opencode-terminal-embed.md`](docs/changes/008-opencode-terminal-embed.md)

**Summary:**
- Terminal view embeds the OpenCode coding agent web UI (plan/build modes) rooted at the Atlas Studio codebase
- Permission-gated via `opencode.json`: every edit and shell command requires owner approval (read-only git status/diff/log pre-approved)
- `GET /api/opencode/status` + `POST /api/opencode/launch` endpoints; "Start OpenCode" button in the offline strip; legacy console kept as fallback
- Windows npm `.cmd` shim handled via `shutil.which` + `cmd /c`

**Status:** Completed

### Chat UI Sizing, Scroll Fix, and Session Memory (2026-08-21)

**Document:** [`docs/changes/007-chat-ui-sizing-scroll-memory.md`](docs/changes/007-chat-ui-sizing-scroll-memory.md)

**Summary:**
- Chat panel resized to industry standards: 14px message text, 760px bubble cap, larger composer/buttons, compact header
- User-controlled sizing: drag-to-resize (vertical) + maximize button (Escape restores)
- Dashboard body scrolls as one page; all overview cards flow at natural height together; chat stays docked sticky at full viewport height
- Voice test panel collapsed behind a "Voice" toggle (preference persisted)
- Atlas remembers 40 messages of context per session; restored history renders in the feed on reload; "New session" button resets feed, storage, and session id

**Status:** Completed

### Status Report Cards in Chat Feed (2026-08-21)

**Document:** [`docs/changes/006-status-report-cards.md`](docs/changes/006-status-report-cards.md)

**Summary:**
- Atlas status reports auto-render as a structured card in the chat feed: PLATFORM STATUS header + color-coded rows (green healthy / amber attention / red action)
- Frontend-only detection in `chat-format.js` — ≥3 `Label: value` fields, all other prose unchanged
- Works during streaming; card fills in live

**Status:** Completed

### Atlas Female Voice (2026-08-21)

**Document:** [`docs/changes/005-atlas-female-voice.md`](docs/changes/005-atlas-female-voice.md)

**Summary:**
- Bundled CC0 female reference voice (LJSpeech samples, 20s WAV) at `models/voice/atlas-female-ref.wav`
- ChatterboxTTS now voice-clones the reference via `audio_prompt_path` — Atlas speaks with a female voice by default
- New `ATLAS_STUDIO_TTS_AUDIO_PROMPT` setting: override with a custom ~20s WAV or set `none` for engine default
- Audit events record which voice prompt was used per synthesis

**Status:** Completed

### Chat Streaming, History Persistence, and Provider Resilience (2026-08-21)

**Document:** [`docs/changes/004-chat-streaming-history-and-provider-resilience.md`](docs/changes/004-chat-streaming-history-and-provider-resilience.md)

**Summary:**
- Ollama auto-reconnect: connection errors retry with exponential backoff (default 3 attempts); LiteLLM `num_retries` now wired into all completion calls
- Separate thinking token budget for qwen3: `think: true` + `num_predict = max_tokens + thinking_tokens` (defaults 384 + 4096) so reasoning no longer truncates answers
- Server-side chat history persistence: JSONL per session under `data/chat_history/`, with `GET/DELETE /api/chat/history/{session_id}`
- Streaming chat panel: new SSE endpoint `POST /api/chat/stream` (start/delta/done/error events); frontend renders deltas live with fallback to blocking `/api/chat`; session id persisted in localStorage

**Status:** Completed

### Terminal Console & Navigation Fixes (2026-08-20)

**Document:** [`docs/changes/003-terminal-view-and-nav-fixes.md`](docs/changes/003-terminal-view-and-nav-fixes.md)

**Summary:**
- Added interactive terminal console view (Build category) with commands for change sets, plans, tasks, and lifecycles
- Fixed navigation dropdown hover persistence — menus no longer disappear when moving mouse to items
- Added page back button with navigation history tracking
- Added dev activity logging — CLI work now appears in DEV TASKS dashboard panel
- Added `POST /api/dev/log` endpoint for logging dev activity to audit trail

**Status:** Completed

### Chat Pipeline (2026-08-20)

**Document:** [`docs/implementation/06-chat-pipeline-progress.md`](docs/implementation/06-chat-pipeline-progress.md)

**Summary:**
- Fixed Ollama qwen3:4b thinking leak by using `think: true`
- Updated system prompt to engineering-focused responses
- Filtered dashboard activity to development events only
- Created `/api/chat` and `/api/chat/delegate` endpoints

**Status:** Core functionality working, minor issues remaining (Ollama connection timeout)

