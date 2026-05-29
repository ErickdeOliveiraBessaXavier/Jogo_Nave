"""Backgrounds dinâmicos por mundo.

Pacote segmentado por tema; ``base`` guarda a classe-base e utilitários
compartilhados. Este ``__init__`` é a fachada que preserva a API pública
anterior (``from ..render.backgrounds import Background, create_background,
MountainsBackground, ...``) — os call sites externos não mudam.
"""

from .atmosphere import AtmosphereBackground
from .base import Background
from .city import CityBackground
from .factory import create_background
from .mountains import MountainsBackground
from .volcanic import VolcanicBackground

__all__ = [
    "Background",
    "create_background",
    "MountainsBackground",
    "CityBackground",
    "VolcanicBackground",
    "AtmosphereBackground",
]
