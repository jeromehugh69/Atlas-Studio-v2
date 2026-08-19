"""Compliance evidence collection and packaging."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class EvidenceCollector:
    def __init__(self):
        self.evidence_store: list[dict[str, Any]] = []

    def collect_audit_event(self, event: dict[str, Any]) -> dict[str, Any]:
        evidence = {
            "type": "audit_event",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": event.get("action"),
            "actor": event.get("actor"),
            "target": event.get("target"),
            "outcome": event.get("outcome"),
            "hash": self._compute_hash(event),
        }
        self.evidence_store.append(evidence)
        return evidence

    def collect_change_set(self, change_set: dict[str, Any]) -> dict[str, Any]:
        evidence = {
            "type": "change_set",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "change_set_id": change_set.get("id"),
            "files": change_set.get("files"),
            "status": change_set.get("status"),
            "approvals": change_set.get("approvals", []),
            "hash": self._compute_hash(change_set),
        }
        self.evidence_store.append(evidence)
        return evidence

    def collect_approval(self, approval: dict[str, Any]) -> dict[str, Any]:
        evidence = {
            "type": "approval",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "approval_id": approval.get("id"),
            "action": approval.get("action"),
            "target": approval.get("target"),
            "outcome": approval.get("outcome"),
            "hash": self._compute_hash(approval),
        }
        self.evidence_store.append(evidence)
        return evidence

    def collect_security_scan(self, scan_result: dict[str, Any]) -> dict[str, Any]:
        evidence = {
            "type": "security_scan",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scan_type": scan_result.get("scan_type"),
            "findings": scan_result.get("findings"),
            "severity_summary": scan_result.get("severity_summary"),
            "hash": self._compute_hash(scan_result),
        }
        self.evidence_store.append(evidence)
        return evidence

    def collect_test_result(self, test_result: dict[str, Any]) -> dict[str, Any]:
        evidence = {
            "type": "test_result",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_name": test_result.get("test_name"),
            "passed": test_result.get("passed"),
            "exit_code": test_result.get("exit_code"),
            "output": test_result.get("output"),
            "hash": self._compute_hash(test_result),
        }
        self.evidence_store.append(evidence)
        return evidence

    def collect_lifecycle_stage(
        self, stage: str, lifecycle_id: str, details: dict[str, Any]
    ) -> dict[str, Any]:
        evidence = {
            "type": "lifecycle_stage",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "lifecycle_id": lifecycle_id,
            "details": details,
            "hash": self._compute_hash({"stage": stage, "id": lifecycle_id, **details}),
        }
        self.evidence_store.append(evidence)
        return evidence

    def package_evidence(
        self, framework: str, control_ids: list[str]
    ) -> dict[str, Any]:
        relevant = []
        for evidence in self.evidence_store:
            relevant.append(evidence)

        return {
            "package": {
                "framework": framework,
                "control_ids": control_ids,
                "evidence_count": len(relevant),
                "evidence": relevant,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "integrity_hash": self._compute_hash(relevant),
            }
        }

    def get_evidence_summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for evidence in self.evidence_store:
            t = evidence.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_evidence": len(self.evidence_store),
            "by_type": by_type,
        }

    def _compute_hash(self, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()
