"""Registry de naves jogáveis.

Cada `ShipProfile` define os multiplicadores e capacidades especiais que a `Ship`
aplica em runtime. Manter este módulo livre de dependências de runtime (sem
pygame, sem entities) para permitir importação cedo e em testes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .i18n import t, t_or

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

    # Nome do arquivo de sprite em `game/assets/icons/`. Default reaproveita
    # o ícone da nave padrão para naves sem arte dedicada.
    sprite_filename: str = "ship_icon.png"

    # Custo em estrelas (0 para a nave inicial). Fixo — não escala.
    unlock_cost: int = 0

    # Multiplicadores base.
    fire_rate_mult: float = 1.0  # >1 = atira mais rápido
    damage_mult: float = 1.0  # >1 = mais dano por tiro
    speed_mult: float = 1.0  # >1 = mais rápida
    agility_mult: float = 1.0  # >1 = responde mais rápido ao mouse/inércia
    extra_lives: int = 0  # vidas extra além do padrão

    # Mecânicas especiais (mutuamente exclusivas na maioria das naves).
    powerup_slots: int = 0  # Cofre: 2
    has_dash: bool = False  # Fantasma
    dash_cooldown: float = 4.0
    permanent_mini_ships: int = 0  # Engenheiro: 1
    pickup_radius_mult: float = 1.0  # Magneto
    thruster_intensity_mult: float = 1.0  # Força visual do thruster
    has_charge_shot: bool = False  # Caçador
    charge_shot_max_time: float = 0.8
    charge_shot_damage_mult: float = 3.0
    combo_damage_per_kill: float = 0.0  # Reverberador
    combo_damage_cap: float = 0.0  # cap aditivo (0.0 = desativado)

    # Lag de reação ao mouse (segundos). A nave persegue a posição que o cursor
    # estava há `reaction_delay` segundos atrás. 0.0 = reação imediata.
    # Range útil: 0.0–0.12 (acima de ~0.15 parece bug).
    reaction_delay: float = 0.0

    # Tags para UI (atributos destacados nos cards).
    tags: tuple[str, ...] = ()


# Ordem do registry define a ordem exibida na UI.
SHIP_REGISTRY: tuple[ShipProfile, ...] = (
    ShipProfile(
        id=DEFAULT_SHIP_ID,
        display_name="Padrão",
        description="Nave inicial balanceada. Sem multiplicadores; bom para aprender.",
        unlock_cost=0,
        speed_mult=1.0,
        agility_mult=1.2,  # Ponto de equilíbrio (1.2 = resposta firme e rápida)
        thruster_intensity_mult=1.0,
        reaction_delay=0.03,  # Imperceptível, suaviza micromovimentos
        tags=("Equilibrada",),
    ),
    ShipProfile(
        id="magneto",
        display_name="Magneto",
        description="Atrai estrelas/powerups e possui um laser carregado ({charge}) devastador.",
        sprite_filename="ship_magnetico.png",
        unlock_cost=25,
        pickup_radius_mult=2.5,
        speed_mult=1.0,
        agility_mult=1.3,  # Coleta exige alcançar drops rapidamente
        thruster_intensity_mult=1.0,
        has_charge_shot=True,
        charge_shot_max_time=0.8,
        charge_shot_damage_mult=3.0,
        reaction_delay=0.04,  # Levemente estável
        tags=("Coleta", "Laser"),
    ),
    ShipProfile(
        id="estilete",
        display_name="Estilete",
        description="Atira 60% mais rápido, mas cada tiro causa 35% menos dano.",
        sprite_filename="ship_estilete.png",
        unlock_cost=40,
        fire_rate_mult=1.60,
        damage_mult=0.65,
        speed_mult=1.2,  # Mais rápida que a padrão
        agility_mult=1.6,  # Máxima agilidade (quase instantânea)
        thruster_intensity_mult=1.2,
        reaction_delay=0.0,  # Reage instantaneamente
        tags=("Rápida", "DPS sustentado"),
    ),
    ShipProfile(
        id="ariete",
        display_name="Aríete",
        description=("Dano +80% e +1 vida, mas é 30% mais lenta e atira 25% menos."),
        sprite_filename="ship_ariete.png",
        unlock_cost=55,
        fire_rate_mult=0.75,
        damage_mult=1.80,
        speed_mult=0.70,
        agility_mult=0.75,  # Tanque de verdade — peso sentido no controle
        thruster_intensity_mult=0.8,
        extra_lives=1,
        reaction_delay=0.12,  # A mais lenta a reagir — tanque total
        tags=("Tanque", "Burst"),
    ),
    ShipProfile(
        id="cofre",
        display_name="Cofre",
        description=(
            "Powerups coletados vão para 2 slots; ative com {cofre} na hora certa. "
            "Velocidade -15% pelo peso do cofre."
        ),
        sprite_filename="ship_cofre.png",
        unlock_cost=70,
        speed_mult=0.85,
        agility_mult=0.9,  # Pesada pelo carregamento
        thruster_intensity_mult=0.75,
        powerup_slots=2,
        reaction_delay=0.10,  # Pesada em todos os sentidos
        tags=("Gerenciamento",),
    ),
    ShipProfile(
        id="fantasma",
        display_name="Fantasma",
        description=(
            "{dash}: dash com invulnerabilidade (cd 4s). Atravessa minas. "
            "-1 vida e dano -20%."
        ),
        sprite_filename="ship_fantasma.png",
        unlock_cost=80,
        damage_mult=0.80,
        speed_mult=1.1,
        agility_mult=1.5,  # Muito ágil para compensar fragilidade
        thruster_intensity_mult=1.25,
        extra_lives=-1,
        has_dash=True,
        dash_cooldown=4.0,
        reaction_delay=0.0,  # Reage instantaneamente — mobilidade é o tema
        tags=("Mobilidade", "Frágil"),
    ),
    ShipProfile(
        id="engenheiro",
        display_name="Engenheiro",
        description=(
            "1 mini-nave permanente orbitando. Tiros principais causam 15% menos dano."
        ),
        sprite_filename="ship_engenheiro.png",
        unlock_cost=90,
        damage_mult=0.85,
        speed_mult=1.0,
        agility_mult=1.05,  # Mini-nave cobre área; jogador pode ser mais conservador
        thruster_intensity_mult=0.9,
        permanent_mini_ships=1,
        reaction_delay=0.06,  # Nave de suporte, não precisa de reflexo
        tags=("Drone", "Suporte"),
    ),
    ShipProfile(
        id="cacador",
        display_name="Caçador",
        description=(
            "Charge shot: segure {charge} até 0.8s para 3× dano. "
            "Falha se soltar antes. Fire rate base -30%."
        ),
        sprite_filename="ship_cacador.png",
        unlock_cost=100,
        fire_rate_mult=0.70,
        speed_mult=1.0,
        agility_mult=1.0,  # Charge shot exige posicionamento deliberado, não reflexo
        thruster_intensity_mult=0.95,
        has_charge_shot=True,
        charge_shot_max_time=0.8,
        charge_shot_damage_mult=3.0,
        reaction_delay=0.08,  # Reforça o estilo deliberado do charge shot
        tags=("Precisão", "Burst"),
    ),
    ShipProfile(
        id="reverberador",
        display_name="Reverberador",
        description=(
            "Cada abate sem tomar dano adiciona +2% de dano (máx +100%). "
            "Reset ao ser atingida. Stats base -10%."
        ),
        sprite_filename="ship_reveberador.png",
        unlock_cost=100,
        fire_rate_mult=0.90,
        damage_mult=0.90,
        speed_mult=0.90,
        agility_mult=0.95,  # Combo pune erros; movimento conservador reforça cautela
        thruster_intensity_mult=0.85,
        combo_damage_per_kill=0.02,
        combo_damage_cap=1.0,
        reaction_delay=0.07,  # Cautela reforçada
        tags=("Combo", "Escalada"),
    ),
)


_SHIPS_BY_ID: dict[str, ShipProfile] = {ship.id: ship for ship in SHIP_REGISTRY}


def get_ship_profile(ship_id: str) -> ShipProfile:
    """Retorna o ShipProfile pelo id. Cai no padrão se o id for desconhecido."""
    return _SHIPS_BY_ID.get(ship_id, _SHIPS_BY_ID[DEFAULT_SHIP_ID])


# Placeholders permitidos nas descrições. Mantidos como dict literal — ao
# adicionar uma nova habilidade input-específica em alguma nave, basta criar
# uma chave aqui e usar `{nova_chave}` no `description` correspondente.
# Placeholders de input traduzidos por token. Só `cofre`/`dash`/`charge` do
# teclado carregam texto PT/EN; os do controle ("LT") são universais.
def _input_tokens(gamepad_active: bool) -> dict[str, str]:
    if gamepad_active:
        return {"charge": "LT", "cofre": t("ship.token.cofre_gp"), "dash": "LT"}
    return {
        "charge": t("ship.token.charge_kb"),
        "cofre": t("ship.token.cofre_kb"),
        "dash": t("ship.token.dash_kb"),
    }


# Mapa tag (PT canônico nos dados) → slug estável usado nas chaves de tradução.
_TAG_KEYS: dict[str, str] = {
    "Equilibrada": "balanced",
    "Coleta": "collection",
    "Laser": "laser",
    "Rápida": "fast",
    "DPS sustentado": "sustained_dps",
    "Tanque": "tank",
    "Burst": "burst",
    "Gerenciamento": "management",
    "Mobilidade": "mobility",
    "Frágil": "fragile",
    "Drone": "drone",
    "Suporte": "support",
    "Precisão": "precision",
    "Combo": "combo",
    "Escalada": "scaling",
}


def ship_display_name(ship: ShipProfile) -> str:
    """Nome da nave no idioma atual (fallback = PT do registry)."""
    return t_or(f"ship.{ship.id}.name", ship.display_name)


def translate_tag(tag: str) -> str:
    """Traduz uma tag de nave; desconhecida passa intacta."""
    slug = _TAG_KEYS.get(tag)
    return t_or(f"ship.tag.{slug}", tag) if slug else tag


def ship_tags(ship: ShipProfile) -> tuple[str, ...]:
    """Tags da nave traduzidas, na ordem original."""
    return tuple(translate_tag(tg) for tg in ship.tags)


def format_ship_description(ship: ShipProfile, gamepad_active: bool = False) -> str:
    """Descrição traduzida da nave com placeholders `{charge}/{cofre}/{dash}`
    substituídos pela tecla/botão do input ativo. Fallback = PT do registry.
    """
    desc = t_or(f"ship.{ship.id}.desc", ship.description)
    try:
        return desc.format(**_input_tokens(gamepad_active))
    except (KeyError, IndexError):
        # Defensivo: placeholder desconhecido → devolve a string crua.
        return desc


def all_ship_profiles() -> tuple[ShipProfile, ...]:
    """Itera sobre todas as naves na ordem de registro."""
    return SHIP_REGISTRY


def is_valid_ship_id(ship_id: str) -> bool:
    return ship_id in _SHIPS_BY_ID
