from __future__ import annotations

import hmac
import os
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


TOKEN = os.getenv("ATLAS_RESEARCH_TOKEN", "atlas-local-research")
SEARXNG_URL = os.getenv("ATLAS_RESEARCH_SEARXNG_URL", "http://searxng:8080").rstrip("/")


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2_000)
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)


app = FastAPI(title="Atlas approved research broker", docs_url=None, redoc_url=None)


def authorized(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(value, f"Bearer {TOKEN}")


@app.get("/health")
async def health():
    return {"status": "ok", "route": "approval-gated", "provider": "local SearXNG"}


@app.post("/search")
async def search(body: SearchRequest, authorization: str | None = Header(default=None)):
    if not authorized(authorization):
        raise HTTPException(401, "research broker authorization failed")
    query = body.query
    if body.allowed_domains:
        query = f"{query} " + " OR ".join(f"site:{domain}" for domain in body.allowed_domains)
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.get(f"{SEARXNG_URL}/search", params={"q": query, "format": "json", "language": "en"})
    if response.is_error:
        raise HTTPException(502, "local search service failed")
    data = response.json()
    allowed = {domain.casefold().lstrip(".") for domain in body.allowed_domains}
    results = []
    for item in data.get("results", [])[:20]:
        host = (urlparse(item.get("url", "")).hostname or "").casefold()
        if allowed and not any(host == domain or host.endswith(f".{domain}") for domain in allowed):
            continue
        results.append({"title": item.get("title", ""), "url": item.get("url", ""), "content": item.get("content", ""), "engine": item.get("engine", "")})
    return {"query": body.query, "allowed_domains": body.allowed_domains, "results": results}
