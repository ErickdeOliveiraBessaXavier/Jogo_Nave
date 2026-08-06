"""upgrade_flight.py — o voo do medalhão entre o card e o slot de upgrade.

Extraído da `UpgradesSelectionScene` (§9). A animação **não conhece a cena nem
o perfil do jogador**: recebe retângulos, raios e uma cor, e devolve posição,
raio e alpha por frame. Quem equipa é o clique, lá na cena — este módulo só faz
o olho acompanhar de ONDE para ONDE o upgrade foi.

Duas peças:

- `UpgradeFlight` — um voo. Trajetória, rastro e o *snap* de chegada.
- `FlightTrack` — a coleção de voos em andamento, com as regras de quando
  lançar, quando descartar e o que o slot pode desenhar enquanto há um voo a
  caminho. É o que a cena guarda.

O desenho do medalhão em si **fica na cena**: ele depende de fonte e paleta, que
são identidade visual da tela. `FlightTrack.draw` recebe esse desenhista como
callback (§9) — é o que mantém este módulo livre de `get_font`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

import pygame

from .ui_helpers import UIParticle

if TYPE_CHECKING:
    from ..core.upgrades import UpgradeMeta

Color = Tuple[int, int, int]
# Assinatura do desenhista de medalhão que a cena fornece:
# (surface, centro, raio, meta, alpha) -> None
MedallionDrawer = Callable[
    [pygame.Surface, Tuple[int, int], int, "UpgradeMeta", int], None
]


def ease_in_out_cubic(t_norm: float) -> float:
    """Aceleração e freada suaves — a curva do voo do medalhão."""
    if t_norm < 0.5:
        return 4.0 * t_norm * t_norm * t_norm
    return 1.0 - ((-2.0 * t_norm + 2.0) ** 3) / 2.0


class UpgradeFlight:
    """Voo do medalhão de um upgrade entre o card da lista e um slot.

    Cosmético: quem equipa é o clique, não a chegada. A animação existe para o
    olho acompanhar de ONDE para ONDE o upgrade foi — sem ela a lista e o slot
    mudam no mesmo frame e o jogador não vê a relação entre os dois.

    Trajetória em bézier quadrática com o ponto de controle deslocado
    perpendicularmente ao trajeto: o arco distingue o voo de um simples
    deslize e dá espaço para o rastro de partículas respirar. No fim, quem
    chega a um slot faz o *snap* (pop de escala + anel), e quem volta para um
    card que não está visível apenas se apaga.
    """

    DURATION = 0.38
    SNAP_DURATION = 0.18
    _EMIT_INTERVAL = 0.02

    def __init__(
        self,
        meta: "UpgradeMeta",
        start: pygame.Rect,
        end: pygame.Rect,
        start_radius: int,
        end_radius: int,
        color: Color,
        *,
        slot_index: Optional[int],
        fade_out: bool = False,
    ) -> None:
        self.meta = meta
        self.slot_index = slot_index
        self.fade_out = fade_out
        self.color = color

        self.x0, self.y0 = float(start.centerx), float(start.centery)
        self.x1, self.y1 = float(end.centerx), float(end.centery)
        self.start_radius = float(start_radius)
        self.end_radius = float(end_radius)

        # Ponto de controle: meio do trajeto empurrado para o lado perpendicular
        # (sempre para CIMA na tela, que é a direção livre do layout).
        mx, my = (self.x0 + self.x1) * 0.5, (self.y0 + self.y1) * 0.5
        dx, dy = self.x1 - self.x0, self.y1 - self.y0
        dist = math.hypot(dx, dy) or 1.0
        arc = dist * 0.22
        self.cx = mx + (-dy / dist) * arc * (1.0 if dy >= 0 else -1.0)
        self.cy = my + (dx / dist) * arc * (1.0 if dy >= 0 else -1.0)
        if self.cy > my:  # garante o arco pela metade de cima
            self.cy = my - abs(self.cy - my)

        self.t = 0.0
        self.snap_t = 0.0
        self.particles: List[UIParticle] = []
        self._emit_acc = 0.0

    # -- estado ------------------------------------------------------------

    @property
    def arrived(self) -> bool:
        """Já encostou no destino (o slot pode desenhar o ícone)."""
        return self.t >= 1.0

    @property
    def snap_finished(self) -> bool:
        return self.arrived and self.snap_t >= self.SNAP_DURATION

    @property
    def medallion_visible(self) -> bool:
        """Depois do snap quem desenha o medalhão é o SLOT, não o voo.

        Sem isto o voo continuaria desenhando um medalhão idêntico por cima do
        slot durante todo o rastro que ainda está se apagando — invisível, mas
        um desenho a mais por frame e um estado a mais para raciocinar."""
        return not self.snap_finished

    @property
    def done(self) -> bool:
        return self.snap_finished and not self.particles

    def position(self) -> Tuple[float, float]:
        p = ease_in_out_cubic(min(1.0, self.t))
        inv = 1.0 - p
        x = inv * inv * self.x0 + 2 * inv * p * self.cx + p * p * self.x1
        y = inv * inv * self.y0 + 2 * inv * p * self.cy + p * p * self.y1
        return x, y

    def radius(self) -> float:
        p = ease_in_out_cubic(min(1.0, self.t))
        base = self.start_radius + (self.end_radius - self.start_radius) * p
        if not self.arrived or self.fade_out:
            return base
        # Snap: estica 25% e volta — o "encaixou" que o olho lê como impacto.
        pop = math.sin(math.pi * min(1.0, self.snap_t / self.SNAP_DURATION))
        return base * (1.0 + 0.25 * pop)

    def alpha(self) -> int:
        if self.fade_out and self.arrived:
            fade = 1.0 - min(1.0, self.snap_t / self.SNAP_DURATION)
            return max(0, int(255 * fade))
        return 255

    # -- ciclo de vida -----------------------------------------------------

    def update(self, dt: float) -> None:
        if self.t < 1.0:
            self.t = min(1.0, self.t + dt / self.DURATION)
            self._emit_trail(dt)
        else:
            self.snap_t += dt

        # Rebuild O(n) de uma lista comprovadamente curta (§6): ~40 partículas
        # no pico de um voo, fora de hot path de combate.
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

    def _emit_trail(self, dt: float) -> None:
        """Rastro: duas fagulhas por intervalo, com carry do resto (§14)."""
        self._emit_acc += dt
        while self._emit_acc >= self._EMIT_INTERVAL:
            self._emit_acc -= self._EMIT_INTERVAL
            x, y = self.position()
            for _ in range(2):
                # Espalhamento curto: o rastro tem que ler como esteira do
                # medalhão, não como poeira solta pela tela.
                self.particles.append(UIParticle(x, y, self.color, 0.35))

    def draw_particles(self, surface: pygame.Surface) -> None:
        for p in self.particles:
            p.draw(surface)

    def draw_ring(self, surface: pygame.Surface) -> None:
        """Anel de chegada: expande e some durante o snap."""
        if not self.arrived or self.fade_out:
            return
        prog = min(1.0, self.snap_t / self.SNAP_DURATION)
        if prog >= 1.0:
            return
        radius = int(self.end_radius * (1.0 + 1.1 * prog))
        alpha = int(200 * (1.0 - prog))
        x, y = self.position()
        pygame.draw.circle(surface, (*self.color, alpha), (int(x), int(y)), radius, 3)


class FlightTrack:
    """Os voos em andamento e as regras de lançamento.

    Guarda a lista, decide o que fazer quando o destino não está visível e
    responde à única pergunta que o render do slot precisa fazer: *tem coisa a
    caminho daqui?* — se tem, o slot desenha vazio, senão o upgrade apareceria
    nos dois lugares ao mesmo tempo.

    ``animations_enabled`` é um callable, não um bool: a qualidade visual pode
    mudar em Settings enquanto a tela está aberta, e uma cópia do valor tirada
    no construtor ficaria velha.
    """

    def __init__(self, animations_enabled: Callable[[], bool]) -> None:
        self._enabled = animations_enabled
        self.flights: List[UpgradeFlight] = []

    def __len__(self) -> int:
        return len(self.flights)

    # -- consultas ---------------------------------------------------------

    def is_slot_pending(self, slot_index: int) -> bool:
        """Há um voo a caminho deste slot que ainda não chegou."""
        return any(
            f.slot_index == slot_index and not f.arrived for f in self.flights
        )

    # -- lançamento --------------------------------------------------------

    def cancel_for_slot(self, slot_index: int) -> None:
        """Descarta voos que iam para este slot — o conteúdo mudou no meio."""
        self.flights = [f for f in self.flights if f.slot_index != slot_index]

    def launch_to_slot(
        self,
        meta: "UpgradeMeta",
        color: Color,
        card_rect: pygame.Rect,
        slot_rect: pygame.Rect,
        card_radius: int,
        slot_radius: int,
        slot_index: int,
    ) -> None:
        """Equipar: card -> slot, com snap na chegada."""
        self.cancel_for_slot(slot_index)
        if not self._enabled():
            return
        self.flights.append(
            UpgradeFlight(
                meta,
                card_rect,
                slot_rect,
                card_radius,
                slot_radius,
                color,
                slot_index=slot_index,
            )
        )

    def launch_to_card(
        self,
        meta: "UpgradeMeta",
        color: Color,
        slot_rect: pygame.Rect,
        card_rect: Optional[pygame.Rect],
        slot_radius: int,
        card_radius: int,
        slot_index: int,
        fallback_center: pygame.Rect,
    ) -> None:
        """Desequipar: slot -> card.

        ``card_rect`` é ``None`` quando o card não está visível (rolado para
        fora, ou noutra aba). Aí o medalhão viaja até ``fallback_center`` e se
        apaga — melhor que mirar num rect que o jogador não está vendo.
        """
        self.cancel_for_slot(slot_index)
        if not self._enabled():
            return
        fade_out = card_rect is None
        destino = card_rect if card_rect is not None else fallback_center
        self.flights.append(
            UpgradeFlight(
                meta,
                slot_rect,
                destino,
                slot_radius,
                slot_radius if fade_out else card_radius,
                color,
                slot_index=None,
                fade_out=fade_out,
            )
        )

    # -- ciclo -------------------------------------------------------------

    def update(self, dt: float) -> None:
        for f in self.flights:
            f.update(dt)
        self.flights = [f for f in self.flights if not f.done]

    def draw(self, surface: pygame.Surface, draw_medallion: MedallionDrawer) -> None:
        for flight in self.flights:
            flight.draw_particles(surface)
            flight.draw_ring(surface)
            if not flight.medallion_visible:
                continue
            x, y = flight.position()
            draw_medallion(
                surface,
                (int(x), int(y)),
                int(flight.radius()),
                flight.meta,
                flight.alpha(),
            )
