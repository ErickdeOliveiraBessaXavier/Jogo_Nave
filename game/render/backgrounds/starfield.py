"""Starfield e corpos celestes: o fundo-base de espaço.

Reúne o campo de estrelas (``StarField``) e os corpos celestes
(``CelestialManager``), e os empacota em ``StarfieldBackground`` — um
``Background`` como os demais temas, para entrar no mesmo fluxo polimórfico
do renderer (sem if/else especial). O ``StarField`` segue acessível para as
cenas de menu que desenham só as estrelas.
"""

import math
import random
from pathlib import Path
from typing import Optional, TypedDict

import pygame

from ...core.assets import BASE_DIR, get_image
from ...core.render_config import RenderConfig
from .base import Background


class Star(TypedDict):
    x: int
    y: float
    speed: float
    size: int
    brightness: int
    phase: float  # Fase da animação (0 a 2π)
    pulse_speed: float  # Velocidade da pulsação
    color: tuple[int, int, int]  # Cor da estrela


class CelestialBody(TypedDict):
    image: pygame.Surface
    x: float
    y: float
    speed: float
    scale: float
    # === NOVO: Rastrear qual imagem está sendo usada ===
    image_path: Path


class CelestialManager:
    def __init__(self, w: int, h: int, n: int = RenderConfig.CELESTIAL_NUM_BODIES):
        self.w, self.h = w, h
        self.celestial_bodies: list[CelestialBody] = []
        self.image_files: list[Path] = self._load_image_files()
        # === NOVO: Controle de imagens já usadas ===
        self._used_images: set[Path] = set()
        # Sistema de cooldown para evitar recorrência
        self._recently_used: dict[Path, float] = {}  # image_path -> last_used_time
        self._cooldown_time = 30.0  # 30 segundos de cooldown
        self.current_time = 0.0  # Para rastrear tempo
        # === Cache para imagens escaladas ===
        self.scaled_image_cache: dict[tuple[Path, float], pygame.Surface] = {}
        # === FIM ===
        # Timer para spawn orgânico
        self.spawn_timer = 0.0
        self.next_spawn_time = random.uniform(
            RenderConfig.CELESTIAL_SPAWN_MIN_INTERVAL,
            RenderConfig.CELESTIAL_SPAWN_MAX_INTERVAL,
        )
        # Initialize the pool with 'n' celestial bodies
        for _ in range(n):
            self.celestial_bodies.append(self._create_and_initialize_celestial_body())

    def _load_image_files(self) -> list[Path]:
        image_dir = BASE_DIR / "assets" / "images"
        return list(image_dir.glob("*.png"))

    def _generate_scaled_image(self, image_path: Path, scale: float) -> pygame.Surface:
        """Loads, scales, and sets alpha for a celestial body image. Uses cache to avoid recomputation."""
        # Quantizar para passos de 0.2 para aumentar reutilização do cache sem
        # impacto visual perceptível.
        scale_key = round(scale * 5.0) / 5.0
        cache_key = (image_path, scale_key)
        if cache_key in self.scaled_image_cache:
            return self.scaled_image_cache[cache_key]

        original_image = get_image(image_path)

        width = int(original_image.get_width() * scale)
        height = int(original_image.get_height() * scale)
        image = pygame.transform.scale(original_image, (width, height))
        image = image.convert_alpha()  # Optimize for blitting

        # Opacity based on size
        alpha = int(
            RenderConfig.CELESTIAL_ALPHA_MIN
            + (scale - RenderConfig.CELESTIAL_SCALE_MIN)
            * (RenderConfig.CELESTIAL_ALPHA_MAX - RenderConfig.CELESTIAL_ALPHA_MIN)
            / (RenderConfig.CELESTIAL_SCALE_MAX - RenderConfig.CELESTIAL_SCALE_MIN)
        )
        image.set_alpha(alpha)

        # Cache the scaled image
        self.scaled_image_cache[cache_key] = image
        return image

    def _get_random_x_position(
        self, width: int, current_body: Optional[CelestialBody] = None
    ) -> float:
        """Generates a random x-position ensuring no overlap with existing bodies."""
        new_x = 0
        max_attempts = 5  # Reduzido de 10 para performance
        for _ in range(max_attempts):
            test_x = random.uniform(0, self.w - width)
            overlap = False
            for existing_body in self.celestial_bodies:
                if existing_body is current_body:  # Don't check overlap with itself
                    continue
                min_gap = RenderConfig.CELESTIAL_MIN_GAP
                if (
                    test_x
                    < existing_body["x"] + existing_body["image"].get_width() + min_gap
                    and test_x + width + min_gap > existing_body["x"]
                ):
                    overlap = True
                    break
            if not overlap:
                new_x = test_x
                break
        return new_x

    def _get_available_image(self, current_time: float) -> Path:
        """
        Retorna uma imagem disponível que não está sendo usada por outros corpos celestiais
        e não foi usada recentemente (cooldown).

        Prioriza imagens nunca usadas, depois imagens fora do cooldown.
        """
        # Primeiro, imagens disponíveis (não usadas atualmente)
        available_images = [
            img for img in self.image_files if img not in self._used_images
        ]

        if not available_images:
            # Se não há nenhuma disponível, permitir duplicata (caso extremo)
            return random.choice(self.image_files)

        # Separar em: nunca usadas vs recentemente usadas
        never_used: list[Path] = []
        recently_used: list[Path] = []

        for img in available_images:
            last_used = self._recently_used.get(img, 0.0)
            if current_time - last_used >= self._cooldown_time:
                never_used.append(img)
            else:
                recently_used.append(img)

        # Priorizar imagens nunca usadas ou fora do cooldown
        if never_used:
            return random.choice(never_used)
        elif recently_used:
            # Se só há recentemente usadas, escolher a menos recente
            recently_used.sort(key=lambda img: self._recently_used.get(img, 0.0))
            return recently_used[0]  # A menos recente
        else:
            # Fallback (não deveria acontecer)
            return random.choice(available_images)

    def _create_and_initialize_celestial_body(
        self, y_position: Optional[float] = None
    ) -> CelestialBody:
        """Creates a new celestial body and initializes its properties."""
        # === MODIFICADO: Usar imagem disponível ===
        image_path = self._get_available_image(self.current_time)
        self._used_images.add(image_path)  # Registrar como usada
        self._recently_used[image_path] = (
            self.current_time
        )  # Marcar como recentemente usada
        # === FIM ===

        scale = random.uniform(
            RenderConfig.CELESTIAL_SCALE_MIN, RenderConfig.CELESTIAL_SCALE_MAX
        )
        image = self._generate_scaled_image(image_path, scale)

        x = self._get_random_x_position(image.get_width())

        body: CelestialBody = {
            "image": image,
            "x": x,
            "y": y_position if y_position is not None else random.uniform(0, self.h),
            "speed": scale
            * RenderConfig.CELESTIAL_SPEED_BASE_MAX  # Corpos menores (mais distantes) são mais lentos
            + RenderConfig.CELESTIAL_SPEED_OFFSET,
            "scale": scale,
            # === NOVO: Armazenar caminho da imagem ===
            "image_path": image_path,
        }
        return body

    def _reset_celestial_body(
        self, body: CelestialBody, y_position: Optional[float] = None
    ) -> None:
        """Resets the properties of an existing celestial body."""
        # === MODIFICADO: Liberar imagem antiga e escolher nova disponível ===
        # Liberar a imagem antiga
        if "image_path" in body:
            self._used_images.discard(body["image_path"])

        # Escolher nova imagem disponível
        image_path = self._get_available_image(self.current_time)
        self._used_images.add(image_path)  # Registrar como usada
        self._recently_used[image_path] = (
            self.current_time
        )  # Marcar como recentemente usada
        # === FIM ===

        scale = random.uniform(
            RenderConfig.CELESTIAL_SCALE_MIN, RenderConfig.CELESTIAL_SCALE_MAX
        )
        image = self._generate_scaled_image(image_path, scale)

        body["image"] = image
        # === NOVO: Atualizar caminho da imagem ===
        body["image_path"] = image_path
        # === FIM ===
        body["x"] = self._get_random_x_position(
            image.get_width(), current_body=body
        )  # Pass current_body for overlap check
        body["y"] = y_position if y_position is not None else random.uniform(0, self.h)
        body["speed"] = (
            scale * RenderConfig.CELESTIAL_SPEED_BASE_MAX
            + RenderConfig.CELESTIAL_SPEED_OFFSET
        )
        body["scale"] = scale

    def update(
        self, dt: float, speed_multiplier: float = 1.0, allow_spawning: bool = True
    ) -> None:
        self.current_time += dt

        # Atualizar corpos existentes e remover os que saíram
        remaining_bodies: list[CelestialBody] = []
        removed_images: list[Path] = []
        for body in self.celestial_bodies:
            body["y"] += body["speed"] * dt * speed_multiplier
            if body["y"] <= self.h + 100:  # Ainda na tela
                remaining_bodies.append(body)
            else:
                # Corpo saiu, liberar imagem e marcar como recentemente usada
                if "image_path" in body:
                    self._used_images.discard(body["image_path"])
                    self._recently_used[body["image_path"]] = self.current_time
                    removed_images.append(body["image_path"])

        self.celestial_bodies = remaining_bodies

        # Timer para spawn orgânico - só spawnar se permitido
        if allow_spawning:
            self.spawn_timer += dt
            if (
                self.spawn_timer >= self.next_spawn_time
                and len(self.celestial_bodies) < RenderConfig.CELESTIAL_NUM_BODIES
            ):
                # Spawnar um novo corpo
                new_body = self._create_and_initialize_celestial_body(
                    y_position=random.uniform(
                        self.h * RenderConfig.CELESTIAL_RESET_Y_MIN_MULTIPLIER,
                        self.h * RenderConfig.CELESTIAL_RESET_Y_MAX_MULTIPLIER,
                    )
                )
                self.celestial_bodies.append(new_body)
                # Resetar timer
                self.spawn_timer = 0.0
                self.next_spawn_time = random.uniform(
                    RenderConfig.CELESTIAL_SPAWN_MIN_INTERVAL,
                    RenderConfig.CELESTIAL_SPAWN_MAX_INTERVAL,
                )

    def draw(self, surface: pygame.Surface) -> None:
        for body in self.celestial_bodies:
            surface.blit(body["image"], (round(body["x"]), round(body["y"])))


class StarField:
    TWO_PI = 2 * math.pi  # Constante de classe
    MAX_STAR_SIZE = 24  # Tamanho máximo da surface do pool

    def __init__(self, w: int, h: int, n: int = RenderConfig.STARFIELD_NUM_STARS):
        self.w, self.h = w, h
        self.stars: list[Star] = []

        # Pool de surfaces para reutilização
        self.star_surface_pool: list[pygame.Surface] = []
        self.POOL_SIZE = 100
        self._pool_index = 0
        self._initialize_surface_pool()

        self._points_buffer: list[tuple[float, float]] = [(0.0, 0.0)] * 20

        for _ in range(n):
            self.stars.append(self._create_and_initialize_star())

    def _initialize_surface_pool(self) -> None:
        """Pré-cria surfaces para reutilização no pool."""
        # Size 3 (max) * 1.3 (max pulse) * 3 (curva cúbica) ≈ 12, *2 para margem segura
        for _ in range(self.POOL_SIZE):
            star_surf = pygame.Surface(
                (self.MAX_STAR_SIZE, self.MAX_STAR_SIZE), pygame.SRCALPHA
            )
            self.star_surface_pool.append(star_surf)

    def _create_and_initialize_star(self) -> Star:
        """Creates and initializes a new star with random color and varied pulse speed."""
        star_colors = [
            (255, 255, 255),  # branco
            (180, 200, 255),  # azul claro
            (255, 220, 180),  # amarelo
            (255, 180, 180),  # vermelho
            (255, 200, 120),  # laranja
        ]
        color = random.choice(star_colors)
        # Proporção: 60% pulsantes rápidas/médias, 20% lentas/quase fixas, 20% totalmente fixas
        r = random.random()
        if r < 0.2:
            pulse_speed = 0.0  # fixa
        elif r < 0.4:
            pulse_speed = random.uniform(0.2, 1.2)  # lenta/quase fixa
        else:
            pulse_speed = random.uniform(1.3, 3.5)  # média/rápida
        return Star(
            {
                "x": random.randint(0, self.w),
                "y": random.randint(0, self.h),
                "speed": random.uniform(
                    RenderConfig.STARFIELD_SPEED_MIN, RenderConfig.STARFIELD_SPEED_MAX
                ),
                "size": random.choice([1, 1, 2, 3]),
                "brightness": random.randint(
                    RenderConfig.STARFIELD_BRIGHTNESS_MIN,
                    RenderConfig.STARFIELD_BRIGHTNESS_MAX,
                ),
                "phase": random.uniform(0, 2 * math.pi),
                "pulse_speed": pulse_speed,
                "color": color,
            }
        )

    def _reset_star(self, star: Star) -> None:
        """Resets the position and phase of an existing star, keeping other properties the same."""
        star["x"] = random.randint(0, self.w)
        star["y"] = -star["size"]  # Start above the screen
        star["phase"] = random.uniform(0, 2 * math.pi)
        # Keep speed, size, brightness, pulse_speed, color unchanged

    def update(self, dt: float, speed_multiplier: float = 1.0) -> None:
        for s in self.stars:
            # Movimento vertical
            s["y"] += s["speed"] * dt * speed_multiplier

            # Atualizar fase da animação
            s["phase"] += s["pulse_speed"] * dt
            if s["phase"] > self.TWO_PI:
                s["phase"] -= self.TWO_PI

            # Reset se sair da tela
            if s["y"] > self.h:
                self._reset_star(s)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha estrelas reutilizando surfaces do pool."""
        for s in self.stars:
            # Calcular pulso (reutilizar cálculo)
            pulse: float = 0.7 + 0.3 * (1 + math.sin(s["phase"]))
            animated_size: float = s["size"] * pulse
            brightness_pulse: float = 0.8 + 0.2 * (1 + math.sin(s["phase"]))

            # Calcular cor com brilho (otimizado)
            base_color = s["color"]
            factor = s["brightness"] * brightness_pulse / 255
            r = int(max(0, min(255, base_color[0] * factor)))
            g = int(max(0, min(255, base_color[1] * factor)))
            b = int(max(0, min(255, base_color[2] * factor)))
            c: tuple[int, int, int] = (r, g, b)

            center_x: int = int(s["x"])
            center_y: int = int(s["y"])

            if s["size"] <= 1:
                # Estrelas pequenas: desenhar direto (não precisam de pool)
                radius: int = max(1, int(animated_size))
                pygame.draw.circle(surface, c, (center_x, center_y), radius)
            else:
                # Estrelas grandes: usar pool de surfaces
                star_surf = self.star_surface_pool[self._pool_index]
                self._pool_index = (self._pool_index + 1) % self.POOL_SIZE

                # Limpar surface
                star_surf.fill((0, 0, 0, 0))

                # Calcular pontos do polígono (reutiliza buffer pré-alocado)
                step = self.TWO_PI / 20
                a = animated_size
                center_offset = self.MAX_STAR_SIZE // 2

                for i in range(20):
                    t = i * step
                    self._points_buffer[i] = (
                        center_offset + a * math.cos(t) ** 3,
                        center_offset + a * math.sin(t) ** 3,
                    )

                pygame.draw.polygon(star_surf, c, self._points_buffer)

                # Blitar na surface principal
                surface.blit(
                    star_surf, (center_x - center_offset, center_y - center_offset)
                )


class StarfieldBackground(Background):
    """Fundo-base de espaço: campo de estrelas + corpos celestes.

    Implementa a interface ``Background`` delegando para um ``StarField`` e um
    ``CelestialManager``. Os hooks ``set_allow_spawning`` (gating do spawn de
    corpos celestes) e o padrão ``update``/``draw`` deixam o tema 'starfield'
    uniforme com os outros — o renderer não precisa mais de caso especial.
    """

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.starfield = StarField(width, height)
        self.celestial_manager = CelestialManager(width, height)
        self._allow_spawning = True

    def set_allow_spawning(self, allow: bool) -> None:
        self._allow_spawning = allow

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        self.starfield.update(dt, speed_mult)
        self.celestial_manager.update(dt, speed_mult, allow_spawning=self._allow_spawning)

    def draw(self, surface: pygame.Surface) -> None:
        self.starfield.draw(surface)
        self.celestial_manager.draw(surface)

    def reset(self) -> None:
        self.starfield = StarField(self.width, self.height)
        self.celestial_manager = CelestialManager(self.width, self.height)
        self._allow_spawning = True
