# ============================================================
#  Monta o staging da build WEB (pygbag) e (opcional) empacota.
#    .\build_web.ps1            -> so monta o staging em web\staging
#    .\build_web.ps1 -Build     -> monta + roda pygbag --build
#    .\build_web.ps1 -Serve     -> monta + roda pygbag (servidor local p/ testar)
#
#  O staging = codigo do jogo (game/) + assets, com o AUDIO LEVE (web/assets/audio)
#  no lugar do audio pesado do desktop, + main.py async.
# ============================================================

param(
    [switch]$Build,
    [switch]$Serve,
    [switch]$AceitarMudos   # publicar mesmo com SFX .mp3 que nao tocam no web
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py    = ".\.venv\Scripts\python.exe"
$stage = "web\staging"

# O copy cru abaixo exclui .mp3 E .wav, entao TODO audio chega ao staging pelo
# overlay de web\assets. Musica e SFX moram os dois sob audio\ (ver
# AUDIO_SFX_ROOT = "game/assets/audio/sfx" em sound_config.py).
#
# A verificacao conta ARQUIVOS, e nao a existencia da pasta. A versao anterior
# fazia Test-Path em "web\assets\sounds" - um diretorio de um layout ANTIGO, de
# quando os SFX ficavam em game\assets\sounds\. Ele continuou existindo no disco,
# entao a guarda passava, o overlay despejava os arquivos em
# staging\game\assets\sounds\ (caminho que NENHUM codigo le) e a build saia MUDA
# de SFX - exatamente o que a guarda existia para impedir, com a mensagem de erro
# certa escrita ao lado.
$sfxWeb = @(Get-ChildItem "web\assets\audio\sfx" -Recurse -File -ErrorAction SilentlyContinue)
$audioWeb = @(Get-ChildItem "web\assets\audio" -Recurse -File -ErrorAction SilentlyContinue)
$musWeb = @($audioWeb | Where-Object { $_.FullName -notmatch '\\audio\\sfx\\' })

# MUSICA e obrigatoria transcodificada: sao 99 MB de .mp3/.wav no repo contra
# 47 MB de .ogg. Nao ha versao "crua aceitavel" - sem o reencode, para aqui.
if ($musWeb.Count -eq 0) {
    Write-Host "ERRO: musica web ausente em web\assets\audio." -ForegroundColor Red
    Write-Host "      Rode antes: .\reencode_audio_web.ps1 (precisa de ffmpeg)" -ForegroundColor Red
    exit 1
}

# SFX tem plano B, e e por isso que a build nao precisa de ffmpeg para ter som.
# Sao 4.2 MB no total: eles entravam na exclusao de .mp3/.wav como efeito
# colateral da regra que existe para barrar a MUSICA, nao por peso proprio.
# Sem os OGG, copiamos os originais - 3 MB a mais numa build que ja carrega 47 MB
# de musica, em troca de a build nunca sair muda.
$sfxRaw = $sfxWeb.Count -eq 0
if ($sfxRaw) {
    Write-Host ">> SFX web ausentes: usando os ORIGINAIS de game\assets\audio\sfx (+4 MB)." -ForegroundColor Yellow
    # O plano B so vale para .WAV. O SDL_mixer do pygbag nao decodifica MP3: e
    # por isso que o reencode existe e que passamos --disable-sound-format-error
    # (o desenho original era todo o audio ser OGG por CONTEUDO, mantendo o nome
    # .mp3). Enviar um .mp3 de verdade e publicar um som mudo, e a falha e
    # silenciosa dos dois lados: nada estoura, o SFX simplesmente nao toca.
    $mudos = @(Get-ChildItem "game\assets\audio\sfx" -Recurse -File -Filter *.mp3)
    if ($mudos.Count -gt 0) {
        Write-Host ""
        Write-Host "   $($mudos.Count) SFX em .mp3 NAO VAO TOCAR no navegador:" -ForegroundColor Red
        foreach ($m in $mudos) { Write-Host "     - $($m.Name)" -ForegroundColor Red }
        Write-Host ""
        Write-Host "   Conserto: winget install Gyan.FFmpeg  +  .\reencode_audio_web.ps1" -ForegroundColor Yellow
        Write-Host "   (isso tambem encolhe os SFX de 4.2 MB para ~1 MB)" -ForegroundColor DarkGray
        if (-not $AceitarMudos) {
            Write-Host "   Para publicar assim mesmo: .\build_web.ps1 -AceitarMudos" -ForegroundColor DarkGray
            exit 1
        }
        Write-Host "   -AceitarMudos: seguindo com os sons acima MUDOS." -ForegroundColor Yellow
    }
}
# Layout antigo deixado para tras: se sobrou, o overlay o copia para um caminho
# morto e ainda infla a build. Melhor falhar aqui do que publicar 5 MB de lixo.
if (Test-Path "web\assets\sounds") {
    Write-Host "ERRO: web\assets\sounds e residuo do layout antigo (SFX agora vivem em audio\sfx)." -ForegroundColor Red
    Write-Host "      Apague a pasta e rode: .\reencode_audio_web.ps1" -ForegroundColor Red
    exit 1
}

Write-Host ">> Limpando staging..." -ForegroundColor Cyan
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$stage\game" | Out-Null

Write-Host ">> Copiando codigo + assets (sem .mp3/.wav e __pycache__)..." -ForegroundColor Cyan
robocopy game "$stage\game" /E /XD __pycache__ /XF *.pyc *.mp3 *.wav /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null

# Plano B dos SFX: os originais entram ANTES do overlay. Como `$sfxRaw` so e
# verdadeiro quando web\assets\audio\sfx esta vazio, os dois nunca coexistem -
# e isso importa: `discover_sfx` indexa pela chave (nome SEM extensao), entao
# `warning.ogg` e `warning.mp3` na mesma pasta seriam a MESMA chave. Uma venceria
# por ordem de varredura, com um aviso de duplicata no log e o som certo sendo
# escolhido por acaso. Uma fonte de cada vez, nunca as duas.
if ($sfxRaw) {
    Write-Host ">> Copiando SFX originais (sem transcodificar)..." -ForegroundColor Cyan
    robocopy "game\assets\audio\sfx" "$stage\game\assets\audio\sfx" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Host "ERRO no robocopy dos SFX ($LASTEXITCODE)" -ForegroundColor Red; exit 1 }
    $global:LASTEXITCODE = 0
}

Write-Host ">> Inserindo audio OGG (web) no lugar dos .mp3/.wav..." -ForegroundColor Cyan
robocopy "web\assets" "$stage\game\assets" /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
# robocopy usa exit codes 0-7 para sucesso; >=8 e erro real.
if ($LASTEXITCODE -ge 8) { Write-Host "ERRO no robocopy ($LASTEXITCODE)" -ForegroundColor Red; exit 1 }
$global:LASTEXITCODE = 0

Copy-Item "web\main.py" "$stage\main.py" -Force

# Confere o RESULTADO, e nao os ingredientes. Foi assim que a build saiu muda
# durante semanas: as guardas de cima olhavam para as pastas de origem, e o
# overlay depositava os SFX num caminho que nenhum codigo le
# (staging\game\assets\sounds\). Aqui perguntamos ao staging exatamente o que o
# jogo vai perguntar em runtime - o AUDIO_SFX_ROOT de sound_config.py.
$sfxStaged = @(Get-ChildItem "$stage\game\assets\audio\sfx" -Recurse -File -ErrorAction SilentlyContinue)
if ($sfxStaged.Count -eq 0) {
    Write-Host "ERRO: staging sem SFX em game\assets\audio\sfx - a build sairia MUDA." -ForegroundColor Red
    exit 1
}
# Musica: mesma checagem, e por pasta. `MusicLibrary` faz `os.listdir` de cada
# uma (music_library.py) - uma pasta vazia nao e erro, e silencio. Foi assim que
# o web ficou sem trilha: os OGG existiam, mas um nivel acima (audio\themes\ em
# vez de audio\music\themes\), sobra de um layout antigo. Nada reclamou.
foreach ($sub in @("themes", "bosses", "menu")) {
    $n = @(Get-ChildItem "$stage\game\assets\audio\music\$sub" -Recurse -File -ErrorAction SilentlyContinue).Count
    if ($n -eq 0) {
        Write-Host "ERRO: staging sem musica em game\assets\audio\music\$sub." -ForegroundColor Red
        Write-Host "      Confira o layout de web\assets\audio\music\ (rode .\reencode_audio_web.ps1)." -ForegroundColor Red
        exit 1
    }
}
$orfaos = @(Get-ChildItem "$stage\game\assets\sounds" -Recurse -File -ErrorAction SilentlyContinue)
if ($orfaos.Count -gt 0) {
    Write-Host "ERRO: $($orfaos.Count) arquivo(s) em staging\game\assets\sounds - caminho morto, ninguem le." -ForegroundColor Red
    exit 1
}
Write-Host (">> SFX no staging: {0} arquivo(s)." -f $sfxStaged.Count) -ForegroundColor Green

$sz = (Get-ChildItem $stage -Recurse | Measure-Object Length -Sum).Sum/1MB
Write-Host (">> Staging pronto: {0}  ({1:N1} MB)" -f $stage, $sz) -ForegroundColor Green

# --disable-sound-format-error: nosso audio ja e OGG (conteudo), so o nome e .mp3;
#   a flag pula a checagem por extensao do pygbag. SDL toca pelo conteudo.
# --ume_block=0: nao espera o "desbloqueio de midia" (clique) antes de rodar o
#   jogo; sem isso o pygbag fica preso na tela cinza esperando o gate de audio.
$pygbagArgs = @("--disable-sound-format-error", "--ume_block=0")
if ($Build) {
    Write-Host ">> pygbag --build (empacota p/ WebAssembly)..." -ForegroundColor Cyan
    & $py -m pygbag @pygbagArgs --build "$stage\main.py"
    if ($LASTEXITCODE -ne 0) { Write-Host "ERRO no pygbag --build ($LASTEXITCODE)" -ForegroundColor Red; exit 1 }

    # O pygbag deixa o index.html buscando ~21 MB de runtime em
    # pygame-web.github.io a cada load, e no Firefox os arquivos grandes desse
    # CDN cortam no meio ("NetworkError for: .../cpython312/main.data"). Sem
    # este passo a build sai quebrada no Firefox e dependente de um terceiro.
    # O motivo completo esta no cabecalho do script.
    & "$PSScriptRoot\web_selfhost_runtime.ps1"
    if ($LASTEXITCODE -ne 0) { Write-Host "ERRO no self-host do runtime web." -ForegroundColor Red; exit 1 }
}
elseif ($Serve) {
    # -Serve NAO recebe o self-host do runtime: o servidor do pygbag regenera o
    # index.html a cada start, entao o patch seria sobrescrito. Nao faz falta
    # aqui - o corte de download e do Firefox contra o CDN, e em localhost os
    # arquivos grandes chegam inteiros. Para testar o bundle self-hosted de
    # verdade: .\build_web.ps1 -Build  e depois
    # python -m http.server 8000 -d web\staging\build\web
    Write-Host ">> pygbag (servidor local em http://localhost:8000)..." -ForegroundColor Cyan
    & $py -m pygbag @pygbagArgs --port 8000 "$stage\main.py"
}
