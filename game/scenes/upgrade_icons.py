"""upgrade_icons.py — a arte de cada upgrade, descoberta por pasta.

Estrutura pronta para a arte que ainda não existe. Um upgrade ganha ícone assim
que um PNG com o nome do `icon_id` aparecer em::

    game/assets/images/upgrades/<icon_id>.png

Sem código novo, sem registro em mapa nenhum — mesma ideia das pastas de música
por tema/boss. Enquanto o arquivo não existe, o chamador desenha o medalhão de
letra de sempre (`get_upgrade_icon`), que é o fallback.

**O cache guarda também a AUSÊNCIA.** Sem isso seriam 23 `Path.exists()` por
frame (um por célula do grid) só para redescobrir que a arte ainda não chegou —
acesso a disco no laço de render, pelo resultado mais previsível possível.
Consequência aceita: soltar um PNG novo com o jogo aberto só aparece no próximo
boot. É uma tela de menu, não um editor.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import pygame

from ..core.assets import BASE_DIR

ICON_DIR = BASE_DIR / "assets" / "images" / "upgrades"

# (icon_id, lado) -> superfície escalada, ou None quando não há arte.
_CACHE: Dict[Tuple[str, int], Optional[pygame.Surface]] = {}


def icon_surface(icon_id: str, size: int) -> Optional[pygame.Surface]:
    """PNG do upgrade escalado para ``size``×``size``, ou ``None``.

    ``None`` significa "ainda não tem arte" — não é erro, é o estado normal
    enquanto os ícones não são produzidos.
    """
    if size <= 0:
        return None
    chave = (icon_id, size)
    if chave in _CACHE:
        return _CACHE[chave]

    caminho = ICON_DIR / f"{icon_id}.png"
    surf: Optional[pygame.Surface] = None
    if caminho.exists():
        try:
            surf = pygame.transform.scale(
                pygame.image.load(str(caminho)).convert_alpha(), (size, size)
            )
        except (OSError, pygame.error, ValueError):
            # Arquivo presente mas ilegível: cai no fallback como se não
            # existisse. Um PNG corrompido não pode derrubar a tela inteira.
            surf = None

    _CACHE[chave] = surf
    return surf


def has_icon(icon_id: str) -> bool:
    """Existe arte para este upgrade? (Consulta barata, via cache.)"""
    return icon_surface(icon_id, 1) is not None


def clear_cache() -> None:
    """Esquece o que foi descoberto. Só para teste."""
    _CACHE.clear()
