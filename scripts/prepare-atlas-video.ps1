$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$videoPath = Join-Path $projectRoot "src\atlas_studio\static\avatars\atlas-idle.mp4"

if (-not (Test-Path -LiteralPath $videoPath)) {
    throw "Atlas video not found: $videoPath"
}

Push-Location $projectRoot
try {
    Write-Host "Starting the local media helper..."
    docker compose --profile speaking-avatar up -d speech
    if ($LASTEXITCODE -ne 0) { throw "The local speech service could not start." }

    $speechContainer = (docker compose --profile speaking-avatar ps -q speech).Trim()
    if (-not $speechContainer) { throw "The local speech container was not found." }

    Write-Host "Converting Atlas from HEVC to browser-compatible H.264..."
    docker cp $videoPath "${speechContainer}:/tmp/atlas-source-hevc.mp4"
    if ($LASTEXITCODE -ne 0) { throw "The source video could not be copied into the media helper." }

    docker exec $speechContainer ffmpeg -hide_banner -loglevel warning -y `
        -i /tmp/atlas-source-hevc.mp4 `
        -an -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p `
        -movflags +faststart /tmp/atlas-idle-h264.mp4
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg could not convert the Atlas video." }

    docker cp "${speechContainer}:/tmp/atlas-idle-h264.mp4" $videoPath
    if ($LASTEXITCODE -ne 0) { throw "The converted video could not be copied back into Atlas Studio." }

    docker exec $speechContainer rm -f /tmp/atlas-source-hevc.mp4 /tmp/atlas-idle-h264.mp4 | Out-Null

    Write-Host "Rebuilding Atlas Studio with the compatible video..."
    docker compose build app
    if ($LASTEXITCODE -ne 0) { throw "The Atlas Studio app image could not be rebuilt." }

    docker compose up -d --force-recreate app
    if ($LASTEXITCODE -ne 0) { throw "The Atlas Studio app could not be restarted." }

    Write-Host "Atlas video conversion completed."
    docker compose ps app portal
}
finally {
    Pop-Location
}
