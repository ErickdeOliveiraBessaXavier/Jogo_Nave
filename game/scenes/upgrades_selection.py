import pygame
from typing import TYPE_CHECKING, List, Optional, Dict
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass, field

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GRAY, GREEN, BLUE, YELLOW, RED
from ..core.assets import get_font
from ..core.upgrades import (
    list_all_upgrades_meta,
    UpgradeCategory,
    UpgradeMeta,
)
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from ..render.renderer import Renderer
from ..core.meta_progression import PlayerProfile

if TYPE_CHECKING:
    from ..app import GameApp


@dataclass
class UILayout:
    """Estrutura para armazenar os retângulos da UI com tipos definidos."""

    cat_col: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    cat_buttons: List[pygame.Rect] = field(default_factory=lambda: [])
    upg_col: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    upg_cards: List[pygame.Rect] = field(default_factory=lambda: [])
    det_col: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    det_box: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    slots_header: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    slots: List[pygame.Rect] = field(default_factory=lambda: [])
    slot_clear_buttons: List[pygame.Rect] = field(default_factory=lambda: [])
    back_button: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))


class UpgradesSelectionScene(Scene):
    """Cena de seleção de aprimoramentos com layout gamificado."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = Renderer()
        # Fonts
        self.title_font = get_font(40)
        self.header_font = get_font(24)
        self.item_font = get_font(20)
        self.small_font = get_font(16)
        self.micro_font = get_font(12)

        # Perfil do Jogador
        self.player_profile = PlayerProfile(Path("player_profile.json"))

        # Organizar upgrades por categoria
        self.all_upgrades = sorted(list_all_upgrades_meta(), key=lambda u: u.name)
        self.categorized_upgrades: Dict[UpgradeCategory, List[UpgradeMeta]] = defaultdict(
            list
        )
        for upg in self.all_upgrades:
            self.categorized_upgrades[upg.category].append(upg)
        self.categories = sorted(
            list(self.categorized_upgrades.keys()), key=lambda c: c.name
        )

        # Estado da UI
        self.selected_category_idx = 0
        self.selected_upgrade_idx = 0
        self.scroll_offset = 0

        # Layout
        self.layout = UILayout()
        self._calculate_layout()

    def _calculate_layout(self):
        """Calcula as posições e tamanhos dos elementos da UI."""
        screen_w, screen_h = self.app.screen.get_size()
        col_w = screen_w / 3
        pad = 20

        # Limpar listas antes de recalcular
        self.layout = UILayout()

        # Coluna 1: Categorias
        self.layout.cat_col = pygame.Rect(0, 0, col_w, screen_h)
        cat_y = 100
        cat_h = 50
        for i, _ in enumerate(self.categories):
            rect = pygame.Rect(pad, cat_y + i * (cat_h + pad), col_w - 2 * pad, cat_h)
            self.layout.cat_buttons.append(rect)

        # Coluna 2: Upgrades
        self.layout.upg_col = pygame.Rect(col_w, 0, col_w, screen_h)
        upg_y = 100
        upg_card_h = 80
        for i in range(7):  # Visível de até 7 upgrades
            rect = pygame.Rect(
                col_w + pad, upg_y + i * (upg_card_h + pad), col_w - 2 * pad, upg_card_h
            )
            self.layout.upg_cards.append(rect)

        # Coluna 3: Detalhes e Slots
        self.layout.det_col = pygame.Rect(col_w * 2, 0, col_w, screen_h)
        self.layout.det_box = pygame.Rect(col_w * 2 + pad, 100, col_w - 2 * pad, 250)
        self.layout.slots_header = pygame.Rect(
            col_w * 2 + pad, 370, col_w - 2 * pad, 40
        )
        slot_h = 100
        for i in range(UPGRADE_SLOT_COUNT):
            rect = pygame.Rect(
                col_w * 2 + pad, 420 + i * (slot_h + pad), col_w - 2 * pad, slot_h
            )
            self.layout.slots.append(rect)
            clear_btn_rect = pygame.Rect(rect.right - 40, rect.bottom - 30, 35, 25)
            self.layout.slot_clear_buttons.append(clear_btn_rect)

        # Botão de Voltar
        self.layout.back_button = pygame.Rect(pad, screen_h - 60, 150, 40)

    def _reset_selection(self):
        self.selected_upgrade_idx = 0
        self.scroll_offset = 0

    def enter(self):
        pygame.mouse.set_visible(True)
        self._calculate_layout()
        self._reset_selection()

    def exit(self):
        self.player_profile.save()

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.states.pop()

        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            if event.button == 1:  # Botão esquerdo
                # Botão de Voltar
                if self.layout.back_button.collidepoint(pos):
                    self.app.states.pop()
                    return

                # Categorias
                for i, rect in enumerate(self.layout.cat_buttons):
                    if rect.collidepoint(pos) and self.selected_category_idx != i:
                        self.selected_category_idx = i
                        self._reset_selection()
                        return

                # Cartas de Upgrades
                current_upgrades = self.categorized_upgrades[
                    self.categories[self.selected_category_idx]
                ]
                visible_upgrades = current_upgrades[
                    self.scroll_offset : self.scroll_offset + 7
                ]
                for i, rect in enumerate(self.layout.upg_cards):
                    if i < len(visible_upgrades) and rect.collidepoint(pos):
                        self.selected_upgrade_idx = self.scroll_offset + i
                        return

                # Slots para equipar
                selected_upgrade = self.get_selected_upgrade()
                if (
                    selected_upgrade
                    and selected_upgrade.type in self.player_profile.unlocked_upgrades
                ):
                    for i, rect in enumerate(self.layout.slots):
                        if rect.collidepoint(pos):
                            self.player_profile.equip_upgrade(selected_upgrade.type, i)
                            return

                # Botões de Limpar Slot
                for i, rect in enumerate(self.layout.slot_clear_buttons):
                    if rect.collidepoint(pos):
                        self.player_profile.equip_upgrade(None, i)
                        return

            elif event.button == 4:  # Scroll para cima
                if self.layout.upg_col.collidepoint(event.pos):
                    self.scroll_offset = max(0, self.scroll_offset - 1)
            elif event.button == 5:  # Scroll para baixo
                if self.layout.upg_col.collidepoint(event.pos):
                    current_upgrades = self.categorized_upgrades[
                        self.categories[self.selected_category_idx]
                    ]
                    max_scroll = max(0, len(current_upgrades) - 7)
                    self.scroll_offset = min(max_scroll, self.scroll_offset + 1)

    def get_selected_upgrade(self) -> Optional[UpgradeMeta]:
        """Retorna o metadado do upgrade atualmente selecionado."""
        try:
            category = self.categories[self.selected_category_idx]
            upgrades = self.categorized_upgrades[category]
            return upgrades[self.selected_upgrade_idx]
        except IndexError:
            return None

    def update(self, dt: float):
        self.r.starfield.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        # Título
        title = self.title_font.render("Arsenal de Aprimoramentos", True, WHITE)
        surface.blit(title, (20, 20))

        # Desenhar colunas
        self._draw_categories(surface)
        self._draw_upgrades_grid(surface)
        self._draw_details_and_slots(surface)

        # Botão de Voltar
        back_rect = self.layout.back_button
        pygame.draw.rect(surface, (50, 50, 50), back_rect, border_radius=5)
        pygame.draw.rect(surface, WHITE, back_rect, 2, border_radius=5)
        back_text = self.item_font.render("Voltar", True, WHITE)
        surface.blit(
            back_text,
            (
                back_rect.x + (back_rect.w - back_text.get_width()) // 2,
                back_rect.y + (back_rect.h - back_text.get_height()) // 2,
            ),
        )

    def _draw_categories(self, surface: pygame.Surface):
        rects = self.layout.cat_buttons
        for i, cat in enumerate(self.categories):
            is_selected = i == self.selected_category_idx
            rect = rects[i]

            bg_color = (40, 40, 80) if is_selected else (30, 30, 30)
            border_color = BLUE if is_selected else GRAY
            pygame.draw.rect(surface, bg_color, rect, border_radius=8)
            pygame.draw.rect(surface, border_color, rect, 2, border_radius=8)

            text = self.header_font.render(cat.name.capitalize(), True, WHITE)
            surface.blit(
                text,
                (
                    rect.x + (rect.w - text.get_width()) // 2,
                    rect.y + (rect.h - text.get_height()) // 2,
                ),
            )

    def _draw_upgrades_grid(self, surface: pygame.Surface):
        category = self.categories[self.selected_category_idx]
        current_upgrades = self.categorized_upgrades[category]
        visible_upgrades = current_upgrades[self.scroll_offset : self.scroll_offset + 7]

        for i, upgrade in enumerate(visible_upgrades):
            is_selected = (self.scroll_offset + i) == self.selected_upgrade_idx
            rect = self.layout.upg_cards[i]

            unlocked = upgrade.type in self.player_profile.unlocked_upgrades
            equipped_slot = self.player_profile.get_equipped_slot(upgrade.type)

            bg_color = (35, 35, 35)
            border_color = GRAY
            if is_selected:
                bg_color = (50, 50, 50)
                border_color = WHITE
            if equipped_slot is not None:
                border_color = YELLOW

            pygame.draw.rect(surface, bg_color, rect, border_radius=8)
            pygame.draw.rect(surface, border_color, rect, 2, border_radius=8)

            icon_rect = pygame.Rect(rect.x + 10, rect.y + 10, 60, 60)
            icon_color = GREEN if unlocked else RED
            pygame.draw.rect(surface, icon_color, icon_rect, border_radius=6)

            name_color = WHITE if unlocked else GRAY
            name_text = self.item_font.render(upgrade.name, True, name_color)
            surface.blit(name_text, (rect.x + 80, rect.y + 15))

            status_text_str = ""
            status_color = WHITE
            if equipped_slot is not None:
                status_text_str = f"EQUIPADO (SLOT {equipped_slot + 1})"
                status_color = YELLOW
            elif not unlocked:
                status_text_str = "BLOQUEADO"
                status_color = RED

            if status_text_str:
                s_text = self.small_font.render(status_text_str, True, status_color)
                surface.blit(s_text, (rect.x + 80, rect.y + 45))

    def _draw_details_and_slots(self, surface: pygame.Surface):
        details_rect = self.layout.det_box
        pygame.draw.rect(surface, (20, 20, 20), details_rect, border_radius=8)
        pygame.draw.rect(surface, GRAY, details_rect, 1, border_radius=8)

        selected_upgrade = self.get_selected_upgrade()
        if selected_upgrade:
            name_text = self.header_font.render(selected_upgrade.name, True, WHITE)
            surface.blit(name_text, (details_rect.x + 15, details_rect.y + 15))

            desc_lines = self._wrap_text(
                selected_upgrade.desc, self.small_font, details_rect.width - 30
            )
            for i, line in enumerate(desc_lines):
                line_text = self.small_font.render(line, True, GRAY)
                surface.blit(
                    line_text, (details_rect.x + 15, details_rect.y + 60 + i * 20)
                )

            y_offset = details_rect.y + 60 + len(desc_lines) * 20 + 20
            attrs: List[Optional[str]] = [
                f"Cooldown: {selected_upgrade.base_cooldown}s",
                f"Duração: {selected_upgrade.base_duration}s"
                if selected_upgrade.base_duration > 0
                else None,
                f"Cargas: {selected_upgrade.base_charges or '∞'}",
            ]
            for attr in filter(None, attrs):
                attr_text = self.small_font.render(attr, True, WHITE)
                surface.blit(attr_text, (details_rect.x + 15, y_offset))
                y_offset += 25

        header_rect = self.layout.slots_header
        slots_header_text = self.header_font.render("Slots Equipados", True, WHITE)
        surface.blit(
            slots_header_text,
            (
                header_rect.x,
                header_rect.y + (header_rect.h - slots_header_text.get_height()) // 2,
            ),
        )

        for i, rect in enumerate(self.layout.slots):
            equipped_type = self.player_profile.upgrade_loadout[i]

            pygame.draw.rect(surface, (25, 25, 25), rect, border_radius=10)
            pygame.draw.rect(surface, GRAY, rect, 2, border_radius=10)

            slot_text = self.item_font.render(f"SLOT {i+1}", True, GRAY)
            surface.blit(slot_text, (rect.x + 15, rect.y + 10))

            if equipped_type:
                meta = next(
                    (u for u in self.all_upgrades if u.type == equipped_type), None
                )
                if meta:
                    name_text = self.item_font.render(meta.name, True, YELLOW)
                    surface.blit(
                        name_text,
                        (
                            rect.centerx - name_text.get_width() // 2,
                            rect.centery - name_text.get_height() // 2,
                        ),
                    )

                clear_rect = self.layout.slot_clear_buttons[i]
                pygame.draw.rect(surface, RED, clear_rect, border_radius=5)
                clear_text = self.micro_font.render("X", True, WHITE)
                surface.blit(
                    clear_text,
                    (
                        clear_rect.x + (clear_rect.w - clear_text.get_width()) // 2,
                        clear_rect.y + (clear_rect.h - clear_text.get_height()) // 2,
                    ),
                )
            else:
                empty_text = self.item_font.render("-- Vazio --", True, GRAY)
                surface.blit(
                    empty_text,
                    (
                        rect.centerx - empty_text.get_width() // 2,
                        rect.centery - empty_text.get_height() // 2,
                    ),
                )

    def _wrap_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> List[str]:
        """Quebra o texto em várias linhas para caber na largura máxima."""
        words = text.split(" ")
        lines: List[str] = []
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < max_width:
                current_line = test_line
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        lines.append(current_line.strip())
        return lines
