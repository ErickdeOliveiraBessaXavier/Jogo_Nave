"""player_slot.py — Abstração de "slot de jogador" para suporte a multiplayer local.

Cada jogador ativo na partida é representado por um `PlayerSlot` que agrupa
sua `Ship`, controle associado, vidas individuais e estado de morte/revive.
O `PlayerRoster` mantém a lista ordenada de slots (P1 primeiro) e expõe
queries comuns ("vivos", "mortos", "primário") usadas pela `PlayingScene`
e pelos sistemas (colisões, shooting, render).

Esta camada existe para que a cena possa iterar `roster.alive_slots()` em
vez de assumir um único `self.ship`. Mantém referência ao `Ship` sem
duplicar seus dados — vidas ficam no slot porque são "metadados de jogador",
não da nave em si (P1 e P2 podem ter pools de vida independentes mesmo
usando ships de mesmo tipo).

Não importa `RevivalBeacon` em runtime: a entidade será criada na Fase 6
do plano de multiplayer e até lá o campo permanece `None`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, List, Optional

if TYPE_CHECKING:
    from ..entities.revival_beacon import RevivalBeacon
    from ..entities.ship import Ship


@dataclass
class PlayerSlot:
    """Estado por-jogador. Mutável: vidas e flags evoluem durante a partida."""

    ship: "Ship"
    lives: int
    gamepad_id: Optional[int] = None
    """`instance_id` do pygame joystick atribuído a este slot. None = teclado."""

    is_dead: bool = False
    """True quando lives chegou a 0 — ship está oculta esperando revive."""

    revival_beacon: Optional["RevivalBeacon"] = None
    """Beacon ativo quando este slot está morto e pode ser revivido."""

    apply_permanent_upgrades: bool = True
    """False para P2: ignora bônus permanentes do MetaProgression do P1."""


@dataclass
class PlayerRoster:
    """Lista ordenada de slots ativos. Slot 0 é sempre P1 (primário)."""

    _slots: List[PlayerSlot] = field(default_factory=list)

    @classmethod
    def with_primary(cls, primary: PlayerSlot) -> "PlayerRoster":
        roster = cls()
        roster._slots.append(primary)
        return roster

    def primary(self) -> PlayerSlot:
        """Retorna P1. Lança IndexError se roster vazio — invariante da cena."""
        return self._slots[0]

    def all_slots(self) -> List[PlayerSlot]:
        return list(self._slots)

    def alive_slots(self) -> List[PlayerSlot]:
        return [s for s in self._slots if not s.is_dead]

    def dead_slots(self) -> List[PlayerSlot]:
        return [s for s in self._slots if s.is_dead]

    def add(self, slot: PlayerSlot) -> None:
        self._slots.append(slot)

    def remove(self, slot: PlayerSlot) -> None:
        self._slots.remove(slot)

    def count(self) -> int:
        return len(self._slots)

    def __iter__(self) -> Iterator[PlayerSlot]:
        return iter(self._slots)

    def __len__(self) -> int:
        return len(self._slots)
