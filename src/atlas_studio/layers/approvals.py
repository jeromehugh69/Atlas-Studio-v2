from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from uuid import UUID

from ..models import ExternalActionApproval, ProtectedActionRequest


class ApprovalError(RuntimeError):
    pass


class ApprovalService:
    """Deterministic one-time approvals; models cannot approve themselves."""

    def __init__(self, records: dict[UUID, ExternalActionApproval]):
        self.records = records

    @staticmethod
    def fingerprint(action: str, target: str, payload: dict) -> str:
        canonical = json.dumps(
            {"action": action, "target": target, "payload": payload},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def request(self, body: ProtectedActionRequest) -> ExternalActionApproval:
        now = datetime.now(timezone.utc)
        record = ExternalActionApproval(
            action=body.action, purpose=body.purpose, target=body.target, actor=body.actor,
            payload=body.payload, action_hash=self.fingerprint(body.action, body.target, body.payload),
            query=str(body.payload.get("query", "")),
            allowed_domains=list(body.payload.get("allowed_domains", [])),
            expires_at=now + timedelta(minutes=body.ttl_minutes),
        )
        self.records[record.id] = record
        return record

    def decide(self, approval_id: UUID, decision: str, *, passcode_verified: bool) -> ExternalActionApproval:
        record = self.records.get(approval_id)
        if not record:
            raise ApprovalError("approval request not found")
        if record.status != "pending":
            raise ApprovalError("approval request already has a decision")
        if not passcode_verified:
            raise ApprovalError("a valid local approval passcode is required")
        record.status = decision
        record.decided_at = datetime.now(timezone.utc)
        return record

    def consume(self, approval_id: UUID, *, action: str, target: str, payload: dict) -> ExternalActionApproval:
        record = self.records.get(approval_id)
        if not record:
            raise ApprovalError("approval request not found")
        now = datetime.now(timezone.utc)
        if record.status != "approved":
            raise ApprovalError("approval is not active")
        if record.expires_at <= now:
            record.status = "expired"
            raise ApprovalError("approval has expired")
        fingerprint = self.fingerprint(action, target, payload)
        if not hmac.compare_digest(record.action_hash, fingerprint):
            raise ApprovalError("approved action does not match the requested payload")
        record.status = "used"
        record.used_at = now
        return record
