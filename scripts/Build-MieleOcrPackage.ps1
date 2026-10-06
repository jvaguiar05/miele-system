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
    (Join-Path $repository ".venv\Scripts\python.exe"),
    (Join-Path $repository ".venv-local\Scripts\python.exe")
)
$python = $null
foreach ($candidate in $pythonCandidates) {
    if (-not (Test-Path -LiteralPath $candidate)) {
        continue
    }
    & $candidate -c "import pypdf, pypdfium2, rapidocr, onnxruntime" 2>$null
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
& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "A preparação OCR falhou. Consulte a mensagem acima; nenhum dado foi enviado ao Miele."
}
