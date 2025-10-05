"""
Configurações do sistema de som.
"""
from enum import Enum
from typing import Dict, Any, Union


class SoundType(Enum):
    """Tipos de sons disponíveis."""
    # Tiros
    SHOT = "shot"
    
    # Explosões
    EXPLOSION_ASTEROID = "explosion_asteroid"
    EXPLOSION_ALIEN = "explosion_alien"
    EXPLOSION_BOSS = "explosion_boss"
    EXPLOSION_SHIP = "explosion_ship"
    
    # Boss
    BOSS_DAMAGE = "boss_damage"
    
    # UI
    WARNING = "warning"
    
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
    "master": 0.5,      # Volume geral
    "sfx": 0.7,         # Efeitos sonoros
    "music": 0.3,       # Música
    "shots": 0.4,       # Tiros específico
}

# Configurações de canais
CHANNEL_CONFIG: Dict[str, int] = {
    "shots": 0,         # Canal dedicado para tiros
    "warning": 1,       # Canal dedicado para warning
    "max_channels": 8,  # Número máximo de canais
}

# Configurações de paths
SOUND_PATHS: Dict[str, Union[str, Dict[str, Any]]] = {
    "base": "game/assets/sounds",
    
    # Música
    "music": {
        "background": "music/background.mp3",
        "boss": "music/boss.mp3",
    },
    
    # Efeitos sonoros
    "sfx": {
        "shots": "sfx/shots/tiro_{}.wav",  # {} será substituído por 1,2,3
        "explosions": {
            "asteroid": "sfx/explosions/explosão_asteroides_{}.wav",  # {} = 0,1,2,3
            "alien": "sfx/explosions/explosão_naves_alienigenas.wav",
            "boss": "sfx/explosions/explisão_boss.wav",
            "ship": "sfx/explosions/explisão_nave.wav",
            "boss_damage": "sfx/explosions/som_dano_boss.wav",
        },
        "ui": {
            "warning": "sfx/ui/warning.mp3",
        }
    }
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
    }
}

# Configuração completa
SOUND_CONFIG: Dict[str, Any] = {
    "volumes": VOLUME_CONFIG,
    "channels": CHANNEL_CONFIG,
    "paths": SOUND_PATHS,
    "behavior": BEHAVIOR_CONFIG,
}