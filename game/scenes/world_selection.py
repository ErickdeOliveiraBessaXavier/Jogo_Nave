"""
Seleção de Mundo - Sistema de Savepoints

Permite ao jogador escolher em qual mundo iniciar o jogo.
Mostra status de desbloqueio e checkpoint atual.
"""

from enum import Enum
from typing import TYPE_CHECKING, List

import pygame

from ..core.assets import get_font
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.world_config import WorldConfig, get_all_worlds
from ..render.backgrounds import create_background

if TYPE_CHECKING:
    pass


def render_text_wrapped(text, font, color, surface, center_x, start_y, max_width):
    """Renderiza texto com quebra de linha automática, centralizado."""
    words = text.split(" ")
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # Verifica a largura da linha com a nova palavra
        width, _ = font.size(test_line)
        if width <= max_width and current_line:
            current_line.append(word)
        elif not current_line:
            current_line.append(word)  # Garante que pelo menos uma palavra entre
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    y_offset = start_y
    for line in lines:
        rendered_line = font.render(line, True, color)
        line_rect = rendered_line.get_rect(centerx=center_x, top=y_offset)
        surface.blit(rendered_line, line_rect)
        y_offset += (
            font.get_linesize() + 2
        )  # +2 para um pequeno espaçamento entre linhas

    return y_offset


class WorldCardState(Enum):
    """Estados possíveis de um card de mundo."""

    LOCKED = 0
    UNLOCKED = 1
    CHECKPOINT = 2


class WorldCard:
    """Card visual representando um mundo."""

    def __init__(
        self, world_config: WorldConfig, state: WorldCardState, best_score: int = 0
    ):
        self.world_config = world_config
        self.state = state
        self.best_score = best_score
        self.hover = False

        # Dimensões do card
        self.width = 340
        self.height = 220
        self.rect = pygame.Rect(0, 0, self.width, self.height)

        # Cores baseadas no estado
        self._update_colors()

        # Fonte
        self.title_font = get_font(24)
        self.desc_font = get_font(16)
        self.score_font = get_font(18)

    def _update_colors(self):
        """Atualiza cores baseado no estado atual."""
        if self.state == WorldCardState.CHECKPOINT:
            self.border_color = CUSTOM_GOLD
            self.bg_color = (30, 30, 30)
            self.title_color = CUSTOM_GOLD
        elif self.state == WorldCardState.UNLOCKED:
            self.border_color = CUSTOM_PURPLE
            self.bg_color = (20, 20, 20)
            self.title_color = CUSTOM_PURPLE
        else:  # LOCKED
            self.border_color = (100, 100, 100)
            self.bg_color = (15, 15, 15)
            self.title_color = (150, 150, 150)

    def set_position(self, x: int, y: int):
        """Define posição do card."""
        self.rect.topleft = (x, y)

    def update_hover(self, mouse_pos: tuple[int, int]):
        """Atualiza estado de hover."""
        self.hover = self.rect.collidepoint(mouse_pos)

    def render(self, surface: pygame.Surface):
        """Renderiza o card."""
        # Fundo
        pygame.draw.rect(surface, self.bg_color, self.rect, border_radius=10)

        # Borda
        border_width = 3 if self.hover else 2
        pygame.draw.rect(
            surface, self.border_color, self.rect, border_width, border_radius=10
        )

        # Margem interna (Padding)
        padding = 20
        max_text_width = self.width - (padding * 2)

        # Título
        title_bottom = render_text_wrapped(
            text=self.world_config.name,
            font=self.title_font,
            color=self.title_color,
            surface=surface,
            center_x=self.rect.centerx,
            start_y=self.rect.top + 20,
            max_width=max_text_width,
        )

        # Descrição usando a nova função de quebra de linha
        desc_start_y = title_bottom + 10
        desc_color = (
            (100, 100, 100) if self.state == WorldCardState.LOCKED else (200, 200, 200)
        )
        render_text_wrapped(
            text=self.world_config.description,
            font=self.desc_font,
            color=desc_color,
            surface=surface,
            center_x=self.rect.centerx,
            start_y=desc_start_y,
            max_width=max_text_width,
        )

        # Status/Score
        if self.state == WorldCardState.CHECKPOINT:
            status_text = self.score_font.render(
                f"Checkpoint - Best: {self.best_score:,}", True, CUSTOM_GOLD
            )
        elif self.state == WorldCardState.UNLOCKED:
            status_text = self.score_font.render("Desbloqueado", True, CUSTOM_PURPLE)
        else:
            status_text = self.score_font.render("Bloqueado", True, (150, 150, 150))

        status_rect = status_text.get_rect(
            centerx=self.rect.centerx, bottom=self.rect.bottom - 20
        )
        surface.blit(status_text, status_rect)

        # Efeito hover
        if self.hover and self.state != WorldCardState.LOCKED:
            # Brilho sutil
            glow_surface = pygame.Surface(
                (self.width + 10, self.height + 10), pygame.SRCALPHA
            )
            pygame.draw.rect(
                glow_surface,
                (*self.border_color, 50),
                glow_surface.get_rect(),
                border_radius=12,
            )
            surface.blit(glow_surface, (self.rect.x - 5, self.rect.y - 5))


class WorldSelectionView:
    """View para seleção de mundo."""

    def __init__(self, on_world_selected, on_back, renderer, player_profile):
        self.on_world_selected = on_world_selected
        self.on_back = on_back
        self.renderer = renderer
        self.player_profile = player_profile

        # Cards de mundo
        self.world_cards: List[WorldCard] = []
        self.selected_index = 0

        # Layout
        self.card_spacing = 40
        self.cols = 2
        self.rows = 2

        # Navegação por teclado
        self.last_key_time = 0
        self.key_repeat_delay = 200  # ms

        # Background dinâmico
        self.current_background = None
        self.last_selected = -1

    def reset(self):
        """Reinicia a view com dados atualizados."""
        self.world_cards.clear()
        self.selected_index = 0

        # Obter mundos disponíveis
        worlds = get_all_worlds()

        for world_config in worlds:
            # Obter status real do perfil
            if world_config.world_id in self.player_profile.world_unlocks:
                unlock_status = self.player_profile.world_unlocks[world_config.world_id]
                if unlock_status.is_unlocked:
                    if (
                        world_config.world_id
                        == self.player_profile.current_checkpoint_world
                    ):
                        state = WorldCardState.CHECKPOINT
                    else:
                        state = WorldCardState.UNLOCKED
                    best_score = unlock_status.last_best_score_at_checkpoint
                else:
                    state = WorldCardState.LOCKED
                    best_score = 0
            else:
                # Mundo não inicializado ainda
                state = WorldCardState.LOCKED
                best_score = 0

            card = WorldCard(world_config, state, best_score)
            self.world_cards.append(card)

        self._layout_cards()

    def _layout_cards(self):
        """Posiciona os cards em grid."""
        start_x = (
            Config.SCREEN_WIDTH
            - (
                self.cols * self.world_cards[0].width
                + (self.cols - 1) * self.card_spacing
            )
        ) // 2
        start_y = (
            Config.SCREEN_HEIGHT
            - (
                self.rows * self.world_cards[0].height
                + (self.rows - 1) * self.card_spacing
            )
        ) // 2

        for i, card in enumerate(self.world_cards):
            row = i // self.cols
            col = i % self.cols
            x = start_x + col * (card.width + self.card_spacing)
            y = start_y + row * (card.height + self.card_spacing)
            card.set_position(x, y)

    def handle_event(self, event: pygame.event.Event):
        """Processa eventos de entrada."""
        if event.type == pygame.KEYDOWN:
            current_time = pygame.time.get_ticks()

            if (
                event.key == pygame.K_LEFT
                and current_time - self.last_key_time > self.key_repeat_delay
            ):
                self.selected_index = (self.selected_index - 1) % len(self.world_cards)
                self.last_key_time = current_time
                sound_manager.play_sound("button_hover")

            elif (
                event.key == pygame.K_RIGHT
                and current_time - self.last_key_time > self.key_repeat_delay
            ):
                self.selected_index = (self.selected_index + 1) % len(self.world_cards)
                self.last_key_time = current_time
                sound_manager.play_sound("button_hover")

            elif (
                event.key == pygame.K_UP
                and current_time - self.last_key_time > self.key_repeat_delay
            ):
                self.selected_index = (self.selected_index - self.cols) % len(
                    self.world_cards
                )
                self.last_key_time = current_time
                sound_manager.play_sound("button_hover")

            elif (
                event.key == pygame.K_DOWN
                and current_time - self.last_key_time > self.key_repeat_delay
            ):
                self.selected_index = (self.selected_index + self.cols) % len(
                    self.world_cards
                )
                self.last_key_time = current_time
                sound_manager.play_sound("button_hover")

            elif event.key == pygame.K_RETURN:
                self._select_current_world()

            elif event.key == pygame.K_ESCAPE:
                self.on_back()

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, card in enumerate(self.world_cards):
                if (
                    card.rect.collidepoint(event.pos)
                    and card.state != WorldCardState.LOCKED
                ):
                    self.selected_index = i
                    self._select_current_world()
                    break

    def _select_current_world(self):
        """Seleciona o mundo atualmente focado."""
        if self.selected_index < len(self.world_cards):
            card = self.world_cards[self.selected_index]
            if card.state != WorldCardState.LOCKED:
                # TODO: Salvar seleção no perfil
                self.on_world_selected(card.world_config.world_id)
                sound_manager.play_sound("button_click")

    def update(self, _dt: float):
        """Atualiza a view."""
        # Atualizar hover dos cards
        mouse_pos = pygame.mouse.get_pos()
        for card in self.world_cards:
            card.update_hover(mouse_pos)

        # Atualizar background se seleção mudou
        if self.selected_index != self.last_selected:
            self.last_selected = self.selected_index
            if self.selected_index < len(self.world_cards):
                world_config = self.world_cards[self.selected_index].world_config
                theme_str = world_config.theme.value.lower()
                if theme_str == "procedural":
                    # Cycle through themes for procedural worlds
                    themes = ["mountains", "city", "volcanic"]
                    theme_str = themes[(world_config.world_id - 5) % len(themes)]
                elif theme_str == "starfield":
                    # Para STARFIELD, usar o starfield do renderer (mesmo do menu)
                    self.current_background = None
                else:
                    try:
                        self.current_background = create_background(
                            theme_str, Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
                        )
                    except ValueError:
                        self.current_background = None

        # Atualizar animação do background
        if self.current_background:
            self.current_background.update(_dt, 0.5)  # Animação mais fluida

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Fundo preto para evitar transparência
        surface.fill((0, 0, 0))

        # Desenhar background baseado no tema
        if self.current_background:
            # Background temático (MOUNTAINS, CITY, VOLCANIC, PROCEDURAL)
            bg_surface = pygame.Surface(
                (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
            )
            self.current_background.draw(bg_surface)
            bg_surface.set_alpha(76)  # 30% opacidade
            surface.blit(bg_surface, (0, 0))
        else:
            # Para STARFIELD, usar o starfield do renderer (mesmo do menu)
            self.renderer.starfield.draw(surface)

        # Renderizar cards
        for i, card in enumerate(self.world_cards):
            card.render(surface)

            # Destaque para card selecionado
            if i == self.selected_index:
                # Borda extra dourada
                pygame.draw.rect(surface, CUSTOM_GOLD, card.rect, 4, border_radius=12)

        # Instruções
        font = get_font(20)
        instructions = font.render(
            "Use setas para navegar, ENTER para confirmar, ESC para voltar",
            True,
            (200, 200, 200),
        )
        inst_rect = instructions.get_rect(
            centerx=Config.SCREEN_WIDTH // 2, bottom=Config.SCREEN_HEIGHT - 30
        )
        surface.blit(instructions, inst_rect)
