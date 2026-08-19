# LiteLLM Integration Plan

## Overview

Replace Atlas Studio's custom Ollama/OpenAI providers with LiteLLM's unified interface for 100+ LLM providers.

## Current State

**Files:**
- `src/atlas_studio/providers.py` - Custom `OllamaProvider` and `OpenAICompatibleProvider`
- `src/atlas_studio/main.py` - Gateway initialization at lines 34, 44, 49-54

**Issues:**
- Manual HTTP calls with custom retry logic
- No cost tracking or observability
- Limited to Ollama and OpenAI-compatible endpoints
- Custom circuit breaker implementation

## Target State

**LiteLLM Benefits:**
- Unified interface for 100+ providers (Ollama, OpenAI, Anthropic, Azure, etc.)
- Built-in retry, fallback, and load balancing
- Cost tracking per request
- Observability callbacks (Langfuse, MLflow, etc.)
- Streaming support out of the box

## Implementation Steps

### Step 1: Add Dependency
```bash
uv add litellm>=1.40,<2
```

### Step 2: Update Configuration
Add to `src/atlas_studio/config.py`:
```python
# LiteLLM Configuration
litellm_api_base: str = "http://localhost:11434"
litellm_api_key: str = ""
litellm_model_prefix: str = "ollama"
litellm_fallback_models: list[str] = []
litellm_cost_tracking: bool = True
litellm_num_retries: int = 2
litellm_timeout: int = 120
```

### Step 3: Create LiteLLM Provider
New class in `src/atlas_studio/providers.py`:
```python
class LiteLLMProvider(ModelProvider):
    """Unified LLM provider using LiteLLM."""
    
    def __init__(self, api_base, api_key, model_prefix, timeout_seconds, max_tokens, context_tokens, num_retries):
        # Initialize LiteLLM
        litellm.api_base = api_base
        if api_key:
            litellm.api_key = api_key
        
        # Cost tracking
        litellm.success_callback = [self._track_cost]
        self._cost_log = []
    
    async def generate(self, messages, model, temperature=0.3):
        full_model = f"{self.model_prefix}/{model}" if "/" not in model else model
        response = await litellm.acompletion(model=full_model, messages=messages, temperature=temperature, max_tokens=self.max_tokens)
        return response.choices[0].message.content
    
    async def stream(self, messages, model, temperature=0.3):
        full_model = f"{self.model_prefix}/{model}" if "/" not in model else model
        response = await litellm.acompletion(model=full_model, messages=messages, temperature=temperature, stream=True)
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def healthy(self):
        # Check provider health
    
    async def chat_with_tools(self, messages, model, tools, temperature=0.1):
        # Tool calling support
```

### Step 4: Update Gateway Initialization
In `src/atlas_studio/main.py`:
```python
from .providers import LiteLLMProvider, ProviderError, ProviderGateway

gateway = ProviderGateway(
    settings.default_provider,
    {
        "litellm": LiteLLMProvider(
            api_base=settings.litellm_api_base,
            api_key=settings.litellm_api_key,
            model_prefix=settings.litellm_model_prefix,
            timeout_seconds=settings.model_timeout_seconds,
            max_tokens=settings.model_max_tokens,
            num_retries=settings.litellm_num_retries,
        ),
    },
)

forge_provider = LiteLLMProvider(
    api_base=settings.litellm_api_base,
    api_key=settings.litellm_api_key,
    model_prefix=settings.litellm_model_prefix,
    timeout_seconds=settings.forge_timeout_seconds,
    max_tokens=settings.forge_max_tokens,
    context_tokens=settings.forge_context_tokens,
    num_retries=settings.litellm_num_retries,
)
```

### Step 4.5: Remove OllamaProvider
Delete the `OllamaProvider` and `OpenAICompatibleProvider` classes from `providers.py`. The `LiteLLMProvider` fully replaces both:
- Ollama calls use `litellm/ollama/qwen3:8b` format
- OpenAI calls use `litellm/openai/gpt-4o-mini` format
- Any other provider uses `litellm/<provider>/<model>` format

LiteLLM handles all provider-specific HTTP logic, retries, circuit breakers, and streaming internally.

### Step 5: Add Cost Metrics Endpoint
New endpoint in `src/atlas_studio/main.py`:
```python
@app.get("/api/metrics/costs")
async def get_cost_metrics():
    provider = gateway.get()
    if hasattr(provider, "get_cost_log"):
        cost_log = provider.get_cost_log()
        total_cost = sum(entry["cost"] for entry in cost_log)
        total_tokens = sum(entry["tokens"] for entry in cost_log)
        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "requests": len(cost_log),
        }
    return {"total_cost": 0, "total_tokens": 0, "requests": 0}
```

## Files to Modify

| File | Changes |
|------|---------|
| `pyproject.toml` | Add `litellm>=1.40,<2` |
| `src/atlas_studio/config.py` | Add LiteLLM settings |
| `src/atlas_studio/providers.py` | **Replace** `OllamaProvider` + `OpenAICompatibleProvider` with `LiteLLMProvider` |
| `src/atlas_studio/main.py` | Update imports, gateway initialization, add cost endpoint |
| `.env.example` | Add LiteLLM environment variables |

## Testing

1. Verify `OllamaProvider` and `OpenAICompatibleProvider` are removed
2. Verify Ollama works with `ollama/qwen3:8b` model via LiteLLM
3. Test streaming produces correct output format
4. Test tool calling returns OpenAI-compatible format
5. Test cost tracking captures per-request costs
6. Test fallback routing works
7. Verify all existing tests pass with new provider

## Rollback

1. Restore original `providers.py` with `OllamaProvider` and `OpenAICompatibleProvider`
2. Revert `main.py` gateway initialization
3. Remove `litellm` from dependencies

## Success Criteria

- [ ] `OllamaProvider` and `OpenAICompatibleProvider` fully removed from `providers.py`
- [ ] All model calls route through `LiteLLMProvider`
- [ ] Cost tracking captures per-request costs
- [ ] Streaming works correctly
- [ ] Tool calling returns OpenAI-compatible format
- [ ] Fallback routing works
- [ ] All existing tests pass
