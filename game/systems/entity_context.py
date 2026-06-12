"""Contexto compartilhado para o update polimórfico de inimigos.

Cada classe de inimigo implementa `update_in_context(ctx)` para traduzir o
contexto uniforme em sua chamada `update(...)` específica e empurrar
emissões (bullets/lasers/orbs/novos inimigos) nos buffers de saída do ctx.

Permite que `EntityManager.update()` dispatch via polimorfismo em vez de
cadeia de `isinstance`, respeitando o Princípio Aberto/Fechado: adicionar
um novo tipo de inimigo exige apenas implementar `update_in_context` nessa
classe — nada muda em `entity_manager.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


def _empty_any_list() -> List[Any]:
    return []


@dataclass
class EnemyUpdateContext:
    """Estado compartilhado passado a `update_in_context()` de cada inimigo.

    `sdt` é mutável e reescrito a cada iteração pelo EntityManager com o
    delta-time efetivo daquele inimigo (após EMP/ice slow).
    """

    dt: float
    sdt: float
    player_x: float
    player_y: float
    is_side_scroll: bool
    screen_width: int
    screen_height: int
    other_enemies: List[Any]

    # Buffers de emissão preenchidos pelos inimigos durante o update.
    # O EntityManager consome-os após o loop para evitar mutação concorrente.
    new_alien_bullets: List[Any] = field(default_factory=_empty_any_list)
    new_eye_lasers: List[Any] = field(default_factory=_empty_any_list)
    new_energy_orbs: List[Any] = field(default_factory=_empty_any_list)
    new_neon_bolts: List[Any] = field(default_factory=_empty_any_list)
    # Orbes da Torreta Orbital: projéteis destrutíveis que memorizam a posição
    # do jogador e viram `ElectricFieldZone` ao chegar. O EntityManager drena
    # para `orbital_orbs` e orquestra a conversão em campo.
    new_orbital_orbs: List[Any] = field(default_factory=_empty_any_list)
    new_enemies: List[Any] = field(default_factory=_empty_any_list)
    # Inimigos que devem ser desenhados ATRÁS dos demais (inseridos no início da
    # lista) — ex.: a caixa de carga do Cargueiro, que emerge por trás dele.
    new_enemies_behind: List[Any] = field(default_factory=_empty_any_list)
    # Blasts de área one-shot (cx, cy, raio) — ex.: dreno do raio do Cyber-Captor.
    # O EntityManager drena para `area_blasts`; a cena aplica dano à nave.
    new_area_blasts: List[Any] = field(default_factory=_empty_any_list)
    # Explosões pedidas por uma entidade no próprio update (x, y, size, type|None)
    # — ex.: autodestruição "Short Circuit" do Tesla Twin (morte sem on_hit).
    # O EntityManager drena chamando `spawn_explosion`.
    new_explosions: List[Any] = field(default_factory=_empty_any_list)
    # Zonas de gelo persistentes pedidas no update (x, y, raio, duração).
    # O EntityManager drena chamando `spawn_ice_poison_zone`.
    new_ice_zones: List[Any] = field(default_factory=_empty_any_list)
