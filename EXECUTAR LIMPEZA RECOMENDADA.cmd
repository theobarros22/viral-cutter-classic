@echo off
title Limpeza recomendada do disco C
color 0A
echo ============================================================
echo  LIMPEZA SEGURA DO DISCO C
echo ============================================================
echo.
echo Esta limpeza remove caches e instaladores antigos e desativa
echo a hibernacao. Seus documentos e projetos nao serao apagados.
echo.
echo Clique em SIM na confirmacao de administrador.
echo.
pause
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0limpeza-recomendada-c.ps1""' -Wait"
echo.
if exist "%~dp0limpeza-recomendada-c.log" (
  type "%~dp0limpeza-recomendada-c.log"
) else (
  echo A limpeza nao foi executada. Aceite a confirmacao de administrador.
)
echo.
pause
