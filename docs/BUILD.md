# Build & Publicação — Pixel Patrol

Como gerar e publicar o jogo no itch.io (`erick-de-oliveira/pixel-patrol`) via **butler**.

> ⚙️ A configuração do ambiente **já foi feita** neste PC. Para o dia a dia, use
> só a seção **"Publicar uma nova versão"** abaixo. A seção de configuração no
> final só é necessária num PC novo.

---

# 🚀 Publicar uma nova versão

Regra de ouro: **a versão sobe só uma vez, no passo do Windows. O Linux herda a
mesma versão.** Por isso faça sempre **Windows primeiro, Linux depois.**

### Passo 1 — Windows
No **PowerShell**, na pasta do projeto:
```powershell
.\publicar_itch.ps1
```
➜ incrementa a versão (ex.: 0.1.1 → 0.1.2), builda e publica o canal **windows**.

### Passo 2 — Linux
No terminal do **Ubuntu** (abra pelo Menu Iniciar, ou rode `wsl -d Ubuntu`):
```bash
cd /mnt/c/Users/eobx/OneDrive/Documentos/Jogos_Python/Nave
bash build_linux.sh
bash publicar_linux.sh
```
➜ builda e publica o canal **linux** usando a **mesma** versão do Passo 1.

**Pronto.** Os dois canais ficam sincronizados na mesma versão.

### Passo 3 — no site do itch (a cada release, opcional)
Escreva um **devlog** contando as novidades (o butler não faz isso).

---

## Escolher o tamanho do incremento
Por padrão o Passo 1 soma +1 no patch. Para mudar:
```powershell
.\publicar_itch.ps1 -Bump patch    # 0.1.2 → 0.1.3   (correções)   [padrão]
.\publicar_itch.ps1 -Bump minor    # 0.1.9 → 0.2.0   (novidades)
.\publicar_itch.ps1 -Bump major    # 0.9.0 → 1.0.0   (marco grande)
```

## Casos especiais
| Situação | O que fazer |
|---|---|
| **Só Windows** (correção rápida) | Só o Passo 1. O Linux fica na versão anterior (tudo bem). |
| **Só Linux** | Suba a versão antes: edite o número no arquivo `VERSION`, depois faça o Passo 2. |
| **Reenviar sem mudar a versão** | Win: `.\publicar_itch.ps1 -SemBump -SoPush`  ·  Linux: repita o Passo 2. |
| **Reduzir tamanho do áudio** | `.\reencode_audio.ps1` (simula) e `.\reencode_audio.ps1 -Aplicar` (git é o backup). |

## Conferir o que está publicado
```powershell
C:\Users\eobx\butler\butler.exe status erick-de-oliveira/pixel-patrol
```

---

# 🔧 Configuração única (PC novo ou 1ª vez)

> Você **já fez isto** neste computador. Guardado só para referência / outro PC.

## Windows
- `.venv` com `pygame` + `pyinstaller`.
- butler em `C:\Users\eobx\butler\`, logado uma vez com `butler login`.

## Linux (via WSL)
**Por quê WSL?** PyInstaller não faz cross-compile: o binário Linux tem que ser
gerado dentro do Linux, e o push também sai de dentro do WSL (para preservar o
bit de execução do binário).

1. **Instalar o WSL** (PowerShell **como Administrador**, depois reiniciar o PC):
   ```powershell
   wsl --install -d Ubuntu
   ```
   No primeiro boot do Ubuntu, crie usuário/senha Unix.

2. **Preparar o ambiente** (no terminal do Ubuntu):
   ```bash
   cd /mnt/c/Users/eobx/OneDrive/Documentos/Jogos_Python/Nave
   bash setup_venv_linux.sh
   ```
   Instala `uv` → Python **3.12** (igual ao Windows) → `pygame` + `pyinstaller` →
   `butler`. Tudo em filesystem **nativa** do Linux (venv e build em `/mnt/c`
   falham por causa de `ensurepip`/`chmod`).

3. **Autorizar o butler no Linux** — reaproveite a credencial do Windows:
   ```bash
   mkdir -p ~/.config/itch && cp /mnt/c/Users/eobx/.config/itch/butler_creds ~/.config/itch/
   ```
   (ou faça `~/butler/butler login`).

---

# Arquivos do fluxo
| Arquivo | Papel | Onde roda |
|---|---|---|
| `VERSION`                 | versão atual (semver `X.Y.Z`) — fonte única | — |
| `publicar_itch.ps1`       | bump + build + publish **Windows** | PowerShell |
| `Pixel_Patrol.spec`       | config do build Windows | — |
| `reencode_audio.ps1`      | reduz o tamanho dos MP3 | PowerShell |
| `setup_venv_linux.sh`     | prepara o ambiente Linux (uma vez) | WSL |
| `build_linux.sh`          | gera a build **Linux** | WSL |
| `publicar_linux.sh`       | publica o canal **Linux** (lê `VERSION`) | WSL |
| `Pixel_Patrol_linux.spec` | config do build Linux | — |

### Onde ficam as saídas do build
- **Windows:** `dist\Pixel_Patrol\`
- **Linux:** `~/pixelpatrol-dist-linux/Pixel_Patrol` (dentro do WSL, não em `/mnt/c`)
