import math
from pathlib import Path
from typing import Optional

import pygame

from ..core.assets import get_image
from ..core.config import config as Config
from ..core.sound import sound_manager
from .alien import Alien
from .explosive_mine import ExplosiveMine
from .eye_enemy import EyeEnemy
from .meteor import Meteor
from .mini_ship_bullet import MiniShipBullet
from .ship import Ship
from .stone_sentry import StoneSentry


_SPRITE_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "icons" / "mini_ship.png"
)


_MAX_TARGETING_RANGE_SQ = 400 * 400


class MiniShip:
    # Sprites pré-escalados e pré-rotacionados (cache de classe para não
    # recriar a cada instância). ``_sprite_top_down`` é o sprite original
    # apontando para cima; ``_sprite_side_scroll`` é rotacionado 90° para
    # apontar à direita nas fases de scroll horizontal.
    _sprite_top_down: Optional[pygame.Surface] = None
    _sprite_side_scroll: Optional[pygame.Surface] = None

    @classmethod
    def _ensure_sprites(cls, size: int) -> None:
        if cls._sprite_top_down is not None:
            return
        raw = get_image(_SPRITE_PATH)
        scaled = pygame.transform.smoothscale(raw, (size, size))
        cls._sprite_top_down = scaled
        # Rotação negativa em pygame = sentido horário; -90 leva o topo
        # do sprite para o lado direito.
        cls._sprite_side_scroll = pygame.transform.rotate(scaled, -90)

    def __init__(
        self,
        player_ship: Ship,
        side: str,
        is_side_scroll: bool = False,
        permanent: bool = False,
    ):
        self.player = player_ship
        self.side = side  # 'left' or 'right'
        self.is_side_scroll = is_side_scroll
        # `permanent` = não é removida quando o timer do powerup `mini_ships`
        # expira. Usado pela nave Engenheiro.
        self.permanent = permanent
        self.w = 20
        self.h = 20
        self._ensure_sprites(self.w)
        self.x = self.player.x
        self.y = self.player.y
        self.shoot_cooldown = 0.75
        self.shoot_timer = self.shoot_cooldown

        self.target_offset_x = 0
        self.target_offset_y = 0
        self.set_orientation(is_side_scroll)

    def set_orientation(self, is_side_scroll: bool) -> None:
        """Atualiza offsets de formação conforme o modo da fase."""
        self.is_side_scroll = is_side_scroll

        if self.is_side_scroll:
            # Em side-scroll, escolta em coluna (acima/abaixo) um pouco atrás da nave.
            self.target_offset_x = -34
            self.target_offset_y = -34 if self.side == "left" else 34
        else:
            # Em top-down, escolta lateral clássica.
            self.target_offset_x = -40 if self.side == "left" else 40
            self.target_offset_y = 10

    def update(
        self,
        dt: float,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry],
        bullets: list[MiniShipBullet],
    ):
        # Movement
        target_x = self.player.x + self.player.w / 2 + self.target_offset_x - self.w / 2
        target_y = self.player.y + self.player.h / 2 + self.target_offset_y - self.h / 2

        # Simple lerp for smooth following
        self.x += (target_x - self.x) * 7 * dt
        self.y += (target_y - self.y) * 7 * dt

        # Shooting
        self.shoot_timer -= dt
        if self.shoot_timer <= 0:
            nearest_enemy = self._find_nearest_enemy(enemies)
            if nearest_enemy:
                self.shoot(nearest_enemy, bullets)
                self.shoot_timer = self.shoot_cooldown

    def _find_nearest_enemy(
        self, enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry]
    ) -> Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry | None:
        from ..systems.targeting import find_nearest_in_list

        return find_nearest_in_list(
            self.x, self.y, enemies, max_range_sq=_MAX_TARGETING_RANGE_SQ
        )

    def shoot(
        self,
        target: Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry,
        bullets: list[MiniShipBullet],
    ):
        if isinstance(target, ExplosiveMine):
            target_cx, target_cy = target.x, target.y
        else:
            target_cx, target_cy = target.x + target.w / 2, target.y + target.h / 2

        if self.is_side_scroll:
            origin_x = self.x + self.w
            origin_y = self.y + self.h / 2
        else:
            origin_x = self.x + self.w / 2
            origin_y = self.y

        angle = math.atan2(target_cy - origin_y, target_cx - origin_x)
        bullet_speed = Config.BULLET_SPEED * 1.2
        vx = math.cos(angle) * bullet_speed
        vy = math.sin(angle) * bullet_speed

        sound_manager.play_shot()

        bullets.append(
            MiniShipBullet(
                origin_x,
                origin_y,
                vx,
                vy,
                piercing=self.player.piercing_shot_timer > 0,
            )
        )

    def draw(self, surface: pygame.Surface):
        should_blink = (
            self.player.mini_ships_timer < 3.0 and self.player.mini_ships_timer > 0
        )

        if should_blink and int(pygame.time.get_ticks() / 150) % 2 == 0:
            return

        sprite = (
            self._sprite_side_scroll if self.is_side_scroll else self._sprite_top_down
        )
        if sprite is None:
            return  # fallback defensivo se o asset não carregou.
        # Centraliza o sprite na bounding box (importante no caso side-scroll,
        # onde a rotação pode mudar o tamanho da surface).
        rect = sprite.get_rect(center=(int(self.x + self.w / 2), int(self.y + self.h / 2)))
        surface.blit(sprite, rect)
