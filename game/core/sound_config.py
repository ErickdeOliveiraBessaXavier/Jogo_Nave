"""
Configurações do sistema de som.
"""

from enum import Enum
from typing import Any, Dict, FrozenSet, Union


class MusicState(Enum):
    """Estados de alto nível da música. Genérico e data-driven: o *qual* tema/boss
    tocar viaja no `key` do `MusicStateChange`, não em um membro por boss.

    `GAME` = música ambiente do tema atual (pasta `audio/music/themes/<tema>/`).
    `BOSS` = música exclusiva do boss ativo (pasta `audio/music/bosses/<BOSS_TYPE_NAME>/`).
    Antes existia um membro por boss (SPIKE_BOSS, STONE_GOLEM_BOSS, ...); foram
    removidos — a identidade da faixa agora vem da pasta, não do enum.
    """

    MENU = "menu"
    GAME = "game"
    BOSS = "boss"
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
    ORBITAL_DISCHARGE = "orbital_discharge"  # Arco elétrico dos orbes

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


# Configurações de volume — fonte única de verdade para defaults de áudio.
# UserPreferences importa estes valores; a UI os expõe como sliders 0–100%.
VOLUME_CONFIG: Dict[str, float] = {
    "master": 1.0,  # Multiplicador global (não exposto na UI)
    "music": 0.75,  # Música de background
    "sfx": 0.3,  # Efeitos sonoros
    "shots": 0.2,  # Tiros (canal separado)
    "boss_music": 1.0,  # Multiplicador da música de boss sobre "music"
}

# Configurações de canais
CHANNEL_CONFIG: Dict[str, int] = {
    "shots": 0,  # Canal dedicado para tiros
    "warning": 1,  # Canal dedicado para warning
    "boss_laser": 2,  # Canal dedicado para carregamento do laser do boss
    "boss_laser_fire": 3,  # Canal dedicado para disparo do laser do boss
    "golem_mine": 4,  # Canal dedicado para tick da mina do Golem
    "golem_orb": 5,  # Canal dedicado para rajada do orbe roxo do Golem
    "metropolis_laser": 6,  # Canal dedicado para o loop do laser do Metropolis Overlord
    # Canal próprio para os cues da parada do tempo. Não é loop, mas é
    # SUSTENTADO e ligado a um estado: precisa ser cortável quando o efeito é
    # cancelado (troca de fase, game over) e os dois cues são mutuamente
    # exclusivos — "acelerando" deve cortar "desacelerando", que o canal
    # compartilhado dá de graça.
    "time_stop": 7,
    # Canais 0–7 são DEDICADOS (loops/sustentados). `reserved` informa ao mixer
    # quantos canais do início reservar — `Sound.play()` (one-shots) nunca os
    # auto-aloca, evitando que `stop_looping_sfx()` mate uma explosão recém-tocada.
    "reserved": 8,  # Reserva canais 0–7; one-shots usam só 8..max-1
    "max_channels": 17,  # 8 dedicados + 9 livres para one-shots simultâneos
}

# ─────────────────────────────────────────────────────────────────────────────
# Roots da descoberta de áudio (orientada por pasta, data-driven)
# ─────────────────────────────────────────────────────────────────────────────
# Uma árvore só — `game/assets/audio/`, com `music/` e `sfx/` lado a lado.
# Só ROOTS aqui: nenhum caminho de arquivo. Música indexa por SUBPASTA
# (tema = WorldTheme.value; boss = BOSS_TYPE_NAME) — ver `music_library.py`.
AUDIO_ROOT = "game/assets/audio"
AUDIO_MUSIC_ROOT = "game/assets/audio/music"
AUDIO_THEMES_ROOT = "game/assets/audio/music/themes"
AUDIO_BOSSES_ROOT = "game/assets/audio/music/bosses"
# Menu é contexto único (sem chave) → pasta PLANA, descoberta direta.
AUDIO_MENU_ROOT = "game/assets/audio/music/menu"

# SFX: a chave de cada som é o NOME DO ARQUIVO sem extensão, em qualquer
# subpasta de `sfx/`. `impacts/shield_activate.wav` registra "shield_activate".
# As subpastas (`ui/`, `weapons/`, `impacts/`, `powerups/`, `ambience/`,
# `bosses/<BOSS_TYPE_NAME>/`) são organização humana — o loader varre tudo, então
# mover um arquivo de categoria NÃO muda a chave nem exige tocar em código.
AUDIO_SFX_ROOT = "game/assets/audio/sfx"

# ─────────────────────────────────────────────────────────────────────────────
# Contrato de SFX — o que o CÓDIGO exige, não onde os arquivos estão
# ─────────────────────────────────────────────────────────────────────────────
# Antes existia aqui um dict com 40+ caminhos literais, e o `sfx_manager` repetia
# as mesmas chaves numa segunda lista (`ui_map`) só para carregá-las. Duas listas
# à mão, espelhadas: esquecer um lado dava no-op SILENCIOSO — foi assim que
# `button_click` ficou anos referenciado por 19 chamadas sem arquivo no disco.
#
# Agora o caminho é descoberto por varredura e o que fica declarado é só o
# CONTRATO: as chaves de que o código depende. `tests/test_audio_assets.py`
# confere contra o disco, então um som faltando falha no CI em vez de sumir.

# Famílias numeradas viram grupos de sorteio aleatório (`_sound_groups`).
# O `{}` casa qualquer inteiro: `shot_1..N` entram sem tocar em nada aqui.
SFX_FAMILIES: Dict[str, str] = {
    "shots": "shot_{}",
    "explosions": "explosion_asteroid_{}",
    "meteor_rain": "meteor_rain_{}",
}

# Tiros têm volume próprio (mais baixo — são disparados sem parar).
SFX_SHOT_PREFIX = "shot_"

# Chaves sem as quais um som que o jogador espera não sai. Ausência = falha no CI.
SFX_REQUIRED: FrozenSet[str] = frozenset({
    # UI
    "button_click", "button_hover", "warning",
    # Power-ups / aprimoramentos
    "powerup", "upgrade_activate",
    # Armas
    "orbital_discharge", "boss_laser_charging", "boss_laser_fire",
    # Impactos
    "explosion_alien", "explosion_boss", "explosion_ship", "boss_damage",
    "shield_activate", "shield_break", "gem_birth", "gem_death",
    # Ambiente
    "black_hole", "time_stop_in", "time_stop_out",
    # Bosses
    "hit_hurt_meteor_boss", "spike_boss_laser",
    "golem_mine_timer", "golem_orb_purple", "golem_eruption",
    "metropolis_overlord_laser",
    # Sentinelas orbitais do Metropolis Overlord (por papel):
    #   missile → descarga atmosférica: antecipação (carga) + raio caindo (impacto).
    #   emp     → zona de sobrecarga elétrica (ElectricPulse).
    #   laser   → grade holográfica energizada (GridSnare).
    #   neon    → trio de drones energéticos (EnergyDrone).
    "metropolis_lightning_charge", "metropolis_lightning_strike",
    "metropolis_energy_zone", "metropolis_electric_grid", "metropolis_triple_shot",
})

# Chaves OPCIONAIS: o código já tem fallback audível documentado para cada uma,
# então a ausência degrada o feedback sem quebrar nada. Ficam aqui para não
# serem confundidas com esquecimento — e para o teste não cobrar o arquivo.
SFX_OPTIONAL: Dict[str, str] = {
    "boss_warning": "aviso específico de boss; cai em `warning` (play_boss_warning)",
    "boss_frenzy": "frenesi do boss; cai em `boss_damage` (play_boss_frenzy)",
    "upgrade_denied": (
        "recusa de poder em cooldown; cai em `button_hover`, que é o placeholder "
        "de MVP — um blip de menu não lê como recusa no meio da luta. O arquivo "
        "que ocupava esta chave era `Usar_Depois.wav`, promovido a `button_click` "
        "(era o som de clique, mal arquivado). Falta gravar o som de recusa."
    ),
    "eye_enemy_laser": (
        "tiro do EyeEnemy; o arquivo existe em `sfx/weapons/` mas `eye_laser.py` "
        "ainda não toca som nenhum. Conteúdo pronto, feature não ligada."
    ),
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
