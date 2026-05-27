import random
from typing import TYPE_CHECKING, Dict, Tuple, Optional

import pygame

from ..core.config import config as Config
from .enemy_hit_mixin import EnemyHitMixin
from .satellite_pixel_map import PIXEL_MAP, PIXEL_COLS, PIXEL_ROWS, C

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult

# Cache estático de superfícies para evitar redesenhar o pixel map todo frame
_SATELLITE_SURFACE_CACHE: Dict[int, pygame.Surface] = {}


def _get_satellite_surface(scale: int) -> pygame.Surface:
    if scale in _SATELLITE_SURFACE_CACHE:
        return _SATELLITE_SURFACE_CACHE[scale]

    w = PIXEL_COLS * scale
    h = PIXEL_ROWS * scale
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, cell in enumerate(row):
            if cell is None:
                continue
            color = C[cell]
            pygame.draw.rect(surf, color, (col_i * scale, row_i * scale, scale, scale))

    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass

    _SATELLITE_SURFACE_CACHE[scale] = surf
    return surf


class Satellite(EnemyHitMixin):
    """
    Satélite — Inimigo custom para a fase da atmosfera.
    Usa renderização via pixel-map.
    """

    SCALE = 4
    POINTS = 300
    HEALTH = 5

    def __init__(self, inverted_vertical: bool = False):
        self.scale = self.SCALE
        self.w = PIXEL_COLS * self.scale
        self.h = PIXEL_ROWS * self.scale

        self.inverted_vertical = inverted_vertical

        # Posição inicial
        # Margem para não nascer colado na borda
        margin = 10
        self.x = float(random.randint(margin, Config.SCREEN_WIDTH - self.w - margin))

        if inverted_vertical:
            # Entering: vem de baixo para cima
            self.y = float(Config.SCREEN_HEIGHT + self.h)
            self.speed_y = -random.uniform(120, 180)
        else:
            # Exiting: vem de cima para baixo
            self.y = -float(self.h)
            self.speed_y = random.uniform(120, 180)

        # Trajetória diagonal mais pronunciada
        # Move-se sempre em direção ao centro da tela inicialmente
        if self.x < Config.SCREEN_WIDTH / 2:
            self.speed_x = random.uniform(80, 140)
        else:
            self.speed_x = -random.uniform(80, 140)

        self.dead = False
        self.health = self.HEALTH

        # Timer para o piscar da luz vermelha (pixel 'G' no mapa)
        self.blink_timer = 0.0
        self.blink_state = True

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        # ctx.sdt é o delta time do jogo com fator de velocidade/slowdown
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Bounce nas bordas horizontais
        if self.x <= 0:
            self.x = 0
            self.speed_x *= -1
        elif self.x + self.w >= Config.SCREEN_WIDTH:
            self.x = float(Config.SCREEN_WIDTH - self.w)
            self.speed_x *= -1

        # Lógica do piscar (luz indicadora)
        self.blink_timer += dt
        if self.blink_timer >= 0.4:
            self.blink_timer = 0
            self.blink_state = not self.blink_state

        # Remoção se sair completamente da tela
        if self.inverted_vertical:
            if self.y < -self.h * 2:
                self.dead = True
        else:
            if self.y > Config.SCREEN_HEIGHT + self.h * 2:
                self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        base_surf = _get_satellite_surface(self.scale)
        surface.blit(base_surf, (int(self.x), int(self.y)))

        # Efeito de brilho na luz vermelha (pixel 'G' está em row 8, cols 11-12 no novo mapa)
        if self.blink_state:
            # Cores do brilho
            glow_color = (255, 180, 180)  # Vermelho claro
            # Posição relativa ao self.x, self.y
            gx = int(self.x) + 11 * self.scale
            gy = int(self.y) + 8 * self.scale
            # Desenha um pequeno retângulo de brilho
            pygame.draw.rect(
                surface, glow_color, (gx, gy, 2 * self.scale, 1 * self.scale)
            )

    def should_remove(self) -> bool:
        return self.dead

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)
