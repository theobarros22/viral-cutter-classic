$ErrorActionPreference = 'Stop'

$target = 'C:\Program Files\Epic Games\HellLetLooseG0WU4'
$expected = 'C:\Program Files\Epic Games\HellLetLooseG0WU4'
$log = Join-Path $PSScriptRoot 'remocao-hell-let-loose.log'

try {
    if (-not (Test-Path -LiteralPath $target)) {
        "Hell Let Loose ja nao existe em $target" | Set-Content -LiteralPath $log
        exit 0
    }

    $resolved = (Resolve-Path -LiteralPath $target).Path
    if ($resolved -ne $expected) {
        throw "Caminho inesperado. Exclusao cancelada: $resolved"
    }

    $before = [System.IO.DriveInfo]::new('C').AvailableFreeSpace
    Remove-Item -LiteralPath $resolved -Recurse -Force
    $after = [System.IO.DriveInfo]::new('C').AvailableFreeSpace

    @(
        "Removido: $resolved"
        "Espaco recuperado (GB): $([math]::Round(($after - $before) / 1GB, 2))"
        "Espaco livre no C (GB): $([math]::Round($after / 1GB, 2))"
    ) | Set-Content -LiteralPath $log
}
catch {
    "ERRO: $($_.Exception.Message)" | Set-Content -LiteralPath $log
    exit 1
}
