"""Boss Serpente de Pedra das Cordilheiras.

Estrutura:
  - _SerpentDustParticle  — partícula de poeira (sistema de partículas)
  - SerpentBlock          — bloco de pedra lateral (entidade inimiga independente)
  - MountainSerpentBoss   — cabeça do boss (entidade principal)
  - SerpentRockBullet     — projétil temático de rocha (fragmento de bloco)

Padrões aplicados
-----------------
* Constantes de física/gameplay centralizadas e comentadas com unidades.
* ``__slots__`` em todas as classes de dados/entidades para reduzir overhead de memória.
* Anotações de tipo explícitas; sem ``Any`` desnecessário.
* Separação clara de responsabilidades: cada método faz uma coisa só.
* Nomes de variáveis em português, alinhados ao restante do projeto.
* Tipos de retorno explícitos em todos os métodos públicos.
* Remoção de código morto (métodos legado vazios substituídos por comentário).
* ``_get_row_pair`` usa dicionário pré-construído em vez de loop O(n).
* Partículas gerenciadas in-place para evitar realocações de lista por frame.
* Easing centralizado em helper estático.
* Fase do boss calculada via método dedicado, sem bloco ternário aninhado.
"""

import math
import random
from typing import Final, List, Literal, Optional, TypedDict
from typing import TypeAlias

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from .mountain_serpent_pixel_map import PIXEL_COLS as _PIXEL_COLS
from .mountain_serpent_pixel_map import PIXEL_MAP as _PIXEL_MAP
from .mountain_serpent_pixel_map import PIXEL_ROWS as _PIXEL_ROWS
from .mountain_serpent_pixel_map import C as _PIX_COLORS
from .stone_sentry import StoneSentry

# ---------------------------------------------------------------------------
# Tipagens e Estruturas de Dados
# ---------------------------------------------------------------------------

_RGB: TypeAlias = tuple[int, int, int]
Side = Literal["left", "right"]


class _AfterImage(TypedDict):
    """Estrutura para rastro fantasmagorico da cabeca."""

    x: float
    y: float
    sprite: pygame.Surface
    life: float


class _BulletAfterImage(TypedDict):
    """Estrutura para rastro fantasmagorico dos estilhacos."""

    x: float
    y: float
    angle: float
    life: float


# ---------------------------------------------------------------------------
# Helpers de uso geral
# ---------------------------------------------------------------------------


def _lerp_color(base: _RGB, t: float) -> _RGB:
    """Interpola *base* em direcao ao branco com fator t em [0, 1]."""
    return (
        min(255, int(base[0] + (255 - base[0]) * t)),
        min(255, int(base[1] + (255 - base[1]) * t)),
        min(255, int(base[2] + (255 - base[2]) * t)),
    )


def _smoothstep(t: float) -> float:
    """Easing suave cubico (Ken Perlin): 3t^2 - 2t^3, t em [0, 1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _ease_out_quad(t: float) -> float:
    """Ease-out quadratico: desacelera ao final."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 2


def _make_white_sprite(surface: pygame.Surface) -> pygame.Surface:
    """Gera uma versão totalmente branca do sprite para flash de dano."""
    white = surface.copy()
    white.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
    return white


# ---------------------------------------------------------------------------
# Sistema de particulas de poeira
# ---------------------------------------------------------------------------


class _SerpentDustParticle:
    """Particula de poeira emitida pelos blocos de pedra."""

    __slots__ = ("x", "y", "vx", "vy", "size", "life", "max_life")

    # Constantes de simulacao
    _VX_RANGE: Final = (-16.0, 16.0)  # px/s
    _VY_RANGE: Final = (44.0, 82.0)  # px/s (positivo = cai)
    _GRAVITY: Final = 78.0  # px/s^2
    _LIFE_RANGE: Final = (0.55, 1.0)  # segundos
    _SIZE_RANGE: Final = (2, 4)  # pixels

    # Cor base da poeira de pedra (RGB)
    _BASE_COLOR: Final[_RGB] = (148, 122, 96)

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(*self._VX_RANGE)
        self.vy = random.uniform(*self._VY_RANGE)
        self.size = random.randint(*self._SIZE_RANGE)
        self.max_life = random.uniform(*self._LIFE_RANGE)
        self.life = self.max_life

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self._GRAVITY * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        fade = max(0.0, self.life / self.max_life)
        r, g, b = self._BASE_COLOR
        color: _RGB = (int(r * fade), int(g * fade), int(b * fade))
        pygame.draw.rect(
            surface, color, (int(self.x), int(self.y), self.size, self.size)
        )


# ---------------------------------------------------------------------------
# Bloco de pedra lateral - entidade inimiga independente
# ---------------------------------------------------------------------------


class SerpentBlock:
    """Bloco de pedra fixo nas laterais da tela."""

    __slots__ = (
        # Posicao e geometria
        "x",
        "y",
        "w",
        "h",
        "cx",
        "cy",
        # Identidade
        "side",
        "boss",
        "row_index",
        "is_fragment",
        # Estado de combate
        "health",
        "dead",
        "_hit_flash",
        "emp_linger_timer",
        # Posicao de origem (loop continuo)
        "origin_cx",
        "_origin_cy",
        # Colisao
        "_rect",
        # Visual
        "_rotation_angle",
        "_rotation_dir",
        "_sprite_frame",
        "_frame_index",
        # Particulas
        "_particles",
        "_particle_timer",
        # Animacao de troca de coluna
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
        # Animacao de entrada (legado - mantido por compatibilidade)
        "_entry_anim_active",
        "_entry_anim_timer",
        "_entry_anim_duration",
        # Movimento de fragmento
        "_ascent_speed",
    )

    # ------------------------------------------------------------------
    # Constantes de gameplay
    # ------------------------------------------------------------------
    RADIUS: Final[int] = 78  # px - raio do bloco circular
    MAX_HEALTH: Final[int] = 20  # pontos de vida por bloco
    POINTS_VALUE: Final[int] = 80  # pontos concedidos ao jogador na destruicao

    # Intervalo de emissao de particulas (segundos)
    _PARTICLE_INTERVAL_MIN: Final = 0.08
    _PARTICLE_INTERVAL_MAX: Final = 0.18
    _PARTICLE_SPAWN_RADIUS: Final = 14.0  # variacao horizontal do ponto de spawn
    _PARTICLE_SPAWN_Y_BIAS: Final = 0.35  # fracao do RADIUS abaixo do centro

    # Cores (constantes de classe - nunca recriadas por frame)
    _COLOR_BODY: Final[_RGB] = (106, 76, 125)
    _COLOR_EDGE: Final[_RGB] = (42, 24, 55)
    _COLOR_HIGHLIGHT: Final[_RGB] = (224, 126, 116)
    _COLOR_HP_HIGH: Final[_RGB] = (80, 220, 80)
    _COLOR_HP_MID: Final[_RGB] = (220, 160, 40)
    _COLOR_HP_LOW: Final[_RGB] = (220, 60, 60)

    # Cache de frames compartilhado entre instancias (carregado uma vez)
    _animation_frames: Optional[List[pygame.Surface]] = None
    _white_animation_frames: Optional[List[pygame.Surface]] = None
    _rotation_cache: dict[tuple[int, int, bool], pygame.Surface] = {}

    # ------------------------------------------------------------------
    # Inicializacao
    # ------------------------------------------------------------------

    def __init__(
        self,
        x: float,
        y: float,
        side: Side,
        boss: "MountainSerpentBoss",
        row_index: int,
        is_fragment: bool = False,
        ascent_speed: float = 0.0,
    ) -> None:
        diameter = self.RADIUS * 2
        self.w = diameter
        self.h = diameter
        self.cx = x
        self.cy = y
        self.x = x - self.RADIUS
        self.y = y - self.RADIUS
        self.side: Side = side
        self.boss = boss
        self.row_index = row_index
        self.is_fragment = is_fragment
        self._ascent_speed = ascent_speed

        self.health: int = self.MAX_HEALTH
        self.dead: bool = False
        self._hit_flash: float = 0.0
        self.emp_linger_timer: float = 0.0

        self.origin_cx: float = x
        self._origin_cy: float = y

        self._rotation_angle: float = random.uniform(0.0, 360.0)
        self._rotation_dir: float = random.choice((-1.0, 1.0))

        self._particles: List[_SerpentDustParticle] = []
        self._particle_timer: float = random.uniform(0.05, 0.22)

        # Semente deterministica por bloco para shakes independentes
        self._swap_seed: float = (row_index + (0.0 if side == "left" else 0.5)) * 11.0
        self._reset_swap_state()

        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame: Optional[pygame.Surface] = (
            random.choice(sprite_frames) if sprite_frames else None
        )
        self._frame_index = (
            sprite_frames.index(self._sprite_frame) if self._sprite_frame else 0
        )

        # Rect de colisao calculado uma unica vez (atualizado in-place)
        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Campos de entrada animada (legado - mantidos para compatibilidade de API)
        self._entry_anim_active: bool = False
        self._entry_anim_timer: float = 0.0
        self._entry_anim_duration: float = 0.0

    def _get_rotated_surface(
        self, surface: pygame.Surface, angle: float, is_white: bool = False
    ) -> pygame.Surface:
        """Retorna uma surface rotacionada do cache, com quantização de 5 graus."""
        q_angle = (int(angle) // 5) * 5 % 360
        key = (self._frame_index, q_angle, is_white)
        if key not in self._rotation_cache:
            self._rotation_cache[key] = pygame.transform.rotate(surface, q_angle)
        return self._rotation_cache[key]

    def _reset_swap_state(self) -> None:
        """Zera todos os campos de troca de coluna para o estado padrao."""
        self._swap_active = False
        self._swap_wait_timer = 0.0
        self._swap_elapsed = 0.0
        self._swap_duration = 0.0
        self._swap_shake_duration = 0.0
        self._swap_start_cx = self.cx
        self._swap_start_cy = self.cy
        self._swap_target_cx = self.cx
        self._swap_target_cy = self.cy
        self._swap_target_side: Side = self.side
        self._swap_arc_dir = 0.0

    # ------------------------------------------------------------------
    # Carregamento de assets (cache por classe)
    # ------------------------------------------------------------------

    @classmethod
    def _load_animation_frames(
        cls, target_w: int, target_h: int
    ) -> List[pygame.Surface]:
        if cls._animation_frames is not None:
            return cls._animation_frames

        sprites_dir = (
            BASE_DIR
            / "assets"
            / "images"
            / "Sprites_Boss_Cobra"
            / "Serpent_Block-Sprites"
        )
        frames: List[pygame.Surface] = []
        if sprites_dir.exists():
            for path in sorted(sprites_dir.glob("*.png")):
                image = get_image(path)
                if image.get_size() != (target_w, target_h):
                    image = pygame.transform.scale(image, (target_w, target_h))
                frames.append(image)

        cls._animation_frames = frames
        cls._white_animation_frames = [_make_white_sprite(f) for f in frames]
        return frames

    @classmethod
    def load_frames_for_preload(cls) -> List[pygame.Surface]:
        """Pre-carrega os frames para uso antes da criacao de instancias."""
        return cls._load_animation_frames(cls.RADIUS * 2, cls.RADIUS * 2)

    # ------------------------------------------------------------------
    # Protocolo de entidade inimiga
    # ------------------------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def origin_cy(self) -> float:
        """Posicao Y de origem no loop continuo."""
        return self._origin_cy

    @origin_cy.setter
    def origin_cy(self, value: float) -> None:
        self._origin_cy = value

    @property
    def swap_active(self) -> bool:
        """True enquanto a animacao de troca de coluna estiver em andamento."""
        return self._swap_active

    def get_points_value(self) -> int:
        return self.POINTS_VALUE

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health = max(0, self.health - amount)
        self._hit_flash = 0.1
        if self.health == 0:
            self.dead = True
            # Apenas blocos da corrente principal notificam o boss
            if not self.is_fragment:
                self.boss.on_block_killed(self.side, self)

    # ------------------------------------------------------------------
    # Revive / Re-entrada
    # ------------------------------------------------------------------

    def revive(self) -> None:
        """Restaura o bloco ao estado inicial (HP, visual, swap)."""
        self.health = self.MAX_HEALTH
        self.dead = False
        self._hit_flash = 0.0
        self._rotation_angle = random.uniform(0.0, 360.0)
        self._rotation_dir = random.choice((-1.0, 1.0))
        sprite_frames = self._load_animation_frames(self.w, self.h)
        self._sprite_frame = random.choice(sprite_frames) if sprite_frames else None
        self._frame_index = (
            sprite_frames.index(self._sprite_frame) if self._sprite_frame else 0
        )
        self._particles.clear()
        self._reset_swap_state()

    def revive_with_entry(self) -> None:
        """Revive o bloco reposicionado fora da tela e acelera o loop do boss."""
        self.revive()
        # Cada bloco entra escalonado pelo row_index para nao empilhar todos no mesmo ponto.
        # Coluna esquerda sobe (entra por baixo), direita desce (entra por cima).
        spacing = self.boss.block_spacing
        if self.side == "left":
            self._origin_cy = (
                Config.SCREEN_HEIGHT + self.RADIUS + self.row_index * spacing
            )
        else:
            self._origin_cy = -self.RADIUS - self.row_index * spacing
        # Arranque de velocidade para re-entrada visualmente dramatica
        self.boss.loop_speed_multiplier = max(self.boss.loop_speed_multiplier, 12.0)

    # ------------------------------------------------------------------
    # Troca de coluna (swap)
    # ------------------------------------------------------------------

    def start_column_swap(
        self,
        target_cx: float,
        target_cy: float,
        target_side: Side,
        row_delay: float,
        arc_dir: float,
        swap_duration: float,
        shake_duration: float,
    ) -> None:
        """Inicia a animacao de troca de posicao entre colunas."""
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

        wave_time = self.boss.block_wave_time

        if self._swap_wait_timer > 0.0:
            self._swap_wait_timer = max(0.0, self._swap_wait_timer - dt)
            tremble = 1.0 - min(
                1.0, self._swap_wait_timer / max(0.001, self._swap_duration)
            )
            shake_x = math.sin(wave_time * 38.0 + self._swap_seed) * 4.0 * tremble
            shake_y = math.cos(wave_time * 44.0 + self._swap_seed * 1.3) * 2.5 * tremble
            self.cx = self._swap_start_cx + shake_x
            self.cy = self._swap_start_cy + shake_y
        else:
            self._swap_elapsed += dt
            if self._swap_elapsed <= self._swap_shake_duration:
                self._apply_pre_move_shake()
            else:
                self._apply_arc_movement()

        self._sync_rect_from_center()

    def _apply_pre_move_shake(self) -> None:
        """Tremor que antecede o movimento principal do swap."""
        shake_dur = max(0.001, self._swap_shake_duration)
        tremble = 1.0 - (self._swap_elapsed / shake_dur)
        shake_x = math.sin(self._swap_elapsed * 52.0 + self._swap_seed) * 5.5 * tremble
        shake_y = (
            math.cos(self._swap_elapsed * 60.0 + self._swap_seed * 1.4) * 3.5 * tremble
        )
        self.cx = self._swap_start_cx + shake_x
        self.cy = self._swap_start_cy + shake_y

    def _apply_arc_movement(self) -> None:
        """Movimento suavizado em arco da posicao de origem ate o destino."""
        move_dur = max(0.001, self._swap_duration - self._swap_shake_duration)
        raw_t = (self._swap_elapsed - self._swap_shake_duration) / move_dur
        t = _smoothstep(raw_t)

        self.cx = self._swap_start_cx + (self._swap_target_cx - self._swap_start_cx) * t
        self.cy = self._swap_start_cy + (self._swap_target_cy - self._swap_start_cy) * t
        self.cy += (
            math.sin(t * math.pi)
            * self.boss.BLOCK_SWAP_ARC_AMPLITUDE
            * self._swap_arc_dir
        )

        if raw_t >= 1.0:
            self._finalize_swap()

    def _finalize_swap(self) -> None:
        """Confirma a troca: atualiza lado, origem e encerra a animacao."""
        self._swap_active = False
        self.side = self._swap_target_side
        self.origin_cx = self._swap_target_cx
        self._origin_cy = self._swap_target_cy
        self.cx = self._swap_target_cx
        self.cy = self._swap_target_cy

    def _sync_rect_from_center(self) -> None:
        """Recalcula x, y e atualiza o rect de colisao in-place."""
        self.x = self.cx - self.RADIUS
        self.y = self.cy - self.RADIUS
        self._rect.x = int(self.x)
        self._rect.y = int(self.y)

    # ------------------------------------------------------------------
    # Particulas
    # ------------------------------------------------------------------

    def _spawn_particle(self) -> None:
        spawn_x = self.cx + random.uniform(
            -self._PARTICLE_SPAWN_RADIUS, self._PARTICLE_SPAWN_RADIUS
        )
        spawn_y = self.cy + self.RADIUS * self._PARTICLE_SPAWN_Y_BIAS
        self._particles.append(_SerpentDustParticle(spawn_x, spawn_y))

    # ------------------------------------------------------------------
    # Loop de jogo
    # ------------------------------------------------------------------

    def update(self, dt: float, *_args: object, **_kwargs: object) -> None:
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._rotation_angle = (
            self._rotation_angle
            + self.boss.BLOCK_ROTATION_SPEED * dt * self._rotation_dir
        ) % 360.0

        # Particulas: emissao periodica + atualizacao in-place reversa (otimizado)
        self._particle_timer -= dt
        if self._particle_timer <= 0.0:
            self._spawn_particle()
            self._particle_timer = random.uniform(
                self._PARTICLE_INTERVAL_MIN, self._PARTICLE_INTERVAL_MAX
            )

        for i in range(len(self._particles) - 1, -1, -1):
            p = self._particles[i]
            p.update(dt)
            if p.dead:
                self._particles.pop(i)

        # Movimento de fragmento (invocado na vulnerabilidade)
        if self.is_fragment:
            self.cy -= self._ascent_speed * dt
            self._sync_rect_from_center()
            if self.cy < -self.RADIUS:
                self.dead = True
            return

        # Movimento: loop continuo ou swap ou estatico
        if self.boss.loop_movement_enabled and not self._swap_active:
            self._apply_loop_movement(dt)
            wave_x, wave_y = self.boss.get_block_wave_offset(self.row_index, self.side)
            self.cx = self.origin_cx + wave_x
            self.cy = self._origin_cy + wave_y
        elif self._swap_active:
            self._update_column_swap(dt)
        else:
            wave_x, wave_y = self.boss.get_block_wave_offset(self.row_index, self.side)
            self.cx = self.origin_cx + wave_x
            self.cy = self._origin_cy + wave_y

        self._sync_rect_from_center()

    def _apply_loop_movement(self, dt: float) -> None:
        """Avanca a posicao de origem na corrente infinita (wrap-around)."""
        speed = self.boss.loop_speed * self.boss.loop_speed_multiplier
        total_area = self.boss.BLOCK_COUNT * self.boss.block_spacing

        if self.side == "left":
            self._origin_cy -= speed * dt
            if self._origin_cy < -self.RADIUS:
                self._origin_cy += total_area
        else:
            self._origin_cy += speed * dt
            if self._origin_cy > Config.SCREEN_HEIGHT + self.RADIUS:
                self._origin_cy -= total_area

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        for particle in self._particles:
            particle.draw(surface)

        cx, cy = int(self.cx), int(self.cy)
        r = self.RADIUS

        if self._sprite_frame is not None:
            self._draw_sprite(surface, cx, cy)
        else:
            self._draw_fallback_circle(surface, cx, cy, r)

        self._draw_health_bar(surface, cx, cy, r)

    def _draw_sprite(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        if self._sprite_frame is None:
            return

        # Otimizado: usa cache de rotação e sprite branco se estiver em flash
        if self._hit_flash > 0.0 and self._white_animation_frames:
            white_sprite = self._white_animation_frames[self._frame_index]
            rotated = self._get_rotated_surface(
                white_sprite, self._rotation_angle, is_white=True
            )
        else:
            rotated = self._get_rotated_surface(
                self._sprite_frame, self._rotation_angle, is_white=False
            )

        dest = rotated.get_rect(center=(cx, cy))
        surface.blit(rotated, dest.topleft)

    def _draw_fallback_circle(
        self, surface: pygame.Surface, cx: int, cy: int, r: int
    ) -> None:
        body_color = (
            _lerp_color(self._COLOR_BODY, self._hit_flash)
            if self._hit_flash > 0.0
            else self._COLOR_BODY
        )
        pygame.draw.circle(surface, self._COLOR_EDGE, (cx, cy), r + 3)
        pygame.draw.circle(surface, body_color, (cx, cy), r)
        pygame.draw.circle(surface, self._COLOR_HIGHLIGHT, (cx, cy), r // 2)

    def _draw_health_bar(
        self, surface: pygame.Surface, cx: int, cy: int, r: int
    ) -> None:
        bar_w = r * 2
        bar_h = 4
        bar_x = cx - r
        bar_y = cy - r - 8
        ratio = self.health / self.MAX_HEALTH
        life_w = max(0, int(bar_w * ratio))
        bar_color = (
            self._COLOR_HP_HIGH
            if ratio > 0.5
            else self._COLOR_HP_MID if ratio > 0.25 else self._COLOR_HP_LOW
        )
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(surface, bar_color, (bar_x, bar_y, life_w, bar_h))


# ---------------------------------------------------------------------------
# Projétil temático: Bola de Rocha
# ---------------------------------------------------------------------------


class SerpentRockBullet:
    """Projétil que usa os sprites do SerpentBlock, mas em tamanho reduzido."""

    __slots__ = (
        "x",
        "y",
        "vx",
        "vy",
        "radius",
        "angle",
        "rot_speed",
        "dead",
        "_rect",
        "_sprite",
        "_afterimages",
        "_trail_timer",
        "_frame_index",
    )

    # Cache para os sprites redimensionados
    _animation_frames: Optional[List[pygame.Surface]] = None
    _rotation_cache: dict[tuple[int, int], pygame.Surface] = {}
    _TRAIL_INTERVAL: Final = 0.04  # Segundos entre cada "fantasma"
    _TRAIL_LIFETIME: Final = 0.3  # Duração de cada fantasma

    def __init__(self, x: float, y: float, vx: float, vy: float) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = 11
        self.angle = random.uniform(0, 360)
        self.rot_speed = random.uniform(180, 480) * random.choice([-1, 1])
        self.dead = False
        self._afterimages: List[_BulletAfterImage] = []
        self._trail_timer = 0.0

        # Carrega os sprites se ainda não foram carregados
        if SerpentRockBullet._animation_frames is None:
            SerpentRockBullet._load_frames()

        # Escolhe um sprite aleatório do set do SerpentBlock
        self._sprite = (
            random.choice(SerpentRockBullet._animation_frames)
            if SerpentRockBullet._animation_frames
            else None
        )
        self._frame_index = (
            SerpentRockBullet._animation_frames.index(self._sprite)
            if (self._sprite and SerpentRockBullet._animation_frames)
            else 0
        )

        self._rect = pygame.Rect(
            int(x - self.radius), int(y - self.radius), self.radius * 2, self.radius * 2
        )

    def _get_rotated_surface(
        self, surface: pygame.Surface, angle: float
    ) -> pygame.Surface:
        """Retorna uma surface rotacionada do cache, com quantização de 10 graus para balas."""
        q_angle = (int(angle) // 10) * 10 % 360
        key = (self._frame_index, q_angle)
        if key not in self._rotation_cache:
            self._rotation_cache[key] = pygame.transform.rotate(surface, q_angle)
        return self._rotation_cache[key]

    @classmethod
    def _load_frames(cls) -> None:
        """Carrega e redimensiona os mesmos sprites usados pelo SerpentBlock."""
        sprites_dir = (
            BASE_DIR
            / "assets"
            / "images"
            / "Sprites_Boss_Cobra"
            / "Serpent_Block-Sprites"
        )
        frames: List[pygame.Surface] = []
        target_size = (22, 22)  # Diâmetro da bala (radius * 2)

        if sprites_dir.exists():
            for path in sorted(sprites_dir.glob("*.png")):
                image = get_image(path)
                if image.get_size() != target_size:
                    image = pygame.transform.scale(image, target_size)
                frames.append(image)

        cls._animation_frames = frames

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.rot_speed * dt
        self._rect.x = int(self.x - self.radius)
        self._rect.y = int(self.y - self.radius)

        # Atualiza o rastro fantasmagórico (in-place reversa)
        for i in range(len(self._afterimages) - 1, -1, -1):
            img = self._afterimages[i]
            img["life"] -= dt
            if img["life"] <= 0:
                self._afterimages.pop(i)

        self._trail_timer -= dt
        if self._trail_timer <= 0:
            self._afterimages.append(
                {
                    "x": self.x,
                    "y": self.y,
                    "angle": self.angle,
                    "life": self._TRAIL_LIFETIME,
                }
            )
            self._trail_timer = self._TRAIL_INTERVAL

        if (
            self.y > Config.SCREEN_HEIGHT + 100
            or self.y < -100
            or self.x < -100
            or self.x > Config.SCREEN_WIDTH + 100
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if not self._sprite:
            return

        # Otimizado: usa cache de rotação e set_alpha() sem copy()
        for img in self._afterimages:
            alpha = int((img["life"] / self._TRAIL_LIFETIME) * 128)
            rotated = self._get_rotated_surface(self._sprite, img["angle"])

            old_alpha = rotated.get_alpha()
            rotated.set_alpha(alpha)
            dest = rotated.get_rect(center=(int(img["x"]), int(img["y"])))
            surface.blit(rotated, dest.topleft)
            rotated.set_alpha(old_alpha)

        # Desenha a pedra principal
        rotated = self._get_rotated_surface(self._sprite, self.angle)
        dest = rotated.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(rotated, dest.topleft)


# ---------------------------------------------------------------------------
# Boss - cabeca movel
# ---------------------------------------------------------------------------


class MountainSerpentBoss:
    """Cabeca da Serpente de Pedra (boss das Cordilheiras).

    Responsabilidades:
      * Mover a cabeca de lado a lado.
      * Receber dano SOMENTE durante a janela de vulnerabilidade
        (todos os blocos destruidos).
      * Gerenciar o ciclo de respawn de blocos e o padrao de troca de colunas.
      * Renderizar a cabeca animada e a barra de HP.
    """

    # ------------------------------------------------------------------
    # Constantes de gameplay
    # ------------------------------------------------------------------

    HEAD_RADIUS: Final[int] = 45  # px
    SIDE_MARGIN: Final[int] = 52  # px - distancia da borda lateral
    HEAD_Y: Final[int] = 88  # px - posicao vertical em repouso
    HEAD_SPEED: Final[float] = 24.0  # px/s - velocidade horizontal
    HEAD_PIXEL_SCALE: Final[int] = 4  # escala do sprite pixel-art
    HEAD_FRAME_REPEAT: Final[int] = 2  # quantas vezes cada frame e repetido
    HEAD_ANIM_SLOW_FACTOR: Final[float] = 1.25  # multiplicador global da animacao

    DEFAULT_HEALTH: Final[int] = 1200  # HP inicial do boss

    # Ataques - fase 1 (cuspida simples)
    ATTACK_SPIT_COOLDOWN: Final[float] = 4.0  # s entre cuspidas
    SPIT_SPEED: Final[float] = 220.0  # px/s

    # Ataques - fase 2 (sopro em leque)
    ATTACK_BREATH_COOLDOWN: Final[float] = 3.8  # s entre sopros (era 1.8)
    BREATH_BULLET_COUNT: Final[int] = 5  # projeteis por sopro
    BREATH_SPREAD_ANGLE: Final[float] = math.radians(45.0)  # angulo total do leque
    BREATH_SPEED: Final[float] = 130.0  # px/s

    # Fase de furia (HP < 30%)
    FURY_ATTACK_COOLDOWN: Final[float] = 2.8  # s entre ataques (era 1.8)
    FURY_RESPAWN_DELAY: Final[float] = 8.0  # s para respawn dos blocos

    # Vulnerabilidade (janela de dano)
    VULNERABLE_HEAD_SPEED_MOD: Final[float] = 2.8  # multiplicador de velocidade
    VULNERABLE_BLOCK_SPAWN_COOLDOWN: Final[tuple[float, float]] = (
        0.6,
        1.4,
    )  # s entre invocações
    VULNERABLE_BLOCK_ASCENT_SPEED: Final[tuple[float, float]] = (120.0, 180.0)  # px/s

    # Blocos laterais
    BLOCK_COUNT: Final[int] = 5  # blocos por coluna
    RESPAWN_DELAY: Final[float] = 15.0
    BLOCK_INDIVIDUAL_RESPAWN_DELAY: Final[float] = 65.0  # s - respawn individual

    # Movimento ondulatorio dos blocos
    BLOCK_WAVE_AMPLITUDE_X: Final[float] = 16.0  # px
    BLOCK_WAVE_AMPLITUDE_Y: Final[float] = 9.0  # px
    BLOCK_WAVE_SPEED: Final[float] = 1.9  # rad/s
    BLOCK_WAVE_PHASE_STEP: Final[float] = 0.85  # rad por linha (cria ondulacao)
    BLOCK_SIDE_PHASE_SHIFT: Final[float] = 1.6  # defasagem entre colunas
    BLOCK_ROTATION_SPEED: Final[float] = 95.0  # graus/s

    # Troca de colunas
    BLOCK_SWAP_DURATION: Final[float] = 2.5  # s - duracao total do swap
    BLOCK_SWAP_SHAKE_DURATION: Final[float] = 1.5  # s - fase de tremor
    BLOCK_SWAP_ARC_AMPLITUDE: Final[float] = 75.0  # px - altura do arco
    BLOCK_SWAP_INTERVAL_MIN: Final[float] = 8.0  # s entre swaps
    BLOCK_SWAP_INTERVAL_MAX: Final[float] = 10.0  # s entre swaps
    BLOCK_SWAP_MIN_ROWS: Final[int] = 1
    BLOCK_SWAP_MAX_ROWS: Final[int] = 1
    BLOCK_SWAP_ROW_STAGGER: Final[float] = 0.14  # s de atraso entre linhas

    # Tremor da cabeca (sob pressao ou dano)
    HEAD_STRAIN_SHAKE_X: Final[float] = 6.0
    HEAD_STRAIN_SHAKE_Y: Final[float] = 2.5
    HEAD_STRAIN_SHAKE_FREQ_X: Final[float] = 46.0  # Hz
    HEAD_STRAIN_SHAKE_FREQ_Y: Final[float] = 61.0  # Hz
    HEAD_PAIN_SHAKE_DURATION: Final[float] = 0.9  # s

    # Cores
    _COLOR_BODY: Final[_RGB] = (106, 76, 125)
    _COLOR_EDGE: Final[_RGB] = (42, 24, 55)
    _COLOR_GLOW: Final[_RGB] = (255, 205, 125)

    # Cache de frames (compartilhado entre instancias)
    _animation_frames: Optional[List[pygame.Surface]] = None
    _white_animation_frames: Optional[List[pygame.Surface]] = None
    _spit_sprite: Optional[pygame.Surface] = None
    _white_spit_sprite: Optional[pygame.Surface] = None
    _pain_sprite: Optional[pygame.Surface] = None
    _white_pain_sprite: Optional[pygame.Surface] = None

    # ------------------------------------------------------------------
    # Inicializacao
    # ------------------------------------------------------------------

    def __init__(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        health: Optional[int] = None,
    ) -> None:
        self._final_head_y = float(y if y is not None else self.HEAD_Y)

        # Posicao e movimento da cabeca
        self.head_x = float(x if x is not None else Config.SCREEN_WIDTH / 2)
        self.head_y = -200.0  # Comeca acima da tela (animacao de entrada)
        self.direction: int = random.choice((-1, 1))
        self.speed = self.HEAD_SPEED
        self.left_x = float(self.SIDE_MARGIN)
        self.right_x = float(Config.SCREEN_WIDTH - self.SIDE_MARGIN)

        # Estado de combate
        self.health = health if health is not None else self.DEFAULT_HEALTH
        self.max_health = self.health
        self.dead = False
        self._hit_flash = 0.0
        self.emp_linger_timer = 0.0
        self._attack_timer = self.ATTACK_SPIT_COOLDOWN * 0.75
        self._phase = 1
        self._head_pain_timer = 0.0
        self._spit_anim_timer = 0.0
        self._pending_shards: List[SerpentRockBullet] = []

        # Blocos laterais
        self._all_blocks: List[SerpentBlock] = []
        self._block_map: dict[tuple[Side, int], SerpentBlock] = {}
        self._left_alive = 0
        self._right_alive = 0
        self._respawn_timer = -1.0
        self.is_vulnerable = False
        self._dead_block_respawn_timers: dict[SerpentBlock, float] = {}

        # Movimento ondulatorio
        self._block_wave_time = random.uniform(0.0, math.tau)

        # Loop continuo dos blocos
        self._loop_movement_enabled = True
        self._loop_speed = 45.0
        self._loop_speed_multiplier = 25.0
        self._block_spacing = 0.0

        # Padrao de troca de colunas
        self._swap_pattern_enabled = False
        self._swap_cycle_timer = 0.0
        self._swap_event_active = False
        self._swap_event_rows: set[int] = set()

        # Rastro fantasmagorico (Alucard)
        self._head_afterimages: List[_AfterImage] = []
        self._head_trail_timer = 0.0

        # Timer para spawn de blocos na vulnerabilidade
        self._vulnerable_block_timer = 0.0
        self._phase2_sentry_spawned = False
        self._phase3_sentry_spawned = False
        self._head_intro_active = True
        self._head_intro_progress = 0.0

        # Bounds de compatibilidade (imutaveis, calculados uma vez)
        self.x = self.left_x - SerpentBlock.RADIUS
        self.y = self.head_y - self.HEAD_RADIUS
        self.w = (self.right_x + SerpentBlock.RADIUS) - self.x
        self.h = float(self.HEAD_RADIUS * 2)

        # Animacao da cabeca
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

        # Rect da cabeca atualizado in-place (sem realocar por frame)
        self._head_rect = pygame.Rect(
            int(self.head_x - self._head_half_w),
            int(self.head_y - self._head_half_h),
            self._head_sprite.get_width(),
            self._head_sprite.get_height(),
        )

    # ------------------------------------------------------------------
    # Carregamento de assets
    # ------------------------------------------------------------------

    @classmethod
    def load_frames_for_preload(cls) -> List[pygame.Surface]:
        """Pre-carrega os frames antes da criacao de instancias."""
        return cls._load_head_animation_frames()

    @classmethod
    def _load_head_animation_frames(cls) -> List[pygame.Surface]:
        if cls._animation_frames is not None:
            return cls._animation_frames

        sprites_dir = BASE_DIR / "assets" / "images" / "Sprites_Boss_Cobra"
        target_size = (
            cls.HEAD_PIXEL_SCALE * _PIXEL_COLS,
            cls.HEAD_PIXEL_SCALE * _PIXEL_ROWS,
        )
        frames: List[pygame.Surface] = []
        white_frames: List[pygame.Surface] = []

        if sprites_dir.exists():
            # Carrega frames de animação idle (exclui os novos sprites especiais)
            for path in sorted(sprites_dir.glob("*.png")):
                if "Cuspindo" in path.name or "Dano" in path.name:
                    continue
                image = get_image(path)
                if image.get_size() != target_size:
                    image = pygame.transform.scale(image, target_size)
                frames.append(image)
                white_frames.append(_make_white_sprite(image))

            # Carrega sprites especiais
            spit_path = sprites_dir / "Animação_Cobra_Cuspindo a pedra.png"
            if spit_path.exists():
                cls._spit_sprite = pygame.transform.scale(
                    get_image(spit_path), target_size
                )
                cls._white_spit_sprite = _make_white_sprite(cls._spit_sprite)

            pain_path = sprites_dir / "Animação_Cobra_Levando_Dano.png"
            if pain_path.exists():
                cls._pain_sprite = pygame.transform.scale(
                    get_image(pain_path), target_size
                )
                cls._white_pain_sprite = _make_white_sprite(cls._pain_sprite)

        cls._animation_frames = frames
        cls._white_animation_frames = white_frames
        return frames

    @staticmethod
    def _build_ping_pong_sequence(frame_count: int, repeat_each: int = 1) -> List[int]:
        """Gera sequencia ping-pong: 0 -> N -> 0, com cada indice repetido N vezes."""
        if frame_count <= 1:
            return [0]
        forward = list(range(frame_count))
        backward = list(range(frame_count - 2, 0, -1))
        repeat = max(1, repeat_each)
        return [idx for idx in (forward + backward) for _ in range(repeat)]

    def _build_head_sprite(self) -> pygame.Surface:
        """Constroi o sprite da cabeca a partir do pixel map (fallback sem arquivo)."""
        scale = self.HEAD_PIXEL_SCALE
        sprite = pygame.Surface(
            (_PIXEL_COLS * scale, _PIXEL_ROWS * scale), pygame.SRCALPHA
        )
        for row_idx, row in enumerate(_PIXEL_MAP):
            for col_idx, key in enumerate(row):
                if key is None:
                    continue
                color = _PIX_COLORS.get(key)
                if color is None:
                    continue
                pygame.draw.rect(
                    sprite, color, (col_idx * scale, row_idx * scale, scale, scale)
                )
        return sprite

    # ------------------------------------------------------------------
    # Animacao da cabeca
    # ------------------------------------------------------------------

    def _get_animation_frame_duration(self, frame_idx: int) -> float:
        """Duracao de exibicao de um frame baseada no estado atual do boss."""
        if self._hit_flash > 0.0:
            base = 0.045
        elif self.is_vulnerable:
            base = 0.065
        else:
            base = 0.09
        base *= self.HEAD_ANIM_SLOW_FACTOR

        max_idx = len(self._head_frames) - 1
        edge_dist = min(frame_idx, max_idx - frame_idx)
        if edge_dist == 0:
            return base * 2.2  # Pausa nos frames extremos
        if edge_dist == 1:
            return base * 1.45
        return base

    def _update_head_animation(self, dt: float) -> None:
        if len(self._head_frames) <= 1:
            self._head_sprite = self._head_frames[0]
            return

        # Congela animacao durante swap (tensao visual)
        if self._swap_event_active:
            frame_idx = self._frame_sequence[self._animation_seq_pos]
            self._set_head_frame(frame_idx)
            return

        self._animation_timer += dt
        current_idx = self._frame_sequence[self._animation_seq_pos]

        # Otimização: chama a duração uma vez por iteração
        dur = self._get_animation_frame_duration(current_idx)
        while self._animation_timer >= dur:
            self._animation_timer -= dur
            self._animation_seq_pos = (self._animation_seq_pos + 1) % len(
                self._frame_sequence
            )
            current_idx = self._frame_sequence[self._animation_seq_pos]
            dur = self._get_animation_frame_duration(current_idx)

        self._set_head_frame(current_idx)

    def _set_head_frame(self, frame_idx: int) -> None:
        """Atualiza o sprite atual e recalcula dimensoes em cache."""
        self._head_sprite = self._head_frames[frame_idx]
        self._head_half_w = self._head_sprite.get_width() // 2
        self._head_half_h = self._head_sprite.get_height() // 2
        self._head_rect.width = self._head_sprite.get_width()
        self._head_rect.height = self._head_sprite.get_height()

    # ------------------------------------------------------------------
    # Fabrica de blocos
    # ------------------------------------------------------------------

    def create_blocks(self) -> List[SerpentBlock]:
        """Instancia os blocos fora da tela para a entrada vertical acelerada.

        Retorna a lista de blocos para ser adicionada ao EntityManager.
        """
        total_area = Config.SCREEN_HEIGHT + 2 * SerpentBlock.RADIUS
        gap_y = total_area / self.BLOCK_COUNT
        self._block_spacing = gap_y

        blocks: List[SerpentBlock] = []
        for i in range(self.BLOCK_COUNT):
            # Coluna esquerda: sobe (entra por baixo)
            left_cy = Config.SCREEN_HEIGHT + SerpentBlock.RADIUS + i * gap_y
            left = SerpentBlock(self.left_x, left_cy, "left", self, row_index=i)
            blocks.append(left)
            self._block_map[("left", i)] = left

            # Coluna direita: desce (entra por cima)
            right_cy = -SerpentBlock.RADIUS - i * gap_y
            right = SerpentBlock(self.right_x, right_cy, "right", self, row_index=i)
            blocks.append(right)
            self._block_map[("right", i)] = right

        self._all_blocks = blocks
        self._left_alive = self.BLOCK_COUNT
        self._right_alive = self.BLOCK_COUNT
        return blocks

    # ------------------------------------------------------------------
    # Callbacks dos blocos
    # ------------------------------------------------------------------

    def on_block_killed(self, side: Side, block: SerpentBlock) -> None:
        """Chamado por ``SerpentBlock.take_damage`` quando um bloco morre."""
        if self.dead:
            return

        self._dead_block_respawn_timers[block] = self.BLOCK_INDIVIDUAL_RESPAWN_DELAY
        self._head_pain_timer = self.HEAD_PAIN_SHAKE_DURATION

        # Atualiza contadores incrementais para performance
        if side == "left":
            self._left_alive -= 1
        else:
            self._right_alive -= 1

        # Ideia 2: Gerar estilhaços de pedra ao destruir um bloco
        num_shards = random.randint(3, 5)
        for _ in range(num_shards):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(100.0, 200.0)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            shard = SerpentRockBullet(block.cx, block.cy, vx, vy)
            self._pending_shards.append(shard)

        if self.all_blocks_dead and not self.is_vulnerable:
            self._dead_block_respawn_timers.clear()  # timers residuais nao devem interferir
            self.is_vulnerable = True
            self._respawn_timer = self._get_respawn_delay()
            self._loop_movement_enabled = False

    # ------------------------------------------------------------------
    # Respawn de blocos
    # ------------------------------------------------------------------

    def _get_respawn_delay(self) -> float:
        return (
            self.FURY_RESPAWN_DELAY
            if self.health / self.max_health < 0.30
            else self.RESPAWN_DELAY
        )

    def _update_dead_block_respawns(self, dt: float) -> None:
        if not self._dead_block_respawn_timers:
            return

        # Itera o dicionário diretamente e coleta keys para remoção (mais rápido)
        to_remove: list[SerpentBlock] = []
        for block, timer in self._dead_block_respawn_timers.items():
            new_timer = timer - dt
            if new_timer > 0.0:
                self._dead_block_respawn_timers[block] = new_timer
                continue

            to_remove.append(block)
            if not block.dead:
                continue

            # FIX: Calcula a posição de origem para alinhar com o ciclo da coluna atual
            anchor_block = next(
                (b for b in self._all_blocks if b.side == block.side and not b.dead),
                None,
            )
            total_area = self.BLOCK_COUNT * self.block_spacing

            if anchor_block:
                row_diff = block.row_index - anchor_block.row_index
                # Na esquerda, Y aumenta com o índice. Na direita, Y diminui com o índice.
                if block.side == "left":
                    new_y = anchor_block.origin_cy + (row_diff * self.block_spacing)
                else:
                    new_y = anchor_block.origin_cy - (row_diff * self.block_spacing)
                # Normaliza para dentro do loop infinito [-RADIUS, total_area - RADIUS]
                block.origin_cy = (
                    (new_y + SerpentBlock.RADIUS) % total_area
                ) - SerpentBlock.RADIUS
            else:
                # Se a coluna estava toda destruída, usamos o cálculo de entrada padrão
                if block.side == "left":
                    block.origin_cy = (
                        Config.SCREEN_HEIGHT
                        + SerpentBlock.RADIUS
                        + block.row_index * self.block_spacing
                    )
                else:
                    block.origin_cy = (
                        -SerpentBlock.RADIUS - block.row_index * self.block_spacing
                    )

            block.revive()
            # Atualiza contadores ao reviver bloco individualmente
            if block.side == "left":
                self._left_alive += 1
            else:
                self._right_alive += 1
            # Nota: encerramento da vulnerabilidade e responsabilidade exclusiva de
            # _respawn_all_blocks (via _respawn_timer), nao do timer individual.

        for b in to_remove:
            del self._dead_block_respawn_timers[b]  # type: ignore

    def _respawn_all_blocks(self) -> list[StoneSentry]:
        """Revive todos os blocos com arranque de velocidade (fim da janela de vulnerabilidade)."""
        self._dead_block_respawn_timers.clear()
        self.is_vulnerable = False
        self._respawn_timer = -1.0
        self._loop_movement_enabled = True
        self._loop_speed_multiplier = 18.0  # boost dramatico de re-entrada

        # Limpa estados de tremor e eventos pendentes
        self._head_pain_timer = 0.0
        self._swap_event_active = False
        self._swap_event_rows.clear()

        # Reseta contadores incrementais
        self._left_alive = self.BLOCK_COUNT
        self._right_alive = self.BLOCK_COUNT

        for block in self._all_blocks:
            block.revive()
            # Reset critico: garante que o bloco volte para sua coluna de origem correta
            block.origin_cx = self.left_x if block.side == "left" else self.right_x

            if block.side == "left":
                block.origin_cy = (
                    Config.SCREEN_HEIGHT
                    + SerpentBlock.RADIUS
                    + block.row_index * self._block_spacing
                )
            else:
                block.origin_cy = (
                    -SerpentBlock.RADIUS - block.row_index * self._block_spacing
                )

        if not self._swap_pattern_enabled:
            self._swap_pattern_enabled = True
        self._schedule_next_swap()

        # Invocação ÚNICA de StoneSentry ao finalizar a vulnerabilidade baseada na fase
        new_ents: list[StoneSentry] = []
        phase = self._current_phase()
        if phase == 2 and not self._phase2_sentry_spawned:
            new_ents.append(StoneSentry())
            self._phase2_sentry_spawned = True
        elif phase == 3 and not self._phase3_sentry_spawned:
            new_ents.append(StoneSentry())
            self._phase3_sentry_spawned = True
        return new_ents

    # ------------------------------------------------------------------
    # Padrao de troca de colunas
    # ------------------------------------------------------------------

    def _schedule_next_swap(self) -> None:
        self._swap_cycle_timer = random.uniform(
            self.BLOCK_SWAP_INTERVAL_MIN, self.BLOCK_SWAP_INTERVAL_MAX
        )

    def _get_row_pair(
        self, row_index: int
    ) -> tuple[Optional[SerpentBlock], Optional[SerpentBlock]]:
        """Retorna o par (esquerdo, direito) de um indice de linha via dicionario O(1)."""
        return (
            self._block_map.get(("left", row_index)),
            self._block_map.get(("right", row_index)),
        )

    def _start_periodic_column_swap(self) -> None:
        if self._swap_event_active or not self._swap_pattern_enabled:
            return

        valid_rows = [
            i
            for i in range(self.BLOCK_COUNT)
            if (lb := self._block_map.get(("left", i))) is not None
            and (rb := self._block_map.get(("right", i))) is not None
            and not lb.dead
            and not rb.dead
        ]

        if not valid_rows:
            self._schedule_next_swap()
            return

        self._loop_movement_enabled = False  # Pausa para organizar troca

        row_count = random.randint(
            min(self.BLOCK_SWAP_MIN_ROWS, len(valid_rows)),
            min(self.BLOCK_SWAP_MAX_ROWS, len(valid_rows)),
        )
        selected_rows = sorted(random.sample(valid_rows, row_count))
        started_rows: set[int] = set()

        for order, row_i in enumerate(selected_rows):
            left, right = self._get_row_pair(row_i)
            if left is None or right is None:
                continue
            delay = order * self.BLOCK_SWAP_ROW_STAGGER
            # Inicia o movimento, mas NÃO atualiza o mapa ainda (Issue 5)
            left.start_column_swap(
                target_cx=self.right_x,
                target_cy=right.origin_cy,
                target_side="right",
                row_delay=delay,
                arc_dir=-1.0,
                swap_duration=self.BLOCK_SWAP_DURATION,
                shake_duration=self.BLOCK_SWAP_SHAKE_DURATION,
            )
            right.start_column_swap(
                target_cx=self.left_x,
                target_cy=left.origin_cy,
                target_side="left",
                row_delay=delay,
                arc_dir=1.0,
                swap_duration=self.BLOCK_SWAP_DURATION,
                shake_duration=self.BLOCK_SWAP_SHAKE_DURATION,
            )
            started_rows.add(row_i)

        if not started_rows:
            self._loop_movement_enabled = True
            self._schedule_next_swap()
            return

        self._swap_event_active = True
        self._swap_event_rows = started_rows

    def _update_swap_cycle(self, dt: float) -> None:
        if not self._swap_pattern_enabled or not self._all_blocks:
            return

        if self._swap_event_active:
            # Issue 4: Verifica apenas blocos que não estão mortos
            swap_done = all(
                not block.swap_active
                for block in self._all_blocks
                if block.row_index in self._swap_event_rows and not block.dead
            )
            if swap_done:
                self._swap_event_active = False
                # Issue 5: A atualização do mapa ocorre apenas na confirmação do término
                for row_i in self._swap_event_rows:
                    left, right = self._get_row_pair(row_i)
                    if left and right:
                        self._block_map[("left", row_i)] = right
                        self._block_map[("right", row_i)] = left

                self._swap_event_rows.clear()
                self._schedule_next_swap()
                if not self.is_vulnerable:
                    self._loop_movement_enabled = True
                    self._loop_speed_multiplier = max(self._loop_speed_multiplier, 3.5)
            return

        # Não inicia troca se estiver vulnerável ou se os blocos ainda estiverem entrando (boost de velocidade)
        if self.is_vulnerable or self._loop_speed_multiplier > 1.1:
            return

        self._swap_cycle_timer = max(0.0, self._swap_cycle_timer - dt)
        if self._swap_cycle_timer <= 0.0:
            self._start_periodic_column_swap()

    # ------------------------------------------------------------------
    # Movimentacao e offset da cabeca
    # ------------------------------------------------------------------

    def get_block_wave_offset(self, row_index: int, side: Side) -> tuple[float, float]:
        """Retorna o deslocamento de onda (x, y) para um bloco na corrente."""
        row_phase = row_index * self.BLOCK_WAVE_PHASE_STEP
        side_phase = 0.0 if side == "left" else self.BLOCK_SIDE_PHASE_SHIFT
        phase = self._block_wave_time + row_phase + side_phase
        return (
            math.sin(phase) * self.BLOCK_WAVE_AMPLITUDE_X,
            math.sin(phase * 2.0) * self.BLOCK_WAVE_AMPLITUDE_Y,
        )

    def _compute_head_shake(self) -> tuple[float, float]:
        """Calcula o tremor atual da cabeca (fúria, swap ou dano)."""
        wave = self._block_wave_time

        # Tremor base de fúria (Fase 3 - HP < 30%)
        fury_x, fury_y = 0.0, 0.0
        if self._phase == 3:
            fury_x = math.sin(wave * 40.0) * 1.5
            fury_y = math.cos(wave * 35.0) * 1.0

        if self._swap_event_active:
            return (
                fury_x
                + math.sin(wave * self.HEAD_STRAIN_SHAKE_FREQ_X)
                * self.HEAD_STRAIN_SHAKE_X,
                fury_y
                + math.cos(wave * self.HEAD_STRAIN_SHAKE_FREQ_Y)
                * self.HEAD_STRAIN_SHAKE_Y,
            )
        if self._head_pain_timer > 0.0:
            intensity = 0.8 + 0.5 * (
                self._head_pain_timer / self.HEAD_PAIN_SHAKE_DURATION
            )
            return (
                fury_x
                + math.sin(wave * self.HEAD_STRAIN_SHAKE_FREQ_X)
                * self.HEAD_STRAIN_SHAKE_X
                * intensity,
                fury_y
                + math.cos(wave * self.HEAD_STRAIN_SHAKE_FREQ_Y)
                * self.HEAD_STRAIN_SHAKE_Y
                * intensity,
            )
        return fury_x, fury_y

    # ------------------------------------------------------------------
    # Fase do boss
    # ------------------------------------------------------------------

    def _current_phase(self) -> int:
        """Fase atual baseada em HP puro (progressão linear)."""
        hp_ratio = self.health / self.max_health
        if hp_ratio < 0.30:
            return 3
        if hp_ratio < 0.70:
            return 2
        return 1

    # ------------------------------------------------------------------
    # Ataques
    # ------------------------------------------------------------------

    def _cooldown_for_phase(self, phase: int) -> float:
        if phase == 3:
            return self.FURY_ATTACK_COOLDOWN
        if phase == 2:
            return self.ATTACK_BREATH_COOLDOWN
        return self.ATTACK_SPIT_COOLDOWN

    def _execute_attack(
        self, player_x: float, player_y: float
    ) -> List[SerpentRockBullet]:
        if self._phase >= 2:
            return self._create_breath(player_x, player_y)
        return [self._create_spit(player_x, player_y)]

    def _create_spit(self, player_x: float, player_y: float) -> SerpentRockBullet:
        dx = player_x - self.head_x
        dy = player_y - self.head_y
        dist = math.hypot(dx, dy)
        if dist > 0:
            vx = dx / dist * self.SPIT_SPEED
            vy = dy / dist * self.SPIT_SPEED
        else:
            vx, vy = 0.0, self.SPIT_SPEED
        bullet = SerpentRockBullet(self.head_x, self.head_y, vx, vy)
        return bullet

    def _create_breath(
        self, player_x: float, player_y: float
    ) -> List[SerpentRockBullet]:
        base_angle = math.atan2(player_y - self.head_y, player_x - self.head_x)
        count = self.BREATH_BULLET_COUNT
        if count <= 1:
            angles = [base_angle]
        else:
            step = self.BREATH_SPREAD_ANGLE / (count - 1)
            half = (count - 1) / 2
            angles = [base_angle + (i - half) * step for i in range(count)]

        bullets: List[SerpentRockBullet] = []
        for angle in angles:
            vx = math.cos(angle) * self.BREATH_SPEED
            vy = math.sin(angle) * self.BREATH_SPEED
            bullet = SerpentRockBullet(self.head_x, self.head_y, vx, vy)
            bullets.append(bullet)
        return bullets

    # ------------------------------------------------------------------
    # Protocolo de entidade inimiga
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> None:
        # FIX: O boss só recebe dano se a janela de vulnerabilidade estiver aberta
        if self.dead or not self.is_vulnerable:
            return
        self.health = max(0, self.health - amount)
        self._hit_flash = 0.1
        if self.health == 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 850

    @property
    def rect(self) -> pygame.Rect:
        """Rect preciso da cabeca - atualizado in-place em ``update()``."""
        return self._head_rect

    # ------------------------------------------------------------------
    # Propriedades publicas para acesso controlado pelos SerpentBlocks
    # ------------------------------------------------------------------

    @property
    def left_alive_count(self) -> int:
        """Otimizado: retorna o contador incremental."""
        return self._left_alive

    @property
    def right_alive_count(self) -> int:
        """Otimizado: retorna o contador incremental."""
        return self._right_alive

    @property
    def all_blocks_dead(self) -> bool:
        """Otimizado: verifica se ambos os contadores são zero."""
        return self._left_alive == 0 and self._right_alive == 0

    @property
    def block_wave_time(self) -> float:
        """Tempo acumulado da onda ondulante dos blocos."""
        return self._block_wave_time

    @property
    def loop_movement_enabled(self) -> bool:
        """True quando o movimento de loop continuo dos blocos esta ativo."""
        return self._loop_movement_enabled

    @property
    def loop_speed(self) -> float:
        """Velocidade base do loop continuo (px/s)."""
        return self._loop_speed

    @property
    def loop_speed_multiplier(self) -> float:
        """Multiplicador atual da velocidade de loop."""
        return self._loop_speed_multiplier

    @loop_speed_multiplier.setter
    def loop_speed_multiplier(self, value: float) -> None:
        self._loop_speed_multiplier = value

    @property
    def block_spacing(self) -> float:
        """Espacamento vertical entre blocos da corrente (px)."""
        return self._block_spacing

    # ------------------------------------------------------------------
    # Loop de jogo
    # ------------------------------------------------------------------

    def update(
        self, dt: float, player_x: float = 0.0, player_y: float = 0.0
    ) -> tuple[List[SerpentRockBullet], List[object]]:
        if self.dead:
            return [], []

        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._head_pain_timer = max(0.0, self._head_pain_timer - dt)
        self._spit_anim_timer = max(
            0.0, self._spit_anim_timer - dt
        )  # Decrementa timer de cuspida

        self._update_head_animation(dt)
        self._block_wave_time += dt * self.BLOCK_WAVE_SPEED
        self._update_dead_block_respawns(dt)

        current_speed = self.speed
        new_entities: List[object] = []

        if self._respawn_timer > 0:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                respawn_ents = self._respawn_all_blocks()
                new_entities.extend(respawn_ents)

        self._update_swap_cycle(dt)

        # Desacelera o loop gradualmente ate a velocidade nominal
        if self._loop_speed_multiplier > 1.0:
            self._loop_speed_multiplier = max(
                1.0, self._loop_speed_multiplier - dt * 6.5
            )

        self._phase = self._current_phase()

        # Spawn de StoneSentry e tratado exclusivamente em _respawn_all_blocks,
        # garantindo exatamente um por vulnerabilidade encerrada (fases 2 e 3).

        if self._head_intro_active:
            if self._loop_speed_multiplier <= 1.0:
                self._head_intro_progress = min(
                    1.0, self._head_intro_progress + dt * 1.5
                )
                eased = _ease_out_quad(self._head_intro_progress)
                self.head_y = -200.0 + (self._final_head_y + 200.0) * eased
                if self._head_intro_progress >= 1.0:
                    self._head_intro_active = False

            self._head_rect.center = (int(self.head_x), int(self.head_y))
            # Mantém os bounds de compatibilidade em sincronia com a posicao real da cabeca
            self.y = self.head_y - self.HEAD_RADIUS
            return [], []

        self._phase = self._current_phase()

        self._attack_timer -= dt
        new_bullets = []
        # O boss NÃO ataca enquanto estiver vulnerável. Frequência reduzida na fúria (fase 3).
        if self._attack_timer <= 0.0 and not self.is_vulnerable:
            new_bullets = self._execute_attack(player_x, player_y)
            self._attack_timer = self._cooldown_for_phase(self._phase)
            # Ativa o sprite de cuspida se houver disparos
            if new_bullets:
                self._spit_anim_timer = 0.4

        if self.is_vulnerable:
            # Velocidade aumentada significativamente para 2.8x
            current_speed *= self.VULNERABLE_HEAD_SPEED_MOD

            # Invocação de blocos (fragmentos) que sobem do fundo
            self._vulnerable_block_timer -= dt
            if self._vulnerable_block_timer <= 0:
                spawn_x = random.uniform(self.left_x, self.right_x)
                ascent_speed = random.uniform(*self.VULNERABLE_BLOCK_ASCENT_SPEED)
                # Cria o bloco com flag is_fragment=True para movimento ascendente
                fragment = SerpentBlock(
                    spawn_x,
                    float(Config.SCREEN_HEIGHT + SerpentBlock.RADIUS),
                    "left",
                    self,
                    row_index=-1,
                    is_fragment=True,
                    ascent_speed=ascent_speed,
                )
                new_entities.append(fragment)
                # Reseta o timer com intervalo aleatório
                self._vulnerable_block_timer = random.uniform(
                    *self.VULNERABLE_BLOCK_SPAWN_COOLDOWN
                )

        # Lógica do rastro fantasmagórico da cabeça (Efeito Alucard)
        # Otimização: Remoção in-place com iteração reversa
        for i in range(len(self._head_afterimages) - 1, -1, -1):
            img = self._head_afterimages[i]
            img["life"] -= dt
            if img["life"] <= 0:
                self._head_afterimages.pop(i)

        if current_speed > self.speed or self.is_vulnerable:
            self._head_trail_timer -= dt
            if self._head_trail_timer <= 0:
                self._head_afterimages.append(
                    {
                        "x": self.head_x,
                        "y": self.head_y,
                        "sprite": self._head_sprite,
                        "life": 0.25,
                    }
                )
                self._head_trail_timer = 0.05

        self.head_x += self.direction * current_speed * dt

        if self.head_x <= self.left_x + self.HEAD_RADIUS:
            self.head_x = self.left_x + self.HEAD_RADIUS
            self.direction = 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS:
            self.head_x = self.right_x - self.HEAD_RADIUS
            self.direction = -1

        # Coleta estilhaços de pedra gerados pela destruição de blocos
        if self._pending_shards:  # Removido hasattr desnecessário
            new_entities.extend(self._pending_shards)
            self._pending_shards.clear()

        self._head_rect.center = (int(self.head_x), int(self.head_y))
        # Mantém os bounds de compatibilidade em sincronia com a posicao real da cabeca
        self.y = self.head_y - self.HEAD_RADIUS

        return new_bullets, new_entities

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        shake_x, shake_y = self._compute_head_shake()

        # Desenha os fantasmas do rastro da cabeça (Efeito Alucard)
        # Otimizado: set_alpha() direto no sprite original, evitando copy()
        for img in self._head_afterimages:
            alpha = int((img["life"] / 0.25) * 100)
            sprite = img["sprite"]
            old_alpha = sprite.get_alpha()
            sprite.set_alpha(alpha)
            # O fantasma é desenhado centralizado na sua posição gravada
            fx = int(img["x"]) - sprite.get_width() // 2
            fy = int(img["y"]) - sprite.get_height() // 2
            surface.blit(sprite, (fx, fy))
            sprite.set_alpha(old_alpha)

        draw_x = int(self.head_x + shake_x) - self._head_half_w
        draw_y = int(self.head_y + shake_y) - self._head_half_h

        # Seleciona o sprite baseado no estado (Prioridade: Dor > Cuspida > Normal)
        current_sprite = self._head_sprite
        white_sprite = None

        if self._head_pain_timer > 0.0 and self._pain_sprite:
            current_sprite = self._pain_sprite
            white_sprite = self._white_pain_sprite
        elif self._spit_anim_timer > 0.0 and self._spit_sprite:
            current_sprite = self._spit_sprite
            white_sprite = self._white_spit_sprite
        else:
            # Pega o frame correspondente da animação atual para o flash
            current_frame_idx = self._frame_sequence[self._animation_seq_pos]
            if self._white_animation_frames and current_frame_idx < len(
                self._white_animation_frames
            ):
                white_sprite = self._white_animation_frames[current_frame_idx]

        if self._hit_flash > 0.0 and white_sprite:
            surface.blit(white_sprite, (draw_x, draw_y))
        else:
            surface.blit(current_sprite, (draw_x, draw_y))

        self._draw_health_bar(surface)

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        bar_w = 140
        bar_h = 8
        bar_x = int(self.head_x - bar_w / 2)
        bar_y = int(self.head_y - self._head_half_h - 14)
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        if self.max_health > 0:
            life_w = int(bar_w * self.health / self.max_health)
            pygame.draw.rect(surface, self._COLOR_GLOW, (bar_x, bar_y, life_w, bar_h))
            pygame.draw.rect(surface, colors.WHITE, (bar_x, bar_y, bar_w, bar_h), 2)
