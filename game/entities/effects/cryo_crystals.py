"""Cristais de gelo do inimigo congelado (upgrade Cryo Shot).

Quando a escada do Cryo enche, o inimigo entra no estágio **congelado** e ganha
cristais brotando em volta do corpo. É só desenho: o efeito não é uma entidade,
não tem ciclo de vida próprio e não guarda referência a inimigo nenhum.

**Por que não é entidade** (a decisão que importa aqui): um efeito que segue um
inimigo precisaria da referência a ele, e aí passa a existir a pergunta "o que
acontece quando o inimigo morre no meio do efeito?" — a mesma classe de problema
que o resíduo de marca no pool já cobrou nesta base de código. Como os cristais
são função pura do estado que JÁ está no inimigo (`cryo_stacks`,
`cryo_slow_timer`) mais a geometria dele, desenhá-los direto no passe de draw
elimina a pergunta: o gelo morre junto com o alvo porque nunca existiu separado.

Nada aqui aloca por frame nem muta estado (§3, §7): a forma dos cristais é
derivada do `id()` do inimigo (estável, sem campo novo para vazar pelo pool) e o
caminho rápido desenha direto na tela, sem buffer.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import pygame

from ...core.upgrades_config import (
    CRYO_CRYSTAL_COUNT,
    CRYO_CRYSTAL_EDGE,
    CRYO_CRYSTAL_FADE,
    CRYO_CRYSTAL_FILL,
    CRYO_CRYSTAL_INNER,
    CRYO_CRYSTAL_OUTER,
    CRYO_CRYSTAL_SHINE,
    CRYO_MAX_STACKS,
)

# Buffer com alpha por pixel, usado SÓ na dissolução final (alpha < 255). No
# resto do congelamento os cristais vão direto na tela — mesma divisão de
# caminhos do `ImplosionPulse`, e pela mesma razão: alocar Surface por inimigo
# por frame é exatamente o que §7 proíbe.
_alpha_scratch: pygame.Surface | None = None


def _get_alpha_scratch(size: int) -> pygame.Surface:
    global _alpha_scratch
    if _alpha_scratch is None or _alpha_scratch.get_width() < size:
        _alpha_scratch = pygame.Surface((size, size), pygame.SRCALPHA)
    return _alpha_scratch


def is_frozen(enemy: Any) -> bool:
    """O inimigo está no estágio congelado (escada cheia e ainda correndo)?"""
    return (
        int(getattr(enemy, "cryo_stacks", 0)) >= CRYO_MAX_STACKS
        and getattr(enemy, "cryo_slow_timer", 0.0) > 0.0
    )


def crystal_alpha(remaining: float) -> int:
    """Opacidade do gelo a `remaining` segundos do fim.

    Cheia quase o tempo todo, com uma cintilação de ±8 (o gelo "respira" sem
    piscar), e dissolvendo linearmente nos últimos `CRYO_CRYSTAL_FADE` segundos.

    O relógio da cintilação é o PRÓPRIO tempo restante, não um acumulador novo:
    ele já anda no update (§3 — o draw não pode ter relógio próprio) e já para
    com o jogo pausado ou em câmera lenta, de graça.
    """
    shimmer = 247 + int(8 * math.sin(remaining * 6.0))
    if remaining >= CRYO_CRYSTAL_FADE:
        return min(255, shimmer)
    return max(0, int(shimmer * (remaining / CRYO_CRYSTAL_FADE)))


def _shard_points(
    cx: float,
    cy: float,
    radius: float,
    angle: float,
    length: float,
    width: float,
    tilt: float,
) -> list[tuple[float, float]]:
    """Um cristal: quadrilátero facetado agarrado à BORDA do inimigo.

    Quatro pontos e não três — o triângulo lê como espinho, o quadrilátero com a
    base recuada lê como cristal.

    A base fica sobre a borda (`CRYO_CRYSTAL_INNER`), não perto do centro. A
    primeira versão nascia lá no meio e os cinco cristais se encontravam no
    miolo: o conjunto virava uma estrela sólida que engolia o sprite, exatamente
    o oposto de "encapsulado PARCIALMENTE". Ancorando na borda, o gelo cresce
    para fora e o inimigo continua visível por dentro.

    `tilt` desalinha a ponta do eixo radial. Cristal que aponta exatamente para
    fora lê como raio de estrela; inclinado, lê como formação natural.
    """
    ca, sa = math.cos(angle), math.sin(angle)
    tx, ty = -sa, ca  # tangente

    r_base = radius * CRYO_CRYSTAL_INNER
    bx, by = cx + ca * r_base, cy + sa * r_base

    # Ponta: direção radial girada por `tilt`.
    tip_a = angle + tilt
    r_tip = radius * length
    px, py = cx + math.cos(tip_a) * r_tip, cy + math.sin(tip_a) * r_tip

    # Ombros: a meio caminho da ponta, abertos na tangente.
    half = radius * width
    mx, my = (bx + px) * 0.5, (by + py) * 0.5

    return [
        (px, py),
        (mx + tx * half, my + ty * half),
        (bx, by),
        (mx - tx * half, my - ty * half),
    ]


def _draw_one(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    radius: float,
    seed: int,
    alpha: int,
    offset: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Desenha a coroa de cristais de UM inimigo."""
    ox, oy = offset
    base_angle = (seed % 360) * math.pi / 180.0
    step = math.tau / CRYO_CRYSTAL_COUNT

    fill = CRYO_CRYSTAL_FILL if alpha >= 255 else (*CRYO_CRYSTAL_FILL, alpha)
    edge = CRYO_CRYSTAL_EDGE if alpha >= 255 else (*CRYO_CRYSTAL_EDGE, alpha)
    shine = CRYO_CRYSTAL_SHINE if alpha >= 255 else (*CRYO_CRYSTAL_SHINE, alpha)

    for i in range(CRYO_CRYSTAL_COUNT):
        # Todas as variações saem do MESMO seed por índice: os cristais de um
        # inimigo são estáveis frame a frame (nada de tremer) e dois inimigos
        # vizinhos não congelam com o desenho idêntico.
        #
        # A irregularidade é forte de propósito. Com jitter pequeno o conjunto
        # volta a ser uma coroa regular — que é o que o olho lê como "estrela",
        # não como "gelo se formando".
        h = (seed >> (i * 5)) & 0x3FF
        angle = base_angle + i * step + ((h & 0xF) / 15.0 - 0.5) * step * 0.75
        length = CRYO_CRYSTAL_OUTER * (0.78 + ((h >> 4) & 0x7) / 7.0 * 0.34)
        # Largura generosa: em escala de jogo o inimigo tem ~40px e um cristal
        # de 2px de espessura some. Ele precisa ter corpo para o congelamento
        # ser lido de relance, que é o ponto do efeito.
        width = 0.17 + ((h >> 7) & 0x3) / 3.0 * 0.10
        tilt = (((h >> 9) & 0x1) * 2 - 1) * (0.18 + ((h >> 4) & 0x3) * 0.06)

        pts = [
            (x + ox, y + oy)
            for x, y in _shard_points(cx, cy, radius, angle, length, width, tilt)
        ]
        pygame.draw.polygon(surface, fill, pts)
        pygame.draw.polygon(surface, edge, pts, 1)
        # Faceta: a aresta da base até a ponta, que é o que dá volume ao cristal.
        pygame.draw.line(surface, shine, pts[2], pts[0], 1)


def draw_frozen(surface: pygame.Surface, enemies: Iterable[Any]) -> int:
    """Desenha o gelo de todos os inimigos congelados. Devolve quantos foram.

    A geometria vem de `collision_circle()`, nunca de `w`/`h`: nem todo inimigo
    tem esses campos, e em alguns (`MountainGeode`) `x`/`y` é o CENTRO e não o
    canto — as duas suposições que já derrubaram o jogo quando a Implosão as fez.
    """
    desenhados = 0
    for enemy in enemies:
        if getattr(enemy, "dead", False) or not is_frozen(enemy):
            continue

        circle = getattr(enemy, "collision_circle", None)
        if circle is None:
            continue
        cx, cy, radius = circle()
        if radius <= 1.0:
            continue

        alpha = crystal_alpha(getattr(enemy, "cryo_slow_timer", 0.0))
        if alpha <= 0:
            continue

        if alpha >= 255:
            _draw_one(surface, cx, cy, radius, id(enemy), 255)
        else:
            # Dissolução: o alpha parcial exige buffer. `fill` com RGBA zera o
            # alpha POR PIXEL — `set_alpha` seria alpha de superfície e ficaria
            # grudado no buffer para o próximo consumidor (a armadilha do §17).
            span = int(radius * CRYO_CRYSTAL_OUTER * 2) + 6
            buf = _get_alpha_scratch(span)
            area = pygame.Rect(0, 0, span, span)
            buf.fill((0, 0, 0, 0), area)
            half = span / 2
            _draw_one(buf, half, half, radius, id(enemy), alpha)
            surface.blit(buf, (int(cx - half), int(cy - half)), area)

        desenhados += 1
    return desenhados
