import pygame
import time
from typing import TYPE_CHECKING, List, Optional, Dict, Tuple
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass, field

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GRAY, GREEN, BLUE, YELLOW, RED
from ..core.assets import get_font, get_image, BASE_DIR
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

    # Tabs (abas de categorias)
    tab_buttons: List[pygame.Rect] = field(default_factory=lambda: [])
    
    # Grid de upgrades (lado esquerdo)
    upgrade_grid_cells: List[pygame.Rect] = field(default_factory=lambda: [])
    upgrade_grid_area: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    visible_upgrades: List[UpgradeMeta] = field(default_factory=lambda: [])
    
    # Grid 2x2 de slots ativos (lado direito)
    active_slots: List[pygame.Rect] = field(default_factory=lambda: [])
    active_slots_header: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    
    # Botão de voltar
    back_button: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))


class UpgradesSelectionScene(Scene):
    """Cena de seleção de aprimoramentos com drag-and-drop e grid 2x2."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = Renderer()
        
        # Fonts
        self.title_font = get_font(40)
        self.header_font = get_font(28)
        self.tab_font = get_font(22)
        self.item_font = get_font(18)
        self.small_font = get_font(12)
        self.tiny_font = get_font(12)

        # Ícone de bloqueado
        icon_path = BASE_DIR / "assets" / "images" / "icons" / "icon_bloqueado.png"
        self.locked_icon = get_image(icon_path)

        # Perfil do Jogador
        self.player_profile = PlayerProfile(Path("player_profile.json"))
        
        # Garantir que o loadout tem exatamente UPGRADE_SLOT_COUNT slots
        while len(self.player_profile.upgrade_loadout) < UPGRADE_SLOT_COUNT:
            self.player_profile.upgrade_loadout.append(None)
        if len(self.player_profile.upgrade_loadout) > UPGRADE_SLOT_COUNT:
            self.player_profile.upgrade_loadout = self.player_profile.upgrade_loadout[:UPGRADE_SLOT_COUNT]

        # Organizar upgrades por categoria
        self.all_upgrades = sorted(list_all_upgrades_meta(), key=lambda u: u.name)
        self.categorized_upgrades: Dict[UpgradeCategory, List[UpgradeMeta]] = defaultdict(list)
        for upg in self.all_upgrades:
            self.categorized_upgrades[upg.category].append(upg)
        self.categories = sorted(list(self.categorized_upgrades.keys()), key=lambda c: c.name)

        # Estado da UI - Tabs
        self.selected_category_idx = 0
        self.scroll_offset = 0

        # Estado de Drag and Drop
        self.dragging_upgrade: Optional[UpgradeMeta] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.drag_source_slot: Optional[int] = None  # Se veio da grid direita
        
        # Shake effect para slots bloqueados
        self.shaking_slot: Optional[int] = None
        self.shake_start_time: float = 0.0
        self.shake_duration: float = 0.3  # segundos
        
        # Tooltip
        self.hovered_upgrade: Optional[UpgradeMeta] = None
        self.hovered_slot_idx: Optional[int] = None

        # Layout
        self.layout = UILayout()
        self._calculate_layout()

    def _calculate_layout(self):
        """Calcula as posições e tamanhos dos elementos da UI."""
        screen_w, screen_h = self.app.screen.get_size()
        
        # Dividir tela: 65% esquerda (seleção), 35% direita (ativos)
        left_w = int(screen_w * 0.65)
        right_w = screen_w - left_w
        pad = 20

        # Limpar listas antes de recalcular
        self.layout = UILayout()

        # === LADO ESQUERDO - TABS ===
        tab_h = 50
        tab_y = 80
        tab_w = (left_w - pad * 2) // len(self.categories)
        for i in range(len(self.categories)):
            tab_rect = pygame.Rect(pad + i * tab_w, tab_y, tab_w - 5, tab_h)
            self.layout.tab_buttons.append(tab_rect)

        # === LADO ESQUERDO - GRID DE UPGRADES ===
        grid_start_y = tab_y + tab_h + 20
        
        self.layout.upgrade_grid_area = pygame.Rect(
            pad, grid_start_y, left_w - pad * 2, screen_h - grid_start_y - 80
        )
        
        # Preencher grid com upgrades da categoria atual
        self._rebuild_upgrade_grid()

        # === LADO DIREITO - HEADER ===
        header_y = 100
        self.layout.active_slots_header = pygame.Rect(
            left_w + pad, header_y, right_w - pad * 2, 40
        )

        # === LADO DIREITO - GRID 3x3 ===
        cols = 3
        rows = 3
        slot_gap = 25
        inner_left = left_w + pad
        inner_width = right_w - pad * 2

        # Tamanho do slot calculado para ocupar toda a largura disponível
        slot_size = max(40, (inner_width - (cols - 1) * slot_gap) // cols)
        grid_start_x = inner_left
        grid_start_y = header_y + 80

        for row in range(rows):
            for col in range(cols):
                x = grid_start_x + col * (slot_size + slot_gap)
                y = grid_start_y + row * (slot_size + slot_gap)
                slot_rect = pygame.Rect(x, y, slot_size, slot_size)
                self.layout.active_slots.append(slot_rect)

        # === BOTÃO DE VOLTAR ===
        self.layout.back_button = pygame.Rect(pad, screen_h - 60, 150, 40)
    
    def _rebuild_upgrade_grid(self):
        """Reconstrói a grid de upgrades baseado na categoria atual e scroll."""
        self.layout.upgrade_grid_cells.clear()
        self.layout.visible_upgrades.clear()
        
        category = self.categories[self.selected_category_idx]
        current_upgrades = self.categorized_upgrades[category]
        
        grid_area = self.layout.upgrade_grid_area
        cell_size = 80
        cell_padding = 15
        grid_cols = 4
        
        start_x = grid_area.x
        start_y = grid_area.y
        
        # Calcular quantidade visível corretamente
        rows_visible = grid_area.height // (cell_size + cell_padding)
        visible_count = rows_visible * grid_cols
        visible_upgrades = current_upgrades[self.scroll_offset : self.scroll_offset + visible_count]
        
        for i, upgrade in enumerate(visible_upgrades):
            row = i // grid_cols
            col = i % grid_cols
            x = start_x + col * (cell_size + cell_padding)
            y = start_y + row * (cell_size + cell_padding)
            rect = pygame.Rect(x, y, cell_size, cell_size)
            self.layout.upgrade_grid_cells.append(rect)
            self.layout.visible_upgrades.append(upgrade)

    def _reset_selection(self):
        """Reseta seleção para o topo da grid."""
        self.scroll_offset = 0
        self._rebuild_upgrade_grid()

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

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            
            # Botão de Voltar
            if self.layout.back_button.collidepoint(pos):
                self.app.states.pop()
                return

            # Clicar em Tabs (trocar categoria)
            for i, tab_rect in enumerate(self.layout.tab_buttons):
                if tab_rect.collidepoint(pos):
                    if self.selected_category_idx != i:
                        self.selected_category_idx = i
                        self._reset_selection()
                    return

            # Iniciar Drag: Upgrade da grid esquerda
            for i, cell_rect in enumerate(self.layout.upgrade_grid_cells):
                if cell_rect.collidepoint(pos):
                    upgrade = self.layout.visible_upgrades[i]
                    if upgrade.type in self.player_profile.unlocked_upgrades:
                        self.dragging_upgrade = upgrade
                        self.drag_offset = (pos[0] - cell_rect.x, pos[1] - cell_rect.y)
                        self.drag_source_slot = None
                    return

            # Iniciar Drag: Upgrade da grid 2x2 (slots ativos)
            for i, slot_rect in enumerate(self.layout.active_slots):
                if slot_rect.collidepoint(pos):
                    # Proteção contra índice fora do range
                    if i >= len(self.player_profile.upgrade_loadout):
                        equipped_type = None
                    else:
                        equipped_type = self.player_profile.upgrade_loadout[i]
                    if equipped_type:
                        upgrade_meta = next(
                            (u for u in self.all_upgrades if u.type == equipped_type),
                            None
                        )
                        if upgrade_meta:
                            self.dragging_upgrade = upgrade_meta
                            self.drag_offset = (pos[0] - slot_rect.x, pos[1] - slot_rect.y)
                            self.drag_source_slot = i
                    return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging_upgrade:
                pos = event.pos
                
                # Soltar em um dos slots da grid 2x2
                dropped_in_slot = False
                for i, slot_rect in enumerate(self.layout.active_slots):
                    if slot_rect.collidepoint(pos):
                        # Se tentar soltar em slot bloqueado, tremer
                        if i >= UPGRADE_SLOT_COUNT:
                            self.shaking_slot = i
                            self.shake_start_time = time.time()
                            continue

                        # Se o slot de destino tem um upgrade e a origem também é um slot
                        target_upgrade = self.player_profile.upgrade_loadout[i] if i < len(self.player_profile.upgrade_loadout) else None
                        if target_upgrade and self.drag_source_slot is not None:
                            # Trocar upgrades entre slots
                            source_upgrade = self.dragging_upgrade.type
                            self.player_profile.equip_upgrade(target_upgrade, self.drag_source_slot)
                            self.player_profile.equip_upgrade(source_upgrade, i)
                            dropped_in_slot = True
                            break
                        
                        # Remover de outros slots se já estiver equipado
                        for slot_idx in range(UPGRADE_SLOT_COUNT):
                            if self.player_profile.upgrade_loadout[slot_idx] == self.dragging_upgrade.type:
                                self.player_profile.equip_upgrade(None, slot_idx)
                        
                        self.player_profile.equip_upgrade(self.dragging_upgrade.type, i)
                        dropped_in_slot = True
                        break
                
                # Se veio de um slot e não foi solto em nenhum, remove
                if self.drag_source_slot is not None and not dropped_in_slot:
                    self.player_profile.equip_upgrade(None, self.drag_source_slot)
                
                # Limpar estado de drag
                self.dragging_upgrade = None
                self.drag_offset = (0, 0)
                self.drag_source_slot = None

        # Scroll na grid de upgrades
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:  # Scroll para cima
                if self.layout.upgrade_grid_area.collidepoint(event.pos):
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                    self._rebuild_upgrade_grid()
            elif event.button == 5:  # Scroll para baixo
                if self.layout.upgrade_grid_area.collidepoint(event.pos):
                    category = self.categories[self.selected_category_idx]
                    current_upgrades = self.categorized_upgrades[category]
                    
                    # Calcular max_scroll dinamicamente
                    grid_area = self.layout.upgrade_grid_area
                    cell_size = 80
                    cell_padding = 15
                    grid_cols = 4
                    rows_visible = grid_area.height // (cell_size + cell_padding)
                    visible_count = rows_visible * grid_cols
                    max_scroll = max(0, len(current_upgrades) - visible_count)
                    
                    self.scroll_offset = min(max_scroll, self.scroll_offset + 1)
                    self._rebuild_upgrade_grid()

    def update(self, dt: float):
        self.r.starfield.update(dt)
        
        # Limpar shake se o tempo expirou
        if self.shaking_slot is not None:
            if time.time() - self.shake_start_time >= self.shake_duration:
                self.shaking_slot = None
        
        # Atualizar hover state
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_upgrade = None
        self.hovered_slot_idx = None
        
        if not self.dragging_upgrade:
            # Hover sobre upgrades da grid
            for i, cell_rect in enumerate(self.layout.upgrade_grid_cells):
                if cell_rect.collidepoint(mouse_pos):
                    self.hovered_upgrade = self.layout.visible_upgrades[i]
                    break
            
            # Hover sobre slots ativos
            for i, slot_rect in enumerate(self.layout.active_slots):
                if slot_rect.collidepoint(mouse_pos):
                    self.hovered_slot_idx = i
                    break

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        # Título
        title = self.title_font.render("Arsenal de Aprimoramentos", True, WHITE)
        surface.blit(title, (20, 20))

        # Desenhar elementos
        self._draw_tabs(surface)
        self._draw_upgrade_grid(surface)
        self._draw_active_slots(surface)
        self._draw_back_button(surface)
        
        # Desenhar upgrade sendo arrastado (último para ficar por cima)
        if self.dragging_upgrade:
            self._draw_dragging_upgrade(surface)
        
        # Desenhar tooltip
        if self.hovered_upgrade and not self.dragging_upgrade:
            self._draw_tooltip(surface)

    def _draw_tabs(self, surface: pygame.Surface):
        """Desenha as abas de categorias."""
        for i, cat in enumerate(self.categories):
            is_selected = i == self.selected_category_idx
            rect = self.layout.tab_buttons[i]

            bg_color = (50, 50, 100) if is_selected else (30, 30, 30)
            border_color = BLUE if is_selected else GRAY
            
            pygame.draw.rect(surface, bg_color, rect, border_radius=8)
            pygame.draw.rect(surface, border_color, rect, 2, border_radius=8)

            text = self.tab_font.render(cat.name.upper(), True, WHITE)
            surface.blit(
                text,
                (
                    rect.x + (rect.w - text.get_width()) // 2,
                    rect.y + (rect.h - text.get_height()) // 2,
                ),
            )

    def _draw_upgrade_grid(self, surface: pygame.Surface):
        """Desenha a grid de upgrades do lado esquerdo."""
        for i, cell_rect in enumerate(self.layout.upgrade_grid_cells):
            upgrade = self.layout.visible_upgrades[i]
            unlocked = upgrade.type in self.player_profile.unlocked_upgrades
            equipped = self.player_profile.get_equipped_slot(upgrade.type) is not None
            is_hovered = self.hovered_upgrade == upgrade

            # Background
            bg_color = (40, 40, 40) if unlocked else (25, 25, 25)
            if is_hovered and unlocked:
                bg_color = (60, 60, 60)
            
            border_color = GRAY
            if equipped:
                border_color = YELLOW
            elif not unlocked:
                border_color = RED
            
            pygame.draw.rect(surface, bg_color, cell_rect, border_radius=6)
            pygame.draw.rect(surface, border_color, cell_rect, 2, border_radius=6)

            # Ícone (círculo colorido)
            icon_center = cell_rect.center
            icon_radius = 25
            icon_color = GREEN if unlocked else (80, 80, 80)
            pygame.draw.circle(surface, icon_color, icon_center, icon_radius)
            
            # Letra inicial do nome
            initial = upgrade.name[0].upper()
            initial_text = self.header_font.render(initial, True, WHITE if unlocked else (50, 50, 50))
            surface.blit(
                initial_text,
                (
                    icon_center[0] - initial_text.get_width() // 2,
                    icon_center[1] - initial_text.get_height() // 2,
                ),
            )

            # Indicador de equipado
            if equipped:
                badge_rect = pygame.Rect(cell_rect.right - 20, cell_rect.y + 5, 15, 15)
                pygame.draw.circle(surface, YELLOW, badge_rect.center, 7)
                check_text = self.tiny_font.render("E", True, BLACK)
                surface.blit(check_text, (badge_rect.x + 3, badge_rect.y + 1))

    def _draw_active_slots(self, surface: pygame.Surface):
        """Desenha a grid 2x2 de slots ativos do lado direito."""
        # Header
        header_rect = self.layout.active_slots_header
        header_text = self.header_font.render("APRIMORAMENTOS", True, WHITE)
        surface.blit(header_text, (header_rect.x, header_rect.y))
        
        # Contador de slots
        equipped_count = sum(1 for u in self.player_profile.upgrade_loadout if u is not None)
        counter_text = self.item_font.render(f"{equipped_count}/{UPGRADE_SLOT_COUNT}", True, GRAY)
        surface.blit(counter_text, (header_rect.right - counter_text.get_width(), header_rect.y + 5))

        # Slots
        for i, slot_rect in enumerate(self.layout.active_slots):
            # Proteção contra índice fora do range
            if i >= len(self.player_profile.upgrade_loadout):
                equipped_type = None
            else:
                equipped_type = self.player_profile.upgrade_loadout[i]
            locked = i >= UPGRADE_SLOT_COUNT
            is_hovered = (self.hovered_slot_idx == i) and (not locked)
            
            # Aplicar shake effect se este slot está tremendo
            draw_rect = slot_rect.copy()
            if self.shaking_slot == i:
                elapsed = time.time() - self.shake_start_time
                progress = elapsed / self.shake_duration
                if progress < 1.0:
                    # Onda senoidal para movimento suave
                    import math
                    shake_intensity = 8 * (1.0 - progress)  # Diminui com o tempo
                    shake_offset = int(shake_intensity * math.sin(progress * 20))
                    draw_rect.x += shake_offset

            # Background
            if equipped_type:
                bg_color = (40, 50, 40) if not is_hovered else (50, 60, 50)
            else:
                bg_color = (30, 30, 30) if not is_hovered else (40, 40, 40)
            
            border_color = YELLOW if is_hovered else (80, 80, 80) if locked else GRAY
            border_style = 2 if equipped_type else 1
            
            pygame.draw.rect(surface, bg_color, draw_rect, border_radius=10)
            
            # Borda tracejada para slots vazios (não bloqueados)
            if not equipped_type and not locked:
                self._draw_dashed_rect(surface, draw_rect, border_color)
            else:
                pygame.draw.rect(surface, border_color, draw_rect, border_style, border_radius=10)

            # Label do slot (sem texto 'BLOQUEADO')
            slot_label = self.small_font.render(f"SLOT {i+1}", True, (120, 120, 120) if locked else GRAY)
            surface.blit(slot_label, (draw_rect.x + 10, draw_rect.y + 5))

            # Conteúdo do slot
            if equipped_type:
                upgrade_meta = next(
                    (u for u in self.all_upgrades if u.type == equipped_type),
                    None
                )
                if upgrade_meta:
                    # Ícone
                    icon_center = (draw_rect.centerx, draw_rect.centery - 10)
                    pygame.draw.circle(surface, GREEN, icon_center, 30)
                    
                    initial = upgrade_meta.name[0].upper()
                    initial_text = self.header_font.render(initial, True, WHITE)
                    surface.blit(
                        initial_text,
                        (
                            icon_center[0] - initial_text.get_width() // 2,
                            icon_center[1] - initial_text.get_height() // 2,
                        ),
                    )
                    
                    # Nome
                    name_text = self.small_font.render(upgrade_meta.name, True, YELLOW)
                    surface.blit(
                        name_text,
                        (
                            draw_rect.centerx - name_text.get_width() // 2,
                            draw_rect.bottom - 25,
                    ),
                )
            else:
                if locked:
                    # Desenhar ícone de bloqueado centralizado
                    icon_size = min(draw_rect.width, draw_rect.height) // 2
                    icon_scaled = pygame.transform.scale(self.locked_icon, (icon_size, icon_size))
                    icon_x = draw_rect.centerx - icon_size // 2
                    icon_y = draw_rect.centery - icon_size // 2
                    surface.blit(icon_scaled, (icon_x, icon_y))
                else:
                    empty_text = self.item_font.render("VAZIO", True, (60, 60, 60))
                    surface.blit(
                        empty_text,
                        (
                            draw_rect.centerx - empty_text.get_width() // 2,
                            draw_rect.centery - empty_text.get_height() // 2,
                        ),
                    )

    def _draw_back_button(self, surface: pygame.Surface):
        """Desenha o botão de voltar."""
        back_rect = self.layout.back_button
        is_hovered = back_rect.collidepoint(pygame.mouse.get_pos())
        bg_color = tuple(min(c + 20, 255) for c in GRAY) if is_hovered else GRAY
        pygame.draw.rect(surface, bg_color, back_rect, border_radius=8)
        pygame.draw.rect(surface, WHITE, back_rect, 2, border_radius=8)
        back_text = self.item_font.render("Voltar", True, WHITE)
        surface.blit(
            back_text,
            (
                back_rect.x + (back_rect.w - back_text.get_width()) // 2,
                back_rect.y + (back_rect.h - back_text.get_height()) // 2,
            ),
        )

    def _draw_dragging_upgrade(self, surface: pygame.Surface):
        """Desenha o upgrade sendo arrastado."""
        if not self.dragging_upgrade:
            return
        
        mouse_pos = pygame.mouse.get_pos()
        drag_x = mouse_pos[0] - self.drag_offset[0]
        drag_y = mouse_pos[1] - self.drag_offset[1]
        drag_rect = pygame.Rect(drag_x, drag_y, 80, 80)

        # Sombra
        shadow_rect = drag_rect.copy()
        shadow_rect.x += 5
        shadow_rect.y += 5
        shadow_surf = pygame.Surface((80, 80), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0, 0, 0, 100), shadow_surf.get_rect(), border_radius=6)
        surface.blit(shadow_surf, shadow_rect.topleft)

        # Upgrade com transparência
        drag_surf = pygame.Surface((80, 80), pygame.SRCALPHA)
        pygame.draw.rect(drag_surf, (60, 60, 60, 200), drag_surf.get_rect(), border_radius=6)
        pygame.draw.rect(drag_surf, (YELLOW[0], YELLOW[1], YELLOW[2], 220), drag_surf.get_rect(), 3, border_radius=6)
        
        # Ícone
        pygame.draw.circle(drag_surf, GREEN, (40, 40), 25)
        initial = self.dragging_upgrade.name[0].upper()
        initial_text = self.header_font.render(initial, True, WHITE)
        drag_surf.blit(
            initial_text,
            (40 - initial_text.get_width() // 2, 40 - initial_text.get_height() // 2),
        )
        
        surface.blit(drag_surf, drag_rect.topleft)

    def _draw_tooltip(self, surface: pygame.Surface):
        """Desenha tooltip ao passar mouse sobre upgrade."""
        if not self.hovered_upgrade:
            return
        
        mouse_pos = pygame.mouse.get_pos()
        upgrade = self.hovered_upgrade
        
        # Tamanho do tooltip
        tooltip_w = 300
        tooltip_h = 150
        tooltip_x = mouse_pos[0] + 20
        tooltip_y = mouse_pos[1] + 20
        
        # Ajustar para não sair da tela
        screen_w, screen_h = self.app.screen.get_size()
        if tooltip_x + tooltip_w > screen_w:
            tooltip_x = mouse_pos[0] - tooltip_w - 20
        if tooltip_y + tooltip_h > screen_h:
            tooltip_y = mouse_pos[1] - tooltip_h - 20
        
        tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_w, tooltip_h)
        
        # Background semi-transparente
        tooltip_surf = pygame.Surface((tooltip_w, tooltip_h), pygame.SRCALPHA)
        pygame.draw.rect(tooltip_surf, (20, 20, 30, 240), tooltip_surf.get_rect(), border_radius=8)
        pygame.draw.rect(tooltip_surf, (WHITE[0], WHITE[1], WHITE[2], 220), tooltip_surf.get_rect(), 2, border_radius=8)
        
        # Nome
        name_text = self.item_font.render(upgrade.name, True, YELLOW)
        tooltip_surf.blit(name_text, (10, 10))
        
        # Descrição
        desc_y = 40
        desc_lines = self._wrap_text(upgrade.desc, self.small_font, tooltip_w - 20)
        for line in desc_lines[:3]:  # Máximo 3 linhas
            line_text = self.small_font.render(line, True, WHITE)
            tooltip_surf.blit(line_text, (10, desc_y))
            desc_y += 18
        
        # Atributos
        attr_y = desc_y + 10
        attrs: List[str] = []
        attrs.append(f"Cooldown: {upgrade.base_cooldown}s")
        if upgrade.base_duration > 0:
            attrs.append(f"Duracao: {upgrade.base_duration}s")
        attrs.append(f"Cargas: {upgrade.base_charges or 'ilim'}")
        
        for attr in attrs:
            attr_text = self.tiny_font.render(attr, True, GRAY)
            tooltip_surf.blit(attr_text, (10, attr_y))
            attr_y += 15
        
        surface.blit(tooltip_surf, tooltip_rect.topleft)

    def _draw_dashed_rect(self, surface: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int]):
        """Desenha borda tracejada."""
        dash_length = 10
        gap_length = 5
        
        # Top
        x = rect.x
        while x < rect.right:
            pygame.draw.line(surface, color, (x, rect.y), (min(x + dash_length, rect.right), rect.y), 2)
            x += dash_length + gap_length
        
        # Bottom
        x = rect.x
        while x < rect.right:
            pygame.draw.line(surface, color, (x, rect.bottom), (min(x + dash_length, rect.right), rect.bottom), 2)
            x += dash_length + gap_length
        
        # Left
        y = rect.y
        while y < rect.bottom:
            pygame.draw.line(surface, color, (rect.x, y), (rect.x, min(y + dash_length, rect.bottom)), 2)
            y += dash_length + gap_length
        
        # Right
        y = rect.y
        while y < rect.bottom:
            pygame.draw.line(surface, color, (rect.right, y), (rect.right, min(y + dash_length, rect.bottom)), 2)
            y += dash_length + gap_length

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """Quebra o texto em várias linhas para caber na largura máxima."""
        words = text.split(" ")
        lines: List[str] = []
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "
        if current_line:
            lines.append(current_line.strip())
        return lines
