import math
from typing import Any, Iterable

import pygame

from ...core.config import config as Config
from ...systems.targeting import is_targetable, target_point


class HomingBullet:
    """Tiro teleguiado com vida consumível que é reduzida pelo dano causado.

    Sem tempo de morte fixo: o projétil vive até acertar algo (consume_life)
    ou sair da tela. Cada instância pode ter um alvo fixo (locked_target) para
    garantir que múltiplos projéteis simultâneos não persigam o mesmo inimigo.

    Interfaces esperadas pelo sistema de colisões:
    - atributos: x, y, w, h, rect, damage, life
    - métodos: update(dt, enemies), consume_life(amount), draw(surface)
    """

    def __init__(
        self,
        x: float,
        y: float,
        damage: int = 10,
        lifetime: float = 6.0,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        max_life: int = 100,
        homing_speed: float | None = None,
        turn_rate: float = 5.0,
        locked_target: Any | None = None,
        source_ship: Any | None = None,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.damage = int(damage)
        self.max_life = int(max_life)
        self.life = float(self.max_life)
        self.dead = False
        self.lifetime = float(lifetime)
        self.age = 0.0
        self.is_side_scroll = is_side_scroll
        # Alvo fixo: quando definido, o projétil ignora outros inimigos enquanto
        # o alvo estiver vivo. Ao morrer, cai no _find_best_target normal.
        self.locked_target: Any | None = locked_target
        # Nave que originou o projétil. Em coop, evita que P1 e P2 (ambos
        # Caçador) compartilhem o mesmo gate de "homing já em tela".
        self.source_ship: Any | None = source_ship

        speed = (
            homing_speed
            if homing_speed is not None
            else float(getattr(Config, "HOMING_BULLET_SPEED", 300))
        )
        self.homing_speed = float(speed)
        self.turn_rate = float(turn_rate)

        # Size and collision rect
        self.w = 10
        self.h = 10
        # `x`/`y` chegam como o CENTRO de onde o tiro sai (a boca do canhão, via
        # `Ship._muzzle_positions`) e o rect é ancorado no canto — a conversão
        # é aqui, como em `Bullet._anchor_on_center`. Sem ela o projétil nasce
        # 5px deslocado nos dois eixos, e o desvio muda de lado conforme a nave
        # gira, porque a boca gira e o deslocamento não.
        self.x -= self.w / 2.0
        self.y -= self.h / 2.0
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Initial velocity
        if direction:
            dx, dy = direction
            mag = (dx * dx + dy * dy) ** 0.5 or 1.0
            self.vx = dx / mag * self.homing_speed
            self.vy = dy / mag * self.homing_speed
        else:
            # Default upward
            self.vx = 0.0
            self.vy = -self.homing_speed

        # Track hits this frame to avoid multi-hit
        self.hit_this_frame: set[int] = set()

    def consume_life(self, amount: float) -> None:
        self.life = max(0.0, self.life - float(amount))
        if self.life <= 0.0:
            self.dead = True

    def _target_center(self, target: Any) -> tuple[float, float] | None:
        """Ponto de mira do alvo via geometria precisa compartilhada.

        Essencial para o boss da Serpente, cujo ``(x, y, w, h)`` é um bound
        fixo de tela inteira: ``target_point`` segue a cabeça via
        ``collision_circle``. Mirar em ``x + w/2`` levaria o projétil a um
        ponto invisível no topo central da tela.
        """
        return target_point(target)

    def _find_best_target(self, enemies: Iterable[Any]) -> Any | None:
        best = None
        best_d = float("inf")
        for e in enemies:
            # Ignora mortos e invulneráveis (boss em entrada/fase protegida).
            if not is_targetable(e):
                continue
            center = self._target_center(e)
            if center is None:
                continue
            cx, cy = center
            d = (cx - (self.x + self.w / 2)) ** 2 + (cy - (self.y + self.h / 2)) ** 2
            if d < best_d:
                best_d = d
                best = e
        return best

    def _is_off_screen(self, screen_w: int, screen_h: int) -> bool:
        """Verifica se o projétil saiu completamente da tela."""
        return (
            self.x + self.w < 0
            or self.x > screen_w
            or self.y + self.h < 0
            or self.y > screen_h
        )

    def update(self, dt: float, enemies: list[Any] | None = None) -> None:
        if self.dead:
            return

        self.age += dt
        if self.age >= self.lifetime:
            self.dead = True
            return

        # Morte por saída de tela.
        sw = int(getattr(Config, "SCREEN_WIDTH", 1600))
        sh = int(getattr(Config, "SCREEN_HEIGHT", 900))
        if self._is_off_screen(sw, sh):
            self.dead = True
            return

        # Homing logic: preferir locked_target se ainda alvejável, senão buscar
        # o mais próximo. Re-adquire se o alvo morreu OU ficou invulnerável
        # (ex.: cabeça da Serpente volta a ficar protegida).
        if enemies:
            if self.locked_target is not None and not is_targetable(
                self.locked_target
            ):
                self.locked_target = None
            target = (
                self.locked_target
                if self.locked_target is not None
                else self._find_best_target(enemies)
            )
            center = self._target_center(target) if target is not None else None
            if center is not None:
                tx, ty = center
                cx = self.x + self.w / 2
                cy = self.y + self.h / 2
                desired = math.atan2(ty - cy, tx - cx)
                current = (
                    math.atan2(self.vy, self.vx)
                    if (self.vx or self.vy)
                    else -math.pi / 2
                )
                diff = (desired - current + math.pi) % (2 * math.pi) - math.pi
                max_turn = self.turn_rate * dt
                if diff > max_turn:
                    diff = max_turn
                elif diff < -max_turn:
                    diff = -max_turn
                angle = current + diff
                self.vx = math.cos(angle) * self.homing_speed
                self.vy = math.sin(angle) * self.homing_speed

        # Integrate position
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def draw(self, surface: pygame.Surface) -> None:
        alpha = int(200 * max(0.0, min(1.0, self.life / float(self.max_life))))
        col = (0, 200, 255)
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        pygame.draw.circle(
            s, (col[0], col[1], col[2], alpha), (self.w // 2, self.h // 2), self.w // 2
        )
        surface.blit(s, (int(self.x), int(self.y)))
