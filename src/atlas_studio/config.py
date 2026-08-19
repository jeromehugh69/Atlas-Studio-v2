from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_STUDIO_", env_file=".env", extra="ignore")

    mode: Literal["community", "integrations"] = "community"
    host: str = "127.0.0.1"
    port: int = 8080
    cors_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]
    session_secret: str = ""
    database_url: str = "postgresql://atlas_studio:atlas-studio@localhost:5432/atlas_studio"
    redis_url: str = "redis://localhost:6379/0"
    artifact_backend: Literal["filesystem", "minio"] = "filesystem"
    artifact_root: Path = Path("./data/artifacts")
    workspace_root: Path = Path(".")
    workspace_max_preview_kb: int = Field(512, ge=16, le=4096)
    default_provider: str = "ollama"
    default_model: str = "qwen3:4b"
    forge_model: str = "qwen3:4b"
    ollama_url: str = "http://localhost:11434"
    model_timeout_seconds: int = Field(120, ge=30, le=900)
    model_max_tokens: int = Field(384, ge=64, le=4096)
    forge_timeout_seconds: int = Field(300, ge=60, le=1800)
    forge_max_tokens: int = Field(2048, ge=256, le=16384)
    forge_context_tokens: int = Field(4096, ge=2048, le=32768)
    sandbox_runtime: Literal["docker", "podman", "local"] = "local"
    sandbox_network: str = "none"  # ignored when sandbox_runtime=local
    sandbox_memory: str = "512m"
    sandbox_cpus: float = Field(1.0, gt=0, le=16)
    sandbox_pids: int = Field(128, ge=16, le=4096)
    worker_url: str = "http://localhost:8092"
    worker_token: str = "atlas-local-worker"
    research_worker_url: str = "http://localhost:8093"
    research_worker_token: str = "atlas-local-research"
    upload_max_mb: int = Field(25, ge=1, le=1024)
    max_body_size_mb: int = Field(10, ge=1, le=100)
    telemetry_enabled: bool = False
    minio_enabled: bool = False
    google_oauth_enabled: bool = False
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    stt_url: str = ""
    tts_url: str = ""
    avatar_local_enabled: bool = False
    avatar_provider: Literal["triposr-local"] = "triposr-local"
    avatar_service_url: str = "http://localhost:8090"
    owner_name: str = "Platform Owner"
    sqlite_encryption_key: str = ""
    compliance_enabled: bool = True
    rate_limit_max_requests: int = Field(100, ge=10, le=10000)
    rate_limit_window_seconds: int = Field(60, ge=10, le=3600)
    
    # LiteLLM Configuration
    litellm_api_base: str = "http://localhost:11434"
    litellm_api_key: str = ""
    litellm_model_prefix: str = "ollama"
    litellm_fallback_models: list[str] = []
    litellm_cost_tracking: bool = True
    litellm_num_retries: int = 2
    litellm_timeout: int = 120

    @model_validator(mode="after")
    def validate_local_first(self):
        if self.mode == "community" and self.minio_enabled:
            raise ValueError("external integrations cannot be enabled in community mode")
        if self.artifact_backend == "minio" and not self.minio_enabled:
            raise ValueError("MinIO backend requires ATLAS_STUDIO_MINIO_ENABLED=true")
        if self.telemetry_enabled and self.mode == "community":
            raise ValueError("telemetry is disabled in community mode")
        if self.google_oauth_enabled and self.mode != "integrations":
            raise ValueError("Google OAuth is optional and requires integrations mode")
        if self.google_oauth_enabled and (not self.google_oauth_client_id or not self.google_oauth_client_secret):
            raise ValueError("Google OAuth requires both a client ID and client secret")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
