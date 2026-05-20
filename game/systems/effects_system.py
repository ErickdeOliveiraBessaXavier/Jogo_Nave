"""
effects_system.py - Sistema de efeitos visuais reativo a eventos.

Este sistema gerencia a criação de efeitos visuais como explosões,
scores flutuantes e tremores de tela, ouvindo eventos do jogo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..entities.floating_score import FloatingScore
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..systems.entity_manager import EntityManager


class EffectsSystem:
    """
    Cria e gerencia efeitos visuais com base em eventos de jogo.
    """

    def __init__(self, event_bus: EventBus, entity_manager: EntityManager):
        self._bus = event_bus
        self._entity_manager = entity_manager
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Inscreve os handlers no EventBus."""
        self._bus.on(events.SpawnEffect, self._on_spawn_effect)
        self._bus.on(events.SpawnFloatingScore, self._on_spawn_floating_score)

    def _on_spawn_effect(self, event: events.SpawnEffect) -> None:
        """Handler genérico para criar efeitos visuais."""
        if event.effect_type == "explosion":
            self._entity_manager.spawn_explosion(
                x=event.position[0],
                y=event.position[1],
                size=event.size,
            )
        # Outros tipos de efeitos podem ser adicionados aqui
        # ex: "smoke", "sparkles", etc.

    def _on_spawn_floating_score(self, event: events.SpawnFloatingScore) -> None:
        """Cria um texto de score flutuante."""
        kwargs = {}
        if event.color is not None:
            kwargs["color"] = event.color

        score_obj = FloatingScore(x=event.x, y=event.y, value=event.score, **kwargs)
        self._entity_manager.floating_scores.append(score_obj)

    def cleanup(self) -> None:
        """Remove handlers registrados no EventBus."""
        self._bus.off(events.SpawnEffect, self._on_spawn_effect)
        self._bus.off(events.SpawnFloatingScore, self._on_spawn_floating_score)
