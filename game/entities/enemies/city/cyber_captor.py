"""Cyber-Captor — "A Armadilha de Energia" do bioma CITY.

Esfera mecânica cercada por **anéis orbitais** (desenhados no draw). Não desce:
**orbita um ponto fixo** (`_orbit`, ancorado no alto da tela) e projeta um
**raio de energia** que tenta **prender o jogador** o maior tempo possível. O
raio tem um **ponto de trava** que persegue o jogador com velocidade limitada
(`LOCK_SPEED`); enquanto o jogador é alcançado, drena vida (dano periódico). O
jogador escapa **correndo mais rápido que a trava** (`LOCK_SPEED`), que então fica
para trás e perde a conexão. O Captor ataca em ciclo (aim→beam→cooldown).

Spawn **"Shadow Support"**: nasce próximo/atrás de um inimigo maior (escondido),
escolhido pelo `EnemySpawner`. Morte **"EMP Discharge"**: o EntityManager dispara
o efeito `CaptorEMP` (onda amarela) e **neutraliza os projéteis inimigos próximos**.

O dano contínuo do raio é entregue por `ctx.new_area_blasts` (mesmo roteador de
dano de área da explosão do CyberTank / mina), drenado pelo EntityManager para
`area_blasts` e aplicado à nave pela cena. Contratos (convenções do projeto): §5 update
polimórfico; §3 draw só lê estado; §8 dano via HitResult; §11 aggressiveness.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

import pygame

from ....core.config import config as Config
from .._shared.enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .cyber_captor_pixel_map import (
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_sphere_surface,
)

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult

_BEAM: pal.RGB = pal.ELECTRIC_BLUE
_BEAM_HOT: pal.RGB = (215, 245, 255)


class CyberCaptor(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 60px

    HEALTH: int = 90
    POINTS: int = 260

    # ── Órbita (não desce; orbita um ponto fixo) ─────────────────────────────
    ORBIT_RX: float = 62.0
    ORBIT_RY: float = 44.0
    ORBIT_SPEED: float = 0.85  # rad/s
    ENTER_DURATION: float = 0.8  # tempo de "deslize" do spawn até a órbita

    # ── Raio (armadilha de energia) ──────────────────────────────────────────
    LOCK_SPEED: float = 300.0  # velocidade com que a trava persegue o jogador
    CAPTURE: float = 38.0  # quão perto a trava precisa estar p/ "prender"
    AIM_TIME: float = 0.7  # telegraph antes do raio
    BEAM_TIME: float = 2.4  # duração do raio conectado
    COOLDOWN: float = 1.6
    DAMAGE_INTERVAL: float = 0.28  # cadência do dreno enquanto preso

    _explosion_size_hit: int = 10
    EMP_RADIUS: int = 150  # raio que neutraliza projéteis inimigos na morte

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        anchor: Tuple[float, float] | None = None,
    ) -> None:
        self.side_scroll: bool = side_scroll
        self.cell: int = self.CELL
        self.w: int = PIXEL_COLS * self.cell
        self.h: int = PIXEL_ROWS * self.cell

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health: int = self.HEALTH
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        # Ponto fixo que orbita (alto da tela por padrão).
        ax, ay = anchor if anchor is not None else (x, y)
        self.anchor_x: float = max(
            self.ORBIT_RX + 20.0, min(Config.SCREEN_WIDTH - self.ORBIT_RX - 20.0, ax)
        )
        self.anchor_y: float = max(
            self.ORBIT_RY + 40.0, min(Config.SCREEN_HEIGHT * 0.45, ay)
        )
        self.orbit_angle: float = random.uniform(0.0, math.tau)
        # Deslize de entrada baseado em TEMPO (o ponto de órbita se move, então
        # não dá pra esperar "encostar" nele — senão `entering` nunca terminava).
        self.spawn_x: float = float(x)
        self.spawn_y: float = float(y)
        self.enter_t: float = 0.0
        self.entering: bool = True

        self.state: str = "cooldown"
        self.aim_timer: float = 0.0
        self.beam_timer: float = 0.0
        self.cooldown_timer: float = self.COOLDOWN * 0.6
        self.dmg_timer: float = 0.0
        self.lock_x: float = x
        self.lock_y: float = y
        self.connected: bool = False

        self.pulse: float = random.uniform(0.0, math.tau)
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
        blast = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if blast is not None:
            ctx.new_area_blasts.append(blast)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> Tuple[float, float, float] | None:
        if dt <= 0.0:
            return None

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Posição na órbita (ponto fixo no alto da tela).
        self.orbit_angle += self.ORBIT_SPEED * dt
        ox = self.anchor_x + math.cos(self.orbit_angle) * self.ORBIT_RX
        oy = self.anchor_y + math.sin(self.orbit_angle) * self.ORBIT_RY
        target_x = ox - self.w / 2
        target_y = oy - self.h / 2
        if self.entering:
            # Lerp temporal (smoothstep) do spawn até o ponto de órbita atual;
            # termina sempre em ENTER_DURATION e faz o handoff suave para a órbita.
            self.enter_t += dt
            p = min(1.0, self.enter_t / self.ENTER_DURATION)
            e = p * p * (3.0 - 2.0 * p)
            self.x = self.spawn_x + (target_x - self.spawn_x) * e
            self.y = self.spawn_y + (target_y - self.spawn_y) * e
            if p >= 1.0:
                self.entering = False
        else:
            self.x, self.y = target_x, target_y

        cx, cy = self._center()
        blast: Tuple[float, float, float] | None = None

        if self.state == "cooldown":
            self.connected = False
            self.cooldown_timer -= dt
            if self.cooldown_timer <= 0.0 and not self.entering:
                # Ataca em ciclo (sem gate de alcance): o dano só acontece se a
                # trava alcançar o jogador — ele foge correndo mais que a trava.
                self.state = "aim"
                self.aim_timer = self.AIM_TIME
                self.lock_x, self.lock_y = cx, cy
        elif self.state == "aim":
            self.lock_x, self.lock_y = cx, cy  # raio "nasce" no captor
            self.aim_timer -= dt
            if self.aim_timer <= 0.0:
                self.state = "beam"
                self.beam_timer = self.BEAM_TIME
                self.dmg_timer = 0.0
        else:  # beam
            self.beam_timer -= dt
            # Trava persegue o jogador com velocidade limitada (dá janela de fuga).
            dx, dy = player_x - self.lock_x, player_y - self.lock_y
            d = math.hypot(dx, dy)
            step = self.LOCK_SPEED * dt
            if d <= step or d < 1e-6:
                self.lock_x, self.lock_y = player_x, player_y
            else:
                self.lock_x += dx / d * step
                self.lock_y += dy / d * step

            caught = (
                math.hypot(player_x - self.lock_x, player_y - self.lock_y) < self.CAPTURE
            )
            self.connected = caught
            self.dmg_timer -= dt
            if caught and self.dmg_timer <= 0.0:
                self.dmg_timer = self.DAMAGE_INTERVAL / max(0.5, self.aggressiveness_multiplier)
                blast = (self.lock_x, self.lock_y, self.CAPTURE * 0.7)

            if self.beam_timer <= 0.0:
                self.state = "cooldown"
                self.cooldown_timer = self.COOLDOWN
                self.connected = False

        return blast

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=0,  # a morte é a descarga EMP (special death)
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=True,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.dead = True
        return HitResult(
            killed=True,
            explosion_size=0,
            sound=hit_sounds.EXPLOSION_ALIEN,
            triggers_special_death=True,
        )

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
        cell = self.cell
        cx, cy = self._center()
        icx, icy = int(cx), int(cy)

        # Raio (atrás do corpo): telegraph na mira, feixe crepitante quando ativo.
        if self.state == "aim":
            self._draw_aim(surface, icx, icy)
        elif self.state == "beam":
            self._draw_beam(surface, icx, icy)

        # Anéis orbitais (elipses "achatadas" animadas → look 3D girando).
        self._draw_rings(surface, cx, cy)

        # Corpo-esfera (flash de hit com BLEND_RGB_ADD).
        base = build_sphere_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Núcleo azul pulsante (mais intenso ao mirar/conectar).
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 6.0)
        boost = 0.5 if self.state == "aim" else (1.0 if self.connected else 0.0)
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, min(1.0, pulse + boost))
        cr = int(cell * (1.6 + pulse) + cell * 2.0 * boost)
        for c, r in CORE_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                cr,
                core_col,
            )

    def _draw_rings(self, surface: pygame.Surface, cx: float, cy: float) -> None:
        cell = self.cell
        rad = self.w * 0.62
        for i in range(2):
            a = self.pulse * 2.2 + i * (math.pi / 2.0)
            squash = abs(math.sin(a))  # 0 (de perfil) .. 1 (de frente)
            col = pal.lerp(pal.ELECTRIC_BLUE_DIM, pal.ELECTRIC_BLUE, 0.35 + 0.65 * squash)
            if i == 0:
                rx, ry = rad, rad * (0.18 + 0.82 * squash)
            else:
                rx, ry = rad * (0.18 + 0.82 * squash), rad
            rx, ry = max(2.0, rx), max(2.0, ry)
            rect = pygame.Rect(int(cx - rx), int(cy - ry), int(rx * 2), int(ry * 2))
            pygame.draw.ellipse(surface, col, rect, max(2, int(cell * 0.5)))

    def _draw_aim(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        # Linha fina de mira até a trava + carga crescente (telegraph).
        p = 1.0 - max(0.0, self.aim_timer) / self.AIM_TIME
        col = pal.lerp((40, 80, 120), _BEAM, p)
        pygame.draw.line(surface, col, (icx, icy), (int(self.lock_x), int(self.lock_y)), 1)
        self._blit_glow(surface, icx, icy, int(self.cell * (1.5 + 3.0 * p)), _BEAM)

    def _draw_beam(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        lx, ly = int(self.lock_x), int(self.lock_y)
        # Feixe crepitante: linha quebrada com jitter (mais grossa/brilhante se preso).
        segs = 6
        prev = (icx, icy)
        flick = 0.5 + 0.5 * math.sin(self.pulse * 30.0)
        amp = (4.0 if self.connected else 2.0) + 3.0 * flick
        base_col = _BEAM_HOT if self.connected else _BEAM
        for k in range(1, segs + 1):
            t = k / segs
            mx = icx + (lx - icx) * t
            my = icy + (ly - icy) * t
            if k < segs:
                mx += random.uniform(-amp, amp)
                my += random.uniform(-amp, amp)
            width = max(2, int(self.cell * (0.9 if self.connected else 0.5)))
            pygame.draw.line(surface, base_col, prev, (int(mx), int(my)), width)
            prev = (int(mx), int(my))
        # Glow na origem e na trava.
        self._blit_glow(surface, icx, icy, int(self.cell * 2.2), _BEAM)
        cap_r = int(self.cell * (2.6 if self.connected else 1.6))
        self._blit_glow(surface, lx, ly, cap_r, _BEAM_HOT if self.connected else _BEAM)
