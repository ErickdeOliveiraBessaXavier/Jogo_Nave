"""Mapeamento dos bumpers no cursor de upgrades da HUD.

LB volta, RB avança — a convenção do gênero. Estava trocado (LB andava +1),
e é o tipo de defeito que ninguém "conserta" lendo o código: só aparece com o
controle na mão, e some da memória assim que a mão se acostuma ao errado.

Varredura de fonte, no espírito de `test_conventions.py`: o handler depende de
uma cena de gameplay inteira para rodar, e o que precisa ser travado aqui é o
SINAL passado em cada botão.
"""

import ast
import re
from pathlib import Path

from game.core.gamepad import XboxButton

FONTE = (
    Path(__file__).resolve().parent.parent
    / "game"
    / "systems"
    / "gameplay_input_handler.py"
)


def _corpo(nome: str) -> str:
    texto = FONTE.read_text(encoding="utf-8")
    linhas = texto.split("\n")
    for no in ast.walk(ast.parse(texto)):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return "\n".join(linhas[no.lineno - 1 : no.end_lineno])
    raise AssertionError(f"{nome} não existe mais em {FONTE.name}")


def _delta_do_bumper(corpo: str, botao: str) -> str:
    """Sinal passado a `navigate_upgrade_select` no ramo daquele botão."""
    achado = re.search(
        rf"XboxButton\.{botao}:\s*(?:#[^\n]*\n\s*)*"
        r"(?:#[^\n]*\n\s*)*scene\.navigate_upgrade_select\(([+-]1)\)",
        corpo,
    )
    assert achado, f"o ramo de {botao} não chama navigate_upgrade_select"
    return achado.group(1)


def test_rb_avanca_e_lb_volta():
    corpo = _corpo("_handle_gamepad_button")
    assert _delta_do_bumper(corpo, "RB") == "+1", "RB tem de avançar"
    assert _delta_do_bumper(corpo, "LB") == "-1", "LB tem de voltar"


def test_lb_e_rb_continuam_sendo_os_bumpers():
    """Guarda o pressuposto do teste acima: LB=4 e RB=5 no layout Xbox."""
    assert (XboxButton.LB, XboxButton.RB) == (4, 5)
