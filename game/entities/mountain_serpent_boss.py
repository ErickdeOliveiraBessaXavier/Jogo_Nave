import math
import random
from typing import Any, Final, Literal

import pygame

from ..core.assets import BASE_DIR, get_image
from ..core import colors
from ..core.config import config as Config
from .mountain_serpent_pixel_map import C as _PIX_COLORS
from .mountain_serpent_pixel_map import PIXEL_COLS as _PIXEL_COLS
from .mountain_serpent_pixel_map import PIXEL_MAP as _PIXEL_MAP
from .mountain_serpent_pixel_map import PIXEL_ROWS as _PIXEL_ROWS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp_color(
    base: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """Interpola uma cor em direção ao branco com fator t ∈ [0, 1]."""
    return (
        min(255, int(base[0] + (255 - base[0]) * t)),
        min(255, int(base[1] + (255 - base[1]) * t)),
        min(255, int(base[2] + (255 - base[2]) * t)),
    )


# ---------------------------------------------------------------------------
# Bloco de pedra independente — tratado como inimigo avulso
# ---------------------------------------------------------------------------

class SerpentBlock:
    """
    Bloco de pedra fixo nas laterais da tela.

    É registrado na lista de inimigos normais do EntityManager e colide com
    balas/laser exatamente como qualquer outro inimigo com HP.
    """

    side: Literal["left", "right"]
    boss: "MountainSerpentBoss"
    health: int
    dead: bool
    x: float
    y: float
    w: int
    h: int
    cx: float
    cy: float
    emp_linger_timer: float
    _hit_flash: float
    _origin_cx: float
    _origin_cy: float
    _rect: pygame.Rect
    mask: pygame.mask.Mask | None
    row_index: int
    _rotation_angle: float
    _sprite_frame: pygame.Surface | None
    _rotated_sprite: pygame.Surface | None
    _rotation_dir: float

    __slots__ = (
        "x", "y", "w", "h", "cx", "cy",
        "side", "boss",
        "health", "dead", "_hit_flash",
        "_origin_cx", "_origin_cy",
        "_rect", "emp_linger_timer",
        "row_index", "_rotation_angle",
        "_sprite_frame", "_rotation_dir",
        "mask", "_rotated_sprite",
    )

    RADIUS: Final[int] = 68
    MAX_HEALTH: Final[int] = 25

    _COLOR_BODY:      Final[tuple[int, int, int]] = (106, 76, 125)
    _COLOR_EDGE:      Final[tuple[int, int, int]] = (42, 24, 55)
    _COLOR_HIGHLIGHT: Final[tuple[int, int, int]] = (224, 126, 116)
    _COLOR_HP_HIGH:   Final[tuple[int, int, int]] = (80, 220, 80)
    _COLOR_HP_MID:    Final[tuple[int, int, int]] = (220, 160, 40)
    _COLOR_HP_LOW:    Final[tuple[int, int, int]] = (220, 60, 60)

    _animation_frames: list[pygame.Surface] | None = None

    def __init__(
        self,
        x: float,
        y: float,
        side: Literal["left", "right"],
        boss: "MountainSerpentBoss",
        row_index: int,
    ) -> None:
        self.x = x - self.RADIUS
        self.y = y - self.RADIUS
        self.w = self.RADIUS * 2
        self.h = self.RADIUS * 2
        self.cx = x
        self.cy = y
        self.side = side
        self.boss = boss
        self.row_index = row_index

        self.health: int = self.MAX_HEALTH
        self.dead: bool = False
        self._hit_flash: float = 0.0
        self.emp_linger_timer: float = 0.0

        self._origin_cx: float = x
        self._origin_cy: float = y

        self._rotation_angle = random.uniform(0.0, 360.0)
        self._rotation_dir = random.choice((-1.0, 1.0))
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None
        
        self._rotated_sprite = None
        self.mask = None

        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        self._update_visuals()

    def _update_visuals(self) -> None:
        """Atualiza o sprite rotacionado e a máscara de colisão."""
        if self._sprite_frame:
            self._rotated_sprite = pygame.transform.rotate(self._sprite_frame, self._rotation_angle)
            self.mask = pygame.mask.from_surface(self._rotated_sprite)
            new_rect = self._rotated_sprite.get_rect(center=(int(self.cx), int(self.cy)))
            self._rect.size = new_rect.size
            self._rect.topleft = new_rect.topleft
        else:
            surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 255, 255), (self.RADIUS, self.RADIUS), self.RADIUS)
            self.mask = pygame.mask.from_surface(surf)
            self._rotated_sprite = None

    @classmethod
    def _load_animation_frames(cls, target_w: int, target_h: int) -> list[pygame.Surface]:
        if cls._animation_frames is not None:
            return cls._animation_frames

        sprites_dir = BASE_DIR / "assets" / "images" / "Sprites_Boss_Cobra" / "Serpent_Block-Sprites"
        frames: list[pygame.Surface] = []
        if sprites_dir.exists():
            for path in sorted(sprites_dir.glob("*.png")):
                image = get_image(path)
                if image.get_size() != (target_w, target_h):
                    image = pygame.transform.scale(image, (target_w, target_h))
                frames.append(image)

        cls._animation_frames = frames
        return cls._animation_frames

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    def get_points_value(self) -> int:
        return 80

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self._hit_flash = 0.18
        if self.health <= 0:
            self.health = 0
            self.dead = True
            self.boss.on_block_killed(self.side)

    def revive(self) -> None:
        """Restaura o bloco ao estado inicial."""
        self.health = self.MAX_HEALTH
        self.dead = False
        self._hit_flash = 0.0
        self.cx = self._origin_cx
        self.cy = self._origin_cy
        self.x = self.cx - self.RADIUS
        self.y = self.cy - self.RADIUS
        self._rotation_angle = random.uniform(0.0, 360.0)
        self._rotation_dir = random.choice((-1.0, 1.0))
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None
        self._update_visuals()

    def update(self, dt: float, *_args: Any, **_kwargs: Any) -> None:
        self._hit_flash = max(0.0, self._hit_flash - dt)

        self._rotation_angle = (
            self._rotation_angle
            + self.boss.BLOCK_ROTATION_SPEED * dt * self._rotation_dir
        ) % 360.0

        wave_offset_x, wave_offset_y = self.boss.get_block_wave_offset(self.row_index, self.side)
        self.cx = self._origin_cx + wave_offset_x
        self.cy = self._origin_cy + wave_offset_y
        
        self._update_visuals()

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        cx, cy, r = int(self.cx), int(self.cy), self.RADIUS

        if self._rotated_sprite is not None:
            rotated_rect = self._rotated_sprite.get_rect(center=(cx, cy))
            surface.blit(self._rotated_sprite, rotated_rect.topleft)
        else:
            body_color = (
                _lerp_color(self._COLOR_BODY, self._hit_flash)
                if self._hit_flash > 0.0
                else self._COLOR_BODY
            )
            pygame.draw.circle(surface, self._COLOR_EDGE, (cx, cy), r + 3)
            pygame.draw.circle(surface, body_color, (cx, cy), r)
            pygame.draw.circle(surface, self._COLOR_HIGHLIGHT, (cx, cy), r // 2)

        # Barra de vida
        bar_w = r * 2
        bar_h = 4
        bar_x = cx - r
        bar_y = cy - r - 8
        ratio = self.health / self.MAX_HEALTH
        life_w = max(0, int(bar_w * ratio))
        bar_color = (
            self._COLOR_HP_HIGH if ratio > 0.5
            else self._COLOR_HP_MID if ratio > 0.25
            else self._COLOR_HP_LOW
        )
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(surface, bar_color, (bar_x, bar_y, life_w, bar_h))


# ---------------------------------------------------------------------------
# Boss — apenas a cabeça móvel
# ---------------------------------------------------------------------------

class MountainSerpentBoss:
    """
    Cabeça da Serpente de Pedra (boss das Cordilheiras).
    """

    head_x: float
    head_y: float
    direction: int
    speed: float
    left_x: float
    right_x: float
    health: int
    max_health: int
    dead: bool
    _hit_flash: float
    _left_alive: int
    _right_alive: int
    _all_blocks: list[SerpentBlock]
    _respawn_timer: float
    is_vulnerable: bool
    emp_linger_timer: float
    x: float
    y: float
    w: float
    h: float
    _head_rect: pygame.Rect
    _head_sprite: pygame.Surface
    mask: pygame.mask.Mask | None
    _head_masks: list[pygame.mask.Mask]
    _head_half_w: int
    _head_half_h: int

    HEAD_RADIUS: Final[int] = 30
    SIDE_MARGIN: Final[int] = 52
    HEAD_Y: Final[int] = 88
    HEAD_SPEED: Final[float] = 24.0
    HEAD_PIXEL_SCALE: Final[int] = 4
    HEAD_FRAME_REPEAT: Final[int] = 2
    HEAD_ANIM_SLOW_FACTOR: Final[float] = 1.25

    SHIELD_RADIUS: Final[int] = 55
    BLOCK_COUNT: Final[int] = 5
    RESPAWN_DELAY: Final[float] = 10.0
    BLOCK_WAVE_AMPLITUDE_X: Final[float] = 16.0
    BLOCK_WAVE_AMPLITUDE_Y: Final[float] = 9.0
    BLOCK_WAVE_SPEED: Final[float] = 1.9
    BLOCK_WAVE_PHASE_STEP: Final[float] = 0.85
    BLOCK_SIDE_PHASE_SHIFT: Final[float] = 1.6
    BLOCK_ROTATION_SPEED: Final[float] = 95.0

    _COLOR_BODY: Final[tuple[int, int, int]] = (106, 76, 125)
    _COLOR_EDGE: Final[tuple[int, int, int]] = (42, 24, 55)
    _COLOR_GLOW: Final[tuple[int, int, int]] = (255, 205, 125)

    _animation_frames: list[pygame.Surface] | None = None
    _animation_masks: list[pygame.mask.Mask] | None = None

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        health: int | None = None,
    ) -> None:
        self.head_x = float(x if x is not None else Config.SCREEN_WIDTH / 2)
        self.head_y = float(y if y is not None else self.HEAD_Y)
        self.direction = random.choice((-1, 1))
        self.speed = self.HEAD_SPEED

        self.left_x = float(self.SIDE_MARGIN)
        self.right_x = float(Config.SCREEN_WIDTH - self.SIDE_MARGIN)

        self.health = health if health is not None else 320
        self.max_health = self.health
        self.dead = False
        self._hit_flash = 0.0
        self.emp_linger_timer = 0.0

        self._left_alive = self.BLOCK_COUNT
        self._right_alive = self.BLOCK_COUNT
        self._all_blocks = []
        self._respawn_timer = -1.0
        self.is_vulnerable = False
        self._block_wave_time = random.uniform(0.0, math.tau)

        # Bounds de compatibilidade
        self.x = self.left_x - SerpentBlock.RADIUS
        self.y = self.head_y - self.HEAD_RADIUS
        self.w = (self.right_x + SerpentBlock.RADIUS) - self.x
        self.h = float(self.HEAD_RADIUS * 2)

        self._head_frames = self._load_head_animation_frames()
        self._head_masks = self._load_head_masks(self._head_frames)
        
        if not self._head_frames:
            sprite = self._build_head_sprite()
            self._head_frames = [sprite]
            self._head_masks = [pygame.mask.from_surface(sprite)]

        self._frame_sequence = self._build_ping_pong_sequence(
            len(self._head_frames), repeat_each=self.HEAD_FRAME_REPEAT
        )
        self._animation_seq_pos = 0
        self._animation_timer = 0.0

        self._head_sprite = self._head_frames[0]
        self.mask = self._head_masks[0]
        self._head_half_w = self._head_sprite.get_width() // 2
        self._head_half_h = self._head_sprite.get_height() // 2

        self._head_rect = pygame.Rect(
            int(self.head_x - self._head_half_w),
            int(self.head_y - self._head_half_h),
            self._head_sprite.get_width(),
            self._head_sprite.get_height(),
        )

    @classmethod
    def _load_head_animation_frames(cls) -> list[pygame.Surface]:
        if cls._animation_frames is not None:
            return cls._animation_frames

        sprites_dir = BASE_DIR / "assets" / "images" / "Sprites_Boss_Cobra"
        target_size = (cls.HEAD_PIXEL_SCALE * _PIXEL_COLS, cls.HEAD_PIXEL_SCALE * _PIXEL_ROWS)

        frames: list[pygame.Surface] = []
        if sprites_dir.exists():
            for path in sorted(sprites_dir.glob("*.png")):
                image = get_image(path)
                if image.get_size() != target_size:
                    image = pygame.transform.scale(image, target_size)
                frames.append(image)

        cls._animation_frames = frames
        return cls._animation_frames

    @classmethod
    def _load_head_masks(cls, frames: list[pygame.Surface]) -> list[pygame.mask.Mask]:
        if cls._animation_masks is not None:
            return cls._animation_masks
        
        masks = [pygame.mask.from_surface(f) for f in frames]
        cls._animation_masks = masks
        return masks

    @staticmethod
    def _build_ping_pong_sequence(frame_count: int, repeat_each: int = 1) -> list[int]:
        if frame_count <= 1:
            return [0]
        forward = list(range(frame_count))
        backward = list(range(frame_count - 2, 0, -1))
        sequence = forward + backward
        repeat = max(1, repeat_each)
        return [idx for idx in sequence for _ in range(repeat)]

    def _get_animation_frame_duration(self, frame_idx: int) -> float:
        if self._hit_flash > 0.0:
            base_duration = 0.045
        elif self.is_vulnerable:
            base_duration = 0.065
        else:
            base_duration = 0.09

        base_duration *= self.HEAD_ANIM_SLOW_FACTOR

        max_idx = len(self._head_frames) - 1
        edge_distance = min(frame_idx, max_idx - frame_idx)
        if edge_distance == 0:
            return base_duration * 2.2
        if edge_distance == 1:
            return base_duration * 1.45
        return base_duration

    def _update_head_animation(self, dt: float) -> None:
        if len(self._head_frames) <= 1:
            self._head_sprite = self._head_frames[0]
            self.mask = self._head_masks[0]
            return

        self._animation_timer += dt

        current_frame_pos = self._frame_sequence[self._animation_seq_pos]
        current_frame_duration = self._get_animation_frame_duration(current_frame_pos)

        while self._animation_timer >= current_frame_duration:
            self._animation_timer -= current_frame_duration
            self._animation_seq_pos = (self._animation_seq_pos + 1) % len(
                self._frame_sequence
            )
            current_frame_pos = self._frame_sequence[self._animation_seq_pos]
            current_frame_duration = self._get_animation_frame_duration(current_frame_pos)

        self._head_sprite = self._head_frames[current_frame_pos]
        self.mask = self._head_masks[current_frame_pos]

        self._head_half_w = self._head_sprite.get_width() // 2
        self._head_half_h = self._head_sprite.get_height() // 2
        self._head_rect.width = self._head_sprite.get_width()
        self._head_rect.height = self._head_sprite.get_height()

    def _build_head_sprite(self) -> pygame.Surface:
        scale = self.HEAD_PIXEL_SCALE
        sprite = pygame.Surface(
            (_PIXEL_COLS * scale, _PIXEL_ROWS * scale), pygame.SRCALPHA
        )

        for r, row in enumerate(_PIXEL_MAP):
            for c, key in enumerate(row):
                if key is None:
                    continue
                color = _PIX_COLORS.get(key)
                if color is None:
                    continue
                pygame.draw.rect(sprite, color, (c * scale, r * scale, scale, scale))

        return sprite

    def create_blocks(self) -> list[SerpentBlock]:
        blocks: list[SerpentBlock] = []
        margin_y = SerpentBlock.RADIUS + 20

        if self.BLOCK_COUNT > 1:
            available_height = Config.SCREEN_HEIGHT - (2 * margin_y)
            gap_y = available_height / (self.BLOCK_COUNT - 1)
        else:
            gap_y = 0.0

        for i in range(self.BLOCK_COUNT):
            cy = (
                margin_y + i * gap_y
                if self.BLOCK_COUNT > 1
                else Config.SCREEN_HEIGHT / 2
            )
            blocks.append(SerpentBlock(self.left_x, cy, "left", self, row_index=i))
            blocks.append(SerpentBlock(self.right_x, cy, "right", self, row_index=i))

        self._all_blocks = blocks
        return blocks

    def on_block_killed(self, side: Literal["left", "right"]) -> None:
        if self.dead:
            return

        if side == "left":
            self._left_alive = max(0, self._left_alive - 1)
        else:
            self._right_alive = max(0, self._right_alive - 1)

        if self._left_alive == 0 and self._right_alive == 0 and not self.is_vulnerable:
            self.is_vulnerable = True
            self._respawn_timer = self.RESPAWN_DELAY

    def _respawn_all_blocks(self) -> None:
        for block in self._all_blocks:
            block.revive()
        self._left_alive = self.BLOCK_COUNT
        self._right_alive = self.BLOCK_COUNT
        self.is_vulnerable = False
        self._respawn_timer = -1.0

    def get_block_wave_offset(
        self, row_index: int, side: Literal["left", "right"]
    ) -> tuple[float, float]:
        side_phase = 0.0 if side == "left" else self.BLOCK_SIDE_PHASE_SHIFT
        phase = (
            self._block_wave_time
            + row_index * self.BLOCK_WAVE_PHASE_STEP
            + side_phase
        )
        offset_x = math.sin(phase) * self.BLOCK_WAVE_AMPLITUDE_X
        offset_y = math.sin(phase * 2.0) * self.BLOCK_WAVE_AMPLITUDE_Y
        return offset_x, offset_y

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self._hit_flash = 0.2
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def get_points_value(self) -> int:
        return 850

    @property
    def rect(self) -> pygame.Rect:
        return self._head_rect

    def update(
        self, dt: float, player_x: float = 0.0, player_y: float = 0.0
    ) -> tuple[list[Any], list[Any]]:
        if self.dead:
            return [], []

        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._update_head_animation(dt)
        self._block_wave_time += dt * self.BLOCK_WAVE_SPEED

        if self._respawn_timer > 0:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self._respawn_all_blocks()

        self.head_x += self.direction * self.speed * dt

        if self.head_x <= self.left_x + self.HEAD_RADIUS:
            self.head_x = self.left_x + self.HEAD_RADIUS
            self.direction = 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS:
            self.head_x = self.right_x - self.HEAD_RADIUS
            self.direction = -1

        self._head_rect.x = int(self.head_x - self._head_half_w)
        self._head_rect.y = int(self.head_y - self._head_half_h)

        return [], []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        if not self.is_vulnerable:
            total_blocks = self.BLOCK_COUNT * 2
            alive_blocks = self._left_alive + self._right_alive
            health_ratio = alive_blocks / total_blocks if total_blocks > 0 else 0
            
            if health_ratio > 0.5:
                t = (health_ratio - 0.5) * 2
                shield_color = (int(255 * (1 - t)), 255, int(255 * t))
            else:
                t = health_ratio * 2
                shield_color = (255, int(255 * t), 0)

            pulse = math.sin(pygame.time.get_ticks() * 0.01) * 4
            radius = self.SHIELD_RADIUS + int(pulse)
            cx, cy = int(self.head_x), int(self.head_y)
            pygame.draw.circle(surface, shield_color, (cx, cy), radius, 3)
            
            glow_surf = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*shield_color, 60), (radius + 5, radius + 5), radius)
            surface.blit(glow_surf, (cx - radius - 5, cy - radius - 5), special_flags=pygame.BLEND_RGBA_ADD)

        draw_x = int(self.head_x) - self._head_half_w
        draw_y = int(self.head_y) - self._head_half_h
        surface.blit(self._head_sprite, (draw_x, draw_y))

        bar_w = 140
        bar_h = 8
        bar_x = int(self.head_x - bar_w / 2)
        bar_y = int(self.head_y - self._head_half_h - 14)
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        if self.max_health > 0:
            life_w = int(bar_w * self.health / self.max_health)
            pygame.draw.rect(surface, self._COLOR_GLOW, (bar_x, bar_y, life_w, bar_h))
            pygame.draw.rect(surface, colors.WHITE, (bar_x, bar_y, bar_w, bar_h), 2)