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
        # Leque: o "Double Shot grande". Peso baixo de propósito — vale mais que
        # o duplo (cobertura + ~2,1x de DPS de pico), então precisa ser o achado
        # ocasional, não o pão de cada dia.
        PowerUpType.SPREAD_SHOT: 60,
        PowerUpType.SPEED: 150,
        PowerUpType.COOLDOWN_HASTE: 50,
        PowerUpType.MINI_SHIPS: 50,
        PowerUpType.PIERCING_SHOT: 50,
        PowerUpType.LIFE: 50,
        PowerUpType.SCORE: 20,
        PowerUpType.TIME_STOP: 70,
        PowerUpType.RAINBOW: 10,
        PowerUpType.DAMAGE_BOOST: 80,
        PowerUpType.CHAIN_SHOT: 60,
        PowerUpType.REPULSION_SHIELD: 60,
    }
