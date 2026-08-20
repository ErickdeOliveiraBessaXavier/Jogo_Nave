"""Flags de desenvolvimento não podem viajar ligadas.

Uma flag de dev ligada não quebra nada em teste unitário — ela quebra o JOGO,
em silêncio, para quem clonar o repositório. Por isso a cobrança é aqui, com
mensagem dizendo o que fazer, e não espalhada por nove asserts numéricos que
falam de `40 >= 80` sem mencionar flag nenhuma.

Foi exatamente assim que passou despercebido: a arena de teste foi commitada
ligada junto com o esqueleto da Tríade, e o sintoma no CI eram números de
balanceamento — que é o último lugar onde alguém procuraria uma flag.
"""

from __future__ import annotations

from game.core.levels import fixed_levels


def test_arena_de_teste_desligada():
    """`TEST_ARENA_ENABLED` ligada troca a campanha inteira pela arena do tema.

    O nível 1 de todo mundo vira "[TESTE] Arena <tema>", com a contagem de
    inimigos e o chefe escritos à mão no bloco de arena — a campanha de verdade
    não roda. É útil no desenvolvimento e inaceitável no repositório.
    """
    assert not fixed_levels.TEST_ARENA_ENABLED, (
        "TEST_ARENA_ENABLED está True em game/core/levels/fixed_levels.py: "
        "a campanha inteira foi substituída pela arena de teste do tema. "
        "Desligue (False) antes de commitar. Enquanto estiver ligada, os testes "
        "de pipeline ficam SKIPPED de propósito — não são eles que estão errados."
    )
