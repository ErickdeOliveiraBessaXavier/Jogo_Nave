import pygame
import random
from typing import List
from collections import deque
from ..core.assets import get_image, BASE_DIR
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.sprite_loader import sprite_loader
from .boss import Boss
from .boss_laser import BossLaser
from .meteor import Meteor
from .boss_square import BossSquare


class SlimeBoss(Boss):
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
            print("❌ SlimeBoss: NENHUM frame foi carregado! Verifique o caminho dos sprites.")
        elif len(frames) < 24:
            print(f"⚠️ SlimeBoss: Apenas {len(frames)}/24 frames foram carregados.")
        else:
            print(f"✅ SlimeBoss: {len(frames)} frames carregados com sucesso.")

        cls._animation_frames = frames
        cls._frames_loaded = True
        return frames

    def __init__(self, x: float, y: float, health: int | None = None):
        # Initialize base Boss to get full behavior
        super().__init__(x, y, health if health is not None else int(Config.BOSS_HEALTH * 1.2))

        # Make the boss span the entire screen width plus movement margins
        self.w = Config.SCREEN_WIDTH + 100  # +50px left +50px right margin
        self.h = 600  # Taller to not be flattened

        # Position from left to right
        self.x = 0
        self.target_y = -100  # Final position higher up, not too low
        self.y = -self.h  # More off-screen from the top

        # No lateral movement, keep it spanning the screen
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
        self._mask_cache_max_size = 6  # Keep masks for last 6 frames to balance memory/performance

        # Disable floating squares for SlimeBoss
        self.floating_squares = []
        self.position_history = deque(maxlen=30)

    def _init_floating_squares(self) -> None:
        """SlimeBoss doesn't use floating squares."""
        pass

    def update(self, dt: float, player_x: float, player_y: float | None = None) -> tuple[List[BossLaser], List[Meteor], List[BossSquare]]:
        # Update animation always
        self._update_animation(dt)
        
        # Call parent update
        return super().update(dt, player_x, player_y)

    def can_take_damage(self) -> bool:
        return self.state != "entering" and not self.dead

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

    def _update_active_state(self, dt: float) -> None:
        """Move lateralmente 50px para esquerda e direita."""
        # Velocidade de movimento
        speed = 50.0  # pixels/segundo (ajuste conforme necessário)
        if self.frenzy_mode:
            speed *= 1.5  # 50% mais rápido no frenzy
        
        # Mover horizontalmente
        if not hasattr(self, 'direction'):
            self.direction = 1  # 1 = direita, -1 = esquerda
        
        self.x += speed * dt * self.direction
        
        # Inverter direção nos limites de 50px
        if self.direction > 0 and self.x >= 50:
            self.direction = -1
        elif self.direction < 0 and self.x <= -50:
            self.direction = 1

    def _update_animation(self, dt: float) -> None:
        """Update animation frame."""
        if not self.animation_frames or len(self.animation_frames) == 0:
            return  # Não atualizar se não há frames
        
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

    def draw(self, surface: pygame.Surface) -> None:
        import pygame  # Ensure pygame is available in local scope
        # Draw the slime sprite stretched to boss dimensions (with simple fallback)
        offset_x, offset_y = (0, 0)
        if self.frenzy_shake_timer > 0:
            offset_x = random.randint(-3, 3)

        # ✅ VERIFICAR SE HÁ FRAMES ANTES DE USAR:
        if self.animation_frames and len(self.animation_frames) > 0:
            try:
                frame = self.animation_frames[self.current_frame]
                scaled_frame = pygame.transform.smoothscale(frame, (int(self.w), int(self.h)))
                surface.blit(scaled_frame, (int(self.x + offset_x), int(self.y + offset_y)))
            except Exception as e:
                print(f"⚠️ SlimeBoss: Erro ao desenhar frame {self.current_frame}: {e}")
                # Fallback
                rect = pygame.Rect(int(self.x + offset_x), int(self.y + offset_y), int(self.w), int(self.h))
                pygame.draw.rect(surface, (0, 255, 100), rect)
                import pygame.font
                font = pygame.font.Font(None, 48)
                text = font.render("SLIME BOSS", True, (255, 255, 255))
                text_rect = text.get_rect(center=(rect.centerx, rect.centery))
                surface.blit(text, text_rect)
        else:
            # Fallback: retângulo vermelho
            rect = pygame.Rect(int(self.x + offset_x), int(self.y + offset_y), int(self.w), int(self.h))
            pygame.draw.rect(surface, (0, 255, 100), rect)  # Verde gosma
            # Desenhar texto "SLIME" no centro
            import pygame.font
            font = pygame.font.Font(None, 48)
            text = font.render("SLIME BOSS", True, (255, 255, 255))
            text_rect = text.get_rect(center=(rect.centerx, rect.centery))
            surface.blit(text, text_rect)

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
            if not self.animation_frames or len(self.animation_frames) <= self.current_frame:
                # Fallback: create a dummy scaled surface
                scaled_frame = pygame.Surface(current_size)
                scaled_frame.fill((255, 255, 255, 255))  # White with alpha
            else:
                try:
                    frame = self.animation_frames[self.current_frame]
                    # Scale the frame to boss dimensions
                    scaled_frame = pygame.transform.smoothscale(frame, current_size)
                except Exception as e:
                    print(f"⚠️ SlimeBoss: Erro ao escalonar frame {self.current_frame}: {e}")
                    # Fallback: create a dummy scaled surface
                    scaled_frame = pygame.Surface(current_size)
                    scaled_frame.fill((255, 255, 255, 255))
            
            self._scaled_frame_cache[self.current_frame] = scaled_frame
        
        # Create mask from cached scaled frame
        try:
            mask = pygame.mask.from_surface(self._scaled_frame_cache[self.current_frame])
        except Exception as e:
            print(f"⚠️ SlimeBoss: Erro ao criar máscara para frame {self.current_frame}: {e}")
            # Fallback: rectangular mask
            mask = pygame.mask.Mask(current_size, fill=True)
        
        # Cache the mask
        self._mask_cache[self.current_frame] = mask
        return mask
