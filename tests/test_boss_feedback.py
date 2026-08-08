"""O boss comunica a vida pelo ESTADO FÍSICO, não por barra.

A faixa vermelha/verde acima do boss saiu por decisão de design: o que restou
como leitura é o próprio boss — casco corrompido no frenzy (`BOSS_FRENZY_THRESHOLD`)
e o fogo/fumaça de dano crítico (`CriticalDamageFX.threshold`). Mesmo caminho que
o `MetropolisOverlordBoss` já seguia ("sem barra de vida tradicional, a progressão
lê-se no estado físico do boss").

A remoção foi **só visual**: `health`/`max_health` seguem intactos e continuam
governando dano, frenzy e morte. É isso que a segunda classe aqui trava — sem
ela, alguém "limpando" a barra poderia levar junto o estado que a alimentava.
"""

import pygame

from game.core.config import config as Config
from game.entities.bosses.boss import Boss
from game.entities.bosses.boss_state import BossState


def boss_ativo() -> Boss:
    b = Boss(550.0, 120.0)
    b.y = b.target_y
    b.state = BossState.ACTIVE
    return b


class TestSemBarraDeVida:
    def test_o_metodo_de_desenho_da_barra_nao_existe_mais(self):
        assert not hasattr(Boss, "_draw_health_bar")

    def test_o_desenho_nao_pinta_os_pixels_da_barra(self):
        """As cores da barra eram vermelho e verde PUROS — não aparecem em mais
        nada do boss (o chassi é aço azulado e a energia é ciano), então achá-las
        na tela só pode ser a barra de volta."""
        b = boss_ativo()
        surface = pygame.Surface((1280, 720), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 255))
        for _ in range(30):
            b.update(1 / 60, 640.0, 600.0)
        b.draw(surface)

        # Faixa onde a barra ficava: 10px de altura, 20px acima do corpo.
        largura = min(200, int(b.w * 2))
        faixa = pygame.Rect(
            int(b.x + (b.w - largura) / 2), int(b.y - 20), largura, 10
        )
        faixa = faixa.clip(surface.get_rect())
        achadas = {
            surface.get_at((x, y))[:3]
            for x in range(faixa.left, faixa.right)
            for y in range(faixa.top, faixa.bottom)
        }
        assert (255, 0, 0) not in achadas
        assert (0, 255, 0) not in achadas


class TestAVidaContinuaFuncionando:
    """'Visualmente apenas': saiu o desenho, não o estado."""

    def test_a_vida_segue_sendo_contabilizada(self):
        b = boss_ativo()
        cheia = b.health
        b.take_damage(100)
        assert b.health == cheia - 100
        assert b.max_health == cheia

    def test_a_razao_de_vida_acompanha(self):
        b = boss_ativo()
        b.take_damage(b.max_health // 2)
        assert 0.45 < b.health_ratio < 0.55

    def test_o_frenzy_ainda_dispara_no_limiar(self):
        b = boss_ativo()
        assert not b.frenzy_mode
        b.take_damage(int(b.max_health * (1 - Config.BOSS_FRENZY_THRESHOLD)) + 1)
        assert b.frenzy_mode or b.pending_frenzy

    def test_o_boss_ainda_morre(self):
        b = boss_ativo()
        b.take_damage(b.max_health)
        assert b.health == 0
        assert b.dead


class TestLeituraFisica:
    """O que substituiu a barra, em ordem de aparição durante a luta."""

    def test_o_fogo_so_aparece_perto_da_morte(self):
        b = boss_ativo()
        b.update(1 / 60, 640.0, 600.0)
        assert not b.critical_fx.emitting

    def test_o_fogo_aparece_abaixo_do_limiar(self):
        b = boss_ativo()
        b.health = int(b.max_health * (b.critical_fx.threshold - 0.05))
        for _ in range(60):
            b.update(1 / 60, 640.0, 600.0)
        assert b.critical_fx.emitting
        assert b.critical_fx.has_particles

    def test_o_fogo_intensifica_conforme_a_vida_cai(self):
        b = boss_ativo()
        b.health = int(b.max_health * 0.20)
        b.update(1 / 60, 640.0, 600.0)
        meio = b.critical_fx.intensity
        b.health = 1
        b.update(1 / 60, 640.0, 600.0)
        assert b.critical_fx.intensity > meio

    def test_o_frenzy_avisa_antes_do_fogo(self):
        """Duas leituras em momentos diferentes da luta, não uma só no fim."""
        assert Config.BOSS_FRENZY_THRESHOLD > boss_ativo().critical_fx.threshold
