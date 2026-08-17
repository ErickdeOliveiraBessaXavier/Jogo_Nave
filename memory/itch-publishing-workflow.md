---
name: itch-publishing-workflow
description: "Fluxo de build/publicação no itch.io via butler — 3 canais: Windows, Linux (WSL) e Web (html5/pygbag)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2a23bd7e-5585-4734-8d8d-5e336c3e7589
---

Publicação do Pixel Patrol no **itch.io** (`erick-de-oliveira/pixel-patrol`) via **butler**. Doc completa em `docs/BUILD.md` (movida da raiz). Ordem de release: **Windows → Linux → Web** (todos leem o mesmo `VERSION`). Estado e gotchas não óbvios:

**Versão:** arquivo `VERSION` (semver) é fonte única; `publicar_itch.ps1` faz bump automático e envia tag `vX.Y.Z` via `--userversion`. **v0.1.0** já publicado no canal `windows`.

**Windows:** `.\publicar_itch.ps1` (bump patch + build + push). Spec `Pixel_Patrol.spec` com `upx=False` + onedir (reduz falso-positivo de antivírus). Áudio re-encodado p/ 128k (`reencode_audio.ps1`) → zip caiu de 233→154 MB. Originais recuperáveis via git.

**butler:** host de download é **`broth.itch.zone`** (o `broth.itch.ovh` foi descontinuado — dá NXDOMAIN até no DNS público). Windows em `C:\Users\eobx\butler\`; Linux em `~/butler/butler` no WSL. Creds em `~/.config/itch/butler_creds` são **portáveis**: copiei do Windows (`/mnt/c/Users/eobx/.config/itch/butler_creds`) pro WSL, evitando 2º login.

**Linux (via WSL) — FUNCIONANDO (v0.1.0 publicado 2026-07-13):** Ubuntu no WSL vem com **Python 3.14** (sem wheel de pygame 2.6.1 → tenta compilar e falha). Solução: **uv** instala Python **3.12** (igual ao Windows) em venv na **fs nativa** `~/.venvs/pixelpatrol-linux` (venv em /mnt/c falha o ensurepip). Build também vai pra fs nativa `~/pixelpatrol-dist-linux` (/mnt/c **não permite chmod** → quebra o COLLECT do PyInstaller). Fluxo: `bash setup_venv_linux.sh` → `bash build_linux.sh` → `bash publicar_linux.sh` (tudo DENTRO do WSL; preserva bit de execução). PyInstaller não faz cross-compile. Rodar wsl via PowerShell (não Git Bash, que mangela paths/variáveis); executar como arquivo .sh (não `-lc` com aspas aninhadas). Smoke test headless: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./Pixel_Patrol`.

**Web (canal `html5`, pygbag/WASM) — NOVO:** `.\publicar_web.ps1` (build via `build_web.ps1 -Build` + `butler push web\staging\build\web ...:html5 --userversion vX.Y.Z`). NÃO faz bump — lê o `VERSION` que o Windows já subiu. Canal `html5` é separado dos downloads; na **1ª publicação** marcar o upload no dashboard como "played in the browser" + embed 1280×720 + Fullscreen button (fica salvo). Pré-req: áudio web em `web\assets\audio` (`.\reencode_audio_web.ps1`). Bundle sai em `web\staging\build\web\` (com `index.html`). Web não persiste save — ver [[web-no-save-persistence]].

**Primeiro load após publicar falha — é cache frio do Cloudflare, não upload quebrado (17/08/2026).** Sintoma: `net::ERR_SSL_PROTOCOL_ERROR` em `https://html-classic.itch.zone/html/<id>/staging.apk`, terminando em `cross_file.error : TypeError: Failed to fetch`, e o jogo não sobe. Antes de investigar qualquer coisa, **recarregue** — resolveu.

Como confirmar que o upload está bom (foi o que fechou o caso): `HEAD` no `staging.apk` publicado devolve `Content-Length` cheio e `Accept-Ranges: bytes`, e um `WebClient.DownloadFile` puxa os ~72 MB inteiros. Se isso passa, o arquivo está íntegro e o problema é transporte. O header que denuncia é **`cf-cache-status: MISS`** junto de um `Last-Modified` de minutos atrás: o primeiro visitante depois do push busca 72 MB na ORIGEM, a transferência mais longa e frágil possível.

**Isso não é só "problema do dev testando cedo":** o MISS é por edge do Cloudflare, então o primeiro jogador a chegar em cada PoP após um release pega o mesmo caminho frio. É um risco real de primeira impressão, e é o argumento concreto para encolher o bundle.

Composição medida do payload (72 MB): **34,6 MB de áudio OGG + 32 MB de PNG + 4,2 MB de código**. Os PNGs **já estão ótimos** — auditei os 766 com PIL: re-encode lossless economiza **0%** e só 20 cabem em paleta de 256 cores. Não perder tempo com otimizador de imagem; o único lever com folga é o áudio.

**RESOLVIDO — `staging.tar.gz` fora do publish (17/08/2026):** o bundle gera `staging.apk` **e** `staging.tar.gz` (~69 MB cada) e no itch só o `.apk` é usado — o `index.html` escolhe pelo host (`location.host.find('.itch.zone')>0`). O `publicar_web.ps1` agora faz `butler push ... --ignore staging.tar.gz`: ~69 MB a menos de upload/armazenamento por release, sem mudar um byte do que o jogador baixa. A exclusão fica no PUBLISH e não no build porque o `.tar.gz` é o ramo `else`, usado ao testar o bundle estático fora do itch.

**Áudio web já está no piso — NÃO refazer esta investigação (medido 17/08/2026).** A música do web é **Vorbis 48k estéreo** e isso é praticamente o limite do libvorbis a 44,1 kHz: **40k estéreo o encoder RECUSA** (`encoder setup failed`). Medido num arquivo de 1.655 KB:

| opção | vs. atual |
|---|---|
| Vorbis estéreo 48k (atual) | — |
| Vorbis mono 48k | **maior** (1.818 KB) |
| Vorbis mono 40k | 90% |
| Vorbis mono 32k | 80% |
| Opus estéreo 32k | 75% |

Outras armadilhas medidas: **`-q:a` negativo é IGNORADO** pelo libvorbis do ffmpeg (q=-1 e q=-2 devolvem o default, 4.280 KB) — VBR não serve de controle aqui; e `-b:a` do libvorbis é aproximativo, alvos próximos convergem.

Conclusão: o melhor caso realista poupa **6–8 MB de 72 MB (9–12%)**, com perda audível (mono/32k) ou com risco de compatibilidade (Opus só toca se o SDL_mixer do pygbag tiver libopus — e a falha é **silenciosa**, build sem música). Decidido **não fazer**. Se um dia valer, testar Opus com UM arquivo e confirmar no navegador antes de converter o resto.

O `reencode_audio_web.ps1` agora separa `-MusicKbps` (48) de `-SfxKbps` (64): música é 33,8 MB do áudio, SFX são 0,8 MB, então bitrate de SFX não muda tamanho e só custaria transiente.

**SmartScreen:** resolvido publicando via itch (jogadores instalam pela itch.io app); não é problema do packer nem do PyInstaller.

**Pendência git:** mudanças não commitadas (26 mp3 re-encodados, `VERSION`, `BUILD.md`, `publicar_itch.ps1`, `reencode_audio.ps1`, `*.sh`, `.gitattributes`). Usuário está no `master` — commitar em branch.
