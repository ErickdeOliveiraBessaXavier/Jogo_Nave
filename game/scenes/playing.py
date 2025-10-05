import pygame
import random
import math
from typing import TYPE_CHECKING
from ..core.state import Scene
from ..core.config import Config
from ..render.renderer import Renderer
from ..entities.ship import Ship
from ..entities.bullet import Bullet
from ..entities.explosion import Explosion
from ..systems.spawner import EnemySpawner, PowerUpSpawner
from ..systems.collisions import Collisions
from ..systems.entity_manager import EntityManager
from ..entities.floating_score import FloatingScore
from ..core.levels import LEVELS
from ..core.assets import get_font
from ..core import colors
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..app import GameApp


class PlayingScene(Scene):
    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = Renderer()
        self.ship = Ship(Config.SCREEN_WIDTH / 2 - 20, Config.SCREEN_HEIGHT - 80)
        self.entity_manager = EntityManager()

        self.current_level_index = 0
        self.level_config = LEVELS[self.current_level_index]
        self.enemies_destroyed_in_level = 0
        self.boss_fight_active = False
        self.pre_boss_transition = False
        self.pre_boss_timer = 0.0
        self.warning_sound_played = False  # Flag para controlar o som de warning
        
        # Sistema de warning em 3 estágios
        self.warning_stage = 0  # 0=idle, 1=pre-delay, 2=warning-active, 3=post-delay
        self.warning_stage_timer = 0.0

        self.level_transition_active = False
        self.level_transition_timer = 0.0
        self.level_transition_delay = Config.LEVEL_TRANSITION_DELAY  # segundos
        
        # Iniciar música de fundo
        sound_manager.play_background_music()

        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = Config.SCREEN_SHAKE_NORMAL
        self.warning_timer = 0.0
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))

        # Inicializar spawner com delay inicial apenas para fase 1
        is_initial_level = (self.current_level_index == 0)
        self.enemy_spawner = EnemySpawner(self.level_config, is_initial_level)
        self.powerup_spawner = PowerUpSpawner()
        self.collisions = Collisions()

        self.score = 0
        self.lives = Config.INITIAL_LIVES
        self.ship.lives = self.lives
        self.total_enemies_destroyed = 0
        self.shoot_cd = 0.0

        # Sequência de Game Over
        self.game_over_sequence_active = False
        self.game_over_timer = 0.0
        self.game_over_font_title = get_font(80)
        self.game_over_font_subtitle = get_font(30)

    def update(self, dt: float):
        if self.game_over_sequence_active:
            self.game_over_timer += dt
            slow_mo_dt = dt * 0.2

            # Atualiza entidades em câmera lenta
            from typing import Any

            entity_lists: list[list[Any]] = [
                self.entity_manager.enemies,
                self.entity_manager.bullets,
                self.entity_manager.alien_bullets,
                self.entity_manager.boss_lasers,
                self.entity_manager.explosions,
                self.entity_manager.powerups,
                self.entity_manager.floating_scores,
            ]
            for entity_list in entity_lists:
                for entity in entity_list:
                    entity.update(slow_mo_dt)
            if self.entity_manager.boss:
                lasers_fired, spawned_meteors = self.entity_manager.boss.update(
                    slow_mo_dt, self.ship.rect.centerx, self.ship.rect.centery
                )
                if lasers_fired:
                    self.entity_manager.boss_lasers.extend(lasers_fired)
                if spawned_meteors:
                    self.entity_manager.enemies.extend(spawned_meteors)

            self.entity_manager.cleanup()
            return

        # Timers
        self.shoot_cd = max(0.0, self.shoot_cd - dt)
        self.warning_timer = max(0.0, self.warning_timer - dt)

        if self.entity_manager.boss and self.entity_manager.boss.state == "entering":
            self.screen_shake_timer = 0.1  # Keep shaking while boss is entering
        else:
            self.screen_shake_timer = max(0.0, self.screen_shake_timer - dt)

        if self.level_transition_active:
            if self._all_animations_finished():
                self.level_transition_timer += dt
                if self.level_transition_timer >= self.level_transition_delay:
                    self._start_next_level()

        self.ship.update(dt)
        held = self.app.input.poll_held()
        self.ship.move(held, dt)

        # Tiro contínuo com tecla segurada
        if (
            "hold_shoot" in held
            and self.shoot_cd == 0.0
            # Permitir tiros durante transições para destruir inimigos restantes
        ):
            bullet_positions = self.ship.bullet_spawn()
            for pos in bullet_positions:
                self.entity_manager.bullets.append(Bullet(*pos))
            # Tocar som de tiro (varia entre os 3 sons automaticamente)
            sound_manager.play_shot()
            # Aplicar multiplicador de velocidade de ataque do power-up de velocidade
            cooldown = Config.SHOOT_COOLDOWN / self.ship.attack_speed_multiplier
            self.shoot_cd = cooldown

        if (
            not self.boss_fight_active
            and not self.pre_boss_transition
            and not self.level_transition_active
        ):
            self.enemy_spawner.update(
                dt,
                self.entity_manager.enemies,
                self.ship.rect.centerx,
                self.ship.rect.centery,
            )
            self.powerup_spawner.update(dt, self.entity_manager.powerups)

        self.entity_manager.update(dt, self.ship.rect.centerx, self.ship.rect.centery)

        self.entity_manager.cleanup()

        # Processar colisões sempre (incluindo durante transições)
        self._handle_collisions()

        # Lógica de progressão de fase
        if self.pre_boss_transition:
            if not self.entity_manager.enemies and self.warning_stage == 0:
                # Iniciar sequência de warning em 3 estágios
                self.warning_stage = 1  # Estágio 1: Pre-delay
                self.warning_stage_timer = 0.0
                self.warning_sound_played = False
            
            self._update_warning_system(dt)
            
        elif not self.boss_fight_active and not self.level_transition_active:
            self._check_level_progression()
        elif self.entity_manager.boss and self.entity_manager.boss.dead:
            self._end_boss_fight()
    
    def _update_warning_system(self, dt: float):
        """Atualiza o sistema de warning em 3 estágios."""
        self.warning_stage_timer += dt
        
        if self.warning_stage == 1:  # Estágio 1: Pre-delay (5s)
            if self.warning_stage_timer >= Config.BOSS_PRE_WARNING_DELAY:
                self.warning_stage = 2
                self.warning_stage_timer = 0.0
                self.warning_timer = Config.BOSS_WARNING_DURATION
                self.screen_shake_timer = Config.BOSS_WARNING_DURATION
                # Tocar som de warning
                if not self.warning_sound_played:
                    sound_manager.play_warning()
                    self.warning_sound_played = True
                    
        elif self.warning_stage == 2:  # Estágio 2: Warning ativo (3s)
            if self.warning_stage_timer >= Config.BOSS_WARNING_DURATION:
                self.warning_stage = 3
                self.warning_stage_timer = 0.0
                self.warning_timer = 0.0  # Parar warning visual
                self.screen_shake_timer = 0.0  # Parar shake
                # Parar som de warning quando o visual termina
                sound_manager.stop_warning()
                
        elif self.warning_stage == 3:  # Estágio 3: Post-delay (3s)
            if self.warning_stage_timer >= Config.BOSS_POST_WARNING_DELAY:
                self._start_boss_fight()

    def _all_animations_finished(self) -> bool:
        return (
            not self.entity_manager.explosions
            # Remover balas do jogador da verificação para permitir transições durante tiros
            # and not self.entity_manager.bullets  
            and not self.entity_manager.alien_bullets
            and not self.entity_manager.boss_lasers
            and not self.entity_manager.enemies
        )

    def _handle_collisions(self):
        gain, destroyed, score_events = self.collisions.bullets_vs_enemies(
            self.entity_manager.bullets,
            self.entity_manager.enemies,
            self.entity_manager.explosions,
        )
        for x, y, pts in score_events:
            self.entity_manager.floating_scores.append(FloatingScore(x, y, pts))
        self.score += gain
        self.total_enemies_destroyed += destroyed
        self.enemies_destroyed_in_level += destroyed

        if self.entity_manager.boss:
            score_gain = self.collisions.bullets_vs_boss(
                self.entity_manager.bullets,
                self.entity_manager.boss,
                self.entity_manager.explosions,
                self.entity_manager.floating_scores,
            )
            self.score += score_gain
        if self.collisions.ship_vs_enemies(
            self.ship, self.entity_manager.enemies, self.entity_manager.explosions
        ):
            self._handle_ship_hit()
        if self.entity_manager.boss and self.collisions.ship_vs_boss(
            self.ship, self.entity_manager.boss, self.entity_manager.explosions
        ):
            self._handle_ship_hit()
        if self.collisions.alien_bullets_vs_ship(
            self.ship, self.entity_manager.alien_bullets
        ):
            self._handle_ship_hit()
        if self.collisions.laser_vs_ship(self.ship, self.entity_manager.boss_lasers):
            self._handle_ship_hit()

        collected_powerups = self.collisions.ship_vs_powerups(
            self.ship, self.entity_manager.powerups
        )
        if collected_powerups:
            for kind in collected_powerups:
                if kind == "life":
                    self.lives += 1
                    self.ship.lives = self.lives
                elif kind == "shield":
                    self.ship.invuln = max(
                        self.ship.invuln, Config.SHIELD_DURATION * 1000
                    )
                elif kind == "double_shot":
                    self.ship.double_shot_timer = max(
                        self.ship.double_shot_timer, Config.DOUBLE_SHOT_DURATION
                    )
                elif kind == "speed":
                    self.ship.speed_boost_timer = max(
                        self.ship.speed_boost_timer, Config.SPEED_BOOST_DURATION
                    )
                elif kind == "score":
                    self.score += Config.POWERUP_SCORE_BONUS
                elif kind == "rainbow":
                    self.lives += 1
                    self.ship.lives = self.lives
                    self.ship.invuln = max(
                        self.ship.invuln, Config.RAINBOW_DURATION * 1000
                    )
                    self.ship.double_shot_timer = max(
                        self.ship.double_shot_timer, Config.RAINBOW_DURATION
                    )
                    self.ship.speed_boost_timer = max(
                        self.ship.speed_boost_timer, Config.RAINBOW_DURATION
                    )
                    self.score += Config.POWERUP_SCORE_BONUS * 2

    def _handle_ship_hit(self):
        if self.ship.invuln > 0 or self.game_over_sequence_active:
            return
        self.lives -= 1
        self.ship.lives = self.lives
        if self.lives > 0:
            self.ship.invuln = Config.INVULN_TIME * 1000
        else:
            self.game_over_sequence_active = True
            self.game_over_timer = 0.0
            self.ship.visible = False
            # Tocar som de explosão da nave
            sound_manager.play_ship_explosion()
            self.entity_manager.explosions.append(
                Explosion(self.ship.rect.centerx, self.ship.rect.centery, size=100)
            )
            self.screen_shake_timer = 0.5
            self.screen_shake_intensity = Config.SCREEN_SHAKE_GAME_OVER

    def _check_level_progression(self):
        if self.enemies_destroyed_in_level >= self.level_config.enemies_to_clear:
            self.enemy_spawner.stop()
            if not self.entity_manager.enemies:
                if self.level_config.boss_type:
                    self.pre_boss_transition = True
                else:
                    self._advance_to_next_level()

    def _start_boss_fight(self):
        self.pre_boss_transition = False
        self.pre_boss_timer = 0.0
        self.warning_sound_played = False  # Resetar flag para próximo boss
        # Resetar sistema de warning
        self.warning_stage = 0
        self.warning_stage_timer = 0.0
        self.warning_timer = 0.0
        
        self.boss_fight_active = True
        self.screen_shake_timer = Config.BOSS_ENTRY_SHAKE_DURATION
        
        # Parar sons de warning e outros efeitos
        sound_manager.stop_warning()
        sound_manager.stop_all_sfx()
        
        if self.level_config.boss_type:
            self.entity_manager.boss = self.level_config.boss_type(
                Config.SCREEN_WIDTH / 2 - 50, 50
            )
            # Tocar música do boss
            sound_manager.play_boss_music()

    def _end_boss_fight(self):
        if not self.entity_manager.boss:
            return

        # Efeitos da explosão
        boss_center = (
            self.entity_manager.boss.x + self.entity_manager.boss.w / 2,
            self.entity_manager.boss.y + self.entity_manager.boss.h / 2,
        )
        self.screen_shake_timer = Config.SCREEN_SHAKE_BOSS_DEATH_DURATION
        self.screen_shake_intensity = Config.SCREEN_SHAKE_BOSS_DEATH

        # Tocar som de explosão do boss
        sound_manager.play_explosion_boss()

        # Explosões em círculo
        num_explosions = Config.BOSS_EXPLOSION_COUNT
        radius = Config.BOSS_EXPLOSION_RADIUS
        for i in range(num_explosions):
            angle = (360 / num_explosions) * i
            rad_angle = math.radians(angle)
            ex = boss_center[0] + radius * math.cos(rad_angle)
            ey = boss_center[1] + radius * math.sin(rad_angle)
            self.entity_manager.explosions.append(
                Explosion(ex, ey, size=Config.BOSS_EXPLOSION_SMALL_SIZE)
            )

        # Explosão central maior
        self.entity_manager.explosions.append(
            Explosion(
                boss_center[0], boss_center[1], size=Config.BOSS_EXPLOSION_LARGE_SIZE
            )
        )

        self.entity_manager.boss = None
        self.boss_fight_active = False
        self.score += Config.BOSS_DEFEAT_SCORE
        # Voltar para música normal
        sound_manager.play_background_music()
        self._advance_to_next_level()

    def _advance_to_next_level(self):
        if not self.level_transition_active:
            self.level_transition_active = True
            self.level_transition_timer = 0.0

    def _start_next_level(self):
        self.level_transition_active = False
        self.current_level_index += 1
        if self.current_level_index < len(LEVELS):
            self.level_config = LEVELS[self.current_level_index]
            self.enemy_spawner.set_level(self.level_config)
            self.enemies_destroyed_in_level = 0
        else:
            # Opcional: o que fazer quando todas as fases terminam?
            # Por enquanto, apenas reinicia a última fase.
            self.enemy_spawner.set_level(self.level_config)
            self.enemies_destroyed_in_level = 0

        # Usar método que preserva balas do jogador durante transições
        self.entity_manager.clear_for_level_transition()

    def handle_event(self, event: pygame.event.Event):
        if self.game_over_sequence_active:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                from .preparation import PreparationScene

                self.app.states.switch(PreparationScene(self.app))
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                from .paused import PausedScene

                self.app.states.switch(PausedScene(self.app, previous_scene=self))

    def render(self, surface: pygame.Surface):
        self.r.background(self.game_surface, dt=1.0 / Config.FPS)

        self.entity_manager.draw(self.game_surface)
        self.ship.draw(self.game_surface)
        self.r.hud(
            self.game_surface,
            self.score,
            self.lives,
            self.total_enemies_destroyed,
            self.ship,
            self.level_config.level_number,
        )

        shake_offset = (0, 0)
        if self.screen_shake_timer > 0:
            shake_offset = (
                random.randint(
                    -self.screen_shake_intensity, self.screen_shake_intensity
                ),
                random.randint(
                    -self.screen_shake_intensity, self.screen_shake_intensity
                ),
            )
        surface.blit(self.game_surface, shake_offset)

        if self.warning_timer > 0 and int(self.warning_timer * 5) % 2 == 1:
            warning_text = self.warning_font.render("WARNING!", True, colors.RED)
            text_rect = warning_text.get_rect(
                center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2)
            )
            surface.blit(warning_text, text_rect)

        if self.game_over_sequence_active:
            progress = min(
                1.0, self.game_over_timer / Config.GAME_OVER_FADE_DURATION
            )  # Duração do fade-in principal

            overlay = pygame.Surface(
                (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
            )
            overlay_alpha = int(
                progress * Config.GAME_OVER_OVERLAY_ALPHA
            )  # Um pouco mais escuro
            overlay.fill((0, 0, 0, overlay_alpha))

            # Renderiza "GAME OVER"
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

            # Renderiza pontuação e instrução de reinício após um atraso
            restart_delay = Config.GAME_OVER_RESTART_DELAY  # segundos
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
