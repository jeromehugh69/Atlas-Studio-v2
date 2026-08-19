from uuid import UUID

import pytest

from atlas_studio.infrastructure import Infrastructure
from atlas_studio.store import DEFAULT_AGENTS


class LegacyAgentDatabase:
    def __init__(self):
        self.rows = {UUID("10000000-0000-0000-0000-000000000003"): "Sage"}

    async def fetchval(self, query, value):
        if "workspace_id" in query and "name=$1" in query:
            return next((agent_id for agent_id, name in self.rows.items() if name == value), None)
        return self.rows.get(value)

    async def execute(self, query, *args):
        self.rows[args[0]] = args[1]


@pytest.mark.asyncio
async def test_legacy_agent_ids_are_reconciled_by_name_without_overwriting_sage():
    database = LegacyAgentDatabase()
    infrastructure = Infrastructure("postgresql://unused", "redis://unused")
    infrastructure.db = database
    sentinel = next(agent for agent in DEFAULT_AGENTS if agent.name == "Sentinel").model_copy(deep=True)
    sage = next(agent for agent in DEFAULT_AGENTS if agent.name == "Sage").model_copy(deep=True)

    await infrastructure.persist_agent(sentinel)
    await infrastructure.persist_agent(sage)

    assert sage.id == UUID("10000000-0000-0000-0000-000000000003")
    assert sentinel.id != sage.id
    assert database.rows[sage.id] == "Sage"
    assert database.rows[sentinel.id] == "Sentinel"
