from .config import PowerUpType
from .difficulty import DifficultyPreset


def get_powerup_weights(difficulty: DifficultyPreset) -> dict[PowerUpType, int]:
    """Retorna pesos relativos de power-ups (qual aparece quando um spawn ocorre).

    A frequência de spawn (intervalo entre power-ups) é controlada
    separadamente em ``PowerUpSpawner`` via ``powerup_spawn_rate_multiplier``
    do preset. Aqui só controlamos a distribuição entre tipos quando um
    spawn já foi decidido — escalar todos os pesos pelo mesmo fator não
    muda a distribuição relativa (``random.choices`` normaliza), então
    isso é deixado igual entre dificuldades por enquanto.
    """
    del difficulty  # Reservado para futura modulação de distribuição.
    return {
        PowerUpType.SHIELD: 150,
        PowerUpType.DOUBLE_SHOT: 200,
        PowerUpType.SPEED: 150,
        PowerUpType.COOLDOWN_HASTE: 100,
        PowerUpType.MINI_SHIPS: 50,
        PowerUpType.PIERCING_SHOT: 50,
        PowerUpType.LIFE: 50,
        PowerUpType.SCORE: 20,
        PowerUpType.TIME_STOP: 20,
        PowerUpType.RAINBOW: 10,
        PowerUpType.DAMAGE_BOOST: 80,
        PowerUpType.CHAIN_SHOT: 60,
        PowerUpType.REPULSION_SHIELD: 60,
    }