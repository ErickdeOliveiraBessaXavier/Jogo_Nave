from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.config import config as Config
from ..events import game_events as events

if TYPE_CHECKING:
    from ..scenes.playing import PlayingScene
    from ..systems.player_slot import PlayerSlot


SCORE_MULTIPLIER_DURATION = 15.0


class PowerupSystem:
    """Aplica efeitos de power-ups coletados e processa a coleta por frame.

    O estado (timers de score multiplier, time stop, etc.) continua na
    `PlayingScene` — esta classe centraliza apenas o dispatch e a lógica de
    cada efeito em um lugar só.

    Em multiplayer local, cada powerup é coletado individualmente pelo slot
    que toca nele. Efeitos vinculados à nave (`shield`, `double_shot`, ...)
    afetam apenas o coletor. Efeitos globais (`score_bonus`, `time_stop`)
    valem para a partida toda, independentemente de quem coletou.
    """

    def __init__(self, scene: "PlayingScene") -> None:
        self.scene = scene
        # Lookup pré-calculado para evitar acesso repetido ao Config (imutável).
        self._powerup_values: dict[str, float] = {
            "shield_duration": Config.SHIELD_DURATION * 1000,
            "double_shot_duration": Config.DOUBLE_SHOT_DURATION,
            "speed_boost_duration": Config.SPEED_BOOST_DURATION,
            "piercing_shot_duration": Config.PIERCING_SHOT_DURATION,
            "mini_ships_duration": Config.MINI_SHIPS_DURATION,
            "rainbow_duration": Config.RAINBOW_DURATION,
            "rainbow_duration_invuln": Config.RAINBOW_DURATION * 1000,
            "rainbow_score": Config.POWERUP_SCORE_BONUS * 2,
            "cooldown_haste_reduction": Config.COOLDOWN_HASTE_REDUCTION,
            "time_stop_duration": Config.TIME_STOP_DURATION,
            "damage_boost_duration": Config.DAMAGE_BOOST_DURATION,
        }

    # ------------------------------------------------------------------
    # Aplicação de cada powerup
    # ------------------------------------------------------------------

    def apply(self, kind: str, slot: "PlayerSlot") -> None:
        """Aplica o efeito de um power-up para o slot coletor."""
        handler = self._dispatch.get(kind)
        if handler is not None:
            handler(self, slot)

    def _apply_shield(self, slot: "PlayerSlot") -> None:
        ship = slot.ship
        ship.invuln = max(ship.invuln, self._powerup_values["shield_duration"])

    def _apply_double_shot(self, slot: "PlayerSlot") -> None:
        ship = slot.ship
        ship.double_shot_timer = max(
            ship.double_shot_timer,
            self._powerup_values["double_shot_duration"],
        )

    def _apply_speed(self, slot: "PlayerSlot") -> None:
        ship = slot.ship
        ship.speed_boost_timer = max(
            ship.speed_boost_timer,
            self._powerup_values["speed_boost_duration"],
        )

    def _apply_score_bonus(self, slot: "PlayerSlot") -> None:
        # Efeito global: independente de quem coletou. Score é compartilhado.
        scene = self.scene
        scene.score_multiplier_timer = SCORE_MULTIPLIER_DURATION
        scene.score_multiplier_active = True

    def _apply_piercing(self, slot: "PlayerSlot") -> None:
        ship = slot.ship
        ship.piercing_shot_timer = max(
            ship.piercing_shot_timer,
            self._powerup_values["piercing_shot_duration"],
        )

    def _apply_mini_ships(self, slot: "PlayerSlot") -> None:
        # Mini-naves do powerup orbitam a nave do coletor. EntityManager mantém
        # uma única lista global, mas cada MiniShip carrega `self.player`, então
        # `build_mini_ships(slot)` substitui apenas as deste slot.
        scene = self.scene
        ship = slot.ship
        ship.mini_ships_timer = max(
            ship.mini_ships_timer,
            self._powerup_values["mini_ships_duration"],
        )
        scene.build_mini_ships(slot)

    def _apply_cooldown_haste(self, slot: "PlayerSlot") -> None:
        # Upgrades permanentes pertencem ao P1; cooldown haste só afeta os
        # slots dele. P2 coletar mantém o efeito sem impacto adicional.
        scene = self.scene
        scene.apply_cooldown_reduction(
            self._powerup_values["cooldown_haste_reduction"]
        )

    def _apply_time_stop(self, slot: "PlayerSlot") -> None:
        # Efeito global: congela inimigos para todos.
        scene = self.scene
        scene.time_stop_timer = max(
            scene.time_stop_timer, self._powerup_values["time_stop_duration"]
        )
        scene.freeze_active = True

    def _apply_damage_boost(self, slot: "PlayerSlot") -> None:
        ship = slot.ship
        ship.damage_boost_timer = max(
            ship.damage_boost_timer,
            self._powerup_values["damage_boost_duration"],
        )

    def _apply_chain_shot(self, slot: "PlayerSlot") -> None:
        slot.ship.activate_chain_shot()

    def _apply_repulsion_shield(self, slot: "PlayerSlot") -> None:
        slot.ship.activate_repulsion_shield()

    def _apply_life(self, slot: "PlayerSlot") -> None:
        # Vida vai para o slot coletor (P2 ganha vida quando P2 coleta).
        self.scene.change_lives_for(slot, 1)

    def _apply_rainbow(self, slot: "PlayerSlot") -> None:
        scene = self.scene
        self._apply_life(slot)
        self._apply_shield(slot)
        self._apply_double_shot(slot)
        self._apply_speed(slot)
        self._apply_mini_ships(slot)
        rainbow_score = int(self._powerup_values["rainbow_score"])
        if scene.score_multiplier_active:
            rainbow_score = int(rainbow_score * scene.score_multiplier_value)
        scene.score += rainbow_score

    # Dispatch table: chave do powerup → método não-vinculado da classe.
    # Instanciado uma vez por classe (compartilhado entre instâncias).
    _dispatch = {
        "life": _apply_life,
        "shield": _apply_shield,
        "double_shot": _apply_double_shot,
        "speed": _apply_speed,
        "score": _apply_score_bonus,
        "piercing_shot": _apply_piercing,
        "mini_ships": _apply_mini_ships,
        "cooldown_haste": _apply_cooldown_haste,
        "time_stop": _apply_time_stop,
        "rainbow": _apply_rainbow,
        "damage_boost": _apply_damage_boost,
        "chain_shot": _apply_chain_shot,
        "repulsion_shield": _apply_repulsion_shield,
    }

    # ------------------------------------------------------------------
    # Processamento por frame
    # ------------------------------------------------------------------

    def process_collection(self) -> None:
        """Processa coleta de power-ups e estrelas para todos os slots vivos.

        Cada slot consulta a colisão individualmente; o primeiro a tocar
        no powerup fica com o efeito (o `Collisions.ship_vs_powerups` remove
        o powerup da lista, então o segundo slot já não vê o que o primeiro
        coletou no mesmo frame).
        """
        scene = self.scene
        for slot in scene.roster.alive_slots():
            ship = slot.ship
            collected_stars = scene.collisions.ship_vs_stars(
                ship, scene.entity_manager.stars
            )
            if collected_stars > 0:
                # Estrelas só contam para o perfil de P1 (progressão permanente
                # vinculada à conta). P2 colhe normalmente — efeito de coleta
                # ainda emite evento, mas estrelas vão pro mesmo perfil.
                scene.player_profile.add_stars(collected_stars)
                scene.app.event_bus.emit(
                    events.PowerupCollected(
                        powerup_type="star", position=(ship.x, ship.y)
                    )
                )

            collected_powerups = scene.collisions.ship_vs_powerups(
                ship, scene.entity_manager.powerups
            )
            if scene.no_powerups_mode:
                collected_powerups = []

            for kind in collected_powerups:
                scene.app.event_bus.emit(
                    events.PowerupCollected(
                        powerup_type=kind, position=(ship.x, ship.y)
                    )
                )
                # Cofre: guarda no slot livre se houver; senão, aplica imediato
                # para não desperdiçar o powerup coletado.
                if not (ship.has_storage_slots() and ship.try_store_powerup(kind)):
                    self.apply(kind, slot)
                scene.level_controller.notify_powerup_collected()
