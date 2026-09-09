@echo off
REM Mostra ao vivo o que o processamento esta fazendo, clipe a clipe.
REM Pode fechar esta janela a qualquer momento: nao interrompe nada.
title Viral Cutter - acompanhamento
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$base = Join-Path $env:USERPROFILE 'Desktop\viral-clipes-TESTE';" ^
  "Write-Host 'Aguardando o processamento comecar...' -ForegroundColor Cyan;" ^
  "while (-not (Test-Path $base)) { Start-Sleep -Seconds 2 };" ^
  "$log = $null;" ^
  "while (-not $log) { $log = Get-ChildItem $base -Recurse -Filter 'viral_cutter_*.log' -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $log) { Start-Sleep -Seconds 2 } };" ^
  "Write-Host ('Acompanhando: ' + $log.FullName) -ForegroundColor Green;" ^
  "Write-Host '';" ^
  "Get-Content $log.FullName -Wait -Tail 40"
