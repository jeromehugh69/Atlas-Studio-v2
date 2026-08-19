# Atlas Studio security model

Atlas Studio treats models, uploads, agent output, and tool requests as untrusted. Community mode enables no external connector and emits no telemetry. Sandboxed execution must use rootless Docker or Podman, an unprivileged user, a read-only root filesystem, an empty capability set, `no-new-privileges`, explicit workspace mounts, resource limits, and no network by default.

Atlas has read-only platform visibility. The API rejects any attempt to grant Atlas file-write or code-execution permissions. Forge is the implementation agent and requires an explicitly assigned workspace. Every permission change, task, upload, cancellation, and kill-switch transition is an audit event.

The optional `avatar_generate` tool is purpose-limited: it may send one explicitly approved image only to the local image-to-3D container and save the returned GLB to artifact storage. It does not permit arbitrary paths, file edits, code execution, or external transmission. The API requires confirmation, PNG/JPEG media, a 10 MB limit, an enabled local worker, and an agent with the capability. Source images and generated models remain in local Docker volumes.

Do not expose port 8080 directly to an untrusted network. Put a locally managed authentication proxy with TLS in front of multi-user deployments. Never mount the container runtime socket into the web application; deploy a separately reviewed sandbox worker when enabling code execution.

Read-only site inspection runs inside the existing rootless worker and is restricted to `ATLAS_WORKER_SITE_ORIGINS` plus the internal Compose network. The exposed action renders page content only; it has no interaction primitives. Treat rendered page content as untrusted evidence. Any future click, typing, upload, form submission, or external navigation action must use a separate approval-gated tool and audit record.

Report vulnerabilities privately to the project maintainer. Do not include secrets or personal data in reports.
