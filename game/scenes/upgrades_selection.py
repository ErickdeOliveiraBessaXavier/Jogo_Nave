import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, TypeVar

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_font, get_image
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.i18n import t
from ..core.ship_types import (
    ShipProfile,
    all_ship_profiles,
    format_ship_description,
    get_ship_profile,
    ship_display_name,
    ship_tags,
)
from ..core.sound import sound_manager
from ..core.state import Scene
from ..core.upgrades import (
    UpgradeMeta,
    get_upgrade_icon,
    list_all_upgrades_meta,
    upgrade_desc,
)
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from .ui_helpers import wrap_text, draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp

# Elemento genérico de uma página de grid (UpgradeMeta, ShipProfile, ...).
_GridItem = TypeVar("_GridItem")


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
    upgrade_area: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )
    upgrade_left_chevron: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )
    upgrade_right_chevron: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )

    # Direita: Hangar
    stats_area: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    ship_grid_cells: List[pygame.Rect] = field(default_factory=lambda: [])
    visible_ships: List[ShipProfile] = field(default_factory=lambda: [])
    ship_area: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )
    ship_left_chevron: pygame.Rect = field(
        default_factory=lambda: pygame.Rect(0, 0, 0, 0)
    )
    ship_right_chevron: pygame.Rect = field(
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

    # A cena possui a navegação por controle: DPad/analógico movem um FOCO
    # discreto próprio (não o cursor virtual do app). Faz o app pular o cursor
    # virtual e a síntese de setas/teclas — ver app._update_virtual_cursor /
    # app._synthesize_menu_events. Elimina o soft lock do snap-focus por cursor.
    owns_gamepad_navigation = True

    # Cadência da repetição ao segurar uma direção no analógico (feel de menu).
    NAV_STICK_THRESHOLD = 0.5
    NAV_INITIAL_DELAY = 0.32
    NAV_REPEAT_RATE = 0.12

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = app.renderer
        self.title_font = get_font(max(8, int(36 * self.ui_scale)))
        self.header_font = get_font(max(8, int(18 * self.ui_scale)))
        self.item_font = get_font(max(8, int(16 * self.ui_scale)))
        self.small_font = get_font(max(8, int(13 * self.ui_scale)))
        self.tiny_font = get_font(max(8, int(11 * self.ui_scale)))

        # Metrics para consistência total (escaladas — propagam a todo o layout)
        self.MARGIN = self._s(24)
        self.GAP = self._s(12)
        self.RADIUS = self._s(8)

        # Estoque/Hangar agora são grids paginados 3×3 navegados por chevrons
        # laterais (mesmo design da seleção de mundos), em vez de scroll.
        self.GRID_COLS = 3
        self.GRID_ROWS = 3
        self._page_size = self.GRID_COLS * self.GRID_ROWS
        # Largura reservada para a coluna do chevron de cada lado do grid.
        self.CHEVRON_W = self._s(30)
        # Acumulador de tempo para a pulsação dos chevrons.
        self._time = 0.0

        self.locked_icon = get_image(
            BASE_DIR / "assets" / "images" / "icons" / "icon_bloqueado.png"
        )
        self.star_icon = get_image(
            BASE_DIR / "assets" / "images" / "icons" / "icon_star.png"
        )
        star_px = self._s(18)
        self.star_icon_small = pygame.transform.scale(self.star_icon, (star_px, star_px))

        # Reusa a instância oficial do app. Criar uma nova aqui causaria
        # divergência: as mudanças (loadout/nave) seriam salvas no JSON mas
        # ficariam invisíveis para PlayingScene, que consome ``app.player_profile``.
        self.player_profile = self.app.player_profile
        self._ensure_slots()

        # Todos os upgrades em ordem alfabética
        self.all_upgrades = sorted(
            list_all_upgrades_meta(), key=lambda u: u.name.lower()
        )

        # Página atual de cada grid paginado (0-based) e o índice máximo.
        self.upgrade_page = 0
        self.ship_page = 0
        self.max_upgrade_page = 0
        self.max_ship_page = 0

        # Drag and Drop para upgrades
        self.dragging_upgrade: Optional[UpgradeMeta] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.drag_source_slot: Optional[int] = None
        self.drag_invalid_target = False

        self.hovered_upgrade: Optional[UpgradeMeta] = None
        self.hovered_ship: Optional[ShipProfile] = None
        self.hovered_slot_idx: Optional[int] = None

        # --- Navegação por FOCO (controle) --------------------------------
        # Descritor do elemento focado: (região, índice). Regiões: "slot",
        # "stock", "ship", "stock_chevron", "ship_chevron", "back". O foco é a
        # única fonte de verdade da navegação por controle (não o cursor).
        self.focus: tuple = ("slot", 0)
        self._nav_stick_dir: tuple = (0, 0)
        self._nav_repeat_timer: float = 0.0

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

        # Alinhamento dos Cabeçalhos
        header_y = self._s(100)
        self.layout.active_slots_header = pygame.Rect(
            self.MARGIN, header_y, lw - self.MARGIN * 2, self._s(25)
        )

        # Conteúdo começa abaixo do cabeçalho
        ly = header_y + self._s(40)
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
        stock_header_y = self.layout.active_slots[-1].bottom + self._s(35)
        self._stock_start_y = stock_header_y + self._s(35)
        stock_full = pygame.Rect(
            self.MARGIN,
            self._stock_start_y,
            lw - self.MARGIN * 2,
            sh - self._stock_start_y - self._s(80),
        )
        (
            self.layout.upgrade_area,
            self.layout.upgrade_left_chevron,
            self.layout.upgrade_right_chevron,
        ) = self._split_grid_area(stock_full)
        self._rebuild_upgrade_grid()

        # --- NAVE (Centro) ---
        # Preview menor para liberar espaço abaixo para descrição e habilidades.
        preview_s = min(self._s(260), cw - self._s(60))
        preview_y = self._s(110)
        self.layout.ship_preview_rect = pygame.Rect(
            lw + cw // 2 - preview_s // 2, preview_y, preview_s, preview_s
        )

        # --- HANGAR (Direita) ---
        # 1. Atributos
        rx = self.layout.right_area.x + self.MARGIN
        ry = header_y  # Alinhado com Arsenal Ativo
        self.layout.stats_area = pygame.Rect(rx, ry, rw - self.MARGIN * 2, self._s(110))

        # 2. Ship Collection
        self._ship_start_y = self.layout.stats_area.bottom + self._s(70)
        ship_full = pygame.Rect(
            rx,
            self._ship_start_y,
            rw - self.MARGIN * 2,
            sh - self._ship_start_y - self._s(80),
        )
        (
            self.layout.ship_area,
            self.layout.ship_left_chevron,
            self.layout.ship_right_chevron,
        ) = self._split_grid_area(ship_full)
        self._rebuild_ship_grid()

        btn_w = self._s(160)
        btn_h = self._s(40)
        self.layout.back_button = pygame.Rect(self.MARGIN, sh - self._s(60), btn_w, btn_h)

    def _split_grid_area(
        self, full: pygame.Rect
    ) -> Tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        """Divide um painel em (área do grid, chevron esquerdo, chevron direito).

        Reserva ``CHEVRON_W`` de cada lado para as setas e devolve a área
        central onde o grid 3×3 é desenhado, mais os hitboxes verticais
        centralizados das duas setas de paginação.
        """
        cw = self.CHEVRON_W
        grid = pygame.Rect(
            full.x + cw, full.y, full.width - cw * 2, full.height
        )
        ch_h = self._s(64)
        cy = full.centery - ch_h // 2
        left = pygame.Rect(full.x, cy, cw, ch_h)
        right = pygame.Rect(full.right - cw, cy, cw, ch_h)
        return grid, left, right

    def _build_paged_grid(
        self, area: pygame.Rect, items: List[_GridItem], page: int
    ) -> Tuple[List[pygame.Rect], List[_GridItem], int, int]:
        """Monta uma página de um grid 3×3 centralizado em ``area``.

        Células são quadradas, dimensionadas pelo menor limite (largura ou
        altura) para sempre caberem na área. Retorna
        ``(cells, visible_items, max_page, clamped_page)``.
        """
        cols, rows = self.GRID_COLS, self.GRID_ROWS
        gap = self.GAP
        max_page = max(0, (len(items) - 1) // self._page_size) if items else 0
        page = max(0, min(page, max_page))

        cell_w = (area.width - (cols - 1) * gap) / cols
        cell_h = (area.height - (rows - 1) * gap) / rows
        size = max(1, int(min(cell_w, cell_h)))

        grid_w = cols * size + (cols - 1) * gap
        grid_h = rows * size + (rows - 1) * gap
        start_x = area.x + (area.width - grid_w) // 2
        start_y = area.y + (area.height - grid_h) // 2

        start_idx = page * self._page_size
        page_items = items[start_idx : start_idx + self._page_size]

        cells: List[pygame.Rect] = []
        for i in range(len(page_items)):
            r, c = divmod(i, cols)
            cells.append(
                pygame.Rect(
                    start_x + c * (size + gap),
                    start_y + r * (size + gap),
                    size,
                    size,
                )
            )
        return cells, list(page_items), max_page, page

    def _rebuild_upgrade_grid(self):
        (
            cells,
            visible,
            self.max_upgrade_page,
            self.upgrade_page,
        ) = self._build_paged_grid(
            self.layout.upgrade_area, self.all_upgrades, self.upgrade_page
        )
        self.layout.upgrade_grid_cells = cells
        self.layout.visible_upgrades = visible

    def _rebuild_ship_grid(self):
        ships = list(all_ship_profiles())
        (
            cells,
            visible,
            self.max_ship_page,
            self.ship_page,
        ) = self._build_paged_grid(self.layout.ship_area, ships, self.ship_page)
        self.layout.ship_grid_cells = cells
        self.layout.visible_ships = visible

    def _page_upgrades(self, delta: int) -> None:
        """Avança/retrocede a página do Estoque, com wrap nos extremos."""
        if self.max_upgrade_page <= 0:
            return
        self.upgrade_page = (self.upgrade_page + delta) % (self.max_upgrade_page + 1)
        self._rebuild_upgrade_grid()
        sound_manager.play_sound("button_hover")

    def _page_ships(self, delta: int) -> None:
        """Avança/retrocede a página do Hangar, com wrap nos extremos."""
        if self.max_ship_page <= 0:
            return
        self.ship_page = (self.ship_page + delta) % (self.max_ship_page + 1)
        self._rebuild_ship_grid()
        sound_manager.play_sound("button_hover")

    def _page_panel_at(self, x: int, delta: int) -> None:
        """Pagina o painel sob a coordenada ``x`` (esquerda=Estoque, dir=Hangar).

        Fonte única usada pela roda do mouse, pelas setas do teclado e pelos
        botões LB/RB do controle.
        """
        mid_x = self.app.screen.get_width() // 2
        if x < mid_x:
            self._page_upgrades(delta)
        else:
            self._page_ships(delta)

    # ------------------------------------------------------------------
    # Navegação por FOCO (controle) — independente do cursor virtual
    # ------------------------------------------------------------------

    def _focus_nodes(self) -> List[Tuple[tuple, pygame.Rect]]:
        """Todos os elementos navegáveis como (descritor, rect), na ordem
        visual. Reconstruído a cada consulta pois página/layout mudam."""
        nodes: List[Tuple[tuple, pygame.Rect]] = []
        for i, r in enumerate(self.layout.active_slots):
            nodes.append((("slot", i), r))
        for i, r in enumerate(self.layout.upgrade_grid_cells):
            nodes.append((("stock", i), r))
        for i, r in enumerate(self.layout.ship_grid_cells):
            nodes.append((("ship", i), r))
        if self.max_upgrade_page > 0:
            nodes.append((("stock_chevron", 0), self.layout.upgrade_left_chevron))
            nodes.append((("stock_chevron", 1), self.layout.upgrade_right_chevron))
        if self.max_ship_page > 0:
            nodes.append((("ship_chevron", 0), self.layout.ship_left_chevron))
            nodes.append((("ship_chevron", 1), self.layout.ship_right_chevron))
        nodes.append((("back", 0), self.layout.back_button))
        return nodes

    def _focus_rect(self, desc: tuple) -> Optional[pygame.Rect]:
        for d, r in self._focus_nodes():
            if d == desc:
                return r
        return None

    def _focused_rect(self) -> Optional[pygame.Rect]:
        return self._focus_rect(self.focus)

    def _validate_focus(self) -> None:
        """Garante que `self.focus` aponta para um elemento existente. Após
        paginar (grid encolheu) ou trocar de layout, reancora sem travar."""
        nodes = self._focus_nodes()
        descs = [d for d, _ in nodes]
        if not descs:
            return
        if self.focus in descs:
            return
        region = self.focus[0] if self.focus else None
        same = [d for d in descs if d[0] == region]
        if same:
            idx = self.focus[1] if len(self.focus) > 1 else 0
            self.focus = same[max(0, min(idx, len(same) - 1))]
        else:
            self.focus = descs[0]

    def _node_at_pos(self, pos: Tuple[int, int]) -> Optional[tuple]:
        for desc, rect in self._focus_nodes():
            if rect.collidepoint(pos):
                return desc
        return None

    def _apply_nav(self, dx: int, dy: int) -> None:
        """Move o foco em (dx, dy) e força o modo focus (esconde o cursor)."""
        self.app._set_cursor_mode("focus")
        self._move_focus(dx, dy)

    def _move_focus(self, dx: int, dy: int) -> None:
        """Foco → vizinho mais próximo na direção (dx +1=dir, dy +1=baixo).

        Ancorado no rect do elemento FOCADO (não no cursor). Score = distância
        no eixo principal + 2× o desvio lateral, favorecendo alvos alinhados e
        evitando saltos diagonais. Sem alvo na direção (borda externa), não faz
        nada — nunca trava, pois B sempre volta ao menu e as demais direções
        seguem disponíveis."""
        self._validate_focus()
        cur = self._focused_rect()
        if cur is None:
            return
        cx, cy = cur.center
        best_desc: Optional[tuple] = None
        best_score = float("inf")
        for desc, rect in self._focus_nodes():
            if desc == self.focus:
                continue
            tx, ty = rect.center
            vx, vy = tx - cx, ty - cy
            if dx != 0 and vx * dx <= 0:
                continue
            if dy != 0 and vy * dy <= 0:
                continue
            if dx != 0:
                primary, lateral = abs(vx), abs(vy)
            else:
                primary, lateral = abs(vy), abs(vx)
            score = primary + lateral * 2.0
            if score < best_score:
                best_score = score
                best_desc = desc
        if best_desc is not None and best_desc != self.focus:
            self.focus = best_desc
            sound_manager.play_sound("button_hover")

    def _sync_hovered_from_focus(self) -> None:
        """Deriva hovered_* (usados por render/tooltip/preview) do foco atual."""
        self.hovered_upgrade = self.hovered_ship = self.hovered_slot_idx = None
        if not self.focus:
            return
        region = self.focus[0]
        idx = self.focus[1] if len(self.focus) > 1 else 0
        if region == "stock" and idx < len(self.layout.visible_upgrades):
            self.hovered_upgrade = self.layout.visible_upgrades[idx]
        elif region == "ship" and idx < len(self.layout.visible_ships):
            self.hovered_ship = self.layout.visible_ships[idx]
        elif region == "slot" and idx < self.player_profile.unlocked_slots:
            self.hovered_slot_idx = idx

    def _poll_stick_nav(self, dt: float) -> None:
        """Analógico (LS/RS de qualquer slot) move o foco discretamente, com
        atraso inicial + repetição ao segurar. Só ativo com gamepad ligado."""
        from ..core.gamepad import MAX_GAMEPAD_SLOTS

        gp = self.app.gamepad
        bx = by = 0.0
        best_mag = 0.0
        for slot in range(MAX_GAMEPAD_SLOTS):
            if not gp.is_slot_active(slot):
                continue
            for side in ("left", "right"):
                sx, sy = gp.get_stick(side, slot=slot)
                mag = sx * sx + sy * sy
                if mag > best_mag:
                    best_mag, bx, by = mag, sx, sy
        if best_mag < self.NAV_STICK_THRESHOLD ** 2:
            self._nav_stick_dir = (0, 0)
            self._nav_repeat_timer = 0.0
            return
        d = (1 if bx > 0 else -1, 0) if abs(bx) >= abs(by) else (0, 1 if by > 0 else -1)
        if d != self._nav_stick_dir:
            self._nav_stick_dir = d
            self._nav_repeat_timer = self.NAV_INITIAL_DELAY
            self._apply_nav(*d)
        else:
            self._nav_repeat_timer -= dt
            if self._nav_repeat_timer <= 0.0:
                self._nav_repeat_timer = self.NAV_REPEAT_RATE
                self._apply_nav(*d)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._return_to_menu()

        # Setas esquerda/direita (teclado, ou D-pad horizontal quando o
        # snap-focus de app.py não encontra alvo) paginam o painel sob o
        # cursor — mesma divisão por x da roda do mouse.
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_LEFT,
            pygame.K_RIGHT,
        ):
            self._page_panel_at(
                pygame.mouse.get_pos()[0], -1 if event.key == pygame.K_LEFT else 1
            )
            return

        # D-pad move o FOCO discreto (hat: y +1 = cima). Fonte única com o
        # analógico (_poll_stick_nav): navegação sem depender do cursor.
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if x:
                self._apply_nav(1 if x > 0 else -1, 0)
            elif y:
                self._apply_nav(0, -1 if y > 0 else 1)
            return

        # Controle: A age sobre o ELEMENTO FOCADO (não sob o cursor). B volta.
        # LB/RB paginam o grid da região focada (atalho às setas de página).
        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                self._handle_gamepad_confirm()
                return
            if event.button == XboxButton.B:
                self._return_to_menu()
                return
            if event.button in (XboxButton.LB, XboxButton.RB):
                delta = -1 if event.button == XboxButton.LB else 1
                if self.focus and self.focus[0] in ("ship", "ship_chevron"):
                    self._page_ships(delta)
                else:
                    self._page_upgrades(delta)
                self._validate_focus()
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout.back_button.collidepoint(pos):
                self._return_to_menu()

            if self._handle_chevron_click(pos):
                return

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
            # Roda do mouse: divisão pelo meio horizontal — esquerda pagina o
            # Estoque, direita o Hangar. A coluna central só mostra preview,
            # então a fronteira exata não importa (sem zona morta).
            self._page_panel_at(event.pos[0], -1 if event.button == 4 else 1)

    def _handle_chevron_click(self, pos: Tuple[int, int]) -> bool:
        """Trata clique/A sobre uma das setas de paginação. Retorna True se
        consumiu o evento."""
        if self.max_upgrade_page > 0:
            if self.layout.upgrade_left_chevron.collidepoint(pos):
                self._page_upgrades(-1)
                return True
            if self.layout.upgrade_right_chevron.collidepoint(pos):
                self._page_upgrades(1)
                return True
        if self.max_ship_page > 0:
            if self.layout.ship_left_chevron.collidepoint(pos):
                self._page_ships(-1)
                return True
            if self.layout.ship_right_chevron.collidepoint(pos):
                self._page_ships(1)
                return True
        return False

    def _handle_gamepad_confirm(self) -> None:
        """Aciona ``A`` sobre o ELEMENTO FOCADO (não o cursor).

        - Voltar: retorna ao menu.
        - Chevron: pagina o grid correspondente.
        - Card de nave: seleciona/compra (igual ao click do mouse).
        - Slot ativo equipado: retira o upgrade; bloqueado: tenta destravar.
        - Card do Estoque: equipa no 1º slot livre; toggle se já equipado.
        """
        self._validate_focus()
        if not self.focus:
            return
        region = self.focus[0]
        idx = self.focus[1] if len(self.focus) > 1 else 0

        if region == "back":
            self._return_to_menu()
        elif region == "stock_chevron":
            self._page_upgrades(-1 if idx == 0 else 1)
            self._validate_focus()
        elif region == "ship_chevron":
            self._page_ships(-1 if idx == 0 else 1)
            self._validate_focus()
        elif region == "slot" and idx < len(self.layout.active_slots):
            self._gamepad_slot_action(idx, self.layout.active_slots[idx])
        elif region == "stock" and idx < len(self.layout.visible_upgrades):
            self._gamepad_stock_action(
                self.layout.visible_upgrades[idx], self.layout.upgrade_grid_cells[idx]
            )
        elif region == "ship" and idx < len(self.layout.visible_ships):
            self._handle_ship_click(
                self.layout.visible_ships[idx], self.layout.ship_grid_cells[idx]
            )

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
                FloatingMessage(_rect.centerx, _rect.top, t("upgrades.msg.locked"), colors.RED)
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
            FloatingMessage(_rect.centerx, _rect.top, t("upgrades.msg.no_space"), colors.RED)
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
                        t("upgrades.msg.acquired", name=ship_display_name(ship)),
                        colors.GREEN,
                    )
                )
        else:
            self.shaking_ship_id, self.shake_start_time = ship.id, time.time()
            self.floating_messages.append(
                FloatingMessage(
                    rect.centerx, rect.top, t("upgrades.msg.insufficient"), colors.RED
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
        from ..core.visual_quality import visual_quality

        anim = visual_quality.ui_animations
        self.r.starfield.update(dt)
        self._time += dt
        if self.is_entering:
            # Animações off: entrada instantânea (sem fade de tela cheia por frame).
            if anim:
                self.entry_progress = min(
                    1.0, self.entry_progress + dt / self.entry_duration
                )
            else:
                self.entry_progress = 1.0
            if self.entry_progress >= 1.0:
                self.is_entering = False
        if self.transitioning:
            if anim:
                self.transition_progress += dt / self.transition_duration
            else:
                self.transition_progress = 1.0
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

        # Analógico → foco discreto (não move o cursor; ver owns_gamepad_navigation).
        self._poll_stick_nav(dt)
        self._validate_focus()

        m_pos = pygame.mouse.get_pos()
        self.hovered_upgrade = self.hovered_ship = self.hovered_slot_idx = None
        if not self.dragging_upgrade:
            if self.app._cursor_navigation_mode == "cursor":
                # Modo mouse: hover segue o cursor E sincroniza o foco, para a
                # troca mouse↔controle continuar do mesmo ponto.
                node = self._node_at_pos(m_pos)
                if node is not None:
                    self.focus = node
                    self._sync_hovered_from_focus()
            else:
                # Modo focus (DPad/analógico): destaques derivam do foco.
                self._sync_hovered_from_focus()
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
        title = self.title_font.render(t("upgrades.title"), True, CUSTOM_GOLD)
        surface.blit(
            title,
            title.get_rect(
                centerx=surface.get_width() // 2,
                top=self._s(24) + int(self._s(20) * (1.0 - alpha_mult)),
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
        panel_top = self._s(80)
        panel_h = sh - panel_top - self._s(70)
        side_pad = self._s(10)
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
        # Ícone da nave pulsando no preview. Animações off: tamanho fixo (sem o
        # re-scale por frame do sprite).
        from ..core.visual_quality import visual_quality

        pulse = (
            1.0 + 0.04 * math.sin(time.time() * 3)
            if visual_quality.ui_animations
            else 1.0
        )
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
        y = rect.bottom + self._s(8)
        name_surf = self.title_font.render(ship_display_name(ship).upper(), True, CUSTOM_GOLD)
        surface.blit(
            name_surf, name_surf.get_rect(center=(cx, y + name_surf.get_height() // 2))
        )
        y += name_surf.get_height() + self._s(6)

        # Largura máxima para todo o texto: respeita a coluna central com folga.
        # Mantém uma margem interna de 20px de cada lado.
        center_x = self.layout.center_area.x
        center_w = self.layout.center_area.width
        max_w = max(self._s(120), center_w - self._s(40))
        text_left = center_x + self._s(20)
        text_right = center_x + center_w - self._s(20)

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
                y_pos += line_surf.get_height() + self._s(2)
            return y_pos

        # Tags (categoria) em uma linha discreta.
        if ship.tags:
            y = _draw_wrapped(
                " · ".join(ship_tags(ship)), self.small_font, (160, 160, 200), y, max_lines=1
            )
            y += self._s(6)

        # Descrição: cap alto o suficiente para caber as descrições mais longas
        # (Reverberador, Caçador) sem truncar. Clip da coluna garante que nada
        # vaze lateralmente; o eixo vertical empurra o conteúdo seguinte. As
        # frases que mencionam ações (charge shot, Cofre, dash) trocam de
        # legenda conforme o input ativo via `format_ship_description`.
        desc_text = format_ship_description(ship, self.app.gamepad.is_active)
        y = _draw_wrapped(desc_text, self.small_font, colors.WHITE, y, max_lines=4)
        y += self._s(6)

        # Linha divisória sutil.
        pygame.draw.line(surface, (90, 90, 110), (text_left, y), (text_right, y), 1)
        y += self._s(8)

        # Atributos numéricos: só os que diferem do padrão.
        stat_rows: list[tuple[str, str]] = []
        if abs(ship.damage_mult - 1.0) > 1e-6:
            stat_rows.append((t("upgrades.stat.damage"), self._fmt_mult(ship.damage_mult)))
        if abs(ship.fire_rate_mult - 1.0) > 1e-6:
            stat_rows.append((t("upgrades.stat.firerate"), self._fmt_mult(ship.fire_rate_mult)))
        if abs(ship.speed_mult - 1.0) > 1e-6:
            stat_rows.append((t("upgrades.stat.speed"), self._fmt_mult(ship.speed_mult)))
        if ship.extra_lives != 0:
            stat_rows.append((t("upgrades.stat.lives"), f"{ship.extra_lives:+d}"))

        for label, value in stat_rows:
            y = _draw_wrapped(
                f"{label}: {value}", self.small_font, (210, 210, 210), y, max_lines=1
            )

        if stat_rows:
            y += self._s(8)

        # Habilidades especiais com as teclas necessárias.
        ability_rows = self._ship_ability_descriptions(ship)
        if ability_rows:
            header = self.small_font.render(t("upgrades.abilities_header"), True, CUSTOM_GOLD)
            surface.blit(
                header, header.get_rect(center=(cx, y + header.get_height() // 2))
            )
            y += header.get_height() + self._s(4)
            for line in ability_rows:
                # Cada habilidade pode quebrar em até 2 linhas se for longa.
                y = _draw_wrapped(
                    line, self.small_font, (200, 220, 255), y, max_lines=2
                )
                y += self._s(1)

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
            lines.append(
                t("upgrades.ability.dash", keys=dash_key, cd=f"{ship.dash_cooldown:.0f}")
            )
        if ship.has_charge_shot:
            charge_key = self._input_label(t("upgrades.key.charge_kb"), "LT")
            lines.append(
                t(
                    "upgrades.ability.charge",
                    keys=charge_key,
                    mult=f"{ship.charge_shot_damage_mult:.0f}",
                    time=f"{ship.charge_shot_max_time:.1f}",
                )
            )
        if ship.powerup_slots > 0:
            powerup_keys = self._input_label("Q/E", "Y/A")
            lines.append(
                t("upgrades.ability.powerup", keys=powerup_keys, n=ship.powerup_slots)
            )
        if ship.permanent_mini_ships > 0:
            n = ship.permanent_mini_ships
            key = "upgrades.ability.mini_many" if n > 1 else "upgrades.ability.mini_one"
            lines.append(t(key, n=n))
        if ship.pickup_radius_mult > 1.5:
            lines.append(t("upgrades.ability.pickup"))
        if ship.pierce_count > 0:
            lines.append(t("upgrades.ability.pierce", n=ship.pierce_count))
        if ship.bullet_speed_mult != 1.0:
            key = (
                "upgrades.ability.fast_shot"
                if ship.bullet_speed_mult > 1.0
                else "upgrades.ability.slow_shot"
            )
            pct = int(round(abs(ship.bullet_speed_mult - 1.0) * 100))
            lines.append(t(key, pct=pct))
        if ship.combo_damage_per_kill > 0:
            per_kill = int(ship.combo_damage_per_kill * 100)
            cap = int(ship.combo_damage_cap * 100) if ship.combo_damage_cap > 0 else 0
            cap_txt = t("upgrades.ability.combo_cap", cap=cap) if cap else ""
            lines.append(t("upgrades.ability.combo", per=per_kill, cap=cap_txt))
            if ship.combo_fire_rate_bonus > 0:
                lines.append(
                    t(
                        "upgrades.ability.combo_fire",
                        fire=int(round(ship.combo_fire_rate_bonus * 100)),
                    )
                )
        return lines

    def _draw_left_column(self, surface: pygame.Surface):
        h = self.layout.active_slots_header
        total_weight = self.player_profile.get_total_equipped_weight()
        cap = self.player_profile.unlocked_slots
        txt = self.header_font.render(
            t("upgrades.arsenal", weight=total_weight, cap=cap), True, colors.WHITE
        )
        surface.blit(txt, h)

        # Barra de capacidade de peso logo abaixo do título.
        bar_x = h.x
        bar_y = h.bottom + self._s(4)
        bar_w = h.width
        bar_h = self._s(6)
        bar_radius = self._s(3)
        pygame.draw.rect(
            surface, (40, 40, 50), (bar_x, bar_y, bar_w, bar_h), border_radius=bar_radius
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
                    surface,
                    fill_color,
                    (bar_x, bar_y, fill_w, bar_h),
                    border_radius=bar_radius,
                )

        for i, r in enumerate(self.layout.active_slots):
            eq = (
                self.player_profile.upgrade_loadout[i]
                if i < len(self.player_profile.upgrade_loadout)
                else None
            )
            lock, dr = i >= self.player_profile.unlocked_slots, r.copy()
            if self.shaking_slot == i:
                dr.x += int(self._s(8) * math.sin((time.time() - self.shake_start_time) * 40))

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
            if self.hovered_slot_idx == i:
                self._draw_focus_ring(surface, dr)
            if lock:
                self._draw_lock_indicator(
                    surface, dr, self.player_profile.get_slot_cost(i)
                )
            elif eq:
                meta = next((u for u in self.all_upgrades if u.type == eq), None)
                if meta:
                    icon_radius = int(dr.width * 0.35)
                    icon_cy = dr.centery - self._s(4)
                    pygame.draw.circle(
                        surface,
                        CUSTOM_PURPLE,
                        (dr.centerx, icon_cy),
                        icon_radius,
                    )
                    surf = self.header_font.render(
                        get_upgrade_icon(meta.name, meta.icon_id), True, CUSTOM_GOLD
                    )
                    surface.blit(surf, surf.get_rect(center=(dr.centerx, icon_cy)))
                    # Badge de peso no canto inferior esquerdo (consistente com Estoque).
                    self._draw_weight_badge(surface, dr, meta.slot_weight, dim=False)
                    self._draw_equipped_badge(surface, dr)

        surface.blit(
            self.header_font.render(
                self._page_header(t("upgrades.stock"), self.upgrade_page, self.max_upgrade_page),
                True,
                colors.WHITE,
            ),
            (self.MARGIN, self._stock_start_y - self._s(35)),
        )
        # Pré-calcula peso atual equipado para decidir se cada upgrade ainda cabe.
        current_weight = self.player_profile.get_total_equipped_weight()
        slot_cap = self.player_profile.unlocked_slots
        for i, rect in enumerate(self.layout.upgrade_grid_cells):
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
            if self.hovered_upgrade == upg:
                self._draw_focus_ring(surface, rect)
        self._draw_chevrons(
            surface,
            self.layout.upgrade_left_chevron,
            self.layout.upgrade_right_chevron,
            self.max_upgrade_page,
        )

    def _draw_right_column(self, surface: pygame.Surface):
        ship = self.hovered_ship or get_ship_profile(self.player_profile.selected_ship)
        curr = get_ship_profile(self.player_profile.selected_ship)
        surface.blit(
            self.header_font.render(t("upgrades.attributes"), True, colors.WHITE),
            self.layout.stats_area.topleft,
        )
        sy = self.layout.stats_area.y + self._s(35)
        stat_gap = self._s(30)
        self._draw_stat_bar(
            surface,
            self.layout.stats_area.x,
            sy,
            self.layout.stats_area.width,
            t("upgrades.bar.power"),
            ship.damage_mult,
            curr.damage_mult,
        )
        self._draw_stat_bar(
            surface,
            self.layout.stats_area.x,
            sy + stat_gap,
            self.layout.stats_area.width,
            t("upgrades.bar.firerate"),
            ship.fire_rate_mult,
            curr.fire_rate_mult,
        )
        self._draw_stat_bar(
            surface,
            self.layout.stats_area.x,
            sy + stat_gap * 2,
            self.layout.stats_area.width,
            t("upgrades.bar.agility"),
            ship.speed_mult,
            curr.speed_mult,
        )

        surface.blit(
            self.header_font.render(
                self._page_header(t("upgrades.hangar"), self.ship_page, self.max_ship_page),
                True,
                colors.WHITE,
            ),
            (
                self.layout.right_area.x + self.MARGIN,
                self.layout.stats_area.bottom + self._s(30),
            ),
        )
        for i, rect in enumerate(self.layout.ship_grid_cells):
            s = self.layout.visible_ships[i]
            unl, sel = (
                self.player_profile.is_ship_unlocked(s.id),
                self.player_profile.selected_ship == s.id,
            )
            dr = rect.move(
                (
                    int(self._s(6) * math.sin((time.time() - self.shake_start_time) * 40))
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
            if self.hovered_ship == s:
                self._draw_focus_ring(surface, dr)
        self._draw_chevrons(
            surface,
            self.layout.ship_left_chevron,
            self.layout.ship_right_chevron,
            self.max_ship_page,
        )
        bal_y = self.app.screen.get_height() - self._s(55)
        surface.blit(
            self.star_icon_small, (self.layout.right_area.x + self.MARGIN, bal_y)
        )
        surface.blit(
            self.item_font.render(
                t("upgrades.stars", n=self.player_profile.available_stars), True, CUSTOM_GOLD
            ),
            (self.layout.right_area.x + self.MARGIN + self._s(25), bal_y + self._s(1)),
        )

    @staticmethod
    def _page_header(label: str, page: int, max_page: int) -> str:
        """Anexa o indicador "n/total" ao título quando há mais de uma página."""
        if max_page <= 0:
            return label
        return f"{label}  {page + 1}/{max_page + 1}"

    def _draw_chevrons(
        self,
        surface: pygame.Surface,
        left: pygame.Rect,
        right: pygame.Rect,
        max_page: int,
    ) -> None:
        """Desenha as setas chevron de paginação (mesmo estilo pixel-art da
        seleção de mundos). Só aparecem quando há mais de uma página."""
        if max_page <= 0:
            return
        from ..core.visual_quality import visual_quality

        pulse = (math.sin(self._time * 4) + 1) * 0.5 if visual_quality.ui_animations else 0.5
        alpha = int(120 + 135 * pulse)
        mouse = pygame.mouse.get_pos()
        focus_rect = self._focused_rect()
        # Realça a seta sob o cursor (mouse) OU com o foco do controle.
        left_hot = left.collidepoint(mouse) or left == focus_rect
        right_hot = right.collidepoint(mouse) or right == focus_rect
        # `<` com o bico à esquerda do box; `>` com o bico à direita.
        self._draw_pixel_chevron(
            surface,
            left.x + self._s(4),
            left.centery,
            -1,
            CUSTOM_GOLD,
            alpha,
            (1.3 if left_hot else 1.0) * self.ui_scale,
        )
        self._draw_pixel_chevron(
            surface,
            right.right - self._s(4),
            right.centery,
            1,
            CUSTOM_GOLD,
            alpha,
            (1.3 if right_hot else 1.0) * self.ui_scale,
        )

    @staticmethod
    def _draw_pixel_chevron(
        surface: pygame.Surface,
        x_tip: int,
        center_y: int,
        direction: int,
        color: Tuple[int, int, int],
        alpha: int,
        scale: float = 1.0,
    ) -> None:
        """Chevron pixelado (``<`` ou ``>``) idêntico ao da seleção de mundos.

        ``direction``: -1 aponta para a esquerda, +1 para a direita. ``x_tip``
        é a coordenada da ponta da seta (lado do bico)."""
        length = max(6, int(16 * scale))
        pixel = max(2, int(4 * scale))
        chevron = pygame.Surface((length + pixel, length * 2 + pixel), pygame.SRCALPHA)
        for i in range(0, length, pixel):
            px = i if direction == -1 else length - i
            pygame.draw.rect(chevron, (*color, alpha), (px, length - i, pixel, pixel))
            pygame.draw.rect(chevron, (*color, alpha), (px, length + i, pixel, pixel))
        dest = chevron.get_rect(centery=center_y)
        if direction == -1:
            dest.left = x_tip
        else:
            dest.right = x_tip
        surface.blit(chevron, dest.topleft)

    def get_focusable_rects(self) -> list[pygame.Rect]:
        """Rects navegáveis pelo snap-focus do D-pad (ver ``app.py``).

        Inclui slots ativos desbloqueados, células visíveis de Estoque e
        Hangar, as setas de paginação ativas e o botão Voltar. O D-pad pula o
        cursor para o rect mais próximo na direção apertada; ``A`` então age
        sobre o que estiver sob o cursor (ver ``_handle_gamepad_confirm``)."""
        rects: list[pygame.Rect] = list(self.layout.active_slots)
        rects.extend(self.layout.upgrade_grid_cells)
        rects.extend(self.layout.ship_grid_cells)
        if self.max_upgrade_page > 0:
            rects.append(self.layout.upgrade_left_chevron)
            rects.append(self.layout.upgrade_right_chevron)
        if self.max_ship_page > 0:
            rects.append(self.layout.ship_left_chevron)
            rects.append(self.layout.ship_right_chevron)
        rects.append(self.layout.back_button)
        return rects

    def _draw_focus_ring(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Anel pulsante de seleção ao redor do item em foco.

        Crítico no controle: o ponteiro do mouse fica oculto no modo de
        navegação por D-pad, então este anel é a única indicação clara de
        qual card/slot está selecionado. Cor distinta das demais bordas
        (amarelo=hover/seleção, dourado=equipado) para não confundir."""
        from ..core.visual_quality import visual_quality

        pulse = (math.sin(self._time * 6) + 1) * 0.5 if visual_quality.ui_animations else 0.5
        color = (int(80 + 70 * pulse), int(190 + 50 * pulse), 255)
        ring = rect.inflate(self._s(8), self._s(8))
        pygame.draw.rect(
            surface, color, ring, 3, border_radius=self.RADIUS + self._s(3)
        )

    def _draw_lock_indicator(
        self, surface: pygame.Surface, rect: pygame.Rect, cost: int
    ):
        can = self.player_profile.available_stars >= cost
        surface.blit(self.star_icon_small, (rect.centerx - self._s(18), rect.y + self._s(4)))
        surface.blit(
            self.tiny_font.render(str(cost), True, colors.GREEN if can else colors.RED),
            (rect.centerx + self._s(4), rect.y + self._s(6)),
        )
        icon_s = int(rect.width * 0.4)
        surface.blit(
            pygame.transform.scale(self.locked_icon, (icon_s, icon_s)),
            (rect.centerx - icon_s // 2, rect.centery - self._s(2)),
        )

    def _draw_equipped_badge(self, surface: pygame.Surface, rect: pygame.Rect):
        pygame.draw.circle(
            surface, colors.YELLOW, (rect.right - self._s(8), rect.y + self._s(8)), self._s(7)
        )
        surface.blit(
            self.tiny_font.render("E", True, BLACK),
            (rect.right - self._s(12), rect.y + self._s(2)),
        )

    def _draw_weight_badge(
        self, surface: pygame.Surface, rect: pygame.Rect, weight: int, dim: bool
    ):
        """Badge circular com o peso do upgrade no canto inferior esquerdo."""
        cx, cy = rect.x + self._s(10), rect.bottom - self._s(10)
        r = self._s(8)
        bg = (90, 60, 30) if dim else (50, 50, 70)
        fg = (200, 150, 100) if dim else colors.WHITE
        pygame.draw.circle(surface, bg, (cx, cy), r)
        pygame.draw.circle(surface, fg, (cx, cy), r, 1)
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
        by, bh = y + self._s(14), self._s(6)
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
            t("common.back"),
            self.item_font,
            CUSTOM_PURPLE,
            255,
            0,
        )
        # Anel de foco quando o controle está com o foco no botão Voltar.
        if self.focus == ("back", 0):
            self._draw_focus_ring(surface, self.layout.back_button)

    def _draw_dragging_upgrade(self, surface: pygame.Surface):
        if self.dragging_upgrade is None:
            return
        pos = pygame.mouse.get_pos()
        drag_sz = self._s(55)
        rect = pygame.Rect(
            pos[0] - self.drag_offset[0], pos[1] - self.drag_offset[1], drag_sz, drag_sz
        )
        bg = (80, 40, 40, 200) if self.drag_invalid_target else (60, 60, 60, 200)
        pygame.draw.rect(surface, bg, rect, border_radius=self.RADIUS)
        pygame.draw.circle(
            surface,
            (150, 50, 50) if self.drag_invalid_target else CUSTOM_PURPLE,
            rect.center,
            self._s(18),
        )
        initial = get_upgrade_icon(
            self.dragging_upgrade.name, self.dragging_upgrade.icon_id
        )
        surf = self.header_font.render(initial, True, CUSTOM_GOLD)
        surface.blit(surf, surf.get_rect(center=rect.center))

    @staticmethod
    def _upgrade_stat_lines(upg: UpgradeMeta) -> List[str]:
        """Linhas curtas de stats do upgrade (recarga/duração/peso/cargas).

        Agrupa dois stats por linha para caber na largura do tooltip com a
        fonte pixelada. ``:g`` evita "0s" em durações fracionárias (ex.: dash
        de 0.4s) e mantém inteiros sem casas decimais."""
        lines = [
            t(
                "upgrades.tip.cooldown_weight",
                cd=f"{upg.base_cooldown:g}",
                weight=upg.slot_weight,
            )
        ]
        second: List[str] = []
        if upg.base_duration > 0:
            second.append(t("upgrades.tip.duration", d=f"{upg.base_duration:g}"))
        if upg.base_charges is not None:
            second.append(t("upgrades.tip.charges", n=upg.base_charges))
        if second:
            lines.append("    ".join(second))
        return lines

    def _draw_tooltip(self, surface: pygame.Surface):
        if self.hovered_upgrade is None:
            return
        pos, upg = pygame.mouse.get_pos(), self.hovered_upgrade
        profile = self.player_profile

        # Largura fixa, altura dinâmica
        w = self._s(280)
        padding = self._s(12)
        line_height = self._s(20)
        stat_lh = self._s(16)

        # Quebrar o texto em linhas antes de calcular a altura
        wrapped_lines = wrap_text(self.small_font, upgrade_desc(upg), w - (padding * 2))
        stat_lines = self._upgrade_stat_lines(upg)

        # Motivo de bloqueio por peso (mesma regra de `no_fit` do Estoque):
        # desbloqueado, não equipado, e equipá-lo estouraria a capacidade.
        equipped = profile.get_equipped_slot(upg.type) is not None
        no_fit = (
            (upg.type in profile.unlocked_upgrades)
            and not equipped
            and (
                profile.get_total_equipped_weight() + upg.slot_weight
                > profile.unlocked_slots
            )
        )
        warn = t("upgrades.tip.no_weight") if no_fit else None

        # Altura: top + nome + separador + descrição + gap + stats + aviso + base
        h = (
            self._s(10)
            + self._s(24)
            + self._s(10)
            + (len(wrapped_lines) * line_height)
            + self._s(8)
            + (len(stat_lines) * stat_lh)
            + (self._s(18) if warn else 0)
            + self._s(10)
        )

        x, y = pos[0] + self._s(20), pos[1] + self._s(20)

        # Ajustar posição para não sair da tela
        if y + h > surface.get_height():
            y = pos[1] - h - self._s(10)
        if x + w > surface.get_width():
            x = pos[0] - w - self._s(10)

        # Garantir que não saia pelo topo ou esquerda
        x = max(self._s(10), x)
        y = max(self._s(10), y)

        # Criar superfície do tooltip
        tooltip_surf = pygame.Surface((w, h), pygame.SRCALPHA)

        # Fundo e borda
        tip_radius = self._s(10)
        pygame.draw.rect(
            tooltip_surf, (15, 15, 25, 245), tooltip_surf.get_rect(), border_radius=tip_radius
        )
        pygame.draw.rect(
            tooltip_surf,
            (200, 200, 220, 200),
            tooltip_surf.get_rect(),
            1,
            border_radius=tip_radius,
        )

        # Nome do upgrade
        name_surf = self.item_font.render(upg.name, True, colors.YELLOW)
        tooltip_surf.blit(name_surf, (padding, self._s(10)))

        # Linha separadora sutil
        sep_y = self._s(38)
        pygame.draw.line(
            tooltip_surf, (60, 60, 80), (padding, sep_y), (w - padding, sep_y), 1
        )

        # Descrição (todas as linhas)
        dy = self._s(48)
        for line in wrapped_lines:
            line_surf = self.small_font.render(line, True, colors.WHITE)
            tooltip_surf.blit(line_surf, (padding, dy))
            dy += line_height

        # Stats em fonte miúda, cor fria para se distinguir da descrição.
        dy += self._s(4)
        for line in stat_lines:
            stat_surf = self.tiny_font.render(line, True, (170, 195, 225))
            tooltip_surf.blit(stat_surf, (padding, dy))
            dy += stat_lh

        # Aviso de bloqueio por peso, se houver.
        if warn:
            warn_surf = self.tiny_font.render(warn, True, (235, 120, 120))
            tooltip_surf.blit(warn_surf, (padding, dy))

        surface.blit(tooltip_surf, (x, y))

    def _return_to_menu(self):
        self.fade_out, self.transitioning, self.transition_progress = True, True, 0.0

    def _draw_floating_messages(self, surface: pygame.Surface):
        for m in self.floating_messages:
            m.draw(surface)
