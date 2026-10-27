# Runs the real backend journey in a dedicated database; never drops existing data.
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$apiRoot = Join-Path $repoRoot 'apps\api'
$variantRoot = Join-Path $repoRoot 'variants\microsoft-power-platform'
$envFile = Join-Path $repoRoot '.env'
$python = Join-Path $apiRoot '.venv\Scripts\python.exe'
$database = 'processmind_power_e2e'

if (-not (Test-Path -LiteralPath $envFile)) { throw 'Root .env is required' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the API development venv first' }
$lines = Get-Content -LiteralPath $envFile
$passwordLine = $lines | Where-Object { $_ -match '^POSTGRES_PASSWORD=' } | Select-Object -First 1
$userLine = $lines | Where-Object { $_ -match '^POSTGRES_USER=' } | Select-Object -First 1
if (-not $passwordLine) { throw 'POSTGRES_PASSWORD is required' }
$password = $passwordLine.Substring('POSTGRES_PASSWORD='.Length).Trim('"')
$dbUser = if ($userLine) { $userLine.Substring('POSTGRES_USER='.Length).Trim('"') } else { 'processmind' }
if ($dbUser -notmatch '^[a-zA-Z_][a-zA-Z0-9_]*$') { throw 'Invalid POSTGRES_USER' }

Push-Location $repoRoot
try {
    $exists = docker compose exec -T db psql -U $dbUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$database'"
    if ($LASTEXITCODE -ne 0) { throw 'Could not query test database' }
    if (-not $exists) {
        docker compose exec -T db psql -U $dbUser -d postgres -c "CREATE DATABASE $database"
        if ($LASTEXITCODE -ne 0) { throw 'Could not create test database' }
    }
    $encoded = [Uri]::EscapeDataString($password)
    $env:DATABASE_URL = "postgresql+psycopg://${dbUser}:${encoded}@127.0.0.1:5432/$database"
    $env:RUN_DB_TESTS = '1'
    $env:PYTHONPATH = "$apiRoot;$variantRoot"
    Push-Location $apiRoot
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
        & $python -m pytest (Join-Path $variantRoot 'tests\test_live_backend.py') -q
        if ($LASTEXITCODE -ne 0) { throw 'Live backend test failed' }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
