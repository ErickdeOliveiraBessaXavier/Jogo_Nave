import pygame
import random
from ..core.config import Config
from typing import Tuple, TypedDict, Union


class ParticleDict(TypedDict):
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    size: float
    color: Tuple[int, int, int]


class Ship:
    PIXEL_ART_SPRITE = [
        "   W   ",
        "  WWW  ",
        "  WGW  ",
        " WWGWW ",
        "WWWRWWW",
        "  RRR  ",
    ]
    COLOR_MAP: dict[str, Union[Tuple[int, int, int], Tuple[int, int, int, int]]] = {
        "W": (255, 255, 255),  # White
        "G": (150, 150, 150),  # Gray
        "R": (255, 0, 0),  # Red (thruster)
        " ": (0, 0, 0, 0),  # Transparent
    }
    PIXEL_SIZE = 5  # Size of each pixel in the sprite

    def __init__(self, x: float, y: float):
        self.w = len(self.PIXEL_ART_SPRITE[0]) * self.PIXEL_SIZE
        self.h = len(self.PIXEL_ART_SPRITE) * self.PIXEL_SIZE
        self.x = x
        self.y = y
        self.speed = 250
        self.invuln = 0  # ms
        self.lives = Config.INITIAL_LIVES
        self.visible = True
        self.move_vec = pygame.math.Vector2(0, 0)

        # Power-ups
        self.double_shot_timer: float = 0.0
        self.speed_boost_timer: float = 0.0
        self.piercing_shot_timer: float = 0.0
        self.mini_ships_timer: float = 0.0
        self.is_entering = False
        self.entry_particles: list[ParticleDict] = []
        self.thruster_particles: list[ParticleDict] = []

    @property
    def attack_speed_multiplier(self) -> float:
        """Retorna o multiplicador de velocidade de ataque baseado nos power-ups ativos."""
        if self.speed_boost_timer > 0.0:
            return Config.SPEED_ATTACK_MULTIPLIER  # Usar configuração personalizada
        if self.piercing_shot_timer > 0.0:
            return Config.PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER
        return 1.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        if self.invuln > 0:
            self.invuln = max(0, self.invuln - dt * 1000)

        self.double_shot_timer = max(0.0, self.double_shot_timer - dt)
        self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)
        self.piercing_shot_timer = max(0.0, self.piercing_shot_timer - dt)
        self.mini_ships_timer = max(0.0, self.mini_ships_timer - dt)

        # Atualizar partículas de entrada
        if self.is_entering:
            # Gerar novas partículas
            for _ in range(3):  # Gerar 3 novas partículas por frame
                particle = ParticleDict(
                    x=self.x + self.w / 2,
                    y=self.y,
                    vx=random.uniform(-80, 80),
                    vy=random.uniform(80, 80),  # Mover para baixo
                    lifetime=random.uniform(0.2, 0.6),
                    size=random.uniform(1, 3),
                    color=(255, random.randint(100, 220), 0),  # Cor de fogo
                )
                self.entry_particles.append(particle)

        # Atualizar e remover partículas antigas de entrada
        for particle in self.entry_particles[:]:
            particle["lifetime"] -= dt
            if particle["lifetime"] <= 0:
                self.entry_particles.remove(particle)
            else:
                particle["x"] += particle["vx"] * dt
                particle["y"] += particle["vy"] * dt

        # Gerar novas partículas de thruster
        for _ in range(2):  # Gerar 2 novas partículas por frame
            particle = ParticleDict(
                x=self.x + self.w / 2 + random.uniform(-5, 5),
                y=self.y + self.h,
                vx=random.uniform(-10, 10),
                vy=random.uniform(100, 200),  # Mover para baixo mais rápido
                lifetime=random.uniform(0.05, 0.15),  # Vida mais curta
                size=random.uniform(2, 4),
                color=(255, random.randint(100, 200), 0),  # Cor de fogo
            )
            self.thruster_particles.append(particle)

        # Atualizar e remover partículas antigas de thruster
        for particle in self.thruster_particles[:]:
            particle["lifetime"] -= dt
            if particle["lifetime"] <= 0:
                self.thruster_particles.remove(particle)
            else:
                particle["x"] += particle["vx"] * dt
                particle["y"] += particle["vy"] * dt
                particle["size"] -= 1 * dt  # Diminuir de tamanho

    def move(self, held_actions: set[str], dt: float):
        current_speed = self.speed * (1.5 if self.speed_boost_timer > 0 else 1.0)
        move_vec = pygame.math.Vector2(0, 0)

        if "hold_left" in held_actions:
            move_vec.x -= 1
        if "hold_right" in held_actions:
            move_vec.x += 1
        if "hold_up" in held_actions:
            move_vec.y -= 1
        if "hold_down" in held_actions:
            move_vec.y += 1

        if move_vec.length() > 0:
            move_vec.normalize_ip()

        self.x += move_vec.x * current_speed * dt
        self.y += move_vec.y * current_speed * dt

        self._keep_in_bounds()

    def _keep_in_bounds(self):
        if self.x < 0:
            self.x = 0
        if self.y < 0:
            self.y = 0
        if self.x + self.w > Config.SCREEN_WIDTH:
            self.x = Config.SCREEN_WIDTH - self.w
        if self.y + self.h > Config.SCREEN_HEIGHT:
            self.y = Config.SCREEN_HEIGHT - self.h

    def bullet_spawn(self) -> list[tuple[float, float, bool]]:
        is_piercing = self.piercing_shot_timer > 0
        if self.double_shot_timer > 0:
            return [
                (self.x + self.w * 0.2 - 2.5, self.y, is_piercing),
                (self.x + self.w * 0.8 - 2.5, self.y, is_piercing),
            ]
        else:
            return [(self.x + self.w / 2 - 2.5, self.y, is_piercing)]

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return

        if self.invuln > 0 and int(self.invuln / 100) % 2 == 0:
            return

        # Desenhar partículas de thruster (atrás da nave)
        for p in self.thruster_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])

        # Calcular tremor
        shake_x, shake_y = 0, 0
        if self.is_entering:
            shake_x = random.randint(-2, 2)
            shake_y = random.randint(-2, 2)

        # Desenha a nave como pixel art com o tremor
        for row_idx, row in enumerate(self.PIXEL_ART_SPRITE):
            for col_idx, char in enumerate(row):
                color = self.COLOR_MAP.get(char)
                if color and len(color) == 4 and color[3] == 0:  # Transparente
                    continue
                if color:
                    pixel_x = self.x + col_idx * self.PIXEL_SIZE + shake_x
                    pixel_y = self.y + row_idx * self.PIXEL_SIZE + shake_y
                    pygame.draw.rect(
                        surface,
                        color,
                        (pixel_x, pixel_y, self.PIXEL_SIZE, self.PIXEL_SIZE),
                    )

        # Desenhar partículas de entrada (acima da nave)
        for p in self.entry_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])
