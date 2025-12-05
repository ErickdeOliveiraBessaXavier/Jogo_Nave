import random
import math
import pygame
from typing import List, Tuple
from ..core.config import config as Config
from ..core import colors


# Cache global de shapes para reutilização (evita recalcular pontos irregulares)
_SHAPE_CACHE: dict[int, List[Tuple[float, float]]] = {}


def _get_or_create_shape(size: int) -> List[Tuple[float, float]]:
    """Retorna shape cacheado ou cria novo."""
    if size not in _SHAPE_CACHE:
        pts: List[Tuple[float, float]] = []
        num = 6
        for i in range(num):
            ang = (2 * math.pi * i) / num
            rv = random.uniform(0.6, 1.4)
            r = size * rv
            pts.append((r * math.cos(ang), r * math.sin(ang)))
        _SHAPE_CACHE[size] = pts
    return _SHAPE_CACHE[size]


class Meteor:
    def __init__(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        # tamanho base
        self.size: int
        self.w: int
        self.h: int

        # posição
        self.x: float
        self.y: float

        # velocidade
        self.vx: float
        self.vy: float

        # rotação (maiores rodam mais devagar)
        self.rotation: float
        self.rotation_speed: float

        # forma irregular + cor
        self._base_points: List[Tuple[float, float]]
        self.color_intensity: float
        self.dead: bool
        self.active: bool  # Para o Pool Pattern

        # tamanho base
        self.size = (
            size
            if size is not None
            else random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
        )
        self.w = self.h = self.size * 2

        # posição
        if x is None:
            self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        else:
            self.x = x
        self.y = -self.h if y is None else y

        # velocidade vertical baseada no tamanho (pequenos mais rápidos)
        ratio = (self.size - Config.MIN_METEOR_SIZE) / (
            Config.MAX_METEOR_SIZE - Config.MIN_METEOR_SIZE + 1e-6
        )
        base_vy = (
            Config.FAST_METEOR_SPEED
            - (Config.FAST_METEOR_SPEED - Config.SLOW_METEOR_SPEED) * ratio
        )

        # velocidade
        if vy is None:
            self.vy = base_vy
        else:
            self.vy = vy

        if vx is None:
            if random.random() < Config.DIAGONAL_CHANCE:
                self.vx = random.uniform(-120.0, 120.0) * (
                    self.vy / max(Config.FAST_METEOR_SPEED, 1e-6)
                )
            else:
                self.vx = 0.0
        else:
            self.vx = vx

        # rotação (maiores rodam mais devagar)
        self.rotation = 0.0
        self.rotation_speed = random.uniform(-3, 3) * (1.0 - ratio * 0.5)

        # forma irregular + cor
        self._base_points: List[Tuple[float, float]] = _get_or_create_shape(self.size)
        self.color_intensity = 1.0 - ratio * 0.3
        self.dead = False
        self.active = True  # Para o Pool Pattern

        # Vida baseada no tamanho (meteoros maiores = mais vida)
        self.health: int = int(10 + (self.size / Config.MAX_METEOR_SIZE) * 40)

    def _generate_irregular_shape(self) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        num = 6  # Reduzido de variável para 6 pontos fixos para otimização
        for i in range(num):
            ang = (2 * math.pi * i) / num
            rv = random.uniform(0.6, 1.4)
            r = self.size * rv
            pts.append((r * math.cos(ang), r * math.sin(ang)))
        return pts

    def reset(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        """Reconfigura o meteoro para reutilização no pool."""
        # tamanho base
        self.size = (
            size
            if size is not None
            else random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
        )
        self.w = self.h = self.size * 2

        # posição
        if x is None:
            self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        else:
            self.x = x
        self.y = -self.h if y is None else y

        # velocidade vertical baseada no tamanho
        ratio = (self.size - Config.MIN_METEOR_SIZE) / (
            Config.MAX_METEOR_SIZE - Config.MIN_METEOR_SIZE + 1e-6
        )
        base_vy = (
            Config.FAST_METEOR_SPEED
            - (Config.FAST_METEOR_SPEED - Config.SLOW_METEOR_SPEED) * ratio
        )

        # velocidade
        if vy is None:
            self.vy = base_vy
        else:
            self.vy = vy

        if vx is None:
            if random.random() < Config.DIAGONAL_CHANCE:
                self.vx = random.uniform(-120.0, 120.0) * (
                    self.vy / max(Config.FAST_METEOR_SPEED, 1e-6)
                )
            else:
                self.vx = 0.0
        else:
            self.vx = vx

        # rotação
        self.rotation = 0.0
        self.rotation_speed = random.uniform(-3, 3) * (1.0 - ratio * 0.5)

        # forma irregular + cor
        self._base_points = _get_or_create_shape(self.size)
        self.color_intensity = 1.0 - ratio * 0.3
        self.dead = False
        self.active = True

        # Vida baseada no tamanho
        self.health = int(10 + (self.size / Config.MAX_METEOR_SIZE) * 40)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rotation += self.rotation_speed
        if (
            (self.y > Config.SCREEN_HEIGHT)
            or (self.x < -self.w)
            or (self.x > Config.SCREEN_WIDTH)
        ):
            self.dead = True

    def _rotated_points(self) -> List[Tuple[int, int]]:
        cr = math.cos(math.radians(self.rotation))
        sr = math.sin(math.radians(self.rotation))
        cx = self.x + self.w // 2
        cy = self.y + self.h // 2
        out: List[Tuple[int, int]] = []
        for px, py in self._base_points:
            rx = px * cr - py * sr
            ry = px * sr + py * cr
            out.append((int(cx + rx), int(cy + ry)))
        return out

    def draw(self, screen: pygame.Surface):
        points = self._rotated_points()
        if self.size <= Config.MIN_METEOR_SIZE + 8:
            body_color = (
                int(255 * self.color_intensity),
                int(200 * self.color_intensity),
                int(100 * self.color_intensity),
            )
            border_color = colors.YELLOW
            core_color = colors.LIGHT_ORANGE
        else:
            body_color = (
                int(200 * self.color_intensity),
                int(100 * self.color_intensity),
                int(50 * self.color_intensity),
            )
            border_color = colors.RED
            core_color = colors.DARK_RED
        pygame.draw.polygon(screen, body_color, points)
        pygame.draw.polygon(screen, border_color, points, 2)
        center = (int(self.x + self.w // 2), int(self.y + self.h // 2))
        pygame.draw.circle(screen, core_color, center, max(2, self.size // 4))

    def get_points_value(self) -> int:
        # Calcula quão pequeno o meteoro é em relação ao máximo
        size_factor = Config.MAX_METEOR_SIZE - self.size
        size_bonus = int(size_factor * Config.SIZE_BONUS_MULTIPLIER)
        return Config.BASE_POINTS + size_bonus

    # ── NOVO: regras de fragmentação ─────────────────────────────────────────
    def can_split(self) -> bool:
        return self.size >= Config.FRAGMENT_SPLIT_THRESHOLD

    def spawn_fragments(self) -> List["Meteor"]:
        if not self.can_split():
            return []
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        count = random.randint(*Config.FRAGMENT_COUNT_RANGE)
        target_size = max(Config.MIN_METEOR_SIZE, int(self.size * 0.55))
        frags: List[Meteor] = []

        # Pré-calcular valores constantes para todos os fragmentos
        base_angle_rad = math.radians(random.uniform(0, 360))
        half_spread_rad = math.radians(Config.FRAGMENT_SPREAD / 2)
        speed_boost = self.vy * Config.FRAGMENT_SPEED_BOOST
        vy_base = self.vy * 0.2
        size_offset_x = self.size * 0.5
        size_offset_y = self.size * 0.3

        for _ in range(count):
            # variação de tamanho (±20%)
            s = max(Config.MIN_METEOR_SIZE, int(target_size * random.uniform(0.8, 1.2)))

            # ângulo relativo (apenas 1 random.uniform por fragmento)
            angle_offset = random.uniform(-half_spread_rad, half_spread_rad)
            ang = base_angle_rad + angle_offset

            # Calcular cos/sin uma única vez
            cos_ang = math.cos(ang)
            sin_ang = math.sin(ang)

            # velocidade
            speed = speed_boost * random.uniform(0.9, 1.25)
            vx = cos_ang * speed
            vy = abs(sin_ang * speed) + vy_base

            # posição (reutilizar cos_ang, sin_ang)
            fx = cx + cos_ang * size_offset_x - s
            fy = cy + sin_ang * size_offset_y - s

            frags.append(Meteor(size=s, x=fx, y=fy, vx=vx, vy=vy))
        return frags
