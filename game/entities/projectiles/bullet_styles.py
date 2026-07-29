"""Estilo visual do tiro básico de cada nave.

Era uma cascata de nove `elif self.ship_id == ...` dentro do `draw` da bala,
com o agravante de que a identidade visual de cada nave estava repartida em
**dois lugares distantes**: o corpo do tiro na cascata, e a cor do halo numa
tabela `_SHIP_GLOW_COLORS` cem linhas acima, cujo comentário pedia a
sincronização à mão — *"mudou a cor do tiro lá, mude aqui também, senão o halo
deixa de refletir o próprio tiro"*. Pedido de sincronização manual entre dois
pontos é uma dessincronização com data marcada.

Aqui cada nave é **uma linha do registro** com tudo que a define: como o corpo é
desenhado, de que cor é o halo, e se o corpo respira sob o Giant Shot. Nave nova
= uma entrada; nada muda na bala. É o mesmo movimento que tirou o
`bullet_size` da bala para o `ShipProfile`, aplicado ao que não cabia num campo
de dado — porque aqui não é um número, é código de desenho.

**Por que o estilo não foi para o `ShipProfile`.** O `ship_types` declara no
cabeçalho que é livre de dependências de runtime (sem pygame, sem entities), e
com razão: ele é importado cedo e em teste. Guardar uma função que desenha lá
dentro furaria isso. O perfil fica com os NÚMEROS da nave; o desenho fica aqui,
junto do pygame, e a ponte entre os dois é o `ship_id`.

As funções de desenho recebem a `Bullet` e leem só estado **público** dela
(`vx`, `vy`, `player_index`, `combo_intensity`, `rotation_angle`, `piercing`) —
o caso "estado público e limpo" que o §1 autoriza a extrair, e o mesmo contrato
do `ShipRenderer` com a `Ship`. Nenhuma delas muta a bala (§3), e o `rect` chega
pronto por parâmetro porque quem decide a respiração do Giant Shot é a bala.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, List, NamedTuple, Tuple

import pygame

from ...core import colors
from ...core.player_tint import player_shot_color

if TYPE_CHECKING:
    from .bullet import Bullet

RGB = Tuple[int, int, int]
DrawFn = Callable[["Bullet", pygame.Surface, pygame.Rect], None]
GlowFn = Callable[["Bullet"], RGB]

# NOTA SOBRE OS CACHES DESTE MÓDULO
# Todo cache de surface é chaveado também por `player_index`, porque o P2 desenha
# o mesmo tiro com a matiz desviada (ver `player_shot_color`). Sem a chave, o
# primeiro jogador a desenhar venceria e os dois atirariam igual.


# ── Fantasma ────────────────────────────────────────────────────────────────
# Surfaces memoizadas — o tiro é translúcido, e alpha parcial exige um
# `Surface` SRCALPHA que sairia caro por bala por frame (§7).
_FANTASMA_SURFACE_CACHE: Dict[Tuple[int, int, int], pygame.Surface] = {}


def _get_fantasma_surface(w: int, h: int, player_index: int) -> pygame.Surface:
    key = (w, h, player_index)
    cached = _FANTASMA_SURFACE_CACHE.get(key)
    if cached is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            s,
            player_shot_color((180, 255, 255, 160), player_index),
            s.get_rect(),
            border_radius=2,
        )
        try:
            s = s.convert_alpha()
        except pygame.error:
            pass
        _FANTASMA_SURFACE_CACHE[key] = s
        return s
    return cached


# ── Berserk ─────────────────────────────────────────────────────────────────
# Frames pré-rotacionados por tamanho. Rotacionar a cada frame de cada bala
# seria alocação e transform por projétil por frame — e o Berserk cospe 4 balas
# por disparo. Chave: (w, h, player_index); o tamanho muda com o Giant Shot.
_BERSERK_NUM_FRAMES: int = 24
_BERSERK_FRAMES: Dict[Tuple[int, int, int], List[pygame.Surface]] = {}


def _get_berserk_frames(w: int, h: int, player_index: int) -> List[pygame.Surface]:
    """Frames do Berserk girado em 360°, memoizados por tamanho e jogador."""
    key = (w, h, player_index)
    frames = _BERSERK_FRAMES.get(key)
    if frames is not None:
        return frames

    base = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(
        base, player_shot_color((150, 0, 255), player_index), (0, 0, w, h)
    )
    inner = pygame.Rect(0, 0, w, h).inflate(-4, -4)
    if inner.width > 0 and inner.height > 0:
        pygame.draw.ellipse(
            base, player_shot_color((255, 100, 255), player_index), inner
        )

    step = 360.0 / _BERSERK_NUM_FRAMES
    frames = []
    for i in range(_BERSERK_NUM_FRAMES):
        frame = pygame.transform.rotate(base, -i * step)
        try:
            frame = frame.convert_alpha()
        except pygame.error:
            pass
        frames.append(frame)
    _BERSERK_FRAMES[key] = frames
    return frames


# ── Reverberador ────────────────────────────────────────────────────────────
# O tiro ESQUENTA com o combo: quanto maior o bônus de dano acumulado, mais
# clara a cor e mais um anel entra. É o único estilo cuja cor não é constante.
_REVERB_COLD = (140, 30, 180)
_REVERB_MID = (255, 0, 255)
_REVERB_HOT = (255, 190, 255)
_REVERB_RING_COLD = (180, 70, 210)
_REVERB_RING_HOT = (255, 225, 255)


def _lerp_color(a: RGB, b: RGB, t: float) -> RGB:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def reverberador_colors(k: float) -> Tuple[RGB, RGB]:
    """Cores (corpo, anel) do tiro do Reverberador para o combo `k` (0..1)."""
    if k < 0.5:
        body = _lerp_color(_REVERB_COLD, _REVERB_MID, k / 0.5)
    else:
        body = _lerp_color(_REVERB_MID, _REVERB_HOT, (k - 0.5) / 0.5)
    return body, _lerp_color(_REVERB_RING_COLD, _REVERB_RING_HOT, k)


# ── Desenho do corpo, por nave ──────────────────────────────────────────────


def _draw_magneto(bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Orbe ovalado roxo/azul."""
    tint = bullet.player_index
    pygame.draw.ellipse(surface, player_shot_color((100, 100, 255), tint), rect)
    pygame.draw.ellipse(
        surface, player_shot_color((200, 200, 255), tint), rect.inflate(-4, -4)
    )


def _draw_estilete(
    bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect
) -> None:
    """Laser fino verde com brilho central."""
    tint = bullet.player_index
    pygame.draw.rect(surface, player_shot_color((0, 255, 100), tint), rect)
    pygame.draw.line(
        surface,
        player_shot_color((200, 255, 200), tint),
        rect.topleft,
        rect.bottomleft,
        1,
    )


def _draw_ariete(bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Bloco laranja intenso com miolo mais claro."""
    tint = bullet.player_index
    pygame.draw.rect(surface, player_shot_color((255, 80, 0), tint), rect)
    pygame.draw.rect(
        surface, player_shot_color((255, 150, 50), tint), rect.inflate(-2, -2)
    )


def _draw_cofre(bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Amarelo claro arredondado."""
    pygame.draw.rect(
        surface,
        player_shot_color((255, 220, 100), bullet.player_index),
        rect,
        border_radius=3,
    )


def _draw_fantasma(
    bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect
) -> None:
    """Ciano pálido translúcido (surface pré-renderizada)."""
    surface.blit(
        _get_fantasma_surface(rect.width, rect.height, bullet.player_index),
        rect.topleft,
    )


def _draw_engenheiro(
    bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect
) -> None:
    """Azul elétrico com núcleo branco."""
    center = rect.center
    pygame.draw.circle(
        surface,
        player_shot_color((0, 150, 255), bullet.player_index),
        center,
        rect.width // 2,
    )
    pygame.draw.circle(surface, (255, 255, 255), center, rect.width // 4)


def _draw_cacador(bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Seta prateada apontando para onde o tiro viaja."""
    if bullet.vx > 0:
        points = [rect.topleft, (rect.right, rect.centery), rect.bottomleft]
    elif bullet.vx < 0:
        points = [rect.topright, (rect.left, rect.centery), rect.bottomright]
    elif bullet.vy < 0:
        points = [rect.bottomleft, (rect.centerx, rect.top), rect.bottomright]
    else:
        points = [rect.topleft, (rect.centerx, rect.bottom), rect.topright]
    pygame.draw.polygon(
        surface, player_shot_color((192, 192, 220), bullet.player_index), points
    )


def _draw_reverberador(
    bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect
) -> None:
    """Magenta com anéis que esquenta com o combo."""
    tint = bullet.player_index
    k = bullet.combo_intensity
    body_color, ring_color = reverberador_colors(k)
    pygame.draw.rect(surface, player_shot_color(body_color, tint), rect)
    # Núcleo branco a partir da metade do combo: o tiro fica incandescente.
    if k >= 0.5 and rect.width > 2 and rect.height > 2:
        core = rect.inflate(-max(2, rect.width // 3), -max(2, rect.height // 3))
        pygame.draw.rect(surface, player_shot_color((255, 255, 255), tint), core)
    tinted_ring = player_shot_color(ring_color, tint)
    for i in range(1, 4 if k >= 0.6 else 3):
        pygame.draw.rect(surface, tinted_ring, rect.inflate(i * 4, i * 4), 1)


def _draw_berserk(bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Rosa dos Ventos girando no próprio eixo (frames pré-rotacionados)."""
    frames = _get_berserk_frames(rect.width, rect.height, bullet.player_index)
    idx = (
        int(bullet.rotation_angle * _BERSERK_NUM_FRAMES / 360.0) % _BERSERK_NUM_FRAMES
    )
    frame = frames[idx]
    # A rotação muda o tamanho da surface — centralizar na bounding box do tiro,
    # senão ele "orbita" o próprio hitbox ao girar.
    surface.blit(frame, frame.get_rect(center=rect.center))


def _draw_default(bullet: "Bullet", surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Retângulo chapado: a Padrão e qualquer id sem estilo próprio."""
    pygame.draw.rect(
        surface, player_shot_color(_default_glow(bullet), bullet.player_index), rect
    )


# ── Cor do halo ─────────────────────────────────────────────────────────────


def _fixed_glow(color: RGB) -> GlowFn:
    """Halo de cor constante — o caso da maioria das naves."""
    return lambda _bullet: color


def _default_glow(bullet: "Bullet") -> RGB:
    """Sem estilo próprio, a cor vem do MODIFICADOR: roxo perfurante ou amarelo."""
    return colors.PURPLE if bullet.piercing else colors.YELLOW


def _reverberador_glow(bullet: "Bullet") -> RGB:
    # A rampa do combo é contínua e cada cor vira uma entrada no cache de glow —
    # quantizar em 5 passos mantém o cache pequeno sem que a transição fique
    # perceptivelmente escalonada.
    k = round(bullet.combo_intensity * 4) / 4.0
    return reverberador_colors(k)[0]


class ShotStyle(NamedTuple):
    """Identidade visual completa do tiro básico de uma nave.

    Os três campos juntos são o ponto do módulo: corpo e halo saem da MESMA
    linha, então não existe mais o par de tabelas para manter em sincronia à mão.
    """

    draw: DrawFn
    # Cor-base do halo. Função (e não `RGB`) porque a do Reverberador depende do
    # combo; as constantes passam por `_fixed_glow`.
    glow: GlowFn
    # O corpo pulsa sob o Giant Shot? O Berserk fica de fora: ele já gira no
    # próprio eixo, e o tamanho variável estouraria o cache de frames.
    breathes: bool = True
    # Giro do projétil no próprio eixo, em graus/s (0 = não gira). Mora aqui,
    # e não na bala, porque só faz sentido para quem tem frames pré-rotacionados
    # para consumir o ângulo — é o desenho que pede o giro, não a física. O
    # `update` da bala lê daqui; o `draw` só usa o ângulo acumulado (§3).
    spin_speed: float = 0.0


DEFAULT_STYLE = ShotStyle(_draw_default, _default_glow)

# Fonte única do visual do tiro por nave. Nave nova entra AQUI — e em lugar
# nenhum mais. Id ausente cai no `DEFAULT_STYLE`, o que é uma escolha legítima
# (o tiro da Padrão), diferente do que acontecia com o TAMANHO, onde o fallback
# silencioso escondia três naves esquecidas.
SHOT_STYLES: Dict[str, ShotStyle] = {
    "magneto": ShotStyle(_draw_magneto, _fixed_glow((150, 150, 255))),
    "estilete": ShotStyle(_draw_estilete, _fixed_glow((0, 255, 100))),
    "ariete": ShotStyle(_draw_ariete, _fixed_glow((255, 110, 20))),
    "cofre": ShotStyle(_draw_cofre, _fixed_glow((255, 220, 100))),
    "fantasma": ShotStyle(_draw_fantasma, _fixed_glow((180, 255, 255))),
    "engenheiro": ShotStyle(_draw_engenheiro, _fixed_glow((0, 150, 255))),
    "cacador": ShotStyle(_draw_cacador, _fixed_glow((192, 192, 220))),
    "reverberador": ShotStyle(_draw_reverberador, _reverberador_glow),
    # Não é nave: é o tiro do upgrade Berserk, que dispara com id próprio para
    # ter forma e visual iguais para o elenco inteiro. Gira mais rápido que o
    # teleguiado (360°/s) porque a bala dele vive pouco: num giro por segundo,
    # morreria antes de completar meia volta.
    "berserk": ShotStyle(
        _draw_berserk,
        _fixed_glow((200, 60, 255)),
        breathes=False,
        spin_speed=540.0,
    ),
}


def style_for(ship_id: str) -> ShotStyle:
    """Estilo da nave, ou o padrão para id desconhecido."""
    return SHOT_STYLES.get(ship_id, DEFAULT_STYLE)
