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
& $Python (Join-Path $ProjectRoot "tools\prepare_meeting_templates.py")
if ($LASTEXITCODE -ne 0) { throw "会议记录模板准备失败，退出码：$LASTEXITCODE" }
if (-not $SkipTests) {
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "自动化测试失败，退出码：$LASTEXITCODE" }
}
$BundledLo = Join-Path $ProjectRoot "runtime\libreoffice"
$env:HOUSEBOOK_BUNDLED_LO = $BundledLo
$DistPath = Join-Path $ProjectRoot "dist\release-1.1.0-meeting-v4"
$WorkPath = Join-Path $ProjectRoot "build\release-1.1.0-meeting-v4"
if (Test-Path -LiteralPath $DistPath) { throw "会议模块构建目录已存在，请手动处理后重试：$DistPath" }
if (Test-Path -LiteralPath $WorkPath) { throw "会议模块工作目录已存在，请手动处理后重试：$WorkPath" }
& $Python -m PyInstaller --noconfirm --distpath $DistPath --workpath $WorkPath (Join-Path $ProjectRoot "village_house_book.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败，退出码：$LASTEXITCODE" }
$PackagedExe = Join-Path $DistPath "VillageDocs\村务材料管理.exe"
$SelfTestRoot = Join-Path $ProjectRoot "tmp\package-self-test-release-1.1.0-meeting-v4"
$SelfTest = Start-Process -FilePath $PackagedExe -ArgumentList "--package-self-test-root=$SelfTestRoot" -Wait -PassThru -WindowStyle Hidden
if ($SelfTest.ExitCode -ne 0) {
    throw "实际发布 EXE 双模块自检失败，退出码：$($SelfTest.ExitCode)，详情：$SelfTestRoot"
}
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
& $Iscc "/DMyOutputBaseFilename=VillageDocs-1.1.0-Meeting-v4-Setup" (Join-Path $ProjectRoot "installer\setup.iss")
if ($LASTEXITCODE -ne 0) { throw "安装包制作失败，退出码：$LASTEXITCODE" }
