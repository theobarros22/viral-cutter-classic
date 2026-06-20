$ErrorActionPreference = "Stop"

$origem = $PSScriptRoot
$destino = "D:\CORTE VIRAL\files"

Write-Host "1/3 Sincronizando versão corrigida para D:..." -ForegroundColor Cyan
& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "$origem\sincronizar_para_D.ps1"
if ($LASTEXITCODE -ne 0) { throw "Sincronização falhou." }

Write-Host "2/3 Reparando ambiente e instalando dependências..." -ForegroundColor Cyan
cmd.exe /d /c "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""$destino\preparar_ambiente.ps1"" > ""$destino\preparar_ambiente.log"" 2>&1"
$codigoPreparacao = $LASTEXITCODE
Get-Content "$destino\preparar_ambiente.log" -Tail 30
if ($codigoPreparacao -ne 0) { throw "Preparação falhou. Consulte $destino\preparar_ambiente.log" }

Write-Host "3/3 Gerando e validando executável..." -ForegroundColor Cyan
cmd.exe /d /c "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""$destino\gerar_release.ps1"" > ""$destino\gerar_release.log"" 2>&1"
$codigoBuild = $LASTEXITCODE
Get-Content "$destino\gerar_release.log" -Tail 30
if ($codigoBuild -ne 0) { throw "Build falhou. Consulte $destino\gerar_release.log" }

$exe = "$destino\dist\ViralCutter\ViralCutter.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "O processo terminou sem criar o executável."
}

Write-Host ""
Write-Host "EXECUTÁVEL CRIADO COM SUCESSO:" -ForegroundColor Green
Write-Host $exe -ForegroundColor Green
Start-Process explorer.exe -ArgumentList "/select,`"$exe`""
