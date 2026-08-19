from uuid import uuid4

import pytest

from atlas_studio.layers.approvals import ApprovalError, ApprovalService
from atlas_studio.layers.task_queue import DurablePriorityQueue
from atlas_studio.models import ProtectedActionRequest


def test_scoped_approval_is_exact_and_single_use():
    records = {}
    service = ApprovalService(records)
    request = ProtectedActionRequest(
        action="file_write",
        purpose="Apply the approved implementation change",
        target="src/example.py",
        actor="Forge",
        payload={"content": "print('safe')", "workspace_id": "workspace-1"},
    )
    approval = service.request(request)
    service.decide(approval.id, "approved", passcode_verified=True)

    with pytest.raises(ApprovalError, match="does not match"):
        service.consume(
            approval.id,
            action="file_write",
            target="src/example.py",
            payload={"content": "print('changed')", "workspace_id": "workspace-1"},
        )

    consumed = service.consume(
        approval.id,
        action="file_write",
        target="src/example.py",
        payload=request.payload,
    )
    assert consumed.status == "used"
    with pytest.raises(ApprovalError, match="not active"):
        service.consume(approval.id, action="file_write", target=request.target, payload=request.payload)


@pytest.mark.asyncio
async def test_fallback_queue_dispatches_critical_before_normal():
    queue = DurablePriorityQueue()
    normal_id, critical_id = uuid4(), uuid4()
    await queue.enqueue(normal_id, "normal", False)
    await queue.enqueue(critical_id, "critical", True)

    first = await queue.dequeue()
    second = await queue.dequeue()

    assert first.task_id == critical_id
    assert first.user_authorized is True
    assert second.task_id == normal_id

