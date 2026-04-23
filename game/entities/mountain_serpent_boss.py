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

    __slots__ = (
        "x", "y", "w", "h", "cx", "cy",
        "side", "boss",
        "health", "dead", "_hit_flash",
        "_origin_cx", "_origin_cy",
        "_rect", "emp_linger_timer",
        "row_index", "_rotation_angle",
        "_sprite_frame", "_rotation_dir",
    )

    RADIUS: Final[int] = 68
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
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None

        # Posição fixa — rect calculado uma única vez
        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

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
        self._hit_flash = 0.18
        if self.health <= 0:
            self.health = 0
            self.dead = True
            self.boss.on_block_killed(self.side)

    def revive(self) -> None:
        """Restaura o bloco ao estado inicial (chamado pelo boss no respawn em grupo)."""
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
        self._rect.x = int(self.x)
        self._rect.y = int(self.y)

    def update(self, dt: float, *_args: Any, **_kwargs: Any) -> None:
        self._hit_flash = max(0.0, self._hit_flash - dt)

        self._rotation_angle = (
            self._rotation_angle
            + self.boss.BLOCK_ROTATION_SPEED * dt * self._rotation_dir
        ) % 360.0

        wave_offset_x, wave_offset_y = self.boss.get_block_wave_offset(self.row_index, self.side)
        self.cx = self._origin_cx + wave_offset_x
        self.cy = self._origin_cy + wave_offset_y
        self.x = self.cx - self.RADIUS
        self.y = self.cy - self.RADIUS
        self._rect.x = int(self.x)
        self._rect.y = int(self.y)

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        cx, cy, r = int(self.cx), int(self.cy), self.RADIUS

        if self._sprite_frame is not None:
            rotated = pygame.transform.rotate(self._sprite_frame, self._rotation_angle)
            rotated_rect = rotated.get_rect(center=(cx, cy))
            surface.blit(rotated, rotated_rect.topleft)
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
    x: float
    y: float
    w: float
    h: float
    _head_rect: pygame.Rect
    _head_sprite: pygame.Surface
    _head_half_w: int
    _head_half_h: int

    HEAD_RADIUS: Final[int] = 30
    SIDE_MARGIN: Final[int] = 52
    HEAD_Y: Final[int] = 88
    HEAD_SPEED: Final[float] = 24.0
    HEAD_PIXEL_SCALE: Final[int] = 4
    HEAD_FRAME_REPEAT: Final[int] = 2
    HEAD_ANIM_SLOW_FACTOR: Final[float] = 1.25

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

        self._animation_timer += dt

        current_frame_idx = self._frame_sequence[self._animation_seq_pos]
        current_frame_duration = self._get_animation_frame_duration(current_frame_idx)

        while self._animation_timer >= current_frame_duration:
            self._animation_timer -= current_frame_duration
            self._animation_seq_pos = (self._animation_seq_pos + 1) % len(
                self._frame_sequence
            )
            current_frame_idx = self._frame_sequence[self._animation_seq_pos]
            current_frame_duration = self._get_animation_frame_duration(current_frame_idx)

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
    # Fábrica de blocos — chame logo após criar o boss
    # ------------------------------------------------------------------

    def create_blocks(self) -> list[SerpentBlock]:
        """
        Instancia e retorna todos os SerpentBlocks das duas colunas,
        distribuídos uniformemente na vertical (estilo space-between).

        Adicione o retorno desta função diretamente em
        ``entity_manager.enemies`` (ou equivalente).
        """
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

    # ------------------------------------------------------------------
    # Callbacks chamados pelos blocos
    # ------------------------------------------------------------------

    def on_block_killed(self, side: Literal["left", "right"]) -> None:
        """
        Chamado por SerpentBlock.take_damage() quando um bloco morre.

        Quando TODOS os blocos (esquerda e direita) são destruídos:
          - A cabeça fica vulnerável a ataques diretos.
          - Inicia um timer de RESPAWN_DELAY s para o respawn coletivo.
        """
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
        """Revive todos os blocos e torna a cabeça imune novamente."""
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

    # ------------------------------------------------------------------
    # Dano direto à cabeça
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self._hit_flash = 0.2
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
        self._update_head_animation(dt)
        self._block_wave_time += dt * self.BLOCK_WAVE_SPEED

        # Tick do timer de respawn coletivo
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

        # Atualiza rect in-place — sem realocar objeto
        self._head_rect.x = int(self.head_x - self._head_half_w)
        self._head_rect.y = int(self.head_y - self._head_half_h)

        return [], []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        draw_x = int(self.head_x) - self._head_half_w
        draw_y = int(self.head_y) - self._head_half_h

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
