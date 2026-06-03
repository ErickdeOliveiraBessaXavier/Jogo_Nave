"""TeslaLink — coordenação leve da dupla de Tesla Twins.

Materializa o **"Boundary Link"**: dois gêmeos (topo e base) ligados por um arco
elétrico vertical. O link gerencia (1) o **handoff de entrada** (o feixe só liga
quando os DOIS chegam à posição), (2) a identidade do **líder** (o gêmeo do topo,
que computa/desenha o feixe uma vez só) e (3) a morte do parceiro → **"Short
Circuit"** no sobrevivente.

Segue o espírito do `InterceptorSquad`/`ChannelingGroup` (§1): coordenador leve
que **não conhece a cena** nem o EntityManager — só medeia entre os membros por
API pública, lendo apenas atributos públicos do irmão (`dead`, `state`), nunca
privados.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from .tesla_twin import TeslaTwin


class TeslaLink:
    def __init__(self, members: List["TeslaTwin"]) -> None:
        # Convenção: members[0] = gêmeo do topo (líder do feixe).
        self.members: List["TeslaTwin"] = list(members)
        for m in self.members:
            m.link = self
        self._advancing: bool = False
        self._overloaded: bool = False

    def _alive(self) -> List["TeslaTwin"]:
        return [m for m in self.members if not m.dead]

    def both_alive(self) -> bool:
        return len(self._alive()) >= 2

    def is_leader(self, member: "TeslaTwin") -> bool:
        alive = self._alive()
        return bool(alive) and member is alive[0]

    def partner_of(self, member: "TeslaTwin") -> "TeslaTwin | None":
        for m in self.members:
            if m is not member and not m.dead:
                return m
        return None

    def beam_active(self) -> bool:
        """Feixe ligado só com os dois vivos e ambos já avançando (entraram)."""
        return self.both_alive() and self._advancing and not self._overloaded

    def tick(self, member: "TeslaTwin", ctx: "EnemyUpdateContext") -> None:
        """Avança a coordenação. Idempotente por frame: só o líder decide."""
        alive = self._alive()

        # Morte do parceiro → sobrecarga do sobrevivente (uma vez).
        if len(alive) <= 1:
            if alive and not self._overloaded:
                self._overloaded = True
                alive[0].begin_overload()
            return

        # Handoff: o feixe só liga quando AMBOS chegaram (estado "hold").
        if member is alive[0] and not self._advancing:
            if all(m.state == "hold" for m in alive):
                self._advancing = True
                for m in alive:
                    m.state = "advance"
