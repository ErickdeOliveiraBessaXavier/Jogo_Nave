"""Geometria da tela de Aprimoramentos, sem abrir janela.

Estes testes são o motivo de a geometria ter saído da cena: antes, "os ícones
cabem sem rolar em 576p?" só se respondia rodando o jogo e olhando. As
invariantes abaixo são as que quebram calado quando alguém mexe num número de
`_s()`:

- nada estoura o painel;
- o elenco inteiro cabe no grid **sem rolagem** (o ponto da referência do
  Hollow Knight — ver o docstring de `upgrades_layout`);
- o card de descrição não invade o grid;
- **toda nave exibe sua descrição inteira**, que é o problema que motivou tirar
  as barras de atributo do fluxo de texto.
"""

import pytest

from game.core.assets import get_font
from game.core.ship_types import all_ship_profiles, format_ship_description, ship_display_name
from game.core.upgrades import list_all_upgrades_meta, upgrade_desc
from game.scenes.ui_helpers import wrap_text
from game.scenes.upgrades_layout import (
    GRID_COLS,
    build_layout,
    case_size,
    cell_icon_rect,
    cell_medallion_radius,
    content_height,
    detail_card_height,
    detail_gutter_x,
    detail_showcase_rect,
    detail_text_rect,
    max_scroll,
    place_cells,
    scroll_to_reveal,
    slot_medallion_radius,
)

# 576p, 720p (o design base) e 1080p — as pontas que a convenção §12 manda
# validar. A 4ª resolução (5K) escala pelo mesmo fator e não acrescenta caso.
RESOLUCOES = [(1024, 576), (1280, 720), (1920, 1080)]
SLOTS = 3
ABAS = 5
LINHAS_DETALHE = 5  # espelha `UpgradesSelectionScene.DETAIL_LINES`
TOTAL_UPGRADES = len(list_all_upgrades_meta())


def escala(largura: int):
    """O `_s` da cena: pixel do design base -> resolução alvo."""
    fator = largura / 1280.0
    return lambda valor: int(valor * fator)


def montar(size):
    return build_layout(
        size,
        escala(size[0]),
        slot_count=SLOTS,
        tab_count=ABAS,
        detail_lines=LINHAS_DETALHE,
    )


@pytest.mark.parametrize("size", RESOLUCOES)
def test_nada_estoura_a_tela(size):
    sw, sh = size
    layout = montar(size)
    rects = [
        layout.left_panel,
        layout.right_panel,
        layout.back_button,
        layout.viewport,
        layout.detail_card,
        layout.ship_stats,
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
    assert layout.left_panel.contains(layout.ship_stats)
    for aba in layout.tabs:
        assert layout.right_panel.contains(aba)
    assert layout.right_panel.contains(layout.viewport)
    assert layout.right_panel.contains(layout.detail_card)
    # Slots e preview não podem se cruzar: o preview cresce por porcentagem da
    # altura e os slots são ancorados no rodapé — é o encontro dos dois que
    # estoura primeiro quando a coluna encolhe.
    assert layout.ship_preview.bottom <= layout.slots[0].top


@pytest.mark.parametrize("size", RESOLUCOES)
def test_bloco_de_atributos_nao_cobre_a_nave(size):
    """As barras foram para o canto justamente para não competir com a nave."""
    layout = montar(size)
    assert not layout.ship_stats.colliderect(layout.ship_preview)


@pytest.mark.parametrize("size", RESOLUCOES)
def test_grid_nao_invade_o_card_de_descricao(size):
    layout = montar(size)
    assert not layout.viewport.colliderect(layout.detail_card)
    assert layout.viewport.bottom <= layout.detail_card.top


@pytest.mark.parametrize("size", RESOLUCOES)
def test_elenco_inteiro_cabe_sem_rolagem(size):
    """23 upgrades em 3 linhas de 8 — sem rolar, que é metade do ponto."""
    layout = montar(size)
    assert max_scroll(layout, TOTAL_UPGRADES) == 0.0
    assert content_height(layout, TOTAL_UPGRADES) <= layout.viewport.height


@pytest.mark.parametrize("size", RESOLUCOES)
def test_rolagem_volta_a_existir_se_o_elenco_dobrar(size):
    """A rede de segurança continua armada para quando houver upgrades demais."""
    layout = montar(size)
    assert max_scroll(layout, TOTAL_UPGRADES * 2) > 0.0


@pytest.mark.parametrize("size", RESOLUCOES)
def test_celulas_ficam_na_janela_do_grid(size):
    layout = montar(size)
    place_cells(layout, list(range(TOTAL_UPGRADES)), 0.0, case_size(TOTAL_UPGRADES))
    for c in layout.cells:
        assert layout.viewport.contains(c), f"célula {c} fora da janela"


def test_estojo_fecha_as_linhas_com_vagas():
    """Filtrar troca ícones por vagas — o estojo não encolhe.

    Sem isso a aba "Defesa" (3 de 23) deixava dois terços do painel em branco e
    o filtro parecia ter quebrado a tela em vez de ter dado foco.
    """
    total = case_size(TOTAL_UPGRADES)
    assert total % GRID_COLS == 0, "o estojo sempre fecha em linhas cheias"
    assert total >= TOTAL_UPGRADES

    layout = montar((1280, 720))
    for n_itens in (TOTAL_UPGRADES, 11, 3, 1):
        place_cells(layout, list(range(n_itens)), 0.0, total)
        assert len(layout.cells) == n_itens
        assert len(layout.cells) + len(layout.sockets) == total
        # Vaga nenhuma pode cair em cima de um ícone.
        for vaga in layout.sockets:
            assert vaga not in layout.cells
            assert not any(vaga.colliderect(c) for c in layout.cells)


def test_vagas_nao_sao_navegaveis():
    """As vagas são decoração: entram em `sockets`, nunca em `cells`.

    Só `cells` alimenta o foco e o clique — uma vaga focável seria um alvo que
    não faz nada, e no controle isso trava a navegação num buraco."""
    layout = montar((1280, 720))
    place_cells(layout, list(range(3)), 0.0, case_size(TOTAL_UPGRADES))
    assert len(layout.cells) == 3
    assert len(layout.sockets) == case_size(TOTAL_UPGRADES) - 3


def test_place_cells_desloca_pela_rolagem():
    layout = montar((1280, 720))
    itens = list(range(40))
    place_cells(layout, itens, 0.0)
    topo = [c.y for c in layout.cells]
    place_cells(layout, itens, 50.0)
    assert [c.y for c in layout.cells] == [y - 50 for y in topo]


def test_scroll_to_reveal_mostra_a_celula_focada():
    layout = montar((1280, 720))
    limite = max_scroll(layout, 80)
    passo = layout.cell_h + layout.cell_gap
    visiveis = layout.viewport.height // passo

    assert scroll_to_reveal(layout, 0, 0.0, limite) == 0.0
    # Primeira célula da linha logo abaixo da última visível.
    fora = visiveis * GRID_COLS
    assert scroll_to_reveal(layout, fora, 0.0, limite) > 0.0
    assert scroll_to_reveal(layout, 0, float(passo), limite) == 0.0
    assert scroll_to_reveal(layout, 79, 0.0, limite) <= limite


@pytest.mark.parametrize("size", RESOLUCOES)
def test_medalhao_cabe_na_celula(size):
    """O raio do medalhão é o raio INICIAL do voo até o slot.

    Se ele não couber na célula, o desenho vaza; se divergir da conta usada no
    render, o medalhão dá um pulo de tamanho no primeiro frame da animação.
    """
    layout = montar(size)
    place_cells(layout, list(range(8)), 0.0)
    celula = layout.cells[0]
    s = escala(size[0])
    icone = cell_icon_rect(celula, s)
    raio = cell_medallion_radius(celula, s)

    assert celula.contains(icone)
    assert raio > 0
    assert raio * 2 <= icone.width


@pytest.mark.parametrize("size", RESOLUCOES)
def test_medalhao_do_slot_cabe_no_slot(size):
    layout = montar(size)
    raio = slot_medallion_radius(layout.slots[0])
    assert 0 < raio * 2 <= layout.slots[0].width


# ── orçamento de texto ──────────────────────────────────────────────────────


@pytest.mark.parametrize("size", RESOLUCOES)
def test_vitrine_e_texto_dividem_o_card_sem_se_cruzar(size):
    """Vitrine à esquerda, texto no meio, calha de rolagem à direita."""
    s = escala(size[0])
    layout = montar(size)
    card = layout.detail_card
    vitrine = detail_showcase_rect(card, s)
    texto = detail_text_rect(card, s)

    assert card.contains(vitrine)
    assert card.contains(texto)
    assert vitrine.width == vitrine.height, "a vitrine é quadrada"
    assert not vitrine.colliderect(texto)
    # A calha fica FORA da largura do texto — senão a barra de rolagem passa
    # por cima da última palavra de cada linha.
    assert texto.right <= detail_gutter_x(card, s) - s(4)
    assert texto.width > 0
    assert card.height == detail_card_height(s, LINHAS_DETALHE)


def test_existe_upgrade_que_rola_de_verdade():
    """A rolagem do texto não pode ser código morto.

    O card é dimensionado pelo caso TÍPICO (5 linhas) e não pelo pior; se um dia
    ninguém mais passar disso, as setas e a barra viram enfeite que nunca
    aparece — e aí o certo é remover o mecanismo, não mantê-lo por via das
    dúvidas.
    """
    s = escala(1280)
    layout = montar((1280, 720))
    fonte = get_font(12)
    largura = detail_text_rect(layout.detail_card, s).width

    contagens = {
        m.name: len(wrap_text(fonte, upgrade_desc(m), largura))
        for m in list_all_upgrades_meta()
    }
    rolaveis = {n: c for n, c in contagens.items() if c > LINHAS_DETALHE}
    assert rolaveis, "nenhum upgrade excede a janela — a rolagem virou enfeite"
    # E o pior caso não pode ser absurdo: muitas telas de rolagem seguidas
    # significam que a janela ficou pequena demais.
    assert max(contagens.values()) <= LINHAS_DETALHE * 3


@pytest.mark.parametrize("size", RESOLUCOES)
def test_toda_nave_cabe_no_bloco_de_texto(size):
    """Nenhuma nave pode ter a descrição cortada.

    Era o defeito que motivou tirar as barras de atributo do fluxo: com elas
    ali, a faixa de texto não comportava as descrições maiores e o jogador via
    a frase truncada no meio. Este teste é o que impede a regressão — se algum
    número de layout encolher a faixa, ele falha aqui, não na tela do jogador.
    """
    fator = size[0] / 1280.0
    s = escala(size[0])
    layout = montar(size)
    f_small = get_font(max(8, int(12 * fator)))
    f_tiny = get_font(max(8, int(10 * fator)))

    disponivel = layout.info_bottom - layout.info_top
    largura = layout.left_panel.width - s(40)

    # Altura fixa do cabeçalho do bloco: nome + pílula de estado + tags.
    fixo = (
        get_font(max(8, int(24 * fator))).get_height() + s(8)  # nome
        + f_tiny.get_height() + s(9) + s(8)  # pílula de estado
        + f_tiny.get_height() + s(6)  # tags
    )

    for ship in all_ship_profiles():
        linhas_desc = len(
            wrap_text(f_small, format_ship_description(ship, False), largura)
        )
        assert linhas_desc <= 4, (
            f"{ship_display_name(ship)} precisa de {linhas_desc} linhas de "
            "descrição e o bloco só desenha 4"
        )
        preciso = fixo + linhas_desc * (f_small.get_height() + s(3))
        assert preciso <= disponivel, (
            f"{ship_display_name(ship)} não cabe: precisa de {preciso}px e a "
            f"faixa tem {disponivel}px em {size[0]}x{size[1]}"
        )
