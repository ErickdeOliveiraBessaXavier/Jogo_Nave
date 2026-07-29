"""Marcas que o DONO do disparo propaga a cada alvo que ele fere.

Um modificador de tiro por tempo que **marca o alvo** (Cryo Shot, Corrosive
Ammo) é uma propriedade da NAVE, não da bala: quem responde por ele é o
`owner_ship`. Isso quer dizer que ele vale para tudo que sai daquela nave — a
bala do cano, o acerto no chefe e, agora, cada salto do Chain Lightning.

**Por que um registro e não um `if` por upgrade.** Antes, cada caminho de acerto
tinha o seu par "booleano + chamada":

    bullet_cryo_active = not is_shard and owner and owner.has_cryo_shot
    ...
    if bullet_cryo_active:
        self._apply_cryo(enemy, owner)

Com dois modificadores isso já eram quatro blocos espalhados por dois métodos, e
cada caminho novo (o salto da cadeia, a explosão, o feixe) precisava lembrar de
repetir todos eles. Quem esquecesse um teria uma sinergia que simplesmente não
acontece, sem erro nenhum para denunciar.

Com o registro, um modificador novo entra **numa linha aqui** e passa a valer,
de graça, em todo caminho que já pergunta por marcas. E um caminho novo vira
duas linhas, não uma por upgrade:

    marks = shot_marks.active_marks(owner)
    shot_marks.apply_marks(marks, alvo, owner)

**A cor.** Efeito que PROPAGA a marca (o raio da cadeia) muda de cor para dizer
o que está carregando. A cor mora no registro junto da marca, então a resposta
para "de que cor fica o raio com o upgrade novo?" também é a mesma linha.

Convivência: as marcas se acumulam — um alvo pode estar gelado E corroído, e a
ordem de aplicação é a do registro. Só a COR tem de escolher uma, e escolhe a
primeira ativa (ver `propagation_color`).
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple, Tuple

from ..core.upgrades_config import (
    CORROSIVE_COLOR,
    CORROSIVE_DURATION,
    CORROSIVE_MAX_STACKS,
    CRYO_FREEZE_DURATION,
    CRYO_MAX_STACKS,
    CRYO_SLOW_DURATION,
)
from ..entities._shared.control_marks import accepts_corrosion, accepts_cryo

# Azul-gelo do cristal. Repetido aqui (e não importado de `bullet`) para o
# registro não depender de um módulo de render — a marca é regra, não desenho.
_CRYO_MARK_COLOR: Tuple[int, int, int] = (170, 225, 255)


def apply_cryo(enemy: Any, owner: Any = None) -> None:
    """Sobe um degrau da escada de gelo no alvo e renova a duração.

    O nível mora no ALVO (`cryo_stacks`), não na nave nem na bala: é o que faz
    P1 e P2 alimentarem a mesma escada em coop, e o que faz o nível cair junto
    com o alvo em vez de sobreviver a ele.

    A duração é REPOSTA a cada acerto (não somada): é isso que torna o upgrade
    condicional — o nível cheio dura enquanto o jogador insistir no mesmo alvo,
    e cai inteiro quando ele solta. Cheia, ela é também o pavio da bomba de gelo,
    então reacertar o alvo ADIA o estouro: o jogador escolhe entre segurar o
    controle e colher o dano.

    `owner` fica gravado no alvo para que o leque de fragmentos saia com a cor do
    jogador certo e credite o kill a ele (combo do Reverberador). Quem marcou por
    último leva o crédito — em coop é o que responde à pergunta "de quem foi esse
    estouro?" da forma que o jogador espera.

    O guard é o `accepts_cryo`, não o `can_be_controlled`: **boss e miniboss
    acumulam as cargas** e cristalizam. O que eles não recebem é a lentidão,
    recusada em `EntityManager._cryo_multiplier`.
    """
    if not accepts_cryo(enemy):
        return
    stacks = min(CRYO_MAX_STACKS, int(getattr(enemy, "cryo_stacks", 0)) + 1)
    enemy.cryo_stacks = stacks
    # O topo da escada é o estágio CONGELADO e vale mais tempo — é a recompensa
    # por ter mantido a pressão nos três acertos.
    enemy.cryo_slow_timer = (
        CRYO_FREEZE_DURATION if stacks >= CRYO_MAX_STACKS else CRYO_SLOW_DURATION
    )
    if owner is not None:
        enemy.cryo_owner = owner


def apply_corrosion(enemy: Any, owner: Any = None) -> None:
    """Sobe uma carga de ácido no alvo e repõe a duração.

    A pilha mora no ALVO (`corrosive_stacks`), não na nave nem na bala, pelos
    mesmos dois motivos do Cryo: em coop os dois jogadores alimentam a mesma
    pilha, e ela morre junto com o alvo em vez de sobreviver a ele.

    A duração é REPOSTA a cada acerto (não somada). Somar deixaria um alvo muito
    castigado corroendo por meio minuto depois de o jogador ter ido embora;
    repondo, o ácido dura o quanto o jogador insistir, mais a janela de
    `CORROSIVE_DURATION` para terminar o serviço.

    O que NÃO é tocado aqui é o `corrosive_damage_cd`: o acumulador do tique é do
    alvo e segue correndo sozinho. Se um acerto o reiniciasse, atirar mais rápido
    adiaria o dano em vez de aumentá-lo — e atirar na cadência exata do intervalo
    cancelaria o DoT por completo.

    O guard é o `accepts_corrosion`: **boss e miniboss corroem**, e é contra eles
    que o upgrade existe (alvo único, muita vida, muito tempo em tela).
    """
    if not accepts_corrosion(enemy):
        return
    enemy.corrosive_stacks = min(
        CORROSIVE_MAX_STACKS, int(getattr(enemy, "corrosive_stacks", 0)) + 1
    )
    enemy.corrosive_timer = CORROSIVE_DURATION
    if owner is not None:
        enemy.corrosive_owner = owner


class ShotMark(NamedTuple):
    """Um modificador de tiro que marca o alvo.

    `flag` é o nome da property da NAVE que diz se ele está ativo — lida por
    `getattr` e não por `isinstance` (§5), o que também faz o registro funcionar
    com qualquer dono que exponha a property (nave, wingman, torreta).
    """

    flag: str
    apply: Callable[[Any, Any], None]
    color: Tuple[int, int, int]


# Fonte única. Modificador de tiro que MARCA o alvo entra aqui — e passa a valer
# em todos os caminhos de acerto sem que nenhum deles mude.
SHOT_MARKS: Tuple[ShotMark, ...] = (
    ShotMark("has_cryo_shot", apply_cryo, _CRYO_MARK_COLOR),
    ShotMark("has_corrosive_ammo", apply_corrosion, CORROSIVE_COLOR),
)


def active_marks(owner: Any) -> Tuple[ShotMark, ...]:
    """Marcas ativas neste dono. Tupla vazia se não há dono ou nenhuma ativa.

    Resolvido UMA vez por projétil (e não por inimigo atingido): uma bala
    perfurante que atravessa cinco alvos consulta a nave uma vez só.
    """
    if owner is None:
        return ()
    return tuple(m for m in SHOT_MARKS if getattr(owner, m.flag, False))


def apply_marks(marks: Tuple[ShotMark, ...], enemy: Any, owner: Any = None) -> None:
    """Aplica todas as marcas ao alvo. As marcas se acumulam, não se excluem."""
    for mark in marks:
        mark.apply(enemy, owner)


def apply_all(enemy: Any, owner: Any) -> None:
    """`active_marks` + `apply_marks` num passo, para acerto avulso."""
    apply_marks(active_marks(owner), enemy, owner)


def propagation_color(
    marks: Tuple[ShotMark, ...], default: Tuple[int, int, int]
) -> Tuple[int, int, int]:
    """Cor do efeito que PROPAGA estas marcas (ex.: o raio da cadeia).

    Com mais de uma ativa vence a primeira do registro, em vez de misturar: dois
    verdes-azulados somados dariam um terceiro tom que não é de ninguém, e o
    jogador perderia justamente a informação que a cor existe para dar.
    """
    return marks[0].color if marks else default
