"""Visual do tiro de GELO (upgrade Cryo Shot): o cristal e o rastro que escoa.

Paleta, sprite memoizado e desenho. A mecânica — a escada de lentidão, a bomba
de gelo — não está aqui: ela mora nas marcas que o sistema de colisão crava no
inimigo (`systems/shot_marks`). Este módulo só sabe desenhar.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, Tuple

import pygame

from ....core.player_tint import player_shot_color
from . import common, ship_styles

if TYPE_CHECKING:
    from ..bullet import Bullet

# Paleta dessaturada de propósito: o azul-elétrico saturado já é do Chain
# Lightning e do Engenheiro. Gelo é claro e frio, não neon.
_CRYO_FILL: Tuple[int, int, int] = (110, 190, 230)
_CRYO_EDGE: Tuple[int, int, int] = (200, 240, 255)
_CRYO_CORE: Tuple[int, int, int] = (255, 255, 255)
# Rastro congelante: blocos que ficam para trás, esfriando. Sem alpha de
# propósito — contra o fundo escuro, escurecer a cor lê como desvanecer e custa
# um `draw.rect` em vez de uma Surface com alpha por bala por frame (§7).
_CRYO_TRAIL: Tuple[Tuple[int, int, int], ...] = (
    (150, 215, 245),
    (95, 160, 205),
    (55, 100, 145),
)
# Segundos que um bloco leva para descer UMA casa do rastro. É a velocidade do
# escoamento, não a do tiro: a bala não muda de rumo nem de ritmo por causa
# disto. Rápido o bastante para o gelo parecer correr atrás do projétil, lento
# o bastante para o olho acompanhar cada bloco encolhendo.
_CRYO_TRAIL_STEP_TIME: float = 0.11

# Sprite do cristal por (w, h, jogador). O tiro tem meia dúzia de tamanhos no
# jogo inteiro, então o cache satura nos primeiros disparos.
_CRYO_BULLET_CACHE: Dict[Tuple[int, int, int], pygame.Surface] = {}


def cryo_trail_blocks(
    anim_time: float, slots: int = len(_CRYO_TRAIL)
) -> Tuple[Tuple[float, float], ...]:
    """Blocos do rastro de gelo: `(casa, fração de tamanho)` por bloco visível.

    O rastro **escoa**: cada bloco desce uma casa por `_CRYO_TRAIL_STEP_TIME`,
    encolhendo conforme se afasta, e some ao chegar na última. Um bloco novo
    surge na FRENTE do rastro, no tamanho cheio, e a fila inteira desce — é o
    que dá a leitura de gelo escorrendo, e não de três quadrados carimbados
    atrás do tiro.

    A casa 0 é desenhada um passo atrás do projétil (ver `draw`) e não sobre
    ele: com o bloco novo nascendo sob o sprite, o jogador via só dois dos três
    blocos a maior parte do tempo.

    A `casa` é contínua (0.0 → `slots`), então o movimento é suave e não um
    salto por bloco. O tamanho é linear na casa: cheio em 0, zero na última.

    Função pura de `anim_time` — sem estado por bloco, nada para vazar pelo pool
    e nada que o `draw` precise mutar (§3). O `anim_time` vem do update.
    """
    phase = (anim_time / _CRYO_TRAIL_STEP_TIME) % 1.0
    out = []
    # Começa em -1: é o bloco recém-nascido, que só entra em cena quando a fase
    # o empurra para dentro (`slot >= 0`). Sem ele haveria um buraco entre a
    # bala e o primeiro bloco no fim de cada ciclo.
    for k in range(-1, slots):
        slot = k + phase
        if slot < 0.0 or slot >= slots:
            continue
        out.append((slot, 1.0 - slot / slots))
    return tuple(out)


def _get_cryo_bullet_surface(w: int, h: int, player_index: int) -> pygame.Surface:
    """Cristal facetado do tamanho do tiro, memoizado.

    Hexágono alongado no eixo maior — a forma que lê como cristal de quartzo em
    poucos pixels. O losango claro por dentro é a faceta: é ela que dá volume e
    diferencia o tiro de uma cápsula azul qualquer.
    """
    key = (w, h, player_index)
    cached = _CRYO_BULLET_CACHE.get(key)
    if cached is not None:
        return cached

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2.0, h / 2.0
    fill = player_shot_color(_CRYO_FILL, player_index)
    edge = player_shot_color(_CRYO_EDGE, player_index)
    core = player_shot_color(_CRYO_CORE, player_index)

    if w >= h:  # cristal deitado (side-scroll / leque horizontal)
        body = [(0, cy), (w * 0.3, 0), (w, cy * 0.75), (w, cy * 1.25), (w * 0.3, h)]
        facet = [(w * 0.25, cy), (w * 0.5, cy * 0.45), (w * 0.8, cy), (w * 0.5, cy * 1.55)]
    else:  # cristal em pé (top-down, o caso comum)
        body = [(cx, 0), (w, h * 0.3), (cx * 1.25, h), (cx * 0.75, h), (0, h * 0.3)]
        facet = [(cx, h * 0.18), (w * 0.8, h * 0.42), (cx, h * 0.72), (w * 0.2, h * 0.42)]

    pygame.draw.polygon(surf, fill, body)
    if w >= 4 and h >= 4:
        pygame.draw.polygon(surf, edge, body, 1)
        pygame.draw.polygon(surf, core, facet)
    else:
        # Tiro minúsculo (Estilete tem 2px de largura): faceta não cabe, então o
        # brilho vira um pixel central — sem isso o cristal some numa mancha.
        surf.set_at((int(cx), int(cy)), core)

    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _CRYO_BULLET_CACHE[key] = surf
    return surf


def draw(bullet: "Bullet", surface: pygame.Surface) -> None:
    """Cristal de gelo com rastro que ESCOA.

    Fica DEPOIS do teleguiado e do explosivo na cadeia de despacho: aqueles
    dois visuais comunicam MECÂNICA (o '+' persegue, a granada explode) e
    escondê-los custaria leitura de jogo. O gelo ainda se anuncia nos combos
    pelo halo, que vira ciano quando o Cryo está ativo.

    O rastro continua sendo três blocos, mas eles não são mais carimbos
    fixos: cada um desce uma casa por ciclo encolhendo, o último some e um
    novo surge na frente (ver `cryo_trail_blocks`). A bala não muda de
    velocidade nem de rumo por causa disso — o ciclo vive só no `anim_time`,
    que o update alimenta.
    """
    rect = bullet.rect
    if bullet.size_multiplier > 1.0 and ship_styles.style_for(bullet.ship_id).breathes:
        rect = common.breathing_rect(rect)

    # Rastro primeiro: fica ATRÁS do cristal, saindo por trás dele.
    speed = math.hypot(bullet.vx, bullet.vy)
    if speed > 1.0:
        step = max(2, min(rect.width, rect.height))
        ux, uy = -bullet.vx / speed, -bullet.vy / speed
        cx, cy = rect.centerx, rect.centery
        full = max(1, step // 2)
        last = len(_CRYO_TRAIL) - 1
        for slot, scale in cryo_trail_blocks(bullet.anim_time):
            size = max(1, int(round(full * scale)))
            # Cor pela casa, não pelo índice do bloco: assim o tom acompanha
            # a POSIÇÃO no rastro e o bloco esfria enquanto desce, em vez de
            # levar a própria cor consigo.
            color = _CRYO_TRAIL[min(last, int(slot))]
            # `slot + 1`: a fila começa um passo ATRÁS do cristal. A casa 0
            # sobre o projétil deixaria o bloco recém-nascido escondido pelo
            # sprite, e o rastro apareceria com dois blocos em vez de três.
            px = int(cx + ux * step * (slot + 1.0)) - size // 2
            py = int(cy + uy * step * (slot + 1.0)) - size // 2
            pygame.draw.rect(surface, color, (px, py, size, size))

    surface.blit(
        _get_cryo_bullet_surface(rect.width, rect.height, bullet.player_index),
        rect.topleft,
    )
