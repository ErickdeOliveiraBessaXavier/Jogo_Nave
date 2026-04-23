import math
import random
from typing import Any, Final, Literal

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from .alien_bullet import AlienBullet
from .mountain_serpent_pixel_map import PIXEL_COLS as _PIXEL_COLS
from .mountain_serpent_pixel_map import PIXEL_MAP as _PIXEL_MAP
from .mountain_serpent_pixel_map import PIXEL_ROWS as _PIXEL_ROWS
from .mountain_serpent_pixel_map import C as _PIX_COLORS

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

    Quando morrer, notifica o boss (MountainSerpentBoss) para que ele
    contabilize se uma coluna inteira foi destruída.
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
    row_index: int
    _rotation_angle: float
    _sprite_frame: pygame.Surface | None
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

    __slots__ = (
        "x",
        "y",
        "w",
        "h",
        "cx",
        "cy",
        "side",
        "boss",
        "health",
        "dead",
        "_hit_flash",
        "_origin_cx",
        "_origin_cy",
        "_rect",
        "emp_linger_timer",
        "row_index",
        "_rotation_angle",
        "_sprite_frame",
        "_rotation_dir",
        "_particles",
        "_particle_timer",
        "_swap_active",
        "_swap_wait_timer",
        "_swap_elapsed",
        "_swap_duration",
        "_swap_shake_duration",
        "_swap_start_cx",
        "_swap_start_cy",
        "_swap_target_cx",
        "_swap_target_cy",
        "_swap_target_side",
        "_swap_arc_dir",
        "_swap_seed",
        "_entry_anim_active",
        "_entry_anim_timer",
        "_entry_anim_duration",
    )

    RADIUS: Final[int] = 78
    MAX_HEALTH: Final[int] = 25

    # Cores como constantes de classe — não recriadas a cada draw()
    _COLOR_BODY: Final[tuple[int, int, int]] = (106, 76, 125)
    _COLOR_EDGE: Final[tuple[int, int, int]] = (42, 24, 55)
    _COLOR_HIGHLIGHT: Final[tuple[int, int, int]] = (224, 126, 116)
    _COLOR_HP_HIGH: Final[tuple[int, int, int]] = (80, 220, 80)
    _COLOR_HP_MID: Final[tuple[int, int, int]] = (220, 160, 40)
    _COLOR_HP_LOW: Final[tuple[int, int, int]] = (220, 60, 60)

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

        # Posição fixa — rect calculado uma única vez
        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Entrada animada (legado)
        self._entry_anim_active = False
        self._entry_anim_timer = 0.0
        self._entry_anim_duration = 0.0

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
        # Posição e outros resets
        self._rotation_angle = random.uniform(0.0, 360.0)
        self._rotation_dir = random.choice((-1.0, 1.0))
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None
        self._swap_active = False
        self._swap_wait_timer = 0.0
        self._swap_elapsed = 0.0
        self._particles.clear()

    def revive_with_entry(self) -> None:
        """Revive o bloco e dá um boost na velocidade do boss para re-entrada rápida."""
        self.revive()
        # Reposiciona fora da tela baseado na direção
        if self.side == "left":
            # Esquerda sobe, entra por baixo
            self._origin_cy = Config.SCREEN_HEIGHT + self.RADIUS
        else:
            # Direita desce, entra por cima
            self._origin_cy = -self.RADIUS

        # Dá o arranque na velocidade do loop se ainda não estiver rápido
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
            tremble_factor = 1.0 - min(
                1.0, self._swap_wait_timer / max(0.001, self._swap_duration)
            )
            shake_x = (
                math.sin(self.boss._block_wave_time * 38.0 + self._swap_seed)
                * 4.0
                * tremble_factor
            )
            shake_y = (
                math.cos(self.boss._block_wave_time * 44.0 + self._swap_seed * 1.3)
                * 2.5
                * tremble_factor
            )
            self.cx = self._swap_start_cx + shake_x
            self.cy = self._swap_start_cy + shake_y
        else:
            self._swap_elapsed += dt
            if self._swap_elapsed <= self._swap_shake_duration:
                tremble_progress = self._swap_elapsed / max(
                    0.001, self._swap_shake_duration
                )
                tremble_factor = 1.0 - tremble_progress
                shake_x = (
                    math.sin(self._swap_elapsed * 52.0 + self._swap_seed)
                    * 5.5
                    * tremble_factor
                )
                shake_y = (
                    math.cos(self._swap_elapsed * 60.0 + self._swap_seed * 1.4)
                    * 3.5
                    * tremble_factor
                )
                self.cx = self._swap_start_cx + shake_x
                self.cy = self._swap_start_cy + shake_y
            else:
                move_duration = max(
                    0.001, self._swap_duration - self._swap_shake_duration
                )
                move_t = min(
                    1.0,
                    (self._swap_elapsed - self._swap_shake_duration) / move_duration,
                )
                eased_t = move_t * move_t * (3.0 - 2.0 * move_t)
                self.cx = (
                    self._swap_start_cx
                    + (self._swap_target_cx - self._swap_start_cx) * eased_t
                )
                self.cy = (
                    self._swap_start_cy
                    + (self._swap_target_cy - self._swap_start_cy) * eased_t
                )
                arc = math.sin(eased_t * math.pi) * self.boss.BLOCK_SWAP_ARC_AMPLITUDE
                self.cy += arc * self._swap_arc_dir

                if move_t >= 1.0:
                    self._swap_active = False
                    self.side = self._swap_target_side
                    self._origin_cx = self._swap_target_cx
                    self._origin_cy = self._swap_target_cy
                    self.cx = self._swap_target_cx
                    self.cy = self._swap_target_cy

        self.x = self.cx - self.RADIUS
        self.y = self.cy - self.RADIUS
        self._rect.x = int(self.x)
        self._rect.y = int(self.y)

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

        # Loop contínuo com sistema de portal individual (Wrap-around)
        if self.boss._loop_movement_enabled and not self._swap_active:
            speed = self.boss._loop_speed * self.boss._loop_speed_multiplier
            # O tamanho total da "corrente" mantém o espaçamento constante
            total_loop_area = self.boss.BLOCK_COUNT * self.boss._block_spacing

            if self.side == "left":
                # Coluna esquerda: Sobe (entra por baixo, sai por cima)
                self._origin_cy -= speed * dt
                if self._origin_cy < -self.RADIUS:
                    self._origin_cy += total_loop_area
            else:
                # Coluna direita: Desce (entra por cima, sai por baixo)
                self._origin_cy += speed * dt
                if self._origin_cy > Config.SCREEN_HEIGHT + self.RADIUS:
                    self._origin_cy -= total_loop_area

            # Wave offset normal aplicado sobre a posição da corrente
            wave_offset_x, wave_offset_y = self.boss.get_block_wave_offset(
                self.row_index, self.side
            )
            self.cx = self._origin_cx + wave_offset_x
            self.cy = self._origin_cy + wave_offset_y

        elif self._swap_active:
            self._update_column_swap(dt)
        else:
            # Comportamento estático (caso loop esteja desligado mas não em swap)
            wave_offset_x, wave_offset_y = self.boss.get_block_wave_offset(
                self.row_index, self.side
            )
            self.cx = self._origin_cx + wave_offset_x
            self.cy = self._origin_cy + wave_offset_y

        self.x = self.cx - self.RADIUS
        self.y = self.cy - self.RADIUS
        self._rect.x = int(self.x)
        self._rect.y = int(self.y)

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        for particle in self._particles:
            particle.draw(surface)

        cx, cy, r = int(self.cx), int(self.cy), self.RADIUS

        if self._sprite_frame is not None:
            rotated = pygame.transform.rotate(self._sprite_frame, self._rotation_angle)
            rotated_rect = rotated.get_rect(center=(cx, cy))

            surface.blit(rotated, rotated_rect.topleft)
            if self._hit_flash > 0.0:
                # Efeito de Brilho (Sem máscara/silhueta sólida)
                surface.blit(
                    rotated, rotated_rect.topleft, special_flags=pygame.BLEND_RGB_ADD
                )
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
            self._COLOR_HP_HIGH
            if ratio > 0.5
            else self._COLOR_HP_MID
            if ratio > 0.25
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

    Responsabilidade desta classe:
      - Mover a cabeça de lado a lado.
      - Receber dano **somente** quando todos os blocos laterais forem destruídos
        (durante a janela de vulnerabilidade, até o respawn em 10 s).
      - Desenhar a cabeça e a barra de HP.

    Os blocos de pedra (SerpentBlock) são entidades separadas gerenciadas
    pelo EntityManager. Ao criar o boss, use ``create_blocks()`` para
    instanciar os blocos e adicioná-los à lista de inimigos.
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
    _head_half_w: int
    _head_half_h: int

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

        # Movimento contínuo dos blocos (loop infinito com portal)
        self._loop_movement_enabled = (
            True  # Já começa ligado para a animação de entrada
        )
        self._loop_speed = 45.0  # Velocidade base
        self._loop_speed_multiplier = 25.0  # Multiplicador inicial (arranque)
        self._block_spacing = 0.0  # Definido no create_blocks

        # Animação de surgimento da cabeça (Descer de cima para baixo)
        self._head_intro_active = True
        self._head_intro_progress = 0.0
        self.head_y = -200.0  # Começa acima da tela
        self._final_head_y = float(y if y is not None else self.HEAD_Y)

        # Bounds de compatibilidade — valores imutáveis, calculados uma vez
        self.x = self.left_x - SerpentBlock.RADIUS
        self.y = self.head_y - self.HEAD_RADIUS
        self.w = (self.right_x + SerpentBlock.RADIUS) - self.x
        self.h = float(self.HEAD_RADIUS * 2)

        self._head_frames = self._load_head_animation_frames()
        if not self._head_frames:
            self._head_frames = [self._build_head_sprite()]

        self._frame_sequence = self._build_ping_pong_sequence(
            len(self._head_frames), repeat_each=self.HEAD_FRAME_REPEAT
        )
        self._animation_seq_pos = 0
        self._animation_timer = 0.0

        self._head_sprite = self._head_frames[0]
        self._head_half_w = self._head_sprite.get_width() // 2
        self._head_half_h = self._head_sprite.get_height() // 2

        # Rect da cabeça cacheado — atualizado in-place em update(), sem realocar
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
        target_size = (
            cls.HEAD_PIXEL_SCALE * _PIXEL_COLS,
            cls.HEAD_PIXEL_SCALE * _PIXEL_ROWS,
        )

        frames: list[pygame.Surface] = []
        if sprites_dir.exists():
            for path in sorted(sprites_dir.glob("*.png")):
                image = get_image(path)
                if image.get_size() != target_size:
                    image = pygame.transform.scale(image, target_size)
                frames.append(image)

        cls._animation_frames = frames
        return cls._animation_frames

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
            return

        if self._swap_event_active:
            current_frame_idx = self._frame_sequence[self._animation_seq_pos]
            self._head_sprite = self._head_frames[current_frame_idx]
            self._head_half_w = self._head_sprite.get_width() // 2
            self._head_half_h = self._head_sprite.get_height() // 2
            self._head_rect.width = self._head_sprite.get_width()
            self._head_rect.height = self._head_sprite.get_height()
            return

        self._animation_timer += dt

        current_frame_idx = self._frame_sequence[self._animation_seq_pos]
        current_frame_duration = self._get_animation_frame_duration(current_frame_idx)

        while self._animation_timer >= current_frame_duration:
            self._animation_timer -= current_frame_duration
            self._animation_seq_pos = (self._animation_seq_pos + 1) % len(
                self._frame_sequence
            )
            current_frame_idx = self._frame_sequence[self._animation_seq_pos]
            current_frame_duration = self._get_animation_frame_duration(
                current_frame_idx
            )

        self._head_sprite = self._head_frames[current_frame_idx]

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

    # ------------------------------------------------------------------
    # Fábrica de blocos
    # ------------------------------------------------------------------

    def create_blocks(self) -> list[SerpentBlock]:
        """
        Instancia os blocos fora da tela para iniciarem a entrada vertical acelerada.
        """
        blocks: list[SerpentBlock] = []

        # Espaçamento para cobrir a tela + margens de segurança para o portal
        total_loop_area = Config.SCREEN_HEIGHT + 2 * SerpentBlock.RADIUS
        gap_y = total_loop_area / self.BLOCK_COUNT
        self._block_spacing = gap_y

        for i in range(self.BLOCK_COUNT):
            # Coluna Esquerda: Sobe (entra por baixo)
            left_cy = Config.SCREEN_HEIGHT + SerpentBlock.RADIUS + i * gap_y
            blocks.append(SerpentBlock(self.left_x, left_cy, "left", self, row_index=i))

            # Coluna Direita: Desce (entra por cima)
            right_cy = -SerpentBlock.RADIUS - i * gap_y
            blocks.append(
                SerpentBlock(self.right_x, right_cy, "right", self, row_index=i)
            )

        self._all_blocks = blocks
        return blocks

    # ------------------------------------------------------------------
    # Callbacks chamados pelos blocos
    # ------------------------------------------------------------------

    def on_block_killed(
        self, side: Literal["left", "right"], block: SerpentBlock
    ) -> None:
        """
        Chamado por SerpentBlock.take_damage() quando um bloco morre.
        """
        if self.dead:
            return

        if side == "left":
            self._left_alive = max(0, self._left_alive - 1)
        else:
            self._right_alive = max(0, self._right_alive - 1)

        self._dead_block_respawn_timers[block] = self.BLOCK_INDIVIDUAL_RESPAWN_DELAY
        self._head_pain_timer = self.HEAD_PAIN_SHAKE_DURATION

        if self._left_alive == 0 and self._right_alive == 0 and not self.is_vulnerable:
            self.is_vulnerable = True
            self._respawn_timer = self._get_respawn_delay()
            self._loop_movement_enabled = False

    def _respawn_all_blocks(self) -> None:
        """Revive todos os blocos com arranque de velocidade."""
        self._dead_block_respawn_timers.clear()
        self._left_alive = self.BLOCK_COUNT
        self._right_alive = self.BLOCK_COUNT
        self.is_vulnerable = False
        self._respawn_timer = -1.0
        self._loop_movement_enabled = True
        self._loop_speed_multiplier = 18.0  # Boost na re-entrada

        # Reposiciona e reseta blocos usando o row_index para manter o sincronismo
        for block in self._all_blocks:
            block.revive()
            if block.side == "left":
                block._origin_cy = (
                    Config.SCREEN_HEIGHT
                    + SerpentBlock.RADIUS
                    + block.row_index * self._block_spacing
                )
            else:
                block._origin_cy = (
                    -SerpentBlock.RADIUS - block.row_index * self._block_spacing
                )

        if not self._swap_pattern_enabled:
            self._swap_pattern_enabled = True
        self._schedule_next_swap()

    def _start_coordinated_entry_animation(self) -> None:
        """Legado da versão anterior. O loop acelerado agora cuida disso."""
        pass

    def _check_if_all_entry_animations_finished(self) -> None:
        """Legado da versão anterior."""
        pass

    def _schedule_next_swap(self) -> None:
        self._swap_cycle_timer = random.uniform(
            self.BLOCK_SWAP_INTERVAL_MIN, self.BLOCK_SWAP_INTERVAL_MAX
        )

    def _get_row_pair(
        self, row_index: int
    ) -> tuple[SerpentBlock | None, SerpentBlock | None]:
        left_block: SerpentBlock | None = None
        right_block: SerpentBlock | None = None
        for block in self._all_blocks:
            if block.row_index != row_index:
                continue
            if block.side == "left":
                left_block = block
            else:
                right_block = block
        return left_block, right_block

    def _start_periodic_column_swap(self) -> None:
        if self._swap_event_active or not self._swap_pattern_enabled:
            return

        valid_rows: list[int] = []
        for row_index in range(self.BLOCK_COUNT):
            left_block, right_block = self._get_row_pair(row_index)
            if left_block is None or right_block is None:
                continue
            if left_block.dead or right_block.dead:
                continue
            valid_rows.append(row_index)

        if not valid_rows:
            self._schedule_next_swap()
            return

        # PAUSAR o movimento vertical para garantir organização das fileiras durante a troca
        self._loop_movement_enabled = False

        max_rows = min(self.BLOCK_SWAP_MAX_ROWS, len(valid_rows))
        min_rows = min(self.BLOCK_SWAP_MIN_ROWS, max_rows)
        row_count = random.randint(min_rows, max_rows)
        selected_rows = sorted(random.sample(valid_rows, row_count))
        started_rows: set[int] = set()

        for order_index, row_index in enumerate(selected_rows):
            left_block, right_block = self._get_row_pair(row_index)
            if left_block is None or right_block is None:
                continue

            row_delay = order_index * self.BLOCK_SWAP_ROW_STAGGER

            left_block.start_column_swap(
                target_cx=self.right_x,
                target_cy=left_block._origin_cy,
                target_side="right",
                row_delay=row_delay,
                arc_dir=-1.0,
                swap_duration=self.BLOCK_SWAP_DURATION,
                shake_duration=self.BLOCK_SWAP_SHAKE_DURATION,
            )
            right_block.start_column_swap(
                target_cx=self.left_x,
                target_cy=right_block._origin_cy,
                target_side="left",
                row_delay=row_delay,
                arc_dir=1.0,
                swap_duration=self.BLOCK_SWAP_DURATION,
                shake_duration=self.BLOCK_SWAP_SHAKE_DURATION,
            )
            started_rows.add(row_index)

        if not started_rows:
            self._loop_movement_enabled = True  # Falha ao iniciar, retoma loop
            self._schedule_next_swap()
            return

        self._swap_event_active = True
        self._swap_event_rows = started_rows

    def _update_swap_cycle(self, dt: float) -> None:
        if not self._swap_pattern_enabled or not self._all_blocks:
            return

        if self._swap_event_active:
            if all(
                not block._swap_active
                for block in self._all_blocks
                if block.row_index in self._swap_event_rows
            ):
                self._swap_event_active = False
                self._swap_event_rows.clear()
                self._schedule_next_swap()

                # RETOMAR movimento vertical apenas se o boss NÃO estiver vulnerável
                if not self.is_vulnerable:
                    self._loop_movement_enabled = True
                    # Dá um pequeno arranque para sinalizar a volta à "normalidade"
                    self._loop_speed_multiplier = max(self._loop_speed_multiplier, 3.5)
            return

        if self.is_vulnerable:
            return

        self._swap_cycle_timer = max(0.0, self._swap_cycle_timer - dt)
        if self._swap_cycle_timer <= 0.0:
            self._start_periodic_column_swap()

    def _update_dead_block_respawns(self, dt: float) -> None:
        if not self._dead_block_respawn_timers:
            return

        for block, timer in list(self._dead_block_respawn_timers.items()):
            next_timer = timer - dt
            if next_timer > 0.0:
                self._dead_block_respawn_timers[block] = next_timer
                continue

            del self._dead_block_respawn_timers[block]
            if not block.dead:
                continue

            block.revive_with_entry()
            if block.side == "left":
                self._left_alive = min(self.BLOCK_COUNT, self._left_alive + 1)
            else:
                self._right_alive = min(self.BLOCK_COUNT, self._right_alive + 1)

    def _get_respawn_delay(self) -> float:
        return (
            self.FURY_RESPAWN_DELAY
            if self.health / self.max_health < 0.30
            else self.RESPAWN_DELAY
        )

    def _cooldown_for_phase(self, phase: int | None = None) -> float:
        phase = self._phase if phase is None else phase
        if phase == 3:
            return self.FURY_ATTACK_COOLDOWN
        if phase == 2:
            return self.ATTACK_BREATH_COOLDOWN
        return self.ATTACK_SPIT_COOLDOWN

    def _execute_attack(self, player_x: float, player_y: float) -> list[AlienBullet]:
        bullets: list[AlienBullet] = []
        if self._phase >= 2:
            bullets.extend(self._create_breath(player_x, player_y))
        if self._phase == 1:
            bullets.append(self._create_spit(player_x, player_y))
        return bullets

    def _create_spit(self, player_x: float, player_y: float) -> AlienBullet:
        dx = player_x - self.head_x
        dy = player_y - self.head_y
        dist = math.hypot(dx, dy)
        if dist > 0:
            vx = dx / dist * self.SPIT_SPEED
            vy = dy / dist * self.SPIT_SPEED
        else:
            vx = 0.0
            vy = self.SPIT_SPEED
        bullet = AlienBullet(self.head_x, self.head_y)
        bullet.vx = vx
        bullet.vy = vy
        return bullet

    def _create_breath(self, player_x: float, player_y: float) -> list[AlienBullet]:
        base_angle = math.atan2(player_y - self.head_y, player_x - self.head_x)
        count = self.BREATH_BULLET_COUNT
        if count <= 1:
            angles = [base_angle]
        else:
            step = self.BREATH_SPREAD_ANGLE / (count - 1)
            angles = [base_angle + (i - (count - 1) / 2) * step for i in range(count)]
        bullets: list[AlienBullet] = []
        for angle in angles:
            bullet = AlienBullet(self.head_x, self.head_y)
            bullet.vx = math.cos(angle) * self.BREATH_SPEED
            bullet.vy = math.sin(angle) * self.BREATH_SPEED
            bullets.append(bullet)
        return bullets

    def get_block_wave_offset(
        self, row_index: int, side: Literal["left", "right"]
    ) -> tuple[float, float]:
        # A defasagem por linha cria o efeito de onda entre os blocos.
        row_phase = row_index * self.BLOCK_WAVE_PHASE_STEP
        side_phase = 0.0 if side == "left" else self.BLOCK_SIDE_PHASE_SHIFT
        phase = self._block_wave_time + row_phase + side_phase
        offset_x = math.sin(phase) * self.BLOCK_WAVE_AMPLITUDE_X
        offset_y = math.sin(phase * 2.0) * self.BLOCK_WAVE_AMPLITUDE_Y
        return offset_x, offset_y

    # ------------------------------------------------------------------
    # Dano direto à cabeça
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self._hit_flash = 0.1
        if self.health <= 0:
            self.health = 0
            self.dead = True

    # ------------------------------------------------------------------
    # Compatibilidade com collisions.py / entity_manager.py
    # ------------------------------------------------------------------

    def get_points_value(self) -> int:
        return 850

    @property
    def rect(self) -> pygame.Rect:
        """Rect preciso da cabeça — atualizado in-place em update()."""
        return self._head_rect

    # ------------------------------------------------------------------
    # Update / Draw
    # ------------------------------------------------------------------

    def update(
        self, dt: float, player_x: float = 0.0, player_y: float = 0.0
    ) -> tuple[list[Any], list[Any]]:
        if self.dead:
            return [], []

        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._head_pain_timer = max(0.0, self._head_pain_timer - dt)
        self._update_head_animation(dt)
        self._block_wave_time += dt * self.BLOCK_WAVE_SPEED
        self._update_dead_block_respawns(dt)

        # Tick do timer de respawn coletivo
        if self._respawn_timer > 0:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self._respawn_all_blocks()

        self._update_swap_cycle(dt)

        # Desaceleração da velocidade do loop até a velocidade normal
        if self._loop_speed_multiplier > 1.0:
            self._loop_speed_multiplier = max(
                1.0, self._loop_speed_multiplier - dt * 6.5
            )

        # Lógica de animação de entrada da cabeça (Surgimento)
        if self._head_intro_active:
            if self._loop_speed_multiplier <= 1.0:
                self._head_intro_progress = min(
                    1.0, self._head_intro_progress + dt * 1.5
                )

                # Ease-out para descida elegante
                t = self._head_intro_progress
                eased_t = 1.0 - (1.0 - t) ** 2

                start_y = -200.0
                self.head_y = start_y + (self._final_head_y - start_y) * eased_t

                if self._head_intro_progress >= 1.0:
                    self._head_intro_active = False

            # Enquanto entra, apenas atualiza o rect e não faz mais nada
            self._head_rect.x = int(self.head_x - self._head_half_w)
            self._head_rect.y = int(self.head_y - self._head_half_h)
            return [], []

        self._phase = (
            3
            if self.health / self.max_health < 0.30
            else 2
            if self.is_vulnerable
            else 1
        )

        self._attack_timer -= dt
        new_bullets: list[AlienBullet] = []
        if self._attack_timer <= 0.0:
            attack_phase = self._phase
            new_bullets = self._execute_attack(player_x, player_y)
            self._attack_timer = self._cooldown_for_phase(attack_phase)

        self.head_x += self.direction * self.speed * dt

        if self.head_x <= self.left_x + self.HEAD_RADIUS:
            self.head_x = self.left_x + self.HEAD_RADIUS
            self.direction = 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS:
            self.head_x = self.right_x - self.HEAD_RADIUS
            self.direction = -1

        # Atualiza rect in-place — sem realocar objeto
        self._head_rect.x = int(self.head_x - self._head_half_w)
        self._head_rect.y = int(self.head_y - self._head_half_h)

        return new_bullets, []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        shake_x = 0.0
        shake_y = 0.0
        if self._swap_event_active:
            shake_x = (
                math.sin(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_X)
                * self.HEAD_STRAIN_SHAKE_X
            )
            shake_y = (
                math.cos(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_Y)
                * self.HEAD_STRAIN_SHAKE_Y
            )
        elif self._head_pain_timer > 0.0:
            pain_t = self._head_pain_timer / self.HEAD_PAIN_SHAKE_DURATION
            shake_x = (
                math.sin(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_X)
                * self.HEAD_STRAIN_SHAKE_X
                * (0.8 + 0.5 * pain_t)
            )
            shake_y = (
                math.cos(self._block_wave_time * self.HEAD_STRAIN_SHAKE_FREQ_Y)
                * self.HEAD_STRAIN_SHAKE_Y
                * (0.8 + 0.5 * pain_t)
            )

        draw_x = int(self.head_x + shake_x) - self._head_half_w
        draw_y = int(self.head_y + shake_y) - self._head_half_h

        if self._hit_flash > 0.0:
            flash_surf = self._head_sprite.copy()
            flash_surf.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(flash_surf, (draw_x, draw_y))
        else:
            surface.blit(self._head_sprite, (draw_x, draw_y))

        # Barra de vida
        bar_w = 140
        bar_h = 8
        bar_x = int(self.head_x - bar_w / 2)
        bar_y = int(self.head_y - self._head_half_h - 14)
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        if self.max_health > 0:
            life_w = int(bar_w * self.health / self.max_health)
            pygame.draw.rect(surface, self._COLOR_GLOW, (bar_x, bar_y, life_w, bar_h))
            pygame.draw.rect(surface, colors.WHITE, (bar_x, bar_y, bar_w, bar_h), 2)
