[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Join-Path $repositoryRoot "backend"
$sandboxDatabase = Join-Path $repositoryRoot ".sandbox\miele-sandbox.sqlite3"
$pythonCandidates = @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path $repositoryRoot ".venv-local\Scripts\python.exe"),
    (Join-Path $repositoryRoot ".venv\Scripts\python.exe")
) | Where-Object { $_ }
$python = $null
foreach ($candidate in $pythonCandidates) {
    if ((Test-Path -LiteralPath $candidate)) {
        & $candidate --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    throw "Nenhum ambiente Python funcional foi encontrado. Recrie .venv-local ou .venv antes de iniciar o sandbox."
}
if (-not (Test-Path -LiteralPath $sandboxDatabase)) {
    throw "Banco sandbox não encontrado. Execute ./scripts/Initialize-Sandbox.ps1 antes de iniciar."
}

# These overrides prevent this local process from using production data or Drive credentials.
$env:DATABASE_URL = "sqlite:///$($sandboxDatabase.Replace('\\', '/'))"
$env:SECRET_KEY = "miele-local-sandbox-not-for-production"
$env:DEBUG = "True"
$env:ALLOWED_HOSTS = "127.0.0.1,localhost"
$env:CORS_ALLOW_ALL_ORIGINS = "True"
$env:GDRIVE_CLIENT_ID = ""
$env:GDRIVE_CLIENT_SECRET = ""
$env:GDRIVE_REFRESH_TOKEN = ""
$env:GDRIVE_CLIENTS_FOLDER_ID = ""
$env:GDRIVE_PERDCOMPS_FOLDER_ID = ""

Push-Location $projectRoot
try {
    & $python manage.py runserver 127.0.0.1:8001
}
finally {
    Pop-Location
}
