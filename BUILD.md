# Build & Publicação — Pixel Patrol

Fluxo padronizado para gerar e publicar o jogo no itch.io
(`erick-de-oliveira/pixel-patrol`) via **butler**, com controle de versão.

## Controle de versão

A versão fica em **`VERSION`** (semver `X.Y.Z`) — fonte única para Windows e Linux.
O script de publicação incrementa automaticamente a cada envio e envia a tag
`vX.Y.Z` ao butler (`--userversion`), aparecendo na coluna VERSION do itch.

| Comando | Efeito na versão |
|---|---|
| `.\publicar_itch.ps1`               | +patch (0.1.0 → 0.1.1) |
| `.\publicar_itch.ps1 -Bump minor`   | +minor (0.1.9 → 0.2.0) |
| `.\publicar_itch.ps1 -Bump major`   | +major (0.9.0 → 1.0.0) |
| `.\publicar_itch.ps1 -SemBump`      | republica a versão atual |

---

## Windows (nativo, PowerShell)

Pré-requisitos: `.venv` com `pygame` + `pyinstaller`; butler em `~\butler\` já logado.

```powershell
# build + publica Windows, incrementando patch:
.\publicar_itch.ps1

# só reenviar o build atual (sem reconstruir):
.\publicar_itch.ps1 -SoPush
```

Saída do build: `dist\Pixel_Patrol\` (onedir). Configuração em `Pixel_Patrol.spec`
(`upx=False`, onedir — menos falso-positivo de antivírus).

### Reduzir tamanho do áudio (opcional)
```powershell
.\reencode_audio.ps1            # simulação (dry-run)
.\reencode_audio.ps1 -Aplicar   # aplica 128 kbps (git é o backup)
```

---

## Linux (via WSL)

> **Por que WSL?** PyInstaller não faz cross-compile — o binário Linux precisa
> ser gerado dentro do Linux. E o **push também** é feito de dentro do WSL, para
> preservar o bit de execução do binário (que se perderia via butler do Windows).

### 1. Instalar o WSL (uma vez, precisa de admin + reiniciar)
Em um PowerShell **como Administrador**:
```powershell
wsl --install -d Ubuntu
```
Reinicie o PC. No primeiro boot do Ubuntu, crie usuário/senha Unix.

### 2. Configurar o ambiente de build (uma vez)
No terminal do Ubuntu (WSL), vá até a pasta do projeto e rode:
```bash
cd /mnt/c/Users/eobx/OneDrive/Documentos/Jogos_Python/Nave
bash setup_venv_linux.sh     # uv + Python 3.12 + pygame + pyinstaller + butler
```
`setup_venv_linux.sh` usa **uv** para instalar o **Python 3.12** (mesma versão do
Windows) num venv na fs **nativa** do Linux (`~/.venvs/pixelpatrol-linux`) — venv
em `/mnt/c` falha o `ensurepip`. O build também sai na fs nativa
(`~/pixelpatrol-dist-linux`) porque `/mnt/c` não permite `chmod`.

Login do butler no Linux: ou `~/butler/butler login`, ou copie a credencial já
autorizada do Windows (evita novo login):
```bash
mkdir -p ~/.config/itch && cp /mnt/c/Users/eobx/.config/itch/butler_creds ~/.config/itch/
```

### 3. Publicar Linux
Opção A — tudo pelo Windows (o script chama o WSL sozinho):
```powershell
.\publicar_itch.ps1 -Plataformas linux     # ou -Plataformas ambos
```
Opção B — direto no WSL:
```bash
bash build_linux.sh          # gera dist-linux/Pixel_Patrol
bash publicar_linux.sh       # push do canal linux (lê VERSION)
```

---

## Publicar Windows **e** Linux juntos (mesma versão)
```powershell
.\publicar_itch.ps1 -Plataformas ambos      # +patch, publica os dois canais
```

## Depois de publicar
- Confirme no painel do itch a plataforma de cada upload (Windows/Linux) e marque
  "executável / roda pela itch.io app".
- Escreva um **devlog** no site (não dá pelo butler) contando as novidades.
- Status rápido: `~\butler\butler.exe status erick-de-oliveira/pixel-patrol`

## Arquivos do fluxo
| Arquivo | Papel |
|---|---|
| `VERSION`                | versão atual (semver) |
| `publicar_itch.ps1`      | build+publish Windows, bump de versão, orquestra Linux via WSL |
| `Pixel_Patrol.spec`      | config do build Windows |
| `reencode_audio.ps1`     | reduz o tamanho dos MP3 |
| `setup_venv_linux.sh`    | prepara o ambiente Linux no WSL |
| `build_linux.sh`         | gera a build Linux |
| `publicar_linux.sh`      | push do canal Linux |
| `Pixel_Patrol_linux.spec`| config do build Linux |
