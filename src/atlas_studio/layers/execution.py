from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("atlas_studio.execution")


class ImplementationWorkerError(RuntimeError):
    pass


class ImplementationWorker:
    def __init__(self, url: str, token: str, timeout_seconds: int = 310):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self._http_ok: bool | None = None
        self._embedded_fn = None

    def _get_embedded(self):
        if self._embedded_fn is None:
            from ..local_worker import execute_action
            self._embedded_fn = execute_action
            logger.info("Using embedded in-process worker (standalone mode)")
        return self._embedded_fn

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.url}/health")
                response.raise_for_status()
                self._http_ok = True
                return response.json()
        except (httpx.HTTPError, ValueError):
            self._http_ok = False
            return {"status": "embedded", "detail": "Using in-process worker (standalone mode)"}

    async def execute(self, payload: dict) -> dict:
        if self._http_ok is not False:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.url}/actions",
                        headers={"Authorization": f"Bearer {self.token}"},
                        json=payload,
                    )
                if response.is_error:
                    try:
                        detail = response.json().get("detail", response.text)
                    except ValueError:
                        detail = response.text
                    raise ImplementationWorkerError(str(detail))
                self._http_ok = True
                return response.json()
            except (httpx.HTTPError, ValueError):
                self._http_ok = False
                logger.info("HTTP worker unreachable, switching to embedded worker")

        try:
            return await self._get_embedded()(payload)
        except ImplementationWorkerError:
            raise
        except Exception as exc:
            raise ImplementationWorkerError(f"embedded worker: {exc}") from exc

