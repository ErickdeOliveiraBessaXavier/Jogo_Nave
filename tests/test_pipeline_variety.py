"""Invariantes do pipeline de progressão / variety cap (§11 do CLAUDE.md).

O pipeline de composição de fases (`_apply_enemy_variety_cap`, `_select_variety_subset`,
`_global_variety_ceiling`) é a lógica pura mais sofisticada do projeto — curva de
introdução, triangulação por papel, recência e anti-repetição do triângulo — e é
justamente onde os "Ajustes" de balanceamento mais mexem. Uma regressão aqui é
**invisível em teste manual** (ninguém percebe que um inimigo sumiu do pool no mundo
4-3, ou que o teto vazou para 4 tipos no Normal).

Estes testes travam as **fronteiras** que o §11 promete, não números exatos:
  - o teto por nível: `não-ocasionais <= min(estágio_absoluto, teto_da_dificuldade)`;
  - nenhum nível vaza inimigo de outro tema (todo caminho passa pelo pipeline);
  - nenhum nível fica sem inimigos (fallback funciona);
  - o SWARM-base abre cada mundo sozinho (X-1 → 1 tipo);
  - a seleção é determinística por nível (salt 0), e o salt de run muda a seleção.

Faixa, não micro-ajuste (§16): o que trava é o outlier grosseiro (teto estourado,
tema vazado), não a escolha específica de specials — essa muda a cada tuning.
"""

import pytest

from game.core.difficulty import DifficultyPreset
from game.core.levels.pipeline import (
    THEME_BASE_ENEMY,
    VARIETY_CAP_FLOOR_BY_DIFFICULTY,
    VARIETY_CAP_MAX_BY_DIFFICULTY,
    _global_variety_ceiling,
    _is_enemy_allowed_in_theme,
    get_level_config,
    set_run_variety_salt,
)
from game.core.world_config import WorldTheme, get_world_for_level

# Cobre os 4 mundos nomeados (W1-W4, L1-45) e um bom trecho procedural (W5+),
# onde os temas rotacionam e os gates de introdução precisam valer em qualquer
# tamanho de mundo.
_LEVEL_RANGE = range(1, 121)
_PRESETS = list(DifficultyPreset)


def _non_occasional(config) -> list[type]:
    """Tipos que DISPUTAM vaga no variety cap.

    Tipos marcados `OCCASIONAL_THREAT` (SquareMinionBoss, GuidedMeteor) são uma
    camada separada — o `_apply_enemy_variety_cap` os remove antes da seleção e os
    devolve intactos no fim (não contam no teto). O invariante do §11 é sobre a
    composição principal, então espelhamos exatamente esse recorte usando o mesmo
    class attribute que o pipeline usa.
    """
    return [
        t
        for t in config.enemy_spawn_config
        if not getattr(t, "OCCASIONAL_THREAT", False)
    ]


class TestVarietyCeiling:
    """`_global_variety_ceiling` — teto puro dirigido pelo tamanho do pool."""

    @pytest.mark.parametrize("preset", _PRESETS)
    def test_dentro_de_floor_e_max(self, preset):
        floor = VARIETY_CAP_FLOOR_BY_DIFFICULTY[preset]
        cap_max = VARIETY_CAP_MAX_BY_DIFFICULTY[preset]
        for pool_size in range(1, 21):
            c = _global_variety_ceiling(pool_size, preset)
            assert floor <= c <= cap_max, (preset.name, pool_size, c)

    @pytest.mark.parametrize("preset", _PRESETS)
    def test_monotonico_no_tamanho_do_pool(self, preset):
        # Mais tipos disponíveis nunca REDUZ o número de vagas.
        prev = 0
        for pool_size in range(1, 21):
            c = _global_variety_ceiling(pool_size, preset)
            assert c >= prev, (preset.name, pool_size)
            prev = c

    def test_teto_por_dificuldade(self):
        # A promessa do §11: 3 no Normal/Casual, 4 no Hardcore/Pesadelo.
        assert VARIETY_CAP_MAX_BY_DIFFICULTY[DifficultyPreset.CASUAL] == 3
        assert VARIETY_CAP_MAX_BY_DIFFICULTY[DifficultyPreset.NORMAL] == 3
        assert VARIETY_CAP_MAX_BY_DIFFICULTY[DifficultyPreset.HARDCORE] == 4
        assert VARIETY_CAP_MAX_BY_DIFFICULTY[DifficultyPreset.NIGHTMARE] == 4


class TestVarietyCapEndToEnd:
    """Sweep de `get_level_config` — o teto do §11 valendo end-to-end."""

    @pytest.mark.parametrize("preset", _PRESETS)
    def test_teto_por_nivel_respeitado(self, preset):
        """`não-ocasionais <= min(estágio_absoluto, teto)` — a regra `cap = min(
        estágio, teto)` do §11, aplicada a TODOS os caminhos (procedural,
        fixed, boss)."""
        cap_max = VARIETY_CAP_MAX_BY_DIFFICULTY[preset]
        violacoes = []
        for lvl in _LEVEL_RANGE:
            cfg = get_level_config(lvl, preset)
            world = get_world_for_level(lvl)
            stage = world.get_stage_number(lvl)
            n = len(_non_occasional(cfg))
            bound = min(stage, cap_max)
            if n > bound:
                nomes = [t.__name__ for t in _non_occasional(cfg)]
                violacoes.append(f"L{lvl} {world.theme.value} stage{stage}: {n}>{bound} {nomes}")
        assert not violacoes, "teto de variedade estourado (§11):\n" + "\n".join(violacoes)

    @pytest.mark.parametrize("preset", _PRESETS)
    def test_nenhum_vazamento_de_tema(self, preset):
        """Todo nível passa por `_apply_theme_enemy_rules`: nenhum inimigo de fora
        do tema sobrevive (§11 — nenhum nível burla o pipeline)."""
        violacoes = []
        for lvl in _LEVEL_RANGE:
            cfg = get_level_config(lvl, preset)
            world = get_world_for_level(lvl)
            for t in cfg.enemy_spawn_config:
                if not _is_enemy_allowed_in_theme(t, world.theme):
                    violacoes.append(f"L{lvl} {world.theme.value}: {t.__name__}")
        assert not violacoes, "inimigo fora do tema vazou:\n" + "\n".join(violacoes)

    @pytest.mark.parametrize("preset", _PRESETS)
    def test_nunca_fica_sem_inimigos(self, preset):
        """O fallback mínimo garante que nenhum nível gere um pool vazio."""
        for lvl in _LEVEL_RANGE:
            cfg = get_level_config(lvl, preset)
            assert cfg.enemy_spawn_config, f"L{lvl} {preset.name} sem inimigos"


class TestSwarmBaseOpensWorld:
    """§11 — 'SWARM + N complementares': o base do tema abre o mundo sozinho."""

    def test_x1_e_so_o_swarm_base(self):
        """No 1º estágio de cada MUNDO NOMEADO, o único tipo principal é o base
        do tema (X-1 → 1 tipo). Pega o pico de complexidade ao entrar num mundo
        novo — se um special vazar para o estágio de abertura, quebra aqui."""
        named = {
            WorldTheme.MOUNTAINS,
            WorldTheme.STARFIELD,
            WorldTheme.CITY,
            WorldTheme.VOLCANIC,
        }
        checados = 0
        for lvl in _LEVEL_RANGE:
            world = get_world_for_level(lvl)
            if world.theme not in named or world.start_level != lvl:
                continue
            base = THEME_BASE_ENEMY[world.theme]
            cfg = get_level_config(lvl, DifficultyPreset.NORMAL)
            principais = _non_occasional(cfg)
            assert principais == [base], (
                f"abertura do mundo L{lvl} ({world.theme.value}) deveria ser só "
                f"{base.__name__}, veio {[t.__name__ for t in principais]}"
            )
            checados += 1
        assert checados >= 4, f"esperava abrir 4 mundos nomeados, checou {checados}"


class TestDeterminismoESalt:
    """A seleção é determinística por nível; o salt de run a diversifica."""

    def test_mesmo_nivel_mesma_selecao(self):
        # Com salt 0 (default), rejogar o mesmo nível traz os mesmos tipos —
        # é o que mantém a anti-repetição entre fases vizinhas coerente.
        set_run_variety_salt(0)
        try:
            for lvl in (3, 17, 30, 44, 55):
                a = set(get_level_config(lvl, DifficultyPreset.NORMAL).enemy_spawn_config)
                b = set(get_level_config(lvl, DifficultyPreset.NORMAL).enemy_spawn_config)
                assert a == b, f"L{lvl} não-determinístico com salt 0"
        finally:
            set_run_variety_salt(0)

    def test_salt_muda_a_selecao_em_algum_nivel(self):
        """O salt de run precisa CHEGAR na seleção (senão um tipo que perde o
        sorteio teria chance ZERO para sempre, para todo jogador). Não fixamos um
        nível — qual nível varia depende do tuning; o invariante é que ALGUM nível
        de pool > vagas mude entre runs distintas."""
        set_run_variety_salt(0)
        try:
            baseline = {
                lvl: frozenset(get_level_config(lvl, DifficultyPreset.NORMAL).enemy_spawn_config)
                for lvl in _LEVEL_RANGE
            }
            algum_mudou = False
            for salt in (1, 7, 13, 29):
                set_run_variety_salt(salt)
                for lvl in _LEVEL_RANGE:
                    s = frozenset(get_level_config(lvl, DifficultyPreset.NORMAL).enemy_spawn_config)
                    if s != baseline[lvl]:
                        algum_mudou = True
                        break
                if algum_mudou:
                    break
            assert algum_mudou, "salt de run não alterou a seleção em NENHUM nível"
        finally:
            set_run_variety_salt(0)
