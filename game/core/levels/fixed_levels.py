"""Tipos centrais do pacote `levels` + dados handcrafted dos níveis fixos.

Módulo "dados puros": dataclasses (LevelConfig, LevelTheme), aliases de tipo
(EnemySpawnConfig), tabelas constantes (LEVEL_THEMES, FIXED_LEVELS). Não
importa nada de `procedural` ou `pipeline` — esses módulos importam daqui.

Responsabilidade de `FIXED_LEVELS` (fonte única do que define): o LAYOUT
handcrafted (inimigos/quantidade/score/nome/formações) de níveis específicos —
intros (L1, L11) e ARENAS de boss. NÃO define a CLASSE do boss: essa vem do
`WORLD_BOSS_ROADMAP` (`world_config.py`) via `get_boss_for_level`, injetada pelo
pipeline. Trocar um boss = editar o roadmap, nunca aqui.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Type

from ...entities.alien import Alien
from ...entities.bot_elemental import ElementalRobot
from ...entities.cutting_storm import CuttingStorm  # noqa: F401  (arena de teste)
from ...entities.eye_enemy import EyeEnemy
from ...entities.giant_meteor_boss import GiantMeteorBoss
from ...entities.ice_golem import IceGolem  # noqa: F401  (arena de teste)
from ...entities.Inimigos_Tema_Cidade.cargo_carrier import CargoCarrier  # noqa: F401

# Linhagem CITY — todos com `# noqa: F401` porque são usados apenas no level de
# debug (nível 1) e podem estar comentados lá; o noqa impede o autofix do ruff de
# removê-los, mantendo-os disponíveis para ligar/desligar à vontade.
from ...entities.Inimigos_Tema_Cidade.city_drone import CityDrone  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.cyber_captor import CyberCaptor  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.cyber_tank import CyberTank  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.jammer_node import JammerNode  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.metropolis_overlord_boss import (
    MetropolisOverlordBoss,
)
from ...entities.Inimigos_Tema_Cidade.mirror_pylon import MirrorPylon  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.mortar_drone import MortarDrone  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.neon_sniper import NeonSniper  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.police_interceptor import (  # noqa: F401
    PoliceInterceptor,
)
from ...entities.Inimigos_Tema_Cidade.sapper_drone import SapperDrone  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.splitter_tank import SplitterTank  # noqa: F401
from ...entities.Inimigos_Tema_Cidade.tesla_twin import TeslaTwin  # noqa: F401
from ...entities.meteor import Meteor
from ...entities.mountain_mage import MountainMage
from ...entities.mountain_propeller import MountainPropeller
from ...entities.orbital_turret import OrbitalTurret  # noqa: F401  (arena de teste)
from ...entities.repair_drone import RepairDrone  # noqa: F401  (arena de teste)
from ...entities.rock_glider import RockGlider
from ...entities.satellite import Satellite  # noqa: F401  (só no level de debug)
from ...entities.slime_boss import SlimeBoss
from ...entities.square_minion_boss import SquareMinionBoss  # noqa: F401  (debug)
from ...entities.stealth_fighter import StealthFighter  # noqa: F401  (arena de teste)
from ...entities.stone_eagle import StoneEagle  # noqa: F401  (arena de teste)
from ...entities.stone_golem_boss import StoneGolemBoss
from ...entities.stone_sentry import StoneSentry
from ..world_config import WorldTheme

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
    # A CLASSE do boss vem do WORLD_BOSS_ROADMAP (injetada pelo pipeline), não
    # daqui — então `Type[Any]` é honesto: a checagem real está no BossSlot do
    # roadmap e no runtime do spawner. Uma union manual só daria falsa segurança
    # estática e exigiria editar a cada boss novo.
    boss_type: Type[Any] | None = None
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
# NÍVEIS FIXOS (HANDCRAFTED) — só LAYOUT; a classe do boss vem do roadmap
# ============================================================================


FIXED_LEVELS: dict[int, LevelConfig] = {
    1: LevelConfig(
        level_number=1,
        enemy_spawn_config={
            RockGlider: 1.2,
        },
        enemies_to_clear=75,
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
    # ── LAYOUTS DOS MID-BOSSES DA CIDADE ─────────────────────────────────────
    # Estas entradas definem só o LAYOUT handcrafted (adds/score/nome) das fases de
    # boss intermediárias da Cidade. A CLASSE do chefe vem do WORLD_BOSS_ROADMAP
    # (world_config.py) via get_boss_for_level e é injetada pelo pipeline — fonte
    # única. Trocar o boss = editar o roadmap, não aqui. Adds da própria linhagem
    # CITY (passam pelo allowlist de tema sem fallback).
    # Nível 30 (estágio 5): City Boss 1
    30: LevelConfig(
        level_number=30,
        enemy_spawn_config={
            CityDrone: 1.0,
            NeonSniper: 8.0,
            PoliceInterceptor: 9.0,
        },
        enemies_to_clear=280,
        mines_enabled=False,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v"],
        theme_name="Sentinela Neon",
        score_multiplier=1.5,
    ),
    # Nível 34 (estágio 9): City Boss 2
    34: LevelConfig(
        level_number=34,
        enemy_spawn_config={
            CityDrone: 1.0,
            CyberTank: 10.0,
            MortarDrone: 9.0,
        },
        enemies_to_clear=300,
        mines_enabled=False,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="Colosso Cibernético",
        score_multiplier=1.55,
    ),
    # Nível 37 (estágio 12): City Boss 3
    37: LevelConfig(
        level_number=37,
        enemy_spawn_config={
            CityDrone: 0.9,
            SplitterTank: 10.0,
            TeslaTwin: 11.0,
        },
        enemies_to_clear=320,
        mines_enabled=False,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="Reator Instável",
        score_multiplier=1.6,
    ),
}


# ============================================================================
# ARENA DE TESTE POR TEMA (DEV) — valida inimigos de um tema isoladamente
# ============================================================================
#
# Objetivo: jogar diretamente um tema específico, com TODOS os inimigos daquele
# tema, sem percorrer a campanha e sem interferência de inimigos de outros
# mundos. Diferente dos fixed levels normais, estas arenas NÃO passam pelo
# variety cap nem pelo fallback de tema (ver `_build_test_arena_config` em
# pipeline.py) — todos os tipos listados aparecem, na cadência configurada aqui.
#
# COMO USAR:
#   1. Ligue o flag abaixo: `TEST_ARENA_ENABLED = True`.
#   2. Rode o jogo, vá em "Selecionar Mundo" (todos destravados no modo teste) e
#      escolha o mundo do tema que quer validar.
#   3. Edite a lista do tema correspondente para ligar/desligar inimigos e
#      ajustar cadência (spawn_time menor = mais frequente).
#   4. Desligue o flag (`False`) antes de commitar/jogar a campanha — com ele
#      OFF a campanha é 100% normal (nada aqui afeta os fixed levels acima).
#
# NOTA DE DESIGN: MOUNTAINS, CITY e STARFIELD têm inimigos EXCLUSIVOS (Montanha e
# Espaço ganharam 3 cada — tank/area_denial/rush e sniper/rush/support). Só
# VOLCANIC ainda reusa o trio genérico (Meteor/Alien/EyeEnemy/SquareMinionBoss) —
# a arena deixa essa lacuna explícita: sem preenchimento com inimigos de outros
# temas, mostra só o que o tema realmente tem hoje.

TEST_ARENA_ENABLED: bool = False

THEME_TEST_LEVELS: dict[WorldTheme, LevelConfig] = {
    # ── MONTANHAS — linhagem própria completa ────────────────────────────────
    WorldTheme.MOUNTAINS: LevelConfig(
        level_number=1,  # sobrescrito pelo nível real em _build_test_arena_config
        enemy_spawn_config={
            # RockGlider: 1.2,
            # MountainPropeller: 4.0,
            # MountainMage: 8.0,
            # ElementalRobot: 8.0,
            # StoneSentry: 10.0,
            StoneEagle: 6.0,
            CuttingStorm: 8.0,
            IceGolem: 10.0,
        },
        enemies_to_clear=40,
        boss_type=StoneGolemBoss,
        mines_enabled=True,  # spawna o MountainGeode (mina temática) por lógica própria
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="[TESTE] Arena Montanhas",
        score_multiplier=1.0,
    ),
    # ── CIDADE — linhagem Inimigos_Tema_Cidade completa ──────────────────────
    WorldTheme.CITY: LevelConfig(
        level_number=26,
        enemy_spawn_config={
            CityDrone: 3.0,
            # NeonSniper: 8.0,
            # PoliceInterceptor: 8.0,
            # CyberCaptor: 10.0,
            # TeslaTwin: 12.0,
            # CyberTank: 4.0,
            # JammerNode: 1.0,
            # MortarDrone: 1.0,
            # CargoCarrier: 2.0,
            # SplitterTank: 2.0,
            # SapperDrone: 5.0,
            # MirrorPylon: 2.0,
        },
        enemies_to_clear=1,
        boss_type=MetropolisOverlordBoss,  # boss nativo da Cidade (em teste)
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="[TESTE] Arena Cidade",
        score_multiplier=1.0,
    ),
    # ── ESPAÇO — trio genérico + satélite + linhagem própria do bioma ────────
    WorldTheme.STARFIELD: LevelConfig(
        level_number=11,
        enemy_spawn_config={
            # Meteor: 1.2,
            # Alien: 3.0,
            # EyeEnemy: 6.0,
            # Satellite: 6.0,
            # StealthFighter: 6.0,  # rush (cloak + investida)
            # OrbitalTurret: 8.0,  # sniper (rajada de plasma)
            # RepairDrone: 10.0,  # suporte
            # SquareMinionBoss: 12.0,
        },
        enemies_to_clear=40,
        boss_type=GiantMeteorBoss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="[TESTE] Arena Espaço",
        score_multiplier=1.0,
    ),
    # ── VULCÃO — sem inimigos exclusivos hoje (trio genérico) ────────────────
    WorldTheme.VOLCANIC: LevelConfig(
        level_number=36,
        enemy_spawn_config={
            Meteor: 1.2,
            Alien: 3.0,
            EyeEnemy: 6.0,
            SquareMinionBoss: 12.0,
        },
        enemies_to_clear=40,
        boss_type=SlimeBoss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="[TESTE] Arena Vulcão",
        score_multiplier=1.0,
    ),
}
