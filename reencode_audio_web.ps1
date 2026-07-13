# ============================================================
#  Gera uma COPIA otimizada do audio para a build WEB (pygbag).
#  NAO altera os assets desktop (game/assets/audio permanece intacto).
#  Origem : game\assets\audio         (MP3 128k do desktop)
#  Destino: web\assets\audio          (MP3 no bitrate -Kbps, espelhando a estrutura)
#
#  Uso:  .\reencode_audio_web.ps1              (64 kbps, padrao)
#        .\reencode_audio_web.ps1 -Kbps 48     (mais agressivo p/ web)
# ============================================================

param(
    [int]$Kbps = 64,
    [string]$Origem  = "game\assets\audio",
    [string]$Destino = "web\assets\audio"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Exe($nome) {
    $c = Get-Command $nome -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "$nome.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}
$ffmpeg = Find-Exe "ffmpeg"
if (-not $ffmpeg) { Write-Host "ERRO: ffmpeg nao encontrado (winget install Gyan.FFmpeg)" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Origem)) { Write-Host "ERRO: origem nao existe: $Origem" -ForegroundColor Red; exit 1 }

Write-Host "== Audio WEB: $Origem -> $Destino  @ ${Kbps}k ==" -ForegroundColor Cyan

$arquivos = Get-ChildItem $Origem -Recurse -Filter *.mp3
$antes = 0.0; $depois = 0.0; $n = 0
foreach ($f in $arquivos) {
    $rel = $f.FullName.Substring((Resolve-Path $Origem).Path.Length).TrimStart('\')
    $out = Join-Path (Join-Path $PSScriptRoot $Destino) $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

    & $ffmpeg -hide_banner -loglevel error -y -i $f.FullName -map 0:a:0 -c:a libmp3lame -b:a "${Kbps}k" $out
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) {
        Write-Host ("  ERRO em {0}" -f $rel) -ForegroundColor Red; continue
    }
    $a = $f.Length/1MB; $d = (Get-Item $out).Length/1MB
    $antes += $a; $depois += $d; $n++
    Write-Host ("  {0,6:N1} -> {1,5:N1} MB  {2}" -f $a, $d, $rel)
}

Write-Host ""
Write-Host ("== $n arquivos | ${Origem}: {0:N1} MB  ->  ${Destino}: {1:N1} MB ==" -f $antes, $depois) -ForegroundColor Cyan
