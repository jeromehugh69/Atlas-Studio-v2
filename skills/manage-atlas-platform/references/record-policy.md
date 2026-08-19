# Atlas record policy

| Record | Source of truth | User action | Protection |
|---|---|---|---|
| Profile display | Local browser profile | Edit in Settings | Local-only; not an identity credential |
| Library | Existing tools, skills, sources, and plans | Open the owning collection | Index only; never duplicate records |
| Agent metadata | `/api/agents` | Edit agent | One-time approval |
| Agent permissions | Agent tool list | Toggle or edit tools | One-time approval; Atlas mutating tools prohibited |
| Knowledge source | Approved source catalog | Request a change | Provenance review required |
| Tool | Tool catalog and library changes | Request access or catalog change | Security review; no silent grant |
| Project | Plan + workspace + lifecycle | Open or request plan | Plan and lifecycle gates |
| Environment placement | Development lifecycle | Drag or select a destination lane | User reason, exact one-time approval, and override audit required |
| Plugin | Bundled skill manifest | Inspect `SKILL.md` | Workspace is read-only to Atlas; edit through Forge |
| Workspace file | Mounted project | Open in Code; request Forge change | Diff, approval, test, and commit gates |
| Analytics | Runtime and audit data | Drill into source record | Computed; never directly editable |
| Runtime setting | Environment/configuration | Review in Settings | Restart and validation may be required |

All changes must preserve auditability, workspace containment, and deny-by-default external access.
