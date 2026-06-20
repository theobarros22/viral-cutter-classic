$ErrorActionPreference = "Stop"

$origem = Split-Path -Parent $MyInvocation.MyCommand.Path
$destino = "D:\CORTE VIRAL\files"
$data = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $destino "_backups\antes_sync_$data"

if (-not (Test-Path -LiteralPath $destino)) {
    throw "Pasta de destino não encontrada: $destino"
}

$arquivos = @(
    ".gitignore",
    "analise.py",
    "AUDITORIA.md",
    "checkpoint.py",
    "CONTINUAR_PROJETO.md",
    "cortes.py",
    "diagnostico.py",
    "enquadramento.py",
    "ESTADO_ATUAL.json",
    "face_detector.tflite",
    "FUNCIONALIDADES_ADOTAVEIS.md",
    "ffmpeg_utils.py",
    "gerar_exe.bat",
    "gerar_exe_release.bat",
    "gerar_release.ps1",
    "historico.py",
    "iniciar.bat",
    "interface.py",
    "main.py",
    "pipeline.py",
    "reframe.py",
    "requirements.txt",
    "requirements-lock.txt",
    "RELATORIO_FINAL.md",
    "ROADMAP_PRODUTO.md",
    "rostos.py",
    "runtime.py",
    "smart_cut.py",
    "tracking.py",
    "validar_build.ps1",
    "version_info.txt",
    "viral_cutter.spec",
    "PLANO_EXECUTAVEL_PROFISSIONAL.md",
    "MATRIZ_VALIDACAO.md",
    "preparar_ambiente.ps1",
    "PREPARAR_AMBIENTE.bat"
)

New-Item -ItemType Directory -Path $backup -Force | Out-Null

foreach ($arquivo in $arquivos) {
    $fonte = Join-Path $origem $arquivo
    $alvo = Join-Path $destino $arquivo

    if (-not (Test-Path -LiteralPath $fonte)) {
        throw "Arquivo auditado ausente: $fonte"
    }

    if (Test-Path -LiteralPath $alvo) {
        Copy-Item -LiteralPath $alvo -Destination (Join-Path $backup $arquivo) -Force
    }

    Copy-Item -LiteralPath $fonte -Destination $alvo -Force
}

foreach ($pasta in @("tests", "tools", "frontend_preview")) {
    $fontePasta = Join-Path $origem $pasta
    $alvoPasta = Join-Path $destino $pasta

    if (Test-Path -LiteralPath $alvoPasta) {
        $backupPasta = Join-Path $backup $pasta
        New-Item -ItemType Directory -Path $backupPasta -Force | Out-Null
        Copy-Item -Path (Join-Path $alvoPasta "*") -Destination $backupPasta -Recurse -Force
    }

    New-Item -ItemType Directory -Path $alvoPasta -Force | Out-Null
    Copy-Item -Path (Join-Path $fontePasta "*") -Destination $alvoPasta -Recurse -Force
}

Write-Host ""
Write-Host "Sincronização concluída." -ForegroundColor Green
Write-Host "Projeto principal: $destino"
Write-Host "Backup anterior: $backup"
Write-Host "As pastas dist, build e venv311 foram preservadas."
