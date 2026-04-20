import logging
import math
import random
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, List, Optional, TypedDict

import pygame

from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..core.state import Scene
from ..core.world_config import get_world_for_level_by_id
from ..entities.explosion_pool import ExplosionPool
from ..entities.meteor import Meteor
from ..scenes.difficulty_selection import DifficultySelectionView
from ..scenes.playing import PlayingScene
from ..scenes.settings import SettingsScene
from ..scenes.statistics import StatisticsScene
from ..scenes.upgrades_selection import UpgradesSelectionScene
from ..scenes.world_selection import WorldSelectionView

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
    BUTTON_SCALE_FACTOR = 1.1
    BUTTON_SPACING = 80
    MENU_X_RATIO = 0.5  # Horizontal position as ratio of screen width (0.5 = center)
    MENU_Y_RATIO = 0.5  # Vertical position as ratio of screen height (0.5 = center)
    TITLE_TOP_MARGIN = 20  # Margin from top of menu container to title
    BUTTONS_TOP_MARGIN = 130  # Margin from title bottom to first button
    TITLE_HEIGHT = 60  # Approximate height of title text

    # Animação de entrada
    ENTRY_DURATION = 0.6  # Duração do fade-in up (segundos)
    ENTRY_OFFSET_Y = 30  # Distância Y da animação de subida
    TITLE_ENTRY_DELAY = 0.3  # Delay antes do título aparecer
    BUTTON_ENTRY_DELAY = 0.6  # Delay antes do primeiro botão
    BUTTON_STAGGER = 0.3  # Delay entre cada botão


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
    TITLE = "Space Shooter"


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
    ):
        self.text = text
        self.rect = rect
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.action = action
        self.state = ButtonState.NORMAL
        self.prev_state = ButtonState.NORMAL
        self.focused = False
        self.chars: List[CharDict] = []
        self.text_width = 0
        self._create_char_data()

        # Animação de entrada
        self.entry_progress = 0.0  # 0.0 = não visível, 1.0 = completamente visível
        self.entry_delay = 0.0  # Delay antes de começar a animar

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
        for i, char_data in enumerate(self.chars):
            if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED):
                sine_wave = math.sin(
                    (time_ms / 1000.0 * anim_speed * 2) + (i * phase_shift)
                )
                char_data["rect"].y = int(
                    char_data["base_rect"].y + sine_wave * anim_range
                )
            else:
                char_data["rect"].y = char_data["base_rect"].y

    def render(
        self,
        surface: pygame.Surface,
        border_color: tuple[int, int, int],
        scale_factor: float,
    ):
        # Não renderizar se ainda não começou a animação
        if self.entry_progress <= 0.0:
            return

        # Calcular alpha e offset Y baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(AnimationConfig.ENTRY_OFFSET_Y * (1.0 - self.entry_progress))

        text_color = (
            self.hover_color
            if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED)
            else self.color
        )

        # Aplicar alpha nas cores
        text_color = (text_color[0], text_color[1], text_color[2], alpha)
        border_color_alpha = (border_color[0], border_color[1], border_color[2], alpha)

        if self.state == ButtonState.HOVERED:
            scaled_rect = pygame.Rect(
                0,
                0,
                int(self.rect.width * scale_factor),
                int(self.rect.height * scale_factor),
            )
            scaled_rect.center = self.rect.center
            scaled_rect.y += offset_y

            # Apenas borda, sem fundo
            # Criar surface temporária com alpha para a borda
            temp_surface = pygame.Surface(
                (scaled_rect.width + 4, scaled_rect.height + 4), pygame.SRCALPHA
            )
            temp_rect = pygame.Rect(2, 2, scaled_rect.width, scaled_rect.height)
            pygame.draw.rect(
                temp_surface, border_color_alpha, temp_rect, 2, border_radius=12
            )
            surface.blit(temp_surface, (scaled_rect.x - 2, scaled_rect.y - 2))

            # Draw animated text
            start_x = scaled_rect.centerx - (self.text_width / 2)
            current_x = start_x
            for char_data in self.chars:
                char_pos = (current_x, char_data["rect"].y + offset_y)
                # Usar texto com cor apropriada
                text_char = self.text[self.chars.index(char_data)]
                colored_char = self.font.render(
                    text_char, True, text_color[:3]
                )  # RGB sem alpha
                colored_char.set_alpha(alpha)
                surface.blit(colored_char, char_pos)
                current_x += char_data["render"].get_width()
        else:
            # Apenas borda, sem fundo
            adjusted_rect = self.rect.copy()
            adjusted_rect.y += offset_y

            # Criar surface temporária com alpha para a borda
            temp_surface = pygame.Surface(
                (adjusted_rect.width + 4, adjusted_rect.height + 4), pygame.SRCALPHA
            )
            temp_rect = pygame.Rect(2, 2, adjusted_rect.width, adjusted_rect.height)
            pygame.draw.rect(
                temp_surface, border_color_alpha, temp_rect, 2, border_radius=10
            )
            surface.blit(temp_surface, (adjusted_rect.x - 2, adjusted_rect.y - 2))

            text_surface = self.font.render(
                self.text, True, text_color[:3]
            )  # RGB sem alpha
            text_surface.set_alpha(alpha)
            text_rect = text_surface.get_rect(center=adjusted_rect.center)
            surface.blit(text_surface, text_rect)


class AutoPlay:
    """Gerencia o modo auto-play visual com meteoros no menu."""

    def __init__(self):
        self.meteors: List[Meteor] = []
        self.meteor_spawn_timer = 0.0
        self.explosion_pool = ExplosionPool(initial_size=20)
        self.meteors_destroyed = 0  # Counter para easter egg

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

    def reset(self):
        """Reseta o estado do auto-play."""
        self.meteors_destroyed = 0
        self.meteors.clear()
        self.meteor_spawn_timer = 0.0
        self.explosion_pool.clear_active()

    def render(self, surface: pygame.Surface):
        """Renderiza o auto-play visual (apenas meteoros e explosões)."""
        # Renderizar explosões (abaixo dos meteoros)
        self.explosion_pool.draw_all(surface)

        # Renderizar meteoros (acima das explosões)
        for meteor in self.meteors:
            meteor.draw(surface)


class MainMenuScene(Scene):
    """
    Main menu scene for the Space Shooter game.

    Handles the display and interaction of the main menu, including title animation,
    button interactions, and navigation to other scenes.
    """

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = app.renderer  # Usar renderer compartilhado
        self.font = get_font(60)
        self.button_font = get_font(22)
        self.border_color = CUSTOM_PURPLE
        self.focused_border_color = CUSTOM_GOLD
        self.focused_button_index = 0

        # Auto-play visual
        self.auto_play = AutoPlay()

        # Sistema de views
        self.current_view = MenuView.MAIN
        self.transitioning = False
        self.transition_progress = 0.0
        self.transition_duration = 0.3
        self.fade_out = False  # True = fade out, False = fade in
        self.returning_to_main = False
        self.pending_game_start = False
        self.pending_difficulty: Optional[DifficultyPreset] = None
        self.game_start_black_hold_active = False
        self.game_start_black_hold_timer = 0.0
        self.game_start_black_hold_duration = 0.18
        self.force_blackout_frame = False

        # View de seleção de dificuldade
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

        # Menu container position - temporary, will be adjusted
        self.menu_x = int(Config.SCREEN_WIDTH * AnimationConfig.MENU_X_RATIO)
        self.menu_y = 0  # Temporary

        # Title animation
        self.title_chars: List[CharDict] = []
        self._create_title_chars()

        # Button definitions
        self.buttons: List[Button] = []
        self._create_buttons()

        # Calculate actual menu bounds and center vertically
        self._center_menu_vertically()

        # Animação de entrada
        self.entry_timer = 0.0
        self.title_entry_progress = 0.0
        self.is_entering = True

    def _center_menu_vertically(self):
        """Calculates the actual bounds of the menu and adjusts menu_y to center it vertically."""
        # Collect all Y positions
        all_y: List[int] = []

        # Title positions
        for char_data in self.title_chars:
            all_y.append(char_data["base_rect"].top)
            all_y.append(char_data["base_rect"].bottom)

        # Button positions
        for button in self.buttons:
            all_y.append(button.rect.top)
            all_y.append(button.rect.bottom)

        if all_y:
            menu_top = min(all_y)
            menu_bottom = max(all_y)
            menu_height = menu_bottom - menu_top

            # Center the menu vertically
            self.menu_y = (Config.SCREEN_HEIGHT - menu_height) // 2

            # Adjust all positions by the new menu_y offset
            offset = self.menu_y - menu_top

            # Adjust title positions
            for char_data in self.title_chars:
                char_data["base_rect"].y += offset
                char_data["rect"].y += offset

            # Adjust button positions
            for button in self.buttons:
                button.rect.y += offset
                # Adjust button's internal char positions
                for char in button.chars:
                    char["base_rect"].y += offset
                    char["rect"].y += offset

    def _start_world_selection(self):
        """Inicia transição para a view de seleção de mundo."""
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _on_difficulty_selected(self, preset: DifficultyPreset):
        """Callback quando uma dificuldade é selecionada."""
        # Iniciar fade de saída e adiar início do jogo até o fim da transição.
        self.pending_game_start = True
        self.pending_difficulty = preset
        self.game_start_black_hold_active = False
        self.game_start_black_hold_timer = 0.0
        self.force_blackout_frame = False
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _start_game_with_preset(self, preset: DifficultyPreset) -> None:
        """Inicia o jogo com o preset já selecionado."""
        # Garante tela preta caso este frame ainda renderize o menu.
        self.force_blackout_frame = True
        self.pending_game_start = False
        self.pending_difficulty = None
        self.game_start_black_hold_active = False
        self.game_start_black_hold_timer = 0.0

        # Armazenar dificuldade no app
        self.app.selected_difficulty = preset

        # Resetar contador de uso do HEAL para novo jogo
        self.app.heal_usage_count = 0

        # Determinar nível inicial baseado no mundo selecionado
        selected_world_id = self.app.player_profile.selected_world_id
        world_config = get_world_for_level_by_id(selected_world_id)
        starting_level = world_config.start_level if world_config else 1

        # Resetar score quando iniciar em novo checkpoint
        if self.app.player_profile.current_session:
            self.app.player_profile.current_session.score = 0

        # Criar e empurrar a cena de jogo
        self.app.states.pop()  # Remove menu
        self.app.states.push(
            PlayingScene(
                self.app,
                self.app.level_manager,
                difficulty_preset=preset,
                starting_level=starting_level,
            )
        )

    def _on_difficulty_back(self):
        """Callback quando o usuário quer voltar da seleção de dificuldade."""
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _on_world_selected(self, world_id: int):
        """Callback quando um mundo é selecionado."""
        # Salvar seleção no perfil
        self.app.player_profile.selected_world_id = world_id
        logger.info(f"Mundo {world_id} selecionado")

        # Avançar para seleção de dificuldade
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _on_world_back(self):
        """Callback quando o usuário quer voltar da seleção de mundo."""
        self.returning_to_main = True
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def _create_title_chars(self):
        """Creates character data for title animation."""
        title_string = MenuStrings.TITLE
        char_renders = [
            self.font.render(char, True, CUSTOM_GOLD) for char in title_string
        ]
        total_width = sum(char_render.get_width() for char_render in char_renders)

        start_x = (Config.SCREEN_WIDTH - total_width) // 2
        base_y = self.menu_y + AnimationConfig.TITLE_TOP_MARGIN
        current_x = start_x

        for char_render in char_renders:
            base_rect = char_render.get_rect(topleft=(current_x, base_y))
            self.title_chars.append(
                {
                    "render": char_render,
                    "base_rect": base_rect,
                    "rect": base_rect.copy(),
                }
            )
            current_x += char_render.get_width()

    def _create_buttons(self):
        """Creates button instances with their actions."""
        buttons_y_start = (
            self.menu_y
            + AnimationConfig.TITLE_TOP_MARGIN
            + AnimationConfig.TITLE_HEIGHT
            + AnimationConfig.BUTTONS_TOP_MARGIN
        )

        button_configs = [
            (
                MenuStrings.START_GAME,
                CUSTOM_GOLD,
                CUSTOM_PURPLE,
                self._start_world_selection,
            ),
            (
                MenuStrings.STATISTICS,
                CUSTOM_GOLD,
                CUSTOM_PURPLE,
                lambda: self.app.states.push(StatisticsScene(self.app)),
            ),
            (
                MenuStrings.UPGRADES,
                CUSTOM_GOLD,
                CUSTOM_PURPLE,
                lambda: self.app.states.push(UpgradesSelectionScene(self.app)),
            ),
            (
                MenuStrings.SETTINGS,
                CUSTOM_GOLD,
                CUSTOM_PURPLE,
                lambda: self.app.states.push(SettingsScene(self.app)),
            ),
            (
                MenuStrings.EXIT,
                CUSTOM_PURPLE,
                CUSTOM_GOLD,
                lambda: setattr(self.app, "running", False),
            ),
        ]

        for i, (text, color, hover_color, action) in enumerate(button_configs):
            # Botão Exit menor que os demais
            if i == len(button_configs) - 1:  # Último botão (Exit)
                rect = pygame.Rect(0, 0, 280, 50)
                # Adicionar espaçamento extra antes do botão Exit
                extra_spacing = 30
            else:
                rect = pygame.Rect(0, 0, 380, 60)
                extra_spacing = 0
            rect.center = (
                self.menu_x,
                buttons_y_start + i * AnimationConfig.BUTTON_SPACING + extra_spacing,
            )
            button = Button(text, rect, self.button_font, color, hover_color, action)
            # Configurar delay de entrada (cada botão entra sequencialmente)
            button.entry_delay = AnimationConfig.BUTTON_ENTRY_DELAY + (
                i * AnimationConfig.BUTTON_STAGGER
            )
            self.buttons.append(button)

    def _calculate_wave_offset(
        self,
        time_ms: float,
        index: int,
        amplitude: float,
        speed: Optional[float] = None,
    ) -> int:
        """Calculates offset based on sine wave for animation."""
        if speed is None:
            speed = AnimationConfig.TITLE_ANIM_SPEED
        sine_wave = math.sin(
            (time_ms / 1000.0 * speed) + (index * AnimationConfig.TITLE_PHASE_SHIFT)
        )
        return int(sine_wave * amplitude)

    def enter(self):
        """Called when entering the scene."""
        pygame.mouse.set_visible(True)
        sound_manager.music_state_manager.transition_to(MusicState.MENU)
        # Resetar o auto-play ao entrar no menu
        self.auto_play.reset()

        # Resetar animação de entrada
        self.entry_timer = 0.0
        self.title_entry_progress = 0.0
        self.is_entering = True

        # Resetar delays dos botões
        for i, button in enumerate(self.buttons):
            button.entry_progress = 0.0
            button.entry_delay = AnimationConfig.BUTTON_ENTRY_DELAY + (
                i * AnimationConfig.BUTTON_STAGGER
            )

    def exit(self):
        """Called when exiting the scene."""
        return None

    def handle_event(self, event: pygame.event.Event):
        """Handles user input events."""
        # Não processar eventos durante transição
        if self.transitioning:
            return

        # Delegar eventos para a view ativa
        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            self.difficulty_view.handle_event(event)
            return
        if self.current_view == MenuView.WORLD_SELECTION:
            self.world_selection_view.handle_event(event)
            return

        # View MAIN (menu principal)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Primeiro verificar cliques nos meteoros
            meteor_clicked = False
            for meteor in self.auto_play.meteors[:]:
                if meteor.rect.collidepoint(event.pos):
                    self.auto_play.destroy_meteor(meteor)
                    sound_manager.play_sound("button_click")
                    meteor_clicked = True
                    break

            # Se não clicou em meteoro, verificar botões
            if not meteor_clicked:
                for button in self.buttons:
                    if button.rect.collidepoint(event.pos):
                        button.action()
                        sound_manager.play_sound("button_click")
                        break
        elif event.type == pygame.MOUSEMOTION:
            for button in self.buttons:
                prev_state = button.state
                button.update_hover(event.pos)
                if (
                    button.state == ButtonState.HOVERED
                    and prev_state != ButtonState.HOVERED
                ):
                    # Reproduzir som de hover (reinicia se já estiver tocando)
                    sound_manager.play_sound("button_hover")
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_DOWN:
                self.focused_button_index = (self.focused_button_index + 1) % len(
                    self.buttons
                )
            elif event.key == pygame.K_UP:
                self.focused_button_index = (self.focused_button_index - 1) % len(
                    self.buttons
                )
            elif event.key == pygame.K_RETURN:
                self.buttons[self.focused_button_index].action()
                sound_manager.play_sound("button_click")
            elif event.key == pygame.K_ESCAPE:
                self.app.running = False
            # Update focused states
            for i, button in enumerate(self.buttons):
                button.focused = i == self.focused_button_index

    def update(self, dt: float):
        """Updates scene logic."""
        self.r.starfield.update(dt)
        self.auto_play.update(dt)
        time_ms = pygame.time.get_ticks()

        # Manter a tela preta por um curto periodo antes de iniciar a gameplay.
        if self.game_start_black_hold_active:
            self.game_start_black_hold_timer -= dt
            if self.game_start_black_hold_timer <= 0.0:
                if self.pending_difficulty is not None:
                    self._start_game_with_preset(self.pending_difficulty)
                return

        # Atualizar transição
        if self.transitioning:
            self.transition_progress += dt / self.transition_duration

            if self.transition_progress >= 1.0:
                self.transition_progress = 1.0
                self.transitioning = False

                # Trocar view e inverter direção do fade
                if self.fade_out:
                    # Completou fade out para iniciar jogo.
                    if self.pending_game_start and self.pending_difficulty is not None:
                        self.game_start_black_hold_active = True
                        self.game_start_black_hold_timer = (
                            self.game_start_black_hold_duration
                        )
                        return

                    # Completou fade out, trocar view
                    if self.returning_to_main:
                        self.current_view = MenuView.MAIN
                        self.returning_to_main = False
                        # Resetar animação de entrada do menu
                        self.entry_timer = 0.0
                        self.title_entry_progress = 0.0
                        self.is_entering = True
                        for i, button in enumerate(self.buttons):
                            button.entry_progress = 0.0
                            button.entry_delay = AnimationConfig.BUTTON_ENTRY_DELAY + (
                                i * AnimationConfig.BUTTON_STAGGER
                            )
                    elif self.current_view == MenuView.MAIN:
                        self.current_view = MenuView.WORLD_SELECTION
                        self.world_selection_view.reset()
                    elif self.current_view == MenuView.WORLD_SELECTION:
                        self.current_view = MenuView.DIFFICULTY_SELECTION
                        self.difficulty_view.reset()
                    else:
                        self.current_view = MenuView.MAIN
                        # Resetar animação de entrada do menu
                        self.entry_timer = 0.0
                        self.title_entry_progress = 0.0
                        self.is_entering = True
                        for i, button in enumerate(self.buttons):
                            button.entry_progress = 0.0
                            button.entry_delay = AnimationConfig.BUTTON_ENTRY_DELAY + (
                                i * AnimationConfig.BUTTON_STAGGER
                            )

                    # Iniciar fade in
                    self.fade_out = False
                    self.transitioning = True
                    self.transition_progress = 0.0
                # else: Completou fade in, transição terminada

        # Atualizar view ativa
        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            self.difficulty_view.update(dt)
        elif self.current_view == MenuView.WORLD_SELECTION:
            self.world_selection_view.update(dt)
        else:  # MenuView.MAIN
            # Atualizar animação de entrada
            if self.is_entering:
                self.entry_timer += dt

                # Atualizar progresso do título
                if self.entry_timer >= AnimationConfig.TITLE_ENTRY_DELAY:
                    elapsed = self.entry_timer - AnimationConfig.TITLE_ENTRY_DELAY
                    self.title_entry_progress = min(
                        1.0, elapsed / AnimationConfig.ENTRY_DURATION
                    )

                # Atualizar progresso dos botões
                for button in self.buttons:
                    button.update_entry(dt)

                # Verificar se animação terminou
                all_buttons_visible = all(
                    btn.entry_progress >= 1.0 for btn in self.buttons
                )
                if self.title_entry_progress >= 1.0 and all_buttons_visible:
                    self.is_entering = False

            # Animate title
            for i, char_data in enumerate(self.title_chars):
                char_data["rect"].y = char_data[
                    "base_rect"
                ].y + self._calculate_wave_offset(
                    time_ms, i, AnimationConfig.TITLE_ANIM_RANGE
                )

            # Animate buttons
            for button in self.buttons:
                button.update_animation(
                    time_ms,
                    AnimationConfig.TITLE_ANIM_SPEED,
                    AnimationConfig.TITLE_PHASE_SHIFT,
                    AnimationConfig.BUTTON_ANIM_RANGE,
                )

    def render(self, surface: pygame.Surface):
        """Renders the scene."""
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        # Renderizar auto-play (meteoros e explosões) atrás do menu
        self.auto_play.render(surface)

        # Calcular alpha de transição
        if self.transitioning:
            if self.fade_out:
                alpha_mult = 1.0 - self.transition_progress
            else:
                alpha_mult = self.transition_progress
        else:
            alpha_mult = 1.0

        # Renderizar view ativa
        if self.current_view == MenuView.DIFFICULTY_SELECTION:
            # Criar surface temporária para aplicar fade
            if alpha_mult < 1.0:
                temp_surface = pygame.Surface(
                    (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
                )
                self.difficulty_view.render(temp_surface)
                temp_surface.set_alpha(int(255 * alpha_mult))
                surface.blit(temp_surface, (0, 0))
            else:
                self.difficulty_view.render(surface)
        elif self.current_view == MenuView.WORLD_SELECTION:
            # Criar surface temporária para aplicar fade
            if alpha_mult < 1.0:
                temp_surface = pygame.Surface(
                    (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
                )
                self.world_selection_view.render(temp_surface)
                temp_surface.set_alpha(int(255 * alpha_mult))
                surface.blit(temp_surface, (0, 0))
            else:
                self.world_selection_view.render(surface)
        else:  # MenuView.MAIN
            # Calcular alpha e offset do título
            title_alpha = int(255 * self.title_entry_progress * alpha_mult)
            title_offset_y = int(
                AnimationConfig.ENTRY_OFFSET_Y * (1.0 - self.title_entry_progress)
            )

            # Render title com efeito rainbow se easter egg ativado
            if self.auto_play.is_rainbow_mode():
                # Cores do arco-íris (HSV para RGB)
                rainbow_colors = [
                    (255, 0, 0),  # Vermelho
                    (255, 127, 0),  # Laranja
                    (255, 255, 0),  # Amarelo
                    (0, 255, 0),  # Verde
                    (0, 0, 255),  # Azul
                    (75, 0, 130),  # Índigo
                    (148, 0, 211),  # Violeta
                ]

                time_ms = pygame.time.get_ticks()

                for i, char_data in enumerate(self.title_chars):
                    # Deslocar cores baseado no tempo (cria efeito de "rainbow wave") - MAIS LENTO
                    color_offset = (time_ms / 200) % len(rainbow_colors)
                    base_color_index = int(color_offset)
                    next_color_index = (base_color_index + 1) % len(rainbow_colors)

                    # Interpolação suave entre cores
                    blend_factor = color_offset - base_color_index
                    base_color = rainbow_colors[base_color_index]
                    next_color = rainbow_colors[next_color_index]

                    # Interpolar RGB entre as duas cores
                    interpolated_color = (
                        int(
                            base_color[0]
                            + (next_color[0] - base_color[0]) * blend_factor
                        ),
                        int(
                            base_color[1]
                            + (next_color[1] - base_color[1]) * blend_factor
                        ),
                        int(
                            base_color[2]
                            + (next_color[2] - base_color[2]) * blend_factor
                        ),
                    )

                    # Adicionar pulsação/brilho usando seno - MAIS SUAVE
                    pulse = math.sin((time_ms / 1000) + i * 0.3) * 0.15 + 0.85
                    final_color = (
                        int(interpolated_color[0] * pulse),
                        int(interpolated_color[1] * pulse),
                        int(interpolated_color[2] * pulse),
                    )

                    # Renderizar letra com cor rainbow animada
                    colored_char = self.font.render(
                        MenuStrings.TITLE[i], True, final_color
                    )
                    colored_char.set_alpha(title_alpha)
                    char_pos = (
                        char_data["rect"].x,
                        char_data["rect"].y + title_offset_y,
                    )
                    surface.blit(colored_char, char_pos)
            else:
                # Render normal (sem rainbow)
                for char_data in self.title_chars:
                    char_surface = char_data["render"].copy()
                    char_surface.set_alpha(title_alpha)
                    char_pos = (
                        char_data["rect"].x,
                        char_data["rect"].y + title_offset_y,
                    )
                    surface.blit(char_surface, char_pos)

            # Render buttons com fade de transição
            for button in self.buttons:
                # Modificar temporariamente o entry_progress para aplicar fade de transição
                original_progress = button.entry_progress
                button.entry_progress = button.entry_progress * alpha_mult

                border_color = (
                    self.focused_border_color
                    if button.state == ButtonState.FOCUSED
                    else self.border_color
                )
                button.render(
                    surface, border_color, AnimationConfig.BUTTON_SCALE_FACTOR
                )

                # Restaurar progresso original
                button.entry_progress = original_progress

        # Transicao para gameplay: fade-out para preto e pequena pausa em preto.
        if self.pending_game_start and self.fade_out and self.transitioning:
            black_alpha = int(255 * self.transition_progress)
            black_overlay = pygame.Surface(
                (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
            )
            black_overlay.fill((0, 0, 0, black_alpha))
            surface.blit(black_overlay, (0, 0))
        elif self.game_start_black_hold_active:
            surface.fill(BLACK)

        if self.force_blackout_frame:
            surface.fill(BLACK)
