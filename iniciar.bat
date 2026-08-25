@echo off
set GRADIO_TEMP_DIR=D:\ViralCutter\gradio_temp
cd /d "%~dp0"
if not exist "venv311\Scripts\python.exe" (
  echo Ambiente Python nao encontrado em "%~dp0venv311".
  echo Instale Python 3.11 e recrie o ambiente antes de continuar.
  pause
  exit /b 1
)
"venv311\Scripts\python.exe" diagnostico.py
if errorlevel 1 (
  pause
  exit /b 1
)
"venv311\Scripts\pythonw.exe" app_desktop.py

