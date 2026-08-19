$ErrorActionPreference = "Stop"

Write-Host "Stopping optional high-memory avatar services..."
docker compose stop openavatarchat echomimic avatar3d headtts speech 2>$null

Write-Host "Starting the Atlas engineering control plane..."
docker compose up -d app worker postgres redis ollama

Write-Host "Unloading any retained Ollama model session..."
docker compose exec ollama ollama stop qwen3:4b 2>$null

Write-Host "Forge performance mode is ready at http://localhost:8080"
