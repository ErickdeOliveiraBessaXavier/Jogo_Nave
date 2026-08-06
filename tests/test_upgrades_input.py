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
