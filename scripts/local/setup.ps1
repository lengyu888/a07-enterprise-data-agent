param(
    [switch]$SkipEmbeddingDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$appDir = Join-Path $repoRoot "services\app"
$webDir = Join-Path $repoRoot "apps\web"
$appEnv = Join-Path $appDir ".env"
$appEnvExample = Join-Path $appDir ".env.example"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js was not found. Install Node.js 22 LTS."
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm.cmd was not found. Make sure Node.js is available on PATH."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[1/4] Creating the Python virtual environment..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            & py -3 -m venv $venvDir
        }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvDir
    } else {
        throw "Python was not found. Install Python 3.12 and enable the py launcher or PATH entry."
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Python virtual environment creation failed."
}

Write-Host "[2/4] Installing backend dependencies..."
& $venvPython -m pip install -r (Join-Path $appDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

Write-Host "[3/4] Installing and building the frontend..."
Push-Location $webDir
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $appEnv)) {
    Copy-Item -LiteralPath $appEnvExample -Destination $appEnv
    Write-Host "Created services/app/.env."
}

if (-not $SkipEmbeddingDownload) {
    Write-Host "[4/4] Downloading the local Chinese embedding model (first run may take a while)..."
    $embeddingCache = Join-Path $appDir ".cache\fastembed"
    New-Item -ItemType Directory -Path $embeddingCache -Force | Out-Null
    $env:A07_EMBEDDING_CACHE = $embeddingCache
    try {
        & $venvPython -c "import os; from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5', cache_dir=os.environ['A07_EMBEDDING_CACHE'])"
        if ($LASTEXITCODE -ne 0) { throw "Embedding model download failed." }
    } finally {
        Remove-Item Env:A07_EMBEDDING_CACHE -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "[4/4] Embedding pre-download skipped; the first startup will require a populated cache."
}

Write-Host "Local dependencies are ready. Next: .\scripts\local\start.ps1"
