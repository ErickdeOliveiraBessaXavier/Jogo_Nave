"""Cyber Tank — "O Colosso Urbano" do bioma CITY.

Fortaleza móvel com padrão **"Juggernaut"**: avança **devagar e constante** para
a esquerda (entra pela direita no side-scroll), **imparável** — não toma recuo e
**não morre por contato** com a nave (só por dano).

Silhueta em **ampulheta horizontal** (ver `cyber_tank_pixel_map`): duas vagens
largas nas pontas, cintura estreita no centro com o reator. **Dois canhões**
integrados às pontas **giram para mirar** o jogador, cada um cobrindo a sua
metade (arco), e cospem plasma pesado (NeonBolt parametrizado). Esquerda =
**Gatling** (rajadas rápidas), direita = **Railcannon** (carrega, tiro forte).

Spawn **"Gatekeeper"** (sozinho) precedido por um **aviso** ("Heavy Unit
Incoming": som + chevrons na borda enquanto entra). Morte **"Structural
Failure"**: o EntityManager dispara `TankMeltdown` (via `triggers_special_death`)
— placas voam (estilhaços visuais) + poça de metal fundido neon.

Contratos (convenções do projeto): §5 update polimórfico via `update_in_context` (empurra
shells em `ctx.new_neon_bolts`); §3 `draw` só lê estado (timers/pulso/heading
alimentados pelo update); §8 dano via `HitResult`; §11 `aggressiveness_multiplier`
propaga até cadência/velocidade do tiro.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .cyber_tank_pixel_map import (
    CANNON_BARREL_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    MOUNT_OFFSET_X,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_cannon_surface,
    build_pod_surface,
)
from .neon_bolt import NeonBolt

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# Plasma das torres: núcleo claro + halo laranja (Gatling) / azul (Railcannon).
_SHELL_CORE: pal.RGB = (255, 236, 205)
_SHELL_GLOW: pal.RGB = pal.TOXIC_ORANGE
_RAIL_CORE: pal.RGB = (235, 250, 255)
_RAIL_GLOW: pal.RGB = pal.ELECTRIC_BLUE

# ── Seta-aviso (chevron pixel-art do telegraph de entrada) ───────────────────
_ARROW_COLS, _ARROW_ROWS = 11, 7
_arrow_cache: dict[int, pygame.Surface] = {}


def _build_warning_arrow(cell: int) -> pygame.Surface:
    """Chevron '>' em pixel-art (ponta p/ a direita = para a lateral/entrada),
    traço de 2px, sem contorno. Cacheado por `cell`. Sem glow/efeitos."""
    cached = _arrow_cache.get(cell)
    if cached is not None:
        return cached

    mid = _ARROW_ROWS // 2
    tip = _ARROW_COLS - 1  # ponta na coluna mais à direita
    surf = pygame.Surface((_ARROW_COLS * cell, _ARROW_ROWS * cell), pygame.SRCALPHA)
    for r in range(_ARROW_ROWS):
        c0 = tip - abs(r - mid)  # ponta no meio (col direita), abre p/ a esquerda
        for c in (c0, c0 - 1):  # 2px de espessura
            if 0 <= c < _ARROW_COLS:
                surf.fill(pal.TOXIC_ORANGE, (c * cell, r * cell, cell, cell))
    _arrow_cache[cell] = surf
    return surf


class _Turret:
    """Canhão de ponta: mira **sempre** o jogador. Fica num encaixe que orbita o
    centro junto com o giro do chassi (`off_x/off_y` é o encaixe em repouso)."""

    __slots__ = (
        "type",
        "off_x",
        "off_y",
        "angle",
        "fire_timer",
        "flash",
        "recoil",
        "charge",
        "burst_count",
    )

    def __init__(
        self, t_type: str, off_x: float, off_y: float, fire_timer: float
    ) -> None:
        self.type = t_type
        self.off_x = off_x
        self.off_y = off_y
        self.angle = math.pi  # apontando à esquerda no início
        self.fire_timer = fire_timer
        self.flash = 0.0  # 0..1, clarão do disparo (decai)
        self.recoil = 0.0  # 0..1, recuo visual do cano (decai)
        self.charge = 0.0  # 0..1, carga do Railcannon
        self.burst_count = 0  # tiros restantes da rajada (Gatling)


class CyberTank(EnemyHitMixin):
    CELL: int = 5  # colosso maior (25*5 = 125px de largura, 13*5 = 65px de altura)
    SIZE: int = PIXEL_COLS * CELL

    HEALTH: int = 1400  # Fortaleza móvel
    POINTS: int = 1500

    # ── Movimentação "Primal Aspid": predador inquieto que jockeia ────────────
    # Não atravessa a tela: entra, fica perto da zona de combate e reposiciona
    # constantemente em torno do jogador — mantém uma distância, busca ângulos,
    # faz pequenas correções e dardos ocasionais. Sensação de perseguição/opressão.
    ENTER_SPEED: float = 105.0  # voa pra dentro até a zona de combate
    ENTER_FRAC: float = 0.82  # x-centro (fração) onde passa a jockear
    STANDOFF_MIN: float = 365.0  # distância de combate preferida (faixa apertada)
    STANDOFF_MAX: float = 430.0
    MAX_SPEED: float = 135.0  # colosso pesado — reposiciona devagar, sem agilidade
    STEER_GAIN: float = 2.3  # ganho do steering até a posição desejada
    STEER_RESP: float = 3.6  # resposta da aceleração (1/s) — pesado/inerte
    JOCKEY_SPAN: float = 1.0  # rad (~57°): cone à direita do jogador onde paira
    RETARGET_MIN: float = 0.9  # correções de trajetória mais calmas/espaçadas
    RETARGET_MAX: float = 1.8
    DART_CHANCE: float = 0.12  # dardos raros (reposicionamento maior p/ ângulo)
    ZONE_X_MIN_FRAC: float = 0.33  # mantém-se à direita do jogador (não invade o canto)
    ZONE_X_MAX_FRAC: float = 0.93  # nem encosta na borda direita
    EDGE_MARGIN: float = 28.0
    BODY_SPIN_RATE: float = 0.7  # rad/s — a ampulheta gira no próprio eixo

    # ── Telegraph de entrada ("Heavy Unit Incoming") ─────────────────────────
    # Antes de surgir, um chevron grande entra pela borda direita e desliza até
    # o ponto de entrada — alerta clássico que cria expectativa segundos antes.
    WARNING_DURATION: float = 5.0  # antecipação: 5s de telegraph antes do tank
    WARNING_SOUND_TIME: float = 1.0  # som de aviso toca ~1s (depois só o visual)
    WARNING_ARROW_CELL: int = 6  # tamanho do pixel da seta pixel-art
    WARNING_EDGE_INSET: float = 30.0  # recuo da seta a partir da borda direita
    WARNING_SPIN_RATE: float = 4.0  # rad/s do giro no próprio eixo (ilusão 3D)
    WARNING_GROW_MIN: float = 0.45  # escala no início (mini boss distante)
    WARNING_GROW_MAX: float = 1.5  # escala ao fim (mini boss perto, prestes a surgir)

    # ── Canhões (miram sempre o jogador) ─────────────────────────────────────
    # Gatling (uma ponta): rajada rápida.
    GATLING_INTERVAL: float = 2.4
    GATLING_BURST: int = 5
    GATLING_BURST_GAP: float = 0.08
    # Railcannon (outra ponta): tiro pesado, carrega.
    RAIL_INTERVAL: float = 4.2
    RAIL_CHARGE_TIME: float = 1.2

    SHELL_SPEED: float = 290.0
    RAIL_SPEED: float = 540.0

    _explosion_size_hit: int = 18

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
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

        # Canhões integrados às duas pontas da ampulheta (encaixe em repouso no
        # eixo horizontal; orbitam o centro junto com o giro do chassi).
        mx = MOUNT_OFFSET_X * self.w
        self.turrets: List[_Turret] = [
            _Turret("GATLING", -mx, 0.0, self.GATLING_INTERVAL * 0.5),
            _Turret("RAILCANNON", +mx, 0.0, self.RAIL_INTERVAL),
        ]

        self.state: str = "warning"  # "warning" → "enter" → "dominate" (jockeying)
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.jockey_angle: float = random.uniform(-0.5, 0.5)  # ângulo à direita do alvo
        self.standoff: float = random.uniform(self.STANDOFF_MIN, self.STANDOFF_MAX)
        self.retarget_timer: float = 0.0

        # Telegraph de entrada (seta pixel-art + som de aviso por ~1s).
        self.warning_timer: float = 0.0
        self._warning_started: bool = False
        self._warning_sound_stopped: bool = False
        self.pulse: float = random.uniform(0.0, math.tau)
        self.body_spin: float = random.uniform(0.0, math.tau)  # giro contínuo
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        # Rect um pouco maior p/ abranger os canhões que projetam das pontas.
        pad = int(self.cell * 5)
        return pygame.Rect(
            int(self.x) - pad,
            int(self.y) - self.cell,
            self.w + pad * 2,
            self.h + self.cell * 2,
        )

    def collision_circle(self) -> Tuple[float, float, float]:
        # Círculo cobrindo a massa central do corpo (pontas/canhões projetam fora).
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.30

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def draws_offscreen(self) -> bool:
        """No telegraph o corpo está fora da borda, mas o chevron (desenhado em
        `draw`) precisa aparecer — pede ao EntityManager para ignorar o culling."""
        return self.state == "warning"

    def _mount_pos(self, t: "_Turret") -> Tuple[float, float]:
        """Posição do encaixe do canhão, orbitando o centro com o giro do chassi.
        Usa a mesma convenção de `pygame.transform.rotate(body_spin)` do draw."""
        cx, cy = self._center()
        rad = self.body_spin
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        mx = cx + t.off_x * cos_r + t.off_y * sin_r
        my = cy - t.off_x * sin_r + t.off_y * cos_r
        return mx, my

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        shells = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if shells:
            ctx.new_neon_bolts.extend(shells)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[NeonBolt] | None:
        if dt <= 0.0:
            return None

        self.pulse += dt
        self.body_spin = (self.body_spin + self.BODY_SPIN_RATE * dt) % math.tau
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # ── Telegraph: chevron + som de aviso, antes de o tank surgir. ──
        if self.state == "warning":
            self._update_warning(dt)
            self._idle_turrets(dt)
            return None

        # ── Movimentação: entra; depois jockeia em torno do jogador. ──
        if self.state == "enter":
            self.x -= self.ENTER_SPEED * dt
            cy = self.y + self.h / 2
            self.y = cy + (player_y - cy) * min(1.0, dt * 1.6) - self.h / 2
            if self.x + self.w / 2 <= self.ENTER_FRAC * Config.SCREEN_WIDTH:
                self.state = "dominate"
                self.retarget_timer = 0.0
            self._idle_turrets(dt)
            return None

        self._jockey(dt, player_x, player_y)
        return self._update_turrets(dt, player_x, player_y)

    def _update_warning(self, dt: float) -> None:
        """Telegraph de entrada: o aviso sonoro toca ~1s (depois para — só a seta
        visual continua). Ao fim da janela, o tank entra de fato em cena."""
        from ...systems import hit_sounds

        if not self._warning_started:
            self._warning_started = True
            hit_sounds.WARNING()  # loop no canal dedicado; parado abaixo após ~1s

        self.warning_timer += dt
        if (
            not self._warning_sound_stopped
            and self.warning_timer >= self.WARNING_SOUND_TIME
        ):
            self._warning_sound_stopped = True
            hit_sounds.STOP_WARNING()

        if self.warning_timer >= self.WARNING_DURATION:
            self.state = "enter"

    def _jockey(self, dt: float, player_x: float, player_y: float) -> None:
        """Reposiciona inquietamente em torno do jogador (estilo Primal Aspid):
        mantém uma distância à direita, corrige a trajetória sem parar e dá
        dardos ocasionais para um ângulo melhor — perseguição + controle de espaço."""
        # Correções de trajetória constantes (+ dardos ocasionais p/ novo ângulo).
        self.retarget_timer -= dt
        if self.retarget_timer <= 0.0:
            self.retarget_timer = random.uniform(self.RETARGET_MIN, self.RETARGET_MAX)
            if random.random() < self.DART_CHANCE:
                self.jockey_angle = random.uniform(-self.JOCKEY_SPAN, self.JOCKEY_SPAN)
                self.standoff = random.uniform(self.STANDOFF_MIN, self.STANDOFF_MAX)
            else:
                self.jockey_angle = max(
                    -self.JOCKEY_SPAN,
                    min(
                        self.JOCKEY_SPAN, self.jockey_angle + random.uniform(-0.3, 0.3)
                    ),
                )
                self.standoff = max(
                    self.STANDOFF_MIN,
                    min(self.STANDOFF_MAX, self.standoff + random.uniform(-35.0, 35.0)),
                )

        # Prioridade: MANTER A DISTÂNCIA. Corrige o raio no rumo atual (sem precisar
        # rodar em volta do jogador) e só desliza para o ângulo de jockey aos poucos
        # → distância consistente + reposicionamento lento (sem agilidade).
        cx, cy = self._center()
        bx, by = cx - player_x, cy - player_y
        cur_d = math.hypot(bx, by) or 1.0
        rad_x = player_x + (bx / cur_d) * self.standoff
        rad_y = player_y + (by / cur_d) * self.standoff
        ang = self.jockey_angle
        jx = player_x + math.cos(ang) * self.standoff
        jy = player_y + math.sin(ang) * self.standoff
        angular_pull = 0.18  # quão rápido desliza p/ o ângulo de jockey (baixo = calmo)
        dx = rad_x + (jx - rad_x) * angular_pull + math.sin(self.pulse * 3.1) * 5.0
        dy = rad_y + (jy - rad_y) * angular_pull + math.cos(self.pulse * 3.7) * 5.0

        # Mantém dentro da zona de combate (não atravessa nem sai da tela).
        xmin = self.ZONE_X_MIN_FRAC * Config.SCREEN_WIDTH
        xmax = self.ZONE_X_MAX_FRAC * Config.SCREEN_WIDTH
        lo = self.EDGE_MARGIN + self.h / 2
        hi = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2
        dx = max(xmin, min(xmax, dx))
        dy = max(lo, min(hi, dy))

        # Steering: acelera para a posição desejada (responsivo, mas suave).
        cx, cy = self._center()
        des_vx = max(-self.MAX_SPEED, min(self.MAX_SPEED, (dx - cx) * self.STEER_GAIN))
        des_vy = max(-self.MAX_SPEED, min(self.MAX_SPEED, (dy - cy) * self.STEER_GAIN))
        k = min(1.0, dt * self.STEER_RESP)
        self.vx += (des_vx - self.vx) * k
        self.vy += (des_vy - self.vy) * k

        ncx = max(xmin, min(xmax, cx + self.vx * dt))
        ncy = max(lo, min(hi, cy + self.vy * dt))
        self.x = ncx - self.w / 2
        self.y = ncy - self.h / 2

    def _idle_turrets(self, dt: float) -> None:
        # Enquanto entra: só decai os timers visuais (sem mirar/atirar).
        for t in self.turrets:
            if t.flash > 0.0:
                t.flash = max(0.0, t.flash - dt * 5.0)
            if t.recoil > 0.0:
                t.recoil = max(0.0, t.recoil - dt * 4.0)

    def _update_turrets(
        self, dt: float, player_x: float, player_y: float
    ) -> List[NeonBolt] | None:
        agg = max(0.5, self.aggressiveness_multiplier)
        shells: List[NeonBolt] | None = None

        for t in self.turrets:
            mx, my = self._mount_pos(t)
            # Sempre apontado para o jogador (sem arco, sem limite de giro).
            t.angle = math.atan2(player_y - my, player_x - mx)

            if t.flash > 0.0:
                t.flash = max(0.0, t.flash - dt * 5.0)
            if t.recoil > 0.0:
                t.recoil = max(0.0, t.recoil - dt * 4.0)

            t.fire_timer -= dt

            if t.type == "GATLING":
                if t.burst_count > 0:
                    if t.fire_timer <= 0.0:
                        if shells is None:
                            shells = []
                        shells.append(self._fire(t, mx, my))
                        t.burst_count -= 1
                        t.fire_timer = (
                            self.GATLING_BURST_GAP / agg
                            if t.burst_count > 0
                            else self.GATLING_INTERVAL / agg
                        )
                elif t.fire_timer <= 0.0:
                    t.burst_count = self.GATLING_BURST
                    t.fire_timer = 0.0
            else:  # RAILCANNON
                # Carga clampeada a 1.0 (antes crescia sem limite quando o timer
                # ficava negativo → "carregando pra sempre"). Dispara assim que o
                # timer zera — a mira já está sempre no jogador.
                t.charge = min(
                    1.0, max(0.0, 1.0 - t.fire_timer / self.RAIL_CHARGE_TIME)
                )
                if t.fire_timer <= 0.0:
                    if shells is None:
                        shells = []
                    shells.append(self._fire(t, mx, my))
                    t.fire_timer = self.RAIL_INTERVAL / agg
                    t.charge = 0.0

        return shells

    def _fire(self, t: _Turret, mx: float, my: float) -> NeonBolt:
        t.flash = 1.0
        t.recoil = 1.0
        barrel = CANNON_BARREL_CELLS * self.cell
        mux = mx + math.cos(t.angle) * barrel
        muy = my + math.sin(t.angle) * barrel
        agg = self.aggressiveness_multiplier
        if t.type == "GATLING":
            speed = self.SHELL_SPEED * (0.9 + 0.2 * agg)
            return NeonBolt(
                mux,
                muy,
                math.cos(t.angle) * speed,
                math.sin(t.angle) * speed,
                core=_SHELL_CORE,
                glow=_SHELL_GLOW,
                radius=5,
                glow_radius=14,
            )
        speed = self.RAIL_SPEED * (0.95 + 0.1 * agg)
        return NeonBolt(
            mux,
            muy,
            math.cos(t.angle) * speed,
            math.sin(t.angle) * speed,
            core=_RAIL_CORE,
            glow=_RAIL_GLOW,
            radius=9,
            glow_radius=26,
        )

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.06
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...entities.explosion import ExplosionType
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            # 1º a explosão NORMAL da nave (destrói a estrutura externa); o núcleo
            # azul fica e entra em colapso crítico via TankMeltdown (special death).
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=int(self.w * 0.9),
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_BOSS,
                triggers_special_death=True,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Juggernaut imparável: sobrevive ao contato (a nave é quem leva dano,
        # aplicado pela camada de colisão). Só solta faísca (killed=False).
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
        # Durante o telegraph, o tank ainda não está em cena: só o chevron.
        if self.state == "warning":
            self._draw_warning(surface)
            return

        cell = self.cell
        cx, cy = self._center()
        deg = math.degrees(self.body_spin)

        # 1 + 3. As DUAS metades da ampulheta (pods) GIRAM em torno do eixo,
        # 180° opostas, com um vão claro até o núcleo no meio. Flash de hit
        # com BLEND_RGB_ADD (preserva alpha dos cantos transparentes).
        pod = build_pod_surface(cell)
        if self.hit_timer > 0.0:
            pod = pod.copy()
            pod.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_ADD)
        for extra in (0.0, 180.0):
            rot = pygame.transform.rotate(pod, deg + extra)
            surface.blit(rot, rot.get_rect(center=(int(cx), int(cy))))

        # 2. Núcleo energético circular ESTÁTICO no centro — parte distinta,
        # separada das metades pelo vão. Energia = pulso + faíscas orbitando.
        self._draw_core(surface, cx, cy)

        # 4. Canhões nas pontas (orbitam com o giro), sempre mirando o jogador.
        for t in self.turrets:
            self._draw_turret(surface, t)

    def _draw_core(self, surface: pygame.Surface, cx: float, cy: float) -> None:
        cell = self.cell
        icx, icy = int(cx), int(cy)
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)

        # Halo de energia (aditivo) + orbe sólido com anel de contenção.
        self._blit_glow(
            surface, icx, icy, int(cell * 3.6 + cell * pulse), pal.ELECTRIC_BLUE
        )
        base_r = int(cell * 2.3)
        pygame.draw.circle(surface, pal.DEEP_SLATE, (icx, icy), base_r)
        pygame.draw.circle(surface, pal.OUTLINE, (icx, icy), base_r, 1)
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, pulse)
        pygame.draw.circle(surface, core_col, (icx, icy), int(cell * 1.5))
        pygame.draw.circle(
            surface, (235, 250, 255), (icx, icy), max(2, int(cell * 0.7))
        )

        # Faíscas de energia orbitando o núcleo (animação de energia, não de giro).
        for k in range(3):
            a = self.pulse * 2.4 + k * (math.tau / 3.0)
            ex = icx + int(math.cos(a) * cell * 2.0)
            ey = icy + int(math.sin(a) * cell * 2.0)
            self._blit_glow(surface, ex, ey, int(cell * 0.9), (200, 245, 255))

    def _draw_turret(self, surface: pygame.Surface, t: _Turret) -> None:
        cell = self.cell
        mx, my = self._mount_pos(t)
        ang = t.angle
        ca, sa = math.cos(ang), math.sin(ang)
        recoil_px = t.recoil * cell * 2.5

        # Pivô = centro do sprite do canhão; aplica recuo ao longo de -mira.
        cannon = build_cannon_surface(cell)
        rot = pygame.transform.rotate(cannon, -math.degrees(ang))
        pivot_x = mx - ca * recoil_px
        pivot_y = my - sa * recoil_px
        surface.blit(rot, rot.get_rect(center=(int(pivot_x), int(pivot_y))))

        barrel = CANNON_BARREL_CELLS * cell - recoil_px
        mux = mx + ca * barrel
        muy = my + sa * barrel

        # Railcannon: glow de carga crescente na boca + arcos elétricos.
        if t.type == "RAILCANNON" and t.charge > 0.1:
            self._blit_glow(
                surface, int(mux), int(muy), int(cell * 3.0 * t.charge), _RAIL_GLOW
            )
            if t.charge > 0.6:
                for _ in range(2):
                    back = random.uniform(0.3, 1.0) * barrel
                    ex = int(mx + ca * back + random.uniform(-4, 4))
                    ey = int(my + sa * back + random.uniform(-4, 4))
                    self._blit_glow(surface, ex, ey, int(cell * 1.3), (200, 255, 255))

        # Clarão do disparo na boca.
        if t.flash > 0.0:
            fcol = _SHELL_GLOW if t.type == "GATLING" else _RAIL_GLOW
            self._blit_glow(
                surface, int(mux), int(muy), int(cell * (2.5 + 6.0 * t.flash)), fcol
            )

    def _draw_warning(self, surface: pygame.Surface) -> None:
        """Seta pixel-art na lateral direita girando no próprio eixo (peão) e
        CRESCENDO conforme o mini boss se aproxima (pequena = distante, grande =
        perto). A altura ~cos(t) + flip dá a ilusão 3D de rotação no eixo Y
        (cima-baixo); a escala geral vem do progresso do telegraph (0..1).
        Sem outros efeitos."""
        arrow = _build_warning_arrow(self.WARNING_ARROW_CELL)
        aw, ah = arrow.get_size()
        p = min(1.0, self.warning_timer / self.WARNING_DURATION)  # aproximação
        g = self.WARNING_GROW_MIN + (self.WARNING_GROW_MAX - self.WARNING_GROW_MIN) * p
        cx = (
            Config.SCREEN_WIDTH - self.WARNING_EDGE_INSET - aw / 2
        )  # centro fixo na lateral
        cy = self.y + self.h / 2
        sy = math.cos(self.pulse * self.WARNING_SPIN_RATE)  # -1..1: altura aparente
        w = max(1, int(aw * g))
        h = max(1, int(ah * g * abs(sy)))
        img = pygame.transform.scale(arrow, (w, h))
        if sy < 0:
            img = pygame.transform.flip(img, False, True)  # girou no eixo Y → vira
        surface.blit(img, (int(cx - w / 2), int(cy - h / 2)))
