import math
import random
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TypedDict

import pygame

from ..core import colors
from ..core.assets import get_font, get_image
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.render_config import RenderConfig
from ..core.sprite_loader import sprite_loader
from ..core.world_config import WorldTheme
from .backgrounds import (
    Background,
    CityBackground,
    MountainsBackground,
    VolcanicBackground,
)

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
        image_dir = Path(__file__).resolve().parents[1] / "assets" / "images"
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

        self._hud_values: dict[str, Optional[int | str]] = {
            "score": None,  # Último valor renderizado (None = nunca renderizado)
            "lives": None,
            "level": None,
            "enemies": None,
            "difficulty": None,
        }
        # === FIM DO CACHE ===

        # NOVO: Background dinâmico (NOVO)
        self.current_background: Optional[Background] = None
        self.current_theme: Optional[WorldTheme] = None
        self._use_starfield_background = True

        self.starfield = StarField(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        self.celestial_manager = CelestialManager(
            Config.SCREEN_WIDTH,
            Config.SCREEN_HEIGHT,
            n=RenderConfig.CELESTIAL_NUM_BODIES,
        )

        # === NOVO: Sistema de medição de FPS ===
        self.fps_counter = 0
        self.fps_timer = 0.0
        self.current_fps = 0.0
        self.max_frame_times = 60  # Manter histórico dos últimos 60 frames
        self.frame_times: deque[float] = deque()
        self._frame_time_sum = 0.0
        self._frame_time_min_candidates: deque[float] = deque()
        self._frame_time_max_candidates: deque[float] = deque()
        self._fps_stats_cache: dict[str, float] = {
            "fps": 0.0,
            "avg_frame_time": 0.0,
            "max_frame_time": 0.0,
            "min_frame_time": 0.0,
        }
        # === FIM DO SISTEMA DE FPS ===

    def set_mountains_progress(self, progress: float) -> None:
        """DEPRECATED: Progressão das cordilheiras é agora automática e contínua.

        O ciclo dia/noite ocorre independentemente em MountainsBackground.
        Este método é mantido por compatibilidade, mas não faz nada.
        """
        pass

    def set_world_theme(self, theme: WorldTheme) -> None:
        """
        Troca o background baseado no tema do mundo.

        Args:
            theme: Tema do mundo (WorldTheme enum)
        """
        # Não recriar se já está no tema correto
        if self.current_theme == theme:
            return

        self.current_theme = theme

        if theme == WorldTheme.MOUNTAINS:
            self.current_background = MountainsBackground(
                Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
            )
            self._use_starfield_background = False
        elif theme == WorldTheme.CITY:
            self.current_background = CityBackground(
                Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
            )
            self._use_starfield_background = False
        elif theme == WorldTheme.VOLCANIC:
            self.current_background = VolcanicBackground(
                Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
            )
            self._use_starfield_background = False
        else:  # STARFIELD ou PROCEDURAL
            self.current_background = None  # Usa sistema original
            self._use_starfield_background = True

    def background(
        self,
        surface: pygame.Surface,
        dt: float,
        speed_multiplier: float = 1.0,
        draw_celestials: bool = True,
    ):
        surface.fill(colors.BLACK)

        # Desenhar starfield APENAS se o tema exigir fundo procedural
        if self._use_starfield_background:
            self.starfield.update(dt, speed_multiplier)
            self.celestial_manager.update(
                dt, speed_multiplier, allow_spawning=draw_celestials
            )
            self.starfield.draw(surface)
            self.celestial_manager.draw(surface)
        else:
            # Para temas customizados (MOUNTAINS, CITY, VOLCANIC)
            # NÃO desenhar starfield, apenas o background do tema
            if self.current_background is not None:
                self.current_background.update(dt, speed_multiplier)
                self.current_background.draw(surface)

    def _render_text_cached(
        self,
        cache_key: str,
        current_value: int | str,
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
        level_display: str = "1",  # MODIFICADO: era level_number: int
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
        lives_surf = self._render_text_cached(
            "lives", lives, "Vidas: {}", self.font_medium, colors.WHITE
        )

        # MODIFICADO: Mostrar estágio formatado (ex: "2-5" ao invés de "Fase: 15")
        lvl = self.font_medium.render(f"Estágio: {level_display}", True, colors.WHITE)

        e = self._render_text_cached(
            "enemies", enemies_destroyed, "Inimigos: {}", self.font_small, colors.WHITE
        )

        # Desenhar textos (mesmas posições)
        surface.blit(s, (10, 10))
        surface.blit(
            lives_surf, (Config.SCREEN_WIDTH - lives_surf.get_width() - 10, 10)
        )
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
                difficulty_preset.value,  # Valor do enum — estável e sem risco de colisão
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
                    blink = int(time.time() * 4) % 2 == 0
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

    def preparation(
        self,
        surface: pygame.Surface,
        remaining: float,
        stage_name: str = "",
        difficulty: Optional["DifficultyPreset"] = None,
    ):
        # Design aprimorado com animações e hierarquia
        t = pygame.time.get_ticks() / 1000.0

        # Parâmetros de animação de saída
        exit_anim_active = remaining <= 0
        exit_progress = min(1.0, abs(remaining) / 1.0) if exit_anim_active else 0.0
        global_alpha = int(255 * (1.0 - exit_progress))
        exit_scale = 1.0 + exit_progress * 1.5  # Expande conforme some

        # 1. Painel de fundo sutil com gradiente otimizado
        panel_h = 240
        panel_y = Config.SCREEN_HEIGHT // 2 - panel_h // 2

        grad_w = 200
        grad_surf = pygame.Surface((grad_w, 1), pygame.SRCALPHA)
        for x in range(grad_w):
            dist_center = abs(x - grad_w // 2)
            alpha = max(
                0,
                int(140 * (1.0 - exit_progress))
                - int(dist_center * (140 / (grad_w // 2))),
            )
            if alpha > 0:
                grad_surf.set_at((x, 0), (0, 0, 0, alpha))

        overlay = pygame.transform.smoothscale(
            grad_surf, (Config.SCREEN_WIDTH, panel_h)
        )
        surface.blit(overlay, (0, panel_y))

        # Fontes
        warning_font = get_font(Config.WARNING_FONT_SIZE)
        info_font = get_font(24)
        diff_font = get_font(18)

        # 2. Nome do Estágio (Acima do contador)
        if stage_name:
            st_alpha = int((180 + int(75 * math.sin(t * 3))) * (1.0 - exit_progress))
            st_surf = info_font.render(stage_name, True, colors.CUSTOM_GOLD)
            st_surf.set_alpha(st_alpha)
            surface.blit(
                st_surf,
                (
                    Config.SCREEN_WIDTH // 2 - st_surf.get_width() // 2,
                    Config.SCREEN_HEIGHT // 2 - 95 - int(exit_progress * 40),
                ),
            )

        # 3. Contador Central (Número Grande ou "COMBATE!")
        if not exit_anim_active:
            count_val = int(remaining) + 1
            fraction = remaining - int(remaining)
            pulse = 1.0 + 0.2 * (1.0 - fraction)
            ct_base = warning_font.render(f"{count_val}", True, colors.RED)
        else:
            pulse = exit_scale
            ct_base = warning_font.render("COMBATE!", True, colors.YELLOW)
            ct_base.set_alpha(global_alpha)

        ct_surf = pygame.transform.smoothscale(
            ct_base,
            (int(ct_base.get_width() * pulse), int(ct_base.get_height() * pulse)),
        )
        crect = ct_surf.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2)
        )
        surface.blit(ct_surf, crect)

        # 4. Dificuldade (Abaixo do contador)
        if difficulty is not None:
            from ..core.difficulty import DifficultyPreset, DifficultySettings

            d_set = DifficultySettings.get_settings(difficulty)
            d_color = {
                DifficultyPreset.CASUAL: colors.GREEN,
                DifficultyPreset.NORMAL: colors.YELLOW,
                DifficultyPreset.HARDCORE: colors.ORANGE,
                DifficultyPreset.NIGHTMARE: colors.RED,
            }.get(difficulty, colors.WHITE)

            d_surf = diff_font.render(
                f"DIFICULDADE: {d_set['name'].upper()}", True, d_color
            )
            d_surf.set_alpha(global_alpha)

            dx = Config.SCREEN_WIDTH // 2 - d_surf.get_width() // 2
            dy = Config.SCREEN_HEIGHT // 2 + 70 + int(exit_progress * 40)

            # Linhas decorativas laterais
            line_w = 60
            l_alpha = global_alpha
            pygame.draw.line(
                surface,
                (*d_color, l_alpha),
                (dx - line_w - 10, dy + 12),
                (dx - 10, dy + 12),
                2,
            )
            pygame.draw.line(
                surface,
                (*d_color, l_alpha),
                (dx + d_surf.get_width() + 10, dy + 12),
                (dx + d_surf.get_width() + line_w + 10, dy + 12),
                2,
            )

            surface.blit(d_surf, (dx, dy))

    def level_popup(
        self, surface: pygame.Surface, text: str, timer: float, duration: float
    ):
        """Renderiza um pop-up de transição de nível que desliza do topo."""
        if timer <= 0:
            return

        # Animação de slide
        # 0.5s entrada, dur-1.0s espera, 0.5s saída
        slide_duration = 0.5
        if timer > duration - slide_duration:
            # Entrada
            progress = (duration - timer) / slide_duration
            y_offset = -60 + 80 * (1.0 - (1.0 - progress) ** 3)  # Ease out cubic
        elif timer < slide_duration:
            # Saída
            progress = timer / slide_duration
            y_offset = -60 + 80 * progress
        else:
            # Espera
            y_offset = 20

        # Design do Pop-up
        font = get_font(22)
        txt_surf = font.render(text, True, colors.WHITE)

        box_w = txt_surf.get_width() + 60
        box_h = 45
        box_x = Config.SCREEN_WIDTH // 2 - box_w // 2
        box_y = y_offset

        # Fundo do painel
        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (0, 0, 0, 180), (0, 0, box_w, box_h), border_radius=10)
        pygame.draw.rect(
            panel, colors.CUSTOM_GOLD, (0, 0, box_w, box_h), 2, border_radius=10
        )

        # Brilho sutil nas bordas
        glow = pygame.Surface((box_w + 10, box_h + 10), pygame.SRCALPHA)
        pygame.draw.rect(
            glow, (218, 165, 32, 50), (5, 5, box_w, box_h), border_radius=12
        )

        surface.blit(glow, (box_x - 5, box_y - 5))
        surface.blit(panel, (box_x, box_y))
        surface.blit(
            txt_surf, (box_x + 30, box_y + (box_h - txt_surf.get_height()) // 2)
        )

    def update_fps(self, dt: float):
        """Atualiza o contador de FPS e calcula métricas de performance."""
        self.fps_counter += 1
        self.fps_timer += dt

        if len(self.frame_times) >= self.max_frame_times:
            removed_dt = self.frame_times.popleft()
            self._frame_time_sum -= removed_dt

            if (
                self._frame_time_min_candidates
                and removed_dt == self._frame_time_min_candidates[0]
            ):
                self._frame_time_min_candidates.popleft()
            if (
                self._frame_time_max_candidates
                and removed_dt == self._frame_time_max_candidates[0]
            ):
                self._frame_time_max_candidates.popleft()

        self.frame_times.append(dt)
        self._frame_time_sum += dt

        while (
            self._frame_time_min_candidates and self._frame_time_min_candidates[-1] > dt
        ):
            self._frame_time_min_candidates.pop()
        self._frame_time_min_candidates.append(dt)

        while (
            self._frame_time_max_candidates and self._frame_time_max_candidates[-1] < dt
        ):
            self._frame_time_max_candidates.pop()
        self._frame_time_max_candidates.append(dt)

        # Atualizar FPS a cada segundo
        if self.fps_timer >= 1.0:
            self.current_fps = self.fps_counter / self.fps_timer
            self.fps_counter = 0
            self.fps_timer = 0.0

        if self.frame_times:
            self._fps_stats_cache = {
                "fps": self.current_fps,
                "avg_frame_time": (self._frame_time_sum / len(self.frame_times)) * 1000,
                "max_frame_time": self._frame_time_max_candidates[0] * 1000,
                "min_frame_time": self._frame_time_min_candidates[0] * 1000,
            }

    def get_fps_stats(self) -> dict[str, float]:
        """Retorna estatísticas de FPS e performance."""
        return dict(self._fps_stats_cache)


# Função para pré-carregar imagens celestiais
def preload_celestial_images():
    """Pré-carrega todas as imagens celestiais para evitar delays."""
    image_dir = Path(__file__).resolve().parents[1] / "assets" / "images"
    image_files = list(image_dir.glob("*.png"))
    for image_path in image_files:
        try:
            get_image(image_path)  # Carrega a imagem
        except (OSError, pygame.error, ValueError, TypeError) as e:
            print(f"Erro ao pré-carregar imagem celestial {image_path}: {e}")


# Registra o loader de imagens celestiais
sprite_loader.register("CelestialImages", preload_celestial_images)
