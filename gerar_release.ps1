$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fechar-ViralCutter {
    $processos = Get-Process -Name "ViralCutter" -ErrorAction SilentlyContinue
    if (-not $processos) {
        return
    }

    Write-Host "Fechando versao anterior do Viral Cutter..." -ForegroundColor Cyan
    $processos | Stop-Process -Force -ErrorAction SilentlyContinue
    $processos | ForEach-Object {
        try { $_.WaitForExit(10000) } catch {}
    }

    if (Get-Process -Name "ViralCutter" -ErrorAction SilentlyContinue) {
        throw "Nao foi possivel fechar o Viral Cutter. Feche-o pelo Gerenciador de Tarefas."
    }
}

$python = Join-Path $PSScriptRoot "venv311\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Ambiente ausente. Execute PREPARAR_AMBIENTE.bat primeiro."
    }

    & $python -c "import sys; assert sys.version_info[:2] == (3, 11)"
    if ($LASTEXITCODE -ne 0) {
        throw "O ambiente Python está quebrado. Execute PREPARAR_AMBIENTE.bat."
    }

    & $python diagnostico.py
    if ($LASTEXITCODE -ne 0) { throw "Diagnóstico falhou." }
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Testes falharam." }
    Fechar-ViralCutter
    & $python -m PyInstaller viral_cutter.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

    & PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\validar_build.ps1"
    if ($LASTEXITCODE -ne 0) { throw "Teste de inicialização falhou." }

    $exe = Join-Path $PSScriptRoot "dist\ViralCutter\ViralCutter.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Build terminou sem criar ViralCutter.exe."
    }

    Write-Host ""
    Write-Host "EXECUTÁVEL CRIADO:" -ForegroundColor Green
Write-Host $exe -ForegroundColor Green
