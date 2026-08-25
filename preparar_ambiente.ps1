$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Atualizar-Path {
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("PATH", "User")
}

function Testar-Python([string]$Executavel) {
    if (-not $Executavel -or -not (Test-Path -LiteralPath $Executavel)) {
        return $false
    }
    try {
        $versao = & $Executavel -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        return $LASTEXITCODE -eq 0 -and $versao.Trim() -eq "3.11"
    } catch {
        return $false
    }
}

function Localizar-Python311 {
    $candidatos = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    foreach ($candidato in $candidatos) {
        if (Testar-Python $candidato) {
            return $candidato
        }
    }
    try {
        $candidato = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null).Trim()
        if (Testar-Python $candidato) {
            return $candidato
        }
    } catch {
    }
    return $null
}

Atualizar-Path
$python = Localizar-Python311

if (-not $python) {
    Write-Host "Reparando/instalando Python 3.11..." -ForegroundColor Cyan
    winget install --id Python.Python.3.11 --exact --force --scope user `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Winget não conseguiu instalar Python 3.11."
    }
    Atualizar-Path
    $python = Localizar-Python311
}
if (-not $python) {
    throw "Python 3.11 não pôde ser iniciado após a instalação."
}

$venv = Join-Path $PSScriptRoot "venv311"
$pythonVenv = Join-Path $venv "Scripts\python.exe"
if (-not (Testar-Python $pythonVenv)) {
    Write-Host "Recriando ambiente Python quebrado..." -ForegroundColor Cyan
    if (Test-Path -LiteralPath $venv) {
        $resolvido = (Resolve-Path -LiteralPath $venv).Path
        if (-not $resolvido.StartsWith($PSScriptRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Recusa de segurança: venv fora da pasta do projeto."
        }
        Remove-Item -LiteralPath $resolvido -Recurse -Force
    }
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Testar-Python $pythonVenv)) {
        throw "Não foi possível recriar o venv311."
    }
}

& $pythonVenv -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar pip." }
$arquivoDependencias = if (Test-Path -LiteralPath "requirements-lock.txt") {
    "requirements-lock.txt"
} else {
    "requirements.txt"
}
Write-Host "Instalando dependencias de $arquivoDependencias..." -ForegroundColor Cyan
& $pythonVenv -m pip install -r $arquivoDependencias
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependências Python." }

$temNvidia = $null -ne (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)
if ($temNvidia) {
    $torchCuda = & $pythonVenv -c "import torch; print('1' if torch.cuda.is_available() else '0')" 2>$null
    if ($LASTEXITCODE -ne 0 -or $torchCuda.Trim() -ne "1") {
        Write-Host "Instalando PyTorch CUDA para a GPU NVIDIA..." -ForegroundColor Cyan
        & $pythonVenv -m pip install --force-reinstall `
            torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 `
            --index-url https://download.pytorch.org/whl/cu124
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao instalar PyTorch CUDA."
        }
    }
}

Atualizar-Path
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "Instalando FFmpeg..." -ForegroundColor Cyan
    winget install --id Gyan.FFmpeg --exact --force --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Winget não conseguiu instalar FFmpeg." }
    Atualizar-Path
}

New-Item -ItemType Directory -Path tools -Force | Out-Null
foreach ($nome in @("ffmpeg.exe", "ffprobe.exe")) {
    $comando = Get-Command $nome -ErrorAction SilentlyContinue
    $origem = if ($comando) { $comando.Source } else { $null }
    if (-not $origem) {
        $origem = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter $nome -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $origem) {
        throw "$nome não foi localizado após a instalação."
    }
    Copy-Item -LiteralPath $origem -Destination (Join-Path "tools" $nome) -Force
}

& $pythonVenv diagnostico.py
if ($LASTEXITCODE -ne 0) { throw "Diagnóstico falhou." }
& $pythonVenv -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "Testes falharam." }

Write-Host ""
Write-Host "Ambiente preparado e validado." -ForegroundColor Green
