"""Quem conta como ALVO PESADO para regras de dano de upgrade.

Existe uma classe de inimigos que quebra o balanceamento de qualquer upgrade
que dispare vários projéteis de uma vez: o corpo é largo o bastante para comer
o leque INTEIRO. Contra um meteoro só um projétil conecta; contra um CyberTank
conectam os três, e o dano por disparo triplica sem que nada no upgrade tenha
mudado. É um efeito de geometria, não de poder — e é por isso que os upgrades
com essa forma (Wingman, Estrela Espiral, Cryo Shot) carregam uma redução que
incide **só aqui**, em vez de perderem dano contra o elenco todo.

**Duas camadas, e elas não são a mesma coisa.** O `is_boss` já existia e é o que
o `BOSS_UPGRADE_DAMAGE_MULTIPLIER` global consulta — mas ele cobre só os chefes
de fase. Os "gatekeepers" que o gerador de níveis spawna sozinhos, com cap 1 e
centenas de pontos de vida, são inimigos comuns para o roteador de colisão e
não recebiam redução nenhuma. `is_miniboss` fecha esse buraco.

**Por atributo formal, nunca por nome de classe** (§5): quem é pesado declara
`is_miniboss = True` no próprio corpo, do lado de quem sabe o quanto aguenta. O
default vive no `EnemyHitMixin`, então o elenco comum não precisa dizer nada.

**O critério é LARGURA DE HITBOX × durabilidade — as duas.** O cap 1 do spawner
("sempre sozinho") é um bom primeiro filtro, e é onde os gatekeepers estão
registrados, mas sozinho ele erra nos dois sentidos:

- **Largo mas frágil não basta**, e nem **durável mas estreito**. O que quebra o
  balanceamento é o produto: um corpo que os três cristais acertam E que vive o
  bastante para a multiplicação virar tempo de luta.
- O `SquareMinionBoss` é miniboss no gerador e morre em um tiro (`health = 1`):
  reduzir dano contra ele não protege nada.
- O `IceGolem` tem 220 HP e cap 1, mas o alvo dele é a gema de **42px**,
  "pequeno de propósito: é o ponto fraco focado". Um alvo desse tamanho não come
  o trio — o Cryo já acerta ali com um cristal, como em qualquer inimigo comum,
  e é justamente essa mira que a luta cobra. Fica de fora.
- O `MountainMage` tem cap 1 por ritmo (é `support`), não por porte: 24 HP.
"""

from __future__ import annotations

from typing import Any


def is_heavy_target(entity: Any) -> bool:
    """O alvo é boss ou miniboss (e portanto largo o bastante para o leque)?

    `getattr` com default nos dois: entidades que nunca ouviram falar de
    nenhuma das duas flags — destroços, peças coreografadas com `__slots__`,
    stubs de teste — respondem False sem estourar.
    """
    return bool(
        getattr(entity, "is_boss", False) or getattr(entity, "is_miniboss", False)
    )
