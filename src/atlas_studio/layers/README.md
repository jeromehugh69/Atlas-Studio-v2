# Atlas Studio layers

Atlas Studio is being reorganized behind explicit dependency boundaries:

1. `experience` — browser pages, voice, workspace, metrics, and approvals.
2. `api` — FastAPI request/response and WebSocket transport.
3. `orchestration` — LangGraph state, workflow definitions, routing, and checkpoints.
4. `security` — tool policy, risk classification, authorization, and posture.
5. `agents` — named agent roles and their workflow assignments.
6. `intelligence` — provider-neutral models, memory, speech, and optional media.
7. `execution` — read-only tools and isolated sandbox workers.
8. `data` — PostgreSQL/pgvector, Redis, audit, and artifacts.
9. `operations` — health, metrics, cancellation, backup, and recovery.

The transition is incremental.  `main.py` remains the composition root while
policy and orchestration move into these modules first.

