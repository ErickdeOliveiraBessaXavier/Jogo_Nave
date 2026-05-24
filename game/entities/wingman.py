import math
import random
from pathlib import Path
from typing import Any, Optional, List

import pygame

from ..core.assets import get_image
from ..core.config import config as Config
from ..core.sound import sound_manager
from .mini_ship_bullet import MiniShipBullet

_SPRITE_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "icons" / "mini_ship.png"
)

class Wingman:
    _sprite: Optional[pygame.Surface] = None

    @classmethod
    def _ensure_sprite(cls, size: int) -> None:
        if cls._sprite is not None:
            return
        raw = get_image(_SPRITE_PATH)
        cls._sprite = pygame.transform.smoothscale(raw, (size, size))

    def __init__(self, player: Any, duration: float):
        self.player = player
        self.w, self.h = 24, 24
        self._ensure_sprite(self.w)
        
        # Inicia ao lado do jogador
        side_offset = 50 if random.random() > 0.5 else -50
        self.x = player.x + side_offset
        self.y = player.y + random.uniform(-20, 20)
        
        self.vx = 0.0
        self.vy = 0.0
        self.speed = 450.0
        self.turn_rate = 9.0
        
        self.duration = duration
        self.timer = duration
        self.dead = False
        
        self.shoot_cooldown = 0.4
        self.shoot_timer = 0.0
        
        self.target = None
        self.state = "FOLLOW"  # "FOLLOW" ou "HUNT"
        
        # Lógica de rotação
        self.current_angle = 270.0 # Olhando para cima inicialmente
        self.target_angle = 270.0
        
        # Lógica de Animação de Nascimento
        self.spawn_timer = 0.0
        self.spawn_duration = 0.8
        self.scale = 0.0
        
        # Offset suave para o modo FOLLOW
        self.follow_offset_x = side_offset
        self.follow_offset_y = 60

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float, enemies: List[Any], bullets: List[Any]):
        self.timer -= dt
        if self.timer <= 0:
            self.dead = True
            return

        # Animação de nascimento
        if self.spawn_timer < self.spawn_duration:
            self.spawn_timer += dt
            self.scale = min(1.0, self.spawn_timer / self.spawn_duration)
            # Não ataca nem persegue enquanto está nascendo
            self._follow_behavior(dt)
            self.x += self.vx * dt
            self.y += self.vy * dt
            return

        self.scale = 1.0

        # Busca alvo se não tiver um ou se o atual morreu
        if not self.target or getattr(self.target, "dead", False):
            self.target = self._find_target(enemies)
        
        if self.target:
            self.state = "HUNT"
        else:
            self.state = "FOLLOW"

        if self.state == "HUNT":
            self._hunt_behavior(dt)
        else:
            self._follow_behavior(dt)

        # Integração de movimento
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Atualizar ângulo visual
        if self.state == "HUNT" and self.target:
            tx = getattr(self.target, "x", 0) + getattr(self.target, "w", 0) / 2
            ty = getattr(self.target, "y", 0) + getattr(self.target, "h", 0) / 2
            dx = tx - (self.x + self.w / 2)
            dy = ty - (self.y + self.h / 2)
            # No pygame, 0 é direita, 90 é baixo. Rotate usa graus (anti-horário)
            # atan2 retorna radianos (-PI a PI)
            self.target_angle = math.degrees(-math.atan2(dy, dx))
        elif math.hypot(self.vx, self.vy) > 10:
            self.target_angle = math.degrees(-math.atan2(self.vy, self.vx))
        else:
            self.target_angle = 90.0 # Olhando para cima padrão

        # Interpolação suave do ângulo (evita snaps bruscos)
        angle_diff = (self.target_angle - self.current_angle + 180) % 360 - 180
        self.current_angle += angle_diff * 10 * dt

        # Limites da tela
        margin = 20
        self.x = max(margin, min(Config.SCREEN_WIDTH - self.w - margin, self.x))
        self.y = max(margin, min(Config.SCREEN_HEIGHT - self.h - margin, self.y))

        # Disparo
        self.shoot_timer -= dt
        if self.state == "HUNT" and self.shoot_timer <= 0 and self.target:
            self._shoot(bullets)
            self.shoot_timer = self.shoot_cooldown

    def _find_target(self, enemies: List[Any]) -> Any:
        best = None
        best_d = 600 * 600 # Alcance máximo de detecção
        for e in enemies:
            if getattr(e, "dead", False):
                continue
            # Ignorar alguns tipos se necessário, mas geralmente queremos atacar tudo que for hostil
            ex = getattr(e, "x", 0) + getattr(e, "w", 0) / 2
            ey = getattr(e, "y", 0) + getattr(e, "h", 0) / 2
            dx = ex - (self.x + self.w / 2)
            dy = ey - (self.y + self.h / 2)
            d = dx * dx + dy * dy
            if d < best_d:
                best_d = d
                best = e
        return best

    def _hunt_behavior(self, dt: float):
        if not self.target:
            return
            
        tx = getattr(self.target, "x", 0) + getattr(self.target, "w", 0) / 2
        ty = getattr(self.target, "y", 0) + getattr(self.target, "h", 0) / 2
        
        # Mantém uma distância segura enquanto persegue
        dx = tx - (self.x + self.w / 2)
        dy = ty - (self.y + self.h / 2)
        dist = math.hypot(dx, dy) or 1.0
        
        # Se estiver muito perto, tenta manter distância; se longe, aproxima
        target_dist = 150.0 # Feedback anterior: agressividade aumentada
        if dist > target_dist:
            desired_vx = (dx / dist) * self.speed
            desired_vy = (dy / dist) * self.speed
        else:
            # Orbita ou flutua por perto
            desired_vx = (-dy / dist) * self.speed * 0.5
            desired_vy = (dx / dist) * self.speed * 0.5
        
        self.vx += (desired_vx - self.vx) * self.turn_rate * dt
        self.vy += (desired_vy - self.vy) * self.turn_rate * dt

    def _follow_behavior(self, dt: float):
        # Acompanha o jogador
        tx = self.player.x + self.player.w / 2 + self.follow_offset_x
        ty = self.player.y + self.player.h / 2 + self.follow_offset_y
        
        dx = tx - (self.x + self.w / 2)
        dy = ty - (self.y + self.h / 2)
        dist = math.hypot(dx, dy)
        
        if dist > 20:
            follow_speed = self.speed * 0.8
            desired_vx = (dx / dist) * follow_speed
            desired_vy = (dy / dist) * follow_speed
            self.vx += (desired_vx - self.vx) * (self.turn_rate * 0.5) * dt
            self.vy += (desired_vy - self.vy) * (self.turn_rate * 0.5) * dt
        else:
            self.vx *= (1 - 4 * dt)
            self.vy *= (1 - 4 * dt)

    def _shoot(self, bullets: List[Any]):
        if not self.target:
            return
        
        tx = getattr(self.target, "x", 0) + getattr(self.target, "w", 0) / 2
        ty = getattr(self.target, "y", 0) + getattr(self.target, "h", 0) / 2
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        
        angle = math.atan2(ty - cy, tx - cx)
        b_speed = Config.BULLET_SPEED * 1.1
        
        # Usa MiniShipBullet para consistência
        bullets.append(
            MiniShipBullet(
                cx - 2,
                cy - 2,
                math.cos(angle) * b_speed,
                math.sin(angle) * b_speed,
                damage=Config.MINI_SHIP_BULLET_DAMAGE * 1.5,  # Wingman é um pouco mais forte
                owner_ship=self.player,
            )
        )
        sound_manager.play_shot()

    def draw(self, surface: pygame.Surface):
        if self._sprite:
            # Pisca quando está prestes a expirar (últimos 3 segundos)
            if self.timer < 3.0 and int(self.timer * 10) % 2 == 0:
                return
            
            # Aplicar rotação ao sprite (ajustando 90 graus pois o original olha para cima)
            rotated_sprite = pygame.transform.rotate(self._sprite, self.current_angle - 90)
            
            # Desenha com um brilho ciano suave ao redor
            rect = rotated_sprite.get_rect(center=(int(self.x + self.w / 2), int(self.y + self.h / 2)))
            
            surface.blit(rotated_sprite, rect)
