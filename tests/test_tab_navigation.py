"""TAB percorre os elementos focáveis — no app (telas de cursor) e nas cenas
que têm foco próprio.

O jogo já publicava `get_focusable_rects()` em quase toda tela (o snap-focus do
D-pad consome essa lista), mas o teclado não tinha como andar por ela: TAB só
acendia o modo focus e parava aí. Aqui o TAB passa a percorrer a MESMA ordem,
num lugar só, para o teclado não depender do mouse em nenhuma tela.
"""

import pygame
import pytest

from game.app import GameApp


class _CenaComRects:
    """Cena mínima de cursor: publica rects e registra o hover recebido."""

    is_gameplay_scene = False

    def __init__(self):
        self.rects = [
            pygame.Rect(100, 100, 80, 30),
            pygame.Rect(100, 200, 80, 30),
            pygame.Rect(100, 300, 80, 30),
        ]
        self.hover = None

    def get_focusable_rects(self):
        return self.rects

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = event.pos


class _CenaGameplay(_CenaComRects):
    is_gameplay_scene = True


class _CenaFocoProprio(_CenaComRects):
    owns_gamepad_navigation = True


class _Stack:
    def __init__(self, cena):
        self._cena = cena

    def current(self):
        return self._cena


class _AppFalso:
    _handle_tab_navigation = GameApp._handle_tab_navigation
    _handle_arrow_navigation = GameApp._handle_arrow_navigation
    _snap_focus_to_direction = GameApp._snap_focus_to_direction
    _focus_rect = GameApp._focus_rect
    _scene_is_gameplay = GameApp._scene_is_gameplay
    warp_cursor = GameApp.warp_cursor
    _set_cursor_mode = GameApp._set_cursor_mode

    def __init__(self, cena):
        self.screen_width = 1280
        self.screen_height = 720
        self._cursor_navigation_mode = "cursor"
        self._warp_targets = []
        self._virtual_cursor_x = 0.0
        self._virtual_cursor_y = 0.0
        self.states = _Stack(cena)


def _tab(shift=False):
    return pygame.event.Event(
        pygame.KEYDOWN,
        {"key": pygame.K_TAB, "mod": pygame.KMOD_LSHIFT if shift else 0, "unicode": ""},
    )


@pytest.fixture
def mouse(monkeypatch):
    """Ponteiro controlável.

    O driver de vídeo dummy ignora `set_pos` (o `get_pos` fica preso em 0,0),
    então o ponteiro real não serve para medir nada aqui. Este stub guarda a
    posição — é ela que o `_handle_tab_navigation` lê para saber de onde sai.
    """

    estado = {"pos": (0, 0)}
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: estado["pos"])
    monkeypatch.setattr(
        pygame.mouse, "set_pos", lambda pos: estado.__setitem__("pos", tuple(pos))
    )
    return estado


def test_tab_anda_na_ordem_declarada_pela_cena(mouse):
    cena = _CenaComRects()
    app = _AppFalso(cena)
    mouse["pos"] = (0, 0)  # fora de tudo

    assert app._handle_tab_navigation(_tab(), cena)
    assert mouse["pos"] == cena.rects[0].center
    app._handle_tab_navigation(_tab(), cena)
    assert mouse["pos"] == cena.rects[1].center
    app._handle_tab_navigation(_tab(), cena)
    assert mouse["pos"] == cena.rects[2].center
    app._handle_tab_navigation(_tab(), cena)
    assert mouse["pos"] == cena.rects[0].center, "TAB tem de ser circular"


def test_shift_tab_volta(mouse):
    cena = _CenaComRects()
    app = _AppFalso(cena)
    mouse["pos"] = cena.rects[1].center
    app._handle_tab_navigation(_tab(shift=True), cena)
    assert mouse["pos"] == cena.rects[0].center


def test_shift_tab_sem_foco_comeca_pelo_ultimo(mouse):
    cena = _CenaComRects()
    app = _AppFalso(cena)
    mouse["pos"] = (0, 0)
    app._handle_tab_navigation(_tab(shift=True), cena)
    assert mouse["pos"] == cena.rects[-1].center


def test_tab_avisa_a_cena_para_o_hover_acompanhar(mouse):
    """A tela desenha o destaque pelo hover; sem o aviso, o TAB moveria um
    cursor invisível e nada acenderia."""
    cena = _CenaComRects()
    app = _AppFalso(cena)
    app._handle_tab_navigation(_tab(), cena)
    assert cena.hover == cena.rects[0].center


def test_tab_esconde_o_ponteiro_e_nao_o_traz_de_volta(mouse):
    """Navegar por TAB é navegação discreta: entra em modo focus e fica."""
    cena = _CenaComRects()
    app = _AppFalso(cena)
    app._handle_tab_navigation(_tab(), cena)
    assert app._cursor_navigation_mode == "focus"
    # O eco do warp fica registrado para o `_track_input_mode` absorver.
    assert app._warp_targets


def test_gameplay_e_cenas_de_foco_proprio_ficam_com_o_tab():
    """Em partida o TAB não navega; com foco próprio, quem trata é a cena."""
    for cena in (_CenaGameplay(), _CenaFocoProprio()):
        app = _AppFalso(cena)
        assert not app._handle_tab_navigation(_tab(), cena)


def test_cena_sem_rects_nao_consome_o_tab():
    class _Vazia(_CenaComRects):
        def get_focusable_rects(self):
            return []

    cena = _Vazia()
    app = _AppFalso(cena)
    assert not app._handle_tab_navigation(_tab(), cena)


# ── setas: navegação geométrica, só nas telas que pedem ─────────────────────


def _seta(key):
    return pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0, "unicode": ""})


class _CenaComSetas(_CenaComRects):
    arrow_keys_navigate_focus = True


class _CenaSoVertical(_CenaComRects):
    arrow_keys_navigate_focus = "vertical"


def test_setas_movem_o_foco_na_direcao_apertada(mouse):
    """Busca geométrica, como o D-pad: ↓ vai para o de baixo na TELA."""
    cena = _CenaComSetas()
    app = _AppFalso(cena)
    mouse["pos"] = cena.rects[0].center

    assert app._handle_arrow_navigation(_seta(pygame.K_DOWN), cena)
    assert mouse["pos"] == cena.rects[1].center
    app._handle_arrow_navigation(_seta(pygame.K_DOWN), cena)
    assert mouse["pos"] == cena.rects[2].center
    app._handle_arrow_navigation(_seta(pygame.K_UP), cena)
    assert mouse["pos"] == cena.rects[1].center


def test_seta_sem_vizinho_na_direcao_nao_faz_nada(mouse):
    """Sem wrap: na borda o foco fica onde está (feedback claro do limite)."""
    cena = _CenaComSetas()
    app = _AppFalso(cena)
    mouse["pos"] = cena.rects[0].center
    assert not app._handle_arrow_navigation(_seta(pygame.K_UP), cena)
    assert mouse["pos"] == cena.rects[0].center


def test_cena_sem_opt_in_fica_com_as_proprias_setas(mouse):
    """Iniciais do game over, abas, carrossel: a tecla continua sendo delas."""
    cena = _CenaComRects()  # sem o atributo
    app = _AppFalso(cena)
    mouse["pos"] = cena.rects[0].center
    assert not app._handle_arrow_navigation(_seta(pygame.K_DOWN), cena)


def test_modo_vertical_devolve_o_eixo_horizontal_para_a_cena(mouse):
    cena = _CenaSoVertical()
    app = _AppFalso(cena)
    mouse["pos"] = cena.rects[0].center
    assert app._handle_arrow_navigation(_seta(pygame.K_DOWN), cena)
    assert not app._handle_arrow_navigation(_seta(pygame.K_LEFT), cena)
    assert not app._handle_arrow_navigation(_seta(pygame.K_RIGHT), cena)


def test_setas_tambem_entram_em_modo_focus(mouse):
    cena = _CenaComSetas()
    app = _AppFalso(cena)
    mouse["pos"] = cena.rects[0].center
    app._handle_arrow_navigation(_seta(pygame.K_DOWN), cena)
    assert app._cursor_navigation_mode == "focus"


# ── quem opta pelas setas, e quem não pode optar ────────────────────────────


def test_telas_que_ja_usam_seta_nao_optaram_pela_navegacao():
    """Guarda-corpo: ligar o opt-in nelas rouba a tecla sem quebrar teste algum.

    O game over edita as INICIAIS com as setas; a seleção de nave do P2 troca de
    nave com ←/→. Se alguém ligar o atributo lá, o app passa a consumir a seta
    antes da cena e o recurso some em silêncio.
    """
    from game.scenes.game_over import GameOverScene
    from game.scenes.p2_ship_select import P2ShipSelectScene

    for cena in (GameOverScene, P2ShipSelectScene):
        assert cena.arrow_keys_navigate_focus is False, (
            f"{cena.__name__} usa as setas para lógica própria"
        )


def test_telas_sem_seta_propria_optaram():
    """As que não tratavam seta nenhuma — onde o teclado não navegava."""
    from game.scenes.paused import PausedScene
    from game.scenes.statistics import StatisticsScene

    assert PausedScene.arrow_keys_navigate_focus is True
    assert StatisticsScene.arrow_keys_navigate_focus is True


def test_quem_navega_por_seta_tambem_confirma_por_enter():
    """Navegar sem poder acionar é meio caminho — e não falha em lugar nenhum.

    Toda tela que declara `arrow_keys_navigate_focus` (valor de classe ou
    property) precisa tratar Enter/Espaço no MESMO módulo, roteando para a
    mesma ação do A do controle. A varredura é por módulo porque cena e view
    costumam morar juntas; o que ela impede é o caso real de ligar a navegação
    e esquecer a confirmação.
    """
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "game" / "scenes"
    sem_confirmacao = []
    for arquivo in raiz.rglob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        declara = False
        for no in ast.walk(arvore):
            # Atributo de classe: arrow_keys_navigate_focus = True/"vertical"
            if isinstance(no, ast.Assign):
                for alvo in no.targets:
                    nome = getattr(alvo, "id", None)
                    if nome == "arrow_keys_navigate_focus":
                        declara = declara or bool(getattr(no.value, "value", False))
            # Property com o mesmo nome.
            if (
                isinstance(no, ast.FunctionDef)
                and no.name == "arrow_keys_navigate_focus"
            ):
                declara = True
        if declara and "K_RETURN" not in fonte:
            sem_confirmacao.append(arquivo.name)

    assert not sem_confirmacao, (
        "estas telas navegam por seta mas não confirmam por Enter: "
        f"{sem_confirmacao}"
    )
