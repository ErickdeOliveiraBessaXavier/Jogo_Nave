import pygame
from typing import TYPE_CHECKING
from ..core.state import Scene
from typing import TYPE_CHECKING
from ..core.state import Scene
from ..core.config import config as Config
from ..core.assets import get_font
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..app import GameApp
    from .playing import PlayingScene


class GameOverScene(Scene):
    def __init__(self, app: "GameApp", score: int, playing_scene: "PlayingScene"):
        super().__init__(app)
        self.score = score
        self.playing_scene = (
            playing_scene  # Reference to the playing scene for rendering
        )
        self.r = playing_scene.r  # Reusar o MESMO renderer da cena de jogo

        self.game_over_timer = 0.0
        self.game_over_font_title = get_font(80)
        self.game_over_font_subtitle = get_font(30)
        self.game_surface = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        )  # Surface to render frozen game state

        # Game over effects
        self.playing_scene.ship.visible = False
        sound_manager.play_ship_explosion()
        self.playing_scene.entity_manager.spawn_explosion(
            self.playing_scene.ship.rect.centerx,
            self.playing_scene.ship.rect.centery,
            size=100,
        )
        self.playing_scene.screen_shake_timer = 0.5
        self.playing_scene.screen_shake_intensity = Config.SCREEN_SHAKE_GAME_OVER

    def update(self, dt: float):
        self.game_over_timer += dt
        slow_mo_dt = dt * 0.2

        # Update entities in slow motion
        self.playing_scene.entity_manager.update_for_game_over_slow_motion(
            slow_mo_dt,
            self.playing_scene.ship.rect.centerx,
            self.playing_scene.ship.rect.centery,
        )

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            # Restart the game by switching to a new PlayingScene
            from .playing import PlayingScene

            self.app.states.switch(
                PlayingScene(
                    self.app,
                    self.playing_scene.level_manager,
                    self.playing_scene.difficulty_preset,
                )
            )

    def render(self, surface: pygame.Surface):
        # Render the frozen game state first
        # Copy rendering logic from PlayingScene without game over overlay
        dt = getattr(self.playing_scene, "last_dt", 1.0 / Config.FPS)
        speed_multiplier = 1.0
        boss_active = bool(
            self.playing_scene.boss_fight_active
            and self.playing_scene.entity_manager.boss
            and not self.playing_scene.entity_manager.boss.dead
        )
        if boss_active:
            speed_multiplier = Config.BOSS_WARP_SPEED_MULTIPLIER

        self.r.background(self.game_surface, dt=dt, speed_multiplier=speed_multiplier)

        self.playing_scene.entity_manager.draw(
            self.game_surface,
            self.playing_scene.ship.rect.centerx,
            self.playing_scene.ship.rect.centery,
        )
        self.playing_scene.ship.draw(self.game_surface)
        self.r.hud(
            self.game_surface,
            self.playing_scene.score,
            self.playing_scene.lives,
            self.playing_scene.total_enemies_destroyed,
            self.playing_scene.ship,
            self.playing_scene.level_config.level_number,
            self.playing_scene.difficulty_preset,
        )

        shake_offset = (0, 0)
        if self.playing_scene.screen_shake_timer > 0:
            import random

            shake_offset = (
                random.randint(
                    -self.playing_scene.screen_shake_intensity,
                    self.playing_scene.screen_shake_intensity,
                ),
                random.randint(
                    -self.playing_scene.screen_shake_intensity,
                    self.playing_scene.screen_shake_intensity,
                ),
            )
        surface.blit(self.game_surface, shake_offset)

        # Render the game over overlay and text
        progress = min(
            1.0, self.game_over_timer / Config.GAME_OVER_FADE_DURATION
        )  # Main fade-in duration

        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay_alpha = int(progress * Config.GAME_OVER_OVERLAY_ALPHA)  # A bit darker
        overlay.fill((0, 0, 0, overlay_alpha))

        # Render "GAME OVER"
        text_alpha = int(progress * 255)
        title_text = self.game_over_font_title.render(
            "GAME OVER", True, (255, 255, 255)
        )
        title_text.set_alpha(text_alpha)
        title_rect = title_text.get_rect(
            center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2 - 40)
        )

        surface.blit(overlay, (0, 0))
        surface.blit(title_text, title_rect)

        # Render score and restart instruction after a delay
        restart_delay = Config.GAME_OVER_RESTART_DELAY  # seconds
        if self.game_over_timer > restart_delay:
            sub_progress = min(1.0, (self.game_over_timer - restart_delay) / 1.0)
            sub_alpha = int(sub_progress * 255)

            score_text = self.game_over_font_subtitle.render(
                f"Score: {self.score}", True, (255, 255, 255)
            )
            score_text.set_alpha(sub_alpha)
            score_rect = score_text.get_rect(
                center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2 + 50)
            )
            surface.blit(score_text, score_rect)

            restart_text = self.game_over_font_subtitle.render(
                "Pressione R para reiniciar", True, (255, 255, 255)
            )
            restart_text.set_alpha(sub_alpha)
            restart_rect = restart_text.get_rect(
                center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2 + 100)
            )
            surface.blit(restart_text, restart_rect)
