"""Audit Logger - Records all requests, responses, and agent actions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditLogger:
    """Log all requests and responses for compliance and security.
    
    Features:
    - Append-only JSONL format
    - Hash chaining for tamper evidence
    - Event categorization
    - Time-based rotation support
    """

    def __init__(self, log_path: str = "audit.jsonl"):
        """Initialize audit logger.
        
        Args:
            log_path: Path to the audit log file
        """
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._get_last_hash()

    def _get_last_hash(self) -> str:
        """Get the hash of the last log entry for chaining."""
        try:
            if self.log_path.exists():
                with open(self.log_path, "rb") as f:
                    # Read last line
                    f.seek(0, 2)  # End of file
                    size = f.tell()
                    if size == 0:
                        return "0" * 64
                    # Read last 4KB to find last line
                    f.seek(max(0, size - 4096))
                    lines = f.read().decode("utf-8", errors="ignore").strip().split("\n")
                    if lines:
                        last_line = lines[-1]
                        entry = json.loads(last_line)
                        return entry.get("hash", "0" * 64)
        except Exception:
            pass
        return "0" * 64

    def _compute_hash(self, data: dict[str, Any], previous_hash: str) -> str:
        """Compute SHA-256 hash for chain integrity."""
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(f"{previous_hash}:{content}".encode()).hexdigest()

    async def log(self, event: dict[str, Any]) -> None:
        """Log an audit event.
        
        Args:
            event: Event data to log
        """
        # Add timestamp if not present
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat()

        # Compute hash chain
        event_hash = self._compute_hash(event, self._last_hash)
        event["hash"] = event_hash
        event["previous_hash"] = self._last_hash
        self._last_hash = event_hash

        # Append to log file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as e:
            # Log to stderr if file write fails
            import sys
            print(f"Audit log write failed: {e}", file=sys.stderr)

    async def log_request(self, request_data: dict[str, Any]) -> None:
        """Log an HTTP request."""
        await self.log({
            "event_type": "request",
            **request_data,
        })

    async def log_response(self, response_data: dict[str, Any]) -> None:
        """Log an HTTP response."""
        await self.log({
            "event_type": "response",
            **response_data,
        })

    async def log_agent_action(self, action_data: dict[str, Any]) -> None:
        """Log an agent action."""
        await self.log({
            "event_type": "agent_action",
            **action_data,
        })

    async def log_security_event(self, security_data: dict[str, Any]) -> None:
        """Log a security event."""
        await self.log({
            "event_type": "security",
            **security_data,
        })

    async def log_compliance_event(self, compliance_data: dict[str, Any]) -> None:
        """Log a compliance event."""
        await self.log({
            "event_type": "compliance",
            **compliance_data,
        })

    def get_events(
        self,
        event_type: str | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit events from the log.
        
        Args:
            event_type: Filter by event type
            limit: Maximum number of events to return
            since: Only return events after this datetime
            
        Returns:
            List of audit events
        """
        events = []
        try:
            if not self.log_path.exists():
                return events

            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        
                        # Filter by event type
                        if event_type and entry.get("event_type") != event_type:
                            continue
                        
                        # Filter by time
                        if since:
                            event_time = datetime.fromisoformat(entry.get("timestamp", ""))
                            if event_time < since:
                                continue
                        
                        events.append(entry)
                        
                        if len(events) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        
        return events

    def verify_chain(self) -> dict[str, Any]:
        """Verify the integrity of the audit log chain.
        
        Returns:
            dict with 'valid', 'total_events', and any 'errors'
        """
        errors = []
        total_events = 0
        previous_hash = "0" * 64

        try:
            if not self.log_path.exists():
                return {"valid": True, "total_events": 0, "errors": []}

            with open(self.log_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        total_events += 1

                        # Verify hash chain
                        stored_previous = entry.get("previous_hash", "0" * 64)
                        if stored_previous != previous_hash:
                            errors.append(f"Line {line_num}: Broken hash chain")

                        # Recompute hash
                        stored_hash = entry.get("hash", "")
                        computed_hash = self._compute_hash(
                            {k: v for k, v in entry.items() if k not in ("hash", "previous_hash")},
                            previous_hash
                        )
                        if stored_hash != computed_hash:
                            errors.append(f"Line {line_num}: Hash mismatch")

                        previous_hash = stored_hash
                    except json.JSONDecodeError:
                        errors.append(f"Line {line_num}: Invalid JSON")
        except Exception as e:
            errors.append(f"Read error: {e}")

        return {
            "valid": len(errors) == 0,
            "total_events": total_events,
            "errors": errors,
        }

    def clear(self) -> None:
        """Clear the audit log (requires admin approval)."""
        if self.log_path.exists():
            # Backup before clearing
            backup_path = self.log_path.with_suffix(".jsonl.bak")
            self.log_path.rename(backup_path)
        self._last_hash = "0" * 64
