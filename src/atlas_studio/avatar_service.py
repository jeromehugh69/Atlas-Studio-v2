from pathlib import Path
from typing import Any

import httpx


class AvatarServiceError(RuntimeError):
    pass


class LocalTripoSRProvider:
    """Adapter for the local MIT-licensed TripoSR worker."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def create(self, files: dict[str, tuple[str, bytes, str]]) -> str:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.base_url}/jobs", files=files)
        except httpx.HTTPError as exc:
            raise AvatarServiceError("local image-to-3D worker is unavailable") from exc
        if response.is_error:
            raise AvatarServiceError(f"local worker rejected the image with HTTP {response.status_code}")
        task_id = response.json().get("id")
        if not task_id:
            raise AvatarServiceError("local worker did not return a job id")
        return task_id

    async def status(self, task_id: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{self.base_url}/jobs/{task_id}")
        except httpx.HTTPError as exc:
            raise AvatarServiceError("local image-to-3D worker became unavailable") from exc
        if response.is_error:
            raise AvatarServiceError(f"local status request failed with HTTP {response.status_code}")
        return response.json()

    @staticmethod
    def find_glb(value: dict[str, Any]) -> str | None:
        return value.get("artifact_url")

    async def download_glb(self, url: str, destination: Path):
        target = url if url.startswith("http") else f"{self.base_url}{url}"
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                response = await client.get(target)
        except httpx.HTTPError as exc:
            raise AvatarServiceError("local generated model download failed") from exc
        if response.is_error or len(response.content) > 150 * 1024 * 1024:
            raise AvatarServiceError("local model download failed or exceeded 150 MB")
        if response.content[:4] != b"glTF":
            raise AvatarServiceError("local worker output was not a valid binary GLB")
        destination.write_bytes(response.content)
