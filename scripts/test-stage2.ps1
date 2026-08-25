$ErrorActionPreference = 'Stop'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host "Checking Stage 2 Docker services..." -ForegroundColor Cyan
$services = docker compose -f compose.yml -f compose.deepseek.yml ps --format json | ConvertFrom-Json
Assert-True (($services | Measure-Object).Count -eq 3) 'three services are running'
Assert-True ((@($services | Where-Object { $_.Health -ne 'healthy' })).Count -eq 0) 'all services are healthy'

$bootstrap = Invoke-RestMethod 'http://localhost:8000/api/v1/system/bootstrap'
$capabilities = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/capabilities'
$runs = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/runs?limit=10'

Assert-True ($bootstrap.phase -eq 'phase-2') 'bootstrap contract reports phase 2'
Assert-True (@($capabilities.supported_scenes).Count -eq 1) 'MVP boundary exposes one quality scene'
Assert-True (@($capabilities.pipeline).Count -eq 8) 'LangGraph exposes eight pipeline nodes'
Assert-True ($capabilities.limits.sql_mode -eq 'read_only') 'SQL execution is read-only'
Assert-True ($capabilities.limits.statement_timeout_ms -eq 5000) 'SQL timeout is five seconds'
Assert-True (@($runs | Where-Object { $_.status -eq 'completed' }).Count -ge 1) 'at least one real Agent run completed'

$unsupportedBody = @{ question = '分析设备温度异常原因' } | ConvertTo-Json -Compress
try {
    Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/agent/runs' -ContentType 'application/json' -Body $unsupportedBody
    throw 'unsupported question unexpectedly succeeded'
} catch {
    Assert-True ($_.Exception.Response.StatusCode.value__ -eq 422) 'unsupported scene is rejected at the MVP boundary'
}

$web = Invoke-WebRequest 'http://localhost:8080' -UseBasicParsing
Assert-True ($web.StatusCode -eq 200) 'Stage 2 web application is reachable'
Write-Host "Stage 2 smoke test completed." -ForegroundColor Cyan
