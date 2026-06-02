"""Inimigos do bioma CITY (Metrópole Neon / Cyberpunk).

Linhagem de inimigos próprios do mundo 3 (`WorldTheme.CITY`). Cada unidade
segue os contratos de `EnemyHitMixin` + `update_in_context` e é construída
com a paleta cyberpunk compartilhada (`city_palette`) e o sistema de
Layered Pixel-Maps descrito em `PROPOSTA_INIMIGOS_CIDADE.md`.

Catálogo planejado (ver proposta):
  - CityDrone     — "O Enxame"                 (implementado)
  - NeonSniper    — "Olho de Longa Distância"  (implementado)
  - PoliceInterceptor — "O Perseguidor"        (implementado)
  - CyberTank     — "O Colosso Urbano"         (implementado)
  - CyberCaptor   — "Armadilha de Energia"      (implementado)
  - TeslaTwins    — "Barreira Vertical"
"""

from .channeling import ChannelingGroup
from .city_drone import CityDrone
from .cyber_captor import CyberCaptor
from .cyber_tank import CyberTank
from .fused_drone import FusedDrone
from .neon_sniper import NeonSniper
from .police_interceptor import PoliceInterceptor

__all__ = [
    "CityDrone",
    "ChannelingGroup",
    "CyberCaptor",
    "CyberTank",
    "FusedDrone",
    "NeonSniper",
    "PoliceInterceptor",
]
