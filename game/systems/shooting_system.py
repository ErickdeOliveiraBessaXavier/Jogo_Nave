"""shooting_system.py — Sistema isolado de disparo do jogador.

Extrai de PlayingScene: _fire_bullets, _get_shoot_cooldown, shoot_cd e o
gerenciamento do canal de áudio do laser carregado do Magneto.

PlayingScene não é referenciada — comunicação via parâmetros explícitos.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.upgrades_config import HOMING_DAMAGE_MULTIPLIER
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..entities.ship import Ship
    from ..systems.entity_manager import EntityManager

logger = logging.getLogger(__name__)


class ShootingSystem:
    """Gerencia cooldown, disparo regular e charge shots especiais do jogador.

    Responsabilidades:
    - Cooldown de tiro (shoot_cd) decrementado em update()
    - Disparo de balas regulares via EntityManager.spawn_bullet
    - Charge shot do Magneto (laser contínuo via spawn_cacador_laser)
    - Charge shot do Caçador (5 homing bullets com targets round-robin)
    - Gerência do canal de áudio do laser carregado (precisa de referência
      local pois usa return_channel=True — não substituível por evento)
    - Emissão de PlayerShot event

    Comunicação com PlayingScene:
    - fire(ship, player_damage_multiplier) → dispara o tiro apropriado
    - is_ready(ship) → True quando o cooldown daquela nave zerou
    - update(dt) → decrementa cooldown e libera canal de áudio
    - reset() → zera cooldowns entre fases

    Cooldown é per-ship (dict keyed por id(ship)). Em multiplayer cada nave
    tem seu próprio timer de disparo, então P1 e P2 atiram independentemente.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        event_bus: EventBus,
    ) -> None:
        self._em = entity_manager
        self._bus = event_bus
        # Cooldown por nave: chave = id(ship), valor = segundos restantes.
        # Naves não-mapeadas têm cooldown 0 implícito (atira imediatamente).
        self._cooldowns: dict[int, float] = {}
        self._charged_laser_channel: Any | None = None

    def is_ready(self, ship: Ship) -> bool:
        return self._cooldowns.get(id(ship), 0.0) <= 0.0

    def reset(self) -> None:
        """Zera todos os cooldowns entre fases. O canal de áudio é liberado em update()."""
        self._cooldowns.clear()

    def update(self, dt: float) -> None:
        """Decrementa cooldowns de todas as naves e libera o canal do laser quando não há lasers vivos."""
        if self._cooldowns:
            # Evita lista intermediária quando há poucos slots; mutação direta.
            for ship_id in list(self._cooldowns.keys()):
                new_cd = self._cooldowns[ship_id] - dt
                if new_cd <= 0.0:
                    del self._cooldowns[ship_id]
                else:
                    self._cooldowns[ship_id] = new_cd
        if self._charged_laser_channel is not None:
            has_alive = any(
                getattr(laser, "state", "") == "alive"
                for laser in self._em.cacador_lasers
            )
            if not has_alive:
                self._charged_laser_channel.stop()
                self._charged_laser_channel = None

    def fire(self, ship: Ship, player_damage_multiplier: float) -> None:
        """Dispara o tiro apropriado e reinicia o cooldown.

        Magneto/Caçador com charge ativo emitem o projétil especial respectivo.
        """
        bullet_specs = ship.bullet_spawn()
        charge_factor = ship.consume_charge()
        adjusted_damage = int(
            Config.BULLET_BASE_DAMAGE
            * player_damage_multiplier
            * ship.damage_multiplier
            * charge_factor
        )

        is_charge_shot = ship.profile.has_charge_shot and charge_factor > 1.0
        if is_charge_shot:
            ship_id = getattr(ship.profile, "id", "")
            if ship_id == "magneto":
                self._fire_magneto_charge(
                    ship, bullet_specs, adjusted_damage, charge_factor
                )
                self._cooldowns[id(ship)] = self._cooldown_for(ship)
                return
            if ship_id == "cacador":
                self._fire_cacador_charge(
                    ship, bullet_specs, adjusted_damage, charge_factor
                )
                self._cooldowns[id(ship)] = self._cooldown_for(ship)
                return

        self._bus.emit(
            events.PlayerShot(
                ship_type=ship.profile.id,
                projectile_type="bullet",
                position=(ship.x, ship.y),
                charge_level=1.0,
            )
        )

        for (
            x,
            y,
            direction,
            is_piercing,
            is_homing,
            is_explosive,
            is_low_ammo,
        ) in bullet_specs:
            # Tiros teleguiados levam multiplicador de dano direto. Combinados
            # com explosivo, o impacto direto fica mais forte (a explosão usa
            # EXPLOSIVE_BULLET_DAMAGE no collision system).
            bullet_damage = (
                int(adjusted_damage * HOMING_DAMAGE_MULTIPLIER)
                if is_homing
                else adjusted_damage
            )
            self._em.spawn_bullet(
                x,
                y,
                damage=bullet_damage,
                piercing=is_piercing,
                homing=is_homing,
                explosive=is_explosive,
                low_ammo=is_low_ammo,
                direction=direction,
                ship_id=ship.profile.id,
            )
            if is_explosive:
                ship.consume_explosive_shot()
        self._cooldowns[id(ship)] = self._cooldown_for(ship)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _cooldown_for(ship: Ship) -> float:
        return 1.0 / (ship.attack_speed_multiplier * Config.FIRE_RATE)

    def _fire_magneto_charge(
        self,
        ship: Ship,
        bullet_specs: list[Any],
        adjusted_damage: int,
        charge_factor: float,
    ) -> None:
        """Dispara o laser carregado do Magneto.

        Mantém referência ao canal de áudio para pará-lo quando o laser
        termina (gerido em update()).
        """
        if self._charged_laser_channel is not None:
            self._charged_laser_channel.stop()
        self._charged_laser_channel = sound_manager.play_boss_laser_fire(
            return_channel=True
        )
        self._bus.emit(
            events.PlayerShot(
                ship_type="magneto",
                projectile_type="cacador_laser",
                position=(ship.x, ship.y),
                charge_level=charge_factor,
            )
        )
        for x, y, direction, *_ in bullet_specs:
            dx, dy = direction
            mag = math.hypot(dx, dy)
            if mag == 0.0:
                continue
            unit_dir = (dx / mag, dy / mag)
            self._em.spawn_cacador_laser(
                x,
                y,
                direction=unit_dir,
                damage=adjusted_damage,
            )

    def _fire_cacador_charge(
        self,
        ship: Ship,
        bullet_specs: list[Any],
        adjusted_damage: int,
        charge_factor: float,
    ) -> None:
        """Dispara 5 tiros teleguiados com targets round-robin.

        No-op se já existem teleguiados em tela — evita acúmulo.
        """
        if self._em.homing_bullets:
            return
        self._bus.emit(
            events.PlayerShot(
                ship_type="cacador",
                projectile_type="homing_bullets",
                position=(ship.x, ship.y),
                charge_level=charge_factor,
            )
        )
        count = 5
        spread = math.radians(90)
        divisor = max(1, count - 1)

        live_enemies: list[Any] = [
            e for e in self._em.enemies if not getattr(e, "dead", False)
        ]
        if self._em.boss and not getattr(self._em.boss, "dead", False):
            live_enemies.append(self._em.boss)

        for x, y, direction, *_ in bullet_specs:
            dx, dy = direction
            mag = math.hypot(dx, dy)
            if mag == 0.0:
                continue
            base_angle = math.atan2(dy, dx)
            for i in range(count):
                t = i / divisor
                angle = base_angle - spread / 2 + t * spread
                dir_vec = (math.cos(angle), math.sin(angle))
                target = live_enemies[i % len(live_enemies)] if live_enemies else None
                self._em.spawn_homing_bullet(
                    x,
                    y,
                    damage=adjusted_damage,
                    direction=dir_vec,
                    locked_target=target,
                )
