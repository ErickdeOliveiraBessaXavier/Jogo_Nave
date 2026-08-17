# ============================================================
#  Publicar a versao WEB (pygbag/WASM) do Pixel Patrol no itch.io.
#  Canal 'html5' (jogavel no navegador). Usa a versao ATUAL de VERSION
#  (NAO incrementa — o bump acontece no publicar_itch.ps1, canal Windows).
#
#  Ordem de um release: publicar_itch.ps1 (Windows, faz o bump) -> Linux (WSL)
#  -> publicar_web.ps1. Assim os tres canais ficam na mesma versao.
#
#  Exemplos:
#    .\publicar_web.ps1            # build (pygbag --build) + push do canal html5
#    .\publicar_web.ps1 -SoPush    # pula o build, so envia o bundle ja gerado
# ============================================================

param(
    [switch]$SoPush,      # pular build, so enviar o bundle existente
    [switch]$AceitarMudos # repassar para build_web.ps1 quando o web ainda nao foi reencodado
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# >>> config do projeto no itch <<<
$ItchUser = "erick-de-oliveira"
$ItchGame = "pixel-patrol"
$Canal    = "html5"
$Bundle   = "web\staging\build\web"   # saida do pygbag --build (contem o index.html)

$butler = "$env:USERPROFILE\butler\butler.exe"
if (-not (Test-Path $butler)) {
    Write-Host "ERRO: butler.exe nao encontrado em $butler" -ForegroundColor Red
    exit 1
}

# ---------------- versao (le VERSION; NAO incrementa) ----------------
$versionFile = Join-Path $PSScriptRoot "VERSION"
if (-not (Test-Path $versionFile)) {
    Write-Host "ERRO: VERSION nao encontrado. Publique o Windows antes (.\publicar_itch.ps1)." -ForegroundColor Red
    exit 1
}
$ver = (Get-Content $versionFile -Raw).Trim()
if ($ver -notmatch '^\d+\.\d+\.\d+$') {
    Write-Host "ERRO: VERSION invalido ('$ver'). Deve ser X.Y.Z" -ForegroundColor Red; exit 1
}
$tag = "v$ver"
Write-Host ">> Versao (web, sem bump): $tag" -ForegroundColor Magenta

# ---------------- build do bundle web (pygbag --build) ----------------
# Reaproveita o build_web.ps1 (monta staging a partir de game/ + audio OGG leve
# e roda pygbag --build). Se o audio web faltar, build_web.ps1 aborta com dica.
if (-not $SoPush) {
    Write-Host ">> Build Web (pygbag --build via build_web.ps1)..." -ForegroundColor Cyan
    # HASHTABLE, nao array. Splatting de ARRAY passa os elementos como valores
    # posicionais: a string "-Build" nao vira o switch -Build, e como
    # build_web.ps1 so tem parametros nomeados, ela e descartada SEM ERRO. O
    # efeito era o build parar depois do staging, sem rodar o pygbag e sem uma
    # linha de aviso — o unico sintoma era o bundle nao existir no passo
    # seguinte. Com hashtable, a chave e o nome do parametro e o switch liga.
    $buildArgs = @{ Build = $true }
    if ($AceitarMudos) {
        $buildArgs.AceitarMudos = $true
    }
    & "$PSScriptRoot\build_web.ps1" @buildArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "Build Web falhou." -ForegroundColor Red; exit 1 }
}

if (-not (Test-Path "$Bundle\index.html")) {
    Write-Host "ERRO: bundle web ausente em '$Bundle' (sem index.html)." -ForegroundColor Red
    Write-Host "      Rode sem -SoPush para gerar o bundle antes." -ForegroundColor Yellow
    exit 1
}

# Confere o RESULTADO antes de subir 90 MB. Vale sobretudo para -SoPush, que
# pode estar enviando um bundle antigo, de antes do self-host do runtime: esse
# bundle busca ~21 MB em pygame-web.github.io e NAO CARREGA NO FIREFOX (os
# arquivos grandes do CDN cortam no meio do download). Falhar aqui custa
# segundos; publicar assim custa uma release quebrada para metade dos jogadores.
& "$PSScriptRoot\web_selfhost_runtime.ps1" -Verificar
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Conserto: .\web_selfhost_runtime.ps1  (ou rode sem -SoPush)" -ForegroundColor Yellow
    exit 1
}

# ---------------- push pro canal html5 ----------------
$alvo = "$ItchUser/$ItchGame`:$Canal"
Write-Host ">> Enviando '$Canal' ($tag) para $alvo ..." -ForegroundColor Cyan
& $butler push $Bundle $alvo --userversion $tag
if ($LASTEXITCODE -ne 0) { Write-Host "Push de '$Canal' falhou." -ForegroundColor Red; exit 1 }

Write-Host "`n>> Concluido. Web publicada: $tag (canal $Canal)" -ForegroundColor Green
Write-Host "   1a vez no itch: marque o upload como 'played in the browser'," -ForegroundColor Yellow
Write-Host "   embed 1280x720 + Fullscreen button (Edit game -> Uploads)." -ForegroundColor Yellow
Write-Host "   Status: $butler status $ItchUser/$ItchGame"
