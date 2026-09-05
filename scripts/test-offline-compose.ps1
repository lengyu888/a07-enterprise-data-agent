$ErrorActionPreference = "Stop"

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

$composePath = Join-Path $PSScriptRoot "..\compose.offline.yml"
$composeText = Get-Content -Raw $composePath
$images = @(docker compose -f $composePath config --images)

Assert-True ($images.Count -eq 3) "offline Compose resolves exactly three images"
Assert-True ($images -contains "a07-agent-app:0.9.2") "offline App image is pinned"
Assert-True ($images -contains "a07-agent-web:0.9.2") "offline Web image is pinned"
Assert-True ($images -contains "pgvector/pgvector:pg16") "offline PostgreSQL image is pinned"
Assert-True (-not $composeText.Contains("build:")) "offline Compose cannot trigger a local build"
Assert-True (-not $composeText.Contains("docker-entrypoint-initdb.d")) "offline Compose has no host init-script dependency"
Assert-True ($composeText.Contains("condition: service_healthy")) "services wait for readiness instead of a fixed delay"

Write-Host "Offline Compose contract passed." -ForegroundColor Cyan
