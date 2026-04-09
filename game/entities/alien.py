import random

import pygame

from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader
from .alien_bullet import AlienBullet


class Alien:
    # Cores de explosão do alien (verde brilhante)
    EXPLOSION_COLORS = [(37, 217, 166), (78, 217, 74)]

    # Cache de sprites de animação (carregado uma vez)
    _animation_frames: list[pygame.Surface] | None = None

    @classmethod
    def load_animation_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona os sprites de animação uma vez."""
        if cls._animation_frames is not None:
            return cls._animation_frames

        frames: list[pygame.Surface] = []
        for i in range(1, 13):
            path = (
                BASE_DIR
                / "assets"
                / "images"
                / "Sprite_Nave_Inimiga_01"
                / f"nave_inimiga ({i}).png"
            )
            image = get_image(path)
            # Redimensionar para o tamanho do alien
            image = pygame.transform.scale(
                image, (Config.ALIEN_WIDTH, Config.ALIEN_HEIGHT)
            )
            frames.append(image)

        cls._animation_frames = frames
        return frames

    def __init__(self):
        self.w, self.h = Config.ALIEN_WIDTH, Config.ALIEN_HEIGHT
        self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        self.y = -self.h
        self.speed_x = random.choice(Config.ALIEN_SPEED_X_OPTIONS)
        self.speed_y = Config.ALIEN_SPEED_Y
        self.dead = False
        self.health = Config.ALIEN_HEALTH

        # Timers de tiro
        self.shoot_timer: float = random.uniform(
            Config.ALIEN_SHOOT_INTERVAL_MIN, Config.ALIEN_SHOOT_INTERVAL_MAX
        )

        # Atributos para controle por formação
        self.formation_controlled = False
        self.formation_index = 0
        self.formation_angle = 0.0

        # Sistemas de pausa e tiro
        self.pause_timer: float = 0.0
        self.is_paused = False
        self.should_shoot = False
        self.post_shoot_cooldown: float = 0.0

        # Sistema de rajada
        self.burst_shots_remaining: int = 0  # Quantos tiros faltam na rajada
        self.burst_shot_timer: float = 0.0  # Timer para o próximo tiro da rajada
        self.is_burst_mode: bool = (
            False  # Se está em modo rajada (fica parado durante toda sequência)
        )

        # Animação
        self.animation_frames = self.load_animation_frames()
        self.current_frame = 0
        self.animation_timer = 0.0
        self.frame_duration = Config.ALIEN_ANIMATION_FRAME_DURATION

        # Explosão (inicializar para satisfazer o Pylint)
        self.explosion_alien = []
        self._explosion_color_set = False

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float) -> list[AlienBullet] | None:
        # Se controlado por formação, não move automaticamente
        if self.formation_controlled:
            # Apenas atualiza timer de tiro (o disparo é gerenciado pela Formation)
            self.shoot_timer -= dt
            # Marcar como morto se sair muito da tela (segurança)
            if (
                self.y > Config.SCREEN_HEIGHT + Config.ALIEN_DEATH_MARGIN
                or self.y < -Config.ALIEN_DEATH_MARGIN
            ):
                self.dead = True
            # Atualizar animação
            self.animation_timer += dt
            if self.animation_timer >= self.frame_duration:
                self.animation_timer = 0.0
                self.current_frame = (self.current_frame + 1) % len(
                    self.animation_frames
                )
            return None

        # Atualizar pausa antes de disparar
        if self.is_paused:
            self.pause_timer -= dt
            if self.pause_timer <= 0:
                self.is_paused = False
                # Não disparar aqui - deixar o sistema de burst_shot_timer gerenciar

        # Atualizar cooldown após disparar
        if self.post_shoot_cooldown > 0:
            self.post_shoot_cooldown -= dt

        # Movimento normal (quando não está em formação e não está pausado ou em cooldown ou em burst)
        if (
            not self.is_paused
            and self.post_shoot_cooldown <= 0
            and not self.is_burst_mode
        ):
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
        if (
            self.shoot_timer <= 0
            and not self.is_paused
            and self.burst_shots_remaining == 0
        ):
            # Decidir se será rajada ou tiro único
            self.is_burst_mode = random.random() < Config.ALIEN_SHOOT_BURST_CHANCE
            if self.is_burst_mode:
                # Modo rajada: 3 tiros
                self.burst_shots_remaining = Config.ALIEN_BURST_COUNT
            else:
                # Modo tiro único: 1 tiro
                self.burst_shots_remaining = 1

            # Iniciar primeira pausa (0.5s para ambos)
            self.is_paused = True
            self.pause_timer = 0.5
            self.burst_shot_timer = (
                0.0  # Primeiro tiro acontece imediatamente após a pausa
            )
            self.shoot_timer = float("inf")

        # Gerenciar tiros da rajada/sequência
        if self.burst_shots_remaining > 0 and not self.is_paused:
            self.burst_shot_timer -= dt
            if self.burst_shot_timer <= 0:
                # Hora de atirar
                self.should_shoot = True
                self.burst_shots_remaining -= 1

                if self.burst_shots_remaining > 0:
                    # Ainda há tiros na sequência
                    if self.is_burst_mode:
                        # Burst: intervalo de 1s, continua parado
                        self.burst_shot_timer = Config.ALIEN_BURST_INTERVAL
                    else:
                        # Tiro único: não há mais tiros, então não faz nada aqui
                        pass
                else:
                    # Acabou a sequência, aplicar cooldown de 0.5s antes de voltar a se mover
                    self.post_shoot_cooldown = 0.5
                    self.is_burst_mode = False
                    # Resetar timer normal
                    self.shoot_timer = random.uniform(
                        Config.ALIEN_SHOOT_INTERVAL_MIN, Config.ALIEN_SHOOT_INTERVAL_MAX
                    )

        # Criar bala se deve disparar
        bullets = None
        if self.should_shoot:
            self.should_shoot = False
            # Não aplicar cooldown aqui - será aplicado quando terminar a sequência
            bullets = [AlienBullet(self.x + self.w / 2, self.y + self.h)]

        # Atualizar animação
        self.animation_timer += dt
        if self.animation_timer >= self.frame_duration:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

        # Se morreu, definir cores personalizadas para a explosão
        if self.dead and not self._explosion_color_set:
            # Cores: #25D9A6 (37, 217, 166) e #4ED94A (78, 217, 74)
            self.explosion_alien = [(37, 217, 166), (78, 217, 74)]
            self._explosion_color_set = True

        return bullets

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
        return Config.ALIEN_POINTS_VALUE


# REGISTRAR no sistema de pré-carregamento (fora da classe)
sprite_loader.register("Alien", Alien.load_animation_frames)
