"""Rolagem do grid de Aprimoramentos: roda, foco e arrasto da barra.

O grid passou a rolar de verdade quando a célula cresceu (`GRID_COLS` 8 → 6), e
com isso apareceram três defeitos que só existiam porque `max_scroll` era zero:

  1. **Travada sobre os cards.** `_ensure_focus_visible` rodava TODO frame e era
     um segundo dono de `scroll_target`. Com o ponteiro parado sobre um card, o
     hover fixava o foco nele e a função devolvia a rolagem para "revelar" um
     card que já estava visível — desfazendo a roda no frame seguinte.
  2. **Passo grosso.** Uma linha inteira por clique, num alcance de pouco mais de
     uma linha: dois cliques iam do topo ao fim.
  3. **Barra sem arrasto.** Era desenho, não controle.

A lógica vive na cena, então os testes montam a cena com stubs mínimos.
"""

import pygame
import pytest

from game.core.config import config as Config
from game.core.config import set_screen_resolution
from game.scenes.upgrades_selection import UpgradesSelectionScene


class _Renderer:
    class _Star:
        def update(self, dt):
            pass

    starfield = _Star()


class _Gamepad:
    """Sem controle conectado: o polling do analógico não deve opinar."""

    is_active = False

    def is_slot_active(self, _slot):
        return False

    def get_stick(self, _side, slot=0):
        return (0.0, 0.0)


class _App:
    def __init__(self, profile, screen):
        self.player_profile = profile
        self.renderer = _Renderer()
        self.preferences = profile._prefs
        self.screen = screen
        self.gamepad = _Gamepad()
        self._mode = "cursor"

    @property
    def cursor_navigation_mode(self):
        return self._mode

    def set_cursor_mode(self, mode):
        self._mode = mode


@pytest.fixture
def cena(tmp_path):
    from game.core.meta_progression import PlayerProfile
    from game.core.preferences import UserPreferences

    set_screen_resolution(1280, 720)
    tela = pygame.display.set_mode((1280, 720))
    profile = PlayerProfile(profile_path=tmp_path / "p.json")
    profile._prefs = UserPreferences(tmp_path / "prefs.json")
    c = UpgradesSelectionScene(_App(profile, tela))
    c.update(1 / 60)
    return c


def _roda(cena, cliques: int, pos) -> None:
    """Gira a roda `cliques` vezes com o ponteiro em `pos` (y negativo = desce)."""
    for _ in range(abs(cliques)):
        cena._scroll_request(1 if cliques > 0 else -1, pos)


def _sobre_um_card(cena):
    return cena.layout.cells[0].center


def _assenta(cena, frames=30):
    for _ in range(frames):
        cena.update(1 / 60)


class TestOGridRola:
    def test_ha_o_que_rolar(self, cena):
        """Sanidade: sem isto os outros testes passariam por vacuidade."""
        assert cena.max_scroll > 0.0

    def test_a_roda_rola_o_grid(self, cena):
        antes = cena.scroll_target
        _roda(cena, 1, cena.layout.viewport.center)
        assert cena.scroll_target > antes

    def test_o_passo_nao_atravessa_a_lista_de_uma_vez(self, cena):
        """Passo de linha cheia levava do topo ao fim em dois cliques."""
        _roda(cena, 1, cena.layout.viewport.center)
        assert cena.scroll_target < cena.max_scroll

    def test_rolar_para_baixo_chega_ao_fim(self, cena):
        _roda(cena, 12, cena.layout.viewport.center)
        assert cena.scroll_target == pytest.approx(cena.max_scroll)

    def test_rolar_para_cima_volta_ao_topo_e_para(self, cena):
        _roda(cena, 12, cena.layout.viewport.center)
        _roda(cena, -12, cena.layout.viewport.center)
        assert cena.scroll_target == 0.0


class TestSobreOsCards:
    """O defeito principal: a roda parada sobre um card não fazia nada."""

    def test_a_roda_funciona_com_o_ponteiro_sobre_um_card(self, cena):
        pos = _sobre_um_card(cena)
        antes = cena.scroll_target
        _roda(cena, 1, pos)
        assert cena.scroll_target > antes

    def test_o_hover_nao_desfaz_a_rolagem_no_frame_seguinte(self, cena, monkeypatch):
        """Era exatamente isto: rolava, e o frame seguinte devolvia."""
        pos = _sobre_um_card(cena)
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)
        _roda(cena, 1, pos)
        pedido = cena.scroll_target
        _assenta(cena)
        assert cena.scroll_target == pytest.approx(pedido)
        assert cena.scroll_y == pytest.approx(pedido, abs=1.0)

    def test_o_foco_por_controle_ainda_arrasta_a_janela(self, cena):
        """A rolagem automática não podia ser jogada fora junto com o defeito:
        o foco do controle continua puxando a janela para o card."""
        cena.app.set_cursor_mode("focus")
        cena.focus = ("upg", len(cena.layout.cells) - 1)  # última célula
        _assenta(cena)
        assert cena.scroll_target > 0.0
        assert cena.layout.viewport.contains(cena.layout.cells[-1])


class TestArrastoDaBarra:
    def test_a_barra_existe_quando_ha_rolagem(self, cena):
        assert cena._scrollbar_thumb() is not None

    def test_arrastar_o_polegar_rola(self, cena):
        polegar = cena._scrollbar_thumb()
        cena._scrollbar_press(polegar.center)
        assert cena._scrollbar_drag_offset is not None
        cena._scrollbar_drag_to(cena.layout.scrollbar.bottom)
        assert cena.scroll_target == pytest.approx(cena.max_scroll)

    def test_arrastar_de_volta_ao_topo(self, cena):
        polegar = cena._scrollbar_thumb()
        cena._scrollbar_press(polegar.center)
        cena._scrollbar_drag_to(cena.layout.scrollbar.bottom)
        cena._scrollbar_drag_to(cena.layout.scrollbar.top)
        assert cena.scroll_target == 0.0

    def test_clicar_na_calha_salta_para_o_ponto(self, cena):
        track = cena.layout.scrollbar
        cena._scrollbar_press((track.centerx, track.bottom - 2))
        assert cena.scroll_target > 0.0

    def test_o_polegar_desenhado_e_o_alvo_do_arrasto_sao_o_mesmo(self, cena):
        """§19: desenhar num lugar e testar o clique em outro."""
        polegar = cena._scrollbar_thumb()
        assert cena._scrollbar_press(polegar.center)

    def test_clique_fora_da_barra_nao_pega_o_arrasto(self, cena):
        assert not cena._scrollbar_press(cena.layout.viewport.center)
        assert cena._scrollbar_drag_offset is None

    def test_soltar_o_botao_encerra_o_arrasto(self, cena):
        polegar = cena._scrollbar_thumb()
        cena._scrollbar_press(polegar.center)
        cena.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": polegar.center})
        )
        assert cena._scrollbar_drag_offset is None

    def test_o_arrasto_nao_passa_dos_limites(self, cena):
        polegar = cena._scrollbar_thumb()
        cena._scrollbar_press(polegar.center)
        cena._scrollbar_drag_to(cena.layout.scrollbar.bottom + 5000)
        assert cena.scroll_target == pytest.approx(cena.max_scroll)
        cena._scrollbar_drag_to(cena.layout.scrollbar.top - 5000)
        assert cena.scroll_target == 0.0


class TestTextoDoCard:
    def test_a_roda_sobre_o_card_de_descricao_rola_o_texto(self, cena):
        """A regra de roteamento continua: sobre o card, rola o TEXTO."""
        antes_grid = cena.scroll_target
        cena._scroll_request(1, cena.layout.detail_card.center)
        assert cena.scroll_target == antes_grid


def teardown_module():
    set_screen_resolution(1280, 720)
    assert Config.SCREEN_WIDTH == 1280


class TestNavegacaoPorTeclado:
    """As setas movem o FOCO pelo grid, e os dois Enter acionam igual.

    Antes: ←/→ eram gastas trocando de aba e ↑/↓ rolando texto, então não havia
    gesto de teclado nenhum para andar pelos cards — só mouse ou controle. E o
    Enter do teclado numérico não era reconhecido em lugar nenhum desta tela.
    """

    def _tecla(self, cena, key, mod=0):
        cena.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": mod}))

    def test_seta_para_a_direita_anda_no_grid(self, cena):
        cena.focus = ("upg", 0)
        self._tecla(cena, pygame.K_RIGHT)
        assert cena.focus == ("upg", 1)

    def test_seta_para_a_esquerda_volta(self, cena):
        cena.focus = ("upg", 1)
        self._tecla(cena, pygame.K_LEFT)
        assert cena.focus == ("upg", 0)

    def test_seta_para_baixo_desce_uma_linha_do_grid(self, cena):
        from game.scenes.upgrades_layout import GRID_COLS

        cena.focus = ("upg", 0)
        self._tecla(cena, pygame.K_DOWN)
        assert cena.focus == ("upg", GRID_COLS)

    def test_seta_para_cima_sobe_uma_linha(self, cena):
        from game.scenes.upgrades_layout import GRID_COLS

        cena.focus = ("upg", GRID_COLS)
        self._tecla(cena, pygame.K_UP)
        assert cena.focus == ("upg", 0)

    def test_andar_no_grid_traz_a_celula_para_a_janela(self, cena):
        """A rolagem segue o foco: descer até a última linha revela o card.

        Desce só enquanto o foco CONTINUA no grid — passando da última linha ele
        sai para outro elemento da tela, e aí não há célula que valha medir.
        """
        cena.focus = ("upg", 0)
        ultimo = 0
        for _ in range(8):
            self._tecla(cena, pygame.K_DOWN)
            cena.update(1 / 60)
            if cena.focus[0] != "upg":
                break
            ultimo = cena.focus[1]
        assert ultimo > 0, "as setas não desceram nenhuma linha no grid"
        assert cena.scroll_target > 0.0, "a janela não seguiu o foco"
        for _ in range(40):
            cena.update(1 / 60)
        assert cena.layout.viewport.contains(cena.layout.cells[ultimo])

    def test_as_setas_alcancam_as_abas_saindo_do_grid(self, cena):
        """Trocar de aba continua possível: as abas são nós de foco acima do
        grid, alcançados pela MESMA navegação geométrica do D-pad."""
        cena.focus = ("upg", 0)
        regioes = set()
        for _ in range(4):
            self._tecla(cena, pygame.K_UP)
            regioes.add(cena.focus[0])
        assert "tab" in regioes

    def test_enter_principal_aciona_o_foco(self, cena):
        cena.focus = ("tab", 1)
        self._tecla(cena, pygame.K_RETURN)
        assert cena.active_tab == 1

    def test_enter_do_numerico_faz_o_mesmo(self, cena):
        """O defeito relatado: `K_KP_ENTER` não era reconhecido."""
        cena.focus = ("tab", 1)
        self._tecla(cena, pygame.K_KP_ENTER)
        assert cena.active_tab == 1

    def test_os_dois_enter_equipam_o_upgrade_em_foco(self, cena):
        """A ação tem de ser a MESMA, não só 'alguma'."""
        from game.core.upgrades import UpgradeType

        def equipar_com(tecla):
            perfil = cena.player_profile
            perfil.upgrade_loadout = [None] * len(perfil.upgrade_loadout)
            alvo = cena.layout.visible_upgrades[0]
            perfil.unlocked_upgrades.add(alvo.type)
            cena.focus = ("upg", 0)
            self._tecla(cena, tecla)
            return perfil.get_equipped_slot(alvo.type)

        principal = equipar_com(pygame.K_RETURN)
        numerico = equipar_com(pygame.K_KP_ENTER)
        assert principal is not None, "o Enter principal nem equipou"
        assert numerico == principal
        assert isinstance(UpgradeType, type)
