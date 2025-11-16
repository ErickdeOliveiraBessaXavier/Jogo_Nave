"""
Configurações do sistema de som.
"""

from enum import Enum
from typing import Dict, Any, Union


class SoundType(Enum):
    """Tipos de sons disponíveis."""

    # Tiros
    SHOT = "shot"

    # Boss Laser
    BOSS_LASER_CHARGING = "boss_laser_charging"
    BOSS_LASER_FIRE = "boss_laser_fire"

    # Explosões
    EXPLOSION_ASTEROID = "explosion_asteroid"
    EXPLOSION_ALIEN = "explosion_alien"
    EXPLOSION_BOSS = "explosion_boss"
    EXPLOSION_SHIP = "explosion_ship"

    # Boss
    BOSS_DAMAGE = "boss_damage"

    # UI
    WARNING = "warning"
    POWERUP = "powerup"  # Adicionado

    # Música
    MUSIC_BACKGROUND = "music_background"
    MUSIC_BOSS = "music_boss"


class SoundCategory(Enum):
    """Categorias de sons."""

    SFX = "sfx"
    MUSIC = "music"
    UI = "ui"


# Configurações de volume
VOLUME_CONFIG: Dict[str, float] = {
    "master": 0.5,  # Volume geral
    "sfx": 0.4,  # Efeitos sonoros
    "music": 0.3,  # Música
    "boss_music": 0.8,  # Música do boss
    "shots": 0.2,  # Tiros específico
    "boss_laser": 0.35,  # Som do laser do boss (balanceado com música)
    "powerup": 0.6,  # Volume do power-up
}

# Configurações de canais
CHANNEL_CONFIG: Dict[str, int] = {
    "shots": 0,  # Canal dedicado para tiros
    "warning": 1,  # Canal dedicado para warning
    "boss_laser": 2,  # Canal dedicado para carregamento do laser do boss
    "boss_laser_fire": 3,  # Canal dedicado para disparo do laser do boss
    "max_channels": 8,  # Número máximo de canais
}

# Configurações de paths
SOUND_PATHS: Dict[str, Union[str, Dict[str, Any]]] = {
    "base": "game/assets/sounds",
    # Música
    "music": {
        "background": [
            "music/background.mp3",
            "music/background_02.mp3",
        ],
        "boss": "music/boss.mp3",
        "spike_boss": "music/spike_boss_theme.mp3",
    },
    # Efeitos sonoros
    "sfx": {
        "shots": "sfx/shots/tiro_{}.wav",  # {} será substituído por 1,2,3
        "boss_laser_charging": "sfx/shots/som_laser_carregando.mp3",
        "boss_laser_fire": "sfx/shots/som_laser.mp3",
        "explosions": {
            "asteroid": "sfx/explosions/explosão_asteroides_{}.wav",  # {} = 0,1,2,3
            "alien": "sfx/explosions/explosão_naves_alienigenas.wav",
            "boss": "sfx/explosions/explisão_boss.wav",
            "ship": "sfx/explosions/explisão_nave.wav",
            "boss_damage": "sfx/explosions/som_dano_boss.wav",
        },
        "ui": {
            "warning": "sfx/ui/warning.mp3",
            "powerup": "sfx/ui/powerUp.wav",  # Adicionado
        },
    },
}

# Configurações de comportamento
BEHAVIOR_CONFIG: Dict[str, Dict[str, Union[bool, float]]] = {
    "shot_anti_irritation": {
        "enabled": True,
        "min_interval": 0.05,  # Intervalo mínimo entre tiros (segundos)
        "volume_reduction": 0.8,  # Reduzir volume após muitos tiros
    },
    "music": {
        "loop": True,
        "fade_duration": 1.0,  # Duração do fade ao trocar música
    },
    "boss_laser": {
        "duck_music": True,  # Reduzir música durante som do laser
        "duck_volume": 0.6,  # Volume da música durante o laser (60% do normal)
        "fade_in": 0.1,  # Fade in suave para o som
        "fade_out": 0.2,  # Fade out suave para o som
    },
}

# Configuração completa
SOUND_CONFIG: Dict[str, Any] = {
    "volumes": VOLUME_CONFIG,
    "channels": CHANNEL_CONFIG,
    "paths": SOUND_PATHS,
    "behavior": BEHAVIOR_CONFIG,
}
