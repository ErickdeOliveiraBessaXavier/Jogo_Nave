"""Contexto compartilhado para o update polimórfico de bosses.

Cada classe de boss implementa `update_boss(ctx)` para traduzir o
contexto uniforme em sua chamada `update(...)` específica e empurrar
emissões (lasers/squares/bullets/etc.) no resultado retornado.

Permite que `EntityManager._update_boss()` dispatch via polimorfismo em vez de
cadeia de `isinstance`, respeitando o Princípio Aberto/Fechado: adicionar
um novo boss exige apenas implementar `update_boss` nessa classe — nada muda
em `entity_manager.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Protocol

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


def _empty_any_list() -> List[Any]:
    return []


@dataclass
class BossUpdateContext:
    """Contexto compartilhado passado a `update_boss()` de cada boss.

    Carrega dt + posição do player + referência ao EntityManager. O boss
    consulta `entity_manager` quando precisa de listas específicas (spikes,
    pools auxiliares) ou para sincronizar estado interno (orbital_debris).
    """

    dt: float
    player_x: float
    player_y: float | None
    entity_manager: EntityManager


@dataclass
class BossUpdateResult:
    """Resultado unificado retornado por `update_boss()`.

    Mapeia todos os tipos de emissão que qualquer boss pode gerar.
    Roteamento (cada lista vai para o grupo correspondente no EntityManager):
      - new_serpent_bullets  -> em.serpent_bullets
      - new_lasers           -> em.boss_lasers
      - new_squares          -> em.boss_squares
      - new_mines            -> em.boulders        (StoneGolem)
      - new_shards           -> em.attack_debris   (StoneGolem)
      - new_spikes           -> em.spikes          (SpikeBoss)
      - spawned_enemies      -> em.enemies
      - sound_events         -> dispatched via _dispatch_boss_sound_events
    """

    new_serpent_bullets: List[Any] = field(default_factory=_empty_any_list)
    new_lasers: List[Any] = field(default_factory=_empty_any_list)
    new_squares: List[Any] = field(default_factory=_empty_any_list)
    new_mines: List[Any] = field(default_factory=_empty_any_list)
    new_shards: List[Any] = field(default_factory=_empty_any_list)
    new_spikes: List[Any] = field(default_factory=_empty_any_list)
    spawned_enemies: List[Any] = field(default_factory=_empty_any_list)
    sound_events: List[str] = field(default_factory=list)


class BossProtocol(Protocol):
    """Protocolo que define o contrato para qualquer boss.

    Todos os bosses devem implementar esses membros para integrar-se
    harmonicamente com EntityManager sem cascata de isinstance.
    """

    is_boss: bool
    dead: bool
    health: int
    max_health: int
    w: float
    h: float
    x: float
    y: float
    BOSS_TYPE_NAME: str

    def update_boss(
        self, dt: float, ctx: BossUpdateContext
    ) -> BossUpdateResult:
        """Atualiza o boss e retorna resultado unificado com emissões.

        Args:
            dt: Delta-time desde o último frame
            ctx: Contexto compartilhado com referência ao EntityManager

        Returns:
            BossUpdateResult com todos os tipos de emissão produzidos
        """
        ...
