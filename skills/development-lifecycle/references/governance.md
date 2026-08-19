# Atlas lifecycle governance

## Policies

| ID | Policy | Required control |
|---|---|---|
| POL-01 | User authority | The user owns scope, approvals, edits, rejection, deletion, and Production promotion. |
| POL-02 | Separation of duties | Atlas coordinates; Forge implements; Quanta tests; Sentinel reviews security; Verity reviews compliance; Release promotes. |
| POL-03 | Least privilege | Agents may use only assigned tools within the active workspace and environment. Forge cannot change its own permissions. |
| POL-04 | Evidence before claims | Source citations or machine evidence must support material findings and completion claims. Missing evidence is `verification_required`. |
| POL-05 | Exact approval | Writes, execution, external access, permission changes, overrides, commits, deletion, and Production promotion require a payload-bound, expiring, one-time approval. |
| POL-06 | Local-first and contained | Default to local models, deny external network access, validate uploads, isolate workspaces, and keep execution sandboxed. |
| POL-07 | Change integrity | Show the proposed change and combined diff before application. Preserve pre-change and post-change hashes and rollback instructions. |
| POL-08 | Audit completeness | Record actor, action, target, outcome, evidence, approval, timestamps, failures, overrides, and next action. |

## Procedures

### Research and development

1. Atlas turns the request into a bounded question and evidence list.
2. Sage prepares a source plan. External research pauses for user approval and uses only approved domains.
3. Blueprint, Nexus, DataCore, Interface, Counsel, Verity, or Sentinel contribute only when relevant.
4. Atlas compares findings, identifies uncertainty, and routes an evidence-backed recommendation to Forge.

### Code change

1. Forge inspects the approved workspace and proposes files, change, risks, tests, and rollback.
2. The user accepts, edits, or rejects the recommendation.
3. Forge creates a multi-file change set; the platform displays the combined diff.
4. The user accepts, edits, or rejects the diff before it is applied.
5. Forge applies only the approved payload. Any changed payload requires new approval.

### Quality and security

1. Quanta creates and runs unit, integration, regression, UI, and relevant performance checks.
2. Sentinel performs threat and security review; Verity maps applicable controls.
3. Failed or missing evidence returns the request to Forge with findings. Review agents do not silently modify code.
4. Passing results attach machine output and gate decisions to the lifecycle record.

### Environment promotion

1. Workspace holds implementation and local verification.
2. Sandbox requires passing test evidence and required reviews.
3. Production requires Sandbox evidence, rollback readiness, and exact one-time user approval.
4. A manual lane move is an override, not evidence; record the reason, approver, and resulting risk.

### Exception and deletion

1. Stop on missing scope, conflicting policies, failed evidence, expired approval, or kill-switch activation.
2. Ask one question naming the missing decision and its impact.
3. Soft-delete requests only after exact user approval; retain the audit record.

## Required lifecycle record

Every request must expose: current stage, owner, participating agents, recommendation, approvals, diff, evidence, findings, decisions, next action, timestamps, and audit status.
