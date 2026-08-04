"""fire_timer.py — Temporizador de cadência independente de frame rate (§14).

Fonte ÚNICA de "quando o próximo disparo sai", para nave, mini-nave, wingman e
qualquer arma futura. Substitui o padrão espalhado pelo projeto:

    timer -= dt
    if timer <= 0:
        atirar()
        timer = intervalo        # <-- descarta a sobra

Esse padrão tem três defeitos, todos medidos neste projeto:

1. **Perda de cadência.** O disparo só acontece em fronteira de frame, então o
   timer não zera exato: ele estoura e fica negativo. Reatribuir o intervalo
   cheio joga essa sobra fora, e o intervalo real vira sempre um número INTEIRO
   de frames. Com 5 tiros/s não aparece (0.200s são frames redondos); com 9.35
   tiros/s o Estilete atirava a 8.5/s — 9% abaixo do configurado.
2. **Ritmo irregular.** Como o erro descartado varia com o `dt`, o intervalo
   alterna entre N e N+1 frames sem padrão, e a rajada parece engasgar.
3. **Teto de um disparo por passo.** Se o intervalo for menor que o `dt`, os
   disparos excedentes somem em vez de serem emitidos no mesmo passo.

`FireTimer` resolve os três acumulando tempo em vez de descontá-lo, e expondo o
`overshoot` — há quanto tempo o disparo já deveria ter saído — para que quem
dispara possa compensar a posição inicial do projétil (ver `overshoot`).

Uso típico::

    timer.advance(dt, interval)
    while timer.consume(interval):
        bullet = spawn(...)
        bullet.x += bullet.vx * timer.overshoot   # compensação sub-frame
        bullet.y += bullet.vy * timer.overshoot

O `while` (em vez de `if`) é o que evita perder disparos em queda de FPS: um
passo longo emite todos os tiros que couberem nele, cada um com o seu próprio
`overshoot`, então eles nascem espaçados corretamente em vez de empilhados.

O intervalo é parâmetro de CADA chamada, não estado interno: assim buffs,
debuffs e modificadores temporários de cadência entram em vigor no mesmo frame,
sem precisar reconfigurar nada — quem chama já calcula o intervalo efetivo.

Não depende de pygame nem de nada do jogo: é testável isoladamente.
"""

from __future__ import annotations


def carry_interval(remaining: float, interval: float) -> float:
    """Reagenda um evento periódico simples PRESERVANDO a sobra do frame.

    Forma enxuta do que `FireTimer` faz, para quem só precisa de um contador
    regressivo: em vez de `timer = INTERVALO` (que descarta o quanto o timer
    passou de zero e faz o evento render menos que o configurado), some o
    intervalo ao que sobrou. A dívida é limitada a um intervalo, então uma
    entidade que ficou muito tempo sem atualizar não dispara uma rajada.

    Use isto em eventos periódicos de entidade (rajada de inimigo, pulso de
    área); use `FireTimer` em armas, onde também importam `is_ready`, disparo
    inicial imediato, múltiplas emissões por passo e compensação sub-frame.
    """
    if interval <= 0.0:
        return 0.0
    return max(remaining, -interval) + interval


def emission_offset(
    proj_vx: float,
    proj_vy: float,
    emitter_vx: float,
    emitter_vy: float,
    overshoot: float,
) -> tuple[float, float]:
    """Deslocamento inicial de um projétil emitido com `overshoot` de atraso.

    A compensação sub-frame precisa acontecer no referencial da BOCA, não no do
    mundo. O disparo era devido há `overshoot` segundos; nesse instante o
    projétil ainda não existia (deve à frente o que andaria) e o emissor estava
    atrás de onde está agora. Compensar só o primeiro corrige o eixo de voo e
    deixa o eixo do movimento do emissor quantizado por frame — que é o defeito
    original, apenas girado 90°.

    Por isso a fórmula usa a velocidade RELATIVA: com o emissor parado ela
    degenera em `v_projétil × overshoot` (o comportamento antigo), e com o
    emissor em movimento ela corrige os dois eixos de uma vez. Um conceito só,
    não duas correções.

    Medido no Estilete (a nave onde os três fatores se somam: maior cadência,
    projétil mais lento e maior velocidade de nave), com strafe lateral:
    espaçamento alternando 4,2% a 60fps e 8,4% a 30fps, contra 0,00px de
    variação em qualquer frame rate com a velocidade relativa.

    Floats puros de propósito: sem pygame e sem tipos do jogo, para que nave,
    Berserk, Wingman, MiniShip e armas futuras compartilhem a mesma matemática
    sem depender do `ShootingSystem` (§1) e para o teste rodar sem instanciar
    nada (§16).
    """
    if overshoot <= 0.0:
        return (0.0, 0.0)
    return (
        (proj_vx - emitter_vx) * overshoot,
        (proj_vy - emitter_vy) * overshoot,
    )


class FireTimer:
    """Acumulador de tempo de disparo. Veja o módulo para o racional."""

    __slots__ = ("_available", "_overshoot", "_primed")

    def __init__(self, ready: bool = True) -> None:
        # Crédito de tempo disponível, em segundos.
        self._available: float = 0.0
        self._overshoot: float = 0.0
        # "Pronto para o primeiro disparo", independente de crédito acumulado.
        # É um flag e não um crédito grande de propósito: o primeiro tiro não
        # está atrasado, então precisa sair com `overshoot` zero — um crédito
        # inicial o deslocaria para frente da nave sem motivo.
        self._primed: bool = ready

    @property
    def overshoot(self) -> float:
        """Há quantos segundos o último `consume` bem-sucedido já era devido.

        Sempre >= 0. É o resto que não coube em um intervalo inteiro — o mesmo
        valor que segue creditado para o próximo disparo, então compensar a
        posição do projétil com ele não adianta nem atrasa a cadência.
        """
        return self._overshoot

    def advance(self, dt: float, interval: float) -> None:
        """Credita `dt` de tempo, limitando o crédito ocioso a um disparo.

        O teto é relativo ao INTERVALO da arma, não a um número fixo de frames:
        uma arma lenta e uma rápida guardam, cada uma, no máximo um disparo de
        crédito. Sem esse teto, uma nave parada por 10s despejaria uma rajada ao
        voltar a atirar; com um teto absoluto (em frames), a compensação
        sub-frame quebraria silenciosamente em qualquer frame rate onde o `dt`
        passasse do teto.

        O `dt` do passo atual entra SEMPRE inteiro, mesmo que estoure o teto:
        é o que permite a um passo longo emitir mais de um disparo.
        """
        if dt <= 0.0:
            return
        cap = interval if interval > 0.0 else 0.0
        if self._available > cap:
            self._available = cap
        self._available += dt

    def is_ready(self, interval: float) -> bool:
        """True se há crédito para disparar agora (não consome)."""
        return self._primed or interval <= 0.0 or self._available >= interval

    def consume(self, interval: float) -> bool:
        """Tenta gastar um intervalo. Em caso positivo, atualiza `overshoot`.

        Chamar em `while` para emitir todos os disparos que couberem no passo.
        """
        if self._primed:
            self._primed = False
            self._available = 0.0
            self._overshoot = 0.0
            return True
        if interval <= 0.0:
            self._overshoot = 0.0
            return False
        if self._available < interval:
            self._overshoot = 0.0
            return False
        self._available -= interval
        # O que sobrou é exatamente há quanto tempo este disparo era devido —
        # e segue como crédito do próximo, então nada é criado nem perdido.
        self._overshoot = self._available
        return True

    def drain(self) -> None:
        """Zera o crédito sem disparar.

        Para disparos FORA da cadência (charge shot solto pelo jogador): o tiro
        já saiu, então a arma recomeça a contar do zero em vez de guardar um
        crédito que viraria um tiro extra imediato.
        """
        self._available = 0.0
        self._overshoot = 0.0
        self._primed = False

    def reset(self, ready: bool = True) -> None:
        """Volta ao estado inicial (troca de fase, respawn)."""
        self._available = 0.0
        self._overshoot = 0.0
        self._primed = ready
