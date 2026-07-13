# ============================================================
#  Publicar Pixel Patrol no itch.io via butler
#  Uso:  .\publicar_itch.ps1            (build + push)
#        .\publicar_itch.ps1 -SoPush    (pula o build, so envia)
# ============================================================

param(
    [switch]$SoPush  # se passar -SoPush, nao reconstroi o jogo
)

# >>> AJUSTE AQUI (uma vez): seu usuario e o slug do jogo no itch <<<
$ItchUser = "erick-de-oliveira"    # usuario da URL (NAO o nome de exibicao)
$ItchGame = "pixel-patrol"         # o slug que aparece na URL do jogo
$Canal    = "windows"              # nome do canal (plataforma)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$butler = "$env:USERPROFILE\butler\butler.exe"
if (-not (Test-Path $butler)) {
    Write-Host "ERRO: butler.exe nao encontrado em $butler" -ForegroundColor Red
    Write-Host "Baixe em https://itchio.itch.io/butler e extraia o butler.exe nessa pasta." -ForegroundColor Yellow
    exit 1
}

if (-not $SoPush) {
    Write-Host ">> Reconstruindo o jogo com PyInstaller..." -ForegroundColor Cyan
    python -m PyInstaller --clean --noconfirm Pixel_Patrol.spec
    if ($LASTEXITCODE -ne 0) { Write-Host "Build falhou." -ForegroundColor Red; exit 1 }
}

if (-not (Test-Path "dist\Pixel_Patrol")) {
    Write-Host "ERRO: dist\Pixel_Patrol nao existe. Rode sem -SoPush primeiro." -ForegroundColor Red
    exit 1
}

$alvo = "$ItchUser/$ItchGame`:$Canal"
Write-Host ">> Enviando para $alvo ..." -ForegroundColor Cyan
& $butler push "dist\Pixel_Patrol" $alvo
if ($LASTEXITCODE -ne 0) { Write-Host "Push falhou." -ForegroundColor Red; exit 1 }

Write-Host ">> Pronto! Veja o status em:" -ForegroundColor Green
Write-Host "   $butler status $ItchUser/$ItchGame"
