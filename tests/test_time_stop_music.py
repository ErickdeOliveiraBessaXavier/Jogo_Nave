"""Envelope de música da parada do tempo + ducking por fonte.

Duas partes:

- o **envelope** (`TimeStopState.music_factor`) é lógica pura e é testado como
  tal;
- o **ducking por fonte** é testado pelo `music_target_volume()` do
  `sound_manager`, não pelos campos. É a regra do §18: o número certo num campo
  não prova nada sobre o que o jogador ouve — foi exatamente esse o bug que
  originou `test_audio_config.py`.

Nada aqui abre dispositivo de áudio: `music_target_volume` é aritmética sobre o
estado do manager, e `set_music_duck` só toca no mixer se ele estiver aberto.
"""

import pytest

from game.core.config import config as Config
from game.core.sound import sound_manager
from game.core.sound_config import VOLUME_CONFIG
from game.systems.time_stop import TimeStopState


def avanca(estado: TimeStopState, segundos: float, passo: float = 1 / 60) -> None:
    restante = segundos
    while restante > 1e-9:
        estado.update(min(passo, restante))
        restante -= passo


@pytest.fixture(autouse=True)
def _duck_limpo():
    """O `sound_manager` é singleton — sem isso um teste contamina o próximo."""
    yield
    for fonte in ("time_stop", "game_over", "default"):
        sound_manager.set_music_duck(fonte, 1.0)
    sound_manager.load_config(
        VOLUME_CONFIG["music"], VOLUME_CONFIG["sfx"], VOLUME_CONFIG["shots"]
    )


# ---------------------------------------------------------------------------
# Ducking por fonte
# ---------------------------------------------------------------------------


class TestDuckingPorFonte:
    def test_sem_fonte_nao_ha_atenuacao(self):
        assert sound_manager.music_duck_factor == 1.0

    def test_uma_fonte_atenua_o_volume_real_da_musica(self):
        cheio = sound_manager.music_target_volume()
        sound_manager.set_music_duck("time_stop", 0.08)
        assert sound_manager.music_target_volume() == pytest.approx(cheio * 0.08)

    def test_fontes_se_compoem_por_produto(self):
        sound_manager.set_music_duck("game_over", 0.5)
        sound_manager.set_music_duck("time_stop", 0.2)
        assert sound_manager.music_duck_factor == pytest.approx(0.1)

    def test_soltar_uma_fonte_preserva_a_outra(self):
        """O bug que o refactor corrige.

        Com um float único, `duck_music(False)` do Game Over escrevia 1.0 e
        apagava o duck da parada do tempo — morrer durante o congelamento
        devolvia o volume cheio no meio do efeito.
        """
        sound_manager.set_music_duck("time_stop", 0.08)
        sound_manager.duck_music(True, source="game_over")
        sound_manager.duck_music(False, source="game_over")

        assert sound_manager.music_duck_factor == pytest.approx(0.08)

    def test_soltar_a_ultima_fonte_restaura_o_volume_cheio(self):
        cheio = sound_manager.music_target_volume()
        sound_manager.set_music_duck("time_stop", 0.08)
        sound_manager.set_music_duck("time_stop", 1.0)
        assert sound_manager.music_target_volume() == pytest.approx(cheio)

    def test_fator_maior_que_um_nao_amplifica(self):
        sound_manager.set_music_duck("time_stop", 3.0)
        assert sound_manager.music_duck_factor == 1.0

    def test_duck_convive_com_mudanca_de_volume_do_jogador(self):
        """O duck é multiplicativo, então segue valendo se o jogador mexer no
        slider durante o efeito."""
        sound_manager.set_music_duck("time_stop", 0.08)
        sound_manager.load_config(0.4, 0.5, 0.5)
        esperado = min(1.0, 0.4 * sound_manager.master_volume) * 0.08
        assert sound_manager.music_target_volume() == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_sem_efeito_a_musica_fica_intocada(self):
        e = TimeStopState()
        assert e.music_factor(0.0) == 1.0

    def test_ativacao_derruba_a_musica_rapido(self):
        e = TimeStopState()
        e.trigger(5.0)
        assert e.music_factor(0.0) == pytest.approx(1.0), "não pode cair de degrau"
        avanca(e, 0.2)
        assert e.music_factor(0.2) < 0.15, "deveria estar quase muda"

    def test_a_queda_e_gradual_e_nao_um_degrau(self):
        """Degrau de volume vira clique audível. A queda é rápida, não seca."""
        e = TimeStopState()
        e.trigger(5.0)
        avanca(e, 1 / 60)
        primeiro = e.music_factor(1 / 60)
        assert 0.1 < primeiro < 1.0, f"caiu de uma vez para {primeiro}"

    def test_permanece_baixa_durante_o_congelamento(self):
        e = TimeStopState()
        e.trigger(4.0)
        avanca(e, 0.5)
        while e.is_frozen:
            assert e.music_factor(0.0) < 0.15
            e.update(1 / 60)

    def test_volta_termina_em_volume_cheio(self):
        e = TimeStopState()
        e.trigger(1.0)
        avanca(e, 1.0 + Config.TIME_STOP_RECOVERY_DURATION + 0.5)
        assert not e.is_active
        assert e.music_factor(0.0) == 1.0

    def test_volta_nao_e_instantanea(self):
        """O pedido explícito: a música não pode voltar de uma vez."""
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.5)  # primeiro instante da recuperação
        assert e.music_factor(0.0) < 0.3

    def test_tendencia_da_volta_e_crescente(self):
        """O tremolo faz o valor oscilar frame a frame, então a monotonia vale
        na TENDÊNCIA (média por janela), não em cada amostra."""
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.5)

        janelas: list[float] = []
        while e.is_active:
            amostras = []
            for _ in range(20):
                if not e.is_active:
                    break
                amostras.append(e.music_factor(e.recovery_ratio * 3.0))
                e.update(1 / 60)
            if amostras:
                janelas.append(sum(amostras) / len(amostras))

        assert len(janelas) >= 3
        for anterior, seguinte in zip(janelas, janelas[1:]):
            assert seguinte > anterior - 0.05, f"a volta recuou: {janelas}"
        assert janelas[-1] > janelas[0] + 0.3

    def test_envelope_nunca_sai_da_faixa(self):
        e = TimeStopState()
        e.trigger(2.0)
        relogio = 0.0
        for _ in range(600):
            relogio += 1 / 60
            assert 0.0 <= e.music_factor(relogio) <= 1.0
            e.update(1 / 60)


class TestTremolo:
    def test_tremolo_oscila_durante_a_volta(self):
        """A única 'distorção' possível só com amplitude: o volume cambaleia.

        `pygame.mixer.music` não expõe pitch nem filtro, então wow-and-flutter
        por modulação de amplitude é o substituto — e precisa de fato oscilar.
        """
        e = TimeStopState()
        e.trigger(0.5)
        # Entra na rampa e avança até ~30% dela. Parar exatamente na fronteira
        # deixaria `is_frozen` ainda verdadeiro por erro de float, e no instante
        # ZERO da rampa a oscilação é proporcionalmente pequena (o envelope
        # ainda está no piso de 8%).
        avanca(e, 0.5 + Config.TIME_STOP_RECOVERY_DURATION * 0.3)
        assert e.is_recovering

        # Amostra num instante fixo da rampa, variando só o relógio do tremolo:
        # isola a oscilação da subida do envelope.
        valores = [e.music_factor(t / 60.0) for t in range(30)]
        assert max(valores) - min(valores) > 0.05, "não há oscilação audível"

    def test_tremolo_some_ao_fim_da_rampa(self):
        """Senão sobraria um trêmulo audível na música já normalizada."""
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.5 + Config.TIME_STOP_RECOVERY_DURATION * 0.97)

        valores = [e.music_factor(t / 60.0) for t in range(30)]
        assert max(valores) - min(valores) < 0.05, "ainda tremendo no fim"

    def test_frequencia_cabe_na_taxa_de_frames(self):
        """A 60fps o Nyquist é 30Hz; acima disso a modulação alia e vira
        chiado em vez de oscilação."""
        from game.systems.time_stop import _MUSIC_TREMOLO_HZ

        assert _MUSIC_TREMOLO_HZ <= 15.0
