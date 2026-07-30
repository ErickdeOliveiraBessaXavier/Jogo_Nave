"""Contratos da parada do tempo (`systems/time_stop.py`).

Lógica pura (§16): a máquina de fases não toca em pygame nem na cena. O tremor
é testado à parte contra um `EntityManager` real, porque o que importa nele é
justamente não corromper a posição das entidades.
"""

import pathlib
import struct
import wave

import pygame
import pytest

from game.core.config import config as Config
from game.core.sfx_manager import discover_sfx
from game.core.sound_config import AUDIO_SFX_ROOT
from game.systems.entity_manager import EntityManager
from game.systems import time_stop
from game.systems.time_stop import TimeStopPhase, TimeStopState


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


class TestRampaDeEntrada:
    """`entry_ratio` — envelope de ABERTURA, só do feedback visual.

    O congelamento é instantâneo (é o ponto do power-up); o que sobe em rampa é
    a moldura da HUD, para ela crescer na tela em vez de piscar pronta no frame
    mais movimentado do efeito.
    """

    def test_sem_efeito_a_abertura_e_zero(self):
        assert TimeStopState().entry_ratio == 0.0

    def test_comeca_do_zero_no_instante_do_trigger(self):
        e = TimeStopState()
        e.trigger(5.0)
        assert e.entry_ratio == pytest.approx(0.0)

    def test_sobe_ate_um_e_satura(self):
        e = TimeStopState()
        e.trigger(5.0)
        avanca(e, 0.18)
        meio = e.entry_ratio
        assert 0.0 < meio < 1.0, f"deveria estar subindo, veio {meio}"
        avanca(e, 1.0)
        assert e.entry_ratio == 1.0

    def test_e_monotonica(self):
        """Recuar faria a moldura piscar durante a própria abertura."""
        e = TimeStopState()
        e.trigger(5.0)
        anterior = e.entry_ratio
        for _ in range(60):
            e.update(1 / 60)
            assert e.entry_ratio >= anterior - 1e-9
            anterior = e.entry_ratio

    def test_vale_um_durante_a_recuperacao(self):
        """Na volta quem comanda é `recovery_ratio`; a abertura já aconteceu.

        Se caísse a zero aqui, a moldura sumiria de estalo no descongelamento
        em vez de se dissolver.
        """
        e = TimeStopState()
        e.trigger(0.4)
        avanca(e, 0.4 + 0.1)
        assert e.is_recovering
        assert e.entry_ratio == 1.0

    def test_o_congelamento_em_si_nao_tem_rampa(self):
        """A rampa é SÓ visual: os inimigos param no primeiro frame."""
        e = TimeStopState()
        e.trigger(5.0)
        assert e.entry_ratio < 1.0
        assert e.enemy_time_scale == 0.0


class TestRampaDeSaida:
    """`exit_ratio` — envelope de FECHAMENTO, cronometrado pelo SFX."""

    def test_congelado_esta_cheio(self):
        e = TimeStopState()
        e.trigger(3.0)
        assert e.exit_ratio == 1.0

    def test_sem_efeito_e_zero(self):
        assert TimeStopState().exit_ratio == 0.0

    def test_segura_durante_o_silencio_inicial_do_som(self):
        """O `time_stop_out` tem 0,47s de silêncio antes do gesto.

        Dissolver já nesse trecho deixaria a moldura quase apagada antes de o
        som começar — exatamente a dessincronia que a rampa existe para evitar.
        """
        e = TimeStopState()
        e.trigger(0.3)
        avanca(e, 0.3 + 0.30)  # dentro do silêncio
        assert e.is_recovering
        assert e.exit_ratio == 1.0

    def test_dissolve_depois_do_hold(self):
        e = TimeStopState()
        e.trigger(0.3)
        avanca(e, 0.3 + 0.95)  # ~meio do gesto
        meio = e.exit_ratio
        assert 0.0 < meio < 1.0, f"deveria estar dissolvendo, veio {meio}"

    def test_zera_ao_fim_do_som_e_nao_da_rampa_de_inimigos(self):
        """O ponto do ajuste: a moldura some com o SOM (1,48s), não com a
        retomada dos inimigos (3,0s)."""
        e = TimeStopState()
        e.trigger(0.3)
        avanca(e, 0.3 + 1.55)
        assert e.exit_ratio == 0.0
        assert e.is_recovering, "a rampa dos inimigos ainda tem de estar correndo"
        assert e.enemy_time_scale < 1.0

    def test_e_monotonica(self):
        e = TimeStopState()
        e.trigger(0.3)
        avanca(e, 0.3)
        anterior = e.exit_ratio
        while e.is_recovering:
            e.update(1 / 60)
            assert e.exit_ratio <= anterior + 1e-9
            anterior = e.exit_ratio


class TestSincroniaComOsEfeitosSonoros:
    """Os envelopes visuais são cronometrados pelos WAVs — o teste lê os WAVs.

    Trocar `time_stop_in`/`time_stop_out` por gravações de outra
    duração dessincroniza a moldura em silêncio: nada quebra, o jogo só passa a
    parecer errado. Este teste transforma isso em falha de CI, com a instrução
    de reajustar as constantes.
    """

    TOLERANCIA = 0.12  # s

    @staticmethod
    def _gesto(chave: str) -> tuple[float, float, float]:
        """(silêncio inicial, fim do trecho audível, duração do arquivo).

        Resolve pela CHAVE do SFX (`discover_sfx`), não por caminho fixo: a
        subpasta em que o arquivo mora é organização humana e pode mudar sem
        que a chave mude — um caminho literal aqui quebraria na próxima
        reorganização, que é exatamente o que aconteceu com
        `game/assets/sounds/sfx/ui`.
        """
        raiz = pathlib.Path(__file__).resolve().parent.parent / AUDIO_SFX_ROOT
        caminho = discover_sfx(str(raiz))[chave]
        with wave.open(str(caminho)) as w:
            sr, canais, quadros = w.getframerate(), w.getnchannels(), w.getnframes()
            cru = w.readframes(quadros)
        amostras = struct.unpack("<%dh" % (len(cru) // 2), cru)
        mono = [
            max(abs(amostras[i]), abs(amostras[i + 1]))
            for i in range(0, len(amostras) - 1, canais)
        ]
        pico = max(mono) or 1
        limite = pico * (10 ** (-45 / 20))  # -45 dBFS
        janela = sr // 100  # 10ms
        niveis = [max(mono[i : i + janela]) for i in range(0, len(mono), janela)]
        inicio = next(i for i, v in enumerate(niveis) if v > limite) / 100.0
        fim = (
            len(niveis) - next(i for i, v in enumerate(reversed(niveis)) if v > limite)
        ) / 100.0
        return inicio, fim, quadros / sr

    def test_a_entrada_dura_o_gesto_do_desacelerando(self):
        inicio, fim, _ = self._gesto("time_stop_in")
        assert inicio < 0.05, "esse SFX deveria começar imediatamente"
        assert abs(time_stop._VISUAL_ENTRY_RAMP - fim) < self.TOLERANCIA, (
            f"a moldura abre em {time_stop._VISUAL_ENTRY_RAMP}s mas o som cala em "
            f"{fim}s — reajuste _VISUAL_ENTRY_RAMP"
        )

    def test_a_saida_segura_o_silencio_e_dura_o_gesto_do_acelerando(self):
        inicio, fim, _ = self._gesto("time_stop_out")
        assert abs(time_stop._VISUAL_EXIT_HOLD - inicio) < self.TOLERANCIA, (
            f"a moldura segura {time_stop._VISUAL_EXIT_HOLD}s mas o som só começa "
            f"em {inicio}s — reajuste _VISUAL_EXIT_HOLD"
        )
        assert abs(time_stop._VISUAL_EXIT_RAMP - (fim - inicio)) < self.TOLERANCIA, (
            f"a moldura dissolve em {time_stop._VISUAL_EXIT_RAMP}s mas o gesto dura "
            f"{fim - inicio:.2f}s — reajuste _VISUAL_EXIT_RAMP"
        )

    def test_o_fechamento_cabe_dentro_da_rampa_de_inimigos(self):
        """Se o áudio passar de `TIME_STOP_RECOVERY_DURATION`, a moldura seria
        cortada no meio pelo fim da recuperação."""
        total = time_stop._VISUAL_EXIT_HOLD + time_stop._VISUAL_EXIT_RAMP
        assert total <= Config.TIME_STOP_RECOVERY_DURATION


class TestContinuidadeDaMoldura:
    """A saída é a entrada rebobinada — sem degrau na virada permanência→saída.

    O bug que isto trava: `warning_ratio` despenca de ~1 para 0 no frame do
    descongelamento. A moldura lia esse valor direto, então a banda encolhia
    **15 px de uma vez** (contra 1 px de variação normal) e o pisca rápido
    voltava à respiração calma no mesmo frame. O olho lê isso como "a animação
    recomeçou", não como "o efeito está terminando".

    A defesa é estrutural: a moldura consome UM parâmetro (`hud_openness`,
    0→1→0) e um aviso já suavizado (`hud_warning`). O renderer não ramifica por
    fase, então não existe caminho de código novo para a saída entrar.
    """

    DT = 1 / 60

    def _serie(self, duracao: float = 3.0) -> list[tuple[str, float, float]]:
        e = TimeStopState()
        e.trigger(duracao)
        quadros = []
        while e.is_active:
            quadros.append((e.phase.name, e.hud_openness, e.hud_warning))
            e.update(self.DT)
        quadros.append((e.phase.name, e.hud_openness, e.hud_warning))
        return quadros

    def _indice_da_virada(self, serie) -> int:
        return next(
            i for i in range(1, len(serie)) if serie[i][0] != serie[i - 1][0]
        )

    def test_a_virada_nao_tem_degrau(self):
        serie = self._serie()
        i = self._indice_da_virada(serie)
        assert serie[i - 1][0] == "FROZEN" and serie[i][0] == "RECOVERING"
        for campo, nome in ((1, "hud_openness"), (2, "hud_warning")):
            salto = abs(serie[i][campo] - serie[i - 1][campo])
            assert salto < 0.05, (
                f"{nome} saltou {salto:.3f} no descongelamento — a moldura vai "
                "dar um pulo visível"
            )

    def test_nenhum_frame_do_efeito_inteiro_da_salto(self):
        """Um passo de 1/60s numa rampa de 1,01s move ~0,0165. Nada pode
        exceder isso de forma relevante em nenhum ponto do efeito."""
        serie = self._serie()
        for campo, nome in ((1, "hud_openness"), (2, "hud_warning")):
            pior, onde = 0.0, 0
            for i in range(1, len(serie)):
                salto = abs(serie[i][campo] - serie[i - 1][campo])
                if salto > pior:
                    pior, onde = salto, i
            assert pior < 0.05, (
                f"{nome} saltou {pior:.3f} no frame {onde} ({serie[onde][0]})"
            )

    def test_a_abertura_sobe_permanece_e_desce(self):
        """O formato pedido: entrada → permanência estável → saída."""
        serie = self._serie(duracao=4.0)
        valores = [q[1] for q in serie]
        topo = valores.index(1.0)
        assert topo > 0, "deveria haver uma subida antes do platô"
        assert all(v <= valores[i + 1] for i, v in enumerate(valores[:topo]))
        fim = len(valores) - 1 - valores[::-1].index(1.0)
        assert fim > topo, "deveria haver um platô"
        descida = valores[fim:]
        assert all(v >= descida[i + 1] for i, v in enumerate(descida[:-1]))
        assert descida[-1] == 0.0

    def test_subida_e_descida_tem_a_mesma_duracao(self):
        """"A mesma animação ao contrário" só vale se as rampas forem iguais.

        A descida é medida até o primeiro zero, não até o fim da série: a
        moldura some em 1,48s de recuperação mas a rampa dos inimigos segue até
        3,0s, e esses ~90 frames de moldura já apagada não são "descida".
        """
        serie = self._serie(duracao=4.0)
        valores = [q[1] for q in serie]
        subida = valores.index(1.0)
        fim_plato = len(valores) - 1 - valores[::-1].index(1.0)
        descida = valores.index(0.0, fim_plato) - fim_plato
        assert abs(subida - descida) <= 2, (
            f"subida {subida} frames, descida {descida} frames — a saída não é "
            "a entrada rebobinada"
        )

    def test_o_tremor_continua_parando_na_hora(self):
        """`hud_warning` suaviza a MOLDURA; `warning_ratio` não pode mudar.

        O tremor dos inimigos tem de cessar no frame do descongelamento — se
        seguisse a curva suave, eles vibrariam enquanto já voltam a andar.
        """
        e = TimeStopState()
        e.trigger(0.3)
        avanca(e, 0.35)
        assert e.is_recovering
        assert e.warning_ratio == 0.0
        assert e.tremor_pixels == 0.0
        assert e.hud_warning > 0.0, "a moldura, essa, ainda está liberando"


class TestFaseNomeada:
    def test_ocioso(self):
        assert TimeStopState().phase is TimeStopPhase.IDLE

    def test_congelado(self):
        e = TimeStopState()
        e.trigger(2.0)
        assert e.phase is TimeStopPhase.FROZEN

    def test_recuperando(self):
        e = TimeStopState()
        e.trigger(0.3)
        avanca(e, 0.4)
        assert e.phase is TimeStopPhase.RECOVERING

    def test_aviso_de_fim_ainda_e_congelamento(self):
        """`WARNING` é feedback, não fase: a escala continua zerada."""
        e = TimeStopState()
        e.trigger(Config.TIME_STOP_WARNING_TIME * 0.5)
        assert e.warning_ratio > 0.0
        assert e.phase is TimeStopPhase.FROZEN

    def test_reset_volta_para_ocioso(self):
        e = TimeStopState()
        e.trigger(3.0)
        e.reset()
        assert e.phase is TimeStopPhase.IDLE


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
