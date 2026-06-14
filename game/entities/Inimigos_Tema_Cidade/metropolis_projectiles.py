"""Projéteis das Sentinelas Orbitais do Metropolis Overlord (tema CITY).

Quatro tipos custom, um por sentinela (decisão de design: projéteis 100% custom
por sentinela, não reuso de orbe genérico):

  NeonBurstShot   — Sentinela superior-esquerda. Rajada reta de neon, rápida,
                    mirada na pose do jogador no instante do disparo.
  MicroMissile    — Sentinela superior-direita. Míssil seguidor com **turn-rate
                    limitado** (desviável, §11/bem-estar) e vida curta.
  VerticalLaser   — Sentinela inferior-esquerda. Feixe vertical que telegrafa e
                    depois cai cruzando a coluna. Indestrutível (só desvio).
  EMPPulse        — Sentinela inferior-direita. Pulso EMP em anel que dá dano de
                    contato. (TODO: debuff de lentidão nos projéteis do jogador —
                    é mecânica reversa nova, ver parecer; stub por enquanto.)

Todos aderem ao contrato de "inimigo comum" do EntityManager: vivem em
`em.enemies` (roteados via `ctx.new_enemies` pela sentinela), implementam
`update_in_context`, `rect`, `collision_circle`, `on_hit`/`causes_damage` e
`draw` sem efeitos colaterais (§3). Assim ganham colisão/desenho/cleanup de graça,
sem nova plumbing no EntityManager.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# Paleta neon da Cidade (magenta/azul-elétrico) — coerente com o Overlord.
_NEON_MAGENTA = (255, 70, 200)
_NEON_BLUE = (90, 200, 255)
_NEON_WHITE = (255, 255, 255)
_NEON_AMBER = (255, 190, 80)


def _off_screen(x: float, y: float, margin: float = 60.0) -> bool:
    return (
        x < -margin
        or x > Config.SCREEN_WIDTH + margin
        or y < -margin
        or y > Config.SCREEN_HEIGHT + margin
    )


class _CityProjectile(EnemyHitMixin):
    """Base enxuta dos projéteis das sentinelas (estado + colisão padrão)."""

    is_boss: bool = False
    HEALTH: int = 6
    POINTS: int = 0
    RADIUS: float = 7.0

    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.health = self.HEALTH
        self.dead = False
        self.lifetime = 8.0
        self._rect = pygame.Rect(0, 0, int(self.RADIUS * 2), int(self.RADIUS * 2))
        self._sync_rect()

    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, self.RADIUS

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead


class NeonBurstShot(_CityProjectile):
    """Rajada reta de neon: mira fixa no alvo do disparo, voa em linha."""

    HEALTH = 4
    RADIUS = 6.0
    SPEED = 460.0

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        super().__init__(x, y)
        ang = math.atan2(target_y - y, target_x - x)
        self.vx = math.cos(ang) * self.SPEED
        self.vy = math.sin(ang) * self.SPEED
        self.lifetime = 4.0

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt
        self._sync_rect()
        if self.lifetime <= 0 or _off_screen(self.x, self.y):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        pygame.draw.circle(surface, _NEON_MAGENTA, (cx, cy), int(self.RADIUS))
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS * 0.45))


class MicroMissile(_CityProjectile):
    """Míssil seguidor com turn-rate limitado (justo de desviar) e vida curta."""

    HEALTH = 5
    RADIUS = 7.0
    SPEED = 300.0
    MAX_TURN_RATE = 2.6  # rad/s — teto do giro; quanto menor, mais desviável
    LIFETIME = 6.0

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        super().__init__(x, y)
        self.angle = math.atan2(target_y - y, target_x - x)
        self.lifetime = self.LIFETIME

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        desired = math.atan2(ctx.player_y - self.y, ctx.player_x - self.x)
        # Diferença angular normalizada para [-pi, pi], clampada ao turn-rate.
        diff = (desired - self.angle + math.pi) % (2 * math.pi) - math.pi
        max_step = self.MAX_TURN_RATE * dt
        self.angle += max(-max_step, min(max_step, diff))
        self.x += math.cos(self.angle) * self.SPEED * dt
        self.y += math.sin(self.angle) * self.SPEED * dt
        self.lifetime -= dt
        self._sync_rect()
        if self.lifetime <= 0 or _off_screen(self.x, self.y):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        # Corpo + chama traseira apontando contra o movimento.
        tail_x = cx - int(math.cos(self.angle) * self.RADIUS * 1.8)
        tail_y = cy - int(math.sin(self.angle) * self.RADIUS * 1.8)
        pygame.draw.line(surface, _NEON_AMBER, (cx, cy), (tail_x, tail_y), 3)
        pygame.draw.circle(surface, _NEON_BLUE, (cx, cy), int(self.RADIUS))
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS * 0.4))


class VerticalLaser(_CityProjectile):
    """Feixe vertical: telegrafa numa coluna, depois desce cruzando a tela.

    Indestrutível — não pode ser destruído a tiro, só desviado. Dano só na fase
    `active` (telegrafo é seguro), na largura da coluna.
    """

    WIDTH = 18.0
    TELEGRAPH_TIME = 0.7
    FALL_SPEED = 720.0

    def __init__(self, column_x: float) -> None:
        super().__init__(column_x, 0.0)
        self.column_x = float(column_x)
        self.phase = "telegraph"  # telegraph | active
        self.phase_t = 0.0
        self.beam_y = 0.0  # frente do feixe descendo
        self.lifetime = 6.0

    @property
    def causes_damage(self) -> bool:
        return self.phase == "active"

    def collision_circle(self) -> tuple[float, float, float]:
        # Disco na frente do feixe (aproxima a coluna para o broadphase).
        return self.column_x, self.beam_y, self.WIDTH / 2

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.phase_t += dt
        if self.phase == "telegraph":
            if self.phase_t >= self.TELEGRAPH_TIME:
                self.phase = "active"
                self.phase_t = 0.0
        else:
            self.beam_y += self.FALL_SPEED * dt
            if self.beam_y > Config.SCREEN_HEIGHT + 40:
                self.dead = True
        self.x, self.y = self.column_x, self.beam_y
        self._sync_rect()

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ...systems.hit_result import HitResult

        return HitResult()  # indestrutível: tiros do jogador passam direto

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems.hit_result import HitResult

        return HitResult()  # não morre ao tocar a nave (continua descendo)

    def draw(self, surface: pygame.Surface) -> None:
        x = int(self.column_x)
        half = int(self.WIDTH / 2)
        if self.phase == "telegraph":
            # Linha fina pulsante de aviso, da borda superior ao fim da tela.
            pulse = 0.5 + 0.5 * math.sin(self.phase_t * 24.0)
            col = (
                int(_NEON_BLUE[0] * pulse),
                int(_NEON_BLUE[1] * pulse),
                int(_NEON_BLUE[2]),
            )
            pygame.draw.line(surface, col, (x, 0), (x, Config.SCREEN_HEIGHT), 2)
        else:
            top = max(0, int(self.beam_y) - Config.SCREEN_HEIGHT)
            rect = pygame.Rect(x - half, top, half * 2, int(self.beam_y) - top)
            pygame.draw.rect(surface, _NEON_BLUE, rect)
            pygame.draw.rect(surface, _NEON_WHITE, rect.inflate(-half, 0))


class EMPPulse(_CityProjectile):
    """Pulso EMP em anel expansivo. Dano de contato na frente do anel.

    TODO (ver parecer): aplicar lentidão temporária aos PROJÉTEIS do jogador é
    uma mecânica reversa do EMP atual (jogador→inimigos). Fica como stub: por
    enquanto o pulso só ameaça por contato. Implementar o debuff exige plumbing
    novo em Ship/bullets + colisão dedicada.
    """

    MAX_RADIUS = 150.0
    GROWTH = 260.0  # px/s
    THICKNESS = 14.0

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.radius = 6.0
        self.lifetime = 3.0

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        # Aproxima a frente do anel; TODO: validação em anel (annulus) fina.
        return self.x, self.y, self.radius

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.radius += self.GROWTH * dt
        self.lifetime -= dt
        self._sync_rect()
        if self.radius >= self.MAX_RADIUS or self.lifetime <= 0:
            self.dead = True

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ...systems.hit_result import HitResult

        return HitResult()  # o pulso não é destrutível a tiro

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems.hit_result import HitResult

        return HitResult()  # passa pela nave (dano vem do contato, não morre)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        r = int(self.radius)
        fade = max(0.0, 1.0 - self.radius / self.MAX_RADIUS)
        col = (
            min(255, int(_NEON_MAGENTA[0] * fade + 60)),
            min(255, int(_NEON_BLUE[1] * fade)),
            min(255, int(_NEON_BLUE[2])),
        )
        pygame.draw.circle(surface, col, (cx, cy), r, max(2, int(self.THICKNESS * fade)))
