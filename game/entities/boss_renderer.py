"""Renderização do Boss (quadrado).

Separa toda a apresentação da simulação: o `Boss` cuida da FSM/estado e delega
o desenho para esta classe, que só LÊ o estado do boss (sem efeitos colaterais).
O cache de máscaras de pixel-art vive aqui; o boss invalida via
`invalidate_layers()` quando a paleta muda (frenzy).
"""

import math
from typing import TYPE_CHECKING, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from .boss_pixel_map import PIXEL_MAP
from .boss_square import BossSquare
from .boss_state import BossState
from .draw_utils import rotated_square_corners

if TYPE_CHECKING:
    from .boss import Boss


class BossRenderer:
    """Desenha o boss a partir do seu estado. Não muta nada do boss."""

    def __init__(self, boss: "Boss") -> None:
        self.boss = boss
        # Máscaras de pixel-art por layer (formas em branco, recoloridas por
        # frame com a paleta atual). Caro de gerar, barato de reusar.
        self._cached_layers: dict[str, pygame.Surface] = {}

    def invalidate_layers(self) -> None:
        """Descarta o cache de layers (chamado quando a paleta muda)."""
        self._cached_layers.clear()

    def _render_layer(self, layer_cells: set[str]) -> pygame.Surface:
        boss = self.boss
        surf = pygame.Surface((int(boss.w), int(boss.h)), pygame.SRCALPHA)
        p = boss.pixel_size
        for r, row in enumerate(PIXEL_MAP):
            for c, cell in enumerate(row):
                if cell in layer_cells:
                    pygame.draw.rect(
                        surf, (255, 255, 255), (int(c * p), int(r * p), int(p), int(p))
                    )
        return surf

    def _get_layer_surfaces(self) -> dict[str, pygame.Surface]:
        if not self._cached_layers:
            self._cached_layers["shell"] = self._render_layer({"A", "C", "D", "E", "F"})
            self._cached_layers["core"] = self._render_layer({"G", "H"})
            self._cached_layers["cannon_base"] = self._render_layer({"I", "M"})
        return self._cached_layers

    def _draw_layer(
        self,
        surface: pygame.Surface,
        layer_name: str,
        dx: int,
        dy: int,
        off_x: float = 0,
        off_y: float = 0,
    ) -> None:
        layers = self._get_layer_surfaces()
        if layer_name not in layers:
            return
        lsurf = layers[layer_name].copy()
        palette = self.boss.current_palette

        cells = {
            "shell": {"A", "C", "D", "E", "F"},
            "core": {"G", "H"},
            "cannon_base": {"I", "M"},
        }[layer_name]
        p = self.boss.pixel_size
        for r, row in enumerate(PIXEL_MAP):
            for c, cell in enumerate(row):
                if cell in cells:
                    pygame.draw.rect(
                        lsurf,
                        palette.get(cell, (255, 0, 255)),
                        (int(c * p), int(r * p), int(p), int(p)),
                    )
        surface.blit(lsurf, (int(dx + off_x), int(dy + off_y)))

    def draw(self, surface: pygame.Surface) -> None:
        boss = self.boss
        dx, dy = int(boss.x + boss.shake_offset_x), int(boss.y + boss.shake_offset_y)

        # 1. Squares Behind
        self._draw_floating_squares(
            surface, boss.shake_offset_x, boss.shake_offset_y, behind=True
        )

        # 2. Body Layers with breathing
        breathing = math.sin(boss.breathing_timer * 2.5) * 2.0
        self._draw_layer(surface, "shell", dx, dy, 0, breathing)
        self._draw_layer(surface, "core", dx, dy, 0, breathing * 1.5)
        self._draw_layer(surface, "cannon_base", dx, dy)

        # 3. Squares Front
        self._draw_floating_squares(
            surface, boss.shake_offset_x, boss.shake_offset_y, behind=False
        )

        # 4. Interactive Elements
        # draw all cannons (central last so it renders on top)
        for c in boss.cannons:
            c.draw(surface, boss.shake_offset_x, boss.shake_offset_y)
        if boss.state != BossState.ENTERING:
            self._draw_health_bar(surface)
        if boss.shows_aiming_line:
            self._draw_aiming_line(surface)

        # 5. Effects
        if boss.shows_charge_circle:
            rad = (
                boss.charge_progress * Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS
                if boss.state == BossState.CHARGING
                else Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS
            )
            if rad > 0:
                pygame.draw.circle(
                    surface,
                    (255, 255, 100),
                    (
                        int(boss.face_center.x + boss.shake_offset_x),
                        int(boss.face_center.y + boss.shake_offset_y),
                    ),
                    int(rad),
                    4,
                )
                if rad > 8:
                    pygame.draw.circle(
                        surface,
                        (255, 255, 0),
                        (
                            int(boss.face_center.x + boss.shake_offset_x),
                            int(boss.face_center.y + boss.shake_offset_y),
                        ),
                        int(rad - 8),
                        2,
                    )
            boss.particle_system.draw_particles(
                surface, boss.shake_offset_x, boss.shake_offset_y
            )

        if boss.state == BossState.PREPARING_TO_FIRE:
            if (pygame.time.get_ticks() % 200) < 100:
                pygame.draw.circle(
                    surface,
                    (255, 255, 255),
                    (
                        int(boss.face_center.x + boss.shake_offset_x),
                        int(boss.face_center.y + boss.shake_offset_y),
                    ),
                    12,
                    3,
                )

        boss.particle_system.draw_circle_disappear_particles(
            surface, boss.shake_offset_x, boss.shake_offset_y
        )

    def _draw_floating_squares(
        self, surface: pygame.Surface, off_x: float, off_y: float, behind: bool
    ) -> None:
        boss = self.boss
        for i, sq in enumerate(boss.floating_squares):
            if (i % 2 == 0) != behind:
                continue

            color, border = (255, 0, 0), (255, 100, 100)  # Fallback
            if sq.state in ("preparing", "launching"):
                p = 0.5 + 0.5 * abs(math.sin(sq.prepare_timer * 8))
                color, border = (255, int(200 * p), 0), (255, 255, 0)
            else:
                pal = boss.current_palette
                # No frenzy usamos a cor do chassi ou similar
                color = pal.get("C", (200, 0, 0))
                intensity = 0.7 + (i / len(boss.floating_squares)) * 0.3
                color = (
                    int(color[0] * intensity),
                    int(color[1] * intensity),
                    int(color[2] * intensity),
                )
                border = (
                    min(255, color[0] + 50),
                    min(255, color[1] + 50),
                    min(255, color[2] + 50),
                )

            if sq.rotation > 0:
                self._draw_rotated_square(surface, sq, color, border, off_x, off_y)
            else:
                r = pygame.Rect(
                    int(sq.x - sq.size / 2 + off_x),
                    int(sq.y - sq.size / 2 + off_y),
                    int(sq.size),
                    int(sq.size),
                )
                pygame.draw.rect(surface, color, r)
                pygame.draw.rect(surface, border, r, 2)

    def _draw_rotated_square(
        self,
        surface: pygame.Surface,
        sq: BossSquare,
        color: Tuple[int, int, int],
        border: Tuple[int, int, int],
        ox: float,
        oy: float,
    ) -> None:
        corners = rotated_square_corners(
            sq.x + ox, sq.y + oy, sq.size / 2, math.radians(sq.rotation)
        )
        pygame.draw.polygon(surface, color, corners)
        pygame.draw.polygon(surface, border, corners, 2)

    def _get_aiming_line_intensity(self) -> float:
        """Calcula a intensidade do traçado de mira baseado no estado.
        0.0 = mínimo, 1.0 = máximo (último frame antes de travar o alvo).

        Em PREPARING_TO_FIRE a mira já foi encerrada (ver _draw_aiming_line):
        a janela de reação é cega, sem tracejado.
        """
        boss = self.boss
        if boss.state == BossState.AIMING:
            return 0.3  # Fraco durante a mira inicial
        elif boss.state == BossState.CHARGING:
            # Aumenta com o progresso de carga (0 -> 1)
            return 0.3 + boss.charge_progress * 0.5  # 0.3 -> 0.8
        elif boss.state == BossState.CONVERGING:
            return 1.0  # Máximo: último frame com mira antes de travar o alvo
        return 0.0

    def _draw_aiming_line(self, surface: pygame.Surface) -> None:
        # A mira é encerrada ao travar o alvo: em PREPARING_TO_FIRE não há
        # tracejado. A janela de reação é cega — o jogador lê a ameaça pela pose
        # congelada do canhão, e o disparo sai exatamente na direção travada
        # (ver _prepare_laser_data / _fire_next_salvo_shot).
        boss = self.boss
        if boss.state == BossState.PREPARING_TO_FIRE:
            return
        total_cycle = Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
        intensity = self._get_aiming_line_intensity()
        # Tracejado em ritmo constante durante AIMING/CHARGING/CONVERGING; não
        # acelera, para não sugerir que o laser sai antes da janela de reação.
        time_based_offset = int(pygame.time.get_ticks() * 0.1) % total_cycle
        if boss.frenzy_mode and len(boss.cannons) > 1:
            # Wall: laterais seguem um vetor fixo relativo ao canhão central.
            if boss.frenzy_pattern == "wall":
                center_cannon = boss.central
                center_tip = pygame.Vector2(center_cannon.get_barrel_tip_position())
                center_dir = center_cannon.get_direction()
                angle = boss.FRENZY_LASER_ANGLES[2]
                left_dir = pygame.Vector2(
                    center_dir.x * math.cos(-angle) - center_dir.y * math.sin(-angle),
                    center_dir.x * math.sin(-angle) + center_dir.y * math.cos(-angle),
                )
                right_dir = pygame.Vector2(
                    center_dir.x * math.cos(angle) - center_dir.y * math.sin(angle),
                    center_dir.x * math.sin(angle) + center_dir.y * math.cos(angle),
                )
                self._draw_dashed_line(
                    surface,
                    pygame.Vector2(boss.cannons[0].get_barrel_tip_position()),
                    left_dir,
                    time_based_offset,
                    False,
                    intensity,
                )
                self._draw_dashed_line(
                    surface,
                    pygame.Vector2(boss.cannons[1].get_barrel_tip_position()),
                    right_dir,
                    time_based_offset,
                    False,
                    intensity,
                )
                self._draw_dashed_line(
                    surface,
                    center_tip,
                    center_dir,
                    time_based_offset,
                    True,
                    intensity,
                )
            else:
                # Demais padrões: uma linha de mira por canhão, da própria ponta.
                for i, c in enumerate(boss.cannons):
                    tip_x, tip_y = c.get_barrel_tip_position()
                    tip = pygame.Vector2(tip_x, tip_y)
                    dirv = c.get_direction()
                    # consider central cannon as primary for styling
                    primary = i == len(boss.cannons) - 1
                    self._draw_dashed_line(
                        surface, tip, dirv, time_based_offset, primary, intensity
                    )
        else:
            self._draw_dashed_line(
                surface,
                boss.face_center,
                boss.facing_direction,
                time_based_offset,
                True,
                intensity,
            )

    def _draw_dashed_line(
        self,
        surface: pygame.Surface,
        start: pygame.Vector2,
        direction: pygame.Vector2,
        offset: int,
        primary: bool,
        intensity: float = 0.5,
    ) -> None:
        # Aumentar cor conforme intensidade
        base_color = (
            colors.BOSS_AIM_LINE
            if primary
            else tuple(max(50, int(c * 0.6)) for c in colors.BOSS_AIM_LINE)
        )
        # Interpolar cor: base -> brilho vermelho conforme intensidade
        r = int(base_color[0] + (255 - base_color[0]) * intensity)
        g = int(base_color[1] + (50 - base_color[1]) * intensity)
        b = int(base_color[2] + (50 - base_color[2]) * intensity)
        color = (r, g, b)

        # Aumentar largura conforme intensidade
        base_width = 4 if primary else 2
        width = max(
            base_width, int(base_width + intensity * 6)
        )  # base_width -> base_width + 6

        laser_distance = self.boss.LASER_DISTANCE
        curr_dist = offset - (Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH)
        while curr_dist < laser_distance:
            if curr_dist + Config.BOSS_AIM_DASH_LENGTH > 0:
                s_dist, e_dist = (
                    max(0, curr_dist),
                    min(laser_distance, curr_dist + Config.BOSS_AIM_DASH_LENGTH),
                )
                pygame.draw.line(
                    surface,
                    color,
                    start + direction * s_dist,
                    start + direction * e_dist,
                    width,
                )
            curr_dist += Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        boss = self.boss
        if boss.health <= 0:
            return
        bmw, bh = min(200, boss.w * 2), 10
        bx, by = boss.x + (boss.w - bmw) / 2, boss.y - 20
        pygame.draw.rect(surface, (255, 0, 0), (bx, by, bmw, bh))
        pygame.draw.rect(
            surface,
            (0, 255, 0),
            (bx, by, int(bmw * (boss.health / boss.max_health)), bh),
        )
