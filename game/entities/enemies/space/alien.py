import random
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from ....core.assets import BASE_DIR, get_image
from ....core.config import config as Config
from ....core.sound import sound_manager
from ....core.sprite_loader import sprite_loader
from ...projectiles.alien_bullet import AlienBullet

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class Alien:
    # Cores de explosão do alien (verde brilhante)
    EXPLOSION_COLORS = [(37, 217, 166), (78, 217, 74)]

    # Sprites: voo em loop na pasta base, morte (uma passada) em Sprite_Morte/
    _SPRITE_DIR = BASE_DIR / "assets" / "images" / "Sprite_Nave_Inimiga_01" / "Alien"
    _FRAME_COUNT = 4
    _DEATH_FRAME_COUNT = 4

    # Cache de sprites (carregados uma vez)
    _animation_frames: list[pygame.Surface] | None = None
    _death_frames: list[pygame.Surface] | None = None

    @classmethod
    def _load_scaled_frames(
        cls, folder: Path, filename_pattern: str, count: int
    ) -> list[pygame.Surface]:
        """Carrega ``count`` frames da pasta, já no tamanho do alien."""
        size = (Config.ALIEN_WIDTH, Config.ALIEN_HEIGHT)
        return [
            pygame.transform.scale(
                get_image(folder / filename_pattern.format(i=i)), size
            )
            for i in range(1, count + 1)
        ]

    @classmethod
    def load_animation_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona os sprites de voo uma vez."""
        if cls._animation_frames is None:
            cls._animation_frames = cls._load_scaled_frames(
                cls._SPRITE_DIR, "Alien_Sprite_{i:02d}.png", cls._FRAME_COUNT
            )
        return cls._animation_frames

    @classmethod
    def load_death_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona os sprites de morte uma vez."""
        if cls._death_frames is None:
            cls._death_frames = cls._load_scaled_frames(
                cls._SPRITE_DIR / "Sprite_Morte",
                "Alien_Sprite_Morte_{i:02d}.png",
                cls._DEATH_FRAME_COUNT,
            )
        return cls._death_frames

    def __init__(self, aggressiveness_multiplier: float = 1.0):
        self.w, self.h = Config.ALIEN_WIDTH, Config.ALIEN_HEIGHT
        self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        self.y = -self.h

        # Agressividade: Aumenta a velocidade
        self.speed_x = (
            random.choice(Config.ALIEN_SPEED_X_OPTIONS) * aggressiveness_multiplier
        )
        self.speed_y = Config.ALIEN_SPEED_Y * aggressiveness_multiplier

        self.dead = False
        self.health = Config.ALIEN_HEALTH

        # Agressividade também se propaga para as balas atiradas por este Alien
        self.aggressiveness_multiplier = aggressiveness_multiplier

        # Timers de tiro
        # Agressividade: Reduz o intervalo entre os tiros (atira mais rápido)
        base_interval = random.uniform(
            Config.ALIEN_SHOOT_INTERVAL_MIN, Config.ALIEN_SHOOT_INTERVAL_MAX
        )
        self.shoot_timer: float = base_interval / aggressiveness_multiplier

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

        # Morte: os frames de Sprite_Morte rodam UMA vez antes da remoção. É só
        # cosmético — pontuação, explosão e som saem do `HitResult` no instante
        # do abate, como sempre.
        self.death_frames = self.load_death_frames()
        self._dying = False
        self._death_frame = 0
        self._death_timer = 0.0

        # Explosão (inicializar para satisfazer o Pylint)
        self.explosion_alien = []
        self._explosion_color_set = False

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        emitted = self.update(ctx.sdt)
        if emitted:
            ctx.new_alien_bullets.extend(emitted)

    def _start_death(self) -> None:
        """Entra na animação de morte. Idempotente (abates simultâneos)."""
        if self._dying:
            return
        self._dying = True
        self._death_frame = 0
        self._death_timer = 0.0
        # Para de atirar: a formação dispara por ele consultando `shoot_timer`.
        self.shoot_timer = float("inf")
        self.burst_shots_remaining = 0
        self.is_burst_mode = False
        self.should_shoot = False
        # Cores personalizadas da explosão (mantido do comportamento anterior)
        if not self._explosion_color_set:
            self.explosion_alien = list(self.EXPLOSION_COLORS)
            self._explosion_color_set = True

    def _advance_death_animation(self, dt: float) -> None:
        """Avança os frames de morte; ao fim dos frames, marca `dead`."""
        self._death_timer += dt
        duration = Config.ALIEN_DEATH_FRAME_DURATION
        while self._death_timer >= duration and self._death_frame < len(
            self.death_frames
        ):
            self._death_timer -= duration
            self._death_frame += 1
        if self._death_frame >= len(self.death_frames):
            self.dead = True

    def update(self, dt: float) -> list[AlienBullet] | None:
        # Morrendo: só roda a animação de morte (sem mover, atirar ou colidir)
        if self._dying:
            self._advance_death_animation(dt)
            return None

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
                    # Agressividade: reduz o tempo de cooldown após atirar
                    self.post_shoot_cooldown = 0.5 / self.aggressiveness_multiplier
                    self.is_burst_mode = False
                    # Resetar timer normal considerando agressividade
                    base_interval = random.uniform(
                        Config.ALIEN_SHOOT_INTERVAL_MIN, Config.ALIEN_SHOOT_INTERVAL_MAX
                    )
                    self.shoot_timer = base_interval / self.aggressiveness_multiplier

        # Criar bala se deve disparar
        bullets = None
        if self.should_shoot:
            self.should_shoot = False
            sound_manager.play_shot()
            # Agressividade: A bala criada também herda o multiplicador de velocidade
            bullet = AlienBullet(self.x + self.w / 2, self.y + self.h)
            bullet.vy *= self.aggressiveness_multiplier
            bullets = [bullet]

        # Atualizar animação
        self.animation_timer += dt
        if self.animation_timer >= self.frame_duration:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

        return bullets

    def draw(self, surface: pygame.Surface):
        # Verificar se tem alpha definido (para formações com fade-in)
        alpha = getattr(self, "alpha", 255)

        # Obter frame atual (voo ou morte)
        if self._dying:
            frame = min(self._death_frame, len(self.death_frames) - 1)
            image = self.death_frames[frame]
        else:
            image = self.animation_frames[self.current_frame]

        # Aplicar alpha se necessário (para formações)
        if alpha < 255:
            image = image.copy()
            image.set_alpha(alpha)

        # Desenhar
        surface.blit(image, (int(self.x), int(self.y)))

    def get_points_value(self) -> int:
        return Config.ALIEN_POINTS_VALUE

    @property
    def causes_damage(self) -> bool:
        return not self._dying and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        if self._dying:
            # Já pontuou e explodiu: os frames de morte são cosméticos.
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def on_hit(self, _damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult
        from ...effects.explosion import ExplosionType

        if self._dying or self.dead:
            return HitResult()
        self._start_death()
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=40,
            explosion_type=ExplosionType.ALIEN,
            sound=hit_sounds.EXPLOSION_ALIEN,
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        if self._dying or self.dead:
            return HitResult()
        self._start_death()
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead


# REGISTRAR no sistema de pré-carregamento (fora da classe)
sprite_loader.register("Alien", Alien.load_animation_frames)
sprite_loader.register("Alien (morte)", Alien.load_death_frames)
