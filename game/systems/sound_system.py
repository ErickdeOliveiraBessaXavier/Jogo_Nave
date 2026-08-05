"""
sound_system.py - Sistema de áudio reativo a eventos.

Este sistema se inscreve no EventBus para ouvir eventos de jogo e
dispara os efeitos sonoros e transições de música correspondentes.
Isso desacopla a lógica de áudio das cenas de gameplay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus


class SoundSystem:
    """
    Gerencia todos os efeitos sonoros e música com base em eventos de jogo.
    """

    def __init__(self, event_bus: EventBus):
        self._bus = event_bus
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Inscreve os métodos de tratamento de eventos no EventBus."""
        self._bus.on(events.PlayerShot, self._on_player_shot)
        self._bus.on(events.AbilityDenied, self._on_ability_denied)
        self._bus.on(events.EnemyDestroyed, self._on_enemy_destroyed)
        self._bus.on(events.BossDefeated, self._on_boss_defeated)
        self._bus.on(events.GameOver, self._on_game_over)
        self._bus.on(events.PowerupCollected, self._on_powerup_collected)
        self._bus.on(events.PlayerDamaged, self._on_player_damaged)
        self._bus.on(events.PlaySound, self._on_play_sound)
        self._bus.on(events.MusicStateChange, self._on_music_state_change)
        self._bus.on(events.ScreenShake, self._on_screen_shake)

    def _on_player_shot(self, event: events.PlayerShot) -> None:
        """Toca o som de tiro do jogador."""
        if event.projectile_type == "cacador_laser":
            # Canal gerenciado diretamente em playing.py (precisa de return_channel).
            return
        sound_manager.play_shot()

    def _on_ability_denied(self, _event: events.AbilityDenied) -> None:
        """Blip curto de recusa — o mesmo do upgrade em cooldown.

        Reaproveitar é intencional: as duas situações são a MESMA para o
        jogador ("apertei e o poder não saiu"), e um som novo para cada uma só
        adicionaria vocabulário a decorar.
        """
        sound_manager.play_upgrade_denied()

    def _on_enemy_destroyed(self, event: events.EnemyDestroyed) -> None:
        """Toca um som de explosão para inimigos."""
        self._play_enemy_explosion_sound(event.enemy_type)

    def _on_boss_defeated(self, _event: events.BossDefeated) -> None:
        """Toca o som de explosão massiva do boss."""
        sound_manager.play_explosion_boss()

    def _on_game_over(self, _event: events.GameOver) -> None:
        """Game Over: abaixa o volume da música (ducking), sem cortar SFX. A
        música atual continua e os one-shots (explosão da nave) soam normalmente.
        O duck é desfeito ao sair da tela (continuar/menu) em game_over.py."""
        sound_manager.duck_music(True, source="game_over")

    def _on_powerup_collected(self, _event: events.PowerupCollected) -> None:
        """Toca o som de coleta de power-up."""
        sound_manager.play_powerup()

    def _on_player_damaged(self, event: events.PlayerDamaged) -> None:
        """Toca o som de dano no jogador."""
        if not event.is_game_over:
            sound_manager.play_boss_damage()  # Reutilizando som de dano

    def _on_play_sound(self, event: events.PlaySound) -> None:
        """Handler genérico para tocar qualquer som pelo nome."""
        self._play_named_sound(event.sound_name)

    def _on_music_state_change(self, event: events.MusicStateChange) -> None:
        """Controla a música. Data-driven: o `key` do evento escolhe a faixa
        (tema para GAME, BOSS_TYPE_NAME para BOSS); a descoberta por pasta cuida
        do resto. Não há mais ramo por boss específico."""
        if event.state == MusicState.GAME:
            sound_manager.play_theme(event.key)
        elif event.state == MusicState.BOSS:
            sound_manager.play_boss(event.key)
        elif event.state == MusicState.MENU:
            sound_manager.play_menu_music()
        elif event.state == MusicState.SILENCE:
            if event.fade_ms > 0:
                sound_manager.fade_out_music(event.fade_ms / 1000.0)
            else:
                sound_manager.stop_music(force=True)

    def _on_screen_shake(self, _event: events.ScreenShake) -> None:
        """Toca som de impacto para o tremor de tela."""
        # Tremor de tela não tem efeito sonoro dedicado no SoundManager atual.
        return None

    def _play_enemy_explosion_sound(self, enemy_type: str) -> None:
        normalized = enemy_type.lower()
        if "boss" in normalized:
            sound_manager.play_explosion_boss()
        elif any(
            token in normalized
            for token in ("alien", "slime", "spike", "serpent", "golem")
        ):
            sound_manager.play_explosion_alien()
        else:
            sound_manager.play_explosion_asteroid()

    def _play_named_sound(self, sound_name: str) -> None:
        sound_map: dict[str, Any] = {
            "shot": sound_manager.play_shot,
            "powerup": sound_manager.play_powerup,
            "warning": sound_manager.play_warning,
            "boss_laser_fire": sound_manager.play_boss_laser_fire,
            "boss_damage": sound_manager.play_boss_damage,
            "explosion_boss": sound_manager.play_explosion_boss,
            "explosion_alien": sound_manager.play_explosion_alien,
            "explosion_asteroid": sound_manager.play_explosion_asteroid,
            "time_stop_in": sound_manager.play_time_stop_in,
            "time_stop_out": sound_manager.play_time_stop_out,
            "metropolis_lightning_charge": sound_manager.play_metropolis_lightning_charge,
            "metropolis_lightning_strike": sound_manager.play_metropolis_lightning_strike,
            "metropolis_energy_zone": sound_manager.play_metropolis_energy_zone,
            "metropolis_electric_grid": sound_manager.play_metropolis_electric_grid,
            "metropolis_triple_shot": sound_manager.play_metropolis_triple_shot,
        }
        handler = sound_map.get(sound_name)
        if handler is not None:
            handler()

    def cleanup(self) -> None:
        """
        Remove os handlers do EventBus para evitar memory leaks quando
        o sistema for destruído.
        """
        self._bus.off(events.PlayerShot, self._on_player_shot)
        self._bus.off(events.AbilityDenied, self._on_ability_denied)
        self._bus.off(events.EnemyDestroyed, self._on_enemy_destroyed)
        self._bus.off(events.BossDefeated, self._on_boss_defeated)
        self._bus.off(events.GameOver, self._on_game_over)
        self._bus.off(events.PowerupCollected, self._on_powerup_collected)
        self._bus.off(events.PlayerDamaged, self._on_player_damaged)
        self._bus.off(events.PlaySound, self._on_play_sound)
        self._bus.off(events.MusicStateChange, self._on_music_state_change)
        self._bus.off(events.ScreenShake, self._on_screen_shake)
