"""upgrades_selection.py — Tela de Aprimoramentos.

**Duas** colunas, não três:

- **Esquerda — a nave.** Carrossel (chevrons ``‹ ›``) com o sprite em destaque,
  nome, estado (em uso / selecionar / custo), descrição, três barras de atributo
  comparando com a nave equipada e, no rodapé do painel, os **três slots** de
  upgrade.
- **Direita — os aprimoramentos.** Grid rolável de cards em duas colunas, com
  abas por papel. Cada card traz medalhão, nome, descrição e stats: a descrição
  virou conteúdo permanente do card porque o tooltip antigo era invisível no
  controle.

O que saiu, e por quê:

- **Peso.** Havia 8 slots E um orçamento de peso (capacidade = slots
  destravados), dois sistemas dizendo a mesma coisa. Agora é um upgrade por
  slot; ``slot_weight`` sobrevive só como *tier de poder* desenhado no card.
- **Drag & drop.** O mouse arrastava e o controle tinha um caminho próprio
  que reimplementava as regras do drop. Um gesto só — clique/``A`` alterna
  equipar/desequipar — vale para os dois inputs e cabe numa função
  (`_activate`).
- **Grade do Hangar.** As 9 naves viraram carrossel; comprar continua aqui.
- **Tooltip.** Substituído pela descrição no card.

**O que esta cena NÃO faz** (extraído, §9 — a cena orquestra, os módulos
decidem):

- `systems/loadout_controller.py` — as regras de equipar/comprar. Devolve um
  `LoadoutResult` tipado; a cena só traduz isso em som, mensagem e animação.
- `scenes/upgrades_layout.py` — toda a geometria (painéis, slots, grid,
  rolagem) e as medidas internas do card.
- `scenes/upgrade_flight.py` — o voo do medalhão entre card e slot.

O voo é **puramente cosmético**: o perfil é alterado no instante do clique,
então sair da tela no meio da animação não deixa estado pendurado. O slot só
desenha o ícone quando o voo chega, para o upgrade não aparecer nos dois
lugares ao mesmo tempo.
"""

import math
from typing import TYPE_CHECKING, List, Optional, Tuple

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
    UpgradeCategory,
    UpgradeMeta,
    UpgradeRole,
    get_upgrade_icon,
    list_all_upgrades_meta,
    upgrade_desc,
)
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from ..systems.loadout_controller import (
    LoadoutAction,
    LoadoutController,
    LoadoutResult,
)
from .ui_helpers import draw_bordered_button, wrap_text
from .upgrade_flight import FlightTrack
from .upgrades_layout import (
    UILayout,
    build_layout,
    card_medallion_radius,
    max_scroll,
    place_cards,
    scroll_to_reveal,
    slot_medallion_radius,
)

if TYPE_CHECKING:
    from ..app import GameApp


# Cor do medalhão por categoria. É a única pista de tipo que o card dá de
# relance — a letra identifica QUAL upgrade, a cor diz DE QUE TIPO ele é.
_CATEGORY_COLORS: dict[UpgradeCategory, Tuple[int, int, int]] = {
    UpgradeCategory.OFFENSIVE: (198, 78, 62),
    UpgradeCategory.DEFENSIVE: (62, 130, 200),
    UpgradeCategory.UTILITY: (142, 98, 202),
}
_MEDALLION_DIM: Tuple[int, int, int] = (70, 70, 78)

# Cor de cada PAPEL — usada nas abas e na tarja do card. Distinta da paleta de
# categoria acima de propósito: são dois eixos diferentes, e pintá-los igual
# faria a aba parecer prometer uma cor de medalhão que não se cumpre.
_ROLE_COLORS: dict[UpgradeRole, Tuple[int, int, int]] = {
    UpgradeRole.DAMAGE: (214, 96, 72),
    UpgradeRole.CROWD: (96, 158, 214),
    UpgradeRole.DEFENSE: (232, 186, 84),
    UpgradeRole.SUPPORT: (110, 200, 140),
}


def _category_color(meta: UpgradeMeta) -> Tuple[int, int, int]:
    return _CATEGORY_COLORS.get(meta.category, CUSTOM_PURPLE)


# Abas de filtro, na ordem de exibição. `None` = "Todos".
#
# São PAPÉIS (`UpgradeRole`), não categorias: a categoria classifica o efeito
# no motor, o papel responde à pergunta que o jogador faz aqui. A tela lê esta
# tupla — acrescentar um papel novo é acrescentar uma linha.
_TABS: Tuple[Tuple[str, Optional[UpgradeRole]], ...] = (
    ("upgrades.tab.all", None),
    ("upgrades.tab.damage", UpgradeRole.DAMAGE),
    ("upgrades.tab.crowd", UpgradeRole.CROWD),
    ("upgrades.tab.defense", UpgradeRole.DEFENSE),
    ("upgrades.tab.support", UpgradeRole.SUPPORT),
)


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
    """Tela de Aprimoramentos (nave à esquerda, lista de upgrades à direita)."""

    # A cena possui a navegação por controle: DPad/analógico movem um FOCO
    # discreto próprio (não o cursor virtual do app). Faz o app pular o cursor
    # virtual e a síntese de setas/teclas — ver app._update_virtual_cursor /
    # app._synthesize_menu_events. Elimina o soft lock do snap-focus por cursor.
    owns_gamepad_navigation = True

    # Cadência da repetição ao segurar uma direção no analógico (feel de menu).
    NAV_STICK_THRESHOLD = 0.5
    NAV_INITIAL_DELAY = 0.32
    NAV_REPEAT_RATE = 0.12

    SHAKE_DURATION = 0.3

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = app.renderer
        self.title_font = get_font(max(8, int(30 * self.ui_scale)))
        self.name_font = get_font(max(8, int(24 * self.ui_scale)))
        self.header_font = get_font(max(8, int(16 * self.ui_scale)))
        self.item_font = get_font(max(8, int(15 * self.ui_scale)))
        self.small_font = get_font(max(8, int(12 * self.ui_scale)))
        self.tiny_font = get_font(max(8, int(10 * self.ui_scale)))

        self.MARGIN = self._s(18)
        self.GAP = self._s(12)
        self.RADIUS = self._s(8)
        self.CHEVRON_W = self._s(28)

        self._time = 0.0

        self.locked_icon = get_image(
            BASE_DIR / "assets" / "images" / "icons" / "icon_bloqueado.png"
        )
        self.star_icon = get_image(
            BASE_DIR / "assets" / "images" / "icons" / "icon_star.png"
        )
        star_px = self._s(18)
        self.star_icon_small = pygame.transform.scale(
            self.star_icon, (star_px, star_px)
        )

        # Reusa a instância oficial do app. Criar uma nova aqui causaria
        # divergência: as mudanças (loadout/nave) seriam salvas no JSON mas
        # ficariam invisíveis para PlayingScene, que consome ``app.player_profile``.
        self.player_profile = self.app.player_profile

        # Grid da direita: categoria primeiro, nome depois. Agrupar por
        # categoria põe cores iguais lado a lado e a aba inteira lê como um
        # bloco, em vez de um mosaico alfabético.
        self.all_upgrades = sorted(
            list_all_upgrades_meta(), key=lambda u: (u.category.value, u.name.lower())
        )
        # Dono das regras (§9): a cena não mexe no perfil por conta própria.
        self.loadout = LoadoutController(self.player_profile, self.all_upgrades)
        self.all_ships: List[ShipProfile] = list(all_ship_profiles())
        self.ship_index = self._index_of_selected_ship()

        # Aba ativa (índice em `_TABS`) e rolagem do grid. `scroll_y` é o valor
        # DESENHADO e `scroll_target` o pedido: a diferença entre os dois é a
        # suavização (ver `update`), que é o que faz a roda do mouse deslizar em
        # vez de pular.
        self.active_tab = 0
        self.scroll_y = 0.0
        self.scroll_target = 0.0
        self.max_scroll = 0.0

        # Voos em andamento (equipar/desequipar). O gate de animações é passado
        # como callable: a qualidade visual pode mudar em Settings com a tela
        # aberta, e uma cópia do valor ficaria velha.
        self.flights = FlightTrack(self._animations_on)

        self.hovered_upgrade: Optional[UpgradeMeta] = None
        self.hovered_slot_idx: Optional[int] = None

        # --- Navegação por FOCO (controle) --------------------------------
        # Descritor do elemento focado: (região, índice). Regiões: "slot",
        # "upg", "ship", "ship_prev", "ship_next", "page_prev", "page_next",
        # "back". O foco é a única fonte de verdade da navegação por controle.
        self.focus: tuple = ("upg", 0)
        self._nav_stick_dir: tuple = (0, 0)
        self._nav_repeat_timer: float = 0.0

        # Tremor de recusa: quem treme e por quanto tempo ainda.
        self.shaking_slot: Optional[int] = None
        self.shaking_ship = False
        self.shake_timer = 0.0

        self.layout = UILayout()
        self._calculate_layout()

        self.floating_messages: List[FloatingMessage] = []
        # Sem campos de transição: o fade de entrar/sair é do `SceneTransition`
        # global. `entry_progress` continua aqui porque NÃO é transição de
        # cena — é a animação de entrada dos elementos da própria tela.
        self.entry_progress, self.is_entering, self.entry_duration = 0.0, True, 0.4

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _index_of_selected_ship(self) -> int:
        for i, ship in enumerate(self.all_ships):
            if ship.id == self.player_profile.selected_ship:
                return i
        return 0

    @property
    def shown_ship(self) -> ShipProfile:
        """Nave no carrossel — nem sempre a equipada (navegar não seleciona)."""
        return self.all_ships[self.ship_index]

    def _calculate_layout(self) -> None:
        """Reconstrói a geometria e recoloca os cards da aba atual."""
        self.layout = build_layout(
            self.app.screen.get_size(),
            self._s,
            slot_count=UPGRADE_SLOT_COUNT,
            tab_count=len(_TABS),
        )
        self._rebuild_grid()

    def _filtered_upgrades(self) -> List[UpgradeMeta]:
        """Upgrades da aba ativa (a ordenação é a do construtor)."""
        return self.loadout.upgrades_for_role(_TABS[self.active_tab][1])

    def _rebuild_grid(self) -> None:
        """Recoloca os cards com a rolagem atual e reprende a rolagem ao fim."""
        itens = self._filtered_upgrades()
        self.max_scroll = max_scroll(self.layout, len(itens))
        self.scroll_target = max(0.0, min(self.scroll_target, self.max_scroll))
        self.scroll_y = max(0.0, min(self.scroll_y, self.max_scroll))
        place_cards(self.layout, itens, self.scroll_y)

    # ------------------------------------------------------------------
    # Navegação por FOCO
    # ------------------------------------------------------------------

    def _focus_nodes(self) -> List[Tuple[tuple, pygame.Rect]]:
        """Elementos navegáveis como (descritor, rect), em ordem visual.

        Reconstruído a cada consulta: página e layout mudam sob os pés."""
        nodes: List[Tuple[tuple, pygame.Rect]] = [
            (("ship_prev", 0), self.layout.ship_prev),
            (("ship", 0), self.layout.ship_preview),
            (("ship_next", 0), self.layout.ship_next),
        ]
        for i, r in enumerate(self.layout.slots):
            nodes.append((("slot", i), r))
        for i, r in enumerate(self.layout.tabs):
            nodes.append((("tab", i), r))
        for i, r in enumerate(self.layout.cards):
            nodes.append((("upg", i), r))
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
        paginar (página menor) ou trocar de layout, reancora sem travar."""
        descs = [d for d, _ in self._focus_nodes()]
        if not descs or self.focus in descs:
            return
        region = self.focus[0] if self.focus else None
        same = [d for d in descs if d[0] == region]
        if same:
            idx = self.focus[1] if len(self.focus) > 1 else 0
            self.focus = same[max(0, min(idx, len(same) - 1))]
        else:
            self.focus = descs[0]

    def _node_at_pos(self, pos: Tuple[int, int]) -> Optional[tuple]:
        """Nó sob o cursor. Card fora da janela do grid não conta.

        Os rects dos cards existem para TODA a aba, inclusive os rolados para
        fora — sem este recorte, um card acima da janela receberia o clique
        dado nas abas ou no cabeçalho, que é onde ele está no papel."""
        dentro_do_grid = self.layout.viewport.collidepoint(pos)
        for desc, rect in self._focus_nodes():
            if desc[0] == "upg" and not dentro_do_grid:
                continue
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
        nada — nunca trava, pois B sempre volta ao menu."""
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
            primary, lateral = (abs(vx), abs(vy)) if dx != 0 else (abs(vy), abs(vx))
            score = primary + lateral * 2.0
            if score < best_score:
                best_score, best_desc = score, desc
        if best_desc is not None and best_desc != self.focus:
            self.focus = best_desc
            sound_manager.play_sound("button_hover")

    def _sync_hovered_from_focus(self) -> None:
        """Deriva hovered_* (usados pelo render) do foco atual."""
        self.hovered_upgrade = None
        self.hovered_slot_idx = None
        if not self.focus:
            return
        region = self.focus[0]
        idx = self.focus[1] if len(self.focus) > 1 else 0
        if region == "upg" and idx < len(self.layout.visible_upgrades):
            self.hovered_upgrade = self.layout.visible_upgrades[idx]
        elif region == "slot":
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
        if best_mag < self.NAV_STICK_THRESHOLD**2:
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

    def get_focusable_rects(self) -> list[pygame.Rect]:
        """Rects navegáveis pelo snap-focus do D-pad (ver ``app.py``)."""
        return [r for _, r in self._focus_nodes()]

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._return_to_menu()
                return
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self._cycle_tab(-1 if event.key == pygame.K_LEFT else 1)
                return
            if event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                self._scroll_by(-1 if event.key == pygame.K_PAGEUP else 1, page=True)
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

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                self._validate_focus()
                self._activate(self.focus)
                return
            if event.button == XboxButton.B:
                self._return_to_menu()
                return
            if event.button in (XboxButton.LB, XboxButton.RB):
                # LB/RB trocam de ABA. É o gesto de "trocar de categoria" que o
                # jogador de controle já conhece das outras telas, e a rolagem
                # do grid não precisa de botão: ela segue o foco sozinha.
                self._cycle_tab(-1 if event.button == XboxButton.LB else 1)
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            node = self._node_at_pos(event.pos)
            if node is not None:
                self.focus = node
                self._activate(node)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self._scroll_by(-1 if event.button == 4 else 1)

    def _activate(self, desc: Optional[tuple]) -> None:
        """Roteador único de ação — clique do mouse e ``A`` do controle.

        Ter UM caminho é o que impede o mouse e o controle de divergirem, que
        era o defeito do fluxo de drag & drop anterior (o drop tinha regras que
        o atalho do controle reimplementava por fora)."""
        if not desc:
            return
        region = desc[0]
        idx = desc[1] if len(desc) > 1 else 0

        if region == "back":
            self._return_to_menu()
        elif region == "ship_prev":
            self._cycle_ship(-1)
        elif region == "ship_next":
            self._cycle_ship(1)
        elif region == "ship":
            self._ship_action()
        elif region == "tab" and idx < len(_TABS):
            self._set_tab(idx)
        elif region == "slot" and idx < len(self.layout.slots):
            self._slot_action(idx)
        elif region == "upg" and idx < len(self.layout.visible_upgrades):
            self._upgrade_action(idx)

    def _set_tab(self, index: int) -> None:
        """Troca a aba e volta o grid ao topo.

        Voltar ao topo é obrigatório: manter a rolagem ao trocar de aba mostra
        um grid vazio quando a aba nova tem menos cards que a rolagem anterior —
        o jogador clica em "Defesa" e vê nada."""
        if index == self.active_tab:
            return
        self.active_tab = index
        self.scroll_y = self.scroll_target = 0.0
        self._rebuild_grid()
        # O foco vai para o primeiro card da aba: quem trocou de aba quer ver o
        # que tem nela, e deixar o foco na aba obrigaria um movimento a mais.
        if self.layout.cards:
            self.focus = ("upg", 0)
        self._validate_focus()
        sound_manager.play_sound("button_hover")

    def _cycle_tab(self, delta: int) -> None:
        self._set_tab((self.active_tab + delta) % len(_TABS))

    def _scroll_by(self, direction: int, *, page: bool = False) -> None:
        """Rola o grid. ``page`` avança uma janela inteira em vez de uma linha."""
        if self.max_scroll <= 0.0:
            return
        step = (
            self.layout.viewport.height
            if page
            else (self.layout.card_h + self.layout.card_gap)
        )
        self.scroll_target = max(
            0.0, min(self.max_scroll, self.scroll_target + direction * step)
        )

    def _ensure_focus_visible(self) -> None:
        """Rola o mínimo necessário para o card focado caber na janela.

        É o que liga a navegação por controle à rolagem: o foco anda pelo grid
        inteiro (inclusive o que está fora da janela) e a janela o persegue, em
        vez de existir um comando separado de rolar."""
        if not self.focus or self.focus[0] != "upg":
            return
        idx = self.focus[1]
        if idx >= len(self.layout.cards):
            return
        self.scroll_target = scroll_to_reveal(
            self.layout, idx, self.scroll_target, self.max_scroll
        )

    def _cycle_ship(self, delta: int) -> None:
        self.ship_index = (self.ship_index + delta) % len(self.all_ships)
        sound_manager.play_sound("button_hover")

    # ------------------------------------------------------------------
    # Ações sobre o perfil
    # ------------------------------------------------------------------

    def _ship_action(self) -> None:
        """Nave do carrossel: seleciona, compra, ou recusa por saldo."""
        ship = self.shown_ship
        self._apply(
            self.loadout.press_ship(ship),
            self.layout.ship_preview,
            ship_name=ship_display_name(ship),
        )

    def _slot_action(self, idx: int) -> None:
        """Slot: destrava (bloqueado) ou devolve o upgrade à lista (equipado)."""
        ancora = self.layout.slots[idx] if idx < len(self.layout.slots) else None
        self._apply(self.loadout.press_slot(idx), ancora)

    def _upgrade_action(self, card_idx: int) -> None:
        """Card: equipa no primeiro slot livre, ou desequipa se já equipado."""
        meta = self.layout.visible_upgrades[card_idx]
        self._apply(self.loadout.toggle_upgrade(meta), self.layout.cards[card_idx])

    # ------------------------------------------------------------------
    # Feedback — a tradução de `LoadoutResult` em som, mensagem e animação
    # ------------------------------------------------------------------

    # Mensagem flutuante por ação. Ausente = ação silenciosa (equipar já é
    # anunciado pelo voo do medalhão; pedir a nave que já está em uso não é
    # evento nenhum).
    _MENSAGEM = {
        LoadoutAction.SLOT_UNLOCKED: ("upgrades.msg.slot_unlocked", colors.GREEN),
        LoadoutAction.SHIP_PURCHASED: ("upgrades.msg.acquired", colors.GREEN),
        LoadoutAction.DENIED_UPGRADE_LOCKED: ("upgrades.msg.locked", colors.RED),
        LoadoutAction.DENIED_NO_FREE_SLOT: ("upgrades.msg.no_space", colors.RED),
        LoadoutAction.DENIED_SLOT_COST: ("upgrades.msg.insufficient", colors.RED),
        LoadoutAction.DENIED_SHIP_COST: ("upgrades.msg.insufficient", colors.RED),
    }

    def _apply(
        self,
        result: LoadoutResult,
        anchor: Optional[pygame.Rect],
        *,
        ship_name: str = "",
    ) -> None:
        """Único ponto que converte uma decisão do controlador em tela e som.

        Concentrar aqui é o que impede o feedback de divergir entre caminhos:
        antes, cada ação tocava o próprio som e montava a própria mensagem, e
        equipar pelo card e pelo slot já soavam diferente por descuido.
        """
        acao = result.action
        if acao is LoadoutAction.NOTHING:
            return

        # Som: conquista, recusa, ou o clique neutro das demais.
        if acao in (
            LoadoutAction.SLOT_UNLOCKED,
            LoadoutAction.SHIP_PURCHASED,
            LoadoutAction.EQUIPPED,
        ):
            sound_manager.play_upgrade_activate()
        elif result.denied:
            sound_manager.play_upgrade_denied()
        else:
            sound_manager.play_sound("button_click")

        # Recusa treme o alvo — é o que diz ONDE o pedido esbarrou.
        if acao is LoadoutAction.DENIED_SHIP_COST:
            self.shaking_ship, self.shake_timer = True, self.SHAKE_DURATION
        elif result.denied and result.slot_index is not None:
            self.shaking_slot = result.slot_index
            self.shake_timer = self.SHAKE_DURATION
            anchor = self.layout.slots[result.slot_index]

        entrada = self._MENSAGEM.get(acao)
        if entrada is not None and anchor is not None:
            chave, cor = entrada
            self._message(anchor, t(chave, name=ship_name), cor)

        self._animate(result, anchor)

    def _animate(self, result: LoadoutResult, anchor: Optional[pygame.Rect]) -> None:
        """Lança o voo do medalhão quando o loadout mudou de fato."""
        meta, slot = result.meta, result.slot_index
        if meta is None or slot is None or slot >= len(self.layout.slots):
            return
        slot_rect = self.layout.slots[slot]
        cor = _category_color(meta)
        if result.action is LoadoutAction.EQUIPPED and anchor is not None:
            self.flights.launch_to_slot(
                meta,
                cor,
                anchor,
                slot_rect,
                card_medallion_radius(anchor, self._s),
                slot_medallion_radius(slot_rect),
                slot,
            )
        elif result.action is LoadoutAction.UNEQUIPPED:
            destino = self._visible_card_rect(meta)
            painel = self.layout.right_panel
            self.flights.launch_to_card(
                meta,
                cor,
                slot_rect,
                destino,
                slot_medallion_radius(slot_rect),
                card_medallion_radius(destino, self._s) if destino else 0,
                slot,
                pygame.Rect(painel.centerx, painel.centery, 1, 1),
            )

    def _message(
        self, anchor: pygame.Rect, text: str, color: Tuple[int, int, int]
    ) -> None:
        self.floating_messages.append(
            FloatingMessage(anchor.centerx, anchor.top, text, color)
        )

    # ------------------------------------------------------------------
    # Animação de voo
    # ------------------------------------------------------------------

    def _animations_on(self) -> bool:
        from ..core.visual_quality import visual_quality

        return bool(visual_quality.ui_animations)

    def _visible_card_rect(self, meta: UpgradeMeta) -> Optional[pygame.Rect]:
        """Rect do card DENTRO da janela do grid, ou None.

        O card pode existir e estar rolado para fora (ou numa aba que não é a
        ativa): nesses casos o voo de volta não tem para onde ir e se apaga."""
        for i, m in enumerate(self.layout.visible_upgrades):
            if m.type != meta.type:
                continue
            rect = self.layout.cards[i]
            return rect if self.layout.viewport.contains(rect) else None
        return None

    # ------------------------------------------------------------------
    # Ciclo da cena
    # ------------------------------------------------------------------

    def exit(self):
        """Garante que loadout/desbloqueios/seleção de nave sejam persistidos
        ao deixar a cena — sem isso o `auto_save` (gated por 10s) pode descartar
        mudanças recentes ao trocar de cena rapidamente."""
        self.player_profile.save()

    def update(self, dt: float):
        self.r.starfield.update(dt)
        self._time += dt

        if self.is_entering:
            # Animações off: entrada instantânea (sem fade de tela cheia por frame).
            if self._animations_on():
                self.entry_progress = min(
                    1.0, self.entry_progress + dt / self.entry_duration
                )
            else:
                self.entry_progress = 1.0
            if self.entry_progress >= 1.0:
                self.is_entering = False

        for m in self.floating_messages:
            m.update(dt)
        self.floating_messages = [m for m in self.floating_messages if not m.is_dead()]

        self.flights.update(dt)

        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - dt)
            if self.shake_timer == 0.0:
                self.shaking_slot, self.shaking_ship = None, False

        # Analógico → foco discreto (não move o cursor; ver owns_gamepad_navigation).
        self._poll_stick_nav(dt)
        self._validate_focus()

        # Rolagem: o alvo persegue o foco e a posição desenhada persegue o
        # alvo. Interpolação exponencial com o passo preso em 1.0 — sem o
        # clamp, um frame longo (dt alto) faria o fator passar de 1 e a
        # rolagem ultrapassaria o alvo, oscilando.
        self._ensure_focus_visible()
        if abs(self.scroll_target - self.scroll_y) > 0.5:
            self.scroll_y += (self.scroll_target - self.scroll_y) * min(1.0, dt * 14.0)
        else:
            self.scroll_y = self.scroll_target
        self._rebuild_grid()

        if self.app._cursor_navigation_mode == "cursor":
            # Modo mouse: hover segue o cursor E sincroniza o foco, para a
            # troca mouse↔controle continuar do mesmo ponto.
            node = self._node_at_pos(pygame.mouse.get_pos())
            if node is not None:
                self.focus = node
        self._sync_hovered_from_focus()

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)
        alpha_mult = self.entry_progress if self.is_entering else 1.0

        title = self.title_font.render(t("upgrades.title"), True, CUSTOM_GOLD)
        surface.blit(
            title,
            title.get_rect(
                centerx=surface.get_width() // 2,
                top=self._s(22) + int(self._s(18) * (1.0 - alpha_mult)),
            ),
        )

        content = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._draw_panel(content, self.layout.left_panel)
        self._draw_panel(content, self.layout.right_panel)
        self._draw_ship_column(content)
        self._draw_slots(content)
        self._draw_upgrade_list(content)
        self._draw_stars(content)
        self._draw_back_button(content)
        self._draw_flights(content)
        self._draw_floating_messages(content)
        content.set_alpha(int(255 * alpha_mult))
        surface.blit(content, (0, 0))

    # ------------------------------------------------------------------
    # Render — peças compartilhadas
    # ------------------------------------------------------------------

    def _draw_panel(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        pygame.draw.rect(
            surface, (20, 20, 25, 180), rect, border_radius=self.RADIUS * 2
        )
        pygame.draw.rect(
            surface, (255, 255, 255, 30), rect, 1, border_radius=self.RADIUS * 2
        )

    def _draw_medallion(
        self,
        surface: pygame.Surface,
        center: Tuple[int, int],
        radius: int,
        meta: UpgradeMeta,
        *,
        dim: bool = False,
        alpha: int = 255,
    ) -> None:
        """Medalhão do upgrade: a MESMA peça no card, no slot e no voo.

        É o que torna a animação legível — o objeto que sai da lista é
        visivelmente o mesmo que aterrissa no slot."""
        if radius <= 1:
            return
        color = _MEDALLION_DIM if dim else _category_color(meta)
        pygame.draw.circle(surface, (*color, alpha), center, radius)
        pygame.draw.circle(
            surface,
            (
                min(255, color[0] + 45),
                min(255, color[1] + 45),
                min(255, color[2] + 45),
                alpha,
            ),
            center,
            radius,
            max(1, self._s(2)),
        )
        font = get_font(max(8, int(radius * 0.95)))
        letter = font.render(
            get_upgrade_icon(meta.name, meta.icon_id),
            True,
            (40, 40, 40) if dim else CUSTOM_GOLD,
        )
        if alpha < 255:
            letter = letter.copy()
            letter.set_alpha(alpha)
        surface.blit(letter, letter.get_rect(center=center))

    def _draw_focus_ring(
        self, surface: pygame.Surface, rect: pygame.Rect, *, inside: bool = False
    ) -> None:
        """Anel pulsante de seleção ao redor do item em foco.

        Crítico no controle: o ponteiro do mouse fica oculto no modo de
        navegação por D-pad, então este anel é a única indicação clara de qual
        card/slot está selecionado.

        ``inside`` desenha o anel POR DENTRO do rect. É o que os cards usam: o
        anel externo cai fora da janela recortada do grid e some justamente nos
        cards da primeira e da última linha, que é onde o foco mais para."""
        pulse = (math.sin(self._time * 6) + 1) * 0.5 if self._animations_on() else 0.5
        color = (int(80 + 70 * pulse), int(190 + 50 * pulse), 255)
        if inside:
            pygame.draw.rect(
                surface,
                color,
                rect.inflate(-self._s(3), -self._s(3)),
                3,
                border_radius=self.RADIUS,
            )
            return
        ring = rect.inflate(self._s(8), self._s(8))
        pygame.draw.rect(
            surface, color, ring, 3, border_radius=self.RADIUS + self._s(3)
        )

    def _draw_pill(
        self,
        surface: pygame.Surface,
        center: Tuple[int, int],
        text: str,
        fg: Tuple[int, int, int],
        bg: Tuple[int, int, int, int],
        font: Optional[pygame.font.Font] = None,
        *,
        midright: Optional[Tuple[int, int]] = None,
    ) -> pygame.Rect:
        """Etiqueta arredondada (estado da nave, selo EQUIPADO).

        ``midright`` ancora pela BORDA DIREITA em vez do centro. Existe porque a
        largura da etiqueta vem do texto: centrada numa coordenada fixa, ela
        cresce para os dois lados e vaza do card quando o rótulo é longo — foi o
        que aconteceu com "EQUIPADO"/"EQUIPPED". Quem precisa encostar numa
        borda tem de ancorar naquela borda, não perto dela."""
        font = font or self.tiny_font
        label = font.render(text, True, fg)
        rect = label.get_rect(center=center).inflate(self._s(16), self._s(9))
        if midright is not None:
            rect.midright = midright
        pygame.draw.rect(surface, bg, rect, border_radius=rect.height // 2)
        pygame.draw.rect(surface, (*fg, 140), rect, 1, border_radius=rect.height // 2)
        surface.blit(label, label.get_rect(center=rect.center))
        return rect

    def _draw_star_cost(
        self, surface: pygame.Surface, center: Tuple[int, int], cost: int
    ) -> None:
        """Custo em estrelas: verde se dá para pagar agora, vermelho se não."""
        can = self.player_profile.available_stars >= cost
        label = self.tiny_font.render(
            str(cost), True, colors.GREEN if can else colors.RED
        )
        icon_w = self.star_icon_small.get_width()
        total = icon_w + self._s(4) + label.get_width()
        x = center[0] - total // 2
        surface.blit(
            self.star_icon_small,
            (x, center[1] - self.star_icon_small.get_height() // 2),
        )
        surface.blit(
            label, label.get_rect(midleft=(x + icon_w + self._s(4), center[1]))
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

    def _draw_chevron_pair(
        self,
        surface: pygame.Surface,
        left: pygame.Rect,
        right: pygame.Rect,
        *,
        scale: float = 1.0,
    ) -> None:
        pulse = (math.sin(self._time * 4) + 1) * 0.5 if self._animations_on() else 0.5
        alpha = int(120 + 135 * pulse)
        mouse = pygame.mouse.get_pos()
        focused = self._focused_rect()
        for rect, direction in ((left, -1), (right, 1)):
            hot = rect.collidepoint(mouse) or rect == focused
            x_tip = rect.x + self._s(3) if direction == -1 else rect.right - self._s(3)
            self._draw_pixel_chevron(
                surface,
                x_tip,
                rect.centery,
                direction,
                CUSTOM_GOLD,
                alpha,
                (1.3 if hot else 1.0) * self.ui_scale * scale,
            )

    # ------------------------------------------------------------------
    # Render — coluna da nave
    # ------------------------------------------------------------------

    def _draw_ship_column(self, surface: pygame.Surface) -> None:
        panel = self.layout.left_panel
        previous_clip = surface.get_clip()
        surface.set_clip(panel)
        try:
            self._draw_ship_preview(surface)
            self._draw_ship_info(surface)
            self._draw_ship_stat_bars(surface)
        finally:
            surface.set_clip(previous_clip)
        self._draw_chevron_pair(surface, self.layout.ship_prev, self.layout.ship_next)

    def _draw_ship_preview(self, surface: pygame.Surface) -> None:
        ship = self.shown_ship
        profile = self.player_profile
        unlocked = profile.is_ship_unlocked(ship.id)
        rect = self.layout.ship_preview.copy()
        if self.shaking_ship:
            rect.x += int(self._s(8) * math.sin(self._time * 40))

        # Holofote: elipse difusa sob a nave. Dá chão ao sprite e é o que faz o
        # preview ler como "peça em exposição" em vez de sprite solto no painel.
        self._draw_spotlight(surface, rect)

        pulse = 1.0 + 0.04 * math.sin(self._time * 3) if self._animations_on() else 1.0
        try:
            img = pygame.transform.scale(
                get_image(BASE_DIR / "assets" / "icons" / ship.sprite_filename),
                (int(rect.width * pulse), int(rect.height * pulse)),
            )
            if not unlocked:
                # Silhueta: a nave bloqueada é reconhecível mas obviamente
                # indisponível — mesma leitura do cadeado do slot.
                img = img.copy()
                img.fill((60, 60, 70), special_flags=pygame.BLEND_MULT)
            surface.blit(img, img.get_rect(center=rect.center))
        except (OSError, pygame.error, ValueError):
            pass

        if not unlocked:
            icon_s = int(rect.width * 0.3)
            icon = pygame.transform.scale(self.locked_icon, (icon_s, icon_s))
            surface.blit(icon, icon.get_rect(center=rect.center))

        if self.focus == ("ship", 0):
            self._draw_focus_ring(surface, self.layout.ship_preview)

    def _draw_spotlight(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Halo elíptico atrás/abaixo da nave, desenhado em camadas.

        Camadas concêntricas com alpha baixo em vez de um blur de verdade: o
        jogo é pixel art e um degradê suave destoaria; três elipses dão o
        volume necessário e custam três `draw` por frame."""
        cx = rect.centerx
        cy = rect.centery + int(rect.height * 0.28)
        for i, alpha in enumerate((14, 20, 30)):
            fator = 1.0 - i * 0.26
            w = int(rect.width * 1.05 * fator)
            h = int(rect.height * 0.34 * fator)
            pygame.draw.ellipse(
                surface,
                (120, 140, 210, alpha),
                pygame.Rect(cx - w // 2, cy - h // 2, w, h),
            )

    def _draw_ship_info(self, surface: pygame.Surface) -> None:
        """Nome, estado, tags, descrição e atributos — de cima para baixo.

        O bloco PARA de desenhar ao encostar no cabeçalho dos slots, em vez de
        depender de contas de altura por resolução: o que não couber some, e o
        que couber nunca invade os slots."""
        ship = self.shown_ship
        profile = self.player_profile
        panel = self.layout.left_panel
        # O texto vai até o topo das barras, que são fixas (ver
        # `_draw_ship_stat_bars`). Quem cede espaço é a prosa.
        limit = self._stat_bars_top() - self._s(4)
        cx = panel.centerx
        y = self.layout.info_top
        max_w = panel.width - self._s(40)

        name = self.name_font.render(ship_display_name(ship).upper(), True, CUSTOM_GOLD)
        surface.blit(name, name.get_rect(midtop=(cx, y)))
        y += name.get_height() + self._s(8)

        # Estado da nave: o que ela é AGORA e o que o clique/A faria.
        if not profile.is_ship_unlocked(ship.id):
            pill = self._draw_pill(
                surface,
                (cx, y + self._s(11)),
                t("upgrades.ship.locked"),
                CUSTOM_GOLD,
                (40, 32, 18, 220),
            )
            self._draw_star_cost(
                surface, (cx, pill.bottom + self._s(11)), ship.unlock_cost
            )
            y = pill.bottom + self._s(24)
        elif profile.selected_ship == ship.id:
            pill = self._draw_pill(
                surface,
                (cx, y + self._s(11)),
                t("upgrades.ship.in_use"),
                CUSTOM_GOLD,
                (48, 40, 12, 220),
            )
            y = pill.bottom + self._s(8)
        else:
            pill = self._draw_pill(
                surface,
                (cx, y + self._s(11)),
                t("upgrades.ship.select"),
                colors.WHITE,
                (34, 34, 48, 220),
            )
            y = pill.bottom + self._s(8)

        if y > limit:
            return

        if ship.tags:
            # " / " em vez do ponto médio da versão antiga: só ASCII no texto
            # renderizado (ver `_card_stats_line`).
            tags = self.tiny_font.render(
                " / ".join(ship_tags(ship)), True, (160, 160, 200)
            )
            surface.blit(tags, tags.get_rect(midtop=(cx, y)))
            y += tags.get_height() + self._s(6)

        # Quantas linhas cabem é decidido ANTES de renderizar: cortar no meio
        # do laço deixaria a última linha terminando numa palavra qualquer, sem
        # as reticências que avisam que há mais texto.
        desc = format_ship_description(ship, self.app.gamepad.is_active)
        linha_h = self.small_font.get_height() + self._s(3)
        cabem = max(0, min(3, (limit - y) // linha_h))
        for line in self._clip_lines(desc, self.small_font, max_w, cabem):
            surf = self.small_font.render(line, True, colors.WHITE)
            surface.blit(surf, surf.get_rect(midtop=(cx, y)))
            y += linha_h

        # Vidas extras não cabem numa barra comparativa (é contagem, não
        # multiplicador), então saem como linha — mas só quando existem.
        if ship.extra_lives != 0 and y + self.tiny_font.get_height() <= limit:
            lives = self.tiny_font.render(
                f"{t('upgrades.stat.lives')}: {ship.extra_lives:+d}",
                True,
                (210, 210, 210),
            )
            surface.blit(lives, lives.get_rect(midtop=(cx, y)))
            y += lives.get_height() + self._s(6)

        self._draw_ship_abilities(surface, ship, cx, y, max_w, limit)

    def _draw_ship_stat_bars(self, surface: pygame.Surface) -> None:
        """As três barras comparativas, ANCORADAS acima dos slots.

        Ficam fora do fluxo de cima para baixo de propósito: são a parte
        estrutural da coluna (existem para toda nave e sempre no mesmo lugar),
        enquanto nome/descrição/habilidades são prosa de tamanho variável. Com
        as barras no fluxo, uma nave de descrição longa empurrava a terceira
        barra para fora e a coluna parecia ter perdido um atributo."""
        panel = self.layout.left_panel
        ship = self.shown_ship
        current = get_ship_profile(self.player_profile.selected_ship)
        bars = (
            (t("upgrades.bar.power"), ship.damage_mult, current.damage_mult),
            (t("upgrades.bar.firerate"), ship.fire_rate_mult, current.fire_rate_mult),
            (t("upgrades.bar.agility"), ship.speed_mult, current.speed_mult),
        )
        bar_x = panel.x + self._s(24)
        bar_w = panel.width - self._s(48)
        y = self._stat_bars_top()
        for label, value, ref in bars:
            self._draw_stat_bar(surface, bar_x, y, bar_w, label, value, ref)
            y += self._s(26)

    def _stat_bars_top(self) -> int:
        """Topo do bloco de barras — também o limite do texto acima dele."""
        return self.layout.slots_header_y - self._s(10) - self._s(26) * 3

    def _draw_ship_abilities(
        self,
        surface: pygame.Surface,
        ship: ShipProfile,
        cx: int,
        y: int,
        max_w: int,
        limit: int,
    ) -> int:
        """Habilidades especiais com as teclas — o que a nave faz de diferente.

        Fica por último no fluxo de propósito: é a informação mais densa da
        coluna e a primeira que pode ser cortada quando a tela é curta."""
        lines = self._ship_ability_descriptions(ship)
        if not lines or y + self.tiny_font.get_height() * 2 > limit:
            return y
        header = self.tiny_font.render(
            t("upgrades.abilities_header"), True, CUSTOM_GOLD
        )
        surface.blit(header, header.get_rect(midtop=(cx, y)))
        y += header.get_height() + self._s(4)
        for line in lines:
            for wrapped in wrap_text(self.tiny_font, line, max_w)[:2]:
                if y + self.tiny_font.get_height() > limit:
                    return y
                surf = self.tiny_font.render(wrapped, True, (200, 220, 255))
                surface.blit(surf, surf.get_rect(midtop=(cx, y)))
                y += surf.get_height() + self._s(2)
        return y

    def _input_label(self, keyboard: str, gamepad: str) -> str:
        """Retorna a legenda apropriada ao modo de input ativo.

        Usa `app.gamepad.is_active` (preferência ligada + controle conectado)
        como discriminador. Quando o player desliga o gamepad em Settings ou
        desconecta o controle, as legendas voltam pro teclado automaticamente.
        """
        return gamepad if self.app.gamepad.is_active else keyboard

    def _ship_ability_descriptions(self, ship: ShipProfile) -> list[str]:
        """Instruções curtas das mecânicas especiais da nave."""
        lines: list[str] = []
        if ship.has_dash:
            lines.append(
                t(
                    "upgrades.ability.dash",
                    keys=self._input_label("SHIFT", "LT"),
                    cd=f"{ship.dash_cooldown:.0f}",
                )
            )
        if ship.has_charge_shot:
            lines.append(
                t(
                    "upgrades.ability.charge",
                    keys=self._input_label(t("upgrades.key.charge_kb"), "LT"),
                    mult=f"{ship.charge_shot_damage_mult:.0f}",
                    time=f"{ship.charge_shot_max_time:.1f}",
                )
            )
        if ship.powerup_slots > 0:
            lines.append(
                t(
                    "upgrades.ability.powerup",
                    keys=self._input_label("Q/E", "Y/A"),
                    n=ship.powerup_slots,
                )
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

    def _draw_stat_bar(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        w: int,
        label: str,
        val: float,
        curr: float,
    ) -> None:
        """Barra comparando a nave do carrossel com a EQUIPADA.

        O trecho verde é o quanto esta nave tem a mais; o vermelho, o quanto
        tem a menos. Sem carrossel a comparação vinha da coluna de atributos;
        aqui ela é o que dá sentido a folhear as naves."""
        text = self.tiny_font.render(label, True, (180, 180, 180))
        surface.blit(text, (x, y))
        by, bh = y + self._s(12), self._s(6)
        pygame.draw.rect(
            surface, (40, 40, 40), (x, by, w, bh), border_radius=self._s(3)
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

    # ------------------------------------------------------------------
    # Render — slots
    # ------------------------------------------------------------------

    def _draw_slots(self, surface: pygame.Surface) -> None:
        profile = self.player_profile
        header = self.header_font.render(
            t(
                "upgrades.slots_header",
                n=profile.unlocked_slots,
                total=UPGRADE_SLOT_COUNT,
            ),
            True,
            colors.WHITE,
        )
        surface.blit(
            header,
            header.get_rect(
                midtop=(self.layout.left_panel.centerx, self.layout.slots_header_y)
            ),
        )

        for i, rect in enumerate(self.layout.slots):
            draw_rect = rect.copy()
            if self.shaking_slot == i:
                draw_rect.x += int(self._s(8) * math.sin(self._time * 40))
            locked = i >= profile.unlocked_slots
            equipped = profile.upgrade_loadout[i] if not locked else None
            focused = self.hovered_slot_idx == i

            bg = (28, 28, 34) if not locked else (22, 22, 26)
            if equipped is not None:
                bg = (38, 46, 38)
            pygame.draw.rect(surface, bg, draw_rect, border_radius=self.RADIUS)
            border = (
                colors.YELLOW
                if focused
                else (70, 70, 78)
                if locked
                else CUSTOM_GOLD
                if equipped is not None
                else colors.GRAY
            )
            pygame.draw.rect(
                surface,
                border,
                draw_rect,
                2 if equipped is not None else 1,
                border_radius=self.RADIUS,
            )

            if locked:
                self._draw_locked_slot(surface, draw_rect, profile.get_slot_cost(i))
            elif equipped is not None and not self.flights.is_slot_pending(i):
                meta = self.loadout.meta_for(equipped)
                if meta is not None:
                    self._draw_equipped_slot(surface, draw_rect, meta)
            else:
                self._draw_empty_slot(surface, draw_rect, i)

            if focused:
                self._draw_focus_ring(surface, draw_rect)

    def _draw_locked_slot(
        self, surface: pygame.Surface, rect: pygame.Rect, cost: int
    ) -> None:
        icon_s = int(rect.width * 0.34)
        icon = pygame.transform.scale(self.locked_icon, (icon_s, icon_s))
        surface.blit(
            icon, icon.get_rect(center=(rect.centerx, rect.centery - self._s(8)))
        )
        self._draw_star_cost(surface, (rect.centerx, rect.bottom - self._s(16)), cost)

    def _draw_empty_slot(
        self, surface: pygame.Surface, rect: pygame.Rect, idx: int
    ) -> None:
        """Slot vazio: um ``+`` discreto e a tecla que o aciona no jogo."""
        arm = int(rect.width * 0.16)
        cx, cy = rect.centerx, rect.centery - self._s(4)
        pygame.draw.line(surface, (90, 90, 100), (cx - arm, cy), (cx + arm, cy), 2)
        pygame.draw.line(surface, (90, 90, 100), (cx, cy - arm), (cx, cy + arm), 2)
        key = self.tiny_font.render(self._slot_key_label(idx), True, (120, 120, 130))
        surface.blit(
            key, key.get_rect(midbottom=(rect.centerx, rect.bottom - self._s(6)))
        )

    def _draw_equipped_slot(
        self, surface: pygame.Surface, rect: pygame.Rect, meta: UpgradeMeta
    ) -> None:
        radius = slot_medallion_radius(rect)
        self._draw_medallion(
            surface, (rect.centerx, rect.centery - self._s(6)), radius, meta
        )
        name = self.tiny_font.render(meta.name, True, colors.WHITE)
        surface.blit(
            name, name.get_rect(midbottom=(rect.centerx, rect.bottom - self._s(6)))
        )

    def _slot_key_label(self, idx: int) -> str:
        """Tecla do slot no jogo — a mesma que o HUD mostra na fileira vazia."""
        try:
            return pygame.key.name(self.player_profile.upgrade_keybindings[idx]).upper()
        except (IndexError, TypeError, pygame.error):
            return str(idx + 1)

    # ------------------------------------------------------------------
    # Render — lista de upgrades
    # ------------------------------------------------------------------

    def _draw_upgrade_list(self, surface: pygame.Surface) -> None:
        # Sem cabeçalho de painel: o título da tela já diz "Aprimoramentos", e
        # repeti-lo aqui gastava uma faixa inteira de altura para dizer o que o
        # jogador acabou de ler. As abas assumem o topo do painel.
        self._draw_tabs(surface)

        # Recorte: o grid rola por baixo das abas e do cabeçalho, e é o clip que
        # impede o card de aparecer em cima delas.
        previous_clip = surface.get_clip()
        surface.set_clip(self.layout.viewport)
        try:
            for i, rect in enumerate(self.layout.cards):
                if rect.bottom < self.layout.viewport.y:
                    continue
                if rect.y > self.layout.viewport.bottom:
                    break  # o resto está abaixo da janela: nada a desenhar
                self._draw_card(surface, rect, self.layout.visible_upgrades[i])
        finally:
            surface.set_clip(previous_clip)

        self._draw_scrollbar(surface)

    def _draw_tabs(self, surface: pygame.Surface) -> None:
        for i, rect in enumerate(self.layout.tabs):
            key, role = _TABS[i]
            ativa = i == self.active_tab
            focada = self.focus == ("tab", i)
            cor = (
                _ROLE_COLORS.get(role, CUSTOM_GOLD) if role is not None else CUSTOM_GOLD
            )
            bg = (*cor, 55) if ativa else (26, 26, 32, 200)
            pygame.draw.rect(surface, bg, rect, border_radius=self.RADIUS)
            pygame.draw.rect(
                surface,
                cor if ativa else (70, 70, 82),
                rect,
                2 if ativa else 1,
                border_radius=self.RADIUS,
            )
            label = self.tiny_font.render(
                t(key), True, colors.WHITE if ativa else (150, 150, 162)
            )
            surface.blit(label, label.get_rect(center=rect.center))
            if focada:
                self._draw_focus_ring(surface, rect)

    def _draw_scrollbar(self, surface: pygame.Surface) -> None:
        """Barra de rolagem fina. Só aparece quando há o que rolar."""
        if self.max_scroll <= 0.0:
            return
        track = self.layout.scrollbar
        pygame.draw.rect(surface, (40, 40, 50), track, border_radius=track.width // 2)
        vp_h = self.layout.viewport.height
        proporcao = vp_h / (vp_h + self.max_scroll)
        alt = max(self._s(24), int(track.height * proporcao))
        avanco = self.scroll_y / self.max_scroll
        y = track.y + int((track.height - alt) * avanco)
        pygame.draw.rect(
            surface,
            (150, 150, 170),
            pygame.Rect(track.x, y, track.width, alt),
            border_radius=track.width // 2,
        )

    def _draw_card(
        self, surface: pygame.Surface, rect: pygame.Rect, meta: UpgradeMeta
    ) -> None:
        profile = self.player_profile
        unlocked = meta.type in profile.unlocked_upgrades
        equipped = profile.get_equipped_slot(meta.type) is not None
        focused = (
            self.hovered_upgrade is not None and self.hovered_upgrade.type == meta.type
        )

        cor = _category_color(meta)
        radius = self.RADIUS

        # --- moldura da carta ---------------------------------------------
        # Duas camadas: o corpo escuro e uma borda interna a 4px. É a borda
        # dupla que dá leitura de CARTA em vez de linha de lista — o mesmo
        # truque das cartas impressas, onde a margem interna emoldura a arte.
        bg = (
            (40, 46, 34)
            if equipped
            else (44, 44, 54)
            if focused
            else (28, 28, 34)
            if unlocked
            else (20, 20, 24)
        )
        pygame.draw.rect(surface, bg, rect, border_radius=radius)
        borda = (
            CUSTOM_GOLD
            if equipped
            else colors.YELLOW
            if focused
            else (*cor, 120)
            if unlocked
            else (60, 60, 68)
        )
        pygame.draw.rect(surface, borda, rect, 2, border_radius=radius)
        pygame.draw.rect(
            surface,
            (255, 255, 255, 18),
            rect.inflate(-self._s(8), -self._s(8)),
            1,
            border_radius=radius,
        )

        # --- tarja de arte (esquerda) --------------------------------------
        # Faixa vertical na cor da categoria com o medalhão no meio: é a "arte"
        # da carta e o ponto de onde o voo até o slot parece se desprender.
        #
        # Ela PARA acima do rodapé em vez de ir até a base: a faixa de rodapé
        # atravessa o card inteiro e é o que dá largura para a linha de stats
        # caber sem ser truncada (presa à coluna de texto, "Duração" não cabia).
        art_w = min(self._s(72), rect.width // 3)
        footer_h = self._s(20)
        art = pygame.Rect(
            rect.x + self._s(5),
            rect.y + self._s(5),
            art_w,
            rect.height - self._s(10) - footer_h,
        )
        art_bg = (
            (int(cor[0] * 0.28), int(cor[1] * 0.28), int(cor[2] * 0.28))
            if unlocked
            else (34, 34, 40)
        )
        pygame.draw.rect(surface, art_bg, art, border_radius=radius - self._s(2))

        medal_r = min(int(art.width * 0.42), int(rect.height * 0.30))
        self._draw_medallion(surface, art.center, medal_r, meta, dim=not unlocked)

        # --- texto ---------------------------------------------------------
        text_x = art.right + self._s(12)
        text_w = rect.right - text_x - self._s(12)

        name = self.item_font.render(
            meta.name, True, CUSTOM_GOLD if equipped else colors.WHITE
        )
        surface.blit(name, (text_x, rect.y + self._s(10)))

        desc_y = rect.y + self._s(32)
        linhas = self._clip_lines(upgrade_desc(meta), self.small_font, text_w, 3)
        for line in linhas:
            surf = self.small_font.render(
                line, True, (205, 205, 215) if unlocked else (105, 105, 115)
            )
            surface.blit(surf, (text_x, desc_y))
            desc_y += surf.get_height() + self._s(2)

        # Rodapé: largura do card inteiro, dividido com os pips de tier à
        # direita. A linha ainda é truncada se não couber, mas com esta largura
        # praticamente todo upgrade exibe recarga E duração.
        stats_x = rect.x + self._s(12)
        stats_w = rect.right - stats_x - self._s(52)
        stats = self.tiny_font.render(
            self._fit_stats_line(meta, stats_w), True, (150, 175, 205)
        )
        surface.blit(stats, (stats_x, rect.bottom - self._s(17)))

        self._draw_tier_pips(surface, rect, meta)
        if equipped:
            # Selo no alto da coluna de texto: é onde a carta colecionável marca
            # edição/raridade, e aqui marca "está na nave" sem roubar linha de
            # descrição. Dentro do card, nunca sobre a borda — em cima da
            # moldura ele seria cortado pelo recorte do grid ao rolar.
            self._draw_pill(
                surface,
                (0, 0),
                t("upgrades.card.equipped"),
                CUSTOM_GOLD,
                (48, 40, 12, 235),
                midright=(rect.right - self._s(9), rect.y + self._s(17)),
            )
        if not unlocked:
            icon_s = self._s(18)
            icon = pygame.transform.scale(self.locked_icon, (icon_s, icon_s))
            surface.blit(
                icon,
                icon.get_rect(center=(rect.right - self._s(22), rect.y + self._s(18))),
            )
        if focused:
            self._draw_focus_ring(surface, rect, inside=True)

    @staticmethod
    def _clip_lines(
        text: str, font: pygame.font.Font, width: int, max_lines: int
    ) -> List[str]:
        """Quebra o texto e marca com "..." o que não coube.

        Sem a marca, uma descrição cortada termina numa palavra qualquer e lê
        como frase completa e sem sentido ("...corrói sozinho por alguns"). As
        reticências são ASCII de propósito (ver `_card_stats_line`).
        """
        if max_lines <= 0:
            return []
        lines = wrap_text(font, text, width)
        if len(lines) <= max_lines:
            return lines
        clipped = lines[:max_lines]
        last = clipped[-1]
        while last and font.size(last + "...")[0] > width:
            last = last[:-1]
        clipped[-1] = last.rstrip() + "..."
        return clipped

    @staticmethod
    def _card_stats_line_parts(meta: UpgradeMeta) -> List[str]:
        parts = [t("upgrades.card.cooldown", cd=f"{meta.base_cooldown:g}")]
        if meta.base_duration > 0:
            parts.append(t("upgrades.tip.duration", d=f"{meta.base_duration:g}"))
        if meta.base_charges is not None:
            parts.append(t("upgrades.tip.charges", n=meta.base_charges))
        return parts

    def _card_stats_line(self, meta: UpgradeMeta) -> str:
        # Separador por ESPAÇOS, não por bullet/ponto médio: a fonte pixelada
        # não cobre símbolo fora do ASCII em todo build (no web sai "?"), e
        # espaço nunca falha. Mesma escolha da linha de stats antiga.
        return "   ".join(self._card_stats_line_parts(meta))

    def _fit_stats_line(self, meta: UpgradeMeta, width: int) -> str:
        """Maior prefixo da linha de stats que cabe em ``width``.

        Descarta da direita para a esquerda, na ordem inversa da importância:
        cargas saem antes de duração, que sai antes da recarga. A recarga
        sozinha sempre cabe — é o número que decide se vale equipar."""
        partes = self._card_stats_line_parts(meta)
        while len(partes) > 1:
            linha = "   ".join(partes)
            if self.tiny_font.size(linha)[0] <= width:
                return linha
            partes.pop()
        return partes[0]

    def _draw_tier_pips(
        self, surface: pygame.Surface, rect: pygame.Rect, meta: UpgradeMeta
    ) -> None:
        """Tier de poder (1–3) em pips no canto inferior direito.

        É o que sobrou do peso: sem gate nenhum sobre o que cabe, só a
        informação de que este upgrade pesa mais na balança do jogo."""
        tier = max(1, min(3, meta.slot_weight))
        r = self._s(4)
        gap = self._s(11)
        cy = rect.bottom - self._s(14)
        x = rect.right - self._s(14) - r
        for i in range(3):
            filled = i < tier
            color = _category_color(meta) if filled else (60, 60, 70)
            pygame.draw.circle(surface, color, (x, cy), r, 0 if filled else 1)
            x -= gap

    # ------------------------------------------------------------------
    # Render — rodapé e animações
    # ------------------------------------------------------------------

    def _draw_stars(self, surface: pygame.Surface) -> None:
        """Saldo no topo direito: todo custo da tela (slot, nave) é em estrelas,
        então o saldo tem de estar no campo de visão de quem lê os custos.

        Alinhado pela DIREITA, não por um x fixo: o rótulo muda de largura com o
        número (1 vs 1000) e com o idioma, e um x fixo cortava o texto na borda.
        """
        label = self.item_font.render(
            t("upgrades.stars", n=self.player_profile.available_stars),
            True,
            CUSTOM_GOLD,
        )
        right = self.layout.right_panel.right
        y = self.layout.stars_y
        surface.blit(label, (right - label.get_width(), y + self._s(2)))
        icon = self.star_icon_small
        surface.blit(
            icon,
            (right - label.get_width() - self._s(6) - icon.get_width(), y),
        )

    def _draw_back_button(self, surface: pygame.Surface) -> None:
        draw_bordered_button(
            surface,
            self.layout.back_button,
            t("common.back"),
            self.item_font,
            CUSTOM_PURPLE,
            255,
            0,
        )
        if self.focus == ("back", 0):
            self._draw_focus_ring(surface, self.layout.back_button)

    def _draw_flights(self, surface: pygame.Surface) -> None:
        self.flights.draw(
            surface,
            lambda surf, pos, radius, meta, alpha: self._draw_medallion(
                surf, pos, radius, meta, alpha=alpha
            ),
        )

    def _draw_floating_messages(self, surface: pygame.Surface) -> None:
        for m in self.floating_messages:
            m.draw(surface)

    def _return_to_menu(self) -> None:
        # Persistência defensiva: garante o save antes de sair — a troca de
        # cena acontece dentro do fade, e nem todo caminho chama `exit()`.
        self.player_profile.save()
        # Desempilha (esta cena foi empilhada sobre o menu ou sobre o Game Over).
        self.app.go_back()
