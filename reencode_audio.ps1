# ============================================================
#  Re-encode dos MP3 de musica para reduzir o tamanho do build
#  Uso:  .\reencode_audio.ps1                 (dry-run: so mostra o que faria)
#        .\reencode_audio.ps1 -Aplicar        (re-encoda de verdade, in-place)
#        .\reencode_audio.ps1 -Aplicar -Kbps 160
#
#  Seguranca: os MP3 estao versionados no git. O script se recusa a rodar
#  se houver alteracoes nao commitadas em game/assets/audio/music (assim o
#  original e sempre recuperavel com:  git checkout -- game/assets/audio/music ).
# ============================================================

param(
    [switch]$Aplicar,          # sem isso, roda em modo simulacao (dry-run)
    [int]$Kbps = 128,          # bitrate alvo (CBR). 128 = bom p/ jogo; 160 = mais seguro
    # So a MUSICA: os SFX (game\assets\audio\sfx) sao curtos e ja leves, e
    # re-encodar por cima nao paga a perda de qualidade. Aponte para
    # game\assets\audio se algum dia quiser incluir os dois.
    [string]$Pasta = "game\assets\audio\music"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- localizar ffmpeg / ffprobe (PATH ou instalacao do winget) ---
function Find-Exe($nome) {
    $c = Get-Command $nome -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "$nome.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}
$ffmpeg  = Find-Exe "ffmpeg"
$ffprobe = Find-Exe "ffprobe"
if (-not $ffmpeg -or -not $ffprobe) {
    Write-Host "ERRO: ffmpeg/ffprobe nao encontrados. Instale com: winget install Gyan.FFmpeg" -ForegroundColor Red
    exit 1
}

# --- trava de seguranca: git limpo na pasta de audio ---
$dirty = git status --porcelain -- $Pasta
if ($dirty) {
    Write-Host "ERRO: ha alteracoes nao commitadas em $Pasta." -ForegroundColor Red
    Write-Host "Commite ou reverta antes de rodar, para o original ficar salvo no git." -ForegroundColor Yellow
    exit 1
}

$modo = if ($Aplicar) { "APLICAR (in-place)" } else { "SIMULACAO (dry-run)" }
Write-Host "== Re-encode de MP3 -> ${Kbps}k CBR  |  modo: $modo ==" -ForegroundColor Cyan
Write-Host "   (pulando arquivos ja <= ${Kbps} kbps)`n"

$arquivos = Get-ChildItem $Pasta -Recurse -Filter *.mp3

# A musica virou OGG Vorbis (~131k, derivada dos masters do git) e nao ha mais
# .mp3 aqui. Este script re-encoda MP3->MP3 e portanto nao tem mais o que fazer:
# sem esta guarda ele imprimiria "0 convertidos" e sairia com sucesso, enquanto
# o BUILD.md manda roda-lo para "reduzir o tamanho do audio" - o operador
# acreditaria ter encolhido algo.
#
# Se um dia for preciso mudar o tamanho da musica do desktop, NAO re-encode o
# .ogg do repo (perda sobre perda): re-derive dos masters, que continuam no
# historico do git sob os caminhos antigos (game/assets/audio/themes/...,
# game/assets/audio/bosses/...), com ffmpeg -c:a libvorbis -q:a <n>.
if ($arquivos.Count -eq 0) {
    Write-Host "Nada a fazer: nao ha .mp3 em $Pasta." -ForegroundColor Yellow
    Write-Host "A musica agora e OGG Vorbis ~131k, ja em qualidade de distribuicao." -ForegroundColor Yellow
    Write-Host "Para mudar o alvo, re-derive dos masters no historico do git (ver comentario no topo)." -ForegroundColor DarkGray
    exit 0
}
$tmp = Join-Path $env:TEMP "reencode_tmp.mp3"
$antesTotal = 0.0; $depoisTotal = 0.0; $convertidos = 0; $pulados = 0

foreach ($f in $arquivos) {
    $antesMB = $f.Length / 1MB
    $antesTotal += $antesMB
    $brRaw = & $ffprobe -v error -show_entries format=bit_rate -of default=noprint_wrappers=1:nokey=1 $f.FullName
    $brK = if ($brRaw -match '^\d+$') { [math]::Round([int]$brRaw / 1000) } else { 0 }

    if ($brK -gt 0 -and $brK -le $Kbps) {
        $pulados++
        $depoisTotal += $antesMB
        Write-Host ("  PULA  {0,4} kbps  {1}" -f $brK, $f.Name) -ForegroundColor DarkGray
        continue
    }

    if (-not $Aplicar) {
        # estimativa pos-conversao
        $estMB = ($Kbps / 8.0) * ($antesMB * 8.0 / [math]::Max($brK,1))  # ~ proporcional
        $estMB = [math]::Round($estMB, 1)
        $depoisTotal += $estMB
        Write-Host ("  conv  {0,4} kbps  {1,6:N1} MB -> ~{2,5:N1} MB  {3}" -f $brK, $antesMB, $estMB, $f.Name)
        $convertidos++
        continue
    }

    # --- conversao real ---
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    & $ffmpeg -hide_banner -loglevel error -y -i $f.FullName -map 0:a:0 -c:a libmp3lame -b:a "${Kbps}k" $tmp
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tmp)) {
        Write-Host ("  ERRO ao converter {0} (mantido original)" -f $f.Name) -ForegroundColor Red
        $depoisTotal += $antesMB
        continue
    }
    $novoMB = (Get-Item $tmp).Length / 1MB
    Move-Item $tmp $f.FullName -Force
    $depoisTotal += $novoMB
    $convertidos++
    Write-Host ("  OK    {0,4} kbps  {1,6:N1} MB -> {2,5:N1} MB  {3}" -f $brK, $antesMB, $novoMB, $f.Name) -ForegroundColor Green
}

Write-Host ""
Write-Host ("== Convertidos: $convertidos   Pulados: $pulados ==") -ForegroundColor Cyan
Write-Host ("== Total audio:  {0:N1} MB  ->  {1:N1} MB   (economia ~{2:N1} MB) ==" -f $antesTotal, $depoisTotal, ($antesTotal - $depoisTotal)) -ForegroundColor Cyan
if (-not $Aplicar) {
    Write-Host "`n(Isto foi uma SIMULACAO. Rode com -Aplicar para converter de verdade.)" -ForegroundColor Yellow
} else {
    Write-Host "`nPronto. Ouca alguns no jogo. Se nao gostar da qualidade:" -ForegroundColor Yellow
    Write-Host "   git checkout -- $Pasta   (restaura os originais)" -ForegroundColor Yellow
}
