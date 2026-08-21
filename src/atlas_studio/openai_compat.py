"""OpenAI-compatible API adapter for Atlas Studio.

Enables external chat UIs (Open WebUI, LM Studio, etc.) to connect to Atlas
as if it were an OpenAI endpoint. Adds two routes:

    GET  /v1/models
    POST /v1/chat/completions

The existing POST /api/chat flow is untouched.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import get_settings

router = APIRouter(prefix="/v1", tags=["openai-compat"])


class OAMessage(BaseModel):
    role: str
    content: str | None = None


class OAChatRequest(BaseModel):
    model: str | None = None
    messages: list[OAMessage]
    stream: bool = False
    temperature: float = 0.3
    max_tokens: int | None = None


def _build_atlas_system_prompt() -> str:
    s = get_settings()
    return (
        "You are Atlas, a senior platform engineer AI for Atlas Studio. "
        "Respond in 1-3 sentences using engineering terminology. "
        "Skip pleasantries. Be direct and technical. "
        f"The platform owner's name is {s.owner_name}."
    )


def _oa_message(msg: OAMessage) -> dict[str, str]:
    return {"role": msg.role, "content": msg.content or ""}


async def _stream_chunks(
    messages: list[dict[str, str]],
    model: str,
    request_id: str,
) -> AsyncIterator[str]:
    from .main import gateway

    created = int(time.time())
    first_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(first_chunk)}\n\n"

    async for delta in gateway.get().stream(messages, model):
        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    finish = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(finish)}\n\n"
    yield "data: [DONE]\n\n"


@router.get("/models")
async def list_models():
    settings = get_settings()
    return {
        "object": "list",
        "data": [
            {
                "id": settings.default_model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "atlas-studio",
            }
        ],
    }


@router.post("/chat/completions")
async def chat_completions(body: OAChatRequest):
    from .main import gateway

    settings = get_settings()
    model = body.model or settings.default_model

    messages = []
    if not any(msg.role == "system" for msg in body.messages):
        messages.append({"role": "system", "content": _build_atlas_system_prompt()})
    for msg in body.messages:
        messages.append(_oa_message(msg))

    request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    if body.stream:
        return StreamingResponse(
            _stream_chunks(messages, model, request_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    output = ""
    try:
        async for delta in gateway.get().stream(messages, model):
            output += delta
    except Exception as exc:
        raise HTTPException(503, f"Model unavailable: {exc}")

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": output},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
