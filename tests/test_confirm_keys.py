"""Enter principal e Enter do numérico acionam a MESMA coisa, em toda tela.

O SDL entrega o Enter do teclado numérico como `K_KP_ENTER`, uma tecla
diferente do `K_RETURN`. Quem lista só o `K_RETURN` simplesmente não responde a
ele: o jogador aperta e nada acontece, sem erro nem pista. Era o caso de dez das
onze telas do jogo — só a de seleção de idioma acertava.

A correção não foi acrescentar a tecla em cada lugar (é o que já tinha
divergido), e sim uma constante única (`ui_helpers.CONFIRM_KEYS`). O teste abaixo
é o que impede a divergência de voltar: varre o código-fonte atrás de quem
compara `event.key` com `K_RETURN` sem passar pela constante.
"""

import pathlib
import re

import pygame

from game.scenes.ui_helpers import CONFIRM_KEYS

CENAS = pathlib.Path("game/scenes")


def test_a_constante_cobre_os_dois_enter_e_o_espaco():
    assert pygame.K_RETURN in CONFIRM_KEYS
    assert pygame.K_KP_ENTER in CONFIRM_KEYS
    assert pygame.K_SPACE in CONFIRM_KEYS


def test_os_dois_enter_sao_teclas_diferentes():
    """Se fossem a mesma, nada disto precisaria existir."""
    assert pygame.K_RETURN != pygame.K_KP_ENTER


def test_nenhuma_cena_compara_com_K_RETURN_por_fora():
    """`K_RETURN` solto num `event.key` é o padrão que deixa o numérico de fora.

    Linhas de COMENTÁRIO não contam: várias explicam o `K_RETURN` sintético que
    o app dispara para o A do controle, e citar o nome não é tratá-lo.
    """
    padrao = re.compile(r"event\.key\s*(==|in)\s*[^\n]*K_RETURN")
    culpados: list[str] = []
    for arquivo in sorted(CENAS.glob("*.py")):
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if linha.lstrip().startswith("#"):
                continue
            if padrao.search(linha):
                culpados.append(f"{arquivo.name}:{n}: {linha.strip()}")
    assert culpados == [], (
        "compare com `CONFIRM_KEYS` (ui_helpers) em vez de `K_RETURN` solto:\n"
        + "\n".join(culpados)
    )


def test_toda_cena_que_confirma_usa_a_constante():
    """Contrapartida do teste acima: garante que ele não passa por vacuidade.

    Se alguém trocar tudo por outra coisa e o padrão proibido sumir, este pega —
    tem de haver telas de fato consumindo a constante.
    """
    usam = [
        a.name
        for a in sorted(CENAS.glob("*.py"))
        if "CONFIRM_KEYS" in a.read_text(encoding="utf-8")
    ]
    assert len(usam) >= 8, f"esperava a constante em várias telas, achei {usam}"
