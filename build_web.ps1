# ============================================================
#  Monta o staging da build WEB (pygbag) e (opcional) empacota.
#    .\build_web.ps1            -> só monta o staging em web\staging
#    .\build_web.ps1 -Build     -> monta + roda pygbag --build
#    .\build_web.ps1 -Serve     -> monta + roda pygbag (servidor local p/ testar)
#
#  O staging = codigo do jogo (game/) + assets, com o AUDIO LEVE (web/assets/audio)
#  no lugar do audio pesado do desktop, + main.py async.
# ============================================================

param(
    [switch]$Build,
    [switch]$Serve
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py    = ".\.venv\Scripts\python.exe"
$stage = "web\staging"

# Exige AMBOS: audio\ (musica OGG) e sounds\ (SFX OGG). O copy cru abaixo exclui
# .mp3 E .wav, entao os SFX so chegam ao staging pelo overlay web\assets\sounds.
# Sem ele (reencode antigo, so-audio) a build sairia MUDA de SFX.
if (-not (Test-Path "web\assets\audio") -or -not (Test-Path "web\assets\sounds")) {
    Write-Host "ERRO: web\assets\audio e/ou web\assets\sounds ausente. Rode antes: .\reencode_audio_web.ps1" -ForegroundColor Red
    exit 1
}

Write-Host ">> Limpando staging..." -ForegroundColor Cyan
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$stage\game" | Out-Null

Write-Host ">> Copiando codigo + assets (sem .mp3/.wav e __pycache__)..." -ForegroundColor Cyan
robocopy game "$stage\game" /E /XD __pycache__ /XF *.pyc *.mp3 *.wav /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null

Write-Host ">> Inserindo audio OGG (web) no lugar dos .mp3/.wav..." -ForegroundColor Cyan
robocopy "web\assets" "$stage\game\assets" /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
# robocopy usa exit codes 0-7 para sucesso; >=8 e erro real.
if ($LASTEXITCODE -ge 8) { Write-Host "ERRO no robocopy ($LASTEXITCODE)" -ForegroundColor Red; exit 1 }
$global:LASTEXITCODE = 0

Copy-Item "web\main.py" "$stage\main.py" -Force

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
}
elseif ($Serve) {
    Write-Host ">> pygbag (servidor local em http://localhost:8000)..." -ForegroundColor Cyan
    & $py -m pygbag @pygbagArgs --port 8000 "$stage\main.py"
}
