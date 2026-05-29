"""Factory de backgrounds por tema."""

from typing import Any, Dict, Type, cast

from .atmosphere import AtmosphereBackground
from .base import Background
from .city import CityBackground
from .mountains import MountainsBackground
from .starfield import StarfieldBackground
from .volcanic import VolcanicBackground


def create_background(
    bg_type: str, width: int, height: int, **kwargs: Any
) -> Background:
    """
    Cria um background baseado no tipo especificado.

    Args:
        bg_type: Tipo do background ('mountains', 'city', 'volcanic', 'atmosphere')
        width: Largura da tela
        height: Altura da tela
        **kwargs: Argumentos extras (ex: route para atmosphere)

    Returns:
        Instância do background apropriado

    Raises:
        ValueError: Se o tipo de background não for válido
    """
    backgrounds: Dict[str, Type[Background]] = {
        "mountains": MountainsBackground,
        "city": CityBackground,
        "volcanic": VolcanicBackground,
        "atmosphere": AtmosphereBackground,
        "starfield": StarfieldBackground,
    }

    bg_class = backgrounds.get(bg_type.lower())
    if bg_class is None:
        raise ValueError(
            f"Tipo de background inválido: {bg_type}. "
            f"Tipos válidos: {', '.join(backgrounds.keys())}"
        )

    if bg_class is AtmosphereBackground:
        route = cast(str, kwargs.get("route", "exiting"))
        return AtmosphereBackground(width, height, route=route)

    return bg_class(width, height)
