"""revival_system.py — Beacons de revive do multiplayer local (§1, §9).

Extraído de `PlayingScene`. Concentra o ciclo de vida do revive cooperativo:
quando um slot morre em coop, nasce um beacon na posição da nave; um parceiro
vivo que entre no raio e segure o botão de revive preenche a barra e o
ressuscita.

Não referencia `PlayingScene` (§1). As dependências entram pelo construtor:

- `roster`  — fonte dos slots vivos/mortos (lido, nunca reatribuído aqui).
- `gamepad` — leitura do botão de revive por slot.
- `sync_lives(slot, lives)`      — callback: ajusta as vidas no revive. A cena
  mantém a lógica de vidas (HUD, game over), então isto volta pra lá.
- `rebuild_mini_ships(slot)`      — callback: restaura mini-naves permanentes
  (Engenheiro), removidas na morte.

O estado do beacon vive em `PlayerSlot.revival_beacon`, não aqui: o sistema é
sem estado próprio, opera sobre os slots do roster. Isso mantém uma fonte única
(o slot) e deixa render e input lerem o beacon direto do slot que já conhecem.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from ..entities.revival_beacon import RevivalBeacon

if TYPE_CHECKING:
    from ..core.gamepad import GamepadManager
    from ..systems.player_slot import PlayerRoster, PlayerSlot

logger = logging.getLogger(__name__)


class RevivalSystem:
    """Ciclo de vida dos beacons de revive cooperativo."""

    def __init__(
        self,
        roster: "PlayerRoster",
        gamepad: "GamepadManager",
        sync_lives: Callable[["PlayerSlot", int], None],
        rebuild_mini_ships: Callable[["PlayerSlot"], None],
    ) -> None:
        self._roster = roster
        self._gamepad = gamepad
        self._sync_lives = sync_lives
        self._rebuild_mini_ships = rebuild_mini_ships

    def spawn_beacon(self, slot: "PlayerSlot") -> None:
        """Cria o beacon na posição da nave do slot que acabou de morrer.

        No-op fora de coop (< 2 slots): em single-player a morte é game over
        imediato, sem revive.
        """
        if self._roster.count() < 2:
            return
        ship = slot.ship
        slot.revival_beacon = RevivalBeacon(
            x=float(ship.rect.centerx),
            y=float(ship.rect.centery),
            for_slot=slot,
            ship_image=ship.ship_image,
        )
        logger.info(
            "Beacon de revive spawnou em (%.0f, %.0f) para slot morto.",
            slot.revival_beacon.x,
            slot.revival_beacon.y,
        )

    def update(self, dt: float) -> None:
        """Processa todos os beacons ativos: hold, acúmulo de timer, revive."""
        dead_with_beacon = [
            s for s in self._roster.dead_slots() if s.revival_beacon is not None
        ]
        if not dead_with_beacon:
            return

        alive = self._roster.alive_slots()
        for dead_slot in dead_with_beacon:
            beacon = dead_slot.revival_beacon
            assert beacon is not None
            beacon.update_visual(dt)

            # Proximidade visual: dica aparece se qualquer vivo estiver no raio.
            near_any = any(
                beacon.contains_point(
                    float(s.ship.rect.centerx), float(s.ship.rect.centery)
                )
                for s in alive
            )
            beacon.set_hint_visible(near_any)

            helper = self._find_helper(beacon, alive)
            if helper is not None:
                beacon.tick_hold(dt)
                if beacon.is_complete:
                    self._revive(dead_slot)
            else:
                beacon.reset_progress()

    def slot_inside_any_beacon(self, slot: "PlayerSlot") -> bool:
        """True se o slot vivo está no raio de algum beacon ativo.

        Usado pelo input handler para suprimir a ativação do Cofre (botão Y)
        enquanto o jogador tenta reviver alguém — o Y é compartilhado e o revive
        (held) tem precedência.
        """
        ship = slot.ship
        px, py = float(ship.rect.centerx), float(ship.rect.centery)
        for dead in self._roster.dead_slots():
            beacon = dead.revival_beacon
            if beacon is not None and beacon.contains_point(px, py):
                return True
        return False

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _find_helper(
        self, beacon: RevivalBeacon, alive_slots: list["PlayerSlot"]
    ) -> Optional["PlayerSlot"]:
        """Primeiro slot vivo no raio segurando o botão de revive, ou None."""
        for helper in alive_slots:
            ship = helper.ship
            if not beacon.contains_point(
                float(ship.rect.centerx), float(ship.rect.centery)
            ):
                continue
            if self._is_button_held(helper):
                return helper
        return None

    def _is_button_held(self, slot: "PlayerSlot") -> bool:
        """Checa se o slot está segurando o botão de revive (Y / tecla Y)."""
        from ..core.gamepad import XboxButton

        slot_idx = slot.gamepad_slot if slot.gamepad_slot is not None else 0
        if self._gamepad.is_button_pressed(XboxButton.Y, slot=slot_idx):
            return True
        # Fallback teclado só para P1 (slot 0 inclui teclado por convenção).
        if slot_idx == 0:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_y]:
                return True
        return False

    def _revive(self, slot: "PlayerSlot") -> None:
        """Ressuscita o slot na posição do beacon com vida e invuln inicial."""
        beacon = slot.revival_beacon
        if beacon is None:
            return
        ship = slot.ship
        # Reposiciona a nave no beacon para o player "renascer" no local.
        ship.x = beacon.x - ship.w / 2.0
        ship.y = beacon.y - ship.h / 2.0
        ship.invuln = RevivalBeacon.POST_REVIVE_INVULN_MS
        slot.is_dead = False
        slot.revival_beacon = None
        self._sync_lives(slot, RevivalBeacon.LIVES_ON_REVIVE)
        # Restaura mini-naves permanentes (Engenheiro), removidas na morte.
        self._rebuild_mini_ships(slot)
        logger.info(
            "Slot revivido em (%.0f, %.0f) com %d vida.",
            beacon.x,
            beacon.y,
            RevivalBeacon.LIVES_ON_REVIVE,
        )
