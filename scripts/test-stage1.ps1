$ErrorActionPreference = 'Stop'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host "Checking Stage 1 Docker services..." -ForegroundColor Cyan
$services = docker compose ps --format json | ConvertFrom-Json
Assert-True (($services | Measure-Object).Count -eq 3) 'three services are running'
Assert-True ((@($services | Where-Object { $_.Health -ne 'healthy' })).Count -eq 0) 'all services are healthy'

$bootstrap = Invoke-RestMethod 'http://localhost:8000/api/v1/system/bootstrap'
$summary = Invoke-RestMethod 'http://localhost:8000/api/v1/catalog/summary'
$tables = Invoke-RestMethod 'http://localhost:8000/api/v1/catalog/tables'
$relations = Invoke-RestMethod 'http://localhost:8000/api/v1/catalog/relations'
$knowledge = Invoke-RestMethod 'http://localhost:8000/api/v1/knowledge/overview'
$metrics = Invoke-RestMethod 'http://localhost:8000/api/v1/knowledge/metrics'

Assert-True ($bootstrap.phase -eq 'phase-1') 'bootstrap contract reports phase 1'
Assert-True ($summary.table_count -eq 10) 'catalog contains 9+1 demo tables'
Assert-True ($summary.column_count -ge 60) 'catalog contains scanned columns'
Assert-True ($summary.relation_count -ge 10) 'catalog contains verified foreign-key relations'
Assert-True ([long]$summary.total_rows -ge 100000) 'demo dataset contains at least 100,000 rows'
Assert-True ($summary.dataset_max_business_date -eq '2025-12-29') 'fixed business date is configured'
Assert-True (@($tables).Count -eq 10) 'table list API returns all demo tables'
Assert-True (@($relations).Count -eq $summary.relation_count) 'relation list matches summary'
Assert-True (@($knowledge.topics).Count -eq 3) 'three manufacturing topics are available'
Assert-True (@($metrics).Count -ge 5) 'seeded metric definitions are available'

$refresh = Invoke-RestMethod -Method Post 'http://localhost:8000/api/v1/catalog/refresh'
Assert-True ($refresh.tables -eq 10) 'metadata refresh is idempotent'

$web = Invoke-WebRequest 'http://localhost:8080' -UseBasicParsing
Assert-True ($web.StatusCode -eq 200) 'Stage 1 web application is reachable'
Write-Host "Stage 1 smoke test completed." -ForegroundColor Cyan
