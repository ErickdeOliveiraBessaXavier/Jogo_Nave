"""Star (Estrela) - Moeda coletável para desbloquear slots de upgrades."""

# math not needed anymore
import random

import pygame

from ...core.assets import BASE_DIR, get_image
from ...core.config import config as Config
from .._shared.attraction_utils import (
    get_attraction_pulse_rect,
    update_closing_pull,
    update_magnetic_attraction,
)


class Star:
    """
    Estrela coletável que serve como moeda para desbloquear slots.

    Usa a imagem icon_star.png com efeitos de rotação e pulsação.
    """

    # Duração do fade de encerramento (dissolver) quando não coletada a tempo.
    FADE_OUT_DURATION: float = 0.35

    # Passos de rotação do ícone. 36 passos = 10°: a 180°/s (o máximo sorteado
    # em `rotation_speed`) são 18 trocas por segundo, acima do que o olho
    # distingue de um giro contínuo num ícone de ~17 px.
    _ROT_STEPS: int = 36

    # Cache COMPARTILHADO do ícone já escalado e girado, por (tamanho, passo).
    # Toda estrela parte do MESMO `icon_star.png`, então a chave não precisa
    # identificar a imagem. `inner_size` assume poucos valores (a pulsação varia
    # 1.0–1.2 sobre um tamanho fixo), então na prática são ~6 tamanhos × 36
    # passos.
    #
    # Sem isto, cada estrela pagava `transform.scale` + `transform.rotate` POR
    # FRAME — render por software, o tipo de operação que o WASM cobra caro (a
    # mesma classe de custo do `_PixelGridFont`).
    _icon_cache: dict[tuple[int, int], pygame.Surface] = {}
    _ICON_CACHE_MAX: int = 512

    @classmethod
    def _icon_for(cls, base: pygame.Surface, size: int, rotation: float) -> pygame.Surface:
        """Ícone escalado e girado, memoizado por (tamanho, passo de rotação)."""
        steps = cls._ROT_STEPS
        step = int(rotation / 360.0 * steps) % steps
        key = (size, step)
        img = cls._icon_cache.get(key)
        if img is None:
            scaled = pygame.transform.scale(base, (size, size))
            img = pygame.transform.rotate(scaled, -step * (360.0 / steps))
            # Teto simples: o conjunto de chaves é pequeno e estável, então
            # estourar significa que alguma premissa mudou — limpar tudo é
            # preferível a crescer sem limite no heap do WASM.
            if len(cls._icon_cache) >= cls._ICON_CACHE_MAX:
                cls._icon_cache.clear()
            cls._icon_cache[key] = img
        return img

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

        # Fade de encerramento de fase (dissolver).
        self._fading: bool = False
        self._fade_timer: float = 0.0

    def begin_fade_out(self) -> None:
        """Inicia o dissolver de encerramento (idempotente)."""
        if self._fading or self.dead:
            return
        self._fading = True
        self._fade_timer = self.FADE_OUT_DURATION
        self.attraction_shake_timer = 0.0

    def update(
        self,
        dt: float,
        screen_width: int = 1600,
        screen_height: int = 900,
        attraction_pos: tuple[float, float] | None = None,
        attraction_mult: float = 1.0,
        closing_pull: tuple[float, float] | None = None,
    ) -> None:
        """
        Atualiza posição e animação da estrela.

        Args:
            dt: Delta time
            screen_width: Largura da tela
            screen_height: Altura da tela
            attraction_pos: Posição do jogador para atração
            attraction_mult: Multiplicador de atração da nave
            closing_pull: Alvo do puxão de encerramento de fase (ignora range).
        """
        if self._fading:
            self._fade_timer -= dt
            if self._fade_timer <= 0.0:
                self.dead = True
            return

        if closing_pull is not None:
            update_closing_pull(self, dt, closing_pull)
        else:
            update_magnetic_attraction(self, dt, attraction_pos, attraction_mult)

        # Rotação da estrela (imagem interna)
        self.rotation += self.rotation_speed * dt
        self.rotation %= 360
        # Animação de pulsação (igual ao PowerUp)
        self.animation_timer += dt * 5
        self.pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )

        # NÃO rotacionar aqui. Existia um `transform.rotate` da imagem inteira
        # neste ponto, guardado em `self.current_image` — atributo que NINGUÉM
        # lia (o `draw` monta o ícone por conta própria). Era um rotate por
        # estrela, por frame, com o resultado descartado.

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

        if self._fading:
            self._draw_fading(surface)
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
        inner_size = max(1, int(pulse_size * 0.7))
        star_img = self._icon_for(self.base_image, inner_size, self.rotation)
        img_rect = star_img.get_rect(center=pulse_rect.center)
        surface.blit(star_img, img_rect)

    def _draw_fading(self, surface: pygame.Surface) -> None:
        """Dissolver de encerramento: alpha decrescente + encolhimento."""
        progress = max(0.0, min(1.0, self._fade_timer / self.FADE_OUT_DURATION))
        size = max(2, int(self.w * (0.35 + 0.65 * progress)))
        buf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.ellipse(buf, (255, 220, 100), buf.get_rect())
        star_img = pygame.transform.scale(self.base_image, (size, size))
        buf.blit(star_img, (0, 0))
        buf.set_alpha(int(255 * progress))
        surface.blit(
            buf, (self.rect.centerx - size // 2, self.rect.centery - size // 2)
        )

    def get_rect(self) -> pygame.Rect:
        """
        Retorna o retângulo de colisão da estrela.

        Returns:
            pygame.Rect: Retângulo de colisão baseado na imagem atual
        """
        # Colisão baseada no retângulo atual
        return self.rect.copy()
