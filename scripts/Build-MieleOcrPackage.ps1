param(
    [Parameter(Mandatory = $true)]
    [string[]]$InputPath,
    [string]$OutputDirectory = ".sandbox\miele-ocr-output",
    [ValidateRange(1, 4)]
    [int]$Workers = 1
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$repository = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    @{ Command = (Join-Path $repository ".venv\Scripts\python.exe"); Prefix = @(); Local = $true },
    @{ Command = (Join-Path $repository ".venv-local\Scripts\python.exe"); Prefix = @(); Local = $true },
    @{ Command = "py"; Prefix = @("-3.11"); Local = $false }
)
$python = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate.Local -and -not (Test-Path -LiteralPath $candidate.Command)) {
        continue
    }
    try {
        & $candidate.Command @($candidate.Prefix) -c "import pypdf, pypdfium2, rapidocr, onnxruntime" 2>$null
    }
    catch {
        continue
    }
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    throw "Nenhum ambiente Python com as dependências de PDF/OCR foi encontrado. Instale requirements/requirements.txt na .venv."
}

$tool = Join-Path $repository "tools\miele_ocr_local.py"
$output = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory
} else {
    Join-Path $repository $OutputDirectory
}
$arguments = @($tool, "--output", $output, "--workers", "$Workers") + $InputPath
& $python.Command @($python.Prefix) @arguments
if ($LASTEXITCODE -ne 0) {
    throw "A preparação OCR falhou. Consulte a mensagem acima; nenhum dado foi enviado ao Miele."
}
