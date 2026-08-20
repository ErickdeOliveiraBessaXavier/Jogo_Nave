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
import pytest  # noqa: E402


def pytest_configure(config):
    """Inicializa pygame headless uma vez para toda a sessão.

    Entidades que carregam fontes/surfaces no `__init__` (RevivalBeacon, HUD)
    exigem `font.init`. Com o driver dummy nada abre janela nem toca som.
    """
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((320, 240))


# ── Arena de teste (flag de desenvolvimento) ─────────────────────────────────
# `fixed_levels.TEST_ARENA_ENABLED` troca a campanha inteira por uma arena de um
# tema só, para validar inimigos isoladamente. As arenas IGNORAM DE PROPÓSITO o
# variety cap e o piso de inimigos (está escrito no bloco delas), então todo
# teste que varre `get_level_config` mede outra coisa enquanto ela está ligada —
# e falha com números crus (`assert 40 >= 80`) que não mencionam flag nenhuma.
#
# Marcar esses testes com `skip_se_arena_de_teste` deixa o dev trabalhar com a
# arena ligada e a suíte legível. Quem cobra o desligamento é
# `test_dev_flags.py`, com UMA falha que diz o que fazer.


def _arena_de_teste_ativa() -> bool:
    from game.core.levels import fixed_levels

    return bool(fixed_levels.TEST_ARENA_ENABLED)


skip_se_arena_de_teste = pytest.mark.skipif(
    _arena_de_teste_ativa(),
    reason=(
        "TEST_ARENA_ENABLED ligada: a arena substitui a campanha e ignora o "
        "variety cap e o piso de inimigos por design (ver test_dev_flags.py)"
    ),
)
