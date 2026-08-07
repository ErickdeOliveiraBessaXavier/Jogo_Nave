"""Exclusão mútua entre o Modo Controle Xbox e o Controle por Mouse.

Existe por um defeito de gameplay, não de tela: ligar o controle deixava o
`mouse_control` ligado, e como o analógico só vence enquanto está inclinado
(ver `ShipMovement._move_impl`), soltar o stick devolvia a nave para debaixo do
ponteiro parado. A nave "escapava" sozinha, sem nada na tela explicando.

A regra mora no `UserPreferences` de propósito: são três caminhos que ligam o
controle (Configurações, modal de controles e o auto-ligar do hot-plug) e a
exclusão precisa valer nos três.
"""

import ast
from pathlib import Path

from game.core.preferences import UserPreferences

RAIZ = Path(__file__).resolve().parent.parent


def _prefs(tmp_path) -> UserPreferences:
    return UserPreferences(tmp_path / "prefs.json")


def test_ligar_o_controle_desliga_o_mouse(tmp_path):
    prefs = _prefs(tmp_path)
    prefs.mouse_control = True
    prefs.set_gamepad_enabled(True)
    assert prefs.gamepad_enabled
    assert not prefs.mouse_control


def test_desligar_o_controle_nao_religa_o_mouse_sozinho(tmp_path):
    """Religar por conta própria seria devolver uma escolha que o jogador não fez."""
    prefs = _prefs(tmp_path)
    prefs.mouse_control = True
    prefs.set_gamepad_enabled(True)
    prefs.set_gamepad_enabled(False)
    assert not prefs.mouse_control
    assert not prefs.gamepad_enabled


def test_o_toggle_do_mouse_fica_travado_com_o_controle_ligado(tmp_path):
    prefs = _prefs(tmp_path)
    assert not prefs.mouse_control_locked
    prefs.set_gamepad_enabled(True)
    assert prefs.mouse_control_locked


def test_perfil_antigo_com_os_dois_ligados_e_corrigido_na_carga(tmp_path):
    """Quem já tinha o JSON salvo com os dois marcados entra no jogo consertado."""
    caminho = tmp_path / "prefs.json"
    caminho.write_text(
        '{"mouse_control": true, "gamepad_enabled": true}', encoding="utf-8"
    )
    prefs = UserPreferences(caminho)
    assert prefs.gamepad_enabled
    assert not prefs.mouse_control


def test_nenhum_caminho_atribui_gamepad_enabled_direto():
    """Varredura: quem liga o controle usa o setter, senão a regra fica local.

    Atribuição crua sobrevive a lint e a teste — só reaparece como o mesmo bug
    de gameplay, num caminho diferente (foi assim no auto-ligar do hot-plug).
    """
    permitido = {
        # O próprio dono da regra e o carregador do JSON.
        RAIZ / "game" / "core" / "preferences.py",
    }
    infratores = []
    for arquivo in (RAIZ / "game").rglob("*.py"):
        if arquivo in permitido:
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Assign):
                continue
            for alvo in no.targets:
                if isinstance(alvo, ast.Attribute) and alvo.attr == "gamepad_enabled":
                    infratores.append(f"{arquivo.relative_to(RAIZ)}:{no.lineno}")
    assert not infratores, (
        "use `preferences.set_gamepad_enabled(...)`; atribuição direta pula a "
        f"exclusão com o mouse em: {infratores}"
    )
