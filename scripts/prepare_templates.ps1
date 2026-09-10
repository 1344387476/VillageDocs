param(
    [string]$Python = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot $Python
$Soffice = Join-Path $ProjectRoot "runtime\libreoffice\program\soffice.exe"
$env:PYTHONPATH = $ProjectRoot

if (-not (Test-Path -LiteralPath $Soffice)) {
    throw "未找到内置 LibreOffice：$Soffice"
}

& $PythonPath (Join-Path $ProjectRoot "tools\prepare_templates.py") `
    --source-dir (Join-Path $ProjectRoot "resources\templates\source") `
    --output-dir (Join-Path $ProjectRoot "resources\templates\house_building") `
    --soffice $Soffice
if ($LASTEXITCODE -ne 0) {
    throw "母版规范化失败（退出码 $LASTEXITCODE）"
}
