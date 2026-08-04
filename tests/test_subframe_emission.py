"""Compensação sub-frame da emissão de projéteis (§14).

O `FireTimer` já tinha teste do lado do TEMPO — quando o disparo sai. Faltava o
lado da GEOMETRIA — onde ele nasce —, e foi por esse buraco que o rastro
desigual do Estilete passou despercebido: a cadência estava certa o tempo todo.

O invariante aqui não é um número de pixels (que muda a cada ajuste de nave), e
sim a **equidistância**: com emissor em velocidade constante, projéteis
consecutivos ficam igualmente espaçados, em qualquer frame rate.
"""

import math

import pytest

from game.core.fire_timer import FireTimer, emission_offset


class TestEmissionOffset:
    def test_emissor_parado_e_o_comportamento_antigo(self):
        # Degenera em `v_projetil * overshoot` — a versão que existia antes.
        dx, dy = emission_offset(100.0, -400.0, 0.0, 0.0, 0.5)
        assert dx == pytest.approx(50.0)
        assert dy == pytest.approx(-200.0)

    def test_velocidade_relativa_desconta_o_emissor(self):
        # Emissor andando junto com o projetil: nada a compensar no eixo comum.
        dx, dy = emission_offset(300.0, 0.0, 300.0, 0.0, 0.25)
        assert dx == pytest.approx(0.0)
        assert dy == pytest.approx(0.0)

    def test_corrige_o_eixo_do_emissor(self):
        # Bala sobe; nave anda para a direita. O eixo X so e corrigido pela
        # velocidade da nave — era exatamente o que faltava.
        dx, dy = emission_offset(0.0, -400.0, 275.0, 0.0, 0.01)
        assert dx == pytest.approx(-2.75)
        assert dy == pytest.approx(-4.0)

    def test_overshoot_nao_positivo_nao_desloca(self):
        assert emission_offset(1.0, 1.0, 1.0, 1.0, 0.0) == (0.0, 0.0)
        assert emission_offset(500.0, 500.0, 0.0, 0.0, -0.1) == (0.0, 0.0)


def _simulate(interval, dts, emitter_vx, proj_speed, compensate=True):
    """Replica a ordem do frame da `PlayingScene.update`.

    `_update_timers` (shooting.update) -> `_update_ship` (ship.move ANTES do
    fire, playing.py:1493 vs :1514) -> `entity_manager.update`, que move também
    a bala recém-nascida.

    Devolve as posições (x, y) de cada projétil ao fim da simulação.
    """
    timer = FireTimer()
    emitter_x = 0.0
    shots: list[list[float]] = []
    for dt in dts:
        timer.advance(dt, interval)
        emitter_x += emitter_vx * dt
        if timer.is_ready(interval):
            overshoot = timer.overshoot if timer.consume(interval) else 0.0
            dx, dy = (
                emission_offset(0.0, -proj_speed, emitter_vx, 0.0, overshoot)
                if compensate
                else (0.0, -proj_speed * overshoot)
            )
            shots.append([emitter_x + dx, dy])
        for s in shots:
            s[1] -= proj_speed * dt
    return shots


def _spacings(shots):
    return [math.dist(shots[i], shots[i + 1]) for i in range(len(shots) - 1)]


class TestEquidistancia:
    # 1/8 = cadencia do Estilete; os fps cobrem o range real (mobile ~30).
    @pytest.mark.parametrize("fps", [60, 50, 45, 40, 30])
    def test_emissor_em_movimento_fica_equidistante(self, fps):
        shots = _simulate(1 / 8.0, [1.0 / fps] * (fps * 4), 275.0, 408.0)
        gaps = _spacings(shots)
        assert len(gaps) > 5
        assert max(gaps) - min(gaps) < 1e-6, f"{fps}fps: {min(gaps)}..{max(gaps)}"

    @pytest.mark.parametrize("fps", [60, 30])
    def test_emissor_parado_continua_equidistante(self, fps):
        # Nao-regressao: o caso que ja funcionava nao pode piorar.
        shots = _simulate(1 / 8.0, [1.0 / fps] * (fps * 4), 0.0, 408.0)
        gaps = _spacings(shots)
        assert max(gaps) - min(gaps) < 1e-6

    def test_sem_compensacao_o_erro_aparece(self):
        # Trava o teste contra si mesmo: se a simulacao nao reproduzisse o
        # defeito, o teste acima passaria por acidente.
        shots = _simulate(1 / 8.0, [1 / 60] * 240, 275.0, 408.0, compensate=False)
        gaps = _spacings(shots)
        assert max(gaps) - min(gaps) > 2.0

    def test_dt_irregular_fica_no_limite_fisico(self):
        """Com `dt` variável sobra um resíduo, e ele tem causa conhecida.

        A bala recém-nascida também leva um `dt` inteiro no `entity_manager.
        update` do frame em que nasce. Com `dt` constante esse extra é igual
        para todas e some do espaçamento; com `dt` variável cada bala leva um
        extra diferente, e o erro de espaçamento vira
        `v_projétil × (dt_k+1 − dt_k)`.

        Medido: 2,171px de variação com jitter de ±2ms, contra 0,000px se o
        `dt` de nascimento for descontado. É resíduo de timestep variável, não
        falha da compensação — e é RUÍDO, não o padrão periódico de 2,5px que
        a versão sem velocidade relativa produzia. O olho pega periodicidade,
        não ruído.

        O limite é derivado da física, não escolhido: travar um número fixo
        aqui só registraria o jitter deste seed.
        """
        import random

        rng = random.Random(7)
        dts = [1 / 60 + rng.uniform(-0.002, 0.002) for _ in range(240)]
        proj_speed = 408.0
        shots = _simulate(1 / 8.0, dts, 275.0, proj_speed)
        gaps = _spacings(shots)

        max_jitter = max(abs(dts[i + 1] - dts[i]) for i in range(len(dts) - 1))
        limite = proj_speed * max_jitter * 1.5
        assert max(gaps) - min(gaps) < limite

    def test_dt_constante_nao_tem_residuo_algum(self):
        # A contraprova do teste acima: sem jitter, o extra do frame de
        # nascimento e' identico para todas as balas e nao afeta espacamento.
        shots = _simulate(1 / 8.0, [1 / 60] * 240, 275.0, 408.0)
        gaps = _spacings(shots)
        assert max(gaps) - min(gaps) < 1e-9


class TestAutoFireNaoTemCadenciaPropria:
    """O auto-fire é um gatilho, não um relógio.

    Havia um segundo gate periódico (janela de 1 frame a cada 0,1s, com
    `timer = 0` no disparo — §14) empilhado sobre o `FireTimer`. Dois gates
    periódicos independentes batem entre si: o tiro só sai quando as duas
    janelas coincidem, e a cadência real vira o batimento.
    """

    def _ship(self, ship_id, auto_fire):
        from game.core.ship_types import get_ship_profile
        from game.entities.player.ship import Ship

        return Ship(
            100.0, 100.0, profile=get_ship_profile(ship_id), auto_fire=auto_fire
        )

    def test_auto_fire_nao_depende_de_relogio_proprio(self):
        ship = self._ship("estilete", auto_fire=True)
        # Verdadeiro em TODO frame: quem decide o instante é o FireTimer.
        for _ in range(20):
            assert ship.should_auto_fire() is True
            ship.update(1 / 60)

    def test_sem_auto_fire_nunca_dispara_sozinha(self):
        ship = self._ship("estilete", auto_fire=False)
        for _ in range(20):
            assert ship.should_auto_fire() is False
            ship.update(1 / 60)

    def test_cadencia_entregue_bate_com_a_configurada(self):
        """A regressão que o jogador via: 8,00/s configurado, 5,71/s na tela."""
        from game.core.config import config as Config
        from game.core.ship_types import get_ship_profile

        profile = get_ship_profile("estilete")
        ship = self._ship("estilete", auto_fire=True)
        interval = 1.0 / (Config.FIRE_RATE * ship.attack_speed_multiplier)

        timer = FireTimer()
        dt = 1 / 60
        frames_de_tiro = []
        for f in range(600):
            ship.update(dt)
            timer.advance(dt, interval)
            if ship.should_auto_fire() and timer.is_ready(interval):
                if timer.consume(interval):
                    frames_de_tiro.append(f)

        gaps = [
            frames_de_tiro[i + 1] - frames_de_tiro[i]
            for i in range(len(frames_de_tiro) - 1)
        ]
        entregue = 60.0 / (sum(gaps) / len(gaps))
        alvo = Config.FIRE_RATE * profile.fire_rate_mult
        assert entregue == pytest.approx(alvo, rel=0.02), (
            f"alvo {alvo:.2f}/s, entregue {entregue:.2f}/s"
        )
        # E o ritmo não agrupa: no máximo 1 frame de diferença entre vãos
        # (a quantização que o `emission_offset` depois dissolve na posição).
        assert max(gaps) - min(gaps) <= 1, f"vãos irregulares: {sorted(set(gaps))}"


class TestShipExpoeVelocidade:
    def test_fachada_devolve_velocidade_medida(self):
        from game.core.ship_types import get_ship_profile
        from game.entities.player.ship import Ship

        ship = Ship(100.0, 100.0, profile=get_ship_profile("estilete"))
        assert ship.emit_velocity == (0.0, 0.0)

        # Sem input: a nave nao anda, logo velocidade zero.
        ship.move(set(), 1 / 60)
        assert ship.emit_velocity == (0.0, 0.0)

    def test_dt_zero_nao_divide_por_zero(self):
        from game.core.ship_types import get_ship_profile
        from game.entities.player.ship import Ship

        ship = Ship(100.0, 100.0, profile=get_ship_profile("padrao"))
        ship.move({"hold_right"}, 0.0)
        assert ship.emit_velocity == (0.0, 0.0)
