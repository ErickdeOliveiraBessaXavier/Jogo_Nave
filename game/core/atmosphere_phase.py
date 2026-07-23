"""Fase de transição "Entering / Exiting the Atmosphere".

Interstício jogável entre dois mundos, disparado quando UM dos lados é sideral
(`WorldTheme.STARFIELD`). Representa a nave entrando ou saindo da atmosfera de
um planeta durante a troca de mundo.

Este módulo concentra só a parte pura: classificação da rota e o registro de
configuração por direção. A orquestração (state machine, spawns, render) vive
em `scenes/playing.py`.

Ver `código_teste/PLANO_FASE_ATMOSFERA.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .world_config import WorldConfig, WorldTheme

# Feature flag — permite desligar a fase sem remover o wiring. Enquanto o
# conteúdo (orientação invertida, spawns, medidor de altitude) está em
# construção, o interstício roda como um placeholder curto (ver playing.py).
ATMOSPHERE_PHASE_ENABLED: bool = True

# Direções da fase.
ENTERING = "entering"  # espaço -> planeta: nave em cima, atira pra baixo (facing "south")
EXITING = "exiting"    # planeta -> espaço: nave embaixo, atira pra cima (facing "north")


def is_sideral(theme: WorldTheme) -> bool:
    """True se o mundo é 'espaço' (sideral). Hoje, apenas STARFIELD."""
    return theme == WorldTheme.STARFIELD


def classify_route(origin: WorldConfig, dest: WorldConfig) -> Optional[str]:
    """Classifica a transição origem→destino.

    - espaço → planeta -> ``ENTERING``
    - planeta → espaço -> ``EXITING``
    - planeta→planeta / espaço→espaço -> ``None`` (sem fase; só a cutscene normal)
    """
    origin_space = is_sideral(origin.theme)
    dest_space = is_sideral(dest.theme)
    if origin_space and not dest_space:
        return ENTERING
    if dest_space and not origin_space:
        return EXITING
    return None


@dataclass(frozen=True)
class AtmospherePhaseConfig:
    """Parâmetros de uma fase de atmosfera.

    `spawn_table` e `background` ficam vazios por ora — preenchidos quando o
    conteúdo (passos 5–6 do plano) for implementado.
    """

    route: str
    facing: str               # "south" (entering) | "north" (exiting)
    inverted_vertical: bool    # True no entering (inimigos sobem, scroll invertido)
    altitude_length: float     # distância/tempo total da fase (segundos) — fase longa


ATMOSPHERE_PHASES: dict[str, AtmospherePhaseConfig] = {
    ENTERING: AtmospherePhaseConfig(
        route=ENTERING,
        facing="south",
        inverted_vertical=True,
        altitude_length=120.0,
    ),
    EXITING: AtmospherePhaseConfig(
        route=EXITING,
        facing="north",
        inverted_vertical=False,
        altitude_length=120.0,
    ),
}


@dataclass
class AtmosphereState:
    """Estado de runtime da fase de atmosfera — só dados.

    Agrupa os ~13 campos que antes ficavam soltos na `PlayingScene`. A lógica
    que os muda (state machine, spawns, cinemática de morte) permanece na cena:
    é acoplada ao FSM dela e ao `EntityManager`/`EnemySpawner`, então extrair o
    comportamento converteria acoplamento intra-classe em callbacks demais
    (§1 do CLAUDE.md). Aqui só concentramos o ESTADO, deixando o `__init__` da
    cena limpo e a fase auto-documentada.

    `phase_done` tem lifecycle próprio (marca que o interstício já rodou nesta
    transição de mundo) e NÃO é resetado ao iniciar uma fase — só quando uma
    nova transição de mundo começa. Por isso não há um `reset()` global aqui:
    cada campo segue sendo escrito pela cena onde já era.
    """

    in_atmosphere: bool = False
    route: Optional[str] = None
    progress: float = 0.0
    phase_done: bool = False

    # Regressão de altitude ao morrer na atmosfera (animada).
    regressing: bool = False
    regress_from: float = 0.0
    regress_to: float = 0.0
    regress_elapsed: float = 0.0
    regress_duration: float = 0.0

    # Cinemática de "nocaute": nave desmaia e re-entra.
    death_active: bool = False
    death_phase: str = "out"  # "out" | "return"
    death_timer: float = 0.0
    death_ships: list[tuple[Any, float, float, float]] = field(default_factory=list)


def get_phase_config(route: Optional[str]) -> Optional[AtmospherePhaseConfig]:
    """Retorna a config de uma rota classificada, ou None."""
    if route is None:
        return None
    return ATMOSPHERE_PHASES.get(route)


def build_spawn_config(route: str) -> dict[type, float]:
    """Spawn table do interstício (mapa ``Tipo -> intervalo em segundos``).

    Por ora: chuva de meteoros nas duas direções. Inimigos custom da fase (e o
    meteoro invertido no Entering) entram em passos seguintes. Import local de
    `Meteor` evita ciclo de import no load do módulo.
    """
    from ..entities.enemies.space.meteor import Meteor
    from ..entities.enemies.space.satellite import Satellite, SatelliteFragment

    if route == EXITING:
        return {
            Meteor: 0.9,
            Satellite: 3.0,
            SatelliteFragment: 2.2,  # Lixo espacial à deriva
        }

    # Entering: meteoros subindo (inverted_vertical) + Satélites + destroços
    return {
        Meteor: 0.9,
        Satellite: 4.0,
        SatelliteFragment: 2.2,  # Lixo espacial à deriva
    }
