"""City Drone — "O Enxame".

Inimigo básico do bioma CITY. Chassi-disco ultra-leve que se move em
**spring-zigzag** polido: deriva pela tela com um *weave* senoidal coerente,
intercalando rajadas de **dardo** (snap rígido em direção ao jogador) e breves
**hovers** flutuantes. Nasce em **cluster** (nuvens de 5-8) e morre num
**static pop** (descarga elétrica → explosão cyber).

Vem em 3 variantes de cor (núcleo azul / magenta / laranja — chassi coeso) e
3 tamanhos (scout leve, padrão, pesado), cada um com HP, pontos e velocidade
próprios.

Contratos seguidos (CLAUDE.md):
  §5 update_in_context polimórfico (sem isinstance no manager).
  §7 surface do chassi cacheada por (cell, variante); glow bucketizado.
  §3 draw() só lê estado — pulso/weave são alimentados pelo update().
  §11 aggressiveness_multiplier propagado até a velocidade da entidade.
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
from .channeling import ChannelingGroup
from .city_drone_pixel_map import (
    DRONE_VARIANTS,
    NEON_CELLS,
    PIXEL_COLS,
    THRUSTER_CELLS,
    build_static_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

RGB = Tuple[int, int, int]


class CityDrone(EnemyHitMixin):
    """Drone de enxame com movimento spring-zigzag polido, em variantes."""

    # ── Tamanhos: (cell_px, health, points, speed_mult) ─────────────────────
    # Spawn pesado raro, scout comum — dá textura ao enxame. O pesado é o
    # "grávido": bem mais lento e tanky, e libera filhotes ao morrer.
    SIZE_TIERS: List[Tuple[int, int, int, float]] = [
        (2, 8, 30, 1.40),  # scout: pequeno, frágil, muito ágil
        (3, 14, 45, 1.00),  # padrão
        (4, 32, 70, 0.58),  # pesado/grávido: grande, tanky, lerdo
    ]
    SIZE_WEIGHTS: List[float] = [0.40, 0.45, 0.15]
    CARRIER_TIER = 2  # índice do tier que "está grávido" (libera filhotes)
    OFFSPRING_MIN = 2  # filhotes liberados na morte do carrier
    OFFSPRING_MAX = 4
    # Maior tamanho possível (tier pesado) — usado por spawners para margens.
    MAX_SIZE: int = PIXEL_COLS * max(tier[0] for tier in SIZE_TIERS)

    _explosion_size_hit = 8

    # Mola da perseguição dos filhotes homing (suave o bastante p/ ser desviável).
    SPRING_K_HOMING = 11.0
    HOMING_LIFETIME = 9.0  # filhote some sozinho após este tempo (anti-clutter)

    # Canalização em grupo → mini-chefe (FusedDrone).
    CHANNEL_SCAN_INTERVAL = (0.4, 0.8)  # cadência do scan de proximidade
    CHANNEL_RADIUS = 135.0  # raio p/ considerar drones "próximos"
    CHANNEL_CHANCE = 0.10  # 10% ao achar o grupo completo perto
    CHANNEL_GROUP_SIZE = 4

    # ── Física do movimento ──────────────────────────────────────────────────
    SPRING_K_CRUISE = 13.0  # cruzeiro: glide suave
    SPRING_K_DART = 26.0  # dardo: snap rígido
    SPRING_K_HOVER = 7.0  # hover: flutua mole
    SPRING_DAMPING = 6.0
    MAX_SPEED = 360.0  # teto base (escala com agressividade × tamanho)
    EDGE_MARGIN = 24.0  # margem vertical para o bounce
    EXIT_MARGIN = 60.0  # quão longe da borda some

    DART_CHANCE = 0.20  # ao re-alvejar: chance de investir no jogador
    HOVER_CHANCE = 0.18  # chance de pairar brevemente

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        variant_index: int | None = None,
        size_tier: int | None = None,
        homing: bool = False,
    ) -> None:
        # Variante de cor + tamanho (aleatórios, ou forçados para teste).
        self.variant_index = (
            variant_index
            if variant_index is not None
            else random.randrange(len(DRONE_VARIANTS))
        )
        self.variant = DRONE_VARIANTS[self.variant_index]
        if size_tier is None:
            size_tier = random.choices(
                range(len(self.SIZE_TIERS)), weights=self.SIZE_WEIGHTS, k=1
            )[0]
        self.size_tier = size_tier
        cell, health, points, speed_mult = self.SIZE_TIERS[size_tier]

        self.cell = cell
        self.w = PIXEL_COLS * cell
        self.h = self.w
        self.x: float = float(x)
        self.y: float = float(y)

        self.dead = False
        self.health = health
        self.points = points
        self._explosion_size_killed = 22 + cell * 4  # pop maior p/ drone maior
        self.aggressiveness_multiplier = aggressiveness_multiplier
        self.side_scroll = side_scroll

        # "Grávido": só o tier pesado carrega filhotes. Filhotes (homing) são
        # scouts e nunca são carriers (não há cascata recursiva).
        self.is_carrier = (size_tier == self.CARRIER_TIER) and not homing
        self.homing = homing
        self.homing_life = self.HOMING_LIFETIME

        self._max_speed = self.MAX_SPEED * aggressiveness_multiplier * speed_mult
        self.vx: float = 0.0
        self.vy: float = 0.0

        # Steering: weave coerente + lane (home) que faz random-walk lento.
        cy = self.y + self.h / 2
        cx = self.x + self.w / 2
        self.home: float = cy if side_scroll else cx  # posição-base no eixo do weave
        self.anchor: float = cx if side_scroll else cy  # trava de posição durante hover
        self.weave_phase = random.uniform(0.0, math.tau)
        self.weave_freq = random.uniform(1.4, 2.6)
        self.weave_amp = random.uniform(40.0, 85.0)
        self.cruise_lead = random.uniform(70.0, 110.0)

        self.mode = "cruise"
        self.target_x: float = cx
        self.target_y: float = cy
        self.retarget_timer = random.uniform(0.6, 1.0)

        # Canalização em grupo (mini-chefe dinâmico). channel_group é setado
        # pela ChannelingGroup quando este drone entra num ritual.
        self.channel_group: ChannelingGroup | None = None
        self.channel_angle = 0.0
        self._scan_timer = random.uniform(0.3, 0.9)

        # Animação (alimentada pelo update; lida pelo draw — §3).
        self.pulse = random.uniform(0.0, math.tau)
        self.hit_timer = 0.0

    # ── Geometria de colisão ─────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        # Disco: raio um pouco menor que a meia-largura (chassi não preenche o quadrado).
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.42

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        if self.channel_group is None:
            self._maybe_start_channel(ctx)

        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

        grp = self.channel_group
        if grp is not None:
            grp.tick(self, ctx.sdt)
            if grp.done:
                grp.spawn_boss(ctx)
            elif grp.broken:
                self.channel_group = None

    def _maybe_start_channel(self, ctx: "EnemyUpdateContext") -> None:
        """Scan de proximidade: 4 drones livres perto → 10% de iniciar ritual."""
        if self.homing or self.is_carrier:
            return

        self._scan_timer -= ctx.dt
        if self._scan_timer > 0.0:
            return
        self._scan_timer = random.uniform(*self.CHANNEL_SCAN_INTERVAL)

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        r2 = self.CHANNEL_RADIUS * self.CHANNEL_RADIUS
        nearby: list[tuple[float, CityDrone]] = []
        for e in ctx.other_enemies:
            if e is self or type(e) is not CityDrone:
                continue
            if e.dead or e.homing or e.is_carrier or e.channel_group is not None:
                continue
            ex = e.x + e.w / 2
            ey = e.y + e.h / 2
            d2 = (ex - cx) ** 2 + (ey - cy) ** 2
            if d2 <= r2:
                nearby.append((d2, e))

        if len(nearby) < self.CHANNEL_GROUP_SIZE - 1:
            return
        if random.random() >= self.CHANNEL_CHANCE:
            return

        nearby.sort(key=lambda t: t[0])
        members = [self] + [e for _, e in nearby[: self.CHANNEL_GROUP_SIZE - 1]]
        ccx = sum(m.x + m.w / 2 for m in members) / len(members)
        ccy = sum(m.y + m.h / 2 for m in members) / len(members)
        # A própria criação atribui channel_group/boost a todos os membros.
        ChannelingGroup(members, ccx, ccy, self.side_scroll)

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        if dt <= 0.0:
            return

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Canalizando: orbita o "sol" invisível, raio encolhendo com o progresso.
        grp = self.channel_group
        if grp is not None and not grp.broken and not grp.done:
            self._update_channel_orbit(dt)
            return

        if self.homing:
            # Filhote especial: persegue o jogador continuamente.
            self.target_x = player_x
            self.target_y = player_y
            spring_k = self.SPRING_K_HOMING
            self.homing_life -= dt
            if self.homing_life <= 0.0:
                self.dead = True
        else:
            self.retarget_timer -= dt
            if self.retarget_timer <= 0.0:
                self._retarget(player_x, player_y)
            self._update_steering(dt)
            spring_k = self._spring_k()

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        # Mola em direção ao alvo (Euler semi-implícito).
        ax = spring_k * (self.target_x - cx) - self.SPRING_DAMPING * self.vx
        ay = spring_k * (self.target_y - cy) - self.SPRING_DAMPING * self.vy
        self.vx += ax * dt
        self.vy += ay * dt

        # Teto de velocidade (preserva direção).
        speed_sq = self.vx * self.vx + self.vy * self.vy
        max_sp = self._max_speed
        if speed_sq > max_sp * max_sp:
            scale = max_sp / math.sqrt(speed_sq)
            self.vx *= scale
            self.vy *= scale

        self.x += self.vx * dt
        self.y += self.vy * dt

        # Homing persegue o jogador (que está em tela) — sem bounce p/ não brigar
        # com a mola; só morre por tempo ou abate.
        if not self.homing:
            self._apply_vertical_bounce()
            self._check_exit()

    def _update_channel_orbit(self, dt: float) -> None:
        grp = self.channel_group
        assert grp is not None
        self.channel_angle += grp.spin_speed() * dt
        radius = grp.current_radius()
        cx = grp.cx + math.cos(self.channel_angle) * radius
        cy = grp.cy + math.sin(self.channel_angle) * radius
        self.x = cx - self.w / 2
        self.y = cy - self.h / 2
        self.vx = 0.0
        self.vy = 0.0

    def _spring_k(self) -> float:
        if self.mode == "dart":
            return self.SPRING_K_DART
        if self.mode == "hover":
            return self.SPRING_K_HOVER
        return self.SPRING_K_CRUISE

    def _retarget(self, player_x: float, player_y: float) -> None:
        """Transição de modo. Dardo sempre relaxa de volta ao cruzeiro."""
        if self.mode == "dart":
            self._begin_cruise()
        else:
            roll = random.random()
            if roll < self.DART_CHANCE:
                self._begin_dart(player_x, player_y)
            elif roll < self.DART_CHANCE + self.HOVER_CHANCE:
                self._begin_hover()
            else:
                self._begin_cruise()

    def _begin_cruise(self) -> None:
        self.mode = "cruise"
        # Random-walk lento da lane (home) + renova o weave para o trajeto não repetir.
        self.home += random.uniform(-55.0, 55.0)
        self.home = self._clamp_home(self.home)
        self.weave_freq = random.uniform(1.4, 2.6)
        self.weave_amp = random.uniform(40.0, 85.0)
        self.cruise_lead = random.uniform(70.0, 110.0)
        self.retarget_timer = random.uniform(0.6, 1.0)

    def _begin_hover(self) -> None:
        self.mode = "hover"
        self.anchor = self.x + self.w / 2 if self.side_scroll else self.y + self.h / 2
        self.retarget_timer = random.uniform(0.4, 0.7)

    def _begin_dart(self, player_x: float, player_y: float) -> None:
        self.mode = "dart"
        # Alvo fixo: investida no jogador com leve dispersão.
        self.target_x = player_x + random.uniform(-50.0, 50.0)
        self.target_y = player_y + random.uniform(-50.0, 50.0)
        self.retarget_timer = random.uniform(0.25, 0.45)

    def _clamp_home(self, value: float) -> float:
        if self.side_scroll:
            lo = self.EDGE_MARGIN + self.h / 2
            hi = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2
        else:
            lo = self.EDGE_MARGIN + self.w / 2
            hi = Config.SCREEN_WIDTH - self.EDGE_MARGIN - self.w / 2
        return max(lo, min(hi, value))

    def _update_steering(self, dt: float) -> None:
        """Recalcula target_x/y por frame (exceto no dardo, que tem alvo fixo)."""
        if self.mode == "dart":
            return

        self.weave_phase += self.weave_freq * dt
        weave = math.sin(self.weave_phase) * self.weave_amp
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        if self.side_scroll:
            if self.mode == "hover":
                # Paira: segura x, balança suave em torno da lane.
                self.target_x = self.anchor
                self.target_y = self.home + weave * 0.4
            else:  # cruise — carrot à esquerda = glide constante
                self.target_x = cx - self.cruise_lead
                self.target_y = self.home + weave
        else:
            if self.mode == "hover":
                self.target_y = self.anchor
                self.target_x = self.home + weave * 0.4
            else:
                self.target_y = cy + self.cruise_lead
                self.target_x = self.home + weave

        # Mantém o alvo do weave dentro de margens jogáveis.
        if self.side_scroll:
            self.target_y = max(
                self.EDGE_MARGIN,
                min(float(Config.SCREEN_HEIGHT) - self.EDGE_MARGIN, self.target_y),
            )
        else:
            self.target_x = max(
                self.EDGE_MARGIN,
                min(float(Config.SCREEN_WIDTH) - self.EDGE_MARGIN, self.target_x),
            )

    def _apply_vertical_bounce(self) -> None:
        top = self.EDGE_MARGIN
        bottom = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h
        if self.y < top:
            self.y = top
            self.vy = abs(self.vy) * 0.6
        elif self.y > bottom:
            self.y = bottom
            self.vy = -abs(self.vy) * 0.6

    def _check_exit(self) -> None:
        if self.side_scroll:
            if self.x + self.w < -self.EXIT_MARGIN:
                self.dead = True
        else:
            if self.y > Config.SCREEN_HEIGHT + self.EXIT_MARGIN:
                self.dead = True

    # ── Filhotes (carrier "grávido") ─────────────────────────────────────────
    def _make_offspring(self) -> Tuple["CityDrone", ...]:
        """Gera 2-4 scouts homing que explodem para fora e perseguem o jogador.

        Mesma variante de cor da mãe (continuidade visual). Recebem um impulso
        radial inicial; a mola de homing redireciona em seguida ao jogador.
        """
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        count = random.randint(self.OFFSPRING_MIN, self.OFFSPRING_MAX)
        babies: list[CityDrone] = []
        for _ in range(count):
            baby = CityDrone(
                cx,
                cy,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                side_scroll=self.side_scroll,
                variant_index=self.variant_index,
                size_tier=0,  # scout
                homing=True,
            )
            baby.x = cx - baby.w / 2
            baby.y = cy - baby.h / 2
            angle = random.uniform(0.0, math.tau)
            burst = random.uniform(140.0, 240.0)
            baby.vx = math.cos(angle) * burst
            baby.vy = math.sin(angle) * burst
            babies.append(baby)
        return tuple(babies)

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.points

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...entities.explosion import ExplosionType
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=self._explosion_size_killed,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
                fragments=self._make_offspring() if self.is_carrier else (),
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...entities.explosion import ExplosionType
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.dead = True
        return HitResult(
            killed=True,
            explosion_size=self._explosion_size_killed,
            explosion_type=ExplosionType.CYBER,
            sound=hit_sounds.EXPLOSION_ALIEN,
            fragments=self._make_offspring() if self.is_carrier else (),
        )

    def should_remove(self) -> bool:
        return self.dead

    # ── Render ──────────────────────────────────────────────────────────────
    def _blit_glow(
        self, surface: pygame.Surface, cx: int, cy: int, radius: int, color: RGB
    ) -> None:
        glow = city_glow.get_glow(radius, color)
        surface.blit(
            glow, (cx - radius, cy - radius), special_flags=pygame.BLEND_RGBA_ADD
        )

    def draw(self, surface: pygame.Surface) -> None:
        cell = self.cell
        base = build_static_surface(cell, self.variant_index)

        # Brilho aditivo: flash de hit OU "charging" crescente durante a canalização.
        # BLEND_RGB_ADD (não RGBA): soma só o RGB e preserva o alpha de cada
        # pixel — os cantos transparentes continuam invisíveis. Com RGBA_ADD o
        # alpha dos cantos subiria e a bounding box inteira piscaria como um
        # quadrado branco por 1 frame.
        grp = self.channel_group
        channeling = grp is not None and not grp.broken and not grp.done
        channel_p = grp.progress if (channeling and grp is not None) else 0.0
        if self.hit_timer > 0.0 or channel_p > 0.0:
            add = 210 if self.hit_timer > 0.0 else int(40 + 150 * channel_p)
            img = base.copy()
            img.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Glow do núcleo neon (pulso) — camada de energia, na cor da variante.
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 6.0)
        neon = pal.lerp(self.variant.neon_dim, self.variant.neon, pulse)
        core_r = int(cell * 1.6 + cell * pulse)
        for c, r in NEON_CELLS:
            gx = int(self.x + (c + 0.5) * cell)
            gy = int(self.y + (r + 0.5) * cell)
            self._blit_glow(surface, gx, gy, core_r, neon)

        # Flicker dos micro-propulsores — camada de acessórios.
        for i, (c, r) in enumerate(THRUSTER_CELLS):
            flick = 0.5 + 0.5 * math.sin(self.pulse * 22.0 + i * 1.7)
            tcol = pal.lerp(pal.HULL_SHADOW, self.variant.thruster, 0.4 + 0.6 * flick)
            tx = int(self.x + (c + 0.5) * cell)
            ty = int(self.y + (r + 0.5) * cell)
            self._blit_glow(surface, tx, ty, int(cell * 1.3), tcol)

        # "Grávida": 3 sementes de energia girando no ventre (telegrafa o carrier).
        if self.is_carrier:
            core_cx = self.x + self.w / 2
            core_cy = self.y + self.h / 2
            for k in range(3):
                ang = self.pulse * 1.6 + k * (math.tau / 3.0)
                ex = int(core_cx + math.cos(ang) * cell * 1.7)
                ey = int(core_cy + math.sin(ang) * cell * 1.7)
                ep = 0.5 + 0.5 * math.sin(self.pulse * 5.0 + k * 1.3)
                ecol = pal.lerp(self.variant.neon_dim, self.variant.neon, ep)
                self._blit_glow(surface, ex, ey, max(2, int(cell * 0.9)), ecol)

        # Canalização: feixe de energia até o "sol" + orbe central crescente.
        if channeling and grp is not None:
            self._draw_channel_fx(surface, grp)

    def _draw_channel_fx(self, surface: pygame.Surface, grp: ChannelingGroup) -> None:
        sx = int(self.x + self.w / 2)
        sy = int(self.y + self.h / 2)
        gx = int(grp.cx)
        gy = int(grp.cy)
        p = grp.progress

        # Feixe pulsante puxando energia para o centro.
        flow = 0.5 + 0.5 * math.sin(self.pulse * 10.0)
        beam_col = pal.lerp(self.variant.neon_dim, self.variant.neon, flow)
        pygame.draw.line(surface, beam_col, (sx, sy), (gx, gy), max(1, int(1 + 3 * p)))

        # Só o líder desenha o "sol" se formando (evita 4× draw no mesmo ponto).
        if grp.members and grp.members[0] is self:
            core_r = int(6 + 40 * p)
            sun = pal.lerp(pal.ELECTRIC_BLUE, (255, 255, 255), p)
            self._blit_glow(surface, gx, gy, core_r, sun)
