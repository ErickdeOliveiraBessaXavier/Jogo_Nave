"""Tipos centrais do pacote `levels` + dados handcrafted dos níveis fixos.

Módulo "dados puros": dataclasses (LevelConfig, LevelTheme), aliases de tipo
(EnemySpawnConfig), tabelas constantes (LEVEL_THEMES, FIXED_LEVELS). Não
importa nada de `procedural` ou `pipeline` — esses módulos importam daqui.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Type

from ...entities.alien import Alien
from ...entities.boss import Boss
from ...entities.bot_elemental import ElementalRobot
from ...entities.cloud_archmage_boss import CloudArchmageBoss
from ...entities.eye_enemy import EyeEnemy
from ...entities.giant_meteor_boss import GiantMeteorBoss
from ...entities.meteor import Meteor
from ...entities.mountain_mage import MountainMage
from ...entities.mountain_propeller import MountainPropeller
from ...entities.mountain_serpent_boss import MountainSerpentBoss
from ...entities.rock_glider import RockGlider
from ...entities.slime_boss import SlimeBoss
from ...entities.spike_boss import SpikeBoss
from ...entities.stone_golem_boss import StoneGolemBoss
from ...entities.stone_sentry import StoneSentry

# Mínimo de spawn em segundos. Replicado também em DifficultyConfig.MIN_SPAWN_TIME
# (procedural.py) — manter os dois em sincronia.
MIN_SPAWN_TIME: float = 0.5

# TypeAlias para mapas de spawn `Type[Inimigo] -> tempo_em_segundos`.
EnemySpawnConfig = dict[type, float]


# ============================================================================
# SISTEMA DE TEMAS DE NÍVEIS
# ============================================================================


@dataclass
class LevelTheme:
    """Define um 'tema' ou estilo de nível."""

    name: str
    description: str
    enemy_weight: dict[str, float]  # "meteor", "alien", "eye" -> peso relativo
    spawn_rate_multiplier: float  # Multiplica spawn rate (>1 = mais inimigos)
    enemies_multiplier: float  # Multiplica quantidade para limpar
    special_feature: str | None = None  # "mines_heavy", "formations_heavy", etc


LEVEL_THEMES: dict[str, LevelTheme] = {
    "asteroid_field": LevelTheme(
        name="Campo de Asteroides",
        description="Muitos meteoros, poucos aliens",
        enemy_weight={
            "meteor": 3.0,
            "alien": 0.5,
            "eye": 0.3,
            "square_minion_boss": 0.1,
            "elemental_robot": 0.2,
        },
        spawn_rate_multiplier=1.3,
        enemies_multiplier=1.2,
        special_feature=None,
    ),
    "alien_invasion": LevelTheme(
        name="Invasão Alienígena",
        description="Predominância de aliens",
        enemy_weight={
            "meteor": 0.5,
            "alien": 3.0,
            "eye": 1.0,
            "square_minion_boss": 0.2,
            "elemental_robot": 0.1,
        },
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature=None,
    ),
    "eye_swarm": LevelTheme(
        name="Enxame de Olhos",
        description="Muitos Eye Enemies",
        enemy_weight={
            "meteor": 0.3,
            "alien": 0.5,
            "eye": 3.0,
            "square_minion_boss": 0.1,
            "elemental_robot": 0.1,
        },
        spawn_rate_multiplier=0.8,
        enemies_multiplier=0.9,
        special_feature=None,
    ),
    "minefield": LevelTheme(
        name="Campo Minado",
        description="Muitas minas explosivas",
        enemy_weight={
            "meteor": 1.0,
            "alien": 1.0,
            "eye": 0.5,
            "square_minion_boss": 0.1,
            "elemental_robot": 0.1,
        },
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature="mines_heavy",
    ),
    "formation_hell": LevelTheme(
        name="Inferno de Formações",
        description="Formações complexas constantemente",
        enemy_weight={
            "meteor": 0.8,
            "alien": 2.0,
            "eye": 1.0,
            "square_minion_boss": 0.2,
            "elemental_robot": 0.1,
        },
        spawn_rate_multiplier=0.9,
        enemies_multiplier=0.85,
        special_feature="formations_heavy",
    ),
    "meteor_storm": LevelTheme(
        name="Tempestade de Meteoros",
        description="Apenas meteoros em volume extremo",
        enemy_weight={
            "meteor": 10.0,
            "alien": 0.0,
            "eye": 0.0,
            "square_minion_boss": 0.0,
            "elemental_robot": 0.0,
        },
        spawn_rate_multiplier=1.4,
        enemies_multiplier=1.3,
        special_feature="meteor_only",
    ),
    "rock_glider_storm": LevelTheme(
        name="Tempestade de Rock Gliders",
        description="Enxame de Rock Gliders pequenos em volume extremo",
        enemy_weight={
            "meteor": 0.0,
            "alien": 0.0,
            "eye": 0.0,
            "square_minion_boss": 0.0,
            "elemental_robot": 0.0,
        },
        spawn_rate_multiplier=1.35,
        enemies_multiplier=1.35,
        special_feature="rock_glider_only",
    ),
    "balanced": LevelTheme(
        name="Balanceado",
        description="Mix equilibrado de tudo",
        enemy_weight={
            "meteor": 1.0,
            "alien": 1.0,
            "eye": 1.0,
            "square_minion_boss": 0.1,
            "elemental_robot": 0.15,
        },
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature=None,
    ),
}


# ============================================================================
# DATACLASS - LEVEL CONFIG
# ============================================================================


@dataclass(eq=False)
class LevelConfig:
    """Configuração de um nível do jogo.

    Dataclass para que ``dataclasses.replace`` funcione — usado no ajuste
    dinâmico de dificuldade (`meta_progression`) e no saneamento de formations
    (`spawner`). ``eq=False`` preserva igualdade/hash por identidade.
    """

    level_number: int
    enemy_spawn_config: dict[type, float]
    enemies_to_clear: int
    boss_type: (
        Type[
            Boss
            | SpikeBoss
            | SlimeBoss
            | GiantMeteorBoss
            | StoneGolemBoss
            | MountainSerpentBoss
            | CloudArchmageBoss
        ]
        | None
    ) = None
    mines_enabled: bool = False
    formations_enabled: bool = False
    formation_types: list[str] | None = None
    theme_name: str | None = None
    score_multiplier: float = 1.0
    storm_kind: str | None = None

    @property
    def is_storm(self) -> bool:
        return self.storm_kind is not None

    @property
    def is_rock_glider_storm(self) -> bool:
        return self.storm_kind == "rock_glider"

    @property
    def enemy_types(self) -> list[type]:
        """Retorna lista de tipos de inimigos configurados."""
        return list(self.enemy_spawn_config.keys())

    def get_spawn_time(self, enemy_type: type) -> float:
        """Retorna o tempo de spawn para um tipo específico de inimigo."""
        return self.enemy_spawn_config.get(enemy_type, 1.0)

    def get_random_enemy_type(self) -> type:
        """Retorna um tipo de inimigo aleatório ponderado pelo spawn_time configurado."""
        if not self.enemy_types:
            raise ValueError(f"Level {self.level_number} has no enemies configured!")
        weights_map = self.get_enemy_spawn_weights()
        types = list(weights_map.keys())
        weights = [weights_map[t] for t in types]
        result: list[type] = random.choices(types, weights=weights, k=1)
        return result[0]

    def get_enemy_spawn_weights(self) -> dict[type, float]:
        """Retorna pesos base de spawn derivados do intervalo configurado.

        Spawn menor significa maior frequência. Convertemos isso em peso por
        inversão de tempo para suportar seleção ponderada dinâmica.
        """
        weights: dict[type, float] = {}
        for enemy_type, spawn_time in self.enemy_spawn_config.items():
            safe_spawn_time = max(MIN_SPAWN_TIME, spawn_time)
            weights[enemy_type] = 1.0 / safe_spawn_time
        return weights

    def get_random_formation_type(self) -> str | None:
        """Retorna um tipo de formação aleatório da lista."""
        if self.formation_types:
            return random.choice(self.formation_types)
        return None

    def validate_sanity(self) -> list[str]:
        """Valida se a configuração do nível é jogável e faz sentido.

        Returns:
            Lista de avisos/problemas encontrados (vazia se tudo OK)
        """
        warnings: list[str] = []

        for enemy_type, spawn_time in self.enemy_spawn_config.items():
            if spawn_time < MIN_SPAWN_TIME:
                warnings.append(
                    f"Spawn time de {enemy_type.__name__} muito rápido: {spawn_time:.2f}s "
                    f"(mínimo recomendado: {MIN_SPAWN_TIME}s)"
                )

        if self.enemies_to_clear > 1000:
            warnings.append(
                f"Muitos inimigos para limpar: {self.enemies_to_clear} "
                f"(pode levar mais de 10 minutos)"
            )

        if self.score_multiplier > 3.0:
            warnings.append(
                f"Score multiplier muito alto: {self.score_multiplier:.1f}x"
            )

        return warnings

    def validate_formation_types(self, valid_types: set[str]) -> list[str]:
        """Valida os tipos de formação configurados."""
        if not self.formation_types:
            return []
        return [t for t in self.formation_types if t not in valid_types]


# ============================================================================
# NÍVEIS FIXOS (HANDCRAFTED)
# ============================================================================


FIXED_LEVELS: dict[int, LevelConfig] = {
    # Nível 1: LEVEL DE DEBUG — todos os inimigos e todos os bosses.
    # Fixed levels pulam o filtro de tema (allowlist) do pipeline, então qualquer
    # inimigo listado aqui spawna direto (mesmo sendo MOUNTAINS/side-scroll). Os
    # caps por tipo (SPAWNER_CAP_*) controlam a quantidade simultânea de cada um.
    # Comente/descomente livremente para isolar o que quer testar.
    #
    # BOSS: só UM boss_type pode estar ativo por vez — descomente um da lista.
    # Para chegar ao boss rápido, baixe `enemies_to_clear` (ex.: 10).
    1: LevelConfig(
        level_number=1,
        enemy_spawn_config={
            # ── Comuns / enxame ──────────────────────────────────────────────
            # RockGlider: 1.2,
            # Meteor: 1.6,
            # CityDrone: 4.0,          # nasce em leva (cluster) de 5-8
            # Alien: 3.0,
            # ── Mundo 1 (MOUNTAINS) ──────────────────────────────────────────
            # MountainPropeller: 5.0,
            # MountainMage: 10.0,
            # ElementalRobot: 10.0,
            # StoneSentry: 20.0,
            # ── STARFIELD / espaço ───────────────────────────────────────────
            # EyeEnemy: 6.0,
            # Satellite: 6.0,
            # SquareMinionBoss: 12.0,
            # ── CITY (linhagem original) ─────────────────────────────────────
            # NeonSniper: 8.0,
            # PoliceInterceptor: 8.0,  # spawna em duplas
            # CyberCaptor: 10.0,
            # TeslaTwin: 12.0,         # spawna o par
            # CyberTank: 14.0,
            # ── CITY (variantes novas) ───────────────────────────────────────
            # JammerNode: 10.0,
            # MortarDrone: 8.0,
            # SapperDrone: 8.0,
            # RiotVan: 14.0,
            # SplitterTank: 16.0,
            # MirrorPylon: 14.0,
        },
        enemies_to_clear=75,
        # ── Descomente UM boss por vez ───────────────────────────────────────
        # boss_type=Boss,
        # boss_type=SpikeBoss,
        # boss_type=SlimeBoss,
        # boss_type=GiantMeteorBoss,
        # boss_type=StoneGolemBoss,
        # boss_type=MountainSerpentBoss,
        # boss_type=CloudArchmageBoss,
        mines_enabled=True,  # também spawna minas (tema CITY → mina temática)
        formations_enabled=True,  # formações (só disparam em temas que as suportam)
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        score_multiplier=1.0,
    ),
    # Nível 3: Primeiro Boss - Mountain Serpent (Montanhas)
    3: LevelConfig(
        level_number=3,
        enemy_spawn_config={
            RockGlider: 0.7,
            ElementalRobot: 12.0,
            StoneSentry: 18.0,
        },
        enemies_to_clear=250,
        boss_type=MountainSerpentBoss,
        mines_enabled=True,
        theme_name="Boss da Serpente de Pedra",
        score_multiplier=1.2,
    ),
    # Nível 6: Segundo Boss - Cloud Archmage
    6: LevelConfig(
        level_number=6,
        enemy_spawn_config={
            RockGlider: 0.6,
            MountainPropeller: 4.0,
            MountainMage: 10.0,
        },
        enemies_to_clear=300,
        boss_type=CloudArchmageBoss,
        mines_enabled=True,
        theme_name="O Arquimago das Nuvens",
        score_multiplier=1.3,
    ),
    # Nível 10: Terceiro Boss - Stone Golem (Final do Mundo 1)
    10: LevelConfig(
        level_number=10,
        enemy_spawn_config={
            RockGlider: 0.5,
            MountainMage: 12.0,
            MountainPropeller: 10.0,
        },
        enemies_to_clear=350,
        boss_type=StoneGolemBoss,
        mines_enabled=True,
        theme_name="Chefe do Golem de Pedra",
        score_multiplier=1.5,
    ),
    # Nível 11 (2-1): Apresentação do mundo — só meteoros em ritmo controlado.
    11: LevelConfig(
        level_number=11,
        enemy_spawn_config={
            Meteor: 1.8,
        },
        enemies_to_clear=80,
        boss_type=None,
        mines_enabled=False,
        formations_enabled=False,
        theme_name="Aprendendo o Vazio",
        score_multiplier=1.0,
    ),
    # Nível 12: Boss clássico
    12: LevelConfig(
        level_number=12,
        enemy_spawn_config={
            Meteor: 1.1,
            Alien: 4.5,
        },
        enemies_to_clear=280,
        boss_type=Boss,
        mines_enabled=False,
        formations_enabled=False,
        theme_name="Chefe Clássico do Espaço",
        score_multiplier=1.3,
    ),
    # Nível 16: Spike Boss
    16: LevelConfig(
        level_number=16,
        enemy_spawn_config={
            Meteor: 0.9,
            Alien: 2.8,
            EyeEnemy: 5.5,
        },
        enemies_to_clear=340,
        boss_type=SpikeBoss,
        mines_enabled=False,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v"],
        theme_name="Criatura Alienígena com Espinhos",
        score_multiplier=1.4,
    ),
    # Nível 20: Giant Meteor Boss
    20: LevelConfig(
        level_number=20,
        enemy_spawn_config={
            Meteor: 0.7,
            Alien: 4.0,
        },
        enemies_to_clear=320,
        boss_type=GiantMeteorBoss,
        mines_enabled=False,
        formations_enabled=False,
        theme_name="Meteorito Gigante",
        score_multiplier=1.5,
    ),
    # Nível 25: Slime Boss
    25: LevelConfig(
        level_number=25,
        enemy_spawn_config={
            Meteor: 0.8,
            Alien: 3.2,
            EyeEnemy: 6.0,
        },
        enemies_to_clear=380,
        boss_type=SlimeBoss,
        mines_enabled=False,
        formations_enabled=True,
        formation_types=[
            "spiral_circle",
            "spiral_v",
            "spiral_square",
        ],
        theme_name="Criatura Gelatinosa Alienígena",
        score_multiplier=1.6,
    ),
}
