"""Registry de naves jogáveis.

Cada `ShipProfile` define os multiplicadores e capacidades especiais que a `Ship`
aplica em runtime. Manter este módulo livre de dependências de runtime (sem
pygame, sem entities) para permitir importação cedo e em testes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


DEFAULT_SHIP_ID: str = "padrao"


@dataclass(frozen=True)
class ShipProfile:
    """Especificação de uma nave jogável.

    Multiplicadores são aplicados sobre os valores-base da `Ship`. Powerups
    herdam esses multiplicadores (efeito é multiplicativo, não substitutivo).
    """

    # Identificação
    id: str
    display_name: str
    description: str

    # Custo em estrelas (0 para a nave inicial). Fixo — não escala.
    unlock_cost: int = 0

    # Multiplicadores base.
    fire_rate_mult: float = 1.0  # >1 = atira mais rápido
    damage_mult: float = 1.0  # >1 = mais dano por tiro
    speed_mult: float = 1.0  # >1 = mais rápida
    extra_lives: int = 0  # vidas extra além do padrão

    # Mecânicas especiais (mutuamente exclusivas na maioria das naves).
    powerup_slots: int = 0  # Cofre: 2
    has_dash: bool = False  # Fantasma
    dash_cooldown: float = 4.0
    permanent_mini_ships: int = 0  # Engenheiro: 1
    pickup_radius_mult: float = 1.0  # Magneto
    has_charge_shot: bool = False  # Caçador
    charge_shot_max_time: float = 0.8
    charge_shot_damage_mult: float = 3.0
    combo_damage_per_kill: float = 0.0  # Reverberador
    combo_damage_cap: float = 0.0  # cap aditivo (0.0 = desativado)

    # Tags para UI (atributos destacados nos cards).
    tags: tuple[str, ...] = field(default_factory=tuple)


# Ordem do registry define a ordem exibida na UI.
SHIP_REGISTRY: tuple[ShipProfile, ...] = (
    ShipProfile(
        id=DEFAULT_SHIP_ID,
        display_name="Padrão",
        description="Nave inicial balanceada. Sem multiplicadores; bom para aprender.",
        unlock_cost=0,
        tags=("Equilibrada",),
    ),
    ShipProfile(
        id="magneto",
        display_name="Magneto",
        description="Atrai estrelas e powerups num raio amplo. Stats normais.",
        unlock_cost=50,
        pickup_radius_mult=2.5,
        tags=("Coleta", "Farm"),
    ),
    ShipProfile(
        id="estilete",
        display_name="Estilete",
        description="Atira 60% mais rápido, mas cada tiro causa 35% menos dano.",
        unlock_cost=30,
        fire_rate_mult=1.60,
        damage_mult=0.65,
        tags=("Rápida", "DPS sustentado"),
    ),
    ShipProfile(
        id="ariete",
        display_name="Aríete",
        description=(
            "Dano +80% e +1 vida, mas é 30% mais lenta e atira 25% menos."
        ),
        unlock_cost=60,
        fire_rate_mult=0.75,
        damage_mult=1.80,
        speed_mult=0.70,
        extra_lives=1,
        tags=("Tanque", "Burst"),
    ),
    ShipProfile(
        id="cofre",
        display_name="Cofre",
        description=(
            "Powerups coletados vão para 2 slots; ative com Q e E na hora certa."
        ),
        unlock_cost=80,
        powerup_slots=2,
        tags=("Gerenciamento",),
    ),
    ShipProfile(
        id="fantasma",
        display_name="Fantasma",
        description=(
            "Dash com invulnerabilidade (cooldown 4s). Atravessa minas. -1 vida."
        ),
        unlock_cost=100,
        extra_lives=-1,
        has_dash=True,
        dash_cooldown=4.0,
        tags=("Mobilidade", "Frágil"),
    ),
    ShipProfile(
        id="engenheiro",
        display_name="Engenheiro",
        description=(
            "1 mini-nave permanente orbitando. Tiros principais causam 15% menos dano."
        ),
        unlock_cost=120,
        damage_mult=0.85,
        permanent_mini_ships=1,
        tags=("Drone", "Suporte"),
    ),
    ShipProfile(
        id="cacador",
        display_name="Caçador",
        description=(
            "Charge shot: segure o tiro até 0.8s para causar 3× dano. "
            "Fire rate base -30%."
        ),
        unlock_cost=150,
        fire_rate_mult=0.70,
        has_charge_shot=True,
        charge_shot_max_time=0.8,
        charge_shot_damage_mult=3.0,
        tags=("Precisão", "Burst"),
    ),
    ShipProfile(
        id="reverberador",
        display_name="Reverberador",
        description=(
            "Cada abate sem tomar dano adiciona +2% de dano (máx +100%). "
            "Reset ao ser atingida. Stats base -10%."
        ),
        unlock_cost=200,
        fire_rate_mult=0.90,
        damage_mult=0.90,
        speed_mult=0.90,
        combo_damage_per_kill=0.02,
        combo_damage_cap=1.0,
        tags=("Combo", "Escalada"),
    ),
)


_SHIPS_BY_ID: dict[str, ShipProfile] = {ship.id: ship for ship in SHIP_REGISTRY}


def get_ship_profile(ship_id: str) -> ShipProfile:
    """Retorna o ShipProfile pelo id. Cai no padrão se o id for desconhecido."""
    return _SHIPS_BY_ID.get(ship_id, _SHIPS_BY_ID[DEFAULT_SHIP_ID])


def all_ship_profiles() -> Iterable[ShipProfile]:
    """Itera sobre todas as naves na ordem de registro."""
    return SHIP_REGISTRY


def is_valid_ship_id(ship_id: str) -> bool:
    return ship_id in _SHIPS_BY_ID
