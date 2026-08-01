"""HUD tocável do modo celular — layout e acionamento.

Duas coisas que só existem juntas:

1. **Uma geometria, dois leitores.** Enquanto o HUD era só desenho, calcular a
   posição dos slots dentro do renderer estava certo. Com o toque passam a
   existir dois leitores — quem pinta e quem descobre onde o dedo caiu —, e
   recalcular dos dois lados é a duplicação que diverge em silêncio no dia em
   que alguém mexer no `gap`. Estes testes travam que os dois leem o MESMO
   `hud_layout`.

2. **A captura do ponteiro.** A nave segue a posição do ponteiro continuamente.
   Sem uma trava, tocar num slot puxaria a nave para cima do botão — e no
   celular é o mesmo dedo que pilota e que toca, então isso aconteceria em todo
   uso de upgrade. É o defeito mais provável desta feature e o mais difícil de
   ver num teste manual (a nave "dá um pulo" e você culpa a rede, o FPS, o dedo).
"""

import pygame
import pytest

from game.core.config import config as Config, set_screen_resolution
from game.core.ship_types import get_ship_profile
from game.entities.player.ship import Ship
from game.render.hud_layout import pause_button_rect, upgrade_hud_layout


@pytest.fixture(autouse=True)
def _res_720p():
    original = (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    set_screen_resolution(1280, 720)
    yield
    set_screen_resolution(*original)


class TestLayout:
    def test_desktop_e_fileira_embaixo_no_centro(self):
        layout = upgrade_hud_layout(4, 1.0, touch_mode=False)

        assert not layout.vertical
        assert layout.container.bottom == Config.SCREEN_HEIGHT
        assert layout.container.centerx == pytest.approx(Config.SCREEN_WIDTH // 2, abs=2)

    def test_toque_e_coluna_na_borda_direita(self):
        """O rodapé central é o pior lugar num celular: num shmup vertical a
        nave vive embaixo e o polegar que pilota fica em cima dela."""
        layout = upgrade_hud_layout(4, 1.0, touch_mode=True)

        assert layout.vertical
        assert layout.container.right < Config.SCREEN_WIDTH
        assert layout.container.centery == pytest.approx(
            Config.SCREEN_HEIGHT // 2, abs=2
        )

    def test_a_coluna_de_toque_sai_do_rodape(self):
        """O invariante que dá sentido ao relayout: se a coluna continuasse na
        faixa de baixo, o dedo que pilota ainda estaria em cima dela."""
        desktop = upgrade_hud_layout(4, 1.0, touch_mode=False)
        toque = upgrade_hud_layout(4, 1.0, touch_mode=True)

        assert toque.container.bottom < desktop.container.top

    @pytest.mark.parametrize("touch", [False, True])
    @pytest.mark.parametrize("count", [1, 2, 4, 8])
    def test_slots_nao_se_sobrepoem_e_cabem_na_tela(self, count, touch):
        layout = upgrade_hud_layout(count, 1.0, touch_mode=touch)

        assert len(layout.slots) == count
        for i, rect in enumerate(layout.slots):
            assert Config.SCREEN_WIDTH >= rect.right and rect.left >= 0
            assert Config.SCREEN_HEIGHT >= rect.bottom and rect.top >= 0
            assert layout.container.contains(rect)
            for outro in layout.slots[i + 1 :]:
                assert not rect.colliderect(outro)

    def test_sem_slots_nao_ha_geometria(self):
        layout = upgrade_hud_layout(0, 1.0, touch_mode=True)
        assert layout.slots == ()
        assert layout.container.width == 0

    @pytest.mark.parametrize("resolution", [(1024, 576), (1280, 720), (1920, 1080)])
    def test_escala_por_resolucao(self, resolution):
        """§12: pixel fixo de UI passa por `ui_scale`. Sem isso a coluna nasce
        minúscula em 1080p e estoura em 576p."""
        set_screen_resolution(*resolution)
        ui_scale = resolution[0] / 1280.0
        layout = upgrade_hud_layout(4, ui_scale, touch_mode=True)

        assert layout.container.right <= resolution[0]
        assert layout.container.top >= 0
        assert layout.slots[0].width == pytest.approx(50 * ui_scale, abs=1)

    def test_pausa_nao_colide_com_a_coluna(self):
        """Errar a pausa não pode ativar um upgrade, e vice-versa: um é sair da
        partida, o outro gasta um recurso."""
        pausa = pause_button_rect(1.0)
        coluna = upgrade_hud_layout(8, 1.0, touch_mode=True).container

        assert not pausa.colliderect(coluna)

    def test_o_alvo_da_pausa_e_grande_o_bastante_para_um_dedo(self):
        """Alvo de toque pequeno demais é o clássico do port apressado. O botão
        é maior que um slot de propósito: é o único caminho para pausar sem
        teclado, e errá-lo custa uma vida."""
        pausa = pause_button_rect(1.0)
        slot = upgrade_hud_layout(1, 1.0, touch_mode=True).slots[0]

        assert min(pausa.width, pausa.height) >= 44
        assert pausa.width > slot.width


class _StubApp:
    def __init__(self, touch_mode: bool):
        self.preferences = type("P", (), {"touch_mode": touch_mode})()


class _StubScene:
    """Só o que o `_touch_hud_hit` toca da cena."""

    ui_scale = 1.0

    def __init__(self, *, touch_mode: bool, n_upgrades: int = 3, joystick: bool = False):
        from game.systems.virtual_joystick import VirtualJoystick

        self.app = _StubApp(touch_mode)
        # None = modo joystick desligado; e o proprio gate (ver PlayingScene).
        self.virtual_joystick = VirtualJoystick() if joystick else None
        self.ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        # Índices reais espaçados de propósito: exibição ≠ índice no loadout, e
        # confundir os dois aciona o upgrade errado.
        self.upgrade_slots = [None] * 8
        for pos, real in enumerate([1, 4, 6][:n_upgrades]):
            self.upgrade_slots[real] = f"upg{pos}"
        self.ativados: list[int] = []
        self.pausas = 0

    def activate_upgrade_slot(self, idx: int) -> None:
        self.ativados.append(idx)

    def can_handle_gameplay_actions(self) -> bool:
        # A cena real recusa acoes durante cutscene/preparacao/game over.
        return True


def _handler(scene):
    from game.systems.gameplay_input_handler import GameplayInputHandler

    h = GameplayInputHandler(scene)
    h._open_pause = lambda: setattr(scene, "pausas", scene.pausas + 1)
    return h


class TestAcionamento:
    def test_o_toque_no_slot_ativa_o_indice_REAL(self):
        """Exibição ≠ índice no loadout. O 2º slot desenhado é o índice 4 — se
        alguém passar o índice de exibição, o jogador toca num poder e usa outro.
        """
        scene = _StubScene(touch_mode=True)
        layout = upgrade_hud_layout(3, 1.0, touch_mode=True)

        assert _handler(scene)._touch_hud_hit(layout.slots[1].center)
        assert scene.ativados == [4]

    def test_cada_slot_desenhado_aciona_o_seu(self):
        scene = _StubScene(touch_mode=True)
        layout = upgrade_hud_layout(3, 1.0, touch_mode=True)
        h = _handler(scene)

        for rect in layout.slots:
            h._touch_hud_hit(rect.center)

        assert scene.ativados == [1, 4, 6]

    def test_o_botao_de_pausa_pausa(self):
        scene = _StubScene(touch_mode=True)

        assert _handler(scene)._touch_hud_hit(pause_button_rect(1.0).center)
        assert scene.pausas == 1

    def test_toque_fora_dos_alvos_nao_consome(self):
        """Devolver True aqui congelaria a pilotagem em todo toque na arena."""
        scene = _StubScene(touch_mode=True)

        assert not _handler(scene)._touch_hud_hit((Config.SCREEN_WIDTH // 2, 200))
        assert scene.ativados == []

    def test_no_desktop_o_hud_nao_captura_nada(self):
        """A regressão que ninguém veria: um clique de tiro no canto da tela
        ativando um upgrade porque o rect de toque existe fora do modo toque."""
        scene = _StubScene(touch_mode=False)
        layout = upgrade_hud_layout(3, 1.0, touch_mode=True)
        h = _handler(scene)

        assert not h._touch_hud_hit(layout.slots[0].center)
        assert not h._touch_hud_hit(pause_button_rect(1.0).center)
        assert scene.ativados == []


class TestCapturaDoPonteiro:
    def test_tocar_num_slot_congela_a_pilotagem(self):
        """Sem isto a nave é puxada para cima do botão a cada uso de upgrade."""
        scene = _StubScene(touch_mode=True)
        layout = upgrade_hud_layout(3, 1.0, touch_mode=True)

        _handler(scene)._touch_hud_hit(layout.slots[0].center)

        assert scene.ship.pointer_captured

    def test_a_nave_ignora_o_ponteiro_enquanto_capturado(self):
        from unittest.mock import patch

        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"), mouse_control=True)
        ship.y = 300.0
        ship.pointer_captured = True
        antes = (ship.x, ship.y)

        with patch("pygame.mouse.get_pos", return_value=(100, 100)):
            ship.move(set(), 1 / 60)

        assert (ship.x, ship.y) == antes

    def test_soltar_o_dedo_devolve_a_pilotagem(self):
        scene = _StubScene(touch_mode=True)
        h = _handler(scene)
        h._touch_hud_hit(pause_button_rect(1.0).center)
        assert scene.ship.pointer_captured

        h._handle_mousebuttonup(
            pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (0, 0)})
        )

        assert not scene.ship.pointer_captured

    def test_nasce_solta(self):
        assert not Ship(0.0, 0.0, profile=get_ship_profile("padrao")).pointer_captured


class TestModoJoystick:
    """O direcional dentro do fluxo real de eventos de ponteiro.

    Com um ponteiro só (multi-toque não existe no pygbag — medido no aparelho),
    o direcional precisa ser o PRIMEIRO a ver o toque: a zona dele é a maior da
    tela e fica no canto onde o polegar mora, então qualquer alvo testado antes
    roubaria gestos de pilotagem.
    """

    @staticmethod
    def _cena():
        from game.render.hud_layout import joystick_center

        scene = _StubScene(touch_mode=True, joystick=True)
        return scene, _handler(scene), joystick_center(1.0)

    def test_o_toque_no_direcional_captura_o_gesto(self):
        scene, h, centro = self._cena()

        assert h._touch_hud_hit(centro)
        assert scene.virtual_joystick.active

    def test_arrastar_pilota(self):
        scene, h, centro = self._cena()
        h._touch_hud_hit(centro)

        h.handle(
            pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": (centro[0] + 60, centro[1]), "rel": (60, 0)}
            )
        )

        vx, vy = scene.virtual_joystick.vector()
        assert vx > 0.5 and abs(vy) < 0.2

    def test_soltar_o_dedo_para_a_nave(self):
        scene, h, centro = self._cena()
        h._touch_hud_hit(centro)
        h.handle(
            pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": (centro[0] + 60, centro[1]), "rel": (60, 0)}
            )
        )
        assert scene.virtual_joystick.vector() != (0.0, 0.0)

        h.handle(
            pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": centro})
        )

        assert scene.virtual_joystick.vector() == (0.0, 0.0)

    def test_arrastar_sem_tocar_no_direcional_nao_pilota(self):
        """`MOUSEMOTION` chega a cada frame; só o gesto iniciado no direcional
        pode movê-lo."""
        scene, h, centro = self._cena()

        h.handle(
            pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": (centro[0] + 60, centro[1]), "rel": (60, 0)}
            )
        )

        assert scene.virtual_joystick.vector() == (0.0, 0.0)

    def test_o_botao_de_girar_gira(self):
        """Sem ele a rotação fica INALCANÇÁVEL no toque: os outros caminhos são
        tecla Ctrl e botão do meio do mouse."""
        from game.render.hud_layout import rotate_button_rect

        scene, h, _ = self._cena()
        antes = scene.ship.facing

        assert h._touch_hud_hit(rotate_button_rect(1.0).center)

        assert scene.ship.facing != antes

    def test_sem_o_modo_joystick_o_botao_de_girar_nao_existe(self):
        """Ele é mobília do modo direcional; no `mouse_control` girar continua
        no clique do meio, e um rect ativo aqui roubaria toques da arena."""
        from game.render.hud_layout import rotate_button_rect

        scene = _StubScene(touch_mode=True, joystick=False)
        antes = scene.ship.facing

        assert not _handler(scene)._touch_hud_hit(rotate_button_rect(1.0).center)
        assert scene.ship.facing == antes

    def test_o_direcional_vence_a_pausa_no_canto(self):
        """A pausa sobe para a meia-altura quando o direcional existe; se ela
        continuasse no canto, pilotar pausaria o jogo."""
        from game.render.hud_layout import joystick_center

        scene, h, _ = self._cena()

        assert h._touch_hud_hit(joystick_center(1.0))
        assert scene.pausas == 0


class TestCantosArredondados:
    """Harmonia dos cantos do HUD de toque.

    Dois raios e só dois (`PANEL_RADIUS` / `SLOT_RADIUS`), numa fonte única. O
    renderer tinha quatro números soltos — container 15, slot 8, pausa 12, girar
    12 — e a diferença entre 12 e 15 não comunicava nada.

    O invariante que muda com o reposicionamento: a fileira do desktop nasce
    COLADA no rodapé, então arredondar embaixo seria curvar fora da tela; a
    coluna do toque FLUTUA a 14px da borda, e ali um canto reto lê como peça
    recortada.
    """

    @staticmethod
    def _pintado(surface, ponto) -> bool:
        return surface.get_at(ponto)[3] > 0

    def _desenhar(self, touch_mode: bool):
        from game.render.game_renderer import GameRenderer
        from game.render.hud_layout import upgrade_hud_layout

        class _Frame:
            unlocked_upgrade_slots = 4
            upgrade_keybindings = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4]
            upgrade_slots = [None] * 8
            upgrade_denied_timers: dict = {}

        _Frame.touch_mode = touch_mode
        r = GameRenderer(None)
        surf = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        surf.fill((0, 0, 0, 0))
        r._render_empty_upgrade_slots(_Frame(), surf)
        return surf, upgrade_hud_layout(4, r.ui_scale, touch_mode).container

    def test_a_coluna_do_toque_arredonda_os_QUATRO_cantos(self):
        surf, box = self._desenhar(touch_mode=True)

        for canto in (box.topleft, box.topright, box.bottomleft, box.bottomright):
            x = min(max(canto[0], box.left), box.right - 1)
            y = min(max(canto[1], box.top), box.bottom - 1)
            assert not self._pintado(surf, (x, y)), (
                f"canto {canto} da coluna flutuante saiu reto"
            )

    def test_a_fileira_do_desktop_mantem_a_base_reta(self):
        """Ela encosta no rodapé: curvar ali é desenhar fora da tela, e o
        resultado visível seria um degrau entre a caixa e a borda."""
        surf, box = self._desenhar(touch_mode=False)

        assert self._pintado(surf, (box.left, box.bottom - 1))
        assert self._pintado(surf, (box.right - 1, box.bottom - 1))
        assert not self._pintado(surf, (box.left, box.top))

    def test_um_raio_so_para_caixa_e_botao(self):
        """Container, pausa e girar são a mesma família visual."""
        from game.render.hud_layout import PANEL_RADIUS, panel_radius

        assert panel_radius(1.0) == int(PANEL_RADIUS)
        assert panel_radius(2.0) == int(PANEL_RADIUS * 2)

    def test_o_slot_arredonda_MENOS_que_o_painel(self):
        """Canto interno com o mesmo raio do painel lê como desalinhado: a curva
        de dentro parece maior, porque percorre um arco menor."""
        from game.render.hud_layout import panel_radius, slot_radius

        assert 0 < slot_radius(1.0) < panel_radius(1.0)

    @pytest.mark.parametrize("resolution", [(1024, 576), (1280, 720), (1920, 1080)])
    def test_os_raios_escalam_com_a_resolucao(self, resolution):
        """§12: pixel fixo de UI passa por `ui_scale`, inclusive raio — senão o
        arredondamento some em 1080p e engole a caixa em 576p."""
        from game.render.hud_layout import panel_radius, slot_radius

        us = resolution[0] / 1280.0
        assert panel_radius(us) == pytest.approx(14 * us, abs=1)
        assert slot_radius(us) == pytest.approx(8 * us, abs=1)


def _dedo(tipo, finger, pos):
    """Evento de dedo com coordenadas NORMALIZADAS, como o SDL entrega."""
    return pygame.event.Event(
        tipo,
        {
            "finger_id": finger,
            "touch_id": 1,
            "x": pos[0] / Config.SCREEN_WIDTH,
            "y": pos[1] / Config.SCREEN_HEIGHT,
            "dx": 0.0,
            "dy": 0.0,
            "pressure": 1.0,
        },
    )


class TestMultiToque:
    """Pilotar com um polegar e agir com o outro.

    A sonda no aparelho mostrou dois dedos simultâneos: o multi-toque existia e
    quem não o lia era a nossa entrada, escrita sobre eventos de mouse. Agora
    cada gesto tem `finger_id`, e é a posse do dedo que separa "estou pilotando"
    de "estou tocando num botão".
    """

    @staticmethod
    def _cena():
        from game.render.hud_layout import joystick_center

        scene = _StubScene(touch_mode=True, joystick=True)
        return scene, _handler(scene), joystick_center(1.0)

    def test_um_dedo_pilota_enquanto_o_outro_ativa_upgrade(self):
        """O caso exato que estava falhando no aparelho."""
        from game.render.hud_layout import upgrade_hud_layout

        scene, h, centro = self._cena()
        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))
        h.handle(_dedo(pygame.FINGERMOTION, 1, (centro[0] + 60, centro[1])))
        pilotando = scene.virtual_joystick.vector()

        slot = upgrade_hud_layout(3, 1.0, touch_mode=True).slots[1]
        h.handle(_dedo(pygame.FINGERDOWN, 2, slot.center))

        assert scene.ativados == [4], "o segundo dedo nao acionou o upgrade"
        assert scene.virtual_joystick.vector() == pilotando, (
            "tocar no upgrade mexeu no direcional"
        )

    def test_o_segundo_dedo_nao_arrasta_a_nave(self):
        """Sem posse de dedo, o `FINGERMOTION` de qualquer um moveria o
        direcional — o oposto do que o multi-toque veio resolver."""
        scene, h, centro = self._cena()
        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))
        h.handle(_dedo(pygame.FINGERMOTION, 1, (centro[0] + 60, centro[1])))
        antes = scene.virtual_joystick.vector()

        h.handle(_dedo(pygame.FINGERMOTION, 2, (centro[0] - 60, centro[1] - 60)))

        assert scene.virtual_joystick.vector() == antes

    def test_soltar_o_segundo_dedo_nao_solta_o_direcional(self):
        scene, h, centro = self._cena()
        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))
        h.handle(_dedo(pygame.FINGERMOTION, 1, (centro[0] + 60, centro[1])))

        h.handle(_dedo(pygame.FINGERUP, 2, (900.0, 200.0)))

        assert scene.virtual_joystick.active
        assert scene.virtual_joystick.vector() != (0.0, 0.0)

    def test_soltar_o_DONO_para_a_nave(self):
        scene, h, centro = self._cena()
        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))
        h.handle(_dedo(pygame.FINGERMOTION, 1, (centro[0] + 60, centro[1])))

        h.handle(_dedo(pygame.FINGERUP, 1, (centro[0] + 60, centro[1])))

        assert not scene.virtual_joystick.active
        assert scene.virtual_joystick.vector() == (0.0, 0.0)

    def test_coordenada_normalizada_vira_pixel(self):
        """`FINGER*` entrega 0..1, não pixels. Sem a multiplicação pela
        resolução, todo toque cairia no canto superior esquerdo."""
        scene, h, centro = self._cena()

        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))

        assert scene.virtual_joystick.active, (
            "o toque no centro do direcional nao foi reconhecido: "
            "coordenada normalizada tratada como pixel"
        )

    def test_mouse_sintetizado_e_descartado_apos_o_primeiro_dedo(self):
        """Aparelho que entrega dedo E mouse fantasma processaria cada toque
        DUAS vezes — o upgrade dispararia em dobro."""
        from game.render.hud_layout import upgrade_hud_layout

        scene, h, centro = self._cena()
        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))  # liga a deteccao
        slot = upgrade_hud_layout(3, 1.0, touch_mode=True).slots[0]

        h.handle(_dedo(pygame.FINGERDOWN, 2, slot.center))
        h.handle(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"pos": slot.center, "button": 1, "touch": True},
            )
        )

        assert scene.ativados == [1], "o toque foi contado duas vezes"

    def test_mouse_de_verdade_continua_passando(self):
        """`.touch=False` é mouse real: no navegador de PC ele tem de seguir
        funcionando mesmo depois de um toque qualquer."""
        from game.render.hud_layout import upgrade_hud_layout

        scene, h, centro = self._cena()
        h.handle(_dedo(pygame.FINGERDOWN, 1, centro))
        slot = upgrade_hud_layout(3, 1.0, touch_mode=True).slots[2]

        h.handle(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"pos": slot.center, "button": 1, "touch": False},
            )
        )

        assert scene.ativados == [6]

    def test_sem_evento_de_dedo_o_mouse_manda(self):
        """Plataforma sem toque: nada muda em relação ao que já funcionava."""
        from game.render.hud_layout import upgrade_hud_layout

        scene, h, _ = self._cena()
        slot = upgrade_hud_layout(3, 1.0, touch_mode=True).slots[0]

        h.handle(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"pos": slot.center, "button": 1, "touch": True},
            )
        )

        assert scene.ativados == [1]
