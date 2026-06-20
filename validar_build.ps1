$ErrorActionPreference = "Stop"

$exe = Join-Path $PSScriptRoot "dist\ViralCutter\ViralCutter.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Executavel nao encontrado: $exe"
}

$env:VIRAL_CUTTER_NO_BROWSER = "1"
$status = Join-Path $env:LOCALAPPDATA "ViralCutter\status.json"
Remove-Item -LiteralPath $status -Force -ErrorAction SilentlyContinue
$processo = $null
$inicioTeste = Get-Date

Get-Process -Name "ViralCutter" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

try {
    $processo = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -PassThru
    $respondeu = $false

    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path -LiteralPath $status) {
            $dados = Get-Content -Raw -LiteralPath $status | ConvertFrom-Json
            try {
                $resposta = Invoke-WebRequest "http://127.0.0.1:$($dados.porta)" -UseBasicParsing -TimeoutSec 2
                if ($resposta.StatusCode -eq 200) {
                    $respondeu = $true
                    break
                }
            } catch {
            }
        }
        $processosAtivos = Get-Process -Name "ViralCutter" -ErrorAction SilentlyContinue
        if (-not $processosAtivos -and $processo.HasExited) {
            throw "O executavel fechou durante o teste de inicializacao."
        }
    }

    if (-not $respondeu) {
        throw "A interface nao respondeu em ate 120 segundos."
    }

    Write-Host "Build aprovado: processo vivo e interface HTTP respondendo." -ForegroundColor Green
} finally {
    Get-Process -Name "ViralCutter" -ErrorAction SilentlyContinue |
        Where-Object { $_.StartTime -ge $inicioTeste } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}
