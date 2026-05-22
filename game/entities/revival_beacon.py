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
import random
from typing import TYPE_CHECKING, Final, Optional

import pygame

from ..core.assets import get_font
from ..core.colors import CUSTOM_GOLD, CYAN, WHITE

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

    def __init__(
        self,
        x: float,
        y: float,
        for_slot: "PlayerSlot",
        ship_image: Optional[pygame.Surface] = None,
    ) -> None:
        self.x: float = x
        self.y: float = y
        self.for_slot = for_slot
        self.ship_image = ship_image
        self.hold_progress: float = 0.0
        self.dead: bool = False
        # Animação visual continua mesmo sem ninguém no raio (pulse).
        self._pulse_timer: float = 0.0
        self._show_hint: bool = False
        self._hint_font = get_font(12)
        self._button_font = get_font(16)

        # Timer para efeitos de glitch
        self._glitch_timer: float = 0.0
        self._scan_line_y: float = 0.0

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

    def update_visual(self, dt: float) -> None:
        """Avança o pulso visual independente do progresso de revive."""
        self._pulse_timer = (self._pulse_timer + dt) % 1.0
        self._glitch_timer += dt

        # Move a linha de scan
        self._scan_line_y = (self._scan_line_y + dt * 1.5) % 1.0

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
        ratio = self.progress_ratio

        # 1. Desenhar Holograma da Nave
        if self.ship_image:
            self._draw_hologram(surface, cx, cy, ratio)

        # 2. Desenhar Círculo de Raio (Aura)
        pulse = 0.6 + 0.4 * math.sin(self._pulse_timer * math.tau)
        aura_color = (
            int(80 + 40 * pulse),
            int(160 + 60 * pulse),
            int(220 + 30 * pulse),
        )

        overlay = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        # Se estiver sendo revivido, o círculo brilha mais
        alpha = 40 + int(ratio * 60)
        pygame.draw.circle(
            overlay, (*aura_color, alpha), (radius + 4, radius + 4), radius
        )
        pygame.draw.circle(
            overlay, (*aura_color, 120), (radius + 4, radius + 4), radius, width=2
        )
        surface.blit(overlay, (cx - radius - 4, cy - radius - 4))

        # 3. Anel de Progresso (Arco)
        if ratio > 0.0:
            inner_r = radius - 6
            arc_rect = pygame.Rect(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            start_angle = -math.pi / 2
            end_angle = start_angle + math.tau * ratio
            pygame.draw.arc(surface, CYAN, arc_rect, start_angle, end_angle, width=4)

        # 4. Dica Visual
        if self._show_hint:
            self._draw_ui_hints(surface, cx, cy, radius, ratio)

    def _draw_hologram(
        self, surface: pygame.Surface, cx: int, cy: int, ratio: float
    ) -> None:
        """Renderiza a nave com efeitos de holograma, glitch e scan."""
        img = self.ship_image
        if not img:
            return

        sw, sh = img.get_size()
        pos_x = cx - sw // 2
        pos_y = cy - sh // 2

        # Efeito de Glitch (Deslocamento horizontal aleatório)
        offset_x = 0
        if random.random() < 0.1:  # 10% de chance de glitch por frame
            offset_x = random.randint(-4, 4)

        # Opacidade aumenta com o progresso (mínimo 60, máximo 255)
        alpha = int(60 + (195 * ratio))

        # Criar superfície temporária para o holograma
        holo_surf = img.copy()
        holo_surf.set_alpha(alpha)

        # Aplicar tom ciano/azul ao holograma
        tint = pygame.Surface((sw, sh), pygame.SRCALPHA)
        # Cor do tint suaviza de Ciano para Branco conforme o download completa
        tint_color = (
            int(0 + (255 * ratio)),
            int(255),
            int(255),
        )
        tint.fill((*tint_color, 100))
        holo_surf.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        surface.blit(holo_surf, (pos_x + offset_x, pos_y))

        # Linha de Scan
        scan_y = pos_y + int(sh * self._scan_line_y)
        scan_w = int(sw * 1.2)
        pygame.draw.line(
            surface,
            CYAN,
            (cx - scan_w // 2, scan_y),
            (cx + scan_w // 2, scan_y),
            1,
        )
        # Brilho da linha de scan
        scan_glow = pygame.Surface((scan_w, 3), pygame.SRCALPHA)
        scan_glow.fill((*CYAN, 80))
        surface.blit(scan_glow, (cx - scan_w // 2, scan_y - 1))

    def _draw_ui_hints(
        self, surface: pygame.Surface, cx: int, cy: int, radius: int, ratio: float
    ) -> None:
        """Renderiza as dicas de botões e progresso."""
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
            pct_surf = self._hint_font.render(
                f"DOWNLOADING {int(ratio * 100)}%", True, CYAN
            )
            surface.blit(pct_surf, (cx - pct_surf.get_width() // 2, cy - radius - 15))
