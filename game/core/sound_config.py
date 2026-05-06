"""
Configurações do sistema de som.
"""

from enum import Enum
from typing import Any, Dict, Union


class MusicState(Enum):
    MENU = "menu"
    GAME = "game"
    BOSS = "boss"
    SPIKE_BOSS = "spike_boss"
    SLIME_BOSS = "slime_boss"
    GIANT_METEOR_BOSS = "giant_meteor_boss"
    MOUNTAIN_SERPENT_BOSS = "mountain_serpent_boss"
    CLOUD_ARCHMAGE_BOSS = "cloud_archmage_boss"
    SILENCE = "silence"


MUSIC_BEHAVIOR_CONFIG: Dict[str, Any] = {
    "auto_resume_from_pause": True,
    "prevent_menu_over_game": True,
    "context_aware_transitions": True,
}


class SoundType(Enum):
    """Tipos de sons disponíveis."""

    # Tiros
    SHOT = "shot"
    LASER_SHOT = "laser_shot"  # Som do laser do upgrade LASER_SHOT

    # Boss Laser
    BOSS_LASER_CHARGING = "boss_laser_charging"
    BOSS_LASER_FIRE = "boss_laser_fire"
    SPIKE_BOSS_LASER = "spike_boss_laser"  # Adicionado

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
    "master": 0.8,  # Volume geral
    "sfx": 0.3,  # Efeitos sonoros
    "music": 0.6,  # Música de background (aumentado de 0.5 para 0.6)
    "boss_music": 0.7,  # Música do boss (reduzido de 2.5 para 0.7 - mais balanceado)
    "shots": 0.2,  # Tiros específico
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
            "music/Lost_Sector_Loop.mp3",
            "music/Starcruiser_Loop.mp3",
            "music/Event_Horizon_Pulse.mp3",
            "music/Rising_From_Restraint_War.mp3",
            "music/Rising_From_Restraint.mp3",
        ],
        "boss": "music/boss.mp3",
        "menu": "music/menu-music.mp3",
        "spike_boss": "music/spike_boss_theme.mp3",
        "slime_boss": "music/Boss-Slime-Theme.mp3",
        "giant_meteor_boss": "music/Musica_Giant_Meteor_Boss.mp3",
        "mountain_serpent_boss": "music/Stone_Snake_Themel.mp3",
        "cloud_archmage_boss": "music/Mago_Robo_Boss.mp3",
    },
    # Efeitos sonoros
    "sfx": {
        "shots": "sfx/shots/tiro_{}.wav",  # {} será substituído por 1,2,3
        "boss_laser_charging": "sfx/shots/som_laser_carregando.mp3",
        "boss_laser_fire": "sfx/shots/som_laser.mp3",
        "spike_boss_laser": "sfx/shots/laser_spike_boss.wav",  # Adicionado
        "explosions": {
            "asteroid": "sfx/explosions/explosão_asteroides_{}.wav",  # {} = 0,1,2,3
            "alien": "sfx/explosions/explosão_naves_alienigenas.wav",
            "boss": "sfx/explosions/explisão_boss.wav",
            "ship": "sfx/explosions/explisão_nave.wav",
            "boss_damage": "sfx/explosions/som_dano_boss.wav",
        },
        "ui": {
            "warning": "sfx/ui/warning.mp3",
            "powerup": "sfx/ui/powerUp.wav",
            "button_click": "sfx/ui/button_click.wav",
            "button_hover": "sfx/ui/sound_hover.wav",
            "upgrade_activate": "sfx/ui/Ativação_Aprimoramentos.wav",
            "meteor_rain": "sfx/ui/som_chuva_meteoro_{}.wav",  # {} = 1,2,3,4
            "laser_shot": "sfx/ui/som_laser_raio.mp3",  # Som do laser do upgrade LASER_SHOT
            "black_hole": "sfx/ui/Buraco_negro_Som.mp3",  # Som do buraco negro
            "hit_hurt_meteor_boss": "sfx/ui/hit_hurt_meteor_boss.wav",  # Som de rachadura do boss meteoro
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
        "fade_duration": 0.5,  # Duração do fade ao trocar música
    },
}

# Configuração completa
SOUND_CONFIG: Dict[str, Any] = {
    "volumes": VOLUME_CONFIG,
    "channels": CHANNEL_CONFIG,
    "paths": SOUND_PATHS,
    "behavior": BEHAVIOR_CONFIG,
}
