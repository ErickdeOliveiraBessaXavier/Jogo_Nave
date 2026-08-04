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

    # Velocidade do projétil (× Config.BULLET_SPEED). É a contrapartida da
    # cadência: quem atira pouco sente cada erro de mira por mais tempo, então
    # o tiro pesado/preciso viaja mais rápido (menos antecipação necessária) e o
    # tiro-metralhadora viaja mais devagar (obriga a se aproximar).
    bullet_speed_mult: float = 1.0

    # Dimensões-base do projétil em px, `(comprimento, espessura)` no eixo do
    # voo — a bala troca os dois conforme a direção predominante. É **visual e
    # hitbox ao mesmo tempo** (o `rect` é o mesmo), então mexer aqui é
    # balanceamento, não estética.
    #
    # Mora no perfil, e não numa tabela dentro da bala, pelo mesmo motivo do
    # `bullet_speed_mult` logo acima: nave nova é UMA entrada neste registry, e
    # não uma entrada mais um `elif` escondido no projétil. Enquanto foi cascata
    # por `ship_id`, Cofre, Fantasma e Reverberador ficaram de fora sem que nada
    # avisasse — atiravam com a forma da Padrão por omissão, não por decisão.
    #
    # O acréscimo global de `Config.BULLET_BASE_SIZE_BONUS` e o Giant Shot são
    # aplicados por cima disto, na bala.
    bullet_size: tuple[int, int] = (10, 3)

    # Alvos EXTRA que o tiro comum atravessa antes de morrer (0 = para no 1º).
    # Existe para o tiro de dano alto não desperdiçar o excedente na massa de
    # inimigos fracos — é onde a nave lenta perdia sem compensação.
    pierce_count: int = 0

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
    # Bônus de cadência do combo, aplicado proporcional ao progresso até o cap
    # (0.15 = +15% de fire rate com o combo cheio). Brando de propósito: o dano
    # já é a recompensa principal, a cadência só dá o "embalo".
    combo_fire_rate_bonus: float = 0.0

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
        bullet_size=(10, 3),  # a forma de referência do elenco
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
        bullet_size=(12, 12),  # orbe quadrado, casa com o tema magnético
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
        description=(
            "A maior cadência do elenco (8 tiros/s), mas o tiro mais fraco "
            "(50% menos dano) e 15% mais lento."
        ),
        sprite_filename="ship_estilete.png",
        unlock_cost=40,
        bullet_size=(14, 2),  # agulha: o tiro mais fino e comprido do elenco
        # A nave ágil: toda a identidade está na cadência, e nenhuma no impacto.
        # O par cadência/dano é UM ajuste só. Veio de 1.87/0.40 (9,35 tiros/s a
        # 4 de dano): o objetivo era acalmar o RITMO, que a 9,35/s era barulhento
        # demais para o que a nave entregava — ela era a penúltima do elenco.
        #
        # O dano por tiro é INTEIRO (`_round_damage`), e é isso que amarra o
        # ajuste: 0.40→0.50 leva o tiro de 4 para 5, exatamente +25%, e não
        # existe meio-termo. Logo a cadência é o único dial fino daqui em diante,
        # e toda mudança nela move o índice composto junto — não dá para descer
        # a cadência de graça neste patamar de dano.
        #
        # 1.60 é o ponto escolhido: 8,0 tiros/s, índice 0.91. Sobe de 0.82 (era
        # o penúltimo) para entre o Reverberador (0.87) e Fantasma/Engenheiro
        # (0.97), ainda abaixo da Padrão. Buff assumido, não efeito colateral.
        #
        # 5 de dano já foi problema em 2.00/0.50 — mas ali eram 10 tiros/s e
        # 50 DPS, e a nave varria a massa E acompanhava o alvo médio. Aqui são
        # 40 DPS: o que quebrava era a combinação, não o 5 em si.
        #
        # Distinção preservada: 8,00 tiros/s contra 5,00/s do segundo mais
        # rápido (+60%), e o tiro de 5 segue o mais fraco por larga margem (o
        # próximo é 9). Ver `memory/ship-balance-model.md` para a métrica.
        fire_rate_mult=1.60,
        damage_mult=0.50,
        # Projétil lento é o custo real da cadência: obriga a lutar mais perto,
        # onde a agilidade máxima dela é gasta em sobreviver, não em farmar.
        bullet_speed_mult=0.85,
        speed_mult=1.1,  # Ainda mais rápida que a padrão, sem ser a melhor em tudo
        agility_mult=1.6,  # Máxima agilidade (quase instantânea)
        thruster_intensity_mult=1.2,
        reaction_delay=0.0,  # Reage instantaneamente
        tags=("Rápida", "DPS sustentado"),
    ),
    ShipProfile(
        id="ariete",
        display_name="Aríete",
        description=(
            "Dano +80% e +1 vida. O tiro é rápido e atravessa 1 inimigo, "
            "mas a cadência é 25% menor e a nave é 20% mais lenta."
        ),
        sprite_filename="ship_ariete.png",
        unlock_cost=55,
        bullet_size=(12, 8),  # aríete: bloco espesso, lê como projétil pesado
        fire_rate_mult=0.75,
        damage_mult=1.80,
        # Projétil pesado e veloz: menos antecipação de mira, o que compensa o
        # custo de errar com uma cadência baixa.
        bullet_speed_mult=1.25,
        # Atravessa 1 alvo — o excedente de dano vira um segundo abate na massa
        # em vez de ser desperdiçado, sem alterar o TTK contra alvo único.
        pierce_count=1,
        # Mobilidade era punitiva a ponto de anular a vantagem de dano: a nave
        # segue a mais pesada do elenco, mas sem pagar duas vezes pelo mesmo
        # trade (cadência baixa JÁ é o custo do dano alto).
        speed_mult=0.80,
        agility_mult=0.85,
        thruster_intensity_mult=0.8,
        extra_lives=1,
        reaction_delay=0.08,  # Ainda a mais lenta a reagir
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
        bullet_size=(10, 3),  # forma da Padrão — herdada quando era cascata
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
            "-1 vida e dano -15%."
        ),
        sprite_filename="ship_fantasma.png",
        unlock_cost=80,
        bullet_size=(10, 3),  # forma da Padrão — herdada quando era cascata
        # 0.85 e não 0.80: a −1 vida já é um custo pesado e o output ofensivo
        # estava em 0.92 do elenco, sem o dash compensar a diferença.
        damage_mult=0.85,
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
        bullet_size=(12, 12),  # quadrado, combina com as mini-naves
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
            "Falha se soltar antes. Projétil o mais rápido do elenco; "
            "fire rate base -25%."
        ),
        sprite_filename="ship_cacador.png",
        unlock_cost=100,
        bullet_size=(14, 6),  # dardo alongado, coerente com o charge shot
        # Alívio pequeno (era 0.70): o tiro comum rendia 0.70× contra QUALQUER
        # alvo, sem vantagem alguma. Não mais que isso porque o charge já é
        # caro de compensar — são 5 teleguiados de 3× dano (~150 de burst).
        fire_rate_mult=0.75,
        # O tiro mais veloz do jogo — identidade de sniper, e o que torna a
        # cadência baixa uma escolha de estilo em vez de um imposto.
        bullet_speed_mult=1.35,
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
            "Cada abate sem tomar dano adiciona +2% de dano (máx +100%) e "
            "acelera a cadência (até +15%). Reset ao ser atingida. Stats base -10%."
        ),
        sprite_filename="ship_reveberador.png",
        unlock_cost=100,
        bullet_size=(10, 3),  # forma da Padrão — herdada quando era cascata
        fire_rate_mult=0.90,
        damage_mult=0.90,
        speed_mult=0.90,
        agility_mult=0.95,  # Combo pune erros; movimento conservador reforça cautela
        thruster_intensity_mult=0.85,
        combo_damage_per_kill=0.02,
        combo_damage_cap=1.0,
        combo_fire_rate_bonus=0.15,
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
