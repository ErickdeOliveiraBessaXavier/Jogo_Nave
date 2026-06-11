"""Sentinela Aranha (StealthFighter) — sentinela de linha do bioma STARFIELD.

Pequena sentinela tecnológica: uma **gema energética** central sustentada por um
chassi com **patas mecânicas** que a fazem patrulhar as **bordas** da arena.
Não avança para o centro — sobe e desce colada à parede, e sempre que cruza
aproximadamente a **altura da nave** carrega a gema e dispara um **laser
horizontal** rápido que atravessa a arena. Pressão de posicionamento, não de
dano: vida baixa, prioridade alta — ignorá-la custa caro.

Comportamento (FSM): `enter` (entra pela lateral até encostar na parede) →
`patrol` (sobe/desce pela borda, vira de direção) → `charge` (ancora, telegrafa
a linha de tiro com energia crescente) → dispara `EyeLaser` → cooldown e volta
a patrulhar.

Composição visual em camadas independentes (`stealth_fighter_pixel_map`): patas
superiores/inferiores caminham e se abrem no carregamento; a gema pulsa por glow.
Colisão por **máscara da silhueta** (não hitbox genérica).

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9); update via `update_in_context`
(§5); `draw` sem efeitos colaterais (§3); dano via `HitResult` (§8); laser
telegrafado emitido por buffer do contexto (`new_eye_lasers`).
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ..core.config import config as Config
from .enemy_hit_mixin import EnemyHitMixin
from .eye_laser import EyeLaser
from . import stealth_fighter_pixel_map as pm

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


def _lerp(a: pm.RGB, b: pm.RGB, t: float) -> pm.RGB:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class StealthFighter(EnemyHitMixin):
    CELL: int = 3
    SIZE: int = pm.PIXEL_COLS * CELL  # 45px
    # Mantidos p/ compat. com o spawner (cálculo de tamanho de entrada).
    W: int = SIZE
    H: int = SIZE

    HEALTH: int = 18          # vida baixa: alvo prioritário, morre rápido
    POINTS: int = 150

    WALL_INSET: float = 26.0  # distância do centro até a parede (gema visível)
    EDGE_MARGIN: float = 44.0  # limites da patrulha no eixo longo
    ENTER_SPEED: float = 195.0
    PATROL_SPEED: float = 125.0
    FLIP_INTERVAL = (1.1, 2.4)  # vira de direção espontaneamente

    ALIGN_TOL: float = 16.0   # "cruza a altura da nave" → janela de disparo
    CHARGE_DURATION: float = 0.95  # antecipação clara (dividida por aggressiveness)
    COOLDOWN: float = 1.15

    LASER_LIFETIME: float = 0.55
    LASER_MAX_W: int = 6

    LEG_WALK_AMP: float = 1.6
    LEG_WALK_SPEED: float = 7.0
    LEG_OPEN: float = CELL * 1.7

    _explosion_size_killed: int = 22
    _explosion_size_hit: int = 8

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        self.cell = self.CELL
        self.w = self.SIZE
        self.h = self.SIZE
        self.x = float(x)
        self.y = float(y)
        self.side_scroll = side_scroll
        self._top_down = not side_scroll

        self.dead = False
        self.health = self.HEALTH
        self.active = True
        self.hit_timer = 0.0
        # Entra parcialmente fora da tela pela lateral: isenta da limpeza de
        # off-screen até encostar na parede (§5: gate por class/instance attr).
        self.offscreen_cull_exempt = True

        self._aggr = max(0.5, aggressiveness_multiplier)

        sw, sh = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        # Eixo da parede (normal à borda em que escala) vs. eixo de patrulha.
        #   top-down  → parede em X (laterais), patrulha em Y, laser horizontal.
        #   side-scroll → parede em Y (topo/base), patrulha em X, laser vertical.
        self._wall_extent = sw if self._top_down else sh
        self._patrol_lo = self.EDGE_MARGIN
        self._patrol_hi = (sh if self._top_down else sw) - self.EDGE_MARGIN

        # Lado da parede decidido pela posição de spawn (perto de qual borda).
        self._wall_high = self._wall_coord() > self._wall_extent * 0.5
        self._dock = (
            self._wall_extent - self.WALL_INSET if self._wall_high else self.WALL_INSET
        )

        self.state = "enter"
        self._vdir = random.choice([-1.0, 1.0])
        self._flip_timer = random.uniform(*self.FLIP_INTERVAL)
        self._cooldown_timer = random.uniform(0.0, 0.6)
        self._charge_timer = 0.0
        self.charge_p = 0.0
        self._fire_flash = 0.0
        self._anim = random.uniform(0.0, math.tau)
        # Laser em voo (estado "firing"): a sentinela fica ancorada até ele
        # terminar todo o ciclo (disparo + dissipação). Safety evita travar
        # caso o laser suma por outro caminho.
        self._active_laser: EyeLaser | None = None
        self._firing_safety = 0.0

    # ── Geometria / orientação ──────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _set_center(self, cx: float, cy: float) -> None:
        self.x = cx - self.w / 2
        self.y = cy - self.h / 2

    def _wall_coord(self) -> float:
        cx, cy = self._center()
        return cx if self._top_down else cy

    def _patrol_coord(self) -> float:
        cx, cy = self._center()
        return cy if self._top_down else cx

    def _set_wall_patrol(self, wall: float, patrol: float) -> None:
        if self._top_down:
            self._set_center(wall, patrol)
        else:
            self._set_center(patrol, wall)

    def collision_circle(self) -> tuple[float, float, float]:
        # Disco justo em torno da gema/chassi (broadphase; a máscara faz o fino).
        cx, cy = self._center()
        return cx, cy, self.w * 0.30

    def get_collision_mask_data(
        self,
    ) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        """Colisão pixel-perfect pela silhueta (§8): respeita gema + estruturas."""
        if self.dead:
            return None
        return pm.build_collision_mask(self.cell), (int(self.x), int(self.y))

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        lasers = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if lasers:
            ctx.new_eye_lasers.extend(lasers)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[EyeLaser] | None:
        if dt <= 0.0:
            return None

        self._anim += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self._fire_flash > 0.0:
            self._fire_flash = max(0.0, self._fire_flash - dt)
        if self._cooldown_timer > 0.0:
            self._cooldown_timer = max(0.0, self._cooldown_timer - dt)

        wall = self._wall_coord()
        patrol = self._patrol_coord()
        player_patrol = player_y if self._top_down else player_x
        emitted: List[EyeLaser] | None = None

        if self.state == "enter":
            if wall < self._dock:
                wall = min(self._dock, wall + self.ENTER_SPEED * dt)
            else:
                wall = max(self._dock, wall - self.ENTER_SPEED * dt)
            if abs(wall - self._dock) < 1.5:
                wall = self._dock
                self.offscreen_cull_exempt = False
                self.state = "patrol"

        elif self.state == "patrol":
            wall = self._dock  # cola na parede
            # Cruzou a altura da nave e o canhão está pronto → PARA e carrega
            # (sem deslocar neste frame: alinhou, ancorou, depois carrega).
            if (
                self._cooldown_timer <= 0.0
                and abs(patrol - player_patrol) < self.ALIGN_TOL
            ):
                self.state = "charge"
                self._charge_timer = self.CHARGE_DURATION / self._aggr
                self.charge_p = 0.0
            else:
                patrol += self._vdir * self.PATROL_SPEED * dt
                # Vira nas bordas da patrulha ou por timer espontâneo.
                if patrol <= self._patrol_lo:
                    patrol = self._patrol_lo
                    self._vdir = 1.0
                elif patrol >= self._patrol_hi:
                    patrol = self._patrol_hi
                    self._vdir = -1.0
                self._flip_timer -= dt
                if self._flip_timer <= 0.0:
                    self._vdir = -self._vdir
                    self._flip_timer = random.uniform(*self.FLIP_INTERVAL)

        elif self.state == "charge":
            wall = self._dock  # ancora durante o carregamento
            self._charge_timer -= dt
            total = self.CHARGE_DURATION / self._aggr
            self.charge_p = 1.0 - max(0.0, self._charge_timer) / total
            if self._charge_timer <= 0.0:
                emitted = self._fire()
                self._active_laser = emitted[0] if emitted else None
                self.charge_p = 0.0
                self._fire_flash = 0.14
                # Permanece comprometida com o ataque: ancorada até o laser
                # concluir disparo + dissipação. Safety = vida + fade + folga.
                self._firing_safety = (
                    self.LASER_LIFETIME + EyeLaser.FADE_DURATION + 1.0
                )
                self.state = "firing"

        elif self.state == "firing":
            wall = self._dock  # segue ancorada durante todo o ciclo do laser
            self._firing_safety -= dt
            laser_done = self._active_laser is None or self._active_laser.dead
            if laser_done or self._firing_safety <= 0.0:
                self._active_laser = None
                self._cooldown_timer = self.COOLDOWN
                self.state = "patrol"

        self._set_wall_patrol(wall, patrol)
        return emitted

    def _laser_endpoints(self) -> tuple[float, float, float, float]:
        """(ox, oy, tx, ty): da gema até a borda oposta, atravessando a arena."""
        cx, cy = self._center()
        if self._top_down:
            tx = -28.0 if self._wall_high else Config.SCREEN_WIDTH + 28.0
            return cx, cy, tx, cy
        ty = -28.0 if self._wall_high else Config.SCREEN_HEIGHT + 28.0
        return cx, cy, cx, ty

    def _fire(self) -> List[EyeLaser]:
        ox, oy, tx, ty = self._laser_endpoints()
        return [
            EyeLaser(
                ox, oy, tx, ty,
                max_w=self.LASER_MAX_W,
                lifetime=self.LASER_LIFETIME,
                owner=self,  # morre junto com a sentinela (sem laser órfão)
            )
        ]

    # ── Dano / morte ────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        layers = pm.build_layers(self.cell)
        bx, by = int(self.x), int(self.y)

        walk = math.sin(self._anim * self.LEG_WALK_SPEED) * self.LEG_WALK_AMP
        # Patas abrem ao carregar e seguem abertas durante o disparo/dissipação
        # (postura de "ancorada e comprometida com o ataque").
        open_amt = self.LEG_OPEN if self.state == "firing" else self.charge_p * self.LEG_OPEN
        upper_dy = int(-open_amt + walk)
        lower_dy = int(open_amt - walk)

        # Patas atrás do corpo; corpo e gema por cima.
        surface.blit(layers["lower_legs"], (bx, by + lower_dy))
        surface.blit(layers["upper_legs"], (bx, by + upper_dy))

        chassis = layers["chassis"]
        gem = layers["gem"]
        if self.hit_timer > 0.0:
            chassis = chassis.copy()
            chassis.fill((150, 150, 160), special_flags=pygame.BLEND_RGB_ADD)
            gem = gem.copy()
            gem.fill((150, 150, 160), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(chassis, (bx, by))
        surface.blit(gem, (bx, by))

        self._draw_gem_glow(surface, bx, by)
        self._draw_accents(surface, bx, by, upper_dy, lower_dy)

        if self.state == "charge":
            self._draw_telegraph(surface)

    def _draw_gem_glow(self, surface: pygame.Surface, bx: int, by: int) -> None:
        pulse = 0.5 + 0.5 * math.sin(self._anim * 5.0)
        core_t = min(1.0, pulse * 0.55 + self.charge_p)
        col = self.cell
        ccol, crow = pm.CORE_CELL
        gx = int(bx + (ccol + 0.5) * col)
        gy = int(by + (crow + 0.5) * col)
        flash = self._fire_flash > 0.0
        color = (255, 255, 255) if flash else _lerp(pm.GEM_GLOW_DIM, pm.GEM_GLOW, core_t)
        radius = int(col * 2 + col * 3.5 * core_t + (col * 5 if flash else 0))
        glow = pm.get_glow(radius, color)
        surface.blit(
            glow, (gx - radius, gy - radius), special_flags=pygame.BLEND_RGBA_ADD
        )
        # Anel de energia durante o carregamento (telegrafa "vai disparar").
        if self.charge_p > 0.0:
            ring_r = int(col * 2.5 + col * 3.0 * (0.4 + 0.6 * pulse) * self.charge_p)
            ring_col = _lerp(pm.GEM_GLOW_DIM, pm.GEM_GLOW, self.charge_p)
            pygame.draw.circle(surface, ring_col, (gx, gy), max(2, ring_r), 1)

    def _draw_accents(
        self, surface: pygame.Surface, bx: int, by: int, upper_dy: int, lower_dy: int
    ) -> None:
        flick = 0.5 + 0.5 * math.sin(self._anim * 12.0)
        color = _lerp((60, 110, 130), pm.ACCENT_GLOW, 0.45 + 0.55 * flick)
        col = self.cell
        ar = int(col * 1.4)
        glow = pm.get_glow(ar, color)
        mid = pm.PIXEL_ROWS // 2
        for c, r in pm.ACCENT_CELLS:
            dy = upper_dy if r < mid else lower_dy
            gx = int(bx + (c + 0.5) * col)
            gy = int(by + (r + 0.5) * col + dy)
            surface.blit(
                glow, (gx - ar, gy - ar), special_flags=pygame.BLEND_RGBA_ADD
            )

    def _draw_telegraph(self, surface: pygame.Surface) -> None:
        ox, oy, tx, ty = self._laser_endpoints()
        p = self.charge_p
        # Linha de mira fina, intensificando com o carregamento.
        line_col = _lerp((50, 24, 80), pm.GEM_GLOW, p)
        width = 1 if p < 0.6 else 2
        pygame.draw.line(
            surface, line_col, (int(ox), int(oy)), (int(tx), int(ty)), width
        )
        # Faísca correndo pela linha em direção ao alvo (leitura do disparo).
        spark = (int(ox + (tx - ox) * p), int(oy + (ty - oy) * p))
        pygame.draw.circle(surface, (255, 255, 255), spark, max(1, int(2 + 2 * p)))
