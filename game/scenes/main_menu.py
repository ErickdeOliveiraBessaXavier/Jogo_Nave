import logging
import math
import random
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, List, Optional, TypedDict

import pygame

from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE, GREEN, YELLOW, WHITE
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..core.state import Scene
from ..core.world_config import get_world_for_level_by_id
from ..entities.explosion_pool import ExplosionPool
from ..entities.meteor import Meteor
from ..systems.cheat_input import CheatBuffer

if TYPE_CHECKING:
    from ..app import GameApp

logger = logging.getLogger(__name__)


class CharDict(TypedDict):
    render: pygame.Surface
    base_rect: pygame.Rect
    rect: pygame.Rect


class AnimationConfig:
    TITLE_ANIM_SPEED = 2.5
    TITLE_PHASE_SHIFT = 0.5
    TITLE_ANIM_RANGE = 15
    BUTTON_ANIM_RANGE = 5
    BUTTON_SCALE_FACTOR = 1.08
    BUTTON_SPACING = 85  # Um pouco mais de espaço
    MENU_X_RATIO = 0.5
    MENU_Y_RATIO = 0.5
    TITLE_TOP_MARGIN = 20
    BUTTONS_TOP_MARGIN = 140
    TITLE_HEIGHT = 60

    # Animação de entrada
    ENTRY_DURATION = 0.8
    ENTRY_OFFSET_Y = 50
    TITLE_ENTRY_DELAY = 0.15
    BUTTON_ENTRY_DELAY = 0.4
    BUTTON_STAGGER = 0.12

    # Novos parâmetros dinâmicos e criativos
    PARALLAX_INTENSITY = 0.05
    MAGNETIC_INTENSITY = 12.0  # Atração dos botões ao mouse
    GLOW_PULSE_SPEED = 4.0
    FLOATING_SPEED = 1.5
    FLOATING_RANGE = 8

    # Efeitos de Polimento
    SCANLINE_ALPHA = 35
    VIGNETTE_ALPHA = 70
    REACTIVE_RADIUS = 150  # Raio de reação do título ao mouse
    WARP_SPEED_MULT = 3.0   # Velocidade das estrelas na transição


class AutoPlayConfig:
    """Configuração para o modo auto-play visual do menu."""

    METEOR_SPAWN_RATE = 0.8  # Novos meteoros a cada X segundos
    MAX_METEORS = 10  # Máximo de meteoros simultâneos


class MenuView(Enum):
    """Estados/Views possíveis do menu."""

    MAIN = 0
    DIFFICULTY_SELECTION = 1
    WORLD_SELECTION = 2


class MenuStrings:
    START_GAME = "Iniciar Jogo"
    STATISTICS = "Estatísticas"
    UPGRADES = "Aprimoramentos"
    SETTINGS = "Configurações"
    EXIT = "Sair"
    TITLE = "Pixel Patrol"


class ButtonIndices:
    START_BUTTON = 0
    STATISTICS_BUTTON = 1
    SETTINGS_BUTTON = 2
    EXIT_BUTTON = 3


class ButtonState(Enum):
    NORMAL = 0
    HOVERED = 1
    PRESSED = 2
    FOCUSED = 3


class Button:
    def __init__(
        self,
        text: str,
        rect: pygame.Rect,
        font: Any,
        color: tuple[int, int, int],
        hover_color: tuple[int, int, int],
        action: Callable[[], None],
        ui_scale: float = 1.0,
    ):
        self.text = text
        self.rect = rect
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.action = action
        self.ui_scale = ui_scale
        self.state = ButtonState.NORMAL
        self.prev_state = ButtonState.NORMAL
        self.focused = False
        self.chars: List[CharDict] = []
        self.text_width = 0
        self._create_char_data()

        # Animação de entrada
        self.entry_progress = 0.0  # 0.0 = não visível, 1.0 = completamente visível
        self.entry_delay = 0.0  # Delay antes de começar a animar

        # Dinâmica
        self.glow_alpha = 0.0
        self.floating_offset = 0.0

    def _create_char_data(self):
        btn_char_renders = [self.font.render(char, True, BLACK) for char in self.text]
        self.text_width = sum(char.get_width() for char in btn_char_renders)

        text_start_x = self.rect.centerx - (self.text_width / 2)
        text_current_x = text_start_x

        for char_render in btn_char_renders:
            char_base_rect = char_render.get_rect(
                topleft=(
                    text_current_x,
                    self.rect.centery - char_render.get_height() / 2,
                )
            )
            self.chars.append(
                {
                    "render": char_render,
                    "base_rect": char_base_rect,
                    "rect": char_base_rect.copy(),
                }
            )
            text_current_x += char_render.get_width()

    def update_hover(self, mouse_pos: tuple[int, int]):
        self.prev_state = self.state
        if self.rect.collidepoint(mouse_pos):
            self.state = ButtonState.HOVERED
        elif self.focused:
            self.state = ButtonState.FOCUSED
        else:
            self.state = ButtonState.NORMAL

    def update_entry(self, dt: float):
        """Atualiza a animação de entrada do botão."""
        if self.entry_delay > 0.0:
            self.entry_delay -= dt
            return

        if self.entry_progress < 1.0:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / AnimationConfig.ENTRY_DURATION
            )

    def update_animation(
        self, time_ms: float, anim_speed: float, phase_shift: float, anim_range: float
    ):
        dt = 1.0 / 60.0  # Assumindo 60 FPS para suavidade de transição de glow

        # Pulsação de floating suave
        self.floating_offset = (
            math.sin(time_ms / 1000.0 * AnimationConfig.FLOATING_SPEED)
            * AnimationConfig.FLOATING_RANGE
            * self.ui_scale
        )

        # Atualizar glow
        target_glow = 1.0 if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED) else 0.0
        glow_diff = target_glow - self.glow_alpha
        self.glow_alpha += glow_diff * dt * AnimationConfig.GLOW_PULSE_SPEED

        for i, char_data in enumerate(self.chars):
            if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED):
                sine_wave = math.sin(
                    (time_ms / 1000.0 * anim_speed * 2) + (i * phase_shift)
                )
                char_data["rect"].y = int(
                    char_data["base_rect"].y + sine_wave * anim_range * self.ui_scale
                )
            else:
                char_data["rect"].y = char_data["base_rect"].y

    def render(
        self,
        surface: pygame.Surface,
        border_color: tuple[int, int, int],
        scale_factor: float,
        mouse_pos: Optional[tuple[int, int]] = None,
    ):
        # Não renderizar se ainda não começou a animação
        if self.entry_progress <= 0.0:
            return

        # Calcular alpha e offset Y baseado no progresso e floating
        alpha = int(255 * self.entry_progress)
        offset_y = (
            int(AnimationConfig.ENTRY_OFFSET_Y * self.ui_scale * (1.0 - self.entry_progress))
            + self.floating_offset
        )

        text_color = (
            self.hover_color
            if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED)
            else self.color
        )

        # Retângulo base com offset de entrada/floating
        rect = self.rect.copy()
        rect.y += int(offset_y)

        # Borda e Glow
        border_thickness = max(1, int(2 * self.ui_scale))
        if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED):
            # Escalar retangulo para hover
            scaled_rect = pygame.Rect(0, 0, int(rect.width * scale_factor), int(rect.height * scale_factor))
            scaled_rect.center = rect.center

            # Glow externo pulsante
            if self.glow_alpha > 0:
                glow_size = int(20 * self.ui_scale * self.glow_alpha)
                for i in range(glow_size, 0, -4):
                    glow_alpha = int(40 * self.glow_alpha * (1.0 - i / glow_size))
                    glow_rect = scaled_rect.inflate(i, i)
                    # Usar a cor da borda para o glow, mas garantir que não ofusque o texto
                    pygame.draw.rect(surface, (*border_color, glow_alpha), glow_rect, border_radius=int(14 * self.ui_scale))

            # Borda principal (Dupla borda para efeito premium)
            pygame.draw.rect(surface, (*border_color, alpha), scaled_rect, border_thickness + 1, border_radius=int(12 * self.ui_scale))
            pygame.draw.rect(surface, (255, 255, 255, int(alpha * 0.4)), scaled_rect.inflate(-4, -4), 1, border_radius=int(10 * self.ui_scale))

            # Texto animado (BRANCO para máximo contraste)
            start_x = scaled_rect.centerx - (self.text_width / 2)
            current_x = start_x
            for char_data in self.chars:
                char_pos = (current_x, char_data["rect"].y + offset_y)
                text_char = self.text[self.chars.index(char_data)]

                # Texto principal
                colored_char = self.font.render(text_char, True, text_color)
                colored_char.set_alpha(alpha)

                # Efeito de brilho no texto (Bloom leve)
                if self.glow_alpha > 0.5:
                    bloom_alpha = int(100 * (self.glow_alpha - 0.5) * 2)
                    bloom_char = self.font.render(text_char, True, (255, 255, 255))
                    bloom_char.set_alpha(bloom_alpha)
                    surface.blit(bloom_char, (char_pos[0]-1, char_pos[1]))
                    surface.blit(bloom_char, (char_pos[0]+1, char_pos[1]))

                surface.blit(colored_char, char_pos)
                current_x += char_data["render"].get_width()
        else:
            # Borda normal
            pygame.draw.rect(surface, (*border_color, alpha), rect, border_thickness, border_radius=int(10 * self.ui_scale))

            # Texto centralizado
            text_surface = self.font.render(self.text, True, text_color)
            text_surface.set_alpha(alpha)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)


class AutoPlay:
    """Gerencia o modo auto-play visual com meteoros no menu."""

    def __init__(self, pre_populate: bool = True):
        self.meteors: List[Meteor] = []
        self.meteor_spawn_timer = 0.0
        self.explosion_pool = ExplosionPool(initial_size=20)
        self.meteors_destroyed = 0  # Counter para easter egg

        if pre_populate:
            self._pre_populate()

    def _pre_populate(self):
        """Inicializa o menu com alguns meteoros já em movimento em várias alturas."""
        # Começar com metade do máximo para não poluir muito, mas parecer vivo
        num_meteors = AutoPlayConfig.MAX_METEORS // 2
        for _ in range(num_meteors):
            size = random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
            x = random.randint(0, Config.SCREEN_WIDTH - size * 2)
            # Posicionar em alturas aleatórias para simular que já estavam caindo
            y = random.randint(-size * 3, Config.SCREEN_HEIGHT)
            meteor = Meteor(size=size, x=x, y=y)
            self.meteors.append(meteor)

    def update(self, dt: float):
        """Atualiza a lógica do auto-play."""
        # Atualizar explosões
        self.explosion_pool.update(dt)

        # Spawnar novos meteoros
        self.meteor_spawn_timer += dt
        if (
            self.meteor_spawn_timer >= AutoPlayConfig.METEOR_SPAWN_RATE
            and len(self.meteors) < AutoPlayConfig.MAX_METEORS
        ):
            self._spawn_meteor()
            self.meteor_spawn_timer = 0.0

        # Atualizar e remover meteoros fora da tela
        for meteor in self.meteors[:]:
            meteor.update(dt)
            if meteor.dead or meteor.y > Config.SCREEN_HEIGHT:
                self.meteors.remove(meteor)

    def _spawn_meteor(self):
        """Spawna um novo meteoro."""
        size = random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
        x = random.randint(0, Config.SCREEN_WIDTH - size * 2)
        # Spawnar meteoros de cima (Y negativo)
        y = -size * 3
        meteor = Meteor(size=size, x=x, y=y)
        self.meteors.append(meteor)

    def destroy_meteor(self, meteor: Meteor):
        """Destrói um meteoro e cria uma explosão."""
        if meteor in self.meteors:
            # Criar explosão no centro do meteoro
            center_x = meteor.x + meteor.w / 2
            center_y = meteor.y + meteor.h / 2
            self.explosion_pool.get(center_x, center_y, size=meteor.size)
            self.meteors.remove(meteor)
            self.meteors_destroyed += 1  # Incrementar contador

    def is_rainbow_mode(self) -> bool:
        """Retorna True se atingiu 15 meteoros destruídos (easter egg)."""
        return self.meteors_destroyed >= 15

    def reset(self, pre_populate: bool = True):
        """Reseta o estado do auto-play."""
        self.meteors_destroyed = 0
        self.meteors.clear()
        self.meteor_spawn_timer = 0.0
        self.explosion_pool.clear_active()
        if pre_populate:
            self._pre_populate()

    def render(self, surface: pygame.Surface):
        """Renderiza o auto-play visual (apenas meteoros e explosões)."""
        # Renderizar explosões (abaixo dos meteoros)
        self.explosion_pool.draw_all(surface)

        # Renderizar meteoros (acima das explosões)
        for meteor in self.meteors:
            meteor.draw(surface)


class MainMenuScene(Scene):
    """
    Main menu scene for the Pixel Patrol game.

    Handles the display and interaction of the main menu, including title animation,
    button interactions, and navigation to other scenes.
    """

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.ui_scale = Config.SCREEN_WIDTH / 1280.0
        self.r = app.renderer  # Usar renderer compartilhado
        self.font = get_font(int(64 * self.ui_scale))
        self.button_font = get_font(int(24 * self.ui_scale))
        self.border_color = CUSTOM_PURPLE
        self.focused_border_color = CUSTOM_PURPLE  # Unificado para evitar flicker
        self.focused_button_index = 0

        # Cheat code buffer
        self.cheat: CheatBuffer = CheatBuffer()

        # Auto-play visual
        self.auto_play = AutoPlay()

        # Sistema de views
        self.current_view = MenuView.MAIN
        self.transitioning = False
        self.transition_progress = 0.0
        self.transition_duration = 0.4
        self.fade_out = False  # True = fade out, False = fade in
        self.returning_to_main = False
        self.pending_game_start = False
        self.pending_difficulty: Optional[DifficultyPreset] = None
        self.game_start_black_hold_active = False
        self.game_start_black_hold_timer = 0.0
        self.game_start_black_hold_duration = 0.2
        self.force_blackout_frame = False

        # View de seleção de dificuldade
        from ..scenes.difficulty_selection import DifficultySelectionView
        from ..scenes.world_selection import WorldSelectionView

        self.difficulty_view = DifficultySelectionView(
            on_select=self._on_difficulty_selected,
            on_back=self._on_difficulty_back,
            renderer=self.r,
        )

        # View de seleção de mundo
        self.world_selection_view = WorldSelectionView(
            on_world_selected=self._on_world_selected,
            on_back=self._on_world_back,
            renderer=self.r,
            player_profile=self.app.player_profile,
        )

        # Menu container position
        self.menu_x = int(Config.SCREEN_WIDTH * AnimationConfig.MENU_X_RATIO)
        self.menu_y = 0

        # Title animation
        self.title_chars: List[CharDict] = []
        self._create_title_chars()

        # Button definitions
        self.buttons: List[Button] = []
        self._create_buttons()

        # Calculate actual menu bounds and center vertically
        self._center_menu_vertically()

        # Ícone de configurações (engrenagem) no canto inferior direito
        self._create_settings_icon()

        # Animação de entrada
        self.entry_timer = 0.0
        self.title_entry_progress = 0.0
        self.is_entering = True

    def _center_menu_vertically(self):
        """Calculates the actual bounds of the menu and adjusts menu_y to center it vertically."""
        all_y: List[int] = []

        for char_data in self.title_chars:
            all_y.append(char_data["base_rect"].top)
            all_y.append(char_data["base_rect"].bottom)

        for button in self.buttons:
            all_y.append(button.rect.top)
            all_y.append(button.rect.bottom)

        if all_y:
            menu_top = min(all_y)
            menu_bottom = max(all_y)
            menu_height = menu_bottom - menu_top
            self.menu_y = (Config.SCREEN_HEIGHT - menu_height) // 2
            offset = self.menu_y - menu_top

            for char_data in self.title_chars:
                char_data["base_rect"].y += offset
                char_data["rect"].y += offset

            for button in self.buttons:
                button.rect.y += offset
                for char in button.chars:
                    char["base_rect"].y += offset
                    char["rect"].y += offset

    def _start_world_selection(self):
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0
        # Não limpar os meteoros aqui: eles acompanham o fade da transição
        # (ver render) e só deixam de ser desenhados quando a view troca.

    def _on_difficulty_selected(self, preset: DifficultyPreset):
        self.pending_game_start = True
        self.pending_difficulty = preset
        self.game_start_black_hold_active = False
        self.game_start_black_hold_timer = 0.0
        self.force_blackout_frame = False
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0
        # Não limpar os meteoros aqui: eles acompanham o fade da transição
        # (ver render) e só deixam de ser desenhados quando a view troca.

    def _start_game_with_preset(self, preset: DifficultyPreset) -> None:
        from ..scenes.controls_modal import ControlsModalScene
        self.force_blackout_frame = True
        self.pending_game_start = False
        self.pending_difficulty = None
        self.game_start_black_hold_active = False
        self.game_start_black_hold_timer = 0.0
        self.app.selected_difficulty = preset
        selected_world_id = self.app.player_profile.selected_world_id
        world_config = get_world_for_level_by_id(selected_world_id)
        starting_level = world_config.start_level if world_config else 1

        if self.app.player_profile.current_session:
            self.app.player_profile.current_session.score = 0

        def _push_playing_scene():
            from ..scenes.playing import PlayingScene
            self.app.states.push(
                PlayingScene(
                    self.app, self.app.level_manager,
                    difficulty_preset=preset, starting_level=starting_level,
                    start_fade_duration=0.8,
                )
            )

        if self.app.preferences.show_controls_modal:
            self.app.states.pop()
            self.app.states.push(ControlsModalScene(self.app, on_finish=_push_playing_scene))
        else:
            self.app.states.pop()
            _push_playing_scene()

    def _on_difficulty_back(self):
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _on_world_selected(self, world_id: int):
        self.app.player_profile.selected_world_id = world_id
        logger.info("Mundo %s selecionado", world_id)
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _on_world_back(self):
        self.returning_to_main = True
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _open_statistics(self) -> None:
        from ..scenes.statistics import StatisticsScene
        self.app.states.push(StatisticsScene(self.app))

    def _open_upgrades(self) -> None:
        from ..scenes.upgrades_selection import UpgradesSelectionScene
        self.app.states.push(UpgradesSelectionScene(self.app))

    def _open_settings(self) -> None:
        from ..scenes.settings import SettingsScene
        self.app.states.push(SettingsScene(self.app))

    def _create_title_chars(self):
        title_string = MenuStrings.TITLE
        char_renders = [self.font.render(char, True, CUSTOM_GOLD) for char in title_string]
        total_width = sum(char_render.get_width() for char_render in char_renders)
        start_x = (Config.SCREEN_WIDTH - total_width) // 2
        base_y = self.menu_y + int(AnimationConfig.TITLE_TOP_MARGIN * self.ui_scale)
        current_x = start_x

        for char_render in char_renders:
            base_rect = char_render.get_rect(topleft=(current_x, base_y))
            self.title_chars.append({"render": char_render, "base_rect": base_rect, "rect": base_rect.copy()})
            current_x += char_render.get_width()

    def _create_buttons(self):
        buttons_y_start = self.menu_y + int((AnimationConfig.TITLE_TOP_MARGIN + AnimationConfig.TITLE_HEIGHT + AnimationConfig.BUTTONS_TOP_MARGIN) * self.ui_scale)
        button_configs = [
            (MenuStrings.START_GAME, CUSTOM_PURPLE, WHITE, self._start_world_selection),
            (MenuStrings.STATISTICS, CUSTOM_PURPLE, WHITE, self._open_statistics),
            (MenuStrings.UPGRADES, CUSTOM_PURPLE, WHITE, self._open_upgrades),
            (MenuStrings.EXIT, CUSTOM_PURPLE, WHITE, lambda: setattr(self.app, "running", False)),
        ]

        for i, (text, color, hover_color, action) in enumerate(button_configs):
            if i == len(button_configs) - 1:
                rect = pygame.Rect(0, 0, int(280 * self.ui_scale), int(50 * self.ui_scale))
                extra_spacing = int(30 * self.ui_scale)
            else:
                rect = pygame.Rect(0, 0, int(380 * self.ui_scale), int(60 * self.ui_scale))
                extra_spacing = 0

            rect.center = (self.menu_x, buttons_y_start + i * int(AnimationConfig.BUTTON_SPACING * self.ui_scale) + extra_spacing)
            button = Button(text, rect, self.button_font, color, hover_color, action, ui_scale=self.ui_scale)
            button.entry_delay = AnimationConfig.BUTTON_ENTRY_DELAY + (i * AnimationConfig.BUTTON_STAGGER)
            self.buttons.append(button)

    def _calculate_wave_offset(self, time_ms: float, index: int, amplitude: float, speed: Optional[float] = None) -> int:
        if speed is None: speed = AnimationConfig.TITLE_ANIM_SPEED
        sine_wave = math.sin((time_ms / 1000.0 * speed) + (index * AnimationConfig.TITLE_PHASE_SHIFT))
        return int(sine_wave * amplitude * self.ui_scale)

    def enter(self, reset_background: bool = True):
        pygame.mouse.set_visible(True)
        sound_manager.music_state_manager.transition_to(MusicState.MENU)

        if reset_background:
            self.auto_play.reset()

        self.is_entering = True
        self.entry_timer = 0.0
        self.title_entry_progress = 0.0
        for i, button in enumerate(self.buttons):
            button.entry_progress = 0.0
            button.entry_delay = AnimationConfig.BUTTON_ENTRY_DELAY + (i * AnimationConfig.BUTTON_STAGGER)

    def get_focusable_rects(self) -> list[pygame.Rect]:
        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            rects = [data["rect"] for data in self.difficulty_view.difficulty_buttons.values()]
            rects.append(self.difficulty_view.back_button_rect)
            return rects
        if self.current_view == MenuView.WORLD_SELECTION:
            return self.world_selection_view.get_focusable_rects()
        return [button.rect for button in self.buttons] + [self.settings_icon_rect]

    def exit(self):
        return None

    def _process_cheat_input(self, event: pygame.event.Event) -> None:
        if not self.cheat.feed(event): return
        self.app.player_profile.add_stars(9999)
        self.app.player_profile.unlock_all_worlds()
        self.app.player_profile.save()
        logger.info("⭐ CHEAT ATIVADO")
        sound_manager.play_sound("button_click")

    def handle_event(self, event: pygame.event.Event):
        if self.transitioning: return
        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            self.difficulty_view.handle_event(event)
            return
        if self.current_view == MenuView.WORLD_SELECTION:
            self.world_selection_view.handle_event(event)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.settings_icon_rect.collidepoint(event.pos):
                self._open_settings()
                sound_manager.play_sound("button_click")
                return
            meteor_clicked = False
            for meteor in self.auto_play.meteors[:]:
                if meteor.rect.collidepoint(event.pos):
                    self.auto_play.destroy_meteor(meteor)
                    sound_manager.play_sound("button_click")
                    meteor_clicked = True
                    break
            if not meteor_clicked:
                for button in self.buttons:
                    if button.rect.collidepoint(event.pos):
                        button.action()
                        sound_manager.play_sound("button_click")
                        break
        elif event.type == pygame.MOUSEMOTION:
            prev_settings_hover = self.settings_hovered
            self.settings_hovered = self.settings_icon_rect.collidepoint(event.pos)
            if self.settings_hovered and not prev_settings_hover:
                sound_manager.play_sound("button_hover")
            for i, button in enumerate(self.buttons):
                prev_state = button.state
                button.update_hover(event.pos)
                if button.state == ButtonState.HOVERED and prev_state != ButtonState.HOVERED:
                    sound_manager.play_sound("button_hover")
                if button.state == ButtonState.HOVERED:
                    self.focused_button_index = i
                    for j, b in enumerate(self.buttons): b.focused = (j == i)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_DOWN:
                self.focused_button_index = (self.focused_button_index + 1) % len(self.buttons)
                sound_manager.play_sound("button_hover")
            elif event.key == pygame.K_UP:
                self.focused_button_index = (self.focused_button_index - 1) % len(self.buttons)
                sound_manager.play_sound("button_hover")
            elif event.key == pygame.K_RETURN:
                self.buttons[self.focused_button_index].action()
                sound_manager.play_sound("button_click")
            elif event.key == pygame.K_ESCAPE:
                self.app.running = False
            self._process_cheat_input(event)
            # Recalcular o estado visual: focado vira ButtonState.FOCUSED (sem
            # isso a navegação por teclado muda o índice mas não destaca nada).
            mouse_pos = pygame.mouse.get_pos()
            for i, button in enumerate(self.buttons):
                button.focused = (i == self.focused_button_index)
                button.update_hover(mouse_pos)

    def update(self, dt: float):
        # Efeito de Warp nas estrelas durante transição
        star_speed_mult = 1.0
        if self.transitioning:
            star_speed_mult = 1.0 + (self.transition_progress * AnimationConfig.WARP_SPEED_MULT)

        self.r.starfield.update(dt * star_speed_mult)
        # Meteoros do background só existem na view principal. Em world/difficulty
        # selection o background fica limpo — sem isso, o update continuaria
        # spawnando meteoros e desfazendo o reset feito ao trocar de view.
        if self.current_view == MenuView.MAIN:
            self.auto_play.update(dt)
        time_ms = pygame.time.get_ticks()

        if self.game_start_black_hold_active:
            self.game_start_black_hold_timer -= dt
            if self.game_start_black_hold_timer <= 0.0:
                if self.pending_difficulty is not None: self._start_game_with_preset(self.pending_difficulty)
                return

        if self.transitioning:
            self.transition_progress += dt / self.transition_duration
            if self.transition_progress >= 1.0:
                self.transition_progress = 1.0
                self.transitioning = False
                if self.fade_out:
                    if self.pending_game_start and self.pending_difficulty is not None:
                        self.game_start_black_hold_active = True
                        self.game_start_black_hold_timer = self.game_start_black_hold_duration
                        return
                    if self.returning_to_main:
                        self.current_view = MenuView.MAIN
                        self.returning_to_main = False
                        self.enter()
                    elif self.current_view == MenuView.MAIN:
                        self.current_view = MenuView.WORLD_SELECTION
                        self.world_selection_view.reset()
                    elif self.current_view == MenuView.WORLD_SELECTION:
                        self.current_view = MenuView.DIFFICULTY_SELECTION
                        self.difficulty_view.reset()
                    self.fade_out = False
                    self.transitioning = True
                    self.transition_progress = 0.0

        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            self.difficulty_view.update(dt)
        elif self.current_view == MenuView.WORLD_SELECTION:
            self.world_selection_view.update(dt)
        else:
            if self.is_entering:
                self.entry_timer += dt
                if self.entry_timer >= AnimationConfig.TITLE_ENTRY_DELAY:
                    elapsed = self.entry_timer - AnimationConfig.TITLE_ENTRY_DELAY
                    self.title_entry_progress = min(1.0, elapsed / AnimationConfig.ENTRY_DURATION)
                for button in self.buttons: button.update_entry(dt)
                if self.title_entry_progress >= 1.0 and all(b.entry_progress >= 1.0 for b in self.buttons):
                    self.is_entering = False

            # Animate title
            for i, char_data in enumerate(self.title_chars):
                # Sine wave base
                wave_off = self._calculate_wave_offset(time_ms, i, AnimationConfig.TITLE_ANIM_RANGE)
                char_data["rect"].y = char_data["base_rect"].y + wave_off
                char_data["rect"].x = char_data["base_rect"].x

            # Animate buttons
            for button in self.buttons:
                button.update_animation(time_ms, AnimationConfig.TITLE_ANIM_SPEED, AnimationConfig.TITLE_PHASE_SHIFT, AnimationConfig.BUTTON_ANIM_RANGE)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        alpha_mult = (1.0 - self.transition_progress if self.fade_out else self.transition_progress) if self.transitioning else 1.0

        # Meteoros só pertencem à view principal. Durante a transição eles
        # acompanham o fade do menu (saindo ou voltando) em vez de sumir de
        # repente; só deixam de ser desenhados depois que a view troca.
        if self.current_view == MenuView.MAIN:
            if self.transitioning and alpha_mult < 1.0:
                temp = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
                self.auto_play.render(temp)
                temp.set_alpha(int(255 * alpha_mult))
                surface.blit(temp, (0, 0))
            else:
                self.auto_play.render(surface)

        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            if alpha_mult < 1.0:
                temp = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
                self.difficulty_view.render(temp)
                temp.set_alpha(int(255 * alpha_mult))
                surface.blit(temp, (0, 0))
            else: self.difficulty_view.render(surface)
        elif self.current_view == MenuView.WORLD_SELECTION:
            if alpha_mult < 1.0:
                temp = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
                self.world_selection_view.render(temp)
                temp.set_alpha(int(255 * alpha_mult))
                surface.blit(temp, (0, 0))
            else: self.world_selection_view.render(surface)
        else:
            # Title
            title_alpha = int(255 * self.title_entry_progress * alpha_mult)
            title_offset_y = int(AnimationConfig.ENTRY_OFFSET_Y * self.ui_scale * (1.0 - self.title_entry_progress))

            if self.auto_play.is_rainbow_mode():
                from ..core.colors import RAINBOW_COLORS
                time_ms = pygame.time.get_ticks()
                for i, char_data in enumerate(self.title_chars):
                    color_offset = (time_ms / 200) % len(RAINBOW_COLORS)
                    idx = int(color_offset)
                    next_idx = (idx + 1) % len(RAINBOW_COLORS)
                    blend = color_offset - idx
                    c1, c2 = RAINBOW_COLORS[idx], RAINBOW_COLORS[next_idx]
                    color = tuple(int(c1[j] + (c2[j] - c1[j]) * blend) for j in range(3))
                    pulse = math.sin((time_ms / 1000) + i * 0.3) * 0.15 + 0.85
                    final_color = tuple(int(c * pulse) for c in color)
                    colored_char = self.font.render(MenuStrings.TITLE[i], True, final_color)
                    colored_char.set_alpha(title_alpha)
                    surface.blit(colored_char, (char_data["rect"].x, char_data["rect"].y + title_offset_y))
            else:
                for char_data in self.title_chars:
                    char_surf = char_data["render"].copy()
                    char_surf.set_alpha(title_alpha)
                    surface.blit(char_surf, (char_data["rect"].x, char_data["rect"].y + title_offset_y))

            # Buttons
            for button in self.buttons:
                orig = button.entry_progress
                button.entry_progress *= alpha_mult
                button.render(surface, self.focused_border_color if button.state == ButtonState.FOCUSED else self.border_color, AnimationConfig.BUTTON_SCALE_FACTOR)
                button.entry_progress = orig

            self._render_settings_icon(surface, alpha_mult)
            self._render_gamepad_status_badge(surface, alpha_mult)

        if self.pending_game_start and self.fade_out and self.transitioning:
            black_overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
            black_overlay.fill((0, 0, 0, int(255 * self.transition_progress)))
            surface.blit(black_overlay, (0, 0))
        elif self.game_start_black_hold_active or self.force_blackout_frame:
            surface.fill(BLACK)

    def _create_settings_icon(self) -> None:
        """Cria o ícone de engrenagem (Configurações) no canto inferior direito."""
        size = int(46 * self.ui_scale)
        margin = int(20 * self.ui_scale)
        self.settings_icon_rect = pygame.Rect(
            Config.SCREEN_WIDTH - size - margin,
            Config.SCREEN_HEIGHT - size - margin,
            size, size,
        )
        self.settings_hovered = False
        self.settings_icon_normal = self._render_gear_surface(size, CUSTOM_PURPLE)
        self.settings_icon_hover = self._render_gear_surface(size, WHITE)

    def _render_gear_surface(self, size: int, color: tuple[int, int, int]) -> pygame.Surface:
        """Desenha uma engrenagem proceduralmente numa surface transparente."""
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size / 2.0
        teeth = 8
        rt = size * 0.46       # ponta do dente
        ri = size * 0.34       # base do dente
        half_w = size * 0.085  # meia largura do dente
        body_r = int(size * 0.34)
        hole_r = int(size * 0.13)
        cos, sin = math.cos, math.sin
        for k in range(teeth):
            a = (math.tau * k) / teeth
            dx, dy = cos(a), sin(a)
            px, py = -sin(a), cos(a)
            pts = [
                (cx + ri * dx + half_w * px, cy + ri * dy + half_w * py),
                (cx + rt * dx + half_w * px, cy + rt * dy + half_w * py),
                (cx + rt * dx - half_w * px, cy + rt * dy - half_w * py),
                (cx + ri * dx - half_w * px, cy + ri * dy - half_w * py),
            ]
            pygame.draw.polygon(surf, color, pts)
        center = (int(cx), int(cy))
        pygame.draw.circle(surf, color, center, body_r)
        pygame.draw.circle(surf, (0, 0, 0, 0), center, hole_r)  # fura o miolo
        return surf

    def _render_settings_icon(self, surface: pygame.Surface, alpha_mult: float) -> None:
        icon_alpha = alpha_mult * self.title_entry_progress
        if icon_alpha <= 0.0:
            return
        rect = self.settings_icon_rect
        bg_r = rect.width // 2 + int(6 * self.ui_scale)
        bg = pygame.Surface((bg_r * 2, bg_r * 2), pygame.SRCALPHA)
        bg_fill_alpha = int((100 if self.settings_hovered else 60) * icon_alpha)
        pygame.draw.circle(bg, (20, 20, 24, bg_fill_alpha), (bg_r, bg_r), bg_r)
        ring_color = WHITE if self.settings_hovered else CUSTOM_PURPLE
        pygame.draw.circle(bg, (*ring_color, int(220 * icon_alpha)), (bg_r, bg_r), bg_r, max(1, int(2 * self.ui_scale)))
        surface.blit(bg, (rect.centerx - bg_r, rect.centery - bg_r))

        icon = self.settings_icon_hover if self.settings_hovered else self.settings_icon_normal
        if self.settings_hovered:
            scaled = int(rect.width * 0.85)
            icon = pygame.transform.smoothscale(icon, (scaled, scaled))
        icon = icon.copy()
        icon.set_alpha(int(255 * icon_alpha))
        surface.blit(icon, icon.get_rect(center=rect.center))

    def _render_gamepad_status_badge(self, surface: pygame.Surface, alpha_mult: float) -> None:
        gamepad = getattr(self.app, "gamepad", None)
        if gamepad is None or not gamepad.connected: return
        label = "Controle Xbox ativo" if gamepad.is_active else "Controle detectado — ative em Settings"
        color = GREEN if gamepad.is_active else YELLOW
        font = get_font(int(14 * self.ui_scale))
        text_surf = font.render(label, True, color)
        text_w, text_h = text_surf.get_size()
        pad_x, pad_y = int(12 * self.ui_scale), int(6 * self.ui_scale)
        bg_w, bg_h = text_w + pad_x * 2 + int(10 * self.ui_scale), text_h + pad_y * 2
        margin = int(16 * self.ui_scale)
        bg_x = Config.SCREEN_WIDTH - bg_w - margin
        # Acima do ícone de configurações para não sobrepor
        bg_y = self.settings_icon_rect.top - bg_h - int(8 * self.ui_scale)
        alpha = int(220 * alpha_mult)
        bg_surf = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, (20, 20, 24, alpha), bg_surf.get_rect(), border_radius=int(8 * self.ui_scale))
        pygame.draw.rect(bg_surf, (*color, alpha), bg_surf.get_rect(), 1, border_radius=int(8 * self.ui_scale))
        dot_r = int(4 * self.ui_scale)
        pygame.draw.circle(bg_surf, (*color, alpha), (pad_x, bg_h // 2), dot_r)
        text_surf.set_alpha(alpha)
        bg_surf.blit(text_surf, (pad_x + dot_r + int(6 * self.ui_scale), pad_y))
        surface.blit(bg_surf, (bg_x, bg_y))
