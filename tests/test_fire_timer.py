"""Contratos de cadência do §14 — `FireTimer` e `carry_interval`.

Estes testes travam o comportamento que gerou os bugs de cadência resolvidos
nesta base: perda de disparo por descarte da sobra do frame, e o teto de um
disparo por passo. Não dependem de pygame — só de `core.fire_timer`.
"""

import math

from game.core.fire_timer import FireTimer, carry_interval


class TestFireTimer:
    def test_pronto_no_primeiro_disparo(self):
        t = FireTimer()
        assert t.is_ready(0.1)
        assert t.consume(0.1)

    def test_primeiro_disparo_sem_overshoot(self):
        # O primeiro tiro não está atrasado — não deve deslocar o projétil.
        t = FireTimer()
        t.consume(0.1)
        assert t.overshoot == 0.0

    def test_nao_dispara_antes_do_intervalo(self):
        t = FireTimer(ready=False)
        t.advance(0.05, 0.1)
        assert not t.consume(0.1)

    def test_dispara_ao_completar_o_intervalo(self):
        t = FireTimer(ready=False)
        t.advance(0.1, 0.1)
        assert t.consume(0.1)

    def test_sobra_do_frame_nao_e_descartada(self):
        # O bug original: reatribuir o intervalo cheio jogava fora o quanto o
        # timer passou de zero, e a cadência real ficava abaixo da pedida.
        t = FireTimer(ready=False)
        t.advance(0.12, 0.1)  # 0.02 de sobra
        assert t.consume(0.1)
        assert math.isclose(t.overshoot, 0.02, abs_tol=1e-9)

    def test_passo_longo_emite_multiplos_disparos(self):
        # Sem isto (um `if` em vez de `while`), disparos somem quando o
        # intervalo é menor que o dt (cadência alta / FPS baixo).
        t = FireTimer(ready=False)
        t.advance(0.25, 0.1)
        n = 0
        while t.consume(0.1):
            n += 1
        assert n == 2

    def test_credito_ocioso_limitado_a_um_intervalo(self):
        # Nave parada por muito tempo não pode despejar uma rajada ao voltar.
        t = FireTimer(ready=False)
        for _ in range(1000):
            t.advance(0.01, 0.1)
        n = 0
        while t.consume(0.1):
            n += 1
        assert n == 1

    def test_cadencia_media_bate_o_pedido_com_jitter(self):
        # Integração: dt oscilando, a taxa média deve convergir ao intervalo.
        import random

        random.seed(5)
        interval = 1.0 / 9.35
        t = FireTimer()
        elapsed = 0.0
        shots = 0
        while elapsed < 20.0:
            dt = max(0.008, 1 / 60 + random.gauss(0, 0.004))
            t.advance(dt, interval)
            elapsed += dt
            while t.consume(interval):
                shots += 1
        taxa = shots / elapsed
        assert math.isclose(taxa, 9.35, rel_tol=0.02)

    def test_drain_zera_sem_disparar(self):
        t = FireTimer(ready=False)
        t.advance(0.5, 0.1)
        t.drain()
        assert not t.consume(0.1)

    def test_intervalo_zero_nao_trava(self):
        t = FireTimer(ready=False)
        t.advance(0.1, 0.0)
        # Não deve estourar; consume com intervalo inválido é no-op controlado.
        t.consume(0.0)


class TestCarryInterval:
    def test_preserva_sobra(self):
        # remaining=-0.01 (passou 0.01 de zero) → próximo alvo = 0.1 - 0.01.
        assert math.isclose(carry_interval(-0.01, 0.1), 0.09, abs_tol=1e-9)

    def test_divida_limitada_a_um_intervalo(self):
        # Muito tempo sem tick não vira rajada: a dívida é clampada, o resultado
        # nunca fica negativo. Debt enorme → 0.0 (dispara UMA vez no próximo
        # tick e retoma a cadência), não uma sequência de disparos represados.
        assert carry_interval(-99.0, 0.1) == 0.0
        assert 0.0 <= carry_interval(-99.0, 0.1) <= 0.1

    def test_intervalo_invalido_retorna_zero(self):
        assert carry_interval(-0.5, 0.0) == 0.0

    def test_cadencia_estavel_ao_longo_do_tempo(self):
        # 0.08s de intervalo numa grade de 1/60 — o caso da rajada do CyberTank,
        # que ficava 25% lenta a 30fps com atribuição direta.
        interval = 0.08
        timer = 0.0
        elapsed = 0.0
        fires = 0
        dt = 1 / 30
        while elapsed < 10.0:
            timer -= dt
            elapsed += dt
            if timer <= 0.0:
                fires += 1
                timer = carry_interval(timer, interval)
        taxa = fires / elapsed
        assert math.isclose(taxa, 1 / interval, rel_tol=0.05)
