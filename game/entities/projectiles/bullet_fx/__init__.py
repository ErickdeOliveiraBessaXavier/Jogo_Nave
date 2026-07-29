"""Aparência do projétil do jogador — um módulo por efeito.

**Por que o pacote existe.** Todo modificador de tiro (teleguiado, explosivo,
gelo, ácido) trouxe para dentro da `Bullet` a própria paleta, o próprio cache de
sprite e a própria função de desenho. Somados ao halo e ao estilo por nave, o
`bullet.py` chegou a **67% de código visual** — a física da bala, que é a razão
de a classe existir, tinha virado um terço do arquivo. E a conta piora sozinha:
cada upgrade de tiro novo custava mais ~120 linhas lá dentro.

Aqui cada efeito é um módulo dono do próprio visual:

| módulo | o que desenha |
|---|---|
| `homing` | o '+' pixelizado que gira |
| `explosive` | a granada com pavio e faíscas |
| `cryo` | o cristal e o rastro que escoa |
| `corrosive` | a bolha de ácido e a cauda que serpenteia |
| `ship_styles` | o corpo do tiro básico, por nave |
| `glow` | o halo pulsante, comum a todos |
| `common` | as peças compartilhadas (respiração do Giant Shot) |

**A fronteira.** Estes módulos DESENHAM: leem estado público da bala e pintam na
surface, sem mutar nada (§3). O que decide *quando* cada um vale — a cadeia de
prioridade — é o `draw_body` abaixo; o que decide o TAMANHO e a trajetória
continua na `Bullet`, e o que decide o EFEITO no inimigo está em
`systems/shot_marks`. Um efeito novo entra aqui e numa linha da cadeia.

**A cadeia de prioridade** existe porque um tiro pode ter vários modificadores ao
mesmo tempo, e só um corpo pode ser desenhado. Vence quem comunica MECÂNICA: o
'+' persegue, a granada explode. Gelo e ácido perdem o corpo nos combos, mas
seguem visíveis no halo (`glow`) e, no caso do ácido, no próprio inimigo
(`corrosion_stain`) — que é onde a mecânica dele mora.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from . import common, corrosive, cryo, explosive, glow, homing, ship_styles

if TYPE_CHECKING:
    from ..bullet import Bullet

__all__ = [
    "common",
    "corrosive",
    "cryo",
    "draw_body",
    "explosive",
    "glow",
    "homing",
    "ship_styles",
]


def draw_body(bullet: "Bullet", surface: pygame.Surface) -> None:
    """Desenha o corpo do projétil pelo efeito de maior prioridade.

    A ordem é a documentada acima e não é arbitrária: quem comunica mecânica
    vence. Trocar a ordem aqui é decisão de leitura de jogo, não de estilo.
    """
    if bullet.homing:
        homing.draw(bullet, surface)
    elif bullet.explosive:
        explosive.draw(bullet, surface)
    elif bullet.cryo:
        cryo.draw(bullet, surface)
    elif bullet.corrosive:
        corrosive.draw(bullet, surface)
    else:
        ship_styles.draw_body(bullet, surface)
