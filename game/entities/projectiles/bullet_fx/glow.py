"""Halo pulsante ('respiração') de todo projétil do jogador.

É o único efeito que vale para TODOS os tiros, então fica num módulo próprio em
vez de dentro de um modificador. A cor sai de uma cadeia de prioridade por
fantasia (gelo > ácido > explosivo > cadeia > teleguiado > gigante > comum), e a
do tiro comum vem do estilo da nave — ver `ship_styles`.

Importa `_CRYO_EDGE` do módulo do gelo em vez de repetir o valor: a cor do halo
tem de ser a MESMA aresta do cristal, e duplicá-la recriaria exatamente o par de
tabelas dessincronizadas que o registro de estilos veio resolver.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, Tuple

import pygame

from ....core.player_tint import player_shot_color
from ....core.upgrades_config import CORROSIVE_COLOR
from ....core.visual_quality import visual_quality as vq
from . import ship_styles
from .cryo import _CRYO_EDGE

if TYPE_CHECKING:
    from ..bullet import Bullet


# Halo pulsante ('respiração') dos tiros de power-up. Sprite radial cacheada por
# (raio, cor, passo) — o `passo` quantiza a fase do pulso em `_GLOW_STEPS`
# níveis, então o brilho "respira" trocando de sprite cacheada em vez de alocar
# por frame. Um blit por bala. Chave inclui a cor (já com a matiz do jogador).
_GLOW_STEPS: int = 5
# Teto de cada eixo do halo (px), para o Giant Shot crescer sem estourar a tela
# nem inchar o cache. Piso por eixo evita glow fino demais no laser estreito.
_GLOW_MAX_PX: int = 140
_GLOW_MIN_COMMON: int = 12
_GLOW_MIN_POWER: int = 8
_GLOW_CACHE: Dict[Tuple[int, int, Tuple[int, int, int], int], pygame.Surface] = {}

# Halo do tiro COMUM: aditivo, com o RGB pré-multiplicado pela intensidade.
# Alpha-blend (o caminho dos power-ups) precisa de alpha alto para aparecer, e
# nessa dose o halo vira uma mancha chapada em volta de um tiro pequeno; somando
# ao fundo, o brilho aparece sobre o preto do espaço sem borrar o projétil.
# `_COMMON_GLOW_PEAK` = fração do brilho da cor somada no centro, no pico do pulso.
# Doses baixas de propósito: com dezenas de tiros na tela os halos SOMAM entre si,
# e o que era brilho individual vira uma mancha só, lavando inimigos e projéteis.
_COMMON_GLOW_MIN: float = 0.22
_COMMON_GLOW_PEAK: float = 0.45
# Expoente da queda radial. Acima de 2 o brilho se concentra num núcleo apertado
# em vez de se espalhar — é o que mantém o tiro "aceso" sem borrar a vizinhança.
_COMMON_GLOW_FALLOFF: float = 3.0
_COMMON_GLOW_CACHE: Dict[
    Tuple[int, int, Tuple[int, int, int], int], pygame.Surface
] = {}


def _get_common_shot_glow(
    w: int, h: int, color: Tuple[int, int, int], step: int
) -> pygame.Surface:
    """Halo ELÍPTICO aditivo do tiro comum, memoizado por (w, h, cor, passo).

    A elipse acompanha as proporções do projétil — `w`/`h` já vêm trocados
    conforme a orientação (side-scroll = largo, top-down = alto) e escalados pelo
    tamanho-base da nave e pelo Giant Shot —, então o glow é sempre uma extensão
    natural do tiro, não um círculo genérico. Degradê quadrático do centro à borda,
    com a cor pré-multiplicada pela intensidade para blit com ``BLEND_RGB_ADD``.
    """
    key = (w, h, color, step)
    cached = _COMMON_GLOW_CACHE.get(key)
    if cached is not None:
        return cached

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    peak = _COMMON_GLOW_MIN + (step / _GLOW_STEPS) * (
        _COMMON_GLOW_PEAK - _COMMON_GLOW_MIN
    )
    r_col, g_col, b_col = color
    cx, cy = w / 2.0, h / 2.0
    # Uma "casca" elíptica por ~pixel do maior semieixo — do exterior (apagado) ao
    # centro (aceso), cada elipse menor sobrescrevendo, formando o degradê radial.
    shells = max(2, max(w, h) // 2)
    for i in range(shells, 0, -1):
        t = i / shells
        f = peak * (1.0 - t) ** _COMMON_GLOW_FALLOFF
        ew = max(1, int(w * t))
        eh = max(1, int(h * t))
        pygame.draw.ellipse(
            surf,
            (int(r_col * f), int(g_col * f), int(b_col * f), 255),
            pygame.Rect(int(cx - ew / 2), int(cy - eh / 2), ew, eh),
        )
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _COMMON_GLOW_CACHE[key] = surf
    return surf


def _get_power_glow(
    w: int, h: int, color: Tuple[int, int, int], step: int
) -> pygame.Surface:
    """Halo ELÍPTICO suave da cor pedida, com brilho central no nível `step`.

    Acompanha as proporções do projétil (`w`/`h`, já orientados e escalados).
    Construído da casca externa (alpha ~0) ao centro (alpha `peak`), com queda
    quadrática — degradê macio. Memoizado por (w, h, cor, passo).
    """
    key = (w, h, color, step)
    cached = _GLOW_CACHE.get(key)
    if cached is not None:
        return cached

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    peak = 30 + int((step / _GLOW_STEPS) * 130)  # alpha central pulsa ~30..160
    r_col, g_col, b_col = color
    cx, cy = w / 2.0, h / 2.0
    shells = max(2, max(w, h) // 2)
    for i in range(shells, 0, -1):
        t = i / shells
        a = int(peak * (1.0 - t) * (1.0 - t))
        if a > 0:
            ew = max(1, int(w * t))
            eh = max(1, int(h * t))
            pygame.draw.ellipse(
                surf,
                (r_col, g_col, b_col, a),
                pygame.Rect(int(cx - ew / 2), int(cy - eh / 2), ew, eh),
            )
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _GLOW_CACHE[key] = surf
    return surf


# Rampa de cor do tiro do Reverberador: violeta apagado (sem combo) -> magenta
# pleno (metade do cap) -> rosa quase branco (cap). O tiro esquenta junto com o
# bônus de dano, então dá para ler a força do combo sem olhar o HUD.

def draw_pulse(bullet: "Bullet", surface: pygame.Surface) -> None:
    """Halo pulsante ('respiração') dos tiros de power-up.

    Dá vida às habilidades — sobretudo ao Giant Shot, que sem isto é só um
    tiro grande e estático. Cor por fantasia (explosivo laranja > chain
    azul-elétrico > teleguiado verde > gigante âmbar) e raio proporcional ao
    tiro (o gigante respira maior). Um blit de sprite cacheada por bala;
    gateado pela Qualidade Visual — some no Baixo, encolhe no Médio.

    O tiro COMUM também ganha halo, na cor do próprio projétil da nave
    (o `glow` do estilo da nave), mas por soma ao fundo (`BLEND_RGB_ADD`) em
    vez de alpha-blend: o tiro é pequeno e um halo translúcido nesse tamanho
    desaparece contra o fundo escuro.
    """
    if not vq.glow_enabled:
        return
    is_giant = bullet.size_multiplier > 1.0
    # Chain Lightning vive na nave (has_chain_shot), não na bala: lê o dono,
    # como o próprio sistema de colisão faz para encadear.
    is_chain = bool(getattr(bullet.owner_ship, "has_chain_shot", False))

    # Cor + ritmo por fantasia. Prioridade quando combinados: o efeito mais
    # dramático manda na cor do halo.
    is_common = not (
        bullet.explosive
        or is_chain
        or bullet.homing
        or is_giant
        or bullet.cryo
        or bullet.corrosive
    )
    radius_factor = 1.4
    if bullet.cryo:
        # Gelo tem prioridade sobre TODOS aqui, ao contrário da cadeia de
        # despacho do corpo. É de propósito: quando o Cryo se combina com
        # teleguiado ou explosivo, o corpo do tiro fica com o visual daquele
        # (que comunica mecânica) e o halo é o que mantém o gelo visível.
        base_color = _CRYO_EDGE
        speed = 0.004  # respiração lenta: gelo não crepita
    elif bullet.corrosive:
        # Logo abaixo do gelo: quando os dois estão ativos o corpo do tiro
        # já é o cristal, e o halo azul é o que mantém o Cryo legível. O
        # ácido não fica sem aviso por isso — ele se anuncia no INIMIGO
        # (`corrosion_stain`), que é onde a mecânica dele mora de fato.
        base_color = CORROSIVE_COLOR
        speed = 0.012  # borbulhar nervoso, mais rápido que o gelo
    elif bullet.explosive:
        base_color = (255, 120, 0)  # laranja de pavio
        speed = 0.009
    elif is_chain:
        base_color = (70, 170, 255)  # azul-elétrico do raio
        speed = 0.014  # tremular rápido, nervoso
    elif bullet.homing:
        base_color = (0, 255, 100)  # verde do '+'
        # Em espera (sem alvo) pulsa mais rápido — casa com o giro idle.
        speed = 0.011 if bullet.target is None else 0.006
    elif is_giant:
        # Giant Shot só ESCALA o tiro da nave — o corpo continua na cor dela,
        # então o halo acompanha (antes era âmbar fixo, destoando: um tiro
        # verde do Estilete ficava com glow amarelo). A identidade do gigante
        # vem do tamanho + respiração, não de uma cor genérica.
        base_color = ship_styles.style_for(bullet.ship_id).glow(bullet)
        speed = 0.005
    else:
        base_color = ship_styles.style_for(bullet.ship_id).glow(bullet)
        speed = 0.007
        # Colado ao tiro: o suficiente para o halo aparecer em volta do
        # corpo, sem virar uma bola que se funde com a do tiro vizinho.
        radius_factor = 1.4
    color = player_shot_color(base_color, bullet.player_index)

    pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * speed)  # 0..1
    step = int(round(pulse * _GLOW_STEPS))

    # Halo ELÍPTICO derivado do próprio tiro: cada eixo escala com o `w`/`h`
    # atual da bala — que já embute a orientação (side/top-down), o tamanho-base
    # da nave e o Giant Shot. `×2` porque o fator é semieixo (raio), a superfície
    # é o diâmetro. Piso por eixo evita glow fino demais no laser estreito; teto
    # deixa o gigante crescer sem estourar. Quantiza em par p/ limitar o cache.
    min_px = _GLOW_MIN_COMMON if is_common else _GLOW_MIN_POWER
    axis = radius_factor * 2.0 * vq.glow_scale
    glow_w = max(min_px, min(int(bullet.w * axis), _GLOW_MAX_PX))
    glow_h = max(min_px, min(int(bullet.h * axis), _GLOW_MAX_PX))
    glow_w -= glow_w % 2
    glow_h -= glow_h % 2

    cx = bullet.x + bullet.w / 2
    cy = bullet.y + bullet.h / 2
    pos = (int(cx - glow_w / 2), int(cy - glow_h / 2))
    if is_common:
        surface.blit(
            _get_common_shot_glow(glow_w, glow_h, color, step),
            pos,
            special_flags=pygame.BLEND_RGB_ADD,
        )
    else:
        surface.blit(_get_power_glow(glow_w, glow_h, color, step), pos)
