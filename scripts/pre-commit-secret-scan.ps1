$ErrorActionPreference = "Stop"

$paths = @(
    (Get-Command gitleaks -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Microsoft\WinGet\Links\gitleaks.exe",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe\gitleaks.exe"
)

$gitleaks = $null
foreach ($p in $paths) {
    if ($p -and (Test-Path $p)) { $gitleaks = $p; break }
}

if (-not $gitleaks) {
    Write-Host "pre-commit: gitleaks not found - skipping scan (install: winget install Gitleaks.Gitleaks)"
    exit 0
}

& $gitleaks protect --staged --redact --verbose
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "COMMIT BLOCKED: gitleaks detected secrets in staged changes." -ForegroundColor Red
    Write-Host "Remove the secret or add a targeted .gitleaksignore entry, then retry."
    exit 1
}
exit 0
