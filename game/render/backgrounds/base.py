"""Base e utilitários compartilhados dos backgrounds de mundo."""

from abc import ABC, abstractmethod

import pygame


def optimize_surface(surf: pygame.Surface) -> pygame.Surface:
    """Aplica convert() para alinhar formato com o display (blits ~2-3x mais rápidos).
    Faz fallback silencioso se o display ainda não estiver pronto."""
    try:
        return surf.convert()
    except pygame.error:
        return surf


def optimize_alpha_surface(surf: pygame.Surface) -> pygame.Surface:
    """Aplica convert_alpha() para alinhar formato RGBA com o display.
    Faz fallback silencioso se o display ainda não estiver pronto."""
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


class Background(ABC):
    """Classe base para backgrounds de mundos."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

    @abstractmethod
    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza animação do background."""
        raise NotImplementedError

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o background."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reseta para estado inicial."""
        raise NotImplementedError

    def set_progress(self, _progress: float) -> None:
        """Hook opcional: progresso 0..1 (usado pela atmosfera). No-op por padrão."""
        return None

    def set_allow_spawning(self, _allow: bool) -> None:
        """Hook opcional: liga/desliga spawn de elementos (corpos celestes do
        starfield). No-op por padrão."""
        return None

    def set_day_night_paused(self, _paused: bool) -> None:
        """Optional hook to pause/resume day/night cycle.

        Background implementations that don't implement a day/night cycle
        can ignore this. Provides a stable API for callers that want to
        request pausing regardless of the concrete background type.
        """
        return None
