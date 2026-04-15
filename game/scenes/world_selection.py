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

if TYPE_CHECKING:
    pass


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
        self.width = 300
        self.height = 200
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

        # Título
        title_text = self.title_font.render(
            self.world_config.name, True, self.title_color
        )
        title_rect = title_text.get_rect(
            centerx=self.rect.centerx, top=self.rect.top + 15
        )
        surface.blit(title_text, title_rect)

        # Descrição
        desc_text = self.desc_font.render(
            self.world_config.description, True, (200, 200, 200)
        )
        desc_rect = desc_text.get_rect(
            centerx=self.rect.centerx, top=title_rect.bottom + 10
        )
        surface.blit(desc_text, desc_rect)

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
            centerx=self.rect.centerx, bottom=self.rect.bottom - 15
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
        self.card_spacing = 50
        self.cols = 2
        self.rows = 2

        # Navegação por teclado
        self.last_key_time = 0
        self.key_repeat_delay = 200  # ms

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

    def update(self, dt: float):
        """Atualiza a view."""
        # Atualizar hover dos cards
        mouse_pos = pygame.mouse.get_pos()
        for card in self.world_cards:
            card.update_hover(mouse_pos)

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        surface.fill((10, 10, 20))  # Fundo escuro

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
