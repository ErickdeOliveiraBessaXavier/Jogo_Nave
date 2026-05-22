"""revival_beacon.py — Beacon de ressurreição para multiplayer coop.

Quando um jogador morre, um beacon nasce na posição da nave. Outro jogador
vivo precisa entrar no raio e segurar Y por `HOLD_TIME_REQUIRED` segundos
para reviver o morto. Se o vivo sair do raio antes de completar, o progresso
**reseta a zero** (decisão travada no PLANO_MULTIPLAYER.md).

A entidade é gerenciada pela `PlayingScene` (não pelo `EntityManager`) —
beacons são raros, atrelados a um `PlayerSlot.revival_beacon` específico,
e não se beneficiam dos pools/spatial grids dedicados a inimigos/projéteis.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import pygame

from ..core.assets import get_font
from ..core.colors import WHITE, CUSTOM_GOLD, CYAN

if TYPE_CHECKING:
    from ..systems.player_slot import PlayerSlot


class RevivalBeacon:
    """Marca a posição de morte de um slot e acumula o timer de revive."""

    HOLD_TIME_REQUIRED: Final[float] = 5.0
    """Segundos contínuos no raio segurando Y para ressuscitar."""

    RADIUS: Final[float] = 70.0
    """Raio em pixels onde o vivo precisa estar pra avançar o timer."""

    POST_REVIVE_INVULN_MS: Final[float] = 2000.0
    """Invuln aplicado à nave revivida (2s) para evitar morte imediata."""

    LIVES_ON_REVIVE: Final[int] = 1
    """Vidas com que o slot volta após o revive."""

    def __init__(self, x: float, y: float, for_slot: "PlayerSlot") -> None:
        self.x: float = x
        self.y: float = y
        self.for_slot = for_slot
        self.hold_progress: float = 0.0
        self.dead: bool = False
        # Animação visual continua mesmo sem ninguém no raio (pulse).
        self._pulse_timer: float = 0.0
        self._show_hint: bool = False
        self._hint_font = get_font(12)
        self._button_font = get_font(16)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def tick_hold(self, dt: float) -> None:
        """Acumula progresso. Chamado pela cena quando alguém está no raio
        segurando o botão de revive."""
        self.hold_progress += dt
        self._show_hint = True

    def reset_progress(self) -> None:
        """Zera o progresso. Chamado pela cena quando ninguém qualifica."""
        self.hold_progress = 0.0
        # A cena deve atualizar _show_hint externamente ou resetar aqui se 
        # ninguém estiver sequer perto. Por simplificação, a PlayingScene 
        # passará a gerir a proximidade visual.

    def update_visual(self, dt: float) -> None:
        """Avança o pulso visual independente do progresso de revive."""
        self._pulse_timer = (self._pulse_timer + dt) % 1.0

    def set_hint_visible(self, visible: bool) -> None:
        """Define se a dica de botão deve ser exibida."""
        self._show_hint = visible

    @property
    def progress_ratio(self) -> float:
        """0.0 → 1.0 conforme o timer enche."""
        if self.HOLD_TIME_REQUIRED <= 0:
            return 1.0
        return min(1.0, self.hold_progress / self.HOLD_TIME_REQUIRED)

    @property
    def is_complete(self) -> bool:
        return self.hold_progress >= self.HOLD_TIME_REQUIRED

    def contains_point(self, px: float, py: float) -> bool:
        dx = px - self.x
        dy = py - self.y
        return (dx * dx + dy * dy) <= (self.RADIUS * self.RADIUS)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        cx = int(self.x)
        cy = int(self.y)
        radius = int(self.RADIUS)

        # Cor base ciano-azul (neutro) com pulso suave.
        pulse = 0.6 + 0.4 * math.sin(self._pulse_timer * math.tau)
        base_color = (
            int(80 + 40 * pulse),
            int(160 + 60 * pulse),
            int(220 + 30 * pulse),
        )

        # Camada externa: círculo translúcido marcando o raio de revive.
        overlay = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        pygame.draw.circle(
            overlay,
            (*base_color, 40),
            (radius + 4, radius + 4),
            radius,
        )
        pygame.draw.circle(
            overlay,
            (*base_color, 120),
            (radius + 4, radius + 4),
            radius,
            width=2,
        )
        surface.blit(overlay, (cx - radius - 4, cy - radius - 4))

        # Anel interno: arco que enche conforme hold_progress.
        ratio = self.progress_ratio
        if ratio > 0.0:
            inner_r = radius - 12
            arc_rect = pygame.Rect(
                cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2
            )
            # Arco começa do topo (-π/2) e gira no sentido horário até 2π.
            start_angle = -math.pi / 2
            end_angle = start_angle + math.tau * ratio
            pygame.draw.arc(
                surface,
                WHITE,
                arc_rect,
                start_angle,
                end_angle,
                width=4,
            )

        # Ícone central minimalista: cruz indicando "respawn point".
        cross_r = 10
        pygame.draw.line(
            surface, base_color, (cx - cross_r, cy), (cx + cross_r, cy), 3
        )
        pygame.draw.line(
            surface, base_color, (cx, cy - cross_r), (cx, cy + cross_r), 3
        )

        # Dica Visual (Instrução de botão)
        if self._show_hint:
            # Badge do Botão [Y]
            btn_surf = self._button_font.render("Y", True, (20, 20, 20))
            btn_bg = pygame.Rect(cx - 15, cy - radius - 45, 30, 30)
            pygame.draw.rect(surface, CUSTOM_GOLD, btn_bg, border_radius=15)
            surface.blit(btn_surf, btn_surf.get_rect(center=btn_bg.center))

            # Texto "SEGURE PARA REVIVER"
            txt_surf = self._hint_font.render("SEGURE PARA REVIVER", True, WHITE)
            surface.blit(txt_surf, (cx - txt_surf.get_width() // 2, cy - radius - 65))
            
            # Progresso em texto se estiver segurando
            if ratio > 0:
                pct_surf = self._hint_font.render(f"{int(ratio * 100)}%", True, CYAN)
                surface.blit(pct_surf, (cx - pct_surf.get_width() // 2, cy - radius - 15))

