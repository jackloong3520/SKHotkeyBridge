#Requires -Version 5.1
<#
.SYNOPSIS
    SKHotkeyBridge 一键部署脚本（Mac KM Link 对拷线快捷键桥接）
.DESCRIPTION
    从 GitHub Releases 下载最新版本，安装到 %LOCALAPPDATA%\SKHotkeyBridge，
    并可选加入开机启动。适用于重装系统或更换电脑后快速恢复使用。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
    下载并安装最新版本，并加入开机启动。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -NoAutoStart
    只安装，不加入开机启动。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
    卸载：停止运行中的桥接、删除安装目录与开机启动项。
#>

param(
    [switch]$Uninstall,
    [switch]$NoAutoStart,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'SKHotkeyBridge')
)

$ErrorActionPreference = 'Stop'

$Repo  = 'jackloong3520/SKHotkeyBridge'
$Base  = "https://github.com/$Repo/releases/latest/download"
$Files = @('SKHotkeyBridge.exe', 'SKHotkeyBridge.ini')

try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

function Write-Step { param($m) Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Info { param($m) Write-Host "    $m" -ForegroundColor Gray }
function Write-Good { param($m) Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Bad  { param($m) Write-Host "    [!!] $m" -ForegroundColor Yellow }

function Get-StartupLinkPath {
    return (Join-Path ([Environment]::GetFolderPath('Startup')) 'SKHotkeyBridge.lnk')
}

function Stop-Bridge {
    $procs = @(Get-Process -Name 'SKHotkeyBridge' -ErrorAction SilentlyContinue)
    if ($procs.Count -gt 0) {
        Write-Step '正在停止运行中的桥接程序'
        foreach ($p in $procs) {
            try { $p.CloseMainWindow() | Out-Null; Start-Sleep -Milliseconds 400 } catch { }
        }
        Get-Process -Name 'SKHotkeyBridge' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Good '已停止'
    }
}

function Remove-AutoStart {
    $link = Get-StartupLinkPath
    if (Test-Path -LiteralPath $link) {
        Remove-Item -LiteralPath $link -Force
        Write-Good ('已移除开机启动项: ' + $link)
    }
}

if ($Uninstall) {
    Write-Step '卸载 SKHotkeyBridge'
    Stop-Bridge
    Remove-AutoStart
    if (Test-Path -LiteralPath $InstallDir) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
        Write-Good ('已删除安装目录: ' + $InstallDir)
    }
    Write-Host ''
    Write-Host '卸载完成，原版对拷线程序不受影响。' -ForegroundColor Green
    exit 0
}

Write-Step '准备安装 SKHotkeyBridge'
Write-Info ('安装目录: ' + $InstallDir)

if (-not (Test-Path -LiteralPath $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# 若已有实例在运行，先停止，避免文件占用
Stop-Bridge

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('SKHotkeyBridge_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    foreach ($f in $Files) {
        Write-Step ('下载 ' + $f)
        $dest = Join-Path $tempRoot $f
        try {
            Invoke-WebRequest -Uri "$Base/$f" -OutFile $dest -UseBasicParsing
        } catch {
            throw "下载 $f 失败。请检查网络，或前往 https://github.com/$Repo/releases 手动下载。错误信息: $($_.Exception.Message)"
        }
        if ((Get-Item -LiteralPath $dest).Length -lt 1024) {
            throw "下载的 $f 体积异常，可能未指向有效 Release 资产。"
        }
        Write-Good ('已下载 {0} KB' -f [math]::Round((Get-Item -LiteralPath $dest).Length / 1KB, 1))
    }

    # SHA-256 校验（可选，失败仅警告）
    Write-Step '校验 SHA-256'
    try {
        $shaFile = Join-Path $tempRoot 'SHA256.txt'
        Invoke-WebRequest -Uri "$Base/SHA256.txt" -OutFile $shaFile -UseBasicParsing
        $expected = ((Get-Content -LiteralPath $shaFile -Raw) -split '\s+' | Where-Object { $_ -match '^[0-9a-fA-F]{64}$' } | Select-Object -First 1)
        if ($expected) {
            $actual = (Get-FileHash -LiteralPath (Join-Path $tempRoot 'SKHotkeyBridge.exe') -Algorithm SHA256).Hash
            if ($actual -ieq $expected) {
                Write-Good ('校验通过: ' + $actual.ToLower())
            } else {
                Write-Bad '校验不一致，请核对 Release 页面公布的值。'
                Write-Info ('期望: ' + $expected)
                Write-Info ('实际: ' + $actual)
            }
        } else {
            Write-Info '未获取到校验值，跳过。'
        }
    } catch {
        Write-Info '未获取到校验值，跳过。'
    }

    Write-Step '安装文件'
    foreach ($f in $Files) {
        Copy-Item -LiteralPath (Join-Path $tempRoot $f) -Destination (Join-Path $InstallDir $f) -Force
        Write-Good $f
    }
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $NoAutoStart) {
    Write-Step '加入开机启动'
    try {
        $shell = New-Object -ComObject WScript.Shell
        $link  = $shell.CreateShortcut((Get-StartupLinkPath))
        $link.TargetPath       = (Join-Path $InstallDir 'SKHotkeyBridge.exe')
        $link.WorkingDirectory = $InstallDir
        $link.Description      = 'Mac KM Link 对拷线快捷键桥接'
        $link.Save()
        Write-Good (Get-StartupLinkPath)
    } catch {
        Write-Bad ('创建开机启动项失败: ' + $_.Exception.Message)
    }
} else {
    Write-Info '已跳过开机启动（使用了 -NoAutoStart）'
}

Write-Host ''
Write-Host '安装完成。' -ForegroundColor Green
Write-Host '  1. 先启动原版对拷线程序（SKLoader.exe）' -ForegroundColor White
Write-Host '  2. 再运行 SKHotkeyBridge.exe' -ForegroundColor White
Write-Host '  3. 默认快捷键 Ctrl+Alt+F11 为一键同步开关' -ForegroundColor White
Write-Host ''
Write-Host ('安装目录: ' + $InstallDir) -ForegroundColor Gray
