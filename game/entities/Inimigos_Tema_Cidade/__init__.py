"""Inimigos do bioma CITY (Metrópole Neon / Cyberpunk).

Linhagem de inimigos próprios do mundo 3 (`WorldTheme.CITY`). Cada unidade
segue os contratos de `EnemyHitMixin` + `update_in_context` e é construída
com a paleta cyberpunk compartilhada (`city_palette`) e o sistema de
Layered Pixel-Maps descrito em `PROPOSTA_INIMIGOS_CIDADE.md`.

Catálogo planejado (ver proposta):
  - CityDrone     — "O Enxame"        (implementado)
  - NeonSniper    — "Olho de Longa Distância"
  - PoliceInterceptor — "O Perseguidor"
  - CyberTank     — "O Colosso Urbano"
  - CyberCaptor   — "Armadilha de Energia"
  - TeslaTwins    — "Barreira Vertical"
"""

from .channeling import ChannelingGroup
from .city_drone import CityDrone
from .fused_drone import FusedDrone

__all__ = ["CityDrone", "ChannelingGroup", "FusedDrone"]
