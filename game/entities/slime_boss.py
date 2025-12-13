import pygame
import math
import random
from typing import Optional, List, Any
from ..core import colors
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader
from ..core.assets import get_image


class SlimeBoss:
    """
    Boss Slime - ocupa a parte superior da tela inteira.

    Características:
    - Ocupa toda a largura da tela na parte superior
    - Movimento horizontal suave da esquerda para a direita (um pouco off-screen)
    - Animação com 24 frames
    - Indestrutível por tiros (como SquareMinionBoss)
    - Pode ser destruído apenas colidindo com a nave
    """

    def __init__(self, x: float, y: float, health: int = 50):
        # Posição e tamanho - ocupa toda a largura da tela
        self.screen_width = Config.SCREEN_WIDTH
        self.screen_height = Config.SCREEN_HEIGHT

        # O boss ocupa toda a largura da tela na parte superior
        self.w = self.screen_width
        self.h = 200  # Altura do boss (parte superior da tela)

        # Posição inicial - começa acima da tela
        self.x = 0  # Sempre começa na posição 0 (esquerda da tela)
        self.y = -self.h  # Acima da tela
        self.target_y = 0  # Posição final na parte superior

        # Movimento horizontal
        self.move_speed = 50.0  # Velocidade de movimento horizontal
        self.move_direction = 1  # 1 = direita, -1 = esquerda
        self.move_range = 100  # Quanto pode se mover para fora da tela
        self.left_limit = -self.move_range
        self.right_limit = self.screen_width - self.w + self.move_range

        # Estado
        self.dead = False
        self.health = health
        self.max_health = health
        self.active = False  # Ativo após animação de entrada

        # Animação
        self.sprite_loader = sprite_loader
        self.current_frame = 0
        self.animation_speed = 0.15  # Velocidade da animação
        self.animation_timer = 0.0
        self.frames: List[pygame.Surface] = []

        # Carregar sprites
        self._load_sprites()

        # Entrada na tela
        self.entry_speed = 30.0
        self.entry_complete = False

        # Pontos
        self.points_value = 1000

    def _load_sprites(self):
        """Carrega os 24 frames de animação do boss slime."""
        try:
            base_path = "sprite_boss_03_slime"
            for i in range(1, 25):  # 1 a 24
                frame_path = f"{base_path}/boss_3_gosma_sprite ({i}).png"
                frame = self.sprite_loader.get_sprite(frame_path)
                if frame:
                    # Redimensionar para ocupar toda a largura da tela
                    scaled_frame = pygame.transform.scale(frame, (self.w, self.h))
                    self.frames.append(scaled_frame)
                else:
                    print(f"Warning: Could not load frame {frame_path}")

            if not self.frames:
                # Fallback se nenhum sprite carregar
                self.frames = [pygame.Surface((self.w, self.h))]
                self.frames[0].fill(colors.GREEN)

        except Exception as e:
            print(f"Error loading slime boss sprites: {e}")
            # Fallback
            self.frames = [pygame.Surface((self.w, self.h))]
            self.frames[0].fill(colors.GREEN)

    def update(self, dt: float, player_x: float, player_y: float) -> Optional[List[Any]]:
        """Atualiza o boss slime."""
        if self.dead:
            return None

        # Animação de entrada
        if not self.entry_complete:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.entry_complete = True
                self.active = True
            return None

        # Movimento horizontal suave
        if self.active:
            self.x += self.move_speed * self.move_direction * dt

            # Inverter direção quando atingir os limites
            if self.move_direction > 0 and self.x >= self.right_limit:
                self.move_direction = -1
            elif self.move_direction < 0 and self.x <= self.left_limit:
                self.move_direction = 1

        # Atualizar animação
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.frames)

        return None  # Boss slime não atira

    def draw(self, surface: pygame.Surface):
        """Desenha o boss slime."""
        if self.dead or not self.frames:
            return

        # Desenhar o frame atual
        if self.current_frame < len(self.frames):
            surface.blit(self.frames[self.current_frame], (self.x, self.y))

    def get_rect(self) -> pygame.Rect:
        """Retorna o retângulo de colisão."""
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, damage: int = 1):
        """Boss slime é indestrutível por tiros."""
        # Não perde vida - indestrutível por tiros
        pass

    def get_points_value(self) -> int:
        """Retorna os pontos concedidos ao ser destruído."""
        return self.points_value

    def is_active(self) -> bool:
        """Verifica se o boss está ativo (após entrada completa)."""
        return self.active

    def get_health_percentage(self) -> float:
        """Retorna a porcentagem de vida restante (sempre 100% pois é indestrutível por tiros)."""
        return 1.0</content>
<parameter name="filePath">c:\Users\eobx\OneDrive\Documentos\Jogos_Python\Nave\game\entities\slime_boss.py