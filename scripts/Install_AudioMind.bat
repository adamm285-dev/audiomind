@echo off
setlocal enabledelayedexpansion
title AudioMind Desktop Installer

cd /d "%~dp0.."
set "ROOT_DIR=%CD%"

echo ==========================================
echo      AudioMind Desktop Installer (Win)
echo ==========================================
echo.

if not exist "%ROOT_DIR%\.venv_voice\Scripts\python.exe" (
    echo [*] Creating Python virtual environment...
    python -m venv "%ROOT_DIR%\.venv_voice"
    if errorlevel 1 (
        echo [!] Python 3.10+ not found on PATH. Please install Python from python.org and re-run.
        pause
        exit /b 1
    )
)

echo [*] Installing desktop dependencies...
"%ROOT_DIR%\.venv_voice\Scripts\python.exe" -m pip install --upgrade pip >nul
"%ROOT_DIR%\.venv_voice\Scripts\python.exe" -m pip install -r "%ROOT_DIR%\desktop\requirements.txt"
if errorlevel 1 (
    echo [!] Dependency installation failed.
    pause
    exit /b 1
)

echo [*] Creating Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
  "$sc = $ws.CreateShortcut((Join-Path $desktop 'AudioMind.lnk')); " ^
  "$sc.TargetPath = 'wscript.exe'; " ^
  "$sc.Arguments = '\"' + '%ROOT_DIR%\scripts\launch_anti_tray.vbs' + '\"'; " ^
  "$sc.WorkingDirectory = '%ROOT_DIR%'; " ^
  "$sc.IconLocation = '%ROOT_DIR%\desktop\resources\anti_voice_assistant.ico'; " ^
  "$sc.Description = 'AudioMind Voice Assistant'; " ^
  "$sc.Save()"

echo [*] Launching AudioMind to the system tray...
start wscript.exe "%ROOT_DIR%\scripts\launch_anti_tray.vbs"
echo [+] Done! Look for the AudioMind icon on your Desktop and in the system tray.
pause
