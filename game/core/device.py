"""Detecção de dispositivo de TOQUE, para separar "web" de "celular".

O build web é o mesmo binário nos dois casos, mas o jogador não é o mesmo: num
celular o toque é o único jeito de mover a nave e de alcançar o HUD; num
navegador de PC existem teclado e mouse, e os controles de tela viram estorvo —
ocupam área útil e sugerem uma interface que não é a daquele aparelho.

**Por que não `sys.platform == "emscripten"`.** Isso responde "estou no
navegador", não "estou no celular". Era a premissa antiga (`touch_mode` e
`virtual_joystick` nasciam ligados em todo web) e ela erra no caso mais comum de
todos: alguém abrindo o link no desktop.

**Por que `(pointer: coarse)` e não `maxTouchPoints`.** A media query pergunta
como é o ponteiro PRIMÁRIO do aparelho. Notebook com tela sensível ao toque
responde `fine` (o primário é o trackpad) e continua sendo tratado como desktop
— que é o certo. Já `maxTouchPoints > 0` seria verdadeiro nele e ligaria os
controles de tela em quem tem mouse.

**Por que não `navigator.userAgentData.mobile`.** Só existe em navegadores
Chromium; no Firefox e no Safari é `undefined`, e o `window.mobile()` que o
pygbag expõe devolve `0` nesse caso — ou seja, diria "desktop" num celular
Firefox. A media query é suportada em todos eles.

Segue a convenção de `orientation.py`: `try/except` largo, porque `platform` é
uma superfície de API que não controlamos e que muda entre versões do pygbag.
Falhar aqui tem de virar "não sei", nunca uma exceção no boot.
"""

from __future__ import annotations

import sys


def is_touch_primary() -> bool:
    """O aparelho tem o DEDO como ponteiro primário (celular/tablet)?

    Fora do navegador é sempre ``False`` — o desktop nativo não tem toque como
    entrada primária. Em caso de dúvida também devolve ``False``: é o padrão
    seguro, porque um desktop que ganhasse controles de toque por engano fica
    com a tela poluída, enquanto um celular sem eles ainda tem a tela de
    Configurações para ligá-los.
    """
    if sys.platform != "emscripten":
        return False

    try:
        import platform as _pyplatform

        window = getattr(_pyplatform, "window", None)
        if window is None:
            return False
        return bool(window.matchMedia("(pointer: coarse)").matches)
    except Exception:
        return False
