"""Splitter Tank — colosso modular do bioma CITY.

Variante da linhagem do Cyber Tank com morte **"Fission"**: um juggernaut que
avança devagar e, ao ser destruído, **se parte em unidades menores** (tier
seguinte) que continuam — escalando a decisão de foco de fogo do jogador, em vez
de simplesmente estilhaçar (`tank_meltdown`).

Uma única classe com `tier`: tier 0 (grande) → 3× tier 1 (pequenos); tier 1 não
se parte mais. O split é disparado pelo EntityManager via
`triggers_special_death` (lê posição/tier/agressividade do alvo e empurra os
filhos em `enemies`), no espírito do offspring do City Drone.

Contratos (convenções do projeto): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
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

# Movimento do mini (tier 1): persegue o jogador, mas mirando um ponto que gira
# num anel em volta dele — cada mini numa fase própria, então cercam o jogador
# por lados diferentes (arcos amplos) sem empilhar no mesmo ponto.
#   orbit_speed  : rad/s da volta no anel (menor = órbitas mais lentas/amplas)
#   orbit_radius : raio (px) do anel em torno do jogador que o mini persegue
_MINI_ORBIT_SPEED: float = 2.0
_MINI_ORBIT_RADIUS: float = 95.0
# Impulso radial ao nascer: os minis saem do centro "explodindo" para fora em
# leque (fases distribuídas) e a órbita vai assumindo ao longo deste tempo.
_MINI_BIRTH_BURST: float = 0.45        # s do impulso antes da órbita assumir 100%
_MINI_BIRTH_BURST_BOOST: float = 1.7   # quão mais rápido que a órbita é o "pop"
# Separação: cada mini repele os irmãos que cheguem mais perto que a distância
# mínima, então mantêm um espaçamento entre si mesmo orbitando o mesmo jogador.
_MINI_MIN_DISTANCE: float = 64.0       # px de espaçamento desejado entre minis
_MINI_SEPARATION_FORCE: float = 2.2    # peso da repulsão (≈1 = ordem da órbita)

# Tier 0: cada tiro recebido pode "vazar" minis (além do split na morte).
_HIT_SPAWN_SINGLE_CHANCE: float = 0.05  # 5% → 1 mini
_HIT_SPAWN_TRIPLE_CHANCE: float = 0.01  # 1% → 3 minis

# Ajuste fino do bloom neon do núcleo, por tier. Tudo em unidades de `cell`
# (multiplicado pelo tamanho do pixel do chassi) para acompanhar a escala.
#   off_x / off_y : desloca o glow a partir do centro do sprite (+x direita, +y baixo)
#   scale         : multiplica o raio do glow (1.0 = base; menor encolhe)
#   min_radius    : piso do raio (em px) p/ o glow não sumir no fundo do pulso
_GLOW_OFFSET_X_BY_TIER: dict[int, float] = {0: 0.15, 1: 0.25}
_GLOW_OFFSET_Y_BY_TIER: dict[int, float] = {0: 0.92, 1: 0.65}
_GLOW_SCALE_BY_TIER: dict[int, float] = {0: 1.0, 1: 0.6}
_GLOW_MIN_RADIUS_BY_TIER: dict[int, int] = {0: 6, 1: 8}


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
        self.orbit_phase: float = random.uniform(0.0, math.tau)  # fase do arco do mini
        # Impulso radial de nascimento (preenchido pelo pai ao gerar o mini).
        self.birth_burst: float = 0.0
        self._burst_vx: float = 0.0
        self._burst_vy: float = 0.0
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
        self.update(ctx.sdt, ctx.player_x, ctx.player_y, ctx.other_enemies)

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        others: "List[SplitterTank] | None" = None,
    ) -> None:
        if dt <= 0.0:
            return
        self.pulse += dt
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.tier == 0:
            self._update_juggernaut(dt, player_x, player_y)
        else:
            self._update_mini_orbit(dt, player_x, player_y, others)

        self.x += self.vx * dt
        self.y += self.vy * dt
        self._cull_if_offscreen()

    def _update_juggernaut(self, dt: float, player_x: float, player_y: float) -> None:
        """Tier 0: avança constante; persegue lentamente o jogador no eixo
        transversal (sobe/desce no side-scroll p/ ameaçar a linha do jogador)."""
        cx, cy = self._center()
        if self.side_scroll:
            track = max(-self.VERTICAL_TRACK, min(self.VERTICAL_TRACK, player_y - cy))
            self.vy += (track - self.vy) * min(1.0, dt * 2.0)
        else:
            track = max(-self.VERTICAL_TRACK, min(self.VERTICAL_TRACK, player_x - cx))
            self.vx += (track - self.vx) * min(1.0, dt * 2.0)

    def _arm_birth_burst(self, base_speed: float) -> None:
        """Carrega o impulso radial de nascimento na direção da `orbit_phase`, para
        o mini sair do centro 'explodindo' para fora antes da órbita assumir."""
        self.birth_burst = _MINI_BIRTH_BURST
        burst = base_speed * _MINI_BIRTH_BURST_BOOST
        self._burst_vx = math.cos(self.orbit_phase) * burst
        self._burst_vy = math.sin(self.orbit_phase) * burst

    def _update_mini_orbit(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        others: "List[SplitterTank] | None",
    ) -> None:
        """Tier 1: persegue um ponto que gira num anel em torno do jogador. Como
        cada mini tem uma fase própria, eles cercam o jogador por lados diferentes
        em curvas amplas, em vez de convergirem (e empilharem) no mesmo ponto. No
        nascimento, um impulso radial os abre em leque e esmaece para a órbita."""
        self.orbit_phase += dt * _MINI_ORBIT_SPEED
        target_x = player_x + math.cos(self.orbit_phase) * _MINI_ORBIT_RADIUS
        target_y = player_y + math.sin(self.orbit_phase) * _MINI_ORBIT_RADIUS
        cx, cy = self._center()
        heading = math.atan2(target_y - cy, target_x - cx)
        speed = _SPEED_BY_TIER[self.tier] * self.aggressiveness_multiplier
        ovx = speed * math.cos(heading)
        ovy = speed * math.sin(heading)
        if self.birth_burst > 0.0:
            self.birth_burst = max(0.0, self.birth_burst - dt)
            t = self.birth_burst / _MINI_BIRTH_BURST  # 1 (nascimento) → 0 (órbita)
            self.vx = self._burst_vx * t + ovx * (1.0 - t)
            self.vy = self._burst_vy * t + ovy * (1.0 - t)
        else:
            self.vx = ovx
            self.vy = ovy
        if others is not None:
            self._separate_from_siblings(others, speed)

    def _separate_from_siblings(self, others: "List[SplitterTank]", speed: float) -> None:
        """Repele os minis-irmãos que invadirem `_MINI_MIN_DISTANCE`, somando uma
        velocidade de fuga (quanto mais perto, mais forte) à órbita. Mantém o
        espaçamento mínimo mesmo todos perseguindo o mesmo jogador."""
        cx, cy = self._center()
        md = _MINI_MIN_DISTANCE
        push_x = 0.0
        push_y = 0.0
        for o in others:
            # Só irmãos do mesmo tier (e não a si mesmo); leitura intra-classe (§1).
            if o is self or type(o) is not SplitterTank or o.tier != self.tier:
                continue
            ox, oy = o._center()
            dx = cx - ox
            dy = cy - oy
            d2 = dx * dx + dy * dy
            if 0.0 < d2 < md * md:
                d = math.sqrt(d2)
                strength = (md - d) / md  # 0 na borda → 1 colado
                push_x += (dx / d) * strength
                push_y += (dy / d) * strength
        if push_x != 0.0 or push_y != 0.0:
            self.vx += push_x * speed * _MINI_SEPARATION_FORCE
            self.vy += push_y * speed * _MINI_SEPARATION_FORCE

    def _cull_if_offscreen(self) -> None:
        if self.tier == 0:
            # Juggernaut: sai de cena ao atravessar a borda de avanço.
            if self.side_scroll:
                if self.x + self.w < -60.0:
                    self.dead = True
            elif self.y - self.h > Config.SCREEN_HEIGHT + 60.0:
                self.dead = True
            return
        # Mini persegue o jogador: só descarta se sair bem longe de qualquer borda.
        m = 200.0
        if (
            self.x + self.w < -m
            or self.x > Config.SCREEN_WIDTH + m
            or self.y + self.h < -m
            or self.y > Config.SCREEN_HEIGHT + m
        ):
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
            # Nascem no centro (juntos) com fases distribuídas e um impulso radial
            # nessa direção → "explodem" para fora em leque e depois orbitam.
            child.orbit_phase = (i / _SPLIT_COUNT) * math.tau
            child.x = cx - child.w / 2
            child.y = cy - child.h / 2
            child._arm_birth_burst(child_speed)
            children.append(child)
        return children

    def _spawn_minis(self, count: int) -> List["SplitterTank"]:
        """Minis que "vazam" do tier 0 por tiro recebido, jogados em direções
        aleatórias a partir do centro. Só o tier 0 chama (minis não geram minis)."""
        cx, cy = self._center()
        speed = _SPEED_BY_TIER[self.tier + 1] * self.aggressiveness_multiplier
        minis: List[SplitterTank] = []
        base_phase = random.uniform(0.0, math.tau)
        for i in range(count):
            # Fases distribuídas a partir de um ângulo base aleatório → nascem
            # separados e orbitam por lados diferentes (não empilham).
            ang = base_phase + (i / count) * math.tau
            mini = SplitterTank(
                cx, cy,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                side_scroll=self.side_scroll,
                health_multiplier=self.health_multiplier,
                tier=self.tier + 1,
                vx=speed * math.cos(ang), vy=speed * math.sin(ang),
            )
            mini.orbit_phase = ang
            mini.x = cx - mini.w / 2
            mini.y = cy - mini.h / 2
            mini._arm_birth_burst(speed)
            minis.append(mini)
        return minis

    def _roll_hit_spawn(self) -> Tuple["SplitterTank", ...]:
        """Sorteia, por tiro, quantos minis vazam: 1% → 3, senão 5% → 1."""
        r = random.random()
        if r < _HIT_SPAWN_TRIPLE_CHANCE:
            return tuple(self._spawn_minis(3))
        if r < _HIT_SPAWN_TRIPLE_CHANCE + _HIT_SPAWN_SINGLE_CHANCE:
            return tuple(self._spawn_minis(1))
        return ()

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
            # Ambos os tiers passam pelo death-sequence (explosão + destroços; o
            # tier 0 ainda gera os filhos). explosion_size=0: a explosão e os
            # cacos vêm do EntityManager, não do roteador de hit.
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=0,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=True,
            )
        # Hit não-fatal: o tier 0 pode "vazar" minis (split na morte é à parte).
        fragments: Tuple["SplitterTank", ...] = ()
        if self.tier == 0:
            fragments = self._roll_hit_spawn()
        return HitResult(
            explosion_size=self._explosion_size_hit,
            sound=hit_sounds.BOSS_DAMAGE,
            fragments=fragments,
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
        # ferido ("vai partir"). Offset/escala por tier ajustáveis no topo do
        # módulo (_GLOW_*_BY_TIER) para casar com o centro visual da arte.
        cx, cy = self._center()
        cx += self.cell * _GLOW_OFFSET_X_BY_TIER[self.tier]
        cy += self.cell * _GLOW_OFFSET_Y_BY_TIER[self.tier]
        hurt = 1.0 - self.health / max(1, self.max_health)
        pulse = 0.5 + 0.5 * math.sin(self.pulse * (5.0 + 6.0 * hurt))
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, 0.4 + 0.6 * pulse)
        # Mais transparente: escurece a cor → contribuição aditiva mais fraca.
        core_col = pal.lerp((0, 0, 0), core_col, 0.5)
        core_r = int(
            self.cell * (1.2 + 0.6 * pulse + 1.2 * hurt) * _GLOW_SCALE_BY_TIER[self.tier]
        )
        # Piso para o pulso/fase aleatória não encolher o glow até sumir.
        core_r = max(_GLOW_MIN_RADIUS_BY_TIER[self.tier], core_r)
        self._blit_glow(surface, int(cx), int(cy), core_r, core_col)
