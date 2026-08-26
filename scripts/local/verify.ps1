Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

$health = Invoke-RestMethod "http://127.0.0.1:8000/api/health"
$ready = Invoke-RestMethod "http://127.0.0.1:8000/api/ready"
$bootstrap = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/system/bootstrap"
$rag = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/rag/status"
$web = Invoke-WebRequest "http://127.0.0.1:8080" -UseBasicParsing

Assert-True ($health.status -eq "ok") "FastAPI health check"
Assert-True ($ready.dependencies.database -eq "ready") "PostgreSQL is ready"
Assert-True ($bootstrap.phase -eq "phase-6") "all database migrations are applied"
Assert-True ($rag.status -eq "ready") "RAG index is available"
Assert-True ($web.StatusCode -eq 200) "desktop web application is reachable"

Write-Host "Local deployment verification passed. Verify DeepSeek separately in the model settings page." -ForegroundColor Cyan
