$ErrorActionPreference = 'Continue'

$log = Join-Path $PSScriptRoot 'limpeza-recomendada-c.log'
$before = [System.IO.DriveInfo]::new('C').AvailableFreeSpace
$results = [System.Collections.Generic.List[string]]::new()

function Clear-SafePath {
    param(
        [Parameter(Mandatory)]
        [string] $Path,
        [Parameter(Mandatory)]
        [string] $Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        $results.Add("${Label}: caminho inexistente")
        return
    }

    $sizeBefore = (
        Get-ChildItem -LiteralPath $Path -Force -File -Recurse -ErrorAction SilentlyContinue |
        Measure-Object Length -Sum
    ).Sum

    Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $sizeAfter = (
        Get-ChildItem -LiteralPath $Path -Force -File -Recurse -ErrorAction SilentlyContinue |
        Measure-Object Length -Sum
    ).Sum

    $freed = [math]::Max(0, $sizeBefore - $sizeAfter)
    $results.Add("${Label}: $([math]::Round($freed / 1GB, 2)) GB liberados")
}

Clear-SafePath -Path 'C:\adobeTemp' -Label 'Temporarios Adobe'
Clear-SafePath -Path 'C:\ProgramData\NVIDIA Corporation\Downloader\latest' -Label 'NVIDIA pacote latest'
Clear-SafePath -Path 'C:\ProgramData\NVIDIA Corporation\Downloader\36e2d6757f12ac1f10371b827992a09f' -Label 'NVIDIA pacote antigo'
Clear-SafePath -Path 'C:\ProgramData\NVIDIA Corporation\Downloader\6a17a49f6c7ea33fbba8775090ee7874' -Label 'NVIDIA pacote antigo 2'
Clear-SafePath -Path 'C:\ProgramData\Epic\EpicGamesLauncher\Data\Update' -Label 'Atualizacao temporaria Epic'
Clear-SafePath -Path 'C:\ProgramData\Dell\drivers' -Label 'Instaladores antigos Dell'
Clear-SafePath -Path 'C:\Windows\Logs' -Label 'Logs antigos Windows'

$hiberBefore = Test-Path -LiteralPath 'C:\hiberfil.sys'
& powercfg.exe /hibernate off 2>&1 | Out-Null
$hiberAfter = Test-Path -LiteralPath 'C:\hiberfil.sys'
if ($hiberBefore -and -not $hiberAfter) {
    $results.Add('Hibernacao desativada com sucesso')
}
elseif ($hiberAfter) {
    $results.Add('Hibernacao nao foi desativada')
}
else {
    $results.Add('Hibernacao ja estava desativada')
}

$after = [System.IO.DriveInfo]::new('C').AvailableFreeSpace

@(
    "Limpeza executada em: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "Espaco livre antes (GB): $([math]::Round($before / 1GB, 2))"
    "Espaco livre depois (GB): $([math]::Round($after / 1GB, 2))"
    "Total recuperado (GB): $([math]::Round(($after - $before) / 1GB, 2))"
    ''
    $results
) | Set-Content -LiteralPath $log
