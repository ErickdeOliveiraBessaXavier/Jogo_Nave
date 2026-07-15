"""Identidade visual do impacto de cada nave (estético, sem efeito em jogo).

Cada nave já tinha um tiro com cor própria; o impacto continuava genérico, então
dois tiros diferentes acertando o mesmo inimigo produziam a mesma faísca. Aqui
cada nave ganha um par (forma, paleta) escolhido para ecoar a fantasia dela — o
Magneto atrai, então o impacto dele IMPLODE; o Reverberador ecoa, então o dele
sai em anéis concêntricos.

Regra de escopo (importante, ver `CollisionPhysics.apply_hit`): este estilo só
vale para hits que NÃO matam. A explosão de morte fica intacta — é a que o
inimigo pede (ALIEN verde, SLIME roxo, CYBER, ICE_CORE) — para não apagar a
identidade de tema que os hostis já carregam.

Consequência aceita de propósito: `Alien.on_hit` e `Meteor.on_hit` setam
`dead = True` incondicionalmente, ignorando dano e vida. Como eles nunca geram
um hit não-letal, o estilo da nave não aparece nesses dois — a explosão deles é
a de sempre. O efeito vale nos demais hostis (que têm vida) e nos bosses, que
levam muitos tiros antes de cair.

Ordem das paletas: `Explosion._get_color` indexa por life_ratio, onde 1.0 é a
partícula recém-nascida. Logo a lista vai de [morte → nascimento] — a última cor
é o clarão do impacto, a primeira é como ele se apaga.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..core.player_tint import player_shot_color
from .explosion import ImpactPattern

Palette = Tuple[Tuple[int, int, int], ...]


@dataclass(frozen=True)
class ImpactStyle:
    """Forma + paleta do impacto de uma nave."""

    pattern: str
    palette: Palette


# Nave → impacto. As cores partem do tiro que a nave já desenha em `Bullet`
# (`_draw_ship_specific_bullet`); manter as duas coisas na mesma família é o que
# faz o impacto parecer consequência do tiro e não um efeito solto.
SHIP_IMPACT_STYLES: Dict[str, ImpactStyle] = {
    # Padrão: o clássico amarelo. Fica no burst de sempre — é a referência
    # contra a qual as outras naves se leem como diferentes.
    "padrao": ImpactStyle(
        ImpactPattern.BURST, ((255, 90, 0), (255, 200, 0), (255, 255, 180))
    ),
    # Magneto atrai: o impacto colapsa para dentro.
    "magneto": ImpactStyle(
        ImpactPattern.IMPLODE, ((40, 40, 160), (100, 100, 255), (200, 220, 255))
    ),
    # Estilete corta rápido e raso: faíscas riscadas, nada de nuvem.
    "estilete": ImpactStyle(
        ImpactPattern.SPARK, ((0, 120, 40), (0, 255, 100), (200, 255, 200))
    ),
    # Aríete é peso: onda de choque anelar.
    "ariete": ImpactStyle(
        ImpactPattern.RING, ((140, 30, 0), (255, 80, 0), (255, 190, 90))
    ),
    # Cofre guarda tesouro: brasas douradas que jorram e caem.
    "cofre": ImpactStyle(
        ImpactPattern.EMBER, ((150, 90, 0), (255, 190, 60), (255, 245, 190))
    ),
    # Fantasma não estala: dissipa em névoa que sobe.
    "fantasma": ImpactStyle(
        ImpactPattern.WISP, ((30, 90, 110), (120, 220, 235), (225, 255, 255))
    ),
    # Engenheiro é elétrico: pequenos raios em zigue-zague.
    "engenheiro": ImpactStyle(
        ImpactPattern.BOLT, ((0, 60, 150), (0, 170, 255), (230, 245, 255))
    ),
    # Caçador é precisão: estrela de pontas retas, como uma mira acertando.
    "cacador": ImpactStyle(
        ImpactPattern.STAR, ((90, 90, 120), (192, 192, 220), (255, 255, 255))
    ),
    # Reverberador ecoa: anéis concêntricos em sequência.
    "reverberador": ImpactStyle(
        ImpactPattern.ECHO, ((110, 0, 110), (255, 0, 255), (255, 190, 255))
    ),
    # Berserk estilhaça.
    "berserk": ImpactStyle(
        ImpactPattern.SHATTER, ((70, 0, 130), (150, 0, 255), (255, 160, 255))
    ),
}


# Memo por (nave, jogador). O P2 gira a matiz da paleta inteira; sem o memo isso
# reconverteria as cores a cada tiro que acerta.
_styles: Dict[Tuple[str, int], Optional[ImpactStyle]] = {}


def impact_style(ship_id: str, player_index: int = 0) -> Optional[ImpactStyle]:
    """Estilo de impacto da nave na cor do jogador, ou None se ela não tem um.

    None não é erro: significa "usa o efeito genérico de sempre", que é o certo
    para projéteis sem dono claro.
    """
    key = (ship_id, player_index)
    if key in _styles:
        return _styles[key]

    base = SHIP_IMPACT_STYLES.get(ship_id)
    if base is None:
        _styles[key] = None
        return None

    if player_index == 1:
        style = ImpactStyle(
            base.pattern,
            tuple(player_shot_color(c, player_index) for c in base.palette),  # type: ignore[arg-type]
        )
    else:
        style = base
    _styles[key] = style
    return style


def impact_for_projectile(projectile: object) -> Optional[ImpactStyle]:
    """Estilo do projétil pelo dono dele, ou None se não dá para saber.

    Aceita as duas convenções de dono que convivem no código (`owner_ship` nas
    balas, `source_ship` no teleguiado) e cai fora silenciosamente para
    projéteis sem nave associada — o efeito genérico segue valendo.
    """
    owner = getattr(projectile, "owner_ship", None)
    if owner is None:
        owner = getattr(projectile, "source_ship", None)

    ship_id = getattr(projectile, "ship_id", None)
    if ship_id is None and owner is not None:
        ship_id = getattr(getattr(owner, "profile", None), "id", None)
    if ship_id is None:
        return None

    return impact_style(ship_id, getattr(owner, "player_index", 0))
