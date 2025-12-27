import pygame
import pygame.font
from typing import Optional, TYPE_CHECKING, Any
from ..core.assets import get_image, BASE_DIR
from ..core.config import config as Config, SlimeBossState, StageConfig
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
        frames: list[pygame.Surface] = []
        for i in range(1, 25):  # 24 frames
            path = (
                BASE_DIR
                / "assets"
                / "images"
                / "sprite_boss_03_slime"
                / f"boss_3_gosma_sprite ({i}).png"
            )

            # ✅ ADICIONAR VALIDAÇÃO AQUI:
            if not path.exists():
                print(f"⚠️ SlimeBoss: Frame {i} não encontrado: {path}")
                continue

            try:
                image = get_image(path)
                frames.append(image)
            except Exception as e:
                print(f"❌ SlimeBoss: Erro ao carregar frame {i}: {e}")
                continue

        # ✅ ADICIONAR VALIDAÇÃO FINAL:
        if not frames:
            print(
                "❌ SlimeBoss: NENHUM frame foi carregado! Verifique o caminho dos sprites."
            )
        elif len(frames) < 24:
            print(f"⚠️ SlimeBoss: Apenas {len(frames)}/24 frames foram carregados.")
        else:
            print(f"✅ SlimeBoss: {len(frames)} frames carregados com sucesso.")

        cls._animation_frames = frames
        cls._frames_loaded = True
        return frames

    def __init__(
        self,
        x: float,
        y: float,
        health: int | None = None,
        difficulty_multiplier: float = 1.0,
    ):
        # Position and size
        self.w = Config.SCREEN_WIDTH + 100  # +50px left +50px right margin
        self.h = 600  # Taller to not be flattened
        self.x = Config.SCREEN_WIDTH / 2 - self.w / 2  # Center the boss horizontally
        self.y = -self.h  # More off-screen from the top
        self.target_y = -100  # Final position higher up, not too low

        # Health and state
        self.health = health if health is not None else Config.SLIME_BOSS_HEALTH
        self.max_health = self.health
        self.dead = False
        self.current_state = SlimeBossState.ENTERING
        self.stage_timer = 0.0
        self.current_stage_config: StageConfig | None = None
        self._next_normal_stage: SlimeBossState | None = None

        # Entry speed
        self.slow_entry_speed = Config.SLIME_BOSS_ENTRY_SPEED_SLOW
        self.fast_entry_speed = Config.SLIME_BOSS_ENTRY_SPEED_FAST
        self.is_first_entry = True
        self.entry_speed = self.slow_entry_speed  # Initialize for ENTERING state

        # Animation
        self.animation_frames = self.load_animation_frames()

        # ✅ ADICIONAR PROTEÇÃO:
        if not self.animation_frames:
            print("⚠️ SlimeBoss: Frames não carregados, usando fallback visual")

        self.current_frame = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.2  # seconds per frame - slower animation

        # Mask cache for pixel-perfect collision optimization (limited to recent frames)
        self._mask_cache: dict[int, pygame.mask.Mask] = {}
        self._scaled_frame_cache: dict[int, pygame.Surface] = {}
        self._last_mask_size = (int(self.w), int(self.h))
        self._mask_cache_max_size = (
            6  # Keep masks for last 6 frames to balance memory/performance
        )

        # Sistema de dripping slime
        self.dripping_effect = SlimeDrippingEffect(
            Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT, difficulty_multiplier
        )

        # Velocidades de entrada/saída
        self.leaving_speed = Config.SLIME_BOSS_LEAVING_SPEED

    def update(self, dt: float, player_x: float, player_y: float | None = None) -> tuple[list[Any], list[Any], list[Any]]:
        # Update animation
        self._update_animation(dt)
        
        # Check transitions
        next_state = self._check_transitions()
        if next_state:
            # Marcar próximo stage homing antes de retreating
            if next_state == SlimeBossState.RETREATING:
                if self.health / self.max_health > 0.20:
                    self._next_homing_stage = SlimeBossState.STAGE_2_HOMING
                else:
                    self._next_homing_stage = SlimeBossState.STAGE_4_HOMING
            self._transition_to_state(next_state)
        
        # Update based on current state
        if self.current_state == SlimeBossState.ENTERING:
            self._update_entering(dt)
        elif self.current_state == SlimeBossState.RETREATING:
            self._update_retreating(dt)
        elif self.current_state in [SlimeBossState.STAGE_2_HOMING, SlimeBossState.STAGE_4_HOMING]:
            self._update_stage_with_timer(dt, player_x, player_y or 0)
            self._update_active_movement(dt)
        elif self.current_state in [SlimeBossState.STAGE_1_NORMAL, SlimeBossState.STAGE_3_NORMAL, SlimeBossState.STAGE_5_FINAL]:
            self._update_active_movement(dt)
        
        # Update dripping effect
        self.dripping_effect.update(dt, self.x, self.y, self.w, player_x, player_y or 0)
        
        return [], [], []

    def can_take_damage(self) -> bool:
        return self.current_state != SlimeBossState.ENTERING and not self.dead

    def take_damage(self, amount: int) -> None:
        if not self.can_take_damage():
            return
        self.health -= amount
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
        speed = 50.0  # pixels/segundo (ajuste conforme necessário)

        # Mover horizontalmente
        if not hasattr(self, "direction"):
            self.direction = 1  # 1 = direita, -1 = esquerda

        self.x += speed * dt * self.direction

        # Calcular posição central
        center_x = Config.SCREEN_WIDTH / 2 - self.w / 2

        # Inverter direção nos limites de ±50px da posição central
        if self.direction > 0 and self.x >= center_x + 50:
            self.direction = -1
        elif self.direction < 0 and self.x <= center_x - 50:
            self.direction = 1

    def _update_animation(self, dt: float) -> None:
        """Update animation frame."""
        if not self.animation_frames or len(self.animation_frames) == 0:
            return  # Não atualizar se não há frames

        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

    def _check_transitions(self) -> SlimeBossState | None:
        health_pct = self.health / self.max_health
        
        # Stage 1 → Waiting (75% vida)
        if self.current_state == SlimeBossState.STAGE_1_NORMAL and health_pct <= 0.75:
            return SlimeBossState.WAITING_DRIPS
        
        # Waiting → Retreating (drips zeradas)
        if self.current_state == SlimeBossState.WAITING_DRIPS:
            if self.dripping_effect.drip_pool.get_active_count() == 0:
                return SlimeBossState.RETREATING
        
        # Retreating → Próximo stage homing (saiu da tela)
        if self.current_state == SlimeBossState.RETREATING and self.y <= -self.h:
            if not hasattr(self, '_next_homing_stage'):
                self._next_homing_stage = SlimeBossState.STAGE_2_HOMING
            next_stage = self._next_homing_stage
            self._next_homing_stage = None
            return next_stage
        
        # Stage 2 Homing → ENTERING (timeout)
        if self.current_state == SlimeBossState.STAGE_2_HOMING:
            if (self.current_stage_config and 
                self.current_stage_config.duration is not None and 
                self.stage_timer >= self.current_stage_config.duration):
                self._next_normal_stage = SlimeBossState.STAGE_3_NORMAL
                return SlimeBossState.ENTERING
        
        # Stage 3 → Waiting (20% vida)
        if self.current_state == SlimeBossState.STAGE_3_NORMAL and health_pct <= 0.20:
            return SlimeBossState.WAITING_DRIPS
        
        # Stage 4 Homing → ENTERING (timeout)
        if self.current_state == SlimeBossState.STAGE_4_HOMING:
            if (self.current_stage_config and 
                self.current_stage_config.duration is not None and 
                self.stage_timer >= self.current_stage_config.duration):
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
            self.dripping_effect.max_drips = config.max_drips
            self.dripping_effect.spawn_interval = config.spawn_interval
            self.dripping_effect.set_homing_mode(
                config.is_homing,
                0, 0  # Temporary coordinates, will be updated in _update_stage_with_timer
            )
            self.dripping_effect.set_spawn_enabled(True)
        
        # Estados especiais
        if new_state == SlimeBossState.WAITING_DRIPS:
            self.dripping_effect.set_spawn_enabled(False)
        elif new_state == SlimeBossState.RETREATING:
            self.target_y = -self.h - 100
        elif new_state in [SlimeBossState.STAGE_2_HOMING, SlimeBossState.STAGE_4_HOMING]:
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

    def _update_stage_with_timer(self, dt: float, player_x: float, player_y: float) -> None:
        # Boss stays hidden during homing phases - no vertical movement
        
        self.stage_timer += dt
        if self.current_stage_config and self.current_stage_config.is_homing:
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
        if not hasattr(self, "direction"):
            self.direction = 1
        self.x += speed * dt * self.direction
        center_x = Config.SCREEN_WIDTH / 2 - self.w / 2
        if self.direction > 0 and self.x >= center_x + 50:
            self.direction = -1
        elif self.direction < 0 and self.x <= center_x - 50:
            self.direction = 1

    def draw(self, surface: pygame.Surface, fps: float = 60.0) -> None:
        # Draw the slime sprite stretched to boss dimensions (with simple fallback)
        offset_x, offset_y = (0, 0)

        # ✅ VERIFICAR SE HÁ FRAMES ANTES DE USAR:
        if self.animation_frames and len(self.animation_frames) > 0:
            try:
                frame = self.animation_frames[self.current_frame]
                scaled_frame = pygame.transform.smoothscale(
                    frame, (int(self.w), int(self.h))
                )
                surface.blit(
                    scaled_frame, (int(self.x + offset_x), int(self.y + offset_y))
                )
            except Exception as e:
                print(f"⚠️ SlimeBoss: Erro ao desenhar frame {self.current_frame}: {e}")
                # Fallback
                rect = pygame.Rect(
                    int(self.x + offset_x),
                    int(self.y + offset_y),
                    int(self.w),
                    int(self.h),
                )
                pygame.draw.rect(surface, (0, 255, 100), rect)
                font = pygame.font.Font(None, 48)
                text = font.render("SLIME BOSS", True, (255, 255, 255))
                text_rect = text.get_rect(center=(rect.centerx, rect.centery))
                surface.blit(text, text_rect)
        else:
            # Fallback: retângulo vermelho
            rect = pygame.Rect(
                int(self.x + offset_x), int(self.y + offset_y), int(self.w), int(self.h)
            )
            pygame.draw.rect(surface, (0, 255, 100), rect)  # Verde gosma
            # Desenhar texto "SLIME" no centro
            font = pygame.font.Font(None, 48)
            text = font.render("SLIME BOSS", True, (255, 255, 255))
            text_rect = text.get_rect(center=(rect.centerx, rect.centery))
            surface.blit(text, text_rect)

        # Draw dripping effect
        self.dripping_effect.draw(surface)

        # Draw health bar across the full screen width
        bar_height = 20
        bar_y = 0  # Top of the screen
        # Background bar (full width, gray)
        pygame.draw.rect(surface, (100, 100, 100), (0, bar_y, Config.SCREEN_WIDTH, bar_height))
        # Health bar (green, proportional to health)
        health_ratio = self.health / self.max_health
        health_width = int(Config.SCREEN_WIDTH * health_ratio)
        pygame.draw.rect(surface, (0, 255, 0), (0, bar_y, health_width, bar_height))

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    @property
    def mask(self) -> pygame.mask.Mask:
        """Generate pixel-perfect collision mask from current animation frame with dual caching."""
        current_size = (int(self.w), int(self.h))

        # Clear cache if boss size changed
        if current_size != self._last_mask_size:
            self._mask_cache.clear()
            self._scaled_frame_cache.clear()
            self._last_mask_size = current_size

        # Return cached mask if available
        if self.current_frame in self._mask_cache:
            return self._mask_cache[self.current_frame]

        # Manage cache size - remove oldest entries if cache is full
        if len(self._mask_cache) >= self._mask_cache_max_size:
            # Remove the oldest frame (simple FIFO - could be improved with LRU)
            oldest_frame = min(self._mask_cache.keys())
            del self._mask_cache[oldest_frame]
            if oldest_frame in self._scaled_frame_cache:
                del self._scaled_frame_cache[oldest_frame]

        # Get or create scaled frame
        if self.current_frame not in self._scaled_frame_cache:
            if (
                not self.animation_frames
                or len(self.animation_frames) <= self.current_frame
            ):
                # Fallback: create a dummy scaled surface
                scaled_frame = pygame.Surface(current_size)
                scaled_frame.fill((255, 255, 255, 255))  # White with alpha
            else:
                try:
                    frame = self.animation_frames[self.current_frame]
                    # Scale the frame to boss dimensions
                    scaled_frame = pygame.transform.smoothscale(frame, current_size)
                except Exception as e:
                    print(
                        f"⚠️ SlimeBoss: Erro ao escalonar frame {self.current_frame}: {e}"
                    )
                    # Fallback: create a dummy scaled surface
                    scaled_frame = pygame.Surface(current_size)
                    scaled_frame.fill((255, 255, 255, 255))

            self._scaled_frame_cache[self.current_frame] = scaled_frame

        # Create mask from cached scaled frame
        try:
            mask = pygame.mask.from_surface(
                self._scaled_frame_cache[self.current_frame]
            )
        except Exception as e:
            print(
                f"⚠️ SlimeBoss: Erro ao criar máscara para frame {self.current_frame}: {e}"
            )
            # Fallback: rectangular mask
            mask = pygame.mask.Mask(current_size, fill=True)

        # Cache the mask
        self._mask_cache[self.current_frame] = mask
        return mask

    def check_drip_damage(
        self, player_rect: pygame.Rect, entity_manager: Optional["EntityManager"] = None
    ) -> int:
        """Verifica se alguma gota acertou o jogador e retorna o dano.

        Args:
            player_rect: Retângulo do jogador
            entity_manager: EntityManager para spawnar efeitos de partículas (opcional)
        """
        return self.dripping_effect.check_collisions(player_rect, entity_manager)
