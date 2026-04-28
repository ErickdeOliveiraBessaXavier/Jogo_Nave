import os
import sys

# Permite importar pacote `game` quando rodando direto no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.levels import DifficultyPreset, get_level_config

# Força o procedural meteor_storm no nível 1
level_config = get_level_config(
    1, difficulty_preset=DifficultyPreset.NORMAL, force_meteor_storm=True
)

print(f"Nível: {level_config.level_number}")
print(f"Tema: {level_config.theme_name}")
print(f"Boss: {level_config.boss_type}")
print(f"Inimigos para limpar: {level_config.enemies_to_clear}")
print(f"Configuração de spawn: {level_config.enemy_spawn_config}")
print(f"Mines: {level_config.mines_enabled}")
print(f"Formations: {level_config.formations_enabled}")
