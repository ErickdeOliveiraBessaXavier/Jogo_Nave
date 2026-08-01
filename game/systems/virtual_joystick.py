"""Joystick virtual do modo celular: direcional analógico desenhado na tela.

**Por que ele existe, se `mouse_control` já move a nave.** No `mouse_control` o
ponteiro É a posição de destino: a nave persegue o dedo. Isso funciona no mouse,
onde o cursor é um pixel, mas no celular o dedo cobre justamente a nave que você
precisa ver — foi o que motivou o `touch_offset`, que é um remendo (afasta a nave
do dedo em 90px e torce para bastar). Com joystick o problema some pela raiz: o
polegar fica ancorado num canto e a nave voa livre, sem nada em cima dela.

**Posse de dedo.** Cada gesto é identificado por um `finger`: o `finger_id` do
SDL quando há eventos de toque, ou `None` no caminho de mouse. O direcional
ADOTA o dedo que o acionou e ignora todos os outros — é isso que libera o
segundo polegar para os botões do HUD enquanto o primeiro pilota.

A primeira versão era de um ponteiro só, porque o toque parecia chegar apenas
como mouse sintetizado. A sonda no aparelho mostrou dois dedos simultâneos: o
multi-toque existia, e quem não o lia era a nossa entrada. O caminho de mouse
continua aqui e funcional (`finger=None`), como reserva para quando eventos de
dedo não existirem.

**O vetor é o mesmo contrato do gamepad.** `vector()` devolve um par no disco
unitário, exatamente o que `ShipMovement` já consome como `gamepad_vec`: ele
aplica magnitude proporcional, normaliza acima de 1, trata a inversão da Toxina e
soma os multiplicadores de velocidade. Nenhuma matemática de movimento nova.
"""

from __future__ import annotations

import math


class VirtualJoystick:
    """Estado do direcional. Sem pygame e sem render — só geometria."""

    # Fração do raio abaixo da qual o toque é considerado centro. Sem ela, o
    # tremor natural do polegar parado vira deriva lenta da nave.
    DEAD_ZONE: float = 0.14

    def __init__(self) -> None:
        self.active: bool = False
        # Dono do gesto em curso. `None` = caminho de mouse (um ponteiro).
        self._finger: object = None
        # Centro efetivo do direcional NESTE gesto. Em geral é o centro do HUD,
        # mas ver `press`: um toque na borda da zona recentra parcialmente.
        self._origin: tuple[float, float] = (0.0, 0.0)
        self._pos: tuple[float, float] = (0.0, 0.0)
        self._radius: float = 1.0

    def owns(self, finger: object) -> bool:
        """Este gesto pertence ao dedo que segura o direcional?

        Sem esta pergunta, o `FINGERMOTION` de QUALQUER dedo moveria o
        direcional — tocar num upgrade com o outro polegar arrastaria a nave
        junto, que é o oposto do que o multi-toque veio resolver.
        """
        return self.active and self._finger == finger

    def press(
        self,
        pos: tuple[float, float],
        center: tuple[float, float],
        radius: float,
        finger: object = None,
    ) -> bool:
        """Tenta capturar este toque. True se ele caiu na zona do direcional.

        A zona é MAIOR que o desenho (`ACTIVATION_SCALE` no layout): errar o
        direcional por alguns pixels e a nave não responder é a falha mais
        irritante possível num controle de toque, e ela acontece o tempo todo com
        alvo do tamanho exato do desenho.
        """
        dx = pos[0] - center[0]
        dy = pos[1] - center[1]
        if math.hypot(dx, dy) > radius:
            return False
        self.active = True
        self._finger = finger
        self._origin = center
        self._pos = (float(pos[0]), float(pos[1]))
        self._radius = max(1.0, radius)
        return True

    def drag(self, pos: tuple[float, float], finger: object = None) -> None:
        """Move o polegar. Fora do raio o valor satura — não desancora.

        Deixar o direcional seguir o dedo para fora seria mais "natural" no
        papel, mas na prática o jogador perde a referência de onde o centro
        ficou e passa a corrigir contra um centro invisível.
        """
        if self.owns(finger):
            self._pos = (float(pos[0]), float(pos[1]))

    def release(self, finger: object = None) -> None:
        """Solta: a nave PARA. É a diferença de sensação para o `mouse_control`,
        onde soltar deixa a nave seguindo rumo ao último ponto tocado.

        Só o DONO solta: levantar o polegar que estava num botão não pode
        derrubar o direcional que o outro ainda segura.
        """
        if self.owns(finger):
            self.active = False
            self._finger = None

    def offset(self) -> tuple[float, float]:
        """Deslocamento do knob em pixels, já preso ao raio (para o HUD)."""
        if not self.active:
            return (0.0, 0.0)
        dx = self._pos[0] - self._origin[0]
        dy = self._pos[1] - self._origin[1]
        dist = math.hypot(dx, dy)
        if dist <= self._radius or dist == 0.0:
            return (dx, dy)
        escala = self._radius / dist
        return (dx * escala, dy * escala)

    def vector(self) -> tuple[float, float]:
        """Direção no disco unitário — o `gamepad_vec` que a nave consome."""
        if not self.active:
            return (0.0, 0.0)
        dx, dy = self.offset()
        mag = math.hypot(dx, dy) / self._radius
        if mag <= self.DEAD_ZONE:
            return (0.0, 0.0)
        # Reescala para que o vetor saia de ZERO na borda da zona morta, em vez
        # de saltar para `DEAD_ZONE` assim que ela é cruzada. Sem isto a nave
        # arranca com 14% de velocidade em vez de partir do repouso.
        util = (mag - self.DEAD_ZONE) / (1.0 - self.DEAD_ZONE)
        dist = math.hypot(dx, dy)
        if dist == 0.0:
            return (0.0, 0.0)
        return (dx / dist * util, dy / dist * util)
