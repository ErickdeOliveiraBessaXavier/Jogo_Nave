"""Encerramento de fase: pull de coletáveis + fade dos retardatários.

Trava o contrato do acabamento de transição (§ pedido do usuário): no fim da fase
nada pode ficar congelado nem atravessar para a próxima. Testa a lógica pura das
entidades — o puxão de encerramento atrai ao jogador, e o fade dissolve e marca o
coletável como morto (para o `_filter_dead_inplace` removê-lo).
"""

from game.core.config import PowerUpType
from game.entities._shared.attraction_utils import update_closing_pull
from game.entities.pickups.powerup import PowerUp
from game.entities.pickups.star import Star


class _Dummy:
    """Alvo mínimo do `update_closing_pull` (só precisa de rect/x/y/shake)."""

    def __init__(self, x, y):
        import pygame

        self.x = float(x)
        self.y = float(y)
        self.rect = pygame.Rect(int(x), int(y), 20, 20)
        self._is_being_attracted = False
        self.attraction_shake_timer = 0.0


class TestClosingPull:
    def test_move_em_direcao_ao_alvo(self):
        e = _Dummy(0, 0)
        target = (500.0, 0.0)
        before = e.x
        update_closing_pull(e, 0.1, target, speed=950.0)
        assert e.x > before  # puxado para a direita, rumo ao alvo
        assert e._is_being_attracted is True

    def test_velocidade_limitada(self):
        # Não teleporta: o passo é speed*dt, independente da distância.
        e = _Dummy(0, 0)
        update_closing_pull(e, 0.1, (10_000.0, 0.0), speed=950.0)
        assert e.x <= 950.0 * 0.1 + 1.0

    def test_converge(self):
        e = _Dummy(0, 0)
        for _ in range(200):
            update_closing_pull(e, 0.016, (400.0, 300.0))
        assert abs(e.rect.centerx - 400) < 30 and abs(e.rect.centery - 300) < 30


class TestPowerUpFade:
    def test_dissolve_e_morre(self):
        p = PowerUp(PowerUpType.SHIELD)
        p.begin_fade_out()
        assert p._fading is True
        assert p.dead is False
        steps = int(PowerUp.FADE_OUT_DURATION / 0.016) + 2
        for _ in range(steps):
            p.update(0.016)
        assert p.dead is True

    def test_fade_ignora_atracao(self):
        # Durante o fade o coletável não se move (nem cai nem é puxado).
        p = PowerUp(PowerUpType.SPEED)
        p.begin_fade_out()
        x0, y0 = p.x, p.y
        p.update(0.016, closing_pull=(9999.0, 9999.0))
        assert (p.x, p.y) == (x0, y0)

    def test_begin_fade_idempotente(self):
        p = PowerUp(PowerUpType.SCORE)
        p.begin_fade_out()
        t = p._fade_timer
        p._fade_timer = 0.05
        p.begin_fade_out()  # não deve reiniciar o timer
        assert p._fade_timer == 0.05 and t == PowerUp.FADE_OUT_DURATION

    def test_closing_pull_move_powerup(self):
        p = PowerUp(PowerUpType.LIFE)
        p.x = 0.0
        p.y = 300.0
        p.rect.topleft = (0, 300)
        p.update(0.1, closing_pull=(600.0, 300.0))
        assert p.x > 0.0


class TestStarFade:
    def test_dissolve_e_morre(self):
        s = Star(100.0, 100.0)
        s.begin_fade_out()
        assert s._fading is True
        steps = int(Star.FADE_OUT_DURATION / 0.016) + 2
        for _ in range(steps):
            s.update(0.016, 1280, 720)
        assert s.dead is True

    def test_closing_pull_move_estrela(self):
        s = Star(0.0, 300.0)
        s.update(0.1, 1280, 720, closing_pull=(600.0, 300.0))
        assert s.x > 0.0
