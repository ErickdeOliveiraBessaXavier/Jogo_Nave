"""ImplosionPulse — zona de controle criada no ponto de impacto (upgrade Implosão).

Cada acerto abre um círculo que fecha em 2s. Quem estiver dentro dele fica
**lento** (75%, com 3s de sobrevida depois que a zona some) e sofre um **dano
contínuo pequeno**. Não há atração: o upgrade compra tempo e pressão sobre um
grupo, não reposicionamento.

*(Houve uma versão com sucção de verdade, puxando os inimigos para o impacto.
Foi removida: exigia um caso especial por família de inimigo — quem deriva a
posição de uma âncora interna desfazia o puxão no próprio `update`, quem tem
mola voltava sozinho, peças coreografadas de boss dessincronizavam — e ainda
arremessava alvos para fora da tela quando os pulsos se sobrepunham. O que
sobrou faz uma coisa só e vale para todo mundo igual.)*

A entidade aqui é só geometria + relógio + desenho. Quem aplica lentidão e dano
é `Collisions.implosion_pulses_vs_enemies`, porque é lá que a spatial grid está
montada (§8) e onde mora o roteador de dano (`apply_hit`/`HitResult`).
"""

from __future__ import annotations

from typing import Any, List

import pygame

from ...core.scale import scaled
from ...core.upgrades_config import (
    IMPLOSION_DURATION,
    IMPLOSION_OPEN_TIME,
    IMPLOSION_RADIUS,
)

_COLOR_RING: tuple[int, int, int] = (120, 220, 255)

# Buffer com alpha por pixel, usado SÓ na fase de abertura (alpha < 255).
# `pygame.draw.circle` direto na tela não tem como aplicar transparência, mas
# alocar uma Surface por pulso por frame é exatamente o que §7 proíbe. Um único
# buffer compartilhado resolve: a abertura dura 0,15s dos 2s de vida, então no
# máximo ~7,5% dos pulsos vivos passam por aqui num frame — o resto segue pelo
# caminho rápido, desenhando direto na tela sem buffer nenhum.
_alpha_scratch: pygame.Surface | None = None


def _get_alpha_scratch(size: int) -> pygame.Surface:
    """Buffer quadrado de pelo menos `size` px, realocado só quando cresce."""
    global _alpha_scratch
    if _alpha_scratch is None or _alpha_scratch.get_width() < size:
        _alpha_scratch = pygame.Surface((size, size), pygame.SRCALPHA)
    return _alpha_scratch


def suction_radius() -> float:
    """Raio efetivo da zona na resolução lógica atual (§12).

    FONTE ÚNICA: a área de efeito, a consulta à spatial grid e o círculo
    desenhado saem todos daqui. Se algum deles lesse `IMPLOSION_RADIUS` cru, o
    desenho passaria a mentir sobre o alcance real fora de 720p — e o círculo
    existe justamente para o jogador saber onde mirar.

    Lido a cada chamada e não congelado no import: a resolução só muda no
    restart, mas o `set_screen_resolution` do `app.py` roda DEPOIS deste módulo
    ser importado, então uma constante calculada no topo nasceria com o valor
    errado.
    """
    return scaled(IMPLOSION_RADIUS)


def accepts_control(enemy: Any) -> bool:
    """A entidade pode receber os efeitos de controle da zona?

    Inimigo comum tem `__dict__` e aceita as marcas (`implosion_slow_timer`,
    `implosion_damage_cd`) na hora. Entidades com `__slots__` — peças
    coreografadas de boss (`SerpentBlock`), destroços, tanques — só aceitam os
    campos que declararam, e escrever nelas estoura `AttributeError`. Uma delas
    derrubou o jogo em combate.

    Quem quiser participar declara o slot, como já fazem com `emp_linger_timer`:
    o opt-in fica explícito na entidade, do lado de quem sabe se ela aguenta.
    """
    return hasattr(enemy, "__dict__") or hasattr(enemy, "implosion_slow_timer")


class ImplosionPulse:
    """Um pulso: conta o próprio tempo e desenha o círculo. Nada além disso."""

    __slots__ = ("cx", "cy", "radius", "t", "dead")

    def __init__(self, cx: float = 0.0, cy: float = 0.0) -> None:
        self.cx: float = cx
        self.cy: float = cy
        self.radius: float = 0.0
        self.t: float = 0.0
        self.dead: bool = True

    def reset(self, cx: float, cy: float) -> None:
        self.cx = cx
        self.cy = cy
        # Congelado no spawn: o raio que o dano e a lentidão usam é o mesmo que
        # o círculo desenha, então o visual não pode divergir da área real.
        self.radius = suction_radius()
        self.t = 0.0
        self.dead = False

    def recycle(self) -> None:
        """Encerra o pulso. Público porque quem chama é o pool (§1)."""
        self.dead = True
        self.t = 0.0

    def update(self, dt: float) -> None:
        if self.dead or dt <= 0.0:
            return
        self.t += dt
        if self.t >= IMPLOSION_DURATION:
            self.t = IMPLOSION_DURATION
            self.dead = True

    def covers(self, cx: float, cy: float, r: float = 0.0) -> bool:
        """O ponto (com raio `r`) está dentro da zona?"""
        dx = cx - self.cx
        dy = cy - self.cy
        alcance = self.radius + r
        return dx * dx + dy * dy < alcance * alcance

    # ── Visual ──────────────────────────────────────────────────────────────

    @staticmethod
    def _eased(u: float) -> float:
        """Fração do fechamento já cumprida em `u` (0..1) da vida do pulso.

        Ease-IN cúbico: começa devagar e acelera até o fim — em `u=0.5` só 12,5%
        do caminho foi feito, e o último quarto entrega quase metade. É a curva
        de uma implosão de verdade (o colapso puxa cada vez mais forte), e é o
        que dá o clímax no instante em que o círculo fecha.
        """
        return u * u * u

    @staticmethod
    def _opening(u: float) -> float:
        """Fração do raio já aberta em `u` (0..1) do tempo de abertura.

        Ease-OUT: cresce rápido e DESACELERA ao chegar no raio cheio. Se fosse
        linear, o anel bateria no tamanho final e travaria — trocaria um pop por
        outro. Assim ele assenta.
        """
        inv = 1.0 - u
        return 1.0 - inv * inv

    def current_radius(self) -> float:
        """Raio do círculo neste instante.

        A abertura é uma MÁSCARA sobre a curva de fechamento, não uma fase
        separada com timer próprio: `min(abertura, fechamento)`. Assim os dois se
        encontram sem degrau (aos 0,15s o fechamento ainda vale 0,9996 do raio).
        """
        if self.t <= 0.0:
            return 0.0
        closing = 1.0 - self._eased(min(1.0, self.t / IMPLOSION_DURATION))
        if self.t < IMPLOSION_OPEN_TIME:
            return self.radius * min(
                self._opening(self.t / IMPLOSION_OPEN_TIME), closing
            )
        return self.radius * closing

    def current_alpha(self) -> int:
        """Opacidade (0–255): sobe durante a abertura, cheia no resto da vida."""
        if self.t >= IMPLOSION_OPEN_TIME:
            return 255
        return int(255 * max(0.0, self.t) / IMPLOSION_OPEN_TIME)

    def draw(self, surface: pygame.Surface) -> None:
        """Um círculo que abre, fecha e some. Só isso.

        O raio cheio é o raio REAL da zona **na resolução atual** (§12): o
        desenho não é enfeite, é a área onde a lentidão e o dano acontecem.

        DOIS caminhos de desenho, de propósito: durante a abertura o alpha é
        parcial e exige buffer (`_get_alpha_scratch`); no resto da vida — a
        grande maioria dos pulsos em qualquer frame — vai direto na tela, sem
        buffer, sem blit. Espessura fixa em 2px: §12 não escala borda fina.
        """
        ring_r = int(self.current_radius())
        if ring_r <= 1:
            return

        cx, cy = int(self.cx), int(self.cy)
        alpha = self.current_alpha()

        if alpha >= 255:
            pygame.draw.circle(surface, _COLOR_RING, (cx, cy), ring_r, 2)
            return

        size = ring_r * 2 + 4
        buf = _get_alpha_scratch(size)
        area = pygame.Rect(0, 0, size, size)
        # `fill` com RGBA zera o alpha POR PIXEL. `set_alpha` não serviria aqui:
        # é alpha de superfície, persiste no objeto e o próximo consumidor do
        # buffer herdaria o valor (a armadilha documentada em §17).
        buf.fill((0, 0, 0, 0), area)
        pygame.draw.circle(
            buf, (*_COLOR_RING, alpha), (size // 2, size // 2), ring_r, 2
        )
        surface.blit(buf, (cx - size // 2, cy - size // 2), area)


class ImplosionPulsePool:
    """Pool de pulsos (§7): free-list LIFO, sweep in-place, zero alocação no uso.

    Mesmo desenho do `BulletPool` — o pulso é entidade de altíssima rotatividade
    (um por bala que acerta, várias por segundo).

    O `initial_size` sai de `taxa de acertos × IMPLOSION_DURATION`: com o leque
    (5 balas a 5 disparos/s = 25 acertos/s) e vida de 2s, ficam ~50 vivos ao
    mesmo tempo. 64 cobre isso com folga, então o combate normal nunca aloca —
    o pool ainda cresce sozinho se alguém passar disso, mas aí a alocação sai do
    caminho quente.
    """

    def __init__(self, initial_size: int = 64) -> None:
        self.active: List[ImplosionPulse] = []
        self.free: List[ImplosionPulse] = [
            ImplosionPulse() for _ in range(initial_size)
        ]

    def get(self, cx: float, cy: float) -> ImplosionPulse:
        pulse = self.free.pop() if self.free else ImplosionPulse()
        pulse.reset(cx, cy)
        self.active.append(pulse)
        return pulse

    def update(self, dt: float) -> None:
        """Atualiza e compacta in-place (§6): sem cópia de lista, sem `remove`."""
        write = 0
        active = self.active
        for pulse in active:
            pulse.update(dt)
            if pulse.dead:
                self.free.append(pulse)
            else:
                active[write] = pulse
                write += 1
        del active[write:]

    def draw_all(self, surface: pygame.Surface) -> None:
        for pulse in self.active:
            pulse.draw(surface)

    def clear_active(self) -> None:
        for pulse in self.active:
            pulse.recycle()
            self.free.append(pulse)
        self.active.clear()

    def get_active_count(self) -> int:
        return len(self.active)
