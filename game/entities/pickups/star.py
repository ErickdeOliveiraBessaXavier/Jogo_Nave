"""Star (Estrela) - Moeda coletável para desbloquear slots de upgrades."""

# math not needed anymore
import random

import pygame

from ...core.assets import BASE_DIR, get_image
from ...core.config import config as Config
from .._shared.attraction_utils import get_attraction_pulse_rect, update_magnetic_attraction


class Star:
    """
    Estrela coletável que serve como moeda para desbloquear slots.

    Usa a imagem icon_star.png com efeitos de rotação e pulsação.
    """

    def __init__(self, x: float, y: float):
        """
        Inicializa uma estrela.

        Args:
            x: Posição x inicial
            y: Posição y inicial
        """
        # Tamanho e posição seguindo mesma lógica do PowerUp
        self.w, self.h = Config.POWERUP_SIZE, Config.POWERUP_SIZE
        self.x: float = float(x)
        self.y: float = float(y)
        self.speed: float = float(Config.POWERUP_SPEED)
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Carregar imagem
        icon_path = BASE_DIR / "assets" / "images" / "icons" / "icon_star.png"
        self.base_image = get_image(icon_path)
        self.current_image = self.base_image

        self.dead: bool = False

        # Animação/pulsação (igual ao PowerUp)
        self.animation_timer: float = 0.0
        self.pulse_scale: float = 1.0

        # Rotação da imagem da estrela
        self.rotation: float = random.uniform(0, 360)
        self.rotation_speed: float = random.uniform(-180, 180)  # graus por segundo

        # Atração magnética
        self._is_being_attracted: bool = False
        self.attraction_shake_timer: float = 0.0

    def update(
        self,
        dt: float,
        screen_width: int = 1600,
        screen_height: int = 900,
        attraction_pos: tuple[float, float] | None = None,
        attraction_mult: float = 1.0,
    ) -> None:
        """
        Atualiza posição e animação da estrela.

        Args:
            dt: Delta time
            screen_width: Largura da tela
            screen_height: Altura da tela
            attraction_pos: Posição do jogador para atração
            attraction_mult: Multiplicador de atração da nave
        """
        update_magnetic_attraction(self, dt, attraction_pos, attraction_mult)

        # Rotação da estrela (imagem interna)
        self.rotation += self.rotation_speed * dt
        self.rotation %= 360
        # Animação de pulsação (igual ao PowerUp)
        self.animation_timer += dt * 5
        self.pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )

        # Atualizar imagem com rotação (sem escala na estrela)
        self.current_image = pygame.transform.rotate(self.base_image, -self.rotation)

        # Remove se sair da tela
        margin = 100
        if (
            self.x < -margin
            or self.x > screen_width + margin
            or self.y > screen_height + margin
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """
        Desenha a estrela usando a imagem icon_star.png com rotação e pulsação.

        Args:
            surface: Superfície do Pygame para desenhar
        """
        if self.dead:
            return

        # Aplicar tremor visual e calcular o retângulo pulsante compartilhado
        _, _, pulse_rect = get_attraction_pulse_rect(self)
        pulse_size = pulse_rect.width

        # Sombra
        shadow_rect = pulse_rect.copy()
        shadow_rect.x += 2
        shadow_rect.y += 2
        pygame.draw.ellipse(surface, (0, 0, 0, 128), shadow_rect)

        # Fundo principal (amarelo dourado)
        pygame.draw.ellipse(surface, pygame.Color(255, 220, 100), pulse_rect)
        # Borda brilhante
        pygame.draw.ellipse(surface, (255, 255, 255), pulse_rect, 2)

        # Desenhar a imagem da estrela centralizada dentro do fundo
        inner_size = int(pulse_size * 0.7)
        star_img = pygame.transform.scale(self.base_image, (inner_size, inner_size))
        star_img = pygame.transform.rotate(star_img, -self.rotation)
        img_rect = star_img.get_rect(center=pulse_rect.center)
        surface.blit(star_img, img_rect)

    def get_rect(self) -> pygame.Rect:
        """
        Retorna o retângulo de colisão da estrela.

        Returns:
            pygame.Rect: Retângulo de colisão baseado na imagem atual
        """
        # Colisão baseada no retângulo atual
        return self.rect.copy()
