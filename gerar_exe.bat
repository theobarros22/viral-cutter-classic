@echo off
setlocal
cd /d "%~dp0"

if not exist "venv311\Scripts\python.exe" (
  echo ERRO: ambiente Python 3.11 nao encontrado em "%~dp0venv311".
  echo Instale Python 3.11 e recrie o ambiente primeiro.
  pause
  exit /b 1
)

"venv311\Scripts\python.exe" diagnostico.py
if errorlevel 1 (
  pause
  exit /b 1
)

"venv311\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 (
  echo ERRO: testes falharam. Build cancelado.
  pause
  exit /b 1
)

"venv311\Scripts\python.exe" -m PyInstaller viral_cutter.spec --noconfirm
if errorlevel 1 (
  echo ERRO: o executavel nao foi gerado.
  pause
  exit /b 1
)

PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0validar_build.ps1"
if errorlevel 1 (
  echo ERRO: o executavel foi criado, mas falhou no teste de inicializacao.
  pause
  exit /b 1
)

echo Executavel criado em dist\ViralCutter\ViralCutter.exe
pause
