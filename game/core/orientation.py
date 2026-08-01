"""Detecção de tela em RETRATO, para pedir que o jogador gire o aparelho.

O jogo é 16:9 em paisagem. Num celular em pé, a mesma imagem cabe numa tira
horizontal no meio da tela: a nave fica com poucos pixels de altura, o HUD
encolhe junto e o jogo passa a impressão de estar quebrado — quando só está
sendo exibido no eixo errado.

**Por que isto não é `pygame.display.get_window_size()`.** No web o `set_mode` é
feito com a resolução LÓGICA fixa (ver `app.py`), e quem escala para o tamanho
real de exibição é o canvas do pygbag, por CSS. Do lado do Python a janela tem
sempre 1280×720 e nunca "gira" — perguntar ao pygame devolveria paisagem em
100% dos casos, inclusive com o aparelho em pé.

Quem sabe o formato real é a PÁGINA. O pygbag expõe o objeto `window` do
navegador pelo módulo `platform`, e é de lá que sai a resposta no web. No
desktop a janela é a própria tela e o `pygame` basta.

Tudo em `try/except` largo de propósito: `platform` é uma superfície de API que
não controlamos e que muda entre versões do pygbag. Falhar aqui tem de virar
"não sei dizer" (nenhum aviso), nunca uma exceção no meio do loop — o custo de
não avisar é um layout ruim; o de estourar é o jogo fechar.
"""

from __future__ import annotations

import sys

import pygame

# Abaixo disto não vale gritar: telas quase quadradas (tablets em pé, janelas
# redimensionadas no desktop) ainda são jogáveis, e um aviso que aparece quando
# não precisa ensina o jogador a ignorá-lo.
PORTRAIT_RATIO: float = 0.95


def viewport_size() -> tuple[int, int] | None:
    """Tamanho REAL de exibição, ou None quando não dá para saber."""
    if sys.platform == "emscripten":
        try:
            import platform as _pyplatform

            window = getattr(_pyplatform, "window", None)
            if window is None:
                return None
            w = int(window.innerWidth)
            h = int(window.innerHeight)
            return (w, h) if w > 0 and h > 0 else None
        except Exception:
            return None

    try:
        w, h = pygame.display.get_window_size()
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def is_portrait() -> bool:
    """A área de exibição está mais alta que larga o bastante para atrapalhar?"""
    size = viewport_size()
    if size is None:
        return False
    w, h = size
    return w / h < PORTRAIT_RATIO
