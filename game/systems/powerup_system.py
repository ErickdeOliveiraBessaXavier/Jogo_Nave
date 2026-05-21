from __future__ import annotations

from typing import TYPE_CHECKING

from ..events import game_events as events

if TYPE_CHECKING:
    from ..scenes.playing import PlayingScene


class PowerupSystem:
    """Aplica efeitos de power-ups coletados e processa a coleta por frame.

    O estado (timers de score multiplier, time stop, etc.) continua na
    `PlayingScene` — esta classe centraliza apenas o dispatch e a lógica de
    cada efeito em um lugar só.
    """

    def __init__(self, scene: "PlayingScene") -> None:
        self.scene = scene

    # ------------------------------------------------------------------
    # Aplicação de cada powerup
    # ------------------------------------------------------------------

    def apply(self, kind: str) -> None:
        """Aplica o efeito de um power-up coletado via dict-dispatch."""
        handler = self._dispatch.get(kind)
        if handler is not None:
            handler(self)

    def _apply_shield(self) -> None:
        scene = self.scene
        scene.ship.invuln = max(scene.ship.invuln, scene._powerup_values["shield_duration"])

    def _apply_double_shot(self) -> None:
        scene = self.scene
        scene.ship.double_shot_timer = max(
            scene.ship.double_shot_timer,
            scene._powerup_values["double_shot_duration"],
        )

    def _apply_speed(self) -> None:
        scene = self.scene
        scene.ship.speed_boost_timer = max(
            scene.ship.speed_boost_timer,
            scene._powerup_values["speed_boost_duration"],
        )

    def _apply_score_bonus(self) -> None:
        # Importação local — evita ciclo com playing.py em módulo top-level.
        from ..scenes.playing import _SCORE_MULTIPLIER_DURATION

        scene = self.scene
        scene.score_multiplier_timer = _SCORE_MULTIPLIER_DURATION
        scene.score_multiplier_active = True

    def _apply_piercing(self) -> None:
        scene = self.scene
        scene.ship.piercing_shot_timer = max(
            scene.ship.piercing_shot_timer,
            scene._powerup_values["piercing_shot_duration"],
        )

    def _apply_mini_ships(self) -> None:
        scene = self.scene
        scene.ship.mini_ships_timer = max(
            scene.ship.mini_ships_timer,
            scene._powerup_values["mini_ships_duration"],
        )
        scene._build_mini_ships()

    def _apply_cooldown_haste(self) -> None:
        scene = self.scene
        scene._apply_cooldown_reduction(
            scene._powerup_values["cooldown_haste_reduction"]
        )

    def _apply_time_stop(self) -> None:
        scene = self.scene
        scene.time_stop_timer = max(
            scene.time_stop_timer, scene._powerup_values["time_stop_duration"]
        )
        scene.freeze_active = True

    def _apply_damage_boost(self) -> None:
        scene = self.scene
        scene.ship.damage_boost_timer = max(
            scene.ship.damage_boost_timer,
            scene._powerup_values["damage_boost_duration"],
        )

    def _apply_chain_shot(self) -> None:
        self.scene.ship.activate_chain_shot()

    def _apply_repulsion_shield(self) -> None:
        self.scene.ship.activate_repulsion_shield()

    def _apply_life(self) -> None:
        self.scene._change_lives(1)

    def _apply_rainbow(self) -> None:
        scene = self.scene
        self._apply_life()
        self._apply_shield()
        self._apply_double_shot()
        self._apply_speed()
        self._apply_mini_ships()
        rainbow_score = int(scene._powerup_values["rainbow_score"])
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
        """Processa coleta de power-ups e estrelas (chamado por frame)."""
        scene = self.scene
        collected_stars = scene.collisions.ship_vs_stars(
            scene.ship, scene.entity_manager.stars
        )
        if collected_stars > 0:
            scene.player_profile.add_stars(collected_stars)
            scene.app.event_bus.emit(
                events.PowerupCollected(
                    powerup_type="star", position=(scene.ship.x, scene.ship.y)
                )
            )

        collected_powerups = scene.collisions.ship_vs_powerups(
            scene.ship, scene.entity_manager.powerups
        )
        if scene._no_powerups_mode:
            collected_powerups = []

        for kind in collected_powerups:
            scene.app.event_bus.emit(
                events.PowerupCollected(
                    powerup_type=kind, position=(scene.ship.x, scene.ship.y)
                )
            )
            # Cofre: guarda no slot livre se houver; senão, aplica imediato
            # para não desperdiçar o powerup coletado.
            if not (
                scene.ship.has_storage_slots() and scene.ship.try_store_powerup(kind)
            ):
                self.apply(kind)
            scene.level_controller.notify_powerup_collected()
