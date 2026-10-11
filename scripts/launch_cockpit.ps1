# Dual-Phone Scrcpy Cockpit Launcher for Multi-Device Voice Testing
param (
    [string]$Device1 = $env:ANTI_DEVICE_1,
    [string]$Device2 = $env:ANTI_DEVICE_2,
    [string]$Device1Title = "Primary Companion Device",
    [string]$Device2Title = "Lab / Secondary Device"
)

$scrcpyPath = (Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter "scrcpy.exe" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName

if (-not $scrcpyPath) {
    $scrcpyPath = "scrcpy"
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "     AUDIOMIND MULTI-DEVICE COCKPIT       " -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan

if (-not $Device1) {
    Write-Host "Usage: .\launch_cockpit.ps1 -Device1 <ip:port_or_serial> [-Device2 <ip:port_or_serial>]" -ForegroundColor DarkYellow
    Write-Host "Or set environment variables: `$env:ANTI_DEVICE_1 and `$env:ANTI_DEVICE_2" -ForegroundColor DarkYellow
    Write-Host "`nDetecting connected adb devices..." -ForegroundColor Gray
    try {
        adb devices
    } catch {
        Write-Host "adb not found in PATH." -ForegroundColor Red
    }
    exit 0
}

Write-Host "Launching Screen 1: $Device1Title ($Device1)..." -ForegroundColor Green
Start-Process -FilePath $scrcpyPath -ArgumentList "-s $Device1 --window-title '$Device1Title' --window-x 100 --window-y 100 --window-width 450"

if ($Device2) {
    Write-Host "Launching Screen 2: $Device2Title ($Device2)..." -ForegroundColor Green
    Start-Process -FilePath $scrcpyPath -ArgumentList "-s $Device2 --window-title '$Device2Title' --window-x 600 --window-y 100 --window-width 450"
}

Write-Host "Cockpit Launched Successfully!" -ForegroundColor Cyan
