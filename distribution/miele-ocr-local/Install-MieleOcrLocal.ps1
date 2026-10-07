[CmdletBinding()]
param(
    [switch]$InstallPythonWithWinget,
    [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    throw "A pasta LOCALAPPDATA do usuário não pôde ser determinada."
}
$localAppData = [System.IO.Path]::GetFullPath($localAppData)
$installRoot = [System.IO.Path]::GetFullPath((Join-Path $localAppData "Miele\OCR Local"))
$expectedInstallRoot = [System.IO.Path]::GetFullPath((Join-Path $localAppData "Miele\OCR Local"))
if ($installRoot -ne $expectedInstallRoot -or $installRoot -eq $localAppData) {
    throw "Destino de instalação inseguro: $installRoot"
}
$payload = Join-Path $PSScriptRoot "app"
$requirements = Join-Path $PSScriptRoot "requirements-ocr-local.txt"
$launcherSource = Join-Path $PSScriptRoot "Start-MieleOcrLocal.ps1"

if (-not (Test-Path -LiteralPath $payload) -or -not (Test-Path -LiteralPath $requirements)) {
    throw "Distribuição incompleta. Extraia todo o ZIP antes de executar o instalador."
}

function Find-Python311 {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += @{ Command = "py"; Prefix = @("-3.11") }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += @{ Command = "python"; Prefix = @() }
    }
    $perUserPython = Join-Path $localAppData "Programs\Python\Python311\python.exe"
    if (Test-Path -LiteralPath $perUserPython) {
        $candidates += @{ Command = $perUserPython; Prefix = @() }
    }
    foreach ($candidate in $candidates) {
        try {
            $version = & $candidate.Command @($candidate.Prefix) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -eq "3.11") { return $candidate }
        }
        catch { continue }
    }
    return $null
}

$python = Find-Python311
$wingetAvailable = [bool](Get-Command winget -ErrorAction SilentlyContinue)
$allowWinget = $InstallPythonWithWinget
if (-not $python -and -not $allowWinget -and $wingetAvailable) {
    $answer = Read-Host "Python 3.11 não foi encontrado. Deseja instalá-lo agora pelo winget, somente para este usuário? [S/N]"
    $allowWinget = $answer -match "^[sSyY]"
}
if (-not $python -and $allowWinget) {
    if (-not $wingetAvailable) {
        throw "winget não está disponível. Instale Python 3.11 manualmente em https://www.python.org/downloads/"
    }
    Write-Host "Instalando Python 3.11 por solicitação explícita do usuário..."
    & winget install --id Python.Python.3.11 --exact --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "A instalação do Python 3.11 pelo winget falhou." }
    $python = Find-Python311
}
if (-not $python) {
    throw @"
Python 3.11 não foi encontrado. Nenhuma instalação foi iniciada automaticamente.
Instale-o em https://www.python.org/downloads/ ou execute novamente com:
  .\Install-MieleOcrLocal.ps1 -InstallPythonWithWinget
"@
}

$approved = $InstallDependencies
if (-not $approved) {
    $answer = Read-Host "O instalador precisa baixar as dependências OCR versionadas. Continuar? [S/N]"
    $approved = $answer -match "^[sSyY]"
}
if (-not $approved) { throw "Instalação cancelada; nenhuma dependência foi baixada." }

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
$installedApp = [System.IO.Path]::GetFullPath((Join-Path $installRoot "app"))
$expectedApp = [System.IO.Path]::GetFullPath((Join-Path $expectedInstallRoot "app"))
if ($installedApp -ne $expectedApp -or (Split-Path -Parent $installedApp) -ne $expectedInstallRoot) {
    throw "Pasta gerenciada inválida; a instalação foi interrompida: $installedApp"
}
if (Test-Path -LiteralPath $installedApp) {
    $appItem = Get-Item -LiteralPath $installedApp -Force
    if (($appItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "A pasta gerenciada é um link/reparse point e não será alterada: $installedApp"
    }
} else {
    New-Item -ItemType Directory -Path $installedApp | Out-Null
}
Copy-Item -Path (Join-Path $payload "*") -Destination $installedApp -Recurse -Force
Copy-Item -LiteralPath $requirements -Destination (Join-Path $installRoot "requirements-ocr-local.txt") -Force
Copy-Item -LiteralPath $launcherSource -Destination (Join-Path $installRoot "Start-MieleOcrLocal.ps1") -Force

$venvPython = Join-Path $installRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python.Command @($python.Prefix) -m venv (Join-Path $installRoot "venv")
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar o ambiente privado do Miele OCR Local." }
}
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $installRoot "requirements-ocr-local.txt")
if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar as dependências OCR." }
& $venvPython -c "import pypdf, pypdfium2, rapidocr, onnxruntime"
if ($LASTEXITCODE -ne 0) { throw "A validação final das dependências OCR falhou." }

$programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcutPath = Join-Path $programs "Miele OCR Local.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $installRoot 'Start-MieleOcrLocal.ps1')`""
$shortcut.WorkingDirectory = $installRoot
$shortcut.Description = "Preparar PDFs para importação segura no Miele"
$shortcut.Save()

Write-Host "Miele OCR Local instalado para este usuário."
Write-Host "Atalho criado: Menu Iniciar > Miele OCR Local."
Write-Host "Abra o atalho para selecionar uma pasta ou seus PDFs."
