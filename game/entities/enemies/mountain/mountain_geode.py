import math
import random
from typing import TYPE_CHECKING

import pygame

from ....core.config import config as Config
from ...projectiles.explosive_mine import ExplosiveMine

if TYPE_CHECKING:
    from ....systems.hit_result import HitResult

# ---------------------------------------------------------------------------
# Constantes globais de configuração — ajuste aqui para afetar toda a classe
# ---------------------------------------------------------------------------

# Geometria
GEODE_RADIUS: int = 26
GEODE_EXPLOSION_RADIUS_FACTOR: float = 6.0

# Saúde / dano
GEODE_HEALTH: int = 50
GEODE_SPEED: int = 42

# Animação principal
GEODE_PULSE_MAGNITUDE: float = 0.16  # amplitude do pulso (fator sobre sin)
GEODE_PULSE_FREQUENCY: float = 4.0  # Hz do pulso
GEODE_SWAY_FREQ_MIN: float = 1.0
GEODE_SWAY_FREQ_MAX: float = 1.4
GEODE_SWAY_AMP_MIN: float = 10.0
GEODE_SWAY_AMP_MAX: float = 18.0

# Explosão / shake
GEODE_PRE_EXPLOSION_DURATION: float = 2.2  # segundos até explodir após HP=0
GEODE_FLASH_INTERVAL: float = 0.11  # intervalo entre flashes
GEODE_SHAKE_DURATION_HIT: float = 0.18  # shake ao tomar hit normal
GEODE_SHAKE_INTENSITY_EXPLODING: int = 9  # intensidade do shake na pré-explosão
GEODE_SHAKE_INTENSITY_MAX: int = 5  # cap do shake ao tomar dano (pixels)

# Posição de parada (fração da altura da tela)
GEODE_STOP_Y_MIN: float = 0.25
GEODE_STOP_Y_MAX: float = 0.60

# Indicador de raio de explosão
GEODE_INDICATOR_ALPHA_START: float = 0.22  # alpha inicial (normalizado 0–1)
GEODE_INDICATOR_ALPHA_END: float = 0.75  # alpha final   (normalizado 0–1)
GEODE_INDICATOR_COLOR: tuple[int, int, int] = (180, 235, 255)

# Aparência do geode (normal)
GEODE_COLOR_NORMAL: tuple[int, int, int, int] = (132, 186, 216, 220)
GEODE_GLOW_NORMAL: tuple[int, int, int, int] = (96, 142, 188, 90)
GEODE_COLOR_FLASH: tuple[int, int, int, int] = (255, 240, 180, 230)
GEODE_GLOW_FLASH: tuple[int, int, int, int] = (255, 210, 130, 140)
GEODE_CORE_COLOR: tuple[int, int, int, int] = (220, 245, 255, 180)
GEODE_CORE_RADIUS_FACTOR: float = 0.35  # raio do núcleo relativo ao radius
GEODE_SPIKE_COUNT: int = 8
GEODE_SPIKE_OUT_FACTOR: float = 1.15  # ponta saliente
GEODE_SPIKE_IN_FACTOR: float = 0.92  # ponta reentrante

# Cache
GEODE_SHAPE_CACHE_MAX: int = 64

# Pontuação
GEODE_POINTS: int = 280

# Dimensão mínima de render (evita raio = 0 em scales extremas)
GEODE_MIN_DRAW_RADIUS: int = 8


class MountainGeode(ExplosiveMine):
    """Inimigo exclusivo de Cordilheiras que substitui minas explosivas."""

    # Cache compartilhado entre instâncias: (r, color_key) -> Surface
    SHAPE_CACHE: dict[tuple[int, int], pygame.Surface] = {}

    def __init__(self, x: float | None = None, y: float | None = None) -> None:
        self.radius: int = GEODE_RADIUS
        self.explosion_radius: int = int(self.radius * GEODE_EXPLOSION_RADIUS_FACTOR)

        self.x: float = (
            x
            if x is not None
            else float(random.randint(self.radius, Config.SCREEN_WIDTH - self.radius))
        )
        self.y: float = float(y) if y is not None else float(-self.radius)

        self.health: int = GEODE_HEALTH
        self.max_health: int = GEODE_HEALTH
        self.speed: int = GEODE_SPEED
        self.dead: bool = False

        # Estado de shake
        self.shake_timer: float = 0.0
        self.shake_intensity: int = 0
        self._shake_offset: tuple[int, int] = (0, 0)

        # Estado de flash / explosão
        self.flash_timer: float = 0.0
        self.flash_interval: float = GEODE_FLASH_INTERVAL
        self.pre_explosion_timer: float = 0.0
        self.is_exploding: bool = False

        # Animação
        self.animation_timer: float = random.uniform(0.0, 8.0)
        self.pulse_scale: float = 1.0
        self.sway_phase: float = random.uniform(0.0, math.tau)
        self.sway_freq: float = random.uniform(GEODE_SWAY_FREQ_MIN, GEODE_SWAY_FREQ_MAX)
        self.sway_amplitude: float = random.uniform(
            GEODE_SWAY_AMP_MIN, GEODE_SWAY_AMP_MAX
        )

        # Posição de parada
        self.stop_y: float = random.uniform(
            Config.SCREEN_HEIGHT * GEODE_STOP_Y_MIN,
            Config.SCREEN_HEIGHT * GEODE_STOP_Y_MAX,
        )
        self.stopped: bool = False
        self.spawns_ice_zone: bool = True

        # Surface pré-alocada para o indicador de explosão (evita alloc por frame)
        self._indicator_surface: pygame.Surface = pygame.Surface(
            (self.explosion_radius * 2, self.explosion_radius * 2),
            pygame.SRCALPHA,
        )

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    # ------------------------------------------------------------------
    # Lógica pública
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> None:
        if self.dead or self.is_exploding:
            return

        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self._start_explosion()
        else:
            self.shake_timer = GEODE_SHAKE_DURATION_HIT
            # `health` pode virar float quando o dano recebido é fracionário
            # (ex.: feixe contínuo). `shake_intensity` alimenta random.randint,
            # que exige int — coagimos aqui para preservar o contrato de tipo.
            raw = (self.max_health - self.health) * 2
            self.shake_intensity = int(min(raw, GEODE_SHAKE_INTENSITY_MAX))

    def update(self, dt: float) -> None:
        if self.is_exploding:
            self._update_exploding(dt)
        else:
            self._update_alive(dt)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._shaken_center()
        r = max(GEODE_MIN_DRAW_RADIUS, int(self.radius * self.pulse_scale))
        color_key = self._flash_color_key()

        shape_surf = self._get_or_build_shape(r, color_key)
        half = r * 3 // 2
        surface.blit(shape_surf, (int(cx - half), int(cy - half)))

        if self.is_exploding:
            self._draw_explosion_indicator(surface)

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + self.radius

    def should_remove(self) -> bool:
        return self.dead

    def get_points_value(self) -> int:
        return GEODE_POINTS

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.radius)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.take_damage(damage)
        sound = (
            hit_sounds.BOSS_DAMAGE if self.health > 0 else hit_sounds.EXPLOSION_ASTEROID
        )
        return HitResult(
            killed=False,
            sound=sound,
            explosion_size=7 if self.health > 0 else 0,
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    # ------------------------------------------------------------------
    # Helpers privados — update
    # ------------------------------------------------------------------

    def _start_explosion(self) -> None:
        self.is_exploding = True
        self.pre_explosion_timer = GEODE_PRE_EXPLOSION_DURATION
        self.shake_timer = GEODE_PRE_EXPLOSION_DURATION
        self.shake_intensity = GEODE_SHAKE_INTENSITY_EXPLODING

    def _update_exploding(self, dt: float) -> None:
        self.pre_explosion_timer -= dt
        self.flash_timer += dt
        if self.flash_timer >= self.flash_interval:
            self.flash_timer -= self.flash_interval  # mais preciso que reset p/ 0

        self.pulse_scale = 1.0
        if self.shake_timer > 0:
            self.shake_timer -= dt
            self._refresh_shake_offset()

    def _update_alive(self, dt: float) -> None:
        self.animation_timer += dt
        self.pulse_scale = 1.0 + GEODE_PULSE_MAGNITUDE * abs(
            math.sin(self.animation_timer * GEODE_PULSE_FREQUENCY)
        )

        if self.shake_timer > 0:
            self.shake_timer -= dt
            self._refresh_shake_offset()
        else:
            self._shake_offset = (0, 0)

        if self.stopped:
            return

        self.y += self.speed * dt
        sway = math.sin(self.sway_phase + self.animation_timer * self.sway_freq)
        self.x += sway * self.sway_amplitude * dt
        self.x = max(self.radius, min(Config.SCREEN_WIDTH - self.radius, self.x))

        if self.y >= self.stop_y:
            self.y = self.stop_y
            self.stopped = True

    def _refresh_shake_offset(self) -> None:
        """Atualiza o offset de shake uma vez por frame, evitando chamadas
        redundantes a random.randint dentro de draw()."""
        si = self.shake_intensity
        self._shake_offset = (
            random.randint(-si, si),
            random.randint(-si, si),
        )

    # ------------------------------------------------------------------
    # Helpers privados — draw
    # ------------------------------------------------------------------

    def _shaken_center(self) -> tuple[float, float]:
        ox, oy = self._shake_offset
        return self.x + ox, self.y + oy

    def _flash_color_key(self) -> int:
        """Retorna 1 se o geode deve piscar (flash), 0 caso contrário."""
        if self.is_exploding and int(self.flash_timer * 20) % 2 == 0:
            return 1
        return 0

    def _draw_explosion_indicator(self, surface: pygame.Surface) -> None:
        progress = 1.0 - (self.pre_explosion_timer / GEODE_PRE_EXPLOSION_DURATION)
        progress = max(0.0, min(1.0, progress))

        alpha_start = int(GEODE_INDICATOR_ALPHA_START * 255)
        alpha_end = int(GEODE_INDICATOR_ALPHA_END * 255)
        alpha = int(alpha_start + (alpha_end - alpha_start) * progress)

        self._indicator_surface.fill((0, 0, 0, 0))
        er = self.explosion_radius
        pygame.draw.circle(
            self._indicator_surface,
            (*GEODE_INDICATOR_COLOR, alpha),
            (er, er),
            er,
            width=2,
        )
        surface.blit(
            self._indicator_surface,
            (int(self.x - er), int(self.y - er)),
        )

    # ------------------------------------------------------------------
    # Cache de shape
    # ------------------------------------------------------------------

    def _get_or_build_shape(self, r: int, color_key: int) -> pygame.Surface:
        cache = self.__class__.SHAPE_CACHE
        key = (r, color_key)
        surf = cache.get(key)
        if surf is not None:
            return surf

        if len(cache) >= GEODE_SHAPE_CACHE_MAX:
            cache.clear()

        cache[key] = self._build_shape_surface(r, color_key)
        return cache[key]

    @staticmethod
    def _build_shape_surface(r: int, color_key: int) -> pygame.Surface:
        """Constrói e retorna uma Surface com o desenho do geode para o raio
        e estado de cor fornecidos. Chamado apenas quando há cache miss."""
        size = r * 3
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)

        if color_key == 1:
            geode_color = GEODE_COLOR_FLASH
            glow_color = GEODE_GLOW_FLASH
        else:
            geode_color = GEODE_COLOR_NORMAL
            glow_color = GEODE_GLOW_NORMAL

        points: list[tuple[int, int]] = []
        for i in range(GEODE_SPIKE_COUNT):
            angle = (math.tau * i / GEODE_SPIKE_COUNT) - math.pi / 2
            spike = GEODE_SPIKE_OUT_FACTOR if i % 2 == 0 else GEODE_SPIKE_IN_FACTOR
            px = int(center[0] + math.cos(angle) * r * spike)
            py = int(center[1] + math.sin(angle) * r * spike)
            points.append((px, py))

        pygame.draw.polygon(surf, glow_color, points)
        pygame.draw.polygon(surf, geode_color, points, width=2)

        core_r = max(4, int(r * GEODE_CORE_RADIUS_FACTOR))
        pygame.draw.circle(surf, GEODE_CORE_COLOR, center, core_r)

        return surf
