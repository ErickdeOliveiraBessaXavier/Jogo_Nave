from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple


class MeteorSpec(NamedTuple):
    """Spec leve para spawn deferido de meteoros via pool.

    O EntityManager.absorb_fragments chama meteor_pool.get(*spec) para cada
    item, evitando que entidades carreguem referência ao pool.
    """

    size: int
    x: float
    y: float
    vx: float
    vy: float


@dataclass(frozen=True, slots=True)
class HitResult:
    """Resposta imutável de uma entidade a um evento de dano.

    Campos:
        killed: True se a entidade morreu neste hit (afeta score/cleanup).
        points: pontos a conceder ao jogador (>0 implica FloatingScore).
        explosion_size: raio em pixels da explosão visual (0 = nenhuma).
        explosion_type: paleta de cores de explosão (ALIEN, SLIME, etc.) ou None.
        sound: callable a tocar (ou None). Use hit_sounds.* para padrões.
        fragments: spawns derivados (entidades já alocadas ou specs). O
            EntityManager.absorb_fragments() materializa cada item.
        triggers_special_death: a entidade quer um death-sequence custom
            controlado pelo entity_manager (ex.: SlimeBoss).
        drops: coletáveis largados pela morte (power-ups). Vão para
            `entity_manager.powerups`, e NÃO para `fragments` — este último
            desemboca em `enemies`, e um power-up ali seria tratado como
            inimigo. Campo próprio em vez de farejar tipo no destino.
    """

    killed: bool = False
    points: int = 0
    explosion_size: int = 0
    explosion_type: Any = None
    sound: Callable[[], None] | None = None
    fragments: tuple[Any, ...] = field(default_factory=tuple)
    triggers_special_death: bool = False
    drops: tuple[Any, ...] = field(default_factory=tuple)


# Resultado neutro reusado quando a entidade absorve sem feedback (zero alocação no hot path).
NO_HIT = HitResult()
