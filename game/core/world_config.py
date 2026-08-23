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
    boss_level: int  # Nível FINAL do mundo (transição de mundo). NÃO define a
    # classe do boss — isso vem do WORLD_BOSS_ROADMAP via get_boss_for_level.

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


# Ordem de expansão dos mundos procedurais em temas concretos (ciclo).
_PROCEDURAL_THEME_CYCLE = ("mountains", "city", "volcanic")


def resolve_theme_key(world: "WorldConfig") -> str:
    """Chave de tema concreta de um mundo (== nome da pasta em `audio/music/themes/`).

    Expande `procedural` para um tema real ciclando por `world_id`. Fonte única
    usada tanto pela seleção de mundo (visual) quanto pela música ambiente, para
    que pasta e bioma fiquem sempre alinhados.
    """
    theme_str = world.theme.value.lower()
    if theme_str == "procedural":
        idx = int((world.world_id - 5) % len(_PROCEDURAL_THEME_CYCLE))
        return _PROCEDURAL_THEME_CYCLE[idx]
    return theme_str


# ============================================================================
# DEFINIÇÃO DOS MUNDOS
# ============================================================================


def _get_worlds() -> dict[int, WorldConfig]:
    """Retorna dicionário de mundos configurados.

    A CLASSE do boss de cada mundo NÃO mora aqui — vem do WORLD_BOSS_ROADMAP via
    get_boss_for_level. `boss_level` aqui é só o nível FINAL do mundo.
    """
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
            theme_modifiers={
                "meteor_weight": 0.9,
                "alien_weight": 0.75,  # Menos aliens durante a curva inteira
                "spawn_rate_multiplier": 1.0,  # Ritmo padrão entre fases
                "formation_chance": 0.45,  # Formações menos frequentes no mundo 2
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
            end_level=40,  # 15 estágios para acomodar os 3 bosses da Cidade (ver WORLD_BOSS_ROADMAP)
            boss_level=40,  # nível FINAL. Bosses (mid+final) no WORLD_BOSS_ROADMAP.
            # CITY usa a própria linhagem (enemies/city); o tuning de spawn/
            # frequência mora em pipeline.py/procedural.py (_configure_city_spawn,
            # ENEMY_*_WEIGHT_PROFILES). Não há theme_modifiers funcionais aqui:
            # "eye_weight" era no-op (EyeEnemy é banido do tema pelo allowlist) e
            # "mines_chance" não é lido por ninguém — removidos para não confundir.
            theme_modifiers={},
        ),
        4: WorldConfig(
            world_id=4,
            name="Núcleo Vulcânico",
            description="Mundo de lava e fragmentos ígneos",
            theme=WorldTheme.VOLCANIC,
            primary_color=(255, 80, 0),  # Laranja lava
            secondary_color=(200, 0, 0),  # Vermelho incandescente
            start_level=41,  # deslocado: Cidade agora vai até 40
            end_level=50,
            boss_level=50,
            theme_modifiers={
                "meteor_weight": 1.8,  # Muitos fragmentos vulcânicos
                "spawn_rate_multiplier": 1.15,  # Mais caótico
            },
        ),
    }


WORLDS = _get_worlds()

# Os mundos nomeados são contíguos; a rotação procedural infinita começa logo após
# o último. Derivado (não hardcoded) para sobreviver a mudanças de fronteira como a
# expansão da Cidade para 15 estágios. SECTOR_SIZE = nº de níveis por setor proc.
NAMED_WORLDS_COUNT: int = len(WORLDS)
PROCEDURAL_START_LEVEL: int = max(w.end_level for w in WORLDS.values()) + 1
PROCEDURAL_SECTOR_SIZE: int = 10


@dataclass(frozen=True)
class BossSlot:
    """Slot de boss num mundo — FONTE DE VERDADE da classe e posição do chefe.

    `boss_type` é a classe que realmente spawna (nativa do tema ou um boss
    existente reusado como placeholder). `status`: "implemented" (chefe nativo do
    tema) ou "placeholder" (reusa um boss existente até o nativo ser criado —
    basta trocar a classe aqui e marcar "implemented"). O resolvedor
    `get_boss_for_level` lê daqui; nada mais define a classe do boss.
    """

    level: int
    label: str
    status: str
    boss_type: Type[Any]


def _get_boss_roadmap() -> dict[int, tuple[BossSlot, ...]]:
    """Roteiro de bosses por mundo — FONTE DE VERDADE única (classe + posição).

    Imports locais pelo mesmo motivo de `_get_worlds`: evitar ciclo de importação.
    O boss de CADA nível (mid e final) é resolvido só por aqui via
    `get_boss_for_level`. Criar um chefe nativo = trocar a classe do slot e marcar
    "implemented" — sem tocar em `FIXED_LEVELS` nem em `WorldConfig`.
    """
    from ..entities.bosses.boss import Boss
    from ..entities.bosses.cloud_archmage_boss import CloudArchmageBoss
    from ..entities.bosses.giant_meteor_boss import GiantMeteorBoss
    from ..entities.bosses.city.metropolis_overlord_boss import (
        MetropolisOverlordBoss,
    )
    from ..entities.bosses.city.triad_boss import TriadBoss
    from ..entities.bosses.mountain_serpent_boss import MountainSerpentBoss
    from ..entities.bosses.slime_boss import SlimeBoss
    from ..entities.bosses.spike_boss import SpikeBoss
    from ..entities.bosses.stone_golem_boss import StoneGolemBoss

    return {
        1: (  # MOUNTAINS — chefes nativos
            BossSlot(3, "Serpente de Pedra", "implemented", MountainSerpentBoss),
            BossSlot(6, "Arquimago das Nuvens", "implemented", CloudArchmageBoss),
            BossSlot(10, "Golem de Pedra (final)", "implemented", StoneGolemBoss),
        ),
        2: (  # STARFIELD — chefes nativos
            BossSlot(12, "Chefe Clássico", "implemented", Boss),
            BossSlot(16, "Spike Boss", "implemented", SpikeBoss),
            BossSlot(20, "Meteoro Gigante", "implemented", GiantMeteorBoss),
            BossSlot(25, "Slime (final)", "implemented", SlimeBoss),
        ),
        3: (  # CITY — 3 bosses: dois nativos + o final ainda placeholder
            BossSlot(
                30, "Metropolis Overlord", "implemented", MetropolisOverlordBoss
            ),
            BossSlot(34, "A Tríade", "implemented", TriadBoss),
            # Nome definitivo já decidido; a classe nativa ainda não existe, por
            # isso o status segue "placeholder" com o GiantMeteorBoss no lugar.
            BossSlot(40, "Bobina Zênite (final)", "placeholder", GiantMeteorBoss),
        ),
        4: (  # VOLCANIC — placeholder até o chefe nativo do Vulcão
            BossSlot(50, "Boss do Vulcão (final)", "placeholder", SlimeBoss),
        ),
    }


WORLD_BOSS_ROADMAP: dict[int, tuple[BossSlot, ...]] = _get_boss_roadmap()


def get_boss_slots(world_id: int) -> tuple[BossSlot, ...]:
    """Slots de boss planejados de um mundo (vazio se não houver roteiro)."""
    return WORLD_BOSS_ROADMAP.get(world_id, ())


def _get_procedural_sector_boss(
    theme: WorldTheme, sector_idx: int, occurrence_offset: int = 0
) -> Optional[Type[Any]]:
    """Boss do chefe de fim de setor procedural (níveis 46+).

    Reusa os chefes existentes, rotacionando por OCORRÊNCIA do tema (cada 4
    setores o tema se repete → `sector_idx // 4`) para dar variedade entre
    setores do mesmo tema. VOLCANIC ainda não tem chefe nativo: usa um
    placeholder temporário até o definitivo (ver
    memory/level-progression-review-backlog).
    """
    # Imports locais (mesmo motivo de _get_worlds: evitar import circular).
    from ..entities.bosses.city.metropolis_overlord_boss import (
        MetropolisOverlordBoss,
    )
    from ..entities.bosses.city.triad_boss import TriadBoss
    from ..entities.bosses.cloud_archmage_boss import CloudArchmageBoss
    from ..entities.bosses.giant_meteor_boss import GiantMeteorBoss
    from ..entities.bosses.mountain_serpent_boss import MountainSerpentBoss
    from ..entities.bosses.slime_boss import SlimeBoss
    from ..entities.bosses.stone_golem_boss import StoneGolemBoss

    rosters: dict[WorldTheme, Tuple[Type[Any], ...]] = {
        # Montanhas tem 3 chefes próprios → rotaciona para variedade entre setores.
        WorldTheme.MOUNTAINS: (StoneGolemBoss, MountainSerpentBoss, CloudArchmageBoss),
        WorldTheme.STARFIELD: (GiantMeteorBoss,),  # chefe espacial (meteoro gigante)
        # Cidade: chefes nativos da linhagem CITY. A Bobina Zênite (slot 40) entra
        # aqui como terceiro quando a classe existir — hoje o mundo nomeado ainda
        # a resolve por placeholder, e um placeholder não pertence a este roster,
        # que é de identidade de tema.
        WorldTheme.CITY: (MetropolisOverlordBoss, TriadBoss),
        WorldTheme.VOLCANIC: (SlimeBoss,),  # TEMP até boss nativo do Vulcão
    }
    roster = rosters.get(theme)
    if not roster:
        return None
    # `occurrence_offset` distingue mid de final dentro do MESMO setor quando o
    # roster do tema tem mais de um chefe (ex.: Montanha, 3); para rosters de um
    # único boss (placeholders City/Vulcão/Espaço) o módulo mantém o mesmo.
    return roster[(sector_idx // 4 + occurrence_offset) % len(roster)]


# Estágio (1-based) do MID-boss dentro de um setor procedural. Os mundos NOMEADOS
# trazem seus mid-bosses hand-authored em FIXED_LEVELS; o modo infinito não pode
# ser hand-authored, então deriva a cadência: um mid-boss no meio do setor, além
# do chefe de fim de setor (WorldConfig.boss_level). Espelha o ritmo "chefes
# intermediários + final" dos mundos nomeados, sem entradas manuais.
PROCEDURAL_MIDBOSS_STAGE: int = PROCEDURAL_SECTOR_SIZE // 2  # 5 num setor de 10


def get_procedural_midboss_for_level(level_number: int) -> Optional[Type[Any]]:
    """Mid-boss de um nível procedural (None se não for nível de mid-boss).

    Só vale para o procedural infinito (>= PROCEDURAL_START_LEVEL): mundos
    nomeados usam FIXED_LEVELS. Retorna a classe do boss quando o nível cai no
    estágio de mid-boss do seu setor, escolhida pelo mesmo roster por tema de
    `_get_procedural_sector_boss` — assim mid e final saem da linhagem do tema.
    """
    if level_number < PROCEDURAL_START_LEVEL:
        return None
    offset = level_number - PROCEDURAL_START_LEVEL
    sector_idx = offset // PROCEDURAL_SECTOR_SIZE
    stage = offset % PROCEDURAL_SECTOR_SIZE + 1  # 1-based dentro do setor
    if stage != PROCEDURAL_MIDBOSS_STAGE:
        return None
    theme_cycle = [
        WorldTheme.MOUNTAINS,
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
    ]
    theme = theme_cycle[sector_idx % 4]
    # offset=1: tenta um chefe diferente do final do setor (no-op se roster tem 1).
    return _get_procedural_sector_boss(theme, sector_idx, occurrence_offset=1)


def get_boss_for_level(level_number: int) -> Optional[Type[Any]]:
    """Classe do boss de um nível, ou None — RESOLVEDOR ÚNICO (mid e final).

    Responde "este nível tem boss, e qual?" para QUALQUER nível:
      - mundos nomeados: lê o slot exato em `WORLD_BOSS_ROADMAP`;
      - procedural infinito: chefe de fim de setor (`level == boss_level`) ou
        mid-boss derivado do setor.
    É distinto de `WorldConfig.boss_level`, que marca só o nível FINAL do mundo
    (usado na transição de mundo, não para detectar bosses intermediários).
    """
    world = get_world_for_level(level_number)
    if world.world_id in WORLD_BOSS_ROADMAP:
        for slot in WORLD_BOSS_ROADMAP[world.world_id]:
            if slot.level == level_number:
                return slot.boss_type
        return None
    # Setor procedural (sem entrada no roadmap): fim de setor ou mid derivado.
    offset = level_number - PROCEDURAL_START_LEVEL
    sector_idx = offset // PROCEDURAL_SECTOR_SIZE
    if level_number == world.boss_level:
        return _get_procedural_sector_boss(world.theme, sector_idx)
    return get_procedural_midboss_for_level(level_number)


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================


def get_world_for_level(level_number: int) -> WorldConfig:
    """
    Retorna o mundo correspondente a um nível.

    Níveis 1-10: Mundo 1 (MOUNTAINS)
    Níveis 11-25: Mundo 2 (STARFIELD)
    Níveis 26-40: Mundo 3 (CITY) — 15 estágios, 3 bosses
    Níveis 41-50: Mundo 4 (VOLCANIC)
    Níveis 51+: Rotação de temas procedurais (MOUNTAINS -> STARFIELD -> CITY -> VOLCANIC -> ...)
    """
    for world in WORLDS.values():
        if world.contains_level(level_number):
            return world

    # Procedural infinito: cada PROCEDURAL_SECTOR_SIZE níveis = um setor com tema
    # rotacionado, começando em PROCEDURAL_START_LEVEL (derivado das fronteiras).
    offset = level_number - PROCEDURAL_START_LEVEL
    sector_idx = offset // PROCEDURAL_SECTOR_SIZE
    sector_id = sector_idx + NAMED_WORLDS_COUNT + 1
    sector_start = PROCEDURAL_START_LEVEL + sector_idx * PROCEDURAL_SECTOR_SIZE
    sector_end = sector_start + PROCEDURAL_SECTOR_SIZE - 1

    # Rotacionar entre os 4 temas principais
    theme_cycle = [
        WorldTheme.MOUNTAINS,
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
    ]
    theme_index = sector_idx % 4  # Começa no 1º setor procedural
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
        boss_level=sector_end,  # chefe de fim de setor resolvido por get_boss_for_level
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

    # IDs após os mundos nomeados representam setores procedurais.
    if world_id > NAMED_WORLDS_COUNT:
        level_number = PROCEDURAL_START_LEVEL + (
            world_id - NAMED_WORLDS_COUNT - 1
        ) * PROCEDURAL_SECTOR_SIZE
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
        final_boss = get_boss_for_level(world.boss_level)
        logger.info(
            "   Boss final: %s",
            final_boss.__name__ if final_boss else "Procedural",
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

    # Cruzar o roteiro de bosses: cada slot deve cair dentro do range do mundo, e o
    # slot FINAL deve coincidir com o boss_level do WorldConfig.
    for world_id, slots in WORLD_BOSS_ROADMAP.items():
        world = WORLDS.get(world_id)
        if world is None:
            continue
        for slot in slots:
            if not world.start_level <= slot.level <= world.end_level:
                errors.append(
                    f"Boss roadmap mundo {world_id}: slot '{slot.label}' "
                    f"(nível {slot.level}) fora do range {world.start_level}-{world.end_level}"
                )
        if slots and slots[-1].level != world.boss_level:
            errors.append(
                f"Boss roadmap mundo {world_id}: slot final (nível {slots[-1].level}) "
                f"!= boss_level {world.boss_level}"
            )

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
