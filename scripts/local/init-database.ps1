param(
    [string]$DatabaseHost = "127.0.0.1",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$psql = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psql) {
    throw "psql was not found. Install PostgreSQL 16 and add its bin directory to PATH."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$createDatabaseScript = Join-Path $scriptDir "001-create-database.sql"
$bootstrapScript = Join-Path $repoRoot "infra\postgres\init\001-bootstrap.sql"
$ownershipScript = Join-Path $scriptDir "002-local-ownership.sql"

Write-Host "[1/3] Creating the local database and application role..."
& $psql.Source "--host=$DatabaseHost" "--port=$Port" "--username=$AdminUser" "--dbname=postgres" "--file=$createDatabaseScript"
if ($LASTEXITCODE -ne 0) { throw "Database or role initialization failed." }

Write-Host "[2/3] Enabling extensions and creating base schemas..."
& $psql.Source "--host=$DatabaseHost" "--port=$Port" "--username=$AdminUser" "--dbname=a07_agent" "--file=$bootstrapScript"
if ($LASTEXITCODE -ne 0) {
    throw "Database bootstrap failed. Make sure pgvector is installed for PostgreSQL."
}

Write-Host "[3/3] Granting object ownership to the application role..."
& $psql.Source "--host=$DatabaseHost" "--port=$Port" "--username=$AdminUser" "--dbname=a07_agent" "--file=$ownershipScript"
if ($LASTEXITCODE -ne 0) { throw "Database permission initialization failed." }

Write-Host "Local database is ready: $DatabaseHost`:$Port/a07_agent"
Write-Host "Application role: a07_app"
