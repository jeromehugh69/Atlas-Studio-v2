$ErrorActionPreference = "Stop"
docker compose exec ollama ollama pull qwen3:4b
Write-Host "Local Atlas Studio model references are ready. No model weights were bundled with the source."
