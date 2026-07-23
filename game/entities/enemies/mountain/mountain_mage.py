from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Final

import pygame
from .._shared.enemy_hit_mixin import EnemyHitMixin

from ....core import colors
from ....core.config import config as Config

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _ease_out_cubic(value: float) -> float:
    v = _clamp(value, 0.0, 1.0)
    return 1.0 - (1.0 - v) ** 3


def _cfg(attr: str, default: float) -> float:
    """Lê atributo de Config com fallback seguro."""
    return getattr(Config, attr, default)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_SpikePolygon = list[tuple[int, int]]
_SpikePolygons = list[_SpikePolygon]

_STONE_COLORS: Final[tuple[tuple[int, int, int], ...]] = (
    (76, 59, 99),  # rocha roxa escura do parallax
    (106, 76, 125),  # pedra violeta média
    (158, 92, 127),  # rosa púrpura suave
    (224, 126, 116),  # destaque quente de montanha
)

_FRAGMENT_GRAVITY: Final[float] = 520.0
_FRAGMENT_COUNT: Final[int] = 18


class _StalagState(Enum):
    RISING = auto()
    ACTIVE = auto()
    SHATTERING = auto()


class _MageState(Enum):
    APPEARING = auto()
    IDLE = auto()
    TELEGRAPH = auto()
    COOLDOWN = auto()


# ---------------------------------------------------------------------------
# StalagmiteFragment
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _StalagmiteFragment:
    x: float
    y: float
    vx: float
    vy: float
    angle: float
    spin: float
    life: float
    max_life: float
    size: float
    color: tuple[int, int, int]


# ---------------------------------------------------------------------------
# MountainStalagmite
# ---------------------------------------------------------------------------


class MountainStalagmite:
    # Estrutura fixa no chão — ``y`` é derivado de ``ground_y - _current_height``,
    # uma property sem setter. Sinaliza ao black_hole.process_all_enemies para
    # ignorar (qualquer ``enemy.y += ...`` causaria AttributeError).
    pullable_by_black_hole: bool = False

    """Pilar de pedra invocado pelo MountainMage, estilo low-poly terroso."""

    # Combat
    MAX_HEALTH: Final[int] = 20

    # Geometry
    BASE_WIDTH: Final = 48
    MIN_HEIGHT: Final = 62

    # Timing (seconds)
    RISE_TIME: Final = 0.32
    LINGER_TIME: Final = 3.0
    SHATTER_TIME: Final = 1.05

    FRAGMENT_LIFE_MIN: Final = 0.62
    FRAGMENT_LIFE_MAX: Final = 1.18

    # Secondary spike delays & ratios
    SECONDARY_DELAY_LEFT: Final = 0.0
    SECONDARY_DELAY_RIGHT: Final = 0.2
    MAIN_DELAY: Final = 0.3
    SECONDARY_RISE_TIME: Final = 0.28
    SECONDARY_MAX_RATIO: Final = 0.48

    # Cached empty collision result
    _EMPTY_HITBOXES: Final[tuple[pygame.Rect, ...]] = ()

    def __init__(self, x: float, ground_y: float, target_y: float) -> None:
        self.x: float = float(x)
        self.ground_y: float = float(ground_y)
        self.target_y: float = float(target_y)

        self.w: int = self.BASE_WIDTH
        self.health: int = self.MAX_HEALTH
        self.dead: bool = False
        self.active: bool = True

        self._state: _StalagState = _StalagState.RISING
        self._rise_timer: float = 0.0
        self._linger_timer: float = 0.0
        self._hit_flash: float = 0.0
        self._pulse_timer: float = random.uniform(0.0, math.tau)
        self._shape_phase: float = random.uniform(0.0, math.tau)
        self._shatter_timer: float = 0.0
        self._fragments: list[_StalagmiteFragment] = []
        self._current_height: float = 1.0

        self._secondary_left_timer: float = -self.SECONDARY_DELAY_LEFT
        self._secondary_right_timer: float = -self.SECONDARY_DELAY_RIGHT
        self._main_delay_timer: float = -self.MAIN_DELAY
        self._secondary_left_height: float = 0.0
        self._secondary_right_height: float = 0.0

        max_height = max(self.MIN_HEIGHT, self.ground_y - 6.0)
        desired_height = self.ground_y - self.target_y + 8.0
        self._target_height: float = _clamp(desired_height, self.MIN_HEIGHT, max_height)

        self._secondary_left_target: int = max(
            20, int(self._target_height * self.SECONDARY_MAX_RATIO)
        )
        self._secondary_right_target: int = max(
            20, int(self._target_height * self.SECONDARY_MAX_RATIO * 0.82)
        )

        self._collision_mask: pygame.mask.Mask | None = None
        self._collision_mask_offset: tuple[int, int] = (0, 0)
        self._collision_bounds_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._update_collision_regions()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        if (
            self._collision_bounds_rect.width <= 0
            or self._collision_bounds_rect.height <= 0
        ):
            return pygame.Rect(int(self.x), int(self.ground_y), 0, 0)
        return self._collision_bounds_rect

    @property
    def y(self) -> float:
        return self.ground_y - self._current_height

    @property
    def h(self) -> float:
        return self._current_height

    @property
    def causes_damage(self) -> bool:
        return not self.dead and self._state in (
            _StalagState.RISING,
            _StalagState.ACTIVE,
        )

    def collision_circle(self) -> tuple[float, float, float]:
        """Geometria circular para chain_shot/AoE — fallback via rect."""
        r = self.rect
        return float(r.centerx), float(r.centery), float(max(r.width, r.height) / 2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_points_value(self) -> int:
        return 120

    def get_ship_contact_hitboxes(self) -> tuple[pygame.Rect, ...]:
        if (
            self.dead
            or self._state is _StalagState.SHATTERING
            or self._collision_bounds_rect.width <= 0
        ):
            return self._EMPTY_HITBOXES
        return (self._collision_bounds_rect,)

    def get_collision_mask_data(
        self,
    ) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        if (
            self.dead
            or self._state is _StalagState.SHATTERING
            or self._collision_mask is None
        ):
            return None
        return self._collision_mask, self._collision_mask_offset

    def take_damage(self, amount: int = 1) -> None:
        if self.dead or self._state is _StalagState.SHATTERING:
            return
        self.health -= amount
        self._hit_flash = 0.12
        if self.health <= 0:
            self.health = 0
            self._begin_shattering()

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        # Já estilhaçando/morto: absorve sem feedback nem crédito de kill (o
        # estado SHATTERING faz take_damage retornar cedo, então o killed só
        # pode disparar no hit de transição — evita double-count no score).
        if self.dead or self._state is _StalagState.SHATTERING:
            return HitResult()

        self.take_damage(damage)
        shattered = self._state is _StalagState.SHATTERING
        return HitResult(
            killed=shattered,
            points=self.get_points_value() if shattered else 0,
            # Sem explosão no kill: a animação de fragmentos já cobre o visual.
            explosion_size=0 if shattered else 8,
            sound=hit_sounds.EXPLOSION_ASTEROID if shattered else hit_sounds.BOSS_DAMAGE,
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        # Triggera shatter via dano massivo.
        self.take_damage(amount=999)
        return HitResult(killed=False, sound=hit_sounds.EXPLOSION_ASTEROID)

    def should_remove(self) -> bool:
        # Permite que a animação de fragmentos termine antes da remoção.
        return self.dead and not self._fragments

    def update(self, dt: float) -> None:
        if self.dead and not self._fragments:
            return

        if self.dead:
            self._update_fragments(dt)
            return

        self._pulse_timer += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)

        self._update_secondary_timers(dt)

        if self._state is _StalagState.RISING:
            self._update_rising(dt)
        elif self._state is _StalagState.ACTIVE:
            self._update_active(dt)
        elif self._state is _StalagState.SHATTERING:
            self._update_fragments(dt)
            if self._shatter_timer >= self.SHATTER_TIME and not self._fragments:
                self.dead = True

        self._update_collision_regions()

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead and not self._fragments:
            return

        cx = int(self.x)
        base_y = int(self.ground_y)
        height = max(8, int(self._current_height))

        if self._state is _StalagState.SHATTERING or (self.dead and self._fragments):
            self._draw_fragments(surface)
            return

        c_center, c_left, c_right, c_edge = self._resolve_colors()

        screen_w = _cfg("SCREEN_WIDTH", 1280)
        main_hw = min(int(self.w * 1.6), int(screen_w * 0.11))
        left_hw = max(8, int(main_hw * 0.70))
        right_hw = max(8, int(main_hw * 0.58))
        left_h = int(self._secondary_left_height)
        right_h = int(self._secondary_right_height)

        if left_h >= 4:
            self._draw_flat_spike(
                surface,
                cx=cx - int(main_hw * 0.95),
                base_y=base_y,
                height=max(4, left_h),
                half_w=left_hw,
                phase_seed=self._shape_phase + 1.2,
                color=c_left,
                edge=c_edge,
                forced_lean_dir=-1,
            )

        if self._main_delay_timer >= 0.0:
            self._draw_flat_spike(
                surface,
                cx=cx,
                base_y=base_y,
                height=height,
                half_w=main_hw,
                phase_seed=self._shape_phase,
                color=c_center,
                edge=c_edge,
            )

        if right_h >= 4:
            self._draw_flat_spike(
                surface,
                cx=cx + int(main_hw * 0.88),
                base_y=base_y,
                height=max(4, right_h),
                half_w=right_hw,
                phase_seed=self._shape_phase - 0.9,
                color=c_right,
                edge=c_edge,
                forced_lean_dir=1,
            )

    # ------------------------------------------------------------------
    # Private – state transitions
    # ------------------------------------------------------------------

    def _begin_shattering(self) -> None:
        self._state = _StalagState.SHATTERING
        self._shatter_timer = 0.0
        self.active = False
        self._spawn_fragments()

    def _update_rising(self, dt: float) -> None:
        self._main_delay_timer += dt
        if self._main_delay_timer < 0.0:
            return
        self._rise_timer += dt
        eased = _ease_out_cubic(self._rise_timer / self.RISE_TIME)
        self._current_height = max(1.0, self._target_height * eased)
        if self._rise_timer >= self.RISE_TIME:
            self._state = _StalagState.ACTIVE
            self._current_height = self._target_height

    def _update_active(self, dt: float) -> None:
        self._linger_timer += dt
        if self._linger_timer >= self.LINGER_TIME:
            self._begin_shattering()

    def _update_secondary_timers(self, dt: float) -> None:
        self._secondary_left_timer += dt
        if self._secondary_left_timer >= 0.0:
            progress = _clamp(
                self._secondary_left_timer / self.SECONDARY_RISE_TIME, 0.0, 1.0
            )
            self._secondary_left_height = max(
                1.0, self._secondary_left_target * _ease_out_cubic(progress)
            )

        self._secondary_right_timer += dt
        if self._secondary_right_timer >= 0.0:
            progress = _clamp(
                self._secondary_right_timer / self.SECONDARY_RISE_TIME, 0.0, 1.0
            )
            self._secondary_right_height = max(
                1.0, self._secondary_right_target * _ease_out_cubic(progress)
            )

    # ------------------------------------------------------------------
    # Private – collision
    # ------------------------------------------------------------------

    def _update_collision_regions(self) -> None:
        _clear = pygame.Rect(0, 0, 0, 0)
        if self.dead or self._state is _StalagState.SHATTERING:
            self._collision_mask = None
            self._collision_mask_offset = (0, 0)
            self._collision_bounds_rect = _clear
            return

        polygons = self._build_visual_spike_polygons()
        if not polygons:
            self._collision_mask = None
            self._collision_mask_offset = (0, 0)
            self._collision_bounds_rect = _clear
            return

        all_pts = [(x, y) for poly in polygons for x, y in poly]
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)

        pad = 2
        mask_x = min_x - pad
        mask_y = min_y - pad
        mask_w = max(1, (max_x - min_x) + 1 + pad * 2)
        mask_h = max(1, (max_y - min_y) + 1 + pad * 2)

        mask_surface = pygame.Surface((mask_w, mask_h), pygame.SRCALPHA)
        for poly in polygons:
            local = [(x - mask_x, y - mask_y) for x, y in poly]
            pygame.draw.polygon(mask_surface, (255, 255, 255, 255), local)

        self._collision_mask = pygame.mask.from_surface(mask_surface, 1)
        self._collision_mask_offset = (mask_x, mask_y)
        self._collision_bounds_rect = pygame.Rect(mask_x, mask_y, mask_w, mask_h)

    # ------------------------------------------------------------------
    # Private – fragments
    # ------------------------------------------------------------------

    def _spawn_fragments(self) -> None:
        if self._fragments:
            return
        base_x = self.x
        top_y = self.ground_y - self._current_height
        for _ in range(_FRAGMENT_COUNT):
            life = random.uniform(self.FRAGMENT_LIFE_MIN, self.FRAGMENT_LIFE_MAX)
            self._fragments.append(
                _StalagmiteFragment(
                    x=base_x + random.uniform(-self.w * 0.45, self.w * 0.45),
                    y=random.uniform(top_y, self.ground_y - 4.0),
                    vx=random.uniform(-150.0, 150.0),
                    vy=random.uniform(-235.0, -55.0),
                    angle=random.uniform(0.0, math.tau),
                    spin=random.uniform(-7.0, 7.0),
                    life=life,
                    max_life=life,
                    size=random.uniform(3.0, 7.0),
                    color=random.choice(_STONE_COLORS),
                )
            )

    def _update_fragments(self, dt: float) -> None:
        self._shatter_timer += dt
        for f in self._fragments:
            f.life = max(0.0, f.life - dt)
            f.vy += _FRAGMENT_GRAVITY * dt
            f.x += f.vx * dt
            f.y += f.vy * dt
            f.angle += f.spin * dt
        self._fragments = [f for f in self._fragments if f.life > 0.0]

    def _draw_fragments(self, surface: pygame.Surface) -> None:
        for fragment in self._fragments:
            life = fragment.life
            max_life = max(0.001, fragment.max_life)
            alpha = int(255 * (life / max_life))
            size = max(1, int(fragment.size))
            piece_w = max(4, size * 2)
            piece_h = max(4, int(size * 1.5))
            dust_size = max(6, int(size * 2.4))
            dust_alpha = int(alpha * 0.35)

            dust_surf = pygame.Surface((dust_size * 2, dust_size * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                dust_surf,
                (*fragment.color, dust_alpha),
                (dust_size, dust_size),
                dust_size,
            )
            pygame.draw.circle(
                dust_surf,
                (193, 154, 131, int(dust_alpha * 0.7)),
                (dust_size + 1, dust_size - 1),
                max(2, dust_size // 2),
            )
            dust_pos = (
                int(fragment.x) - dust_size + int(fragment.vx * 0.02),
                int(fragment.y) - dust_size + int(fragment.vy * 0.01),
            )
            surface.blit(dust_surf, dust_pos)

            frag_surf = pygame.Surface((piece_w + 8, piece_h + 8), pygame.SRCALPHA)
            frag_rect = pygame.Rect(0, 0, piece_w, piece_h)
            frag_rect.center = ((piece_w + 8) // 2, (piece_h + 8) // 2)
            br = max(1, size // 4)

            pygame.draw.rect(
                frag_surf, (*fragment.color, alpha), frag_rect, border_radius=br
            )
            pygame.draw.rect(
                frag_surf,
                (70, 44, 34, min(255, alpha + 20)),
                frag_rect,
                width=1,
                border_radius=br,
            )
            pygame.draw.line(
                frag_surf,
                (215, 178, 154, int(alpha * 0.55)),
                (frag_rect.left + 2, frag_rect.centery - 1),
                (frag_rect.right - 3, frag_rect.centery - 2),
                width=1,
            )
            rotated = pygame.transform.rotate(frag_surf, math.degrees(fragment.angle))
            surface.blit(
                rotated, rotated.get_rect(center=(int(fragment.x), int(fragment.y)))
            )

    # ------------------------------------------------------------------
    # Private – drawing helpers
    # ------------------------------------------------------------------

    def _resolve_colors(
        self,
    ) -> tuple[
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
    ]:
        if self._hit_flash > 0.0:
            return (255, 255, 255), (210, 210, 210), (185, 185, 185), (160, 160, 160)
        return (
            (106, 76, 125),  # roxo médio
            (158, 92, 127),  # rosa púrpura
            (224, 126, 116),  # laranja quente
            (15, 10, 20),  # borda escura
        )

    def _build_visual_spike_polygons(self) -> _SpikePolygons:
        cx = int(self.x)
        base_y = int(self.ground_y)
        height = max(8, int(self._current_height))

        screen_w = _cfg("SCREEN_WIDTH", 1280)
        main_hw = min(int(self.w * 1.6), int(screen_w * 0.11))
        left_hw = max(8, int(main_hw * 0.70))
        right_hw = max(8, int(main_hw * 0.58))
        left_h = int(self._secondary_left_height)
        right_h = int(self._secondary_right_height)

        polygons: _SpikePolygons = []

        if left_h >= 4:
            polygons.append(
                self._build_flat_spike_pts(
                    cx=cx - int(main_hw * 0.95),
                    base_y=base_y,
                    height=max(4, left_h),
                    half_w=left_hw,
                    phase_seed=self._shape_phase + 1.2,
                    forced_lean_dir=-1,
                )
            )

        if self._main_delay_timer >= 0.0:
            polygons.append(
                self._build_flat_spike_pts(
                    cx=cx,
                    base_y=base_y,
                    height=height,
                    half_w=main_hw,
                    phase_seed=self._shape_phase,
                )
            )

        if right_h >= 4:
            polygons.append(
                self._build_flat_spike_pts(
                    cx=cx + int(main_hw * 0.88),
                    base_y=base_y,
                    height=max(4, right_h),
                    half_w=right_hw,
                    phase_seed=self._shape_phase - 0.9,
                    forced_lean_dir=1,
                )
            )

        return polygons

    def _build_flat_spike_pts(
        self,
        cx: int,
        base_y: int,
        height: int,
        half_w: int,
        phase_seed: float,
        forced_lean_dir: int | None = None,
    ) -> list[tuple[int, int]]:
        if forced_lean_dir is not None:
            lean_dir = 1 if forced_lean_dir >= 0 else -1
        else:
            lean_dir = 1 if math.sin(phase_seed) >= 0 else -1
        lean_top = int(half_w * (0.20 + 0.12 * abs(math.sin(phase_seed))))
        lean_mid = int(half_w * (0.10 + 0.08 * abs(math.cos(phase_seed * 0.9))))
        notch_cut = int(half_w * (0.28 + 0.14 * abs(math.sin(phase_seed * 1.4))))
        return self._build_spike_pts(
            cx, base_y, height, half_w, lean_dir, lean_top, lean_mid, notch_cut
        )

    @staticmethod
    def _build_spike_pts(
        cx: int,
        base_y: int,
        height: int,
        half_w: int,
        lean_dir: int,
        lean_top: int,
        lean_mid: int,
        notch_cut: int,
    ) -> list[tuple[int, int]]:
        """Vértices da silhueta angular de uma estalagmite."""
        y_tip = base_y - height
        y_n1 = base_y - int(height * 0.73)
        y_n2 = base_y - int(height * 0.46)
        y_n3 = base_y - int(height * 0.20)

        hw_base = half_w
        hw_n3 = max(int(half_w * 0.80), 4)
        hw_n2 = max(int(half_w * 0.54), 3)
        hw_n1 = max(int(half_w * 0.30), 2)

        zag_n2 = min(notch_cut, max(0, hw_n3 - hw_n2))

        cx_tip = cx + lean_dir * lean_top
        cx_n1 = cx + lean_dir * lean_mid
        cx_n2 = cx - lean_dir * zag_n2
        cx_n3 = cx + lean_dir * (lean_mid // 2)

        return [
            (cx_tip, y_tip),
            (cx_n1 - hw_n1, y_n1),
            (cx_n2 - hw_n2, y_n2),
            (cx_n3 - hw_n3, y_n3),
            (cx - hw_base, base_y),
            (cx + hw_base, base_y),
            (cx_n3 + hw_n3, y_n3),
            (cx_n2 + hw_n2, y_n2),
            (cx_n1 + hw_n1, y_n1),
        ]

    def _draw_flat_spike(
        self,
        surface: pygame.Surface,
        cx: int,
        base_y: int,
        height: int,
        half_w: int,
        phase_seed: float,
        color: tuple[int, int, int],
        edge: tuple[int, int, int],
        forced_lean_dir: int | None = None,
    ) -> None:
        pts = self._build_flat_spike_pts(
            cx, base_y, height, half_w, phase_seed, forced_lean_dir
        )
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, edge, pts, width=2)

    def _draw_shadow_stalactite(
        self,
        surface: pygame.Surface,
        offset_x: float,
        scale: float,
        alpha: int,
        color_base: tuple[int, int, int],
        color_mid: tuple[int, int, int],
        _color_light: tuple[int, int, int],
    ) -> None:
        """Estalagmite fantasma low-poly para efeito de profundidade."""
        cx = int(self.x + offset_x)
        base_y = int(self.ground_y)
        height = max(8, int(self._current_height * scale))
        if height < 8:
            return

        screen_w = _cfg("SCREEN_WIDTH", 1280)
        W = min(int(self.BASE_WIDTH * 3.2 * scale), int(screen_w * 0.22))
        half_W = W // 2
        sp = self._shape_phase

        lean_dir = 1 if math.sin(sp) >= 0 else -1
        lean_top = int(W * (0.10 + 0.06 * abs(math.sin(sp))))
        lean_mid = int(W * (0.05 + 0.04 * abs(math.cos(sp * 0.9))))
        notch_cut = int(W * (0.14 + 0.07 * abs(math.sin(sp * 1.4))))

        y_tip = base_y - height
        y_n1 = base_y - int(height * 0.73)
        y_n2 = base_y - int(height * 0.46)
        y_n3 = base_y - int(height * 0.20)
        hw_base, hw_n3, hw_n2, hw_n1 = (
            half_W,
            max(int(half_W * 0.80), 4),
            max(int(half_W * 0.54), 3),
            max(int(half_W * 0.30), 2),
        )

        zag_n2 = min(notch_cut, max(0, hw_n3 - hw_n2))
        cx_tip = cx + lean_dir * lean_top
        cx_n1 = cx + lean_dir * lean_mid
        cx_n2 = cx - lean_dir * zag_n2
        cx_n3 = cx + lean_dir * (lean_mid // 2)

        n1_l, n1_r = cx_n1 - hw_n1, cx_n1 + hw_n1
        n2_l, n2_r = cx_n2 - hw_n2, cx_n2 + hw_n2
        n3_l, n3_r = cx_n3 - hw_n3, cx_n3 + hw_n3

        body_pts = [
            (cx_tip, y_tip),
            (n1_l, y_n1),
            (n2_l, y_n2),
            (n3_l, y_n3),
            (cx - hw_base, base_y),
            (cx + hw_base, base_y),
            (n3_r, y_n3),
            (n2_r, y_n2),
            (n1_r, y_n1),
        ]
        off = int(W * 0.10)
        mid_pts = [
            (cx_tip, y_tip),
            (n1_l + off, y_n1),
            (n2_l + off, y_n2),
            (n3_l + off, y_n3),
            (cx - hw_base + off * 2, base_y),
            (cx + hw_base - off, base_y),
            (n3_r - off // 2, y_n3),
            (n2_r - off // 2, y_n2),
            (n1_r - off // 2, y_n1),
        ]

        surf_w = W * 2 + 60
        surf_h = height + 40
        s = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        ox = cx - surf_w // 2
        oy = base_y - surf_h + 20

        def _loc(pts: list[tuple[int, int]]) -> list[tuple[int, int]]:
            return [(p[0] - ox, p[1] - oy) for p in pts]

        pygame.draw.polygon(s, (*color_base, alpha), _loc(body_pts))
        pygame.draw.polygon(s, (*color_mid, alpha), _loc(mid_pts))
        pygame.draw.polygon(s, (32, 16, 10, alpha), _loc(body_pts), width=2)
        surface.blit(s, (ox, oy))


# ---------------------------------------------------------------------------
# MountainStalactite
# ---------------------------------------------------------------------------


class MountainStalactite:
    # Estrutura fixa no teto — análogo a MountainStalagmite
    pullable_by_black_hole: bool = False

    """Estalactite que cai do teto — espelho invertido de MountainStalagmite."""

    MAX_HEALTH: Final[int] = 20

    BASE_WIDTH: Final = 48
    MIN_HEIGHT: Final = 62

    RISE_TIME: Final = 0.32  # tempo de "descida" até a posição alvo
    LINGER_TIME: Final = 3.0
    SHATTER_TIME: Final = 1.05

    FRAGMENT_LIFE_MIN: Final = 0.62
    FRAGMENT_LIFE_MAX: Final = 1.18

    SECONDARY_DELAY_LEFT: Final = 0.0
    SECONDARY_DELAY_RIGHT: Final = 0.2
    MAIN_DELAY: Final = 0.3
    SECONDARY_RISE_TIME: Final = 0.28
    SECONDARY_MAX_RATIO: Final = 0.48

    _EMPTY_HITBOXES: Final[tuple[pygame.Rect, ...]] = ()

    def __init__(self, x: float, ceiling_y: float, target_y: float) -> None:
        """
        ceiling_y: posição Y de onde a estalactite nasce (topo da tela, valor baixo).
        target_y:  posição Y alvo que a ponta deve atingir.
        """
        self.x: float = float(x)
        self.ceiling_y: float = float(ceiling_y)  # análogo a ground_y, mas no teto
        self.target_y: float = float(target_y)

        self.w: int = self.BASE_WIDTH
        self.health: int = self.MAX_HEALTH
        self.dead: bool = False
        self.active: bool = True

        self._state: _StalagState = _StalagState.RISING
        self._rise_timer: float = 0.0
        self._linger_timer: float = 0.0
        self._hit_flash: float = 0.0
        self._pulse_timer: float = random.uniform(0.0, math.tau)
        self._shape_phase: float = random.uniform(0.0, math.tau)
        self._shatter_timer: float = 0.0
        self._fragments: list[_StalagmiteFragment] = []
        self._current_height: float = 1.0

        self._secondary_left_timer: float = -self.SECONDARY_DELAY_LEFT
        self._secondary_right_timer: float = -self.SECONDARY_DELAY_RIGHT
        self._main_delay_timer: float = -self.MAIN_DELAY
        self._secondary_left_height: float = 0.0
        self._secondary_right_height: float = 0.0

        # Altura = distância do teto até o alvo
        screen_h = float(_cfg("SCREEN_HEIGHT", 720))
        max_height = max(self.MIN_HEIGHT, screen_h - self.ceiling_y - 6.0)
        desired_height = self.target_y - self.ceiling_y + 8.0
        self._target_height: float = _clamp(desired_height, self.MIN_HEIGHT, max_height)

        self._secondary_left_target: int = max(
            20, int(self._target_height * self.SECONDARY_MAX_RATIO)
        )
        self._secondary_right_target: int = max(
            20, int(self._target_height * self.SECONDARY_MAX_RATIO * 0.82)
        )

        self._collision_mask: pygame.mask.Mask | None = None
        self._collision_mask_offset: tuple[int, int] = (0, 0)
        self._collision_bounds_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._update_collision_regions()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        if (
            self._collision_bounds_rect.width <= 0
            or self._collision_bounds_rect.height <= 0
        ):
            return pygame.Rect(int(self.x), int(self.ceiling_y), 0, 0)
        return self._collision_bounds_rect

    @property
    def y(self) -> float:
        """Topo visual da estalactite (junto ao teto)."""
        return self.ceiling_y

    @property
    def h(self) -> float:
        return self._current_height

    @property
    def causes_damage(self) -> bool:
        return not self.dead and self._state in (
            _StalagState.RISING,
            _StalagState.ACTIVE,
        )

    def collision_circle(self) -> tuple[float, float, float]:
        """Geometria circular para chain_shot/AoE — fallback via rect."""
        r = self.rect
        return float(r.centerx), float(r.centery), float(max(r.width, r.height) / 2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_points_value(self) -> int:
        return 120

    def get_ship_contact_hitboxes(self) -> tuple[pygame.Rect, ...]:
        if (
            self.dead
            or self._state is _StalagState.SHATTERING
            or self._collision_bounds_rect.width <= 0
        ):
            return self._EMPTY_HITBOXES
        return (self._collision_bounds_rect,)

    def get_collision_mask_data(
        self,
    ) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        if (
            self.dead
            or self._state is _StalagState.SHATTERING
            or self._collision_mask is None
        ):
            return None
        return self._collision_mask, self._collision_mask_offset

    def take_damage(self, amount: int = 1) -> None:
        if self.dead or self._state is _StalagState.SHATTERING:
            return
        self.health -= amount
        self._hit_flash = 0.12
        if self.health <= 0:
            self.health = 0
            self._begin_shattering()

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        # Já estilhaçando/morto: absorve sem feedback nem crédito de kill (o
        # estado SHATTERING faz take_damage retornar cedo, então o killed só
        # pode disparar no hit de transição — evita double-count no score).
        if self.dead or self._state is _StalagState.SHATTERING:
            return HitResult()

        self.take_damage(damage)
        shattered = self._state is _StalagState.SHATTERING
        return HitResult(
            killed=shattered,
            points=self.get_points_value() if shattered else 0,
            # Sem explosão no kill: a animação de fragmentos já cobre o visual.
            explosion_size=0 if shattered else 8,
            sound=hit_sounds.EXPLOSION_ASTEROID if shattered else hit_sounds.BOSS_DAMAGE,
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.take_damage(amount=999)
        return HitResult(killed=False, sound=hit_sounds.EXPLOSION_ASTEROID)

    def should_remove(self) -> bool:
        return self.dead and not self._fragments

    def update(self, dt: float) -> None:
        if self.dead and not self._fragments:
            return

        if self.dead:
            self._update_fragments(dt)
            return

        self._pulse_timer += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._update_secondary_timers(dt)

        if self._state is _StalagState.RISING:
            self._update_rising(dt)
        elif self._state is _StalagState.ACTIVE:
            self._update_active(dt)
        elif self._state is _StalagState.SHATTERING:
            self._update_fragments(dt)
            if self._shatter_timer >= self.SHATTER_TIME and not self._fragments:
                self.dead = True

        self._update_collision_regions()

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead and not self._fragments:
            return

        if self._state is _StalagState.SHATTERING or (self.dead and self._fragments):
            self._draw_fragments(surface)
            return

        cx = int(self.x)
        height = max(8, int(self._current_height))

        c_center, c_left, c_right, c_edge = self._resolve_colors()

        screen_w = _cfg("SCREEN_WIDTH", 1280)
        main_hw = min(int(self.w * 1.6), int(screen_w * 0.11))
        left_hw = max(8, int(main_hw * 0.70))
        right_hw = max(8, int(main_hw * 0.58))
        left_h = int(self._secondary_left_height)
        right_h = int(self._secondary_right_height)

        # Desenha espelhado verticalmente: base no teto, ponta para baixo
        if left_h >= 4:
            self._draw_flat_spike_flipped(
                surface,
                cx=cx - int(main_hw * 0.95),
                base_y=int(self.ceiling_y),
                height=max(4, left_h),
                half_w=left_hw,
                phase_seed=self._shape_phase + 1.2,
                color=c_left,
                edge=c_edge,
                forced_lean_dir=-1,
            )

        if self._main_delay_timer >= 0.0:
            self._draw_flat_spike_flipped(
                surface,
                cx=cx,
                base_y=int(self.ceiling_y),
                height=height,
                half_w=main_hw,
                phase_seed=self._shape_phase,
                color=c_center,
                edge=c_edge,
            )

        if right_h >= 4:
            self._draw_flat_spike_flipped(
                surface,
                cx=cx + int(main_hw * 0.88),
                base_y=int(self.ceiling_y),
                height=max(4, right_h),
                half_w=right_hw,
                phase_seed=self._shape_phase - 0.9,
                color=c_right,
                edge=c_edge,
                forced_lean_dir=1,
            )

    # ------------------------------------------------------------------
    # Private — delegates to MountainStalagmite helpers via composition
    # ------------------------------------------------------------------

    def _resolve_colors(
        self,
    ) -> tuple[
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
    ]:
        if self._hit_flash > 0.0:
            return (255, 255, 255), (210, 210, 210), (185, 185, 185), (160, 160, 160)
        # Tons mais frios/azulados para diferenciar visualmente das estalagmites
        return (
            (80, 100, 140),
            (100, 130, 170),
            (60, 80, 120),
            (15, 20, 40),
        )

    def _begin_shattering(self) -> None:
        self._state = _StalagState.SHATTERING
        self._shatter_timer = 0.0
        self.active = False
        self._spawn_fragments()

    def _update_rising(self, dt: float) -> None:
        self._main_delay_timer += dt
        if self._main_delay_timer < 0.0:
            return
        self._rise_timer += dt
        eased = _ease_out_cubic(self._rise_timer / self.RISE_TIME)
        self._current_height = max(1.0, self._target_height * eased)
        if self._rise_timer >= self.RISE_TIME:
            self._state = _StalagState.ACTIVE
            self._current_height = self._target_height

    def _update_active(self, dt: float) -> None:
        self._linger_timer += dt
        if self._linger_timer >= self.LINGER_TIME:
            self._begin_shattering()

    def _update_secondary_timers(self, dt: float) -> None:
        self._secondary_left_timer += dt
        if self._secondary_left_timer >= 0.0:
            progress = _clamp(
                self._secondary_left_timer / self.SECONDARY_RISE_TIME, 0.0, 1.0
            )
            self._secondary_left_height = max(
                1.0, self._secondary_left_target * _ease_out_cubic(progress)
            )

        self._secondary_right_timer += dt
        if self._secondary_right_timer >= 0.0:
            progress = _clamp(
                self._secondary_right_timer / self.SECONDARY_RISE_TIME, 0.0, 1.0
            )
            self._secondary_right_height = max(
                1.0, self._secondary_right_target * _ease_out_cubic(progress)
            )

    def _update_collision_regions(self) -> None:
        _clear = pygame.Rect(0, 0, 0, 0)
        if self.dead or self._state is _StalagState.SHATTERING:
            self._collision_mask = None
            self._collision_mask_offset = (0, 0)
            self._collision_bounds_rect = _clear
            return

        polygons = self._build_visual_spike_polygons()
        if not polygons:
            self._collision_mask = None
            self._collision_mask_offset = (0, 0)
            self._collision_bounds_rect = _clear
            return

        all_pts = [(x, y) for poly in polygons for x, y in poly]
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)

        pad = 2
        mask_x = min_x - pad
        mask_y = min_y - pad
        mask_w = max(1, (max_x - min_x) + 1 + pad * 2)
        mask_h = max(1, (max_y - min_y) + 1 + pad * 2)

        mask_surface = pygame.Surface((mask_w, mask_h), pygame.SRCALPHA)
        for poly in polygons:
            local = [(x - mask_x, y - mask_y) for x, y in poly]
            pygame.draw.polygon(mask_surface, (255, 255, 255, 255), local)

        self._collision_mask = pygame.mask.from_surface(mask_surface, 1)
        self._collision_mask_offset = (mask_x, mask_y)
        self._collision_bounds_rect = pygame.Rect(mask_x, mask_y, mask_w, mask_h)

    def _spawn_fragments(self) -> None:
        if self._fragments:
            return
        tip_y = self.ceiling_y + self._current_height
        for _ in range(_FRAGMENT_COUNT):
            life = random.uniform(self.FRAGMENT_LIFE_MIN, self.FRAGMENT_LIFE_MAX)
            self._fragments.append(
                _StalagmiteFragment(
                    x=self.x + random.uniform(-self.w * 0.45, self.w * 0.45),
                    y=random.uniform(self.ceiling_y, tip_y),
                    vx=random.uniform(-150.0, 150.0),
                    vy=random.uniform(55.0, 235.0),  # cai para baixo
                    angle=random.uniform(0.0, math.tau),
                    spin=random.uniform(-7.0, 7.0),
                    life=life,
                    max_life=life,
                    size=random.uniform(3.0, 7.0),
                    color=random.choice(_STONE_COLORS),
                )
            )

    def _update_fragments(self, dt: float) -> None:
        self._shatter_timer += dt
        for f in self._fragments:
            f.life = max(0.0, f.life - dt)
            f.vy += _FRAGMENT_GRAVITY * dt
            f.x += f.vx * dt
            f.y += f.vy * dt
            f.angle += f.spin * dt
        self._fragments = [f for f in self._fragments if f.life > 0.0]

    def _draw_fragments(self, surface: pygame.Surface) -> None:
        for fragment in self._fragments:
            life = fragment.life
            max_life = max(0.001, fragment.max_life)
            alpha = int(255 * (life / max_life))
            size = max(1, int(fragment.size))
            piece_w = max(4, size * 2)
            piece_h = max(4, int(size * 1.5))

            frag_surf = pygame.Surface((piece_w + 8, piece_h + 8), pygame.SRCALPHA)
            frag_rect = pygame.Rect(0, 0, piece_w, piece_h)
            frag_rect.center = ((piece_w + 8) // 2, (piece_h + 8) // 2)
            br = max(1, size // 4)
            pygame.draw.rect(
                frag_surf, (*fragment.color, alpha), frag_rect, border_radius=br
            )
            rotated = pygame.transform.rotate(frag_surf, math.degrees(fragment.angle))
            rr = rotated.get_rect(center=(int(fragment.x), int(fragment.y)))
            surface.blit(rotated, rr)

    def _build_visual_spike_polygons(self) -> list[list[tuple[int, int]]]:
        cx = int(self.x)
        base_y = int(self.ceiling_y)
        height = max(8, int(self._current_height))

        screen_w = _cfg("SCREEN_WIDTH", 1280)
        main_hw = min(int(self.w * 1.6), int(screen_w * 0.11))
        left_hw = max(8, int(main_hw * 0.70))
        right_hw = max(8, int(main_hw * 0.58))
        left_h = int(self._secondary_left_height)
        right_h = int(self._secondary_right_height)

        polygons: list[list[tuple[int, int]]] = []

        if left_h >= 4:
            polygons.append(
                self._build_flipped_pts(
                    cx - int(main_hw * 0.95),
                    base_y,
                    max(4, left_h),
                    left_hw,
                    self._shape_phase + 1.2,
                    forced_lean_dir=-1,
                )
            )

        if self._main_delay_timer >= 0.0:
            polygons.append(
                self._build_flipped_pts(
                    cx,
                    base_y,
                    height,
                    main_hw,
                    self._shape_phase,
                )
            )

        if right_h >= 4:
            polygons.append(
                self._build_flipped_pts(
                    cx + int(main_hw * 0.88),
                    base_y,
                    max(4, right_h),
                    right_hw,
                    self._shape_phase - 0.9,
                    forced_lean_dir=1,
                )
            )

        return polygons

    def _build_flipped_pts(
        self,
        cx: int,
        base_y: int,  # teto (y baixo)
        height: int,
        half_w: int,
        phase_seed: float,
        forced_lean_dir: int | None = None,
    ) -> list[tuple[int, int]]:
        """Vértices espelhados: base no teto, ponta apontando para baixo."""
        lean_dir = (
            (1 if forced_lean_dir >= 0 else -1)
            if forced_lean_dir is not None
            else (1 if math.sin(phase_seed) >= 0 else -1)
        )
        lean_top = int(half_w * (0.20 + 0.12 * abs(math.sin(phase_seed))))
        lean_mid = int(half_w * (0.10 + 0.08 * abs(math.cos(phase_seed * 0.9))))
        notch_cut = int(half_w * (0.28 + 0.14 * abs(math.sin(phase_seed * 1.4))))

        # Espelha Y: tip aponta para baixo (base_y + height), base fica em base_y
        y_tip = base_y + height
        y_n1 = base_y + int(height * 0.73)
        y_n2 = base_y + int(height * 0.46)
        y_n3 = base_y + int(height * 0.20)

        hw_base = half_w
        hw_n3 = max(int(half_w * 0.80), 4)
        hw_n2 = max(int(half_w * 0.54), 3)
        hw_n1 = max(int(half_w * 0.30), 2)
        zag_n2 = min(notch_cut, max(0, hw_n3 - hw_n2))

        cx_tip = cx + lean_dir * lean_top
        cx_n1 = cx + lean_dir * lean_mid
        cx_n2 = cx - lean_dir * zag_n2
        cx_n3 = cx + lean_dir * (lean_mid // 2)

        return [
            (cx_tip, y_tip),
            (cx_n1 - hw_n1, y_n1),
            (cx_n2 - hw_n2, y_n2),
            (cx_n3 - hw_n3, y_n3),
            (cx - hw_base, base_y),
            (cx + hw_base, base_y),
            (cx_n3 + hw_n3, y_n3),
            (cx_n2 + hw_n2, y_n2),
            (cx_n1 + hw_n1, y_n1),
        ]

    def _draw_flat_spike_flipped(
        self,
        surface: pygame.Surface,
        cx: int,
        base_y: int,
        height: int,
        half_w: int,
        phase_seed: float,
        color: tuple[int, int, int],
        edge: tuple[int, int, int],
        forced_lean_dir: int | None = None,
    ) -> None:
        pts = self._build_flipped_pts(
            cx, base_y, height, half_w, phase_seed, forced_lean_dir
        )
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, edge, pts, width=2)


# ---------------------------------------------------------------------------
# MountainMage
# ---------------------------------------------------------------------------


class MountainMage(EnemyHitMixin):
    """Robo/mago exclusivo das montanhas que invoca estalagmites no alvo."""

    MAX_HEALTH: Final[int] = 24

    WIDTH: Final = 54
    HEIGHT: Final = 58
    ORBIT_RADIUS: Final = 50.0
    ORB_RADIUS: Final = 10
    DRIFT_SPEED: Final = 38.0
    TELEGRAPH_SLOWDOWN: Final = 0.30

    _BORDER_MARGIN: Final = 52.0
    _TOP_LIMIT: Final = 48.0
    _BOB_SPEED: Final = 1.7
    _BOB_AMPLITUDE: Final = 4.0

    APPEAR_DURATION: Final = 1.2

    def __init__(self, x: float | None = None, y: float | None = None) -> None:
        screen_w = _cfg("SCREEN_WIDTH", 1280)
        screen_h = _cfg("SCREEN_HEIGHT", 720)

        self.w: int = self.WIDTH
        self.h: int = self.HEIGHT
        self.x: float = float(
            x if x is not None else random.randint(90, max(110, int(screen_w) - 140))
        )
        self.y: float = float(
            y if y is not None else random.randint(70, max(90, int(screen_h * 0.24)))
        )
        # Garante nascimento sempre dentro da tela, independente do spawner.
        self.x = _clamp(
            self.x, self._BORDER_MARGIN, screen_w - self.WIDTH - self._BORDER_MARGIN
        )
        self.y = _clamp(self.y, self._TOP_LIMIT, screen_h * 0.35)

        self.dead: bool = False
        self.active: bool = False
        self.health: int = self.MAX_HEALTH

        self._state: _MageState = _MageState.APPEARING
        self._state_timer: float = self.APPEAR_DURATION
        self._hit_flash: float = 0.0
        self._pulse_timer: float = random.uniform(0.0, math.tau)
        self._bob_phase: float = random.uniform(0.0, math.tau)
        self._orb_angle: float = random.uniform(0.0, math.tau)
        self._drift_dir: int = random.choice((-1, 1))
        self._target_x: float = self.x
        self._target_y: float = self.y
        self._last_player_pos: tuple[float, float] = (
            self.x + self.w / 2,
            self.y + self.h,
        )
        self._telegraph_charge: float = 0.0

        # Partículas místicas de entrada
        self._entry_particles: list[dict[str, float]] = []
        for _ in range(18):
            self._entry_particles.append(
                {
                    "ang": random.uniform(0, math.tau),
                    "dist": random.uniform(90, 180),
                    "speed": random.uniform(1.4, 3.2),
                    "size": random.uniform(2, 5),
                }
            )

        self._body_color: tuple[int, int, int] = (62, 66, 78)
        self._robe_color: tuple[int, int, int] = (88, 92, 108)
        self._accent_color: tuple[int, int, int] = colors.CYAN
        self._eye_color: tuple[int, int, int] = colors.YELLOW
        self._orb_base_color: tuple[int, int, int] = (155, 220, 255)
        self._thruster_surfs: list[pygame.Surface] = [
            pygame.Surface((64, 32), pygame.SRCALPHA) for _ in range(5)
        ]

    # ------------------------------------------------------------------
    # Properties / public API
    # ------------------------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def is_appearing(self) -> bool:
        return self._state is _MageState.APPEARING

    def get_points_value(self) -> int:
        return 320

    def take_damage(self, amount: int = 1) -> None:
        if self.dead or not self.active:
            return
        self.health -= amount
        self._hit_flash = 0.14
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        if not self.active:
            return HitResult(explosion_size=0, killed=False)

        self.take_damage(self.health)
        return HitResult(killed=False, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        emitted = self.update(ctx.sdt, (ctx.player_x, ctx.player_y))
        if emitted:
            ctx.new_enemies.extend(emitted)

    def update(
        self, dt: float, player_pos: tuple[float, float] | None = None
    ) -> list[MountainStalagmite]:
        if self.dead:
            return []

        # Cap dt para animação suave de entrada
        actual_dt = min(dt, 0.05)
        self._pulse_timer += actual_dt
        self._hit_flash = max(0.0, self._hit_flash - actual_dt)

        if player_pos is not None:
            self._track_player(player_pos)

        orb_speed = 15.0 if self._state is _MageState.TELEGRAPH else 2.4
        self._orb_angle += orb_speed * actual_dt

        if self._state is _MageState.APPEARING:
            # Partículas convergem para o centro e encolhem conforme chegam
            for p in self._entry_particles:
                p["dist"] = max(2.0, p["dist"] - p["speed"] * 125.0 * actual_dt)
                p["ang"] += p["speed"] * 6.0 * actual_dt
                dist_ratio = _clamp(p["dist"] / 140.0, 0.0, 1.0)
                p["size"] = max(0.5, dist_ratio * 5.0 + 0.5)
        else:
            self._update_movement(actual_dt)

        return self._update_state(actual_dt, player_pos)

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        if self._state is _MageState.APPEARING:
            appear_dur = max(0.001, self.APPEAR_DURATION)
            progress = _clamp(1.0 - (self._state_timer / appear_dur), 0.0, 1.0)
            alpha = int(_clamp(progress * 255 * 2.0, 0, 255))
            scale = 0.3 + 0.7 * _ease_out_cubic(progress)
            # Partículas: visíveis desde o frame 1, desvanecem ao fim quando o corpo materializa
            particle_alpha = max(80, int(_clamp((1.0 - progress) * 255 * 1.6, 0, 255)))
            self._draw_appearing_effect(surface, alpha=particle_alpha)
            self._draw_orb(surface, alpha=alpha)
            self._draw_body(surface, alpha=alpha, scale=scale)
        else:
            self._draw_telegraph_marker(surface)
            self._draw_orb(surface)
            self._draw_body(surface)
            self._draw_thruster(surface)

    # ------------------------------------------------------------------
    # Private – state
    # ------------------------------------------------------------------

    def _track_player(self, player_pos: tuple[float, float]) -> None:
        screen_w = _cfg("SCREEN_WIDTH", 1280)
        screen_h = _cfg("SCREEN_HEIGHT", 720)
        px, py = player_pos
        self._last_player_pos = (
            _clamp(px, 36.0, screen_w - 36.0),
            _clamp(py, 6.0, screen_h - 40.0),
        )
        if self._state is _MageState.TELEGRAPH:
            self._target_x, self._target_y = self._last_player_pos

    def _update_state(
        self, dt: float, player_pos: tuple[float, float] | None
    ) -> list[MountainStalagmite]:
        spawned: list[MountainStalagmite] = []

        if self._state is _MageState.APPEARING:
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                self._state = _MageState.IDLE
                self._state_timer = random.uniform(1.2, 2.8)
                self.active = True
                self._entry_particles.clear()

        elif self._state is _MageState.IDLE:
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                self._begin_telegraph(player_pos)

        elif self._state is _MageState.TELEGRAPH:
            warning_duration = max(0.01, _cfg("MOUNTAIN_MAGE_WARNING_DURATION", 0.9))
            self._telegraph_charge = _clamp(
                1.0 - self._state_timer / warning_duration, 0.0, 1.0
            )
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                spawned.append(self._spawn_stalagmite())
                self._state = _MageState.COOLDOWN
                self._state_timer = _cfg("MOUNTAIN_MAGE_COOLDOWN", 2.8)
                self._telegraph_charge = 0.0

        elif self._state is _MageState.COOLDOWN:
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                self._state = _MageState.IDLE
                self._state_timer = random.uniform(1.2, 2.8)

        return spawned

    def _begin_telegraph(self, player_pos: tuple[float, float] | None) -> None:
        screen_w = _cfg("SCREEN_WIDTH", 1280)
        screen_h = _cfg("SCREEN_HEIGHT", 720)

        if player_pos is None:
            target_x, target_y = self.x + self.w / 2, screen_h - 80.0
        else:
            target_x, target_y = player_pos

        self._target_x = _clamp(target_x, 36.0, screen_w - 36.0)
        self._target_y = _clamp(target_y, 6.0, screen_h - 40.0)
        self._last_player_pos = (self._target_x, self._target_y)
        self._state = _MageState.TELEGRAPH
        self._state_timer = _cfg("MOUNTAIN_MAGE_WARNING_DURATION", 0.9)
        self._telegraph_charge = 0.0

    def _spawn_stalagmite(self) -> MountainStalagmite:
        screen_h = _cfg("SCREEN_HEIGHT", 720)
        target_x, target_y = self._last_player_pos
        return MountainStalagmite(target_x, screen_h + 1.0, target_y)

    # ------------------------------------------------------------------
    # Private – movement
    # ------------------------------------------------------------------

    def _update_movement(self, dt: float) -> None:
        screen_w = _cfg("SCREEN_WIDTH", 1280)
        screen_h = _cfg("SCREEN_HEIGHT", 720)

        bob_offset = math.sin(self._bob_phase) * self._BOB_AMPLITUDE
        self._bob_phase += dt * self._BOB_SPEED

        drift_speed = self.DRIFT_SPEED * (
            self.TELEGRAPH_SLOWDOWN if self._state is _MageState.TELEGRAPH else 1.0
        )
        self.x += self._drift_dir * drift_speed * dt

        left_limit = self._BORDER_MARGIN
        right_limit = screen_w - self.w - self._BORDER_MARGIN
        if self.x <= left_limit:
            self.x, self._drift_dir = left_limit, 1
        elif self.x >= right_limit:
            self.x, self._drift_dir = right_limit, -1

        self.y += bob_offset * dt * 2.0
        self.y = _clamp(self.y, self._TOP_LIMIT, screen_h * 0.35)

    # ------------------------------------------------------------------
    # Private – drawing
    # ------------------------------------------------------------------

    def _draw_orb(self, surface: pygame.Surface, alpha: int = 255) -> None:
        center_x = int(self.x + self.w / 2)
        center_y = int(self.y + self.h * 0.42)
        orb_x = center_x + math.cos(self._orb_angle) * self.ORBIT_RADIUS
        orb_y = center_y + math.sin(self._orb_angle) * (self.ORBIT_RADIUS * 0.72)

        is_telegraphing = self._state is _MageState.TELEGRAPH
        charge = self._telegraph_charge if is_telegraphing else 0.0
        glow_r = int(self.ORB_RADIUS * (2.0 + charge * 1.6))
        glow_a = int((45 + charge * 135) * (alpha / 255))
        glow_color = (
            (255, 120, 120, glow_a)
            if is_telegraphing
            else (*self._orb_base_color, glow_a)
        )
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, glow_color, (glow_r, glow_r), glow_r)
        surface.blit(glow_surf, (int(orb_x) - glow_r, int(orb_y) - glow_r))

        orb_color = (
            (255, 60, 60, alpha)
            if is_telegraphing
            else (int(120 + charge * 70), int(210 + charge * 35), 255, alpha)
        )
        # Orb sólido (usando surface temporária para alpha se necessário ou draw.circle direto se alpha=255)
        if alpha < 255:
            os = pygame.Surface(
                (self.ORB_RADIUS * 2, self.ORB_RADIUS * 2), pygame.SRCALPHA
            )
            pygame.draw.circle(
                os, orb_color, (self.ORB_RADIUS, self.ORB_RADIUS), self.ORB_RADIUS
            )
            surface.blit(
                os, (int(orb_x) - self.ORB_RADIUS, int(orb_y) - self.ORB_RADIUS)
            )
        else:
            pygame.draw.circle(
                surface, orb_color[:3], (int(orb_x), int(orb_y)), self.ORB_RADIUS
            )

        pygame.draw.circle(
            surface,
            (255, 255, 255, alpha),
            (int(orb_x) - 3, int(orb_y) - 3),
            max(2, self.ORB_RADIUS // 4),
        )

    def _draw_telegraph_marker(self, surface: pygame.Surface) -> None:
        if self._state is not _MageState.TELEGRAPH:
            return

        screen_h = _cfg("SCREEN_HEIGHT", 720)
        mr = int(18 + self._telegraph_charge * 16)
        ms = pygame.Surface((mr * 4, mr * 4), pygame.SRCALPHA)
        mc = (mr * 2, mr * 2)
        color = (255, 235, 140, int(110 + self._telegraph_charge * 100))

        pygame.draw.circle(ms, color, mc, mr, width=2)
        pygame.draw.line(ms, color, (mc[0], 0), (mc[0], ms.get_height()), width=1)
        pygame.draw.line(ms, color, (0, mc[1]), (ms.get_width(), mc[1]), width=1)
        surface.blit(ms, (int(self._target_x) - mr * 2, screen_h - mr * 2))

    def _draw_appearing_effect(self, surface: pygame.Surface, alpha: int = 255) -> None:
        """Desenha as partículas convergindo para o centro durante a entrada.

        Usa surface local com SRCALPHA para que o alpha das cores funcione mesmo
        quando 'surface' é uma game_surface sem SRCALPHA. O centro das partículas
        é clampado à tela para o caso do mage ser spawnado temporariamente off-screen.
        """
        screen_w = int(_cfg("SCREEN_WIDTH", 1280))
        screen_h = int(_cfg("SCREEN_HEIGHT", 720))

        # Centro clampado: garante que as partículas apareçam na tela mesmo que o
        # mage seja instanciado com coordenadas fora da área visível.
        raw_cx = self.x + self.w / 2
        raw_cy = self.y + self.h / 2
        cx = int(_clamp(raw_cx, 0.0, float(screen_w)))
        cy = int(_clamp(raw_cy, 0.0, float(screen_h)))

        # Surface local centrada no mage — muito mais leve que uma full-screen.
        # Raio máximo inicial das partículas é 180px; margem de 200 cobre com folga.
        margin = 200
        surf_w = margin * 2
        surf_h = margin * 2
        ox = cx - margin
        oy = cy - margin

        particle_surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)

        for p in self._entry_particles:
            px = cx + math.cos(p["ang"]) * p["dist"]
            py = cy + math.sin(p["ang"]) * (p["dist"] * 0.8)

            p_alpha = int(alpha * 0.8)
            size = max(1, int(p["size"]))
            lx = int(px - ox)
            ly = int(py - oy)
            pygame.draw.circle(particle_surf, (*colors.CYAN, p_alpha), (lx, ly), size)
            pygame.draw.circle(
                particle_surf,
                (255, 255, 255, int(p_alpha * 0.6)),
                (lx, ly),
                max(1, size // 2),
            )

        surface.blit(particle_surf, (ox, oy))

    def _draw_body(
        self, surface: pygame.Surface, alpha: int = 255, scale: float = 1.0
    ) -> None:
        """Bloquinho fofinho com chapéu de mago pixel-art."""
        screen_w = int(_cfg("SCREEN_WIDTH", 1280))
        screen_h = int(_cfg("SCREEN_HEIGHT", 720))

        # Durante APPEARING o mage pode estar temporariamente fora da tela (spawn
        # off-screen pelo spawner). Clampamos para que o corpo apareça visível.
        body_x = int(_clamp(self.x + self.w / 2, 0.0, float(screen_w)))
        body_y = int(_clamp(self.y, 0.0, float(screen_h)))

        pulse = 0.5 + 0.5 * math.sin(self._pulse_timer * math.tau * 1.1)

        # Surface grande o suficiente para corpo + chapéu acima.
        # Extra de 32px verticais garante que a ponta do chapéu não seja cortada.
        sw = max(1, int(56 * scale))
        sh = max(1, int(68 * scale) + 32)
        bs = pygame.Surface((sw, sh), pygame.SRCALPHA)
        cx = sw // 2

        flash = self._hit_flash > 0.0

        # ── Corpo: bloco quadrado fofinho ─────────────────────────────────────
        body_top = int(30 * scale)
        body_w, body_h = int(34 * scale), int(28 * scale)
        bx = cx - body_w // 2

        body_col = (220, 220, 220) if flash else (78, 82, 98)
        border = (255, 255, 255) if flash else (30, 32, 42)

        # Aplicar alpha
        body_col = (*body_col, alpha)
        border = (*border, alpha)

        # Corpo principal
        pygame.draw.rect(
            bs,
            body_col,
            (bx, body_top, body_w, body_h - 2),
            border_radius=int(4 * scale),
        )
        # Borda escura
        pygame.draw.rect(
            bs,
            border,
            (bx, body_top, body_w, body_h - 2),
            max(1, int(2 * scale)),
            border_radius=int(4 * scale),
        )

        # Highlight superior
        hi_col = (255, 255, 255) if flash else (110, 116, 140)
        pygame.draw.line(
            bs,
            (*hi_col, alpha),
            (bx + int(4 * scale), body_top + int(2 * scale)),
            (bx + body_w - int(5 * scale), body_top + int(2 * scale)),
            1,
        )

        # ── Bochechas ────────────────────────────────────────────────────────
        is_telegraph = self._state == _MageState.TELEGRAPH
        charge = self._telegraph_charge

        cheek_radius = int(3 * scale)
        if flash:
            cheek_col = (255, 220, 220)
        elif is_telegraph:
            r = min(255, int(180 + 75 * charge))
            g_b = max(80, int(180 - 100 * charge))
            cheek_col = (r, g_b, g_b)
            cheek_radius = int((3 + int(charge * 1.5)) * scale)
        else:
            cheek_col = (255, 180, 180)

        pygame.draw.circle(
            bs,
            (*cheek_col, alpha),
            (bx + int(5 * scale), body_top + int(18 * scale)),
            cheek_radius,
        )
        pygame.draw.circle(
            bs,
            (*cheek_col, alpha),
            (bx + body_w - int(6 * scale), body_top + int(18 * scale)),
            cheek_radius,
        )

        # ── Olhos ────────────────────────────────────────────────────────────
        eye_glow = 0.6 + 0.4 * pulse + (charge * 0.6)
        if flash:
            eye_white = (255, 255, 255)
            pupil_col = (200, 200, 200)
            shine_col = (255, 255, 255)
        else:
            ey_r = 255
            ey_g = int(_clamp(200 + 30 * eye_glow, 0, 255))
            ey_b = int(_clamp(40 + 20 * eye_glow, 0, 255))
            eye_white = (ey_r, ey_g, ey_b)
            pupil_col = (30, 20, 10)
            shine_col = (255, 255, 220)

        eye_y = body_top + int(10 * scale)
        is_recovering = self._state == _MageState.COOLDOWN
        recovery_time = 2.8 - self._state_timer if is_recovering else 0.0
        is_telegraphing = self._state == _MageState.TELEGRAPH
        tremor_window = is_telegraphing or (
            is_recovering and (0.0 < recovery_time < 0.18)
        )
        recovery_blink = is_recovering and (
            (0.20 < recovery_time < 0.30) or (0.45 < recovery_time < 0.55)
        )

        is_blinking = (self._pulse_timer % 4.0) < 0.15
        look_x = int(math.sin(self._pulse_timer * 1.2) * 2.8 * scale)
        look_y = int(math.cos(self._pulse_timer * 0.5) * 1.0 * scale)
        body_shake_x = (
            int(math.sin(self._pulse_timer * 40.0) * 2.0 * scale)
            if tremor_window
            else 0
        )
        body_shake_y = (
            int(math.cos(self._pulse_timer * 40.0) * 1.0 * scale)
            if tremor_window
            else 0
        )

        for i, ex_base in enumerate((cx - int(7 * scale), cx + int(7 * scale))):
            ex = ex_base
            ey = eye_y
            pupil_x = ex + max(1, int(1 * scale)) + (0 if is_telegraph else look_x)
            pupil_y = (
                ey
                + max(1, int(1 * scale))
                + (int(2 * scale) if is_telegraph else look_y)
            )

            if recovery_blink or (
                is_blinking and not is_telegraph and not is_recovering
            ):
                pygame.draw.line(
                    bs,
                    (*border[:3], alpha),
                    (ex - int(4 * scale), ey),
                    (ex + int(4 * scale), ey),
                    max(1, int(2 * scale)),
                )
            elif is_telegraph:
                squint_h = max(2, int((8 - 6 * charge) * scale))
                pygame.draw.ellipse(
                    bs,
                    (*eye_white, alpha),
                    (
                        ex - int(4 * scale),
                        ey - squint_h // 2 + int(2 * scale),
                        int(8 * scale),
                        squint_h,
                    ),
                )
                px = ex + (int(1 * scale) if i == 0 else -int(1 * scale))
                pygame.draw.circle(
                    bs, (*pupil_col, alpha), (px, ey + int(2 * scale)), 1
                )
            else:
                pygame.draw.circle(bs, (*eye_white, alpha), (ex, ey), int(5 * scale))
                pygame.draw.circle(
                    bs, (*pupil_col, alpha), (pupil_x, pupil_y), int(2 * scale)
                )
                pygame.draw.circle(
                    bs,
                    (*shine_col, alpha),
                    (ex - int(3 * scale), ey - int(3 * scale)),
                    1,
                )

        # ── Chapéu de mago ───────────────────────────────────────────────────
        hat_col = (45, 28, 80, alpha)
        hat_mid = (62, 40, 110, alpha)
        hat_border = (20, 10, 40, alpha)
        star_col = (255, 220, 60, alpha)

        hat_float_offset = math.sin(self._bob_phase - 1.5) * 2.5 * scale
        brim_y = body_top - int(8 * scale) + int(hat_float_offset)

        # Aba
        brim_w, brim_h = int(40 * scale), int(5 * scale)
        brim_x = cx - brim_w // 2
        pygame.draw.rect(
            bs,
            hat_col,
            (brim_x, brim_y, brim_w, brim_h),
            border_radius=max(1, int(2 * scale)),
        )
        pygame.draw.rect(
            bs,
            hat_border,
            (brim_x, brim_y, brim_w, brim_h),
            1,
            border_radius=max(1, int(2 * scale)),
        )

        # Corpo do chapéu
        wobble = math.sin(self._bob_phase - 2.5) * 3.5 * scale
        bw = int(20 * scale)
        mid_y = brim_y - int(12 * scale)
        tip_x = cx + int(18 * scale) + wobble
        tip_y = brim_y - int(24 * scale)

        cone_pts: list[tuple[float, float]] = [
            (float(cx - bw), float(brim_y)),
            (float(cx + bw), float(brim_y)),
            (float(cx + int(8 * scale)), float(mid_y)),
            (float(tip_x), float(tip_y)),
            (float(cx - int(2 * scale)), float(mid_y)),
        ]
        pygame.draw.polygon(bs, hat_col, cone_pts)

        # Face frontal (iluminada) para efeito 3D
        face_pts: list[tuple[float, float]] = [
            (float(cx - bw + int(3 * scale)), float(brim_y)),
            (float(cx + bw), float(brim_y)),
            (float(cx + int(8 * scale)), float(mid_y)),
            (float(tip_x), float(tip_y)),
            (float(cx), float(mid_y)),
        ]
        pygame.draw.polygon(bs, hat_mid, face_pts)
        pygame.draw.polygon(bs, hat_border, cone_pts, 1)

        # Estrela
        star_cx, star_cy = cx + int(3 * scale), brim_y - int(10 * scale)
        pygame.draw.circle(bs, star_col, (star_cx, star_cy), max(1, int(2 * scale)))

        # ── Blit final ───────────────────────────────────────────────────────
        surface.blit(
            bs,
            (
                body_x - cx + body_shake_x,
                body_y - int(10 * scale) + body_shake_y,
            ),
        )

    def _draw_thruster(self, surface: pygame.Surface) -> None:
        cx = int(self.x + self.w / 2)
        sy = int(self.y + self.h)
        t = self._pulse_timer

        pygame.draw.rect(surface, (255, 255, 255), (cx - 4, sy, 8, 4))
        for i in range(5):
            ph = ((t * 2.0) + (i / 5)) % 1.0
            w = int(4 * 10 * (1 - ph))
            h = max(4, int(4 * 4 * (1 - ph)))
            y = sy + int(ph * 4 * 14) + 4
            al = max(0, int(255 * (1 - ph * ph)))
            if w < 4:
                continue
            col = (
                (255, 255, 255)
                if ph < 0.15
                else ((157, 212, 240) if ph < 0.5 else (91, 159, 200))
            )
            thruster = self._thruster_surfs[i]
            thruster.fill((0, 0, 0, 0))
            pygame.draw.rect(thruster, (*col, al), (0, 0, w, h), 4)
            surface.blit(thruster, (cx - w // 2, y - h // 2))
