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

**SmartScreen:** resolvido publicando via itch (jogadores instalam pela itch.io app); não é problema do packer nem do PyInstaller.

**Pendência git:** mudanças não commitadas (26 mp3 re-encodados, `VERSION`, `BUILD.md`, `publicar_itch.ps1`, `reencode_audio.ps1`, `*.sh`, `.gitattributes`). Usuário está no `master` — commitar em branch.
