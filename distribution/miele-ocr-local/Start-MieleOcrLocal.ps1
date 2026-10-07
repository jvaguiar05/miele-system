[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Add-Type -AssemblyName System.Windows.Forms

$installRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $installRoot "venv\Scripts\python.exe"
$tool = Join-Path $installRoot "app\tools\miele_ocr_local.py"
$outputRoot = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Miele OCR"
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $tool)) {
    [System.Windows.Forms.MessageBox]::Show(
        "A instalação está incompleta. Execute novamente o instalador do Miele OCR Local.",
        "Miele OCR Local", "OK", "Error"
    ) | Out-Null
    exit 1
}

$choice = [System.Windows.Forms.MessageBox]::Show(
    "Escolha Sim para processar uma pasta inteira ou Não para selecionar PDFs específicos.",
    "Miele OCR Local", "YesNoCancel", "Question"
)
if ($choice -eq "Cancel") { exit 0 }
$inputs = @()
if ($choice -eq "Yes") {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Selecione a pasta que contém os PDFs"
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -ne "OK") { exit 0 }
    $inputs = @($dialog.SelectedPath)
} else {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Selecione os PDFs"
    $dialog.Filter = "Documentos PDF (*.pdf)|*.pdf"
    $dialog.Multiselect = $true
    if ($dialog.ShowDialog() -ne "OK") { exit 0 }
    $inputs = @($dialog.FileNames)
}

Write-Host "Miele OCR Local"
Write-Host "Os originais não serão alterados nem enviados pela internet."
Write-Host "Saída: $outputRoot"
Write-Host "Aguarde; o progresso será mostrado arquivo por arquivo."
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$before = @(Get-ChildItem -LiteralPath $outputRoot -Directory -Filter "miele_ocr_*" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
& $python $tool --workers 1 --output $outputRoot @inputs
$exitCode = $LASTEXITCODE
$after = @(Get-ChildItem -LiteralPath $outputRoot -Directory -Filter "miele_ocr_*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
$newRun = $after | Where-Object { $_.FullName -notin $before } | Select-Object -First 1
if (-not $newRun) { $newRun = $after | Select-Object -First 1 }

if ($exitCode -eq 0 -and $newRun) {
    $packages = Join-Path $newRun.FullName "pacotes"
    [System.Windows.Forms.MessageBox]::Show(
        "Pacotes preparados. A pasta será aberta agora; envie os arquivos .miele.zip pelo botão Importar do Miele.",
        "Miele OCR Local", "OK", "Information"
    ) | Out-Null
    Start-Process explorer.exe -ArgumentList $packages
    exit 0
}
if ($newRun) { Start-Process explorer.exe -ArgumentList $newRun.FullName }
[System.Windows.Forms.MessageBox]::Show(
    "Nenhum pacote foi criado. Consulte relatorio.csv na pasta aberta.",
    "Miele OCR Local", "OK", "Warning"
) | Out-Null
exit $exitCode
