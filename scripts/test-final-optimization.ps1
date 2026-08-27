$ErrorActionPreference = "Stop"

$apiBase = "http://localhost:8000"
$webBase = "http://localhost:8080"

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) {
        throw "FAILED: $Message"
    }
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host "A07 final optimization acceptance" -ForegroundColor Cyan

$web = Invoke-WebRequest -UseBasicParsing -Uri $webBase
Assert-True ($web.StatusCode -eq 200) "desktop web is reachable"

$health = Invoke-RestMethod -Uri "$apiBase/api/health"
Assert-True ($health.status -eq "ok") "backend health check passes"

$capabilities = Invoke-RestMethod -Uri "$apiBase/api/v1/agent/capabilities"
Assert-True ($capabilities.pipeline[0] -eq "contextualize") "contextual follow-up is the optional first Agent node"
Assert-True ($capabilities.pipeline.Count -eq 10) "Agent capability pipeline exposes ten nodes"

$ambiguousBody = '{"question":"\u5206\u6790\u4e00\u4e0b\u8bbe\u5907"}'
$clarification = Invoke-RestMethod -Method Post -Uri "$apiBase/api/v1/agent/runs" -ContentType "application/json" -Body $ambiguousBody
Assert-True ($clarification.status -eq "needs_clarification") "ambiguous question is intercepted"
Assert-True ($clarification.missing_fields.Count -ge 1) "missing fields are returned"
Assert-True ($clarification.options.Count -eq 3) "three complete follow-up questions are returned"

$evaluation = Invoke-RestMethod -Uri "$apiBase/api/v1/agent/evaluation/overview"
Assert-True ($evaluation.metrics.Count -eq 6) "quality dashboard exposes six auditable gates"
Assert-True ($evaluation.rag.case_count -eq 16) "RAG benchmark contains sixteen fixed cases"
Assert-True ($evaluation.rag.passed_cases -eq $evaluation.rag.case_count) "all fixed RAG cases pass"
Assert-True ($evaluation.rag.required_table_recall_pct -eq 100) "required-table recall is 100 percent"
Assert-True ($evaluation.rag.metric_accuracy_pct -eq 100) "metric recognition accuracy is 100 percent"

Write-Host "All final optimization checks passed." -ForegroundColor Cyan
Write-Host "CSV and PNG downloads are covered by tests/e2e/test_final_analysis_quality_ui.py." -ForegroundColor DarkGray
