@echo off
title Remover Hell Let Loose do disco C
color 0E
set "SCRIPT=%~dp0remover-hell-let-loose.ps1"
echo ============================================================
echo  REMOVER HELL LET LOOSE - LIBERAR APROXIMADAMENTE 47 GB
echo ============================================================
echo.
echo Uma confirmacao de administrador sera exibida.
echo Clique em SIM para autorizar a remocao.
echo.
pause
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%SCRIPT%""' -Wait"
echo.
if exist "%~dp0remocao-hell-let-loose.log" (
  type "%~dp0remocao-hell-let-loose.log"
) else (
  echo A remocao nao foi executada. Aceite a confirmacao de administrador do Windows.
)
echo.
pause
