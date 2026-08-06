"""upgrades_layout.py — geometria da tela de Aprimoramentos.

Extraído da `UpgradesSelectionScene` (§9). Aqui não se desenha nada: entram
tamanho de tela, `ui_scale`, quantidade de itens e rolagem; saem retângulos.

Isso é o que torna o layout **testável sem abrir janela** — as invariantes que
importam ("nada estoura o painel", "cabem exatamente 4 linhas de cards em
qualquer resolução", "a rolagem para no fim do conteúdo") deixam de depender de
inspeção visual (ver `tests/test_upgrades_layout.py`).

A geometria do card mora aqui inteira (`card_art_rect`, `card_medallion_radius`)
porque ela tinha DOIS donos: `_draw_card` calculava a tarja de arte e o
`_card_medallion_radius` repetia a conta para saber de onde o voo parte. Duas
cópias da mesma fórmula que precisavam concordar — e não havia nada além de um
comentário garantindo isso.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Sequence, Tuple

import pygame

if TYPE_CHECKING:
    from ..core.upgrades import UpgradeMeta

# `_s` da cena: converte pixel do design base (1280×720) para a resolução atual.
Scale = Callable[[float], int]

# Cards visíveis de uma vez. As duas contas do grid saem daqui e da janela —
# nunca de uma altura fixa de card —, e é isso que mantém o grid idêntico em
# 576p, 720p e 1080p (§12).
GRID_COLS = 2
GRID_ROWS = 4


@dataclass
class UILayout:
    """Retângulos da tela. Reconstruído por `build_layout` / ao rolar."""

    left_panel: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    right_panel: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))

    # Esquerda — nave
    ship_preview: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    ship_prev: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    ship_next: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    info_top: int = 0
    slots: List[pygame.Rect] = field(default_factory=lambda: [])
    slots_header_y: int = 0

    # Direita — grid de cards
    tabs: List[pygame.Rect] = field(default_factory=lambda: [])
    # Janela recortada onde o grid vive. O que sai dela é cortado no render e
    # ignorado no clique — é o que torna a rolagem possível sem os cards
    # invadirem as abas.
    viewport: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    scrollbar: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    # TODOS os cards da aba atual, já com a rolagem aplicada (não só os
    # visíveis): o foco do controle precisa alcançar o que está fora da janela
    # para poder rolar até lá.
    cards: List[pygame.Rect] = field(default_factory=lambda: [])
    visible_upgrades: List["UpgradeMeta"] = field(default_factory=lambda: [])

    card_w: int = 0
    card_h: int = 0
    card_gap: int = 0

    back_button: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    stars_y: int = 0


def build_layout(
    screen_size: Tuple[int, int],
    s: Scale,
    *,
    slot_count: int,
    tab_count: int,
) -> UILayout:
    """Monta a tela inteira, menos os cards (que dependem da aba e da rolagem)."""
    sw, sh = screen_size
    layout = UILayout()

    margin, gap = s(18), s(12)
    panel_top = s(74)
    panel_h = sh - s(62) - panel_top
    total_w = sw - margin * 2 - gap
    # 40/60: o grid de duas colunas precisa da largura maior (dois cards
    # legíveis lado a lado), e a nave compra destaque na ALTURA — preview
    # grande e centralizado — em vez de na largura. Trocar para 44/56 daria
    # cards estreitos demais para o nome e a descrição conviverem.
    left_w = int(total_w * 0.40)
    right_w = total_w - left_w

    layout.left_panel = pygame.Rect(margin, panel_top, left_w, panel_h)
    layout.right_panel = pygame.Rect(
        margin + left_w + gap, panel_top, right_w, panel_h
    )

    _layout_ship_column(layout, s, slot_count=slot_count)
    _layout_grid_column(layout, s, tab_count=tab_count)

    layout.back_button = pygame.Rect(margin, sh - s(52), s(150), s(38))
    layout.stars_y = s(30)
    return layout


def _layout_ship_column(layout: UILayout, s: Scale, *, slot_count: int) -> None:
    panel = layout.left_panel
    pad = s(16)
    inner = panel.inflate(-pad * 2, -pad * 2)

    # Slots ancorados no RODAPÉ do painel: o bloco de texto acima cresce e
    # encolhe conforme a nave, e os slots não podem dançar junto — eles são
    # o alvo do voo e precisam de posição estável.
    slot_gap = s(12)
    slot_size = min(
        s(84), (inner.width - slot_gap * (slot_count - 1)) // slot_count
    )
    slots_w = slot_size * slot_count + slot_gap * (slot_count - 1)
    slots_x = inner.centerx - slots_w // 2
    slots_y = inner.bottom - slot_size
    layout.slots = [
        pygame.Rect(
            slots_x + i * (slot_size + slot_gap), slots_y, slot_size, slot_size
        )
        for i in range(slot_count)
    ]
    layout.slots_header_y = slots_y - s(22)

    # A nave é o protagonista da tela: o preview toma o que a coluna permitir,
    # limitado por 42% da altura do painel para o bloco de texto + slots ainda
    # caber embaixo (o texto tem guarda de espaço própria e encolhe sozinho; o
    # preview, não).
    chevron_w = s(28)
    preview_s = min(
        s(250), inner.width - chevron_w * 2 - s(16), int(inner.height * 0.42)
    )
    layout.ship_preview = pygame.Rect(
        inner.centerx - preview_s // 2, inner.y, preview_s, preview_s
    )
    ch_h = s(56)
    cy = layout.ship_preview.centery - ch_h // 2
    layout.ship_prev = pygame.Rect(inner.x, cy, chevron_w, ch_h)
    layout.ship_next = pygame.Rect(inner.right - chevron_w, cy, chevron_w, ch_h)
    layout.info_top = layout.ship_preview.bottom + s(8)


def _layout_grid_column(layout: UILayout, s: Scale, *, tab_count: int) -> None:
    panel = layout.right_panel
    pad = s(14)
    inner = panel.inflate(-pad * 2, -pad * 2)

    # Abas: largura uniforme repartindo a linha inteira. Uniforme e não por
    # conteúdo porque a fileira é um seletor — aba que muda de tamanho com o
    # idioma faz o alvo do clique dançar entre traduções.
    tab_h = s(28)
    tab_gap = s(6)
    tab_w = (inner.width - tab_gap * (tab_count - 1)) // tab_count
    layout.tabs = [
        pygame.Rect(inner.x + i * (tab_w + tab_gap), inner.y, tab_w, tab_h)
        for i in range(tab_count)
    ]

    top = inner.y + tab_h + s(10)
    layout.viewport = pygame.Rect(inner.x, top, inner.width, inner.bottom - top)

    bar_w = s(5)
    layout.scrollbar = pygame.Rect(
        layout.viewport.right - bar_w,
        layout.viewport.y,
        bar_w,
        layout.viewport.height,
    )

    layout.card_gap = s(10)
    grid_w = layout.viewport.width - bar_w - s(6)
    layout.card_w = (grid_w - layout.card_gap * (GRID_COLS - 1)) // GRID_COLS
    layout.card_h = (
        layout.viewport.height - layout.card_gap * (GRID_ROWS - 1)
    ) // GRID_ROWS


def content_height(layout: UILayout, item_count: int) -> int:
    """Altura total do grid de ``item_count`` itens, com os vãos entre linhas."""
    if item_count <= 0:
        return 0
    rows = math.ceil(item_count / GRID_COLS)
    return rows * layout.card_h + (rows - 1) * layout.card_gap


def max_scroll(layout: UILayout, item_count: int) -> float:
    """Quanto dá para rolar. Zero quando o conteúdo cabe inteiro na janela."""
    return max(0.0, float(content_height(layout, item_count) - layout.viewport.height))


def place_cards(
    layout: UILayout, items: Sequence["UpgradeMeta"], scroll_y: float
) -> None:
    """Escreve em ``layout`` os cards da aba, já deslocados pela rolagem."""
    vp = layout.viewport
    step_x = layout.card_w + layout.card_gap
    step_y = layout.card_h + layout.card_gap
    offset = int(scroll_y)
    layout.visible_upgrades = list(items)
    layout.cards = [
        pygame.Rect(
            vp.x + (i % GRID_COLS) * step_x,
            vp.y + (i // GRID_COLS) * step_y - offset,
            layout.card_w,
            layout.card_h,
        )
        for i in range(len(items))
    ]


def scroll_to_reveal(layout: UILayout, index: int, scroll: float, limit: float) -> float:
    """Rolagem mínima para o card ``index`` caber inteiro na janela.

    É o que liga a navegação por controle à rolagem: o foco anda pelo grid
    inteiro (inclusive o que está fora da janela) e a janela o persegue, em vez
    de existir um comando separado de rolar.
    """
    row = index // GRID_COLS
    top = row * (layout.card_h + layout.card_gap)
    bottom = top + layout.card_h
    if top < scroll:
        scroll = float(top)
    elif bottom > scroll + layout.viewport.height:
        scroll = float(bottom - layout.viewport.height)
    return max(0.0, min(limit, scroll))


# ---------------------------------------------------------------------------
# Geometria interna do card — dono único das medidas que o render e a animação
# de voo precisam concordar.
# ---------------------------------------------------------------------------

def card_footer_height(s: Scale) -> int:
    """Faixa inferior da carta, de largura cheia, onde a linha de stats cabe."""
    return s(20)


def card_art_rect(rect: pygame.Rect, s: Scale) -> pygame.Rect:
    """Tarja de arte da carta: faixa vertical à esquerda com o medalhão.

    Para acima do rodapé em vez de ir até a base — é o rodapé de largura cheia
    que dá espaço para "Recarga" e "Duração" caberem na mesma linha.
    """
    art_w = min(s(72), rect.width // 3)
    return pygame.Rect(
        rect.x + s(5),
        rect.y + s(5),
        art_w,
        rect.height - s(10) - card_footer_height(s),
    )


def card_medallion_radius(rect: pygame.Rect, s: Scale) -> int:
    """Raio do medalhão dentro da tarja de arte.

    Também é o raio INICIAL do voo até o slot: um valor diferente daqui faria o
    medalhão dar um pulo de tamanho no primeiro frame da animação.
    """
    return min(int(card_art_rect(rect, s).width * 0.42), int(rect.height * 0.30))


def slot_medallion_radius(rect: pygame.Rect) -> int:
    """Raio do medalhão dentro de um slot — o raio FINAL do voo."""
    return int(rect.width * 0.32)
