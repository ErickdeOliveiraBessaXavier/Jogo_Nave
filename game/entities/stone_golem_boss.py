"""
Stone Golem Boss — Mundo 1: Cordilheira Celestial (Montanhas)

Boss do nível 10. Padrão Arc (como Boss original).
Refatorado para seguir boas práticas de performance, robustez e legibilidade.
"""

import logging
import math
import random
from typing import TYPE_CHECKING, Any, Final, List, Optional, Tuple

import pygame

from ..core.config import config as Config
from ..core.sound_config import MusicState
from ..entities.bot_elemental import ElementalRobot
from ..entities.stone_golem_pixel_map import EYE_COL_END as _EYE_COL_END
from ..entities.stone_golem_pixel_map import EYE_COL_START as _EYE_COL_START
from ..entities.stone_golem_pixel_map import EYE_ROW as _EYE_ROW
from ..entities.stone_golem_pixel_map import EYE_ROW_ABOVE as _EYE_ROW_ABOVE
from ..entities.stone_golem_pixel_map import EYE_ROW_BELOW as _EYE_ROW_BELOW
from ..entities.stone_golem_pixel_map import PIXEL_COLS as _PIXEL_COLS
from ..entities.stone_golem_pixel_map import PIXEL_MAP as _PIXEL_MAP
from ..entities.stone_golem_pixel_map import PIXEL_ROWS as _PIXEL_ROWS
from ..entities.stone_golem_pixel_map import C as _C
from .boss_hit_mixin import BossHitMixin

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..systems.hit_result import HitResult

logger = logging.getLogger(__name__)

# Paleta de cores de terra, pedras escuras e poeira (Refinada para alto contraste)
_EARTH_COLORS = [
    (25, 15, 10),  # Solo Profundo (Escuríssimo)
    (55, 40, 30),  # Marrom Sombra
    (90, 70, 50),  # Terra Média
    (130, 110, 80),  # Barro / Argila
    (170, 150, 120),  # Pedra Seca
    (205, 190, 160),  # Areia Clara (Contraste)
    (240, 225, 200),  # Highlight Final (Muito Claro)
    (180, 105, 65),  # Sienna / Argila Queimada
    (40, 40, 40),  # Rocha Vulcânica (Quase Preto)
    (100, 100, 100),  # Cinza Pedra
    (155, 160, 170),  # Ardósia (Cinza Frio)
]


def _get_random_earth_color() -> Tuple[int, int, int]:
    """Retorna uma cor de terra aleatória com pequena variação para maior diversidade."""
    base = random.choice(_EARTH_COLORS)
    j = random.randint(-12, 12)
    return (
        int(_clamp(base[0] + j, 0, 255)),
        int(_clamp(base[1] + j, 0, 255)),
        int(_clamp(base[2] + j, 0, 255)),
    )


# ============================================================================
# HELPERS MATEMATICOS
# ============================================================================


def _ease_out_cubic(t: float) -> float:
    """Easing para movimentos orgânicos do olho."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _clamp(val: float, lo: float, hi: float) -> float:
    """Garante que o valor esteja entre o limite inferior e superior."""
    return max(lo, min(hi, val))


# ============================================================================
# ENTIDADES PROJETADAS PELO GOLEM
# ============================================================================


class GolemMine:
    """
    Mina de energia vermelha plantada pelo boss na posição do jogador.
    """

    FUSE_TIME = 5.0
    LAND_SPEED = 900.0
    RADIUS = 12  # Escala visual da cruz central e do arco do fuse.
    # Hitbox maior que o RADIUS visual: o halo vermelho pulsante se estende
    # além da cruz, então o tiro do jogador (e o contato com a nave) alcança
    # essa área. Mantém o desenho no RADIUS original.
    HIT_RADIUS = 20
    EXPL_SHARDS = 14

    _COLOR_BODY = (200, 40, 40)
    _COLOR_RING = (255, 100, 100)
    _COLOR_PULSE = (255, 200, 200)

    def __init__(self, x: float, y: float, target_x: float, target_y: float):
        self.x = float(x)
        self.y = float(y)
        self.target_x = float(target_x)
        self.target_y = float(target_y)
        self.dead = False
        self.health = 50
        self._hit_flash = 0.0

        self._phase = "landing"
        self._fuse_timer = 0.0
        self._pulse_t = 0.0
        self._tick_timer: float = 0.0

        self.rect = pygame.Rect(
            int(self.x - self.HIT_RADIUS),
            int(self.y - self.HIT_RADIUS),
            self.HIT_RADIUS * 2,
            self.HIT_RADIUS * 2,
        )

        # Pré-alocação de superfícies
        r = self.RADIUS
        max_glow_r = int(r * 2.2)
        self._glow_surf = pygame.Surface(
            (max_glow_r * 2, max_glow_r * 2), pygame.SRCALPHA
        )
        self._arc_surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)

    @property
    def causes_damage(self) -> bool:
        """Sempre causa dano ao contato."""
        return True

    def take_damage(self, amount: int = 1) -> None:
        """Recebe dano do jogador."""
        if self._phase == "exploded":
            return
        self.health -= amount
        self._hit_flash = 0.15
        if self.health <= 0:
            self.health = 0
            self.dead = True
            from ..systems import hit_sounds as _hs

            _hs.GOLEM_STOP_MINE_TIMER()

    def get_points_value(self) -> int:
        """Retorna pontos ao ser destruído."""
        return 50

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.HIT_RADIUS)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        # Reuse existing take_damage logic and translate to HitResult for
        # the damage router in CollisionPhysics.
        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=max(16, int(self.RADIUS * 1.5)),
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def update(self, dt: float) -> list["AttackDebris"]:
        self._pulse_t += dt
        if self._hit_flash > 0:
            self._hit_flash -= dt

        spawned: list[AttackDebris] = []

        if self._phase == "landing":
            dx = self.target_x - self.x
            dy = self.target_y - self.y
            dist = math.hypot(dx, dy)
            if dist < self.LAND_SPEED * dt:
                self.x, self.y = self.target_x, self.target_y
                self._phase = "armed"
            else:
                nx, ny = dx / dist, dy / dist
                self.x += nx * self.LAND_SPEED * dt
                self.y += ny * self.LAND_SPEED * dt

        elif self._phase == "armed":
            self._fuse_timer += dt
            blink_freq = 4.0 + (self._fuse_timer / self.FUSE_TIME) * 14.0
            self._tick_timer -= dt
            if self._tick_timer <= 0:
                from ..systems import hit_sounds as _hs

                _hs.GOLEM_MINE_TIMER()
                self._tick_timer = 1.0 / blink_freq
            if self._fuse_timer >= self.FUSE_TIME:
                from ..systems import hit_sounds as _hs

                _hs.GOLEM_STOP_MINE_TIMER()
                _hs.GOLEM_ORB_PURPLE()
                self._phase = "exploded"
                for i in range(self.EXPL_SHARDS):
                    angle_deg = (360.0 / self.EXPL_SHARDS) * i + random.uniform(-5, 5)
                    spawned.append(
                        AttackDebris(
                            self.x,
                            self.y,
                            angle_deg,
                            speed_mult=1.4,
                            color=(255, 100, 60),
                        )
                    )
                self.dead = True

        self.rect.x = int(self.x - self.HIT_RADIUS)
        self.rect.y = int(self.y - self.HIT_RADIUS)
        return spawned

    def draw(self, surface: pygame.Surface) -> None:
        if self._phase == "exploded":
            return

        cx, cy = int(self.x), int(self.y)
        r = self.RADIUS
        fuse_ratio = (
            self._fuse_timer / self.FUSE_TIME if self._phase == "armed" else 0.0
        )
        blink_freq = 4.0 + fuse_ratio * 14.0
        blink_on = math.sin(self._pulse_t * blink_freq * math.pi * 2) > 0

        pulse = abs(math.sin(self._pulse_t * blink_freq * math.pi))
        glow_r = int(r * 1.6 + pulse * r * 0.6)
        glow_alpha = int(60 + pulse * 80)

        self._glow_surf.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self._glow_surf, (*self._COLOR_RING, glow_alpha), (glow_r, glow_r), glow_r
        )
        surface.blit(self._glow_surf, (cx - glow_r, cy - glow_r))

        S = max(2, r // 3)
        if self._hit_flash > 0:
            body_color = (255, 255, 255)
        else:
            body_color = self._COLOR_PULSE if blink_on else self._COLOR_BODY

        pygame.draw.rect(surface, body_color, (cx - S, cy - S * 3, S * 2, S * 6))
        pygame.draw.rect(surface, body_color, (cx - S * 3, cy - S, S * 6, S * 2))
        pygame.draw.rect(surface, body_color, (cx - S * 2, cy - S * 2, S * 4, S * 4))

        if self._phase == "armed":
            remaining = 1.0 - fuse_ratio
            arc_end = int(remaining * 360)
            if arc_end > 2:
                self._arc_surf.fill((0, 0, 0, 0))
                arc_col = (
                    int(255 * fuse_ratio + 60 * remaining),
                    int(200 * remaining),
                    40,
                    200,
                )
                pygame.draw.arc(
                    self._arc_surf,
                    arc_col,
                    (4, 4, r * 4 - 8, r * 4 - 8),
                    math.radians(90),
                    math.radians(90 + arc_end),
                    max(1, S),
                )
                surface.blit(self._arc_surf, (cx - r * 2, cy - r * 2))


class AttackDebris:
    """
    Fragmento de pedra disparado pelo boss.
    """

    MAX_HEALTH: Final[int] = 50  # 5 hits com BULLET_BASE_DAMAGE=10

    def __init__(
        self,
        x: float,
        y: float,
        angle_deg: float,
        speed_mult: float = 1.0,
        color: Optional[Tuple[int, int, int]] = None,
    ):
        self.x = x
        self.y = y
        self.size = random.randint(10, 16)
        self.health: int = self.MAX_HEALTH
        self.dead = False
        self.color = color if color is not None else _get_random_earth_color()

        # Cache de configurações
        self._screen_w = getattr(Config, "SCREEN_WIDTH", 480)
        self._screen_h = getattr(Config, "SCREEN_HEIGHT", 800)

        speed = getattr(Config, "GOLEM_ATTACK_DEBRIS_SPEED", 300) * speed_mult
        rad = math.radians(angle_deg)
        self.vx = math.cos(rad) * speed
        self.vy = math.sin(rad) * speed

        self._angle = angle_deg
        self._spin = random.uniform(-220, 220)

        # Hitbox dimensionada pela rocha sólida desenhada (~size de largura),
        # não pelo halo de glow externo. Half-extent = size//2 para acompanhar
        # exatamente o quadrado opaco visível.
        self._hit_half = max(1, self.size // 2)
        self.rect = pygame.Rect(
            int(self.x - self._hit_half),
            int(self.y - self._hit_half),
            self._hit_half * 2,
            self._hit_half * 2,
        )

        s = self.size // 2
        self._glow_surf = pygame.Surface((s * 4, s * 4), pygame.SRCALPHA)
        self._glow_surf.fill((*self.color, 60))
        # Vida para que ataques do jogador possam destruí-lo
        self.health = int(self.MAX_HEALTH)

    @property
    def causes_damage(self) -> bool:
        """Fragmentos sempre causam dano."""
        return True

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self._angle += self._spin * dt
        self.rect.x = int(self.x - self._hit_half)
        self.rect.y = int(self.y - self._hit_half)

        margin = 40
        if (
            self.y > self._screen_h + margin
            or self.y < -margin
            or self.x < -margin
            or self.x > self._screen_w + margin
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        s = self.size // 2
        c = self.color
        core = (255, 255, 255)
        surface.blit(self._glow_surf, (cx - s * 2, cy - s * 2))
        pygame.draw.rect(surface, c, (cx - s, cy - s, s * 2, s * 2))
        pygame.draw.rect(surface, core, (cx - s // 2, cy - s // 2, s, s))

    def collision_circle(self) -> tuple[float, float, float]:
        # Raio = metade da largura visível da rocha sólida (size//2), não o
        # raio do halo de glow que se estende até size*2.
        return self.x, self.y, float(self._hit_half)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.health -= int(damage)
        if self.health <= 0:
            self.dead = True
            return HitResult(
                killed=True,
                points=0,
                explosion_size=max(8, int(self.size)),
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)


class OrbitalDebris:
    """
    Pedra de terra usada no ataque Earth do Golem.
    """

    TRAIL_SPAWN_CHANCE = 0.4
    TRAIL_FADE_SPEED = 800.0

    # Static attribute annotations to help static analysis (Pylance)
    _S: int
    _size: int
    health: int

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        orbit_cx: float,
        orbit_cy: float,
        target_rx: float,
        target_ry: float,
        orbit_angle_start: float,
        rock_size: int,
        color: Tuple[int, int, int],
        S: int,
    ):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.dead = False
        self.x = orbit_cx + (random.random() - 0.5) * screen_w * 0.8
        self.y = screen_h + 50 + random.random() * 150
        self.orbit_cx = orbit_cx
        self.orbit_cy = orbit_cy
        self.target_rx = target_rx
        self.target_ry = target_ry
        self.orbit_angle = orbit_angle_start
        self.orbit_speed = 0.03 + random.random() * 0.04
        self._S = S
        self._size = rock_size
        self.color = color
        self.bob_offset = random.uniform(0, math.pi * 2)
        self.spin = random.uniform(0, 360)
        self.spin_speed = random.uniform(200, 450) * random.choice([-1, 1])
        self.trail: list[list[float]] = []
        self.phase = "pulling"
        self.fire_delay = 0.0
        self._fire_vx = 0.0
        self._fire_vy = 0.0
        self._fire_perp_x = 0.0
        self._fire_perp_y = 0.0
        self._fire_perp_decay = 3.5
        self._fire_gravity = getattr(Config, "GOLEM_DEBRIS_GRAVITY", 30)

        # Half-extent baseado na largura visível da rocha (size*S), não no
        # canvas inflado (size+2)*S. Usado tanto para rect quanto para o raio
        # de colisão, garantindo que a hitbox case com o sprite.
        self._hit_half = max(1, (S * self._size) // 2)
        self.rect = pygame.Rect(
            int(self.x) - self._hit_half,
            int(self.y) - self._hit_half,
            self._hit_half * 2,
            self._hit_half * 2,
        )

        canvas_size = (self._size + 2) * S * 2
        self._rock_surf = pygame.Surface((canvas_size, canvas_size), pygame.SRCALPHA)
        ox = canvas_size // 2 - (self._size * S) // 2
        oy = canvas_size // 2 - S
        if self._size == 2:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 2, S * 2))
        else:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 3, S * 2))
            pygame.draw.rect(self._rock_surf, self.color, (ox + S, oy - S, S, S))
            pygame.draw.rect(self._rock_surf, self.color, (ox - S, oy + S, S, S))
        self._dust_surf = pygame.Surface((S * 2, S * 2), pygame.SRCALPHA)
        # Vida simples para permitir que o jogador quebre os detritos
        self.health = max(1, int(self._size * 10))

    def _orbit_target(self) -> Tuple[float, float]:
        bobbing_y = math.sin(self.orbit_angle * 2 + self.bob_offset) * 15
        return (
            self.orbit_cx + math.cos(self.orbit_angle) * self.target_rx,
            self.orbit_cy + math.sin(self.orbit_angle) * self.target_ry + bobbing_y,
        )

    def fire_at(self, target_x: float, target_y: float) -> None:
        self.phase = "fired"
        base_speed = getattr(Config, "GOLEM_ORBITAL_DEBRIS_SPEED", 340) * 1.15
        spread_x = target_x + random.uniform(-250, 250)
        spread_y = target_y + random.uniform(-100, 250)
        dx, dy = spread_x - self.x, spread_y - self.y
        dist = math.hypot(dx, dy) or 1.0
        self._fire_vx, self._fire_vy = dx / dist * base_speed, dy / dist * base_speed
        perp_strength = random.uniform(-400, 400)
        self._fire_perp_x, self._fire_perp_y = (
            -dy / dist * perp_strength,
            dx / dist * perp_strength,
        )
        self._fire_perp_decay = random.uniform(1.8, 3.5)

    def update(
        self,
        dt: float,
        orbit_cx: float,
        orbit_cy: float,
        player_x: float = 0.0,
        player_y: float = 0.0,
    ) -> None:
        self.orbit_cx, self.orbit_cy = orbit_cx, orbit_cy
        self.orbit_angle += self.orbit_speed * 60 * dt

        if self.phase == "pulling":
            tx, ty = self._orbit_target()
            self.x += (tx - self.x) * min(1.0, 3.0 * dt)
            self.y += (ty - self.y) * min(1.0, 3.0 * dt)
        elif self.phase == "orbiting":
            tx, ty = self._orbit_target()
            self.x += (tx - self.x) * min(1.0, 12.0 * dt)
            self.y += (ty - self.y) * min(1.0, 12.0 * dt)
            if self.fire_delay > 0:
                self.fire_delay -= dt
                if self.fire_delay <= 0:
                    self.fire_at(player_x, player_y)
        elif self.phase == "fired":
            decay = math.exp(-self._fire_perp_decay * dt)
            self._fire_perp_x *= decay
            self._fire_perp_y *= decay
            self._fire_vy += self._fire_gravity * dt
            self.x += (self._fire_vx + self._fire_perp_x) * dt
            self.y += (self._fire_vy + self._fire_perp_y) * dt
            self.spin += self.spin_speed * dt
            if random.random() < self.TRAIL_SPAWN_CHANCE:
                self.trail.append([self.x, self.y, 255.0])
            if (
                self.y > self.screen_h + 80
                or self.x < -80
                or self.x > self.screen_w + 80
            ):
                self.dead = True

        for t in self.trail:
            t[2] -= self.TRAIL_FADE_SPEED * dt
        self.trail = [t for t in self.trail if t[2] > 0]
        self.rect.x = int(self.x) - self._hit_half
        self.rect.y = int(self.y) - self._hit_half

    @property
    def causes_damage(self) -> bool:
        """Só causa dano quando arremessada."""
        return self.phase == "fired"

    @property
    def behind_boss(self) -> bool:
        """True quando a pedra está 'atrás' do boss na órbita (sin < 0)."""
        return math.sin(self.orbit_angle) < 0 and self.phase != "fired"

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha a pedra orbital com rastro e rotação."""
        for t in self.trail:
            alpha = int(max(0, min(255, t[2])))
            if alpha > 0:
                s = self._S
                self._dust_surf.fill((0, 0, 0, 0))
                pygame.draw.rect(
                    self._dust_surf,
                    (*self.color, alpha),
                    (0, 0, s * 2, s * 2),
                )
                surface.blit(self._dust_surf, (int(t[0]) - s, int(t[1]) - s))

        rotated = pygame.transform.rotate(self._rock_surf, self.spin)
        rw, rh = rotated.get_size()
        surface.blit(rotated, (int(self.x) - rw // 2, int(self.y) - rh // 2))

    def collision_circle(self) -> tuple[float, float, float]:
        # Raio = metade da largura da rocha (size*S/2), não size*S inteiro.
        return self.x, self.y, float(self._hit_half)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.health -= int(damage)
        if self.health <= 0:
            self.dead = True
            return HitResult(
                killed=True,
                points=0,
                explosion_size=max(10, int(self._size * 4)),
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)


class EmergeDebris:
    """
    Detritos lançados quando o boss irrompe do chão.
    Design similar ao OrbitalDebris, com gravidade.
    """

    TRAIL_FADE_SPEED = 600.0
    # Paleta expandida: tons de terra, pedras escuras e poeira
    EARTH_COLORS = [
        (101, 67, 33),  # Marrom escuro (terra)
        (84, 56, 26),  # Marrom profundo
        (65, 65, 65),  # Cinza pedra
        (45, 45, 45),  # Pedra escura
        (139, 115, 85),  # Barro/Argila
        (160, 82, 45),  # Sienna
    ]

    # Static attribute annotations to help static analysis (Pylance)
    S: int
    rock_size: int
    health: int

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        color: Optional[Tuple[int, int, int]] = None,
        S: int = 10,
        rock_size: int = 3,
        gravity: Optional[float] = None,
    ):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = vx, vy
        self.dead = False
        self.S = S
        self.rock_size = rock_size
        self.color = color if color else random.choice(self.EARTH_COLORS)
        self.spin = random.uniform(0, 360)
        self.spin_speed = random.uniform(150, 450) * random.choice([-1, 1])
        self.trail: list[list[float]] = []
        self._gravity = (
            gravity
            if gravity is not None
            else getattr(Config, "GOLEM_DEBRIS_GRAVITY", 30) * 5.0
        )

        self._screen_w = getattr(Config, "SCREEN_WIDTH", 480)
        self._screen_h = getattr(Config, "SCREEN_HEIGHT", 800)

        # Half-extent baseado na largura visível da rocha (size*S), espelhando
        # o mesmo cálculo de OrbitalDebris para hitbox coerente com o sprite.
        self._hit_half = max(1, (S * self.rock_size) // 2)
        self.rect = pygame.Rect(
            int(self.x) - self._hit_half,
            int(self.y) - self._hit_half,
            self._hit_half * 2,
            self._hit_half * 2,
        )

        canvas_size = (self.rock_size + 2) * S * 2
        self._rock_surf = pygame.Surface((canvas_size, canvas_size), pygame.SRCALPHA)
        ox = canvas_size // 2 - (self.rock_size * S) // 2
        oy = canvas_size // 2 - S
        if self.rock_size <= 2:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 2, S * 2))
        else:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 3, S * 2))
            pygame.draw.rect(self._rock_surf, self.color, (ox + S, oy - S, S, S))
            pygame.draw.rect(self._rock_surf, self.color, (ox - S, oy + S, S, S))
        self._dust_surf = pygame.Surface((S * 2, S * 2), pygame.SRCALPHA)
        # Vida para permitir destruição por tiros
        self.health = max(1, int(self.rock_size * 12))

    @property
    def causes_damage(self) -> bool:
        return True

    def update(self, dt: float) -> None:
        # Aplicar gravidade
        self.vy += self._gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.spin += self.spin_speed * dt

        # Rastro
        if random.random() < 0.3:
            self.trail.append([self.x, self.y, 200.0])
        for t in self.trail:
            t[2] -= self.TRAIL_FADE_SPEED * dt
        self.trail = [t for t in self.trail if t[2] > 0]

        self.rect.x = int(self.x) - self._hit_half
        self.rect.y = int(self.y) - self._hit_half

        if (
            self.y > self._screen_h + 100
            or self.x < -100
            or self.x > self._screen_w + 100
        ):
            self.dead = True

    def draw_trail(self, surface: pygame.Surface) -> None:
        """Desenha apenas o rastro de poeira (atrás)."""
        # Cor de poeira neutra/cinza para contraste com a pedra
        dust_base = (140, 130, 120)
        for t in self.trail:
            alpha = int(_clamp(t[2], 0, 255))
            s = self.S
            self._dust_surf.fill((0, 0, 0, 0))
            # Usa cor de poeira com o alpha do rastro
            pygame.draw.rect(
                self._dust_surf, (*dust_base, alpha // 2), (0, 0, s * 2, s * 2)
            )
            surface.blit(self._dust_surf, (int(t[0]) - s, int(t[1]) - s))

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha apenas o corpo sólido da pedra."""
        rotated = pygame.transform.rotate(self._rock_surf, self.spin)
        rw, rh = rotated.get_size()
        surface.blit(rotated, (int(self.x) - rw // 2, int(self.y) - rh // 2))

    def collision_circle(self) -> tuple[float, float, float]:
        # Raio = metade da largura da rocha (size*S/2), consistente com a rect.
        return self.x, self.y, float(self._hit_half)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.health -= int(damage)
        if self.health <= 0:
            self.dead = True
            return HitResult(
                killed=True,
                points=0,
                explosion_size=max(10, int(self.rock_size * 4)),
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)


# ============================================================================
# PARTICULA DE CARGA
# ============================================================================


class _ChargeParticle:
    def __init__(
        self,
        pupil_x: float,
        pupil_y: float,
        color: Tuple[int, int, int],
        size: Optional[int] = None,
        radial_speed: Optional[float] = None,
        orbit_speed: Optional[float] = None,
        dist: Optional[float] = None,
        follow_pupil: bool = True,
        max_burst_dist: float = 300.0,
    ):
        self.angle = random.uniform(0, math.pi * 2)
        self.dist = dist if dist is not None else (120 + random.uniform(0, 40))
        self.start_dist = self.dist
        self.orbit_speed = (
            orbit_speed if orbit_speed is not None else (0.05 + random.uniform(0, 0.08))
        )
        self.radial_speed = (
            radial_speed if radial_speed is not None else (80 + random.uniform(0, 80))
        )
        self.color = color
        self.size = size if size is not None else random.randint(3, 6)
        self.px, self.py = pupil_x, pupil_y
        self.anchor_x, self.anchor_y = pupil_x, pupil_y
        self.follow_pupil = follow_pupil
        self.max_burst_dist = max_burst_dist
        self.dead = False
        self._surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)

    def update(self, dt: float, pupil_x: float, pupil_y: float) -> None:
        self.dist -= self.radial_speed * dt
        speed_mul = 1.0 + (1.0 - _clamp(self.dist / self.start_dist, 0, 1)) * 2.0
        self.angle += self.orbit_speed * speed_mul * (dt * 60)
        # Morre ao convergir no centro (partículas normais)
        # ou ao se afastar demais (burst de morte)
        if self.radial_speed > 0 and self.dist < 2:
            self.dead = True
            return
        if self.radial_speed < 0 and self.dist > self.max_burst_dist:
            self.dead = True
            return

        cx = pupil_x if self.follow_pupil else self.anchor_x
        cy = pupil_y if self.follow_pupil else self.anchor_y
        self.px = cx + math.cos(self.angle) * self.dist
        self.py = cy + math.sin(self.angle) * self.dist

    def draw(self, surface: pygame.Surface) -> None:
        if self.radial_speed > 0:
            # Partícula de convergência: fica mais transparente ao chegar no centro
            ratio = _clamp(self.dist / self.start_dist * 2, 0, 1)
        else:
            # Partícula de burst: fica mais transparente ao se afastar
            ratio = _clamp(1.0 - self.dist / self.max_burst_dist, 0, 1)
        if ratio < 0.05:
            return
        self._surf.fill((0, 0, 0, 0))
        pygame.draw.rect(
            self._surf,
            (*self.color, int(ratio * 220)),
            (0, 0, self.size * 2, self.size * 2),
        )
        surface.blit(self._surf, (int(self.px) - self.size, int(self.py) - self.size))


class StoneGolemBoss(BossHitMixin):
    """
    Boss do Mundo 1 — Cordilheira Celestial.
    Implementação otimizada com FSM modularizada.
    """

    is_boss: bool = True
    SCALE = 10
    MAX_CHARGE_PARTICLES = 100

    # Frações de HP que disparam mudanças de fase.
    # Half phase: boss afunda e invoca minas/bots auxiliares.
    # Third phase: segunda submersão + entra em rage (movimento e ataques acelerados).
    HALF_PHASE_HP_FRACTION: Final = 0.75
    THIRD_PHASE_HP_FRACTION: Final = 0.35

    MUSIC_STATE: Final = MusicState.STONE_GOLEM_BOSS

    # Otimização: Estados onde o boss deve flutuar ou ficar ancorado
    _ANCHORED_STATES = frozenset(
        {
            "CHARGE",
            "FIRE",
            "EARTH_SHAKE",
            "EARTH_PULL",
            "EARTH_ORBIT",
            "EARTH_FIRE",
            "ORB_SPAWN",
            "ORB_HOLD",
            "ORB_FIRE",
            "SWEEP_CHARGE",
            "SWEEP_FIRE",
        }
    )

    # Cache de máscara pixel-perfeita para colisão baseada em pixel map
    _collision_mask: Optional[pygame.mask.Mask] = None

    def __init__(
        self,
        _x: float,
        y: float,
        health: Optional[int] = None,
        difficulty_multiplier: float = 1.0,
        event_bus: Optional["EventBus"] = None,
    ):
        # Declarações explícitas para satisfazer W0201 (pylint).
        # Valores reais são atribuídos pelos helpers _init_*.
        self.x: float = 0.0
        self.y: float = 0.0
        self.w: int = 0
        self.h: int = 0
        self.dead: bool = False
        self.health: int = 0
        self.max_health: int = 0
        self.hit_score: int = 0
        self.difficulty_multiplier: float = 1.0
        self.direction: int = 1
        self.target_y: float = 0.0
        self.entry_speed: float = 0.0
        self.fsm_state: str = "ENTERING"
        self._prev_fsm_state: str = "ENTERING"
        self._last_attack: str = ""
        self._attack_bag: List[str] = []
        self.fsm_ticks: float = 0.0
        self.eye_growth: float = 0.0
        self._scan_step: int = 0
        self._current_float_y: float = 0.0
        self.stomp_shake: float = 0.0
        self._jitter_x: float = 0.0
        self._jitter_y: float = 0.0
        self._sweep_angle: float = 0.0
        self._sweep_total: float = 0.0
        self._shards_fired_at: set[int] = set()
        self._sweep_locked_angle: float = 0.0
        self._sweep_lock_done: bool = False
        self._orbital_debris: List[OrbitalDebris] = []
        self._mines: List[GolemMine] = []
        self._half_phase_mines: List[GolemMine] = []
        self._half_phase_bots: List[ElementalRobot] = []
        self._fire_shots_count: int = 0
        self._fire_shot_timer: float = 0.0
        self._fire_ready: bool = False
        self._cycles_since_fire: int = 0
        self._orb_shots_done: int = 0
        self._orb_rotation: float = 0.0
        self._charge_particles: List[_ChargeParticle] = []
        self._emerge_debris: List[EmergeDebris] = []
        self._emerge_debris_timer: float = 0.0
        self._burst_done: bool = False
        self._retreat_step: int = 0
        self._retreat_waiting: bool = False
        self._retreat_wait_timer: float = 0.0
        self._half_phase_triggered: bool = False
        self._half_phase_pending: bool = False
        self._half_phase_bots_spawned: bool = False
        self._half_phase_summon_timer: float = 0.0
        self._half_phase_wave_timer: float = 0.0
        self._half_mine_queue: int = 0
        self._half_mine_timer: float = 0.0
        self._third_phase_triggered: bool = False
        self._third_phase_pending: bool = False
        self._current_half_phase: int = 0
        self._sentry_active: bool = False
        self._sentry_spawn_timer: float = 0.0
        self._active_sentry: Any | None = None
        self._entity_manager: Any | None = None
        self._bus = event_bus
        self._dive_phase: str = "none"
        self._dive_timer: float = 0.0
        self._dive_start_y: float = 0.0
        self._time: float = 0.0
        self.rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.emp_linger_timer: float = 0.0
        self._screen_w: int = 0
        self._screen_h: int = 0
        self._body_surf_top: Optional[pygame.Surface] = None
        self._body_surf_bottom: Optional[pygame.Surface] = None
        self._thruster_surfs: list[pygame.Surface] = []
        self._cone_surf: pygame.Surface
        self._beam_surf: pygame.Surface
        self._halo_surf: pygame.Surface

        self._init_stats(health, difficulty_multiplier)
        self._init_fsm(y)
        self._init_surfaces()

    def _init_stats(self, health: Optional[int], difficulty_multiplier: float) -> None:
        """Inicializa atributos de status e dificuldade."""
        S = self.SCALE
        self._screen_w = getattr(Config, "SCREEN_WIDTH", 480)
        self._screen_h = getattr(Config, "SCREEN_HEIGHT", 800)
        self.w, self.h = _PIXEL_COLS * S, _PIXEL_ROWS * S

        margin_x = 70
        # Inicia abaixo da tela (irrompendo de baixo)
        self.x = self._screen_w - self.w - margin_x
        self.y = float(self._screen_h + 100)
        self.difficulty_multiplier = difficulty_multiplier

        base_health = getattr(Config, "GOLEM_HEALTH", 2500)
        self.max_health = int(base_health * difficulty_multiplier)
        self.health = health if health is not None else self.max_health
        self.dead, self.hit_score = False, 60

    def _init_fsm(self, target_y: float) -> None:
        """Inicializa o estado da máquina de estados (FSM)."""
        self.target_y = target_y
        self.direction = 1
        self.entry_speed = getattr(Config, "GOLEM_ENTRY_SPEED", 160)
        self.fsm_state = "ENTERING"
        self._prev_fsm_state = "ENTERING"
        self._last_attack = ""
        self._attack_bag = []
        self.fsm_ticks = 0.0

        # Estados visuais
        self.eye_growth = 0.0
        self._scan_step = 0
        self._current_float_y = 0.0
        self.stomp_shake = 0.0
        self._jitter_x, self._jitter_y = 0.0, 0.0

        # Ataques
        self._sweep_angle = math.pi / 2
        self._sweep_total = math.radians(30)
        self._shards_fired_at: set[int] = set()
        self._sweep_locked_angle, self._sweep_lock_done = math.pi / 2, False
        self._orbital_debris = []
        self._mines = []
        self._half_phase_mines = []
        self._half_phase_bots = []
        self._fire_shots_count, self._fire_shot_timer, self._cycles_since_fire = (
            0,
            0.0,
            0,
        )
        self._fire_ready = False
        self._orb_shots_done, self._orb_rotation = 0, 0.0
        self._charge_particles = []
        self._emerge_debris: List[EmergeDebris] = []
        self._emerge_debris_timer: float = 0.0
        self._burst_done: bool = False
        self._retreat_step = 0
        self._retreat_waiting = False
        self._retreat_wait_timer = 0.0
        self._half_phase_triggered = False
        self._half_phase_pending = False
        self._half_phase_bots_spawned = False
        self._half_phase_summon_timer = 0.0
        self._half_phase_wave_timer = 0.0
        self._half_mine_queue = 0
        self._half_mine_timer = 0.0
        self._third_phase_triggered = False
        self._third_phase_pending = False
        self._current_half_phase = 0
        self._sentry_active = False
        self._sentry_spawn_timer = 0.0
        self._active_sentry = None
        self._time = 0.0
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        self.emp_linger_timer = 0.0

    def _init_surfaces(self) -> None:
        """Inicializa e pré-renderiza as superfícies gráficas."""
        S = self.SCALE
        self._body_surf_top, self._body_surf_bottom = None, None
        self._pre_bake_body()
        self._thruster_surfs = [
            pygame.Surface((S * 10 + 2, S * 4 + 2), pygame.SRCALPHA) for _ in range(5)
        ]
        self._cone_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )
        self._beam_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )
        self._halo_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )

    def _pre_bake_body(self) -> None:
        S = self.SCALE
        self._body_surf_top = pygame.Surface(
            (self.w, _EYE_ROW_ABOVE * S), pygame.SRCALPHA
        )
        for r in range(_EYE_ROW_ABOVE):
            for c, k in enumerate(_PIXEL_MAP[r]):
                if k:
                    pygame.draw.rect(self._body_surf_top, _C[k], (c * S, r * S, S, S))
        bottom_start = _EYE_ROW_BELOW + 1
        self._body_surf_bottom = pygame.Surface(
            (self.w, (_PIXEL_ROWS - bottom_start) * S), pygame.SRCALPHA
        )
        for r in range(bottom_start, _PIXEL_ROWS):
            dr = r - bottom_start
            for c, k in enumerate(_PIXEL_MAP[r]):
                if k:
                    pygame.draw.rect(
                        self._body_surf_bottom, _C[k], (c * S, dr * S, S, S)
                    )

    def _shared_center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self._current_float_y

    def _pupil_pos(self) -> Tuple[float, float]:
        S = self.SCALE
        px = (
            self.x + _EYE_COL_START * S + self._jitter_x + S * 2.5 + self._scan_step * S
        )
        return px, self._shared_center()[1] + self._jitter_y

    def _change_fsm(self, new_state: str) -> None:
        self._prev_fsm_state, self.fsm_state, self.fsm_ticks = (
            self.fsm_state,
            new_state,
            0.0,
        )
        from ..systems import hit_sounds as _hs

        if self._prev_fsm_state == "SWEEP_FIRE":
            _hs.GOLEM_STOP_SWEEP_LASER()

        if new_state == "CHARGE":
            self._charge_particles.clear()
            _hs.GOLEM_CHARGING()
        elif new_state == "FIRE":
            self._fire_shots_count, self._fire_shot_timer, self._cycles_since_fire = (
                0,
                0.0,
                0,
            )
            self._fire_ready = False
            _hs.GOLEM_STOP_CHARGING()
        elif new_state == "ORB_SPAWN":
            self._orb_rotation, self._orb_shots_done = 0.0, 0
        elif new_state == "SWEEP_CHARGE":
            self._sweep_locked_angle, self._sweep_lock_done = math.pi / 2, False
            _hs.GOLEM_CHARGING()
        elif new_state == "SWEEP_FIRE":
            self._sweep_angle, self._shards_fired_at = (
                self._sweep_locked_angle - self._sweep_total / 2,
                set[int](),
            )
            _hs.GOLEM_STOP_CHARGING()
            _hs.GOLEM_SWEEP_LASER()
        elif new_state == "EARTH_PULL":
            self._orbital_debris.clear()
            cx, cy, S = *self._shared_center(), self.SCALE
            for _ in range(15):
                rx, ry = (
                    self.w * 0.45 + random.random() * self.w * 0.2,
                    self.w * 0.12 + random.random() * self.w * 0.1,
                )
                self._orbital_debris.append(
                    OrbitalDebris(
                        self._screen_w,
                        self._screen_h,
                        cx,
                        cy,
                        rx,
                        ry,
                        random.random() * math.pi * 2,
                        2 if random.random() > 0.5 else 3,
                        _get_random_earth_color(),  # Usa a nova paleta
                        S,
                    )
                )
        elif new_state == "EARTH_ORBIT":
            for r in self._orbital_debris:
                r.phase = "orbiting"
        elif new_state == "EARTH_FIRE":
            for r in self._orbital_debris:
                if r.phase == "orbiting":
                    r.fire_delay = random.uniform(0.1, 1.2)
        elif new_state == "HALF_RETREAT":
            self._half_phase_summon_timer = 0.0
            self._half_phase_wave_timer = 0.0
            self._half_phase_bots_spawned = False
            self._half_phase_mines.clear()
            self._half_phase_bots.clear()
            self._orbital_debris.clear()
            self._mines.clear()
            self._charge_particles.clear()
            self._emerge_debris.clear()
            self._burst_done = False
            self._retreat_step = 0
            self._retreat_waiting = False
            self._retreat_wait_timer = 0.0
            self._emerge_debris_timer = 0.0
            self._dive_phase = "none"
            self._dive_timer = 0.0
        elif new_state == "HALF_SUMMON":
            self._half_phase_summon_timer = 0.0
        elif new_state == "HALF_VOLLEY":
            self._half_phase_wave_timer = 0.0
            self._half_mine_queue = 0
            self._half_mine_timer = 0.0

    def _start_half_phase(self) -> None:
        self._half_phase_triggered = True
        self._current_half_phase = 1
        self._change_fsm("HALF_RETREAT")

    def _start_third_phase(self) -> None:
        self._third_phase_triggered = True
        self._current_half_phase = 2
        self._change_fsm("HALF_RETREAT")

    def _spawn_half_phase_bots(self) -> None:
        manager = self._entity_manager
        if manager is None or self._half_phase_bots_spawned:
            return

        screen_w = self._screen_w
        screen_h = self._screen_h
        left_bot = manager.spawn_elemental_robot(
            x=screen_w * 0.28,
            y=screen_h * 0.2,
            difficulty_multiplier=self.difficulty_multiplier,
        )
        right_bot = manager.spawn_elemental_robot(
            x=screen_w * 0.72,
            y=screen_h * 0.2,
            difficulty_multiplier=self.difficulty_multiplier,
        )
        self._half_phase_bots = [left_bot, right_bot]
        self._half_phase_bots_spawned = True

    def _active_half_phase_bots(self) -> list[ElementalRobot]:
        bots = self._half_phase_bots
        write = 0
        for bot in bots:
            if not bot.dead:
                bots[write] = bot
                write += 1
        del bots[write:]
        return bots

    def _spawn_half_phase_mines(
        self,
        new_mines: List[GolemMine],
        player_x: float,
        player_y: float,
    ) -> None:
        del player_x, player_y
        if self._half_phase_mines:
            return

        base_x = self.x + self.w / 2
        base_y = self.y + self.h / 2
        screen_w = self._screen_w
        screen_h = self._screen_h
        for _ in range(3):
            target_x = random.uniform(90, screen_w - 90)
            target_y = random.uniform(90, screen_h - 120)
            mine = GolemMine(base_x, base_y, target_x, target_y)
            self._half_phase_mines.append(mine)
            new_mines.append(mine)

    def _finish_half_phase(self) -> None:
        was_third_phase = self._current_half_phase == 2
        self._half_phase_mines.clear()
        self._half_phase_bots.clear()
        self._half_phase_bots_spawned = False
        self._half_phase_summon_timer = 0.0
        self._half_phase_wave_timer = 0.0
        self._half_mine_queue = 0
        self._half_mine_timer = 0.0
        self._emerge_debris.clear()
        self._charge_particles.clear()
        self._orbital_debris.clear()
        self._mines.clear()
        self._attack_bag.clear()
        self._last_attack = ""
        self._cycles_since_fire = 0
        self._fire_ready = False
        self._fire_shots_count = 0
        self._fire_shot_timer = 0.0
        self._orb_shots_done = 0
        self._orb_rotation = 0.0
        self._shards_fired_at.clear()
        self._sweep_locked_angle = math.pi / 2
        self._sweep_lock_done = False
        self._current_float_y = 0.0
        self._scan_step = 0
        self._jitter_x = 0.0
        self._jitter_y = 0.0
        self._burst_done = False
        self._current_half_phase = 0
        self.y = float(self._screen_h + 100)
        if was_third_phase:
            self._sentry_active = True
            self._sentry_spawn_timer = 0.0
            self._active_sentry = None
        self._change_fsm("ENTERING")

    def _update_sentry_spawn(self, dt: float, entity_manager: Any | None) -> None:
        if not self._sentry_active or entity_manager is None:
            return

        # Cull reference if the sentry died
        if self._active_sentry is not None and getattr(
            self._active_sentry, "dead", True
        ):
            self._active_sentry = None

        # If no sentry alive, count down and spawn one
        if self._active_sentry is None:
            self._sentry_spawn_timer += dt
            if self._sentry_spawn_timer >= 10.0:
                self._sentry_spawn_timer = 0.0
                self._active_sentry = entity_manager.spawn_stone_sentry()

    @property
    def _rage_mult(self) -> float:
        """Multiplicador de velocidade ativo a partir da third phase (rage)."""
        threshold = self.max_health * self.THIRD_PHASE_HP_FRACTION
        return 1.5 if self.health <= threshold else 1.0

    @property
    def _attack_spd(self) -> float:
        """difficulty_multiplier × 1.25x rage — aplicado nas durações dos estados de ataque."""
        threshold = self.max_health * self.THIRD_PHASE_HP_FRACTION
        rage = 1.25 if self.health <= threshold else 1.0
        return self.difficulty_multiplier * rage

    @property
    def emerge_debris(self) -> List[EmergeDebris]:
        """Expõe os detritos de emerge/submerge para colisão externa."""
        return self._emerge_debris

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        entity_manager: Any | None = None,
    ) -> Tuple[List["GolemMine"], List[AttackDebris], List[OrbitalDebris]]:
        new_mines: List[GolemMine] = []
        new_shards: List[AttackDebris] = []
        self._entity_manager = entity_manager
        self._time += dt
        self.fsm_ticks += dt

        target_float = (
            0.0
            if self.fsm_state in self._ANCHORED_STATES
            else round(math.sin(self._time * 2.5) * 12)
        )
        self._current_float_y += (target_float - self._current_float_y) * min(
            1.0, 6.0 * dt
        )
        self._scan_step = (
            round(math.cos(self._time * 3))
            if self.fsm_state in {"SCAN", "OPENING", "ORB_SPAWN"}
            else 0
        )

        # Executa a FSM primeiro para definir os jitter e novos estados
        self._run_fsm(dt, player_x, player_y, new_mines, new_shards)

        # Gerenciamento de tremores (jitter)
        S = self.SCALE
        if self.fsm_state in ("EARTH_SHAKE", "EARTH_PULL", "SWEEP_FIRE"):
            # Estados nativos de tremor do boss
            self._jitter_x, self._jitter_y = (
                random.uniform(-0.5, 0.5) * S,
                random.uniform(-0.5, 0.5) * S,
            )
        elif self.fsm_state in ("ENTERING", "HALF_RETREAT"):
            # Deixa o jitter ser controlado pelos métodos de estado (antecipação)
            pass
        else:
            # Reseta jitter para estados estáticos
            self._jitter_x, self._jitter_y = 0.0, 0.0

        self.stomp_shake = self._jitter_y

        # Sweep in-place: update + filter de mortos em uma passagem só,
        # sem rebuild de lista por frame.
        px, py = self._pupil_pos()
        particles = self._charge_particles
        write = 0
        for p in particles:
            p.update(dt, px, py)
            if not p.dead:
                particles[write] = p
                write += 1
        del particles[write:]

        debris = self._emerge_debris
        write = 0
        for d in debris:
            d.update(dt)
            if not d.dead:
                debris[write] = d
                write += 1
        del debris[write:]

        mines = self._mines
        write = 0
        for m in mines:
            if not m.dead:
                mines[write] = m
                write += 1
        del mines[write:]

        cx, cy = self._shared_center()
        orbital = self._orbital_debris
        write = 0
        for r in orbital:
            r.update(dt, cx, cy, player_x, player_y)
            if not r.dead:
                orbital[write] = r
                write += 1
        del orbital[write:]

        self._update_sentry_spawn(dt, entity_manager)

        # Rect acompanha float vertical e jitter para casar com a posição desenhada.
        # get_collision_mask_data usa self.rect como fonte única de verdade,
        # por isso jitter também deve entrar aqui.
        self.rect.x = int(self.x + self._jitter_x)
        self.rect.y = int(self.y + self._current_float_y + self._jitter_y)
        self._entity_manager = None
        return new_mines, new_shards, self._orbital_debris

    def _run_fsm(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        new_mines: List["GolemMine"],
        new_shards: List[AttackDebris],
    ) -> None:
        """Delegador da FSM para métodos específicos de estado."""
        handler = getattr(self, f"_fsm_{self.fsm_state.lower()}", None)
        if handler:
            handler(dt, player_x, player_y, new_mines, new_shards)

    def _fsm_entering(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        # Posição onde o "burst" acontece (quando o topo do boss toca a borda da tela)
        burst_y = self._screen_h - 20

        # Antes do burst: Tremor forte no chão (abaixo da tela)
        if self.y > burst_y:
            self.y -= self.entry_speed * 0.4 * dt
            self._jitter_x = random.uniform(-5, 5)
            self._jitter_y = random.uniform(-2, 2)

            # Alguns detritos prévios (intervalo fixo de 0.25s)
            self._emerge_debris_timer += dt
            if self._emerge_debris_timer >= 0.25:
                self._emerge_debris_timer = 0.0
                self._spawn_debris_cluster(1, _px, _py)
        else:
            # O BURST: Sobe muito rápido
            speed = self.entry_speed * 2.5
            self.y -= speed * dt
            self._jitter_x = random.uniform(-8, 8)
            self._jitter_y = random.uniform(-8, 8)

            # No frame exato do burst (primeira vez cruzando burst_y), solta o cluster massivo
            if not self._burst_done:
                self._spawn_debris_cluster(
                    Config.GOLEM_EMERGE_DEBRIS_COUNT,
                    _px,
                    _py,
                )
                self._burst_done = True
                from ..systems import hit_sounds as _hs

                _hs.GOLEM_ERUPTION()

            # Detritos contínuos durante a subida explosiva (intervalo fixo de 0.12s)
            self._emerge_debris_timer += dt
            if self._emerge_debris_timer >= 0.12:
                self._emerge_debris_timer = 0.0
                self._spawn_debris_cluster(
                    2,
                    _px,
                    _py,
                )

        if self.y <= self.target_y:
            self.y = self.target_y
            self._jitter_x, self._jitter_y = 0.0, 0.0
            self._burst_done = False  # Reset para a próxima vez (se houver)
            self._change_fsm("SCAN")

    def _fsm_half_retreat(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        # Profundidades de parada intermediárias
        _SINK_OFFSETS = (self.h * 0.38, self.h * 0.74)
        _BASE = getattr(Config, "GOLEM_SUBMERGE_DEBRIS_COUNT", 8)
        _BURST_COUNTS = (_BASE, _BASE, _BASE)
        _WAIT = 3.0
        retreat_speed = getattr(Config, "GOLEM_ENTRY_SPEED", 160) * 1.8

        if self._retreat_waiting:
            # Tremor de "luta" — intensidade cresce por step
            intensity = 3.5 + self._retreat_step * 2.0
            self._jitter_x = random.uniform(-intensity, intensity)
            self._jitter_y = random.uniform(-intensity * 0.45, intensity * 0.45)

            # Detritos contínuos durante a pausa
            self._emerge_debris_timer += dt
            interval = max(0.12, 0.22 - self._retreat_step * 0.05)
            if self._emerge_debris_timer >= interval:
                self._emerge_debris_timer = 0.0
                self._spawn_debris_cluster(
                    2 + self._retreat_step,
                    _px,
                    _py,
                    spawn_from_bottom=True,
                )

            self._retreat_wait_timer += dt
            if self._retreat_wait_timer >= _WAIT:
                self._retreat_step += 1
                self._retreat_waiting = False
                self._retreat_wait_timer = 0.0
                self._emerge_debris_timer = 0.0
                self._dive_phase = "none"  # Reset para a próxima descida
        else:
            # LÓGICA DE MERGULHO COM ANTECIPAÇÃO
            if self._dive_phase == "none":
                self._dive_phase = "tension"
                self._dive_timer = 0.0
                self._dive_start_y = self.y

            self._dive_timer += dt

            if self._dive_phase == "tension":
                # 1. Tensão: Tremor forte parado (1.0s)
                self._jitter_x = random.uniform(-12, 12)
                self._jitter_y = random.uniform(-8, 8)

                # Tremor de tela sutil durante a antecipação da PRIMEIRA descida
                if self._retreat_step == 0 and self._bus and random.random() < 0.15:
                    from ..events import game_events as events

                    self._bus.emit(events.ScreenShake(intensity=2, duration=0.1))

                if self._dive_timer >= 1.0:
                    self._dive_phase = "recoil"
                    self._dive_timer = 0.0

            elif self._dive_phase == "recoil":
                # 2. Recuo: Move para cima de forma tensa (1.0s)
                recoil_dist = 70.0
                recoil_dur = 1.0
                recoil_speed = recoil_dist / recoil_dur
                self.y -= recoil_speed * dt
                # Tremor aumenta conforme chega no ponto máximo do recuo
                intensity = 4.0 + (self._dive_timer / recoil_dur) * 6.0
                self._jitter_x = random.uniform(-intensity, intensity)
                self._jitter_y = random.uniform(-intensity * 0.7, intensity * 0.7)
                if self._dive_timer >= recoil_dur:
                    self._dive_phase = "pause"
                    self._dive_timer = 0.0

            elif self._dive_phase == "pause":
                # 3. Pausa Dramática: Congelamento total (0.5s)
                self._jitter_x, self._jitter_y = 0.0, 0.0
                if self._dive_timer >= 0.5:
                    self._dive_phase = "action"
                    self._dive_timer = 0.0

            elif self._dive_phase == "action":
                # 4. Mergulho Violento: Velocidade muito maior (Contrast)
                dive_speed = retreat_speed * 4.5
                self.y += dive_speed * dt
                self._jitter_x = random.uniform(-2, 2)

                # Verifica se atingiu o alvo (parada ou fim da tela)
                target_y = 0.0
                if self._retreat_step < 2:
                    target_bottom = self._screen_h + _SINK_OFFSETS[self._retreat_step]
                    target_y = float(target_bottom - self.h)
                else:
                    target_y = float(self._screen_h + self.h + 80)

                if self.y >= target_y:
                    self.y = target_y
                    self._dive_phase = "impact"
                    self._dive_timer = 0.0

                    # IMPACTO PESADO
                    from ..events import game_events as events
                    from ..systems import hit_sounds as _hs

                    # Screen Shake: Muito mais forte na primeira descida (step 0)
                    if self._bus:
                        shake_intensity = 22 if self._retreat_step == 0 else 14
                        self._bus.emit(
                            events.ScreenShake(intensity=shake_intensity, duration=0.5)
                        )

                    # Burst de detritos (SÓ NO IMPACTO)
                    burst_count = _BURST_COUNTS[min(2, self._retreat_step)]
                    self._spawn_debris_cluster(
                        burst_count * 2,
                        _px,
                        _py,
                        spawn_from_bottom=True,
                        force=True,
                    )

                    # Som e transição
                    _hs.GOLEM_ERUPTION()

                    if self._retreat_step < 2:
                        self._retreat_waiting = True
                    else:
                        # Submersão completa
                        self._jitter_x = 0.0
                        self._jitter_y = 0.0
                        self._change_fsm("HALF_SUMMON")

    def _fsm_half_summon(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._half_phase_summon_timer += dt

        # Após submergir, espera 3s antes de invocar os bots e retomar ataques.
        if self._half_phase_summon_timer < 3.0:
            return

        if not self._half_phase_bots_spawned:
            self._spawn_half_phase_bots()

        if self._half_phase_bots_spawned and self._half_phase_summon_timer >= 3.35:
            self._change_fsm("HALF_VOLLEY")

    def _fsm_half_volley(
        self,
        dt: float,
        _player_x: float,
        _player_y: float,
        new_mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        active_bots = self._active_half_phase_bots()
        hp_mines = self._half_phase_mines
        write = 0
        for m in hp_mines:
            if not m.dead:
                hp_mines[write] = m
                write += 1
        del hp_mines[write:]

        if active_bots:
            # Kick off a new volley of 3 when the previous one is fully gone and no queue pending
            if self._half_mine_queue == 0 and not self._half_phase_mines:
                self._half_mine_queue = 3
                self._half_mine_timer = 0.0

        # Drena a queue independente do status dos bots — evita travar quando
        # os bots morrem com _half_mine_queue > 0.
        if self._half_mine_queue > 0:
            self._half_mine_timer -= dt
            if self._half_mine_timer <= 0.0:
                base_x = self.x + self.w / 2
                base_y = self.y + self.h / 2
                target_x = random.uniform(90, self._screen_w - 90)
                target_y = random.uniform(90, self._screen_h - 120)
                mine = GolemMine(base_x, base_y, target_x, target_y)
                self._half_phase_mines.append(mine)
                new_mines.append(mine)
                self._half_mine_queue -= 1
                self._half_mine_timer = 1.0

        if (
            not active_bots
            and not self._half_phase_mines
            and self._half_mine_queue == 0
        ):
            self._finish_half_phase()

    def _spawn_debris_cluster(
        self,
        count: int,
        player_x: float = 0.0,
        player_y: float = 0.0,
        spawn_from_bottom: bool = False,
        force: bool = False,
    ) -> None:
        """
        Cria detritos com trajetória parabólica a partir do TOPO do boss.
        ~40% dos fragmentos têm mira parcial no player; o restante é aleatório.
        force=True bypassa o cap — usado em bursts de impacto para garantir sincronização visual.
        """
        cx = self.x + self.w / 2
        # Entrada normal: topo (boss irrompendo de baixo para cima).
        # Submersão: base do boss, clampeada à borda visível para que detritos
        # não spawnem abaixo do threshold de morte do EmergeDebris (screen_h+100).
        if spawn_from_bottom:
            cy = min(self.y + self.h - self.SCALE * 2, self._screen_h + 50)
        else:
            cy = self.y + self.SCALE * 2

        # Gravidade reduzida para arco mais amplo
        gravity = getattr(Config, "GOLEM_DEBRIS_GRAVITY", 30) * 5.0

        if force:
            spawn_times = count
        else:
            # Enforce an active cap so on-screen debris matches config
            cap = (
                getattr(Config, "GOLEM_SUBMERGE_DEBRIS_COUNT", 8)
                if spawn_from_bottom
                else getattr(Config, "GOLEM_EMERGE_DEBRIS_COUNT", 8)
            )
            allowed = max(0, cap - len(self._emerge_debris))
            spawn_times = min(count, allowed)

        for _ in range(spawn_times):
            aimed = player_x != 0.0 and random.random() < 0.4

            if aimed:
                # Calcula ângulo base em direção ao player com spread de ±25°
                dx = player_x - cx
                dy = player_y - cy
                base_angle = math.degrees(
                    math.atan2(-dy, dx)
                )  # negativo pois y cresce p/ baixo
                # Garante que o fragmento sempre suba (ângulo entre 10° e 170°)
                base_angle = _clamp(base_angle, 10.0, 170.0)
                angle_deg = base_angle + random.uniform(-25, 25)
            else:
                # Dispersão aleatória — ampliada para cobrir mais área
                angle_deg = random.uniform(20, 160)

            angle_rad = math.radians(angle_deg)
            initial_velocity = random.uniform(500, 800)

            vx = initial_velocity * math.cos(angle_rad)
            vy = -initial_velocity * math.sin(angle_rad)  # negativo = sobe

            start_x = cx + random.uniform(-self.w / 4, self.w / 4)

            self._emerge_debris.append(
                EmergeDebris(
                    start_x,
                    cy,
                    vx,
                    vy,
                    None,
                    self.SCALE,
                    rock_size=random.randint(2, 5),
                    gravity=gravity,
                )
            )

    def _fsm_scan(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        if self._half_phase_pending:
            self._half_phase_pending = False
            self._start_half_phase()
            return

        if self._third_phase_pending:
            self._third_phase_pending = False
            self._start_third_phase()
            return

        self._move_vertical(dt)
        self.eye_growth = 0.0
        spd = self.difficulty_multiplier
        if self.fsm_ticks > (1.4 / (spd * self._rage_mult)):
            # Laser forçado se faz muito tempo que não dispara
            if self._cycles_since_fire >= 2:
                self._change_fsm("OPENING")
                return

            # Bag shuffle: garante que todos os ataques apareçam antes de repetir.
            if not self._attack_bag:
                pool = ["OPENING", "EARTH_SHAKE", "ORB_SPAWN", "SWEEP_CHARGE"]
                random.shuffle(pool)

                # Evitar repetição imediata na virada do bag
                last_map = {
                    "FIRE": "OPENING",
                    "EARTH_FIRE": "EARTH_SHAKE",
                    "ORB_FIRE": "ORB_SPAWN",
                    "SWEEP_FIRE": "SWEEP_CHARGE",
                }
                last_equiv = last_map.get(self._last_attack, "")

                # Se o primeiro do novo bag é igual ao último, ou se temos
                # dois ataques de partículas (OPENING e SWEEP_CHARGE) seguidos
                particle_attacks = {"OPENING", "SWEEP_CHARGE"}
                needs_swap = (pool[0] == last_equiv) or (
                    self._last_attack in ("FIRE", "SWEEP_FIRE")
                    and pool[0] in particle_attacks
                )

                if needs_swap and len(pool) > 1:
                    # Encontra o primeiro que não seja de partículas para quebrar o padrão
                    for i in range(1, len(pool)):
                        if pool[i] not in particle_attacks:
                            pool[0], pool[i] = pool[i], pool[0]
                            break
                self._attack_bag = pool

            chosen = self._attack_bag.pop(0)
            self._change_fsm(chosen)
            if chosen == "SWEEP_CHARGE":
                px, py = self._pupil_pos()
                self._sweep_locked_angle = math.atan2(player_y - py, player_x - px) % (
                    2 * math.pi
                )

    def _fsm_opening(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        spd = self._attack_spd
        # Abertura mais rápida: 1.5s -> 0.7s
        dur = 0.7 / spd
        self.eye_growth = _ease_out_cubic(_clamp(self.fsm_ticks / dur, 0, 1))
        if self.fsm_ticks > (dur + 0.15):
            self._change_fsm("CHARGE")

    def _fsm_charge(
        self,
        dt: float,
        _player_x: float,
        _player_y: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        px, py = self._pupil_pos()

        # Dispara UM ÚNICO CLUSTER no início em vez de stream contínuo
        # Isso evita a sensação de "partículas dobradas"
        if self.fsm_ticks < 0.05 and not self._charge_particles:
            for _ in range(self.MAX_CHARGE_PARTICLES):
                self._charge_particles.append(
                    _ChargeParticle(
                        px,
                        py,
                        random.choice([(255, 77, 77), (255, 153, 153)]),
                        radial_speed=160 + random.uniform(0, 120),  # Muito mais rápido
                    )
                )

        # Só avança para o disparo quando as partículas convergiram
        # Adicionada margem de segurança temporal
        if self.fsm_ticks >= 0.2 and not self._charge_particles:
            self._change_fsm("FIRE")

    def _fsm_fire(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        new_mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._fire_shot_timer -= dt
        spd = self._attack_spd
        if self._fire_shot_timer <= 0 and self._fire_shots_count < 3:
            px, py = self._pupil_pos()
            mine = GolemMine(
                px,
                py,
                player_x + random.uniform(-40, 40),
                player_y + random.uniform(-40, 40),
            )
            new_mines.append(mine)
            self._mines.append(mine)
            self._fire_shots_count += 1
            self._fire_shot_timer = 1.0 / spd
        if self._fire_shots_count >= 3 and self._fire_shot_timer <= -0.3:
            self._change_fsm("CLOSING")

    def _fsm_earth_shake(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        if self.fsm_ticks > (0.8 / self._attack_spd):
            self._change_fsm("EARTH_PULL")

    def _fsm_earth_pull(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        if self.fsm_ticks > (1.33 / self._attack_spd):
            self._change_fsm("EARTH_ORBIT")

    def _fsm_earth_orbit(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        if self.fsm_ticks > (1.5 / self._attack_spd):
            self._change_fsm("EARTH_FIRE")

    def _fsm_earth_fire(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        if (
            not self._orbital_debris
            or all(r.phase == "fired" and r.dead for r in self._orbital_debris)
            or self.fsm_ticks > (5.0 / self._attack_spd)
        ):
            self._cycles_since_fire += 1
            self._last_attack = "EARTH_FIRE"
            self._change_fsm("SCAN")

    def _fsm_orb_spawn(
        self,
        _dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        spd = self._attack_spd
        self.eye_growth = _ease_out_cubic(_clamp(self.fsm_ticks / (0.8 / spd), 0, 1))

        # Burst único de partículas roxas na abertura
        if self.fsm_ticks < 0.05 and not self._charge_particles:
            px, py = self._pupil_pos()
            for _ in range(self.MAX_CHARGE_PARTICLES):
                self._charge_particles.append(
                    _ChargeParticle(
                        px,
                        py,
                        _C["EYE_IRIS_ORB"],
                        radial_speed=160 + random.uniform(0, 120),
                    )
                )

        if self.fsm_ticks > (0.8 / spd):
            self._change_fsm("ORB_HOLD")

    def _fsm_orb_hold(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        new_shards: List[AttackDebris],
    ) -> None:
        px, py = self._pupil_pos()
        spd = self._attack_spd
        wave_interval = 0.22 / spd
        max_waves = 15

        # Rotaciona o padrão continuamente enquanto dispara
        # O spd aumenta a velocidade da rotação para dificultar em dificuldades altas
        self._orb_rotation += dt * 160 * spd

        if self._orb_shots_done < max_waves and self.fsm_ticks >= (
            self._orb_shots_done * wave_interval
        ):
            # Dispara 8 projéteis em leque rotativo (Estrela Espiral)
            for i in range(8):
                angle = (i * 45.0) + self._orb_rotation
                new_shards.append(
                    AttackDebris(
                        px,
                        py,
                        angle,
                        speed_mult=1.8,
                        color=_C["EYE_IRIS_ORB"],
                    )
                )
            self._orb_shots_done += 1
            from ..systems import hit_sounds as _hs

            _hs.GOLEM_ORB_PURPLE()

        if self._orb_shots_done >= max_waves and self.fsm_ticks > (
            max_waves * wave_interval + 0.4
        ):
            self._change_fsm("CLOSING")

    def _fsm_sweep_charge(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        spd = self._attack_spd
        track_duration = 1.2 / spd  # tempo rastreando o jogador
        freeze_duration = 1.0 / spd  # tempo parado antes de disparar
        total_duration = track_duration + freeze_duration
        self.eye_growth = _ease_out_cubic(_clamp(self.fsm_ticks / track_duration, 0, 1))
        if self.fsm_ticks < track_duration:
            # Fase de rastreamento: cone segue o jogador
            px, py = self._pupil_pos()
            self._sweep_locked_angle = math.atan2(player_y - py, player_x - px) % (
                2 * math.pi
            )
            self._sweep_lock_done = False
        elif not self._sweep_lock_done:
            # Travou — congela o ângulo
            self._sweep_lock_done = True
        # Partículas de carregamento azuis (Burst Único)
        if self.fsm_ticks < 0.05 and not self._charge_particles:
            px, py = self._pupil_pos()
            for _ in range(self.MAX_CHARGE_PARTICLES):
                self._charge_particles.append(
                    _ChargeParticle(
                        px,
                        py,
                        random.choice([_C["EYE_IRIS_SWEEP"], _C["SWEEP_BEAM"]]),
                        radial_speed=160 + random.uniform(0, 120),
                    )
                )
        if self.fsm_ticks > total_duration:
            self._change_fsm("SWEEP_FIRE")

    def _fsm_sweep_fire(
        self,
        _dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        new_shards: List[AttackDebris],
    ) -> None:
        px, py = self._pupil_pos()
        fire_duration = 0.9 / self._attack_spd
        sweep_progress = _clamp(self.fsm_ticks / fire_duration, 0, 1)
        self._sweep_angle = (
            self._sweep_locked_angle
            - self._sweep_total / 2
            + sweep_progress * self._sweep_total
        )
        bucket = int(math.degrees(self._sweep_angle) / 4)
        if bucket not in self._shards_fired_at:
            self._shards_fired_at.add(bucket)
            new_shards.append(
                AttackDebris(
                    px,
                    py,
                    math.degrees(self._sweep_angle),
                    speed_mult=1.3,
                    color=_C["SWEEP_BEAM"],
                )
            )
        if self.fsm_ticks > fire_duration + 0.3:
            # Burst de partículas de morte do laser ao longo da linha do laser
            px, py = self._pupil_pos()
            burst_col = _C["SWEEP_BEAM"]

            # Calculamos a linha final do laser (similar ao boss_laser.py)
            bl = max(self._screen_w, self._screen_h) * 1.2
            dx, dy = math.cos(self._sweep_angle), math.sin(self._sweep_angle)

            # Spawna partículas ao longo da linha
            step = 30
            num_steps = int(bl / step)
            for i in range(num_steps):
                dist_on_line = i * step + random.uniform(0, step)
                pos_x = px + dx * dist_on_line
                pos_y = py + dy * dist_on_line

                # Para cada ponto na linha, spawna algumas partículas
                for _ in range(2):
                    p = _ChargeParticle(
                        pos_x,
                        pos_y,
                        burst_col,
                        size=random.randint(2, 5),
                        radial_speed=-(140 + random.uniform(0, 120)),
                        orbit_speed=random.uniform(-0.1, 0.1),
                        dist=random.uniform(1, 6),
                        follow_pupil=False,
                        max_burst_dist=120.0,
                    )
                    self._charge_particles.append(p)

            self._change_fsm("CLOSING")

    def _fsm_closing(
        self,
        dt: float,
        _px: float,
        _py: float,
        _mines: List["GolemMine"],
        _shards: List[AttackDebris],
    ) -> None:
        self._move_vertical(dt)
        spd = self._attack_spd
        self.eye_growth = 1.0 - _ease_out_cubic(
            _clamp(self.fsm_ticks / (0.6 / spd), 0, 1)
        )
        if self.eye_growth <= 0.01:
            self.eye_growth = 0.0
            self._cycles_since_fire = (
                0 if self._prev_fsm_state == "FIRE" else self._cycles_since_fire + 1
            )
            self._last_attack = self._prev_fsm_state
            self._change_fsm("SCAN")

    def _move_vertical(self, dt: float) -> None:
        speed = getattr(Config, "GOLEM_SPEED", 75) * self._rage_mult
        self.y += self.direction * speed * dt
        lower = int(self._screen_h * (0.65 if self._rage_mult > 1.0 else 0.5))
        if self.y <= 40 or self.y >= lower:
            self.direction *= -1

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return

        half_health = self.max_health * self.HALF_PHASE_HP_FRACTION
        third_health = self.max_health * self.THIRD_PHASE_HP_FRACTION
        prev_health = self.health
        self.health -= amount
        if self.health <= 0:
            self.health, self.dead = 0, True
            return

        if (
            not self._half_phase_triggered
            and prev_health > half_health
            and self.health <= half_health
        ):
            self._half_phase_pending = True
        elif (
            self._half_phase_triggered
            and not self._third_phase_triggered
            and prev_health > third_health
            and self.health <= third_health
        ):
            self._third_phase_pending = True

    @classmethod
    def _build_collision_mask(cls) -> pygame.mask.Mask:
        """
        Constrói máscara pixel-perfeita a partir do PIXEL_MAP.
        Cada pixel do mapa que não é None resulta em um pixel sólido na máscara.
        A máscara é escalada e cacheada para reutilização.
        """
        if cls._collision_mask is not None:
            return cls._collision_mask

        S = cls.SCALE
        mask_w = _PIXEL_COLS * S
        mask_h = _PIXEL_ROWS * S

        # Cria máscara vazia (todos os pixels transparentes por padrão)
        mask = pygame.mask.Mask((mask_w, mask_h), fill=False)

        # Para cada célula do pixel map com valor (não None),
        # marca toda a área escalada como sólida
        for row_idx, row in enumerate(_PIXEL_MAP):
            for col_idx, cell in enumerate(row):
                if cell is not None:  # Célula com cor (sólida)
                    x = col_idx * S
                    y = row_idx * S
                    for px in range(S):
                        for py in range(S):
                            if x + px < mask_w and y + py < mask_h:
                                mask.set_at((x + px, y + py), True)

        cls._collision_mask = mask
        return mask

    def get_collision_mask_data(
        self,
    ) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        """
        Retorna dados para colisão pixel-perfeita.

        Usado pelo sistema de colisão: primeiro tenta máscara (pixel-perfect),
        depois fallback para collision_circle().

        Posição base do boss (x, y), mas com ajuste do float vertical.
        """
        mask = self._build_collision_mask()
        # Usa self.rect como fonte única de verdade: já inclui float vertical
        # e jitter, garantindo alinhamento perfeito com o AABB pré-filtro do
        # sistema de colisão e com a posição visual desenhada.
        return mask, (self.rect.x, self.rect.y)

    def can_take_damage(self) -> bool:
        """O boss não recebe dano durante a introdução ou se estiver morto."""
        return self.fsm_state != "ENTERING" and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        # Centro acompanha o float vertical do boss (mesmo offset usado pelo
        # draw). Raio usa min(w, h)/2 — círculo inscrito no bounding box, mais
        # próximo da silhueta em diamante do golem. max(w,h)/2 inflava os
        # cantos da rect que ficam transparentes no sprite.
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2 + self._current_float_y
        return cx, cy, min(self.w, self.h) / 2

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        S, ox, oy = (
            self.SCALE,
            int(self.x + self._jitter_x),
            int(self.y + self._current_float_y + self._jitter_y),
        )
        for r in self._orbital_debris:
            if r.behind_boss:
                r.draw(surface)
        if self._body_surf_top:
            surface.blit(self._body_surf_top, (ox, oy))
        if self._body_surf_bottom:
            surface.blit(self._body_surf_bottom, (ox, oy + (_EYE_ROW_BELOW + 1) * S))
        eye_off = int(self.eye_growth * S)
        for r_idx in (_EYE_ROW_ABOVE, _EYE_ROW, _EYE_ROW_BELOW):
            for c_idx, k in enumerate(_PIXEL_MAP[r_idx]):
                if k is None or (
                    r_idx == _EYE_ROW and _EYE_COL_START <= c_idx <= _EYE_COL_END
                ):
                    continue
                px_d, py_d = ox + c_idx * S, oy + r_idx * S
                if _EYE_COL_START <= c_idx <= _EYE_COL_END:
                    if r_idx == _EYE_ROW_ABOVE:
                        py_d -= eye_off
                    elif r_idx == _EYE_ROW_BELOW:
                        py_d += eye_off
                pygame.draw.rect(surface, _C[k], (px_d, py_d, S, S))
        self._draw_eye(surface, ox, oy, S, eye_off)
        self._draw_thruster(surface, ox, oy, S)

        # 1. Desenhar rastros de poeira PRIMEIRO (atrás de tudo)
        for p in self._charge_particles:
            p.draw(surface)
        for d in self._emerge_debris:
            d.draw_trail(surface)

        # 2. Desenhar corpos sólidos por CIMA da poeira
        for d in self._emerge_debris:
            d.draw(surface)

        if self.fsm_state in ("SWEEP_CHARGE", "SWEEP_FIRE"):
            self._draw_sweep_cone(surface)
        if self.fsm_state == "SWEEP_FIRE":
            self._draw_sweep_beam(surface)
        if self.fsm_state in ("SWEEP_CHARGE", "SWEEP_FIRE"):
            self._draw_sweep_orb(surface)
        if self.fsm_state in ("CHARGE", "FIRE"):
            self._draw_red_orb(surface)
        if self.fsm_state in ("ORB_SPAWN", "ORB_HOLD"):
            self._draw_purple_orb(surface)
        for r in self._orbital_debris:
            if not r.behind_boss:
                r.draw(surface)
        self._draw_health_bar(surface, ox, oy)

    def _draw_eye(
        self, surface: pygame.Surface, ox: int, oy: int, S: int, eye_offset: int
    ) -> None:
        state = self.fsm_state
        if state in {"OPENING", "CHARGE", "FIRE"}:
            bg, iris = _C["EYE_BG_LASER"], _C["EYE_IRIS_LASER"]
        elif state in {"EARTH_SHAKE", "EARTH_PULL", "EARTH_ORBIT", "EARTH_FIRE"}:
            bg, iris = _C["EYE_BG_EARTH"], _C["EYE_IRIS_EARTH"]
        elif state in {"ORB_SPAWN", "ORB_HOLD", "ORB_FIRE"}:
            bg, iris = _C["EYE_BG_ORB"], _C["EYE_IRIS_ORB"]
        elif state in {"SWEEP_CHARGE", "SWEEP_FIRE"}:
            bg, iris = _C["EYE_BG_SWEEP"], _C["EYE_IRIS_SWEEP"]
        else:
            bg, iris = _C["EYE_BG_DEFAULT"], _C["EYE_IRIS_DEFAULT"]
        vx, ey, vh = ox + _EYE_COL_START * S, oy + _EYE_ROW * S, S + eye_offset * 2
        vy = ey - eye_offset
        pygame.draw.rect(surface, bg, (vx, vy, S * 5, vh))
        pygame.draw.rect(surface, iris, (vx + S + self._scan_step * S, vy, S * 3, vh))
        pygame.draw.rect(
            surface, _C["PUPIL"], (vx + S * 2 + self._scan_step * S, vy + 1, S, S)
        )

    def _draw_thruster(self, surface: pygame.Surface, ox: int, oy: int, S: int) -> None:
        cx, sy, t = ox + self.w // 2, oy + self.h, self._time
        pygame.draw.rect(surface, (255, 255, 255), (cx - S, sy, S * 2, S))
        for i in range(5):
            ph = ((t * 2.0) + (i / 5)) % 1.0
            w, h = int(S * 10 * (1 - ph)), max(S, int(S * 4 * (1 - ph)))
            y, al = sy + int(ph * S * 14) + S, max(0, int(255 * (1 - ph**2)))
            if w < S:
                continue
            col = (
                (255, 255, 255)
                if ph < 0.15
                else ((157, 212, 240) if ph < 0.5 else (91, 159, 200))
            )
            self._thruster_surfs[i].fill((0, 0, 0, 0))
            pygame.draw.rect(self._thruster_surfs[i], (*col, al), (0, 0, w, h), S)
            surface.blit(self._thruster_surfs[i], (cx - w // 2, y - h // 2))

    def _draw_sweep_cone(self, surface: pygame.Surface) -> None:
        px, py = self._pupil_pos()
        cone_len, half = (
            max(self._screen_w, self._screen_h) * 2.5,
            self._sweep_total / 2,
        )
        al = (
            int(38 + math.sin(self._time * 20) * 12)
            if self.fsm_state == "SWEEP_CHARGE"
            else 40
        )
        ang = self._sweep_locked_angle
        self._cone_surf.fill((0, 0, 0, 0))
        pts = [
            (int(px), int(py)),
            (
                int(px + math.cos(ang - half) * cone_len),
                int(py + math.sin(ang - half) * cone_len),
            ),
            (
                int(px + math.cos(ang + half) * cone_len),
                int(py + math.sin(ang + half) * cone_len),
            ),
        ]
        pygame.draw.polygon(self._cone_surf, (*_C["SWEEP_BEAM"], al), pts)
        surface.blit(self._cone_surf, (0, 0))

    def get_sweep_beam(self) -> Optional[Tuple[float, float, float, float]]:
        if self.fsm_state != "SWEEP_FIRE":
            return None
        px, py = self._pupil_pos()
        bl = max(self._screen_w, self._screen_h) * 2.5
        return (
            px,
            py,
            px + math.cos(self._sweep_angle) * bl,
            py + math.sin(self._sweep_angle) * bl,
        )

    def _draw_sweep_beam(self, surface: pygame.Surface) -> None:
        beam = self.get_sweep_beam()
        if beam is None:
            return
        px, py, ex, ey = beam
        self._halo_surf.fill((0, 0, 0, 0))
        pygame.draw.line(
            self._halo_surf,
            (*_C["SWEEP_BEAM"], 77),
            (int(px), int(py)),
            (int(ex), int(ey)),
            self.SCALE * 3,
        )
        surface.blit(self._halo_surf, (0, 0))
        pygame.draw.line(
            surface,
            (255, 255, 255),
            (int(px), int(py)),
            (int(ex), int(ey)),
            max(1, self.SCALE),
        )

    def _draw_red_orb(self, surface: pygame.Surface) -> None:
        """Esfera vermelha: cresce no CHARGE, encolhe a cada disparo no FIRE."""
        px, py = self._pupil_pos()
        S = self.SCALE
        col_inner = _C["EYE_IRIS_LASER"]
        col_outer = (255, 77, 77)

        if self.fsm_state == "CHARGE":
            spd = self.difficulty_multiplier
            charge_duration = 1.5 / spd
            t = _clamp(self.fsm_ticks / charge_duration, 0, 1)
            # Pulsa levemente quando cheio
            if t >= 1.0:
                pulse = math.sin(self._time * math.pi * 8) * 0.1
                radius = int(S * 4 * (1.0 + pulse))
            else:
                radius = int(S * 0.5 + _ease_out_cubic(t) * S * 3.5)
            alpha = 220

        else:  # FIRE — encolhe a cada disparo
            shots_done = self._fire_shots_count
            total_shots = 3
            shrink = _clamp(shots_done / total_shots, 0, 1)
            # Também aplica progresso dentro do intervalo entre disparos
            pulse = math.sin(self._time * math.pi * 6) * 0.08
            radius = int(S * 4 * (1.0 - shrink * 0.85) * (1.0 + pulse))
            alpha = int(220 * (1.0 - shrink * 0.7))

        if radius < 2:
            return

        # Glow externo
        glow_r = int(radius * 1.5)
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            glow_surf,
            (*col_outer, int(alpha * 0.25)),
            (0, 0, glow_r * 2, glow_r * 2),
        )
        surface.blit(glow_surf, (int(px) - glow_r, int(py) - glow_r))

        # Núcleo em camadas de quadrados rotacionados
        rot = self._time * 25
        for layer, (size_mult, col, alpha_mult) in enumerate(
            [
                (1.0, col_outer, 0.5),
                (0.7, col_inner, 0.8),
                (0.4, (255, 255, 255), 1.0),
            ]
        ):
            r = max(1, int(radius * size_mult))
            a = math.radians(rot + layer * 15)
            cx = int(px - r * math.cos(a) * 0.1)
            cy = int(py - r * math.sin(a) * 0.1)
            sq_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.rect(
                sq_surf,
                (*col, int(alpha * alpha_mult)),
                (0, 0, r * 2, r * 2),
            )
            rotated = pygame.transform.rotate(sq_surf, rot + layer * 45)
            rw, rh = rotated.get_size()
            surface.blit(rotated, (cx - rw // 2, cy - rh // 2))

    def _draw_sweep_orb(self, surface: pygame.Surface) -> None:
        """Esfera de energia do laser: cresce no charge, encolhe no fire."""
        px, py = self._pupil_pos()
        S = self.SCALE
        col_inner = _C["EYE_IRIS_SWEEP"]
        col_outer = _C["SWEEP_BEAM"]

        if self.fsm_state == "SWEEP_CHARGE":
            spd = self.difficulty_multiplier
            track_duration = 1.2 / spd
            freeze_duration = 1.0 / spd
            # Cresce durante o tracking, pulsa levemente durante o freeze
            if self.fsm_ticks < track_duration:
                t = self.fsm_ticks / track_duration
                radius = int(S * 0.5 + _ease_out_cubic(t) * S * 3.5)
            else:
                freeze_t = (self.fsm_ticks - track_duration) / freeze_duration
                pulse = math.sin(freeze_t * math.pi * 6) * 0.12
                radius = int(S * 4 + pulse * S * 4)
            alpha = 220

        else:  # SWEEP_FIRE
            fire_duration = 0.9 / self._attack_spd
            progress = _clamp(self.fsm_ticks / fire_duration, 0, 1)
            radius = int(S * 4 * (1.0 - progress))
            alpha = int(220 * (1.0 - progress))

        if radius < 2:
            return

        # Glow externo
        glow_r = int(radius * 1.5)
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            glow_surf,
            (*col_outer, int(alpha * 0.25)),
            (0, 0, glow_r * 2, glow_r * 2),
        )
        surface.blit(glow_surf, (int(px) - glow_r, int(py) - glow_r))

        # Núcleo em camadas de quadrados rotacionados
        rot = self._time * 30
        for layer, (size_mult, col, alpha_mult) in enumerate(
            [
                (1.0, col_outer, 0.5),
                (0.7, col_inner, 0.8),
                (0.4, (255, 255, 255), 1.0),
            ]
        ):
            r = max(1, int(radius * size_mult))
            a = math.radians(rot + layer * 15)
            cx = int(px - r * math.cos(a) * 0.1)
            cy = int(py - r * math.sin(a) * 0.1)
            sq_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.rect(
                sq_surf,
                (*col, int(alpha * alpha_mult)),
                (0, 0, r * 2, r * 2),
            )
            rotated = pygame.transform.rotate(sq_surf, rot + layer * 45)
            rw, rh = rotated.get_size()
            surface.blit(rotated, (cx - rw // 2, cy - rh // 2))

    def _draw_purple_orb(self, surface: pygame.Surface) -> None:
        """Esfera roxa: cresce no SPAWN, encolhe durante os disparos no HOLD."""
        px, py = self._pupil_pos()
        S = self.SCALE
        col_inner = _C["EYE_IRIS_ORB"]
        col_outer = (217, 66, 255)  # Roxo vibrante

        if self.fsm_state == "ORB_SPAWN":
            spd = self.difficulty_multiplier
            dur = 0.8 / spd
            t = _clamp(self.fsm_ticks / dur, 0, 1)
            radius = int(S * 0.5 + _ease_out_cubic(t) * S * 3.5)
            alpha = 220
        else:  # ORB_HOLD
            shots_done = self._orb_shots_done
            max_waves = 15
            progress = _clamp(shots_done / max_waves, 0, 1)
            pulse = math.sin(self._time * math.pi * 10) * 0.1
            radius = int(S * 4 * (1.0 - progress * 0.8) * (1.0 + pulse))
            alpha = int(220 * (1.0 - progress * 0.6))

        if radius < 2:
            return

        # Glow externo
        glow_r = int(radius * 1.6)
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            glow_surf,
            (*col_outer, int(alpha * 0.25)),
            (0, 0, glow_r * 2, glow_r * 2),
        )
        surface.blit(glow_surf, (int(px) - glow_r, int(py) - glow_r))

        # Núcleo em camadas de quadrados rotacionados (estilo glitch/magia)
        rot = self._time * 40
        for layer, (size_mult, col, alpha_mult) in enumerate(
            [
                (1.0, col_outer, 0.5),
                (0.7, col_inner, 0.8),
                (0.4, (255, 255, 255), 1.0),
            ]
        ):
            r = max(1, int(radius * size_mult))
            sq_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.rect(
                sq_surf,
                (*col, int(alpha * alpha_mult)),
                (0, 0, r * 2, r * 2),
            )
            # Rotação alternada por camada
            layer_rot = rot * (1.0 if layer % 2 == 0 else -1.2)
            rotated = pygame.transform.rotate(sq_surf, layer_rot + layer * 30)
            rw, rh = rotated.get_size()
            surface.blit(rotated, (int(px) - rw // 2, int(py) - rh // 2))

    def _draw_health_bar(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        bw, bx, by, bh = self.w + 16, ox - 8, oy - 14, 7
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, bh), border_radius=3)
        hp = max(0.0, self.health / self.max_health)
        pygame.draw.rect(
            surface,
            (int(220 * (1 - hp) + 60 * hp), int(200 * hp), 40),
            (bx, by, int(bw * hp), bh),
            border_radius=3,
        )
        pygame.draw.rect(surface, (180, 180, 180), (bx, by, bw, bh), 1, border_radius=3)
