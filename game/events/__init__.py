"""
events - Package de eventos do jogo.

Define eventos tipados que são emitidos pelo EventBus para comunicação
desacoplada entre sistemas.
"""

from . import game_events

__all__ = ["game_events"]
