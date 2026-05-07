from .config import PowerUpType
from .difficulty import DifficultyPreset


def get_powerup_weights(difficulty: DifficultyPreset) -> dict[PowerUpType, int]:
    """
    Retorna pesos de power-ups ajustados pela dificuldade.
    Em dificuldades mais altas, power-ups ficam mais raros (pesos menores).
    """
    # Pesos base (de Config.POWERUP_WEIGHTS, multiplicados por 10)
    base_weights = {
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
    }

    # Multiplicadores para raridade por dificuldade
    rarity_multiplier = {
        DifficultyPreset.CASUAL: 1.2,  # Mais comuns (20% a mais)
        DifficultyPreset.NORMAL: 1.0,  # Padrão
        DifficultyPreset.HARDCORE: 0.7,  # Menos comuns (30% a menos)
        DifficultyPreset.NIGHTMARE: 0.5,  # Muito raros (50% a menos)
    }.get(difficulty, 1.0)

    # Aplica multiplicador e converte para int
    return {k: max(1, int(v * rarity_multiplier)) for k, v in base_weights.items()}
