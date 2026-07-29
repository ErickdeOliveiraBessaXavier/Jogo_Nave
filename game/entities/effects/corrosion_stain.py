"""Bolhas de ácido do alvo corroído (upgrade Corrosive Ammo).

Mesma arquitetura dos cristais do Cryo (`cryo_crystals`), e pelo mesmo motivo:
o efeito **não é entidade**. Ele é função pura do estado que JÁ vive no inimigo
(`corrosive_stacks`, `corrosive_timer`) mais a geometria dele, desenhada direto
no passe de draw. Assim não existe a pergunta "o que acontece com o efeito
quando o alvo morre no meio dele?" — o ácido some junto porque nunca existiu
separado, e nada precisa segurar referência a inimigo nenhum.

O que ele comunica é a **pilha**, que é o upgrade inteiro: são
`CORROSIVE_BUBBLES_PER_STACK` bolhas por carga, então 1 carga é um respingo e 3
é um alvo fervendo. Sem isso o jogador não teria como saber se vale insistir no
mesmo inimigo — que é a única decisão que o Corrosive pede dele.

Nada aqui aloca por frame nem muta estado (§3, §7): as posições saem do `id()`
do alvo (estável, sem campo novo para vazar pelo pool) e o desenho vai direto na
tela, sem buffer. As bolhas SOBEM em ciclo curto derivado do `corrosive_timer`,
que já anda no update — sem relógio próprio no draw.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import pygame

from ...core.upgrades_config import (
    CORROSIVE_BUBBLES_PER_STACK,
    CORROSIVE_COLOR,
    CORROSIVE_COLOR_DARK,
    CORROSIVE_MAX_STACKS,
)


def is_corroded(enemy: Any) -> bool:
    """O alvo está com ácido ativo (pelo menos uma carga e duração correndo)?"""
    return (
        int(getattr(enemy, "corrosive_stacks", 0)) > 0
        and getattr(enemy, "corrosive_timer", 0.0) > 0.0
    )


def bubble_count(stacks: int) -> int:
    """Bolhas para esta pilha. É a leitura de "quanto ácido" na tela."""
    return max(0, min(stacks, CORROSIVE_MAX_STACKS)) * CORROSIVE_BUBBLES_PER_STACK


def _draw_one(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    radius: float,
    seed: int,
    stacks: int,
    clock: float,
) -> None:
    """Desenha as bolhas de UM alvo."""
    count = bubble_count(stacks)
    if count <= 0:
        return

    # Raio da bolha proporcional ao alvo, com piso e teto em pixels: num inimigo
    # pequeno uma bolha de 1px some, e num boss de 120px de raio a mesma fração
    # viraria uma poça cobrindo o corpo (o erro que os cristais do Cryo já
    # tinham cometido antes dos tetos).
    r = max(2, min(5, int(radius * 0.16)))

    for i in range(count):
        # Todas as variações do MESMO seed por índice, com embaralhamento
        # multiplicativo: as bolhas de um alvo são estáveis frame a frame e dois
        # inimigos vizinhos não borbulham igual. Deslocar bits por índice zerava
        # o `id()` na cauda quando a contagem cresce (lição dos cristais).
        h = ((seed >> 4) * (i * 2654435761 + 1)) & 0x3FF
        angle = (h & 0xFF) / 255.0 * math.tau
        # Sobem: a fase é o relógio do próprio debuff mais um deslocamento por
        # bolha, então cada uma está num ponto diferente da subida.
        phase = (clock * 1.6 + ((h >> 8) & 0x3) * 0.25 + i * 0.17) % 1.0
        # Nasce colada ao corpo e sobe até um pouco além da borda.
        dist = radius * (0.55 + 0.65 * phase)
        bx = int(cx + math.cos(angle) * dist)
        by = int(cy + math.sin(angle) * dist - radius * 0.35 * phase)
        # Encolhe ao subir: bolha que some por tamanho não precisa de alpha —
        # alpha parcial obrigaria a um Surface SRCALPHA por alvo por frame (§7).
        size = max(1, int(r * (1.0 - 0.55 * phase)))
        pygame.draw.circle(surface, CORROSIVE_COLOR_DARK, (bx, by), size)
        if size > 1:
            pygame.draw.circle(surface, CORROSIVE_COLOR, (bx, by), size - 1)


def draw_corroded(surface: pygame.Surface, enemies: Iterable[Any]) -> int:
    """Desenha o ácido de todos os alvos corroídos. Devolve quantos foram.

    A geometria vem de `collision_circle()`, nunca de `w`/`h`: nem todo inimigo
    tem esses campos, e em alguns (`MountainGeode`) `x`/`y` é o CENTRO e não o
    canto — as duas suposições que já derrubaram o jogo quando a Implosão as fez.
    """
    desenhados = 0
    for enemy in enemies:
        if getattr(enemy, "dead", False) or not is_corroded(enemy):
            continue

        circle = getattr(enemy, "collision_circle", None)
        if circle is None:
            continue
        cx, cy, radius = circle()
        if radius <= 1.0:
            continue

        _draw_one(
            surface,
            cx,
            cy,
            radius,
            id(enemy),
            int(getattr(enemy, "corrosive_stacks", 0)),
            getattr(enemy, "corrosive_timer", 0.0),
        )
        desenhados += 1
    return desenhados
