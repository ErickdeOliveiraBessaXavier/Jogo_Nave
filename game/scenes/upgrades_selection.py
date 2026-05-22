import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_font, get_image
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.ship_types import (
    ShipProfile,
    all_ship_profiles,
    format_ship_description,
    get_ship_profile,
)
from ..core.state import Scene
from ..core.upgrades import UpgradeMeta, get_upgrade_icon, list_all_upgrades_meta
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from .ui_helpers import wrap_text, draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp


@dataclass
class UILayout:
    """Estrutura para as 3 colunas da Central de Loadout."""

    # Áreas principais
    left_area: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    center_area: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    right_area: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))

    # Esquerda: Arsenal
    active_slots: List[pygame.Rect] = field(default_factory=lambda: [])
    active_slots_header: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )
    upgrade_grid_cells: List[pygame.Rect] = field(default_factory=lambda: [])
    visible_upgrades: List[UpgradeMeta] = field(default_factory=lambda: [])
    upgrade_scroll_area: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )

    # Direita: Hangar
    stats_area: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    ship_grid_cells: List[pygame.Rect] = field(default_factory=lambda: [])
    visible_ships: List[ShipProfile] = field(default_factory=lambda: [])
    ship_scroll_area: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )

    # Centro: Preview
    ship_preview_rect: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )

    # Botão de voltar
    back_button: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))


class FloatingMessage:
    """Mensagem flutuante para feedback visual."""

    def __init__(
        self,
        x: float,
        y: float,
        message: str,
        color: Tuple[int, int, int] = (255, 100, 100),
    ):
        self.x, self.y, self.message, self.color = x, y, message, color
        self.alpha, self.lifetime, self.dy = 255, 1.5, -60.0
        self.font, self.fade_start = get_font(20), 0.5

    def update(self, dt: float) -> None:
        self.y += self.dy * dt
        self.lifetime -= dt
        if self.lifetime <= self.fade_start:
            self.alpha = max(0, int(255 * (self.lifetime / self.fade_start)))

    def draw(self, surface: pygame.Surface) -> None:
        if self.alpha <= 0:
            return
        surf = self.font.render(self.message, True, self.color)
        surf.set_alpha(self.alpha)
        surface.blit(surf, surf.get_rect(center=(int(self.x), int(self.y))))

    def is_dead(self) -> bool:
        return self.lifetime <= 0


class UpgradesSelectionScene(Scene):
    """Central de Loadout Unificada (Refinamento Visual e Alinhamento)."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = app.renderer
        self.title_font = get_font(36)
        self.header_font = get_font(18)
        self.item_font = get_font(16)
        self.small_font = get_font(13)
        self.tiny_font = get_font(11)

        # Metrics para consistência total
        self.MARGIN = 24
        self.GAP = 12
        self.RADIUS = 8

        self.locked_icon = get_image(
            BASE_DIR / "assets" / "images" / "icons" / "icon_bloqueado.png"
        )
        self.star_icon = get_image(
            BASE_DIR / "assets" / "images" / "icons" / "icon_star.png"
        )
        self.star_icon_small = pygame.transform.scale(self.star_icon, (18, 18))

        # Reusa a instância oficial do app. Criar uma nova aqui causaria
        # divergência: as mudanças (loadout/nave) seriam salvas no JSON mas
        # ficariam invisíveis para PlayingScene, que consome ``app.player_profile``.
        self.player_profile = self.app.player_profile
        self._ensure_slots()

        # Todos os upgrades em ordem alfabética
        self.all_upgrades = sorted(
            list_all_upgrades_meta(), key=lambda u: u.name.lower()
        )

        # Estado do Scroll e UI
        self.upgrade_scroll = 0
        self.ship_scroll = 0
        self.max_upgrade_scroll = 0
        self.max_ship_scroll = 0

        # Drag and Drop para upgrades
        self.dragging_upgrade: Optional[UpgradeMeta] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.drag_source_slot: Optional[int] = None
        self.drag_invalid_target = False

        self.hovered_upgrade: Optional[UpgradeMeta] = None
        self.hovered_ship: Optional[ShipProfile] = None
        self.hovered_slot_idx: Optional[int] = None

        self.shaking_slot: Optional[int] = None
        self.shaking_ship_id: Optional[str] = None
        self.shake_start_time = 0.0
        self.shake_duration = 0.3

        self.layout = UILayout()
        self._calculate_layout()

        self.floating_messages: List[FloatingMessage] = []
        self.transitioning, self.transition_progress, self.fade_out = False, 0.0, False
        self.transition_duration = 0.3
        self.entry_progress, self.is_entering, self.entry_duration = 0.0, True, 0.4

    def _ensure_slots(self):
        while len(self.player_profile.upgrade_loadout) < UPGRADE_SLOT_COUNT:
            self.player_profile.upgrade_loadout.append(None)
        if len(self.player_profile.upgrade_loadout) > UPGRADE_SLOT_COUNT:
            self.player_profile.upgrade_loadout = self.player_profile.upgrade_loadout[
                :UPGRADE_SLOT_COUNT
            ]

    def _calculate_layout(self):
        sw, sh = self.app.screen.get_size()

        # 33% | 34% | 33% split — laterais com mais respiro para acomodar os
        # títulos sem vazar do painel. Centro ainda comporta o preview (até 400px).
        lw = int(sw * 0.33)
        rw = int(sw * 0.33)
        cw = sw - lw - rw

        self.layout = UILayout()
        self.layout.left_area = pygame.Rect(0, 0, lw, sh)
        self.layout.center_area = pygame.Rect(lw, 0, cw, sh)
        self.layout.right_area = pygame.Rect(sw - rw, 0, rw, sh)

        # --- ARSENAL (Esquerda) ---
        # Slots Ativos em grid 4×2 (8 slots), com tamanho de célula idêntico aos
        # demais grids (Estoque/Hangar também usam 4 colunas).
        cols_slots = 4
        size_slots = (lw - self.MARGIN * 2 - (cols_slots - 1) * self.GAP) // cols_slots
        lx_slots = self.MARGIN

        # Alinhamento dos Cabeçalhos: y = 100
        header_y = 100
        self.layout.active_slots_header = pygame.Rect(
            self.MARGIN, header_y, lw - self.MARGIN * 2, 25
        )

        # Conteúdo começa abaixo do cabeçalho
        ly = header_y + 40
        for i in range(UPGRADE_SLOT_COUNT):
            r, c = i // cols_slots, i % cols_slots
            self.layout.active_slots.append(
                pygame.Rect(
                    lx_slots + c * (size_slots + self.GAP),
                    ly + r * (size_slots + self.GAP),
                    size_slots,
                    size_slots,
                )
            )

        # 2. Estoque (Starting after slots)
        stock_header_y = self.layout.active_slots[-1].bottom + 35
        self._stock_start_y = stock_header_y + 35
        self.layout.upgrade_scroll_area = pygame.Rect(
            self.MARGIN,
            self._stock_start_y,
            lw - self.MARGIN * 2,
            sh - self._stock_start_y - 80,
        )
        self._rebuild_upgrade_grid()

        # --- NAVE (Centro) ---
        # Preview menor para liberar espaço abaixo para descrição e habilidades.
        preview_s = min(260, cw - 60)
        preview_y = 110
        self.layout.ship_preview_rect = pygame.Rect(
            lw + cw // 2 - preview_s // 2, preview_y, preview_s, preview_s
        )

        # --- HANGAR (Direita) ---
        # 1. Atributos
        rx = self.layout.right_area.x + self.MARGIN
        ry = header_y  # Alinhado com Arsenal Ativo
        self.layout.stats_area = pygame.Rect(rx, ry, rw - self.MARGIN * 2, 110)

        # 2. Ship Collection
        self._ship_start_y = self.layout.stats_area.bottom + 70
        self.layout.ship_scroll_area = pygame.Rect(
            rx, self._ship_start_y, rw - self.MARGIN * 2, sh - self._ship_start_y - 80
        )
        self._rebuild_ship_grid()

        btn_w = 160
        btn_h = 40
        self.layout.back_button = pygame.Rect(self.MARGIN, sh - 60, btn_w, btn_h)

    def _rebuild_upgrade_grid(self):
        self.layout.upgrade_grid_cells.clear()
        self.layout.visible_upgrades.clear()
        cols = 4
        area = self.layout.upgrade_scroll_area
        size = (area.width - (cols - 1) * self.GAP) // cols
        visible_rows = area.height // (size + self.GAP)

        total_rows = math.ceil(len(self.all_upgrades) / cols)
        self.max_upgrade_scroll = max(0, total_rows - visible_rows)
        start_idx = self.upgrade_scroll * cols
        visible_items = self.all_upgrades[
            start_idx : start_idx + (visible_rows + 1) * cols
        ]

        for i, upg in enumerate(visible_items):
            r, c = i // cols, i % cols
            rect = pygame.Rect(
                area.x + c * (size + self.GAP),
                area.y + r * (size + self.GAP),
                size,
                size,
            )
            self.layout.upgrade_grid_cells.append(rect)
            self.layout.visible_upgrades.append(upg)

    def _rebuild_ship_grid(self):
        self.layout.ship_grid_cells.clear()
        self.layout.visible_ships.clear()
        ships = list(all_ship_profiles())
        cols = 4
        area = self.layout.ship_scroll_area
        size = (area.width - (cols - 1) * self.GAP) // cols
        visible_rows = area.height // (size + self.GAP)

        total_rows = math.ceil(len(ships) / cols)
        self.max_ship_scroll = max(0, total_rows - visible_rows)
        start_idx = self.ship_scroll * cols
        visible_ships = ships[start_idx : start_idx + (visible_rows + 1) * cols]

        for i, ship in enumerate(visible_ships):
            r, c = i // cols, i % cols
            rect = pygame.Rect(
                area.x + c * (size + self.GAP),
                area.y + r * (size + self.GAP),
                size,
                size,
            )
            self.layout.ship_grid_cells.append(rect)
            self.layout.visible_ships.append(ship)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._return_to_menu()

        # Controle: A aciona equipar/retirar automaticamente no item sob o
        # cursor virtual (movido pelo stick direito em app.py). Sem
        # drag-and-drop — clicar o upgrade no Estoque manda para o primeiro
        # slot livre; clicar o slot equipado devolve o item ao Estoque.
        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                self._handle_gamepad_confirm()
                return
            if event.button == XboxButton.B:
                self._return_to_menu()
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout.back_button.collidepoint(pos):
                self._return_to_menu()

            for i, rect in enumerate(self.layout.ship_grid_cells):
                if rect.collidepoint(pos):
                    self._handle_ship_click(self.layout.visible_ships[i], rect)
                    return
            for i, rect in enumerate(self.layout.upgrade_grid_cells):
                if rect.collidepoint(pos):
                    upg = self.layout.visible_upgrades[i]
                    if upg.type in self.player_profile.unlocked_upgrades:
                        (
                            self.dragging_upgrade,
                            self.drag_offset,
                            self.drag_source_slot,
                        ) = (upg, (pos[0] - rect.x, pos[1] - rect.y), None)
                    return
            for i, rect in enumerate(self.layout.active_slots):
                if rect.collidepoint(pos):
                    self._handle_slot_click(i, rect, pos)
                    return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging_upgrade:
                self._handle_drop_upgrade(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            # Divisão simples pelo meio horizontal: mouse à esquerda do centro
            # rola o Estoque; à direita, rola o Hangar. A coluna central só
            # mostra preview/descrição (nada scrollável), então a fronteira
            # exata não importa — eliminando qualquer zona morta.
            mid_x = self.app.screen.get_width() // 2
            if event.pos[0] < mid_x:
                if event.button == 4:
                    self.upgrade_scroll = max(0, self.upgrade_scroll - 1)
                else:
                    self.upgrade_scroll = min(
                        self.max_upgrade_scroll, self.upgrade_scroll + 1
                    )
                self._rebuild_upgrade_grid()
            else:
                if event.button == 4:
                    self.ship_scroll = max(0, self.ship_scroll - 1)
                else:
                    self.ship_scroll = min(self.max_ship_scroll, self.ship_scroll + 1)
                self._rebuild_ship_grid()

    def _handle_gamepad_confirm(self) -> None:
        """Aciona ``A`` do controle sobre o item embaixo do cursor virtual.

        Substitui o drag-and-drop por auto-equip/auto-retirar:
        - Botão Voltar: retorna ao menu.
        - Card de nave: equivalente ao click do mouse (selecionar/comprar).
        - Slot ativo equipado: retira o upgrade (volta ao Estoque).
        - Slot ativo bloqueado: tenta desbloquear pelo custo em estrelas.
        - Card do Estoque: equipa no primeiro slot livre que aceite o peso;
          se já estiver equipado, retira (toggle).
        """
        pos = pygame.mouse.get_pos()

        if self.layout.back_button.collidepoint(pos):
            self._return_to_menu()
            return

        for i, rect in enumerate(self.layout.ship_grid_cells):
            if rect.collidepoint(pos):
                self._handle_ship_click(self.layout.visible_ships[i], rect)
                return

        for i, rect in enumerate(self.layout.active_slots):
            if rect.collidepoint(pos):
                self._gamepad_slot_action(i, rect)
                return

        for i, rect in enumerate(self.layout.upgrade_grid_cells):
            if rect.collidepoint(pos):
                self._gamepad_stock_action(self.layout.visible_upgrades[i], rect)
                return

    def _gamepad_slot_action(self, idx: int, _rect: pygame.Rect) -> None:
        """Slot ativo: retira o upgrade equipado ou tenta destravar slot."""
        profile = self.player_profile
        if idx >= profile.unlocked_slots:
            if profile.can_unlock_slot(idx):
                profile.unlock_slot(idx)
            else:
                self.shaking_slot, self.shake_start_time = idx, time.time()
            return
        if profile.upgrade_loadout[idx] is not None:
            profile.equip_upgrade(None, idx)

    def _gamepad_stock_action(self, upg: UpgradeMeta, _rect: pygame.Rect) -> None:
        """Estoque: equipa no primeiro slot livre; toggle se já equipado.

        Sem slot livre OU peso excedido: tremor + mensagem para indicar que o
        upgrade não cabe agora, espelhando o feedback do fluxo de drag.
        """
        profile = self.player_profile

        if upg.type not in profile.unlocked_upgrades:
            self.floating_messages.append(
                FloatingMessage(_rect.centerx, _rect.top, "Bloqueado", colors.RED)
            )
            return

        # Toggle: clicar item já equipado retira-o.
        current_slot = profile.get_equipped_slot(upg.type)
        if current_slot is not None:
            profile.equip_upgrade(None, current_slot)
            return

        # Procura primeiro slot livre que aceite o peso atual.
        for i in range(profile.unlocked_slots):
            if profile.upgrade_loadout[i] is None and profile.can_equip_upgrade(
                upg.type, i
            ):
                profile.equip_upgrade(upg.type, i)
                return

        # Não coube — shake no slot 0 + mensagem.
        self.shaking_slot, self.shake_start_time = 0, time.time()
        self.floating_messages.append(
            FloatingMessage(_rect.centerx, _rect.top, "Sem espaço", colors.RED)
        )

    def _handle_ship_click(self, ship: ShipProfile, rect: pygame.Rect):
        profile = self.player_profile
        if profile.is_ship_unlocked(ship.id):
            profile.select_ship(ship.id)
        elif profile.can_unlock_ship(ship.id):
            if profile.unlock_ship(ship.id):
                profile.select_ship(ship.id)
                self.floating_messages.append(
                    FloatingMessage(
                        rect.centerx,
                        rect.top,
                        f"{ship.display_name} Adquirida!",
                        colors.GREEN,
                    )
                )
        else:
            self.shaking_ship_id, self.shake_start_time = ship.id, time.time()
            self.floating_messages.append(
                FloatingMessage(
                    rect.centerx, rect.top, "Saldo Insuficiente", colors.RED
                )
            )

    def _handle_slot_click(self, idx: int, rect: pygame.Rect, pos: tuple[int, int]):
        profile = self.player_profile
        if idx >= profile.unlocked_slots:
            if profile.can_unlock_slot(idx):
                profile.unlock_slot(idx)
            else:
                self.shaking_slot, self.shake_start_time = idx, time.time()
            return
        equipped_type = profile.upgrade_loadout[idx]
        if equipped_type:
            upg = next((u for u in self.all_upgrades if u.type == equipped_type), None)
            if upg:
                self.dragging_upgrade, self.drag_offset, self.drag_source_slot = (
                    upg,
                    (pos[0] - rect.x, pos[1] - rect.y),
                    idx,
                )

    def _handle_drop_upgrade(self, pos: tuple[int, int]):
        if self.dragging_upgrade is None:
            return
        profile, dropped = self.player_profile, False
        for i, rect in enumerate(self.layout.active_slots):
            if rect.collidepoint(pos) and i < profile.unlocked_slots:
                if self.drag_source_slot is not None:
                    orig = profile.upgrade_loadout[self.drag_source_slot]
                    profile.upgrade_loadout[self.drag_source_slot] = None
                    if profile.can_equip_upgrade(self.dragging_upgrade.type, i):
                        target = profile.upgrade_loadout[i]
                        profile.equip_upgrade(self.dragging_upgrade.type, i)
                        profile.equip_upgrade(target, self.drag_source_slot)
                        dropped = True
                    else:
                        profile.upgrade_loadout[self.drag_source_slot] = orig
                        self.shaking_slot, self.shake_start_time = i, time.time()
                elif profile.can_equip_upgrade(self.dragging_upgrade.type, i):
                    for j in range(UPGRADE_SLOT_COUNT):
                        if profile.upgrade_loadout[j] == self.dragging_upgrade.type:
                            profile.equip_upgrade(None, j)
                    profile.equip_upgrade(self.dragging_upgrade.type, i)
                    dropped = True
                else:
                    self.shaking_slot, self.shake_start_time = i, time.time()
                break
        if not dropped and self.drag_source_slot is not None:
            profile.equip_upgrade(None, self.drag_source_slot)
        self.dragging_upgrade = None

    def exit(self):
        """Garante que loadout/desbloqueios/seleção de nave sejam persistidos
        ao deixar a cena — sem isso o `auto_save` (gated por 10s) pode descartar
        mudanças recentes ao trocar de cena rapidamente.
        """
        self.player_profile.save()

    def update(self, dt: float):
        self.r.starfield.update(dt)
        if self.is_entering:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / self.entry_duration
            )
            if self.entry_progress >= 1.0:
                self.is_entering = False
        if self.transitioning:
            self.transition_progress += dt / self.transition_duration
            if self.transition_progress >= 1.0:
                from .main_menu import MainMenuScene

                # Persistência defensiva: garante save antes do switch — algumas
                # implementações de Scene não chamam exit() na transição.
                self.player_profile.save()
                self.app.states.switch(MainMenuScene(self.app))
                return
        for m in self.floating_messages[:]:
            m.update(dt)
            if m.is_dead():
                self.floating_messages.remove(m)
        if (
            self.shaking_ship_id
            and time.time() - self.shake_start_time > self.shake_duration
        ):
            self.shaking_ship_id = None
        if (
            self.shaking_slot is not None
            and time.time() - self.shake_start_time > self.shake_duration
        ):
            self.shaking_slot = None

        m_pos = pygame.mouse.get_pos()
        self.hovered_upgrade = self.hovered_ship = self.hovered_slot_idx = None
        if not self.dragging_upgrade:
            for i, r in enumerate(self.layout.upgrade_grid_cells):
                if r.collidepoint(m_pos):
                    self.hovered_upgrade = self.layout.visible_upgrades[i]
                    break
            for i, r in enumerate(self.layout.ship_grid_cells):
                if r.collidepoint(m_pos):
                    self.hovered_ship = self.layout.visible_ships[i]
                    break
            for i, r in enumerate(self.layout.active_slots):
                if r.collidepoint(m_pos) and i < self.player_profile.unlocked_slots:
                    self.hovered_slot_idx = i
                    break
        else:
            self.drag_invalid_target = True
            for i, r in enumerate(self.layout.active_slots):
                if r.collidepoint(m_pos) and i < self.player_profile.unlocked_slots:
                    if self.drag_source_slot is not None:
                        orig = self.player_profile.upgrade_loadout[
                            self.drag_source_slot
                        ]
                        self.player_profile.upgrade_loadout[self.drag_source_slot] = (
                            None
                        )
                        self.drag_invalid_target = (
                            not self.player_profile.can_equip_upgrade(
                                self.dragging_upgrade.type, i
                            )
                        )
                        self.player_profile.upgrade_loadout[self.drag_source_slot] = (
                            orig
                        )
                    else:
                        self.drag_invalid_target = (
                            not self.player_profile.can_equip_upgrade(
                                self.dragging_upgrade.type, i
                            )
                        )
                    break

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)
        alpha_mult = (
            (
                1.0 - self.transition_progress
                if self.fade_out
                else self.transition_progress
            )
            if self.transitioning
            else self.entry_progress
            if self.is_entering
            else 1.0
        )
        alpha = int(255 * alpha_mult)
        title = self.title_font.render("Central de Loadout", True, CUSTOM_GOLD)
        surface.blit(
            title,
            title.get_rect(
                centerx=surface.get_width() // 2, top=24 + int(20 * (1.0 - alpha_mult))
            ),
        )

        content_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._draw_lateral_panels(content_surf)
        self._draw_center_column(content_surf)
        self._draw_left_column(content_surf)
        self._draw_right_column(content_surf)
        self._draw_back_button(content_surf)
        self._draw_floating_messages(content_surf)
        if self.dragging_upgrade:
            self._draw_dragging_upgrade(content_surf)
        elif self.hovered_upgrade:
            self._draw_tooltip(content_surf)
        content_surf.set_alpha(alpha)
        surface.blit(content_surf, (0, 0))

    def _draw_lateral_panels(self, surface: pygame.Surface):
        # Padding consistente: 10px horizontal, top em 80 (logo abaixo do título da tela)
        # e bottom em sh-70 (logo acima do botão Voltar). Engloba header + conteúdo.
        sh = surface.get_height()
        panel_top = 80
        panel_h = sh - panel_top - 70
        side_pad = 10
        border_color = (255, 255, 255, 30)

        panel_l = pygame.Rect(
            self.layout.left_area.x + side_pad,
            panel_top,
            self.layout.left_area.width - side_pad * 2,
            panel_h,
        )
        pygame.draw.rect(
            surface, (20, 20, 25, 180), panel_l, border_radius=self.RADIUS * 2
        )
        pygame.draw.rect(
            surface, border_color, panel_l, 1, border_radius=self.RADIUS * 2
        )

        panel_r = pygame.Rect(
            self.layout.right_area.x + side_pad,
            panel_top,
            self.layout.right_area.width - side_pad * 2,
            panel_h,
        )
        pygame.draw.rect(
            surface, (20, 20, 25, 180), panel_r, border_radius=self.RADIUS * 2
        )
        pygame.draw.rect(
            surface, border_color, panel_r, 1, border_radius=self.RADIUS * 2
        )

    def _draw_center_column(self, surface: pygame.Surface):
        ship = self.hovered_ship or get_ship_profile(self.player_profile.selected_ship)
        rect = self.layout.ship_preview_rect

        # Clip à coluna central garante que nenhum texto/imagem vaze para as
        # colunas vizinhas, mesmo se uma palavra exceder o wrap.
        previous_clip = surface.get_clip()
        surface.set_clip(self.layout.center_area)
        try:
            self._draw_center_column_body(surface, ship, rect)
        finally:
            surface.set_clip(previous_clip)

    def _draw_center_column_body(
        self, surface: pygame.Surface, ship: ShipProfile, rect: pygame.Rect
    ):
        # Ícone da nave pulsando no preview.
        pulse = 1.0 + 0.04 * math.sin(time.time() * 3)
        try:
            img = pygame.transform.scale(
                get_image(BASE_DIR / "assets" / "icons" / ship.sprite_filename),
                (int(rect.width * pulse), int(rect.height * pulse)),
            )
            surface.blit(img, img.get_rect(center=rect.center))
        except (OSError, pygame.error, ValueError):
            pass

        # Nome da nave logo abaixo do preview.
        cx = rect.centerx
        y = rect.bottom + 8
        name_surf = self.title_font.render(ship.display_name.upper(), True, CUSTOM_GOLD)
        surface.blit(
            name_surf, name_surf.get_rect(center=(cx, y + name_surf.get_height() // 2))
        )
        y += name_surf.get_height() + 6

        # Largura máxima para todo o texto: respeita a coluna central com folga.
        # Mantém uma margem interna de 20px de cada lado.
        center_x = self.layout.center_area.x
        center_w = self.layout.center_area.width
        max_w = max(120, center_w - 40)
        text_left = center_x + 20
        text_right = center_x + center_w - 20

        # Helper local: renderiza texto centralizado com wrap respeitando max_w.
        def _draw_wrapped(
            text: str,
            font: pygame.font.Font,
            color: tuple[int, int, int],
            y_pos: int,
            max_lines: int = 3,
        ) -> int:
            for line in wrap_text(font, text, max_w)[:max_lines]:
                line_surf = font.render(line, True, color)
                # Clip garante que nada vaze mesmo se a palavra individual exceder.
                surface.blit(
                    line_surf,
                    line_surf.get_rect(
                        center=(cx, y_pos + line_surf.get_height() // 2)
                    ),
                )
                y_pos += line_surf.get_height() + 2
            return y_pos

        # Tags (categoria) em uma linha discreta.
        if ship.tags:
            y = _draw_wrapped(
                " · ".join(ship.tags), self.small_font, (160, 160, 200), y, max_lines=1
            )
            y += 6

        # Descrição: cap alto o suficiente para caber as descrições mais longas
        # (Reverberador, Caçador) sem truncar. Clip da coluna garante que nada
        # vaze lateralmente; o eixo vertical empurra o conteúdo seguinte. As
        # frases que mencionam ações (charge shot, Cofre, dash) trocam de
        # legenda conforme o input ativo via `format_ship_description`.
        desc_text = format_ship_description(ship, self.app.gamepad.is_active)
        y = _draw_wrapped(
            desc_text, self.small_font, colors.WHITE, y, max_lines=4
        )
        y += 6

        # Linha divisória sutil.
        pygame.draw.line(surface, (90, 90, 110), (text_left, y), (text_right, y), 1)
        y += 8

        # Atributos numéricos: só os que diferem do padrão.
        stat_rows: list[tuple[str, str]] = []
        if abs(ship.damage_mult - 1.0) > 1e-6:
            stat_rows.append(("Dano", self._fmt_mult(ship.damage_mult)))
        if abs(ship.fire_rate_mult - 1.0) > 1e-6:
            stat_rows.append(("Cadência", self._fmt_mult(ship.fire_rate_mult)))
        if abs(ship.speed_mult - 1.0) > 1e-6:
            stat_rows.append(("Velocidade", self._fmt_mult(ship.speed_mult)))
        if ship.extra_lives != 0:
            stat_rows.append(("Vidas", f"{ship.extra_lives:+d}"))

        for label, value in stat_rows:
            y = _draw_wrapped(
                f"{label}: {value}", self.small_font, (210, 210, 210), y, max_lines=1
            )

        if stat_rows:
            y += 8

        # Habilidades especiais com as teclas necessárias.
        ability_rows = self._ship_ability_descriptions(ship)
        if ability_rows:
            header = self.small_font.render("HABILIDADES", True, CUSTOM_GOLD)
            surface.blit(
                header, header.get_rect(center=(cx, y + header.get_height() // 2))
            )
            y += header.get_height() + 4
            for line in ability_rows:
                # Cada habilidade pode quebrar em até 2 linhas se for longa.
                y = _draw_wrapped(
                    line, self.small_font, (200, 220, 255), y, max_lines=2
                )
                y += 1

    @staticmethod
    def _fmt_mult(value: float) -> str:
        """1.6 → '+60%', 0.65 → '-35%', 1.0 → '—'."""
        if abs(value - 1.0) < 1e-6:
            return "—"
        pct = (value - 1.0) * 100.0
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.0f}%"

    def _input_label(self, keyboard: str, gamepad: str) -> str:
        """Retorna a legenda apropriada ao modo de input ativo.

        Usa `app.gamepad.is_active` (preferência ligada + controle conectado)
        como discriminador. Quando o player desliga o gamepad em Settings ou
        desconecta o controle, as legendas voltam pro teclado automaticamente.
        """
        return gamepad if self.app.gamepad.is_active else keyboard

    def _ship_ability_descriptions(self, ship: ShipProfile) -> list[str]:
        """Retorna instruções curtas das mecânicas especiais da nave.

        Mantém cada linha sob ~40 chars para caber em coluna estreita sem
        depender de quebra automática. As teclas/botões alternam conforme o
        modo de input ativo (teclado x controle) — ver `_input_label`.
        """
        lines: list[str] = []
        if ship.has_dash:
            dash_key = self._input_label("SHIFT", "LT")
            lines.append(f"{dash_key}: dash i-frames ({ship.dash_cooldown:.0f}s cd)")
        if ship.has_charge_shot:
            charge_key = self._input_label("ALT+Espaço", "LT")
            lines.append(
                f"{charge_key}: até {ship.charge_shot_damage_mult:.0f}× dano "
                f"({ship.charge_shot_max_time:.1f}s)"
            )
        if ship.powerup_slots > 0:
            powerup_keys = self._input_label("Q/E", "Y/A")
            lines.append(f"{powerup_keys}: usa {ship.powerup_slots} slots de powerup")
        if ship.permanent_mini_ships > 0:
            n = ship.permanent_mini_ships
            lines.append(
                f"{n} mini-nave{'s' if n > 1 else ''} permanente{'s' if n > 1 else ''}"
            )
        if ship.pickup_radius_mult > 1.5:
            lines.append("Raio amplo de coleta")
        if ship.combo_damage_per_kill > 0:
            per_kill = int(ship.combo_damage_per_kill * 100)
            cap = int(ship.combo_damage_cap * 100) if ship.combo_damage_cap > 0 else 0
            cap_txt = f", máx +{cap}%" if cap else ""
            lines.append(f"Combo: +{per_kill}%/abate{cap_txt}")
        return lines

    def _draw_left_column(self, surface: pygame.Surface):
        h = self.layout.active_slots_header
        total_weight = self.player_profile.get_total_equipped_weight()
        cap = self.player_profile.unlocked_slots
        txt = self.header_font.render(
            f"Arsenal ({total_weight}/{cap})", True, colors.WHITE
        )
        surface.blit(txt, h)

        # Barra de capacidade de peso logo abaixo do título.
        bar_x = h.x
        bar_y = h.bottom + 4
        bar_w = h.width
        bar_h = 6
        pygame.draw.rect(
            surface, (40, 40, 50), (bar_x, bar_y, bar_w, bar_h), border_radius=3
        )
        if cap > 0:
            fill_w = int(bar_w * min(1.0, total_weight / cap))
            # Verde quando há folga; amarelo perto do limite; vermelho cheio.
            ratio = total_weight / cap
            if ratio >= 1.0:
                fill_color = (220, 80, 80)
            elif ratio >= 0.8:
                fill_color = (220, 200, 80)
            else:
                fill_color = (100, 200, 120)
            if fill_w > 0:
                pygame.draw.rect(
                    surface, fill_color, (bar_x, bar_y, fill_w, bar_h), border_radius=3
                )

        for i, r in enumerate(self.layout.active_slots):
            eq = (
                self.player_profile.upgrade_loadout[i]
                if i < len(self.player_profile.upgrade_loadout)
                else None
            )
            lock, dr = i >= self.player_profile.unlocked_slots, r.copy()
            if self.shaking_slot == i:
                dr.x += int(8 * math.sin((time.time() - self.shake_start_time) * 40))

            is_valid_target = False
            if self.dragging_upgrade and not lock:
                if dr.collidepoint(pygame.mouse.get_pos()):
                    is_valid_target = not self.drag_invalid_target
            bg = (
                (45, 60, 45)
                if (is_valid_target and not self.drag_invalid_target)
                else (
                    (40, 50, 40)
                    if (eq and self.hovered_slot_idx != i)
                    else (30, 30, 30)
                )
            )
            pygame.draw.rect(surface, bg, dr, border_radius=self.RADIUS)
            color = (
                colors.YELLOW
                if (self.hovered_slot_idx == i or is_valid_target)
                else (80, 80, 80)
                if lock
                else colors.GRAY
            )
            pygame.draw.rect(
                surface, color, dr, 2 if eq else 1, border_radius=self.RADIUS
            )
            if lock:
                self._draw_lock_indicator(
                    surface, dr, self.player_profile.get_slot_cost(i)
                )
            elif eq:
                meta = next((u for u in self.all_upgrades if u.type == eq), None)
                if meta:
                    icon_radius = int(dr.width * 0.35)
                    pygame.draw.circle(
                        surface,
                        CUSTOM_PURPLE,
                        (dr.centerx, dr.centery - 4),
                        icon_radius,
                    )
                    surf = self.header_font.render(
                        get_upgrade_icon(meta.name, meta.icon_id), True, CUSTOM_GOLD
                    )
                    surface.blit(
                        surf, surf.get_rect(center=(dr.centerx, dr.centery - 4))
                    )
                    # Badge de peso no canto inferior esquerdo (consistente com Estoque).
                    self._draw_weight_badge(surface, dr, meta.slot_weight, dim=False)
                    self._draw_equipped_badge(surface, dr)

        surface.blit(
            self.header_font.render("Estoque", True, colors.WHITE),
            (self.MARGIN, self._stock_start_y - 35),
        )
        area = self.layout.upgrade_scroll_area
        surface.set_clip(area)
        # Pré-calcula peso atual equipado para decidir se cada upgrade ainda cabe.
        current_weight = self.player_profile.get_total_equipped_weight()
        slot_cap = self.player_profile.unlocked_slots
        for i, rect in enumerate(self.layout.upgrade_grid_cells):
            if rect.bottom < area.y or rect.top > area.bottom:
                continue
            upg = self.layout.visible_upgrades[i]
            unl = upg.type in self.player_profile.unlocked_upgrades
            eq = self.player_profile.get_equipped_slot(upg.type) is not None
            # `no_fit`: upgrade desbloqueado mas que excederia o peso disponível
            # se equipado agora. Não se aplica se já está equipado.
            no_fit = unl and not eq and (current_weight + upg.slot_weight > slot_cap)

            bg = (
                (60, 60, 60)
                if self.hovered_upgrade == upg
                else (40, 40, 40)
                if unl
                else (25, 25, 25)
            )
            pygame.draw.rect(surface, bg, rect, border_radius=self.RADIUS)
            border = (
                colors.YELLOW
                if eq
                else colors.RED
                if not unl
                else (130, 90, 50)
                if no_fit
                else colors.GRAY
            )
            pygame.draw.rect(surface, border, rect, 2, border_radius=self.RADIUS)

            icon_radius = int(rect.width * 0.35)
            icon_color = (80, 80, 80) if (not unl or no_fit) else CUSTOM_PURPLE
            pygame.draw.circle(surface, icon_color, rect.center, icon_radius)
            icon_text_color = CUSTOM_GOLD if unl and not no_fit else (50, 50, 50)
            icon_text = self.header_font.render(
                get_upgrade_icon(upg.name, upg.icon_id), True, icon_text_color
            )
            surface.blit(icon_text, icon_text.get_rect(center=rect.center))

            # Badge de peso no canto inferior esquerdo (sempre visível).
            self._draw_weight_badge(surface, rect, upg.slot_weight, no_fit)

            if no_fit:
                # Overlay escuro semi-transparente + ícone de cadeado de peso.
                overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 130))
                surface.blit(overlay, rect.topleft)
                self._draw_weight_lock(surface, rect)

            if eq:
                self._draw_equipped_badge(surface, rect)
        surface.set_clip(None)
        self._draw_scrollbar(
            surface, area, self.upgrade_scroll, self.max_upgrade_scroll
        )

    def _draw_right_column(self, surface: pygame.Surface):
        ship = self.hovered_ship or get_ship_profile(self.player_profile.selected_ship)
        curr = get_ship_profile(self.player_profile.selected_ship)
        surface.blit(
            self.header_font.render("Atributos", True, colors.WHITE),
            self.layout.stats_area.topleft,
        )
        sy = self.layout.stats_area.y + 35
        self._draw_stat_bar(
            surface,
            self.layout.stats_area.x,
            sy,
            self.layout.stats_area.width,
            "POTÊNCIA",
            ship.damage_mult,
            curr.damage_mult,
        )
        self._draw_stat_bar(
            surface,
            self.layout.stats_area.x,
            sy + 30,
            self.layout.stats_area.width,
            "CADÊNCIA",
            ship.fire_rate_mult,
            curr.fire_rate_mult,
        )
        self._draw_stat_bar(
            surface,
            self.layout.stats_area.x,
            sy + 60,
            self.layout.stats_area.width,
            "AGILIDADE",
            ship.speed_mult,
            curr.speed_mult,
        )

        surface.blit(
            self.header_font.render("Hangar", True, colors.WHITE),
            (
                self.layout.right_area.x + self.MARGIN,
                self.layout.stats_area.bottom + 30,
            ),
        )
        area = self.layout.ship_scroll_area
        surface.set_clip(area)
        for i, rect in enumerate(self.layout.ship_grid_cells):
            if rect.bottom < area.y or rect.top > area.bottom:
                continue
            s = self.layout.visible_ships[i]
            unl, sel = (
                self.player_profile.is_ship_unlocked(s.id),
                self.player_profile.selected_ship == s.id,
            )
            dr = rect.move(
                (
                    int(6 * math.sin((time.time() - self.shake_start_time) * 40))
                    if self.shaking_ship_id == s.id
                    else 0
                ),
                0,
            )
            bg = (
                (40, 60, 40)
                if sel
                else (60, 60, 70)
                if self.hovered_ship == s
                else (30, 30, 35)
            )
            pygame.draw.rect(surface, bg, dr, border_radius=self.RADIUS)
            pygame.draw.rect(
                surface,
                (
                    colors.YELLOW
                    if sel
                    else (
                        CUSTOM_PURPLE
                        if (unl and self.hovered_ship == s)
                        else colors.GRAY
                    )
                ),
                dr,
                2,
                border_radius=self.RADIUS,
            )
            if not unl:
                self._draw_lock_indicator(surface, dr, s.unlock_cost)
            else:
                try:
                    img_s = int(dr.width * 0.6)
                    img = pygame.transform.scale(
                        get_image(BASE_DIR / "assets" / "icons" / s.sprite_filename),
                        (img_s, img_s),
                    )
                    surface.blit(img, img.get_rect(center=dr.center))
                except (OSError, pygame.error, ValueError):
                    pass
                if sel:
                    self._draw_equipped_badge(surface, dr)
        surface.set_clip(None)
        self._draw_scrollbar(surface, area, self.ship_scroll, self.max_ship_scroll)
        bal_y = self.app.screen.get_height() - 55
        surface.blit(
            self.star_icon_small, (self.layout.right_area.x + self.MARGIN, bal_y)
        )
        surface.blit(
            self.item_font.render(
                f"{self.player_profile.available_stars} Estrelas", True, CUSTOM_GOLD
            ),
            (self.layout.right_area.x + self.MARGIN + 25, bal_y + 1),
        )

    def _draw_scrollbar(
        self, surface: pygame.Surface, area: pygame.Rect, current: int, max_s: int
    ):
        if max_s <= 0:
            return
        sb_w, sb_x = 4, area.right + 6
        pygame.draw.rect(
            surface, (40, 40, 40), (sb_x, area.y, sb_w, area.height), border_radius=2
        )
        hh = max(20, area.height // (max_s + 1))
        pygame.draw.rect(
            surface,
            CUSTOM_PURPLE,
            (sb_x, area.y + (current / max_s) * (area.height - hh), sb_w, hh),
            border_radius=2,
        )

    def _draw_lock_indicator(
        self, surface: pygame.Surface, rect: pygame.Rect, cost: int
    ):
        can = self.player_profile.available_stars >= cost
        surface.blit(self.star_icon_small, (rect.centerx - 18, rect.y + 4))
        surface.blit(
            self.tiny_font.render(str(cost), True, colors.GREEN if can else colors.RED),
            (rect.centerx + 4, rect.y + 6),
        )
        icon_s = int(rect.width * 0.4)
        surface.blit(
            pygame.transform.scale(self.locked_icon, (icon_s, icon_s)),
            (rect.centerx - icon_s // 2, rect.centery - 2),
        )

    def _draw_equipped_badge(self, surface: pygame.Surface, rect: pygame.Rect):
        pygame.draw.circle(surface, colors.YELLOW, (rect.right - 8, rect.y + 8), 7)
        surface.blit(
            self.tiny_font.render("E", True, BLACK), (rect.right - 12, rect.y + 2)
        )

    def _draw_weight_badge(
        self, surface: pygame.Surface, rect: pygame.Rect, weight: int, dim: bool
    ):
        """Badge circular com o peso do upgrade no canto inferior esquerdo."""
        cx, cy = rect.x + 10, rect.bottom - 10
        bg = (90, 60, 30) if dim else (50, 50, 70)
        fg = (200, 150, 100) if dim else colors.WHITE
        pygame.draw.circle(surface, bg, (cx, cy), 8)
        pygame.draw.circle(surface, fg, (cx, cy), 8, 1)
        txt = self.tiny_font.render(str(weight), True, fg)
        surface.blit(txt, txt.get_rect(center=(cx, cy)))

    def _draw_weight_lock(self, surface: pygame.Surface, rect: pygame.Rect):
        """Ícone de cadeado "sem peso disponível" centralizado sobre o card.

        Reusa `self.locked_icon` com tint avermelhado para distinguir do
        bloqueio por estrelas (que mantém o tom original).
        """
        size = int(min(rect.width, rect.height) * 0.45)
        icon = pygame.transform.scale(self.locked_icon, (size, size))
        tinted = icon.copy()
        tinted.fill((255, 150, 150), special_flags=pygame.BLEND_MULT)
        surface.blit(tinted, tinted.get_rect(center=rect.center))

    def _draw_stat_bar(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        w: int,
        label: str,
        val: float,
        curr: float,
    ):
        surface.blit(self.tiny_font.render(label, True, (180, 180, 180)), (x, y))
        by, bh = y + 14, 6
        pygame.draw.rect(
            surface, (40, 40, 40), (x, by, w, bh), border_radius=self.RADIUS
        )

        def norm(v: float) -> float:
            return max(0.1, min(1.0, float((v - 0.5) / 1.5)))

        fw, cw = int(w * norm(val)), int(w * norm(curr))
        if fw > cw:
            pygame.draw.rect(surface, (40, 180, 40), (x + cw, by, fw - cw, bh))
            pygame.draw.rect(surface, (100, 100, 100), (x, by, cw, bh))
        elif fw < cw:
            pygame.draw.rect(surface, (180, 40, 40), (x + fw, by, cw - fw, bh))
            pygame.draw.rect(surface, (100, 100, 100), (x, by, fw, bh))
        else:
            pygame.draw.rect(surface, (100, 100, 100), (x, by, fw, bh))

    def _draw_back_button(self, surface: pygame.Surface):
        draw_bordered_button(
            surface,
            self.layout.back_button,
            "Voltar",
            self.item_font,
            CUSTOM_PURPLE,
            255,
            0,
        )

    def _draw_dragging_upgrade(self, surface: pygame.Surface):
        if self.dragging_upgrade is None:
            return
        pos = pygame.mouse.get_pos()
        rect = pygame.Rect(
            pos[0] - self.drag_offset[0], pos[1] - self.drag_offset[1], 55, 55
        )
        bg = (80, 40, 40, 200) if self.drag_invalid_target else (60, 60, 60, 200)
        pygame.draw.rect(surface, bg, rect, border_radius=self.RADIUS)
        pygame.draw.circle(
            surface,
            (150, 50, 50) if self.drag_invalid_target else CUSTOM_PURPLE,
            rect.center,
            18,
        )
        initial = get_upgrade_icon(
            self.dragging_upgrade.name, self.dragging_upgrade.icon_id
        )
        surf = self.header_font.render(initial, True, CUSTOM_GOLD)
        surface.blit(surf, surf.get_rect(center=rect.center))

    def _draw_tooltip(self, surface: pygame.Surface):
        if self.hovered_upgrade is None:
            return
        pos, upg = pygame.mouse.get_pos(), self.hovered_upgrade

        # Largura fixa, altura dinâmica
        w = 280
        padding = 12
        line_height = 20

        # Quebrar o texto em linhas antes de calcular a altura
        wrapped_lines = wrap_text(self.small_font, upg.desc, w - (padding * 2))

        # Calcular altura necessária: Top + Nome + Gap + Linhas + Bottom
        # 10 (top) + 24 (nome) + 10 (gap) + (linhas * height) + 10 (bottom)
        h = 10 + 24 + 10 + (len(wrapped_lines) * line_height) + 10

        x, y = pos[0] + 20, pos[1] + 20

        # Ajustar posição para não sair da tela
        if y + h > surface.get_height():
            y = pos[1] - h - 10
        if x + w > surface.get_width():
            x = pos[0] - w - 10

        # Garantir que não saia pelo topo ou esquerda
        x = max(10, x)
        y = max(10, y)

        # Criar superfície do tooltip
        tooltip_surf = pygame.Surface((w, h), pygame.SRCALPHA)

        # Fundo e borda
        pygame.draw.rect(
            tooltip_surf, (15, 15, 25, 245), tooltip_surf.get_rect(), border_radius=10
        )
        pygame.draw.rect(
            tooltip_surf,
            (200, 200, 220, 200),
            tooltip_surf.get_rect(),
            1,
            border_radius=10,
        )

        # Nome do upgrade
        name_surf = self.item_font.render(upg.name, True, colors.YELLOW)
        tooltip_surf.blit(name_surf, (padding, 10))

        # Linha separadora sutil
        pygame.draw.line(
            tooltip_surf, (60, 60, 80), (padding, 38), (w - padding, 38), 1
        )

        # Descrição (todas as linhas)
        dy = 48
        for line in wrapped_lines:
            line_surf = self.small_font.render(line, True, colors.WHITE)
            tooltip_surf.blit(line_surf, (padding, dy))
            dy += line_height

        surface.blit(tooltip_surf, (x, y))


    def _return_to_menu(self):
        self.fade_out, self.transitioning, self.transition_progress = True, True, 0.0

    def _draw_floating_messages(self, surface: pygame.Surface):
        for m in self.floating_messages:
            m.draw(surface)
