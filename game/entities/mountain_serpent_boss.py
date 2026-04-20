import random
from typing import Any, Final

import pygame

from ..core import colors
from ..core.config import config as Config


# ---------------------------------------------------------------------------
# Bloco de pedra independente — tratado como inimigo avulso
# ---------------------------------------------------------------------------

class SerpentBlock:
    """
    Bloco de pedra fixo nas laterais da tela.

    É registrado na lista de inimigos normais do EntityManager e colide com
    balas/laser exatamente como qualquer outro inimigo com HP.

    Quando morrer, notifica o boss (MountainSerpentBoss) para que ele
    contabilize se uma coluna inteira foi destruída.
    """

    RADIUS: Final[int] = 24
    MAX_HEALTH: Final[int] = 25

    def __init__(
        self,
        x: float,
        y: float,
        side: str,          # "left" | "right"
        boss: "MountainSerpentBoss",
    ) -> None:
        self.x = x - self.RADIUS
        self.y = y - self.RADIUS
        self.w = self.RADIUS * 2
        self.h = self.RADIUS * 2
        self.cx = x          # centro X (posição canônica do círculo)
        self.cy = y          # centro Y
        self.side = side
        self.boss = boss

        self.health: int = self.MAX_HEALTH
        self.dead: bool = False
        self._hit_flash: float = 0.0

    # -- Protocolo Enemy ------------------------------------------------

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def get_points_value(self) -> int:
        return 80

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self._hit_flash = 0.18
        if self.health <= 0:
            self.health = 0
            self.dead = True
            # Avisa o boss: "um bloco desta coluna morreu"
            self.boss.on_block_killed(self.side)

    def update(self, dt: float, *_args: Any, **_kwargs: Any) -> None:
        self._hit_flash = max(0.0, self._hit_flash - dt)

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        body_color = (106, 76, 125)
        edge_color = (42, 24, 55)
        highlight_color = (224, 126, 116)

        cx, cy = int(self.cx), int(self.cy)

        # Flash de dano
        draw_color = body_color
        if self._hit_flash > 0.0:
            draw_color = tuple(
                min(255, int(c + (255 - c) * self._hit_flash)) for c in body_color
            )

        pygame.draw.circle(surface, edge_color, (cx, cy), self.RADIUS + 3)
        pygame.draw.circle(surface, draw_color, (cx, cy), self.RADIUS)
        pygame.draw.circle(surface, highlight_color, (cx, cy), self.RADIUS // 2)

        # Barra de vida
        bar_w = self.RADIUS * 2
        bar_h = 4
        bar_x = cx - self.RADIUS
        bar_y = cy - self.RADIUS - 8
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        life_w = max(0, int(bar_w * (self.health / self.MAX_HEALTH)))
        bar_color = (
            (80, 220, 80)
            if self.health > self.MAX_HEALTH * 0.5
            else (220, 160, 40)
            if self.health > self.MAX_HEALTH * 0.25
            else (220, 60, 60)
        )
        pygame.draw.rect(surface, bar_color, (bar_x, bar_y, life_w, bar_h))


# ---------------------------------------------------------------------------
# Boss — apenas a cabeça móvel
# ---------------------------------------------------------------------------

class MountainSerpentBoss:
    """
    Cabeça da Serpente de Pedra (boss das Cordilheiras).

    Responsabilidade desta classe:
      - Mover a cabeça de lado a lado.
      - Receber dano **somente** quando uma coluna inteira de SerpentBlocks
        é destruída (25 % do HP máximo por coluna).
      - Desenhar a cabeça e a barra de HP.

    Os blocos de pedra (SerpentBlock) são entidades separadas gerenciadas
    pelo EntityManager. Ao criar o boss, use ``create_blocks()`` para
    instanciar os blocos e adicioná-los à lista de inimigos.
    """

    HEAD_RADIUS: Final[int] = 30
    SIDE_MARGIN: Final[int] = 52
    HEAD_Y: Final[int] = 88
    HEAD_SPEED: Final[float] = 24.0

    # Dano recebido pela cabeça ao se destruir uma coluna inteira de blocos
    HEAD_DAMAGE_PER_COLUMN: Final[float] = 0.25  # 25 % do HP máximo

    # Layout dos blocos
    BLOCK_COUNT: Final[int] = 5          # blocos por coluna (esq. e dir.)
    BLOCK_START_OFFSET_Y: Final[int] = 80  # distância vertical da cabeça ao 1.º bloco
    BLOCK_GAP_Y: Final[int] = 82          # espaçamento entre blocos

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

        self.left_x: float = float(self.SIDE_MARGIN)
        self.right_x: float = float(Config.SCREEN_WIDTH - self.SIDE_MARGIN)

        self.health: int = health if health is not None else 320
        self.max_health: int = self.health
        self.dead: bool = False
        self.hit_flash: float = 0.0

        # Quantas colunas já causaram dano (máx. 2)
        self._left_column_damaged: bool = False
        self._right_column_damaged: bool = False

        # Contadores de blocos vivos por coluna
        self._left_alive: int = self.BLOCK_COUNT
        self._right_alive: int = self.BLOCK_COUNT

        # Bounds para compatibilidade com código existente
        self.x: float = self.left_x - SerpentBlock.RADIUS
        self.y: float = self.head_y - self.HEAD_RADIUS
        self.w: float = (self.right_x + SerpentBlock.RADIUS) - self.x
        self.h: float = float(self.HEAD_RADIUS * 2)

        self.floating_squares: list[Any] = []

    # ------------------------------------------------------------------
    # Fábrica de blocos — chame logo após criar o boss
    # ------------------------------------------------------------------

    def create_blocks(self) -> list[SerpentBlock]:
        """
        Instancia e retorna todos os SerpentBlocks das duas colunas.

        Adicione o retorno desta função diretamente em
        ``entity_manager.enemies`` (ou equivalente).
        """
        blocks: list[SerpentBlock] = []
        for i in range(self.BLOCK_COUNT):
            cy = self.head_y + self.BLOCK_START_OFFSET_Y + i * self.BLOCK_GAP_Y
            blocks.append(SerpentBlock(self.left_x, cy, "left", self))
            blocks.append(SerpentBlock(self.right_x, cy, "right", self))
        return blocks

    # ------------------------------------------------------------------
    # Callbacks chamados pelos blocos
    # ------------------------------------------------------------------

    def on_block_killed(self, side: str) -> None:
        """
        Chamado por SerpentBlock.take_damage() quando um bloco morre.

        Decrementa o contador do lado correspondente; se a coluna zerar,
        aplica o dano de coluna à cabeça (uma única vez por coluna).
        """
        if self.dead:
            return

        if side == "left":
            self._left_alive = max(0, self._left_alive - 1)
            if self._left_alive == 0 and not self._left_column_damaged:
                self._left_column_damaged = True
                self._apply_column_damage()
        else:
            self._right_alive = max(0, self._right_alive - 1)
            if self._right_alive == 0 and not self._right_column_damaged:
                self._right_column_damaged = True
                self._apply_column_damage()

    def _apply_column_damage(self) -> None:
        penalty = int(self.max_health * self.HEAD_DAMAGE_PER_COLUMN)
        self.take_damage(penalty)

    # ------------------------------------------------------------------
    # Dano direto à cabeça
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self.hit_flash = 0.2
        if self.health <= 0:
            self.health = 0
            self.dead = True

    # ------------------------------------------------------------------
    # Compatibilidade com collisions.py / entity_manager.py existentes
    # ------------------------------------------------------------------

    def get_points_value(self) -> int:
        return 850

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.head_x - self.HEAD_RADIUS),
            int(self.head_y - self.HEAD_RADIUS),
            self.HEAD_RADIUS * 2,
            self.HEAD_RADIUS * 2,
        )

    def get_ship_contact_hitboxes(self) -> tuple[pygame.Rect, ...]:
        """Apenas a cabeça colide com a nave."""
        if self.dead:
            return ()
        return (self.rect,)

    # ------------------------------------------------------------------
    # Update / Draw
    # ------------------------------------------------------------------

    def update(
        self, dt: float, player_x: float = 0.0, player_y: float = 0.0
    ) -> tuple[list[Any], list[Any]]:
        if self.dead:
            return [], []

        self.hit_flash = max(0.0, self.hit_flash - dt)

        self.head_x += self.direction * self.speed * dt

        if self.head_x <= self.left_x + self.HEAD_RADIUS:
            self.head_x = self.left_x + self.HEAD_RADIUS
            self.direction = 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS:
            self.head_x = self.right_x - self.HEAD_RADIUS
            self.direction = -1

        # Atualizar bounds (compatibilidade)
        self.x = self.left_x - SerpentBlock.RADIUS
        self.y = self.head_y - self.HEAD_RADIUS
        self.w = (self.right_x + SerpentBlock.RADIUS) - self.x

        return [], []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        body_color = (106, 76, 125)
        edge_color = (42, 24, 55)
        glow_color = (255, 205, 125)

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
        for dx in (-10, 10):
            pygame.draw.circle(
                surface, colors.YELLOW,
                (int(self.head_x + dx), int(self.head_y - 6)), 5,
            )
            pygame.draw.circle(
                surface, colors.BLACK,
                (int(self.head_x + dx), int(self.head_y - 6)), 2,
            )

        # Barra de vida da cabeça
        bar_w = 140
        bar_h = 8
        bar_x = int(self.head_x - bar_w / 2)
        bar_y = int(self.head_y - self.HEAD_RADIUS - 18)
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        if self.max_health > 0:
            life_w = int(bar_w * (self.health / self.max_health))
            pygame.draw.rect(surface, glow_color, (bar_x, bar_y, life_w, bar_h))
            pygame.draw.rect(surface, colors.WHITE, (bar_x, bar_y, bar_w, bar_h), 2)
