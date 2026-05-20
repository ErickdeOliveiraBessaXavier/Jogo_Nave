from __future__ import annotations

from collections import defaultdict
from typing import Callable, Type, TypeVar

from ..events.game_events import Event

T = TypeVar("T", bound=Event)


class EventBus:
    """
    Um barramento de eventos simples para comunicação desacoplada entre sistemas.

    Permite que partes do jogo se inscrevam para ouvir eventos específicos
    e que outras partes emitam esses eventos sem conhecimento direto
    dos ouvintes.

    Usa tipos de eventos (classes) em vez de strings para segurança de tipo.
    """

    def __init__(self) -> None:
        self._subscribers: dict[Type[Event], list[Callable[..., None]]] = defaultdict(
            list
        )

    def on(self, event_type: Type[T], fn: Callable[[T], None]) -> None:
        """
        Inscreve uma função (callback) para um tipo de evento específico.

        Args:
            event_type: A classe do evento a ser ouvida (ex: PlayerShot).
            fn: A função que será chamada quando o evento for emitido.
                A função deve aceitar uma instância do evento como argumento.
        """
        self._subscribers[event_type].append(fn)

    def emit(self, event: Event) -> None:
        """
        Emite um evento, notificando todos os seus inscritos.

        Args:
            event: Uma instância de uma classe de evento (ex: PlayerShot(...)).
        """
        # Notifica os inscritos para o tipo de evento específico
        for fn in self._subscribers[type(event)]:
            try:
                fn(event)
            except Exception as e:
                print(f"Error in event handler for {type(event).__name__}: {e}")

    def clear(self) -> None:
        """Remove todos os inscritos de todos os eventos."""
        self._subscribers.clear()
