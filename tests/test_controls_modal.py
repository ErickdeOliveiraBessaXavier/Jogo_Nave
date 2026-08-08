"""Modal pré-jogo: o que ele mostra e como se navega nele pelo controle.

Duas regressões de UX que nada mais pegava:

1. Os atalhos de método de controle / tiro automático apareciam SEMPRE, mesmo
   para quem já tinha decidido — repetindo uma pergunta respondida a cada
   partida.
2. A navegação dependia do cursor virtual do app: o ponteiro entrava onde a
   tela anterior o havia deixado, então nada aparecia focado e o A caía no
   `_finish` por não achar nada sob o cursor. Apertar A "para escolher"
   começava a partida.

O modal roda com stubs mínimos (sem app de verdade), que é a prova de que ele
não depende da cena que o abriu.
"""

import pygame
import pytest

from game.core.config import config as Config
from game.core.config import set_screen_resolution
from game.core.gamepad import XboxButton
from game.core.i18n import t
from game.core.preferences import UserPreferences
from game.scenes.controls_modal import ControlsModalScene

RESOLUCOES = [(1024, 576), (1280, 720), (1920, 1080)]


class _Gamepad:
    connected = True
    is_active = True

    def is_slot_active(self, slot):
        return slot == 0

    def get_stick(self, _side, slot=0):
        return (0.0, 0.0)


class _Input:
    mouse_control = False
    auto_fire = False


class _App:
    def __init__(self, prefs):
        self.preferences = prefs
        self.input = _Input()
        self.gamepad = _Gamepad()
        self._mode = "cursor"

    @property
    def cursor_navigation_mode(self):
        return self._mode

    def set_cursor_mode(self, mode):
        self._mode = mode


def montar(tmp_path, **flags):
    prefs = UserPreferences(tmp_path / "prefs.json")
    for chave, valor in flags.items():
        setattr(prefs, chave, valor)
    fim = []
    cena = ControlsModalScene(_App(prefs), on_finish=lambda: fim.append(True))
    cena.enter()
    return cena, prefs, fim


def acoes(cena):
    return [acao for acao, _rect in cena._focus_nodes()]


def joy(cena, button):
    cena.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": button}))


def dpad(cena, y):
    cena.handle_event(pygame.event.Event(pygame.JOYHATMOTION, {"value": (0, y)}))


# ── o que o modal mostra ────────────────────────────────────────────────────


def test_atalhos_aparecem_enquanto_nada_foi_configurado(tmp_path):
    cena, _prefs, _fim = montar(tmp_path, controls_configured=False)
    assert cena.show_quick_toggles
    assert acoes(cena)[:2] == ["control", "autofire"]


def test_atalhos_somem_depois_de_configurado(tmp_path):
    cena, _prefs, _fim = montar(
        tmp_path, controls_configured=True, controls_modal_seen=True
    )
    assert not cena.show_quick_toggles
    assert acoes(cena) == ["button", "checkbox"]
    assert cena.toggle_rects == {}


def test_modal_encolhe_quando_os_atalhos_somem(tmp_path):
    """Esconder sem encolher deixaria um vazio do tamanho do que foi escondido."""
    com, _p1, _f1 = montar(tmp_path, controls_configured=False)
    sem, _p2, _f2 = montar(tmp_path, controls_configured=True)
    assert sem.modal_h < com.modal_h


def test_usar_um_atalho_marca_a_preferencia(tmp_path):
    """É o que faz o modal parar de perguntar nas próximas partidas."""
    cena, prefs, _fim = montar(tmp_path, controls_configured=False)
    assert not prefs.controls_configured
    cena._toggle_auto_fire()
    assert prefs.controls_configured


def test_atalho_travado_pelo_controle_sai_da_ordem_de_foco(tmp_path):
    """Sem o que alternar, receber foco só criaria um passo morto."""
    cena, _prefs, _fim = montar(
        tmp_path, controls_configured=False, gamepad_enabled=True
    )
    assert "control" not in acoes(cena)
    assert "autofire" in acoes(cena)


# ── navegação por controle ──────────────────────────────────────────────────


def test_abre_com_o_primeiro_elemento_focado(tmp_path):
    cena, _prefs, _fim = montar(tmp_path, controls_configured=False)
    assert cena._focused_action() == "control"
    assert cena.app.cursor_navigation_mode == "focus"


def test_quem_ja_configurou_abre_focado_no_botao(tmp_path):
    """Caminho de um A só para quem já sabe o que quer."""
    cena, _prefs, _fim = montar(
        tmp_path, controls_configured=True, controls_modal_seen=True
    )
    assert cena._focused_action() == "button"


def test_dpad_percorre_a_ordem_visual(tmp_path):
    cena, _prefs, _fim = montar(
        tmp_path, controls_configured=False, controls_modal_seen=True
    )
    esperado = acoes(cena)
    vistos = [cena._focused_action()]
    for _ in range(len(esperado) - 1):
        dpad(cena, -1)  # hat y = -1 → baixo
        vistos.append(cena._focused_action())
    assert vistos == esperado
    dpad(cena, -1)
    assert cena._focused_action() == esperado[0], "a navegação tem de ser circular"


def test_a_aciona_o_elemento_focado_e_nao_fecha_o_modal(tmp_path):
    """A regressão exata: A sem nada sob o cursor caía no `_finish`."""
    cena, prefs, fim = montar(tmp_path, controls_configured=False)
    cena.focus_index = acoes(cena).index("autofire")
    antes = prefs.auto_fire
    joy(cena, XboxButton.A)
    assert prefs.auto_fire is not antes, "o A não acionou o atalho focado"
    assert not fim, "o A começou a partida em vez de acionar o foco"


def test_a_no_botao_principal_fecha(tmp_path):
    cena, _prefs, fim = montar(tmp_path, controls_configured=False)
    cena.focus_index = acoes(cena).index("button")
    joy(cena, XboxButton.A)
    assert fim


def test_b_fecha_o_modal(tmp_path):
    cena, _prefs, fim = montar(tmp_path, controls_configured=False)
    joy(cena, XboxButton.B)
    assert fim


def test_teclado_navega_e_aciona(tmp_path):
    cena, prefs, _fim = montar(tmp_path, controls_configured=False)
    cena.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN}))
    assert cena._focused_action() == "autofire"
    antes = prefs.auto_fire
    cena.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert prefs.auto_fire is not antes


def test_hover_do_mouse_sincroniza_o_foco(tmp_path):
    """Mouse e controle apontam para o MESMO selecionado."""
    cena, _prefs, _fim = montar(tmp_path, controls_configured=False)
    cena.app.set_cursor_mode("cursor")
    cena.handle_event(
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {
                "pos": cena.toggle_rects["autofire"].center,
                "rel": (1, 1),
                "buttons": (0, 0, 0),
            },
        )
    )
    assert cena._focused_action() == "autofire"


def test_hover_nao_rouba_o_foco_em_modo_controle(tmp_path):
    """Ponteiro parado sobre um botão não pode desfazer o que o D-pad moveu."""
    cena, _prefs, _fim = montar(tmp_path, controls_configured=False)
    dpad(cena, -1)
    focado = cena._focused_action()
    cena.handle_event(
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {
                "pos": cena.toggle_rects["control"].center,
                "rel": (0, 0),
                "buttons": (0, 0, 0),
            },
        )
    )
    assert cena._focused_action() == focado


# ── formato compacto do atalho de tiro ──────────────────────────────────────
#
# O rótulo era "Tiro automático: Ligado/Desligado". Como os botões do bloco têm
# largura UNIFORME (o maior rótulo entre TODOS os botões e estados manda, ver
# `layout_flow_buttons`), o "Desligado" definia a largura dos DOIS e a fileira
# não cabia numa linha: o bloco quebrava em duas e o modal crescia junto.
# Hoje é "Tiro: Automático/Manual" e os dois atalhos ficam lado a lado.


def _rotulos_do_atalho_de_tiro() -> list[str]:
    return [
        t("controls.toggle.autofire", v=t("controls.fire.auto")),
        t("controls.toggle.autofire", v=t("controls.fire.manual")),
    ]


def test_o_atalho_de_tiro_diz_automatico_ou_manual(tmp_path):
    """'Ligado/Desligado' descrevia o estado de uma opção; 'Automático/Manual'
    diz o que o tiro faz."""
    assert _rotulos_do_atalho_de_tiro() == ["Tiro: Automático", "Tiro: Manual"]


def test_os_dois_atalhos_ficam_na_mesma_linha(tmp_path):
    """O ganho concreto do rótulo curto: uma linha em vez de duas."""
    cena, _prefs, _fim = montar(tmp_path, controls_configured=False)
    control, autofire = cena.toggle_rects["control"], cena.toggle_rects["autofire"]
    assert control.top == autofire.top, "os atalhos quebraram em linhas separadas"
    assert control.right <= autofire.left, "os atalhos se sobrepõem"


def test_o_atalho_de_tiro_nao_manda_mais_na_largura(tmp_path):
    """Enquanto o rótulo de tiro era o mais longo, ele inflava o outro botão."""
    cena, _prefs, _fim = montar(tmp_path, controls_configured=False)
    fonte = cena.toggle_font
    mais_longo_tiro = max(fonte.size(s)[0] for s in _rotulos_do_atalho_de_tiro())
    mais_longo_controle = max(
        fonte.size(t("controls.toggle.control", v=t(k)))[0]
        for k in ("controls.method.mouse", "controls.method.keyboard")
    )
    assert mais_longo_tiro <= mais_longo_controle


def test_a_largura_do_atalho_nao_muda_ao_alternar(tmp_path):
    """Largura estável entre estados — senão o botão pula sob o cursor."""
    cena, prefs, _fim = montar(tmp_path, controls_configured=False)
    antes = cena.toggle_rects["autofire"].width
    cena._toggle_auto_fire()
    cena._calculate_layout()
    assert cena.toggle_rects["autofire"].width == antes


def test_a_coluna_de_instrucoes_usa_o_mesmo_vocabulario(tmp_path):
    """O atalho e a instrução falam do mesmo assunto; usar duas palavras
    diferentes ("Automático" no botão, "ligado" na instrução) faz parecer que
    são dois ajustes."""
    assert t("controls.fire.auto") in t("controls.shoot_auto")


def test_a_instrucao_manual_continua_dizendo_a_tecla(tmp_path):
    """Alinhar vocabulário não pode custar a informação da coluna: quem joga no
    manual precisa saber QUAL tecla atira."""
    assert "Espaço" in t("controls.kb.shoot")
    assert "RT" in t("controls.gp.shoot")


def test_alternar_continua_trocando_a_preferencia(tmp_path):
    """A lógica de seleção é a mesma; mudou só a apresentação."""
    cena, prefs, _fim = montar(tmp_path, controls_configured=False, auto_fire=False)
    cena._activate("autofire")
    assert prefs.auto_fire
    cena._activate("autofire")
    assert not prefs.auto_fire


# ── layout em todas as resoluções (§12) ─────────────────────────────────────


@pytest.mark.parametrize("size", RESOLUCOES)
@pytest.mark.parametrize("configurado", [False, True])
def test_o_modal_cabe_na_tela_e_os_alvos_cabem_nele(tmp_path, size, configurado):
    original = (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    try:
        set_screen_resolution(*size)
        cena, _prefs, _fim = montar(
            tmp_path, controls_configured=configurado, controls_modal_seen=True
        )
        tela = pygame.Rect(0, 0, *size)
        assert tela.contains(cena.modal_rect), "o modal estourou a tela"
        for acao, rect in cena._focus_nodes():
            # O alvo do checkbox é inflado para incluir o rótulo e pode passar
            # da borda do modal; os demais têm de caber inteiros nele.
            if acao == "checkbox":
                assert tela.contains(rect)
            else:
                assert cena.modal_rect.contains(rect), f"{acao} saiu do modal"
    finally:
        set_screen_resolution(*original)
