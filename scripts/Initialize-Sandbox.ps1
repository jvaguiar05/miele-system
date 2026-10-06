[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Join-Path $repositoryRoot "backend"
$sandboxDirectory = Join-Path $repositoryRoot ".sandbox"
$sandboxDatabase = Join-Path $sandboxDirectory "miele-sandbox.sqlite3"
$pyLauncherPython = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyLauncherPython = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
}
$pythonCandidates = @(
    (Join-Path $repositoryRoot ".venv-local\Scripts\python.exe"),
    (Join-Path $repositoryRoot ".venv\Scripts\python.exe"),
    ($repositoryRoot + ".venv\Scripts\python.exe"),
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    $pyLauncherPython
) | Where-Object { $_ } | Select-Object -Unique
$python = $null
foreach ($candidate in $pythonCandidates) {
    if ((Test-Path -LiteralPath $candidate)) {
        $candidateWorks = $false
        try {
            & $candidate -c "import django, pypdf, pypdfium2, rapidocr, onnxruntime" 2>$null
            $candidateWorks = $LASTEXITCODE -eq 0
        }
        catch {
            $candidateWorks = $false
        }
        if ($candidateWorks) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    throw "Nenhum Python com as dependências do projeto (Django, PDF e OCR) foi encontrado. Recrie .venv-local/.venv ou instale requirements/requirements.txt no Python 3.11."
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
