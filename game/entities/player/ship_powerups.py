from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Optional

from ...core.config import config as Config
from ...systems.targeting import enemy_center, find_nearest_enemy

if TYPE_CHECKING:
    from ...systems.entity_manager import EntityManager
    from .ship import Ship


ORBITAL_ROTATION_SPEED = 2.0
ORBITAL_COOLDOWN_MIN = 2.0
ORBITAL_COOLDOWN_MAX = 4.0
ORBITAL_INITIAL_COOLDOWN_MIN = 2.0
ORBITAL_INITIAL_COOLDOWN_MAX = 5.0


class ShipPowerups:
    """Lida com ativação, ticks e timers dos powerups da `Ship`.

    Os atributos de timer continuam vivendo na `Ship` (leitura externa difundida
    no código). Esta classe centraliza as mutações coesas em um único lugar.
    """

    def __init__(self, ship: "Ship") -> None:
        self.ship = ship

    # ---------- Ativações ----------

    def activate_shield(self, duration: float, shield_hp: int = 1) -> None:
        ship = self.ship
        ship.shield_timer = max(ship.shield_timer, duration)
        ship.shield_hp = max(ship.shield_hp, shield_hp)

    def activate_homing_shots(
        self,
        duration: float,
        speed_penalty: float = 0.75,
        fire_rate_penalty: float = 0.8,
    ) -> None:
        ship = self.ship
        ship.homing_shots_active = True
        ship.homing_shots_timer = duration
        ship.homing_speed_penalty = speed_penalty
        ship.homing_fire_rate_penalty = fire_rate_penalty
        ship.speed = ship.original_speed * speed_penalty

    def activate_orbital_lasers(self) -> None:
        ship = self.ship
        ship.orbital_lasers_active = True
        ship.orbital_angle = 0.0
        ship.orbital_laser_charges = [
            ship.orbital_charges_per_ball for _ in range(ship.num_orbital_balls)
        ]
        ship.orbital_ball_fade = [0.0 for _ in range(ship.num_orbital_balls)]
        # Animação de entrada: cada orb entra com delay sequencial (0.2s).
        entry_delay = 0.2
        ship.orbital_ball_entry = [
            0.5 + (i * entry_delay) for i in range(ship.num_orbital_balls)
        ]
        ship.orbital_ball_shake = [0.0 for _ in range(ship.num_orbital_balls)]
        ship.orbital_current_ball = 0
        ship.orbital_global_cooldown = random.uniform(
            ORBITAL_INITIAL_COOLDOWN_MIN, ORBITAL_INITIAL_COOLDOWN_MAX
        )

    def activate_explosive_shots(self, charges: int) -> None:
        ship = self.ship
        ship.explosive_shots_active = True
        ship.explosive_shots_remaining = charges

    def activate_giant_shots(self, duration: float) -> None:
        """Ativa (ou estende) o Giant Shot: balas maiores por ``duration`` s."""
        ship = self.ship
        ship.big_shot_timer = max(ship.big_shot_timer, duration)

    def activate_dash(self, duration: float) -> None:
        ship = self.ship
        ship.dash_timer = max(ship.dash_timer, duration)
        
        # Corrigir direção do dash para seguir a orientação da nave
        import pygame
        vx, vy = ship.get_facing_vector()
        ship.dash_dir = pygame.math.Vector2(vx, vy)
        
        # Bônus de velocidade durante o Blink Dash
        if not hasattr(ship, "original_speed"):
            ship.original_speed = ship.speed
        ship.speed = ship.original_speed * 2.5

    def activate_chain_shot(self, duration: float | None = None) -> None:
        ship = self.ship
        d = duration if duration is not None else Config.CHAIN_SHOT_DURATION
        ship.chain_shot_timer = max(ship.chain_shot_timer, d)

    def activate_implosion_shots(self, duration: float) -> None:
        ship = self.ship
        ship.implosion_shot_timer = max(ship.implosion_shot_timer, duration)

    def activate_critical_core(self, duration: float) -> None:
        ship = self.ship
        ship.critical_core_timer = max(ship.critical_core_timer, duration)

    def activate_cryo_shots(self, duration: float) -> None:
        ship = self.ship
        ship.cryo_shot_timer = max(ship.cryo_shot_timer, duration)

    def activate_shockwave(self, duration: float) -> None:
        ship = self.ship
        ship.shockwave_timer = max(ship.shockwave_timer, duration)

    def activate_corrosive_ammo(self, duration: float) -> None:
        ship = self.ship
        ship.corrosive_timer = max(ship.corrosive_timer, duration)

    def activate_repulsion_shield(self, duration: float | None = None) -> None:
        ship = self.ship
        d = duration if duration is not None else Config.REPULSION_SHIELD_DURATION
        ship.repulsion_shield_timer = max(ship.repulsion_shield_timer, d)

    # ---------- Consumo / Storage ----------

    def consume_explosive_shot(self) -> bool:
        ship = self.ship
        if ship.explosive_shots_remaining > 0:
            ship.explosive_shots_remaining -= 1
            if ship.explosive_shots_remaining <= 0:
                ship.explosive_shots_active = False
            return True
        return False

    def has_storage_slots(self) -> bool:
        return self.ship.profile.powerup_slots > 0

    def try_store_powerup(self, kind: str) -> bool:
        ship = self.ship
        if not self.has_storage_slots():
            return False
        for i, slot in enumerate(ship.stored_powerups):
            if slot is None:
                ship.stored_powerups[i] = kind
                return True
        return False

    def consume_stored_powerup(self, slot_index: int) -> Optional[str]:
        ship = self.ship
        if not (0 <= slot_index < len(ship.stored_powerups)):
            return None
        kind = ship.stored_powerups[slot_index]
        if kind is not None:
            ship.stored_powerups[slot_index] = None
        return kind

    # ---------- Updates por frame ----------

    def update_timers(self, dt: float) -> None:
        ship = self.ship
        if ship.invuln > 0:
            ship.invuln = max(0, ship.invuln - dt * 1000)
            if ship.invuln == 0:
                # Zera a referência junto: um `invuln_total` órfão faria a
                # próxima concessão herdar a duração da anterior por um frame,
                # e a piscada começaria na fase errada.
                ship.invuln_total = 0.0

        ship.double_shot_timer = max(0.0, ship.double_shot_timer - dt)
        ship.spread_shot_timer = max(0.0, ship.spread_shot_timer - dt)
        ship.speed_boost_timer = max(0.0, ship.speed_boost_timer - dt)
        ship.piercing_shot_timer = max(0.0, ship.piercing_shot_timer - dt)
        ship.mini_ships_timer = max(0.0, ship.mini_ships_timer - dt)
        ship.damage_boost_timer = max(0.0, ship.damage_boost_timer - dt)
        ship.big_shot_timer = max(0.0, ship.big_shot_timer - dt)
        ship.chain_shot_timer = max(0.0, ship.chain_shot_timer - dt)
        ship.implosion_shot_timer = max(0.0, ship.implosion_shot_timer - dt)
        ship.critical_core_timer = max(0.0, ship.critical_core_timer - dt)
        ship.cryo_shot_timer = max(0.0, ship.cryo_shot_timer - dt)
        ship.shockwave_timer = max(0.0, ship.shockwave_timer - dt)
        ship.corrosive_timer = max(0.0, ship.corrosive_timer - dt)
        ship.repulsion_shield_timer = max(0.0, ship.repulsion_shield_timer - dt)

        ship.shield_timer = max(0.0, ship.shield_timer - dt)
        if ship.shield_timer <= 0.0:
            ship.shield_hp = 0

        if ship.homing_shots_active:
            ship.homing_shots_timer = max(0.0, ship.homing_shots_timer - dt)
            if ship.homing_shots_timer <= 0.0:
                ship.homing_shots_active = False
                ship.speed = ship.original_speed

        # Reset de velocidade do Blink Dash
        if hasattr(ship, "dash_timer") and ship.dash_timer > 0.0:
            # Note: dash_timer é decrementado em ShipMovement.update_dash(dt)
            if ship.dash_timer <= dt: # Vai acabar agora ou já acabou
                ship.speed = ship.original_speed

        # Debuffs elementais
        ship.fire_rate_modifier_timer = max(0.0, ship.fire_rate_modifier_timer - dt)
        ship.invert_controls_timer = max(0.0, ship.invert_controls_timer - dt)
        ship.speed_modifier_timer = max(0.0, ship.speed_modifier_timer - dt)

        self._update_electric_debuff(dt)

    def _update_electric_debuff(self, dt: float) -> None:
        """Debuff elétrico da Torreta Orbital: descarga periódica que paralisa.

        Enquanto "carregada", a nave rola a cada `ELECTRIC_DISCHARGE_INTERVAL`
        uma chance `ELECTRIC_DISCHARGE_CHANCE` de uma descarga breve que trava o
        movimento por `ELECTRIC_STUN_MIN..MAX` segundos. Após cada descarga há uma
        **janela de recuperação** (`ELECTRIC_STUN_RECOVERY`) imune a nova
        paralisia — garante tempo de sair do campo e evita chain-stun.
        """
        ship = self.ship

        # Paralisia (descarga ativa) e imunidade pós-descarga correm sempre.
        if ship.electric_stun_timer > 0.0:
            ship.electric_stun_timer = max(0.0, ship.electric_stun_timer - dt)
        if ship.electric_stun_recovery_timer > 0.0:
            ship.electric_stun_recovery_timer = max(
                0.0, ship.electric_stun_recovery_timer - dt
            )

        if ship.electric_debuff_timer <= 0.0:
            ship._electric_discharge_roll_t = 0.0
            return

        ship.electric_debuff_timer = max(0.0, ship.electric_debuff_timer - dt)

        # Sem novas descargas durante a paralisia ou a janela de recuperação.
        if ship.is_stunned or ship.electric_stun_recovery_timer > 0.0:
            return

        ship._electric_discharge_roll_t += dt
        interval = ship.ELECTRIC_DISCHARGE_INTERVAL
        while ship._electric_discharge_roll_t >= interval:
            ship._electric_discharge_roll_t -= interval
            if random.random() < ship.ELECTRIC_DISCHARGE_CHANCE:
                dur = random.uniform(ship.ELECTRIC_STUN_MIN, ship.ELECTRIC_STUN_MAX)
                ship.electric_stun_timer = dur
                # A imunidade cobre o próprio stun + a folga de recuperação.
                ship.electric_stun_recovery_timer = dur + ship.ELECTRIC_STUN_RECOVERY
                break

    def update_orbital_lasers(
        self, dt: float, entity_manager: Optional["EntityManager"]
    ) -> None:
        ship = self.ship
        if not ship.orbital_lasers_active:
            return

        all_done = all(
            charges <= 0 and fade <= 0.0
            for charges, fade in zip(ship.orbital_laser_charges, ship.orbital_ball_fade)
        )
        if all_done:
            ship.orbital_lasers_active = False
            return

        ship.orbital_angle += dt * ORBITAL_ROTATION_SPEED

        for i in range(ship.num_orbital_balls):
            if ship.orbital_ball_entry[i] > 0.0:
                ship.orbital_ball_entry[i] = max(0.0, ship.orbital_ball_entry[i] - dt)

            if ship.orbital_ball_shake[i] > 0.0:
                ship.orbital_ball_shake[i] = max(0.0, ship.orbital_ball_shake[i] - dt)

            if ship.orbital_laser_charges[i] <= 0 and ship.orbital_ball_fade[i] > 0.0:
                ship.orbital_ball_fade[i] = max(0.0, ship.orbital_ball_fade[i] - dt)

        if entity_manager is None:
            return

        ship.orbital_global_cooldown = max(0.0, ship.orbital_global_cooldown - dt)
        if ship.orbital_global_cooldown > 0.0:
            return

        # Import local para evitar custo no módulo (sound_manager toca laser shot).
        from ...core.sound import sound_manager

        attempts = 0
        while attempts < ship.num_orbital_balls:
            i = ship.orbital_current_ball

            if ship.orbital_laser_charges[i] > 0:
                if ship.ship_image is not None:
                    sprite_w, sprite_h = ship.ship_image.get_size()
                else:
                    sprite_w, sprite_h = ship.w, ship.h

                angle = ship.orbital_angle + (i * 2 * math.pi / ship.num_orbital_balls)
                ball_x = ship.x + sprite_w / 2 + math.cos(angle) * ship.orbital_radius
                ball_y = ship.y + sprite_h / 2 + math.sin(angle) * ship.orbital_radius

                nearest_enemy = find_nearest_enemy(ball_x, ball_y, entity_manager)

                if nearest_enemy is not None:
                    target = enemy_center(nearest_enemy)
                    if (
                        target is not None
                        and -50 < target[0] < Config.SCREEN_WIDTH + 50
                        and -50 < target[1] < Config.SCREEN_HEIGHT + 50
                    ):
                        entity_manager.spawn_player_laser(
                            ball_x,
                            ball_y,
                            target[0],
                            target[1],
                            ship=ship,
                            ball_index=i,
                            target_entity=nearest_enemy,
                        )
                        sound_manager.play_laser_shot()
                        # Tremor de 0.8s (duração do laser).
                        ship.orbital_ball_shake[i] = 0.8
                        ship.orbital_laser_charges[i] -= 1
                        if ship.orbital_laser_charges[i] <= 0:
                            ship.orbital_ball_fade[i] = 1.5

                        ship.orbital_current_ball = (
                            ship.orbital_current_ball + 1
                        ) % ship.num_orbital_balls

                        ship.orbital_global_cooldown = random.uniform(
                            ORBITAL_COOLDOWN_MIN, ORBITAL_COOLDOWN_MAX
                        )
                        return

                ship.orbital_current_ball = (
                    ship.orbital_current_ball + 1
                ) % ship.num_orbital_balls
                attempts += 1
            else:
                ship.orbital_current_ball = (
                    ship.orbital_current_ball + 1
                ) % ship.num_orbital_balls
                attempts += 1

    def update_repulsion_shield(
        self, dt: float, entity_manager: Optional["EntityManager"]
    ) -> None:
        ship = self.ship
        if entity_manager is None:
            return

        if ship.repulsion_shield_timer > 0.0:
            spawn_rate = 60
            for _ in range(
                int(spawn_rate * dt)
                + (1 if random.random() < (spawn_rate * dt) % 1 else 0)
            ):
                sprite_w, sprite_h = ship.get_rendered_sprite_size()
                angle = random.uniform(0, math.tau)
                ship.repulsion_wind_streaks.append(
                    {
                        "angle": angle,
                        "dist": random.uniform(5.0, 30.0),
                        "speed": random.uniform(900, 1500),
                        "len": random.uniform(40, 90),
                        "alpha": random.randint(120, 200),
                        "cx": ship.x + sprite_w / 2,
                        "cy": ship.y + sprite_h / 2,
                    }
                )

            # Sopro constante: empurra inimigos no raio (exclui bosses e mountain).
            radius = Config.REPULSION_SHIELD_RADIUS * 1.5
            cx = ship.x + ship.w / 2
            cy = ship.y + ship.h / 2

            enemies = entity_manager.enemy_spatial_grid.query(
                cx - radius, cy - radius, radius * 2, radius * 2
            )

            for enemy in enemies:
                if getattr(enemy, "dead", False):
                    continue
                class_name = enemy.__class__.__name__
                if (
                    hasattr(enemy, "boss")
                    or "Boss" in class_name
                    or "Mountain" in class_name
                ):
                    continue

                center = enemy_center(enemy)
                ex = (
                    center[0] if center is not None else float(getattr(enemy, "x", 0.0))
                )
                ey = (
                    center[1] if center is not None else float(getattr(enemy, "y", 0.0))
                )

                dx = ex - cx
                dy = ey - cy
                dist_sq = dx * dx + dy * dy

                if 0 < dist_sq < radius**2:
                    dist = math.sqrt(dist_sq)
                    blow_force = Config.REPULSION_FORCE * 2.8 * (1.0 - (dist / radius))
                    try:
                        setattr(
                            enemy,
                            "x",
                            getattr(enemy, "x") + (dx / dist) * blow_force * dt,
                        )
                        setattr(
                            enemy,
                            "y",
                            getattr(enemy, "y") + (dy / dist) * blow_force * dt,
                        )
                    except (AttributeError, TypeError):
                        continue

        # Streaks visuais decaem independente do timer do power-up.
        # §6: update in-place, rebuild por comprehension.
        max_dist = Config.REPULSION_SHIELD_RADIUS * 2.5
        for s in ship.repulsion_wind_streaks:
            s["dist"] += s["speed"] * dt
            s["alpha"] -= 400 * dt
        ship.repulsion_wind_streaks = [
            s
            for s in ship.repulsion_wind_streaks
            if s["alpha"] > 0 and s["dist"] <= max_dist
        ]
