"""
Sistema de Mundos com Progressão Procedural

Organiza o jogo em 4 mundos temáticos + procedural infinito.
Cada mundo tem um tema visual, modificadores de spawn, e um boss específico.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Set, Tuple, Type

logger = logging.getLogger(__name__)


class WorldTheme(Enum):
    """Temas visuais dos mundos."""

    MOUNTAINS = "mountains"
    STARFIELD = "starfield"
    CITY = "city"
    VOLCANIC = "volcanic"
    PROCEDURAL = "procedural"


@dataclass
class WorldConfig:
    """Configuração de um mundo."""

    world_id: int
    name: str
    description: str
    theme: WorldTheme

    # Visual
    primary_color: Tuple[int, int, int]
    secondary_color: Tuple[int, int, int]

    # Gameplay
    start_level: int  # Nível inicial (ex: 1, 11, 21)
    end_level: int  # Nível final (ex: 10, 20, 30)
    boss_level: int  # Nível do boss (sempre end_level)

    # Boss específico (None = procedural)
    boss_type: Optional[Type[Any]] = None

    # Modificadores de tema (aplicados à geração procedural)
    theme_modifiers: dict[str, float] = field(default_factory=lambda: {})

    @property
    def total_stages(self) -> int:
        """Total de estágios no mundo."""
        return self.end_level - self.start_level + 1

    def get_stage_number(self, level_number: int) -> int:
        """Converte nível absoluto para número do estágio (1-10)."""
        return level_number - self.start_level + 1

    def contains_level(self, level_number: int) -> bool:
        """Verifica se o nível pertence a este mundo."""
        return self.start_level <= level_number <= self.end_level


# ============================================================================
# DEFINIÇÃO DOS MUNDOS
# ============================================================================


def _get_worlds() -> dict[int, WorldConfig]:
    """Retorna dicionário de mundos configurados."""
    # Importações locais para evitar circular imports
    from ..entities.cloud_archmage_boss import CloudArchmageBoss
    from ..entities.giant_meteor_boss import GiantMeteorBoss
    from ..entities.slime_boss import SlimeBoss

    return {
        1: WorldConfig(
            world_id=1,
            name="Cordilheira Celestial",
            description="Montanhas rochosas flutuantes nas nuvens",
            theme=WorldTheme.MOUNTAINS,
            primary_color=(139, 90, 60),  # Marrom rochoso
            secondary_color=(200, 200, 220),  # Névoa clara
            start_level=1,
            end_level=10,
            boss_level=10,
            boss_type=CloudArchmageBoss,  # Boss das montanhas
            theme_modifiers={
                "alien_weight": 0.5,  # Menos aliens
                "formation_chance": 0.5,  # Formações muito raras no começo
            },
        ),
        2: WorldConfig(
            world_id=2,
            name="Vazio Sideral",
            description="A vastidão infinita do espaço profundo",
            theme=WorldTheme.STARFIELD,
            primary_color=(30, 30, 80),  # Azul espacial
            secondary_color=(100, 100, 150),  # Nebulosa
            start_level=11,
            end_level=25,
            boss_level=25,
            boss_type=None,  # Bosses determinados por FIXED_LEVELS
            theme_modifiers={
                "meteor_weight": 1.0,
                "alien_weight": 1.15,  # Reduzido de 1.5 para suavizar entrada no mundo
                "formation_chance": 0.8,  # Reduzido de 1.1
            },
        ),
        3: WorldConfig(
            world_id=3,
            name="Metrópole Neon",
            description="Cidade cyberpunk com arranha-céus brilhantes",
            theme=WorldTheme.CITY,
            primary_color=(150, 50, 200),  # Roxo neon
            secondary_color=(0, 255, 255),  # Cyan elétrico
            start_level=26,
            end_level=35,
            boss_level=35,
            boss_type=GiantMeteorBoss,
            theme_modifiers={
                "eye_weight": 1.5,  # Mais olhos (câmeras de segurança)
                "mines_chance": 1.3,  # Mais minas (armadilhas urbanas)
            },
        ),
        4: WorldConfig(
            world_id=4,
            name="Núcleo Vulcânico",
            description="Mundo de lava e fragmentos ígneos",
            theme=WorldTheme.VOLCANIC,
            primary_color=(255, 80, 0),  # Laranja lava
            secondary_color=(200, 0, 0),  # Vermelho incandescente
            start_level=36,
            end_level=45,
            boss_level=45,
            boss_type=SlimeBoss,  # Slime de lava
            theme_modifiers={
                "meteor_weight": 1.8,  # Muitos fragmentos vulcânicos
                "spawn_rate_multiplier": 1.15,  # Mais caótico
            },
        ),
    }


WORLDS = _get_worlds()


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================


def get_world_for_level(level_number: int) -> WorldConfig:
    """
    Retorna o mundo correspondente a um nível.

    Níveis 1-10: Mundo 1 (MOUNTAINS)
    Níveis 11-25: Mundo 2 (STARFIELD)
    Níveis 26-35: Mundo 3 (CITY)
    Níveis 36-45: Mundo 4 (VOLCANIC)
    Níveis 46+: Rotação de temas procedurais (MOUNTAINS -> STARFIELD -> CITY -> VOLCANIC -> ...)
    """
    for world in WORLDS.values():
        if world.contains_level(level_number):
            return world

    # Níveis 46+: Rotação de temas procedurais
    # Cada 10 níveis = um novo "setor" com tema rotacionado
    offset = level_number - 46
    sector_idx = offset // 10
    sector_id = sector_idx + 5
    sector_start = 46 + sector_idx * 10
    sector_end = sector_start + 9

    # Rotacionar entre os 4 temas principais
    theme_cycle = [
        WorldTheme.MOUNTAINS,
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
    ]
    theme_index = sector_idx % 4  # Começa no setor 5 (nível 46+)
    theme = theme_cycle[theme_index]

    # Usar colors e modifiers do mundo correspondente ao tema
    world_template = WORLDS[theme_index + 1]  # Worlds 1-4

    return WorldConfig(
        world_id=sector_id,
        name=f"Setor {sector_id} - {world_template.name}",
        description=f"{world_template.description} (Procedimental)",
        theme=theme,
        primary_color=world_template.primary_color,
        secondary_color=world_template.secondary_color,
        start_level=sector_start,
        end_level=sector_end,
        boss_level=sector_end,
        boss_type=None,  # Rotação procedural de bosses
        theme_modifiers=world_template.theme_modifiers.copy(),
    )


def get_world_for_level_by_id(world_id: int) -> Optional[WorldConfig]:
    """
    Retorna a configuração de mundo para um world_id específico.

    Args:
        world_id: ID do mundo (1-4 fixos, 5+ procedurais)

    Returns:
        WorldConfig ou None se não encontrado
    """
    if world_id in WORLDS:
        return WORLDS[world_id]

    # IDs 5+ representam setores procedurais de 10 níveis.
    if world_id >= 5:
        level_number = 46 + (world_id - 5) * 10
        return get_world_for_level(level_number)

    return None


def get_stage_identifier(level_number: int) -> Tuple[int, int]:
    """
    Retorna (world_id, stage_number) para um nível.

    Exemplo: level 15 -> (2, 5)
    """
    world = get_world_for_level(level_number)
    stage = world.get_stage_number(level_number)
    return (world.world_id, stage)


def format_stage_name(level_number: int) -> str:
    """
    Formata nome do estágio no formato "MUNDO-ESTÁGIO".

    Exemplos:
    - level 1 -> "1-1"
    - level 10 -> "1-10"
    - level 15 -> "2-5"
    - level 45 -> "4-10"
    - level 46 -> "5-1"
    """
    world_id, stage = get_stage_identifier(level_number)
    return f"{world_id}-{stage}"


# ============================================================================
# SISTEMA DE MODO DE JOGO (Top-Down vs Side-Scroll)
# ============================================================================


def is_top_down_mode(theme: WorldTheme) -> bool:
    """
    Retorna True se o tema usa modo TOP-DOWN (vertical).
    Retorna False se usa modo SIDE-SCROLL (horizontal).

    TOP-DOWN: STARFIELD
    SIDE-SCROLL: MOUNTAINS, CITY, VOLCANIC, PROCEDURAL
    """
    return theme == WorldTheme.STARFIELD


def is_side_scroll_mode(theme: WorldTheme) -> bool:
    """Retorna True se o tema usa modo SIDE-SCROLL (horizontal)."""
    return not is_top_down_mode(theme)


# ============================================================================
# FUNÇÕES DE DEBUG
# ============================================================================


def get_all_worlds() -> list[WorldConfig]:
    """Retorna lista de todos os mundos configurados (4 primeiros)."""
    return sorted(WORLDS.values(), key=lambda w: w.world_id)


def print_world_summary() -> None:
    """Imprime resumo de todos os mundos."""
    logger.info("=" * 70)
    logger.info("RESUMO DE MUNDOS")
    logger.info("=" * 70)

    for world in get_all_worlds():
        logger.info("\n🌍 Mundo %s: %s", world.world_id, world.name)
        logger.info("   Descrição: %s", world.description)
        logger.info(
            "   Níveis: %s-%s (Total: %s)",
            world.start_level,
            world.end_level,
            world.total_stages,
        )
        logger.info(
            "   Boss: %s", world.boss_type.__name__ if world.boss_type else "Procedural"
        )
        logger.info("   Tema: %s", world.theme.value)
        logger.info(
            "   Cores: RGB%s / RGB%s", world.primary_color, world.secondary_color
        )

        if world.theme_modifiers:
            logger.info("   Modificadores: %s", world.theme_modifiers)

    logger.info("\n%s", "=" * 70)
    logger.info("Níveis 46+: Mundos procedurais infinitos")
    logger.info("=" * 70)


# ============================================================================
# TESTES E VALIDAÇÃO
# ============================================================================


def validate_worlds() -> bool:
    """Valida a configuração dos mundos."""
    errors: list[str] = []

    # Verificar sobreposição de níveis
    used_levels: Set[int] = set()
    for world in get_all_worlds():
        for level in range(world.start_level, world.end_level + 1):
            if level in used_levels:
                errors.append(f"Nível {level} é compartilhado por múltiplos mundos")
            used_levels.add(level)

    # Verificar que cada mundo tem um boss_level dentro de seu range
    for world in get_all_worlds():
        if not world.start_level <= world.boss_level <= world.end_level:
            errors.append(f"Mundo {world.world_id}: boss_level fora do range")

    # Verificar que mundos 1-4 são contíguos
    for i in range(1, 4):
        w1 = WORLDS[i]
        w2 = WORLDS[i + 1]
        if w1.end_level + 1 != w2.start_level:
            errors.append(f"Mundos {i} e {i + 1} não são contíguos")

    if errors:
        logger.error("Erros na validação de mundos:")
        for error in errors:
            logger.error("  - %s", error)
        return False

    logger.info("✓ Configuração de mundos validada com sucesso")
    return True


if __name__ == "__main__":
    # Debug: imprimir resumo
    print_world_summary()
    validate_worlds()
