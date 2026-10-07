[CmdletBinding()]
param(
    [string]$Version = "1.0.0",
    [string]$OutputDirectory = ".sandbox\miele-ocr-distribution"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$repository = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repository "distribution\miele-ocr-local"
$output = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory
} else {
    Join-Path $repository $OutputDirectory
}
if ($Version -notmatch "^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$") {
    throw "Versão inválida. Use o formato 1.2.3 ou 1.2.3-beta.1."
}
$toolSource = Get-Content -LiteralPath (Join-Path $repository "tools\miele_ocr_local.py") -Raw
$toolVersionMatch = [regex]::Match($toolSource, 'TOOL_VERSION\s*=\s*"([^"]+)"')
if (-not $toolVersionMatch.Success -or $toolVersionMatch.Groups[1].Value -ne $Version) {
    throw "A versão da distribuição ($Version) deve ser igual a TOOL_VERSION no gerador."
}

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("miele-ocr-dist-" + [guid]::NewGuid().ToString("N"))
$packageName = "Miele-OCR-Local-$Version"
$stage = Join-Path $temporaryRoot $packageName
$app = Join-Path $stage "app"
$zip = Join-Path $output "$packageName.zip"
try {
    New-Item -ItemType Directory -Force -Path $app | Out-Null
    Copy-Item -Path (Join-Path $source "*") -Destination $stage -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $repository "requirements\ocr-local.txt") -Destination (Join-Path $stage "requirements-ocr-local.txt")
    Copy-Item -LiteralPath (Join-Path $repository "LICENSE") -Destination (Join-Path $stage "LICENSE.txt")

    $runtimeFiles = @(
        "backend\apps\perdcomps\__init__.py",
        "backend\apps\perdcomps\import_files.py",
        "backend\apps\perdcomps\import_parser.py",
        "backend\apps\perdcomps\import_pdf_worker.py",
        "backend\apps\perdcomps\ocr_package.py",
        "tools\miele_ocr_local.py"
    )
    foreach ($relative in $runtimeFiles) {
        $from = Join-Path $repository $relative
        if (-not (Test-Path -LiteralPath $from)) { throw "Arquivo obrigatório ausente: $relative" }
        $to = Join-Path $app $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
        Copy-Item -LiteralPath $from -Destination $to -Force
    }
    Set-Content -LiteralPath (Join-Path $stage "VERSION.txt") -Value $Version -Encoding ascii
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Distribuição criada sem credenciais: $zip"
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        $resolvedTemporary = [System.IO.Path]::GetFullPath($temporaryRoot)
        $temporaryParent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
        if ((Split-Path -Parent $resolvedTemporary).TrimEnd('\') -ne $temporaryParent -or
                (Split-Path -Leaf $resolvedTemporary) -notmatch '^miele-ocr-dist-[0-9a-f]{32}$') {
            throw "Pasta temporária insegura; limpeza recusada: $resolvedTemporary"
        }
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
