"""
effects_system.py - Sistema de efeitos visuais reativo a eventos.

Este sistema gerencia a criação de efeitos visuais como explosões,
scores flutuantes e tremores de tela, ouvindo eventos do jogo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

from ..entities.effects.floating_score import FloatingScore
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..systems.entity_manager import EntityManager


class ScreenFeedback(Protocol):
    """O que este sistema precisa da cena — e só isso (§1).

    Contrato explícito no lugar do `scene: Any` + `hasattr` que existia aqui:
    a dependência passa a ser verificável pelo type checker, e renomear um
    método na cena vira erro em vez de um efeito que some sem aviso.
    """

    def request_screen_shake(self, duration: float, intensity: int) -> None: ...

    def request_impact_flash(self, duration: float, alpha: int) -> None: ...


class EffectsSystem:
    """
    Cria e gerencia efeitos visuais com base em eventos de jogo.
    """

    def __init__(
        self,
        event_bus: EventBus,
        entity_manager: EntityManager,
        scene: Optional[ScreenFeedback] = None,
    ):
        self._bus = event_bus
        self._entity_manager = entity_manager
        self._scene = scene
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Inscreve os handlers no EventBus."""
        self._bus.on(events.SpawnEffect, self._on_spawn_effect)
        self._bus.on(events.SpawnFloatingScore, self._on_spawn_floating_score)
        self._bus.on(events.ScreenShake, self._on_screen_shake)
        self._bus.on(events.ImpactFlash, self._on_impact_flash)

    def _on_screen_shake(self, event: events.ScreenShake) -> None:
        """Handler para tremor de tela — repassa os dados para a cena."""
        if self._scene is not None:
            self._scene.request_screen_shake(event.duration, event.intensity)

    def _on_impact_flash(self, event: events.ImpactFlash) -> None:
        """Handler para o flash de impacto (white frames) — repassa para a cena."""
        if self._scene is not None:
            self._scene.request_impact_flash(event.duration, event.alpha)

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
        if event.color is not None:
            score_obj = FloatingScore(
                x=event.x, y=event.y, value=event.score, color=event.color
            )
        else:
            score_obj = FloatingScore(x=event.x, y=event.y, value=event.score)
        self._entity_manager.floating_scores.append(score_obj)

    def cleanup(self) -> None:
        """Remove handlers registrados no EventBus."""
        self._bus.off(events.SpawnEffect, self._on_spawn_effect)
        self._bus.off(events.SpawnFloatingScore, self._on_spawn_floating_score)
        self._bus.off(events.ScreenShake, self._on_screen_shake)
        self._bus.off(events.ImpactFlash, self._on_impact_flash)
