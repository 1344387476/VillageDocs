$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = $ProjectRoot
Set-Location -LiteralPath $ProjectRoot
& (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m housebook.app
