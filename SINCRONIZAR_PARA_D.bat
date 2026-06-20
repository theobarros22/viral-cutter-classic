@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sincronizar_para_D.ps1"
if errorlevel 1 (
  echo.
  echo A sincronizacao falhou. Nenhum build ou ambiente foi apagado.
  pause
  exit /b 1
)
pause
