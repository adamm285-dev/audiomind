@echo off
title AudioMind
cd /d "%~dp0.."
start wscript.exe "scripts\launch_anti_tray.vbs"
echo [*] AudioMind launched to the Windows system tray.
exit
