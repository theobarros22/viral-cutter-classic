@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar_ambiente.ps1"
if errorlevel 1 (
  echo.
  echo Falha ao preparar o ambiente.
  pause
  exit /b 1
)
pause
