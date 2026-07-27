"""Contratos do ajuste dinâmico de dificuldade (`meta_progression`).

Lógica pura (§16): diagnóstico de performance + política de ajuste. Não
instancia o jogo nem toca em pygame — só monta `LevelPerformance` e
`LevelConfig` sintéticos.

Cada teste aqui trava um comportamento que já esteve errado em produção; o
docstring de cada um diz qual. O tema comum é o §11: errar para o lado fácil
custa uma fase morna, errar para o lado difícil custa o jogador.
"""

import copy

from game.core.levels import DifficultyConfig, LevelConfig
from game.core.meta_progression import (
    DOMINATE_CLEAR_RATE,
    MIN_ATTEMPTS_TO_DIAGNOSE,
    STRUGGLE_CLEAR_RATE,
    DifficultyAdjuster,
    LevelPerformance,
    PerformanceAnalyzer,
    PerformanceState,
    PlayerProfile,
)
from game.core.meta_progression_service import MetaProgressionService


class _Enemy:
    """Tipo dummy — o ajuste só olha os VALORES do enemy_spawn_config."""


def make_config(
    level_number: int = 5,
    enemies_to_clear: int = 200,
    spawn_time: float = 2.0,
) -> LevelConfig:
    return LevelConfig(
        level_number=level_number,
        enemy_spawn_config={_Enemy: spawn_time},
        enemies_to_clear=enemies_to_clear,
    )


def make_stats(
    attempts: int,
    clears: int,
    *,
    level_number: int = 5,
    outcomes: list[bool] | None = None,
    best_time: float | None = None,
    total_time: float = 0.0,
) -> LevelPerformance:
    stats = LevelPerformance(level_number=level_number)
    stats.attempts = attempts
    stats.clears = clears
    stats.deaths = attempts - clears
    stats.best_time = best_time
    stats.total_time = total_time
    for cleared in outcomes or []:
        stats.recent_attempts.append({"cleared": cleared})
    return stats


def stats_with_clear_rate(rate: float, attempts: int = 100) -> LevelPerformance:
    return make_stats(attempts, round(rate * attempts))


# ---------------------------------------------------------------------------
# Diagnóstico (rótulo para UI) — os limiares têm UMA fonte
# ---------------------------------------------------------------------------


class TestPerformanceState:
    def test_poucas_tentativas_e_sempre_learning(self):
        stats = make_stats(MIN_ATTEMPTS_TO_DIAGNOSE - 1, 0)
        assert stats.get_performance_state() == PerformanceState.LEARNING

    def test_clear_rate_baixo_e_struggling(self):
        stats = make_stats(MIN_ATTEMPTS_TO_DIAGNOSE, 0)
        assert stats.clear_rate < STRUGGLE_CLEAR_RATE
        assert stats.get_performance_state() == PerformanceState.STRUGGLING

    def test_struggling_e_dominating_usam_o_mesmo_minimo_de_tentativas(self):
        """Antes: endurecer exigia 3 tentativas e aliviar exigia 5.

        O sistema apertava quase 2x mais rápido do que ajudava. Os dois lados
        agora entram no mesmo gate — este teste falha se alguém reintroduzir a
        assimetria.
        """
        n = MIN_ATTEMPTS_TO_DIAGNOSE
        struggling = make_stats(n, 0)
        dominating = make_stats(n, n, best_time=10.0, total_time=10.0 * n)

        assert struggling.get_performance_state() == PerformanceState.STRUGGLING
        assert dominating.get_performance_state() == PerformanceState.DOMINATING

    def test_limiares_sao_lidos_das_constantes_do_modulo(self):
        """As constantes do analyzer eram lidas por ninguém (eram 0.35/0.85
        enquanto o diagnóstico usava 0.3/0.9 hardcoded). Aqui provamos que
        mexer na constante move o diagnóstico de verdade."""
        attempts = 100
        acima = make_stats(attempts, int(attempts * STRUGGLE_CLEAR_RATE) + 1)
        abaixo = make_stats(attempts, int(attempts * STRUGGLE_CLEAR_RATE) - 1)

        assert acima.get_performance_state() != PerformanceState.STRUGGLING
        assert abaixo.get_performance_state() == PerformanceState.STRUGGLING


# ---------------------------------------------------------------------------
# O multiplicador: função pura das estatísticas
# ---------------------------------------------------------------------------


class TestPureza:
    """A razão de existir do refactor: o multiplicador não pode depender de
    quantas vezes foi consultado.

    Antes, cada chamada avançava um EMA persistido — o grau de adaptação era
    medido pelo número de chamadas, um contador implícito que sombreava
    `stats.attempts`. Um leitor a mais (preview de HUD, tela de seleção)
    aceleraria a adaptação em silêncio, e o desvio ia para o disco.
    """

    def test_multiplier_for_e_idempotente(self):
        stats = make_stats(20, 1)
        primeiro = DifficultyAdjuster.multiplier_for(stats)
        for _ in range(50):
            assert DifficultyAdjuster.multiplier_for(stats) == primeiro

    def test_resolve_level_config_nao_muta_o_perfil(self, tmp_path):
        profile = PlayerProfile(profile_path=tmp_path / "profile.json")
        profile.level_stats[5] = make_stats(20, 1)
        profile.highest_level_reached = 5
        antes = copy.deepcopy(profile.__dict__)

        MetaProgressionService.resolve_level_config(profile, make_config())

        assert profile.__dict__.keys() == antes.keys()
        assert profile.level_stats[5].attempts == antes["level_stats"][5].attempts
        assert profile.highest_level_reached == antes["highest_level_reached"]

    def test_resolve_level_config_e_estavel_entre_chamadas(self, tmp_path):
        profile = PlayerProfile(profile_path=tmp_path / "profile.json")
        profile.level_stats[5] = make_stats(20, 1)
        profile.highest_level_reached = 5

        primeiro = MetaProgressionService.resolve_level_config(profile, make_config())
        for _ in range(20):
            repetido = MetaProgressionService.resolve_level_config(
                profile, make_config()
            )
            assert repetido.enemies_to_clear == primeiro.enemies_to_clear
            assert (
                repetido.enemy_spawn_config[_Enemy]
                == primeiro.enemy_spawn_config[_Enemy]
            )

    def test_perfil_nao_tem_mais_estado_de_ajuste(self):
        """`level_adjustments` foi removido — o multiplicador é derivado.

        Se voltar, volta junto o acoplamento entre nº de chamadas e
        dificuldade.
        """
        assert not hasattr(PlayerProfile, "record_level_adjustment")


class TestAlvoContinuo:
    """A descontinuidade era a doença; o amortecimento do EMA era o curativo.

    Com alvo discreto por faixa (0.85 / 1.0 / 1.15), o multiplicador saltava
    15% de uma fase para a outra quando o clear rate cruzava um limiar — e com
    poucas tentativas um único abate cruzava.
    """

    def test_no_limiar_exato_o_desvio_e_zero(self):
        stats = stats_with_clear_rate(STRUGGLE_CLEAR_RATE)
        assert DifficultyAdjuster._target(stats) == 1.0

    def test_continuidade_no_limiar_de_struggle(self):
        """Cruzar o limiar não pode produzir SALTO.

        A versão discreta ia de 1.0 para 0.85 sem meio-termo: 0.15 de degrau
        para uma variação infinitesimal de clear rate.
        """
        abaixo = DifficultyAdjuster._target(
            stats_with_clear_rate(STRUGGLE_CLEAR_RATE - 0.001, attempts=10000)
        )
        acima = DifficultyAdjuster._target(
            stats_with_clear_rate(STRUGGLE_CLEAR_RATE + 0.001, attempts=10000)
        )
        assert abs(abaixo - acima) < 0.01

    def test_continuidade_no_limiar_de_dominate(self):
        abaixo = DifficultyAdjuster._target(
            stats_with_clear_rate(DOMINATE_CLEAR_RATE - 0.001, attempts=10000)
        )
        acima = DifficultyAdjuster._target(
            stats_with_clear_rate(DOMINATE_CLEAR_RATE + 0.001, attempts=10000)
        )
        assert abs(abaixo - acima) < 0.01

    def test_teto_de_aperto_e_menor_que_o_piso_de_alivio(self):
        """§11 na dimensão da MAGNITUDE: o alívio vai mais fundo que o aperto.

        Não é só uma questão de velocidade — a faixa de clear rate que gera
        aperto (0.90→1.0) é 3x mais estreita que a de alívio (0.30→0), então
        tetos iguais fariam o aperto reagir 3x mais forte ao mesmo desvio.
        """
        assert DifficultyAdjuster.MAX_HARDEN < DifficultyAdjuster.MAX_EASE

    def test_severidade_maxima_atinge_os_limites(self):
        piso = DifficultyAdjuster._target(make_stats(100, 0))
        teto = DifficultyAdjuster._target(make_stats(100, 100))
        assert piso == DifficultyAdjuster.MIN_ADJUSTMENT
        assert teto == DifficultyAdjuster.MAX_ADJUSTMENT

    def test_alivio_cresce_com_a_severidade(self):
        pouco = DifficultyAdjuster._target(stats_with_clear_rate(0.25))
        muito = DifficultyAdjuster._target(stats_with_clear_rate(0.05))
        assert muito < pouco < 1.0

    def test_quem_esta_melhorando_recebe_menos_alivio(self):
        parado = make_stats(20, 1, outcomes=[False] * 6)
        melhorando = make_stats(20, 1, outcomes=[False, False, False, True, True, True])
        assert melhorando.improvement_trend > 0
        assert DifficultyAdjuster._target(melhorando) > DifficultyAdjuster._target(
            parado
        )


class TestRampaDeEvidencia:
    def test_sem_tentativas_suficientes_nao_ajusta(self):
        stats = make_stats(MIN_ATTEMPTS_TO_DIAGNOSE, 0)
        assert DifficultyAdjuster.multiplier_for(stats) == 1.0

    def test_evidencia_satura_em_um(self):
        stats = make_stats(500, 0)
        assert DifficultyAdjuster.multiplier_for(stats) == (
            DifficultyAdjuster.MIN_ADJUSTMENT
        )

    def test_alivio_satura_com_menos_tentativas_que_o_aperto(self):
        """§11: ajudar rápido, apertar devagar."""
        assert (
            DifficultyAdjuster.EASE_RAMP_ATTEMPTS
            < DifficultyAdjuster.HARDEN_RAMP_ATTEMPTS
        )
        n = MIN_ATTEMPTS_TO_DIAGNOSE + DifficultyAdjuster.EASE_RAMP_ATTEMPTS

        aliviando = make_stats(n, 0)  # clear rate 0 => alvo no piso
        apertando = make_stats(n, n)  # clear rate 1 => alvo no teto

        assert DifficultyAdjuster.multiplier_for(aliviando) == (
            DifficultyAdjuster.MIN_ADJUSTMENT
        )
        assert DifficultyAdjuster.multiplier_for(apertando) < (
            DifficultyAdjuster.MAX_ADJUSTMENT
        )

    def test_multiplicador_nunca_sai_dos_limites(self):
        for attempts in (0, 3, 4, 10, 100, 5000):
            for clears in (0, attempts // 2, attempts):
                mult = DifficultyAdjuster.multiplier_for(make_stats(attempts, clears))
                assert (
                    DifficultyAdjuster.MIN_ADJUSTMENT
                    <= mult
                    <= DifficultyAdjuster.MAX_ADJUSTMENT
                )


class TestHardeningFrontier:
    """§11: morrer manda o jogador ao checkpoint, e as fases de ENTRADA do mundo
    são rejogadas (e limpas) em toda run. Pelas estatísticas puras elas parecem
    dominadas, e o adaptativo as endurecia em até +25% — o caminho de volta
    ficava mais duro exatamente para quem já estava apanhando."""

    def test_fase_na_fronteira_pode_endurecer(self):
        assert DifficultyAdjuster.hardening_allowed(10, highest_level_reached=10)

    def test_fase_muito_atras_da_fronteira_nao_endurece(self):
        assert not DifficultyAdjuster.hardening_allowed(2, highest_level_reached=12)

    def test_gate_fechado_impede_o_aperto(self):
        dominando = make_stats(50, 50)
        assert DifficultyAdjuster.multiplier_for(dominando) > 1.0
        assert (
            DifficultyAdjuster.multiplier_for(dominando, allow_hardening=False) == 1.0
        )

    def test_gate_fechado_nao_impede_alivio(self):
        """Ajudar é sempre permitido — o gate é só do aperto."""
        travado = make_stats(50, 1)
        assert DifficultyAdjuster.multiplier_for(travado, allow_hardening=False) < 1.0


class TestApplyToConfig:
    def test_multiplicador_alto_acelera_spawn_e_aumenta_contagem(self):
        base = make_config(enemies_to_clear=200, spawn_time=2.0)
        adjusted = DifficultyAdjuster.apply_to_config(base, 1.2)
        assert adjusted.enemy_spawn_config[_Enemy] < 2.0
        assert adjusted.enemies_to_clear > 200

    def test_multiplicador_baixo_desacelera_spawn_e_reduz_contagem(self):
        base = make_config(enemies_to_clear=200, spawn_time=2.0)
        adjusted = DifficultyAdjuster.apply_to_config(base, 0.8)
        assert adjusted.enemy_spawn_config[_Enemy] > 2.0
        assert adjusted.enemies_to_clear < 200

    def test_respeita_o_piso_de_spawn_do_pipeline(self):
        base = make_config(spawn_time=DifficultyConfig.MIN_SPAWN_TIME)
        adjusted = DifficultyAdjuster.apply_to_config(base, 1.25)
        assert adjusted.enemy_spawn_config[_Enemy] >= DifficultyConfig.MIN_SPAWN_TIME

    def test_respeita_o_piso_de_inimigos_do_pipeline(self):
        """Antes era um `max(20, ...)` solto, desalinhado do
        `MIN_ENEMIES_TO_CLEAR` do pipeline — o adaptativo furava em 25% o
        mínimo que o próprio pipeline declara."""
        base = make_config(enemies_to_clear=DifficultyConfig.MIN_ENEMIES_TO_CLEAR)
        adjusted = DifficultyAdjuster.apply_to_config(base, 0.75)
        assert adjusted.enemies_to_clear >= DifficultyConfig.MIN_ENEMIES_TO_CLEAR

    def test_nao_muta_a_config_base(self):
        base = make_config(enemies_to_clear=200, spawn_time=2.0)
        DifficultyAdjuster.apply_to_config(base, 0.8)
        assert base.enemies_to_clear == 200
        assert base.enemy_spawn_config[_Enemy] == 2.0


class TestServico:
    def test_sem_historico_devolve_a_config_base(self, tmp_path):
        profile = PlayerProfile(profile_path=tmp_path / "profile.json")
        base = make_config()
        assert MetaProgressionService.resolve_level_config(profile, base) is base

    def test_banda_neutra_devolve_a_config_base(self, tmp_path):
        profile = PlayerProfile(profile_path=tmp_path / "profile.json")
        profile.level_stats[5] = make_stats(50, 25)  # clear rate 50% = confortável
        base = make_config()
        assert MetaProgressionService.resolve_level_config(profile, base) is base

    def test_jogador_travado_recebe_fase_mais_facil(self, tmp_path):
        profile = PlayerProfile(profile_path=tmp_path / "profile.json")
        profile.level_stats[5] = make_stats(20, 0)
        profile.highest_level_reached = 5

        base = make_config(enemies_to_clear=400)
        ajustado = MetaProgressionService.resolve_level_config(profile, base)

        assert ajustado.enemies_to_clear < base.enemies_to_clear
        assert ajustado.enemy_spawn_config[_Enemy] > base.enemy_spawn_config[_Enemy]

    def test_fase_de_entrada_nao_endurece_para_quem_trava_adiante(self, tmp_path):
        """O cenário que motivou o gate de fronteira, ponta a ponta."""
        profile = PlayerProfile(profile_path=tmp_path / "profile.json")
        # Fase 2 limpa em toda run (o jogador passa por ela toda vez)...
        profile.level_stats[2] = make_stats(30, 30, level_number=2)
        # ...porque morre lá na frente.
        profile.highest_level_reached = 12

        base = make_config(level_number=2, enemies_to_clear=400)
        ajustado = MetaProgressionService.resolve_level_config(profile, base)

        assert ajustado.enemies_to_clear <= base.enemies_to_clear


class TestAnalyzerRelatorio:
    def test_relatorio_nao_decide_dificuldade(self):
        """O número vem do `DifficultyAdjuster`; o analyzer só descreve."""
        analysis = PerformanceAnalyzer.analyze_level_performance(make_stats(20, 1))
        assert "adjustment" not in analysis
        assert "confidence" not in analysis

    def test_relatorio_traz_estado_e_motivo(self):
        analysis = PerformanceAnalyzer.analyze_level_performance(
            make_stats(20, 1, outcomes=[False] * 6)
        )
        assert analysis["state"] == PerformanceState.STRUGGLING
        assert analysis["reason"]

    def test_dominando_e_descrito_como_tal(self):
        n = 10
        stats = make_stats(
            n, n, outcomes=[True] * 6, best_time=10.0, total_time=10.0 * n
        )
        stats.current_win_streak = 5
        assert stats.clear_rate > DOMINATE_CLEAR_RATE
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)
        assert analysis["state"] == PerformanceState.DOMINATING
