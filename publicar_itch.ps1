# ============================================================
#  Publicar Pixel Patrol no itch.io via butler (Windows + Linux)
#  com controle de versao automatico (semver em VERSION).
#
#  Exemplos:
#    .\publicar_itch.ps1                       # bump patch + publica Windows
#    .\publicar_itch.ps1 -Bump minor           # 0.1.9 -> 0.2.0
#    .\publicar_itch.ps1 -Plataformas ambos    # Windows E Linux (mesma versao)
#    .\publicar_itch.ps1 -Plataformas linux    # so Linux
#    .\publicar_itch.ps1 -SemBump              # republica a versao atual (sem incrementar)
#    .\publicar_itch.ps1 -SoPush               # nao reconstroi, so envia
# ============================================================

param(
    [ValidateSet("patch","minor","major")]
    [string]$Bump = "patch",              # tamanho do incremento
    [switch]$SemBump,                     # nao incrementar a versao
    [ValidateSet("windows","linux","ambos")]
    [string]$Plataformas = "windows",     # o que publicar
    [switch]$SoPush                       # pular build, so enviar
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# >>> config do projeto no itch <<<
$ItchUser = "erick-de-oliveira"
$ItchGame = "pixel-patrol"

$butler = "$env:USERPROFILE\butler\butler.exe"
if (-not (Test-Path $butler)) {
    Write-Host "ERRO: butler.exe nao encontrado em $butler" -ForegroundColor Red
    exit 1
}

# ---------------- controle de versao (VERSION, semver) ----------------
$versionFile = Join-Path $PSScriptRoot "VERSION"
if (-not (Test-Path $versionFile)) { "0.1.0" | Set-Content $versionFile -Encoding ascii }
$cur = (Get-Content $versionFile -Raw).Trim()
if ($cur -notmatch '^\d+\.\d+\.\d+$') {
    Write-Host "ERRO: VERSION invalido ('$cur'). Deve ser X.Y.Z" -ForegroundColor Red; exit 1
}
$maj,$min,$pat = $cur.Split('.') | ForEach-Object { [int]$_ }

if (-not $SemBump) {
    switch ($Bump) {
        "major" { $maj++; $min = 0; $pat = 0 }
        "minor" { $min++; $pat = 0 }
        "patch" { $pat++ }
    }
    $novo = "$maj.$min.$pat"
    $novo | Set-Content $versionFile -Encoding ascii
    Write-Host ">> Versao: $cur -> $novo" -ForegroundColor Magenta
} else {
    $novo = $cur
    Write-Host ">> Versao (sem bump): $novo" -ForegroundColor Magenta
}
$tag = "v$novo"

# ---------------- helper de publicacao por plataforma ----------------
function Publicar-Plataforma($canal, $pastaDist) {
    if (-not (Test-Path $pastaDist)) {
        Write-Host "AVISO: '$pastaDist' nao existe -> pulando canal '$canal'." -ForegroundColor Yellow
        Write-Host "       (Para Linux, gere a build no WSL com build_linux.sh antes.)" -ForegroundColor Yellow
        return $false
    }
    $alvo = "$ItchUser/$ItchGame`:$canal"
    Write-Host ">> Enviando '$canal' ($tag) para $alvo ..." -ForegroundColor Cyan
    & $butler push $pastaDist $alvo --userversion $tag
    if ($LASTEXITCODE -ne 0) { Write-Host "Push de '$canal' falhou." -ForegroundColor Red; return $false }
    return $true
}

# ---------------- WINDOWS ----------------
if ($Plataformas -eq "windows" -or $Plataformas -eq "ambos") {
    if (-not $SoPush) {
        Write-Host ">> Build Windows (PyInstaller)..." -ForegroundColor Cyan
        python -m PyInstaller --clean --noconfirm Pixel_Patrol.spec
        if ($LASTEXITCODE -ne 0) { Write-Host "Build Windows falhou." -ForegroundColor Red; exit 1 }
    }
    Publicar-Plataforma "windows" "dist\Pixel_Patrol" | Out-Null
}

# ---------------- LINUX (via WSL) ----------------
# A build + push Linux rodam DENTRO do WSL (preserva o bit de execucao do
# binario e usa o butler do Linux). O bump de versao ja foi feito acima; os
# scripts .sh leem o mesmo arquivo VERSION.
if ($Plataformas -eq "linux" -or $Plataformas -eq "ambos") {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) {
        Write-Host "AVISO: WSL nao encontrado -> canal 'linux' pulado (veja docs/BUILD.md)." -ForegroundColor Yellow
    } else {
        # Converte C:\...\Nave  ->  /mnt/c/.../Nave
        $mnt = "/mnt/" + $PSScriptRoot.Substring(0,1).ToLower() + ($PSScriptRoot.Substring(2) -replace '\\','/')
        Write-Host ">> Linux via WSL ($tag): build + push em $mnt" -ForegroundColor Cyan
        if (-not $SoPush) {
            wsl.exe -e bash -lc "cd '$mnt' && bash build_linux.sh"
            if ($LASTEXITCODE -ne 0) { Write-Host "Build Linux (WSL) falhou. Ambiente configurado? Veja docs/BUILD.md." -ForegroundColor Yellow }
        }
        wsl.exe -e bash -lc "cd '$mnt' && bash publicar_linux.sh"
        if ($LASTEXITCODE -ne 0) { Write-Host "Push Linux (WSL) falhou. Veja docs/BUILD.md." -ForegroundColor Yellow }
    }
}

Write-Host "`n>> Concluido. Versao publicada: $tag" -ForegroundColor Green
Write-Host "   Status: $butler status $ItchUser/$ItchGame"
