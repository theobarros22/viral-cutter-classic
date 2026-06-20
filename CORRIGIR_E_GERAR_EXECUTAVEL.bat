@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0corrigir_e_gerar.ps1"
if errorlevel 1 (
  echo.
  echo O processo falhou. Consulte os logs informados acima.
  pause
  exit /b 1
)
pause
