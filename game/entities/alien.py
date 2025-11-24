import pygame
import random
from ..core.config import Config
from ..core.assets import get_image, BASE_DIR
from .alien_bullet import AlienBullet
from ..core.sprite_loader import sprite_loader


class Alien:
    # Constantes para dimensões do alien
    ALIEN_WIDTH = 75
    ALIEN_HEIGHT = 58
    
    # Cache de sprites de animação (carregado uma vez)
    _animation_frames: list[pygame.Surface] | None = None

    @classmethod
    def load_animation_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona os sprites de animação uma vez."""
        if cls._animation_frames is not None:
            return cls._animation_frames
        
        frames: list[pygame.Surface] = []
        for i in range(1, 13):
            path = BASE_DIR / "assets" / "images" / "Sprite_Nave_Inimiga_01" / f"nave_inimiga ({i}).png"
            image = get_image(path)
            # Redimensionar para o tamanho do alien
            image = pygame.transform.scale(image, (cls.ALIEN_WIDTH, cls.ALIEN_HEIGHT))
            frames.append(image)
        
        cls._animation_frames = frames
        return frames

    def __init__(self):
        self.w: int
        self.h: int
        self.x: float
        self.y: float
        self.speed_x: float
        self.speed_y: float
        self.dead: bool
        self.shoot_timer: float

        # Atributos para controle por formação
        self.formation_controlled: bool
        self.formation_index: int
        self.formation_angle: float

        # Carregar sprites de animação (usando cache)
        self.animation_frames: list[pygame.Surface]
        
        # Controle de animação
        self.current_frame: int
        self.animation_timer: float
        self.frame_duration: float

        self.w, self.h = self.ALIEN_WIDTH, self.ALIEN_HEIGHT
        self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        self.y = -self.h
        self.speed_x = random.choice([-100, 100])
        self.speed_y = 60
        self.dead = False
        self.shoot_timer = random.uniform(1.5, 3.0)

        # Atributos para controle por formação
        self.formation_controlled = False
        self.formation_index = 0
        self.formation_angle = 0.0

        # Carregar sprites de animação (usando cache)
        self.animation_frames = self.load_animation_frames()
        
        # Controle de animação
        self.current_frame = 0
        self.animation_timer = 0.0
        self.frame_duration = 0.1

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float) -> list[AlienBullet] | None:
        # Se controlado por formação, não move automaticamente
        if self.formation_controlled:
            # Apenas atualiza timer de tiro (o disparo é gerenciado pela Formation)
            self.shoot_timer -= dt
            # Marcar como morto se sair muito da tela (segurança)
            if self.y > Config.SCREEN_HEIGHT + 100 or self.y < -100:
                self.dead = True
            # Atualizar animação
            self.animation_timer += dt
            if self.animation_timer >= self.frame_duration:
                self.animation_timer = 0.0
                self.current_frame = (self.current_frame + 1) % len(self.animation_frames)
            return None

        # Movimento normal (quando não está em formação)
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Inverter direção nas bordas
        if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
            self.speed_x *= -1

        # Marcar como morto se sair da tela
        if self.y > Config.SCREEN_HEIGHT:
            self.dead = True

        # Atirar
        self.shoot_timer -= dt
        if self.shoot_timer <= 0:
            self.shoot_timer = random.uniform(2.0, 4.0)
            return [AlienBullet(self.x + self.w / 2, self.y + self.h)]

        # Atualizar animação
        self.animation_timer += dt
        if self.animation_timer >= self.frame_duration:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

        return None

    def draw(self, surface: pygame.Surface):
        # Verificar se tem alpha definido (para formações com fade-in)
        alpha = getattr(self, "alpha", 255)

        # Obter frame atual
        image = self.animation_frames[self.current_frame]

        # Aplicar alpha se necessário (para formações)
        if alpha < 255:
            image = image.copy()
            image.set_alpha(alpha)

        # Desenhar
        surface.blit(image, (int(self.x), int(self.y)))

    def get_points_value(self) -> int:
        return 150  # Pontos por destruir um alien

# REGISTRAR no sistema de pré-carregamento (fora da classe)
sprite_loader.register("Alien", Alien.load_animation_frames)
