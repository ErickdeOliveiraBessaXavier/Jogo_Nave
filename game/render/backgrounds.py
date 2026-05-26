"""
Backgrounds Dinâmicos para Mundos

Implementa backgrounds temáticos para cada mundo:
- Montanhas: Parallax com picos rochosos
- Cidade: Prédios cyberpunk com janelas piscantes
- Vulcânico: Lava ondulante com brasas flutuantes
- Starfield: Mantém sistema original
"""

import logging
import math
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type, cast

import pygame

logger = logging.getLogger(__name__)


def _optimize_surface(surf: pygame.Surface) -> pygame.Surface:
    """Aplica convert() para alinhar formato com o display (blits ~2-3x mais rápidos).
    Faz fallback silencioso se o display ainda não estiver pronto."""
    try:
        return surf.convert()
    except pygame.error:
        return surf


def _optimize_alpha_surface(surf: pygame.Surface) -> pygame.Surface:
    """Aplica convert_alpha() para alinhar formato RGBA com o display.
    Faz fallback silencioso se o display ainda não estiver pronto."""
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


class ColorPalette:
    """Paleta de cores para camadas de montanha."""

    def __init__(self, light: Tuple[int, int, int], dark: Tuple[int, int, int]) -> None:
        self.light: Tuple[int, int, int] = light
        self.dark: Tuple[int, int, int] = dark


class LayerData:
    """Dados de uma camada de parallax."""

    def __init__(
        self,
        surface: pygame.Surface,
        speed: float,
        offset: float = 0.0,
        y_pos: int = 0,
    ) -> None:
        self.surface: pygame.Surface = surface
        self.speed: float = speed
        self.offset: float = offset
        # Dimensões cacheadas — evitam get_width/get_height por frame
        self.width: int = surface.get_width()
        self.height: int = surface.get_height()
        self.y_pos: int = y_pos


class Background(ABC):
    """Classe base para backgrounds de mundos."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

    @abstractmethod
    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza animação do background."""
        raise NotImplementedError

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o background."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reseta para estado inicial."""
        raise NotImplementedError

    def set_day_night_paused(self, _paused: bool) -> None:
        """Optional hook to pause/resume day/night cycle.

        Background implementations that don't implement a day/night cycle
        can ignore this. Provides a stable API for callers that want to
        request pausing regardless of the concrete background type.
        """
        return None


class Cloud:
    """Representa uma nuvem individual com otimizações."""

    # Cache estático de superfícies de nuvem por (cor, camada)
    _surface_cache: Dict[Tuple[Tuple[int, int, int], bool], pygame.Surface] = {}

    def __init__(
        self,
        width: int,
        height: int,
        speed_range: Tuple[float, float],
        color: Tuple[int, int, int],
        is_back_layer: bool,
    ):
        self.screen_width = width
        self.screen_height = height
        self.speed_range = speed_range
        self.color = color
        self.is_back_layer = is_back_layer

        # Usar cache de superfície quando possível — chave inclui is_back_layer
        # pois o alpha difere entre camadas (102 vs 179)
        cache_key = (color, is_back_layer)
        if cache_key not in Cloud._surface_cache:
            Cloud._surface_cache[cache_key] = _optimize_alpha_surface(
                self._generate_cloud_surface()
            )

        self.base_surface = Cloud._surface_cache[cache_key]

        # Propriedades da instância
        self.x: float = 0.0
        self.y: float = 0.0
        self.speed: float = 0.0
        self.scaled_surface: pygame.Surface = self.base_surface

        self.reset(is_first_time=True)

    def _generate_cloud_surface(self) -> pygame.Surface:
        """Gera superfície da nuvem estilo pixel art."""
        surf = pygame.Surface((200, 100), pygame.SRCALPHA)

        # Desenhar forma da nuvem em camadas
        rects = [
            (30, 60, 140, 10),  # Camada inferior
            (40, 50, 120, 15),  # Camada meio-baixo
            (60, 35, 80, 15),  # Camada meio-alto
            (80, 20, 40, 15),  # Topo
            (50, 45, 10, 5),  # Detalhes esquerda
            (70, 30, 10, 5),
            (140, 45, 10, 5),  # Detalhes direita
            (120, 30, 10, 5),
            (90, 15, 20, 5),  # Topo detalhado
        ]

        for rect in rects:
            pygame.draw.rect(surf, self.color, rect)

        # Aplicar transparência baseada na camada
        alpha = 102 if self.is_back_layer else 179  # 0.4 e 0.7 em 255
        surf.set_alpha(alpha)

        return surf

    def reset(self, is_first_time: bool = False) -> None:
        """Reseta posição, tamanho e velocidade."""
        # Escala aleatória
        scale = random.uniform(0.5, 1.5)
        new_width = int(self.base_surface.get_width() * scale)
        new_height = int(self.base_surface.get_height() * scale)

        # Reutilizar surface transformada
        self.scaled_surface = _optimize_alpha_surface(
            pygame.transform.scale(self.base_surface, (new_width, new_height))
        )

        # Posição inicial
        if is_first_time:
            self.x = random.uniform(0, self.screen_width)
        else:
            self.x = self.screen_width + random.randint(50, 200)

        self.y = (self.screen_height * 0.05) + random.random() * (
            self.screen_height * 0.35
        )

        # Velocidade
        self.speed = random.uniform(self.speed_range[0], self.speed_range[1])

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza posição da nuvem."""
        self.x -= self.speed * dt * speed_mult

        # Reset quando sair da tela
        if self.x < -self.scaled_surface.get_width():
            self.reset()

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha a nuvem."""
        surface.blit(self.scaled_surface, (int(self.x), int(self.y)))


class MountainsBackground(Background):
    """Background de montanhas com parallax."""

    # Constantes da classe
    PALETTES = [
        ColorPalette(light=(76, 59, 99), dark=(45, 33, 61)),
        ColorPalette(light=(106, 76, 125), dark=(66, 45, 82)),
        ColorPalette(light=(158, 92, 127), dark=(94, 58, 88)),
        ColorPalette(light=(224, 126, 116), dark=(122, 62, 82)),
        ColorPalette(light=(82, 52, 94), dark=(42, 27, 51)),
        ColorPalette(light=(36, 25, 51), dark=(15, 10, 20)),
    ]

    LAYER_SPEEDS = [0.1, 0.3, 0.7, 1.5, 3.5, 7.0]
    HEIGHT_PERCENTAGES = [0.65, 0.55, 0.45, 0.32, 0.20, 0.12]
    PEAKS_COUNTS = [8, 12, 15, 7, 20, 30]
    ROUGHNESS_VALUES = [15, 20, 25, 45, 15, 10]

    NUM_STARS = 40  # Reduzido de 70 para melhor performance
    NUM_CLOUDS_BACK = 3  # Reduzido de 4 para melhor performance
    NUM_CLOUDS_FRONT = 2  # Reduzido de 3 para melhor performance
    STAR_ALPHA_LEVELS = 16

    def __init__(self, width: int, height: int):
        super().__init__(width, height)

        # Pré-calcular valores
        self.star_twinkle_speed = 2.0

        # Inicializar coleções
        self.layers: List[LayerData] = []
        self.stars: List[Dict[str, Any]] = []
        self.clouds_back: List[Cloud] = []
        self.clouds_front: List[Cloud] = []

        # Sol
        self.sun_rect: Optional[pygame.Rect] = None
        self.sun_surface: Optional[pygame.Surface] = None

        # Dois gradientes pré-renderizados: warm (pôr do sol) e night (azul-frio).
        # O blit final do céu mistura os dois via alpha proporcional ao
        # ``_current_progress`` (0 = warm puro, 1 = night puro).
        self.sky_warm_gradient: Optional[pygame.Surface] = None
        self.sky_night_gradient: Optional[pygame.Surface] = None

        # Ciclo contínuo dia/noite: anoitecer → noite → amanhecer → dia → repete.
        # _phase: 'sunset' (0→1), 'night' (permanece 1), 'sunrise' (1→0), 'day' (permanece 0)
        self._phase: str = "day"
        self._phase_elapsed_time: float = 0.0
        self._sunset_duration: float = (
            600.0  # segundos para anoitecer completo (10 min)
        )
        self._night_duration: float = 180.0  # noite (3 min intervalo)
        self._sunrise_duration: float = (
            600.0  # segundos para amanhecer completo (10 min)
        )
        self._day_duration: float = 180.0  # dia (3 min intervalo)
        self._current_progress: float = 0.0
        self._pause_day_night_cycle: bool = False  # Pausar ciclo enquanto boss ativo

        # Quanto o sol desce verticalmente quando vai do meio-dia à noite.
        self._sun_dive_distance: int = int(self.height * 0.22)

        # Criar elementos
        self._create_sky_gradients()
        self._create_layers()
        self._create_stars()
        self._create_sun()
        self._create_clouds()

    @staticmethod
    def _ease_progress(progress: float) -> float:
        """Aplica smoothstep em 0..1 para suavizar a transição visual."""
        progress = max(0.0, min(1.0, progress))
        return progress * progress * (3.0 - 2.0 * progress)

    def _create_sky_gradients(self) -> None:
        """Pré-renderiza dois gradientes (warm e night) que serão misturados
        via alpha em tempo de desenho conforme ``_current_progress``.

        Custo: dois loops por linha, executados uma vez no construtor.
        """
        warm_colors = [
            (30, 17, 40),  # topo profundo (já era escuro no warm)
            (58, 37, 82),  # ~40% — roxo
            (140, 75, 110),  # ~70% — rosa-vinho
            (201, 109, 99),  # ~90% — laranja avermelhado
            (255, 158, 125),  # base — peach
        ]
        night_colors = [
            (5, 8, 18),  # topo — quase preto azulado
            (10, 15, 35),  # ~40% — azul-marinho profundo
            (18, 28, 55),  # ~70% — azul noite
            (28, 42, 72),  # ~90% — azul-petróleo
            (40, 60, 95),  # base — azul-acinzentado frio
        ]
        stops = [0.0, 0.4, 0.7, 0.9, 1.0]

        # convert() alinha o formato dos gradientes com o display — blit
        # full-screen fica significativamente mais barato.
        self.sky_warm_gradient = _optimize_surface(
            self._render_sky_gradient(warm_colors, stops)
        )
        self.sky_night_gradient = _optimize_surface(
            self._render_sky_gradient(night_colors, stops)
        )

    def _render_sky_gradient(
        self,
        colors: List[Tuple[int, int, int]],
        stops: List[float],
    ) -> pygame.Surface:
        """Renderiza uma surface vertical com gradiente interpolado entre
        ``colors`` posicionados em ``stops`` (0..1)."""
        surf = pygame.Surface((self.width, self.height))
        for y in range(self.height):
            t = y / self.height
            for i in range(len(stops) - 1):
                if t <= stops[i + 1]:
                    local_t = (t - stops[i]) / (stops[i + 1] - stops[i])
                    color = tuple(
                        int(colors[i][c] + (colors[i + 1][c] - colors[i][c]) * local_t)
                        for c in range(3)
                    )
                    pygame.draw.line(surf, color, (0, y), (self.width, y))
                    break
        return surf

    def set_theme_duration(
        self,
        sunset_duration: float,
        night_duration: float = 300.0,
        sunrise_duration: float = 600.0,
        day_duration: float = 300.0,
    ) -> None:
        """Define as durações de cada fase do ciclo dia/noite.

        Args:
            sunset_duration: Tempo para ir de 0 (dia) a 1 (noite) em segundos.
            night_duration: Tempo de permanência em noite (1.0) em segundos.
            sunrise_duration: Tempo para ir de 1 (noite) a 0 (dia) em segundos.
            day_duration: Tempo de permanência em dia (0.0) em segundos.
        """
        self._sunset_duration = max(1.0, sunset_duration)
        self._night_duration = max(0.0, night_duration)
        self._sunrise_duration = max(1.0, sunrise_duration)
        self._day_duration = max(0.0, day_duration)

    def set_day_night_paused(self, _paused: bool) -> None:
        """Pausa ou retoma o ciclo dia/noite.

        Útil para manter a iluminação constante durante combates de boss.

        Args:
            paused: True para pausar, False para retomar.
        """
        self._pause_day_night_cycle = _paused

    def _create_layers(self) -> None:
        """Cria camadas de parallax otimizadas."""
        speed_multiplier = 50  # Ajuste de escala

        for i in range(6):
            layer_surface = _optimize_alpha_surface(
                self._generate_mountain_surface(
                    self.PALETTES[i],
                    self.PEAKS_COUNTS[i],
                    self.ROUGHNESS_VALUES[i],
                    self.HEIGHT_PERCENTAGES[i],
                )
            )

            self.layers.append(
                LayerData(
                    surface=layer_surface,
                    speed=self.LAYER_SPEEDS[i] * speed_multiplier,
                    offset=0.0,
                    y_pos=self.height - layer_surface.get_height(),
                )
            )

    def _generate_mountain_surface(
        self, palette: ColorPalette, peaks: int, roughness: int, h_pct: float
    ) -> pygame.Surface:
        """Cria superfície otimizada da montanha com gradiente."""
        surf_height = int(self.height * h_pct)
        # Largura igual à tela — o parallax infinito é feito desenhando 2 cópias lado a lado
        surf_width = self.width

        # Criar superfície final
        final_surf = pygame.Surface((surf_width, surf_height), pygame.SRCALPHA)

        # Gerar pontos da montanha
        points = self._generate_mountain_points(
            surf_width, surf_height, peaks, roughness
        )
        highest_y = min(p[1] for p in points[1:-1])  # Ignorar pontos de fechamento

        # Criar gradiente (otimizado com surface lock)
        grad_surf = self._create_gradient_surface(
            surf_width, surf_height, palette, highest_y
        )

        # Aplicar máscara
        mask_surf = pygame.Surface((surf_width, surf_height), pygame.SRCALPHA)
        pygame.draw.polygon(mask_surf, (255, 255, 255, 255), points)

        final_surf.blit(grad_surf, (0, 0))
        final_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        return final_surf

    def _generate_mountain_points(
        self, width: int, height: int, peaks: int, roughness: int
    ) -> List[Tuple[int, int]]:
        """Gera pontos da silhueta da montanha."""
        base_y = height * 0.8
        step = width / peaks

        points: List[Tuple[int, int]] = [(0, height)]
        current_y = base_y + random.randint(0, int(height * 0.2))
        start_y = current_y
        points.append((0, int(current_y)))

        min_y = height * 0.1
        max_y = height - 20

        for i in range(1, peaks):
            x = int(i * step)
            change = random.uniform(-0.5, 0.5) * roughness * 6
            current_y = max(min_y, min(max_y, current_y + change))
            points.append((x, int(current_y)))

        points.extend([(width - 1, int(start_y)), (width - 1, height)])

        return points

    def _create_gradient_surface(
        self, width: int, height: int, palette: ColorPalette, highest_y: float
    ) -> pygame.Surface:
        """Cria superfície de gradiente otimizada com draw.line."""
        grad_surf = pygame.Surface((width, height), pygame.SRCALPHA)

        gradient_range = height - highest_y

        # Desempacotar cores para evitar indexação e tuple comprehension no loop
        lr, lg, lb = palette.light
        dr, dg, db = palette.dark
        light_color = (lr, lg, lb, 255)

        for y in range(height):
            if y < highest_y:
                color = light_color
            else:
                rel_y = min(
                    1.0, (y - highest_y) / gradient_range if gradient_range > 0 else 0
                )
                color = (
                    int(lr + (dr - lr) * rel_y),
                    int(lg + (dg - lg) * rel_y),
                    int(lb + (db - lb) * rel_y),
                    255,
                )
            pygame.draw.line(grad_surf, color, (0, y), (width - 1, y))

        return grad_surf

    def _create_stars(self) -> None:
        """Gera estrelas com distribuição pré-calculada."""
        star_area_height = self.height * 0.5

        # Surfaces pré-renderizadas por tamanho e nível de alpha.
        self._star_surf_cache: Dict[int, List[pygame.Surface]] = {}
        for size in (2, 4):
            variants: List[pygame.Surface] = []
            for level in range(self.STAR_ALPHA_LEVELS):
                alpha = int(255 * (level / (self.STAR_ALPHA_LEVELS - 1)))
                surf = pygame.Surface((size, size), pygame.SRCALPHA)
                surf.fill((255, 255, 255, alpha))
                variants.append(_optimize_alpha_surface(surf))
            self._star_surf_cache[size] = variants

        for _ in range(self.NUM_STARS):
            size = 2 if random.random() < 0.8 else 4
            self.stars.append(
                {
                    "x": random.random() * self.width,
                    "y": random.random() * star_area_height,
                    "size": size,
                    # Bind direto da lista de variants p/ evitar dict lookup por frame.
                    "variants": self._star_surf_cache[size],
                    "delay": random.random() * 5,
                    "base_alpha": random.uniform(0.3, 1.0),
                }
            )

    def _draw_stars(self, surface: pygame.Surface) -> None:
        """Desenha estrelas com brilho piscante usando variants pré-renderizadas.

        O brilho geral é escalado pelo ``_current_progress`` — estrelas quase
        invisíveis no pôr do sol (0) e fortes na noite fechada (1).
        """
        current_time = pygame.time.get_ticks() / 1000.0
        # Locals — atalho mais rápido que atributo/global em Python hot loops.
        twinkle_phase = current_time * self.star_twinkle_speed
        # Floor de 0.25 garante que estrelas existem mesmo de dia (apenas
        # discretas); 1.0 é o brilho máximo na noite.
        brightness_mult = 0.25 + self._current_progress * 0.75
        max_level = self.STAR_ALPHA_LEVELS - 1
        level_factor = max_level / 255.0
        sin = math.sin
        blit = surface.blit

        for star in self.stars:
            alpha_factor = (sin(twinkle_phase + star["delay"]) + 1) * 0.5
            alpha = (
                star["base_alpha"] * (0.3 + alpha_factor * 0.7) * brightness_mult * 255
            )
            level = int(alpha * level_factor + 0.5)
            if level <= 0:
                continue
            if level > max_level:
                level = max_level
            blit(star["variants"][level], (int(star["x"]), int(star["y"])))

    def _create_sun(self) -> None:
        """Cria superfície do sol com brilho pré-renderizado."""
        sun_size = 160
        sun_center_x = self.width // 2
        sun_center_y = self.height - int(self.height * 0.5)

        self.sun_rect = pygame.Rect(
            sun_center_x - sun_size // 2,
            sun_center_y - sun_size // 2,
            sun_size,
            sun_size,
        )

        # Pré-renderizar o sol com todos os efeitos
        self.sun_surface = _optimize_alpha_surface(self._render_sun(sun_size))

    def _render_sun(self, size: int) -> pygame.Surface:
        """Renderiza o sol com gradiente radial otimizado."""
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = size // 2
        radius = size // 2

        # Cores do sol
        sun_inner = (255, 220, 163)  # Cor interna (mais clara)
        sun_outer = (255, 189, 102)  # Cor externa (mais escura)

        # Desenha o gradiente radial de fora para dentro (otimizado: passo de 2 em 2)
        for r in range(radius, 0, -2):
            t = r / radius
            # Interpolação quadrática para transição mais suave
            t_smooth = t * t

            color = tuple(
                int(sun_inner[c] + (sun_outer[c] - sun_inner[c]) * t_smooth)
                for c in range(3)
            )

            pygame.draw.circle(surf, color, (center, center), r)

        return surf

    def _create_clouds(self) -> None:
        """Cria nuvens em duas camadas."""
        cloud_color = (200, 200, 220)

        # Camada de fundo (mais lentas)
        for _ in range(self.NUM_CLOUDS_BACK):
            self.clouds_back.append(
                Cloud(
                    self.width, self.height, (10, 30), cloud_color, is_back_layer=True
                )
            )

        # Camada da frente (mais rápidas)
        for _ in range(self.NUM_CLOUDS_FRONT):
            self.clouds_front.append(
                Cloud(
                    self.width, self.height, (40, 70), cloud_color, is_back_layer=False
                )
            )

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza animação do parallax e elementos."""
        # Atualizar camadas
        for layer in self.layers:
            layer.offset += layer.speed * dt * speed_mult
            # Wrap via módulo — evita acúmulo de float e mantém offset em [0, layer_w)
            layer.offset %= layer.surface.get_width()

        # Atualizar nuvens — iterar sem criar lista temporária
        for cloud in self.clouds_back:
            cloud.update(dt, speed_mult)
        for cloud in self.clouds_front:
            cloud.update(dt, speed_mult)

        # Ciclo contínuo dia/noite com fases distintas.
        # Se o ciclo estiver pausado (boss ativo), não avança o tempo.
        if not self._pause_day_night_cycle:
            self._phase_elapsed_time += dt * speed_mult

        if self._phase == "day":
            if self._phase_elapsed_time >= self._day_duration:
                self._phase = "sunset"
                self._phase_elapsed_time = 0.0
            else:
                self._current_progress = 0.0

        elif self._phase == "sunset":
            if self._phase_elapsed_time >= self._sunset_duration:
                self._phase = "night"
                self._phase_elapsed_time = 0.0
                self._current_progress = 1.0
            else:
                # Interpola de 0 a 1 durante o anoitecer
                t = self._phase_elapsed_time / self._sunset_duration
                self._current_progress = t

        elif self._phase == "night":
            if self._phase_elapsed_time >= self._night_duration:
                self._phase = "sunrise"
                self._phase_elapsed_time = 0.0
            else:
                self._current_progress = 1.0

        elif self._phase == "sunrise":
            if self._phase_elapsed_time >= self._sunrise_duration:
                self._phase = "day"
                self._phase_elapsed_time = 0.0
                self._current_progress = 0.0
            else:
                # Interpola de 1 a 0 durante o amanhecer
                t = self._phase_elapsed_time / self._sunrise_duration
                self._current_progress = 1.0 - t

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha todos os elementos do background."""
        progress = self._current_progress
        display_progress = self._ease_progress(progress)
        # Skip de blits nos extremos: full-day usa apenas warm, full-night
        # usa apenas night. Evita um blit fullscreen quando não há mistura.
        if progress <= 0.001:
            if self.sky_warm_gradient:
                surface.blit(self.sky_warm_gradient, (0, 0))
        elif progress >= 0.999:
            if self.sky_night_gradient:
                self.sky_night_gradient.set_alpha(255)
                surface.blit(self.sky_night_gradient, (0, 0))
        else:
            if self.sky_warm_gradient:
                surface.blit(self.sky_warm_gradient, (0, 0))
            if self.sky_night_gradient:
                self.sky_night_gradient.set_alpha(int(progress * 255))
                surface.blit(self.sky_night_gradient, (0, 0))

        # Desenhar estrelas (brilho escalado em _draw_stars conforme o progresso)
        self._draw_stars(surface)

        # Desenhar nuvens de fundo
        for cloud in self.clouds_back:
            cloud.draw(surface)

        # Desenhar sol: fade out + desliza para baixo conforme escurece.
        if self.sun_surface and self.sun_rect:
            sun_alpha = int((1.0 - display_progress) * 255)
            if sun_alpha > 0:
                self.sun_surface.set_alpha(sun_alpha)
                offset_y = int(display_progress * self._sun_dive_distance)
                surface.blit(self.sun_surface, self.sun_rect.move(0, offset_y))

        # Desenhar camadas de montanhas (parallax) — dimensões cacheadas em LayerData.
        blit = surface.blit
        for layer in self.layers:
            layer_w = layer.width
            x_offset = -(int(layer.offset) % layer_w)
            blit(layer.surface, (x_offset, layer.y_pos))
            if x_offset != 0:
                blit(layer.surface, (x_offset + layer_w, layer.y_pos))

        # Desenhar nuvens da frente
        for cloud in self.clouds_front:
            cloud.draw(surface)

    def reset(self) -> None:
        """Reseta para estado inicial."""
        for layer in self.layers:
            layer.offset = 0.0

        for cloud in self.clouds_back:
            cloud.reset(is_first_time=True)
        for cloud in self.clouds_front:
            cloud.reset(is_first_time=True)

        # Reseta o ciclo dia/noite
        self._phase = "day"
        self._phase_elapsed_time = 0.0
        self._current_progress = 0.0


class CityBackground(Background):
    """Background de cidade cyberpunk."""

    # Constantes
    NUM_BUILDINGS = 12
    WINDOW_SIZE = (12, 20)
    WINDOW_SPACING = 25
    BLINK_SPEED = 1.5

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.buildings: List[Dict[str, Any]] = []
        self.blink_timer: float = 0.0
        self._create_buildings()

    def _create_buildings(self) -> None:
        """Gera prédios com propriedades variadas."""
        neon_colors = [
            (0, 255, 255),  # Ciano
            (255, 0, 255),  # Magenta
            (255, 255, 0),  # Amarelo
            (0, 255, 127),  # Verde neon
        ]

        x_pos = 0
        min_spacing = 20

        for _ in range(self.NUM_BUILDINGS):
            width = random.randint(80, 180)
            height = random.randint(200, 500)

            self.buildings.append(
                {
                    "x": x_pos,
                    "y": self.height - height,
                    "width": width,
                    "height": height,
                    "color": (
                        random.randint(20, 40),
                        random.randint(20, 40),
                        random.randint(40, 60),
                    ),
                    "neon_color": random.choice(neon_colors),
                }
            )

            x_pos += width + min_spacing

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza timer de piscar."""
        self.blink_timer += dt * self.BLINK_SPEED * speed_mult

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha cidade com janelas piscantes."""
        # Fundo escuro
        surface.fill((10, 10, 20))

        window_w, window_h = self.WINDOW_SIZE
        spacing = self.WINDOW_SPACING
        blink_time = int(self.blink_timer * 100)

        for bldg in self.buildings:
            x, y = bldg["x"], bldg["y"]

            # Corpo do prédio
            pygame.draw.rect(
                surface, bldg["color"], (x, y, bldg["width"], bldg["height"])
            )

            # Borda neon
            pygame.draw.rect(
                surface, bldg["neon_color"], (x, y, bldg["width"], bldg["height"]), 2
            )

            # Desenhar janelas de forma otimizada
            self._draw_windows(
                surface,
                x,
                y,
                bldg["width"],
                bldg["height"],
                window_w,
                window_h,
                spacing,
                blink_time,
            )

    def _draw_windows(
        self,
        surface: pygame.Surface,
        bldg_x: int,
        bldg_y: int,
        bldg_width: int,
        bldg_height: int,
        window_w: int,
        window_h: int,
        spacing: int,
        blink_time: int,
    ) -> None:
        """Desenha janelas com padrão de piscar otimizado."""
        lit_color = (255, 255, 200)
        dark_color = (40, 40, 60)

        y_start = bldg_y + 30
        y_end = bldg_y + bldg_height - 30
        x_start = bldg_x + 15
        x_end = bldg_x + bldg_width - 15

        for wy in range(y_start, y_end, spacing + window_h):
            for wx in range(x_start, x_end, spacing):
                color = (
                    lit_color
                    if (blink_time + (wx + wy) % 100) % 200 < 150
                    else dark_color
                )
                pygame.draw.rect(surface, color, (wx, wy, window_w, window_h))

    def reset(self) -> None:
        """Reseta cidade para estado inicial."""
        self.buildings.clear()
        self.blink_timer = 0.0
        self._create_buildings()


class VolcanicBackground(Background):
    """Background vulcânico com lava e brasas."""

    # Constantes
    NUM_LAVA_POOLS = 3
    NUM_EMBERS = 40
    WAVE_SPEED = 2.0
    LAVA_RESOLUTION = 20  # Pontos de amostragem para ondas

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.lava_pools: List[Dict[str, Any]] = []
        self.embers: List[Dict[str, Any]] = []
        self.wave_offset: float = 0.0

        # Pré-alocar listas de pontos para evitar realocações
        self._lava_points_cache: List[List[Tuple[int, int]]] = [
            [] for _ in range(self.NUM_LAVA_POOLS)
        ]

        self._create_lava()
        self._create_embers()

    def _create_lava(self) -> None:
        """Cria pools de lava otimizados."""
        for _ in range(self.NUM_LAVA_POOLS):
            self.lava_pools.append(
                {
                    "y": self.height - random.randint(50, 150),
                    "amplitude": random.randint(5, 15),
                    "frequency": random.uniform(0.5, 1.5),
                    "phase": random.uniform(0, 6.28),
                }
            )

    def _create_embers(self) -> None:
        """Cria partículas de brasa."""
        for _ in range(self.NUM_EMBERS):
            self.embers.append(
                {
                    "x": random.randint(0, self.width),
                    "y": random.randint(0, self.height),
                    "speed": random.uniform(20, 80),
                    "size": random.randint(2, 5),
                    "brightness": random.uniform(0.5, 1.0),
                }
            )

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza animação de lava e brasas."""
        self.wave_offset += dt * self.WAVE_SPEED * speed_mult

        # Atualizar brasas
        for ember in self.embers:
            ember["y"] -= ember["speed"] * dt * speed_mult

            # Resetar se sair da tela
            if ember["y"] < -10:
                ember["y"] = self.height + 10
                ember["x"] = random.randint(0, self.width)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha cenário vulcânico otimizado."""
        # Fundo escuro avermelhado
        surface.fill((30, 10, 10))

        # Desenhar lava com ondulação
        for pool in self.lava_pools:
            points = self._calculate_lava_wave(pool)

            if len(points) >= 3:
                # Preenchimento
                pygame.draw.polygon(surface, (200, 50, 0), points)
                # Borda brilhante
                pygame.draw.polygon(surface, (255, 100, 0), points, 3)

        # Desenhar brasas
        for ember in self.embers:
            brightness = int(255 * ember["brightness"])
            color = (brightness, brightness // 3, 0)
            pygame.draw.circle(
                surface, color, (int(ember["x"]), int(ember["y"])), ember["size"]
            )

    def _calculate_lava_wave(self, pool: Dict[str, Any]) -> List[Tuple[int, int]]:
        """Calcula pontos da onda de lava de forma otimizada."""
        points: List[Tuple[int, int]] = []

        # Usar resolução fixa para melhor performance
        for x in range(0, self.width, self.LAVA_RESOLUTION):
            wave = math.sin(
                (x * pool["frequency"] / 100)
                + (self.wave_offset * pool["frequency"])
                + pool["phase"]
            )
            y = pool["y"] + wave * pool["amplitude"]
            points.append((x, int(y)))

        # Fechar o polígono
        points.append((self.width, self.height))
        points.append((0, self.height))

        return points

    def reset(self) -> None:
        """Reseta vulcão para estado inicial."""
        self.lava_pools.clear()
        self.embers.clear()
        self.wave_offset = 0.0
        self._lava_points_cache = [[] for _ in range(self.NUM_LAVA_POOLS)]
        self._create_lava()
        self._create_embers()


class VerticalCloud:
    """Nuvem que se move verticalmente para a fase de atmosfera."""

    def __init__(
        self,
        width: int,
        height: int,
        speed_range: Tuple[float, float],
        color: Tuple[int, int, int],
        is_entering: bool,
    ):
        self.screen_width = width
        self.screen_height = height
        self.speed_range = speed_range
        self.color = color
        self.is_entering = is_entering

        # Surface inicial
        self.scaled_surface = pygame.Surface((1, 1), pygame.SRCALPHA)
        self.reset(is_first_time=True)

    def _generate_cloud_surface(self) -> pygame.Surface:
        w, h = random.randint(150, 350), random.randint(80, 180)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        # Desenha várias elipses sobrepostas para dar volume
        for _ in range(5):
            ew = random.randint(w // 2, w)
            eh = random.randint(h // 2, h)
            ex = random.randint(0, w - ew)
            ey = random.randint(0, h - eh)
            alpha = random.randint(40, 100)
            pygame.draw.ellipse(surf, (*self.color, alpha), (ex, ey, ew, eh))
        return _optimize_alpha_surface(surf)

    def reset(self, is_first_time: bool = False) -> None:
        # Regenera a superfície para cada reset para maior variedade visual
        base_surface = self._generate_cloud_surface()
        
        scale = random.uniform(0.6, 1.4)
        self.scaled_surface = pygame.transform.smoothscale(
            base_surface,
            (
                int(base_surface.get_width() * scale),
                int(base_surface.get_height() * scale),
            ),
        )

        self.x = random.uniform(-50, self.screen_width - 100)
        
        # Para um efeito orgânico de "entrar" na camada de nuvens, 
        # as nuvens SEMPRE começam fora da tela e entram nela.
        # Usamos um range maior no primeiro spawn para elas não entrarem todas juntas.
        stagger = random.randint(20, 800) if is_first_time else random.randint(20, 150)
        
        if self.is_entering: # Sobe (spawn embaixo)
            self.y = self.screen_height + stagger
        else: # Desce (spawn em cima)
            self.y = -self.scaled_surface.get_height() - stagger

        self.speed = random.uniform(self.speed_range[0], self.speed_range[1])

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        # Direção: -1 se entering (sobe), 1 se exiting (desce)
        direction = -1.0 if self.is_entering else 1.0
        self.y += direction * self.speed * dt * speed_mult

        if self.is_entering:
            if self.y < -self.scaled_surface.get_height():
                self.reset()
        else:
            if self.y > self.screen_height:
                self.reset()

    def draw(self, surface: pygame.Surface, alpha_mult: float = 1.0) -> None:
        if alpha_mult <= 0:
            return

        # Calcula um fade local para evitar "pop" nas bordas de spawn
        # Quando está perto da borda de spawn, o alpha diminui
        edge_fade = 1.0
        fade_margin = 100.0
        
        if self.is_entering: # Sobe (spawn em screen_height)
            dist_to_spawn = (self.screen_height - self.y)
            if dist_to_spawn < fade_margin:
                edge_fade = max(0.0, dist_to_spawn / fade_margin)
        else: # Desce (spawn em -height)
            cloud_h = self.scaled_surface.get_height()
            dist_to_spawn = (self.y + cloud_h)
            if dist_to_spawn < fade_margin:
                edge_fade = max(0.0, dist_to_spawn / fade_margin)

        final_alpha = int(255 * alpha_mult * edge_fade)
        if final_alpha <= 0:
            return
            
        if final_alpha < 255:
            # Para SRCALPHA, set_alpha multiplica o alpha existente na blit
            self.scaled_surface.set_alpha(final_alpha)
            surface.blit(self.scaled_surface, (int(self.x), int(self.y)))
            # Importante resetar o alpha para blits futuros (ou se for reutilizada)
            self.scaled_surface.set_alpha(255)
        else:
            surface.blit(self.scaled_surface, (int(self.x), int(self.y)))


class AtmosphereStreak:
    """Riscos que simulam o vento vertical durante entrada/re-entrada."""

    def __init__(self, width: int, height: int, is_entering: bool):
        self.width = width
        self.height = height
        self.is_entering = is_entering
        self.x = 0.0
        self.y = 0.0
        self.speed = 0.0
        self.length = 0.0
        self.alpha = 0
        self.reset(is_first_time=True)

    def reset(self, is_first_time: bool = False) -> None:
        self.x = random.uniform(0, self.width)
        self.length = random.uniform(60, 180)
        self.speed = random.uniform(1400, 2200)
        self.alpha = random.randint(40, 110)

        # Para um efeito orgânico, sempre começa fora da tela.
        # Stagger inicial para não entrarem todos em uma linha só.
        stagger = random.uniform(20, 1200) if is_first_time else random.uniform(20, 150)

        if self.is_entering:  # Sobe (spawn embaixo)
            self.y = self.height + stagger
        else:  # Desce (spawn em cima)
            self.y = -self.length - stagger

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        direction = -1.0 if self.is_entering else 1.0
        self.y += direction * self.speed * dt * speed_mult

        if self.is_entering:
            # Margem maior para o reset quando esticado
            if self.y + self.length < -400:
                self.reset()
        else:
            if self.y > self.height + 400:
                self.reset()

    def draw(
        self, surface: pygame.Surface, global_alpha: float = 1.0, speed_mult: float = 1.0
    ) -> None:
        alpha = int(self.alpha * global_alpha)
        if alpha <= 0:
            return

        # Estica o rastro proporcionalmente à velocidade
        # Para speed_mult=30x, o rastro fica bem longo para dar sensação de warp
        stretch_factor = 1.0 + (speed_mult - 1.0) * 0.4
        draw_length = self.length * stretch_factor

        # Desenha o rastro como uma linha vertical branca com alpha
        # Se is_entering (sobe), o rastro "estica" para baixo a partir de y
        if self.is_entering:
            start_pos = (int(self.x), int(self.y + draw_length))
            end_pos = (int(self.x), int(self.y))
        else:
            start_pos = (int(self.x), int(self.y))
            end_pos = (int(self.x), int(self.y + draw_length))

        # Linha principal
        pygame.draw.line(surface, (255, 255, 255, alpha), start_pos, end_pos, 1)


class AtmosphereBackground(Background):
    """Background para transição de atmosfera com transição de cor e nuvens."""

    def __init__(self, width: int, height: int, route: str = "exiting"):
        super().__init__(width, height)
        self.route = route
        self.is_entering = route == "entering"
        self.progress: float = 0.0
        self.last_speed_mult: float = 1.0

        # Cores: [Space (Dark)] <-> [Sky (Cyan/Blue)]
        # Exiting: progress 0 (Sky) -> progress 1 (Space)
        # Entering: progress 0 (Space) -> progress 1 (Sky)
        self.color_space_top = (5, 8, 15)
        self.color_space_bottom = (15, 25, 45)
        self.color_sky_top = (30, 100, 180)
        self.color_sky_bottom = (120, 200, 255)

        self.clouds: List[VerticalCloud] = []
        for _ in range(12):
            self.clouds.append(
                VerticalCloud(
                    width, height, (100, 250), (220, 230, 255), self.is_entering
                )
            )

        self.streaks: List[AtmosphereStreak] = []
        for _ in range(25):
            self.streaks.append(AtmosphereStreak(width, height, self.is_entering))

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(1.0, progress))

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        self.last_speed_mult = speed_mult
        # A densidade de nuvens e velocidade pode mudar com o progresso
        # mas por ora mantemos fixo para fluidez.
        for cloud in self.clouds:
            cloud.update(dt, speed_mult)

        for streak in self.streaks:
            streak.update(dt, speed_mult)

    def draw(self, surface: pygame.Surface) -> None:
        # Calcula cores atuais baseadas no progresso e rota
        # Exiting: p=0 (Atmo), p=1 (Space) -> t = progress
        # Entering: p=0 (Space), p=1 (Atmo) -> t = 1 - progress
        t = self.progress if self.route == "exiting" else 1.0 - self.progress

        c_top: tuple[int, int, int] = (
            int(self.color_sky_top[0] * (1 - t) + self.color_space_top[0] * t),
            int(self.color_sky_top[1] * (1 - t) + self.color_space_top[1] * t),
            int(self.color_sky_top[2] * (1 - t) + self.color_space_top[2] * t),
        )
        c_bottom: tuple[int, int, int] = (
            int(self.color_sky_bottom[0] * (1 - t) + self.color_space_bottom[0] * t),
            int(self.color_sky_bottom[1] * (1 - t) + self.color_space_bottom[1] * t),
            int(self.color_sky_bottom[2] * (1 - t) + self.color_space_bottom[2] * t),
        )

        # Desenha gradiente de fundo
        self._draw_gradient(surface, c_top, c_bottom)

        # Intensidade do efeito de vento/nuvens baseada na proximidade com a atmosfera
        # t=0 (Atmosphere), t=1 (Space)
        effect_intensity = 1.0 - (t * 0.8)

        # Desenha nuvens (alpha/densidade proporcional à proximidade com a atmosfera)
        cloud_alpha_base = effect_intensity
        for i, cloud in enumerate(self.clouds):
            # Algumas nuvens somem primeiro
            individual_alpha = max(0.0, cloud_alpha_base - (i % 4) * 0.15)
            if individual_alpha > 0:
                cloud.draw(surface, individual_alpha)

        # Desenha riscos de vento
        streak_global_alpha = effect_intensity
        for streak in self.streaks:
            streak.draw(surface, streak_global_alpha, self.last_speed_mult)

    def _draw_gradient(
        self,
        surface: pygame.Surface,
        top: tuple[int, int, int],
        bottom: tuple[int, int, int],
    ) -> None:
        """Desenha gradiente vertical."""
        # Otimização: desenha em uma surface pequena e escala
        grad = pygame.Surface((1, 2), pygame.SRCALPHA)
        grad.set_at((0, 0), top)
        grad.set_at((0, 1), bottom)
        surface.blit(
            pygame.transform.smoothscale(grad, (self.width, self.height)), (0, 0)
        )

    def reset(self) -> None:
        self.progress = 0.0
        self.last_speed_mult = 1.0
        for cloud in self.clouds:
            cloud.reset(is_first_time=True)
        for streak in self.streaks:
            streak.reset(is_first_time=True)


# Factory function para facilitar criação
def create_background(bg_type: str, width: int, height: int, **kwargs: Any) -> Background:
    """
    Cria um background baseado no tipo especificado.

    Args:
        bg_type: Tipo do background ('mountains', 'city', 'volcanic', 'atmosphere')
        width: Largura da tela
        height: Altura da tela
        **kwargs: Argumentos extras (ex: route para atmosphere)

    Returns:
        Instância do background apropriado

    Raises:
        ValueError: Se o tipo de background não for válido
    """
    backgrounds: Dict[str, Type[Background]] = {
        "mountains": MountainsBackground,
        "city": CityBackground,
        "volcanic": VolcanicBackground,
        "atmosphere": AtmosphereBackground,
    }

    bg_class = backgrounds.get(bg_type.lower())
    if bg_class is None:
        raise ValueError(
            f"Tipo de background inválido: {bg_type}. "
            f"Tipos válidos: {', '.join(backgrounds.keys())}"
        )

    if bg_class is AtmosphereBackground:
        route = cast(str, kwargs.get("route", "exiting"))
        return AtmosphereBackground(width, height, route=route)

    return bg_class(width, height)
