import logging
import math
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pygame

from ..core import colors
from ..core.assets import get_font, get_image
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset
from ..core.i18n import t
from ..core.sprite_loader import sprite_loader
from ..core.world_config import WorldTheme
from .backgrounds import (
    AtmosphereBackground,
    Background,
    CelestialManager,
    CityBackground,
    MountainsBackground,
    StarField,
    StarfieldBackground,
    VolcanicBackground,
    create_background,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..entities.ship import Ship


class Renderer:
    def __init__(self):
        # Escala de UI relativa ao design base (1280×720). Resoluções ofertadas
        # são 16:9, então um único fator (largura) cobre os dois eixos. Overlays
        # in-game desenhados em pixels do design base (preparation/level_popup)
        # precisam dele para não ficarem desproporcionais fora de 720p — mesma
        # convenção dos menus e do HUD (ver memory/menu-ui-scale-convention).
        # Em 720p ui_scale == 1.0, então nada muda.
        self.ui_scale = Config.SCREEN_WIDTH / 1280.0

        self.font_small = get_font(max(8, int(12 * self.ui_scale)))
        self.font_medium = get_font(max(8, int(24 * self.ui_scale)))
        self.font_large = get_font(max(8, int(32 * self.ui_scale)))

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

        # Background dinâmico. O starfield agora é um Background como os demais
        # (StarfieldBackground), mantido como instância persistente: é o default
        # e as cenas de menu desenham as estrelas direto via a property
        # `starfield`. Sem flag especial — o fluxo de desenho é uniforme.
        self._starfield_bg = StarfieldBackground(
            Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        )
        self.current_background: Background = self._starfield_bg
        self.current_theme: Optional[WorldTheme] = None

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

    def _s(self, value: float) -> int:
        """Escala um valor de pixel do design base (1280×720) para a resolução
        lógica atual. Em 720p retorna o valor original (ui_scale == 1.0)."""
        return int(value * self.ui_scale)

    @property
    def starfield(self) -> StarField:
        """Campo de estrelas do fundo-base — desenhado direto pelas cenas de menu."""
        return self._starfield_bg.starfield

    @property
    def celestial_manager(self) -> CelestialManager:
        return self._starfield_bg.celestial_manager

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
        elif theme == WorldTheme.CITY:
            self.current_background = CityBackground(
                Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
            )
        elif theme == WorldTheme.VOLCANIC:
            self.current_background = VolcanicBackground(
                Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
            )
        else:  # STARFIELD ou PROCEDURAL
            self.current_background = self._starfield_bg

    def set_atmosphere_mode(self, route: str) -> None:
        """Configura o background para a fase de atmosfera."""
        if (
            isinstance(self.current_background, AtmosphereBackground)
            and self.current_background.route == route
        ):
            return

        self.current_background = create_background(
            "atmosphere", Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT, route=route
        )
        self.current_theme = None
        logger.info("[RENDERER] Background de atmosfera ativado: %s", route)

    def background(
        self,
        surface: pygame.Surface,
        dt: float,
        speed_multiplier: float = 1.0,
        draw_celestials: bool = True,
        atmosphere_progress: float = 0.0,
    ):
        surface.fill(colors.BLACK)

        # Fluxo único: todo tema é um Background. Os hooks abaixo são no-op na
        # base e só fazem efeito onde importam (spawn de celestiais no starfield,
        # progresso na atmosfera) — sem if/else nem isinstance (§5).
        bg = self.current_background
        bg.set_allow_spawning(draw_celestials)
        bg.set_progress(atmosphere_progress)
        bg.update(dt, speed_multiplier)
        bg.draw(surface)

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
            "score", score, t("hud.score"), self.font_medium, colors.WHITE
        )
        lives_surf = self._render_text_cached(
            "lives", lives, t("hud.lives"), self.font_medium, colors.WHITE
        )

        # MODIFICADO: Mostrar estágio formatado (ex: "2-5" ao invés de "Fase: 15")
        lvl = self.font_medium.render(t("hud.stage", n=level_display), True, colors.WHITE)

        e = self._render_text_cached(
            "enemies", enemies_destroyed, t("hud.enemies"), self.font_small, colors.WHITE
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
            difficulty_color = {
                DifficultyPreset.CASUAL: colors.GREEN,
                DifficultyPreset.NORMAL: colors.YELLOW,
                DifficultyPreset.HARDCORE: colors.ORANGE,
                DifficultyPreset.NIGHTMARE: colors.RED,
            }.get(difficulty_preset, colors.WHITE)

            diff_text = self._render_text_cached(
                "difficulty",
                difficulty_preset.value,  # Valor do enum — estável e sem risco de colisão
                t(
                    "hud.difficulty",
                    name=t(f"difficulty.{difficulty_preset.value}.name"),
                ),
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
                surf = self.font_small.render(txt, True, color)
                surface.blit(surf, (10, y))
                y += 18

            invuln_s = ship.get_invulnerable_time()
            ds_s = ship.get_double_shot_time()
            sp_s = ship.get_speed_boost_time()

            if invuln_s > 0:
                line(t("hud.effect.shield", sec=f"{invuln_s:.1f}"), colors.BLUE)
            if ds_s > 0:
                line(t("hud.effect.double", sec=f"{ds_s:.1f}"), colors.GREEN)
            if sp_s > 0:
                line(t("hud.effect.speed", sec=f"{sp_s:.1f}"), colors.YELLOW)

            # Mostrar multiplicador de score se ativo
            if score_multiplier_active and score_multiplier_timer > 0:
                line(t("hud.effect.score", sec=f"{score_multiplier_timer:.1f}"), colors.YELLOW)

            # Mostrar mini ships se ativo
            if mini_ships_active and mini_ships_timer > 0:
                line(t("hud.effect.mini", sec=f"{mini_ships_timer:.1f}"), colors.CYAN)

            # Mostrar tiros explosivos restantes
            if explosive_shots_active and explosive_shots_remaining > 0:
                # Piscar quando restarem 5 ou menos cargas
                if explosive_shots_remaining <= 5:
                    blink = int(time.time() * 4) % 2 == 0
                    color = colors.ORANGE if blink else colors.RED
                else:
                    color = colors.ORANGE
                line(t("hud.effect.explosive", n=explosive_shots_remaining), color)

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
        anim_t = pygame.time.get_ticks() / 1000.0

        # Parâmetros de animação de saída
        exit_anim_active = remaining <= 0
        exit_progress = min(1.0, abs(remaining) / 1.0) if exit_anim_active else 0.0
        global_alpha = int(255 * (1.0 - exit_progress))
        exit_scale = 1.0 + exit_progress * 1.5  # Expande conforme some

        # 1. Painel de fundo sutil com gradiente otimizado
        panel_h = self._s(240)
        panel_y = Config.SCREEN_HEIGHT // 2 - panel_h // 2

        # grad_w é só a resolução interna de amostragem do gradiente (é
        # esticado para a largura da tela depois) — independe da resolução.
        grad_w = 200
        # Altura 2 (não 1): ao expandir na vertical, o smoothscale interpola com
        # a linha vizinha; uma origem de 1px de altura faz o filtro ler a linha
        # seguinte (inexistente) → leitura fora dos limites → access violation
        # intermitente no Windows (depende do layout de heap). O gradiente varia
        # só na horizontal, então duplicar a linha é visualmente idêntico e
        # seguro — mesmo padrão do gradiente em render/backgrounds/atmosphere.py.
        grad_surf = pygame.Surface((grad_w, 2), pygame.SRCALPHA)
        for x in range(grad_w):
            dist_center = abs(x - grad_w // 2)
            alpha = max(
                0,
                int(140 * (1.0 - exit_progress))
                - int(dist_center * (140 / (grad_w // 2))),
            )
            if alpha > 0:
                grad_surf.set_at((x, 0), (0, 0, 0, alpha))
                grad_surf.set_at((x, 1), (0, 0, 0, alpha))

        overlay = pygame.transform.smoothscale(
            grad_surf, (Config.SCREEN_WIDTH, panel_h)
        )
        surface.blit(overlay, (0, panel_y))

        # Fontes (escaladas)
        warning_font = get_font(max(8, int(Config.WARNING_FONT_SIZE * self.ui_scale)))
        info_font = get_font(max(8, int(24 * self.ui_scale)))
        diff_font = get_font(max(8, int(18 * self.ui_scale)))

        # 2. Nome do Estágio (Acima do contador)
        if stage_name:
            st_alpha = int((180 + int(75 * math.sin(anim_t * 3))) * (1.0 - exit_progress))
            st_surf = info_font.render(stage_name, True, colors.CUSTOM_GOLD)
            st_surf.set_alpha(st_alpha)
            surface.blit(
                st_surf,
                (
                    Config.SCREEN_WIDTH // 2 - st_surf.get_width() // 2,
                    Config.SCREEN_HEIGHT // 2 - self._s(95) - int(exit_progress * self._s(40)),
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
            ct_base = warning_font.render(t("hud.combat"), True, colors.YELLOW)
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
            d_color = {
                DifficultyPreset.CASUAL: colors.GREEN,
                DifficultyPreset.NORMAL: colors.YELLOW,
                DifficultyPreset.HARDCORE: colors.ORANGE,
                DifficultyPreset.NIGHTMARE: colors.RED,
            }.get(difficulty, colors.WHITE)

            d_surf = diff_font.render(
                t(
                    "hud.difficulty_prep",
                    name=t(f"difficulty.{difficulty.value}.name").upper(),
                ),
                True,
                d_color,
            )
            d_surf.set_alpha(global_alpha)

            dx = Config.SCREEN_WIDTH // 2 - d_surf.get_width() // 2
            dy = Config.SCREEN_HEIGHT // 2 + self._s(70) + int(exit_progress * self._s(40))

            # Linhas decorativas laterais
            line_w = self._s(60)
            line_gap = self._s(10)
            line_y = dy + self._s(12)
            l_alpha = global_alpha
            pygame.draw.line(
                surface,
                (*d_color, l_alpha),
                (dx - line_w - line_gap, line_y),
                (dx - line_gap, line_y),
                2,
            )
            pygame.draw.line(
                surface,
                (*d_color, l_alpha),
                (dx + d_surf.get_width() + line_gap, line_y),
                (dx + d_surf.get_width() + line_w + line_gap, line_y),
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
        slide_hidden = -self._s(60)  # posição inicial acima do topo
        slide_travel = self._s(80)  # distância percorrida no slide
        if timer > duration - slide_duration:
            # Entrada
            progress = (duration - timer) / slide_duration
            y_offset = slide_hidden + slide_travel * (1.0 - (1.0 - progress) ** 3)
        elif timer < slide_duration:
            # Saída
            progress = timer / slide_duration
            y_offset = slide_hidden + slide_travel * progress
        else:
            # Espera
            y_offset = self._s(20)

        # Design do Pop-up
        font = get_font(max(8, int(22 * self.ui_scale)))
        txt_surf = font.render(text, True, colors.WHITE)

        box_w = txt_surf.get_width() + self._s(60)
        box_h = self._s(45)
        box_x = Config.SCREEN_WIDTH // 2 - box_w // 2
        box_y = y_offset
        radius = self._s(10)
        glow_pad = self._s(5)

        # Fundo do painel
        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (0, 0, 0, 180), (0, 0, box_w, box_h), border_radius=radius)
        pygame.draw.rect(
            panel, colors.CUSTOM_GOLD, (0, 0, box_w, box_h), 2, border_radius=radius
        )

        # Brilho sutil nas bordas
        glow = pygame.Surface((box_w + glow_pad * 2, box_h + glow_pad * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            glow,
            (218, 165, 32, 50),
            (glow_pad, glow_pad, box_w, box_h),
            border_radius=radius + self._s(2),
        )

        surface.blit(glow, (box_x - glow_pad, box_y - glow_pad))
        surface.blit(panel, (box_x, box_y))
        surface.blit(
            txt_surf, (box_x + self._s(30), box_y + (box_h - txt_surf.get_height()) // 2)
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
