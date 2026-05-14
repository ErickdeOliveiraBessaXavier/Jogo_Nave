import math
from typing import Any, Iterable

import pygame

from ..core.config import config as Config


class HomingBullet:
    """Tiro teleguiado com vida consumível que é reduzida pelo dano causado.

    Interfaces esperadas pelo sistema de colisões:
    - atributos: x, y, w, h, rect, damage, life
    - métodos: update(dt, enemies), consume_life(amount), draw(surface)
    """

    def __init__(
        self,
        x: float,
        y: float,
        damage: int = 10,
        lifetime: float = 1.5,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        max_life: int = 100,
        homing_speed: float | None = None,
        turn_rate: float = 5.0,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.damage = int(damage)
        self.max_life = int(max_life)
        self.life = float(self.max_life)
        self.dead = False
        self.lifetime = float(lifetime)
        self.age = 0.0
        self.is_side_scroll = is_side_scroll

        speed = homing_speed if homing_speed is not None else float(
            getattr(Config, "HOMING_BULLET_SPEED", 300)
        )
        self.homing_speed = float(speed)
        self.turn_rate = float(turn_rate)

        # Size and collision rect
        self.w = 10
        self.h = 10
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Initial velocity
        if direction:
            dx, dy = direction
            mag = (dx * dx + dy * dy) ** 0.5 or 1.0
            self.vx = dx / mag * self.homing_speed
            self.vy = dy / mag * self.homing_speed
        else:
            # Default upward
            self.vx = 0.0
            self.vy = -self.homing_speed

        # Track hits this frame to avoid multi-hit
        self.hit_this_frame: set[int] = set()

    def consume_life(self, amount: float) -> None:
        self.life = max(0.0, self.life - float(amount))
        if self.life <= 0.0:
            self.dead = True

    def _find_best_target(self, enemies: Iterable[Any]) -> Any | None:
        best = None
        best_d = float("inf")
        for e in enemies:
            if getattr(e, "dead", False):
                continue
            ex = getattr(e, "x", None)
            ey = getattr(e, "y", None)
            ew = getattr(e, "w", getattr(getattr(e, "rect", None), "width", 0))
            eh = getattr(e, "h", getattr(getattr(e, "rect", None), "height", 0))
            if ex is None or ey is None:
                continue
            cx, cy = ex + ew / 2, ey + eh / 2
            d = (cx - (self.x + self.w / 2)) ** 2 + (cy - (self.y + self.h / 2)) ** 2
            if d < best_d:
                best_d = d
                best = e
        return best

    def update(self, dt: float, enemies: list[Any] | None = None) -> None:
        if self.dead:
            return
        self.age += dt
        if self.age >= self.lifetime:
            self.dead = True
            return

        # Homing logic
        if enemies:
            target = self._find_best_target(enemies)
            if target is not None:
                tx = getattr(target, "x", 0) + getattr(target, "w", 0) / 2
                ty = getattr(target, "y", 0) + getattr(target, "h", 0) / 2
                cx = self.x + self.w / 2
                cy = self.y + self.h / 2
                desired = math.atan2(ty - cy, tx - cx)
                current = math.atan2(self.vy, self.vx) if (self.vx or self.vy) else -math.pi / 2
                diff = (desired - current + math.pi) % (2 * math.pi) - math.pi
                max_turn = self.turn_rate * dt
                if diff > max_turn:
                    diff = max_turn
                elif diff < -max_turn:
                    diff = -max_turn
                angle = current + diff
                self.vx = math.cos(angle) * self.homing_speed
                self.vy = math.sin(angle) * self.homing_speed

        # Integrate position
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def draw(self, surface: pygame.Surface) -> None:
        alpha = int(200 * max(0.0, min(1.0, self.life / float(self.max_life))))
        col = (0, 200, 255)
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        pygame.draw.circle(s, (col[0], col[1], col[2], alpha), (self.w // 2, self.h // 2), self.w // 2)
        surface.blit(s, (int(self.x), int(self.y)))
