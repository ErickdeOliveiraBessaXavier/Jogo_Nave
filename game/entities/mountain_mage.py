from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from ..core import colors
from ..core.config import config as Config


@dataclass
class _StalagmiteFragment:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: tuple[int, int, int]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _ease_out_cubic(value: float) -> float:
    value = _clamp(value, 0.0, 1.0)
    return 1.0 - (1.0 - value) ** 3

class MountainStalagmite:
    """Pilar de pedra invocado pelo MountainMage, estilo low-poly terroso."""

    BASE_WIDTH = 48
    MIN_HEIGHT = 62
    RISE_TIME = 0.32
    LINGER_TIME = 3.0
    SHATTER_TIME = 0.42

    def __init__(self, x: float, ground_y: float, target_y: float):
        self.x = float(x)
        self.ground_y = float(ground_y)
        self.target_y = float(target_y)

        self.w = self.BASE_WIDTH
        self.health = 3
        self.dead = False
        self.active = True

        self._state = "rising"
        self._rise_timer = 0.0
        self._linger_timer = 0.0
        self._hit_flash = 0.0
        self._pulse_timer = random.uniform(0.0, math.tau)
        self._shape_phase = random.uniform(0.0, math.tau)
        self._shatter_timer = 0.0
        self._fragments: list[_StalagmiteFragment] = []
        self._current_height = 1.0
        max_height = max(self.MIN_HEIGHT, self.ground_y - 6.0)
        desired_height = self.ground_y - self.target_y + 8.0
        self._target_height = _clamp(
            desired_height,
            self.MIN_HEIGHT,
            max_height,
        )

    @property
    def rect(self) -> pygame.Rect:
        height = max(8, int(self._current_height))
        return pygame.Rect(int(self.x - self.w / 2), int(self.ground_y - height), self.w, height)

    @property
    def y(self) -> float:
        return self.ground_y - self._current_height

    @property
    def h(self) -> float:
        return self._current_height

    @property
    def causes_damage(self) -> bool:
        return not self.dead and self._state in ("rising", "active")

    def _spawn_fragments(self) -> None:
        if self._fragments:
            return

        base_x = self.x
        top_y = self.ground_y - self._current_height
        for _ in range(16):
            vx = random.uniform(-180.0, 180.0)
            vy = random.uniform(-210.0, -40.0)
            life = random.uniform(0.18, self.SHATTER_TIME)
            size = random.uniform(2.0, 5.0)
            self._fragments.append(
                _StalagmiteFragment(
                    x=base_x + random.uniform(-self.w * 0.45, self.w * 0.45),
                    y=random.uniform(top_y, self.ground_y - 4.0),
                    vx=vx,
                    vy=vy,
                    life=life,
                    max_life=life,
                    size=size,
                    # Cores terrosas baseadas na imagem anexada
                    color=random.choice(
                        (
                            (140, 100, 84),  # Marrom médio
                            (175, 130, 107), # Marrom claro/Bege
                            (89, 56, 49),    # Marrom escuro
                            (193, 154, 131), # Detalhe claro
                        )
                    ),
                )
            )

    def take_damage(self, amount: int = 1) -> None:
        if self.dead or self._state == "shattering":
            return

        self.health -= amount
        self._hit_flash = 0.12
        if self.health <= 0:
            self.health = 0
            self._state = "shattering"
            self._shatter_timer = 0.0
            self.active = False
            self._spawn_fragments()

    def get_points_value(self) -> int:
        return 120

    def update(self, dt: float) -> None:
        if self.dead:
            return

        self._pulse_timer += dt
        if self._hit_flash > 0.0:
            self._hit_flash = max(0.0, self._hit_flash - dt)

        if self._state == "rising":
            self._rise_timer += dt
            rise_progress = self._rise_timer / self.RISE_TIME
            eased = _ease_out_cubic(rise_progress)
            self._current_height = max(1.0, self._target_height * eased)
            if self._rise_timer >= self.RISE_TIME:
                self._state = "active"
                self._current_height = self._target_height
        elif self._state == "active":
            self._linger_timer += dt
            if self._linger_timer >= self.LINGER_TIME:
                self._state = "shattering"
                self._shatter_timer = 0.0
                self.active = False
                self._spawn_fragments()
        elif self._state == "shattering":
            self._shatter_timer += dt
            gravity = 430.0
            for fragment in self._fragments:
                fragment.life = max(0.0, fragment.life - dt)
                fragment.vy = fragment.vy + gravity * dt
                fragment.x = fragment.x + fragment.vx * dt
                fragment.y = fragment.y + fragment.vy * dt

            self._fragments = [frag for frag in self._fragments if frag.life > 0.0]

            if self._shatter_timer >= self.SHATTER_TIME and not self._fragments:
                self.dead = True

    def _draw_shadow_stalactite(
        self, surface: pygame.Surface, offset_x: float, scale: float, alpha: int, color_base: tuple[int, int, int], color_mid: tuple[int, int, int], color_light: tuple[int, int, int]
    ) -> None:
        """Desenha uma estalagmite fantasma low-poly angular para efeito de profundidade."""
        cx = int(self.x + offset_x)
        base_y = int(self.ground_y)
        height = max(8, int(self._current_height * scale))
        if height < 8:
            return

        screen_w = getattr(Config, "SCREEN_WIDTH", 1280)
        W = min(int(self.BASE_WIDTH * 3.2 * scale), int(screen_w * 0.22))
        half_W = W // 2

        sp = self._shape_phase
        lean_dir  = 1 if math.sin(sp) >= 0 else -1
        lean_top  = int(W * (0.10 + 0.06 * abs(math.sin(sp))))
        lean_mid  = int(W * (0.05 + 0.04 * abs(math.cos(sp * 0.9))))
        notch_cut = int(W * (0.14 + 0.07 * abs(math.sin(sp * 1.4))))

        y_tip = base_y - height
        y_n1  = base_y - int(height * 0.73)
        y_n2  = base_y - int(height * 0.46)
        y_n3  = base_y - int(height * 0.20)

        # Larguras fixas decrescentes: base > n3 > n2 > n1 > ponta
        hw_base = half_W
        hw_n3   = max(int(half_W * 0.80), 4)
        hw_n2   = max(int(half_W * 0.54), 3)
        hw_n1   = max(int(half_W * 0.30), 2)

        # Zig-zag: n2 desloca para o lado oposto (cotovelo do raio),
        # limitado para não extrapolar o envelope de n3.
        max_zag_n2 = hw_n3 - hw_n2
        zag_n2     = min(notch_cut, max(0, max_zag_n2))

        cx_tip = cx + lean_dir * lean_top
        cx_n1  = cx + lean_dir * lean_mid
        cx_n2  = cx - lean_dir * zag_n2
        cx_n3  = cx + lean_dir * (lean_mid // 2)

        n1_l = cx_n1 - hw_n1;  n1_r = cx_n1 + hw_n1
        n2_l = cx_n2 - hw_n2;  n2_r = cx_n2 + hw_n2
        n3_l = cx_n3 - hw_n3;  n3_r = cx_n3 + hw_n3

        body_pts = [
            (cx_tip, y_tip), (n1_l, y_n1), (n2_l, y_n2), (n3_l, y_n3),
            (cx - hw_base, base_y), (cx + hw_base, base_y),
            (n3_r, y_n3), (n2_r, y_n2), (n1_r, y_n1),
        ]
        off = int(W * 0.10)
        mid_pts = [
            (cx_tip, y_tip),
            (n1_l + off, y_n1), (n2_l + off, y_n2), (n3_l + off, y_n3),
            (cx - hw_base + off * 2, base_y), (cx + hw_base - off, base_y),
            (n3_r - off // 2, y_n3), (n2_r - off // 2, y_n2), (n1_r - off // 2, y_n1),
        ]

        # Offscreen surface para suportar alpha por camada
        surf_w = W * 2 + 60
        surf_h = height + 40
        s = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        ox = cx - surf_w // 2
        oy = base_y - surf_h + 20

        def _loc(pts: list[tuple[int, int]]) -> list[tuple[int, int]]:
            return [(p[0] - ox, p[1] - oy) for p in pts]

        pygame.draw.polygon(s, (*color_base, alpha), _loc(body_pts))
        pygame.draw.polygon(s, (*color_mid,  alpha), _loc(mid_pts))
        pygame.draw.polygon(s, (32, 16, 10,  alpha), _loc(body_pts), width=2)
        surface.blit(s, (ox, oy))

    # ------------------------------------------------------------------
    # Helpers de desenho
    # ------------------------------------------------------------------

    @staticmethod
    def _build_spike_pts(
        cx: int, base_y: int, height: int, half_w: int,
        lean_dir: int, lean_top: int, lean_mid: int, notch_cut: int,
    ) -> list[tuple[int, int]]:
        """Retorna os vértices da silhueta angular de uma estalagmite.

        Zig-zag: o centro de cada nível oscila lateralmente (notch_cut),
        criando a quebra angular estilo raio. A largura em cada nível
        é fixa e decrescente, garantindo hierarquia base > meio > ponta
        independente do deslocamento do centro.
        """
        y_tip = base_y - height
        y_n1  = base_y - int(height * 0.73)
        y_n2  = base_y - int(height * 0.46)
        y_n3  = base_y - int(height * 0.20)

        # Larguras fixas decrescentes (metade): base > n3 > n2 > n1 > ponta
        hw_base = half_w
        hw_n3   = max(int(half_w * 0.80), 4)
        hw_n2   = max(int(half_w * 0.54), 3)
        hw_n1   = max(int(half_w * 0.30), 2)

        # Centro de cada nível: zig-zag lateral controlado pelo notch_cut.
        # n1 e n3 inclinam para lean_dir; n2 zaga para o lado oposto.
        # O deslocamento é limitado a no máximo (hw_atual - hw_acima) para
        # nunca fazer o lado estreito cruzar a borda do nível abaixo.
        max_zag_n2 = hw_n3 - hw_n2          # margem disponível antes de sair do envelope de n3
        zag_n2     = min(notch_cut, max(0, max_zag_n2))

        cx_tip = cx + lean_dir * lean_top
        cx_n1  = cx + lean_dir * lean_mid
        cx_n2  = cx - lean_dir * zag_n2      # lado oposto — cria o "cotovelo" do raio
        cx_n3  = cx + lean_dir * (lean_mid // 2)

        return [
            (cx_tip,        y_tip),
            (cx_n1 - hw_n1, y_n1), (cx_n2 - hw_n2, y_n2), (cx_n3 - hw_n3, y_n3),
            (cx - hw_base,  base_y), (cx + hw_base, base_y),
            (cx_n3 + hw_n3, y_n3), (cx_n2 + hw_n2, y_n2), (cx_n1 + hw_n1, y_n1),
        ]

    def _draw_flat_spike(
        self, surface: pygame.Surface,
        cx: int, base_y: int, height: int, half_w: int,
        phase_seed: float,
        color: tuple[int, int, int],
        edge: tuple[int, int, int],
        forced_lean_dir: int | None = None,
    ) -> None:
        """Desenha uma estalagmite flat 2D com cor única sólida."""
        if forced_lean_dir is None:
            lean_dir = 1 if math.sin(phase_seed) >= 0 else -1
        else:
            lean_dir = 1 if forced_lean_dir >= 0 else -1
        lean_top  = int(half_w * (0.20 + 0.12 * abs(math.sin(phase_seed))))
        lean_mid  = int(half_w * (0.10 + 0.08 * abs(math.cos(phase_seed * 0.9))))
        notch_cut = int(half_w * (0.28 + 0.14 * abs(math.sin(phase_seed * 1.4))))

        pts = self._build_spike_pts(
            cx, base_y, height, half_w,
            lean_dir, lean_top, lean_mid, notch_cut,
        )
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, edge,  pts, width=2)

    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        cx     = int(self.x)
        base_y = int(self.ground_y)
        height = max(8, int(self._current_height))

        # ── Fragmentos do shatter ─────────────────────────────────────────────
        if self._state == "shattering":
            for fragment in self._fragments:
                life     = fragment.life
                max_life = max(0.001, fragment.max_life)
                alpha    = int(255 * (life / max_life))
                size     = max(1, int(fragment.size))
                frag_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.polygon(
                    frag_surf,
                    (*fragment.color, alpha),
                    [(size, 0), (size * 2, size), (size, size * 2), (0, size)],
                )
                surface.blit(frag_surf, (int(fragment.x) - size, int(fragment.y) - size))
            return

        # ── Cores únicas por estalagmite (monocromático, sem overlay) ────────
        if self._hit_flash > 0.0:
            c_center = (255, 255, 255)
            c_left   = (210, 210, 210)
            c_right  = (185, 185, 185)
            c_edge   = (160, 160, 160)
        else:
            c_center = (52,  30,  22)   # mais escura — central
            c_left   = (88,  60,  46)   # média
            c_right  = (112, 80,  62)   # levemente mais clara
            c_edge   = (28,  14,  10)

        screen_w = getattr(Config, "SCREEN_WIDTH", 1280)
        main_hw  = min(int(self.w * 1.6), int(screen_w * 0.11))

        side_h   = max(20, int(self._target_height * 0.48))
        left_hw  = max(8, int(main_hw * 0.70))
        right_hw = max(8, int(main_hw * 0.58))

        # ── Lateral de fundo (atrás da principal) ──────────────────────────────
        self._draw_flat_spike(
            surface,
            cx         = cx - int(main_hw * 0.95),
            base_y     = base_y,
            height     = side_h,
            half_w     = left_hw,
            phase_seed = self._shape_phase + 1.2,
            color      = c_left,
            edge       = c_edge,
            forced_lean_dir = -1,
        )
        # ── Central (cresce com animação, mais escura, desenhada por cima) ────
        self._draw_flat_spike(
            surface,
            cx         = cx,
            base_y     = base_y,
            height     = height,
            half_w     = main_hw,
            phase_seed = self._shape_phase,
            color      = c_center,
            edge       = c_edge,
        )

        # ── Lateral de frente (sobre a principal) ──────────────────────────────
        self._draw_flat_spike(
            surface,
            cx         = cx + int(main_hw * 0.88),
            base_y     = base_y,
            height     = int(side_h * 0.82),
            half_w     = right_hw,
            phase_seed = self._shape_phase - 0.9,
            color      = c_right,
            edge       = c_edge,
            forced_lean_dir = 1,
        )
class MountainMage:
    """Robo/mago exclusivo das montanhas que invoca estalagmites no alvo."""

    WIDTH = 54
    HEIGHT = 58
    ORBIT_RADIUS = 28.0
    ORB_RADIUS = 12
    DRIFT_SPEED = 38.0
    TELEGRAPH_SLOWDOWN = 0.30

    def __init__(self, x: float | None = None, y: float | None = None):
        screen_w = getattr(Config, "SCREEN_WIDTH", 1280)
        screen_h = getattr(Config, "SCREEN_HEIGHT", 720)

        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.x = float(
            x if x is not None else random.randint(90, max(110, screen_w - 140))
        )
        self.y = float(
            y if y is not None else random.randint(70, max(90, int(screen_h * 0.24)))
        )

        self.dead = False
        self.active = True
        self.health = 24

        self._state = "idle"
        self._state_timer = random.uniform(1.1, 2.6)
        self._hit_flash = 0.0
        self._pulse_timer = random.uniform(0.0, math.tau)
        self._bob_phase = random.uniform(0.0, math.tau)
        self._orb_angle = random.uniform(0.0, math.tau)
        self._drift_dir = random.choice((-1, 1))
        self._target_x = self.x
        self._target_y = self.y
        self._last_player_pos = (self.x + self.w / 2, self.y + self.h)
        self._telegraph_charge = 0.0

        self._body_color = (62, 66, 78)
        self._robe_color = (88, 92, 108)
        self._accent_color = colors.CYAN
        self._eye_color = colors.YELLOW
        self._orb_base_color = (155, 220, 255)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def get_points_value(self) -> int:
        return 320

    def take_damage(self, amount: int = 1) -> None:
        if self.dead:
            return

        self.health -= amount
        self._hit_flash = 0.14
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def _begin_telegraph(self, player_pos: tuple[float, float] | None) -> None:
        screen_w = getattr(Config, "SCREEN_WIDTH", 1280)
        screen_h = getattr(Config, "SCREEN_HEIGHT", 720)

        if player_pos is None:
            target_x = self.x + self.w / 2
            target_y = screen_h - 80.0
        else:
            target_x, target_y = player_pos

        self._target_x = _clamp(target_x, 36.0, screen_w - 36.0)
        self._target_y = _clamp(target_y, 6.0, screen_h - 40.0)
        self._last_player_pos = (self._target_x, self._target_y)
        self._state = "telegraph"
        self._state_timer = getattr(Config, "MOUNTAIN_MAGE_WARNING_DURATION", 0.9)
        self._telegraph_charge = 0.0

    def _spawn_stalagmite(self) -> MountainStalagmite:
        screen_h = getattr(Config, "SCREEN_HEIGHT", 720)
        target_x, target_y = self._last_player_pos
        return MountainStalagmite(
            target_x,
            screen_h + 1.0,
            target_y,
        )

    def _update_movement(self, dt: float) -> None:
        screen_w = getattr(Config, "SCREEN_WIDTH", 1280)
        bob_offset = math.sin(self._bob_phase) * 4.0
        self._bob_phase += dt * 1.7

        if self._state == "telegraph":
            drift = self.DRIFT_SPEED * self.TELEGRAPH_SLOWDOWN
            self.x += self._drift_dir * drift * dt
        else:
            self.x += self._drift_dir * self.DRIFT_SPEED * dt

        left_limit = 52.0
        right_limit = screen_w - self.w - 52.0
        if self.x <= left_limit:
            self.x = left_limit
            self._drift_dir = 1
        elif self.x >= right_limit:
            self.x = right_limit
            self._drift_dir = -1

        self.y += bob_offset * dt * 2.0
        top_limit = 48.0
        bottom_limit = getattr(Config, "SCREEN_HEIGHT", 720) * 0.35
        self.y = _clamp(self.y, top_limit, bottom_limit)

    def update(
        self, dt: float, player_pos: tuple[float, float] | None = None
    ) -> list[MountainStalagmite]:
        if self.dead:
            return []

        self._pulse_timer += dt
        if self._hit_flash > 0.0:
            self._hit_flash = max(0.0, self._hit_flash - dt)

        spawned: list[MountainStalagmite] = []

        if player_pos is not None:
            screen_w = getattr(Config, "SCREEN_WIDTH", 1280)
            screen_h = getattr(Config, "SCREEN_HEIGHT", 720)
            px, py = player_pos
            self._last_player_pos = (
                _clamp(px, 36.0, screen_w - 36.0),
                _clamp(py, 6.0, screen_h - 40.0),
            )
            if self._state == "telegraph":
                self._target_x, self._target_y = self._last_player_pos

        self._orb_angle += (2.4 if self._state != "telegraph" else 6.0) * dt
        self._update_movement(dt)

        if self._state == "idle":
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                self._begin_telegraph(player_pos)
        elif self._state == "telegraph":
            warning_duration = max(
                0.01, getattr(Config, "MOUNTAIN_MAGE_WARNING_DURATION", 0.9)
            )
            self._telegraph_charge = _clamp(
                1.0 - (self._state_timer / warning_duration), 0.0, 1.0
            )
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                spawned.append(self._spawn_stalagmite())
                self._state = "cooldown"
                self._state_timer = getattr(Config, "MOUNTAIN_MAGE_COOLDOWN", 2.8)
                self._telegraph_charge = 0.0
        elif self._state == "cooldown":
            self._state_timer -= dt
            if self._state_timer <= 0.0:
                self._state = "idle"
                self._state_timer = random.uniform(1.2, 2.8)

        return spawned

    def _draw_orb(self, surface: pygame.Surface) -> None:
        center_x = int(self.x + self.w / 2)
        center_y = int(self.y + self.h * 0.42)
        orb_x = center_x + math.cos(self._orb_angle) * self.ORBIT_RADIUS
        orb_y = center_y + math.sin(self._orb_angle) * (self.ORBIT_RADIUS * 0.72)

        charge = self._telegraph_charge if self._state == "telegraph" else 0.0
        glow_radius = int(self.ORB_RADIUS * (2.0 + charge * 1.6))
        glow_alpha = int(45 + charge * 135)
        glow_surface = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surface,
            (*self._orb_base_color, glow_alpha),
            (glow_radius, glow_radius),
            glow_radius,
        )
        surface.blit(glow_surface, (int(orb_x) - glow_radius, int(orb_y) - glow_radius))

        orb_color = (
            int(120 + charge * 70),
            int(210 + charge * 35),
            255,
        )
        pygame.draw.circle(surface, orb_color, (int(orb_x), int(orb_y)), self.ORB_RADIUS)
        pygame.draw.circle(
            surface,
            colors.WHITE,
            (int(orb_x) - 3, int(orb_y) - 3),
            max(2, self.ORB_RADIUS // 4),
        )

    def _draw_telegraph_marker(self, surface: pygame.Surface) -> None:
        if self._state != "telegraph":
            return

        screen_h = getattr(Config, "SCREEN_HEIGHT", 720)
        marker_radius = int(18 + self._telegraph_charge * 16)
        marker_surface = pygame.Surface((marker_radius * 4, marker_radius * 4), pygame.SRCALPHA)
        marker_center = (marker_radius * 2, marker_radius * 2)
        marker_color = (255, 235, 140, int(110 + self._telegraph_charge * 100))
        pygame.draw.circle(marker_surface, marker_color, marker_center, marker_radius, width=2)
        pygame.draw.line(
            marker_surface,
            marker_color,
            (marker_center[0], 0),
            (marker_center[0], marker_surface.get_height()),
            width=1,
        )
        pygame.draw.line(
            marker_surface,
            marker_color,
            (0, marker_center[1]),
            (marker_surface.get_width(), marker_center[1]),
            width=1,
        )
        surface.blit(
            marker_surface,
            (int(self._target_x) - marker_radius * 2, screen_h - marker_radius * 2),
        )

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        self._draw_telegraph_marker(surface)
        self._draw_orb(surface)

        body_x = int(self.x)
        body_y = int(self.y)
        pulse = 0.5 + 0.5 * math.sin(self._pulse_timer * math.tau * 1.1)

        body_surface = pygame.Surface((self.w + 28, self.h + 26), pygame.SRCALPHA)
        center_x = body_surface.get_width() // 2
        center_y = body_surface.get_height() // 2

        if self._hit_flash > 0.0:
            robe_color = colors.WHITE
            body_color = colors.BRIGHT_GRAY
        else:
            robe_color = self._robe_color
            body_color = self._body_color

        pygame.draw.ellipse(body_surface, robe_color, (center_x - 18, 10, 36, 42))
        pygame.draw.rect(body_surface, body_color, (center_x - 14, 18, 28, 32), border_radius=6)
        pygame.draw.rect(body_surface, (45, 48, 58), (center_x - 20, 28, 40, 12), border_radius=4)

        hood_color = (72, 76, 90)
        pygame.draw.polygon(
            body_surface,
            hood_color,
            [
                (center_x - 22, 24),
                (center_x - 10, 4),
                (center_x + 10, 4),
                (center_x + 22, 24),
                (center_x + 14, 50),
                (center_x - 14, 50),
            ],
        )

        eye_glow = 0.55 + 0.45 * pulse + self._telegraph_charge * 0.55
        eye_color = (
            int(_clamp(220 + 35 * eye_glow, 0, 255)),
            int(_clamp(220 + 20 * eye_glow, 0, 255)),
            int(_clamp(120 + 10 * eye_glow, 0, 255)),
        )
        pygame.draw.circle(body_surface, eye_color, (center_x - 7, 24), 3)
        pygame.draw.circle(body_surface, eye_color, (center_x + 7, 24), 3)
        pygame.draw.line(
            body_surface,
            self._accent_color,
            (center_x, 8),
            (center_x, 2),
            width=2,
        )
        pygame.draw.circle(body_surface, self._accent_color, (center_x, 2), 3)

        # Pequenas faixas laterais para reforcar a leitura de robo/mago.
        pygame.draw.rect(body_surface, (112, 118, 136), (center_x - 24, 30, 6, 16), border_radius=2)
        pygame.draw.rect(body_surface, (112, 118, 136), (center_x + 18, 30, 6, 16), border_radius=2)

        surface.blit(body_surface, (body_x - center_x + 10, body_y - center_y + 4))
