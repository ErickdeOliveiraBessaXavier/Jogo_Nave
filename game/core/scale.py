"""Escala global de gameplay por resolução (§12) — FONTE ÚNICA do fator.

O jogo desenha numa resolução lógica fixa (576p→1080p, escolhida em settings) que
o pygame escala para a tela física mantendo 16:9. Posições de mundo/spawn já usam
fração de `SCREEN_WIDTH` e se adaptam sozinhas; **tamanhos de pixel fixo** (raios,
larguras, espessuras e velocidades de ataques/efeitos) NÃO — ficam minúsculos em
resoluções maiores e exagerados nas menores.

Este módulo centraliza o fator de escala sobre o design base (1280×720), para que
ataques e entidades temporárias mantenham presença visual, distância e legibilidade
consistentes em qualquer resolução. Use `gameplay_scale()` para o fator ou
`scaled(v)` para escalar um valor — nunca duplique a fórmula `SCREEN_WIDTH/1280`
espalhada pelo código.
"""

from __future__ import annotations

from .config import config as Config

# Largura do design base (720p) — ui_scale == 1.0 aqui, layout idêntico ao original.
DESIGN_WIDTH: float = 1280.0


def gameplay_scale() -> float:
    """Fator de escala da resolução lógica atual sobre o design base (1280×720).

    576p→0.8, 720p→1.0, 900p→1.25, 1080p→1.5. Lido a cada chamada (a resolução só
    muda no restart via `set_screen_resolution`), então reflete sempre o valor atual.
    Um único fator serve aos dois eixos por ser 16:9.
    """
    return Config.SCREEN_WIDTH / DESIGN_WIDTH


def scaled(value: float) -> float:
    """Escala um valor de pixel/velocidade do design base pela resolução atual."""
    return value * gameplay_scale()
