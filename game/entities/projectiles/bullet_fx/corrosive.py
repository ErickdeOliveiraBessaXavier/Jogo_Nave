"""Visual do tiro CORROSIVO (upgrade Corrosive Ammo): a bolha e a cauda que serpenteia.

Paleta, sprite memoizado e desenho. A mecânica — a pilha de ácido, o dano por
tique — não está aqui: ela mora nas marcas que o sistema de colisão crava no
inimigo (`systems/shot_marks`) e no `corrosion_stain`, que desenha o ácido no
ALVO. Este módulo cuida só do projétil.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, Tuple

import pygame

from ....core.player_tint import player_shot_color
from . import common, ship_styles

if TYPE_CHECKING:
    from ..bullet import Bullet

# Verde MUSGO, não neon: o verde saturado já é do tiro teleguiado (0,255,100) e
# do halo do Estilete, e um ácido fluorescente competiria com os dois na tela.
# Ácido lê como líquido pesado e opaco — a leitura vem da forma (bolha assimétrica
# com poços escuros), não do brilho.
_CORROSIVE_FILL: Tuple[int, int, int] = (124, 176, 72)
_CORROSIVE_EDGE: Tuple[int, int, int] = (68, 106, 44)
_CORROSIVE_SHINE: Tuple[int, int, int] = (196, 232, 142)
_CORROSIVE_PIT: Tuple[int, int, int] = (54, 82, 36)
# Gotejamento: pingos que se soltam da bolha e escurecem para trás. Sem alpha
# pelo mesmo motivo do rastro do gelo — escurecer lê como desvanecer contra o
# fundo escuro e custa um `draw.circle` em vez de uma Surface por bala (§7).
_CORROSIVE_TRAIL: Tuple[Tuple[int, int, int], ...] = (
    (138, 190, 86),
    (100, 144, 62),
    (66, 96, 44),
)
_CORROSIVE_BULLET_CACHE: Dict[Tuple[int, int, int], pygame.Surface] = {}

# ── Serpenteio do rastro de ácido ───────────────────────────────────────────
# Quantos pingos formam a cauda. Mais que os 3 do gelo: a onda precisa de
# amostras para LER como onda — com três pontos ela vira um zigue-zague.
_CORROSIVE_TRAIL_SEGMENTS: int = 6
# Período da ondulação (s) e defasagem entre pingos vizinhos (rad). A defasagem
# é o que faz a onda VIAJAR pela cauda em vez de todos os pingos balançarem
# juntos — é ela, e não a amplitude, que dá a leitura de serpente.
_CORROSIVE_WAVE_PERIOD: float = 0.42
_CORROSIVE_WAVE_LAG: float = 1.15
# Espaçamento entre pingos, em frações do passo do rastro. Menor que 1 de
# propósito: com os pingos separados por um passo cheio a cauda vira uma fila de
# pontos soltos, e onda em pontos soltos não lê como onda. Apertados, eles quase
# se tocam e a cauda vira uma FITA — que é o que ondula de forma legível.
_CORROSIVE_SEGMENT_SPACING: float = 0.62
# Amplitude do desvio lateral, em frações do passo entre pingos.
_CORROSIVE_WAVE_AMP: float = 0.85
# Borbulhar: cada pingo pulsa de tamanho num ritmo PRÓPRIO, mais rápido que a
# ondulação e defasado por índice. São dois movimentos independentes de
# propósito — juntos leem como líquido instável, sincronizados leem como
# animação em loop.
_CORROSIVE_BUBBLE_PERIOD: float = 0.19
_CORROSIVE_BUBBLE_LAG: float = 2.1
_CORROSIVE_BUBBLE_DEPTH: float = 0.3


def corrosive_trail_segments(
    anim_time: float, segments: int = _CORROSIVE_TRAIL_SEGMENTS
) -> Tuple[Tuple[float, float, float], ...]:
    """Pingos do rastro de ácido: `(casa, desvio lateral, fração de tamanho)`.

    Duas oscilações independentes sobre o eixo do tiro:

    * **serpenteio** — desvio lateral senoidal com defasagem crescente por
      pingo, o que faz a onda percorrer a cauda de trás para frente. A amplitude
      cresce com a distância (perto do projétil o líquido ainda está preso a
      ele; longe, chicoteia solto) — é o mesmo perfil de um rabo de serpente;
    * **borbulhar** — o tamanho de cada pingo pulsa num ritmo próprio, mais
      rápido e defasado, para o ácido parecer fervendo enquanto avança.

    Tudo puramente visual: quem chama só desenha nas coordenadas devolvidas, e
    o `x`/`y`/`vx`/`vy` da bala não entram na conta nem saem alterados.

    Função pura de `anim_time` (que o update alimenta), sem estado por pingo —
    nada para vazar pelo pool e nada que o `draw` precise mutar (§3).
    """
    wave = math.tau * anim_time / _CORROSIVE_WAVE_PERIOD
    bubble = math.tau * anim_time / _CORROSIVE_BUBBLE_PERIOD
    out = []
    for i in range(segments):
        t = i / (segments - 1) if segments > 1 else 0.0
        sway = math.sin(wave - i * _CORROSIVE_WAVE_LAG)
        # Amplitude crescente: 35% colada ao projétil, 100% na ponta da cauda.
        amp = _CORROSIVE_WAVE_AMP * (0.35 + 0.65 * t)
        pulse = 1.0 + _CORROSIVE_BUBBLE_DEPTH * math.sin(bubble - i * _CORROSIVE_BUBBLE_LAG)
        # Afina para trás: a cauda se dissolve em vez de terminar em bloco.
        slot = (i + 1) * _CORROSIVE_SEGMENT_SPACING
        out.append((slot, sway * amp, (1.0 - 0.72 * t) * pulse))
    return tuple(out)


def _get_corrosive_bullet_surface(w: int, h: int, player_index: int) -> pygame.Surface:
    """Bolha de ácido do tamanho do tiro, memoizada.

    A silhueta é o que carrega a fantasia: DUAS elipses sobrepostas e
    descentradas, não uma cápsula — é a assimetria que lê como gota viscosa
    prestes a escorrer, em vez de "bala verde". Por cima vão dois poços escuros
    (o ácido comendo a própria gota) e um brilho úmido fora do centro.

    Tudo derivado de `w`/`h`, então a mesma receita serve do Estilete (2px) ao
    tiro gigante — e o cache satura nos primeiros disparos, como o do gelo.
    """
    key = (w, h, player_index)
    cached = _CORROSIVE_BULLET_CACHE.get(key)
    if cached is not None:
        return cached

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    fill = player_shot_color(_CORROSIVE_FILL, player_index)
    edge = player_shot_color(_CORROSIVE_EDGE, player_index)
    shine = player_shot_color(_CORROSIVE_SHINE, player_index)
    pit = player_shot_color(_CORROSIVE_PIT, player_index)

    if w < 4 or h < 4:
        # Tiro minúsculo: nem elipse nem poço cabem. Vira um pixel de ácido com
        # contorno — sem isto o tiro do Estilete some numa mancha indistinta.
        surf.fill(edge)
        surf.set_at((w // 2, h // 2), fill)
        try:
            surf = surf.convert_alpha()
        except pygame.error:
            pass
        _CORROSIVE_BULLET_CACHE[key] = surf
        return surf

    # Corpo: elipse cheia + lobo menor deslocado no eixo MAIOR. A gota fica
    # "pesada" de um lado, que é o que a diferencia de uma cápsula simétrica.
    pygame.draw.ellipse(surf, fill, (0, 0, w, h))
    if w >= h:  # deitada (side-scroll / leque horizontal)
        lobe = pygame.Rect(int(w * 0.42), int(h * 0.10), int(w * 0.56), int(h * 0.80))
    else:  # em pé (top-down, o caso comum)
        lobe = pygame.Rect(int(w * 0.10), int(h * 0.42), int(w * 0.80), int(h * 0.56))
    if lobe.width >= 2 and lobe.height >= 2:
        pygame.draw.ellipse(surf, fill, lobe)
        pygame.draw.ellipse(surf, edge, lobe, 1)
    pygame.draw.ellipse(surf, edge, (0, 0, w, h), 1)

    # Poços de corrosão: o buraco escuro é o detalhe que diz "isto come coisas".
    # Dois, em quadrantes opostos, para a gota não ficar com cara de olho.
    pit_r = max(1, min(w, h) // 6)
    pygame.draw.circle(surf, pit, (int(w * 0.62), int(h * 0.34)), pit_r)
    if min(w, h) >= 8:
        pygame.draw.circle(surf, pit, (int(w * 0.34), int(h * 0.66)), max(1, pit_r - 1))

    # Brilho úmido: fora do centro, senão vira miolo e a gota lê como esfera.
    pygame.draw.circle(surf, shine, (int(w * 0.33), int(h * 0.30)), max(1, pit_r))

    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _CORROSIVE_BULLET_CACHE[key] = surf
    return surf


def draw(bullet: "Bullet", surface: pygame.Surface) -> None:
    """Bolha de ácido gotejando.

    Fica DEPOIS do teleguiado e do explosivo na cadeia de despacho, e depois
    do gelo, pela mesma razão dos irmãos: aqueles visuais comunicam MECÂNICA
    (o '+' persegue, a granada explode, o cristal gela) e escondê-los custa
    leitura de jogo. Nos combos o ácido continua se anunciando no halo e,
    sobretudo, no próprio INIMIGO (`corrosion_stain`) — que é onde a mecânica
    dele mora.

    A cauda SERPENTEIA: a onda percorre os pingos de trás para frente e a
    amplitude cresce com a distância, como o rabo de uma serpente. Por cima,
    cada pingo borbulha de tamanho num ritmo próprio. Os dois movimentos são
    independentes de propósito — sincronizados, leriam como animação em
    loop; somados, leem como líquido instável (ver `corrosive_trail_segments`).

    Nada disso toca a trajetória: a bala segue reta, e é só o desenho da
    cauda que ondula em volta do eixo dela.
    """
    rect = bullet.rect
    if bullet.size_multiplier > 1.0 and ship_styles.style_for(bullet.ship_id).breathes:
        rect = common.breathing_rect(rect)

    # Pingos primeiro: ficam ATRÁS da bolha, saindo por trás dela.
    speed = math.hypot(bullet.vx, bullet.vy)
    if speed > 1.0:
        step = max(2, min(rect.width, rect.height))
        ux, uy = -bullet.vx / speed, -bullet.vy / speed
        px_, py_ = -uy, ux  # perpendicular: o eixo em que a cauda ondula
        cx, cy = rect.centerx, rect.centery
        base_r = max(1, step // 3)
        last = len(_CORROSIVE_TRAIL) - 1
        segments = corrosive_trail_segments(bullet.anim_time)
        span = float(len(segments))
        for i, (slot, sway, scale) in enumerate(segments):
            # Cor pela POSIÇÃO na cauda: o ácido escurece ao se afastar,
            # independente de quantos pingos a cauda tenha.
            color = _CORROSIVE_TRAIL[min(last, int(i / span * len(_CORROSIVE_TRAIL)))]
            dx = int(cx + ux * step * slot + px_ * sway * step)
            dy = int(cy + uy * step * slot + py_ * sway * step)
            pygame.draw.circle(surface, color, (dx, dy), max(1, int(base_r * scale)))

    surface.blit(
        _get_corrosive_bullet_surface(rect.width, rect.height, bullet.player_index),
        rect.topleft,
    )
