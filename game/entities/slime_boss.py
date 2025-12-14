import pygame
import random
from typing import List
from collections import deque
from ..core.assets import get_image, BASE_DIR
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.sprite_loader import sprite_loader
from .boss import Boss
from .boss_laser import BossLaser
from .meteor import Meteor
from .boss_square import BossSquare


class SlimeBoss(Boss):
    """Large horizontal slime boss that spans the screen width and slides side-to-side.

    Visuals use `game/assets/images/sprite_boss_03_slime.png` (scaled to boss size).
    """

    _animation_frames: list[pygame.Surface] | None = None

    @classmethod
    def load_animation_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona os sprites de animação uma vez."""
        if cls._animation_frames is not None:
            return cls._animation_frames

        # Register for preloading if not loaded
        if not sprite_loader.is_loaded():
            sprite_loader.register("slime_boss", cls.load_frames_for_preload)

        # Load immediately if not preloaded
        return cls._load_frames()

    @classmethod
    def load_frames_for_preload(cls) -> list[pygame.Surface]:
        """Public method for preloading frames."""
        return cls._load_frames()

    @classmethod
    def _load_frames(cls) -> list[pygame.Surface]:
        """Internal method to load the frames."""
        frames: list[pygame.Surface] = []
        for i in range(1, 25):  # 24 frames
            path = (
                BASE_DIR
                / "assets"
                / "images"
                / "sprite_boss_03_slime"
                / f"boss_3_gosma_sprite ({i}).png"
            )
            image = get_image(path)
            frames.append(image)

        cls._animation_frames = frames
        return frames

    def __init__(self, x: float, y: float, health: int | None = None):
        # Initialize base Boss to get full behavior
        super().__init__(x, y, health if health is not None else int(Config.BOSS_HEALTH * 1.2))

        # Make the boss span the entire screen width
        self.w = Config.SCREEN_WIDTH
        self.h = 600  # Taller to not be flattened

        # Position from left to right
        self.x = 0
        self.target_y = -100  # Final position higher up, not too low
        self.y = -self.h  # More off-screen from the top

        # No lateral movement, keep it spanning the screen
        # Animation
        self.animation_frames = self.load_animation_frames()
        self.current_frame = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.2  # seconds per frame - slower animation

        # Disable floating squares for SlimeBoss
        self.floating_squares = []
        self.position_history = deque(maxlen=30)

    def _init_floating_squares(self) -> None:
        """SlimeBoss doesn't use floating squares."""
        pass

    def update(self, dt: float, player_x: float, player_y: float | None = None) -> tuple[List[BossLaser], List[Meteor], List[BossSquare]]:
        # Update animation always
        self._update_animation(dt)
        
        # Call parent update
        return super().update(dt, player_x, player_y)

    def can_take_damage(self) -> bool:
        return self.state != "entering" and not self.dead

    def take_damage(self, amount: int) -> None:
        if not self.can_take_damage():
            return
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.dead = True
            sound_manager.play_explosion_boss()
        else:
            sound_manager.play_boss_damage()

    def _update_active_state(self, dt: float) -> None:
        # Stationary, no movement
        pass

    def _update_animation(self, dt: float) -> None:
        """Update animation frame."""
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

    def draw(self, surface: pygame.Surface) -> None:
        # Draw the slime sprite stretched to boss dimensions (with simple fallback)
        offset_x, offset_y = (0, 0)
        if self.frenzy_shake_timer > 0:
            offset_x = random.randint(-3, 3)

        if self.animation_frames:
            frame = self.animation_frames[self.current_frame]
            scaled_frame = pygame.transform.smoothscale(frame, (int(self.w), int(self.h)))
            surface.blit(scaled_frame, (int(self.x + offset_x), int(self.y + offset_y)))
        else:
            # Fallback: draw a red rectangle for visibility
            rect = pygame.Rect(int(self.x + offset_x), int(self.y + offset_y), int(self.w), int(self.h))
            pygame.draw.rect(surface, (255, 0, 0), rect)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))
