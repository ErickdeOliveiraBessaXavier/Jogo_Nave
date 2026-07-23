"""Configuração compartilhada dos testes.

Roda tudo **headless**: driver de vídeo/áudio dummy do SDL, sem abrir janela
nem exigir placa de som. Isso precisa acontecer ANTES de qualquer `import
pygame`, por isso vive no conftest (carregado pelo pytest antes dos testes) e
mexe em `os.environ` no topo do módulo.

A raiz do projeto entra no `sys.path` para os testes importarem `game.*` sem
instalação editável.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pygame  # noqa: E402  (após o SDL dummy do ambiente, de propósito)


def pytest_configure(config):
    """Inicializa pygame headless uma vez para toda a sessão.

    Entidades que carregam fontes/surfaces no `__init__` (RevivalBeacon, HUD)
    exigem `font.init`. Com o driver dummy nada abre janela nem toca som.
    """
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((320, 240))
