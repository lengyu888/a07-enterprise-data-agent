param(
    [switch]$SkipBuild,
    [int]$StartupTimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$appDir = Join-Path $repoRoot "services\app"
$webDir = Join-Path $repoRoot "apps\web"
$runtimeDir = Join-Path $repoRoot ".local-runtime"
$stateFile = Join-Path $runtimeDir "processes.json"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$viteEntry = Join-Path $webDir "node_modules\vite\bin\vite.js"
$appEnv = Join-Path $appDir ".env"

function Assert-PortAvailable([int]$Port) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
    } catch {
        throw "Port $Port is already in use. Stop the process that owns the port first."
    } finally {
        $listener.Stop()
    }
}

function Wait-ForUrl([string]$Url, [System.Diagnostics.Process]$Process, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) { return $false }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw ".venv was not found. Run .\scripts\local\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $viteEntry)) {
    throw "Frontend dependencies were not found. Run .\scripts\local\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $appEnv)) {
    throw "services/app/.env was not found. Copy services/app/.env.example and configure the database."
}
if (Test-Path -LiteralPath $stateFile) {
    throw "A local runtime state file already exists. Run .\scripts\local\stop.ps1 first."
}

Assert-PortAvailable 8000
Assert-PortAvailable 8080

if (-not $SkipBuild) {
    Write-Host "[1/3] Building frontend production assets..."
    Push-Location $webDir
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally {
        Pop-Location
    }
} elseif (-not (Test-Path -LiteralPath (Join-Path $webDir "dist\index.html"))) {
    throw "Frontend dist is missing; -SkipBuild cannot be used."
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$backendOut = Join-Path $runtimeDir "backend.out.log"
$backendErr = Join-Path $runtimeDir "backend.err.log"
$frontendOut = Join-Path $runtimeDir "frontend.out.log"
$frontendErr = Join-Path $runtimeDir "frontend.err.log"

Write-Host "[2/3] Starting FastAPI and automatic migrations..."
$backend = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $appDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr

if (-not (Wait-ForUrl "http://127.0.0.1:8000/api/health" $backend $StartupTimeoutSeconds)) {
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    if (Test-Path -LiteralPath $backendErr) { Get-Content -LiteralPath $backendErr -Tail 30 }
    throw "Backend startup failed. Check PostgreSQL/pgvector and services/app/.env."
}

Write-Host "[3/3] Starting the Vue desktop workspace..."
$node = (Get-Command node -ErrorAction Stop).Source
$frontend = Start-Process -FilePath $node `
    -ArgumentList @($viteEntry, "preview", "--host", "127.0.0.1", "--port", "8080", "--strictPort") `
    -WorkingDirectory $webDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr

if (-not (Wait-ForUrl "http://127.0.0.1:8080" $frontend 30)) {
    if (-not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force }
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    if (Test-Path -LiteralPath $frontendErr) { Get-Content -LiteralPath $frontendErr -Tail 30 }
    throw "Frontend startup failed."
}

@{
    backend = @{ pid = $backend.Id; process_name = $backend.ProcessName }
    frontend = @{ pid = $frontend.Id; process_name = $frontend.ProcessName }
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $stateFile -Encoding UTF8

Write-Host "System URL: http://127.0.0.1:8080"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "Logs: $runtimeDir"
Write-Host "Stop command: .\scripts\local\stop.ps1"
