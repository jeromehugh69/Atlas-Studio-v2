# Atlas Studio — Delegation Architecture

End-to-end reference for how user requests flow through the governed multi-agent system, from intake to production commit.

---

## 1. System Overview

```mermaid
graph TB
    subgraph UserLayer["User Layer"]
        U[Engineer]
    end

    subgraph FrontendLayer["Frontend"]
        CH[Chat Feed]
        DL[Delegation Card]
        DT[Dev Tasks Panel]
        WS["WebSocket (live)"]
    end

    subgraph APILayer["FastAPI Server"]
        INTAKE["POST /api/atlas/intake"]
        CHAT["POST /api/chat"]
        DELEG["POST /api/chat/delegate"]
        TASKS["POST /api/tasks"]
        PLANS["POST /api/plans"]
        CS["POST /api/change-sets/*"]
        LC["POST /api/lifecycles/*"]
        APR["POST /api/approvals/*"]
    end

    subgraph AgentLayer["Agent Pool"]
        ATLAS["Atlas\n(read-only orchestrator)"]
        FORGE["Forge\n(implementation)"]
        QUANTA["Quanta\n(QA testing)"]
        SENTINEL["Sentinel\n(security)"]
        VERITY["Verity\n(compliance)"]
        SAGE["Sage\n(research)"]
        RELEASE["Release\n(devops)"]
    end

    subgraph InfraLayer["Infrastructure"]
        OLLAMA["Ollama\nqwen3:4b"]
        PG["SQLite / PostgreSQL"]
        REDIS["In-Memory Queue"]
        WORKER["Implementation Worker\n(isolated sandbox)"]
        GIT["Git Repository"]
    end

    U --> CH
    CH --> INTAKE
    CH --> CHAT
    CH --> DELEG
    DL --> DELEG
    DT --> TASKS
    WS --> CH
    WS --> DT

    INTAKE --> ATLAS
    CHAT --> ATLAS
    DELEG --> FORGE
    DELEG --> QUANTA
    DELEG --> SENTINEL
    DELEG --> VERITY
    DELEG --> SAGE
    DELEG --> RELEASE
    TASKS --> ATLAS

    ATLAS --> OLLAMA
    FORGE --> OLLAMA
    QUANTA --> OLLAMA
    SENTINEL --> OLLAMA

    FORGE --> WORKER
    QUANTA --> WORKER
    WORKER --> GIT

    PLANS --> PG
    CS --> PG
    LC --> PG
    APR --> PG
```

---

## 2. Vertical Swimlane — Agent Responsibilities

```mermaid
graph TD
    subgraph USER["User / Engineer"]
        U1[Submits request]
        U2[Reviews diff]
        U3[Enters passcode]
        U4[Approves plan]
        U5[Approves commit]
    end

    subgraph ATLAS["Atlas — Orchestrator"]
        A1[Receives intake]
        A2[Classifies intent]
        A3[Routes to agent]
        A4[Streams response]
        A5[Emits delegation signal]
    end

    subgraph FORGE["Forge — Implementation"]
        F1[Inspects workspace]
        F2[Reads files]
        F3[Proposes change set]
        F4[Computes diffs]
    end

    subgraph QUANTA["Quanta — QA"]
        Q1[Runs pytest]
        Q2[Validates output]
        Q3[Records evidence]
    end

    subgraph SENTINEL["Sentinel — Security"]
        S1[Scans for vulnerabilities]
        S2[Validates boundaries]
        S3[Records security evidence]
    end

    subgraph VERITY["Verity — Compliance"]
        V1[Maps SOC2/ISO/NIST controls]
        V2[Verifies audit chain]
        V3[Records compliance evidence]
    end

    subgraph RELEASE["Release — DevOps"]
        R1[Validates sandbox]
        R2[Promotes to production]
        R3[Monitors deployment]
    end

    U1 --> A1
    A1 --> A2
    A2 --> A3
    A3 -->|delegation signal| A5
    A5 --> F1
    F1 --> F2
    F2 --> F3
    F3 --> U2
    U2 -->|approve| U3
    U3 -->|passcode valid| Q1
    Q1 --> Q2
    Q2 --> S1
    S1 --> S2
    S2 --> V1
    V1 --> V2
    V2 --> R1
    R1 --> U4
    U4 --> R2
    R2 --> U5
    U5 -->|final passcode| R3
```

---

## 3. End-to-End Request Lifecycle

```mermaid
sequenceDiagram
    participant U as Engineer
    participant FE as Frontend
    participant API as FastAPI
    participant AT as Atlas
    participant FG as Forge
    participant QN as Quanta
    participant SN as Sentinel
    participant VR as Verity
    participant RL as Release
    participant WK as Worker
    participant DB as Database

    U->>FE: Types request in chat
    FE->>API: POST /api/atlas/intake
    API->>AT: Classifies intent
    AT-->>API: Returns approval challenge
    API-->>FE: { challenge_code: "482917" }
    FE-->>U: Shows passcode dialog
    U->>FE: Enters 482917
    FE->>API: POST /api/atlas/intake/{id}/approve
    API->>DB: Creates Plan + Lifecycle
    API->>FG: Lifecycle review task
    API->>QN: Lifecycle review task
    API->>SN: Lifecycle review task
    API->>VR: Lifecycle review task
    API-->>FE: WebSocket lifecycle.guide
    FE-->>U: Shows review cards

    U->>FE: Approves plan
    FE->>API: POST /api/plans/{id}/decision
    API->>WK: Creates isolated workspace
    API->>FG: Creates implementation task
    API->>DB: Plan → in_progress

    loop Forge Tool Loop (up to 8 rounds)
        FG->>WK: list_workspace
        WK-->>FG: file tree
        FG->>WK: read_file
        WK-->>FG: file contents
        FG->>WK: propose_change_set
        WK-->>FG: ChangeSet with diffs
    end

    API-->>FE: WebSocket forge.change_set
    FE-->>U: Shows diff review card

    U->>FE: Approves write
    FE->>API: POST /api/change-sets/{id}/apply
    API->>WK: apply_change_set
    API->>DB: status → applied

    U->>FE: Approves test
    FE->>API: POST /api/change-sets/{id}/test
    API->>WK: python -m pytest -q
    WK-->>API: exit 0, stdout
    API->>DB: status → tests_passed

    U->>FE: Approves commit
    FE->>API: POST /api/chat/commit
    API-->>FE: approval challenge
    U->>FE: Enters passcode
    FE->>API: POST /api/chat/commit/execute
    API->>WK: git commit
    WK-->>API: branch + commit hash
    API->>DB: status → committed

    API->>RL: Sandbox promotion
    RL->>SN: Security validation
    RL->>QN: QA validation
    SN-->>RL: evidence passed
    QN-->>RL: evidence passed
    RL-->>API: sandbox evidence

    U->>FE: Approves production
    FE->>API: POST /api/lifecycles/{id}/transition
    API->>DB: stage → production, completed
```

---

## 4. Delegation Signal Mechanism

Atlas communicates delegation via a structured text signal embedded in its LLM response:

```
[DELEGATE:Forge:Implement a dark mode toggle in the settings panel]
```

### Signal Flow

```mermaid
flowchart LR
    A["Atlas LLM response"] --> B["Regex parser\n\\[DELEGATE:(\\w+):(.*?)\\]"]
    B --> C{"Agent found?"}
    C -->|Yes| D["Return delegation object\n{ agent, prompt }"]
    C -->|No| E["Return direct response"]
    D --> F["Frontend shows delegation card"]
    F --> G["POST /api/chat/delegate"]
    G --> H["SecurityPolicy.task_policy()"]
    H -->|"allowed"| I["Create task, enqueue"]
    H -->|"denied"| J["Return 403"]
    I --> K["WebSocket task.progress events"]
    K --> L["Frontend updates card status"]
```

### Agent Routing Table

| Signal Agent | Actual Agent | Capability | Required Approval |
|-------------|-------------|-----------|-------------------|
| `Forge` | Forge | Implementation, file writes, code execution | Yes (`user_authorized=true`) |
| `Quanta` | Quanta | QA testing, test execution | Yes |
| `Sentinel` | Sentinel | Security scanning, boundary validation | Yes |
| `Verity` | Verity | Compliance review, SOC2/ISO/NIST | Yes |
| `Sage` | Sage | Research, web search (via SearXNG) | Conditional |
| `Release` | Release | DevOps, deployment, monitoring | Yes |

---

## 5. Approval Gates — Every Decision Point

```mermaid
flowchart TD
    START["User Request"] --> INTAKE["Plan Intake\nPOST /api/atlas/intake"]
    INTAKE --> CHALLENGE1["6-digit passcode\n5-min TTL, 5 attempts"]
    CHALLENGE1 --> PLAN["Plan Created\nstatus: pending_approval"]
    PLAN --> REVIEWS["Agent Reviews\nForge, Sage, Sentinel,\nBlueprint, Verity"]
    REVIEWS --> APPROVE_PLAN["User Approves Plan\nPOST /api/plans/{id}/decision"]
    APPROVE_PLAN --> WORKSPACE["Isolated Workspace\ncreated via Worker"]
    WORKSPACE --> FORGE_IMPL["Forge Implements\nChange Set proposed"]
    FORGE_IMPL --> DIFF_REVIEW["User Reviews Diff\nPOST /api/change-sets/{id}/apply"]
    DIFF_REVIEW --> CHALLENGE2["6-digit passcode"]
    CHALLENGE2 --> WRITE["Write Applied\nstatus: applied"]
    WRITE --> TEST_APPROVE["User Approves Test\nPOST /api/change-sets/{id}/test"]
    TEST_APPROVE --> CHALLENGE3["6-digit passcode"]
    CHALLENGE3 --> TEST["pytest Run\nstatus: tests_passed"]
    TEST --> COMMIT_APPROVE["User Approves Commit\nPOST /api/chat/commit"]
    COMMIT_APPROVE --> CHALLENGE4["6-digit passcode"]
    CHALLENGE4 --> COMMIT["Git Commit\nstatus: committed"]
    COMMIT --> SANDBOX["Sandbox Validation\nSentinel + Quanta"]
    SANDBOX --> PROD_APPROVE["User Approves Production\nPOST /api/lifecycles/{id}/transition"]
    PROD_APPROVE --> CHALLENGE5["6-digit passcode"]
    CHALLENGE5 --> PRODUCTION["Production Deployed\nstage: production"]

    style CHALLENGE1 fill:#1a3a4a,stroke:#4ae68a,color:#b9dce6
    style CHALLENGE2 fill:#1a3a4a,stroke:#4ae68a,color:#b9dce6
    style CHALLENGE3 fill:#1a3a4a,stroke:#4ae68a,color:#b9dce6
    style CHALLENGE4 fill:#1a3a4a,stroke:#4ae68a,color:#b9dce6
    style CHALLENGE5 fill:#1a3a4a,stroke:#4ae68a,color:#b9dce6
```

---

## 6. Change Set Lifecycle

```mermaid
stateDiagram-v2
    [*] --> PendingReview: Forge proposes change set
    PendingReview --> Applied: User approves write\nPOST /api/change-sets/{id}/apply
    Applied --> TestsPassed: pytest exits 0\nPOST /api/change-sets/{id}/test
    Applied --> Failed: pytest exits non-0
    TestsPassed --> Committed: Git commit created\nPOST /api/change-sets/{id}/commit
    TestsPassed --> Rejected: User rejects
    PendingReview --> Rejected: User rejects
    Failed --> Applied: Re-apply after fix
    Committed --> [*]
    Rejected --> [*]
```

### ChangeSet Fields

| Field | Description |
|-------|-------------|
| `id` | UUID — unique identifier |
| `task_id` | Linked Forge task |
| `plan_id` | Linked Plan |
| `workspace_id` | Isolated workspace |
| `title` | Human-readable title |
| `summary` | What changed and why |
| `files[]` | Array of `ChangeSetFile` (path, before_sha256, after_sha256, diff) |
| `combined_diff` | Full unified diff |
| `status` | pending_review → applied → tests_passed → committed |
| `test_result` | { exit_code, stdout, stderr } |
| `branch` | Git branch name (atlas/...) |
| `commit` | Git commit hash |

---

## 7. Lifecycle Stages — The 10-Stage Pipeline

```mermaid
graph LR
    subgraph Stage1["1. Request"]
        S1A[User submits change request]
    end
    subgraph Stage2["2. Recommendation"]
        S2A[Forge proposes solution]
    end
    subgraph Stage3["3. Reviews"]
        S3A[Forge, Sage, Blueprint,\nSentinel, Verity review]
    end
    subgraph Stage4["4. Authorization"]
        S4A[User approves plan\nwith passcode]
    end
    subgraph Stage5["5. Implementation"]
        S5A[Forge creates change set\nin isolated workspace]
    end
    subgraph Stage6["6. Diff Review"]
        S6A[User reviews combined diff\napproves file write]
    end
    subgraph Stage7["7. Test"]
        S7A[Quanta runs pytest\nrecords evidence]
    end
    subgraph Stage8["8. Sandbox"]
        S8A[Sentinel + Quanta\nvalidate in sandbox]
    end
    subgraph Stage9["9. Production"]
        S9A[User authorizes\nproduction promotion]
    end
    subgraph Stage10["10. Monitoring"]
        S10A[Release + Sentinel\nmonitor deployment]
    end

    Stage1 --> Stage2 --> Stage3 --> Stage4 --> Stage5 --> Stage6 --> Stage7 --> Stage8 --> Stage9 --> Stage10
```

### Stage Evidence Requirements

| Stage | Required Evidence | Required Approval |
|-------|------------------|-------------------|
| Development | Implementation task completed | No |
| Test | Test or security evidence passed | No |
| Sandbox | Sandbox evidence from Sentinel + Quanta | No |
| Production | Sandbox evidence + user authorization | Yes (`production_promotion`) |

---

## 8. WebSocket Event Map

```mermaid
flowchart TD
    subgraph Server["FastAPI Server"]
        B1[broadcast]
    end

    subgraph Events["Event Types"]
        E1["task.delta\n(streaming tokens)"]
        E2["task.progress\n(status changes)"]
        E3["task.delegated\n(agent handoff)"]
        E4["forge.change_set\n(created/applied/committed)"]
        E5["lifecycle.guide\n(stage transitions)"]
        E6["atlas.approval_required\n(passcode needed)"]
        E7["control.kill_switch\n(stop/start all)"]
        E8["worker.action\n(file write/test)"]
    end

    subgraph Handlers["Frontend Handlers"]
        H1["app.js\nreconcileTask()"]
        H2["app.js\naddEvent()"]
        H3["live-atlas.js\nhandleTaskEvent()"]
        H4["developer-features.js\nrefreshChangeSets()"]
        H5["developer-features.js\nrefreshLifecycleGuide()"]
        H6["terminal.js\nhandleEvent()"]
    end

    B1 --> E1
    B1 --> E2
    B1 --> E3
    B1 --> E4
    B1 --> E5
    B1 --> E6
    B1 --> E7
    B1 --> E8

    E1 --> H3
    E2 --> H1
    E2 --> H2
    E2 --> H6
    E3 --> H1
    E4 --> H4
    E4 --> H5
    E5 --> H5
    E6 --> H3
    E7 --> H2
    E8 --> H6
```

---

## 9. Security Enforcement

```mermaid
flowchart TD
    REQ["Incoming Request"] --> MITM["MITM Middleware"]
    MITM --> RATE{"Rate limit?"}
    RATE -->|Exceeded| R429["429 Too Many Requests"]
    RATE -->|OK| AUTH{"Auth check?"}
    AUTH -->|Failed| R401["401 Unauthorized"]
    AUTH -->|OK| INPUT{"Input validation?"}
    INPUT -->|Failed| R400["400 Bad Input"]
    INPUT -->|OK| POLICY{"Policy evaluation?"}
    POLICY -->|Denied| R403["403 Policy Violation"]
    POLICY -->|Allowed| ROUTE["Route to handler"]

    ROUTE --> SEC{"SecurityPolicy?"}
    SEC -->|Atlas write attempt| BLOCK["BLOCKED\nAtlas is permanently read-only"]
    SEC -->|Unauthorized impl| R409["409 Authorization Required"]
    SEC -->|Allowed| EXEC["Execute action"]

    EXEC --> AUDIT["AuditEvent recorded\nSHA-256 hash chain"]
```

### Key Security Rules

| Rule | Enforcement |
|------|-------------|
| Atlas is permanently read-only | `SecurityPolicy.validate_agent_tools()` rejects mutating tools on Atlas |
| Implementation requires authorization | `requires_user_authorization=true` enforced at API level |
| External providers blocked | Model names validated against SSRF; openai/anthropic/ etc. rejected |
| All approvals are single-use | `ApprovalService.consume()` marks as `used` after validation |
| Passcodes expire in 5 minutes | HMAC digest with TTL, max 5 attempts |
| Workspace is isolated | Each plan gets a dedicated workspace; no cross-plan access |
| Audit trail is tamper-evident | SHA-256 hash chain linking every event to its predecessor |

---

## 10. API Endpoint Reference

### Chat & Delegation

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/chat` | Direct chat with Atlas (streams response, detects delegation) |
| `POST` | `/api/chat/delegate` | Execute delegated task to named agent |
| `POST` | `/api/chat/commit` | Initiate change set commit (returns approval) |
| `POST` | `/api/chat/commit/execute` | Execute commit after approval |

### Intake & Plans

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/atlas/intake` | Intake user request; creates approval |
| `POST` | `/api/atlas/intake/{id}/approve` | Approve intake; creates Plan + reviews |
| `POST` | `/api/plans` | Create plan request (queues reviews) |
| `POST` | `/api/plans/{id}/decision` | Approve/reject plan (creates workspace + Forge task) |

### Change Sets

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/change-sets` | List change sets |
| `POST` | `/api/change-sets/{id}/apply` | Apply change set (requires approval) |
| `POST` | `/api/change-sets/{id}/test` | Run tests (requires approval) |
| `POST` | `/api/change-sets/{id}/commit` | Git commit (requires approval) |
| `DELETE` | `/api/change-sets/{id}` | Soft-delete change set |

### Lifecycles

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/lifecycles` | List all lifecycles |
| `POST` | `/api/lifecycles/{id}/transition` | Advance lifecycle stage |
| `POST` | `/api/lifecycles/{id}/override` | Override lifecycle (requires approval) |
| `GET` | `/api/lifecycle-guide` | Full lifecycle guide with stages |

### Approvals

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/approvals` | Request protected action approval |
| `POST` | `/api/approvals/{id}/decision` | Decide (approve/reject) with passcode |

### WebSocket

| Method | Path | Purpose |
|--------|------|---------|
| `WS` | `/api/ws` | Real-time event stream |

---

## 11. Data Model Relationships

```mermaid
erDiagram
    PLAN ||--o{ TASK : "has tasks"
    PLAN ||--o| LIFECYCLE : "has lifecycle"
    PLAN ||--o{ CHANGESET : "has change sets"
    PLAN ||--o{ REVIEW : "has reviews"

    TASK ||--o| PLAN : "belongs to"
    TASK }o--|| AGENT : "assigned to"

    CHANGESET ||--|| TASK : "linked to"
    CHANGESET ||--|| PLAN : "linked to"
    CHANGESET ||--|| WORKSPACE : "in workspace"

    LIFECYCLE ||--|| PLAN : "linked to"
    LIFECYCLE ||--o{ EVIDENCE : "has evidence"

    PLAN {
        uuid id PK
        string title
        string request
        uuid implementation_agent_id FK
        string status
        string recommendation
        string impact
        string test_plan
        string rollback_plan
    }

    TASK {
        uuid id PK
        string title
        string prompt
        uuid agent_id FK
        string status
        string output
        uuid plan_id FK
        uuid workspace_id FK
        string grounding_status
    }

    CHANGESET {
        uuid id PK
        uuid task_id FK
        uuid plan_id FK
        uuid workspace_id FK
        string title
        string summary
        string status
        string branch
        string commit
    }

    LIFECYCLE {
        uuid id PK
        uuid plan_id FK
        string stage
        string status
        jsonb gates
        jsonb evidence
    }

    AGENT {
        uuid id PK
        string name
        string role
        boolean read_only
        array tools
        array skills
    }

    WORKSPACE {
        uuid id PK
        uuid plan_id FK
        string status
    }
```
