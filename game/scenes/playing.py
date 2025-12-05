import pygame
import random
import math
import time
from typing import TYPE_CHECKING, Optional, cast
from ..core.state import Scene
from ..core.config import config as Config
from ..render.renderer import Renderer
from ..entities.ship import Ship
from ..systems.spawner import EnemySpawner, PowerUpSpawner, StarSpawner
from ..systems.collisions import Collisions
from ..systems.entity_manager import EntityManager
from ..entities.floating_score import FloatingScore
from ..core.levels import LevelManager, get_level_config, LevelConfig
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.assets import get_font
from ..core import colors
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..entities.mini_ship import MiniShip
from ..entities.spike_boss_laser import SpikeBossLaser
from ..core.meta_progression import PlayerProfile
from ..core.paths import get_profile_path
from ..core.upgrades import create_upgrade, ActiveUpgrade
from ..core.upgrades_config import UPGRADE_SLOT_COUNT

if TYPE_CHECKING:
    from ..app import GameApp


class PlayingScene(Scene):
    def __init__(
        self,
        app: "GameApp",
        level_manager: LevelManager,
        difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
    ):
        super().__init__(app)
        self.level_manager = level_manager
        self.difficulty_preset = difficulty_preset
        self.difficulty_settings = DifficultySettings.get_settings(difficulty_preset)
        self.last_dt = 1.0 / Config.FPS
        self.r = Renderer()
        self.ship = Ship(
            Config.SCREEN_WIDTH / 2 - 20, Config.SCREEN_HEIGHT + 100
        )  # Start 100 pixels below the screen
        self.ship.is_entering = True
        self.entity_manager = EntityManager()
        self.first_entry = True

        # Aplicar configurações de dificuldade após criar a nave
        self._apply_difficulty_settings()
        self.enemies_destroyed_in_level = 0
        self.boss_fight_active = False
        self.pre_boss_transition = False
        self.pre_boss_timer = 0.0
        self.warning_sound_played = False  # Flag para controlar o som de warning

        # Sistema de warning em 3 estágios
        self.warning_stage = 0  # 0=idle, 1=pre-delay, 2=warning-active, 3=post-delay
        self.warning_stage_timer = 0.0

        # Music transition control
        self.music_fade_started = False
        self.boss_music_started = False

        # Level transition control
        self.level_transition_active = False
        self.level_transition_timer = 0.0
        self.level_transition_delay = Config.LEVEL_TRANSITION_DELAY  # segundos

        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = Config.SCREEN_SHAKE_NORMAL
        self.warning_timer = 0.0
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)
        # Meta-progression system
        self.player_profile = PlayerProfile(get_profile_path())
        self.player_profile.start_session()

        self.current_level_index = 0
        self.level_config = self._get_adjusted_level_config(
            self.current_level_index + 1
        )
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))

        # Inicializar spawner com delay inicial apenas para fase 1
        is_initial_level = self.current_level_index == 0
        self.enemy_spawner = EnemySpawner(
            self.level_manager,
            self.entity_manager.meteor_pool,
            is_initial_level,
            self.difficulty_preset,
            self.enemy_health_multiplier,
        )
        self.powerup_spawner = PowerUpSpawner()
        self.collisions = Collisions()

        # Star spawner centralizado
        self.star_spawner = StarSpawner()

        # Cache de multiplicadores para otimização
        self._base_score_multiplier = (
            self.level_config.score_multiplier
            * self.difficulty_settings["rewards_multiplier"]
        )
        self._boss_type_cache = None  # Cache do tipo de boss

        # Cache de regras especiais para otimização
        self._special_rules = self.difficulty_settings.get("special_rules", [])
        self._no_powerups_mode = "no_powerups" in self._special_rules

        # Pré-calcular valores de power-ups para otimização
        self._powerup_values = {
            "shield_duration": Config.SHIELD_DURATION * 1000,
            "double_shot_duration": Config.DOUBLE_SHOT_DURATION,
            "speed_boost_duration": Config.SPEED_BOOST_DURATION,
            "piercing_shot_duration": Config.PIERCING_SHOT_DURATION,
            "mini_ships_duration": Config.MINI_SHIPS_DURATION,
            "rainbow_duration": Config.RAINBOW_DURATION,
            "rainbow_duration_invuln": Config.RAINBOW_DURATION * 1000,
            "rainbow_score": Config.POWERUP_SCORE_BONUS * 2,
        }

        # Sistema de limpeza de inimigos restantes
        self.enemy_cleanup_active = False  # Se o timer de limpeza está ativo
        self.enemy_cleanup_timer = 0.0  # Timer para limpeza dos inimigos restantes
        self.enemy_cleanup_duration = 20.0  # 15 segundos para limpeza
        self.enemy_blink_timer = 0.0  # Timer para efeito de piscar
        self.enemy_blink_interval = 0.2  # Intervalo de piscar (200ms)
        self.enemy_visible = True  # Controle de visibilidade para piscar

        # Debug FPS display (F3 toggle)
        self.show_fps = False

        # Sistema de multiplicador de score
        self.score_multiplier_timer = 0.0
        self.score_multiplier_active = False
        self.score_multiplier_value = 1.5

        # Aprimoramentos ativos (slots)
        self.upgrade_slots: list[ActiveUpgrade | None] = []
        self._init_upgrades_from_profile()

    def _apply_difficulty_settings(self):
        """Aplica configurações globais do preset de dificuldade."""
        settings = self.difficulty_settings

        # Vidas iniciais
        self.lives: int = settings["lives"]

        # Armazenar multiplicadores para uso em colisões e dano
        self.player_damage_multiplier = settings["player_damage_multiplier"]
        self.enemy_health_multiplier = settings["enemy_health_multiplier"]

        self.score: int = 0
        self.ship.lives = self.lives
        self.total_enemies_destroyed = 0
        self.shoot_cd = 0.0

        # Sistema de cheat codes
        self.cheat_buffer = ""  # Buffer para sequência de teclas
        self.god_mode = False  # Modo invulnerável

        # Estado de preparação
        self.state = "preparing"
        self.preparation_time_left = Config.PREPARATION_TIME

        # Meta-progression tracking
        self.level_start_time: Optional[float] = None
        self.level_damage_taken = 0
        self.level_powerups_collected = 0

    def _get_adjusted_level_config(self, level_number: int) -> LevelConfig:
        """Obtém configuração de nível ajustada pelo meta-progression."""
        base_config = get_level_config(level_number, self.difficulty_preset)
        return self.player_profile.get_adjusted_config(base_config)

    def enter(self):
        pygame.mouse.set_visible(False)
        if self.first_entry:
            sound_manager.music_state_manager.transition_to(MusicState.GAME)
            self.first_entry = False

    def exit(self):
        pygame.mouse.set_visible(True)

    def update(self, dt: float):
        self.last_dt = dt

        if self.state == "preparing":
            self.preparation_time_left -= dt

            # Mover a nave para a posição inicial de forma suave
            target_y = Config.SCREEN_HEIGHT - 80
            initial_y = (
                Config.SCREEN_HEIGHT + 100
            )  # Match the ship's initial y position

            if self.preparation_time_left > 0:
                elapsed_time = Config.PREPARATION_TIME - self.preparation_time_left
                progress = min(1.0, elapsed_time / Config.PREPARATION_TIME)
                # Interpolação linear para suavizar o movimento
                self.ship.y = initial_y + (target_y - initial_y) * progress
            else:
                self.ship.y = target_y
                self.state = "playing"
                self.ship.is_entering = False

                # Meta-progression: Record level attempt
                self.player_profile.record_attempt(self.current_level_index + 1)
                self.level_start_time = None  # Reset to None instead of 0.0
                self.level_damage_taken = 0
                self.level_powerups_collected = 0

        if self.state == "playing" and self.level_start_time is None:
            self.level_start_time = time.time()

            self.ship.update(
                dt, self.entity_manager
            )  # Atualiza animações da nave (ex: propulsores)
            return

        # Timers
        self.shoot_cd = max(0.0, self.shoot_cd - dt)
        self.warning_timer = max(0.0, self.warning_timer - dt)

        # Atualizar timer de multiplicador de score
        if self.score_multiplier_active:
            self.score_multiplier_timer -= dt
            if self.score_multiplier_timer <= 0.0:
                self.score_multiplier_timer = 0.0
                self.score_multiplier_active = False

        # Atualizar upgrades (cooldown/duração)
        self._update_upgrades(dt)

        if self.entity_manager.boss and self.entity_manager.boss.state == "entering":
            self.screen_shake_timer = 0.1  # Keep shaking while boss is entering
        else:
            self.screen_shake_timer = max(0.0, self.screen_shake_timer - dt)

        if self.level_transition_active:
            if self._all_animations_finished():
                self.level_transition_timer += dt
                if self.level_transition_timer >= self.level_transition_delay:
                    self._start_next_level()

        self.ship.update(dt, self.entity_manager)
        if self.ship.mini_ships_timer == 0.0 and self.entity_manager.mini_ships:
            self.entity_manager.mini_ships.clear()

        # Verificar se o boss está em pausa do frenzy
        boss_pausing = False
        if self._boss_type_cache == "spike" and self.entity_manager.boss:
            from ..entities.spike_boss import SpikeBoss

            boss_pausing = cast(SpikeBoss, self.entity_manager.boss).is_pausing_game()

        # Bloquear movimento e tiro durante entrada da nave
        if not self.ship.is_entering:
            held = self.app.input.poll_held()
            self.ship.move(held, dt)

            # Tiro contínuo com tecla segurada
            if "hold_shoot" in held and self.shoot_cd == 0.0 and not boss_pausing:
                bullet_specs = self.ship.bullet_spawn()
                for (
                    x,
                    y,
                    is_piercing,
                    is_homing,
                    is_explosive,
                    is_low_ammo,
                ) in bullet_specs:
                    base_damage = 10
                    adjusted_damage = int(base_damage * self.player_damage_multiplier)
                    self.entity_manager.spawn_bullet(
                        x,
                        y,
                        damage=adjusted_damage,
                        piercing=is_piercing,
                        homing=is_homing,
                        explosive=is_explosive,
                        low_ammo=is_low_ammo,
                    )
                    # Consumir carga de tiro explosivo se usado
                    if is_explosive:
                        self.ship.consume_explosive_shot()
                # Tocar som de tiro (varia entre os 3 sons automaticamente)
                sound_manager.play_shot()
                # Aplicar multiplicador de velocidade de ataque do power-up de velocidade
                cooldown = Config.SHOOT_COOLDOWN / self.ship.attack_speed_multiplier
                self.shoot_cd = cooldown

        # Se boss está em pausa, só atualiza o boss (com tremor)
        if boss_pausing:
            from ..entities.spike_boss import SpikeBoss

            spawned_spikes, spike_boss_lasers = cast(
                SpikeBoss, self.entity_manager.boss
            ).update(
                dt,
                self.ship.rect.centerx,
                self.ship.rect.centery,
                self.entity_manager.spikes,
            )
            if spawned_spikes:
                self.entity_manager.spikes.extend(spawned_spikes)  # type: ignore
            if spike_boss_lasers:
                self.entity_manager.boss_lasers.extend(spike_boss_lasers)  # type: ignore
            return  # Não atualiza nada mais

        if (
            not self.boss_fight_active
            and not self.pre_boss_transition
            and not self.level_transition_active
        ):
            self.enemy_spawner.update(
                dt,
                self.entity_manager,
                self.ship.rect.centerx,
                self.ship.rect.centery,
            )

            # Não spawnar power-ups no Nightmare (regra especial)
            special_rules = self.difficulty_settings.get("special_rules", [])
            if "no_powerups" not in special_rules:
                self.powerup_spawner.update(dt, self.entity_manager.powerups)

            # Spawner de estrelas
            self.star_spawner.update(dt, self.entity_manager.stars)

        self.entity_manager.update(dt, self.ship.rect.centerx, self.ship.rect.centery)

        # Processar colisões sempre (incluindo durante transições)
        self._handle_collisions()

        self.entity_manager.cleanup()

        # Lógica de progressão de fase
        if self.pre_boss_transition:
            if not self.entity_manager.enemies and self.warning_stage == 0:
                # Iniciar sequência de warning em 3 estágios
                self.warning_stage = 1  # Estágio 1: Pre-delay
                self.warning_stage_timer = 0.0
                self.warning_sound_played = False

            self._update_warning_system(dt)

        elif not self.boss_fight_active and not self.level_transition_active:
            # Atualizar timer de limpeza de inimigos se ativo
            if self.enemy_cleanup_active:
                self.enemy_cleanup_timer += dt

                # Sistema de piscar: começa nos últimos 5 segundos
                time_remaining = self.enemy_cleanup_duration - self.enemy_cleanup_timer
                if time_remaining <= 5.0:
                    # Piscar acelera conforme o tempo vai acabando
                    blink_min = 0.05  # 50ms
                    blink_max = 0.4  # 400ms
                    # Interpolação: quanto menos tempo, menor o intervalo
                    t = max(0.0, min(1.0, time_remaining / 5.0))
                    self.enemy_blink_interval = blink_min + (blink_max - blink_min) * t
                    self.enemy_blink_timer += dt
                    if self.enemy_blink_timer >= self.enemy_blink_interval:
                        self.enemy_blink_timer = 0.0
                        self.enemy_visible = not self.enemy_visible

                # Se timer expirou, marcar todos os inimigos como mortos
                if self.enemy_cleanup_timer >= self.enemy_cleanup_duration:
                    print(
                        f"⏰ TEMPO ESGOTADO! Removendo {len(self.entity_manager.enemies)} inimigos restantes automaticamente..."
                    )
                    # Marcar todos os inimigos restantes como mortos
                    for enemy in self.entity_manager.enemies[:]:
                        enemy.dead = True
                    self.entity_manager.enemies.clear()

            self._check_level_progression()
        elif self.entity_manager.boss and self.entity_manager.boss.dead:
            self._end_boss_fight()

        # Auto-save profile periodically
        self.player_profile.auto_save()

    def _update_warning_system(self, dt: float):
        """Atualiza o sistema de warning em 3 estágios."""
        self.warning_stage_timer += dt

        if self.warning_stage == 1:  # Estágio 1: Pre-delay (5s)
            # Iniciar fade-out da música 3 segundos antes do warning
            if (
                not self.music_fade_started
                and self.warning_stage_timer >= Config.BOSS_MUSIC_FADE_OUT_START
            ):
                sound_manager.fade_out_music(Config.BOSS_MUSIC_FADE_OUT_DURATION)
                self.music_fade_started = True

            if self.warning_stage_timer >= Config.BOSS_PRE_WARNING_DELAY:
                self.warning_stage = 2
                self.warning_stage_timer = 0.0
                self.warning_timer = Config.BOSS_WARNING_DURATION
                self.screen_shake_timer = Config.BOSS_WARNING_DURATION
                # Tocar som de warning (sem música de fundo)
                if not self.warning_sound_played:
                    sound_manager.play_warning()
                    self.warning_sound_played = True

        elif self.warning_stage == 2:  # Estágio 2: Warning ativo (5s) - SILÊNCIO TOTAL
            if self.warning_stage_timer >= Config.BOSS_WARNING_DURATION:
                self.warning_stage = 3
                self.warning_stage_timer = 0.0
                self.warning_timer = 0.0  # Parar warning visual
                self.screen_shake_timer = 0.0  # Parar shake
                # Parar som de warning quando o visual termina
                sound_manager.stop_warning()

        elif self.warning_stage == 3:  # Estágio 3: Post-delay (3s) - CONTINUA SILÊNCIO
            if self.warning_stage_timer >= Config.BOSS_POST_WARNING_DELAY:
                self._start_boss_fight()

    def _cache_boss_type(self):
        """Cachear tipo de boss quando ele spawna"""
        if self.entity_manager.boss:
            from ..entities.spike_boss import SpikeBoss

            self._boss_type_cache = (
                "spike" if isinstance(self.entity_manager.boss, SpikeBoss) else "normal"
            )
        else:
            self._boss_type_cache = None

    def _all_animations_finished(self) -> bool:
        """Check if all animations (explosions) have finished for level transition."""
        return not self.entity_manager.explosive_effects  # type: ignore

    def _process_cheat_input(self, event: pygame.event.Event):
        """
        Processa entrada de teclado para detectar cheat codes.
        Cheat code: '271195' para ativar/desativar invulnerabilidade.
        """
        # Obter caractere da tecla pressionada (números e letras)
        if event.key >= pygame.K_0 and event.key <= pygame.K_9:
            char = chr(event.key)
            self.cheat_buffer += char

            # Manter apenas os últimos 6 caracteres (tamanho de "271195")
            if len(self.cheat_buffer) > 6:
                self.cheat_buffer = self.cheat_buffer[-6:]

            # Verificar se o código foi digitado
            if self.cheat_buffer == "271195":
                self.god_mode = not self.god_mode
                self.cheat_buffer = ""  # Resetar buffer

                if self.god_mode:
                    print("🛡️ GOD MODE ATIVADO - Invulnerabilidade ligada!")
                    if hasattr(sound_manager, "play_powerup"):
                        sound_manager.play_powerup()  # type: ignore
                else:
                    print("⚔️ GOD MODE DESATIVADO - Invulnerabilidade desligada!")

    def _handle_collisions(self):
        # A grid JÁ FOI CONSTRUÍDA no entity_manager.update()
        enemy_grid = self.entity_manager.enemy_spatial_grid

        # Colisões com TODOS os inimigos (normais + formações) usando grid única
        gain: int = 0
        destroyed: int = 0
        score_events: list[tuple[float, float, int]] = []
        gain, destroyed, score_events = self.collisions.bullets_vs_enemies(
            self.entity_manager.bullets,
            self.entity_manager.mine_explosions,
            self.ship,
            enemy_grid,
            self.entity_manager.enemies,  # Para adicionar fragments
            self.entity_manager,  # <-- NOVO
        )

        # Mini ships vs TODOS os inimigos usando a mesma grid
        vector_gain: int
        vector_destroyed: int
        vector_score_events: list[tuple[float, float, int]]
        vector_gain, vector_destroyed, vector_score_events = (
            self.collisions.mini_ship_bullets_vs_enemies(
                self.entity_manager.mini_ship_bullets,
                enemy_grid,
                self.entity_manager.enemies,  # Para adicionar fragments
                self.entity_manager,  # <-- ADICIONAR
            )
        )
        gain += vector_gain
        destroyed += vector_destroyed
        score_events.extend(vector_score_events)

        # Lasers do jogador vs inimigos
        laser_gain: int
        laser_destroyed: int
        laser_score_events: list[tuple[float, float, int]]
        laser_gain, laser_destroyed, laser_score_events = (
            self.collisions.player_lasers_vs_enemies(
                self.entity_manager.player_lasers,
                self.entity_manager.enemies,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )
        )
        gain += laser_gain
        destroyed += laser_destroyed
        score_events.extend(laser_score_events)

        # Explosões de minas vs inimigos normais
        mine_gain: int
        mine_destroyed: int
        mine_score_events: list[tuple[float, float, int]]
        ship_hit: bool
        mine_gain, mine_destroyed, mine_score_events, ship_hit = (
            self.collisions.check_mine_explosions(
                self.entity_manager.enemies,
                self.entity_manager.mine_explosions,
                self.ship,
                self.entity_manager,
            )
        )
        gain += mine_gain
        destroyed += mine_destroyed
        score_events.extend(mine_score_events)

        # NOVO: Processar formações uma única vez (consolidando 3 loops em 1)
        for formation in self.entity_manager.formations:
            formation_enemies = formation.get_enemies()

            # Minas vs formação
            f_gain, f_destroyed, f_score_events, f_ship_hit = (
                self.collisions.check_mine_explosions(
                    formation_enemies,
                    self.entity_manager.mine_explosions,
                    self.ship,
                    self.entity_manager,
                )
            )
            gain += f_gain
            destroyed += f_destroyed
            score_events.extend(f_score_events)
            if f_ship_hit:
                ship_hit = True

            # Explosive effects vs formação
            if self.entity_manager.explosive_effects:
                f_exp_gain, f_exp_destroyed, f_exp_score_events = (
                    self.collisions.explosive_effects_vs_enemies(
                        self.entity_manager.explosive_effects,
                        formation_enemies,
                        self.entity_manager,
                    )
                )
                gain += f_exp_gain
                destroyed += f_exp_destroyed
                score_events.extend(f_exp_score_events)

            # Air strike vs formação
            if self.entity_manager.air_strike_bombs:
                f_air_gain, f_air_destroyed, f_air_score_events = (
                    self.collisions.air_strike_bombs_vs_enemies(
                        self.entity_manager.air_strike_bombs,
                        formation_enemies,
                        self.entity_manager,
                    )
                )
                gain += f_air_gain
                destroyed += f_air_destroyed
                score_events.extend(f_air_score_events)

        if ship_hit:
            self._handle_ship_hit()
            # Meta-progression: Track damage taken
            self.level_damage_taken += 1

        # Colisão contínua dos efeitos explosivos vs inimigos (para pegar fragmentos)
        if self.entity_manager.explosive_effects:
            exp_gain, exp_destroyed, exp_score_events = (
                self.collisions.explosive_effects_vs_enemies(
                    self.entity_manager.explosive_effects,
                    self.entity_manager.enemies,
                    self.entity_manager,
                )
            )
            gain += exp_gain
            destroyed += exp_destroyed
            score_events.extend(exp_score_events)

        # Colisão das bombas de bombardeio aéreo vs inimigos
        if self.entity_manager.air_strike_bombs:
            air_gain, air_destroyed, air_score_events = (
                self.collisions.air_strike_bombs_vs_enemies(
                    self.entity_manager.air_strike_bombs,
                    self.entity_manager.enemies,
                    self.entity_manager,
                )
            )
            gain += air_gain
            destroyed += air_destroyed
            score_events.extend(air_score_events)

        for x, y, pts in score_events:
            # Usar multiplicador em cache
            multiplier = self._base_score_multiplier
            if self.score_multiplier_active:
                multiplier *= self.score_multiplier_value
            adjusted_pts = int(pts * multiplier)
            self.entity_manager.floating_scores.append(
                FloatingScore(x, y, adjusted_pts)
            )
        # Usar multiplicador em cache
        multiplier = self._base_score_multiplier
        if self.score_multiplier_active:
            multiplier *= self.score_multiplier_value
        score_to_add = int(gain * multiplier)
        self.score += score_to_add
        self.total_enemies_destroyed += destroyed
        self.enemies_destroyed_in_level += destroyed
        # Regra: spawnar estrela a cada N inimigos destruídos
        if destroyed > 0:
            self.star_spawner.add_kills(destroyed, self.entity_manager.stars)

        if self.entity_manager.boss:
            score_gain = 0
            if self._boss_type_cache == "spike":
                from ..entities.spike_boss import SpikeBoss

                score_gain = self.collisions.bullets_vs_spike_boss(
                    self.entity_manager.bullets,
                    cast(SpikeBoss, self.entity_manager.boss),
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                # Mini ships vs SpikeBoss
                mini_ship_boss_gain = self.collisions.mini_ship_bullets_vs_spike_boss(
                    self.entity_manager.mini_ship_bullets,
                    cast(SpikeBoss, self.entity_manager.boss),
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                score_gain += mini_ship_boss_gain
            elif self._boss_type_cache == "normal":
                score_gain = self.collisions.bullets_vs_boss(
                    self.entity_manager.bullets,
                    self.entity_manager.boss,  # type: ignore
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                # Mini ships vs Boss normal
                mini_ship_boss_gain = self.collisions.mini_ship_bullets_vs_boss(
                    self.entity_manager.mini_ship_bullets,
                    self.entity_manager.boss,  # type: ignore
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                score_gain += mini_ship_boss_gain

            # Lasers do jogador vs Boss
            laser_boss_gain = self.collisions.player_lasers_vs_boss(
                self.entity_manager.player_lasers,
                self.entity_manager.boss,  # type: ignore
                self.entity_manager.floating_scores,
                self.entity_manager,
            )
            score_gain += laser_boss_gain

            if self.score_multiplier_active:
                score_gain = int(score_gain * self.score_multiplier_value)
            self.score += score_gain

        # Mini ships vs Spikes
        if self.entity_manager.spikes:
            spike_gain = self.collisions.mini_ship_bullets_vs_spikes(
                self.entity_manager.mini_ship_bullets,
                self.entity_manager.spike_spatial_grid,  # OPT #1: Usa grid pronta
                self.entity_manager,
            )
            if self.score_multiplier_active:
                spike_gain = int(spike_gain * self.score_multiplier_value)
            self.score += spike_gain

        # Colisão da nave com TODOS os inimigos usando grid única
        if self.collisions.ship_vs_enemies(self.ship, enemy_grid, self.entity_manager):
            self._handle_ship_hit()

        # CONSOLIDAÇÃO: Todas as colisões com boss em um bloco único
        boss = self.entity_manager.boss
        if boss:
            score_gain = 0

            # Projéteis vs Boss
            if self._boss_type_cache == "spike":
                from ..entities.spike_boss import SpikeBoss

                spike_boss = cast(SpikeBoss, boss)
                score_gain = self.collisions.bullets_vs_spike_boss(
                    self.entity_manager.bullets,
                    spike_boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                score_gain += self.collisions.mini_ship_bullets_vs_spike_boss(
                    self.entity_manager.mini_ship_bullets,
                    spike_boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
            elif self._boss_type_cache == "normal":
                score_gain = self.collisions.bullets_vs_boss(
                    self.entity_manager.bullets,
                    boss,  # type: ignore
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                score_gain += self.collisions.mini_ship_bullets_vs_boss(
                    self.entity_manager.mini_ship_bullets,
                    boss,  # type: ignore
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )

            # Lasers vs Boss (comum para ambos tipos)
            score_gain += self.collisions.player_lasers_vs_boss(
                self.entity_manager.player_lasers,
                boss,  # type: ignore
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

            if self.score_multiplier_active:
                score_gain = int(score_gain * self.score_multiplier_value)
            self.score += score_gain

            # Nave vs Boss
            if self._boss_type_cache == "spike":
                from ..entities.spike_boss import SpikeBoss

                if self.collisions.ship_vs_spike_boss(
                    self.ship, cast(SpikeBoss, boss), self.entity_manager
                ):
                    self._handle_ship_hit()
            elif self._boss_type_cache == "normal":
                if self.collisions.ship_vs_boss(
                    self.ship, boss, self.entity_manager  # type: ignore
                ):
                    self._handle_ship_hit()

        if self.collisions.alien_bullets_vs_ship(
            self.ship, self.entity_manager.alien_bullets
        ):
            self._handle_ship_hit()
        if self.collisions.eye_laser_vs_ship(self.ship, self.entity_manager.eye_lasers):
            self._handle_ship_hit()

        from ..entities.boss_laser import BossLaser

        boss_lasers = [
            laser
            for laser in self.entity_manager.boss_lasers
            if isinstance(laser, BossLaser)
        ]
        if self.collisions.laser_vs_ship(self.ship, boss_lasers):
            self._handle_ship_hit()

        # Verificar colisão com laser do SpikeBoss (filtrando SpikeBossLaser)
        spike_boss_lasers: list[SpikeBossLaser] = [
            laser
            for laser in self.entity_manager.boss_lasers
            if isinstance(laser, SpikeBossLaser)
        ]
        if spike_boss_lasers and self.collisions.spike_boss_laser_vs_ship(
            self.ship, spike_boss_lasers
        ):
            self._handle_ship_hit()

        # Colisões com espinhos (SpikeBoss)
        if self.collisions.ship_vs_spikes(
            self.ship, self.entity_manager.spikes, self.entity_manager
        ):
            self._handle_ship_hit()

        # Colisões com quadrados do boss (indestrutíveis)
        if self.collisions.ship_vs_boss_squares(
            self.ship, self.entity_manager.boss_squares
        ):
            self._handle_ship_hit()

        # Balas vs quadrados do boss (gera explosão mas não destrói os quadrados)
        self.collisions.bullets_vs_boss_squares(
            self.entity_manager.bullets,
            self.entity_manager.boss_squares,
            self.entity_manager,
        )

        # Balas vs espinhos
        spike_score = self.collisions.bullets_vs_spikes(
            self.entity_manager.bullets,
            self.entity_manager.spike_spatial_grid,  # OPT #1: Usa grid pronta
            self.entity_manager,
        )
        if self.score_multiplier_active:
            spike_score = int(spike_score * self.score_multiplier_value)
        self.score += spike_score

        collected_powerups = self.collisions.ship_vs_powerups(
            self.ship, self.entity_manager.powerups
        )

        # Verificar colisão com estrelas
        collected_stars = self.collisions.ship_vs_stars(
            self.ship, self.entity_manager.stars
        )
        if collected_stars > 0:
            self.player_profile.add_stars(collected_stars)
            sound_manager.play_powerup()  # Som temporário, pode criar um específico depois

        # Verificar regras especiais da dificuldade (usando cache)
        if self._no_powerups_mode:
            collected_powerups = []  # Ignorar todos os power-ups

        if collected_powerups:
            for kind in collected_powerups:
                sound_manager.play_powerup()
                if kind == "life":
                    self.lives += 1
                    self.ship.lives = self.lives
                elif kind == "shield":
                    self.ship.invuln = max(
                        self.ship.invuln, self._powerup_values["shield_duration"]
                    )
                elif kind == "double_shot":
                    self.ship.double_shot_timer = max(
                        self.ship.double_shot_timer,
                        self._powerup_values["double_shot_duration"],
                    )
                elif kind == "speed":
                    self.ship.speed_boost_timer = max(
                        self.ship.speed_boost_timer,
                        self._powerup_values["speed_boost_duration"],
                    )
                elif kind == "score":
                    # Ativar multiplicador de score por 15 segundos
                    self.score_multiplier_timer = 15.0
                    self.score_multiplier_active = True
                elif kind == "piercing_shot":
                    self.ship.piercing_shot_timer = max(
                        self.ship.piercing_shot_timer,
                        self._powerup_values["piercing_shot_duration"],
                    )
                elif kind == "mini_ships":
                    self.ship.mini_ships_timer = max(
                        self.ship.mini_ships_timer,
                        self._powerup_values["mini_ships_duration"],
                    )
                    self.entity_manager.mini_ships.clear()
                    self.entity_manager.mini_ships.append(MiniShip(self.ship, "left"))
                    self.entity_manager.mini_ships.append(MiniShip(self.ship, "right"))
                elif kind == "rainbow":
                    self.lives += 1
                    self.ship.lives = self.lives
                    self.ship.invuln = max(
                        self.ship.invuln,
                        self._powerup_values["rainbow_duration_invuln"],
                    )
                    self.ship.double_shot_timer = max(
                        self.ship.double_shot_timer,
                        self._powerup_values["rainbow_duration"],
                    )
                    self.ship.speed_boost_timer = max(
                        self.ship.speed_boost_timer,
                        self._powerup_values["rainbow_duration"],
                    )
                    self.ship.mini_ships_timer = max(
                        self.ship.mini_ships_timer,
                        self._powerup_values["mini_ships_duration"],
                    )
                    self.entity_manager.mini_ships.clear()
                    self.entity_manager.mini_ships.append(MiniShip(self.ship, "left"))
                    self.entity_manager.mini_ships.append(MiniShip(self.ship, "right"))
                    rainbow_score = self._powerup_values["rainbow_score"]
                    if self.score_multiplier_active:
                        rainbow_score = int(rainbow_score * self.score_multiplier_value)
                    self.score += rainbow_score

                # Meta-progression: Track powerup collection
                self.level_powerups_collected += 1

    def _handle_ship_hit(self):
        # God mode: ignorar dano
        if self.god_mode:
            return

        if self.ship.invuln > 0:
            return

        # Verificar se o escudo pode absorver o dano
        if self.ship.has_shield:
            self.ship.shield_hp -= 1
            if self.ship.shield_hp <= 0:
                self.ship.shield_timer = 0.0
            # Som de escudo absorvendo dano
            sound_manager.play_powerup()  # Usar som existente temporariamente
            return

        self.lives -= 1
        self.ship.lives = self.lives
        if self.lives > 0:
            self.ship.invuln = Config.INVULN_TIME * 1000

            # Meta-progression: Record death (but not game over)
            self.player_profile.record_death(self.current_level_index + 1, "collision")
        else:
            # Switch to GameOverScene
            from .game_over import GameOverScene

            self.app.states.switch(GameOverScene(self.app, self.score, self))

            # Meta-progression: Record death and end session
            self.player_profile.record_death(self.current_level_index + 1, "game_over")
            self.player_profile.end_session()

    def _check_level_progression(self):
        if self.enemies_destroyed_in_level >= self.level_config.enemies_to_clear:
            self.enemy_spawner.stop()

            # Iniciar limpeza de inimigos restantes se ainda houver inimigos
            if self.entity_manager.enemies and not self.enemy_cleanup_active:
                self.enemy_cleanup_active = True
                self.enemy_cleanup_timer = 0.0
                print(
                    f"🧹 SISTEMA DE LIMPEZA ATIVADO! {len(self.entity_manager.enemies)} inimigos restantes terão 15 segundos para serem derrotados..."
                )
            elif not self.entity_manager.enemies or (
                self.enemy_cleanup_active
                and self.enemy_cleanup_timer >= self.enemy_cleanup_duration
            ):
                # Todos os inimigos foram limpos ou timer expirou
                self.enemy_cleanup_active = False
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

        # Reset music transition flags
        self.music_fade_started = False
        self.boss_music_started = False

        self.boss_fight_active = True
        self.screen_shake_timer = Config.BOSS_ENTRY_SHAKE_DURATION

        # Parar sons de warning e outros efeitos
        sound_manager.stop_warning()
        sound_manager.stop_all_sfx()

        if self.level_config.boss_type:
            boss = self.level_config.boss_type(Config.SCREEN_WIDTH / 2 - 50, 50)
            # Aplicar multiplicador de health da dificuldade
            boss.health = int(boss.health * self.enemy_health_multiplier)
            boss.max_health = boss.health  # Atualizar max_health também
            self.entity_manager.boss = boss

            self._cache_boss_type()  # Cache do tipo de boss

            from ..entities.spike_boss import SpikeBoss

            if isinstance(self.entity_manager.boss, SpikeBoss):
                sound_manager.music_state_manager.transition_to(MusicState.SPIKE_BOSS)
            else:
                sound_manager.music_state_manager.transition_to(MusicState.BOSS)

            self.boss_music_started = True

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
            # Nova forma
            self.entity_manager.spawn_explosion(
                ex, ey, size=Config.BOSS_EXPLOSION_SMALL_SIZE
            )

        # Explosão central maior
        # Nova forma
        self.entity_manager.spawn_explosion(
            boss_center[0], boss_center[1], size=Config.BOSS_EXPLOSION_LARGE_SIZE
        )

        # Limpar todos os spikes quando o boss for derrotado
        for spike in self.entity_manager.spikes[:]:
            # Criar pequenas explosões onde os spikes estavam
            if spike.state != "respawning":
                self.entity_manager.spawn_explosion(
                    spike.center_x, spike.center_y, size=15
                )
        self.entity_manager.spikes.clear()

        self.entity_manager.boss = None
        self.boss_fight_active = False
        self._boss_type_cache = None  # Limpar cache
        boss_score = Config.BOSS_DEFEAT_SCORE
        if self.score_multiplier_active:
            boss_score = int(boss_score * self.score_multiplier_value)
        self.score += boss_score

        # Reset music transition flags for next boss
        self.music_fade_started = False
        self.boss_music_started = False

        # Voltar para música normal
        sound_manager.music_state_manager.transition_to(MusicState.GAME)
        self._advance_to_next_level()

    def _advance_to_next_level(self):
        # Meta-progression: Record level clear
        if self.level_start_time is not None:
            clear_time = time.time() - self.level_start_time
            self.player_profile.record_clear(
                level_number=self.current_level_index + 1,
                time_taken=clear_time,
                score=self.score,
                enemies_killed=self.total_enemies_destroyed,
                damage_taken=self.level_damage_taken,
                powerups_collected=self.level_powerups_collected,
            )

        if not self.level_transition_active:
            self.level_transition_active = True
            self.level_transition_timer = 0.0

    def _start_next_level(self):
        self.level_transition_active = False
        self.current_level_index += 1

        # Gerar próximo nível (sistema híbrido: fixo ou procedural)
        self.level_config = self._get_adjusted_level_config(
            self.current_level_index + 1
        )

        # Recalcular multiplicador para o novo nível
        self._base_score_multiplier = (
            self.level_config.score_multiplier
            * self.difficulty_settings["rewards_multiplier"]
        )

        self.enemy_spawner.set_level(self.current_level_index + 1)
        self.enemies_destroyed_in_level = 0

        # Reset level tracking
        self.level_start_time = None  # Reset to None instead of 0.0
        self.level_damage_taken = 0
        self.level_powerups_collected = 0

        # Reset enemy cleanup system
        self.enemy_cleanup_active = False
        self.enemy_cleanup_timer = 0.0
        self.enemy_blink_timer = 0.0
        self.enemy_visible = True

        # Meta-progression: Record attempt for new level
        self.player_profile.record_attempt(self.current_level_index + 1)

        # Usar método que preserva balas do jogador durante transições
        self.entity_manager.clear_for_level_transition()

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                from .paused import PausedScene

                self.app.states.push(PausedScene(self.app, previous_scene=self))

            # Sistema de debug: mostrar/ocultar FPS com F3
            elif event.key == pygame.K_F3:
                self.show_fps = not self.show_fps
                print(f"Debug FPS: {'ATIVADO' if self.show_fps else 'DESATIVADO'}")

            # Sistema de cheat code
            self._process_cheat_input(event)

            # Ativar upgrades (quando jogando)
            if self.state == "playing" and not self.ship.is_entering:
                # Use keybindings from player profile
                try:
                    keybinds = self.player_profile.upgrade_keybindings
                    for i, keycode in enumerate(keybinds[:UPGRADE_SLOT_COUNT]):
                        if event.key == keycode:
                            self._activate_upgrade_slot(i)
                            break
                except Exception:
                    # Fallback to defaults (1-9)
                    default_keys = [
                        pygame.K_1,
                        pygame.K_2,
                        pygame.K_3,
                        pygame.K_4,
                        pygame.K_5,
                        pygame.K_6,
                        pygame.K_7,
                        pygame.K_8,
                        pygame.K_9,
                    ]
                    for i, keycode in enumerate(default_keys[:UPGRADE_SLOT_COUNT]):
                        if event.key == keycode:
                            self._activate_upgrade_slot(i)
                            break

    def render(self, surface: pygame.Surface):
        # Usa o dt armazenado pela última chamada de update
        dt = self.last_dt
        speed_multiplier = 1.0
        if self.state == "preparing":
            progress = (
                Config.PREPARATION_TIME - self.preparation_time_left
            ) / Config.PREPARATION_TIME
            progress = min(1.0, max(0.0, progress))  # Garantir que esteja entre 0 e 1
            # Interpola para começar rápido e terminar na velocidade normal
            speed_multiplier = 1.0 + (Config.WARP_SPEED_MULTIPLIER - 1.0) * (
                1.0 - progress**2
            )
        else:
            boss_active = bool(
                self.boss_fight_active
                and self.entity_manager.boss
                and not self.entity_manager.boss.dead
            )
            if boss_active:
                speed_multiplier = Config.BOSS_WARP_SPEED_MULTIPLIER

        self.r.background(self.game_surface, dt=dt, speed_multiplier=speed_multiplier)

        self.entity_manager.draw(
            self.game_surface,
            self.ship.rect.centerx,
            self.ship.rect.centery,
            self.enemy_visible,
        )
        self.ship.draw(self.game_surface)

        # Atualizar FPS
        self.r.update_fps(dt)

        self.r.hud(
            self.game_surface,
            self.score,
            self.lives,
            self.total_enemies_destroyed,
            self.ship,
            self.level_config.level_number,
            self.difficulty_preset,
            score_multiplier_active=self.score_multiplier_active,
            score_multiplier_timer=self.score_multiplier_timer,
            mini_ships_active=self.ship.mini_ships_timer > 0,
            mini_ships_timer=self.ship.mini_ships_timer,
            explosive_shots_active=self.ship.explosive_shots_active,
            explosive_shots_remaining=self.ship.explosive_shots_remaining,
        )

        # HUD de aprimoramentos (na game_surface)
        self._render_upgrades_hud(self.game_surface)

        # Mostrar FPS se ativado (F3)
        if self.show_fps:
            fps_stats = self.r.get_fps_stats()
            fps_text = f"FPS: {fps_stats['fps']:.1f} | Avg: {fps_stats['avg_frame_time']:.1f}ms | Max: {fps_stats['max_frame_time']:.1f}ms"
            fps_surface = self.r.font_small.render(fps_text, True, colors.YELLOW)
            self.game_surface.blit(fps_surface, (10, Config.SCREEN_HEIGHT - 30))

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

        if self.state == "preparing":
            self.r.preparation(surface, self.preparation_time_left)

    # ===================== Upgrades (helpers) =====================
    def _init_upgrades_from_profile(self):
        # Cria instâncias por slot baseado no profile
        self.upgrade_slots = []
        if not hasattr(self, "player_profile"):
            self.upgrade_slots = [None] * UPGRADE_SLOT_COUNT
            return
        for t in self.player_profile.upgrade_loadout[:UPGRADE_SLOT_COUNT]:
            if t is None:
                self.upgrade_slots.append(None)
            else:
                try:
                    self.upgrade_slots.append(create_upgrade(t))
                except Exception:
                    self.upgrade_slots.append(None)

    def _build_upgrade_ctx(self):
        # Objeto simples com atributos esperados pelo upgrade
        ctx = type(
            "UpgradeCtx",
            (),
            {
                "ship": self.ship,
                "entity_manager": self.entity_manager,
                "difficulty_settings": self.difficulty_settings,
                "sound_manager": sound_manager,
                "scene": self,
            },
        )()
        return ctx

    def _update_upgrades(self, dt: float):
        if not self.upgrade_slots:
            return
        from typing import Any as _Any

        ctx: _Any = self._build_upgrade_ctx()
        for upg in self.upgrade_slots:
            if upg is not None:
                upg.update(dt, ctx)

    def _activate_upgrade_slot(self, idx: int):
        if idx < 0 or idx >= len(self.upgrade_slots):
            return
        upg = self.upgrade_slots[idx]
        if upg is None:
            return
        from typing import Any as _Any

        ctx: _Any = self._build_upgrade_ctx()
        try:
            upg.activate(ctx)
        except Exception:
            pass

    def _render_upgrades_hud(self, surface: pygame.Surface):
        import pygame as _pg
        from ..core import colors as _colors

        if not self.upgrade_slots:
            return

        # Filtrar apenas slots com upgrades ativos (não None)
        active_slots = [
            (i, upg) for i, upg in enumerate(self.upgrade_slots) if upg is not None
        ]

        if not active_slots:
            return

        # Criar surface semi-transparente para os slots
        font = get_font(20)
        font_small = get_font(12)
        pad = 8
        slot_w, slot_h = 50, 50  # Menores: de 64x64 para 50x50
        x = Config.SCREEN_WIDTH - pad - slot_w
        y = 44  # Abaixo do texto "Vidas" (que está em y=10)

        for display_index, (i, upg) in enumerate(active_slots):
            # Criar surface temporária com alpha
            slot_surface = _pg.Surface((slot_w, slot_h), _pg.SRCALPHA)

            # Fundo semi-transparente (30, 30, 30) com alpha 180
            _pg.draw.rect(
                slot_surface, (30, 30, 30, 180), (0, 0, slot_w, slot_h), border_radius=8
            )
            _pg.draw.rect(
                slot_surface,
                (*_colors.WHITE, 200),
                (0, 0, slot_w, slot_h),
                2,
                border_radius=8,
            )

            # Nome da tecla vinculada no canto superior esquerdo
            try:
                keycode = self.player_profile.upgrade_keybindings[i]
                key_label = _pg.key.name(keycode).upper()
            except Exception:
                key_label = str(i + 1)
            label = font_small.render(key_label, True, _colors.WHITE)
            slot_surface.blit(label, (4, 2))

            ui = upg.get_ui_state()  # type: ignore

            # Ícone no centro (usando função centralizada de mapeamento)
            from ..core.upgrades import get_upgrade_icon
            name_str = str(ui.get("name", ""))
            icon_id = str(ui.get("icon_id", "")) if ui.get("icon_id") else None
            icon = get_upgrade_icon(name_str, icon_id)
            icon_txt = font.render(icon, True, _colors.CYAN)
            icon_rect = icon_txt.get_rect(center=(slot_w // 2, slot_h // 2))
            slot_surface.blit(icon_txt, icon_rect)

            # Cooldown overlay (barra circular ou overlay semi-transparente)
            cd_left = (
                float(ui["cooldown_left"])
                if ui.get("cooldown_left") is not None
                else 0.0
            )
            cd_base = float(ui["cooldown"]) if ui.get("cooldown") is not None else 1.0
            if cd_left > 0.0:
                pct = max(0.0, min(1.0, cd_left / cd_base))
                bar_h = 4
                _pg.draw.rect(
                    slot_surface,
                    (120, 120, 120, 150),
                    (2, slot_h - bar_h - 2, slot_w - 4, bar_h),
                    border_radius=2,
                )
                bar_w = int((slot_w - 4) * pct)
                _pg.draw.rect(
                    slot_surface,
                    (80, 180, 255, 200),
                    (2, slot_h - bar_h - 2, bar_w, bar_h),
                    border_radius=2,
                )

            # Cargas (canto inferior direito)
            charges = ui.get("charges_left")
            if charges is not None:
                c_txt = font_small.render(f"{charges}", True, _colors.WHITE)
                c_rect = c_txt.get_rect()
                c_rect.bottomright = (slot_w - 3, slot_h - 3)
                slot_surface.blit(c_txt, c_rect)

            # Renderizar slot na posição correta (usar display_index para posicionamento)
            slot_x = x - display_index * (slot_w + 6)
            surface.blit(slot_surface, (slot_x, y))

            # Borda verde quando ativo (renderizada diretamente na surface principal)
            if ui["active"]:
                rect = _pg.Rect(slot_x, y, slot_w, slot_h)
                _pg.draw.rect(surface, _colors.GREEN, rect, 3, border_radius=8)
