---
name: web-cdn-runtime-firefox
description: Build web baixava ~21 MB de runtime do pygame-web.github.io a cada load e no Firefox os arquivos grandes cortavam aos ~20%. RESOLVIDO por self-host do runtime no bundle (web_selfhost_runtime.ps1, chamado pelo build_web.ps1 -Build).
metadata:
  node_type: memory
  type: project
---

Investigação de 15/08/2026, **corrigida e verificada em 17/08/2026** — o jogo
sobe inteiro no Firefox pelo bundle self-hosted (testado por `127.0.0.1`, ver
armadilha de teste abaixo). Falta só confirmar no itch depois do próximo
`publicar_web.ps1`. Sintoma original no Firefox:
`Error occurred: NetworkError for: https://pygame-web.github.io/cdn/0.9.3/cpython312/main.data`
(o `main.wasm` dava o mesmo). Chrome não era afetado.

## Causa

O `index.html` gerado pelo pygbag 0.9.3 **não** empacota o runtime CPython: ele
o busca no CDN de terceiro a cada carregamento.

| origem | arquivos | tamanho |
|---|---|---|
| itch (mesma origem) | `staging.apk` | 72 MB |
| `pygame-web.github.io/cdn/0.9.3/` | `pythons.js` (69 KB), `cpythonrc.py` (50 KB), `empty.ogg` (4 KB), `empty.html` (14 B), `cpython312/main.js` (850 KB), `cpython312/main.data` (6,67 MB), `cpython312/main.wasm` (13,45 MB) | ~21 MB |

No Firefox os arquivos **grandes** desse CDN cortam no meio; os pequenos passam
(por isso a tela aparecia e o jogo nunca subia). Os prefixos salvos em disco na
época mediam 19% do `main.wasm` e 21% do `main.data`, com o primeiro 1 KB
**idêntico** ao do CDN (byte a byte, via `AddRange(0,1023)` + MD5) — download
começou certo e foi interrompido. **Não era rede nem antivírus desta máquina:**
`WebClient.DownloadFile` puxou os 13.447.111 bytes completos em 6,3 s.

## Correção implementada

`web_selfhost_runtime.ps1` (raiz), rodado automaticamente pelo
`build_web.ps1 -Build` depois do `pygbag --build`:

1. Espelha **11 arquivos** em `web/cdn_cache/` (gitignored), reproduzindo o
   layout do CDN, validando **tamanho contra o `Content-Length`** e promovendo
   só o arquivo íntegro (`.tmp` → `Move-Item`, mesma lógica do §15). Cache
   inválido por tamanho é rebaixado — não dá para herdar em casa o problema que
   estamos consertando.
2. Copia para `web/staging/build/web/runtime/` (o butler sobe a pasta inteira,
   então viaja sozinho).
3. Reescreve o `index.html`: apaga a tag do `browserfs.min.js`, aponta o
   `<script>` do `pythons.js` e o `src` do iframe para o espelho, e troca o
   `cdn :` por `new URL("./runtime/0.9.3/", location.href).href`.
4. Falha a build se sobrar qualquer `pygame-web.github.io` no `index.html`, se
   o `config.cdn` não tiver ficado absoluto, ou se faltar arquivo no bundle.

### Espelhar a ESTRUTURA, não os arquivos — e `config.cdn` ABSOLUTO

As duas coisas que a primeira tentativa errou, cada uma com sintoma próprio:

- **`config.cdn = "./"` (tudo achatado numa pasta) quebra os `../`.** O runtime
  sai da pasta da versão para buscar coisa na raiz do CDN:
  `pythons.js:1011  import("../vtx.js")` → `cdn/vtx.js`, e
  `vtx.js:18  config.cdn + "../vt/"` → `cdn/vt/{xterm.css, xterm.js,
  xterm-addon-image.js}`. Achatado, o `../` sobe para **fora** do bundle:
  *"error loading dynamically imported module: .../vtx.js"*.
  Por isso o bundle reproduz o layout sob `runtime/`, que faz o papel de `cdn/`:
  `runtime/vtx.js`, `runtime/vt/…`, `runtime/0.9.3/…`. Assim **nenhum** caminho
  calculado pelo runtime precisa ser reescrito.
- **`config.cdn` relativo quebra o `vtx.js` mesmo com o layout certo.** O
  `import()` dele resolve relativo ao **módulo** (`runtime/vtx.js`), não ao
  documento — um `"./runtime/0.9.3/"` viraria `runtime/runtime/vt/xterm.js`. No
  CDN isso nunca apareceu porque lá o valor já era URL absoluta. Daí o
  `new URL(..., location.href).href`. O `vtx.js` lê de
  `window.Module.config.cdn` (`window.Module = vm`, `pythons.js:2046`); sem ele
  cairia num `https://pygame-web.github.io/cdn/vt/` **hardcoded**, e o
  self-host vazaria sem nenhum erro visível.

**Armadilha ao auditar:** `cdn/vtx.js` existe (9.887 bytes) e `cdn/vt/*`
também; o que **não** existe é `cdn/0.9.3/vtx.js`. Testar o caminho errado dá um
404 tranquilizador e falso. O único que dá 404 de verdade em toda parte é
`xtermjsixel/xterm-addon-image-worker.js` (`pythons.js:1036`) — já quebrado
upstream hoje, com a build funcionando; não espelhar.

`publicar_web.ps1` chama `-Verificar` antes do push — o caso que isso pega é
`-SoPush` sobre um bundle antigo, anterior ao self-host.

Custo: +20,4 MB no canal `html5`. Ganhos: carrega mais rápido e some a
dependência de terceiro (**se a pasta `0.9.3/` sair do ar, todas as builds já
publicadas quebram de uma vez, inclusive as antigas**).

## Detalhes que custaram tempo — não redescobrir

- **`config.cdn` alcança tudo do boot.** O `pythons.js` resolve por ele
  (linhas 393 `cdn+"cpythonrc.py"`, 480 `cdn+"cpython312/main.data"`, 1166
  `cdn+"empty.ogg"`, 2358 `config.executable = cdn+"cpython312/main.js"`). O
  `main.wasm` não aparece com `cdn` na frente porque o `locateFile` devolve
  `prefix + path` — o prefix é a pasta do `main.js`, então ele acompanha. Única
  quebra conhecida e irrelevante: linha 954, `cdn+"../../cdn/lib/index.html"`,
  do handler de download, fora do boot.
- **TESTAR O BUNDLE POR `127.0.0.1`, NUNCA POR `localhost`.** Duas coisas
  distintas mudam de comportamento quando a URL tem `//localhost:` e as duas
  fazem o teste medir outra coisa:
  - `cpythonrc.py:1082` liga o **modo dev do pygbag**, que troca o índice de
    pacotes por um servidor pygbag local e vai buscar o wheel do pygame_ce
    (`/cdn/cp312/pygame_ce-…whl`). Sem esse servidor no ar, falha com
    `status 0` — **falso negativo puro**, o ramo tem `else: PyConfig.pygbag = 0`
    e nunca roda no itch (a captura de rede no itch não mostra request de
    wheel). Não descobri de onde saiu a porta 8000 no request (a substituição
    usa `location.port`); provável default dentro do `aio.pep0723`, que está
    comprimido no `main.data`. Irrelevante enquanto o ramo for gated.
  - `pythons.js:2352` **sobrescreve `config.cdn`** pela pasta da própria tag
    quando `location.hostname === "localhost"` — ou seja, por localhost o teste
    nem exercita o `config.cdn` escrito no `index.html`.

  Comando: `python -m http.server 8123 -d web\staging\build\web` e abrir
  **`http://127.0.0.1:8123/`**.
- O `build_web.ps1 -Serve` **não** recebe o patch: o servidor do pygbag regenera
  o `index.html` a cada start.
- **Reuse de `WebClient` entre downloads falha.** O `main.data` estourou
  `WebException` no meio da sequência e baixou de primeira sozinho logo depois.
  O script usa instância nova por tentativa, 3 tentativas.
- **Escrever o `index.html` sem BOM** (`UTF8Encoding($false)`): o arquivo tem
  UTF-8 no meio (botões do console) e o BOM antes do `<html>` vira lixo.
- A flag `--cdn` do pygbag **não serve**: o `app.py` usa o mesmo valor para
  buscar o *template* em tempo de build (`tmpl_url = f"{args.cdn}{args.template}"`).

## Descartado — não perder tempo de novo

- **COOP/COEP / SharedArrayBuffer do itch.** Medido: `Cross-Origin-Opener-Policy`
  e `Cross-Origin-Embedder-Policy` **ausentes** tanto em
  `erick-de-oliveira.itch.io/pixel-patrol` quanto no embed real
  `html-classic.itch.zone/html/18331903-1867401/index.html`. Não mexer nas
  configurações do jogo no itch.
- **Extensões e Proteção Aprimorada do Firefox.** Já desativadas pelo usuário,
  sem mudança.
- **`browserfs.min.js` no console** → 404 no CDN **para todo mundo**. O
  `index.html` do pygbag pede com barra dupla e o arquivo não existe; o
  `pythons.js` sequer usa BrowserFS (`// was browserfs , removed`). A tag agora
  é removida pelo script.
- **`pygbag0.9.3.js` (service worker)** → também 404, e o `register` já vem
  comentado no template. Registro cross-origin é proibido por spec de qualquer
  forma.

## Pendência separada (não é este bug)

O bundle publicado leva `staging.apk` **e** `staging.tar.gz`, ~72 MB cada, e só
um é usado (o `.apk` quando o host casa `.itch.zone`, o `.tar.gz` fora dele) —
72 MB por release à toa. Remover o `.tar.gz` do upload quebraria o teste local
do bundle estático, então precisa de decisão.

Relacionado: [[itch-publishing-workflow]], [[web-no-save-persistence]].
