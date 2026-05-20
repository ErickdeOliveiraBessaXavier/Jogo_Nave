"""
sound_system.py - Sistema de áudio reativo a eventos.

Este sistema se inscreve no EventBus para ouvir eventos de jogo e
dispara os efeitos sonoros e transições de música correspondentes.
Isso desacopla a lógica de áudio das cenas de gameplay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.sound import sound_manager
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
        self._bus.on(events.EnemyDestroyed, self._on_enemy_destroyed)
        self._bus.on(events.BossDefeated, self._on_boss_defeated)
        self._bus.on(events.PowerupCollected, self._on_powerup_collected)
        self._bus.on(events.PlayerDamaged, self._on_player_damaged)
        self._bus.on(events.PlaySound, self._on_play_sound)
        self._bus.on(events.MusicStateChange, self._on_music_state_change)
        self._bus.on(events.ScreenShake, self._on_screen_shake)

    def _on_player_shot(self, event: events.PlayerShot) -> None:
        """Toca o som de tiro do jogador."""
        # Lógica mais complexa pode ser adicionada aqui, ex: som diferente por arma
        if event.projectile_type == "cacador_laser":
            sound_manager.play_boss_laser_fire()
        else:
            sound_manager.play_shot()

    def _on_enemy_destroyed(self, event: events.EnemyDestroyed) -> None:
        """Toca um som de explosão para inimigos."""
        # Poderia ter sons diferentes para inimigos grandes/pequenos
        sound_manager.play_explosion()

    def _on_boss_defeated(self, event: events.BossDefeated) -> None:
        """Toca o som de explosão massiva do boss."""
        sound_manager.play_explosion_boss()

    def _on_powerup_collected(self, event: events.PowerupCollected) -> None:
        """Toca o som de coleta de power-up."""
        sound_manager.play_powerup()

    def _on_player_damaged(self, event: events.PlayerDamaged) -> None:
        """Toca o som de dano no jogador."""
        if not event.is_game_over:
            sound_manager.play_boss_damage()  # Reutilizando som de dano

    def _on_play_sound(self, event: events.PlaySound) -> None:
        """Handler genérico para tocar qualquer som pelo nome."""
        # Este é um evento mais genérico que permite a qualquer sistema
        # solicitar a reprodução de um som sem conhecer o sound_manager.
        sound_manager.play(event.sound_name, volume=event.volume)

    def _on_music_state_change(self, event: events.MusicStateChange) -> None:
        """Controla a música de fundo."""
        sound_manager.set_music_state(event.state, event.fade_ms)

    def _on_screen_shake(self, event: events.ScreenShake) -> None:
        """Toca som de impacto para o tremor de tela."""
        # Exemplo: som de "rumble" ou impacto pesado
        sound_manager.play("rumble", volume=0.7)

    def cleanup(self) -> None:
        """
        Remove os handlers do EventBus para evitar memory leaks quando
        o sistema for destruído.
        """
        # A implementação do EventBus.off(event, handler) seria necessária
        # para uma limpeza seletiva. Por enquanto, o bus pode ser recriado
        # a cada nova cena.
        pass
