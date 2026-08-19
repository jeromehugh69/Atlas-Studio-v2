"""OSCAL (Open Security Controls Assessment Language) document generation."""

from datetime import datetime, timezone
from typing import Any


SOC2_CONTROLS = {
    "CC6.1": {
        "name": "Logical Access Security",
        "description": "The entity implements logical access security measures to protect against threats from sources outside its system boundaries.",
        "evidence_types": ["agent_permissions", "approval_tokens", "security_scans"],
    },
    "CC6.2": {
        "name": "Access Authentication",
        "description": "Prior to issuing system credentials and granting system access, the entity registers and authorizes new internal and external users.",
        "evidence_types": ["approval_challenges", "user_authorization"],
    },
    "CC7.2": {
        "name": "Monitoring",
        "description": "The entity monitors system components for anomalies indicative of malicious acts, natural disasters, and errors affecting the entity's ability to meet its objectives.",
        "evidence_types": ["audit_events", "security_scans", "system_health"],
    },
    "CC7.3": {
        "name": "Incident Response",
        "description": "The entity evaluates security events to determine whether they could or have resulted in a failure of the entity to meet its objectives.",
        "evidence_types": ["audit_events", "incident_reports"],
    },
    "CC8.1": {
        "name": "Change Management",
        "description": "The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements changes to infrastructure, data, software, and procedures to meet its objectives.",
        "evidence_types": ["change_sets", "approvals", "test_results", "lifecycle_stages"],
    },
}

ISO27001_CONTROLS = {
    "A.12.1.4": {
        "name": "Control of Operational Software",
        "description": "Procedures should be implemented to control changes to operational software.",
        "evidence_types": ["change_sets", "approvals", "lifecycle_stages"],
    },
    "A.14.2.5": {
        "name": "Secure System Engineering Principles",
        "description": "Principles for engineering secure systems should be established, documented, maintained, and applied to any information system implementation.",
        "evidence_types": ["security_scans", "agent_permissions", "sandbox_config"],
    },
    "A.9.2.1": {
        "name": "User Registration and Authorization",
        "description": "A formal user registration and de-registration process should be implemented to enable assignment of access rights.",
        "evidence_types": ["approval_challenges", "user_authorization"],
    },
    "A.12.4.1": {
        "name": "Event Logging",
        "description": "Event logs recording user activities, exceptions, faults, and information security events should be produced, kept, and regularly reviewed.",
        "evidence_types": ["audit_events", "hash_chain"],
    },
}

NIST_CSF_CONTROLS = {
    "PR.DS-1": {
        "name": "Data-at-rest Protection",
        "description": "Data-at-rest is protected.",
        "evidence_types": ["encryption_status", "data_classification"],
    },
    "PR.AC-1": {
        "name": "Identity Management",
        "description": "Identities and credentials are issued, managed, verified, revoked, and archived.",
        "evidence_types": ["approval_challenges", "user_authorization"],
    },
    "PR.AC-4": {
        "name": "Access Permissions",
        "description": "Access permissions and authorizations are managed, incorporating the principles of least privilege and separation of duties.",
        "evidence_types": ["agent_permissions", "approval_tokens"],
    },
    "DE.CM-1": {
        "name": "Network Monitoring",
        "description": "The network is monitored to detect potential cybersecurity events.",
        "evidence_types": ["security_scans", "system_health"],
    },
    "DE.AE-2": {
        "name": "Anomaly Analysis",
        "description": "Detected events are analyzed to better understand attacks and gaps in defenses.",
        "evidence_types": ["audit_events", "security_scans"],
    },
    "RS.AN-1": {
        "name": "Incident Investigation",
        "description": "Investigations are conducted to ensure effective response and support recovery activities.",
        "evidence_types": ["audit_events", "incident_reports"],
    },
    "RC.RP-1": {
        "name": "Recovery Plan Execution",
        "description": "Recovery plan is executed during or after a cybersecurity incident.",
        "evidence_types": ["lifecycle_stages", "deployment_records"],
    },
}


class OSCALGenerator:
    @staticmethod
    def generate_ssp(
        system_name: str,
        audit_events: list[dict[str, Any]],
        controls: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        all_controls = {}
        all_controls.update(SOC2_CONTROLS)
        all_controls.update(ISO27001_CONTROLS)
        all_controls.update(NIST_CSF_CONTROLS)

        if controls:
            all_controls.update(controls)

        implemented_controls = []
        for ctrl_id, ctrl_info in all_controls.items():
            evidence_count = sum(
                1
                for event in audit_events
                if any(
                    et in event.get("action", "")
                    for et in ctrl_info.get("evidence_types", [])
                )
            )
            implemented_controls.append(
                {
                    "control-id": ctrl_id,
                    "name": ctrl_info["name"],
                    "description": ctrl_info["description"],
                    "status": "implemented" if evidence_count > 0 else "planned",
                    "evidence-count": evidence_count,
                }
            )

        return {
            "system-security-plan": {
                "metadata": {
                    "title": f"{system_name} System Security Plan",
                    "last-updated": datetime.now(timezone.utc).isoformat(),
                    "version": "1.0.0",
                },
                "control-implementation": {
                    "implemented-controls": implemented_controls,
                    "frameworks": [
                        {
                            "name": "SOC 2 Type 2",
                            "controls": [
                                c
                                for c in implemented_controls
                                if c["control-id"].startswith("CC")
                            ],
                        },
                        {
                            "name": "ISO 27001",
                            "controls": [
                                c
                                for c in implemented_controls
                                if c["control-id"].startswith("A.")
                            ],
                        },
                        {
                            "name": "NIST CSF",
                            "controls": [
                                c
                                for c in implemented_controls
                                if any(
                                    c["control-id"].startswith(p)
                                    for p in ["PR.", "DE.", "RS.", "RC."]
                                )
                            ],
                        },
                    ],
                },
            }
        }

    @staticmethod
    def get_control_by_id(control_id: str) -> dict[str, Any] | None:
        all_controls = {}
        all_controls.update(SOC2_CONTROLS)
        all_controls.update(ISO27001_CONTROLS)
        all_controls.update(NIST_CSF_CONTROLS)
        return all_controls.get(control_id)

    @staticmethod
    def list_all_controls() -> dict[str, Any]:
        all_controls = {}
        all_controls.update(SOC2_CONTROLS)
        all_controls.update(ISO27001_CONTROLS)
        all_controls.update(NIST_CSF_CONTROLS)
        return all_controls
