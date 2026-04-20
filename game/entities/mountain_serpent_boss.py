import random
from dataclasses import dataclass
from typing import Any, Final

import pygame

from ..core import colors
from ..core.config import config as Config


@dataclass
class SerpentSegment:
    """Um boulder individual do corpo da serpente."""

    y: float
    side: str  # "left" ou "right"
    health: int = 25
    max_health: int = 25
    dead: bool = False
    hit_flash: float = 0.0

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self.hit_flash = 0.18
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def update(self, dt: float) -> None:
        self.hit_flash = max(0.0, self.hit_flash - dt)


class MountainSerpentBoss:
    """Boss serpente de pedra exclusivo das Cordilheiras."""

    HEAD_RADIUS: Final[int] = 30
    SEGMENT_RADIUS: Final[int] = 24
    SEGMENT_COUNT: Final[int] = 5
    SIDE_MARGIN: Final[int] = 52
    SIDE_GAP_Y: Final[int] = 82
    HEAD_Y: Final[int] = 88
    HEAD_SPEED: Final[float] = 24.0

    # HP perdido pela cabeça quando uma coluna inteira de segmentos é destruída
    HEAD_DAMAGE_PER_COLUMN: Final[float] = 0.25  # 25% da vida máxima

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        health: int | None = None,
    ) -> None:
        self.head_x: float = float(x if x is not None else Config.SCREEN_WIDTH / 2)
        self.head_y: float = float(y if y is not None else self.HEAD_Y)
        self.direction: int = random.choice((-1, 1))
        self.speed: float = self.HEAD_SPEED
        self.hit_flash: float = 0.0

        self.left_x: float = float(self.SIDE_MARGIN)
        self.right_x: float = float(Config.SCREEN_WIDTH - self.SIDE_MARGIN)

        # Segmentos independentes: lista por lado
        segment_ys = [
            float(self.head_y + 80 + i * self.SIDE_GAP_Y)
            for i in range(self.SEGMENT_COUNT)
        ]
        self.left_segments: list[SerpentSegment] = [
            SerpentSegment(y=y, side="left") for y in segment_ys
        ]
        self.right_segments: list[SerpentSegment] = [
            SerpentSegment(y=y, side="right") for y in segment_ys
        ]

        # Rastrear quais colunas já causaram dano à cabeça
        self._left_column_damaged: bool = False
        self._right_column_damaged: bool = False

        self.health: int = health if health is not None else 320
        self.max_health: int = self.health
        self.dead: bool = False
        self.floating_squares: list[Any] = []

        self._recalc_bounds()

    # ------------------------------------------------------------------
    # Propriedades de conveniência (mantém compatibilidade com código antigo)
    # ------------------------------------------------------------------

    @property
    def segment_ys(self) -> list[float]:
        """Retorna as posições Y dos segmentos (compatibilidade)."""
        return [seg.y for seg in self.left_segments]

    # ------------------------------------------------------------------
    # Bounds / Rect
    # ------------------------------------------------------------------

    def _recalc_bounds(self) -> None:
        top = int(self.head_y - self.HEAD_RADIUS)

        # Calcular bottom considerando apenas segmentos vivos
        alive_ys = [
            seg.y for seg in self.left_segments + self.right_segments if not seg.dead
        ]
        if alive_ys:
            bottom = int(max(alive_ys) + self.SEGMENT_RADIUS)
        else:
            bottom = int(self.head_y + self.HEAD_RADIUS)

        left = int(self.left_x - self.SEGMENT_RADIUS)
        right = int(self.right_x + self.SEGMENT_RADIUS)

        self.x = float(left)
        self.y = float(top)
        self.w = max(1, right - left)
        self.h = max(1, bottom - top)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    # ------------------------------------------------------------------
    # Pontos / hitboxes
    # ------------------------------------------------------------------

    def get_points_value(self) -> int:
        return 850

    def get_ship_contact_hitboxes(self) -> tuple[pygame.Rect, ...]:
        """Retorna hitboxes individuais para colisão com a nave."""
        if self.dead:
            return ()

        hitboxes: list[pygame.Rect] = []

        # Cabeça
        hitboxes.append(
            pygame.Rect(
                int(self.head_x - self.HEAD_RADIUS),
                int(self.head_y - self.HEAD_RADIUS),
                self.HEAD_RADIUS * 2,
                self.HEAD_RADIUS * 2,
            )
        )

        # Segmentos vivos
        for seg in self.left_segments:
            if not seg.dead:
                hitboxes.append(
                    pygame.Rect(
                        int(self.left_x - self.SEGMENT_RADIUS),
                        int(seg.y - self.SEGMENT_RADIUS),
                        self.SEGMENT_RADIUS * 2,
                        self.SEGMENT_RADIUS * 2,
                    )
                )
        for seg in self.right_segments:
            if not seg.dead:
                hitboxes.append(
                    pygame.Rect(
                        int(self.right_x - self.SEGMENT_RADIUS),
                        int(seg.y - self.SEGMENT_RADIUS),
                        self.SEGMENT_RADIUS * 2,
                        self.SEGMENT_RADIUS * 2,
                    )
                )

        return tuple(hitboxes)

    def get_segment_hitboxes(self) -> list[tuple[pygame.Rect, "SerpentSegment"]]:
        """
        Retorna lista de (Rect, segmento) apenas para boulders vivos.

        A cabeça é imune a projéteis — só recebe dano ao destruir uma coluna inteira.
        Cada Rect tem exatamente o diâmetro do círculo desenhado (SEGMENT_RADIUS * 2).
        """
        if self.dead:
            return []

        result: list[tuple[pygame.Rect, SerpentSegment]] = []

        for seg in self.left_segments:
            if not seg.dead:
                result.append(
                    (
                        pygame.Rect(
                            int(self.left_x - self.SEGMENT_RADIUS),
                            int(seg.y - self.SEGMENT_RADIUS),
                            self.SEGMENT_RADIUS * 2,
                            self.SEGMENT_RADIUS * 2,
                        ),
                        seg,
                    )
                )
        for seg in self.right_segments:
            if not seg.dead:
                result.append(
                    (
                        pygame.Rect(
                            int(self.right_x - self.SEGMENT_RADIUS),
                            int(seg.y - self.SEGMENT_RADIUS),
                            self.SEGMENT_RADIUS * 2,
                            self.SEGMENT_RADIUS * 2,
                        ),
                        seg,
                    )
                )

        return result

    # ------------------------------------------------------------------
    # Dano
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> None:
        """Dano direto à cabeça."""
        if self.dead:
            return
        self.health -= amount
        self.hit_flash = 0.2
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def take_segment_damage(self, segment: SerpentSegment, amount: int) -> None:
        """
        Aplica dano a um segmento individual.

        Se todos os segmentos de uma coluna morrerem pela primeira vez,
        a cabeça perde HEAD_DAMAGE_PER_COLUMN da sua vida máxima.
        """
        if self.dead or segment.dead:
            return

        segment.take_damage(amount)

        # Verificar se uma coluna inteira acabou de ser destruída
        self._check_column_cleared()

    def _check_column_cleared(self) -> None:
        """Aplica dano de coluna à cabeça quando todos os segmentos de um lado morrem."""
        if not self._left_column_damaged and all(
            seg.dead for seg in self.left_segments
        ):
            self._left_column_damaged = True
            penalty = int(self.max_health * self.HEAD_DAMAGE_PER_COLUMN)
            self.take_damage(penalty)

        if not self._right_column_damaged and all(
            seg.dead for seg in self.right_segments
        ):
            self._right_column_damaged = True
            penalty = int(self.max_health * self.HEAD_DAMAGE_PER_COLUMN)
            self.take_damage(penalty)

    # ------------------------------------------------------------------
    # Update / Draw
    # ------------------------------------------------------------------

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> tuple[list[Any], list[Any]]:
        if self.dead:
            return [], []

        self.hit_flash = max(0.0, self.hit_flash - dt)

        # Atualizar flash dos segmentos
        for seg in self.left_segments + self.right_segments:
            seg.update(dt)

        self.head_x += self.direction * self.speed * dt

        if self.head_x <= self.left_x + self.HEAD_RADIUS:
            self.head_x = self.left_x + self.HEAD_RADIUS
            self.direction = 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS:
            self.head_x = self.right_x - self.HEAD_RADIUS
            self.direction = -1

        self._recalc_bounds()
        return [], []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        body_color = (106, 76, 125)
        edge_color = (42, 24, 55)
        highlight_color = (224, 126, 116)
        glow_color = (255, 205, 125)
        dead_color = (55, 45, 55)  # tom acinzentado para slots vazios
        dead_edge_color = (30, 22, 38)

        # ── Segmentos laterais ──────────────────────────────────────────
        for i, (left_seg, right_seg) in enumerate(
            zip(self.left_segments, self.right_segments)
        ):
            for seg, sx in ((left_seg, self.left_x), (right_seg, self.right_x)):
                cx, cy = int(sx), int(seg.y)

                if seg.dead:
                    # Slot vazio: apenas contorno escuro pequeno (pedaços destruídos)
                    pygame.draw.circle(
                        surface, dead_edge_color, (cx, cy), self.SEGMENT_RADIUS // 2
                    )
                    continue

                # Flash ao tomar dano
                seg_body = body_color
                if seg.hit_flash > 0.0:
                    seg_body = tuple(
                        min(255, int(c + (255 - c) * seg.hit_flash)) for c in seg_body
                    )

                # Boulder principal
                pygame.draw.circle(
                    surface, edge_color, (cx, cy), self.SEGMENT_RADIUS + 3
                )
                pygame.draw.circle(surface, seg_body, (cx, cy), self.SEGMENT_RADIUS)
                pygame.draw.circle(
                    surface, highlight_color, (cx, cy), self.SEGMENT_RADIUS // 2
                )

                # ── Mini barra de vida do segmento ──
                bar_w = self.SEGMENT_RADIUS * 2
                bar_h = 4
                bar_x = cx - self.SEGMENT_RADIUS
                bar_y = cy - self.SEGMENT_RADIUS - 8
                pygame.draw.rect(
                    surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h)
                )
                if seg.max_health > 0:
                    life_w = max(0, int(bar_w * (seg.health / seg.max_health)))
                    bar_color = (
                        (80, 220, 80)
                        if seg.health > seg.max_health * 0.5
                        else (220, 160, 40)
                        if seg.health > seg.max_health * 0.25
                        else (220, 60, 60)
                    )
                    pygame.draw.rect(surface, bar_color, (bar_x, bar_y, life_w, bar_h))

        # ── Cabeça ──────────────────────────────────────────────────────
        head_body_color = body_color
        if self.hit_flash > 0.0:
            head_body_color = tuple(
                min(255, int(c + (255 - c) * self.hit_flash)) for c in head_body_color
            )

        head_center = (int(self.head_x), int(self.head_y))
        pygame.draw.circle(surface, edge_color, head_center, self.HEAD_RADIUS + 4)
        pygame.draw.circle(surface, head_body_color, head_center, self.HEAD_RADIUS)
        pygame.draw.circle(surface, glow_color, head_center, self.HEAD_RADIUS // 2)

        # Olhos
        pygame.draw.circle(
            surface,
            colors.YELLOW,
            (int(self.head_x - 10), int(self.head_y - 6)),
            5,
        )
        pygame.draw.circle(
            surface,
            colors.YELLOW,
            (int(self.head_x + 10), int(self.head_y - 6)),
            5,
        )
        pygame.draw.circle(
            surface,
            colors.BLACK,
            (int(self.head_x - 10), int(self.head_y - 6)),
            2,
        )
        pygame.draw.circle(
            surface,
            colors.BLACK,
            (int(self.head_x + 10), int(self.head_y - 6)),
            2,
        )

        # ── Barra de vida da cabeça ──────────────────────────────────────
        bar_w = 140
        bar_h = 8
        bar_x = int(self.head_x - bar_w / 2)
        bar_y = int(self.head_y - self.HEAD_RADIUS - 18)
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        if self.max_health > 0:
            life_w = int(bar_w * (self.health / self.max_health))
            pygame.draw.rect(surface, glow_color, (bar_x, bar_y, life_w, bar_h))
            pygame.draw.rect(surface, colors.WHITE, (bar_x, bar_y, bar_w, bar_h), 2)
