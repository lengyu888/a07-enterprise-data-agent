Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$stateFile = Join-Path $repoRoot ".local-runtime\processes.json"

if (-not (Test-Path -LiteralPath $stateFile)) {
    Write-Host "Local services are not running or the state file is missing."
    exit 0
}

$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
foreach ($serviceName in @("frontend", "backend")) {
    $entry = $state.$serviceName
    $process = Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Host "$serviceName is already stopped."
        continue
    }
    if ($process.ProcessName -ne [string]$entry.process_name) {
        Write-Warning "Skipped PID $($entry.pid): the process name changed, so it may be unrelated."
        continue
    }
    Stop-Process -Id $process.Id -Force
    Write-Host "Stopped $serviceName (PID $($process.Id))."
}

Remove-Item -LiteralPath $stateFile -Force
Write-Host "Local services stopped."
