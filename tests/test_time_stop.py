"""Contratos da parada do tempo (`systems/time_stop.py`).

Lógica pura (§16): a máquina de fases não toca em pygame nem na cena. O tremor
é testado à parte contra um `EntityManager` real, porque o que importa nele é
justamente não corromper a posição das entidades.
"""

import pygame
import pytest

from game.core.config import config as Config
from game.systems.entity_manager import EntityManager
from game.systems.time_stop import TimeStopState


def avanca(estado: TimeStopState, segundos: float, passo: float = 1 / 60) -> None:
    restante = segundos
    while restante > 1e-9:
        estado.update(min(passo, restante))
        restante -= passo


class TestFases:
    def test_comeca_ocioso_em_velocidade_normal(self):
        e = TimeStopState()
        assert not e.is_active
        assert e.enemy_time_scale == 1.0

    def test_trigger_congela(self):
        e = TimeStopState()
        e.trigger(5.0)
        assert e.is_frozen
        assert e.enemy_time_scale == 0.0

    def test_congelamento_dura_o_tempo_pedido(self):
        e = TimeStopState()
        e.trigger(2.0)
        avanca(e, 1.9)
        assert e.is_frozen
        avanca(e, 0.2)
        assert not e.is_frozen

    def test_fim_do_congelamento_entra_em_recuperacao(self):
        e = TimeStopState()
        e.trigger(1.0)
        avanca(e, 1.1)
        assert e.is_recovering
        assert e.is_active

    def test_recuperacao_termina_em_velocidade_normal(self):
        e = TimeStopState()
        e.trigger(1.0)
        avanca(e, 1.0 + Config.TIME_STOP_RECOVERY_DURATION + 0.2)
        assert not e.is_active
        assert e.enemy_time_scale == 1.0

    def test_reset_zera_sem_deixar_rampa(self):
        """A rampa não pode atravessar a virada de fase: os inimigos da fase
        seguinte nasceriam em câmera lenta sem motivo visível."""
        e = TimeStopState()
        e.trigger(1.0)
        avanca(e, 1.1)
        assert e.is_recovering
        e.reset()
        assert not e.is_active
        assert e.enemy_time_scale == 1.0

    def test_recoletar_renova_sem_acumular(self):
        e = TimeStopState()
        e.trigger(5.0)
        avanca(e, 4.0)  # sobra 1.0
        e.trigger(5.0)
        avanca(e, 4.5)
        assert e.is_frozen, "deveria ter renovado para 5s, não somado"
        avanca(e, 0.6)
        assert not e.is_frozen, "não pode ter acumulado 10s"

    def test_recoletar_durante_a_recuperacao_cancela_a_rampa(self):
        e = TimeStopState()
        e.trigger(1.0)
        avanca(e, 1.5)  # em plena recuperação
        e.trigger(5.0)
        assert e.is_frozen
        assert e.enemy_time_scale == 0.0
        assert e.recovery_ratio == 0.0


class TestRampaDeVolta:
    def test_escala_e_monotonica_e_nunca_extrapola(self):
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.6)

        anterior = -1.0
        for _ in range(400):
            escala = e.enemy_time_scale
            assert 0.0 <= escala <= 1.0
            assert escala >= anterior - 1e-9, "a volta não pode desacelerar"
            anterior = escala
            e.update(1 / 60)
        assert e.enemy_time_scale == 1.0

    def test_volta_comeca_devagar_e_acelera(self):
        """Ease-in: o pedido é 'recuperando as forças'.

        Uma rampa linear já se lê como velocidade normal na primeira metade —
        na metade do tempo o inimigo estaria a 50%. Com ease-in quadrático ele
        está a 25%, e a maior parte do ganho acontece no fim.
        """
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.5)

        metade = Config.TIME_STOP_RECOVERY_DURATION / 2
        avanca(e, metade)
        assert e.enemy_time_scale < 0.4, "na metade do tempo ainda deve estar lento"

    def test_nao_ha_salto_no_instante_do_descongelamento(self):
        """O ponto do pedido: nada de voltar à velocidade cheia de um frame
        para o outro."""
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.49)
        assert e.enemy_time_scale == 0.0
        e.update(1 / 60)  # primeiro frame descongelado
        assert e.enemy_time_scale < 0.05


class TestAvisoDeFim:
    def test_sem_aviso_no_comeco_do_congelamento(self):
        e = TimeStopState()
        e.trigger(Config.TIME_STOP_WARNING_TIME + 2.0)
        assert e.warning_ratio == 0.0
        assert e.tremor_pixels == 0.0

    def test_aviso_sobe_ate_um_no_fim(self):
        e = TimeStopState()
        e.trigger(Config.TIME_STOP_WARNING_TIME + 1.0)
        avanca(e, 1.0)  # entra exatamente na janela de aviso

        anterior = -1.0
        vistos: list[float] = []
        while e.is_frozen:
            r = e.warning_ratio
            assert 0.0 <= r <= 1.0
            assert r >= anterior - 1e-9, "o aviso não pode retroceder"
            anterior = r
            vistos.append(r)
            e.update(1 / 60)
        assert max(vistos) > 0.9, "deveria chegar perto de 1 antes de descongelar"

    def test_aviso_zera_quando_descongela(self):
        e = TimeStopState()
        e.trigger(0.5)
        avanca(e, 0.6)
        assert e.warning_ratio == 0.0
        assert e.tremor_pixels == 0.0

    def test_tremor_e_sutil(self):
        """'Sem comprometer a sensação de que ainda estão paralisados': a
        amplitude é de um dígito de pixels, e no auge do aviso o inimigo segue
        com escala de tempo ZERO — ele vibra, não anda."""
        e = TimeStopState()
        e.trigger(Config.TIME_STOP_WARNING_TIME)
        avanca(e, Config.TIME_STOP_WARNING_TIME * 0.99)
        assert e.is_frozen
        assert e.enemy_time_scale == 0.0
        assert 0.0 < e.tremor_pixels <= Config.TIME_STOP_TREMOR_PIXELS
        assert e.tremor_pixels < 10.0


class _Inimigo:
    """Dublê com a mesma superfície posicional dos inimigos reais."""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.rect = pygame.Rect(int(x), int(y), 20, 20)
        self.dead = False


class TestTremorNasEntidades:
    def _manager(self, n: int = 8) -> tuple[EntityManager, list[_Inimigo]]:
        em = EntityManager()
        inimigos = [_Inimigo(100.0 + i * 30, 200.0) for i in range(n)]
        em.enemies.extend(inimigos)
        return em, inimigos

    def test_tremor_desloca_os_inimigos(self):
        em, inimigos = self._manager()
        originais = [(e.x, e.y) for e in inimigos]
        em.apply_freeze_tremor(2.0, phase=0.3)
        assert any(
            (e.x, e.y) != orig for e, orig in zip(inimigos, originais)
        ), "nenhum inimigo se moveu"

    def test_inimigos_nao_tremem_em_bloco(self):
        """Deslocamento igual para todos leria como screen shake, não como
        'cada um preso tentando se soltar'."""
        em, inimigos = self._manager()
        originais = [(e.x, e.y) for e in inimigos]
        em.apply_freeze_tremor(2.0, phase=0.3)
        deltas = {
            (round(e.x - ox, 4), round(e.y - oy, 4))
            for e, (ox, oy) in zip(inimigos, originais)
        }
        assert len(deltas) > 1

    def test_tremor_nao_acumula_ao_longo_dos_frames(self):
        """O risco real: aplicar deslocamento por frame faria os congelados
        passearem pela tela em vez de vibrar no lugar."""
        em, inimigos = self._manager()
        originais = [(e.x, e.y) for e in inimigos]

        fase = 0.0
        for _ in range(600):
            fase += 1 / 60
            em.apply_freeze_tremor(2.0, phase=fase)
            for e, (ox, oy) in zip(inimigos, originais):
                assert abs(e.x - ox) <= 2.001
                assert abs(e.y - oy) <= 2.001

    def test_amplitude_zero_assenta_os_inimigos_no_lugar(self):
        """Ao descongelar, os inimigos voltam ao lugar de origem.

        `x`/`y` voltam a menos de erro de ponto flutuante, não bit a bit: o
        tremor desfaz o deslocamento SOMANDO o inverso, e `(a + d) - d` não é
        exatamente `a` em float. É deliberado — guardar o deslocamento (em vez
        da posição original) é o que deixa o tremor conviver com qualquer outra
        coisa que mova o inimigo no meio, em vez de tê-lo de volta à força.
        Depois de 120 frames a deriva fica na casa de 1e-13 px.

        O `rect`, que é quem manda na colisão e no desenho, volta EXATO — é
        inteiro e o deslocamento é aplicado arredondado.
        """
        em, inimigos = self._manager()
        originais = [(e.x, e.y) for e in inimigos]
        rects = [e.rect.topleft for e in inimigos]

        fase = 0.0
        for _ in range(120):
            fase += 1 / 60
            em.apply_freeze_tremor(2.0, phase=fase)
        em.apply_freeze_tremor(0.0, phase=fase)

        for e, (ox, oy) in zip(inimigos, originais):
            assert e.x == pytest.approx(ox, abs=1e-6)
            assert e.y == pytest.approx(oy, abs=1e-6)
        for e, topleft in zip(inimigos, rects):
            assert e.rect.topleft == topleft

    def test_rect_nao_deriva_ao_longo_do_tremor(self):
        """O `rect` é inteiro e é ele quem manda na colisão e no desenho.

        Bug real que este teste pegou: o passo do rect vinha de
        `round(delta_do_frame)`, e o erro de arredondamento ACUMULAVA — 2px de
        deriva em 120 frames. Na tela, congelados escorregando.
        """
        em, inimigos = self._manager()
        originais = [e.rect.topleft for e in inimigos]

        fase = 0.0
        for _ in range(600):
            fase += 1 / 60
            em.apply_freeze_tremor(2.0, phase=fase)
            for e, (ox, oy) in zip(inimigos, originais):
                assert abs(e.rect.x - ox) <= 2
                assert abs(e.rect.y - oy) <= 2

    def test_lista_vazia_nao_quebra(self):
        em = EntityManager()
        em.apply_freeze_tremor(2.0, phase=1.0)
        em.apply_freeze_tremor(0.0, phase=1.0)
