# ============================================================
#  Gera o AUDIO da build WEB (pygbag) em formato OGG.
#
#  O pygbag/SDL-no-navegador NAO aceita MP3 -> exige OGG. Para nao mexer em
#  nenhum caminho no codigo (que referencia .mp3), gravamos CONTEUDO OGG
#  mantendo a extensao .mp3 (ffmpeg -f ogg). O SDL detecta o formato pelo
#  conteudo (magic bytes "OggS"), entao toca normalmente.
#
#  Converte TODO .mp3 sob game\assets (musica + SFX) -> web\assets\<mesmo caminho>.
#  NAO altera os assets desktop.
#
#  Uso:  .\reencode_audio_web.ps1            (64 kbps OGG, padrao)
#        .\reencode_audio_web.ps1 -Kbps 48   (mais agressivo)
# ============================================================

param(
    [int]$Kbps = 64,
    [string]$Origem  = "game\assets",
    [string]$Destino = "web\assets"
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

Write-Host "== Audio WEB (OGG @ ${Kbps}k, nome .mp3): $Origem -> $Destino ==" -ForegroundColor Cyan

$srcRoot = (Resolve-Path $Origem).Path
$arquivos = Get-ChildItem $Origem -Recurse -Filter *.mp3
$antes = 0.0; $depois = 0.0; $n = 0
foreach ($f in $arquivos) {
    $rel = $f.FullName.Substring($srcRoot.Length).TrimStart('\')
    $out = Join-Path (Join-Path $PSScriptRoot $Destino) $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

    # -f ogg força o container OGG mesmo com a extensão .mp3
    & $ffmpeg -hide_banner -loglevel error -y -i $f.FullName -map 0:a:0 -c:a libvorbis -b:a "${Kbps}k" -f ogg $out
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) {
        Write-Host ("  ERRO em {0}" -f $rel) -ForegroundColor Red; continue
    }
    $antes += $f.Length/1MB; $depois += (Get-Item $out).Length/1MB; $n++
}

Write-Host ("== $n arquivos convertidos p/ OGG | ${Origem}: {0:N1} MB  ->  ${Destino}: {1:N1} MB ==" -f $antes, $depois) -ForegroundColor Green
