"""Quem manda no ponteiro do mouse: o MODO de navegação, e mais ninguém.

Duas regressões visíveis com o mesmo sintoma — "o ícone do mouse aparece no
meio da navegação por controle":

1. Uma tela que reposiciona a mira por causa de um input discreto (LB/RB na
   seleção de dificuldade, setas na seleção de idioma) chamava
   `pygame.mouse.set_pos`. O SDL responde com um `MOUSEMOTION` idêntico ao de
   um movimento humano, e o app o lia como "o usuário pegou no mouse".
2. Cenas forçavam `pygame.mouse.set_visible(True)` no `enter()`. Como
   `_set_cursor_mode` só toca no ponteiro quando o modo MUDA, o estado real
   passava a contradizer o modo — e apertar LB de novo não escondia nada,
   porque para o app nada havia mudado.

Os métodos do `GameApp` são exercitados ligados a um objeto mínimo: instanciar
o app de verdade abriria janela, áudio e perfil, e nada disso importa aqui.
"""

import pygame

from game.app import GameApp
from game.core.gamepad import XboxButton


class _Cena:
    is_gameplay_scene = False


class _CenaGameplay:
    is_gameplay_scene = True


class _Stack:
    def __init__(self, cena=None):
        self._cena = cena

    def current(self):
        return self._cena


class _AppFalso:
    """Só o estado que os métodos abaixo tocam."""

    # Métodos reais do app, ligados a este stub.
    warp_cursor = GameApp.warp_cursor
    _consume_warp_motion = GameApp._consume_warp_motion
    _track_input_mode = GameApp._track_input_mode
    _set_cursor_mode = GameApp._set_cursor_mode
    _scene_is_gameplay = GameApp._scene_is_gameplay
    _sync_cursor_visibility = GameApp._sync_cursor_visibility

    def __init__(self, cena=None):
        self._cursor_navigation_mode = "cursor"
        self._warp_targets = []
        self.states = _Stack(cena if cena is not None else _Cena())


def _motion(pos):
    return pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": pos, "rel": (5, 5), "buttons": (0, 0, 0)}
    )


def _botao(b):
    return pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": b})


# ── warp: o eco do próprio jogo não conta como uso do mouse ─────────────────


def test_eco_do_warp_nao_reativa_o_cursor():
    app = _AppFalso()
    app._track_input_mode(_botao(XboxButton.RB))
    assert app._cursor_navigation_mode == "focus"

    app.warp_cursor((100, 120))
    app._track_input_mode(_motion((100, 120)))
    assert app._cursor_navigation_mode == "focus", (
        "o MOUSEMOTION gerado pelo próprio jogo tirou o modo de foco"
    )


def test_movimento_real_do_mouse_reativa_o_cursor():
    """O outro lado da regra: mexer no mouse de verdade continua valendo."""
    app = _AppFalso()
    app._track_input_mode(_botao(XboxButton.LB))
    app.warp_cursor((100, 120))
    app._track_input_mode(_motion((640, 400)))
    assert app._cursor_navigation_mode == "cursor"


def test_warps_seguidos_sao_todos_absorvidos():
    """LB/RB repetidos: cada eco casa com o seu destino."""
    app = _AppFalso()
    app._track_input_mode(_botao(XboxButton.RB))
    app.warp_cursor((10, 10))
    app.warp_cursor((20, 20))
    app._track_input_mode(_motion((10, 10)))
    app._track_input_mode(_motion((20, 20)))
    assert app._cursor_navigation_mode == "focus"


def test_o_eco_so_vale_uma_vez():
    """Consumido o destino, um segundo motion na mesma posição é do usuário."""
    app = _AppFalso()
    app._track_input_mode(_botao(XboxButton.RB))
    app.warp_cursor((10, 10))
    app._track_input_mode(_motion((10, 10)))
    app._track_input_mode(_motion((10, 10)))
    assert app._cursor_navigation_mode == "cursor"


# ── visibilidade reaplicada na troca de cena ────────────────────────────────


def test_troca_de_cena_reaplica_o_modo_no_ponteiro():
    """Cena nova não herda um ponteiro que contradiz o modo."""
    app = _AppFalso()
    app._track_input_mode(_botao(XboxButton.LB))  # modo focus, cursor escondido
    pygame.mouse.set_visible(True)  # o que uma cena fazia no `enter()`

    app._sync_cursor_visibility(_Cena())
    assert pygame.mouse.get_visible() is False

    app._cursor_navigation_mode = "cursor"
    app._sync_cursor_visibility(_Cena())
    assert pygame.mouse.get_visible() is True


def test_gameplay_mantem_a_propria_politica():
    """A `PlayingScene` esconde o cursor por conta; o app não interfere."""
    app = _AppFalso()
    pygame.mouse.set_visible(False)
    app._cursor_navigation_mode = "cursor"
    app._sync_cursor_visibility(_CenaGameplay())
    assert pygame.mouse.get_visible() is False


def test_nenhuma_cena_de_menu_forca_o_cursor_visivel():
    """Varredura: `set_visible(True)` fora do app volta a criar a divergência.

    Exceção: `PlayingScene`/`WorldTransition`/`GameOver` no `exit()` — ali a
    cena está saindo e a próxima passa pelo sync mesmo assim.
    """
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "game" / "scenes"
    infratores = []
    for arquivo in raiz.rglob("*.py"):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.FunctionDef) or no.name == "exit":
                continue
            for interno in ast.walk(no):
                if not isinstance(interno, ast.Call):
                    continue
                alvo = interno.func
                if (
                    isinstance(alvo, ast.Attribute)
                    and alvo.attr == "set_visible"
                    and interno.args
                    and getattr(interno.args[0], "value", None) is True
                ):
                    infratores.append(
                        f"{arquivo.name}:{interno.lineno} ({no.name})"
                    )
    assert not infratores, (
        "quem manda na visibilidade do ponteiro é o modo de navegação do app "
        f"(_sync_cursor_visibility); forçado em: {infratores}"
    )


def test_eco_com_1px_de_desvio_ainda_e_reconhecido():
    """`pygame.SCALED` devolve a posição 1px torta em escala não inteira."""
    app = _AppFalso()
    app._track_input_mode(_botao(XboxButton.RB))
    app.warp_cursor((300, 200))
    app._track_input_mode(_motion((301, 199)))
    assert app._cursor_navigation_mode == "focus"
