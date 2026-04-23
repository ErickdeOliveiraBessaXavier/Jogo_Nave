import math
import random
from typing import Any, Final, Literal

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from .alien_bullet import AlienBullet
from .mountain_serpent_pixel_map import C as _PIX_COLORS
from .mountain_serpent_pixel_map import PIXEL_COLS as _PIXEL_COLS
from .mountain_serpent_pixel_map import PIXEL_MAP as _PIXEL_MAP
from .mountain_serpent_pixel_map import PIXEL_ROWS as _PIXEL_ROWS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp_color(base: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Interpola uma cor em direção ao branco com fator t ∈ [0, 1]."""
    return (
        min(255, int(base[0] + (255 - base[0]) * t)),
        min(255, int(base[1] + (255 - base[1]) * t)),
        min(255, int(base[2] + (255 - base[2]) * t)),
    )


class _SerpentDustParticle:
    __slots__ = ("x", "y", "vx", "vy", "size", "life", "max_life")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(-16.0, 16.0)
        self.vy = random.uniform(44.0, 82.0)
        self.size = random.randint(2, 4)
        self.max_life = random.uniform(0.55, 1.0)
        self.life = self.max_life

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 78.0 * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        fade = max(0.0, self.life / self.max_life)
        color = (
            int(148 * fade),
            int(122 * fade),
            int(96 * fade),
        )
        pygame.draw.rect(
            surface,
            color,
            (int(self.x), int(self.y), self.size, self.size),
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
    _particles: list[_SerpentDustParticle]
    _particle_timer: float
    _swap_active: bool
    _swap_wait_timer: float
    _swap_elapsed: float
    _swap_duration: float
    _swap_shake_duration: float
    _swap_start_cx: float
    _swap_start_cy: float
    _swap_target_cx: float
    _swap_target_cy: float
    _swap_target_side: Literal["left", "right"]
    _swap_arc_dir: float
    _swap_seed: float
    _entry_anim_active: bool
    _entry_anim_timer: float
    _entry_anim_duration: float

    __slots__ = (
        "x", "y", "w", "h", "cx", "cy",
        "side", "boss",
        "health", "dead", "_hit_flash",
        "_origin_cx", "_origin_cy",
        "_rect", "emp_linger_timer",
        "row_index", "_rotation_angle",
        "_sprite_frame", "_rotation_dir",
        "mask", "_rotated_sprite",
        "_particles", "_particle_timer",
        "_swap_active", "_swap_wait_timer",
        "_swap_elapsed", "_swap_duration",
        "_swap_shake_duration", "_swap_start_cx",
        "_swap_start_cy", "_swap_target_cx",
        "_swap_target_cy", "_swap_target_side",
        "_swap_arc_dir", "_swap_seed",
        "_entry_anim_active", "_entry_anim_timer",
        "_entry_anim_duration",
    )

    RADIUS: Final[int] = 78
    MAX_HEALTH: Final[int] = 25

    # Cores como constantes de classe — não recriadas a cada draw()
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
        self._particles = []
        self._particle_timer = random.uniform(0.05, 0.22)
        self._swap_active = False
        self._swap_wait_timer = 0.0
        self._swap_elapsed = 0.0
        self._swap_duration = 0.0
        self._swap_shake_duration = 0.0
        self._swap_start_cx = x
        self._swap_start_cy = y
        self._swap_target_cx = x
        self._swap_target_cy = y
        self._swap_target_side = side
        self._swap_arc_dir = 0.0
        self._swap_seed = (row_index + (0.0 if side == "left" else 0.5)) * 11.0
        
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None
        
        self._rotated_sprite = None
        self.mask = None

        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        self._update_visuals()

        self._entry_anim_active = False
        self._entry_anim_timer = 0.0
        self._entry_anim_duration = 0.0

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
    def _load_animation_frames(
        cls, target_w: int, target_h: int
    ) -> list[pygame.Surface]:
        if cls._animation_frames is not None:
            return cls._animation_frames

        sprites_dir = (
            BASE_DIR
            / "assets"
            / "images"
            / "Sprites_Boss_Cobra"
            / "Serpent_Block-Sprites"
        )
        frames: list[pygame.Surface] = []
        if sprites_dir.exists():
            for path in sorted(sprites_dir.glob("*.png")):
                image = get_image(path)
                if image.get_size() != (target_w, target_h):
                    image = pygame.transform.scale(image, (target_w, target_h))
                frames.append(image)

        cls._animation_frames = frames
        return cls._animation_frames

    @classmethod
    def load_frames_for_preload(cls) -> list[pygame.Surface]:
        return cls._load_animation_frames(cls.RADIUS * 2, cls.RADIUS * 2)

    # -- Protocolo Enemy ------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    def get_points_value(self) -> int:
        return 80

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self._hit_flash = 0.1
        if self.health <= 0:
            self.health = 0
            self.dead = True
            self.boss.on_block_killed(self.side, self)

    def revive(self) -> None:
        """Restaura o bloco ao estado inicial (usado no portal)."""
        self.health = self.MAX_HEALTH
        self.dead = False
        self._hit_flash = 0.0
        self._rotation_angle = random.uniform(0.0, 360.0)
        self._rotation_dir = random.choice((-1.0, 1.0))
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None
        self._swap_active = False
        self._swap_wait_timer = 0.0
        self._swap_elapsed = 0.0
        self._particles.clear()
        self._update_visuals()

    def revive_with_entry(self) -> None:
        """Revive o bloco e dá um boost na velocidade do boss para re-entrada rápida."""
        self.revive()
        if self.side == "left":
            self._origin_cy = Config.SCREEN_HEIGHT + self.RADIUS
        else:
            self._origin_cy = -self.RADIUS
        self.boss._loop_speed_multiplier = max(self.boss._loop_speed_multiplier, 12.0)

    def _spawn_particle(self) -> None:
        spawn_x = self.cx + random.uniform(-14.0, 14.0)
        spawn_y = self.cy + self.RADIUS * 0.35
        self._particles.append(_SerpentDustParticle(spawn_x, spawn_y))

    def start_column_swap(
        self,
        target_cx: float,
        target_cy: float,
        target_side: Literal["left", "right"],
        row_delay: float,
        arc_dir: float,
        swap_duration: float,
        shake_duration: float,
    ) -> None:
        self._swap_active = True
        self._swap_wait_timer = max(0.0, row_delay)
        self._swap_elapsed = 0.0
        self._swap_duration = max(swap_duration, shake_duration + 0.01)
        self._swap_shake_duration = max(0.0, min(shake_duration, self._swap_duration))
        self._swap_start_cx = self.cx
        self._swap_start_cy = self.cy
        self._swap_target_cx = target_cx
        self._swap_target_cy = target_cy
        self._swap_target_side = target_side
        self._swap_arc_dir = arc_dir

    def _update_column_swap(self, dt: float) -> None:
        if not self._swap_active:
            return

        if self._swap_wait_timer > 0.0:
            self._swap_wait_timer = max(0.0, self._swap_wait_timer - dt)
            tremble_factor = 1.0 - min(1.0, self._swap_wait_timer / max(0.001, self._swap_duration))
            shake_x = math.sin(self.boss._block_wave_time * 38.0 + self._swap_seed) * 4.0 * tremble_factor
            shake_y = math.cos(self.boss._block_wave_time * 44.0 + self._swap_seed * 1.3) * 2.5 * tremble_factor
            self.cx = self._swap_start_cx + shake_x
            self.cy = self._swap_start_cy + shake_y
        else:
            self._swap_elapsed += dt
            if self._swap_elapsed <= self._swap_shake_duration:
                tremble_progress = self._swap_elapsed / max(0.001, self._swap_shake_duration)
                tremble_factor = 1.0 - tremble_progress
                shake_x = math.sin(self._swap_elapsed * 52.0 + self._swap_seed) * 5.5 * tremble_factor
                shake_y = math.cos(self._swap_elapsed * 60.0 + self._swap_seed * 1.4) * 3.5 * tremble_factor
                self.cx = self._swap_start_cx + shake_x
                self.cy = self._swap_start_cy + shake_y
            else:
                move_duration = max(0.001, self._swap_duration - self._swap_shake_duration)
                move_t = min(1.0, (self._swap_elapsed - self._swap_shake_duration) / move_duration)
                eased_t = move_t * move_t * (3.0 - 2.0 * move_t)
                self.cx = self._swap_start_cx + (self._swap_target_cx - self._swap_start_cx) * eased_t
                self.cy = self._swap_start_cy + (self._swap_target_cy - self._swap_start_cy) * eased_t
                arc = math.sin(eased_t * math.pi) * self.boss.BLOCK_SWAP_ARC_AMPLITUDE
                self.cy += arc * self._swap_arc_dir

                if move_t >= 1.0:
                    self._swap_active = False
                    self.side = self._swap_target_side
                    self._origin_cx = self._swap_target_cx
                    self._origin_cy = self._swap_target_cy
                    self.cx = self._swap_target_cx
                    self.cy = self._swap_target_cy

    def update(self, dt: float, *_args: Any, **_kwargs: Any) -> None:
        self._hit_flash = max(0.0, self._hit_flash - dt)

        self._rotation_angle = (
            self._rotation_angle
            + self.boss.BLOCK_ROTATION_SPEED * dt * self._rotation_dir
        ) % 360.0

        self._particle_timer -= dt
        if self._particle_timer <= 0.0:
            self._spawn_particle()
            self._particle_timer = random.uniform(0.08, 0.18)

        self._particles = [p for p in self._particles if not p.dead]
        for particle in self._particles:
            particle.update(dt)

        if self.boss._loop_movement_enabled and not self._swap_active:
            speed = self.boss._loop_speed * self.boss._loop_speed_multiplier
            total_loop_area = self.boss.BLOCK_COUNT * self.boss._block_spacing

            if self.side == "left":
                self._origin_cy -= speed * dt
                if self._origin_cy < -self.RADIUS:
                    self._origin_cy += total_loop_area
            else:
                self._origin_cy += speed * dt
                if self._origin_cy > Config.SCREEN_HEIGHT + self.RADIUS:
                    self._origin_cy -= total_loop_area

            wave_offset_x, wave_offset_y = self.boss.get_block_wave_offset(self.row_index, self.side)
            self.cx = self._origin_cx + wave_offset_x
            self.cy = self._origin_cy + wave_offset_y

        elif self._swap_active:
            self._update_column_swap(dt)
        else:
            wave_offset_x, wave_offset_y = self.boss.get_block_wave_offset(self.row_index, self.side)
            self.cx = self._origin_cx + wave_offset_x
            self.cy = self._origin_cy + wave_offset_y

        self._update_visuals()

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        for particle in self._particles:
            particle.draw(surface)

        cx, cy, r = int(self.cx), int(self.cy), self.RADIUS

        if self._rotated_sprite is not None:
            rotated_rect = self._rotated_sprite.get_rect(center=(cx, cy))
            surface.blit(self._rotated_sprite, rotated_rect.topleft)
            if self._hit_flash > 0.0:
                # Efeito de Brilho Mesclado
                surface.blit(self._rotated_sprite, rotated_rect.topleft, special_flags=pygame.BLEND_RGB_ADD)
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
    _attack_timer: float
    _phase: int
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
    _loop_movement_enabled: bool
    _loop_speed: float
    _loop_speed_multiplier: float
    _block_spacing: float
    _head_intro_active: bool
    _head_intro_progress: float
    _final_head_y: float
    _swap_pattern_enabled: bool
    _swap_cycle_timer: float
    _swap_event_active: bool
    _swap_event_rows: set[int]
    _dead_block_respawn_timers: dict[SerpentBlock, float]
    _head_pain_timer: float
    _block_wave_time: float
    _animation_seq_pos: int
    _animation_timer: float
    _head_frames: list[pygame.Surface]

    HEAD_RADIUS: Final[int] = 45
    SIDE_MARGIN: Final[int] = 52
    HEAD_Y: Final[int] = 88
    HEAD_SPEED: Final[float] = 24.0
    HEAD_PIXEL_SCALE: Final[int] = 4
    HEAD_FRAME_REPEAT: Final[int] = 2
    HEAD_ANIM_SLOW_FACTOR: Final[float] = 1.25
    DEFAULT_HEALTH: Final[int] = 1200

    ATTACK_SPIT_COOLDOWN: Final[float] = 4.0
    SPIT_SPEED: Final[float] = 220.0
    ATTACK_BREATH_COOLDOWN: Final[float] = 1.8
    BREATH_BULLET_COUNT: Final[int] = 5
    BREATH_SPREAD_ANGLE: Final[float] = math.radians(45.0)
    BREATH_SPEED: Final[float] = 130.0
    FURY_RESPAWN_DELAY: Final[float] = 6.0
    FURY_ATTACK_COOLDOWN: Final[float] = 1.2

    SHIELD_RADIUS: Final[int] = 55
    BLOCK_COUNT: Final[int] = 5
    RESPAWN_DELAY: Final[float] = 10.0
    BLOCK_WAVE_AMPLITUDE_X: Final[float] = 16.0
    BLOCK_WAVE_AMPLITUDE_Y: Final[float] = 9.0
    BLOCK_WAVE_SPEED: Final[float] = 1.9
    BLOCK_WAVE_PHASE_STEP: Final[float] = 0.85
    BLOCK_SIDE_PHASE_SHIFT: Final[float] = 1.6
    BLOCK_ROTATION_SPEED: Final[float] = 95.0
    BLOCK_SWAP_DURATION: Final[float] = 2.5
    BLOCK_SWAP_SHAKE_DURATION: Final[float] = 1.5
    BLOCK_SWAP_ARC_AMPLITUDE: Final[float] = 75.0
    BLOCK_SWAP_INTERVAL_MIN: Final[float] = 8.0
    BLOCK_SWAP_INTERVAL_MAX: Final[float] = 10.0
    BLOCK_SWAP_MIN_ROWS: Final[int] = 1
    BLOCK_SWAP_MAX_ROWS: Final[int] = 1
    BLOCK_SWAP_ROW_STAGGER: Final[float] = 0.14
    BLOCK_INDIVIDUAL_RESPAWN_DELAY: Final[float] = 50.0
    HEAD_STRAIN_SHAKE_X: Final[float] = 4.0
    HEAD_STRAIN_SHAKE_Y: Final[float] = 2.5
    HEAD_STRAIN_SHAKE_FREQ_X: Final[float] = 46.0
    HEAD_STRAIN_SHAKE_FREQ_Y: Final[float] = 61.0
    HEAD_PAIN_SHAKE_DURATION: Final[float] = 0.7

    _COLOR_BODY: Final[tuple[int, int, int]] = (106, 76, 125)
    _COLOR_EDGE: Final[tuple[int, int, int]] = (42, 24, 55)
    _COLOR_GLOW: Final[tuple[int, int, int]] = (255, 205, 125)

    _animation_frames: list[pygame.Surface] | None = None
    _animation_masks: list[pygame.mask.Mask] | None = None

    @classmethod
    def load_frames_for_preload(cls) -> list[pygame.Surface]:
        return cls._load_head_animation_frames()

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

        self.health = health if health is not None else self.DEFAULT_HEALTH
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
        self._attack_timer = self.ATTACK_SPIT_COOLDOWN * 0.75
        self._phase = 1
        self._swap_pattern_enabled = False
        self._swap_cycle_timer = 0.0
        self._swap_event_active = False
        self._swap_event_rows: set[int] = set()
        self._dead_block_respawn_timers: dict[SerpentBlock, float] = {}
        self._head_pain_timer = 0.0

        self._loop_movement_enabled = True
        self._loop_speed = 45.0
        self._loop_speed_multiplier = 25.0
        self._block_spacing = 0.0

        self._head_intro_active = True
        self._head_intro_progress = 0.0
        self.head_y = -200.0
        self._final_head_y = float(y if y is not None else self.HEAD_Y)

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
        if edge_distance == 0: return base_duration * 2.2
        if edge_distance == 1: return base_duration * 1.45
        return base_duration

    def _update_head_animation(self, dt: float) -> None:
        if len(self._head_frames) <= 1:
            self._head_sprite = self._head_frames[0]
            self.mask = self._head_masks[0]
            return

        if self._swap_event_active:
            current_frame_pos = self._frame_sequence[self._animation_seq_pos]
            self._head_sprite = self._head_frames[current_frame_pos]
            self.mask = self._head_masks[current_frame_pos]
            # No update de timer durante swap para "congelar" visualmente ou manter pose
            return

        self._animation_timer += dt
        current_frame_pos = self._frame_sequence[self._animation_seq_pos]
        current_frame_duration = self._get_animation_frame_duration(current_frame_pos)

        while self._animation_timer >= current_frame_duration:
            self._animation_timer -= current_frame_duration
            self._animation_seq_pos = (self._animation_seq_pos + 1) % len(self._frame_sequence)
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
        sprite = pygame.Surface((_PIXEL_COLS * scale, _PIXEL_ROWS * scale), pygame.SRCALPHA)
        for r, row in enumerate(_PIXEL_MAP):
            for c, key in enumerate(row):
                if key is None: continue
                color = _PIX_COLORS.get(key)
                if color is None: continue
                pygame.draw.rect(sprite, color, (c * scale, r * scale, scale, scale))
        return sprite

    def create_blocks(self) -> list[SerpentBlock]:
        blocks: list[SerpentBlock] = []
        total_loop_area = Config.SCREEN_HEIGHT + 2 * SerpentBlock.RADIUS
        gap_y = total_loop_area / self.BLOCK_COUNT
        self._block_spacing = gap_y

        for i in range(self.BLOCK_COUNT):
            left_cy = Config.SCREEN_HEIGHT + SerpentBlock.RADIUS + i * gap_y
            blocks.append(SerpentBlock(self.left_x, left_cy, "left", self, row_index=i))
            right_cy = -SerpentBlock.RADIUS - i * gap_y
            blocks.append(SerpentBlock(self.right_x, right_cy, "right", self, row_index=i))

        self._all_blocks = blocks
        return blocks

    def on_block_killed(self, side: Literal["left", "right"], block: SerpentBlock) -> None:
        if self.dead: return
        if side == "left": self._left_alive = max(0, self._left_alive - 1)
        else: self._right_alive = max(0, self._right_alive - 1)

        self._dead_block_respawn_timers[block] = self.BLOCK_INDIVIDUAL_RESPAWN_DELAY
        self._head_pain_timer = self.HEAD_PAIN_SHAKE_DURATION

        if self._left_alive == 0 and self._right_alive == 0 and not self.is_vulnerable:
            self.is_vulnerable = True
            self._respawn_timer = self._get_respawn_delay()
            self._loop_movement_enabled = False

    def _respawn_all_blocks(self) -> None:
        self._dead_block_respawn_timers.clear()
        self._left_alive = self.BLOCK_COUNT
        self._right_alive = self.BLOCK_COUNT
        self.is_vulnerable = False
        self._respawn_timer = -1.0
        self._loop_movement_enabled = True
        self._loop_speed_multiplier = 18.0

        for block in self._all_blocks:
            block.revive()
            if block.side == "left":
                block._origin_cy = Config.SCREEN_HEIGHT + SerpentBlock.RADIUS + block.row_index * self._block_spacing
            else:
                block._origin_cy = -SerpentBlock.RADIUS - block.row_index * self._block_spacing

        if not self._swap_pattern_enabled: self._swap_pattern_enabled = True
        self._schedule_next_swap()

    def _schedule_next_swap(self) -> None:
        self._swap_cycle_timer = random.uniform(self.BLOCK_SWAP_INTERVAL_MIN, self.BLOCK_SWAP_INTERVAL_MAX)

    def _get_row_pair(self, row_index: int) -> tuple[SerpentBlock | None, SerpentBlock | None]:
        left_block = next((b for b in self._all_blocks if b.row_index == row_index and b.side == "left"), None)
        right_block = next((b for b in self._all_blocks if b.row_index == row_index and b.side == "right"), None)
        return left_block, right_block

    def _start_periodic_column_swap(self) -> None:
        if self._swap_event_active or not self._swap_pattern_enabled: return
        valid_rows = [i for i in range(self.BLOCK_COUNT) if all(b and not b.dead for b in self._get_row_pair(i))]
        if not valid_rows:
            self._schedule_next_swap()
            return

        self._loop_movement_enabled = False
        row_count = random.randint(self.BLOCK_SWAP_MIN_ROWS, min(self.BLOCK_SWAP_MAX_ROWS, len(valid_rows)))
        selected_rows = sorted(random.sample(valid_rows, row_count))
        started_rows: set[int] = set()

        for idx, row in enumerate(selected_rows):
            left, right = self._get_row_pair(row)
            if not left or not right: continue
            delay = idx * self.BLOCK_SWAP_ROW_STAGGER
            left.start_column_swap(self.right_x, left._origin_cy, "right", delay, -1.0, self.BLOCK_SWAP_DURATION, self.BLOCK_SWAP_SHAKE_DURATION)
            right.start_column_swap(self.left_x, right._origin_cy, "left", delay, 1.0, self.BLOCK_SWAP_DURATION, self.BLOCK_SWAP_SHAKE_DURATION)
            started_rows.add(row)

        if not started_rows:
            self._loop_movement_enabled = True
            self._schedule_next_swap()
            return
        self._swap_event_active = True
        self._swap_event_rows = started_rows

    def _update_swap_cycle(self, dt: float) -> None:
        if not self._swap_pattern_enabled or not self._all_blocks: return
        if self._swap_event_active:
            if all(not b._swap_active for b in self._all_blocks if b.row_index in self._swap_event_rows):
                self._swap_event_active = False
                self._swap_event_rows.clear()
                self._schedule_next_swap()
                if not self.is_vulnerable:
                    self._loop_movement_enabled = True
                    self._loop_speed_multiplier = max(self._loop_speed_multiplier, 3.5)
            return
        if self.is_vulnerable: return
        self._swap_cycle_timer = max(0.0, self._swap_cycle_timer - dt)
        if self._swap_cycle_timer <= 0.0: self._start_periodic_column_swap()

    def _update_dead_block_respawns(self, dt: float) -> None:
        for block, timer in list(self._dead_block_respawn_timers.items()):
            next_timer = timer - dt
            if next_timer > 0.0:
                self._dead_block_respawn_timers[block] = next_timer
            else:
                del self._dead_block_respawn_timers[block]
                if block.dead:
                    block.revive_with_entry()
                    if block.side == "left": self._left_alive = min(self.BLOCK_COUNT, self._left_alive + 1)
                    else: self._right_alive = min(self.BLOCK_COUNT, self._right_alive + 1)

    def _get_respawn_delay(self) -> float:
        return self.FURY_RESPAWN_DELAY if self.health / self.max_health < 0.30 else self.RESPAWN_DELAY

    def _cooldown_for_phase(self, phase: int | None = None) -> float:
        p = self._phase if phase is None else phase
        if p == 3: return self.FURY_ATTACK_COOLDOWN
        if p == 2: return self.ATTACK_BREATH_COOLDOWN
        return self.ATTACK_SPIT_COOLDOWN

    def _execute_attack(self, px: float, py: float) -> list[AlienBullet]:
        bullets: list[AlienBullet] = []
        if self._phase >= 2: bullets.extend(self._create_breath(px, py))
        if self._phase == 1: bullets.append(self._create_spit(px, py))
        return bullets

    def _create_spit(self, px: float, py: float) -> AlienBullet:
        dx, dy = px - self.head_x, py - self.head_y
        dist = math.hypot(dx, dy)
        vx = dx / dist * self.SPIT_SPEED if dist > 0 else 0.0
        vy = dy / dist * self.SPIT_SPEED if dist > 0 else self.SPIT_SPEED
        bullet = AlienBullet(self.head_x, self.head_y)
        bullet.vx, bullet.vy = vx, vy
        return bullet

    def _create_breath(self, px: float, py: float) -> list[AlienBullet]:
        base_angle = math.atan2(py - self.head_y, px - self.head_x)
        count = self.BREATH_BULLET_COUNT
        step = self.BREATH_SPREAD_ANGLE / (count - 1) if count > 1 else 0
        bullets: list[AlienBullet] = []
        for i in range(count):
            angle = base_angle + (i - (count - 1) / 2) * step
            bullet = AlienBullet(self.head_x, self.head_y)
            bullet.vx, bullet.vy = math.cos(angle) * self.BREATH_SPEED, math.sin(angle) * self.BREATH_SPEED
            bullets.append(bullet)
        return bullets

    def get_block_wave_offset(self, row_index: int, side: Literal["left", "right"]) -> tuple[float, float]:
        phase = self._block_wave_time + row_index * self.BLOCK_WAVE_PHASE_STEP + (0.0 if side == "left" else self.BLOCK_SIDE_PHASE_SHIFT)
        return math.sin(phase) * self.BLOCK_WAVE_AMPLITUDE_X, math.sin(phase * 2.0) * self.BLOCK_WAVE_AMPLITUDE_Y

    def take_damage(self, amount: int) -> None:
        if self.dead: return
        self.health -= amount
        self._hit_flash = 0.1
        if self.health <= 0:
            self.health, self.dead = 0, True

    def get_points_value(self) -> int: return 850

    @property
    def rect(self) -> pygame.Rect: return self._head_rect

    def update(self, dt: float, player_x: float = 0.0, player_y: float = 0.0) -> tuple[list[Any], list[Any]]:
        if self.dead: return [], []
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._head_pain_timer = max(0.0, self._head_pain_timer - dt)
        self._update_head_animation(dt)
        self._block_wave_time += dt * self.BLOCK_WAVE_SPEED
        self._update_dead_block_respawns(dt)
        if self._respawn_timer > 0:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0: self._respawn_all_blocks()
        self._update_swap_cycle(dt)
        if self._loop_speed_multiplier > 1.0: self._loop_speed_multiplier = max(1.0, self._loop_speed_multiplier - dt * 6.5)

        if self._head_intro_active:
            if self._loop_speed_multiplier <= 1.0:
                self._head_intro_progress = min(1.0, self._head_intro_progress + dt * 1.5)
                eased_t = 1.0 - (1.0 - self._head_intro_progress) ** 2
                self.head_y = -200.0 + (self._final_head_y + 200.0) * eased_t
                if self._head_intro_progress >= 1.0: self._head_intro_active = False
            self._head_rect.x, self._head_rect.y = int(self.head_x - self._head_half_w), int(self.head_y - self._head_half_h)
            return [], []

        self._phase = 3 if self.health / self.max_health < 0.30 else 2 if self.is_vulnerable else 1
        self._attack_timer -= dt
        new_bullets = self._execute_attack(player_x, player_y) if self._attack_timer <= 0.0 else []
        if new_bullets: self._attack_timer = self._cooldown_for_phase()

        self.head_x += self.direction * self.speed * dt
        if self.head_x <= self.left_x + self.HEAD_RADIUS: self.head_x, self.direction = self.left_x + self.HEAD_RADIUS, 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS: self.head_x, self.direction = self.right_x - self.HEAD_RADIUS, -1
        self._head_rect.x, self._head_rect.y = int(self.head_x - self._head_half_w), int(self.head_y - self._head_half_h)

        return new_bullets, []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead: return

        # 1. Escudo
        if not self.is_vulnerable:
            total = self.BLOCK_COUNT * 2
            ratio = (self._left_alive + self._right_alive) / total if total > 0 else 0
            sc = (int(255 * (1 - (ratio - 0.5) * 2)), 255, int(255 * (ratio - 0.5) * 2)) if ratio > 0.5 else (255, int(255 * ratio * 2), 0)
            radius = self.SHIELD_RADIUS + int(math.sin(pygame.time.get_ticks() * 0.01) * 4)
            cx, cy = int(self.head_x), int(self.head_y)
            pygame.draw.circle(surface, sc, (cx, cy), radius, 3)
            gs = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
            pygame.draw.circle(gs, (*sc, 60), (radius + 5, radius + 5), radius)
            surface.blit(gs, (cx - radius - 5, cy - radius - 5), special_flags=pygame.BLEND_RGBA_ADD)

        # 2. Cabeça com Shake
        sx, sy = 0.0, 0.0
        if self._swap_event_active:
            sx = math.sin(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_X) * self.HEAD_STRAIN_SHAKE_X
            sy = math.cos(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_Y) * self.HEAD_STRAIN_SHAKE_Y
        elif self._head_pain_timer > 0.0:
            pt = self._head_pain_timer / self.HEAD_PAIN_SHAKE_DURATION
            sx = math.sin(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_X) * self.HEAD_STRAIN_SHAKE_X * (0.8 + 0.5 * pt)
            sy = math.cos(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_Y) * self.HEAD_STRAIN_SHAKE_Y * (0.8 + 0.5 * pt)

        dx, dy = int(self.head_x + sx) - self._head_half_w, int(self.head_y + sy) - self._head_half_h
        if self._hit_flash > 0.0:
            fs = self._head_sprite.copy()
            fs.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(fs, (dx, dy))
        else:
            surface.blit(self._head_sprite, (dx, dy))

        # 3. Barra de HP
        bx, by, bw, bh = int(self.head_x - 70), int(self.head_y - self._head_half_h - 14), 140, 8
        pygame.draw.rect(surface, colors.DARK_GRAY, (bx, by, bw, bh))
        if self.max_health > 0:
            lw = int(bw * self.health / self.max_health)
            pygame.draw.rect(surface, self._COLOR_GLOW, (bx, by, lw, bh))
            pygame.draw.rect(surface, colors.WHITE, (bx, by, bw, bh), 2)
