$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "FAILED: $Message"
    }

    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host "Checking Docker services..." -ForegroundColor Cyan
$services = docker compose ps --format json | ConvertFrom-Json
Assert-True (($services | Measure-Object).Count -eq 3) 'three services are running'
Assert-True ((@($services | Where-Object { $_.Health -ne 'healthy' })).Count -eq 0) 'all services are healthy'

Write-Host "Checking API endpoints..." -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri 'http://localhost:8000/api/health'
Assert-True ($health.status -eq 'ok') 'backend liveness endpoint'

$ready = Invoke-RestMethod -Uri 'http://localhost:8000/api/ready'
Assert-True ($ready.status -eq 'ready') 'backend readiness endpoint'
Assert-True ($ready.dependencies.database -eq 'ready') 'database connectivity'

$bootstrap = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/system/bootstrap'
Assert-True ($bootstrap.phase -eq 'phase-0') 'bootstrap contract reports phase 0'

$web = Invoke-WebRequest -Uri 'http://localhost:8080' -UseBasicParsing
Assert-True ($web.StatusCode -eq 200) 'web application is reachable'

Write-Host "Stage 0 smoke test completed." -ForegroundColor Cyan

