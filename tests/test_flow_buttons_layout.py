"""`layout_flow_buttons`: fileira de botões responsiva (flex-wrap) por conteúdo.

Trava o contrato usado pelo modal de Instruções de Voo (e reutilizável): largura
UNIFORME dimensionada pelo maior rótulo, quebra em linhas quando não cabe, e
encolhe a fonte só em último caso — o texto nunca ultrapassa o botão. Roda
headless (fonte real via conftest).
"""

import pygame

from game.core.assets import get_font
from game.scenes.ui_helpers import layout_flow_buttons

# Estados possíveis de dois toggles, com um rótulo propositalmente longo.
_STATES = [
    ["Controle: Mouse", "Controle: Teclado"],
    ["Tiro automático: Ligado", "Tiro automático: Desligado"],
]


def _widest(font, states):
    return max(font.size(s)[0] for grp in states for s in grp)


def test_largura_uniforme_e_texto_nunca_transborda():
    rects, font, block_w, _block_h, _rows = layout_flow_buttons(
        _STATES, get_font, 17, avail_w=680, btn_h=40, gap_x=24, gap_y=14, pad_x=18
    )
    # Todos os botões têm a MESMA largura (proporcionais entre si).
    assert len({r.width for r in rects}) == 1
    # Nenhum rótulo possível ultrapassa a largura do seu botão.
    for grp, r in zip(_STATES, rects):
        for label in grp:
            assert font.size(label)[0] <= r.width
    # O bloco nunca é mais largo que o espaço disponível.
    assert block_w <= 680


def test_uma_linha_quando_cabe_varias_quando_nao():
    # Espaço largo: os dois botões numa linha só.
    _r, _f, _bw, _bh, rows_wide = layout_flow_buttons(
        _STATES, get_font, 17, avail_w=2000, btn_h=40, gap_x=24, gap_y=14, pad_x=18
    )
    assert rows_wide == 1
    # Espaço estreito: quebra para empilhar (2 linhas).
    _r2, _f2, _bw2, _bh2, rows_narrow = layout_flow_buttons(
        _STATES, get_font, 17, avail_w=500, btn_h=40, gap_x=24, gap_y=14, pad_x=18
    )
    assert rows_narrow == 2


def test_fonte_encolhe_quando_um_botao_sozinho_nao_cabe():
    # avail menor que o rótulo mais longo na fonte base → a fonte encolhe até o
    # botão (texto + padding) caber, garantindo que nada é cortado.
    base_font = get_font(17)
    long_w = _widest(base_font, _STATES)
    avail = long_w // 2  # força o encolhimento
    rects, font, block_w, _bh, _rows = layout_flow_buttons(
        _STATES, get_font, 17, avail_w=avail, btn_h=40, gap_x=24, gap_y=14, pad_x=6
    )
    assert font.get_height() < base_font.get_height()
    assert block_w <= avail
    for grp, r in zip(_STATES, rects):
        for label in grp:
            assert font.size(label)[0] <= r.width


def test_rects_relativos_ao_bloco_sem_sobreposicao():
    rects, _f, _bw, _bh, _rows = layout_flow_buttons(
        _STATES, get_font, 17, avail_w=680, btn_h=40, gap_x=24, gap_y=14, pad_x=18
    )
    # Origem no canto do bloco (nada com coordenada negativa).
    assert all(r.x >= 0 and r.y >= 0 for r in rects)
    # Botões não se sobrepõem entre si.
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not rects[i].colliderect(rects[j])


def test_lista_vazia_e_seguro():
    pygame.font.init()
    rects, _f, block_w, block_h, rows = layout_flow_buttons(
        [["único"]], get_font, 17, avail_w=680, btn_h=40, gap_x=24, gap_y=14, pad_x=18
    )
    assert len(rects) == 1 and rows == 1 and block_w > 0 and block_h == 40
