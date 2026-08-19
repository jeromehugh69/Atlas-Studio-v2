$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Wait-AtlasServiceHealthy {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [int]$Attempts = 40
    )
    $containerId = (docker compose ps -q $Service).Trim()
    if (-not $containerId) { throw "The Atlas $Service container was not created." }
    $state = "starting"
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $state = (docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId 2>$null).Trim()
        if ($state -eq "healthy" -or $state -eq "running") { return }
        if ($state -in @("exited", "dead", "unhealthy")) { break }
        Start-Sleep -Seconds 3
    }
    Write-Host "The Atlas $Service service did not become ready (state: $state). Recent output:"
    docker compose logs --tail 120 $Service
    throw "The Atlas $Service service failed its startup check."
}

Push-Location $projectRoot
try {
    Write-Host "Building the interactive Atlas voice conversation..."
    docker compose --profile speaking-avatar build app portal speech
    if ($LASTEXITCODE -ne 0) { throw "The Atlas interface images could not be built." }

    Write-Host "Restarting the Atlas app, speech worker, and portal..."
    docker compose --profile speaking-avatar up -d --force-recreate speech app portal
    if ($LASTEXITCODE -ne 0) { throw "The Atlas interface services could not be restarted." }

    Write-Host "Waiting for local speech and the Atlas portal to become ready..."
    Wait-AtlasServiceHealthy -Service "speech" -Attempts 50
    Wait-AtlasServiceHealthy -Service "portal" -Attempts 40

    Write-Host "Atlas interactive voice conversation is ready."
    docker compose ps app portal speech headtts
}
finally {
    Pop-Location
}
