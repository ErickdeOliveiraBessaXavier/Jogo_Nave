import pygame
import random
import math
from typing import TypedDict, Optional, TYPE_CHECKING, Any
from pathlib import Path
from ..core import colors
from ..core.config import config as Config
from ..core.assets import get_font, get_image  # Added get_image
from ..core.render_config import RenderConfig
from ..core.difficulty import DifficultyPreset, DifficultySettings

if TYPE_CHECKING:
    from ..entities.ship import Ship


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
        self.image_files = self._load_image_files()
        # === NOVO: Controle de imagens já usadas ===
        self._used_images: set[Path] = set()
        # === Cache para imagens escaladas ===
        self.scaled_image_cache: dict[tuple[Path, float], pygame.Surface] = {}
        # === FIM ===
        # Initialize the pool with 'n' celestial bodies
        for _ in range(n):
            self.celestial_bodies.append(self._create_and_initialize_celestial_body())

    def _load_image_files(self) -> list[Path]:
        image_dir = Path(__file__).resolve().parents[1] / "assets" / "images"
        return list(image_dir.glob("*.png"))

    def _generate_scaled_image(self, image_path: Path, scale: float) -> pygame.Surface:
        """Loads, scales, and sets alpha for a celestial body image. Uses cache to avoid recomputation."""
        cache_key = (image_path, scale)
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

    def _get_available_image(self) -> Path:
        """
        Retorna uma imagem disponível que não está sendo usada por outros corpos celestiais.

        Se não houver imagens suficientes disponíveis, permite alguma duplicata.
        """
        # Imagens disponíveis (não usadas)
        available_images = [
            img for img in self.image_files if img not in self._used_images
        ]

        if available_images:
            # Há imagens disponíveis, escolher uma aleatoriamente
            return random.choice(available_images)
        else:
            # Não há imagens suficientes, escolher qualquer uma (permite duplicata)
            return random.choice(self.image_files)

    def _create_and_initialize_celestial_body(
        self, y_position: Optional[float] = None
    ) -> CelestialBody:
        """Creates a new celestial body and initializes its properties."""
        # === MODIFICADO: Usar imagem disponível ===
        image_path = self._get_available_image()
        self._used_images.add(image_path)  # Registrar como usada
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
            "speed": random.uniform(
                RenderConfig.CELESTIAL_SPEED_BASE_MIN,
                RenderConfig.CELESTIAL_SPEED_BASE_MAX,
            )
            * scale
            + RenderConfig.CELESTIAL_SPEED_OFFSET,
            "scale": scale,
            # === NOVO: Armazenar caminho da imagem ===
            "image_path": image_path,
        }
        return body

    def _reset_celestial_body(
        self, body: CelestialBody, y_position: Optional[float] = None
    ):
        """Resets the properties of an existing celestial body."""
        # === MODIFICADO: Liberar imagem antiga e escolher nova disponível ===
        # Liberar a imagem antiga
        if "image_path" in body:
            self._used_images.discard(body["image_path"])

        # Escolher nova imagem disponível
        image_path = self._get_available_image()
        self._used_images.add(image_path)  # Registrar como usada
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
            random.uniform(
                RenderConfig.CELESTIAL_SPEED_BASE_MIN,
                RenderConfig.CELESTIAL_SPEED_BASE_MAX,
            )
            * scale
            + RenderConfig.CELESTIAL_SPEED_OFFSET
        )
        body["scale"] = scale

    def update(self, dt: float, speed_multiplier: float = 1.0):
        for body in self.celestial_bodies:
            body["y"] += body["speed"] * dt * speed_multiplier
            if body["y"] > self.h:
                # Reset the existing body instead of creating a new one
                self._reset_celestial_body(
                    body,
                    y_position=random.uniform(
                        self.h * RenderConfig.CELESTIAL_RESET_Y_MIN_MULTIPLIER,
                        self.h * RenderConfig.CELESTIAL_RESET_Y_MAX_MULTIPLIER,
                    ),
                )

    def draw(self, surface: pygame.Surface):
        for body in self.celestial_bodies:
            surface.blit(body["image"], (round(body["x"]), round(body["y"])))


class StarField:
    TWO_PI = 2 * math.pi  # Constante de classe
    
    def __init__(self, w: int, h: int, n: int = RenderConfig.STARFIELD_NUM_STARS):
        self.w, self.h = w, h
        self.stars: list[Star] = []
        
        # Pool de surfaces para reutilização
        self.star_surface_pool: list[pygame.Surface] = []
        self.POOL_SIZE = 100
        self._pool_index = 0
        self._initialize_surface_pool()
        
        for _ in range(n):
            self.stars.append(self._create_and_initialize_star())

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

    def _reset_star(self, star: Star):
        """Resets the position and phase of an existing star, keeping other properties the same."""
        star["x"] = random.randint(0, self.w)
        star["y"] = -star["size"]  # Start above the screen
        star["phase"] = random.uniform(0, 2 * math.pi)
        # Keep speed, size, brightness, pulse_speed, color unchanged

    def update(self, dt: float, speed_multiplier: float = 1.0):
        for s in self.stars:
            # Movimento vertical
            s["y"] += s["speed"] * dt * speed_multiplier

            # Atualizar fase da animação
            s["phase"] += s["pulse_speed"] * dt
            if s["phase"] > 2 * math.pi:
                s["phase"] -= 2 * math.pi

            # Reset se sair da tela
            if s["y"] > self.h:
                self._reset_star(s)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha as estrelas com cache de surfaces para performance."""
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
                # Estrela pequena: usar cache
                cache_key = ("small", s["size"], s["brightness"], c)
                if cache_key not in self.star_surface_cache:
                    radius: int = max(1, int(s["size"] * pulse))
                    star_surf = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(star_surf, c, (radius + 1, radius + 1), radius)
                    self.star_surface_cache[cache_key] = star_surf
                    # Limitar cache
                    if len(self.star_surface_cache) > self.MAX_CACHE_SIZE:
                        # Remover entrada aleatória (simples LRU aproximado)
                        self.star_surface_cache.pop(next(iter(self.star_surface_cache)))
                cached_surf = self.star_surface_cache[cache_key]
                radius = max(1, int(animated_size))
                surface.blit(cached_surf, (center_x - radius - 1, center_y - radius - 1))
            else:
                # Estrela grande: forma asteroide usando trigonometria (mais bonita)
                # Discretizar phase para cache
                phase_discretized = int((s["phase"] % (2 * math.pi)) / (2 * math.pi) * 16)
                cache_key = ("large", s["size"], phase_discretized, s["brightness"], c)
                if cache_key not in self.star_surface_cache:
                    # Loop para criar pontos da forma asteroide
                    points: list[tuple[float, float]] = []
                    t = 0.0
                    TWO_PI = 2 * math.pi
                    step = TWO_PI / 25  # Reduzido para 25 iterações
                    a = s["size"] * pulse  # Usar s["size"] * pulse em vez de animated_size

                    while t < TWO_PI:
                        x = a * (math.cos(t) ** 3)
                        y = a * (math.sin(t) ** 3)
                        points.append((a + x, a + y))  # Centralizar em (a, a)
                        t += step

                    # Criar surface
                    size = int(a * 2 + 4)
                    star_surf = pygame.Surface((size, size), pygame.SRCALPHA)
                    pygame.draw.polygon(star_surf, c, points)
                    self.star_surface_cache[cache_key] = star_surf
                    # Limitar cache
                    if len(self.star_surface_cache) > self.MAX_CACHE_SIZE:
                        self.star_surface_cache.pop(next(iter(self.star_surface_cache)))
                cached_surf = self.star_surface_cache[cache_key]
                a = int(animated_size)
                surface.blit(cached_surf, (center_x - a - 2, center_y - a - 2))


class Renderer:
    def __init__(self):
        self.font_small = get_font(12)
        self.font_medium = get_font(24)
        self.font_large = get_font(32)

        # === NOVO: Sistema de cache de textos ===
        self._hud_cache: dict[str, Optional[pygame.Surface]] = {
            "score": None,  # Surface renderizada
            "lives": None,
            "level": None,
            "enemies": None,
            "difficulty": None,
        }

        self._hud_values: dict[str, Optional[int]] = {
            "score": None,  # Último valor renderizado (None = nunca renderizado)
            "lives": None,
            "level": None,
            "enemies": None,
            "difficulty": None,
        }
        # === FIM DO CACHE ===

        self.starfield = StarField(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        self.celestial_manager = CelestialManager(
            Config.SCREEN_WIDTH,
            Config.SCREEN_HEIGHT,
            n=RenderConfig.CELESTIAL_NUM_BODIES,
        )
        self.halo_cache: dict[int, pygame.Surface] = (
            {}
        )  # Cache for halo surfaces by radius
        self.MAX_HALO_CACHE_SIZE = 30  # Limitar tamanho do cache

        # === NOVO: Sistema de medição de FPS ===
        self.fps_counter = 0
        self.fps_timer = 0.0
        self.current_fps = 0.0
        self.frame_times: list[float] = []
        self.max_frame_times = 60  # Manter histórico dos últimos 60 frames
        # === FIM DO SISTEMA DE FPS ===

    def background(
        self, surface: pygame.Surface, dt: float, speed_multiplier: float = 1.0
    ):
        surface.fill(colors.BLACK)
        self.starfield.update(dt, speed_multiplier)
        self.celestial_manager.update(dt, speed_multiplier)
        self.starfield.draw(surface)
        self.celestial_manager.draw(surface)

    def _render_text_cached(
        self,
        cache_key: str,
        current_value: int,
        text_template: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        """
        Renderiza texto com cache.

        Só re-renderiza se o valor mudou desde a última vez.

        Args:
            cache_key: Chave no dicionário de cache ('score', 'lives', etc)
            current_value: Valor atual (ex: score atual)
            text_template: Template do texto (ex: "Pontos: {}")
            font: Fonte pygame
            color: Cor do texto

        Returns:
            Surface com o texto renderizado (do cache ou recém-criado)
        """
        # Verificar se valor mudou ou se nunca foi renderizado
        if self._hud_values[cache_key] != current_value:
            # Valor mudou ou nunca foi renderizado, re-renderizar
            text = text_template.format(current_value)
            self._hud_cache[cache_key] = font.render(text, True, color)
            self._hud_values[cache_key] = current_value

        # Retornar surface cacheada (sempre deve existir após verificação acima)
        surface = self._hud_cache[cache_key]
        assert surface is not None, f"Cache surface for {cache_key} should not be None"
        return surface

    def hud(
        self,
        surface: pygame.Surface,
        score: int,
        lives: int,
        enemies_destroyed: int,
        ship: Optional["Ship"] = None,
        level_number: int = 1,
        difficulty_preset: Optional["DifficultyPreset"] = None,
        score_multiplier_active: bool = False,
        score_multiplier_timer: float = 0.0,
        mini_ships_active: bool = False,
        mini_ships_timer: float = 0.0,
        explosive_shots_active: bool = False,
        explosive_shots_remaining: int = 0,
    ):
        # Renderizar com cache (só re-renderiza se valores mudaram)
        s = self._render_text_cached(
            "score", score, "Pontos: {}", self.font_medium, colors.WHITE
        )
        l = self._render_text_cached(
            "lives", lives, "Vidas: {}", self.font_medium, colors.WHITE
        )
        lvl = self._render_text_cached(
            "level", level_number, "Fase: {}", self.font_medium, colors.WHITE
        )
        e = self._render_text_cached(
            "enemies", enemies_destroyed, "Inimigos: {}", self.font_small, colors.WHITE
        )

        # Desenhar textos (mesmas posições)
        surface.blit(s, (10, 10))
        surface.blit(l, (Config.SCREEN_WIDTH - l.get_width() - 10, 10))
        surface.blit(lvl, (10, 44))
        surface.blit(e, (10, 78))

        # Indicador de dificuldade
        if difficulty_preset is not None:
            settings = DifficultySettings.get_settings(difficulty_preset)
            difficulty_color = {
                DifficultyPreset.CASUAL: colors.GREEN,
                DifficultyPreset.NORMAL: colors.YELLOW,
                DifficultyPreset.HARDCORE: colors.ORANGE,
                DifficultyPreset.NIGHTMARE: colors.RED,
            }.get(difficulty_preset, colors.WHITE)

            diff_text = self._render_text_cached(
                "difficulty",
                hash(difficulty_preset.name),  # Usar hash do nome para consistência
                f"Dificuldade: {settings['name']}",
                self.font_small,
                difficulty_color,
            )
            surface.blit(diff_text, (10, 102))

        # --- efeitos ativos (se ship for informado) ---
        # Este código permanece IGUAL (não precisa cache, é dinâmico)
        if ship is not None:
            y = 126 if difficulty_preset is not None else 110

            def line(txt: str, color: tuple[int, int, int] = colors.GREEN):
                nonlocal y
                t = self.font_small.render(txt, True, color)
                surface.blit(t, (10, y))
                y += 18

            invuln_s = ship.get_invulnerable_time()
            ds_s = ship.get_double_shot_time()
            sp_s = ship.get_speed_boost_time()

            if invuln_s > 0:
                line(f"[S] Escudo: {invuln_s:.1f}s", colors.BLUE)
            if ds_s > 0:
                line(f"[2X] Tiro Duplo: {ds_s:.1f}s", colors.GREEN)
            if sp_s > 0:
                line(f"[V] Velocidade: {sp_s:.1f}s", colors.YELLOW)
            
            # Mostrar multiplicador de score se ativo
            if score_multiplier_active and score_multiplier_timer > 0:
                line(f"[x1.5] Score x1.5: {score_multiplier_timer:.1f}s", colors.YELLOW)
            
            # Mostrar mini ships se ativo
            if mini_ships_active and mini_ships_timer > 0:
                line(f"[M] Mini Ships: {mini_ships_timer:.1f}s", colors.CYAN)
            
            # Mostrar tiros explosivos restantes
            if explosive_shots_active and explosive_shots_remaining > 0:
                # Piscar quando restarem 5 ou menos cargas
                if explosive_shots_remaining <= 5:
                    import time as _time
                    blink = int(_time.time() * 4) % 2 == 0
                    color = colors.ORANGE if blink else colors.RED
                else:
                    color = colors.ORANGE
                line(f"[💥] Explosivos: {explosive_shots_remaining}", color)

    def overlay(self, surface: pygame.Surface, title: str, subtitle: str = ""):
        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))
        t = self.font_large.render(title, True, colors.YELLOW)
        rect = t.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 - 40)
        )
        surface.blit(t, rect)
        if subtitle:
            s = self.font_medium.render(subtitle, True, colors.WHITE)
            rect = s.get_rect(
                center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 + 20)
            )
            surface.blit(s, rect)

    def preparation(self, surface: pygame.Surface, remaining: float):
        # Usar fonte do warning (60pt)
        warning_font = get_font(Config.WARNING_FONT_SIZE)

        # contador
        ct = warning_font.render(f"{int(remaining) + 1}", True, colors.RED)
        crect = ct.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2)
        )
        surface.blit(ct, crect)

    def effects_on_ship(self, surface: pygame.Surface, ship: "Ship"):
        """Desenha efeitos visuais na nave (ex.: halo de escudo)."""
        if ship.is_invulnerable:
            cx = int(ship.x + ship.w / 2)
            cy = int(ship.y + ship.h / 2)
            radius = max(ship.w, ship.h) // 2 + 6

            if radius not in self.halo_cache:
                # Limitar tamanho do cache
                if len(self.halo_cache) >= self.MAX_HALO_CACHE_SIZE:
                    self.halo_cache.clear()

                halo = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(
                    halo, (0, 120, 255, 120), (radius + 3, radius + 3), radius, width=3
                )
                self.halo_cache[radius] = halo
            halo = self.halo_cache[radius]
            surface.blit(halo, (cx - radius - 3, cy - radius - 3))

    def update_fps(self, dt: float):
        """Atualiza o contador de FPS e calcula métricas de performance."""
        self.fps_counter += 1
        self.fps_timer += dt
        self.frame_times.append(dt)

        # Manter apenas os últimos frames
        if len(self.frame_times) > self.max_frame_times:
            self.frame_times.pop(0)

        # Atualizar FPS a cada segundo
        if self.fps_timer >= 1.0:
            self.current_fps = self.fps_counter / self.fps_timer
            self.fps_counter = 0
            self.fps_timer = 0.0

    def get_fps_stats(self) -> dict[str, float]:
        """Retorna estatísticas de FPS e performance."""
        if not self.frame_times:
            return {
                "fps": 0.0,
                "avg_frame_time": 0.0,
                "max_frame_time": 0.0,
                "min_frame_time": 0.0,
            }

        avg_frame_time = sum(self.frame_times) / len(self.frame_times)
        max_frame_time = max(self.frame_times)
        min_frame_time = min(self.frame_times)

        return {
            "fps": self.current_fps,
            "avg_frame_time": avg_frame_time * 1000,  # em ms
            "max_frame_time": max_frame_time * 1000,  # em ms
            "min_frame_time": min_frame_time * 1000,  # em ms
        }
