from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from .lifecycle_catalog import agent_workflow_definitions


try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # Keeps source checkouts usable until dependencies are installed.
    END = START = StateGraph = None

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    AsyncPostgresSaver = None


class AgentWorkflowState(TypedDict, total=False):
    run_id: str
    task_id: str
    agent_id: str
    agent_name: str
    prompt: str
    model: str
    tools: list[str]
    requires_authorization: bool
    user_authorized: bool
    risk_tier: int
    status: str
    output: str
    error: str | None
    plan_id: str | None
    workspace_id: str | None
    grounding_status: str
    grounding_issues: list[str]
    evidence_refs: list[str]


ModelRunner = Callable[[AgentWorkflowState], Awaitable[dict[str, Any]]]


WORKFLOW_DEFINITIONS = [
    {
        "id": "governed-agent-task",
        "name": "Governed agent task",
        "version": 1,
        "owner": "Atlas",
        "status": "active",
        "nodes": ["policy", "model", "complete"],
        "description": "Universal policy-first workflow used for local agent responses.",
    },
    {
        "id": "software-feature-delivery",
        "name": "Software feature delivery",
        "version": 1,
        "owner": "Forge",
        "status": "designed",
        "nodes": ["plan", "approve", "implement", "qa", "security", "release"],
        "description": "User-controlled implementation with quality and security gates.",
    },
    {
        "id": "security-remediation",
        "name": "Security remediation",
        "version": 1,
        "owner": "Sentinel",
        "status": "designed",
        "nodes": ["verify", "approve", "fix", "test", "retest", "release"],
        "description": "Evidence-based remediation with independent retesting.",
    },
    {
        "id": "research-to-decision",
        "name": "Research to decision",
        "version": 1,
        "owner": "Sage",
        "status": "designed",
        "nodes": ["frame", "research", "compare", "review", "decide"],
        "description": "Primary-source research routed through architecture, security, and legal review.",
    },
    {
        "id": "research-and-development-delivery",
        "name": "Research and development delivery",
        "version": 1,
        "owner": "Sage",
        "status": "designed",
        "nodes": [
            "intake", "scope", "research-plan", "egress-approval",
            "primary-source-research", "option-analysis", "prototype-plan",
            "user-approval", "isolated-prototype", "qa-validation",
            "security-legal-review", "sandbox-evaluation", "decision-record",
        ],
        "agents": ["Atlas", "Sage", "Blueprint", "Forge", "Quanta", "Sentinel", "Counsel"],
        "gates": ["external research", "prototype implementation", "sandbox promotion", "production implementation"],
        "outputs": ["research brief", "source register", "architecture options", "prototype", "test evidence", "risk decision"],
        "description": "Turns an approved research question into sourced findings, architecture options, an isolated Forge prototype, independent validation, and a user-owned implementation decision.",
    },
    *agent_workflow_definitions(),
]


class LangGraphOrchestrator:
    """Small orchestration boundary around LangGraph OSS.

    The web layer supplies one model runner.  Policy and completion remain
    deterministic graph nodes, making the model only one step in a governed
    workflow instead of the workflow controller.
    """

    def __init__(self, database_url: str, model_runner: ModelRunner):
        self.database_url = database_url
        self.model_runner = model_runner
        self.graph = None
        self.checkpointer = None
        self._checkpointer_context = None
        self.durable = False

    async def initialize(self, database_available: bool) -> None:
        if StateGraph is None:
            return
        if database_available and AsyncPostgresSaver is not None:
            try:
                self._checkpointer_context = AsyncPostgresSaver.from_conn_string(self.database_url)
                self.checkpointer = await self._checkpointer_context.__aenter__()
                await self.checkpointer.setup()
                self.durable = True
            except Exception:
                self.checkpointer = None
                self.durable = False
                if self._checkpointer_context is not None:
                    try:
                        await self._checkpointer_context.__aexit__(None, None, None)
                    except Exception:
                        pass
                    self._checkpointer_context = None

        builder = StateGraph(AgentWorkflowState)
        builder.add_node("policy", self._policy_node)
        builder.add_node("model", self._model_node)
        builder.add_node("complete", self._complete_node)
        builder.add_edge(START, "policy")
        builder.add_conditional_edges("policy", self._after_policy, {"model": "model", "end": END})
        builder.add_edge("model", "complete")
        builder.add_edge("complete", END)
        self.graph = builder.compile(checkpointer=self.checkpointer)

    async def close(self) -> None:
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
            self._checkpointer_context = None

    async def run(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if self.graph is None:
            policy = self._policy_node(state)
            state.update(policy)
            if self._after_policy(state) == "end":
                return state
            state.update(await self._model_node(state))
            state.update(self._complete_node(state))
            return state
        return await self.graph.ainvoke(
            state,
            config={"configurable": {"thread_id": state["run_id"]}},
        )

    def status(self) -> dict[str, Any]:
        return {
            "engine": "LangGraph OSS",
            "available": StateGraph is not None,
            "durable_checkpoints": self.durable,
            "checkpoint_store": "PostgreSQL" if self.durable else "process fallback",
            "definitions": WORKFLOW_DEFINITIONS,
        }

    @staticmethod
    def _policy_node(state: AgentWorkflowState) -> dict[str, Any]:
        if state.get("requires_authorization") and not state.get("user_authorized"):
            return {"status": "awaiting_approval", "error": "Explicit user authorization is required"}
        return {"status": "running", "error": None}

    @staticmethod
    def _after_policy(state: AgentWorkflowState) -> str:
        return "end" if state.get("status") == "awaiting_approval" else "model"

    async def _model_node(self, state: AgentWorkflowState) -> dict[str, Any]:
        return await self.model_runner(state)

    @staticmethod
    def _complete_node(state: AgentWorkflowState) -> dict[str, Any]:
        if state.get("status") in {"failed", "cancelled"}:
            return {}
        return {"status": "completed"}
