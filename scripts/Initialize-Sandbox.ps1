[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Join-Path $repositoryRoot "backend"
$sandboxDirectory = Join-Path $repositoryRoot ".sandbox"
$sandboxDatabase = Join-Path $sandboxDirectory "miele-sandbox.sqlite3"
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

New-Item -ItemType Directory -Force -Path $sandboxDirectory | Out-Null

# Process-level overrides always win over .env. The original database is never selected.
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
    & $python manage.py migrate --noinput
    & $python manage.py setup_roles

    $userCheck = & $python manage.py shell -c "from django.contrib.auth import get_user_model; print('SANDBOX_USER_EXISTS=' + str(get_user_model().objects.filter(username='sandbox.admin').exists()))" 2>&1
    if ($userCheck -notmatch "SANDBOX_USER_EXISTS=True") {
        Write-Host "Crie agora a senha do administrador local sandbox.admin."
        & $python manage.py create_superuser_with_role --username sandbox.admin --email sandbox.admin@example.test --first-name Sandbox --last-name Admin --role admin
    }

    Write-Host "Sandbox inicializado em: $sandboxDatabase"
    Write-Host "Próximo passo: ./scripts/Start-Sandbox.ps1"
}
finally {
    Pop-Location
}
