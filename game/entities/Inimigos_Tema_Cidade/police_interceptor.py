"""Police Interceptor — "O Perseguidor" do bioma CITY.

Viatura aérea pesada com padrão **"Patrol & Strike"**: flutua preguiçosamente em
patrulha (deriva lenta para a esquerda + leve serpenteado vertical) varrendo um
radar em cone (mecânica, sem visual). Quando o jogador é **pego no cone**, ela
**estanca** (~0.3s), **vira a frente em direção ao jogador** (telegraph da
intenção) e dispara um **dash violento** na direção encarada; depois desacelera,
recupera e volta a patrulhar. Nasce em **duplas sincronizadas** ("Squad Pairs"):
o radar de um pega o jogador e a `InterceptorSquad` **arma um bote conjunto** —
os dois pinçam de lados opostos. Sobrevivente de uma dupla fica em **modo solo**
(radar maior, cooldown menor).

A turbina é única (foguete) e renderiza uma **chama de partículas em duas
camadas** (`TurbineFlame`: núcleo amarelo-claro + envelope azul), saindo do bocal
traseiro na direção oposta ao nariz.

Morte **"Crash & Burn"**: não explode na hora — o EntityManager dispara o efeito
`PoliceCrash` (via `triggers_special_death`), que faz o destroço girar, cair em
diagonal soltando fumaça negra e estourar embaixo numa labareda. Tudo cosmético
(sem dano — os estilhaços são meramente visuais).

Contratos (convenções do projeto): §5 update polimórfico via `update_in_context`; §3 `draw`
só lê estado (timers/pulso/heading/chama alimentados pelo update); §8 dano via
`HitResult`; §11 `aggressiveness_multiplier` propagado até velocidade/cadência.
A coordenação da dupla mora na `InterceptorSquad` (§1: sem ler privado do irmão).
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .police_interceptor_pixel_map import (
    LIGHT_CELLS,
    LIGHT_NEON,
    LIGHT_NEON_DIM,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_interceptor_surface,
)
from .turbine_flame import TurbineFlame

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult
    from .interceptor_squad import InterceptorSquad


def _lerp_angle(cur: float, target: float, t: float) -> float:
    """Interpola ângulos (graus) pelo caminho mais curto."""
    d = ((target - cur + 180.0) % 360.0) - 180.0
    return cur + d * t


class PoliceInterceptor(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 76px (eixo maior)

    HEALTH: int = 70
    POINTS: int = 230

    # ── Patrulha (deriva preguiçosa) ────────────────────────────────────────
    PATROL_SPEED: float = 78.0  # cruzeiro lento para a esquerda
    PATROL_ACCEL: float = 4.0  # ganho da aproximação de velocidade (1/s)
    WEAVE_AMP: float = 46.0
    EDGE_MARGIN: float = 26.0
    EXIT_MARGIN: float = 70.0

    # ── Radar em cone (mecânica; sem desenho) ───────────────────────────────
    CONE_RANGE: float = 420.0  # alcance da detecção
    CONE_HALF_ANGLE: float = math.radians(25.0)  # meia-abertura do cone
    SWEEP_AMP: float = math.radians(34.0)  # amplitude da varredura vertical
    SWEEP_FREQ: float = 1.15  # rad/s da varredura
    SOLO_RANGE_MULT: float = 1.18  # radar maior quando solo (mais agressivo)
    SOLO_COOLDOWN_MULT: float = 0.6

    # ── Strike ──────────────────────────────────────────────────────────────
    LOCK_TIME: float = 0.3  # "estanca" + vira a frente antes do dash (telegraph)
    DASH_SPEED: float = 660.0  # investida violenta
    DASH_TIME: float = 0.42
    RECOVER_TIME: float = 0.4
    COOLDOWN: float = 1.7  # descanso (modo solo) antes de poder atacar de novo

    _explosion_size_hit: int = 12

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        patrol_bias: float = 0.0,
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

        self.vx: float = -self.PATROL_SPEED
        self.vy: float = 0.0

        # Coordenação da dupla (atribuída pela InterceptorSquad no spawn).
        self.squad: "InterceptorSquad | None" = None

        # Lane vertical da patrulha + viés de cruzamento da dupla (Squad Pairs):
        # bias>0 desce, bias<0 sobe — as duas unidades da dupla recebem sinais
        # opostos, então se cruzam ao atravessar a tela.
        self.home: float = self.y + self.h / 2
        self.patrol_bias: float = patrol_bias
        self.weave_phase: float = random.uniform(0.0, math.tau)
        self.weave_freq: float = random.uniform(1.0, 1.6)
        self.scan_phase: float = random.uniform(0.0, math.tau)  # varredura do radar

        self.state: str = "patrol"
        self.lock_timer: float = 0.0
        self.dash_timer: float = 0.0
        self.recover_timer: float = 0.0
        self.cooldown_timer: float = self.COOLDOWN * 0.5  # carência inicial (solo)
        self.dash_dir: Tuple[float, float] = (-1.0, 0.0)

        # Render: heading (graus pygame; 0 = nariz à esquerda) e chama de turbina.
        self.render_deg: float = 0.0
        self.flame: TurbineFlame = TurbineFlame()

        # Animação (alimentada pelo update; lida pelo draw — §3).
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0
        self.turbine_flare: float = 0.0  # 0..1, sobe no lock/dash (intensidade da chama)

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.40

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _is_solo(self) -> bool:
        return self.squad is None or self.squad.solo

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if self.squad is not None:
            self.squad.tick(self, ctx.sdt)

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        if dt <= 0.0:
            return

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self.cooldown_timer > 0.0:
            self.cooldown_timer = max(0.0, self.cooldown_timer - dt)

        cx, cy = self._center()

        if self.state == "patrol":
            self._update_patrol(dt, cx, cy, player_x, player_y)
        elif self.state == "lock":
            self._update_lock(dt, player_x, player_y)
        elif self.state == "dash":
            self._update_dash(dt)
        else:  # recover
            self._update_recover(dt)

        self.x += self.vx * dt
        self.y += self.vy * dt

        self._apply_vertical_bounce()
        self._check_exit()

        # Heading (vira a frente p/ o alvo no lock/dash) + chama de partículas.
        self._update_render(dt, player_x, player_y)

    def _update_patrol(
        self, dt: float, cx: float, cy: float, player_x: float, player_y: float
    ) -> None:
        self.turbine_flare = max(0.0, self.turbine_flare - dt * 2.0)
        self.scan_phase += self.SWEEP_FREQ * dt

        # Lane faz random-walk lento + viés de cruzamento da dupla.
        self.home += self.patrol_bias * 40.0 * dt
        self.home = self._clamp_home(self.home)

        self.weave_phase += self.weave_freq * dt
        weave = math.sin(self.weave_phase) * self.WEAVE_AMP
        target_v_lane = (self.home + weave - cy) * 2.2

        # Aproxima as velocidades suavemente (deriva preguiçosa para a esquerda).
        k = min(1.0, dt * self.PATROL_ACCEL)
        self.vx += (-self.PATROL_SPEED - self.vx) * k
        self.vy += (target_v_lane - self.vy) * min(1.0, dt * 6.0)

        # Radar pega o jogador?
        caught = self._player_in_cone(player_x, player_y)

        if self._is_solo():
            # Solo: o próprio radar dispara o bote (cooldown individual).
            if caught and self.cooldown_timer <= 0.0:
                self._begin_lock()
        else:
            squad = self.squad
            assert squad is not None
            # Pincer: quem pega arma o bote; os dois aderem enquanto a janela
            # estiver aberta (sincronia) — mesmo quem não enxergou o alvo.
            if caught and squad.can_arm():
                squad.arm()
            if squad.poll():
                self._begin_lock()

    def _begin_lock(self) -> None:
        if self.state != "patrol":
            return
        self.state = "lock"
        self.lock_timer = self.LOCK_TIME / max(0.5, self.aggressiveness_multiplier)

    def _update_lock(self, dt: float, player_x: float, player_y: float) -> None:
        # Estanca: freia rápido e telegrafa (turbina acendendo + virando a frente).
        self.vx *= 1.0 - min(1.0, dt * 8.0)
        self.vy *= 1.0 - min(1.0, dt * 8.0)
        self.turbine_flare = min(1.0, self.turbine_flare + dt * 4.0)

        self.lock_timer -= dt
        if self.lock_timer <= 0.0:
            cx, cy = self._center()
            dx, dy = player_x - cx, player_y - cy
            d = math.hypot(dx, dy) or 1.0
            self.dash_dir = (dx / d, dy / d)
            speed = self.DASH_SPEED * (0.85 + 0.3 * self.aggressiveness_multiplier)
            self.vx = self.dash_dir[0] * speed
            self.vy = self.dash_dir[1] * speed
            self.state = "dash"
            self.dash_timer = self.DASH_TIME

    def _update_dash(self, dt: float) -> None:
        self.turbine_flare = 1.0
        self.dash_timer -= dt
        if self.dash_timer <= 0.0:
            self.state = "recover"
            self.recover_timer = self.RECOVER_TIME

    def _update_recover(self, dt: float) -> None:
        self.turbine_flare = max(0.0, self.turbine_flare - dt * 1.5)
        # Desacelera o ímpeto do dash de volta ao cruzeiro.
        self.vx *= 1.0 - min(1.0, dt * 3.0)
        self.vy *= 1.0 - min(1.0, dt * 3.0)
        self.recover_timer -= dt
        if self.recover_timer <= 0.0:
            self.state = "patrol"
            mult = self.SOLO_COOLDOWN_MULT if self._is_solo() else 1.0
            self.cooldown_timer = self.COOLDOWN * mult
            _, cy = self._center()
            self.home = self._clamp_home(cy)

    def _clamp_home(self, value: float) -> float:
        lo = self.EDGE_MARGIN + self.h / 2
        hi = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2
        return max(lo, min(hi, value))

    def _apply_vertical_bounce(self) -> None:
        top = self.EDGE_MARGIN
        bottom = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h
        if self.y < top:
            self.y = top
            self.vy = abs(self.vy) * 0.5
        elif self.y > bottom:
            self.y = bottom
            self.vy = -abs(self.vy) * 0.5

    def _check_exit(self) -> None:
        # Patrulha deriva para a esquerda; some ao sair de cena por lá (ou se
        # o dash a jogar para muito fora pela direita).
        if self.x + self.w < -self.EXIT_MARGIN:
            self.dead = True
        elif self.x > Config.SCREEN_WIDTH + self.EXIT_MARGIN:
            self.dead = True

    # ── Heading + chama (render alimentado pelo update — §3) ─────────────────
    @staticmethod
    def _aim_deg(dx: float, dy: float) -> float:
        # Graus pygame p/ o nariz (que aponta -x por padrão) encarar (dx, dy).
        return math.degrees(math.atan2(-dy, dx)) + 180.0

    def _update_render(self, dt: float, player_x: float, player_y: float) -> None:
        cx, cy = self._center()
        if self.state == "lock":
            target = self._aim_deg(player_x - cx, player_y - cy)
            t = min(1.0, dt * 12.0)  # vira rápido dentro do windup
        elif self.state == "dash":
            target = self._aim_deg(self.dash_dir[0], self.dash_dir[1])
            t = min(1.0, dt * 16.0)
        else:  # patrol/recover: nariz volta a apontar à esquerda
            target = 0.0
            t = min(1.0, dt * 5.0)
        self.render_deg = _lerp_angle(self.render_deg, target, t)

        # Forward a partir do heading; escapamento sai pela traseira (oposto).
        rad = math.radians(self.render_deg)
        fwd_x, fwd_y = -math.cos(rad), math.sin(rad)
        ex_x, ex_y = -fwd_x, -fwd_y
        nozzle_x = cx + ex_x * (self.w * 0.45)
        nozzle_y = cy + ex_y * (self.w * 0.45)
        intensity = max(0.2, self.turbine_flare)  # chama-piloto sempre acesa
        self.flame.update(dt, nozzle_x, nozzle_y, ex_x, ex_y, intensity)

    # ── Radar em cone (detecção; sem desenho) ────────────────────────────────
    def _cone_range(self) -> float:
        return self.CONE_RANGE * (self.SOLO_RANGE_MULT if self._is_solo() else 1.0)

    def _scan_dir(self) -> float:
        # Aponta para a frente (esquerda, -x = π) varrendo na vertical.
        return math.pi + math.sin(self.scan_phase) * self.SWEEP_AMP

    def _player_in_cone(self, px: float, py: float) -> bool:
        cx, cy = self._center()
        dx, dy = px - cx, py - cy
        dist = math.hypot(dx, dy)
        if dist < 1.0 or dist > self._cone_range():
            return False
        ang = math.atan2(dy, dx)
        diff = abs((ang - self._scan_dir() + math.pi) % math.tau - math.pi)
        return diff <= self.CONE_HALF_ANGLE

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            # explosion_size=0: o "Crash & Burn" (via triggers_special_death)
            # substitui a explosão imediata — o destroço cai e estoura depois.
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=0,
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=True,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

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

        # 1. Chama de partículas (atrás do chassi).
        self.flame.draw(surface)

        # 2. Chassi — rotacionado para encarar o alvo no lock/dash. BLEND_RGB_ADD
        # no flash preserva o alpha dos cantos transparentes (ver nota no City Drone).
        img = build_interceptor_surface(cell)
        if self.hit_timer > 0.0:
            img = img.copy()
            img.fill((210, 210, 210), special_flags=pygame.BLEND_RGB_ADD)
        if abs(self.render_deg) > 0.5:
            rot = pygame.transform.rotate(img, self.render_deg)
            surface.blit(rot, rot.get_rect(center=(int(cx), int(cy))))
        else:
            surface.blit(img, (int(self.x), int(self.y)))

        # 3. Barra de luz azul piscando (posições acompanham a rotação do chassi).
        strobe = 0.5 + 0.5 * math.sin(self.pulse * 11.0)
        flare = self.turbine_flare
        lcol = pal.lerp(LIGHT_NEON_DIM, LIGHT_NEON, 0.3 + 0.7 * max(strobe, flare))
        lr = int(cell * (1.0 + 0.6 * strobe))
        rad = math.radians(self.render_deg)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        for c, r in LIGHT_CELLS:
            ox = (c + 0.5) * cell - self.w / 2
            oy = (r + 0.5) * cell - self.h / 2
            gx = int(cx + ox * cos_r + oy * sin_r)
            gy = int(cy - ox * sin_r + oy * cos_r)
            self._blit_glow(surface, gx, gy, lr, lcol)

        # 4. Telegraph do bote: anel de aviso encolhendo em volta do alvo travado.
        if self.state == "lock":
            self._draw_lock_telegraph(surface)

    def _draw_lock_telegraph(self, surface: pygame.Surface) -> None:
        cx, cy = self._center()
        denom = self.LOCK_TIME / max(0.5, self.aggressiveness_multiplier)
        p = 1.0 - max(0.0, self.lock_timer) / denom if denom > 0 else 1.0
        ring_r = int(self.w * (0.9 - 0.4 * p))
        if ring_r > 2:
            pygame.draw.circle(
                surface, pal.TOXIC_ORANGE, (int(cx), int(cy)), ring_r, 1
            )
