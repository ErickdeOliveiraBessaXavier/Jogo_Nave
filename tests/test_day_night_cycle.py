"""Ciclo dia/noite das Cordilheiras: pausa DERIVADA, nunca por borda de evento.

O ciclo mede tempo de relógio (uma transição dura ~10 min). Sempre que o fundo
entra em warp — boss fight, cutscene de entrada/saída de mundo — o mesmo
`speed_multiplier` que acelera o parallax atropelaria o ciclo e faria um
anoitecer inteiro passar em segundos. Por isso o relógio do ciclo congela
enquanto o tempo está deformado.

Bug travado aqui: essa pausa era ligada/desligada por evento no
`BossFightController` (`start()` liga, `end()` desliga). O `Background` vive no
`Renderer`, que **sobrevive à `PlayingScene`** — e `set_world_theme` não recria
o tema quando ele é o mesmo. Morrer no meio de um boss fight pulava o `end()`,
a fase recomeçava com o mesmo background e o ciclo ficava congelado para o
resto da sessão. Estado derivado por frame não tem borda para perder.
"""

import pygame
import pytest

from game.core.config import config as Config
from game.core.world_config import WorldTheme
from game.render.backgrounds import MountainsBackground
from game.render.renderer import Renderer


@pytest.fixture
def cordilheiras():
    r = Renderer()
    r.set_world_theme(WorldTheme.MOUNTAINS)
    bg = r.current_background
    assert isinstance(bg, MountainsBackground)
    surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
    return r, bg, surface


class TestPausaDerivadaDoWarp:
    def test_warp_congela_o_relogio_do_ciclo(self, cordilheiras):
        r, bg, surface = cordilheiras
        antes = bg._phase_elapsed_time

        r.background(surface, dt=0.5, speed_multiplier=Config.BOSS_WARP_SPEED_MULTIPLIER)

        assert bg._pause_day_night_cycle is True
        assert bg._phase_elapsed_time == antes

    def test_tempo_normal_avanca_o_ciclo(self, cordilheiras):
        r, bg, surface = cordilheiras
        antes = bg._phase_elapsed_time

        r.background(surface, dt=0.5, speed_multiplier=1.0)

        assert bg._pause_day_night_cycle is False
        assert bg._phase_elapsed_time == pytest.approx(antes + 0.5)

    def test_frame_normal_descongela_pausa_herdada(self, cordilheiras):
        """A regressão: fase reiniciada após morte no boss fight.

        O background sobrevive à cena, então ele volta com a pausa que o boss
        fight deixou. O primeiro frame em tempo normal precisa restaurá-lo
        sozinho — sem depender de ninguém ter chamado o desligamento.
        """
        r, bg, surface = cordilheiras
        bg.set_day_night_paused(True)  # estado herdado da run anterior
        antes = bg._phase_elapsed_time

        r.background(surface, dt=0.5, speed_multiplier=1.0)

        assert bg._pause_day_night_cycle is False
        assert bg._phase_elapsed_time == pytest.approx(antes + 0.5)

    def test_alterna_com_o_warp_sem_estado_preso(self, cordilheiras):
        r, bg, surface = cordilheiras
        warp = Config.BOSS_WARP_SPEED_MULTIPLIER

        for mult, esperado in ((warp, True), (1.0, False), (warp, True), (1.0, False)):
            r.background(surface, dt=0.1, speed_multiplier=mult)
            assert bg._pause_day_night_cycle is esperado


class TestResetLimpaAPausa:
    def test_reset_devolve_o_estado_inicial_completo(self, cordilheiras):
        _r, bg, _surface = cordilheiras
        bg.set_day_night_paused(True)
        bg._phase = "sunset"
        bg._phase_elapsed_time = 42.0

        bg.reset()

        assert bg._pause_day_night_cycle is False
        assert bg._phase == "day"
        assert bg._phase_elapsed_time == 0.0


class TestBossControllerNaoTocaNoBackground:
    """§1: a iluminação congelada é consequência do warp, não responsabilidade
    do controlador de boss. Ele não deve voltar a ter o background em mãos."""

    def test_controlador_nao_tem_acesso_ao_background(self):
        import inspect

        from game.systems.boss_fight_controller import BossFightController

        fonte = inspect.getsource(BossFightController)
        assert "set_day_night_paused" not in fonte
        assert "background_getter" not in inspect.signature(
            BossFightController.__init__
        ).parameters
