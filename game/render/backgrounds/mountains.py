"""Background de Montanhas: parallax com picos rochosos e nuvens."""

import math
import random
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .base import Background, optimize_alpha_surface, optimize_surface


class ColorPalette:
    """Paleta de cores para camadas de montanha."""

    def __init__(self, light: Tuple[int, int, int], dark: Tuple[int, int, int]) -> None:
        self.light: Tuple[int, int, int] = light
        self.dark: Tuple[int, int, int] = dark


class LayerData:
    """Dados de uma camada de parallax.

    A surface da camada é trimada nas regiões irrelevantes e dividida em
    duas faixas para otimização de fillrate:

    - ``top_surface``: faixa SRCALPHA com a silhueta jagged. Posicionada em
      ``y_pos + top_y_offset``. A região acima de ``highest_y`` (que seria
      100% transparente) **não** é blittada.
    - ``bot_surface``: faixa OPACA com a área totalmente preenchida abaixo do
      pico mais baixo. Posicionada em ``y_pos + bot_y_offset``. Blit opaco
      é ~2x mais rápido que SRCALPHA em pygame.

    ``bot_surface`` pode ser ``None`` em layers degenerados (silhueta encosta
    na base).
    """

    def __init__(
        self,
        top_surface: pygame.Surface,
        bot_surface: Optional[pygame.Surface],
        top_y_offset: int,
        bot_y_offset: int,
        speed: float,
        offset: float = 0.0,
        y_pos: int = 0,
    ) -> None:
        self.top_surface: pygame.Surface = top_surface
        self.bot_surface: Optional[pygame.Surface] = bot_surface
        self.top_y_offset: int = top_y_offset
        self.bot_y_offset: int = bot_y_offset
        self.speed: float = speed
        self.offset: float = offset
        # Dimensões cacheadas — evitam get_width/get_height por frame
        self.width: int = top_surface.get_width()
        self.height: int = bot_y_offset + (
            bot_surface.get_height() if bot_surface is not None else 0
        )
        self.y_pos: int = y_pos


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
            Cloud._surface_cache[cache_key] = optimize_alpha_surface(
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
        self.scaled_surface = optimize_alpha_surface(
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

        # Surface opaca com o céu warm+night já composto. Recomposta apenas
        # quando o alpha do night muda em 0..255. Como o progresso varia
        # ~0,00003/frame durante transições de 10 min, a maioria dos frames
        # reaproveita o cache — 1 blit fullscreen opaco no lugar de 2 SRCALPHA.
        self._sky_composited: Optional[pygame.Surface] = None
        self._sky_composited_alpha: int = -1

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

        # Web (WASM): a meia-resolução já corta fillrate, mas NÃO reduz o número
        # de chamadas de blit nem o custo do loop Python por frame — que no pygbag
        # é o gargalo real. Estrelas e nuvens são muitos blits SRCALPHA pequenos;
        # reduzir a contagem (e o twinkle a 30 Hz) poupa esse custo com impacto
        # visual mínimo em meia-res. As 6 camadas de parallax ficam intactas.
        import sys as _sys

        self._is_web: bool = _sys.platform == "emscripten"
        self._twinkle_tick: int = 0
        if self._is_web:
            self.NUM_STARS = 16
            self.NUM_CLOUDS_BACK = 2
            self.NUM_CLOUDS_FRONT = 1

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
        self.sky_warm_gradient = optimize_surface(
            self._render_sky_gradient(warm_colors, stops)
        )
        self.sky_night_gradient = optimize_surface(
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
            top_raw, bot_raw, top_y_offset, bot_y_offset = (
                self._generate_mountain_surface(
                    self.PALETTES[i],
                    self.PEAKS_COUNTS[i],
                    self.ROUGHNESS_VALUES[i],
                    self.HEIGHT_PERCENTAGES[i],
                )
            )
            top_surface = optimize_alpha_surface(top_raw)
            bot_surface = optimize_surface(bot_raw) if bot_raw is not None else None

            # Altura total considera a posição original da layer (do topo do
            # surf_height original até a base da tela), não o tamanho dos
            # strips — a região acima de top_y_offset era transparente e
            # continua "ausente" sem mudar o alinhamento visual.
            total_h = bot_y_offset + (
                bot_raw.get_height() if bot_raw is not None else 0
            )

            self.layers.append(
                LayerData(
                    top_surface=top_surface,
                    bot_surface=bot_surface,
                    top_y_offset=top_y_offset,
                    bot_y_offset=bot_y_offset,
                    speed=self.LAYER_SPEEDS[i] * speed_multiplier,
                    offset=0.0,
                    y_pos=self.height - total_h,
                )
            )

    def _generate_mountain_surface(
        self, palette: ColorPalette, peaks: int, roughness: int, h_pct: float
    ) -> Tuple[pygame.Surface, Optional[pygame.Surface], int, int]:
        """Cria superfícies otimizadas da montanha com gradiente.

        Retorna ``(top_surf, bot_surf, top_y_offset, bot_y_offset)``:
        - ``top_surf`` SRCALPHA com a silhueta jagged (de y=top_y_offset a
          y=bot_y_offset). Acima do pico mais alto é 100% transparente,
          então o strip é recortado para começar nesse y — economiza
          fillrate sem mudança visual.
        - ``bot_surf`` opaca com a faixa totalmente preenchida abaixo do pico
          mais baixo (de y=bot_y_offset a y=surf_height), ou ``None`` quando
          a silhueta encosta na base.
        - ``top_y_offset`` é o y onde o top strip começa (relativo à layer).
        - ``bot_y_offset`` é o y onde o bot strip começa (relativo à layer).

        Justificativa: blit opaco é ~2x mais rápido que SRCALPHA em pygame.
        Como a região abaixo do pico mais baixo está 100% preenchida e a
        região acima do pico mais alto é 100% transparente, dá pra remover
        as duas extremidades do strip SRCALPHA — só a área jagged precisa
        de blending per-pixel.
        """
        surf_height = int(self.height * h_pct)
        # Largura igual à tela — o parallax infinito é feito desenhando 2 cópias lado a lado
        surf_width = self.width

        # Criar superfície final
        final_surf = pygame.Surface((surf_width, surf_height), pygame.SRCALPHA)

        # Gerar pontos da montanha
        points = self._generate_mountain_points(
            surf_width, surf_height, peaks, roughness
        )
        silhouette_ys = [p[1] for p in points[1:-1]]  # Ignorar pontos de fechamento
        highest_y = min(silhouette_ys)
        # Pico mais BAIXO (maior y entre os pontos da silhueta) — abaixo dele
        # o polígono está totalmente preenchido.
        lowest_peak_y = max(silhouette_ys)

        # Criar gradiente (otimizado com surface lock)
        grad_surf = self._create_gradient_surface(
            surf_width, surf_height, palette, highest_y
        )

        # Aplicar máscara
        mask_surf = pygame.Surface((surf_width, surf_height), pygame.SRCALPHA)
        pygame.draw.polygon(mask_surf, (255, 255, 255, 255), points)

        final_surf.blit(grad_surf, (0, 0))
        final_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        # Limites do split com margens de segurança de 1-2px para evitar
        # artefato visível de borda entre as faixas.
        bot_y_offset = min(surf_height, max(0, lowest_peak_y + 2))
        top_y_offset = max(0, highest_y - 1)

        # Bot strip (opaca) — só vale criar se sobra área útil
        bot_h = surf_height - bot_y_offset
        if bot_h <= 1:
            bot_surf: Optional[pygame.Surface] = None
            bot_y_offset = surf_height
            bot_h = 0
        else:
            bot_surf = pygame.Surface((surf_width, bot_h))  # opaca (sem SRCALPHA)
            bot_surf.blit(final_surf, (0, -bot_y_offset))

        # Top strip (SRCALPHA) — recortado para conter só a silhueta jagged
        top_h = max(1, bot_y_offset - top_y_offset)
        top_surf = pygame.Surface((surf_width, top_h), pygame.SRCALPHA)
        top_surf.blit(final_surf, (0, -top_y_offset))

        return top_surf, bot_surf, top_y_offset, bot_y_offset

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
                variants.append(optimize_alpha_surface(surf))
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
                    # Nível de alpha cacheado — no web o twinkle recalcula a 30 Hz
                    # e reaproveita este valor nos frames intermediários.
                    "level": 0,
                }
            )

    def _draw_stars(self, surface: pygame.Surface) -> None:
        """Desenha estrelas com brilho piscante usando variants pré-renderizadas.

        O brilho geral é escalado pelo ``_current_progress`` — estrelas quase
        invisíveis no pôr do sol (0) e fortes na noite fechada (1).
        """
        blit = surface.blit
        max_level = self.STAR_ALPHA_LEVELS - 1

        # No web recalcula o twinkle a cada 2 frames (30 Hz) — o brilho é lento
        # (star_twinkle_speed=2.0), então o passo é imperceptível e poupa os
        # sin()/aritmética do loop. Os blits acontecem sempre (senão as estrelas
        # sumiriam nos frames pulados). No desktop recalcula todo frame.
        recompute = True
        if self._is_web:
            recompute = (self._twinkle_tick % 2) == 0
            self._twinkle_tick += 1

        if recompute:
            current_time = pygame.time.get_ticks() / 1000.0
            # Locals — atalho mais rápido que atributo/global em Python hot loops.
            twinkle_phase = current_time * self.star_twinkle_speed
            # Floor de 0.25 garante que estrelas existem mesmo de dia (apenas
            # discretas); 1.0 é o brilho máximo na noite.
            brightness_mult = 0.25 + self._current_progress * 0.75
            level_factor = max_level / 255.0
            sin = math.sin
            for star in self.stars:
                alpha_factor = (sin(twinkle_phase + star["delay"]) + 1) * 0.5
                alpha = (
                    star["base_alpha"]
                    * (0.3 + alpha_factor * 0.7)
                    * brightness_mult
                    * 255
                )
                level = int(alpha * level_factor + 0.5)
                if level < 0:
                    level = 0
                elif level > max_level:
                    level = max_level
                star["level"] = level

        for star in self.stars:
            level = star["level"]
            if level > 0:
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
        self.sun_surface = optimize_alpha_surface(self._render_sun(sun_size))

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
            layer.offset %= layer.width

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

        # Céu composto cacheado: recompõe warm+night apenas quando o alpha
        # discretizado em 0..255 muda. Durante sunset/sunrise (10 min),
        # 1 unidade de alpha leva ~14 frames a 60 FPS — recompõe raramente
        # e per-frame faz só 1 blit fullscreen opaco.
        if self._sky_composited is None and self.sky_warm_gradient is not None:
            self._sky_composited = optimize_surface(
                pygame.Surface((self.width, self.height))
            )

        night_alpha = max(0, min(255, int(progress * 255)))
        if (
            self._sky_composited is not None
            and night_alpha != self._sky_composited_alpha
        ):
            if night_alpha == 0:
                if self.sky_warm_gradient is not None:
                    self._sky_composited.blit(self.sky_warm_gradient, (0, 0))
            elif night_alpha == 255:
                if self.sky_night_gradient is not None:
                    self.sky_night_gradient.set_alpha(255)
                    self._sky_composited.blit(self.sky_night_gradient, (0, 0))
            else:
                if self.sky_warm_gradient is not None:
                    self._sky_composited.blit(self.sky_warm_gradient, (0, 0))
                if self.sky_night_gradient is not None:
                    self.sky_night_gradient.set_alpha(night_alpha)
                    self._sky_composited.blit(self.sky_night_gradient, (0, 0))
            self._sky_composited_alpha = night_alpha

        if self._sky_composited is not None:
            surface.blit(self._sky_composited, (0, 0))

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

        # Desenhar camadas de montanhas (parallax). Cada layer é dividida em
        # top SRCALPHA (silhueta jagged) + bot opaco (faixa cheia abaixo do
        # pico mais baixo). Blit opaco é ~2x mais rápido em pygame, então
        # mover a maior parte dos pixels para a faixa opaca reduz fillrate
        # drasticamente — gap observado de ~6 ms no Mundo 1 vs Starfield.
        blit = surface.blit
        for layer in self.layers:
            layer_w = layer.width
            x_offset = -(int(layer.offset) % layer_w)
            top_surf = layer.top_surface
            bot_surf = layer.bot_surface
            y_top = layer.y_pos + layer.top_y_offset
            y_bot = layer.y_pos + layer.bot_y_offset

            blit(top_surf, (x_offset, y_top))
            if bot_surf is not None:
                blit(bot_surf, (x_offset, y_bot))

            if x_offset != 0:
                x_wrap = x_offset + layer_w
                blit(top_surf, (x_wrap, y_top))
                if bot_surf is not None:
                    blit(bot_surf, (x_wrap, y_bot))

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
