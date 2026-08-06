"""upgrades_layout.py — geometria da tela de Aprimoramentos.

Extraído da `UpgradesSelectionScene` (§9). Aqui não se desenha nada: entram
tamanho de tela, `ui_scale`, quantidade de itens e rolagem; saem retângulos.

Isso é o que torna o layout **testável sem abrir janela** — as invariantes que
importam ("nada estoura o painel", "as 23 células cabem sem rolagem", "toda
nave exibe a descrição inteira") deixam de depender de inspeção visual (ver
`tests/test_upgrades_layout.py`).

A geometria interna da célula mora aqui inteira (`cell_medallion_radius`)
porque ela tinha DOIS donos: o render calculava o ícone e a animação de voo
repetia a conta para saber de onde o medalhão parte.

**Organização da coluna direita** (referência declarada: os amuletos de Hollow
Knight): grid de ÍCONES em cima, um card de descrição de altura FIXA embaixo. O
texto não se repete célula a célula — ele mora num lugar só e responde ao que
está selecionado. É o que permite a célula ser pequena, o grid inteiro caber
sem rolagem e a leitura ter um destino único.
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

# Colunas do grid de ícones. OITO porque é o que faz os 23 upgrades caberem em
# 3 linhas dentro da área disponível — ou seja, **sem rolagem nenhuma**, que era
# metade do ponto da referência do Hollow Knight. O número é fixo (não derivado
# da largura) para o grid ser idêntico em 576p, 720p e 1080p (§12).
GRID_COLS = 8


@dataclass
class UILayout:
    """Retângulos da tela. Reconstruído por `build_layout` / ao rolar."""

    left_panel: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    right_panel: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))

    # Esquerda — nave
    ship_preview: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    ship_prev: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    ship_next: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    # Bloco compacto de atributos no canto superior esquerdo, ao lado da nave.
    ship_stats: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    info_top: int = 0
    info_bottom: int = 0
    slots: List[pygame.Rect] = field(default_factory=lambda: [])
    slots_header_y: int = 0

    # Direita — grid de ícones + card de descrição
    tabs: List[pygame.Rect] = field(default_factory=lambda: [])
    # Janela recortada onde o grid vive. O que sai dela é cortado no render e
    # ignorado no clique — é o que sustenta a rolagem de segurança quando o
    # elenco crescer além do que cabe.
    viewport: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    scrollbar: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    # TODAS as células da aba atual, já com a rolagem aplicada (não só as
    # visíveis): o foco do controle precisa alcançar o que está fora da janela.
    cells: List[pygame.Rect] = field(default_factory=lambda: [])
    visible_upgrades: List["UpgradeMeta"] = field(default_factory=lambda: [])
    # Vagas do mostruário: as células que sobram depois dos itens da aba. São
    # decorativas (não recebem foco nem clique) — existem para o arsenal
    # parecer um estojo com lugares a preencher em vez de uma grade truncada.
    sockets: List[pygame.Rect] = field(default_factory=lambda: [])
    # Card de descrição do upgrade selecionado, altura fixa.
    detail_card: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))

    cell_w: int = 0
    cell_h: int = 0
    cell_gap: int = 0

    back_button: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    stars_y: int = 0


def build_layout(
    screen_size: Tuple[int, int],
    s: Scale,
    *,
    slot_count: int,
    tab_count: int,
    detail_lines: int,
) -> UILayout:
    """Monta a tela inteira, menos as células (que dependem da aba e da rolagem).

    ``detail_lines`` é quantas linhas de descrição o card de baixo reserva. Vem
    de fora porque é uma decisão de conteúdo (o pior upgrade do elenco), não de
    geometria — e é o que define a altura fixa do card.
    """
    sw, sh = screen_size
    layout = UILayout()

    margin, gap = s(18), s(12)
    panel_top = s(74)
    panel_h = sh - s(62) - panel_top
    total_w = sw - margin * 2 - gap
    # 40/60: o grid de ícones e o card de descrição precisam da largura maior
    # (o card é onde a descrição inteira tem de caber em poucas linhas), e a
    # nave compra destaque na ALTURA — preview grande e centralizado.
    left_w = int(total_w * 0.40)
    right_w = total_w - left_w

    layout.left_panel = pygame.Rect(margin, panel_top, left_w, panel_h)
    layout.right_panel = pygame.Rect(
        margin + left_w + gap, panel_top, right_w, panel_h
    )

    _layout_ship_column(layout, s, slot_count=slot_count)
    _layout_grid_column(layout, s, tab_count=tab_count, detail_lines=detail_lines)

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

    # A nave é o protagonista: o preview toma o que a coluna permitir, limitado
    # a 40% da altura do painel. Os 2% que saíram (era 42%) são o que garante
    # que a descrição MAIS LONGA do elenco caiba inteira embaixo — ver
    # `tests/test_upgrades_layout.py::test_toda_nave_cabe_no_bloco_de_texto`.
    chevron_w = s(28)
    preview_s = min(
        s(250), inner.width - chevron_w * 2 - s(16), int(inner.height * 0.40)
    )
    layout.ship_preview = pygame.Rect(
        inner.centerx - preview_s // 2, inner.y, preview_s, preview_s
    )
    ch_h = s(56)
    cy = layout.ship_preview.centery - ch_h // 2
    layout.ship_prev = pygame.Rect(inner.x, cy, chevron_w, ch_h)
    layout.ship_next = pygame.Rect(inner.right - chevron_w, cy, chevron_w, ch_h)

    # Atributos no canto superior esquerdo, encostados na nave: eram três barras
    # de largura cheia no meio da coluna e roubavam a atenção da descrição, que
    # é o texto que o jogador está tentando ler. Aqui viram anotação de canto —
    # a comparação continua disponível, sem competir.
    stats_w = min(s(104), (inner.width - preview_s) // 2 - s(4))
    layout.ship_stats = pygame.Rect(inner.x, inner.y + s(2), stats_w, s(60))

    # Bloco de texto: do fim do preview até o cabeçalho dos slots. Tudo (nome,
    # estado, tags, descrição, habilidades) vive nesta faixa.
    layout.info_top = layout.ship_preview.bottom + s(6)
    layout.info_bottom = layout.slots_header_y - s(6)


def _layout_grid_column(
    layout: UILayout, s: Scale, *, tab_count: int, detail_lines: int
) -> None:
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

    # Card de descrição ancorado no RODAPÉ, com altura fixa. Fixa é o ponto: o
    # card não pode crescer com o texto, senão o grid acima dança a cada
    # seleção e o jogador perde de vista a célula que estava mirando.
    detail_h = detail_card_height(s, detail_lines)
    layout.detail_card = pygame.Rect(
        inner.x, inner.bottom - detail_h, inner.width, detail_h
    )

    top = inner.y + tab_h + s(10)
    layout.viewport = pygame.Rect(
        inner.x, top, inner.width, layout.detail_card.top - s(10) - top
    )

    bar_w = s(5)
    layout.scrollbar = pygame.Rect(
        layout.viewport.right - bar_w,
        layout.viewport.y,
        bar_w,
        layout.viewport.height,
    )

    # Célula: largura reparte a janela em `GRID_COLS`; altura é a largura mais
    # uma linha para o nome curto embaixo do ícone. O nome existe porque hoje o
    # "ícone" é uma letra — quando a arte real entrar, ele pode sair sem mexer
    # em geometria nenhuma.
    layout.cell_gap = s(8)
    grid_w = layout.viewport.width - bar_w - s(4)
    layout.cell_w = (grid_w - layout.cell_gap * (GRID_COLS - 1)) // GRID_COLS
    layout.cell_h = layout.cell_w + s(14)


def detail_card_height(s: Scale, lines: int) -> int:
    """Altura do card de descrição para ``lines`` linhas de texto.

    Fonte única da conta: o layout reserva por ela e o render desenha por ela.
    """
    return s(16) + s(20) + s(14) + s(10) + lines * s(15) + s(18) + s(12)


def content_height(layout: UILayout, item_count: int) -> int:
    """Altura total do grid de ``item_count`` células, com os vãos."""
    if item_count <= 0:
        return 0
    rows = math.ceil(item_count / GRID_COLS)
    return rows * layout.cell_h + (rows - 1) * layout.cell_gap


def max_scroll(layout: UILayout, item_count: int) -> float:
    """Quanto dá para rolar. Zero quando o grid inteiro cabe na janela.

    Com o elenco atual (23) é sempre zero — a rolagem é rede de segurança para
    quando o número de upgrades crescer, não parte do fluxo normal.
    """
    return max(0.0, float(content_height(layout, item_count) - layout.viewport.height))


def case_size(total_upgrades: int) -> int:
    """Quantas vagas o mostruário mostra — sempre linhas cheias.

    Constante entre abas de propósito: filtrar reduz os ÍCONES, não o estojo.
    Sem isso, a aba "Defesa" (3 itens) deixava dois terços do painel em branco e
    o filtro parecia ter quebrado a tela em vez de ter dado foco.
    """
    if total_upgrades <= 0:
        return 0
    return math.ceil(total_upgrades / GRID_COLS) * GRID_COLS


def place_cells(
    layout: UILayout,
    items: Sequence["UpgradeMeta"],
    scroll_y: float,
    total_slots: int = 0,
) -> None:
    """Escreve em ``layout`` as células da aba, já deslocadas pela rolagem.

    ``total_slots`` (de `case_size`) estende o grid com VAGAS decorativas até
    fechar as linhas. As vagas entram em `sockets`, nunca em `cells` — só
    `cells` é navegável e clicável.
    """
    vp = layout.viewport
    step_x = layout.cell_w + layout.cell_gap
    step_y = layout.cell_h + layout.cell_gap
    offset = int(scroll_y)

    def rect_em(i: int) -> pygame.Rect:
        return pygame.Rect(
            vp.x + (i % GRID_COLS) * step_x,
            vp.y + (i // GRID_COLS) * step_y - offset,
            layout.cell_w,
            layout.cell_h,
        )

    layout.visible_upgrades = list(items)
    layout.cells = [rect_em(i) for i in range(len(items))]
    layout.sockets = [rect_em(i) for i in range(len(items), max(total_slots, len(items)))]


def scroll_to_reveal(layout: UILayout, index: int, scroll: float, limit: float) -> float:
    """Rolagem mínima para a célula ``index`` caber inteira na janela.

    É o que liga a navegação por controle à rolagem: o foco anda pelo grid
    inteiro (inclusive o que está fora da janela) e a janela o persegue.
    """
    row = index // GRID_COLS
    top = row * (layout.cell_h + layout.cell_gap)
    bottom = top + layout.cell_h
    if top < scroll:
        scroll = float(top)
    elif bottom > scroll + layout.viewport.height:
        scroll = float(bottom - layout.viewport.height)
    return max(0.0, min(limit, scroll))


# ---------------------------------------------------------------------------
# Geometria interna da célula — dono único das medidas que o render e a
# animação de voo precisam concordar.
# ---------------------------------------------------------------------------

def detail_showcase_rect(card: pygame.Rect, s: Scale) -> pygame.Rect:
    """Vitrine: o quadrado à esquerda do card onde o upgrade é exibido grande.

    150px no design base. A vitrine come largura da coluna de texto ao lado, e
    antes esse era o limite duro do tamanho dela — o card tinha de comportar o
    texto mais longo do elenco INTEIRO, então 140px já estouravam a altura
    disponível. Com a coluna de texto rolável (`detail_scroll`), a altura deixou
    de ser ditada pelo pior caso: o que não cabe rola, e a vitrine pôde crescer.
    """
    pad = s(14)
    lado = min(s(150), card.height - pad * 2)
    return pygame.Rect(card.x + pad, card.centery - lado // 2, lado, lado)


def detail_gutter_x(card: pygame.Rect, s: Scale) -> int:
    """Eixo da calha à direita do texto: setas e barra de posição moram aqui."""
    return card.right - s(14) - s(6)


def detail_text_rect(card: pygame.Rect, s: Scale) -> pygame.Rect:
    """Coluna de texto do card: entre a vitrine e a calha de rolagem.

    A calha é descontada SEMPRE, mesmo quando o texto cabe inteiro e nenhuma
    seta aparece. Descontar só quando rola seria circular — é a largura que
    determina a quebra de linha, que determina se rola.
    """
    vitrine = detail_showcase_rect(card, s)
    x = vitrine.right + s(14)
    largura = detail_gutter_x(card, s) - s(8) - x
    return pygame.Rect(x, card.y + s(12), largura, card.height - s(24))


def cell_icon_rect(rect: pygame.Rect, s: Scale) -> pygame.Rect:
    """Quadrado do ícone dentro da célula (o nome curto fica abaixo dele)."""
    lado = rect.width - s(10)
    return pygame.Rect(rect.x + s(5), rect.y + s(4), lado, lado)


def cell_medallion_radius(rect: pygame.Rect, s: Scale) -> int:
    """Raio do medalhão dentro da célula.

    Também é o raio INICIAL do voo até o slot: um valor diferente daqui faria o
    medalhão dar um pulo de tamanho no primeiro frame da animação.
    """
    return int(cell_icon_rect(rect, s).width * 0.46)


def slot_medallion_radius(rect: pygame.Rect) -> int:
    """Raio do medalhão dentro de um slot — o raio FINAL do voo."""
    return int(rect.width * 0.32)
