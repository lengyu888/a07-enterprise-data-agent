$ErrorActionPreference = 'Stop'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host 'Checking Stage 6 Docker services...' -ForegroundColor Cyan
$services = docker compose ps --format json | ConvertFrom-Json
Assert-True (($services | Measure-Object).Count -eq 3) 'three services are running'
Assert-True ((@($services | Where-Object { $_.Health -ne 'healthy' })).Count -eq 0) 'all services are healthy'

$ready = Invoke-RestMethod 'http://localhost:8000/api/ready'
$bootstrap = Invoke-RestMethod 'http://localhost:8000/api/v1/system/bootstrap'
$capabilities = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/capabilities'
$recipes = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/algorithms'
Assert-True ($ready.dependencies.deepseek -eq 'configured') 'DeepSeek was configured from the frontend page'
Assert-True ($bootstrap.phase -eq 'phase-6') 'bootstrap contract reports phase 6'
Assert-True (@($capabilities.production_specialization).Count -eq 4) 'four production capabilities are exposed'
Assert-True ($recipes.count -eq 6) 'six reviewed algorithm recipes are published'

$suite = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/agent/algorithms/evaluate' -TimeoutSec 300
Assert-True ($suite.status -eq 'completed') 'six-algorithm evaluation completes'
Assert-True ($suite.algorithm_count -eq 6) 'evaluation executes six algorithms'
Assert-True ($suite.passed_count -eq 6) 'all six algorithm templates pass engineering acceptance'
$algorithmNames = @($suite.algorithms | ForEach-Object { $_.algorithm })
foreach ($name in @('LinearRegression', 'LogisticRegression', 'DecisionTree', 'RandomForest', 'KMeans', 'IsolationForest')) {
    Assert-True ($name -in $algorithmNames) "$name recipe is evaluated"
}

$runs = @()
1..3 | ForEach-Object {
    $trend = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/agent/production/trend' -TimeoutSec 300
    $runs += $trend
    Assert-True ($trend.status -eq 'completed') "production trend run $_ completes"
    Assert-True ($trend.recipe.algorithm -eq 'LinearRegression') "run $_ uses reviewed LinearRegression recipe"
    Assert-True ($trend.assessment.final_output -eq 74535) "run $_ returns stable final-process output"
    Assert-True ($trend.assessment.plan_attainment -eq 95.86) "run $_ returns stable plan attainment"
    Assert-True ($trend.assessment.attention_line.line_id -eq 'L02') "run $_ identifies L02 as attention line"
    Assert-True (@($trend.ranking).Count -eq 3) "run $_ ranks three production lines"
    Assert-True (@($trend.daily_trend).Count -eq 29) "run $_ returns 29-day daily trend"
    Assert-True (@($trend.trace).Count -eq 5) "run $_ exposes five LangGraph steps"
}

$latest = $runs[-1]
Assert-True ($latest.assessment.attention_line.slope_per_day -eq -44.61) 'L02 seven-day slope is reproducible'
Assert-True ($latest.assessment.trend_disclaimer -match '不是未来产量预测') 'trend result carries a non-forecast boundary'
Assert-True ($latest.recipe.parameters.mode -eq 'trend_calculation') 'trend and model-acceptance modes are separated'

$evaluation = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/evaluation/stage6'
Assert-True ($evaluation.passed) 'Stage 6 has three production successes and a six-algorithm run'
$web = Invoke-WebRequest 'http://localhost:8080' -UseBasicParsing
Assert-True ($web.StatusCode -eq 200) 'Stage 6 web application is reachable'
Write-Host 'Stage 6 production and six-algorithm acceptance completed.' -ForegroundColor Cyan
