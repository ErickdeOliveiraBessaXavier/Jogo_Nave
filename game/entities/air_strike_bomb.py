"""Bomba do Air Strike: cai reto sobre um alvo pré-definido e explode em área.

Fluxo: a bomba nasce acima do topo, na coluna do alvo (``x == target_x``), e cai
reto até **cruzar** ``target_y`` — onde explode. O impacto é SEMPRE no alvo (que o
``AirStrikeUpgrade`` já sorteia dentro da área jogável) e o dano é aplicado em
``(x, target_y)`` pelo roteador de colisão, independente da posição visual.

Ponto-chave da mecânica: o gatilho de explosão é o cruzamento ``y >= target_y``,
não uma proximidade por limiar. A versão antiga testava ``abs(y - target_y) < 5``
com passo de queda de ~13px/frame — o passo era maior que o limiar, então em
muitos frames a bomba "pulava" a zona de detecção, nunca explodia e caía para fora
da tela, desperdiçando o projétil. O teste por cruzamento é robusto a qualquer
``dt`` (lag/slow-motion) e determinístico.

Modelado no ``MineExplosion`` (§3/§7): surfaces pré-alocadas e compartilhadas,
sem alocação nem ``random`` por frame; ``draw()`` apenas lê estado e desenha.
"""

from __future__ import annotations

from typing import Callable, Optional

import pygame

from ..core.config import config as Config
from ..core.upgrades_config import (
    AIR_STRIKE_BOMB_DAMAGE,
    AIR_STRIKE_BOMB_FALL_SPEED,
    AIR_STRIKE_BOMB_RADIUS,
    AIR_STRIKE_EXPLOSION_DURATION,
    AIR_STRIKE_SCREEN_MARGIN,
)

# Paleta do meteoro, baked nos sprites compartilhados.
_COLOR_YELLOW = (242, 186, 82)
_COLOR_ORANGE = (242, 105, 56)
_COLOR_RED = (191, 48, 48)

_SPAWN_HEIGHT = 120  # pixels acima do topo onde a bomba nasce
_DAMAGE_ACTIVE_FRAC = 0.8  # fração da duração em que o dano é aplicado
_HEAD_SIZE = 24  # lado do sprite da cabeça (glow)
_TRAIL_W, _TRAIL_H = 14, 50  # dimensões do rastro


class AirStrikeBomb:
    """Uma bomba do bombardeio aéreo: queda reta + explosão em área no alvo."""

    # Sprites compartilhados por todas as bombas (construídos uma vez, sob demanda).
    _head_sprite: Optional[pygame.Surface] = None
    _trail_sprite: Optional[pygame.Surface] = None

    def __init__(
        self,
        target_x: float,
        target_y: float,
        on_explode: Optional[Callable[[], None]] = None,
        on_fall: Optional[Callable[[], None]] = None,
    ) -> None:
        # Clamp de segurança final: mantém o círculo de explosão INTEIRO na tela
        # mesmo que o alvo chegue fora (o upgrade já sorteia dentro; esta é a última
        # barreira, e a bomba é a dona desse invariante). Margem = raio + folga.
        screen = pygame.display.get_surface()
        sw = screen.get_width() if screen else int(Config.SCREEN_WIDTH)
        sh = screen.get_height() if screen else int(Config.SCREEN_HEIGHT)
        m = AIR_STRIKE_SCREEN_MARGIN
        self.target_x = max(m, min(sw - m, target_x))
        self.target_y = max(m, min(sh - m, target_y))

        # Posição: começa acima do topo, na coluna do alvo, e cai reto.
        self.x = self.target_x
        self.y = -float(_SPAWN_HEIGHT)
        self.fall_speed = AIR_STRIKE_BOMB_FALL_SPEED

        self.explosion_radius = AIR_STRIKE_BOMB_RADIUS
        self.damage = AIR_STRIKE_BOMB_DAMAGE
        self.explosion_duration = AIR_STRIKE_EXPLOSION_DURATION

        self.on_explode = on_explode
        self.on_fall = on_fall
        self._fall_sound_played = False

        self.state = "falling"  # "falling" | "exploding" | "done"
        self.dead = False
        self.explosion_timer = 0.0
        self.hit_enemies: set[int] = set()

        self._ensure_sprites()
        # Surface da explosão pré-alocada, reusada por frame (estilo MineExplosion).
        d = int(self.explosion_radius * 2)
        self._explosion_surface = pygame.Surface((d, d), pygame.SRCALPHA)

    # ── Estado consultado pelo roteador de colisão / culling ────────────────────
    @property
    def rect(self) -> pygame.Rect:
        """Bounding box para culling de visibilidade (não é a hitbox de dano)."""
        if self.state == "exploding":
            r = int(self.explosion_radius)
            return pygame.Rect(int(self.x) - r, int(self.target_y) - r, 2 * r, 2 * r)
        # Caindo: cobre a cabeça e o rastro acima dela.
        return pygame.Rect(int(self.x) - 10, int(self.y) - _TRAIL_H - 8, 20, _TRAIL_H + 20)

    @property
    def exploding(self) -> bool:
        return self.state == "exploding"

    @property
    def damage_active(self) -> bool:
        return (
            self.state == "exploding"
            and self.explosion_timer < self.explosion_duration * _DAMAGE_ACTIVE_FRAC
        )

    @property
    def explosion_progress(self) -> float:
        if self.state != "exploding":
            return 0.0
        return min(1.0, self.explosion_timer / self.explosion_duration)

    # ── Ciclo de vida ───────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        if self.state == "falling":
            self.y += self.fall_speed * dt

            if not self._fall_sound_played and self.y > 0.0:
                self._fall_sound_played = True
                if self.on_fall:
                    self.on_fall()

            # Explode ao CRUZAR o alvo (robusto a dt grande — sem tunneling). Trava
            # a posição no alvo para que visual e dano coincidam exatamente.
            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "exploding"
                if self.on_explode:
                    self.on_explode()

        elif self.state == "exploding":
            self.explosion_timer += dt
            if self.explosion_timer >= self.explosion_duration:
                self.state = "done"
                self.dead = True

    # ── Render (§3: só lê estado; §7: sem alocação/random por frame) ────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        if self.state == "falling":
            self._draw_falling(surface)
        elif self.state == "exploding":
            self._draw_explosion(surface)

    def _draw_falling(self, surface: pygame.Surface) -> None:
        trail = self._trail_sprite
        head = self._head_sprite
        assert trail is not None and head is not None
        x, y = int(self.x), int(self.y)
        # Rastro: base logo acima da cabeça, subindo e enfraquecendo.
        surface.blit(
            trail,
            (x - trail.get_width() // 2, y - trail.get_height()),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
        # Cabeça: glow centrado na posição.
        hs = head.get_width() // 2
        surface.blit(
            head, (x - hs, y - hs), special_flags=pygame.BLEND_RGBA_ADD
        )

    def _draw_explosion(self, surface: pygame.Surface) -> None:
        progress = self.explosion_progress
        radius = int(self.explosion_radius * progress)
        if radius < 2:
            return
        r = int(self.explosion_radius)
        alpha = int(220 * (1.0 - progress))
        surf = self._explosion_surface
        surf.fill((0, 0, 0, 0))
        pygame.draw.circle(
            surf, (255, int(200 * (1.0 - progress)), 40, alpha), (r, r), radius
        )
        surface.blit(surf, (int(self.x) - r, int(self.target_y) - r))

    # ── Sprites compartilhados (construídos uma vez) ────────────────────────────
    @classmethod
    def _ensure_sprites(cls) -> None:
        if cls._head_sprite is not None:
            return

        # Cabeça: glow radial vermelho→laranja→amarelo→núcleo quente.
        head = pygame.Surface((_HEAD_SIZE, _HEAD_SIZE), pygame.SRCALPHA)
        c = _HEAD_SIZE // 2
        for radius, color in (
            (c, (*_COLOR_RED, 120)),
            (c - 3, (*_COLOR_ORANGE, 200)),
            (c - 6, (*_COLOR_YELLOW, 255)),
            (3, (255, 255, 210, 255)),
        ):
            if radius > 0:
                pygame.draw.circle(head, color, (c, c), radius)
        cls._head_sprite = head

        # Rastro: streak vertical em gota que some para cima (gradiente baked).
        trail = pygame.Surface((_TRAIL_W, _TRAIL_H), pygame.SRCALPHA)
        for i in range(_TRAIL_H):
            p = i / _TRAIL_H  # 0 no topo (fraco) → 1 na base (forte)
            alpha = int(200 * p * p)
            width = max(1, int(_TRAIL_W * p))
            color = _COLOR_ORANGE if p < 0.7 else _COLOR_YELLOW
            x0 = (_TRAIL_W - width) // 2
            pygame.draw.line(trail, (*color, alpha), (x0, i), (x0 + width, i))
        cls._trail_sprite = trail
