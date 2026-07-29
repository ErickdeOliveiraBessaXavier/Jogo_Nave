"""Marcas de controle que sistemas externos cravam NA entidade.

EMP, gelo, vórtice, Implosão e Cryo não escrevem na velocidade do inimigo: cada
um crava um TIMER na entidade e o `EntityManager` traduz os timers em
multiplicador de `dt` no tick. É o que faz todos se comporem por multiplicação
em vez de disputarem o mesmo campo.

O contrato tem duas pontas soltas, e as duas já cobraram caro:

**1. O timer só anda enquanto a entidade está viva no loop de update.** Entidade
de POOL que volta ao pool marcada congela o timer no valor que sobrou, e o
próximo spawn nasce com ele. Foi o bug da Implosão: a zona fechava, o upgrade
entrava em cooldown, e meteoros reciclados continuavam nascendo a 25% da
velocidade — sem nenhum círculo na tela para explicar. Por isso todo `reset()`
de entidade poolada limpa as marcas: o objeto é reaproveitado, o estado dele não.

**2. Nem toda entidade aceita atributo novo.** Peça coreografada de boss com
`__slots__` estourava `AttributeError` no meio do combate. Daí o `accepts_control`.
"""

from __future__ import annotations

from typing import Any

# Fonte única. Marca de controle nova entra AQUI — senão volta a vazar pelo pool
# e o sintoma (inimigo lento sem causa visível) só aparece minutos depois.
CONTROL_MARKS: tuple[str, ...] = (
    "implosion_slow_timer",
    "implosion_damage_cd",
    "cryo_slow_timer",
    "cryo_stacks",
    "cryo_owner",
    "corrosive_timer",
    "corrosive_stacks",
    "corrosive_damage_cd",
    "corrosive_owner",
    "_ice_slow_timer",
    "vortex_slow_timer",
    "emp_linger_timer",
)


def clear_control_marks(entity: Any) -> None:
    """Zera em `entity` as marcas de controle que ela já tiver.

    `hasattr` antes de escrever, pelos dois lados: quem nunca foi marcado não
    ganha o campo à toa (todos os leitores usam `getattr(..., 0.0)`), e entidade
    com `__slots__` que não declarou o campo não estoura — mesmo opt-in de
    `accepts_control`.
    """
    for mark in CONTROL_MARKS:
        if hasattr(entity, mark):
            setattr(entity, mark, 0.0)


def accepts_control(enemy: Any) -> bool:
    """A entidade pode RECEBER as marcas (é possível escrever nela)?

    Inimigo comum tem `__dict__` e aceita as marcas na hora. Entidades com
    `__slots__` — peças coreografadas de boss (`SerpentBlock`), destroços,
    tanques — só aceitam os campos que declararam, e escrever nelas estoura
    `AttributeError`. Uma delas derrubou o jogo em combate.

    Quem quiser participar declara o slot, como já fazem com `emp_linger_timer`:
    o opt-in fica explícito na entidade, do lado de quem sabe se ela aguenta.
    """
    return hasattr(enemy, "__dict__") or hasattr(enemy, "implosion_slow_timer")


def can_be_controlled(enemy: Any) -> bool:
    """A entidade DEVE receber efeito de controle (lentidão, freio, DoT de zona)?

    Guard único dos efeitos de controle do jogador — antes existia copiado em
    cada um, e a cópia é onde as regras divergem em silêncio.

    - **morto**: nada a fazer;
    - **boss**: fica de fora. Um boss lento a cada acerto é buff de dano
      disfarçado de utilitário. Pelo atributo formal `is_boss`, nunca por nome
      de classe (§5);
    - **`position_locked`**: estruturas ancoradas (estalagmite, estalactite) têm
      tempo próprio no ciclo RISE→LINGER→SHATTER — freá-las faz a AMEAÇA durar
      mais, ou seja, o "controle" piora a situação do jogador;
    - **`accepts_control`**: ver acima.
    """
    if getattr(enemy, "dead", False):
        return False
    if getattr(enemy, "is_boss", False):
        return False
    if getattr(enemy, "position_locked", False):
        return False
    return accepts_control(enemy)


def _accepts_damage_mark(enemy: Any) -> bool:
    """Base dos efeitos que marcam para DANO (e não para freio): boss incluído.

    Igual ao `can_be_controlled` **menos o opt-out de boss**, e é essa a única
    diferença que existe entre os dois. Os call sites usam os nomes específicos
    abaixo, não este: quem lê `accepts_cryo(x)` vê qual regra está em jogo, o
    que um parâmetro booleano esconderia.

    `position_locked` continua de fora: estrutura ancorada tem ciclo próprio
    (RISE→LINGER→SHATTER) e não sobrevive à janela do efeito de forma previsível.
    """
    if getattr(enemy, "dead", False):
        return False
    if getattr(enemy, "position_locked", False):
        return False
    return accepts_control(enemy)


def accepts_cryo(enemy: Any) -> bool:
    """A entidade pode acumular a ESCADA do Cryo Shot?

    Boss e miniboss **cristalizam mas não congelam**: acumulam as cargas, ganham
    os cristais e detonam a bomba de gelo no fim, mas nunca são freados. Quem
    garante a segunda metade é `EntityManager._cryo_multiplier`, que devolve 1.0
    para `is_boss` — a lentidão é o que dessincroniza padrão roteirizado e peça
    coreografada, não a marca em si. Assim o upgrade continua entregando dano
    contra chefe sem tocar na IA nem no ritmo da luta.
    """
    return _accepts_damage_mark(enemy)


def accepts_corrosion(enemy: Any) -> bool:
    """A entidade pode acumular a PILHA do Corrosive Ammo?

    Boss incluído, e aqui isso não é um detalhe: o Corrosive é alvo único e
    cumulativo justamente para ser bom contra quem tem muita vida e fica muito
    tempo na tela. Excluir chefe apagaria o upgrade inteiro.

    O ácido não freia ninguém — é dano ao longo do tempo —, então não existe o
    risco de dessincronizar padrão roteirizado que motiva o opt-out de boss em
    `can_be_controlled`. O que o chefe recebe a menos é o `BOSS_UPGRADE_DAMAGE_
    MULTIPLIER` global, aplicado no tique (ver `Collisions.corrosion_vs_enemies`).
    """
    return _accepts_damage_mark(enemy)
