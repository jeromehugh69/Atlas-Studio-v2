"""Output Sanitizer - Sanitizes all outputs before sending to client."""
from __future__ import annotations

import json
import re
from typing import Any


class OutputSanitizer:
    """Sanitize all outputs before sending to client.
    
    Features:
    - Redacts sensitive data (API keys, passwords, tokens)
    - Removes potentially harmful content
    - Preserves data structure
    """

    # Patterns to redact with their replacements
    SENSITIVE_PATTERNS = [
        # API keys
        (r"(api[_-]?key\s*[=:]\s*['\"]?)([a-zA-Z0-9]{20,})(['\"]?)", r"\1***REDACTED***\3"),
        (r"(API[_-]?KEY\s*[=:]\s*['\"]?)([a-zA-Z0-9]{20,})(['\"]?)", r"\1***REDACTED***\3"),
        
        # Passwords
        (r"(password\s*[=:]\s*['\"]?)([^\s'\"]+)(['\"]?)", r"\1***REDACTED***\3"),
        (r"(PASSWORD\s*[=:]\s*['\"]?)([^\s'\"]+)(['\"]?)", r"\1***REDACTED***\3"),
        
        # Secrets
        (r"(secret\s*[=:]\s*['\"]?)([a-zA-Z0-9]{20,})(['\"]?)", r"\1***REDACTED***\3"),
        (r"(SECRET\s*[=:]\s*['\"]?)([a-zA-Z0-9]{20,})(['\"]?)", r"\1***REDACTED***\3"),
        
        # Tokens
        (r"(token\s*[=:]\s*['\"]?)([a-zA-Z0-9]{20,})(['\"]?)", r"\1***REDACTED***\3"),
        (r"(TOKEN\s*[=:]\s*['\"]?)([a-zA-Z0-9]{20,})(['\"]?)", r"\1***REDACTED***\3"),
        
        # Bearer tokens
        (r"(Bearer\s+)([a-zA-Z0-9\-._~+/]+=*)", r"\1***REDACTED***"),
        
        # AWS keys
        (r"(AKIA[A-Z0-9]{16})", "***REDACTED***"),
        
        # Private keys
        (r"(-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----)", "***REDACTED***"),
        
        # Connection strings
        (r"(mongodb(\+srv)?://[^\s]+)", "***REDACTED***"),
        (r"(postgres(ql)?://[^\s]+)", "***REDACTED***"),
        (r"(redis://[^\s]+)", "***REDACTED***"),
    ]

    def __init__(self, custom_patterns: list[tuple[str, str]] | None = None):
        """Initialize sanitizer.
        
        Args:
            custom_patterns: Additional patterns to redact
        """
        self.patterns = self.SENSITIVE_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)
        
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.patterns
        ]

    def sanitize(self, body: bytes) -> bytes:
        """Sanitize response body.
        
        Args:
            body: Raw response body bytes
            
        Returns:
            Sanitized body bytes
        """
        try:
            body_str = body.decode("utf-8")
            
            # Check if JSON
            stripped = body_str.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                data = json.loads(body_str)
                sanitized = self._sanitize_value(data)
                return json.dumps(sanitized, default=str).encode("utf-8")
            else:
                # Plain text or other
                return self._sanitize_text(body_str).encode("utf-8")
        except Exception:
            # If sanitization fails, return original
            return body

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively sanitize a value."""
        if isinstance(value, str):
            return self._sanitize_text(value)
        elif isinstance(value, dict):
            return {
                key: self._sanitize_value(val)
                for key, val in value.items()
            }
        elif isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        return value

    def _sanitize_text(self, text: str) -> str:
        """Sanitize text content."""
        for pattern, replacement in self.compiled_patterns:
            text = pattern.sub(replacement, text)
        return text

    def sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize a dictionary."""
        return self._sanitize_value(data)

    def sanitize_string(self, text: str) -> str:
        """Sanitize a string."""
        return self._sanitize_text(text)

    def add_pattern(self, pattern: str, replacement: str) -> None:
        """Add a custom redaction pattern."""
        compiled = re.compile(pattern, re.IGNORECASE)
        self.compiled_patterns.append((compiled, replacement))

    def get_redacted_count(self, text: str) -> int:
        """Count how many redactions would be applied."""
        count = 0
        for pattern, _ in self.compiled_patterns:
            count += len(pattern.findall(text))
        return count
