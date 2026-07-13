#!/usr/bin/env bash
# ============================================================
#  Publica a build LINUX no itch via butler. Rode DENTRO do WSL:
#    bash publicar_linux.sh
#  Le a versao de VERSION (mesma fonte do Windows). NAO incrementa
#  (o bump e responsabilidade do fluxo de publicacao Windows/PS).
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

ITCH_USER="erick-de-oliveira"
ITCH_GAME="pixel-patrol"
BUTLER="$HOME/butler/butler"
DIST="$HOME/pixelpatrol-dist-linux/Pixel_Patrol"   # fs nativa (mesma referencia em build_linux.sh)

[ -x "$BUTLER" ] || { echo "ERRO: butler nao encontrado em $BUTLER. Rode setup_venv_linux.sh"; exit 1; }
[ -d "$DIST" ] || { echo "ERRO: $DIST nao existe. Rode build_linux.sh antes."; exit 1; }

VER="$(tr -d ' \r\n' < VERSION)"
TAG="v${VER}"
echo ">> Enviando 'linux' (${TAG}) para ${ITCH_USER}/${ITCH_GAME}:linux ..."
"$BUTLER" push "$DIST" "${ITCH_USER}/${ITCH_GAME}:linux" --userversion "${TAG}"
echo ">> Concluido (linux ${TAG})."
