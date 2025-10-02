import pygame
from ..core.config import Config

class Ship:
    def __init__(self, x: float, y: float):
        self.w = 40
        self.h = 40
        self.x = x
        self.y = y
        self.speed = 250
        self.invuln = 0 # ms
        self.lives = Config.INITIAL_LIVES
        self.visible = True

        # Power-ups
        self.double_shot_timer = 0.0
        self.speed_boost_timer = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        if self.invuln > 0:
            self.invuln = max(0, self.invuln - dt * 1000)
        
        self.double_shot_timer = max(0.0, self.double_shot_timer - dt)
        self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)

    def move(self, held_actions: set[str], dt: float):
        current_speed = self.speed * (1.5 if self.speed_boost_timer > 0 else 1.0)
        if "hold_left" in held_actions:
            self.x -= current_speed * dt
        if "hold_right" in held_actions:
            self.x += current_speed * dt
        if "hold_up" in held_actions:
            self.y -= current_speed * dt
        if "hold_down" in held_actions:
            self.y += current_speed * dt
        self._keep_in_bounds()

    def _keep_in_bounds(self):
        if self.x < 0: self.x = 0
        if self.y < 0: self.y = 0
        if self.x + self.w > Config.SCREEN_WIDTH: self.x = Config.SCREEN_WIDTH - self.w
        if self.y + self.h > Config.SCREEN_HEIGHT: self.y = Config.SCREEN_HEIGHT - self.h

    def bullet_spawn(self) -> list[tuple[float, float]]:
        if self.double_shot_timer > 0:
            return [
                (self.x + self.w * 0.2 - 2.5, self.y),
                (self.x + self.w * 0.8 - 2.5, self.y)
            ]
        else:
            return [(self.x + self.w/2 - 2.5, self.y)]

    def draw(self, surface: pygame.Surface):
        if not self.visible: return

        if self.invuln > 0 and int(self.invuln / 100) % 2 == 0:
            return

        ship_color = (255, 255, 255)
        if self.speed_boost_timer > 0:
            ship_color = (100, 255, 255)
        elif self.double_shot_timer > 0:
            ship_color = (255, 255, 100)

        # Desenha a nave como um polígono (triângulo)
        points = [
            (self.x + self.w / 2, self.y), # Ponto de cima
            (self.x, self.y + self.h),       # Ponto inferior esquerdo
            (self.x + self.w, self.y + self.h) # Ponto inferior direito
        ]
        pygame.draw.polygon(surface, ship_color, points)