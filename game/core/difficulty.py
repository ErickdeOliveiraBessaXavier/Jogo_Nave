from enum import Enum
from functools import lru_cache
from typing import NotRequired, TypedDict


class DifficultySettingsDict(TypedDict):
    """Estrutura das configurações de dificuldade."""

    name: str
    description: str
    difficulty_scaling: float
    spawn_rate_multiplier: float
    enemy_health_multiplier: float
    player_damage_multiplier: float
    lives: int
    rewards_multiplier: float
    # Multiplica a frequência de power-ups. >1 = mais frequente (Casual),
    # <1 = mais raro (Hardcore/Pesadelo). Aplicado dividindo o intervalo
    # base, análogo ao spawn_rate_multiplier de inimigos.
    powerup_spawn_rate_multiplier: float
    # Multiplica a velocidade de movimento e tiro dos inimigos.
    # >1 = mais rápido/letal (Hardcore/Pesadelo), <1 = mais lento (Casual).
    aggressiveness_multiplier: float
    special_rules: NotRequired[
        list[str]
    ]  # Regras especiais opcionais (ex.: "permadeath")


class DifficultyPreset(Enum):
    """Presets de dificuldade para o jogador escolher."""

    CASUAL = "casual"
    NORMAL = "normal"
    HARDCORE = "hardcore"
    NIGHTMARE = "nightmare"


class DifficultySettings:
    """Configurações específicas por preset de dificuldade."""

    PRESETS: dict[DifficultyPreset, DifficultySettingsDict] = {
        DifficultyPreset.CASUAL: {
            "name": "Casual",
            "description": "Relaxe e aproveite a jornada",
            "difficulty_scaling": 0.10,  # Dificuldade sobe mais devagar
            "spawn_rate_multiplier": 0.75,  # Menos inimigos por segundo
            "enemy_health_multiplier": 0.8,  # Inimigos mais fracos
            "player_damage_multiplier": 1.3,  # Jogador mais forte
            "lives": 5,  # Mais vidas
            "rewards_multiplier": 0.8,  # Menos recompensas
            "powerup_spawn_rate_multiplier": 1.3,  # Power-ups mais frequentes
            "aggressiveness_multiplier": 0.85,  # Inimigos e projéteis mais lentos
        },
        DifficultyPreset.NORMAL: {
            "name": "Normal",
            "description": "Experiência balanceada",
            "difficulty_scaling": 0.15,
            "spawn_rate_multiplier": 1.0,
            "enemy_health_multiplier": 1.0,
            "player_damage_multiplier": 1.0,
            "lives": 3,
            "rewards_multiplier": 1.0,
            "powerup_spawn_rate_multiplier": 1.0,
            "aggressiveness_multiplier": 1.0,
        },
        DifficultyPreset.HARDCORE: {
            "name": "Hardcore",
            "description": "Para veteranos",
            "difficulty_scaling": 0.22,
            "spawn_rate_multiplier": 1.2,
            "enemy_health_multiplier": 1.3,
            "player_damage_multiplier": 0.9,
            "lives": 2,
            "rewards_multiplier": 1.5,
            "powerup_spawn_rate_multiplier": 0.7,  # ~43% mais raros
            "aggressiveness_multiplier": 1.20,  # 20% mais rápido/letal
        },
        DifficultyPreset.NIGHTMARE: {
            "name": "Pesadelo",
            "description": "Você foi avisado",
            "difficulty_scaling": 0.30,
            "spawn_rate_multiplier": 1.55,
            "enemy_health_multiplier": 1.5,
            "player_damage_multiplier": 0.8,
            "lives": 1,  # Permadeath!
            "rewards_multiplier": 3.0,  # Alta recompensa, alto risco
            "powerup_spawn_rate_multiplier": 0.5,  # 2x mais raros
            "aggressiveness_multiplier": 1.45,  # 45% mais rápido/letal
            "special_rules": ["permadeath"],
        },
    }

    @classmethod
    @lru_cache(maxsize=4)
    def _get_settings_cached(cls, preset: DifficultyPreset) -> DifficultySettingsDict:
        """Retorna referência cacheada interna (não expor fora da classe)."""
        return cls.PRESETS[preset]

    @classmethod
    def get_settings(cls, preset: DifficultyPreset) -> DifficultySettingsDict:
        """Retorna cópia defensiva das configurações para um preset."""
        return cls._get_settings_cached(preset).copy()
