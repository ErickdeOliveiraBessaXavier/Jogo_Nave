#!/usr/bin/env bash
# ============================================================
#  Configura o ambiente de build LINUX (rodar DENTRO do WSL).
#    bash setup_venv_linux.sh
#  Usa uv + Python 3.12 (mesma versao do build Windows) num venv em
#  filesystem NATIVO do Linux (~/.venvs), pois venv em /mnt/c falha o
#  ensurepip. Nao precisa de sudo.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

UV="$HOME/.local/bin/uv"
VENV="$HOME/.venvs/pixelpatrol-linux"

# 1. uv (instalador de Python + pacotes, userspace)
if [ ! -x "$UV" ]; then
    echo ">> Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
"$UV" --version

# 2. venv com Python 3.12 (uv baixa o CPython standalone; sem sudo)
echo ">> Criando venv (Python 3.12) em $VENV ..."
mkdir -p "$(dirname "$VENV")"
rm -rf "$VENV"
"$UV" venv --python 3.12 "$VENV"

# 3. dependencias (wheels prontas p/ 3.12; nao compila nada)
echo ">> Instalando pygame==2.6.1 + pyinstaller..."
VIRTUAL_ENV="$VENV" "$UV" pip install pygame==2.6.1 pyinstaller

# 4. butler (Linux) em ~/butler  (descompacta com python, sem depender de unzip)
echo ">> Instalando butler (Linux) em ~/butler ..."
mkdir -p "$HOME/butler"
if curl -fsSL "https://broth.itch.zone/butler/linux-amd64/LATEST/archive/default" -o /tmp/butler.zip; then
    python3 -m zipfile -e /tmp/butler.zip "$HOME/butler/"
    chmod +x "$HOME/butler/butler"
    "$HOME/butler/butler" -V || true
    echo ">> butler OK. Faca o login UMA vez:  ~/butler/butler login"
else
    echo "!! Nao consegui baixar o butler (DNS/rede)."
    echo "   Baixe a versao Linux em https://itchio.itch.io/butler ,"
    echo "   extraia 'butler' em ~/butler/ e rode: chmod +x ~/butler/butler"
fi

echo ">> Ambiente Linux pronto. Proximo: bash build_linux.sh"
