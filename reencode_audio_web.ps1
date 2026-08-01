# ============================================================
#  Gera o AUDIO da build WEB (pygbag) em formato OGG.
#
#  O pygbag/SDL-no-navegador NAO aceita MP3 -> exige OGG; e WAV (PCM cru) e
#  pesado demais para download web. Para nao mexer em nenhum caminho no codigo
#  (que referencia .mp3/.wav), gravamos CONTEUDO OGG mantendo a extensao
#  original nos SFX (ffmpeg -f ogg). O SDL detecta o formato pelo conteudo
#  (magic bytes "OggS"), entao toca normalmente.
#
#  Converte TODO .mp3 E .wav sob game\assets (musica + SFX) ->
#  web\assets\<mesmo caminho>. NAO altera os assets desktop.
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

Write-Host "== Audio WEB (OGG @ ${Kbps}k, mesmo nome .mp3/.wav): $Origem -> $Destino ==" -ForegroundColor Cyan

$srcRoot = (Resolve-Path $Origem).Path
# Varre .mp3 (musica + SFX) E .wav (SFX). Ambos viram conteudo OGG no destino.
$arquivos = Get-ChildItem $Origem -Recurse -File |
    Where-Object { $_.Extension -in '.mp3', '.wav' }
$antes = 0.0; $depois = 0.0; $n = 0
foreach ($f in $arquivos) {
    $rel = $f.FullName.Substring($srcRoot.Length).TrimStart('\')
    # Tudo vira .ogg de verdade (extensao inclusive). Musica PRECISA disso:
    # mixer.music detecta o formato pela EXTENSAO no web, e um .mp3 com conteudo
    # OGG dentro nao toca. Para os SFX tanto faz (mixer.Sound detecta pelo
    # conteudo), e `discover_sfx` aceita .ogg - a chave e o nome sem extensao,
    # que nao muda.
    #
    # O ramo `else` que preservava a extensao servia ao layout ANTIGO, com SFX em
    # game\assets\sounds\. Hoje eles vivem em game\assets\audio\sfx\ (ver
    # AUDIO_SFX_ROOT), entao caem todos no `audio\*` e o outro caminho era codigo
    # morto - mas com um comentario que descrevia um layout inexistente, que foi
    # o que sustentou a pasta web\assets\sounds\ obsoleta por tanto tempo.
    $outRel = [System.IO.Path]::ChangeExtension($rel, '.ogg')
    $out = Join-Path (Join-Path $PSScriptRoot $Destino) $outRel
    New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

    # -f ogg forca o container OGG mesmo com a extensao .mp3/.wav.
    # -ar 44100: libvorbis nao inicia o encoder em sample-rates muito baixos
    #   (ex.: SFX 8-bit a 5512 Hz -> "encoder setup failed"); reamostrar p/ 44100
    #   resolve E casa com o mixer web (sound.py fixa 44100 p/ evitar resample).
    & $ffmpeg -hide_banner -loglevel error -y -i $f.FullName -map 0:a:0 -c:a libvorbis -ar 44100 -b:a "${Kbps}k" -f ogg $out
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) {
        Write-Host ("  ERRO em {0}" -f $rel) -ForegroundColor Red; continue
    }
    $antes += $f.Length/1MB; $depois += (Get-Item $out).Length/1MB; $n++
}

Write-Host ("== $n arquivos convertidos p/ OGG | ${Origem}: {0:N1} MB  ->  ${Destino}: {1:N1} MB ==" -f $antes, $depois) -ForegroundColor Green
