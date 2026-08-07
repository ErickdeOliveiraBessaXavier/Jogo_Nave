"""Convenções de entrada da tela de Aprimoramentos.

Varredura de código-fonte, no espírito de `test_conventions.py`: o que está
travado aqui é uma decisão de UX que não aparece em nenhuma asserção de lógica
pura e que uma edição distraída desfaz sem quebrar teste nenhum.

**Um eixo, um destino.** O analógico ESQUERDO move o foco no grid; o DIREITO
rola a descrição. Antes os dois moviam o foco — sobrou gesto para o texto
justamente porque o direito foi cedido. Se alguém devolver o RS à navegação, o
jogador de controle perde o único jeito de ler uma descrição longa.
"""

import ast
import re
from pathlib import Path

FONTE = Path(__file__).resolve().parent.parent / "game" / "scenes" / "upgrades_selection.py"


def corpo_do_metodo(nome: str, classe: str = "UpgradesSelectionScene") -> str:
    """Corpo de um método da CENA.

    Escopado à classe de propósito: `ast.walk` sem filtro devolvia o primeiro
    `update` do arquivo, que é o da `FloatingMessage` — o teste passava a medir
    outra coisa sem reclamar.
    """
    texto = FONTE.read_text(encoding="utf-8")
    linhas = texto.split("\n")
    for no in ast.parse(texto).body:
        if isinstance(no, ast.ClassDef) and no.name == classe:
            for m in no.body:
                if isinstance(m, ast.FunctionDef) and m.name == nome:
                    return "\n".join(linhas[m.lineno - 1 : m.end_lineno])
            raise AssertionError(f"{classe}.{nome} não existe mais")
    raise AssertionError(f"classe {classe} não existe mais em {FONTE.name}")


def test_navegacao_do_foco_usa_so_o_analogico_esquerdo():
    corpo = corpo_do_metodo("_poll_stick_nav")
    lados = set(re.findall(r'get_stick\(\s*"(\w+)"', corpo))
    assert lados == {"left"}, (
        f"a navegação do foco leu {sorted(lados)}; o analógico direito é da "
        "rolagem da descrição (ver _poll_detail_stick)"
    )


def test_rolagem_da_descricao_usa_so_o_analogico_direito():
    corpo = corpo_do_metodo("_poll_detail_stick")
    lados = set(re.findall(r'get_stick\(\s*"(\w+)"', corpo))
    assert lados == {"right"}, (
        f"a rolagem do texto leu {sorted(lados)}; o esquerdo é da navegação"
    )


def test_os_dois_pollings_rodam_no_update():
    """Um sem o outro deixa metade do controle morta."""
    corpo = corpo_do_metodo("update")
    assert "_poll_stick_nav" in corpo
    assert "_poll_detail_stick" in corpo


def test_a_seta_de_rolagem_e_desenhada_e_nao_escrita():
    """Caractere de seta viraria "?" na fonte pixelada (ver a memória
    `ascii-only-em-texto-renderizado`). O indicador tem de ser polígono."""
    corpo = corpo_do_metodo("_draw_scroll_arrow")
    assert "draw.polygon" in corpo
    # `render` é o que transforma string em pixel: sem ele, não há caractere
    # nenhum sendo desenhado aqui — só geometria.
    assert ".render(" not in corpo, "o indicador não pode ser texto"


def test_trocar_de_upgrade_volta_o_texto_ao_inicio():
    """Começar a ler a descrição nova pelo meio seria um defeito silencioso."""
    corpo = corpo_do_metodo("_set_detail")
    assert "detail_scroll = 0" in corpo


# ── roda do mouse ───────────────────────────────────────────────────────────


def test_a_roda_do_mouse_e_lida_como_mousewheel():
    """Botão 4/5 é da era do pygame 1 — o SDL2 não emite mais.

    Era exatamente por isso que a roda não rolava NADA nesta tela enquanto o
    analógico direito rolava: o `handle_event` esperava um evento que nunca
    chegava. Quem trocar de volta reintroduz o bug sem quebrar mais nada.
    """
    corpo = corpo_do_metodo("handle_event")
    assert "MOUSEWHEEL" in corpo, "a roda tem de ser lida como MOUSEWHEEL"
    assert not re.search(r"button in \(4, 5\)", corpo), (
        "botão 4/5 do mouse não existe no pygame 2; a roda é MOUSEWHEEL"
    )


def test_roda_teclado_e_setas_passam_pelo_mesmo_roteador():
    """Um único caminho para os três dispositivos.

    A regra "sobre o card rola o texto, fora dele rola o grid" tem de existir em
    UM lugar; duplicada, o mouse e o teclado divergem no primeiro ajuste.
    """
    corpo = corpo_do_metodo("handle_event")
    assert corpo.count("_scroll_request(") >= 2, (
        "roda e teclado deveriam chamar o mesmo roteador de rolagem"
    )


def test_as_setas_do_card_sao_clicaveis():
    """A seta é botão: o clique é testado no MOUSEBUTTONDOWN.

    Enquanto ela era só desenho, o jogador de mouse via um indicador que não
    respondia — a queixa que originou este teste.
    """
    corpo = corpo_do_metodo("handle_event")
    assert "_detail_arrow_at(" in corpo
    assert "_press_detail_arrow(" in corpo


def test_desenho_e_clique_da_seta_usam_a_mesma_geometria():
    """Desenhar num lugar e testar o clique noutro é o defeito de origem."""
    assert "detail_arrow_rects(" in corpo_do_metodo("_draw_detail_text")
    assert "detail_arrow_rects(" in corpo_do_metodo("_detail_arrow_at")


def test_a_repeticao_da_seta_roda_no_update():
    """Segurar a seta precisa repetir — e no update, nunca no render (§3)."""
    assert "_poll_detail_arrow" in corpo_do_metodo("update")
    corpo = corpo_do_metodo("_poll_detail_arrow")
    assert "NAV_REPEAT_RATE" in corpo, (
        "a repetição do mouse tem de usar a cadência do analógico"
    )


# ── destaque de foco ────────────────────────────────────────────────────────


def test_nenhum_anel_de_foco_desenhado_por_cima():
    """Foco muda a BORDA do elemento; não desenha uma segunda moldura.

    O anel externo (`_draw_focus_ring`) era exclusivo desta tela: dava borda
    dupla e usava um ciano que não existe em mais lugar nenhum da interface.
    Hoje o caminho é `interactive_border_color`, o mesmo do hover dos botões.
    """
    texto = FONTE.read_text(encoding="utf-8")
    assert "_draw_focus_ring" not in texto.replace(
        "# `_draw_focus_ring` foi REMOVIDO.", ""
    ), "voltou a existir um anel de foco desenhado por cima do componente"
    assert "interactive_border_color" in texto


def test_o_destaque_de_foco_vem_do_helper_compartilhado():
    """Uma cor de destaque para a interface inteira, num arquivo só."""
    ui_helpers = (FONTE.parent / "ui_helpers.py").read_text(encoding="utf-8")
    assert "FOCUS_HIGHLIGHT" in ui_helpers
    assert "def interactive_border_color(" in ui_helpers
    # O botão padrão do jogo aceita foco explícito: sem isso, telas que navegam
    # por foco próprio (sem cursor virtual) não teriam como destacá-lo.
    assert re.search(r"def draw_bordered_button\([^)]*focused", ui_helpers, re.S)
