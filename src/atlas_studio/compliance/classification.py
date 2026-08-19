"""Data classification for compliance."""

from enum import Enum
from typing import Any


class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


CLASSIFICATION_RULES: dict[str, DataClassification] = {
    "user_prompt": DataClassification.CONFIDENTIAL,
    "model_output": DataClassification.INTERNAL,
    "audit_event": DataClassification.RESTRICTED,
    "agent_request": DataClassification.CONFIDENTIAL,
    "agent_response": DataClassification.INTERNAL,
    "change_set": DataClassification.CONFIDENTIAL,
    "approval_token": DataClassification.RESTRICTED,
    "api_key": DataClassification.RESTRICTED,
    "session_token": DataClassification.RESTRICTED,
    "file_upload": DataClassification.CONFIDENTIAL,
    "plan_decision": DataClassification.CONFIDENTIAL,
    "test_result": DataClassification.INTERNAL,
    "deployment_config": DataClassification.RESTRICTED,
    "security_scan": DataClassification.RESTRICTED,
    "compliance_evidence": DataClassification.RESTRICTED,
}


class DataClassifier:
    def __init__(self, custom_rules: dict[str, DataClassification] | None = None):
        self.rules = {**CLASSIFICATION_RULES, **(custom_rules or {})}

    def classify(self, action: str) -> DataClassification:
        for pattern, classification in self.rules.items():
            if pattern in action:
                return classification
        return DataClassification.INTERNAL

    def requires_encryption(self, action: str) -> bool:
        classification = self.classify(action)
        return classification in (
            DataClassification.CONFIDENTIAL,
            DataClassification.RESTRICTED,
        )

    def get_classification_label(self, action: str) -> str:
        return self.classify(action).value

    def audit_retention_days(self, action: str) -> int:
        classification = self.classify(action)
        retention = {
            DataClassification.PUBLIC: 90,
            DataClassification.INTERNAL: 365,
            DataClassification.CONFIDENTIAL: 730,
            DataClassification.RESTRICTED: 2555,
        }
        return retention.get(classification, 365)
