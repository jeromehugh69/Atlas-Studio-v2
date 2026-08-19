#!/usr/bin/env python3
"""
Fix #6: Create standalone .env file with localhost defaults
============================================================
Creates .env.standalone with all hostnames set to localhost instead of
Docker service names. Copy to .env to use.

Usage: python scripts/fix_06_env_defaults.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / ".env.standalone"

CONTENT = """\
# Standalone mode - all services on localhost
# Copy this file to .env:  copy .env.standalone .env
ATLAS_STUDIO_MODE=community
ATLAS_STUDIO_HOST=127.0.0.1
ATLAS_STUDIO_PORT=8080
ATLAS_STUDIO_DATABASE_URL=postgresql://atlas_studio:atlas-studio@localhost:5432/atlas_studio
ATLAS_STUDIO_REDIS_URL=redis://localhost:6379/0
ATLAS_STUDIO_ARTIFACT_BACKEND=filesystem
ATLAS_STUDIO_ARTIFACT_ROOT=./data/artifacts
ATLAS_STUDIO_WORKSPACE_ROOT=.
ATLAS_STUDIO_WORKSPACE_MAX_PREVIEW_KB=512
ATLAS_STUDIO_DEFAULT_PROVIDER=ollama
ATLAS_STUDIO_DEFAULT_MODEL=qwen3:4b
ATLAS_STUDIO_FORGE_MODEL=qwen3:4b
ATLAS_STUDIO_OLLAMA_URL=http://localhost:11434

# LiteLLM Configuration
ATLAS_STUDIO_LITELLM_API_BASE=http://localhost:11434
ATLAS_STUDIO_LITELLM_API_KEY=
ATLAS_STUDIO_LITELLM_MODEL_PREFIX=ollama
ATLAS_STUDIO_LITELLM_FALLBACK_MODELS=[]
ATLAS_STUDIO_LITELLM_COST_TRACKING=true
ATLAS_STUDIO_LITELLM_NUM_RETRIES=2
ATLAS_STUDIO_LITELLM_TIMEOUT=120

ATLAS_STUDIO_MODEL_TIMEOUT_SECONDS=120
ATLAS_STUDIO_MODEL_MAX_TOKENS=384
ATLAS_STUDIO_FORGE_TIMEOUT_SECONDS=300
ATLAS_STUDIO_FORGE_MAX_TOKENS=2048
ATLAS_STUDIO_FORGE_CONTEXT_TOKENS=4096
ATLAS_STUDIO_WORKER_URL=http://localhost:8092
ATLAS_STUDIO_WORKER_TOKEN=atlas-local-worker
ATLAS_STUDIO_UPLOAD_MAX_MB=25
ATLAS_STUDIO_TELEMETRY_ENABLED=false
ATLAS_STUDIO_MINIO_ENABLED=false
ATLAS_STUDIO_GOOGLE_OAUTH_ENABLED=false
ATLAS_STUDIO_AVATAR_LOCAL_ENABLED=false
"""


def main():
    print("=" * 50)
    print("Fix #6: Create standalone .env file")
    print("=" * 50)

    TARGET.write_text(CONTENT, encoding="utf-8")
    print(f"  OK:   Created {TARGET.name}")
    print()
    print("To activate:  copy .env.standalone .env")


if __name__ == "__main__":
    main()
