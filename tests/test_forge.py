from uuid import uuid4

import pytest

from atlas_studio.layers.forge import FORGE_TOOLS, ForgeToolLoop


class ToolProvider:
    def __init__(self):
        self.calls = 0

    async def chat_with_tools(self, messages, model, tools, temperature=0.1):
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "list_workspace", "arguments": {}}}],
            }
        return {
            "role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": "propose_change_set", "arguments": {
                "title": "Add a health note", "summary": "Adds one reviewed local file.",
                "files": [{"path": "HEALTH.md", "content": "healthy\n"}],
            }}}],
        }


class PreviewWorker:
    def __init__(self):
        self.actions = []

    async def execute(self, payload):
        self.actions.append(payload)
        if payload["action"] == "list_workspace":
            return {"entries": [{"path": "README.md", "type": "file"}], "truncated": False}
        assert payload["action"] == "preview_change_set"
        return {
            "files": [{
                "path": "HEALTH.md", "content": "healthy\n", "changed": True,
                "before_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "expected_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "after_sha256": "f0a593257a1b7b5c2cf6e4dc0b79c77b40d7bca4f617f4a043110383815f0f95",
                "diff": "--- a/HEALTH.md\n+++ b/HEALTH.md\n+healthy\n",
            }],
            "combined_diff": "--- a/HEALTH.md\n+++ b/HEALTH.md\n+healthy\n",
        }


@pytest.mark.asyncio
async def test_forge_uses_only_read_and_preview_tools_to_create_reviewable_change_set():
    provider, worker = ToolProvider(), PreviewWorker()
    loop = ForgeToolLoop(provider, worker)
    task_id, plan_id, workspace_id = uuid4(), uuid4(), uuid4()

    message, change_set = await loop.run(
        prompt="Add a local health note", model="qwen3:4b", task_id=task_id,
        plan_id=plan_id, workspace_id=workspace_id,
    )

    assert [item["function"]["name"] for item in FORGE_TOOLS] == [
        "list_workspace", "read_file", "search_workspace", "propose_change_set",
    ]
    assert [item["action"] for item in worker.actions] == ["list_workspace", "preview_change_set"]
    assert change_set is not None
    assert change_set.status == "pending_review"
    assert change_set.files[0].path == "HEALTH.md"
    assert "Review the combined diff" in message


@pytest.mark.asyncio
async def test_forge_asks_for_input_without_fabricating_a_change_set():
    class QuestionProvider:
        async def chat_with_tools(self, messages, model, tools, temperature=0.1):
            return {"role": "assistant", "content": "Which authentication provider should this target?"}

    worker = PreviewWorker()
    message, change_set = await ForgeToolLoop(QuestionProvider(), worker).run(
        prompt="Change authentication", model="qwen3:4b", task_id=uuid4(),
        plan_id=uuid4(), workspace_id=uuid4(),
    )
    assert change_set is None
    assert message.endswith("?")
    assert worker.actions == []
