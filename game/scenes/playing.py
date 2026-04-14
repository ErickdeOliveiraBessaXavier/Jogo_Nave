from __future__ import annotations

import logging
import math
import random
import time
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional, cast

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.config import SlimeBossState
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.levels import LevelConfig, LevelManager, get_level_config
from ..core.meta_progression import PlayerProfile
from ..core.paths import get_profile_path
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..core.state import Scene
from ..core.upgrades import ActiveUpgrade, HealUpgrade, create_upgrade, get_upgrade_icon
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from ..core.world_config import (
    WorldConfig,
    format_stage_name,
    get_world_for_level,
    is_side_scroll_mode,
)
from ..entities.floating_score import FloatingScore
from ..entities.mini_ship import MiniShip
from ..entities.ship import Ship
from ..entities.spike_boss_laser import SpikeBossLaser
from ..systems.collisions import Collisions
from ..systems.entity_manager import EntityManager
from ..systems.spawner import EnemySpawner, PowerUpSpawner, StarSpawner

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..app import GameApp
    from ..core.spatial_grid import SpatialGrid


class TransitionPhase(Enum):
    PLAYING = auto()
    POST_VICTORY_DELAY = auto()
    LEVEL_TRANSITION_WAIT = auto()
    CUTSCENE_EXIT = auto()
    WORLD_PANEL = auto()
    LEVEL_ENTRY = auto()


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
        self.r = app.renderer  # Usar renderer compartilhado

        # Carregar configurações do jogador
        self.player_profile = PlayerProfile(get_profile_path())

        # Meta-progression system (salvar profil antes)
        self.player_profile.start_session()

        # Detectar modo de jogo CEDO (antes de criar nave)
        self.current_level_index: int = 0
        self.current_world = get_world_for_level(self.current_level_index + 1)
        self.is_side_scroll = is_side_scroll_mode(self.current_world.theme)

        # Criar nave com posição correta baseado no modo
        if self.is_side_scroll:
            # Side-scroll: Nave vem da esquerda, centrada verticalmente
            ship_x = -50  # Fora da tela à esquerda
            ship_y = (Config.SCREEN_HEIGHT - 35) / 2  # Centrada verticalmente
        else:
            # Top-down: Nave vem de baixo, centrada horizontalmente
            ship_x = Config.SCREEN_WIDTH / 2 - 20
            ship_y = Config.SCREEN_HEIGHT + 100  # Abaixo da tela

        self.ship = Ship(
            ship_x,
            ship_y,
            mouse_control=self.app.preferences.mouse_control,
            auto_fire=self.app.preferences.auto_fire,
        )
        self.ship.is_entering = True
        self.ship.is_side_scroll = self.is_side_scroll

        # Rotacionar nave em side-scroll (90 graus para a direita)
        if self.is_side_scroll:
            self.ship.set_rotation(90.0)

        self.first_entry = True

        # Aplicar configurações de dificuldade após criar a nave
        # Declarações antecipadas — valores reais definidos em _apply_difficulty_settings()
        self.shoot_cd: float = 0.0
        self.cheat_buffer: str = ""
        self.god_mode: bool = False
        self.state: str = "preparing"
        self.level_start_time: Optional[float] = None
        self.level_damage_taken: int = 0
        self.level_powerups_collected: int = 0
        self.level_attempt_recorded: bool = False
        self.transition_phase: TransitionPhase = TransitionPhase.LEVEL_ENTRY
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
        self.level_transition_pending = False
        self.level_transition_pending_timer = 0.0
        self.level_transition_pending_delay = Config.LEVEL_TRANSITION_PENDING_DELAY
        self.level_transition_animation_timeout = (
            Config.LEVEL_TRANSITION_ANIMATION_TIMEOUT
        )
        self.pending_world_transition: Optional[WorldConfig] = None
        self.awaiting_world_transition_panel = False

        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = Config.SCREEN_SHAKE_NORMAL
        self.warning_timer = 0.0
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)

        self.level_config = self._get_adjusted_level_config(
            self.current_level_index + 1
        )
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))

        # Criar EntityManager ANTES de usar (necessário para spawner)
        self.entity_manager = EntityManager(is_side_scroll=self.is_side_scroll)

        # Aplicar tema do mundo
        self._apply_world_theme()

        # Cache de configuração de nível (otimização)
        self._cache_level_thresholds()

        # Inicializar spawner com delay inicial apenas para fase 1
        is_initial_level = self.current_level_index == 0
        self.enemy_spawner = EnemySpawner(
            self.level_manager,
            self.entity_manager.meteor_pool,
            is_initial_level,
            self.difficulty_preset,
            self.enemy_health_multiplier,
        )
        self.powerup_spawner = PowerUpSpawner(self.difficulty_preset)
        self.collisions = Collisions(is_side_scroll=self.is_side_scroll)

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
            "cooldown_haste_reduction": Config.COOLDOWN_HASTE_REDUCTION,
            "time_stop_duration": Config.TIME_STOP_DURATION,
        }

        # Timers de novos power-ups
        self.time_stop_timer: float = 0.0
        self.freeze_active = False

        # Sistema de limpeza de inimigos restantes
        self.enemy_cleanup_active = False  # Se o timer de limpeza está ativo
        self.enemy_cleanup_timer = 0.0  # Timer para limpeza dos inimigos restantes
        self.enemy_cleanup_duration = 20.0  # 15 segundos para limpeza
        self.enemy_blink_timer = 0.0  # Timer para efeito de piscar
        self.enemy_blink_interval = 0.2  # Intervalo de piscar (200ms)
        self.enemy_visible = True  # Controle de visibilidade para piscar

        # Debug FPS display (F3 toggle)
        self.show_fps = False

        # Cutscene de transição de mundo (saída da nave antes do painel)
        self.world_transition_cutscene_active = False
        self.world_transition_cutscene_timer = 0.0
        self.world_transition_cutscene_duration = (
            Config.WORLD_TRANSITION_CUTSCENE_DURATION
        )
        self.world_transition_cutscene_charge_duration = (
            Config.WORLD_TRANSITION_CUTSCENE_CHARGE_DURATION
        )
        self.world_transition_cutscene_launch_speed = (
            Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED
        )
        self.world_transition_cutscene_origin = (0.0, 0.0)
        self.world_transition_cutscene_recoil_offset = 0.0
        self.world_transition_cutscene_launch_distance = 0.0
        self.world_transition_cutscene_target_world: Optional[WorldConfig] = None
        self.world_transition_cutscene_debug_mode = False
        self.world_transition_thruster_particles: list[dict[str, Any]] = []

        # Sistema de multiplicador de score
        self.score_multiplier_timer = 0.0
        self.score_multiplier_active = False
        self.score_multiplier_value = 1.5

        # Batching de floating scores para otimização
        self.floating_score_batch_threshold = 60.0  # pixels

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
        self.level_attempt_recorded = False

    def _cache_level_thresholds(self):
        """Pre-calcula valores usados em verificações frequentes."""
        self.enemies_to_clear = self.level_config.enemies_to_clear
        self.has_boss = bool(self.level_config.boss_type)

    def _get_adjusted_level_config(self, level_number: int) -> LevelConfig:
        """Obtém configuração de nível ajustada pelo meta-progression."""
        base_config = get_level_config(level_number, self.difficulty_preset)
        return self.player_profile.get_adjusted_config(base_config)

    def _apply_world_theme(self) -> None:
        """Aplica o tema visual do mundo atual."""
        self.r.set_world_theme(self.current_world.theme)
        logger.info(
            f"🌍 Mundo aplicado: {self.current_world.name} ({self.current_world.theme.value})"
        )

    def _set_transition_phase(self, phase: TransitionPhase) -> None:
        """Atualiza a fase de transicao e sincroniza os flags legados."""
        self.transition_phase = phase
        self.level_transition_pending = phase == TransitionPhase.POST_VICTORY_DELAY
        self.level_transition_active = phase == TransitionPhase.LEVEL_TRANSITION_WAIT
        self.world_transition_cutscene_active = phase == TransitionPhase.CUTSCENE_EXIT
        self.awaiting_world_transition_panel = phase == TransitionPhase.WORLD_PANEL

        if phase != TransitionPhase.POST_VICTORY_DELAY:
            self.level_transition_pending_timer = 0.0
        if phase != TransitionPhase.LEVEL_TRANSITION_WAIT:
            self.level_transition_timer = 0.0

    def _can_handle_gameplay_actions(self) -> bool:
        """Retorna True quando o jogador pode agir normalmente."""
        return self.transition_phase == TransitionPhase.PLAYING

    def _begin_level_preparation(self) -> None:
        """Coloca a cena em modo de preparação para o próximo nível."""
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
        self.level_transition_pending = False
        self.level_transition_active = False
        self.awaiting_world_transition_panel = False
        self.state = "preparing"
        self.preparation_time_left = Config.PREPARATION_TIME
        self.level_start_time = None
        self.level_damage_taken = 0
        self.level_powerups_collected = 0
        self.level_attempt_recorded = False
        self._reset_ship_for_level_entry()

    def _begin_playing_state(self) -> None:
        """Ativa o gameplay e registra a tentativa do nível uma única vez."""
        self._set_transition_phase(TransitionPhase.PLAYING)
        self.state = "playing"
        self.ship.is_entering = False
        if self.level_start_time is None:
            self.level_start_time = time.time()
        if not self.level_attempt_recorded:
            self.player_profile.record_attempt(self.current_level_index + 1)
            self.level_attempt_recorded = True

    def _apply_pending_world_transition(self) -> None:
        """Aplica o mundo pendente após o painel de transição finalizar."""
        if self.pending_world_transition is None:
            self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
            return

        new_world = self.pending_world_transition
        self.pending_world_transition = None
        self.awaiting_world_transition_panel = False

        self.current_world = new_world
        self._apply_world_theme()

        new_is_side_scroll = is_side_scroll_mode(self.current_world.theme)
        if new_is_side_scroll != self.is_side_scroll:
            self.is_side_scroll = new_is_side_scroll
            self.entity_manager.is_side_scroll = new_is_side_scroll
            self.ship.is_side_scroll = new_is_side_scroll
            self.collisions.is_side_scroll = new_is_side_scroll
            logger.info(
                f"📋 Modo alterado para: {'Side-Scroll (Horizontal)' if self.is_side_scroll else 'Top-Down (Vertical)'}"
            )

        logger.info(f"✨ Bem-vindo ao {new_world.name}!")

        self._begin_level_preparation()

    def _reset_ship_for_level_entry(self) -> None:
        """Reposiciona a nave para a animação de entrada do próximo nível."""
        self.ship.is_entering = True
        self.ship.is_side_scroll = self.is_side_scroll

        if self.is_side_scroll:
            self.ship.x = -50
            self.ship.y = (Config.SCREEN_HEIGHT - 35) / 2
            self.ship.set_rotation(90.0)
        else:
            self.ship.x = Config.SCREEN_WIDTH / 2 - 20
            self.ship.y = Config.SCREEN_HEIGHT + 100
            self.ship.set_rotation(0.0)

    def _find_next_world_for_debug_preview(self):
        """Retorna o próximo mundo com tema diferente para preview visual da transição."""
        current_level = self.current_level_index + 1
        base_world = get_world_for_level(current_level)

        # Janela ampla para cobrir setores procedurais sem custo relevante.
        for level in range(current_level + 1, current_level + 120):
            candidate_world = get_world_for_level(level)
            if candidate_world.theme != base_world.theme:
                return candidate_world, level

        return None, None

    def _spawn_world_transition_thruster_particles(self, intensity: int) -> None:
        """Gera partículas extras para o impulso da cutscene."""
        if self.ship.ship_image is not None:
            sprite_w, sprite_h = self.ship.ship_image.get_size()
        else:
            sprite_w, sprite_h = self.ship.w, self.ship.h

        for _ in range(intensity):
            if self.is_side_scroll:
                particle = {
                    "offset_x": random.uniform(-14, 4),
                    "offset_y": sprite_h / 2 + random.uniform(-8, 8),
                    "vx": -random.uniform(220, 460),
                    "vy": random.uniform(-120, 120),
                    "lifetime": random.uniform(0.14, 0.34),
                    "size": random.uniform(2.0, 4.8),
                    "color": (255, random.randint(120, 230), 0),
                }
            else:
                particle = {
                    "offset_x": sprite_w / 2 + random.uniform(-9, 9),
                    "offset_y": sprite_h + random.uniform(-4, 10),
                    "vx": random.uniform(-90, 90),
                    "vy": random.uniform(220, 460),
                    "lifetime": random.uniform(0.14, 0.34),
                    "size": random.uniform(2.0, 4.8),
                    "color": (255, random.randint(120, 230), 0),
                }
            self.world_transition_thruster_particles.append(particle)

    def _update_world_transition_thruster_particles(self, dt: float) -> None:
        """Atualiza partículas extras da cutscene."""
        self.world_transition_thruster_particles = [
            {
                "offset_x": p["offset_x"] + p["vx"] * dt,
                "offset_y": p["offset_y"] + p["vy"] * dt,
                "vx": p["vx"],
                "vy": p["vy"],
                "lifetime": p["lifetime"] - dt,
                "size": max(0.0, p["size"] - dt * 6.0),
                "color": p["color"],
            }
            for p in self.world_transition_thruster_particles
            if p["lifetime"] - dt > 0.0 and p["size"] - dt * 6.0 > 0.0
        ]

    def _start_world_transition_cutscene(
        self, target_world: WorldConfig, debug_mode: bool = False
    ) -> None:
        """Inicia a cutscene de saída da nave antes do painel de transição."""
        self._set_transition_phase(TransitionPhase.CUTSCENE_EXIT)
        self.world_transition_cutscene_timer = 0.0
        self.world_transition_cutscene_launch_speed = (
            Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED
        )
        self.world_transition_cutscene_origin = (float(self.ship.x), float(self.ship.y))
        self.world_transition_cutscene_recoil_offset = 0.0
        self.world_transition_cutscene_launch_distance = 0.0
        self.world_transition_cutscene_target_world = target_world
        self.world_transition_cutscene_debug_mode = debug_mode
        self.world_transition_thruster_particles.clear()

        # A cutscene usa apenas movimento da nave; não há tremor de tela.
        self.ship.is_entering = True
        self.ship.is_side_scroll = self.is_side_scroll

        logger.info(
            f"[CUTSCENE] Iniciando saída da nave para {target_world.name} (debug={debug_mode})"
        )

    def _finish_world_transition_cutscene(self) -> None:
        """Finaliza a cutscene e abre o painel de transição."""
        if not self.world_transition_cutscene_active:
            return

        target_world = self.world_transition_cutscene_target_world
        debug_mode = self.world_transition_cutscene_debug_mode

        self.world_transition_cutscene_active = False
        self.world_transition_cutscene_timer = 0.0
        self.world_transition_cutscene_target_world = None
        self.world_transition_cutscene_debug_mode = False
        self.world_transition_thruster_particles.clear()
        self.world_transition_cutscene_recoil_offset = 0.0
        self.world_transition_cutscene_launch_distance = 0.0

        if target_world is None:
            return

        if debug_mode:
            # Preview de debug não altera progressão real.
            self._begin_level_preparation()
        else:
            self._set_transition_phase(TransitionPhase.WORLD_PANEL)

        logger.info(
            f"[CUTSCENE] Saída concluída, abrindo painel de transição ({target_world.name})"
        )

        from .world_transition import WorldTransitionScene

        self.app.states.push(WorldTransitionScene(self.app, target_world))

        # Em preview de debug, não alterar progressão; apenas reproduzir o pacote visual.
        if debug_mode:
            logger.info("[CUTSCENE] Preview visual completo executado via F8")

    def _update_world_transition_cutscene(self, dt: float) -> None:
        """Atualiza a cinemática de saída da nave (charge -> launch)."""
        if not self.world_transition_cutscene_active:
            return

        self.world_transition_cutscene_timer += dt
        t = self.world_transition_cutscene_timer
        charge_end = self.world_transition_cutscene_charge_duration
        charge_progress = min(1.0, max(0.0, t / charge_end))

        # Sequência visual da nave:
        # 1) Tremor curto
        # 2) Pequeno recoil para trás
        # 3) Estabiliza com thrusters intensos
        recoil_sign = -1.0 if self.is_side_scroll else 1.0
        if charge_progress < 0.28:
            tremble_strength = 1.8 * (1.0 - charge_progress * 0.8)
            ship_x = self.world_transition_cutscene_origin[0]
            ship_y = self.world_transition_cutscene_origin[1]
            ship_x += math.sin(t * 55.0) * tremble_strength
            ship_y += math.cos(t * 47.0) * tremble_strength * 0.75
            self.world_transition_cutscene_recoil_offset = 0.0
            thruster_intensity = 6
        elif charge_progress < 0.68:
            recoil_progress = (charge_progress - 0.28) / (0.68 - 0.28)
            self.world_transition_cutscene_recoil_offset = 12.0 * recoil_progress
            ship_x = self.world_transition_cutscene_origin[0]
            ship_y = self.world_transition_cutscene_origin[1]
            ship_x += recoil_sign * self.world_transition_cutscene_recoil_offset
            tremble_strength = 1.2 * (1.0 - recoil_progress)
            ship_x += math.sin(t * 42.0) * tremble_strength * 0.55
            ship_y += math.cos(t * 39.0) * tremble_strength * 0.55
            thruster_intensity = 10
        else:
            hold_progress = (charge_progress - 0.68) / (1.0 - 0.68)
            self.world_transition_cutscene_recoil_offset = 12.0
            ship_x = (
                self.world_transition_cutscene_origin[0]
                + recoil_sign * self.world_transition_cutscene_recoil_offset
            )
            ship_y = self.world_transition_cutscene_origin[1]
            thruster_intensity = 14 + int(6 * hold_progress)

        self.ship.x = ship_x
        self.ship.y = ship_y

        self._spawn_world_transition_thruster_particles(intensity=thruster_intensity)

        if t >= charge_end:
            # Fase de lançamento: aceleração rápida para fora da tela.
            self.world_transition_cutscene_launch_speed += (
                Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_ACCELERATION * dt
            )
            launch_speed = self.world_transition_cutscene_launch_speed
            self.world_transition_cutscene_launch_distance += launch_speed * dt
            if self.is_side_scroll:
                self.ship.x = (
                    self.world_transition_cutscene_origin[0]
                    + recoil_sign * self.world_transition_cutscene_recoil_offset
                    + self.world_transition_cutscene_launch_distance
                )
            else:
                self.ship.y = (
                    self.world_transition_cutscene_origin[1]
                    - self.world_transition_cutscene_launch_distance
                )
            self._spawn_world_transition_thruster_particles(intensity=14)

        # Intensificar emissão base durante a cutscene.
        ship_dt_multiplier = 3.4 if t >= charge_end else 2.2
        self.ship.update(
            dt * ship_dt_multiplier,
            self.entity_manager,
            is_side_scroll=self.is_side_scroll,
        )
        self._update_world_transition_thruster_particles(dt)

        if (
            self.world_transition_cutscene_timer
            >= self.world_transition_cutscene_duration
        ):
            self._finish_world_transition_cutscene()

    def _trigger_world_transition_debug_preview(self) -> None:
        """Abre a transição de mundo manualmente, sem mexer na progressão."""
        if self.world_transition_cutscene_active:
            logger.info("[DEBUG] Cutscene já está ativa")
            return

        world, level = self._find_next_world_for_debug_preview()
        if world is None:
            logger.warning("[DEBUG] Nenhum próximo mundo encontrado para preview")
            return

        logger.info(
            f"[DEBUG] Preview de transição: {self.current_world.name} -> {world.name} (nível alvo {level})"
        )
        self._start_world_transition_cutscene(world, debug_mode=True)

    def enter(self):
        pygame.mouse.set_visible(False)
        if self.first_entry:
            sound_manager.music_state_manager.transition_to(MusicState.GAME)
            self.first_entry = False

        if self.transition_phase == TransitionPhase.WORLD_PANEL:
            self._apply_pending_world_transition()

    def exit(self):
        pygame.mouse.set_visible(True)

    def update(self, dt: float):
        self.last_dt = dt

        if self.transition_phase == TransitionPhase.CUTSCENE_EXIT:
            self._update_world_transition_cutscene(dt)
            return

        if self.transition_phase == TransitionPhase.POST_VICTORY_DELAY:
            self.level_transition_pending_timer += dt
            if (
                self.level_transition_pending_timer
                >= self.level_transition_pending_delay
            ):
                self._set_transition_phase(TransitionPhase.LEVEL_TRANSITION_WAIT)

        if self.state == "preparing":
            self.preparation_time_left -= dt

            # Mover a nave para a posição inicial de forma suave
            if self.is_side_scroll:
                # Side-scroll: Nave entra pela esquerda, move para centro horizontal
                target_x = 100  # Posição final (da esquerda)
                initial_x = -50  # Posição inicial (fora da tela)
                target_y = (Config.SCREEN_HEIGHT - 35) / 2  # Mantém altura

                if self.preparation_time_left > 0:
                    elapsed_time = Config.PREPARATION_TIME - self.preparation_time_left
                    progress = min(1.0, elapsed_time / Config.PREPARATION_TIME)
                    # Interpolação linear para suavizar o movimento
                    self.ship.x = initial_x + (target_x - initial_x) * progress
                    self.ship.y = target_y  # Manter altura constante
                else:
                    self.ship.x = target_x
                    self.ship.y = target_y
                    self._begin_playing_state()
            else:
                # Top-down: Nave entra de baixo, move para topo (comportamento original)
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
                    self._begin_playing_state()

        # Timers
        self.time_stop_timer = max(0.0, self.time_stop_timer - dt)
        self.freeze_active = self.time_stop_timer > 0.0

        # Cooldown de tiro NÃO é afetado pelo cooldown_haste (só aprimoramentos)
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

        boss = cast(Any, self.entity_manager.boss)
        if boss and (
            getattr(boss, "state", None) == "entering"
            or getattr(boss, "current_state", None) == SlimeBossState.ENTERING
        ):
            self.screen_shake_timer = 0.1  # Keep shaking while boss is entering
        else:
            self.screen_shake_timer = max(0.0, self.screen_shake_timer - dt)

        if self.transition_phase == TransitionPhase.LEVEL_TRANSITION_WAIT:
            self.level_transition_timer += dt
            if self.level_transition_timer >= self.level_transition_delay:
                timed_out = self.level_transition_timer >= (
                    self.level_transition_delay
                    + self.level_transition_animation_timeout
                )
                if self._all_animations_finished() or timed_out:
                    self._start_next_level()

        self.ship.update(dt, self.entity_manager, is_side_scroll=self.is_side_scroll)
        if self.ship.mini_ships_timer == 0.0 and self.entity_manager.mini_ships:
            self.entity_manager.mini_ships.clear()

        # Verificar se o boss está em pausa do frenzy
        boss_pausing = False
        if self._boss_type_cache == "spike" and self.entity_manager.boss:
            from ..entities.spike_boss import SpikeBoss

            boss_pausing = cast(SpikeBoss, self.entity_manager.boss).is_pausing_game()

        # Bloquear movimento e tiro durante entrada da nave
        if self._can_handle_gameplay_actions() and not self.ship.is_entering:
            held = self.app.input.poll_held()
            self.ship.move(held, dt, is_side_scroll=self.is_side_scroll)

            # Tiro contínuo com tecla segurada ou automático
            if (
                ("hold_shoot" in held or self.ship.should_auto_fire())
                and self.shoot_cd == 0.0
                and not boss_pausing
                and self.ship.speed_modifier_timer <= 0.0  # Bloquear tiro se congelado
            ):
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
            and not self.level_transition_pending
        ):
            if not self.freeze_active:
                self.enemy_spawner.update(
                    dt,
                    self.entity_manager,
                    self.ship.rect.centerx,
                    self.ship.rect.centery,
                    is_side_scroll=self.is_side_scroll,
                )

            # Não spawnar power-ups no Nightmare (regra especial, usando cache)
            if not self._no_powerups_mode:
                self.powerup_spawner.update(dt, self.entity_manager.powerups)

            # Spawner de estrelas
            self.star_spawner.update(dt, self.entity_manager.stars)

        self.entity_manager.update(
            dt,
            self.ship.rect.centerx,
            self.ship.rect.centery,
            freeze_enemies=self.freeze_active,
            screen_width=Config.SCREEN_WIDTH,
            screen_height=Config.SCREEN_HEIGHT,
        )

        # Durante troca de fase, evitar novas colisões para não prolongar a transição.
        if self.transition_phase in (
            TransitionPhase.PLAYING,
            TransitionPhase.LEVEL_ENTRY,
        ):
            self._handle_collisions()

        self.entity_manager.cleanup()

        # Lógica de progressão de fase
        if self.boss_fight_active:
            if self.entity_manager.boss and self.entity_manager.boss.dead:
                self._end_boss_fight()
        elif self.pre_boss_transition:
            if not self.entity_manager.enemies and self.warning_stage == 0:
                # Iniciar sequência de warning em 3 estágios
                self.warning_stage = 1  # Estágio 1: Pre-delay
                self.warning_stage_timer = 0.0
                self.warning_sound_played = False

            self._update_warning_system(dt)

        elif self.transition_phase == TransitionPhase.PLAYING:
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
                    total_enemies = len(self.entity_manager.enemies)
                    total_formations = sum(
                        len(f.enemies) for f in self.entity_manager.formations
                    )

                    logger.info(
                        f"TEMPO ESGOTADO! Removendo {total_enemies} inimigos normais "
                        f"e {total_formations} inimigos em formação automaticamente..."
                    )

                    # Limpar inimigos normais
                    for enemy in self.entity_manager.enemies[:]:
                        enemy.dead = True
                    self.entity_manager.enemies.clear()

                    # Limpar formações também
                    for formation in self.entity_manager.formations[:]:
                        for enemy in formation.enemies:
                            enemy.dead = True
                        formation.dead = True
                    self.entity_manager.formations.clear()

            self._check_level_progression()

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
            from ..entities.giant_meteor_boss import GiantMeteorBoss
            from ..entities.slime_boss import SlimeBoss
            from ..entities.spike_boss import SpikeBoss
            from ..entities.stone_golem_boss import StoneGolemBoss

            if isinstance(self.entity_manager.boss, SpikeBoss):
                self._boss_type_cache = "spike"
            elif isinstance(self.entity_manager.boss, SlimeBoss):
                self._boss_type_cache = "slime"
            elif isinstance(self.entity_manager.boss, GiantMeteorBoss):
                self._boss_type_cache = "giant_meteor"
            elif isinstance(self.entity_manager.boss, StoneGolemBoss):
                self._boss_type_cache = "stone_golem"
            else:
                self._boss_type_cache = "normal"
        else:
            self._boss_type_cache = None

    def _all_animations_finished(self) -> bool:
        """Check if all animations (explosions) have finished for level transition."""
        pool_stats = self.entity_manager.explosion_pool.get_stats()
        return (
            not self.entity_manager.explosive_effects
            and pool_stats.get("active", 0) == 0
        )

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
                    logger.info("GOD MODE ATIVADO - Invulnerabilidade ligada!")
                    # Reduzir cooldowns ativos para 1 segundo quando god_mode é ativado
                    self._apply_god_mode_cooldowns()
                    if hasattr(sound_manager, "play_powerup"):
                        sound_manager.play_powerup()  # type: ignore
                else:
                    logger.info("GOD MODE DESATIVADO - Invulnerabilidade desligada!")

    def _batch_floating_scores(
        self,
        score_events: list[tuple[float, float, int]],
        proximity_threshold: float = 60.0,
    ) -> list[tuple[float, float, int]]:
        """
        Agrupa score events próximos em um único evento somado.

        Args:
            score_events: Lista de (x, y, pontos)
            proximity_threshold: Distância máxima para considerar "próximo" (pixels)

        Returns:
            Lista compactada de (x, y, pontos_somados)
        """
        if not score_events:
            return []

        # Criar grupos de eventos próximos
        batched: list[tuple[float, float, int]] = []
        used = [False] * len(score_events)

        for i, (x1, y1, pts1) in enumerate(score_events):
            if used[i]:
                continue

            # Iniciar novo batch com este evento
            batch_x = x1
            batch_y = y1
            batch_pts = pts1
            batch_count = 1
            used[i] = True

            # Procurar eventos próximos
            for j, (x2, y2, pts2) in enumerate(score_events):
                if used[j] or i == j:
                    continue

                # Calcular distância euclidiana
                dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

                if dist <= proximity_threshold:
                    # Adicionar ao batch (média ponderada da posição)
                    batch_x = (batch_x * batch_count + x2) / (batch_count + 1)
                    batch_y = (batch_y * batch_count + y2) / (batch_count + 1)
                    batch_pts += pts2
                    batch_count += 1
                    used[j] = True

            batched.append((batch_x, batch_y, batch_pts))

        return batched

    def _check_projectile_vs_enemies(
        self,
        enemy_grid: SpatialGrid[Any],
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        """
        Verifica colisões de projéteis contra inimigos normais.
        Retorna: (ganho_score, destruídos, score_events, ship_hit)
        """
        gain: int = 0
        destroyed: int = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hit: bool = False

        # Balas vs inimigos
        gain, destroyed, score_events = self.collisions.bullets_vs_enemies(
            self.entity_manager.bullets,
            self.entity_manager.mine_explosions,
            self.ship,
            enemy_grid,
            self.entity_manager.enemies,
            self.entity_manager,
        )

        # Mini ships vs inimigos
        vector_gain, vector_destroyed, vector_score_events = (
            self.collisions.mini_ship_bullets_vs_enemies(
                self.entity_manager.mini_ship_bullets,
                enemy_grid,
                self.entity_manager.enemies,
                self.entity_manager,
            )
        )
        gain += vector_gain
        destroyed += vector_destroyed
        score_events.extend(vector_score_events)

        # Lasers do jogador vs inimigos
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
        mine_gain, mine_destroyed, mine_score_events, mine_ship_hit = (
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
        ship_hit = ship_hit or mine_ship_hit

        return gain, destroyed, score_events, ship_hit

    def _check_formation_collisions(
        self, gain: int, destroyed: int, score_events: list[tuple[float, float, int]]
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        """
        Verifica colisões de formações e efeitos contra inimigos.
        Retorna: (ganho_score_acumulado, destruídos_acumulados, score_events, ship_hit)
        """
        ship_hit = False
        # Processar formações
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
            ship_hit = ship_hit or f_ship_hit

            # Minas de torres vs formação
            if self.entity_manager.cannon_mines:
                f_cannon_gain, f_cannon_destroyed, f_cannon_score_events = (
                    self.collisions.cannon_mines_vs_enemies(
                        self.entity_manager.cannon_mines,
                        formation_enemies,
                        self.entity_manager,
                    )
                )
                gain += f_cannon_gain
                destroyed += f_cannon_destroyed
                score_events.extend(f_cannon_score_events)

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

        # Colisão de minas das torres vs inimigos
        if self.entity_manager.cannon_mines:
            mine_gain, mine_destroyed, mine_score_events = (
                self.collisions.cannon_mines_vs_enemies(
                    self.entity_manager.cannon_mines,
                    self.entity_manager.enemies,
                    self.entity_manager,
                )
            )
            gain += mine_gain
            destroyed += mine_destroyed
            score_events.extend(mine_score_events)

        return gain, destroyed, score_events, ship_hit

    def _check_boss_collisions(self, gain: int) -> int:
        """
        Verifica todas as colisões envolvendo o boss.
        Retorna: ganho_score_do_boss
        """
        score_gain = 0
        boss = self.entity_manager.boss

        if boss and self._boss_type_cache:
            # Projéteis vs Boss (usando cache para evitar isinstance)
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
            elif self._boss_type_cache == "slime":
                from ..entities.slime_boss import SlimeBoss

                slime_boss = cast(SlimeBoss, boss)
                # SlimeBoss usa bullets e mini_ship_bullets
                score_gain = self.collisions.bullets_vs_slime_boss(
                    self.entity_manager.bullets,
                    slime_boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
                score_gain += self.collisions.mini_ship_bullets_vs_slime_boss(
                    self.entity_manager.mini_ship_bullets,
                    slime_boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
            elif self._boss_type_cache == "giant_meteor":
                from ..entities.giant_meteor_boss import GiantMeteorBoss

                gm_boss = cast(GiantMeteorBoss, boss)
                score_gain = self.collisions.bullets_vs_giant_meteor_boss(
                    self.entity_manager.bullets,
                    gm_boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )
            else:  # self._boss_type_cache == "normal"
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

            # Lasers vs Boss (aplicável a todos os bosses)
            score_gain += self.collisions.player_lasers_vs_boss(
                self.entity_manager.player_lasers,
                boss,  # type: ignore
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

            # Efeitos explosivos vs boss
            if self.entity_manager.explosive_effects:
                score_gain += self.collisions.explosive_effects_vs_boss(
                    self.entity_manager.explosive_effects,
                    boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )

            # Bombas de bombardeio aéreo vs boss
            if self.entity_manager.air_strike_bombs:
                score_gain += self.collisions.air_strike_bombs_vs_boss(
                    self.entity_manager.air_strike_bombs,
                    boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )

            # Minas das torres vs boss
            if self.entity_manager.cannon_mines:
                score_gain += self.collisions.cannon_mines_vs_boss(
                    self.entity_manager.cannon_mines,
                    boss,
                    self.entity_manager.floating_scores,
                    self.entity_manager,
                )

            # Dano das gotas do SlimeBoss
            if self._boss_type_cache == "slime":
                from ..entities.slime_boss import SlimeBoss

                slime_boss = cast(SlimeBoss, boss)
                drip_damage = slime_boss.check_drip_damage(
                    self.ship.rect, self.entity_manager
                )
                if drip_damage > 0:
                    self._handle_ship_hit()
                    self.level_damage_taken += drip_damage

            if self.score_multiplier_active:
                score_gain = int(score_gain * self.score_multiplier_value)

        return gain + score_gain

    def _check_ship_damage(self) -> None:
        """Verifica todas as colisões que causam dano à nave."""
        if self.collisions.alien_bullets_vs_ship(
            self.ship, self.entity_manager.alien_bullets
        ):
            self._handle_ship_hit()
        if self.collisions.eye_laser_vs_ship(self.ship, self.entity_manager.eye_lasers):
            self._handle_ship_hit()

        # Colisão com EnergyOrb (ElementalRobot)
        orb_hit = self.collisions.energy_orbs_vs_ship(
            self.ship, self.entity_manager.energy_orbs
        )
        if orb_hit:
            # Aplicar dano normal
            self._handle_ship_hit()

            # Se a nave ficou invulnerável (recebeu o dano), aplicar debuffs elementais
            if self.ship.invuln > 0:
                if orb_hit.theme == "inferno":
                    self.ship.fire_rate_modifier_timer = 5  # 5s de cadência lenta
                elif orb_hit.theme == "toxina":
                    self.ship.invert_controls_timer = 4  # 4s de controles invertidos
                elif orb_hit.theme == "nevasca":
                    self.ship.speed_modifier_timer = 3  # 3s de velocidade lenta

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

        # Colisão com o feixe sweep do StoneGolemBoss (laser azul visual)
        if self._boss_type_cache == "stone_golem" and self.entity_manager.boss:
            from ..entities.stone_golem_boss import StoneGolemBoss

            golem = cast(StoneGolemBoss, self.entity_manager.boss)
            beam = golem.get_sweep_beam()
            if beam and self.ship.invuln <= 0:
                px, py, ex, ey = beam
                # Distância do centro da nave à linha do feixe
                sx = float(self.ship.rect.centerx)
                sy = float(self.ship.rect.centery)
                dx, dy = ex - px, ey - py
                len_sq = dx * dx + dy * dy
                if len_sq > 0:
                    t = max(0.0, min(1.0, ((sx - px) * dx + (sy - py) * dy) / len_sq))
                    closest_x = px + t * dx
                    closest_y = py + t * dy
                    dist = math.hypot(sx - closest_x, sy - closest_y)
                    hit_radius = golem.SCALE * 2 + self.ship.rect.width * 0.4
                    if dist < hit_radius:
                        self._handle_ship_hit()

        # NOTA: Boulders, RockShards e Detritos agora são tratados no ship_vs_enemies
        # através da SpatialGrid e do Protocol Enemy.

    def _apply_score_multiplier(self, pts: int) -> int:
        """Aplica multiplicador de score se ativo."""
        multiplier = self._base_score_multiplier
        if self.score_multiplier_active:
            multiplier *= self.score_multiplier_value
        return int(pts * multiplier)

    def _handle_collisions(self):
        """
        Orquestrador de colisões. Delega para métodos especializados em ordem:
        1. Projéteis vs inimigos normais
        2. Formações e efeitos de área vs inimigos
        3. Score e floating scores dos inimigos
        4. Mini ships vs spikes
        5. Nave vs inimigos (físico)
        6. Boss (projéteis, efeitos, físico, slime drips)
        7. Balas vs objetos indestrutíveis (boss squares, slime drips, spikes)
        8. Dano à nave (lasers, spikes, quadrados)
        9. Power-ups e estrelas
        """
        enemy_grid = self.entity_manager.enemy_spatial_grid

        # --- Passo 1 & 2: Inimigos normais e formações ---
        gain, destroyed, score_events, ship_hit_proj = (
            self._check_projectile_vs_enemies(enemy_grid)
        )
        gain, destroyed, score_events, ship_hit_form = self._check_formation_collisions(
            gain, destroyed, score_events
        )

        if ship_hit_proj or ship_hit_form:
            self._handle_ship_hit()
            self.level_damage_taken += 1

        # --- Passo 3: Aplicar score dos inimigos ---
        batched_events = self._batch_floating_scores(
            score_events, proximity_threshold=self.floating_score_batch_threshold
        )
        for x, y, pts in batched_events:
            self.entity_manager.floating_scores.append(
                FloatingScore(x, y, self._apply_score_multiplier(pts))
            )

        self.score += self._apply_score_multiplier(gain)
        self.total_enemies_destroyed += destroyed
        self.enemies_destroyed_in_level += destroyed

        if destroyed > 0:
            self.star_spawner.add_kills(destroyed, self.entity_manager.stars)

        # --- Passo 4: Mini ships vs Spikes ---
        if self.entity_manager.spikes:
            spike_gain = self.collisions.mini_ship_bullets_vs_spikes(
                self.entity_manager.mini_ship_bullets,
                self.entity_manager.spike_spatial_grid,
                self.entity_manager,
            )
            if self.score_multiplier_active:
                spike_gain = int(spike_gain * self.score_multiplier_value)
            self.score += spike_gain

        # --- Passo 5: Nave vs inimigos (físico) ---
        if self.collisions.ship_vs_enemies(self.ship, enemy_grid, self.entity_manager):
            self._handle_ship_hit()

        # --- Passo 6: Boss (projéteis, área, físico, slime drips) ---
        boss_score_gain = self._check_boss_collisions(0)
        self.score += boss_score_gain

        boss = self.entity_manager.boss
        if boss and self._boss_type_cache:
            if self._boss_type_cache == "spike":
                from ..entities.spike_boss import SpikeBoss

                if self.collisions.ship_vs_spike_boss(
                    self.ship, cast(SpikeBoss, boss), self.entity_manager
                ):
                    self._handle_ship_hit()
            elif self._boss_type_cache in ("slime", "normal"):
                if self.collisions.ship_vs_boss(
                    self.ship,
                    boss,  # type: ignore
                    self.entity_manager,
                ):
                    self._handle_ship_hit()

        # --- Passo 7: Balas vs objetos indestrutíveis ---
        self.collisions.bullets_vs_boss_squares(
            self.entity_manager.bullets,
            self.entity_manager.boss_squares,
            self.entity_manager,
        )

        if self._boss_type_cache == "slime":
            self.collisions.bullets_vs_slime_drips(
                self.entity_manager.bullets,
                self.entity_manager.slime_drips,
                self.entity_manager,
            )

        spike_score = self.collisions.bullets_vs_spikes(
            self.entity_manager.bullets,
            self.entity_manager.spike_spatial_grid,
            self.entity_manager,
        )
        if self.score_multiplier_active:
            spike_score = int(spike_score * self.score_multiplier_value)
        self.score += spike_score

        # --- Passo 8: Dano à nave (lasers, spikes, quadrados) ---
        self._check_ship_damage()

        # --- Passo 9: Power-ups e estrelas ---
        self._process_powerups_and_stars()

    def _process_powerups_and_stars(self) -> None:
        """Processa coleta de power-ups e estrelas."""
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
                elif kind == "cooldown_haste":
                    # Reduz instantaneamente o cooldown de todos os upgrades ativos
                    reduction = self._powerup_values["cooldown_haste_reduction"]
                    self._apply_cooldown_reduction(reduction)
                elif kind == "time_stop":
                    self.time_stop_timer = max(
                        self.time_stop_timer,
                        self._powerup_values["time_stop_duration"],
                    )
                    self.freeze_active = True
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

        # Som de colisão
        sound_manager.play_boss_damage()

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
        # Usar cache ao invés de acessar level_config toda vez
        if self.enemies_destroyed_in_level >= self.enemies_to_clear:
            self.enemy_spawner.stop()

            # Lazy evaluation: verificar presença de inimigos uma única vez
            has_enemies = bool(self.entity_manager.enemies)

            # Iniciar limpeza de inimigos restantes se ainda houver inimigos
            if has_enemies and not self.enemy_cleanup_active:
                self.enemy_cleanup_active = True
                self.enemy_cleanup_timer = 0.0
                logging.info(
                    f"🧹 SISTEMA DE LIMPEZA ATIVADO! {len(self.entity_manager.enemies)} inimigos restantes terão 15 segundos para serem derrotados..."
                )
            elif not has_enemies or (
                self.enemy_cleanup_active
                and self.enemy_cleanup_timer >= self.enemy_cleanup_duration
            ):
                # Todos os inimigos foram limpos ou timer expirou
                self.enemy_cleanup_active = False
                if self.has_boss:  # Cache ao invés de self.level_config.boss_type
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
        # Garante que inimigos/mini-bosses voltem a renderizar após o piscar
        # do sistema de limpeza pré-boss.
        self.enemy_visible = True
        self.enemy_blink_timer = 0.0

        # Parar sons de warning e outros efeitos
        sound_manager.stop_warning()
        sound_manager.stop_all_sfx()

        if self.level_config.boss_type:
            from ..entities.stone_golem_boss import StoneGolemBoss

            # Sistema flexível para inicializar bosses com suporte a dificuldade
            if self.level_config.boss_type == StoneGolemBoss:
                # StoneGolemBoss já aplica o multiplicador internamente no __init__
                boss = StoneGolemBoss(
                    Config.SCREEN_WIDTH / 2 - 50,
                    50,
                    difficulty_multiplier=self.enemy_health_multiplier,
                )
            else:
                # Bosses legados
                boss = self.level_config.boss_type(Config.SCREEN_WIDTH / 2 - 50, 50)
                # Aplicar multiplicador de health da dificuldade
                boss.health = int(boss.health * self.enemy_health_multiplier)
                boss.max_health = boss.health  # Atualizar max_health também

            self.entity_manager.boss = boss

            self._cache_boss_type()  # Cache do tipo de boss

            _boss_music_map = {
                "spike": MusicState.SPIKE_BOSS,
                "slime": MusicState.SLIME_BOSS,
                "giant_meteor": MusicState.GIANT_METEOR_BOSS,
            }
            # Garantir que boss_type não é None para o Pylance
            boss_type = self._boss_type_cache or "normal"
            sound_manager.music_state_manager.transition_to(
                _boss_music_map.get(boss_type, MusicState.BOSS)
            )

            self.boss_music_started = True

    def _end_boss_fight(self):
        from ..entities.giant_meteor_boss import GiantMeteorBoss

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

        # Para GiantMeteorBoss: destruir todos os meteoros ativos com explosões
        if isinstance(self.entity_manager.boss, GiantMeteorBoss):
            for meteor in self.entity_manager.meteor_pool.active[:]:
                # Calcular centro do meteoro
                center_x = meteor.x + meteor.w / 2
                center_y = meteor.y + meteor.h / 2
                # Criar explosão no meteoro
                self.entity_manager.spawn_explosion(
                    center_x, center_y, size=max(12, int(meteor.w // 2))
                )
            # Limpar todos os meteoros do pool
            self.entity_manager.meteor_pool.clear_active()

        # Limpar inimigos restantes com explosões quando o boss for derrotado
        for enemy in self.entity_manager.enemies[:]:
            # Calcular centro do inimigo (alguns podem não ter w/h)
            center_x = getattr(enemy, "x", 0.0)
            center_y = getattr(enemy, "y", 0.0)
            w = getattr(enemy, "w", 0)
            h = getattr(enemy, "h", 0)
            self.entity_manager.spawn_explosion(
                float(center_x + w / 2), float(center_y + h / 2), size=15
            )
        self.entity_manager.enemies.clear()

        # Limpar formações restantes com explosões quando o boss for derrotado
        for formation in self.entity_manager.formations[:]:
            for enemy in formation.enemies:
                # Calcular centro do inimigo (alguns podem não ter w/h)
                center_x = getattr(enemy, "x", 0.0)
                center_y = getattr(enemy, "y", 0.0)
                w = getattr(enemy, "w", 0)
                h = getattr(enemy, "h", 0)
                self.entity_manager.spawn_explosion(
                    float(center_x + w / 2), float(center_y + h / 2), size=15
                )
            formation.dead = True
        self.entity_manager.formations.clear()

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
        if self.transition_phase == TransitionPhase.PLAYING:
            self._set_transition_phase(TransitionPhase.POST_VICTORY_DELAY)

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

    def _start_next_level(self):
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
        self.current_level_index += 1

        # Gerar próximo nível (sistema híbrido: fixo ou procedural)
        self.level_config = self._get_adjusted_level_config(
            self.current_level_index + 1
        )

        # Dispara cutscene apenas quando muda o tema visual.
        new_world = get_world_for_level(self.current_level_index + 1)
        theme_changed = new_world.theme != self.current_world.theme
        if theme_changed:
            # Tema e modo serão aplicados só após o painel de transição.
            self.pending_world_transition = new_world
        else:
            # Mantém o mundo em sincronia sem acionar transição temática.
            self.current_world = new_world

        # Atualizar cache de nível (otimização)
        self._cache_level_thresholds()

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
        self.level_attempt_recorded = False

        if theme_changed:
            self._start_world_transition_cutscene(new_world)
        else:
            # Sem troca de mundo, iniciar o próximo nível imediatamente.
            self._begin_playing_state()

        # Reset enemy cleanup system
        self.enemy_cleanup_active = False
        self.enemy_cleanup_timer = 0.0
        self.enemy_blink_timer = 0.0
        self.enemy_visible = True

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
                logging.info(
                    f"Debug FPS: {'ATIVADO' if self.show_fps else 'DESATIVADO'}"
                )

            # Debug visual: prévia da próxima transição de mundo
            elif event.key == pygame.K_F8:
                self._trigger_world_transition_debug_preview()

            # Sistema de cheat code
            self._process_cheat_input(event)

            # Ativar upgrades (quando jogando)
            if self._can_handle_gameplay_actions() and not self.ship.is_entering:
                # Use keybindings from player profile
                try:
                    keybinds = self.player_profile.upgrade_keybindings
                    for i, keycode in enumerate(keybinds[:UPGRADE_SLOT_COUNT]):
                        if event.key == keycode:
                            self._activate_upgrade_slot(i)
                            break
                except (AttributeError, TypeError):
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

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Disparar com clique esquerdo se não estiver em auto-fire
            if (
                not self.ship.auto_fire
                and self.shoot_cd == 0.0
                and not self.ship.is_entering
                and self._can_handle_gameplay_actions()
            ):
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
                # Reset shoot cooldown
                self.shoot_cd = 1.0 / (
                    self.ship.attack_speed_multiplier * Config.FIRE_RATE
                )

    def render(self, surface: pygame.Surface):
        # Usa o dt armazenado pela última chamada de update
        dt = self.last_dt
        speed_multiplier = 1.0
        boss_active = False  # Initialize to False
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

        self.r.background(
            self.game_surface,
            dt=dt,
            speed_multiplier=speed_multiplier,
            draw_celestials=not boss_active,
        )

        fps_stats = self.r.get_fps_stats()
        self.entity_manager.draw(
            self.game_surface,
            self.ship.rect.centerx,
            self.ship.rect.centery,
            self.enemy_visible,
            fps=fps_stats.get("fps", 60.0),
        )

        # Partículas extras da cutscene (atrás da nave)
        for p in self.world_transition_thruster_particles:
            px = self.ship.x + p["offset_x"]
            py = self.ship.y + p["offset_y"]
            pygame.draw.circle(
                self.game_surface,
                p["color"],
                (int(px), int(py)),
                max(1, int(p["size"])),
            )

        self.ship.draw(self.game_surface)

        # Atualizar FPS
        self.r.update_fps(dt)

        # MODIFICADO: Mostrar estágio formatado (ex: "2-5" ao invés de "Fase: 15")
        stage_name = format_stage_name(self.level_config.level_number)

        self.r.hud(
            self.game_surface,
            self.score,
            self.lives,
            self.total_enemies_destroyed,
            self.ship,
            stage_name,  # MODIFICADO (era level_number)
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
                    upgrade = create_upgrade(t)
                    if isinstance(upgrade, HealUpgrade):
                        upgrade.usage_count = self.app.heal_usage_count
                    self.upgrade_slots.append(upgrade)
                except (ValueError, AttributeError):
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
                "god_mode": self.god_mode,  # Adicionar god_mode ao contexto
            },
        )()
        return ctx

    def _update_upgrades(self, dt: float):
        if not self.upgrade_slots:
            return

        ctx: Any = self._build_upgrade_ctx()
        for upg in self.upgrade_slots:
            if upg is not None:
                upg.update(dt, ctx)

    def _apply_cooldown_reduction(self, reduction: float):
        """Reduz instantaneamente o cooldown de todos os upgrades ativos."""
        if not self.upgrade_slots:
            return
        for upg in self.upgrade_slots:
            if upg is not None and upg.cooldown_left > 0:
                upg.cooldown_left = max(0.0, upg.cooldown_left - reduction)

    def _apply_god_mode_cooldowns(self):
        """Reduz todos os cooldowns ativos para 1 segundo quando god_mode é ativado."""
        if not self.upgrade_slots:
            return
        for upg in self.upgrade_slots:
            if upg is not None and upg.cooldown_left > 0:
                # Reduzir cooldown para 1 segundo (ou manter se já for menor)
                upg.cooldown_left = min(upg.cooldown_left, 1.0)

    def _activate_upgrade_slot(self, idx: int):
        if idx < 0 or idx >= len(self.upgrade_slots):
            return
        upg = self.upgrade_slots[idx]
        if upg is None:
            return

        ctx: Any = self._build_upgrade_ctx()
        try:
            upg.activate(ctx)
            if isinstance(upg, HealUpgrade):
                self.app.heal_usage_count = upg.usage_count
        except (AttributeError, TypeError):
            pass

    def _render_upgrades_hud(self, surface: pygame.Surface):

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
            slot_surface = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)

            # Fundo semi-transparente (30, 30, 30) com alpha 180
            pygame.draw.rect(
                slot_surface, (30, 30, 30, 180), (0, 0, slot_w, slot_h), border_radius=8
            )
            pygame.draw.rect(
                slot_surface,
                (*_colors.WHITE, 200),
                (0, 0, slot_w, slot_h),
                2,
                border_radius=8,
            )

            # Nome da tecla vinculada no canto superior esquerdo
            try:
                keycode = self.player_profile.upgrade_keybindings[i]
                key_label = pygame.key.name(keycode).upper()
            except (AttributeError, IndexError, TypeError):
                key_label = str(i + 1)
            label = font_small.render(key_label, True, _colors.WHITE)
            slot_surface.blit(label, (4, 2))

            ui = upg.get_ui_state()  # type: ignore

            # Ícone no centro (usando função centralizada de mapeamento)
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
                pygame.draw.rect(
                    slot_surface,
                    (120, 120, 120, 150),
                    (2, slot_h - bar_h - 2, slot_w - 4, bar_h),
                    border_radius=2,
                )
                bar_w = int((slot_w - 4) * pct)
                pygame.draw.rect(
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
                rect = pygame.Rect(slot_x, y, slot_w, slot_h)
                pygame.draw.rect(surface, _colors.GREEN, rect, 3, border_radius=8)
