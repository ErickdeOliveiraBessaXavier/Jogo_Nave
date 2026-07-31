"""Offset de toque — a nave voa ACIMA do dedo, não embaixo dele.

No mouse o ponteiro é um pixel e desaparece sob a nave. No celular o ponteiro é
um dedo: uma mancha de contato de ~1cm que cobre a nave inteira, e o jogador
pilota às cegas exatamente aquilo que precisa ver. Deslocar o alvo verticalmente
devolve a nave para cima do polegar sem tocar em mais nada da física.

O que estes testes travam:

1. **é opt-in** — desligado, a mira continua sendo o ponteiro cru. No desktop não
   há o que compensar, e o build web roda nos dois (navegador de PC com mouse e
   celular com dedo), então quem decide é o jogador, não o `sys.platform`;
2. **desloca para CIMA** — o sinal é a coisa mais fácil de inverter aqui, e
   invertido ele piora exatamente o problema que veio resolver;
3. **vale só no caminho do ponteiro** — teclado e gamepad não têm dedo cobrindo
   nada;
4. **entra ANTES da inversão de controles** (debuff de Toxina). O offset corrige
   o DISPOSITIVO, não a intenção: aplicado depois, o controle invertido mandaria
   a nave para baixo do dedo de novo;
5. **sobrevive ao round-trip do JSON** de preferências.

O ponteiro é controlado por PATCH em `pygame.mouse.get_pos`, e não por
`set_pos`: o driver de vídeo dummy dos testes headless ignora `set_pos` em
silêncio e devolve sempre (0, 0), então toda medição sairia do mesmo ponto sem
nenhum erro para denunciar.
"""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from game.core.preferences import UserPreferences
from game.core.ship_types import get_ship_profile
from game.entities.player.ship import Ship
from game.entities.player.ship_movement import TOUCH_OFFSET_Y


def _nave(**kwargs) -> Ship:
    nave = Ship(600.0, 500.0, profile=get_ship_profile("padrao"), **kwargs)
    nave.y = 300.0
    return nave


@contextmanager
def _ponteiro_em(x: float, y: float):
    with patch("pygame.mouse.get_pos", return_value=(int(x), int(y))):
        yield


def _passo(ship: Ship, pointer: tuple[float, float]) -> float:
    """Quanto a nave se move no eixo Y num passo, com o ponteiro em `pointer`.

    Mede o deslocamento REAL pela fachada pública da `Ship` (§9), em vez de
    espiar o cálculo interno: é o comportamento que importa, e o teste não
    quebra se a mola for reescrita.
    """
    antes = ship.y
    with _ponteiro_em(*pointer):
        ship.move(set(), 1 / 60)
    return ship.y - antes


def _centro(ship: Ship) -> tuple[float, float]:
    return ship.x + ship.w / 2, ship.y + ship.h / 2


class TestOptIn:
    def test_desligado_por_padrao(self):
        assert _nave().touch_offset is False

    def test_desligado_mira_o_ponteiro_cru(self):
        """A regressão que mais importa: ninguém no desktop pode sentir isto.

        Ponteiro na altura exata do centro da nave → ela não sobe nem desce.
        """
        ship = _nave(mouse_control=True)

        assert _passo(ship, _centro(ship)) == pytest.approx(0.0, abs=0.5)


class TestDirecao:
    def test_ligado_a_nave_sobe_em_relacao_ao_dedo(self):
        """Com o dedo na altura do centro da nave, ela precisa SUBIR — é isso
        que a tira de baixo do polegar. Descer é o bug que este teste pega."""
        ship = _nave(mouse_control=True, touch_offset=True)

        assert _passo(ship, _centro(ship)) < 0.0, (
            "a nave desceu: o sinal do offset está invertido"
        )

    def test_o_ponto_de_equilibrio_fica_uma_folga_acima_do_dedo(self):
        """Onde a nave PARA: com o dedo a `TOUCH_OFFSET_Y` abaixo do centro."""
        ship = _nave(mouse_control=True, touch_offset=True)
        cx, cy = _centro(ship)

        assert _passo(ship, (cx, cy + TOUCH_OFFSET_Y)) == pytest.approx(0.0, abs=0.5)

    def test_a_folga_e_visivel_o_bastante(self):
        """Uma altura de nave só encosta a base dela no dedo, e a mancha de
        contato ainda cobre metade. O valor tem que passar disso para o ajuste
        ter servido para alguma coisa."""
        assert TOUCH_OFFSET_Y > _nave().h


class TestEscopo:
    def test_sem_mouse_control_nao_ha_offset(self):
        """Teclado e gamepad não têm dedo cobrindo nada. O offset só existe no
        caminho que lê a posição do ponteiro."""
        ship = _nave(mouse_control=False, touch_offset=True)

        assert _passo(ship, _centro(ship)) == pytest.approx(0.0, abs=0.5)

    def test_entra_ANTES_da_inversao_de_controles(self):
        """Debuff de Toxina espelha o alvo no centro da tela.

        O offset corrige o DISPOSITIVO (onde o dedo está), não a intenção, então
        entra ANTES do espelho — e é isso que este teste distingue. Sob inversão:

        - **antes** (correto): o espelho leva junto o deslocamento, e o alvo cai
          `TOUCH_OFFSET_Y` ABAIXO do alvo sem offset;
        - **depois** (errado): o deslocamento sobrevive ao espelho e o alvo sobe,
          jogando a nave para baixo do dedo justamente quando o jogador já está
          lutando contra o controle.

        Comparar só "difere de" não distinguiria os dois — os dois diferem. O
        que separa é o SINAL.
        """
        com = _nave(mouse_control=True, touch_offset=True)
        sem = _nave(mouse_control=True, touch_offset=False)
        for s in (com, sem):
            s.invert_controls_timer = 5.0

        dedo = (700.0, 500.0)
        assert _passo(com, dedo) > _passo(sem, dedo), (
            "sob inversão a nave subiu em vez de descer: o offset está sendo "
            "aplicado DEPOIS do espelho"
        )


class TestPreferencia:
    def test_sobrevive_ao_round_trip(self, tmp_path: Path):
        prefs = UserPreferences(tmp_path / "prefs.json")
        assert prefs.touch_offset is False

        prefs.touch_offset = True
        prefs.save()

        assert UserPreferences(tmp_path / "prefs.json").touch_offset is True

    def test_reset_volta_ao_default(self, tmp_path: Path):
        prefs = UserPreferences(tmp_path / "prefs.json")
        prefs.touch_offset = True
        prefs.reset()
        assert prefs.touch_offset is False

    def test_a_tela_de_configuracoes_expoe_o_toggle(self):
        """Sem entrada na tela, a preferência existe e ninguém consegue ligar —
        e no celular não há teclado para um atalho salvar o dia."""
        from game.core.i18n import t
        from game.scenes.settings import SettingsScene

        assert t("settings.toggle.touch_offset") != "settings.toggle.touch_offset"
        # O toggle tem que estar na ORDEM de layout, senão nasce sem rect.
        fonte = Path(SettingsScene.__module__.replace(".", "/") + ".py").read_text(
            encoding="utf-8"
        )
        assert '"touch_offset",' in fonte
