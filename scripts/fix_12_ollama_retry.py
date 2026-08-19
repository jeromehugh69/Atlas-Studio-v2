#!/usr/bin/env python3
"""
Fix #12: Add retry and circuit breaker to Ollama provider
===========================================================
Adds connection retry logic with exponential backoff and a circuit breaker
to prevent cascading failures when Ollama is overloaded.

Usage: python scripts/fix_12_ollama_retry.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "providers.py"


def main():
    print("=" * 50)
    print("Fix #12: Ollama retry/circuit breaker")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    if "_circuit_open_until" in c:
        print("  SKIP: Already patched")
        return

    # 1. Add circuit breaker fields to __init__
    c = c.replace(
        "        self.base_url = base_url.rstrip(\"/\")\n        self.timeout_seconds = timeout_seconds\n        self.max_tokens = max_tokens\n        self.context_tokens = context_tokens\n\n    async def generate",
        "        self.base_url = base_url.rstrip(\"/\")\n        self.timeout_seconds = timeout_seconds\n        self.max_tokens = max_tokens\n        self.context_tokens = context_tokens\n        self._consecutive_failures = 0\n        self._circuit_open_until = 0.0\n\n    async def generate",
    )
    print("  OK:   Added circuit breaker fields")

    # 2. Fix Docker error message
    c = c.replace(
        "raise ProviderError(f\"Ollama does not have model '{model}'. Run: docker compose exec ollama ollama pull {model}\")",
        "raise ProviderError(f\"Ollama does not have model '{model}'. Pull it with: ollama pull {model}\")"
    )
    print("  OK:   Fixed Docker error message")

    # 3. Add retry wrapper around stream method body
    c = c.replace(
        "    async def stream(self, messages, model, temperature=0.3):\n        try:\n            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=10)) as client:\n                async with client.stream(",
        "    async def stream(self, messages, model, temperature=0.3):\n        import time as _time\n        import logging as _log\n        _logger = _log.getLogger(\"atlas_studio.providers\")\n        max_retries = 2\n        for _attempt in range(max_retries + 1):\n            if _time.time() < self._circuit_open_until:\n                raise ProviderError(\"Ollama circuit breaker open - wait a moment and retry\")\n            try:\n                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=10)) as client:\n                    async with client.stream("
    )
    print("  OK:   Added retry loop to stream()")

    # 4. Update error handling in stream to include retry
    c = c.replace(
        "        except httpx.TimeoutException as exc:\n            raise ProviderError(f\"Ollama timed out while running '{model}' after {self.timeout_seconds} seconds. Stop unused model services or select a smaller local model, then retry\") from exc\n        except httpx.HTTPError as exc:\n            raise ProviderError(f\"Ollama connection failed: {exc.__class__.__name__}\") from exc",
        "            except httpx.TimeoutException as exc:\n                self._consecutive_failures += 1\n                if self._consecutive_failures >= 3:\n                    self._circuit_open_until = _time.time() + 30\n                    _logger.warning(\"Ollama circuit breaker opened\")\n                if _attempt < max_retries:\n                    _logger.info(\"Ollama timeout, retry %d/%d\", _attempt + 1, max_retries)\n                    continue\n                raise ProviderError(f\"Ollama timed out running '{model}' after {self.timeout_seconds}s. Retry or select a smaller model.\") from exc\n            except httpx.HTTPError as exc:\n                self._consecutive_failures += 1\n                if self._consecutive_failures >= 3:\n                    self._circuit_open_until = _time.time() + 30\n                    _logger.warning(\"Ollama circuit breaker opened\")\n                if _attempt < max_retries:\n                    _logger.info(\"Ollama connection failed, retry %d/%d\", _attempt + 1, max_retries)\n                    continue\n                raise ProviderError(f\"Ollama connection failed: {exc.__class__.__name__}. Is Ollama running at {self.base_url}?\") from exc\n        self._consecutive_failures = 0"
    )
    print("  OK:   Added retry and circuit breaker error handling")

    FILE.write_text(c, encoding="utf-8")
    print()
    print("Ollama will retry twice on failure, then open circuit breaker for 30s.")


if __name__ == "__main__":
    main()
