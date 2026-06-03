"""Splitter Tank — colosso modular do bioma CITY.

Variante da linhagem do Cyber Tank com morte **"Fission"**: um juggernaut que
avança devagar e, ao ser destruído, **se parte em unidades menores** (tier
seguinte) que continuam — escalando a decisão de foco de fogo do jogador, em vez
de simplesmente estilhaçar (`tank_meltdown`).

Uma única classe com `tier`: tier 0 (grande) → 3× tier 1 (pequenos); tier 1 não
se parte mais. O split é disparado pelo EntityManager via
`triggers_special_death` (lê posição/tier/agressividade do alvo e empurra os
filhos em `enemies`), no espírito do offspring do City Drone.

Contratos (CLAUDE.md): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
`HitResult`; §11 `aggressiveness`/`health_multiplier` propagados aos filhos.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.assets import BASE_DIR, get_image
from ...core.config import config as Config
from ...entities.explosion import ExplosionType
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .splitter_tank_pixel_map import (
    CORE_NEON,
    CORE_NEON_DIM,
    PIXEL_COLS,
    PIXEL_ROWS,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

MAX_TIER: int = 1
_SPLIT_COUNT: int = 3  # quantos filhos o tier 0 gera

_CELL_BY_TIER: dict[int, int] = {0: 6, 1: 5}

# Sprites pixel-art (32×32) feitos à mão: tier 0 pulsa o núcleo em 6 frames,
# o mini (tier 1) em 2. Escalados por tier ao tamanho do chassi.
_SPRITE_DIR = BASE_DIR / "assets" / "images" / "Sprites_Splitter_Tank"
_FRAMES_BY_TIER: dict[int, int] = {0: 6, 1: 2}
_ANIM_FPS: float = 8.0
_HEALTH_BY_TIER: dict[int, int] = {0: 180, 1: 55}
_POINTS_BY_TIER: dict[int, int] = {0: 380, 1: 110}
_SPEED_BY_TIER: dict[int, float] = {0: 46.0, 1: 130.0}


class SplitterTank(EnemyHitMixin):
    PIXEL_COLS = PIXEL_COLS
    PIXEL_ROWS = PIXEL_ROWS

    VERTICAL_TRACK: float = 26.0  # quão rápido persegue o jogador no eixo lento
    _explosion_size_hit: int = 12

    # Frames já escalados ao chassi do tier, carregados uma vez (§7).
    _frames_by_tier: dict[int, List[pygame.Surface]] = {}

    @classmethod
    def _frames(cls, tier: int) -> List[pygame.Surface]:
        cached = cls._frames_by_tier.get(tier)
        if cached is not None:
            return cached
        cell = _CELL_BY_TIER[tier]
        size = (PIXEL_COLS * cell, PIXEL_ROWS * cell)
        if tier == 0:
            paths = [
                _SPRITE_DIR / f"splitter_tank_sprite_{i:02d}.png"
                for i in range(1, _FRAMES_BY_TIER[0] + 1)
            ]
        else:
            paths = [
                _SPRITE_DIR / "splitter_mini" / f"splitter_tank_mini_sprite_{i:02d}.png"
                for i in range(1, _FRAMES_BY_TIER[1] + 1)
            ]
        frames = [pygame.transform.scale(get_image(p), size) for p in paths]
        cls._frames_by_tier[tier] = frames
        return frames

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        health_multiplier: float = 1.0,
        tier: int = 0,
        vx: float | None = None,
        vy: float | None = None,
    ) -> None:
        self.side_scroll: bool = side_scroll
        self.tier: int = tier
        self.cell: int = _CELL_BY_TIER[tier]
        self.w: int = PIXEL_COLS * self.cell
        self.h: int = PIXEL_ROWS * self.cell

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health_multiplier: float = health_multiplier
        self.health: int = max(1, int(_HEALTH_BY_TIER[tier] * health_multiplier))
        self.max_health: int = self.health
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        # Velocidade: avança no eixo de profundidade (esquerda no side-scroll,
        # baixo no vertical); filhos herdam um espalhamento (vx/vy) explícito.
        base_speed = _SPEED_BY_TIER[tier] * aggressiveness_multiplier
        if vx is None and vy is None:
            if side_scroll:
                self.vx, self.vy = -base_speed, 0.0
            else:
                self.vx, self.vy = 0.0, base_speed
        else:
            self.vx = vx if vx is not None else 0.0
            self.vy = vy if vy is not None else 0.0

        self.pulse: float = random.uniform(0.0, math.tau)
        self.anim_time: float = random.uniform(0.0, 1.0)  # dessincroniza o pulso
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.42

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        if dt <= 0.0:
            return
        self.pulse += dt
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Juggernaut: avança constante; persegue lentamente o jogador no eixo
        # transversal (sobe/desce no side-scroll p/ ameaçar a linha do jogador).
        cx, cy = self._center()
        if self.side_scroll:
            track = max(-self.VERTICAL_TRACK, min(self.VERTICAL_TRACK, player_y - cy))
            self.vy += (track - self.vy) * min(1.0, dt * 2.0)
        else:
            track = max(-self.VERTICAL_TRACK, min(self.VERTICAL_TRACK, player_x - cx))
            self.vx += (track - self.vx) * min(1.0, dt * 2.0)

        self.x += self.vx * dt
        self.y += self.vy * dt

        # Sai de cena quando atravessa pela borda de avanço.
        if self.side_scroll:
            if self.x + self.w < -60.0:
                self.dead = True
        elif self.y - self.h > Config.SCREEN_HEIGHT + 60.0:
            self.dead = True

    # ── Split (consumido pelo EntityManager no death sequence) ─────────────────
    def make_children(self) -> List["SplitterTank"]:
        """Gera os filhos do próximo tier espalhados a partir do centro. Vazio se
        já é o último tier."""
        if self.tier >= MAX_TIER:
            return []
        cx, cy = self._center()
        children: List[SplitterTank] = []
        child_speed = _SPEED_BY_TIER[self.tier + 1] * self.aggressiveness_multiplier
        for i in range(_SPLIT_COUNT):
            # Leque de direções em torno do avanço (esquerda no side-scroll).
            spread = (i - (_SPLIT_COUNT - 1) / 2) * 0.85
            if self.side_scroll:
                vx = -child_speed * math.cos(spread)
                vy = child_speed * math.sin(spread)
            else:
                vx = child_speed * math.sin(spread)
                vy = child_speed * math.cos(spread)
            child = SplitterTank(
                cx, cy,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                side_scroll=self.side_scroll,
                health_multiplier=self.health_multiplier,
                tier=self.tier + 1,
                vx=vx, vy=vy,
            )
            child.x = cx - child.w / 2
            child.y = cy - child.h / 2
            children.append(child)
        return children

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.07
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return _POINTS_BY_TIER[self.tier]

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            splits = self.tier < MAX_TIER
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                # tier 0: explosão pequena (o "split" é o espetáculo, via special
                # death); tier 1: explosão normal de morte.
                explosion_size=0 if splits else 30,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=splits,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Juggernaut pesado: sobrevive ao contato (a nave leva dano pela camada de
        # colisão). Destrua-o com tiros.
        return HitResult(killed=False, explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render ──────────────────────────────────────────────────────────────
    def _blit_glow(
        self, surface: pygame.Surface, cx: int, cy: int, radius: int, color: pal.RGB
    ) -> None:
        glow = city_glow.get_glow(radius, color)
        surface.blit(
            glow, (cx - radius, cy - radius), special_flags=pygame.BLEND_RGBA_ADD
        )

    def draw(self, surface: pygame.Surface) -> None:
        frames = self._frames(self.tier)
        base = frames[int(self.anim_time * _ANIM_FPS) % len(frames)]
        pos = (int(self.x), int(self.y))
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, pos)
        else:
            surface.blit(base, pos)

        # Bloom neon no núcleo: telegrafa o split — pisca mais forte quanto mais
        # ferido ("vai partir"). Ancorado um pouco abaixo do centro do sprite.
        cx, cy = self._center()
        cy += self.cell * 1.2
        hurt = 1.0 - self.health / max(1, self.max_health)
        pulse = 0.5 + 0.5 * math.sin(self.pulse * (5.0 + 6.0 * hurt))
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, 0.4 + 0.6 * pulse)
        # Mais transparente: escurece a cor → contribuição aditiva mais fraca.
        core_col = pal.lerp((0, 0, 0), core_col, 0.5)
        core_r = int(self.cell * (1.2 + 0.6 * pulse + 1.2 * hurt))
        self._blit_glow(surface, int(cx), int(cy), core_r, core_col)
