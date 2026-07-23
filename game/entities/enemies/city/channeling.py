"""Canalização em grupo dos City Drones → mini-chefe dinâmico.

Quando 4 drones livres ficam próximos, há 10% de chance de iniciarem uma
**canalização em grupo**: orbitam um ponto central invisível ("sol"), ganham
um boost grande de vida e entram em transformação. Se o jogador **não** abater
os 4 a tempo, eles se fundem num `FusedDrone` (mini-chefe). Abater qualquer um
**quebra** o ritual.

Este coordenador é deliberadamente leve e não conhece a cena (§1): recebe os
membros, dirige o progresso e empurra o mini-chefe no buffer `ctx.new_enemies`
(o mesmo contrato que o `EntityManager` consome após o loop de update).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from .city_drone import CityDrone


class ChannelingGroup:
    DURATION = 4.5  # segundos até a fusão completar
    HP_BOOST = 3.0  # multiplicador de vida ao entrar em canalização
    RADIUS_START = 95.0  # raio orbital inicial
    RADIUS_END = 16.0  # raio ao completar (convergem para o centro)
    SPIN_START = 1.4  # rad/s no início
    SPIN_END = 7.0  # rad/s ao completar (gira cada vez mais rápido)
    CENTER_DRIFT = 22.0  # deriva lenta do centro (px/s) p/ não ficar congelado

    def __init__(
        self,
        members: List["CityDrone"],
        center_x: float,
        center_y: float,
        side_scroll: bool,
    ) -> None:
        self.members = list(members)
        self.cx = center_x
        self.cy = center_y
        self.side_scroll = side_scroll
        self.progress = 0.0
        self.done = False
        self.broken = False
        self.spawned = False

        # Vida original de cada membro antes do boost. Estado do ritual (não do
        # drone): vive aqui para não furar a fronteira do CityDrone (§1).
        self._health_before: dict[CityDrone, int] = {}

        n = len(self.members)
        for i, member in enumerate(self.members):
            member.channel_group = self
            member.channel_angle = i * (math.tau / n)
            self._health_before[member] = member.health
            member.health = int(member.health * self.HP_BOOST) + 1
            member.vx = 0.0
            member.vy = 0.0

    def current_radius(self) -> float:
        return self.RADIUS_START + (self.RADIUS_END - self.RADIUS_START) * self.progress

    def spin_speed(self) -> float:
        return self.SPIN_START + (self.SPIN_END - self.SPIN_START) * self.progress

    def tick(self, member: "CityDrone", dt: float) -> None:
        """Avança o ritual. Chamado por cada membro; só o líder soma progresso."""
        if self.done or self.broken:
            return
        if any(m.dead for m in self.members):
            self._break()
            return
        # Líder = primeiro membro (vivo, senão o any-dead acima já quebrou).
        if member is self.members[0]:
            self.progress = min(1.0, self.progress + dt / self.DURATION)
            if self.side_scroll:
                self.cx -= self.CENTER_DRIFT * dt
            if self.progress >= 1.0:
                self.done = True

    def _break(self) -> None:
        self.broken = True
        for m in self.members:
            if not m.dead:
                # Remove o boost remanescente (não pode ficar tanky para sempre).
                m.health = min(m.health, self._health_before[m])
            m.channel_group = None

    def spawn_boss(self, ctx: "EnemyUpdateContext") -> None:
        """Funde os membros num FusedDrone, empurrado no buffer de novos inimigos."""
        if self.spawned:
            return
        self.spawned = True

        # Import local: evita ciclo (fused_drone importa CityDrone no topo).
        from .fused_drone import FusedDrone

        proto = self.members[0]
        boss = FusedDrone(
            self.cx,
            self.cy,
            aggressiveness_multiplier=proto.aggressiveness_multiplier,
            side_scroll=self.side_scroll,
            health_multiplier=proto.health_multiplier,
        )
        ctx.new_enemies.append(boss)

        # Membros são "consumidos": morrem em silêncio (sem explosão/pontos).
        for m in self.members:
            m.dead = True
            m.channel_group = None
