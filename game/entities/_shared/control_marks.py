"""Marcas de controle que sistemas externos cravam NA entidade.

EMP, gelo, vórtice e Implosão não escrevem na velocidade do inimigo: cada um
crava um TIMER na entidade e o `EntityManager` traduz os timers em multiplicador
de `dt` no tick. É o que faz os quatro se comporem por multiplicação em vez de
disputarem o mesmo campo.

O contrato tem uma ponta solta: **o timer só anda enquanto a entidade está viva
no loop de update**. Entidade de POOL que volta ao pool marcada congela o timer
no valor que sobrou, e o próximo spawn nasce com ele.

Foi exatamente o bug da Implosão: a zona fechava, o upgrade entrava em cooldown,
e meteoros reciclados continuavam nascendo a 25% da velocidade — sem nenhum
círculo na tela para explicar. Por isso todo `reset()` de entidade poolada
limpa as marcas: o objeto é reaproveitado, o estado dele não.
"""

from __future__ import annotations

from typing import Any

# Fonte única. Marca de controle nova entra AQUI — senão volta a vazar pelo pool
# e o sintoma (inimigo lento sem causa visível) só aparece minutos depois.
CONTROL_MARKS: tuple[str, ...] = (
    "implosion_slow_timer",
    "implosion_damage_cd",
    "_ice_slow_timer",
    "vortex_slow_timer",
    "emp_linger_timer",
)


def clear_control_marks(entity: Any) -> None:
    """Zera em `entity` as marcas de controle que ela já tiver.

    `hasattr` antes de escrever, pelos dois lados: quem nunca foi marcado não
    ganha o campo à toa (todos os leitores usam `getattr(..., 0.0)`), e entidade
    com `__slots__` que não declarou o campo não estoura — mesmo opt-in de
    `implosion_pulse.accepts_control`.
    """
    for mark in CONTROL_MARKS:
        if hasattr(entity, mark):
            setattr(entity, mark, 0.0)
