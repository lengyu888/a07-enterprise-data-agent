$ErrorActionPreference = 'Stop'
$QuestionText = '{"Alarm":"\u672c\u6708\u5404\u8bbe\u5907\u62a5\u8b66\u6b21\u6570\u6392\u540d","Downtime":"\u672c\u6708\u5404\u8bbe\u5907\u975e\u8ba1\u5212\u505c\u673a\u6b21\u6570\u6392\u540d"}' | ConvertFrom-Json

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host 'Checking Stage 5 Docker services...' -ForegroundColor Cyan
$services = docker compose ps --format json | ConvertFrom-Json
Assert-True (($services | Measure-Object).Count -eq 3) 'three services are running'
Assert-True ((@($services | Where-Object { $_.Health -ne 'healthy' })).Count -eq 0) 'all services are healthy'

$ready = Invoke-RestMethod 'http://localhost:8000/api/ready'
$bootstrap = Invoke-RestMethod 'http://localhost:8000/api/v1/system/bootstrap'
$capabilities = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/capabilities'
Assert-True ($ready.dependencies.deepseek -eq 'configured') 'DeepSeek was configured from the frontend page'
Assert-True ($bootstrap.phase -eq 'phase-5') 'bootstrap contract reports phase 5'
Assert-True (@($capabilities.equipment_specialization).Count -eq 5) 'five equipment specialization capabilities are exposed'

foreach ($case in @(
    @{ Question = $QuestionText.Alarm; Metric = 'alarm_count' },
    @{ Question = $QuestionText.Downtime; Metric = 'downtime_count' }
)) {
    $body = @{ question = $case.Question; top_k = 10 } | ConvertTo-Json -Compress
    $bundle = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/rag/search' `
        -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    Assert-True ($bundle.metric.metric_code -eq $case.Metric) "RAG selects $($case.Metric)"
    Assert-True ('demo.fact_equipment_event' -in @($bundle.tables.table_name)) "$($case.Metric) retrieves equipment events"
}

$runs = @()
1..3 | ForEach-Object {
    $diagnosis = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/agent/equipment/diagnosis' -TimeoutSec 300
    $runs += $diagnosis
    Assert-True ($diagnosis.status -eq 'completed') "equipment diagnosis run $_ completes"
    Assert-True ($diagnosis.recipe.algorithm -eq 'IsolationForest') "run $_ uses IsolationForest"
    Assert-True ($diagnosis.assessment.top_equipment.equipment_id -eq 'E08') "run $_ identifies E08 as top anomaly"
    Assert-True ($diagnosis.assessment.top_equipment.anomaly_days -ge 5) "run $_ finds at least five anomaly days"
    Assert-True (@($diagnosis.ranking).Count -eq 9) "run $_ ranks all nine machines"
    Assert-True (@($diagnosis.deviations).Count -eq 5) "run $_ returns five robust deviations"
    Assert-True (@($diagnosis.trace).Count -eq 5) "run $_ exposes five LangGraph steps"
}

$latest = $runs[-1]
Assert-True ($latest.assessment.top_equipment.max_single_duration -eq 145) 'E08 maximum single downtime is 145 minutes'
Assert-True ($latest.timeline.Count -eq 29) 'top machine timeline contains 29 scoring days'
Assert-True ($latest.recipe.parameters.random_state -eq 42) 'algorithm random seed is fixed at 42'
Assert-True ($latest.recipe.features.Count -eq 7) 'reviewed recipe contains seven daily features'

$evaluation = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/evaluation/stage5'
Assert-True ($evaluation.passed) 'equipment diagnosis has three consecutive successful runs'
$web = Invoke-WebRequest 'http://localhost:8080' -UseBasicParsing
Assert-True ($web.StatusCode -eq 200) 'Stage 5 web application is reachable'
Write-Host 'Stage 5 equipment anomaly acceptance completed.' -ForegroundColor Cyan
