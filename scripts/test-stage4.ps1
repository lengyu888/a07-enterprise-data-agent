$ErrorActionPreference = 'Stop'
$QuestionText = '{"Pareto":"\u672c\u6708\u7f3a\u9677\u7c7b\u578b Pareto \u5206\u6790","Trend":"\u6700\u8fd130\u5929\u6bcf\u65e5\u826f\u7387\u8d8b\u52bf","Comparison":"\u5bf9\u6bd4\u672c\u6708\u4e0e\u4e0a\u6708\u603b\u4f53\u826f\u7387"}' | ConvertFrom-Json

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAILED: $Message" }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

function Invoke-AgentQuestion {
    param([string]$Question)
    $body = @{ question = $Question } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/agent/runs' `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 300
}

Write-Host 'Checking Stage 4 Docker services...' -ForegroundColor Cyan
$services = docker compose -f compose.yml -f compose.deepseek.yml ps --format json | ConvertFrom-Json
Assert-True (($services | Measure-Object).Count -eq 3) 'three services are running'
Assert-True ((@($services | Where-Object { $_.Health -ne 'healthy' })).Count -eq 0) 'all services are healthy'

$ready = Invoke-RestMethod 'http://localhost:8000/api/ready'
$bootstrap = Invoke-RestMethod 'http://localhost:8000/api/v1/system/bootstrap'
$capabilities = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/capabilities'
Assert-True ($ready.dependencies.deepseek -eq 'configured') 'DeepSeek Docker Secret is mounted'
Assert-True ($bootstrap.phase -eq 'phase-4') 'bootstrap contract reports phase 4'
Assert-True (@($capabilities.quality_specialization).Count -eq 5) 'five quality specialization capabilities are exposed'

$pareto = Invoke-AgentQuestion $QuestionText.Pareto
Assert-True ($pareto.evidence.metric.code -eq 'defect_count') 'Pareto RAG selects defect_count metric'
Assert-True ($pareto.chart.type -eq 'pareto') 'Pareto result uses combination chart contract'
Assert-True (@($pareto.result.rows).Count -eq 6) 'six real defect categories are returned'
Assert-True ([double]$pareto.result.rows[-1].cumulative_share -eq 100) 'Pareto cumulative share closes at 100 percent'
Assert-True (@($pareto.sql.referenced_tables).Count -eq 2) 'Pareto SQL stays inside two approved quality tables'

$trend = Invoke-AgentQuestion $QuestionText.Trend
Assert-True ($trend.chart.type -eq 'line') 'daily yield trend uses line chart contract'
Assert-True (@($trend.result.rows).Count -eq 30) 'daily yield trend returns 30 business dates'
Assert-True ($trend.result.rows[0].business_date -eq '2025-11-30') 'trend starts at the fixed 30-day boundary'
Assert-True ($trend.result.rows[-1].business_date -eq '2025-12-29') 'trend ends at the dataset anchor'

$comparison = Invoke-AgentQuestion $QuestionText.Comparison
Assert-True (@($comparison.result.rows).Count -eq 2) 'month-over-month query returns two periods'
Assert-True ($comparison.result.rows[0].business_month -eq '2025-11') 'comparison includes previous natural month'
Assert-True ($comparison.result.rows[1].business_month -eq '2025-12') 'comparison includes current anchored month'

$brief = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/agent/quality/brief' -TimeoutSec 300
Assert-True ($brief.status -eq 'completed') 'LangGraph quality brief completes'
Assert-True (@($brief.evidence).Count -eq 3) 'quality brief contains three RAG evidence bundles'
Assert-True (@($brief.trace).Count -eq 4) 'quality brief exposes four LangGraph steps'
Assert-True (@($brief.charts.trend).Count -eq 30) 'quality cockpit receives 30 trend points'
Assert-True ($brief.assessment.yield_delta_pp -eq -1.19) 'quality brief calculates -1.19 percentage-point change'

$evaluation = Invoke-RestMethod 'http://localhost:8000/api/v1/agent/evaluation/stage4'
Assert-True ($evaluation.passed) 'quality scenario has at least three consecutive successful runs'
$web = Invoke-WebRequest 'http://localhost:8080' -UseBasicParsing
Assert-True ($web.StatusCode -eq 200) 'Stage 4 web application is reachable'
Write-Host 'Stage 4 quality analysis acceptance completed.' -ForegroundColor Cyan
