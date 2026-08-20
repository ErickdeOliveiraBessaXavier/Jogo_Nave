"""Cabeça que MIRA e dispara um feixe — o executor da Sentença.

A Sentença é uma sequência de sobrevivência com muitas fontes de tiro, não com
duas. Este módulo é a fonte: uma aparição de cabeça que materializa numa posição
qualquer da arena, se orienta para a direção do feixe, dispara e se dissolve.

Duas encarnações, uma classe só:

  * **Eco** (`head=None`) — aparição temporária. Nasce, dispara, some. É o que
    permite a coreografia ter oito cabeças na tela sem o boss ter oito Vozes.
  * **Voz** (`head=<TriadHead>`) — não desenha nada por conta própria: a pose
    calculada aqui é copiada pelo boss para a cabeça real, que é quem se desenha.
    A coreografia trata as duas do mesmo jeito, então o roteiro não precisa saber
    quem é quem (§5). **Hoje ninguém constrói esta forma**: as Vozes reais
    dissolvem no corpo durante a Sentença inteira (`TriadBoss._VOICE_FADE`) e a
    marcação `Shot.voice` escolhe só o ROSTO do eco. O caminho fica porque é ele
    que permitiria a uma cabeça de verdade voltar a atuar sem tocar no roteiro.

**O rosto olha para o feixe.** A mira não é decoração: `aimed_part` gira o sprite
e `muzzle()` devolve a BOCA já girada, que é a origem que o feixe lê todo frame.
Quando o caster desliza ou gira, o feixe acompanha — a cabeça leva o feixe em vez
de os dois viverem em relógios separados, que era o defeito da versão anterior
(o feixe varria a arena enquanto a cabeça ficava parada noutra altura).

**Nada aparece pronto.** O eco sobe de alpha durante a CARGA — o mesmo intervalo
em que o feixe é visível e inofensivo — e afunda depois de disparar. Aparecer no
frame do disparo transformaria o telégrafo em emboscada.
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Tuple

import pygame

from . import triad_pixel_map as pmap

_RISE = "rise"
_FIRE = "fire"
_SINK = "sink"

Ponto = Tuple[float, float]


class TriadCaster:
    """Uma cabeça disparando um feixe: materializa, mira, atira, dissolve."""

    # Igual ao `TriadBeam.FADE_TIME` de propósito: a cabeça se dissolve no mesmo
    # ritmo em que o feixe dela se dissipa. Se a cabeça sumisse antes, sobraria
    # um feixe pendurado no nada — exatamente o defeito que esta reescrita veio
    # corrigir. Amarrado por `test_a_cabeca_se_dissolve_junto_com_o_feixe`.
    SINK_TIME: float = 0.45

    def __init__(
        self,
        part: str,
        x: float,
        y: float,
        aim: float,
        charge: float,
        lethal: float,
        *,
        path: Optional[Callable[[float], Ponto]] = None,
        swing: Optional[Callable[[float], float]] = None,
        head: object | None = None,
    ) -> None:
        self.part = part
        self.x = float(x)
        self.y = float(y)
        self.aim = float(aim)
        self._charge = max(0.01, charge)
        self._lethal = max(0.01, lethal)
        # O percurso é medido sobre a vida INTEIRA (carga + janela letal), não
        # sobre a janela letal. Ver `_apply`.
        self._span = self._charge + self._lethal
        self._age = 0.0
        self._path = path
        self._swing = swing
        self.head = head

        self._phase = _RISE
        self._phase_t = 0.0
        self.alpha = 0.0 if head is None else 1.0
        self.dead = False
        # Aplica o instante zero já no construtor: quem lê `muzzle()` no mesmo
        # frame em que o caster nasce (o feixe, para montar a origem inicial)
        # tem que receber a pose de partida, não a pose crua do argumento.
        self._apply(0.0)

    # ── Consultas ────────────────────────────────────────────────────────────
    @property
    def firing(self) -> bool:
        return self._phase is _FIRE

    def muzzle(self) -> Ponto:
        """A boca, já girada para a mira atual. É a origem do feixe."""
        mx, my = pmap.part_muzzle(self.part)
        dx, dy = pmap.rotate_offset(mx, my, self.aim - pmap.part_facing(self.part))
        return self.x + dx, self.y + dy

    def angle(self) -> float:
        return self.aim

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        if self.dead or dt <= 0.0:
            return
        self._phase_t += dt

        if self._phase is _RISE:
            self._age += dt
            p = min(1.0, self._phase_t / self._charge)
            self.alpha = p * p * (3.0 - 2.0 * p)
            self._apply(self._age / self._span)
            if self._phase_t >= self._charge:
                self._phase, self._phase_t = _FIRE, 0.0
        elif self._phase is _FIRE:
            self._age += dt
            self.alpha = 1.0
            self._apply(min(1.0, self._age / self._span))
            if self._phase_t >= self._lethal:
                self._phase, self._phase_t = _SINK, 0.0
        else:
            self.alpha = max(0.0, 1.0 - self._phase_t / self.SINK_TIME)
            self._apply(1.0)
            if self._phase_t >= self.SINK_TIME:
                self.dead = True

        if self.head is not None:
            self.head.attacking = self._phase is not _SINK

    def _apply(self, p: float) -> None:
        """Põe pose e mira do progresso `p` (0..1 na vida INTEIRA do caster).

        **O percurso começa na CARGA, não no disparo.** É a diferença entre um
        telégrafo que diz "vai nascer um feixe ali" e um que diz "vai nascer um
        feixe ali e ele vem PARA CÁ". Enquanto a cabeça ficava parada durante a
        carga, o jogador lia a posição inicial, se julgava seguro a 80px dali, e
        era varrido por um feixe cuja trajetória ele não tinha como conhecer —
        "impossível de escapar mesmo se movendo certo", relatado em playtest.
        Movendo desde a carga, a direção e a velocidade da varredura são
        informação pública antes de qualquer dano.

        Consequência para a partitura: o trecho inicial de cada `path` é varrido
        INOFENSIVO. Os intervalos são escritos já contando com isso — o feixe
        entra em cena antes de onde precisa ferir.

        Pose e mira ficam SÓ aqui; quem as copia para a Voz é o boss, que é
        quem conhece o (x, y) dele e sabe converter mundo em offset (§1 — o
        caster não escreve no estado de um objeto irmão).
        """
        if self._path is not None:
            self.x, self.y = self._path(p)
        if self._swing is not None:
            self.aim = self._swing(p)

    # ── Render ───────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        """`draw` não muta estado (§3). A Voz não passa por aqui: ela se desenha."""
        if self.head is not None or self.dead or self.alpha <= 0.01:
            return
        posed = pmap.aimed_part(self.part, self.aim, attacking=True)
        if posed is None:
            return
        sprite, ox, oy = posed
        pos = (int(self.x + ox), int(self.y + oy))
        if self.alpha >= 0.99:
            surface.blit(sprite, pos)
            return
        # Cópia só enquanto o eco entra ou sai (~0,6s de vida útil): `set_alpha`
        # na surface do cache contaminaria todos os ecos que usam aquele ângulo.
        faded = sprite.copy()
        faded.set_alpha(int(255 * max(0.0, min(1.0, self.alpha))))
        surface.blit(faded, pos)


def aim_toward(origem: Ponto, alvo: Ponto) -> float:
    """Ângulo de `origem` para `alvo`, no referencial de tela (y para baixo)."""
    return math.atan2(alvo[1] - origem[1], alvo[0] - origem[0])


__all__ = ["TriadCaster", "aim_toward"]
