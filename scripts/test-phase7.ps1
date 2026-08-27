$ErrorActionPreference = "Stop"

$apiBase = "http://localhost:8000"
$webBase = "http://localhost:8080"

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host "A07 phase 7 interaction and data intake acceptance" -ForegroundColor Cyan

$web = Invoke-WebRequest -UseBasicParsing -Uri $webBase
Assert-True ($web.StatusCode -eq 200) "desktop web is reachable"

$health = Invoke-RestMethod -Uri "$apiBase/api/health"
Assert-True ($health.status -eq "ok") "backend health check passes"
Assert-True ($health.version -eq "0.9.1") "phase 7 patch application version is active"

$composeImages = @(docker compose config --images)
Assert-True ($composeImages.Count -eq 3) "Compose resolves exactly three service images"
Assert-True ($composeImages -contains 'a07-agent-app:0.9.1') "Compose pins the App 0.9.1 image"
Assert-True ($composeImages -contains 'a07-agent-web:0.9.1') "Compose pins the Web 0.9.1 image"

$driverCheck = @(docker compose run --rm --no-deps `
    -e "DATABASE_URL=postgresql://a07_app:a07_local_dev_change_me@postgres:5432/a07_agent" `
    app python -c "from app.core.config import get_settings; from app.core.database import check_database; print(get_settings().database_url.startswith('postgresql+psycopg://') and check_database())")
$driverResult = [string]$driverCheck[$driverCheck.Count - 1]
Assert-True ($driverResult.Trim() -eq 'True') "plain postgresql URL uses psycopg 3 and connects successfully"

$capabilities = Invoke-RestMethod -Uri "$apiBase/api/v1/agent/capabilities"
Assert-True ($capabilities.interaction.multi_turn) "multi-turn follow-up is enabled"
Assert-True ($capabilities.interaction.cancellable) "cooperative cancellation is enabled"
Assert-True ($capabilities.interaction.retryable) "run retry is enabled"

$templates = Invoke-RestMethod -Uri "$apiBase/api/v1/data-imports/templates"
Assert-True ($templates.Count -eq 3) "exactly three fixed CSV templates are exposed"
Assert-True (($templates.code -join ',') -eq 'quality_inspection,equipment_event,production_output') "templates match the three manufacturing scenes"
Assert-True (($templates | Where-Object { $_.limits.max_rows -ne 500 }).Count -eq 0) "all imports are capped at 500 rows"

$before = @(Invoke-RestMethod -Uri "$apiBase/api/v1/data-imports?limit=30").Count
$invalidBody = @{ template_code = 'production_output'; filename = 'invalid.csv'; csv_text = "wrong,header`n1,2" } | ConvertTo-Json
$rejected = $false
try {
    Invoke-RestMethod -Method Post -Uri "$apiBase/api/v1/data-imports" -ContentType 'application/json' -Body $invalidBody | Out-Null
} catch {
    $rejected = $_.Exception.Response.StatusCode.value__ -eq 422
}
Assert-True $rejected "invalid CSV header is rejected"
$after = @(Invoke-RestMethod -Uri "$apiBase/api/v1/data-imports?limit=30").Count
Assert-True ($before -eq $after) "rejected CSV creates no import batch"

$runId = [guid]::NewGuid().ToString()
$cancel = Invoke-RestMethod -Method Post -Uri "$apiBase/api/v1/agent/runs/$runId/cancel"
Assert-True ($cancel.accepted) "cancel request is accepted before or during run creation"

Write-Host "All phase 7 API checks passed." -ForegroundColor Cyan
Write-Host "Run tests/e2e/test_phase7_workflow_ui.py for the desktop import and contextual follow-up flow." -ForegroundColor DarkGray
