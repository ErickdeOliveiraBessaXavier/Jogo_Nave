"""Rampa de entrada de mundo + escala de co-op (`_apply_stage_grace_and_coop`).

Este passo é COMUM aos três caminhos de `get_level_config` (fixo,
meteor_storm, procedural) — antes eram três cópias verbatim do mesmo bloco.
Os testes cobrem o helper diretamente e depois verificam que o piso de spawn
sobrevive ao caminho completo, que é onde o furo acontecia.
"""

import pytest

from game.core.difficulty import DifficultyPreset
from game.core.levels import DifficultyConfig, LevelConfig, get_level_config
from game.core.levels.pipeline import _STAGE_ENTRY_GRACE, _apply_stage_grace_and_coop
from game.core.world_config import get_world_for_level


class _Enemy:
    pass


def make_config(level_number: int, spawn_time: float, enemies: int) -> LevelConfig:
    return LevelConfig(
        level_number=level_number,
        enemy_spawn_config={_Enemy: spawn_time},
        enemies_to_clear=enemies,
    )


def first_level_of_a_world() -> int:
    """Um nível cujo estágio dentro do mundo é 1 (entrada, grace máximo)."""
    for level in range(1, 200):
        if get_world_for_level(level).get_stage_number(level) == 1:
            return level
    raise AssertionError("nenhum nível de entrada de mundo encontrado")


class TestStageGrace:
    def test_entrada_de_mundo_alivia_spawn_e_contagem(self):
        level = first_level_of_a_world()
        world = get_world_for_level(level)
        base = make_config(level, spawn_time=4.0, enemies=1000)

        adjusted = _apply_stage_grace_and_coop(base, world, level, player_count=1)

        # grace < 1.0 => intervalo MAIOR (menos pressão) e menos inimigos.
        assert adjusted.enemy_spawn_config[_Enemy] > 4.0
        assert adjusted.enemies_to_clear < 1000

    def test_estagio_sem_grace_nao_altera_nada_em_single_player(self):
        level = None
        for candidate in range(1, 200):
            world = get_world_for_level(candidate)
            if world.get_stage_number(candidate) not in _STAGE_ENTRY_GRACE:
                level = candidate
                break
        if level is None:
            pytest.skip("nenhum estágio fora da rampa de grace nos 200 primeiros")

        world = get_world_for_level(level)
        base = make_config(level, spawn_time=4.0, enemies=1000)
        adjusted = _apply_stage_grace_and_coop(base, world, level, player_count=1)

        assert adjusted.enemy_spawn_config[_Enemy] == 4.0
        assert adjusted.enemies_to_clear == 1000

    def test_nao_muta_a_config_recebida(self):
        level = first_level_of_a_world()
        world = get_world_for_level(level)
        base = make_config(level, spawn_time=4.0, enemies=1000)

        _apply_stage_grace_and_coop(base, world, level, player_count=2)

        assert base.enemy_spawn_config[_Enemy] == 4.0
        assert base.enemies_to_clear == 1000


class TestCoopScaling:
    def test_jogador_extra_aumenta_pressao(self):
        level = first_level_of_a_world()
        world = get_world_for_level(level)
        base = make_config(level, spawn_time=4.0, enemies=1000)

        solo = _apply_stage_grace_and_coop(base, world, level, player_count=1)
        duo = _apply_stage_grace_and_coop(base, world, level, player_count=2)

        assert duo.enemy_spawn_config[_Enemy] < solo.enemy_spawn_config[_Enemy]
        assert duo.enemies_to_clear > solo.enemies_to_clear

    def test_coop_nao_fura_o_piso_de_spawn(self):
        """O bug: o grace só ALONGA o intervalo, mas a divisão por
        `coop_spawn_multiplier` o encurta e roda DEPOIS dos clamps do gerador
        procedural e do `_apply_difficulty_to_fixed_level`. Sem reclamp,
        2 jogadores viam 0.5s / 1.2 = 0.417s."""
        level = first_level_of_a_world()
        world = get_world_for_level(level)
        base = make_config(
            level, spawn_time=DifficultyConfig.MIN_SPAWN_TIME, enemies=1000
        )

        adjusted = _apply_stage_grace_and_coop(base, world, level, player_count=4)

        assert adjusted.enemy_spawn_config[_Enemy] >= DifficultyConfig.MIN_SPAWN_TIME


class TestPipelineEndToEnd:
    @pytest.mark.parametrize("player_count", [1, 2, 3, 4])
    @pytest.mark.parametrize("preset", list(DifficultyPreset))
    def test_piso_de_spawn_sobrevive_ao_pipeline_completo(self, preset, player_count):
        for level in range(1, 41):
            config = get_level_config(level, preset, player_count=player_count)
            for enemy_type, spawn_time in config.enemy_spawn_config.items():
                assert spawn_time >= DifficultyConfig.MIN_SPAWN_TIME, (
                    f"level={level} preset={preset} players={player_count} "
                    f"enemy={enemy_type.__name__} spawn={spawn_time}"
                )

    @pytest.mark.parametrize("player_count", [1, 2, 4])
    def test_piso_de_inimigos_sobrevive_ao_pipeline_completo(self, player_count):
        for level in range(1, 41):
            config = get_level_config(
                level, DifficultyPreset.NORMAL, player_count=player_count
            )
            assert config.enemies_to_clear >= DifficultyConfig.MIN_ENEMIES_TO_CLEAR
