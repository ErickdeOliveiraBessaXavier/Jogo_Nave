import math
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Tuple

import pygame

from ..core.player_tint import player_sprite
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..systems import aiming
from ..systems.targeting import find_nearest_enemy, is_targetable, target_point
from .alien import Alien
from .explosive_mine import ExplosiveMine
from .eye_enemy import EyeEnemy
from .meteor import Meteor
from .mini_ship_bullet import MiniShipBullet
from .ship import Ship
from .stone_sentry import StoneSentry
from ..core.fire_timer import FireTimer

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager

_SPRITE_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "icons" / "mini_ship.png"
)


_MAX_TARGETING_RANGE_SQ = 400 * 400


class MiniShip:
    # Sprite-base pré-escalado apontando para cima (cache de classe para não
    # recriar a cada instância). A rotação na direção do alvo é aplicada no
    # desenho via ``aiming.rotate_sprite_up``.
    #
    # Chaveado por (tamanho, jogador): as minis do P2 são recoloridas junto com
    # a nave dele, então não podem dividir uma única surface de classe.
    _sprites: Dict[Tuple[int, int], pygame.Surface] = {}

    @classmethod
    def _get_sprite(cls, size: int, player_index: int) -> pygame.Surface:
        key = (size, player_index)
        sprite = cls._sprites.get(key)
        if sprite is None:
            raw = player_sprite(_SPRITE_PATH, player_index, cast_neutral=True)
            sprite = pygame.transform.smoothscale(raw, (size, size))
            cls._sprites[key] = sprite
        return sprite

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
        self._sprite = self._get_sprite(self.w, player_ship.player_index)
        self.x = self.player.x
        self.y = self.player.y
        self.shoot_cooldown = 0.75
        # Cadência pelo FireTimer compartilhado: o padrão antigo
        # (`shoot_timer = shoot_cooldown` após atirar) descartava a sobra do
        # frame e fazia a mini-nave atirar abaixo da cadência configurada.
        self._fire_timer = FireTimer()

        self.target_offset_x = 0
        self.target_offset_y = 0
        self.set_orientation(is_side_scroll)

        # Alvo cacheado entre frames (re-adquirido quando morre ou sai do
        # alcance) e estado de rotação do sprite na direção da mira.
        self.target: Optional[Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry] = None
        self.current_angle = self._idle_angle
        self.target_angle = self._idle_angle

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

    @property
    def _idle_angle(self) -> float:
        """Orientação de repouso (sem alvo): direita em side-scroll, cima em top-down."""
        return aiming.ANGLE_RIGHT if self.is_side_scroll else aiming.ANGLE_UP

    def update(
        self,
        dt: float,
        entity_manager: "EntityManager",
        bullets: list[MiniShipBullet],
    ):
        # Movement
        target_x = self.player.x + self.player.w / 2 + self.target_offset_x - self.w / 2
        target_y = self.player.y + self.player.h / 2 + self.target_offset_y - self.h / 2

        # Simple lerp for smooth following
        self.x += (target_x - self.x) * 7 * dt
        self.y += (target_y - self.y) * 7 * dt

        self._acquire_target(entity_manager)

        # Orientação: gira na direção do alvo; sem alvo volta ao repouso.
        if self.target is not None:
            cx, cy = self._aim_point(self.target)
            self.target_angle = aiming.angle_to(
                cx - (self.x + self.w / 2), cy - (self.y + self.h / 2)
            )
        else:
            self.target_angle = self._idle_angle
        self.current_angle = aiming.approach_angle(
            self.current_angle, self.target_angle, dt
        )

        # Shooting
        self._fire_timer.advance(dt, self.shoot_cooldown)
        if self.target is not None and self._fire_timer.consume(self.shoot_cooldown):
            self.shoot(self.target, bullets)

    def _acquire_target(self, entity_manager: "EntityManager") -> None:
        """Mantém o alvo atual enquanto atacável e em alcance; senão re-adquire.

        ``is_targetable`` cobre morte e invulnerabilidade (boss em fase
        protegida), garantindo que o MiniShip largue um alvo que ficou imune.
        """
        current = self.target
        if (
            current is not None
            and is_targetable(current)
            and self._in_range(current)
        ):
            return
        self.target = self._find_nearest_enemy(entity_manager)

    def _in_range(
        self, target: Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry
    ) -> bool:
        cx, cy = self._aim_point(target)
        dx = cx - (self.x + self.w / 2)
        dy = cy - (self.y + self.h / 2)
        return dx * dx + dy * dy <= _MAX_TARGETING_RANGE_SQ

    def _aim_point(
        self, target: Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry
    ) -> tuple[float, float]:
        """Ponto-alvo da mira — usa a geometria precisa compartilhada."""
        return target_point(target) or (target.x, target.y)

    def _find_nearest_enemy(
        self, entity_manager: "EntityManager"
    ) -> Optional[Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry]:
        """Usa a função de targeting compartilhada com range máximo."""
        return find_nearest_enemy(
            self.x, self.y, entity_manager, max_range_sq=_MAX_TARGETING_RANGE_SQ
        )

    def shoot(
        self,
        target: Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry,
        bullets: list[MiniShipBullet],
    ):
        target_cx, target_cy = self._aim_point(target)

        # Dispara do centro; o sprite já aponta para o alvo via rotação.
        origin_x = self.x + self.w / 2
        origin_y = self.y + self.h / 2

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
                owner_ship=self.player,
            )
        )

    def draw(self, surface: pygame.Surface):
        should_blink = (
            self.player.mini_ships_timer < 3.0 and self.player.mini_ships_timer > 0
        )

        if should_blink and int(pygame.time.get_ticks() / 150) % 2 == 0:
            return

        if self._sprite is None:
            return  # fallback defensivo se o asset não carregou.
        # Rotaciona o sprite-base (aponta para cima) na direção da mira.
        sprite = aiming.rotate_sprite_up(self._sprite, self.current_angle)
        # Centraliza na bounding box (a rotação muda o tamanho da surface).
        rect = sprite.get_rect(
            center=(int(self.x + self.w / 2), int(self.y + self.h / 2))
        )
        surface.blit(sprite, rect)
