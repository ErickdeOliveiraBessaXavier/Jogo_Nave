"""Joystick virtual do modo celular.

Ele existe porque o `mouse_control` faz o dedo SER a mira: a nave persegue o
ponteiro, então a mão cobre exatamente a peça que o jogador precisa ver. O
`touch_offset` remendava isso afastando a nave 90px; o joystick resolve pela
raiz, ancorando o polegar num canto.

O que estes testes travam:

1. **o vetor é o contrato do gamepad** — disco unitário. É o que permite reusar
   `ShipMovement` inteiro (magnitude proporcional, inversão da Toxina,
   multiplicadores de velocidade) sem escrever matemática de movimento nova;
2. **zona morta que parte do zero** — cruzar a borda não pode dar um salto de
   velocidade;
3. **satura no raio, não desancora** — seguir o dedo para fora faz o jogador
   perder a referência de onde o centro ficou;
4. **soltar PARA a nave** — a diferença de sensação para o `mouse_control`, onde
   soltar deixa a nave indo até o último ponto tocado;
5. **a zona de toque é maior que o desenho** — errar o direcional por poucos
   pixels e a nave não responder é a pior falha possível num controle de toque.
"""

import math

import pytest

from game.core.config import config as Config, set_screen_resolution
from game.render.hud_layout import (
    joystick_activation_radius,
    joystick_center,
    joystick_radius,
    pause_button_rect,
    rotate_button_rect,
    upgrade_hud_layout,
)
from game.systems.virtual_joystick import VirtualJoystick

CENTER = (200.0, 500.0)
RADIUS = 68.0


@pytest.fixture(autouse=True)
def _res_720p():
    original = (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    set_screen_resolution(1280, 720)
    yield
    set_screen_resolution(*original)


def _segurando(offset: tuple[float, float]) -> VirtualJoystick:
    j = VirtualJoystick()
    assert j.press(CENTER, CENTER, RADIUS)
    j.drag((CENTER[0] + offset[0], CENTER[1] + offset[1]))
    return j


class TestVetor:
    def test_parado_no_centro_nao_move(self):
        assert _segurando((0.0, 0.0)).vector() == (0.0, 0.0)

    def test_solto_nao_move(self):
        """A diferença central para o `mouse_control`: soltar PARA a nave, em vez
        de deixá-la voando rumo ao último ponto tocado."""
        j = _segurando((RADIUS, 0.0))
        assert j.vector() != (0.0, 0.0)

        j.release()

        assert j.active is False
        assert j.vector() == (0.0, 0.0)

    @pytest.mark.parametrize(
        "offset,esperado",
        [
            ((RADIUS, 0.0), (1.0, 0.0)),  # direita
            ((-RADIUS, 0.0), (-1.0, 0.0)),  # esquerda
            ((0.0, -RADIUS), (0.0, -1.0)),  # cima
            ((0.0, RADIUS), (0.0, 1.0)),  # baixo
        ],
    )
    def test_direcao_no_maximo(self, offset, esperado):
        vx, vy = _segurando(offset).vector()
        assert (vx, vy) == pytest.approx(esperado, abs=0.01)

    def test_nunca_passa_do_disco_unitario(self):
        """`ShipMovement` normaliza acima de 1, então um vetor maior viraria só
        velocidade máxima — mas a magnitude é lida antes disso para o movimento
        proporcional, e um valor fora de escala quebraria a proporção."""
        for offset in [(RADIUS * 5, 0.0), (RADIUS * 3, RADIUS * 3), (0.0, -RADIUS * 9)]:
            vx, vy = _segurando(offset).vector()
            assert math.hypot(vx, vy) <= 1.0 + 1e-6

    def test_movimento_e_proporcional(self):
        """Inclinar pouco anda devagar: é o que o jogador espera de analógico, e
        é o que separa isto de um D-pad."""
        pouco = math.hypot(*_segurando((RADIUS * 0.5, 0.0)).vector())
        muito = math.hypot(*_segurando((RADIUS, 0.0)).vector())

        assert 0.0 < pouco < muito


class TestZonaMorta:
    def test_tremor_do_polegar_nao_vira_deriva(self):
        tremor = RADIUS * (VirtualJoystick.DEAD_ZONE * 0.5)
        assert _segurando((tremor, 0.0)).vector() == (0.0, 0.0)

    def test_a_saida_da_zona_morta_parte_do_ZERO(self):
        """Sem o reescalonamento, cruzar a borda faria a nave arrancar já com
        ~14% da velocidade — um solavanco em todo início de movimento."""
        logo_depois = RADIUS * (VirtualJoystick.DEAD_ZONE + 0.01)
        mag = math.hypot(*_segurando((logo_depois, 0.0)).vector())

        assert 0.0 < mag < 0.05

    def test_o_maximo_continua_sendo_1(self):
        """A zona morta come o começo da escala, não o fim."""
        mag = math.hypot(*_segurando((RADIUS, 0.0)).vector())
        assert mag == pytest.approx(1.0, abs=0.01)


class TestCaptura:
    def test_toque_fora_da_zona_nao_captura(self):
        j = VirtualJoystick()
        assert not j.press((CENTER[0] + RADIUS * 3, CENTER[1]), CENTER, RADIUS)
        assert not j.active

    def test_arrastar_sem_ter_capturado_nao_faz_nada(self):
        """O `MOUSEMOTION` chega a cada frame do jogo inteiro; só o gesto que
        começou no direcional pode movê-lo."""
        j = VirtualJoystick()
        j.drag((CENTER[0] + RADIUS, CENTER[1]))
        assert j.vector() == (0.0, 0.0)

    def test_o_knob_satura_no_raio(self):
        """Deixar o direcional seguir o dedo para fora seria mais natural no
        papel, mas o jogador perde a referência de onde o centro ficou."""
        ox, oy = _segurando((RADIUS * 4, 0.0)).offset()
        assert math.hypot(ox, oy) == pytest.approx(RADIUS, abs=0.5)

    def test_o_knob_segue_o_dedo_dentro_do_raio(self):
        ox, oy = _segurando((RADIUS * 0.5, 0.0)).offset()
        assert (ox, oy) == pytest.approx((RADIUS * 0.5, 0.0), abs=0.5)


class TestLayoutDoJoystick:
    def test_a_zona_de_toque_e_maior_que_o_desenho(self):
        """Alvo do tamanho exato do desenho falha o tempo todo: o dedo cobre a
        peça que está tentando acertar."""
        assert joystick_activation_radius(1.0) > joystick_radius(1.0)

    def test_fica_no_canto_inferior_esquerdo(self):
        cx, cy = joystick_center(1.0)
        assert cx < Config.SCREEN_WIDTH // 3
        assert cy > Config.SCREEN_HEIGHT * 2 // 3

    def test_cabe_na_tela_com_a_zona_inteira(self):
        cx, cy = joystick_center(1.0)
        r = joystick_activation_radius(1.0)
        assert cx - r >= -r * 0.5 and cy + r <= Config.SCREEN_HEIGHT + r * 0.5

    def test_a_pausa_SAI_do_canto_do_joystick(self):
        """Sobrepor os dois trocaria 'pausei sem querer' por 'parei de pilotar
        sem querer' — os dois no meio de uma esquiva."""
        cx, cy = joystick_center(1.0)
        r = joystick_activation_radius(1.0)
        pausa = pause_button_rect(1.0, joystick=True)

        dist = math.hypot(pausa.centerx - cx, pausa.centery - cy)
        assert dist > r

    def test_girar_fica_longe_do_direcional(self):
        """Diagonal e não ao lado: o polegar que sai do direcional passa por
        tudo à direita dele, e girar no meio de uma esquiva troca a direção do
        tiro sem o jogador pedir."""
        cx, _ = joystick_center(1.0)
        girar = rotate_button_rect(1.0)

        assert girar.left > Config.SCREEN_WIDTH // 2
        assert girar.centerx > cx

    def test_girar_nao_colide_com_a_coluna_de_upgrades(self):
        girar = rotate_button_rect(1.0)
        coluna = upgrade_hud_layout(8, 1.0, touch_mode=True).container

        assert not girar.colliderect(coluna)

    def test_girar_e_alvo_de_dedo(self):
        girar = rotate_button_rect(1.0)
        assert min(girar.width, girar.height) >= 44

    @pytest.mark.parametrize("resolution", [(1024, 576), (1280, 720), (1920, 1080)])
    def test_tudo_cabe_em_qualquer_resolucao(self, resolution):
        """§12: pixel fixo de UI passa por `ui_scale`."""
        set_screen_resolution(*resolution)
        us = resolution[0] / 1280.0

        cx, cy = joystick_center(us)
        r = joystick_radius(us)
        girar = rotate_button_rect(us)
        pausa = pause_button_rect(us, joystick=True)

        assert cx - r >= 0 and cy + r <= resolution[1]
        assert girar.right <= resolution[0] and girar.bottom <= resolution[1]
        assert pausa.left >= 0 and pausa.bottom <= resolution[1]
        assert not girar.colliderect(pausa)
