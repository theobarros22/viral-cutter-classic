@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0gerar_release.ps1"
if errorlevel 1 (
  echo.
  echo Build falhou. Consulte gerar_release.log.
  pause
  exit /b 1
)
pause
