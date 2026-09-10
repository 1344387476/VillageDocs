param(
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $ProjectRoot "runtime\libreoffice"
if (-not $Destination) {
    $Destination = Join-Path $ProjectRoot "build\runtime-zh-cn-1.1.0-r4"
}
if (-not (Test-Path -LiteralPath (Join-Path $Source "program\soffice.exe"))) {
    throw "缺少完整 LibreOffice 来源"
}
if (Test-Path -LiteralPath $Destination) {
    if (Get-ChildItem -LiteralPath $Destination -Force -ErrorAction SilentlyContinue) {
        if (Test-Path -LiteralPath (Join-Path $Destination "program\soffice.exe")) {
            Write-Output (Resolve-Path -LiteralPath $Destination).Path
            exit 0
        }
        throw "中文运行库目录已存在且不完整，请手动处理：$Destination"
    }
} else {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}

function Copy-RelativeFile([string]$RelativePath) {
    $From = Join-Path $Source $RelativePath
    if (-not (Test-Path -LiteralPath $From -PathType Leaf)) { return }
    $To = Join-Path $Destination $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $To) -Force | Out-Null
    Copy-Item -LiteralPath $From -Destination $To
}

function Copy-RelativeTree([string]$RelativePath) {
    $From = Join-Path $Source $RelativePath
    if (-not (Test-Path -LiteralPath $From -PathType Container)) { return }
    $To = Join-Path $Destination $RelativePath
    New-Item -ItemType Directory -Path $To -Force | Out-Null
    Get-ChildItem -LiteralPath $From -Recurse -File | ForEach-Object {
        $Relative = $_.FullName.Substring($From.Length).TrimStart('\')
        $Target = Join-Path $To $Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $Target
    }
}

foreach ($Name in @("LICENSE.html", "license.txt", "NOTICE", "update-settings.ini")) { Copy-RelativeFile $Name }
Copy-RelativeTree "presets"

$ProgramSource = Join-Path $Source "program"
$ProgramTarget = Join-Path $Destination "program"
New-Item -ItemType Directory -Path $ProgramTarget -Force | Out-Null
Get-ChildItem -LiteralPath $ProgramSource -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ProgramTarget $_.Name)
}
Get-ChildItem -LiteralPath $ProgramSource -Directory | Where-Object { $_.Name -ne "resource" } | ForEach-Object {
    Copy-RelativeTree ("program\" + $_.Name)
}
foreach ($Tree in @("program\resource\common", "program\resource\zh_CN")) {
    Copy-RelativeTree $Tree
}

$FontPatterns = @("LiberationSans-*.ttf", "LiberationSans-Regular.ttf", "LiberationSerif-*.ttf", "LiberationSerif-Regular.ttf")
$FontsTarget = Join-Path $Destination "Fonts"
New-Item -ItemType Directory -Path $FontsTarget -Force | Out-Null
foreach ($Pattern in $FontPatterns) {
    Get-ChildItem -LiteralPath (Join-Path $Source "Fonts") -Filter $Pattern -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $FontsTarget $_.Name)
    }
}

Get-ChildItem -LiteralPath (Join-Path $Source "share") -Directory | Where-Object {
    $_.Name -notin @("extensions", "gallery", "template", "config", "registry", "autocorr")
} | ForEach-Object { Copy-RelativeTree ("share\" + $_.Name) }
Copy-RelativeTree "share\config\soffice.cfg"
Get-ChildItem -LiteralPath (Join-Path $Source "share\registry") -File | Where-Object {
    $_.Name -notlike "Langpack-*"
} | ForEach-Object { Copy-RelativeFile ("share\registry\" + $_.Name) }
foreach ($File in @(
    "share\config\images_colibre.zip",
    "share\registry\Langpack-zh-CN.xcd", "share\registry\res\fcfg_langpack_zh-CN.xcd",
    "share\registry\res\registry_zh-CN.xcd"
)) { Copy-RelativeFile $File }
Copy-RelativeFile "share\autocorr\acor_zh-CN.dat"

Write-Output (Resolve-Path -LiteralPath $Destination).Path
