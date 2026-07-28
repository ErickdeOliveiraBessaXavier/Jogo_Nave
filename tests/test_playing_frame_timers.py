"""Os timers de frame da `PlayingScene` rodam em TODO frame.

Regressão real: o refactor da parada do tempo inseriu `_apply_time_stop_music`
no meio de `_update_timers`, e a cauda do método (timer de preparação, pop-up
de nível, multiplicador, shake, vinheta, espera da transição de fase) acabou
dentro do método novo — atrás do early-out `if not is_active: return`.

Sem power-up de parada do tempo, nada daquilo rodava: a introdução da fase
nunca terminava, a contagem nunca começava e a nave nunca ganhava controle.
Nem o lint nem os testes de `TimeStopState` pegaram, porque a lógica pura
continuava correta — o que quebrou foi a **ligação** na cena.

O teste é de fiação: chama `_update_timers` num stub mínimo (sem instanciar o
jogo) e exige que os timers de frame avancem com a parada do tempo INATIVA.
"""

from types import SimpleNamespace

import pytest

from game.core.sound import sound_manager
from game.events import game_events as events
from game.scenes.playing import PlayingScene
from game.systems.time_stop import TimeStopPhase, TimeStopState


@pytest.fixture(autouse=True)
def _duck_limpo():
    """`_apply_time_stop_music` escreve no `sound_manager`, que é singleton —
    sem isto o duck da parada do tempo vaza para o arquivo de teste seguinte."""
    yield
    sound_manager.set_music_duck("time_stop", 1.0)


class _CenaStub:
    """Só o que `_update_timers` toca — nada de pygame nem de cena real."""

    _update_timers = PlayingScene._update_timers
    _apply_time_stop_music = PlayingScene._apply_time_stop_music
    _emit_time_stop_cues = PlayingScene._emit_time_stop_cues

    def __init__(self) -> None:
        self.time_stop = TimeStopState()
        self._time_stop_phase = 0.0
        self._time_stop_music_clock = 0.0
        self._time_stop_last_phase = TimeStopPhase.IDLE
        self.shooting = SimpleNamespace(update=lambda dt: None)
        self.frames_de_timer = 0
        self.dt_recebido = 0.0
        self.sons: list[str] = []
        self.app = SimpleNamespace(event_bus=SimpleNamespace(emit=self._emit))

    def _emit(self, evento: object) -> None:
        if isinstance(evento, events.PlaySound):
            self.sons.append(evento.sound_name)

    def _update_frame_timers(self, dt: float) -> None:
        self.frames_de_timer += 1
        self.dt_recebido += dt


def test_timers_de_frame_rodam_sem_parada_de_tempo():
    """O caminho comum: nenhum power-up ativo, e mesmo assim tudo avança."""
    cena = _CenaStub()
    assert not cena.time_stop.is_active

    for _ in range(10):
        cena._update_timers(1 / 60)

    assert cena.frames_de_timer == 10, "a cauda de timers voltou a ser engolida"
    assert cena.dt_recebido > 0.0


def test_timers_de_frame_rodam_durante_a_parada_de_tempo():
    cena = _CenaStub()
    cena.time_stop.trigger(2.0)

    for _ in range(10):
        cena._update_timers(1 / 60)

    assert cena.frames_de_timer == 10


def test_o_envelope_de_musica_nao_consome_a_cauda():
    """Guarda direta contra a forma do bug.

    `_apply_time_stop_music` tem early-out; se algum timer de frame voltar para
    dentro dele, este teste (que roda o método isolado, com o efeito inativo)
    continua passando — mas o de cima quebra. Aqui só travamos que o early-out
    existe e não faz trabalho no caminho comum.
    """
    cena = _CenaStub()
    cena._apply_time_stop_music(1 / 60)

    assert cena._time_stop_music_clock == 0.0
    assert cena.frames_de_timer == 0


# ---------------------------------------------------------------------------
# Cues de áudio da parada do tempo (desacelerando / acelerando)
# ---------------------------------------------------------------------------


def _roda(cena: _CenaStub, segundos: float, passo: float = 1 / 60) -> None:
    restante = segundos
    while restante > 1e-9:
        cena._update_timers(min(passo, restante))
        restante -= passo


class TestCuesDaParadaDoTempo:
    def test_ocioso_nao_toca_nada(self):
        cena = _CenaStub()
        _roda(cena, 1.0)
        assert cena.sons == []

    def test_congelar_toca_o_desacelerando_uma_vez(self):
        cena = _CenaStub()
        cena.time_stop.trigger(2.0)
        _roda(cena, 1.0)
        assert cena.sons == ["time_stop_in"]

    def test_descongelar_toca_o_acelerando(self):
        cena = _CenaStub()
        cena.time_stop.trigger(0.5)
        _roda(cena, 0.5 + 0.2)  # entra na rampa de recuperação
        assert cena.sons == ["time_stop_in", "time_stop_out"]

    def test_fim_da_rampa_nao_toca_um_terceiro_cue(self):
        """`RECOVERING → IDLE` é o efeito acabando, não um evento audível."""
        from game.core.config import config as Config

        cena = _CenaStub()
        cena.time_stop.trigger(0.5)
        _roda(cena, 0.5 + Config.TIME_STOP_RECOVERY_DURATION + 0.5)
        assert cena.sons == ["time_stop_in", "time_stop_out"]
        assert cena.time_stop.phase is TimeStopPhase.IDLE

    def test_repegar_durante_o_congelamento_nao_repete_o_cue(self):
        """`trigger` renova a duração; a fase não virou, então nada re-soa."""
        cena = _CenaStub()
        cena.time_stop.trigger(4.0)
        _roda(cena, 1.0)
        cena.time_stop.trigger(4.0)
        _roda(cena, 1.0)
        assert cena.sons == ["time_stop_in"]

    def test_reset_nao_soa_como_recuperacao(self):
        """Cancelar o efeito (troca de fase, game over) pula direto para IDLE.

        Sem o guarda `anterior is FROZEN`, o cancelamento tocaria o
        "acelerando" — um som de mundo voltando à vida numa tela que já trocou.
        """
        cena = _CenaStub()
        cena.time_stop.trigger(4.0)
        _roda(cena, 1.0)
        cena.time_stop.reset()
        _roda(cena, 0.5)
        assert cena.sons == ["time_stop_in"]

    def test_dois_congelamentos_seguidos_tocam_o_par_duas_vezes(self):
        cena = _CenaStub()
        cena.time_stop.trigger(0.3)
        _roda(cena, 0.3 + 0.1)
        cena.time_stop.trigger(0.3)
        _roda(cena, 0.3 + 0.1)
        assert cena.sons == [
            "time_stop_in",
            "time_stop_out",
            "time_stop_in",
            "time_stop_out",
        ]
