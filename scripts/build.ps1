param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "请先运行 scripts\bootstrap.ps1"
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "runtime\libreoffice\program\soffice.exe"))) {
    throw "缺少 runtime\libreoffice，无法制作独立安装包"
}

& (Join-Path $PSScriptRoot "prepare_templates.ps1")
if ($LASTEXITCODE -ne 0) { throw "模板准备失败，退出码：$LASTEXITCODE" }
if (-not $SkipTests) {
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "自动化测试失败，退出码：$LASTEXITCODE" }
}
$BundledLo = Join-Path $ProjectRoot "runtime\libreoffice"
$env:HOUSEBOOK_BUNDLED_LO = $BundledLo
$DistPath = Join-Path $ProjectRoot "dist\release-1.1.0-stable"
$WorkPath = Join-Path $ProjectRoot "build\release-1.1.0-stable"
if (Test-Path -LiteralPath $DistPath) { throw "1.1.0 构建目录已存在，请手动处理后重试：$DistPath" }
if (Test-Path -LiteralPath $WorkPath) { throw "1.1.0 工作目录已存在，请手动处理后重试：$WorkPath" }
& $Python -m PyInstaller --noconfirm --distpath $DistPath --workpath $WorkPath (Join-Path $ProjectRoot "village_house_book.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败，退出码：$LASTEXITCODE" }
if ($SkipInstaller) { return }

$Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $Iscc) {
    $Candidate = Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 6\ISCC.exe"
    if (Test-Path -LiteralPath $Candidate) { $Iscc = $Candidate }
}
if (-not $Iscc) {
    throw "未找到 Inno Setup 6（ISCC.exe）"
}
$env:HOUSEBOOK_DIST_DIR = Join-Path $DistPath "VillageDocs"
& $Iscc (Join-Path $ProjectRoot "installer\setup.iss")
if ($LASTEXITCODE -ne 0) { throw "安装包制作失败，退出码：$LASTEXITCODE" }
