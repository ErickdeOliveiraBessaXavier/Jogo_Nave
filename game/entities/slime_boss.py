import logging
import random
from typing import TYPE_CHECKING, Any, Optional

import pygame
import pygame.font

from ..core.config import SlimeBossState, SlimeDripMode, StageConfig
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.sprite_loader import sprite_loader
from .slime_drip import SlimeDrippingEffect

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


class SlimeBoss:
    """Large horizontal slime boss that spans the screen width and slides side-to-side.

    Visuals use `game/assets/images/sprite_boss_03_slime.png` (scaled to boss size).
    """

    _animation_frames: list[pygame.Surface] | None = None

    @classmethod
    def load_animation_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona os sprites de animação uma vez."""
        if cls._animation_frames is not None:
            return cls._animation_frames

        # Register for preloading if not loaded
        if not sprite_loader.is_loaded():
            sprite_loader.register("slime_boss", cls.load_frames_for_preload)

        # Load immediately if not preloaded
        return cls._load_frames()

    @classmethod
    def load_frames_for_preload(cls) -> list[pygame.Surface]:
        """Public method for preloading frames."""
        return cls._load_frames()

    @classmethod
    def _load_frames(cls) -> list[pygame.Surface]:
        """Internal method to load the frames."""
        return sprite_loader.load_animation_frames(
            "sprite_boss_03_slime", 24, "SlimeBoss"
        )

    def __init__(
        self,
        _x: float,
        _y: float,
        health: int | None = None,
        difficulty_multiplier: float = 1.0,
    ):
        # Position and size
        self.w = (
            Config.SCREEN_WIDTH + Config.SLIME_BOSS_WIDTH_MARGIN
        )  # +50px left +50px right margin
        self.h = Config.SLIME_BOSS_HEIGHT  # Taller to not be flattened
        self.x = Config.SCREEN_WIDTH / 2 - self.w / 2  # Center the boss horizontally
        self.y = -self.h  # More off-screen from the top
        self.target_y = -100  # Final position higher up, not too low

        # ✅ PRÉ-CALCULAR VALORES CONSTANTES
        self.center_x = Config.SCREEN_WIDTH / 2 - self.w / 2
        self.move_range = Config.SLIME_BOSS_MOVE_RANGE

        # Health and state
        self.health = health if health is not None else Config.SLIME_BOSS_HEALTH
        self.max_health = self.health
        self.dead = False
        self.current_state = SlimeBossState.ENTERING
        self.stage_timer = 0.0
        self.current_stage_config: StageConfig | None = None
        self._next_normal_stage: SlimeBossState | None = None
        self._next_homing_stage: SlimeBossState | None = None
        self.direction = 1

        # Entry speed
        self.slow_entry_speed = Config.SLIME_BOSS_ENTRY_SPEED_SLOW
        self.fast_entry_speed = Config.SLIME_BOSS_ENTRY_SPEED_FAST
        self.is_first_entry = True
        self.entry_speed = self.slow_entry_speed  # Initialize for ENTERING state

        # Animation
        self.animation_frames = self.load_animation_frames()

        # ✅ ADICIONAR PROTEÇÃO:
        if not self.animation_frames:
            logging.warning("SlimeBoss: Frames não carregados, usando fallback visual")

        # ✅ VALIDAR FRAMES UMA VEZ NO INIT (evitar try/except no hot path)
        self.has_valid_frames = bool(
            self.animation_frames and len(self.animation_frames) > 0
        )

        self.current_frame = 0
        self.animation_timer = 0.0
        self.animation_speed = (
            Config.SLIME_BOSS_ANIMATION_SPEED
        )  # seconds per frame - slower animation

        # Hit feedback (flash overlay)
        self.hit_flash_timer = 0.0
        self.hit_flash_duration = 0.15

        # Death sequence guard
        self.death_sequence_started = False

        # Rage shake feedback
        self.shake_timer = 0.0
        self.shake_duration = 0.2
        self.shake_magnitude = 8.0

        # Mask cache for pixel-perfect collision optimization (limited to recent frames)
        self._mask_cache: dict[int, pygame.mask.Mask] = {}
        self._scaled_frame_cache: dict[int, pygame.Surface] = {}
        self._outline_cache: dict[int, list[tuple[int, int]]] = (
            {}
        )  # Cache for hit flash outlines
        self._last_mask_size = (int(self.w), int(self.h))
        self._mask_cache_max_size = (
            6  # Keep masks for last 6 frames to balance memory/performance
        )
        self._flash_surface: pygame.Surface | None = None

        # Sistema de dripping slime
        self.dripping_effect = SlimeDrippingEffect(
            Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT, difficulty_multiplier
        )

        # Velocidades de entrada/saída
        self.leaving_speed = Config.SLIME_BOSS_LEAVING_SPEED

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float | None = None,
        entity_manager: Optional["EntityManager"] = None,
    ) -> tuple[list[Any], list[Any], list[Any]]:
        # Update animation
        self._update_animation(dt)

        # Decay hit flash timer
        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)

        # Decay rage shake timer
        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - dt)

        # Check transitions
        next_state = self._check_transitions()
        if next_state:
            # Marcar próximo stage homing antes de retreating
            if next_state == SlimeBossState.RETREATING:
                if self.health / self.max_health > Config.SLIME_BOSS_THRESHOLD_STAGE_3:
                    self._next_homing_stage = SlimeBossState.STAGE_2_HOMING
                else:
                    self._next_homing_stage = SlimeBossState.STAGE_4_HOMING
            self._transition_to_state(next_state)

        # Update based on current state
        if self.current_state == SlimeBossState.ENTERING:
            self._update_entering(dt)
        elif self.current_state == SlimeBossState.RETREATING:
            self._update_retreating(dt)
        elif self.current_state in [
            SlimeBossState.STAGE_2_HOMING,
            SlimeBossState.STAGE_4_HOMING,
        ]:
            self._update_stage_with_timer(dt, player_x, player_y or 0)
            self._update_active_movement(dt)
        elif self.current_state in [
            SlimeBossState.STAGE_1_NORMAL,
            SlimeBossState.STAGE_3_NORMAL,
            SlimeBossState.STAGE_5_FINAL,
        ]:
            self._update_active_movement(dt)

        # Update dripping effect
        self.dripping_effect.update(
            dt, self.x, self.y, self.w, player_x, player_y or 0, entity_manager
        )

        return [], [], []

    def can_take_damage(self) -> bool:
        return self.current_state != SlimeBossState.ENTERING and not self.dead

    def take_damage(self, amount: int) -> None:
        if not self.can_take_damage():
            return
        self.health -= amount
        # Trigger brief hit flash
        self.hit_flash_timer = self.hit_flash_duration

        # Occasionally trigger a short rage shake on heavy damage or low HP
        if not self.dead and self.shake_timer == 0.0:
            health_pct = self.health / self.max_health if self.max_health else 1.0
            heavy_hit = amount >= 0.04 * self.max_health
            low_health = health_pct <= 0.4 and random.random() < 0.35
            if heavy_hit or low_health:
                self.shake_timer = self.shake_duration
        if self.health <= 0:
            self.health = 0
            self.dead = True
            sound_manager.play_explosion_boss()
        else:
            sound_manager.play_boss_damage()

    def get_stage_info(self) -> str:
        return f"{self.current_state.name} | Timer: {self.stage_timer:.1f}s | HP: {self.health}/{self.max_health}"

    def _update_active_state(self, dt: float) -> None:
        """Move lateralmente 50px para esquerda e direita a partir da posição central."""
        # Velocidade de movimento
        speed = (
            Config.SLIME_BOSS_MOVE_SPEED
        )  # pixels/segundo (ajuste conforme necessário)

        # Mover horizontalmente
        self.x += speed * dt * self.direction

        # Calcular posição central
        center_x = Config.SCREEN_WIDTH / 2 - self.w / 2

        # Inverter direção nos limites de ±50px da posição central
        if self.direction > 0 and self.x >= center_x + Config.SLIME_BOSS_MOVE_RANGE:
            self.direction = -1
        elif self.direction < 0 and self.x <= center_x - Config.SLIME_BOSS_MOVE_RANGE:
            self.direction = 1

    def _update_animation(self, dt: float) -> None:
        """Update animation frame com limpeza agressiva de cache."""
        if not self.animation_frames or len(self.animation_frames) == 0:
            return  # Não atualizar se não há frames

        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0.0
            old_frame = self.current_frame
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

            # ✅ LIMPAR CACHES: manter apenas 3 frames (atual + 2 próximos)
            if old_frame != self.current_frame:
                total_frames = len(self.animation_frames)
                frames_to_keep = {
                    self.current_frame,
                    (self.current_frame + 1) % total_frames,
                    (self.current_frame + 2) % total_frames,
                }

                # Limpar scaled frames antigos
                if len(self._scaled_frame_cache) > 3:
                    self._scaled_frame_cache = {
                        k: v
                        for k, v in self._scaled_frame_cache.items()
                        if k in frames_to_keep
                    }

                # Limpar masks antigos
                if len(self._mask_cache) > 3:
                    self._mask_cache = {
                        k: v for k, v in self._mask_cache.items() if k in frames_to_keep
                    }

                # Limpar outlines antigos
                if len(self._outline_cache) > 3:
                    self._outline_cache = {
                        k: v
                        for k, v in self._outline_cache.items()
                        if k in frames_to_keep
                    }

    def _check_transitions(self) -> SlimeBossState | None:
        health_pct = self.health / self.max_health

        # Stage 1 → Waiting (75% vida)
        if (
            self.current_state == SlimeBossState.STAGE_1_NORMAL
            and health_pct <= Config.SLIME_BOSS_THRESHOLD_STAGE_1
        ):
            return SlimeBossState.WAITING_DRIPS

        # Waiting → Retreating (drips zeradas)
        if self.current_state == SlimeBossState.WAITING_DRIPS:
            if self.dripping_effect.drip_pool.get_active_count() == 0:
                return SlimeBossState.RETREATING

        # Retreating → Próximo stage homing (saiu da tela)
        if self.current_state == SlimeBossState.RETREATING and self.y <= -self.h:
            if self._next_homing_stage is None:
                self._next_homing_stage = SlimeBossState.STAGE_2_HOMING
            next_stage = self._next_homing_stage
            self._next_homing_stage = None
            return next_stage

        # Stage 2 Homing → ENTERING (timeout)
        if self.current_state == SlimeBossState.STAGE_2_HOMING:
            if (
                self.current_stage_config
                and self.current_stage_config.duration is not None
                and self.stage_timer >= self.current_stage_config.duration
            ):
                self._next_normal_stage = SlimeBossState.STAGE_3_NORMAL
                return SlimeBossState.ENTERING

        # Stage 3 → Waiting (20% vida)
        if (
            self.current_state == SlimeBossState.STAGE_3_NORMAL
            and health_pct <= Config.SLIME_BOSS_THRESHOLD_STAGE_3
        ):
            return SlimeBossState.WAITING_DRIPS

        # Stage 4 Homing → ENTERING (timeout)
        if self.current_state == SlimeBossState.STAGE_4_HOMING:
            if (
                self.current_stage_config
                and self.current_stage_config.duration is not None
                and self.stage_timer >= self.current_stage_config.duration
            ):
                self._next_normal_stage = SlimeBossState.STAGE_5_FINAL
                return SlimeBossState.ENTERING

        return None

    def _transition_to_state(self, new_state: SlimeBossState) -> None:
        self.current_state = new_state
        self.stage_timer = 0.0

        # Configurar stage específico
        if new_state in Config.SLIME_BOSS_STAGES:
            config = Config.SLIME_BOSS_STAGES[new_state]
            self.current_stage_config = config
            self.target_y = config.target_y

            # Verificar modo do stage
            if config.drip_mode == SlimeDripMode.DUAL:
                # MODO DUAL: Configurar ambos os tipos
                self.dripping_effect.set_dual_mode(
                    enabled=True,
                    max_normal=config.max_drips,
                    normal_interval=config.spawn_interval,
                    max_homing=config.max_homing_drips,
                    homing_interval=config.homing_spawn_interval,
                    target_x=0,  # Será atualizado no update
                    target_y=0,
                )
            elif config.is_homing:
                # MODO HOMING PURO
                self.dripping_effect.set_homing_mode(True, 0, 0)
                self.dripping_effect.max_drips = config.max_drips
                self.dripping_effect.spawn_interval = config.spawn_interval
            else:
                # MODO NORMAL PURO
                self.dripping_effect.set_homing_mode(False, 0, 0)
                self.dripping_effect.max_drips = config.max_drips
                self.dripping_effect.spawn_interval = config.spawn_interval

            self.dripping_effect.set_spawn_enabled(True)

        # Estados especiais
        if new_state == SlimeBossState.WAITING_DRIPS:
            self.dripping_effect.set_spawn_enabled(False)
        elif new_state == SlimeBossState.RETREATING:
            self.target_y = -self.h - 100
        elif new_state in [
            SlimeBossState.STAGE_2_HOMING,
            SlimeBossState.STAGE_4_HOMING,
        ]:
            # Boss stays hidden during homing phase
            self.target_y = -self.h - 100  # Completely off-screen
        elif new_state in [SlimeBossState.STAGE_3_NORMAL, SlimeBossState.STAGE_5_FINAL]:
            self.y = -self.h
            self.target_y = -50  # Consistent with Stage 1

    def _update_entering(self, dt: float) -> None:
        # Use appropriate entry speed based on whether this is the first entry
        speed = self.slow_entry_speed if self.is_first_entry else self.fast_entry_speed

        self.y += speed * dt
        if self.y >= self.target_y:
            self.y = self.target_y
            self.is_first_entry = False  # Mark that first entry is complete

            # Check if there's a stage defined after homing
            if self._next_normal_stage:
                next_stage = self._next_normal_stage
                self._next_normal_stage = None
                self._transition_to_state(next_stage)
            else:
                # Initial entry
                self._transition_to_state(SlimeBossState.STAGE_1_NORMAL)

    def _update_retreating(self, dt: float) -> None:
        self.y -= self.leaving_speed * dt

    def _update_stage_with_timer(
        self, dt: float, player_x: float, player_y: float
    ) -> None:
        # Boss stays hidden during homing phases - no vertical movement

        self.stage_timer += dt
        if self.current_stage_config and (
            self.current_stage_config.is_homing
            or (self.current_stage_config.drip_mode == SlimeDripMode.DUAL)
        ):
            self.dripping_effect.set_homing_mode(True, player_x, player_y)

    def _update_active_movement(self, dt: float) -> None:
        if self.current_state == SlimeBossState.ENTERING:
            return

        # Handle vertical movement if needed (for entering after homing phases)
        if self.y < self.target_y:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y

        # Horizontal movement
        speed = 50.0
        self.x += speed * dt * self.direction
        # ✅ USAR VALORES PRÉ-CALCULADOS
        if self.direction > 0 and self.x >= self.center_x + self.move_range:
            self.direction = -1
        elif self.direction < 0 and self.x <= self.center_x - self.move_range:
            self.direction = 1

    def _draw_fallback(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Fallback drawing when animation frames are not available."""
        rect = pygame.Rect(
            int(self.x + offset_x),
            int(self.y + offset_y),
            int(self.w),
            int(self.h),
        )
        pygame.draw.rect(surface, (0, 255, 100), rect)  # Verde gosma
        font = pygame.font.Font(None, 48)
        text = font.render("SLIME BOSS", True, (255, 255, 255))
        text_rect = text.get_rect(center=(rect.centerx, rect.centery))
        surface.blit(text, text_rect)

    def draw(self, surface: pygame.Surface, _fps: float = 60.0) -> None:
        # Draw the slime sprite stretched to boss dimensions (with simple fallback)
        offset_x, offset_y = (0, 0)

        # Apply temporary shake when enraged/hit
        if self.shake_timer > 0.0:
            offset_x += random.uniform(-self.shake_magnitude, self.shake_magnitude)
            offset_y += random.uniform(-self.shake_magnitude, self.shake_magnitude)
        scaled_frame: pygame.Surface | None = None

        # ✅ EVITAR TRY/EXCEPT NO HOT PATH: usar validação prévia
        if not self.has_valid_frames:
            self._draw_fallback(surface, offset_x, offset_y)
        else:
            # ✅ OTIMIZAR VERIFICAÇÃO DE CACHE: usar .get() ao invés de 'in' + acesso
            scaled_frame = self._scaled_frame_cache.get(self.current_frame)
            if scaled_frame is None:
                frame = self.animation_frames[self.current_frame]
                scaled_frame = pygame.transform.smoothscale(
                    frame, (int(self.w), int(self.h))
                )
                self._scaled_frame_cache[self.current_frame] = scaled_frame

            surface.blit(scaled_frame, (int(self.x + offset_x), int(self.y + offset_y)))

        # Draw dripping effect
        self.dripping_effect.draw(surface)

        # ✅ FLASH OTIMIZADO: só desenhar se boss visível + usar cache de outline
        if self.hit_flash_timer > 0.0 and self.y > -self.h:  # Skip se off-screen
            self._draw_flash_outline(surface, scaled_frame, offset_x, offset_y)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    @property
    def mask(self) -> pygame.mask.Mask:
        """Generate pixel-perfect collision mask (optimized)."""
        current_size = (int(self.w), int(self.h))

        # Clear cache if boss size changed
        if current_size != self._last_mask_size:
            self._mask_cache.clear()
            self._scaled_frame_cache.clear()
            self._outline_cache.clear()
            self._flash_surface = None
            self._last_mask_size = current_size

        # ✅ OTIMIZAR VERIFICAÇÃO DE CACHE: usar .get() ao invés de 'in' + acesso
        cached_mask = self._mask_cache.get(self.current_frame)
        if cached_mask is not None:
            return cached_mask

        # ✅ REUTILIZAR scaled_frame_cache (evita smoothscale duplicado)
        scaled_frame = self._scaled_frame_cache.get(self.current_frame)
        if scaled_frame is None:
            if (
                not self.animation_frames
                or len(self.animation_frames) <= self.current_frame
            ):
                scaled_frame = pygame.Surface(current_size)
                scaled_frame.fill((255, 255, 255, 255))
            else:
                try:
                    frame = self.animation_frames[self.current_frame]
                    scaled_frame = pygame.transform.smoothscale(frame, current_size)
                except (pygame.error, ValueError, TypeError) as e:
                    logging.warning(
                        f"SlimeBoss: Erro ao escalar frame {self.current_frame}: {e}"
                    )
                    scaled_frame = pygame.Surface(current_size)
                    scaled_frame.fill((255, 255, 255, 255))

            self._scaled_frame_cache[self.current_frame] = scaled_frame

        # Create mask from cached scaled frame
        try:
            mask = pygame.mask.from_surface(
                self._scaled_frame_cache[self.current_frame]
            )
        except (pygame.error, ValueError, TypeError) as e:
            logging.warning(f"SlimeBoss: Erro ao criar máscara: {e}")
            mask = pygame.mask.Mask(current_size, fill=True)

        # ✅ NÃO LIMITAR CACHE AQUI: deixar para _update_animation
        self._mask_cache[self.current_frame] = mask
        return mask

    def _draw_flash_outline(
        self,
        surface: pygame.Surface,
        scaled_frame: pygame.Surface | None,
        offset_x: float,
        offset_y: float,
    ) -> None:
        """Desenha outline com LOD baseado em distância."""
        flash_intensity = self.hit_flash_timer / self.hit_flash_duration
        alpha = max(0, min(255, int(220 * flash_intensity)))

        # ✅ LAZY LOADING: Skip se alpha seria invisível
        if alpha < 10:  # Invisível, pular completamente
            return

        if self._flash_surface is None:
            self._flash_surface = pygame.Surface(
                (int(self.w), int(self.h)), pygame.SRCALPHA
            )

        self._flash_surface.fill((0, 0, 0, 0))

        if scaled_frame is not None:
            # ✅ LOD MAIS AGRESSIVO: simplificar outline baseado na distância
            if self.y < -300:  # Muito distante, nem desenhar
                return
            elif self.y < -200:  # Boss escondido, usar 1/4 dos pontos
                outline = self._outline_cache.get(self.current_frame)
                if outline is None:
                    try:
                        mask = pygame.mask.from_surface(scaled_frame)
                        outline = mask.outline()
                        outline = outline[::4]  # 1/4 dos pontos
                        self._outline_cache[self.current_frame] = outline
                    except (pygame.error, ValueError, TypeError) as e:
                        logging.warning(
                            f"SlimeBoss: Erro ao gerar outline simplificado: {e}"
                        )
                        outline = []
                        self._outline_cache[self.current_frame] = outline

                if len(outline) > 1:
                    pygame.draw.lines(
                        self._flash_surface,
                        (255, 255, 255, alpha),
                        True,
                        outline,
                        1,  # Espessura mínima
                    )
            else:
                # Outline completo quando visível
                outline = self._outline_cache.get(self.current_frame)
                if outline is None:
                    try:
                        mask = pygame.mask.from_surface(scaled_frame)
                        outline = mask.outline()

                        # ✅ SIMPLIFICAR OUTLINE: pegar 1 a cada 2 pontos se muito grande
                        if len(outline) > 200:
                            outline = outline[::2]  # Pegar metade dos pontos

                        self._outline_cache[self.current_frame] = outline
                    except (pygame.error, ValueError, TypeError) as e:
                        logging.warning(f"SlimeBoss: Erro ao gerar outline: {e}")
                        outline = []
                        self._outline_cache[self.current_frame] = outline

                if len(outline) > 1:
                    pygame.draw.lines(
                        self._flash_surface,
                        (255, 255, 255, alpha),
                        True,
                        outline,
                        2,  # Espessura reduzida
                    )
        else:
            # Fallback: rect outline
            pygame.draw.rect(
                self._flash_surface,
                (255, 255, 255, alpha),
                pygame.Rect(0, 0, int(self.w), int(self.h)),
                width=2,  # Espessura reduzida
            )

        surface.blit(
            self._flash_surface, (int(self.x + offset_x), int(self.y + offset_y))
        )

    def check_drip_damage(
        self, player_rect: pygame.Rect, entity_manager: Optional["EntityManager"] = None
    ) -> int:
        """Verifica se alguma gota acertou o jogador e retorna o dano.

        Args:
            player_rect: Retângulo do jogador
            entity_manager: EntityManager para spawnar efeitos de partículas (opcional)
        """
        return self.dripping_effect.check_collisions(player_rect, entity_manager)
