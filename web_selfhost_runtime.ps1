# ============================================================
#  Self-host do runtime CPython/WASM dentro do bundle web.
#
#    .\web_selfhost_runtime.ps1            -> espelha + corrige web\staging\build\web
#    .\web_selfhost_runtime.ps1 -Force     -> rebaixa tudo, ignorando o cache
#    .\web_selfhost_runtime.ps1 -Verificar -> so confere, nao altera nada
#
#  POR QUE ISSO EXISTE
#  -------------------
#  O index.html gerado pelo pygbag NAO empacota o interpretador: ele busca ~21 MB
#  de runtime em pygame-web.github.io a CADA carregamento do jogo. No Firefox os
#  arquivos grandes desse CDN cortam no meio do download - main.wasm parava em
#  19% e main.data em 21%, com "NetworkError for: .../cpython312/main.data" no
#  console. Nao e rede nem antivirus da maquina: um WebClient.DownloadFile puxa
#  os 13.447.111 bytes do main.wasm em 6,3 s. Os arquivos PEQUENOS do CDN passam,
#  os grandes cortam - por isso a tela aparecia e o jogo nunca subia.
#
#  Descartado na investigacao (nao repetir): COOP/COEP do itch (os headers nao
#  existem nem na pagina nem no embed), extensoes e Protecao Aprimorada do
#  Firefox. E o browserfs.min.js do console e ruido: da 404 no CDN para todo
#  mundo (o index pede com barra dupla e o arquivo nem existe), e o pythons.js
#  nao usa BrowserFS - o proprio codigo diz "was browserfs, removed".
#
#  Servindo o runtime da MESMA ORIGEM do jogo, o download passa pelo CDN do itch,
#  que ja entrega os 72 MB do staging.apk sem cortar. De brinde: carrega mais
#  rapido e o jogo para de depender de um terceiro - hoje, se a pasta 0.9.3/
#  sair do ar, TODAS as builds ja publicadas quebram de uma vez, inclusive as
#  antigas. Custo: +20,5 MB no upload do canal html5.
#
#  A flag --cdn do pygbag NAO resolve isso: o app.py usa o mesmo valor para
#  baixar o TEMPLATE em tempo de build (tmpl_url = f"{args.cdn}{args.template}"),
#  entao apontar para "./" quebra a build. Por isso o pos-processamento.
#
#  POR QUE ESPELHAR A ESTRUTURA, E NAO SO OS ARQUIVOS
#  --------------------------------------------------
#  O runtime faz contas de caminho RELATIVAS a raiz do CDN, saindo da pasta da
#  versao:
#      pythons.js:1011   await import("../vtx.js")            -> cdn/vtx.js
#      vtx.js:18         config.cdn + "../vt/"                -> cdn/vt/
#  Achatar tudo numa pasta so (config.cdn = "./") quebra as duas: o "../" sobe
#  para FORA do bundle. Foi o que aconteceu na primeira tentativa -
#  "error loading dynamically imported module: .../vtx.js".
#
#  Entao o bundle reproduz o layout do CDN sob runtime\, que faz o papel de
#  cdn\, e config.cdn aponta para runtime/<versao>/:
#      runtime\vtx.js                     <- ../vtx.js  cai aqui
#      runtime\vt\xterm*.js|css           <- ../vt/     cai aqui
#      runtime\0.9.3\pythons.js, cpythonrc.py, empty.ogg, empty.html
#      runtime\0.9.3\cpython312\main.js, main.data, main.wasm
#  Assim NENHUM caminho calculado pelo runtime precisa ser reescrito: todos
#  resolvem igualzinho ao CDN, so que dentro do bundle.
#
#  E config.cdn tem que ser ABSOLUTO (new URL(..., location.href).href). O
#  import() do vtx.js resolve relativo ao MODULO (runtime/vtx.js), nao ao
#  documento: um config.cdn relativo viraria runtime/runtime/vt/xterm.js. No
#  CDN isso nunca apareceu porque la o valor ja era uma URL absoluta.
# ============================================================

param(
    [string]$Bundle    = "web\staging\build\web",
    [string]$Version   = "0.9.3",
    [string]$Interp    = "cpython312",
    [switch]$Force,      # rebaixar mesmo com cache valido
    [switch]$Verificar   # so auditar o bundle, sem baixar nem escrever
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$CdnRoot  = "https://pygame-web.github.io/cdn/"   # raiz, NAO a pasta da versao
$CacheDir = "web\cdn_cache"                       # espelha o layout do CdnRoot
$Espelho  = "runtime"                             # pasta do bundle que faz o papel do cdn/
$Index    = Join-Path $Bundle "index.html"

# Caminhos RELATIVOS A RAIZ do CDN. A lista saiu de ler o pythons.js e o vtx.js,
# nao de chutar:
#   pythons.js  393  cdn + "cpythonrc.py"
#   pythons.js  480  cdn + "cpython312/main.data"   (locateFile do emscripten)
#   pythons.js 1011  import("../vtx.js")
#   pythons.js 1166  cdn + "empty.ogg"              (teste de media engagement)
#   pythons.js 2358  cdn + "cpython312/main.js"     (config.executable)
#   vtx.js       18  cdn + "../vt/" + {xterm.css, xterm.js, xterm-addon-image.js}
#   index.html       pythons.js + empty.html (iframe)
# O main.wasm nao aparece com o cdn na frente porque o locateFile devolve
# `prefix + path` para ele - o prefix e a pasta do main.js, entao ele acompanha.
#
# FORA da lista de proposito: xtermjsixel/xterm-addon-image-worker.js (pedido
# pelo pythons.js:1036) da 404 no CDN em qualquer lugar - cdn/, cdn/0.9.3/ e
# cdn/vt/. Ja esta quebrado hoje, com a build funcionando; espelhar o que nao
# existe so faria a build falhar por engano.
$Arquivos = @(
    "vtx.js",
    "vt/xterm.css",
    "vt/xterm.js",
    "vt/xterm-addon-image.js",
    "$Version/pythons.js",
    "$Version/cpythonrc.py",
    "$Version/empty.ogg",
    "$Version/empty.html",
    "$Version/$Interp/main.js",
    "$Version/$Interp/main.data",
    "$Version/$Interp/main.wasm"
)

if (-not (Test-Path $Index)) {
    Write-Host "ERRO: bundle web ausente em '$Bundle' (sem index.html)." -ForegroundColor Red
    Write-Host "      Rode antes: .\build_web.ps1 -Build" -ForegroundColor Yellow
    exit 1
}

function Get-TamanhoRemoto([string]$url) {
    $req = [System.Net.HttpWebRequest]::Create($url)
    $req.Method = "HEAD"
    $req.Timeout = 30000
    $resp = $req.GetResponse()
    $len = $resp.ContentLength
    $resp.Close()
    return $len
}

# ------------------------------------------------------------
#  Modo -Verificar: audita o bundle e sai.
# ------------------------------------------------------------
if ($Verificar) {
    $html = [System.IO.File]::ReadAllText((Resolve-Path $Index).Path, [System.Text.Encoding]::UTF8)
    $falhas = 0
    if ($html -match 'pygame-web\.github\.io') {
        Write-Host "FALHA: index.html ainda aponta para pygame-web.github.io." -ForegroundColor Red
        $falhas++
    }
    foreach ($rel in $Arquivos) {
        $dst = Join-Path $Bundle (Join-Path $Espelho ($rel -replace '/', '\'))
        if (-not (Test-Path $dst)) {
            Write-Host "FALHA: runtime ausente no bundle: $Espelho/$rel" -ForegroundColor Red
            $falhas++
        }
    }
    if ($falhas -gt 0) {
        Write-Host ">> Bundle NAO esta self-hosted ($falhas problema(s))." -ForegroundColor Red
        exit 1
    }
    Write-Host ">> Bundle self-hosted: nada e buscado fora da propria origem." -ForegroundColor Green
    exit 0
}

# ------------------------------------------------------------
#  1) Espelhar o runtime no cache local (com verificacao de tamanho).
# ------------------------------------------------------------
Write-Host ">> Espelhando runtime do CDN ($Version)..." -ForegroundColor Cyan

$baixados = 0

# Retentativa com WebClient NOVO a cada tentativa. Nao e paranoia decorativa:
# reusando uma unica instancia entre os arquivos, o main.data falhou com
# WebException no meio da sequencia e baixou de primeira sozinho logo depois.
# O CDN corta conexao reaproveitada de vez em quando - e um download parcial
# aqui produziria exatamente o bundle quebrado que este script existe para
# evitar. A verificacao de tamanho no chamador e quem decide se valeu.
function Invoke-DownloadComRetry([string]$url, [string]$destino, [int]$tentativas = 3) {
    for ($i = 1; $i -le $tentativas; $i++) {
        try {
            $wc = New-Object System.Net.WebClient
            try { $wc.DownloadFile($url, $destino) } finally { $wc.Dispose() }
            return
        } catch {
            if ($i -eq $tentativas) { throw }
            Write-Host ("   (tentativa {0}/{1} falhou: {2})" -f $i, $tentativas, $_.Exception.Message) -ForegroundColor DarkYellow
            Start-Sleep -Seconds 2
        }
    }
}

foreach ($rel in $Arquivos) {
    $url   = $CdnRoot + $rel
    $cache = Join-Path $CacheDir ($rel -replace '/', '\')
    $pasta = Split-Path $cache -Parent
    if (-not (Test-Path $pasta)) { New-Item -ItemType Directory -Force -Path $pasta | Out-Null }

    $esperado = Get-TamanhoRemoto $url

    # O cache so vale se o tamanho BATE com o do CDN. Um arquivo cortado pela
    # metade e exatamente o que estamos consertando - nao da para herdar o
    # problema de dentro de casa.
    if ((-not $Force) -and (Test-Path $cache) -and ((Get-Item $cache).Length -eq $esperado)) {
        Write-Host ("   cache  {0,-30} {1,10:N0} bytes" -f $rel, $esperado) -ForegroundColor DarkGray
        continue
    }

    # Baixa para .tmp e so promove o arquivo INTEIRO (mesma logica do save
    # atomico do jogo, CLAUDE.md 15): um download interrompido nunca vira
    # cache valido.
    $tmp = "$cache.tmp"
    Invoke-DownloadComRetry $url $tmp
    $real = (Get-Item $tmp).Length
    if ($real -ne $esperado) {
        Remove-Item $tmp -Force
        Write-Host "ERRO: $rel baixou $real de $esperado bytes (download cortado)." -ForegroundColor Red
        exit 1
    }
    Move-Item $tmp $cache -Force
    $baixados++
    Write-Host ("   baixa  {0,-30} {1,10:N0} bytes" -f $rel, $real) -ForegroundColor Green
}

if ($baixados -eq 0) { Write-Host "   (tudo do cache local)" -ForegroundColor DarkGray }

# ------------------------------------------------------------
#  2) Copiar para dentro do bundle, sob runtime\.
# ------------------------------------------------------------
Write-Host ">> Copiando runtime para o bundle..." -ForegroundColor Cyan

# Restos do layout ACHATADO da primeira versao deste script (runtime solto na
# raiz do bundle). Ficariam como 20 MB de lixo mudo dentro do upload.
foreach ($velho in @("pythons.js", "cpythonrc.py", "empty.ogg", "empty.html", $Interp)) {
    $p = Join-Path $Bundle $velho
    if (Test-Path $p) {
        Remove-Item $p -Recurse -Force
        Write-Host "   (removido layout antigo: $velho)" -ForegroundColor DarkYellow
    }
}

$total = 0
foreach ($rel in $Arquivos) {
    $cache = Join-Path $CacheDir ($rel -replace '/', '\')
    $dst   = Join-Path $Bundle (Join-Path $Espelho ($rel -replace '/', '\'))
    $pasta = Split-Path $dst -Parent
    if (-not (Test-Path $pasta)) { New-Item -ItemType Directory -Force -Path $pasta | Out-Null }
    Copy-Item $cache $dst -Force
    $total += (Get-Item $dst).Length
}
Write-Host (">> Runtime no bundle: {0:N1} MB em {1}\" -f ($total/1MB), $Espelho) -ForegroundColor Green

# ------------------------------------------------------------
#  3) Reapontar o index.html para o espelho local.
# ------------------------------------------------------------
Write-Host ">> Reapontando index.html para './$Espelho/$Version/'..." -ForegroundColor Cyan

$idxPath = (Resolve-Path $Index).Path
$html = [System.IO.File]::ReadAllText($idxPath, [System.Text.Encoding]::UTF8)

# As tres substituicoes casam por ALVO (pythons.js, cdn:, empty.html) e nao pelo
# valor antigo, entao rodam a partir de qualquer estado: index recem-gerado pelo
# pygbag, ja corrigido, ou corrigido por uma versao anterior deste script. Isso
# e o que torna o passo idempotente sem precisar guardar copia do original.
$html = [regex]::Replace(
    $html,
    '(?m)^[ \t]*<script src="[^"]*browserfs\.min\.js"></script>[ \t]*\r?\n',
    ''
)
$html = [regex]::Replace(
    $html,
    '<script src="[^"]*pythons\.js"',
    "<script src=`"./$Espelho/$Version/pythons.js`""
)
$html = [regex]::Replace(
    $html,
    '(?m)^(\s*)cdn\s*:\s*.*?,\s*$',
    "`$1cdn : new URL(`"./$Espelho/$Version/`", location.href).href,"
)
$html = [regex]::Replace(
    $html,
    'src="[^"]*empty\.html"',
    "src=`"./$Espelho/$Version/empty.html`""
)
# Sobra so o banner de log e o serviceWorker (que ja vem comentado no template).
$html = $html.Replace($CdnRoot, "./$Espelho/")

# Sem BOM: o index tem UTF-8 no meio (os botoes do console) e o BOM antes do
# <html> vira lixo no comeco do documento.
[System.IO.File]::WriteAllText($idxPath, $html, (New-Object System.Text.UTF8Encoding($false)))

# ------------------------------------------------------------
#  4) Conferir o RESULTADO, nao os ingredientes.
# ------------------------------------------------------------
if ($html -match 'pygame-web\.github\.io') {
    $sobra = ([regex]::Matches($html, '.*pygame-web\.github\.io.*') | ForEach-Object { $_.Value.Trim() })
    Write-Host "ERRO: index.html AINDA busca coisa no CDN:" -ForegroundColor Red
    foreach ($s in $sobra) { Write-Host "   $s" -ForegroundColor Red }
    exit 1
}
if ($html -notmatch [regex]::Escape("cdn : new URL(`"./$Espelho/$Version/`"")) {
    Write-Host "ERRO: o config.cdn do index.html nao ficou absoluto (o vtx.js quebra sem isso)." -ForegroundColor Red
    exit 1
}
foreach ($rel in $Arquivos) {
    $dst = Join-Path $Bundle (Join-Path $Espelho ($rel -replace '/', '\'))
    if (-not (Test-Path $dst)) {
        Write-Host "ERRO: runtime ausente no bundle apos a copia: $Espelho/$rel" -ForegroundColor Red
        exit 1
    }
}

Write-Host ">> OK: o bundle nao busca NADA fora da propria origem." -ForegroundColor Green
Write-Host "   Teste local: python -m http.server 8123 -d $Bundle" -ForegroundColor DarkGray
# 127.0.0.1, NAO localhost - a URL com "//localhost:" muda DOIS comportamentos e
# faz o teste medir outra coisa:
#   cpythonrc.py:1082  liga o modo dev do pygbag, que troca o indice de pacotes
#                      por um servidor pygbag local e falha buscando o wheel do
#                      pygame_ce. Esse ramo tem else: pygbag = 0 e NUNCA roda no
#                      itch - o erro e falso negativo.
#   pythons.js:2352    sobrescreve config.cdn pela pasta da propria tag, entao
#                      por localhost o teste nem exercita o valor que este script
#                      escreveu no index.html.
Write-Host "   Abra por http://127.0.0.1:8123/ (NAO localhost: liga o modo dev do pygbag)" -ForegroundColor Yellow
