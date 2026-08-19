from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("atlas_studio.providers")


class ProviderError(RuntimeError):
    pass


def _sanitize_error(exc: Exception) -> str:
    """Strip URLs, keys, and sensitive data from exception messages before returning to client."""
    import re
    msg = str(exc) or exc.__class__.__name__
    # Remove URLs (may contain API keys)
    msg = re.sub(r'https?://[^\s\'"]+', '[redacted-url]', msg)
    # Remove API key patterns
    msg = re.sub(r'(api[_-]?key\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', msg, flags=re.IGNORECASE)
    msg = re.sub(r'(Bearer\s+)[^\s,;]+', r'\1[redacted]', msg)
    # Remove sk-... patterns (OpenAI keys)
    msg = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[redacted-key]', msg)
    # Truncate to prevent information leakage via long messages
    if len(msg) > 200:
        msg = msg[:200] + '...'
    return msg


class ModelProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], model: str, temperature: float = 0.3) -> str: ...

    @abstractmethod
    def stream(self, messages: list[dict[str, str]], model: str, temperature: float = 0.3) -> AsyncIterator[str]: ...

    @abstractmethod
    async def healthy(self) -> bool: ...

    async def chat_with_tools(self, messages: list[dict], model: str, tools: list[dict], temperature: float = 0.1) -> dict:
        raise ProviderError("configured model provider does not support structured tool calls")


class LiteLLMProvider(ModelProvider):
    """Unified LLM provider using LiteLLM.
    
    Supports 100+ LLM providers through a single interface:
    - Ollama: ollama/qwen3:4b
    - OpenAI: openai/gpt-4o-mini
    - Anthropic: anthropic/claude-3-haiku
    - Azure: azure/gpt-4
    - And many more...
    
    Features:
    - Built-in retry and fallback
    - Cost tracking per request
    - Streaming support
    - Tool calling support
    """

    def __init__(
        self,
        api_base: str = "http://localhost:11434",
        api_key: str = "",
        model_prefix: str = "ollama",
        timeout_seconds: int = 120,
        max_tokens: int = 384,
        context_tokens: int = 4096,
        num_retries: int = 2,
        cost_tracking: bool = True,
        fallback_models: list[str] | None = None,
    ):
        """Initialize LiteLLM provider.
        
        Args:
            api_base: Base URL for the LLM provider
            api_key: API key for the provider (optional for local providers)
            model_prefix: Provider prefix (e.g., "ollama", "openai")
            timeout_seconds: Request timeout in seconds
            max_tokens: Maximum tokens to generate
            context_tokens: Maximum context window size
            num_retries: Number of retries on failure
            cost_tracking: Enable cost tracking
            fallback_models: List of fallback models if primary fails
        """
        try:
            import litellm
            self.litellm = litellm
        except ImportError:
            raise ProviderError("litellm package not installed. Run: pip install litellm")
        
        self.api_base = api_base
        self.api_key = api_key
        self.model_prefix = model_prefix
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.context_tokens = context_tokens
        self.num_retries = num_retries
        self.cost_tracking = cost_tracking
        self.fallback_models = fallback_models or []
        
        # Configure LiteLLM
        self.litellm.api_base = api_base
        if api_key:
            self.litellm.api_key = api_key
        
        # Cost tracking
        self._cost_log: list[dict[str, Any]] = []
        self._total_cost = 0.0
        self._total_tokens = 0
        
        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _get_full_model(self, model: str) -> str:
        """Get full model name with provider prefix. Validates against SSRF."""
        import re
        # Strip and validate: only alphanumeric, dots, hyphens, underscores, slashes
        model = model.strip()
        if not model or len(model) > 128:
            raise ValueError(f"Invalid model name length: {len(model)}")
        if not re.match(r'^[a-zA-Z0-9._/\-]+$', model):
            raise ValueError(f"Model name contains disallowed characters: {model}")
        # Block external provider prefixes that could route to paid APIs
        blocked_prefixes = ["openai/", "anthropic/", "google/", "azure/", "cohere/", "bedrock/", "huggingface/"]
        if any(model.lower().startswith(p) for p in blocked_prefixes):
            raise ValueError(f"External provider routing not allowed: {model}")
        if "/" in model:
            return model
        return f"{self.model_prefix}/{model}"

    async def generate(self, messages: list[dict[str, str]], model: str, temperature: float = 0.3) -> str:
        """Generate a complete response."""
        full_model = self._get_full_model(model)
        
        try:
            response = await self.litellm.acompletion(
                model=full_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout_seconds,
            )
            
            # Track cost
            if self.cost_tracking and hasattr(response, "usage"):
                self._track_cost(response.usage, full_model)
            
            self._consecutive_failures = 0
            return response.choices[0].message.content
            
        except Exception as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._circuit_open_until = time.time() + 30
                logger.warning("LiteLLM circuit breaker opened")
            
            # Try fallback models
            if self.fallback_models:
                for fallback_model in self.fallback_models:
                    try:
                        return await self.generate(messages, fallback_model, temperature)
                    except Exception:
                        continue
            
            raise ProviderError(f"LiteLLM request failed: {_sanitize_error(exc)}") from exc

    async def stream(self, messages: list[dict[str, str]], model: str, temperature: float = 0.3) -> AsyncIterator[str]:
        """Stream a response chunk by chunk."""
        full_model = self._get_full_model(model)
        
        try:
            response = await self.litellm.acompletion(
                model=full_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout_seconds,
                stream=True,
            )
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            self._consecutive_failures = 0
            
        except Exception as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._circuit_open_until = time.time() + 30
                logger.warning("LiteLLM circuit breaker opened")
            
            # Try fallback models
            if self.fallback_models:
                for fallback_model in self.fallback_models:
                    try:
                        async for chunk in self.stream(messages, fallback_model, temperature):
                            yield chunk
                        return
                    except Exception:
                        continue
            
            raise ProviderError(f"LiteLLM stream failed: {_sanitize_error(exc)}") from exc

    async def chat_with_tools(self, messages: list[dict], model: str, tools: list[dict], temperature: float = 0.1) -> dict:
        """Chat with tool calling support."""
        full_model = self._get_full_model(model)
        
        try:
            response = await self.litellm.acompletion(
                model=full_model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout_seconds,
            )
            
            message = response.choices[0].message
            
            # Track cost
            if self.cost_tracking and hasattr(response, "usage"):
                self._track_cost(response.usage, full_model)
            
            self._consecutive_failures = 0
            
            return {
                "role": "assistant",
                "content": str(message.content or ""),
                "tool_calls": message.tool_calls or [],
            }
            
        except Exception as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._circuit_open_until = time.time() + 30
                logger.warning("LiteLLM circuit breaker opened")
            
            raise ProviderError(f"LiteLLM tool call failed: {_sanitize_error(exc)}") from exc

    async def healthy(self) -> bool:
        """Check if the provider is reachable."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.api_base}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def _track_cost(self, usage: Any, model: str) -> None:
        """Track cost for a request."""
        try:
            # LiteLLM provides cost information
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = prompt_tokens + completion_tokens
            
            # Calculate cost (simplified - actual cost depends on provider)
            # For local Ollama, cost is $0
            cost = 0.0
            
            self._cost_log.append({
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
                "timestamp": time.time(),
            })
            
            self._total_cost += cost
            self._total_tokens += total_tokens
            
        except Exception as e:
            logger.warning(f"Cost tracking failed: {e}")

    def get_cost_log(self) -> list[dict[str, Any]]:
        """Get the cost log."""
        return self._cost_log.copy()

    def get_total_cost(self) -> float:
        """Get total cost."""
        return self._total_cost

    def get_total_tokens(self) -> int:
        """Get total tokens used."""
        return self._total_tokens


class ProviderGateway:
    def __init__(self, default: str, providers: dict[str, ModelProvider]):
        self.default = default
        self.providers = providers

    def get(self, provider: str | None = None) -> ModelProvider:
        name = provider or self.default
        if name not in self.providers:
            raise ProviderError(f"provider '{name}' is disabled or unavailable")
        return self.providers[name]
