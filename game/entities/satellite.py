import random
from typing import TYPE_CHECKING, Dict, List, Optional

import pygame

from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class SatelliteFragment(EnemyHitMixin):
    """
    Fragmento de Satélite — destroços que surgem ao destruir um satélite ou,
    naturalmente, como lixo espacial à deriva (ver `spawn_ambient`).
    """

    TARGET_SIZE = 48  # Fragmentos são menores

    # Cache de imagem por índice de fragmento: evita reler o PNG do disco a cada
    # spawn (relevante agora que aparecem como lixo espacial recorrente).
    _image_cache: Dict[int, pygame.Surface] = {}

    @classmethod
    def _get_image(cls, fragment_idx: int) -> pygame.Surface:
        cached = cls._image_cache.get(fragment_idx)
        if cached is not None:
            return cached
        # Caminho resolvido via BASE_DIR (não relativo ao CWD). Um caminho
        # relativo "game/assets/..." só funcionava rodando da raiz do repo; na
        # build distribuída (executada de outra pasta, ex.: Downloads) dava
        # FileNotFoundError e derrubava o jogo ao spawnar o fragmento na fase de
        # atmosfera. `get_image` ainda traz fallback resiliente (Surface vazia)
        # em vez de crashar — mesmo padrão do resto das entidades.
        path = (
            BASE_DIR
            / "assets"
            / "images"
            / "Sprite_Inimigo_Satélite"
            / f"Fragmento_0{fragment_idx}.png"
        )
        raw_image = get_image(path)
        orig_w, orig_h = raw_image.get_size()
        scale_factor = cls.TARGET_SIZE / max(orig_w, orig_h)
        image = pygame.transform.scale(
            raw_image, (int(orig_w * scale_factor), int(orig_h * scale_factor))
        )
        cls._image_cache[fragment_idx] = image
        return image

    def __init__(
        self,
        x: float,
        y: float,
        fragment_idx: int,
        speed_x: Optional[float] = None,
        speed_y: Optional[float] = None,
    ):
        self.x = x
        self.y = y

        self.base_image = self._get_image(fragment_idx)
        self.image = self.base_image
        self.w, self.h = self.image.get_size()

        # Velocidade: default = explosão (sai do satélite e cai); callers podem
        # sobrescrever (ex.: lixo espacial entrando devagar pela borda).
        self.speed_x = random.uniform(-150, 150) if speed_x is None else speed_x
        self.speed_y = random.uniform(50, 150) if speed_y is None else speed_y

        # Lógica de rotação
        self.angle = random.uniform(0, 360)
        self.rotation_speed = random.uniform(-360, 360)  # Graus por segundo

        self.dead = False
        self.health = Config.SATELLITE_FRAGMENT_HEALTH
        # Sobe de baixo pra cima? (lixo espacial no re-entry). Usado pelo culling
        # do EntityManager para não matar o destroço ao nascer abaixo do rodapé.
        self.inverted_vertical = False

    @classmethod
    def spawn_ambient(cls, inverted_vertical: bool = False) -> "SatelliteFragment":
        """Cria um fragmento como lixo espacial à deriva, entrando por fora da
        tela. Top-down padrão (exiting): entra pelo topo e desce; invertido
        (re-entry/entering): entra pela base e sobe. Deriva lateral leve."""
        fragment_idx = random.randint(1, 4)
        x = float(random.randint(0, max(1, Config.SCREEN_WIDTH - cls.TARGET_SIZE)))
        drift_x = random.uniform(-50, 50)
        speed = random.uniform(80, 140)
        frag = cls(
            x,
            0.0,
            fragment_idx,
            speed_x=drift_x,
            speed_y=(-speed if inverted_vertical else speed),
        )
        frag.y = (
            float(Config.SCREEN_HEIGHT + frag.h)
            if inverted_vertical
            else float(-frag.h * 2)
        )
        frag.inverted_vertical = inverted_vertical
        return frag

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def get_points_value(self) -> int:
        return Config.SATELLITE_FRAGMENT_POINTS

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Atualiza rotação
        self.angle += self.rotation_speed * dt

        # Bounce nas bordas horizontais
        if self.x <= 0:
            self.x = 0
            self.speed_x *= -0.8  # Perde energia no impacto
            self.rotation_speed *= -1 # Inverte rotação no impacto lateral
        elif self.x + self.w >= Config.SCREEN_WIDTH:
            self.x = float(Config.SCREEN_WIDTH - self.w)
            self.speed_x *= -0.8
            self.rotation_speed *= -1

        # Remoção se sair da tela
        if self.y > Config.SCREEN_HEIGHT + self.h * 2 or self.y < -self.h * 2:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
            
        # Desenha rotacionado e centralizado
        rotated_surf = pygame.transform.rotate(self.base_image, self.angle)
        rect = rotated_surf.get_rect(center=(int(self.x + self.w/2), int(self.y + self.h/2)))
        surface.blit(rotated_surf, rect.topleft)

    def should_remove(self) -> bool:
        return self.dead

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult
        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)


class Satellite(EnemyHitMixin):
    """
    Satélite — Inimigo custom para a fase da atmosfera.
    Usa animação de sprites PNG.
    """

    # Frames: satellite_pixel_map_01.png até satellite_pixel_map_05.png
    SPRITE_DIR = "Sprite_Inimigo_Satélite"

    _frames_cache: List[pygame.Surface] = []

    def __init__(self, inverted_vertical: bool = False):
        # Garante que os frames estão carregados
        if not self._frames_cache:
            self.load_animation_frames()
            
        self.frames = self._frames_cache
        self.current_frame = 0
        self.animation_timer = 0.0
        self.animation_direction = 1  # 1 para frente, -1 para trás
        
        # Usa o primeiro frame para definir dimensões
        if self.frames:
            self.image = self.frames[self.current_frame]
            self.w, self.h = self.image.get_size()
        else:
            # Fallback caso falhe o carregamento
            self.image = pygame.Surface((Config.SATELLITE_TARGET_SIZE, Config.SATELLITE_TARGET_SIZE), pygame.SRCALPHA)
            self.w, self.h = Config.SATELLITE_TARGET_SIZE, Config.SATELLITE_TARGET_SIZE

        self.inverted_vertical = inverted_vertical

        # Posição inicial
        margin = 10
        self.x = float(random.randint(margin, Config.SCREEN_WIDTH - self.w - margin))

        if inverted_vertical:
            self.y = float(Config.SCREEN_HEIGHT + self.h)
            self.speed_y = -random.uniform(Config.SATELLITE_SPEED_Y_MIN, Config.SATELLITE_SPEED_Y_MAX)
        else:
            self.y = -float(self.h)
            self.speed_y = random.uniform(Config.SATELLITE_SPEED_Y_MIN, Config.SATELLITE_SPEED_Y_MAX)

        if self.x < Config.SCREEN_WIDTH / 2:
            self.speed_x = random.uniform(Config.SATELLITE_SPEED_X_MIN, Config.SATELLITE_SPEED_X_MAX)
        else:
            self.speed_x = -random.uniform(Config.SATELLITE_SPEED_X_MIN, Config.SATELLITE_SPEED_X_MAX)

        self.dead = False
        self.health = Config.SATELLITE_HEALTH

    @classmethod
    def load_animation_frames(cls) -> List[pygame.Surface]:
        """Carrega e escala os frames da animação mantendo a proporção."""
        if cls._frames_cache:
            return cls._frames_cache
            
        raw_frames = sprite_loader.load_animation_frames(
            base_path=cls.SPRITE_DIR,
            num_frames=5,
            name="Satellite",
            filename_pattern="satellite_pixel_map_0{i}.png"
        )
        
        if not raw_frames:
            return []

        # Calcula a escala baseada na altura desejada (SATELLITE_TARGET_SIZE)
        # Mantendo a proporção original
        cls._frames_cache = []
        for frame in raw_frames:
            orig_w, orig_h = frame.get_size()
            scale_factor = Config.SATELLITE_TARGET_SIZE / orig_h
            new_w = int(orig_w * scale_factor)
            new_h = Config.SATELLITE_TARGET_SIZE
            
            scaled = pygame.transform.scale(frame, (new_w, new_h))
            cls._frames_cache.append(scaled)
            
        return cls._frames_cache

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def get_points_value(self) -> int:
        return Config.SATELLITE_POINTS

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)
        
        # Verifica se morreu para spawnar fragmentos via contexto
        if self.dead and self.health <= 0:
            for i in range(1, 5):
                fragment = SatelliteFragment(self.x + self.w/2, self.y + self.h/2, i)
                ctx.new_enemies.append(fragment)

    def update(self, dt: float) -> None:
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Bounce nas bordas horizontais
        if self.x <= 0:
            self.x = 0
            self.speed_x *= -1
        elif self.x + self.w >= Config.SCREEN_WIDTH:
            self.x = float(Config.SCREEN_WIDTH - self.w)
            self.speed_x *= -1

        # Lógica de animação (Ping-Pong)
        if self.frames and len(self.frames) > 1:
            self.animation_timer += dt
            if self.animation_timer >= Config.SATELLITE_ANIMATION_SPEED:
                self.animation_timer = 0
                
                # Atualiza o índice baseado na direção
                self.current_frame += self.animation_direction
                
                # Inverte a direção se atingir os limites
                if self.current_frame >= len(self.frames) - 1:
                    self.current_frame = len(self.frames) - 1
                    self.animation_direction = -1
                elif self.current_frame <= 0:
                    self.current_frame = 0
                    self.animation_direction = 1
                    
                self.image = self.frames[self.current_frame]

        # Remoção se sair da tela
        if self.inverted_vertical:
            if self.y < -self.h * 2:
                self.dead = True
        else:
            if self.y > Config.SCREEN_HEIGHT + self.h * 2:
                self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead or not self.image:
            return
        surface.blit(self.image, (int(self.x), int(self.y)))

    def should_remove(self) -> bool:
        return self.dead

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

# Registra para o preload
sprite_loader.register("Satellite", Satellite.load_animation_frames)
