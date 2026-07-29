"""Cristais de gelo do alvo cristalizado (upgrade Cryo Shot).

Quando a escada do Cryo enche, o alvo ganha cristais brotando em volta do corpo.
É só desenho: o efeito não é uma entidade, não tem ciclo de vida próprio e não
guarda referência a inimigo nenhum.

**Por que não é entidade** (a decisão que importa aqui): um efeito que segue um
inimigo precisaria da referência a ele, e aí passa a existir a pergunta "o que
acontece quando o inimigo morre no meio do efeito?" — a mesma classe de problema
que o resíduo de marca no pool já cobrou nesta base de código. Como os cristais
são função pura do estado que JÁ está no inimigo (`cryo_stacks`,
`cryo_slow_timer`) mais a geometria dele, desenhá-los direto no passe de draw
elimina a pergunta: o gelo morre junto com o alvo porque nunca existiu separado.

Os cristais são o **pavio visível da bomba de gelo**: enquanto estão na tela a
carga está acumulando, e na janela final (`CRYO_CRYSTAL_CHARGE`) eles clareiam
e incham rumo ao estilhaço. Quem detona é o `EntityManager`/`Collisions` — aqui
só se lê o mesmo timer que eles leem.

Nada aqui aloca por frame nem muta estado (§3, §7): a forma dos cristais é
derivada do `id()` do alvo (estável, sem campo novo para vazar pelo pool) e o
desenho vai direto na tela — **sem buffer nenhum**. A versão anterior dissolvia
o gelo por alpha no fim, e alpha parcial obriga a um `Surface` SRCALPHA por alvo
por frame; com o estilhaço no lugar da dissolução, a variação de brilho passou a
ser cor, e o caminho de buffer deixou de existir.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import pygame

from ...core.upgrades_config import (
    CRYO_CRYSTAL_ARC,
    CRYO_CRYSTAL_CHARGE,
    CRYO_CRYSTAL_COUNT,
    CRYO_CRYSTAL_COUNT_MAX,
    CRYO_CRYSTAL_EDGE,
    CRYO_CRYSTAL_FILL,
    CRYO_CRYSTAL_INNER,
    CRYO_CRYSTAL_MAX_LENGTH,
    CRYO_CRYSTAL_MAX_WIDTH,
    CRYO_CRYSTAL_OUTER,
    CRYO_CRYSTAL_SHINE,
    CRYO_MAX_STACKS,
)


def is_frozen(enemy: Any) -> bool:
    """O alvo está cristalizado (escada cheia e pavio ainda correndo)?

    Vale igual para inimigo e para boss — a diferença entre os dois não está
    aqui, e sim na lentidão: boss cristaliza mas nunca é freado (ver
    `accepts_cryo` e `EntityManager._cryo_multiplier`).
    """
    return (
        int(getattr(enemy, "cryo_stacks", 0)) >= CRYO_MAX_STACKS
        and getattr(enemy, "cryo_slow_timer", 0.0) > 0.0
    )


def shimmer(remaining: float) -> float:
    """Cintilação do gelo (0..1) a `remaining` segundos do estouro.

    Modula o BRILHO, não a opacidade: alpha parcial exigiria um buffer SRCALPHA
    por alvo por frame (§7) para um efeito de ±3% que ninguém consegue nomear.
    Clarear a cor entrega a mesma "respiração" desenhando direto na tela.

    A frequência sobe junto com a carga — o gelo fica nervoso antes de estourar.

    O relógio é o PRÓPRIO tempo restante, não um acumulador novo: ele já anda no
    update (§3 — o draw não pode ter relógio próprio) e já para com o jogo
    pausado ou em câmera lenta, de graça.
    """
    speed = 6.0 + 26.0 * charge_ratio(remaining)
    return 0.5 + 0.5 * math.sin(remaining * speed)


def charge_ratio(remaining: float) -> float:
    """Quanto a bomba já carregou (0 = recém-congelado, 1 = estourando).

    Só sobe na janela final (`CRYO_CRYSTAL_CHARGE`). Antes dela o gelo é gelo;
    dentro dela ele vira aviso — e é esse aviso que dá ao jogador a chance de
    posicionar o próximo alvo perto do estouro.
    """
    if remaining >= CRYO_CRYSTAL_CHARGE:
        return 0.0
    return max(0.0, min(1.0, 1.0 - remaining / CRYO_CRYSTAL_CHARGE))


def crystal_count(radius: float) -> int:
    """Quantos cristais cabem em volta de um alvo de raio `radius`.

    Alvo comum (~20px de raio) fica no `CRYO_CRYSTAL_COUNT` de sempre: poucos e
    grandes, que é o que lê como "encapsulado parcialmente". Alvo grande (boss)
    ganha MAIS cristais em vez de cristais maiores — ver `_crystal_scale`.
    """
    by_arc = int(math.tau * radius / CRYO_CRYSTAL_ARC)
    return max(CRYO_CRYSTAL_COUNT, min(CRYO_CRYSTAL_COUNT_MAX, by_arc))


def _crystal_scale(radius: float) -> tuple[float, float]:
    """(fração de comprimento, fração de largura) do cristal para este raio.

    As frações de `upgrades_config` são do raio do alvo, o que funciona enquanto
    o alvo tem tamanho de inimigo. Num boss de 120px de raio, 0.5×raio viraria
    uma lâmina de 60px: o "gelo" cobriria o corpo inteiro e a arena junto. Os
    tetos em pixels (`CRYO_CRYSTAL_MAX_*`) seguram o tamanho do cristal, e o
    perímetro extra é preenchido com mais cristais (`crystal_count`).
    """
    over = radius * (CRYO_CRYSTAL_OUTER - 1.0)
    if over > CRYO_CRYSTAL_MAX_LENGTH:
        length = 1.0 + CRYO_CRYSTAL_MAX_LENGTH / radius
    else:
        length = CRYO_CRYSTAL_OUTER
    width_cap = CRYO_CRYSTAL_MAX_WIDTH / radius
    return length, width_cap


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _shard_points(
    cx: float,
    cy: float,
    radius: float,
    angle: float,
    length: float,
    width: float,
    tilt: float,
) -> list[tuple[float, float]]:
    """Um cristal: quadrilátero facetado agarrado à BORDA do alvo.

    Quatro pontos e não três — o triângulo lê como espinho, o quadrilátero com a
    base recuada lê como cristal.

    A base fica sobre a borda (`CRYO_CRYSTAL_INNER`), não perto do centro. A
    primeira versão nascia lá no meio e os cinco cristais se encontravam no
    miolo: o conjunto virava uma estrela sólida que engolia o sprite, exatamente
    o oposto de "encapsulado PARCIALMENTE". Ancorando na borda, o gelo cresce
    para fora e o alvo continua visível por dentro.

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
    charge: float = 0.0,
    glint: float = 0.0,
) -> None:
    """Desenha a coroa de cristais de UM alvo."""
    count = crystal_count(radius)
    max_length, max_width = _crystal_scale(radius)
    base_angle = (seed % 360) * math.pi / 180.0
    step = math.tau / count

    # Carga: o gelo clareia rumo ao branco e as pontas incham. Duas leituras do
    # mesmo estado — quem olha a cor e quem olha a silhueta recebem o aviso.
    # A cintilação entra como um empurrãozinho na mesma rampa de cor.
    heat = min(1.0, charge * 0.75 + glint * 0.06)
    fill = _lerp(CRYO_CRYSTAL_FILL, CRYO_CRYSTAL_SHINE, heat)
    edge = _lerp(CRYO_CRYSTAL_EDGE, CRYO_CRYSTAL_SHINE, charge)
    shine = CRYO_CRYSTAL_SHINE
    swell = 1.0 + 0.18 * charge

    for i in range(count):
        # Todas as variações saem do MESMO seed por índice: os cristais de um
        # alvo são estáveis frame a frame (nada de tremer) e dois inimigos
        # vizinhos não congelam com o desenho idêntico.
        #
        # O embaralhamento multiplicativo (e não `seed >> i*5`) existe porque a
        # coroa de um boss chega a 16 cristais: deslocar 5 bits por índice
        # zerava o `id()` a partir do 10º e o resto da coroa saía idêntico.
        #
        # A irregularidade é forte de propósito. Com jitter pequeno o conjunto
        # volta a ser uma coroa regular — que é o que o olho lê como "estrela",
        # não como "gelo se formando".
        h = ((seed >> 4) * (i * 2654435761 + 1)) & 0x3FF
        angle = base_angle + i * step + ((h & 0xF) / 15.0 - 0.5) * step * 0.75
        # O jitter mexe no que PASSA da borda, não no raio inteiro: é o que
        # mantém a variação de ponta legível quando o teto em pixels do boss
        # encurta os cristais (jitter sobre o total viraria ruído de 1px lá).
        over = (max_length - 1.0) * (0.34 + ((h >> 4) & 0x7) / 7.0 * 0.9)
        length = 1.0 + over * swell
        # Largura generosa: em escala de jogo o inimigo tem ~40px e um cristal
        # de 2px de espessura some. Ele precisa ter corpo para o congelamento
        # ser lido de relance, que é o ponto do efeito.
        width = min(max_width, 0.17 + ((h >> 7) & 0x3) / 3.0 * 0.10)
        tilt = (((h >> 9) & 0x1) * 2 - 1) * (0.18 + ((h >> 4) & 0x3) * 0.06)

        pts = _shard_points(cx, cy, radius, angle, length, width, tilt)
        pygame.draw.polygon(surface, fill, pts)
        pygame.draw.polygon(surface, edge, pts, 1)
        # Faceta: a aresta da base até a ponta, que é o que dá volume ao cristal.
        pygame.draw.line(surface, shine, pts[2], pts[0], 1)


def draw_frozen(surface: pygame.Surface, enemies: Iterable[Any]) -> int:
    """Desenha o gelo de todos os alvos cristalizados. Devolve quantos foram.

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

        remaining = getattr(enemy, "cryo_slow_timer", 0.0)
        _draw_one(
            surface,
            cx,
            cy,
            radius,
            id(enemy),
            charge_ratio(remaining),
            shimmer(remaining),
        )
        desenhados += 1
    return desenhados
