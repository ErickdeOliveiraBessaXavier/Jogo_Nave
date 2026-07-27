"""Piscada com aceleração no fim — feedback de "isto está acabando".

Um efeito temporário que pisca em frequência fixa não diz ao jogador QUANDO vai
acabar; ele precisa olhar a HUD. Acelerando a piscada perto do fim, a urgência
fica no próprio objeto que está piscando.

**Por que integrar a frequência em vez de só variá-la.** O reflexo é escrever
`int(tempo * hz) % 2` com um `hz` que cresce. Não funciona: mudar `hz` muda o
resultado de `tempo * hz` de forma descontínua, então a fase SALTA a cada
frame — a piscada engasga, chega a "voltar atrás", e não se lê como aceleração.
O que precisa ser contínuo é a **fase** (quantas trocas já aconteceram), que é
a integral da frequência no tempo. Aqui essa integral tem forma fechada, então
sai direto do tempo restante, sem acumulador.

Sem acumulador é o ponto: `visible()` é **pura**, função só do tempo restante.
Dá para chamar de dentro de um `draw()` sem violar o §3 (draw não muta estado),
e dois objetos com o mesmo tempo restante piscam em sincronia de graça.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlinkProfile:
    """Parâmetros de uma piscada que acelera no fim.

    ``slow_hz``/``fast_hz`` são ciclos por segundo (um ciclo = apareceu +
    sumiu) no começo e no instante final.

    A rampa — quanto antes do fim a aceleração começa — é
    ``min(ramp_seconds, total * ramp_fraction)``. Os dois limites existem
    porque efeitos curtos e longos precisam de coisas diferentes: a fração
    garante que um efeito de 1s (invuln de escudo) tenha uma rampa
    proporcional em vez de acelerar do início ao fim, e o teto em segundos
    evita que um efeito de 30s passe meio minuto acelerando.
    """

    slow_hz: float = 2.5
    fast_hz: float = 10.0
    ramp_seconds: float = 4.0
    ramp_fraction: float = 0.55

    def ramp_for(self, total: float) -> float:
        """Duração da janela final acelerada, para um efeito de `total`s."""
        if total <= 0.0:
            return 0.0
        return min(self.ramp_seconds, total * self.ramp_fraction)

    def frequency_at(self, remaining: float, total: float) -> float:
        """Frequência instantânea (Hz) com `remaining`s de efeito pela frente.

        Exposta para diagnóstico e para quem quiser casar outro efeito (som,
        partícula) com a mesma curva.
        """
        ramp = self.ramp_for(total)
        if remaining >= ramp or ramp <= 0.0:
            return self.slow_hz
        # Linear na janela final: fast no instante 0, slow na entrada da rampa.
        t = max(0.0, remaining) / ramp
        return self.fast_hz + (self.slow_hz - self.fast_hz) * t

    def _raw_phase(self, remaining: float, total: float) -> float:
        """Trocas de estado acumuladas entre o fim do efeito e `remaining`.

        Integral da frequência, contada de trás para frente (do fim para o
        agora) — é o que torna a função pura. Dois "toggles" por ciclo: um para
        sumir, outro para reaparecer.
        """
        ramp = self.ramp_for(total)
        slow = 2.0 * self.slow_hz
        fast = 2.0 * self.fast_hz

        if ramp <= 0.0:
            return slow * remaining

        if remaining <= ramp:
            # ∫₀^u [fast + (slow-fast)·(r/ramp)] dr
            return fast * remaining + (slow - fast) * remaining**2 / (2.0 * ramp)

        # Rampa inteira (a média das pontas, por ser linear) + o trecho lento.
        return ramp * (fast + slow) / 2.0 + slow * (remaining - ramp)

    def _phase_target(self, total: float) -> float:
        """Ajuste fino para o efeito começar E terminar com o objeto visível.

        A fase é contada do fim para trás, então o fim sempre cai limpo em 0
        (visível). O COMEÇO, não: ele cai onde a integral der, quase sempre no
        meio de um intervalo — a nave aparecia apagada no frame do dano e a
        primeira piscada saía picotada.

        Esticar a fase para um número ÍMPAR de trocas resolve os dois lados de
        uma vez: com N ímpar os intervalos alternam começando e terminando em
        "visível". O custo é a frequência mudar alguns por cento (27,4 → 27
        trocas numa invuln de 3s), o que ninguém enxerga — bem menos do que a
        piscada torta que isso remove.
        """
        raw = self._raw_phase(total, total)
        if raw <= 1.0:
            return 1.0
        nearest_odd = round((raw - 1.0) / 2.0) * 2.0 + 1.0
        return max(1.0, nearest_odd)

    def _phase(self, remaining: float, total: float) -> float:
        raw_total = self._raw_phase(total, total)
        if raw_total <= 0.0:
            return 0.0
        target = self._phase_target(total)
        phase = self._raw_phase(remaining, total) * (target / raw_total)
        # No primeiro frame `remaining == total`, e a fase cai EXATAMENTE sobre
        # o ímpar `target` — `int()` de um ímpar exato dá "apagado", um frame
        # solto antes da primeira piscada. Segurar logo abaixo do inteiro põe
        # esse frame dentro do primeiro intervalo visível, onde ele pertence.
        return min(phase, target - 1e-9)

    def visible(self, remaining: float, total: float) -> bool:
        """A coisa que pisca deve ser desenhada NESTE frame?

        `remaining <= 0` devolve True: acabou o efeito, estado normal na hora,
        sem piscada residual. A fase vale 0 exatamente no fim e um ímpar exato
        no começo, então as duas pontas terminam visíveis, sem salto.
        """
        if remaining <= 0.0 or total <= 0.0:
            return True
        return int(self._phase(min(remaining, total), total)) % 2 == 0


# Perfil dos i-frames da nave. Começa devagar (dá para ver a nave), termina
# rápido o bastante para ler como "acabando" sem virar estroboscópio: 10Hz a
# 60fps é uma troca a cada 3 frames, o limite antes de o olho perder a contagem.
SHIP_INVULN_BLINK = BlinkProfile(
    slow_hz=2.5,
    fast_hz=10.0,
    ramp_seconds=4.0,
    ramp_fraction=0.55,
)
