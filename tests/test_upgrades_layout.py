"""Geometria da tela de Aprimoramentos, sem abrir janela.

Estes testes são o motivo de a geometria ter saído da cena: antes, "os cards
cabem no painel em 576p?" só se respondia rodando o jogo e olhando. As
invariantes abaixo são as que quebram calado quando alguém mexe num número de
`_s()` — nada estoura o painel, o grid mostra sempre 2×4, e a rolagem para no
fim do conteúdo.
"""

import pytest

from game.scenes.upgrades_layout import (
    GRID_COLS,
    GRID_ROWS,
    build_layout,
    card_art_rect,
    card_medallion_radius,
    content_height,
    max_scroll,
    place_cards,
    scroll_to_reveal,
    slot_medallion_radius,
)

# 576p, 720p (o design base) e 1080p — as pontas que a convenção §12 manda
# validar. A 4ª resolução (5K) escala pelo mesmo fator e não acrescenta caso.
RESOLUCOES = [(1024, 576), (1280, 720), (1920, 1080)]
SLOTS = 3
ABAS = 5


def escala(largura: int):
    """O `_s` da cena: pixel do design base -> resolução alvo."""
    fator = largura / 1280.0
    return lambda valor: int(valor * fator)


def montar(size):
    return build_layout(size, escala(size[0]), slot_count=SLOTS, tab_count=ABAS)


@pytest.mark.parametrize("size", RESOLUCOES)
def test_nada_estoura_a_tela(size):
    sw, sh = size
    layout = montar(size)
    rects = [
        layout.left_panel,
        layout.right_panel,
        layout.back_button,
        layout.viewport,
        layout.scrollbar,
        *layout.slots,
        *layout.tabs,
    ]
    for r in rects:
        assert r.x >= 0 and r.y >= 0, f"{r} sai pela borda superior/esquerda"
        assert r.right <= sw and r.bottom <= sh, f"{r} sai pela borda inferior/direita"


@pytest.mark.parametrize("size", RESOLUCOES)
def test_paineis_nao_se_sobrepoem(size):
    layout = montar(size)
    assert not layout.left_panel.colliderect(layout.right_panel)


@pytest.mark.parametrize("size", RESOLUCOES)
def test_conteudo_fica_dentro_do_painel(size):
    layout = montar(size)
    for slot in layout.slots:
        assert layout.left_panel.contains(slot)
    for aba in layout.tabs:
        assert layout.right_panel.contains(aba)
    assert layout.right_panel.contains(layout.viewport)
    # Slots e preview não podem se cruzar: o preview cresce por porcentagem da
    # altura e os slots são ancorados no rodapé — é o encontro dos dois que
    # estoura primeiro quando a coluna encolhe.
    assert layout.ship_preview.bottom <= layout.slots[0].top


@pytest.mark.parametrize("size", RESOLUCOES)
def test_cabem_exatamente_duas_colunas_por_quatro_linhas(size):
    """O grid é 2×4 em QUALQUER resolução — é o que §12 exige."""
    layout = montar(size)
    largura_usada = (
        GRID_COLS * layout.card_w
        + (GRID_COLS - 1) * layout.card_gap
        + layout.scrollbar.width
    )
    assert largura_usada <= layout.viewport.width
    altura_usada = GRID_ROWS * layout.card_h + (GRID_ROWS - 1) * layout.card_gap
    assert altura_usada <= layout.viewport.height
    # E sobra pouco: se coubesse uma 5ª linha, o grid não seria 2×4.
    assert altura_usada + layout.card_h > layout.viewport.height


@pytest.mark.parametrize("size", RESOLUCOES)
def test_oito_cards_nao_rolam(size):
    """Com o grid cheio (8) e nem um a mais, não há o que rolar."""
    layout = montar(size)
    assert max_scroll(layout, GRID_COLS * GRID_ROWS) == 0.0
    assert max_scroll(layout, GRID_COLS * GRID_ROWS + 1) > 0.0


@pytest.mark.parametrize("size", RESOLUCOES)
def test_rolagem_maxima_para_no_fim_do_conteudo(size):
    layout = montar(size)
    limite = max_scroll(layout, 23)
    assert limite == content_height(layout, 23) - layout.viewport.height
    # Rolado ao máximo, o último card encosta na base da janela — nem sobra
    # espaço vazio embaixo, nem fica card cortado.
    itens = list(range(23))
    place_cards(layout, itens, limite)
    assert layout.cards[-1].bottom == pytest.approx(layout.viewport.bottom, abs=2)


def test_place_cards_desloca_pela_rolagem():
    layout = montar((1280, 720))
    itens = list(range(10))
    place_cards(layout, itens, 0.0)
    topo = [c.y for c in layout.cards]
    place_cards(layout, itens, 50.0)
    assert [c.y for c in layout.cards] == [y - 50 for y in topo]


def test_scroll_to_reveal_mostra_o_card_focado():
    layout = montar((1280, 720))
    limite = max_scroll(layout, 23)
    passo = layout.card_h + layout.card_gap

    # Card da 1ª linha com o grid no topo: nada a fazer.
    assert scroll_to_reveal(layout, 0, 0.0, limite) == 0.0
    # Card da 5ª linha (índice 8) exige rolar exatamente uma linha.
    assert scroll_to_reveal(layout, 8, 0.0, limite) == pytest.approx(passo)
    # Voltando para o topo, rola de volta para revelar o de cima.
    assert scroll_to_reveal(layout, 0, float(passo), limite) == 0.0
    # E nunca passa do fim do conteúdo.
    assert scroll_to_reveal(layout, 22, 0.0, limite) <= limite


@pytest.mark.parametrize("size", RESOLUCOES)
def test_medalhao_do_card_cabe_na_tarja_de_arte(size):
    """O raio do medalhão é o raio INICIAL do voo até o slot.

    Se ele não couber na tarja, o desenho vaza; se divergir da conta usada no
    render, o medalhão dá um pulo de tamanho no primeiro frame da animação —
    era exatamente essa a duplicação que motivou trazer as duas contas para cá.
    """
    layout = montar(size)
    place_cards(layout, list(range(8)), 0.0)
    card = layout.cards[0]
    s = escala(size[0])
    arte = card_art_rect(card, s)
    raio = card_medallion_radius(card, s)

    assert card.contains(arte)
    assert raio * 2 <= arte.width
    assert raio * 2 <= arte.height
    assert raio > 0


@pytest.mark.parametrize("size", RESOLUCOES)
def test_medalhao_do_slot_cabe_no_slot(size):
    layout = montar(size)
    raio = slot_medallion_radius(layout.slots[0])
    assert 0 < raio * 2 <= layout.slots[0].width
