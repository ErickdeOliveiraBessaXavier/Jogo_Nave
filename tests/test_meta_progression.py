"""Contratos do ajuste dinâmico de dificuldade (`meta_progression`).

Lógica pura (§16): diagnóstico de performance + política de ajuste. Não
instancia o jogo nem toca em pygame — só monta `LevelPerformance` e
`LevelConfig` sintéticos.

Cada teste aqui trava um comportamento que já esteve errado em produção; o
docstring de cada um diz qual. O tema comum é o §11: errar para o lado fácil
custa uma fase morna, errar para o lado difícil custa o jogador.
"""

from game.core.levels import DifficultyConfig, LevelConfig
from game.core.meta_progression import (
    DOMINATE_CLEAR_RATE,
    MIN_ATTEMPTS_TO_DIAGNOSE,
    STRUGGLE_CLEAR_RATE,
    DifficultyAdjuster,
    LevelPerformance,
    PerformanceAnalyzer,
    PerformanceState,
)


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


# ---------------------------------------------------------------------------
# Diagnóstico: os limiares têm UMA fonte
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
        # Logo ACIMA do limiar de struggle: não é struggling.
        attempts = 100
        clears = int(attempts * STRUGGLE_CLEAR_RATE) + 1
        assert make_stats(attempts, clears).get_performance_state() != (
            PerformanceState.STRUGGLING
        )
        # Logo ABAIXO: é.
        clears = int(attempts * STRUGGLE_CLEAR_RATE) - 1
        assert make_stats(attempts, clears).get_performance_state() == (
            PerformanceState.STRUGGLING
        )


# ---------------------------------------------------------------------------
# Política de ajuste
# ---------------------------------------------------------------------------


class TestApplyAdjustment:
    def test_confianca_media_preserva_o_sinal_do_ajuste(self):
        """O bug de sinal invertido.

        A conta era `sugerido * fator`: "dominando" sugeria 1.08, virava
        1.08*0.6 = 0.648 e o jogo ficava ~18% MAIS FÁCIL para quem estava
        dominando. Ajuste sugerido acima de 1.0 tem de resultar em acima de 1.0.
        """
        analysis = {"adjustment": 1.08, "confidence": "medium", "reason": ""}
        _, mult = DifficultyAdjuster.apply_adjustment(make_config(), analysis, 1.0)
        assert mult > 1.0

    def test_confianca_media_nao_estoura_o_piso_no_alivio(self):
        """Mesmo bug, lado do alívio: 0.85*0.6 = 0.51 saltava direto ao piso.

        Um passo de confiança MÉDIA deve ser mais suave que o alvo sugerido.
        """
        analysis = {"adjustment": 0.85, "confidence": "medium", "reason": ""}
        _, mult = DifficultyAdjuster.apply_adjustment(make_config(), analysis, 1.0)
        assert 0.85 < mult < 1.0

    def test_confianca_baixa_congela_o_ajuste_vigente(self):
        """Não volta para 1.0.

        Cenário original: jogador travado, já aliviado em 0.85, começa a
        melhorar → ramo "lutando mas melhorando" (confiança baixa) → o ajuste
        voltava a 1.0 e ele levava os 15% de volta na cara justamente ao
        progredir.
        """
        analysis = {"adjustment": 0.95, "confidence": "low", "reason": ""}
        config, mult = DifficultyAdjuster.apply_adjustment(make_config(), analysis, 0.85)
        assert mult == 0.85
        assert config.enemies_to_clear < make_config().enemies_to_clear

    def test_alivio_converge_mais_rapido_que_aperto(self):
        ease = {"adjustment": 0.85, "confidence": "high", "reason": ""}
        harden = {"adjustment": 1.15, "confidence": "high", "reason": ""}

        _, eased = DifficultyAdjuster.apply_adjustment(make_config(), ease, 1.0)
        _, hardened = DifficultyAdjuster.apply_adjustment(make_config(), harden, 1.0)

        assert abs(eased - 1.0) > abs(hardened - 1.0)

    def test_convergencia_estavel_dentro_dos_limites(self):
        analysis = {"adjustment": 0.85, "confidence": "high", "reason": ""}
        mult = 1.0
        for _ in range(50):
            _, mult = DifficultyAdjuster.apply_adjustment(make_config(), analysis, mult)
        assert DifficultyAdjuster.MIN_ADJUSTMENT <= mult <= DifficultyAdjuster.MAX_ADJUSTMENT
        assert abs(mult - 0.85) < 0.01

    def test_ajuste_nunca_sai_dos_limites(self):
        extremos = [
            {"adjustment": 0.1, "confidence": "high", "reason": ""},
            {"adjustment": 9.0, "confidence": "high", "reason": ""},
        ]
        for analysis in extremos:
            mult = 1.0
            for _ in range(50):
                _, mult = DifficultyAdjuster.apply_adjustment(
                    make_config(), analysis, mult
                )
            assert (
                DifficultyAdjuster.MIN_ADJUSTMENT
                <= mult
                <= DifficultyAdjuster.MAX_ADJUSTMENT
            )

    def test_banda_neutra_devolve_a_config_base_intocada(self):
        base = make_config()
        analysis = {"adjustment": 1.0, "confidence": "high", "reason": ""}
        config, mult = DifficultyAdjuster.apply_adjustment(base, analysis, 1.0)
        assert mult == 1.0
        assert config is base

    def test_banda_neutra_nao_trava_a_convergencia_lenta(self):
        """A banda decide se vale materializar uma config diferente — não pode
        arredondar o valor PERSISTIDO.

        Arredondando, um aperto suave (alvo 1.048 a 0.25 por tentativa) rendia
        1.012, virava 1.0, e o passo seguinte recomeçava do zero: o ramo ficava
        preso na banda para sempre.
        """
        analysis = {"adjustment": 1.08, "confidence": "medium", "reason": ""}
        mult = 1.0
        for _ in range(10):
            _, mult = DifficultyAdjuster.apply_adjustment(make_config(), analysis, mult)
        assert mult > 1.0 + DifficultyAdjuster.NEUTRAL_BAND


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
        analysis = {"adjustment": 1.15, "confidence": "high", "reason": ""}
        _, mult = DifficultyAdjuster.apply_adjustment(
            make_config(), analysis, 1.0, allow_hardening=False
        )
        assert mult <= 1.0

    def test_gate_fechado_deixa_ajuste_alto_decair_para_o_neutro(self):
        """Quem já estava endurecido não fica preso: o alvo é limitado a 1.0 e
        o multiplicador anda de volta ao neutro."""
        analysis = {"adjustment": 1.15, "confidence": "high", "reason": ""}
        _, mult = DifficultyAdjuster.apply_adjustment(
            make_config(), analysis, 1.20, allow_hardening=False
        )
        assert mult < 1.20

    def test_gate_fechado_nao_impede_alivio(self):
        """Ajudar é sempre permitido — o gate é só do aperto."""
        analysis = {"adjustment": 0.85, "confidence": "high", "reason": ""}
        _, mult = DifficultyAdjuster.apply_adjustment(
            make_config(), analysis, 1.0, allow_hardening=False
        )
        assert mult < 1.0


class TestApplyToConfig:
    def test_multiplicador_alto_acelera_spawn_e_aumenta_contagem(self):
        base = make_config(enemies_to_clear=200, spawn_time=2.0)
        adjusted = DifficultyAdjuster._apply_to_config(base, 1.2)
        assert adjusted.enemy_spawn_config[_Enemy] < 2.0
        assert adjusted.enemies_to_clear > 200

    def test_multiplicador_baixo_desacelera_spawn_e_reduz_contagem(self):
        base = make_config(enemies_to_clear=200, spawn_time=2.0)
        adjusted = DifficultyAdjuster._apply_to_config(base, 0.8)
        assert adjusted.enemy_spawn_config[_Enemy] > 2.0
        assert adjusted.enemies_to_clear < 200

    def test_respeita_o_piso_de_spawn_do_pipeline(self):
        base = make_config(spawn_time=DifficultyConfig.MIN_SPAWN_TIME)
        adjusted = DifficultyAdjuster._apply_to_config(base, 1.25)
        assert adjusted.enemy_spawn_config[_Enemy] >= DifficultyConfig.MIN_SPAWN_TIME

    def test_respeita_o_piso_de_inimigos_do_pipeline(self):
        """Antes era um `max(20, ...)` solto, desalinhado do
        `MIN_ENEMIES_TO_CLEAR` do pipeline — o adaptativo furava em 25% o
        mínimo que o próprio pipeline declara."""
        base = make_config(enemies_to_clear=DifficultyConfig.MIN_ENEMIES_TO_CLEAR)
        adjusted = DifficultyAdjuster._apply_to_config(base, 0.75)
        assert adjusted.enemies_to_clear >= DifficultyConfig.MIN_ENEMIES_TO_CLEAR

    def test_nao_muta_a_config_base(self):
        base = make_config(enemies_to_clear=200, spawn_time=2.0)
        DifficultyAdjuster._apply_to_config(base, 0.8)
        assert base.enemies_to_clear == 200
        assert base.enemy_spawn_config[_Enemy] == 2.0


class TestAnalyzerIntegration:
    def test_dados_insuficientes_nao_ajustam(self):
        stats = make_stats(MIN_ATTEMPTS_TO_DIAGNOSE - 1, 0)
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)
        assert analysis["adjustment"] == 1.0

    def test_struggling_sem_melhora_pede_alivio(self):
        stats = make_stats(10, 1, outcomes=[False] * 6)
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)
        assert analysis["state"] == PerformanceState.STRUGGLING
        assert analysis["adjustment"] < 1.0

    def test_dominando_pede_aperto(self):
        n = 10
        stats = make_stats(
            n, n, outcomes=[True] * 6, best_time=10.0, total_time=10.0 * n
        )
        stats.current_win_streak = 5
        assert stats.clear_rate > DOMINATE_CLEAR_RATE
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)
        assert analysis["state"] == PerformanceState.DOMINATING
        assert analysis["adjustment"] > 1.0
