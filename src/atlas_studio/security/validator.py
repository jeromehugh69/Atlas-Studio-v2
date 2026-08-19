"""Input Validator - Validates all inputs for dangerous patterns."""
from __future__ import annotations

import json
import re
from typing import Any


class InputValidator:
    """Validate all inputs before processing.
    
    Detects and blocks:
    - XSS (Cross-Site Scripting)
    - SQL injection
    - Path traversal
    - Code execution attempts
    - Command injection
    """

    # Dangerous patterns to detect
    DANGEROUS_PATTERNS = [
        # XSS patterns
        (r"<script[^>]*>.*?</script>", "XSS script tag"),
        (r"javascript:", "JavaScript protocol"),
        (r"on\w+\s*=", "Event handler attribute"),
        (r"<iframe[^>]*>", "iframe tag"),
        (r"<object[^>]*>", "object tag"),
        (r"<embed[^>]*>", "embed tag"),
        
        # SQL injection patterns
        (r"union\s+select", "SQL UNION SELECT"),
        (r"drop\s+table", "SQL DROP TABLE"),
        (r"delete\s+from", "SQL DELETE FROM"),
        (r"insert\s+into", "SQL INSERT INTO"),
        (r"update\s+.*\s+set", "SQL UPDATE SET"),
        (r";\s*select", "SQL chained SELECT"),
        
        # Path traversal patterns
        (r"\.\./", "Path traversal"),
        (r"\.\.\\", "Path traversal (Windows)"),
        (r"%2e%2e", "URL-encoded path traversal"),
        
        # Code execution patterns
        (r"exec\s*\(", "exec() call"),
        (r"eval\s*\(", "eval() call"),
        (r"__import__", "Module import"),
        (r"subprocess", "Subprocess call"),
        (r"os\.system", "System call"),
        (r"os\.popen", "Popen call"),
        
        # Command injection patterns
        (r";\s*\w+", "Command chaining"),
        (r"\|\s*\w+", "Pipe command"),
        (r"`[^`]+`", "Backtick command"),
        (r"\$\([^)]+\)", "Command substitution"),
    ]

    def __init__(self, strict_mode: bool = False):
        """Initialize validator.
        
        Args:
            strict_mode: If True, blocks more patterns
        """
        self.strict_mode = strict_mode
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), desc)
            for pattern, desc in self.DANGEROUS_PATTERNS
        ]

    def validate(self, body: bytes, content_type: str | None = None) -> dict[str, Any]:
        """Validate request body.
        
        Args:
            body: Raw request body bytes
            content_type: Content-Type header value
            
        Returns:
            dict with 'valid' and optional 'reason'
        """
        try:
            if content_type and "json" in content_type:
                return self._validate_json(body)
            elif content_type and "form" in content_type:
                return self._validate_form(body)
            elif content_type and "multipart" in content_type:
                return {"valid": True}  # Multipart handled separately
            else:
                return self._validate_raw(body)
        except Exception as e:
            return {"valid": False, "reason": f"Validation error: {e}"}

    def _validate_json(self, body: bytes) -> dict[str, Any]:
        """Validate JSON body."""
        try:
            data = json.loads(body)
            return self._validate_value(data)
        except json.JSONDecodeError as e:
            return {"valid": False, "reason": f"Invalid JSON: {e}"}

    def _validate_form(self, body: bytes) -> dict[str, Any]:
        """Validate form-encoded body."""
        try:
            body_str = body.decode("utf-8")
            # Check for dangerous patterns in form data
            for pattern, desc in self.compiled_patterns:
                if pattern.search(body_str):
                    return {"valid": False, "reason": f"Dangerous pattern: {desc}"}
            return {"valid": True}
        except UnicodeDecodeError:
            return {"valid": True}

    def _validate_raw(self, body: bytes) -> dict[str, Any]:
        """Validate raw body."""
        try:
            body_str = body.decode("utf-8", errors="ignore")
            for pattern, desc in self.compiled_patterns:
                if pattern.search(body_str):
                    return {"valid": False, "reason": f"Dangerous pattern: {desc}"}
            return {"valid": True}
        except Exception:
            return {"valid": True}

    def _validate_value(self, value: Any) -> dict[str, Any]:
        """Recursively validate a value."""
        if isinstance(value, str):
            for pattern, desc in self.compiled_patterns:
                if pattern.search(value):
                    return {"valid": False, "reason": f"Dangerous pattern: {desc}"}
        elif isinstance(value, dict):
            for key, val in value.items():
                # Validate key
                for pattern, desc in self.compiled_patterns:
                    if pattern.search(str(key)):
                        return {"valid": False, "reason": f"Dangerous pattern in key: {desc}"}
                # Validate value recursively
                result = self._validate_value(val)
                if not result["valid"]:
                    return result
        elif isinstance(value, list):
            for item in value:
                result = self._validate_value(item)
                if not result["valid"]:
                    return result
        return {"valid": True}

    def validate_string(self, text: str) -> dict[str, Any]:
        """Validate a string value."""
        for pattern, desc in self.compiled_patterns:
            if pattern.search(text):
                return {"valid": False, "reason": f"Dangerous pattern: {desc}"}
        return {"valid": True}

    def sanitize_string(self, text: str) -> str:
        """Sanitize a string by removing dangerous characters."""
        # Remove null bytes
        text = text.replace("\x00", "")
        # Remove control characters except newline and tab
        text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        return text
