# ============================================================
#  Gera o AUDIO da build WEB (pygbag) em formato OGG.
#
#  O pygbag/SDL-no-navegador NAO aceita MP3 -> exige OGG; e WAV (PCM cru) e
#  pesado demais para download web.
#
#  A MUSICA do repo ja e OGG Vorbis (~131k, derivada dos masters) desde a
#  migracao de MP3. Ela entra aqui assim mesmo: o web precisa dela a 48k, e o
#  ganho e de 98 MB para ~34 MB. Os SFX continuam .mp3/.wav e viram conteudo
#  OGG (o SDL detecta pelos magic bytes "OggS").
#
#  Converte TODO .ogg, .mp3 e .wav sob game\assets (musica + SFX) ->
#  web\assets\<mesmo caminho>. NAO altera os assets desktop.
#
#  MUSICA e SFX tem bitrates SEPARADOS, e a razao e de tamanho, nao de gosto:
#  medido, a musica e 33,8 MB dos 34,6 MB do audio web — os SFX sao 0,8 MB.
#  Baixar bitrate de SFX nao encolhe nada e so custaria fidelidade nos
#  transientes (impacto, tiro), que e onde compressao baixa aparece primeiro.
#  Entao o corte vai todo na musica, que e longa, fica DEBAIXO do combate e
#  tolera bem menos bitrate.
#
#  Por que isso importa no web: o bundle publicado e baixado inteiro antes de
#  jogar, e o primeiro visitante de cada edge do Cloudflare depois de um release
#  puxa tudo da ORIGEM (cache MISS). Quanto menor, menor a chance de a conexao
#  quebrar no meio — ver [[itch-publishing-workflow]].
#
#  Uso:  .\reencode_audio_web.ps1                   (musica 48k, sfx 64k)
#        .\reencode_audio_web.ps1 -MusicKbps 40     (mais agressivo na musica)
# ============================================================

param(
    [int]$MusicKbps = 48,
    [int]$SfxKbps = 64,
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

Write-Host "== Audio WEB (OGG | musica ${MusicKbps}k, sfx ${SfxKbps}k): $Origem -> $Destino ==" -ForegroundColor Cyan

$srcRoot = (Resolve-Path $Origem).Path
# Varre .ogg (musica), .mp3 e .wav (SFX). Todos viram OGG leve no destino.
#
# O .ogg PRECISA entrar mesmo ja sendo OGG: a musica do repo e Vorbis ~131k
# (qualidade de desktop, derivada dos masters) e o web precisa dela a 48k. Sem
# .ogg neste filtro a musica inteira era PULADA, `webssetsudio\music` saia
# vazia e o `build_web.ps1` abortava - ou, pior, reusava um webssets antigo e
# publicava a trilha de uma versao anterior.
$arquivos = Get-ChildItem $Origem -Recurse -File |
    Where-Object { $_.Extension -in '.ogg', '.mp3', '.wav' }
$antes = 0.0; $depois = 0.0; $n = 0
$musMB = 0.0; $sfxMB = 0.0
foreach ($f in $arquivos) {
    $rel = $f.FullName.Substring($srcRoot.Length).TrimStart('\')
    # SFX vivem sob audio\sfx\ (AUDIO_SFX_ROOT); todo o resto e musica.
    $ehSfx = $rel -match '(^|\\)audio\\sfx\\'
    $kbps = if ($ehSfx) { $SfxKbps } else { $MusicKbps }
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
    & $ffmpeg -hide_banner -loglevel error -y -i $f.FullName -map 0:a:0 -c:a libvorbis -ar 44100 -b:a "${kbps}k" -f ogg $out
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) {
        Write-Host ("  ERRO em {0}" -f $rel) -ForegroundColor Red; continue
    }
    $saiuMB = (Get-Item $out).Length/1MB
    $antes += $f.Length/1MB; $depois += $saiuMB; $n++
    if ($ehSfx) { $sfxMB += $saiuMB } else { $musMB += $saiuMB }
}

Write-Host ("== $n arquivos convertidos p/ OGG | ${Origem}: {0:N1} MB  ->  ${Destino}: {1:N1} MB ==" -f $antes, $depois) -ForegroundColor Green
Write-Host ("   musica: {0:N1} MB (@ ${MusicKbps}k) | sfx: {1:N1} MB (@ ${SfxKbps}k)" -f $musMB, $sfxMB) -ForegroundColor DarkGray
