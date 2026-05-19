"""
playing.py — Cena principal de gameplay.

Melhorias aplicadas (boas práticas Python / Pygame):
  1. Constantes de módulo extraídas do __init__ para evitar "magic numbers".
  2. __init__ dividido em métodos _init_* coesos (Single Responsibility).
  3. UpgradeContext substituído por dataclass tipada (elimina `type(..., (), ...)(...)`).
  4. _build_mini_ships() elimina duplicação em _process_powerups_and_stars.
  5. _apply_powerup() com dict-dispatch substitui cadeia de elif crescente.
  6. _count_active_stage_hostiles() simplificado com sum() + generator coeso.
  7. Laços de explosão de boss extraídos em _explode_entities().
  8. _compute_shake_offset() encapsula lógica de screen-shake.
  9. _get_shoot_cooldown() centraliza o cálculo do cooldown de tiro.
 10. Docstrings e type hints revisados; comentários inline redundantes removidos.
 11. Importações locais reagrupadas no topo quando possível; ciclos restantes mantidos.
 12. f-strings usadas de forma consistente no logging.
 13. Variável `t` ambígua renomeada para `blink_t` (evita colisão com variável de
     cutscene e melhora legibilidade).
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional, Sequence, TypedDict, cast

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.config import SlimeBossState
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.levels import LevelConfig, LevelManager, get_level_config
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..core.state import Scene
from ..core.upgrades import ActiveUpgrade, HealUpgrade, create_upgrade, get_upgrade_icon
from ..core.upgrades_config import HOMING_DAMAGE_MULTIPLIER, UPGRADE_SLOT_COUNT
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
    from ..systems.collision_protocols import Enemy

# ---------------------------------------------------------------------------
# Constantes de módulo (eliminam "magic numbers" espalhados pela classe)
# ---------------------------------------------------------------------------
_CHEAT_CODE = "271195"
_CHEAT_BUFFER_MAX = len(_CHEAT_CODE)
_SCORE_MULTIPLIER_DURATION = 15.0
_SIDE_SCROLL_SHIP_ENTRY_X = 100
_TOP_DOWN_SHIP_TARGET_Y_OFFSET = 80
_HUD_UPGRADE_SLOT_SIZE = 50
_HUD_UPGRADE_SLOT_GAP = 6


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------


class TransitionPhase(Enum):
    PLAYING = auto()
    POST_VICTORY_DELAY = auto()
    LEVEL_TRANSITION_WAIT = auto()
    CUTSCENE_EXIT = auto()
    WORLD_PANEL = auto()
    LEVEL_ENTRY = auto()


class GameState(Enum):
    """Estado de jogo interno da cena (fase de preparação vs gameplay ativo)."""

    PREPARING = auto()
    PLAYING = auto()


class ThrusterParticle(TypedDict):
    offset_x: float
    offset_y: float
    vx: float
    vy: float
    lifetime: float
    size: float
    color: tuple[int, int, int]


@dataclass
class UpgradeContext:
    """Contexto passado para os upgrades ativos durante update/activate."""

    ship: Ship
    entity_manager: EntityManager
    difficulty_settings: Any
    sound_manager: Any
    scene: "PlayingScene"
    god_mode: bool
    permadeath_mode: bool = False


# ---------------------------------------------------------------------------
# Cena principal
# ---------------------------------------------------------------------------


class PlayingScene(Scene):
    # Flag lida pelo GameApp para suprimir tradução sintética de eventos JOY
    # em menus — playing.py trata os botões do controle nativamente.
    is_gameplay_scene: bool = True

    def __init__(
        self,
        app: "GameApp",
        level_manager: LevelManager,
        difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
        starting_level: int = 1,
    ) -> None:
        super().__init__(app)
        self.level_manager = level_manager
        self.difficulty_preset = difficulty_preset
        self.difficulty_settings = DifficultySettings.get_settings(difficulty_preset)
        self.last_dt: float = 1.0 / Config.FPS
        self.r = app.renderer
        self.first_entry: bool = True
        self.shoot_cd: float = 0.0
        self.cheat_buffer: str = ""
        self.god_mode: bool = False
        self.state: GameState = GameState.PREPARING
        self.preparation_time_left: float = Config.PREPARATION_TIME
        self.level_start_time: Optional[float] = None
        self.level_start_score: int = 0
        self.level_damage_taken: int = 0
        self.level_powerups_collected: int = 0
        # Estado anterior dos triggers analógicos do controle (para detectar
        # transição abaixo/acima do threshold sem disparar a cada AXISMOTION).
        self._lt_pressed: bool = False
        # Calibração defensiva do LT: só confiamos no axis 2 como gatilho se
        # ele já reportou valor próximo de -1 (estado solto de trigger real).
        # Sticks analógicos repousam em ~0 e nunca chegam a -1 sem input —
        # então qualquer controle que reporte o RS Y em axis 2 (mapeamento
        # SDL não-padrão) NÃO acionará habilidades especiais por engano.
        self._lt_calibrated: bool = False
        # Modo de seleção de upgrade via controle: D-pad ↑ alterna, LB/RB
        # navegam entre slots ativos, A confirma, B cancela.
        self._upgrade_select_mode: bool = False
        self._upgrade_select_index: int = 0
        self.level_attempt_recorded: bool = False
        self.transition_phase: TransitionPhase = TransitionPhase.LEVEL_ENTRY
        self.enemies_destroyed_in_level: int = 0
        self.boss_fight_active: bool = False
        self.pre_boss_transition: bool = False
        self.pre_boss_timer: float = 0.0
        self.warning_sound_played: bool = False
        self.warning_stage: int = 0
        self.warning_stage_timer: float = 0.0
        self.music_fade_started: bool = False
        self.boss_music_started: bool = False
        self.screen_shake_timer: float = 0.0
        self.screen_shake_intensity: int = Config.SCREEN_SHAKE_NORMAL
        self.warning_timer: float = 0.0
        self.time_stop_timer: float = 0.0
        self.freeze_active: bool = False
        self._cacador_laser_channel: Any | None = None
        self.enemy_cleanup_active: bool = False
        self.enemy_cleanup_timer: float = 0.0
        self.enemy_blink_timer: float = 0.0
        self.enemy_blink_interval: float = 0.2
        self.enemy_visible: bool = True
        self.show_fps: bool = False
        self.show_enemy_hitboxes: bool = False
        self._game_over_triggered: bool = False
        self.score_multiplier_timer: float = 0.0
        self.score_multiplier_active: bool = False
        self._boss_type_cache: Optional[str] = None
        self.level_transition_timer: float = 0.0
        self.level_transition_pending_timer: float = 0.0
        self.pending_world_transition: Optional[WorldConfig] = None
        self.world_transition_cutscene_timer: float = 0.0
        self.world_transition_cutscene_launch_speed: float = 0.0
        self.world_transition_cutscene_origin: tuple[float, float] = (0.0, 0.0)
        self.world_transition_cutscene_recoil_offset: float = 0.0
        self.world_transition_cutscene_launch_distance: float = 0.0
        self.world_transition_cutscene_target_world: Optional[WorldConfig] = None
        self.world_transition_cutscene_debug_mode: bool = False
        self.world_transition_thruster_particles: list[ThrusterParticle] = []
        self.start_fade_active: bool = False
        self.start_fade_alpha: float = 255.0
        self.start_fade_elapsed: float = 0.0
        self.level_config: LevelConfig | None = None
        self._base_score_multiplier: float = 1.0
        self.lives: int = 0
        self.player_damage_multiplier: float = 1.0
        self.enemy_health_multiplier: float = 1.0
        self.score: int = 0
        self.total_enemies_destroyed: int = 0
        self.enemies_to_clear: int = 0
        self.has_boss: bool = False

        # Índice 0-based; starting_level é 1-based
        self.current_level_index: int = starting_level - 1
        self.current_world = get_world_for_level(self.current_level_index + 1)
        self.is_side_scroll: bool = is_side_scroll_mode(self.current_world.theme)

        self._init_player_profile()
        self._init_ship()
        self._init_game_state()
        self._init_transition_state()
        self._init_fade()
        self._init_systems()
        # Engenheiro: mini-naves permanentes só podem ser spawnadas depois que
        # `entity_manager` existe (criado em `_init_systems`).
        self._build_permanent_mini_ships()
        self._init_upgrades_from_profile()

    # ------------------------------------------------------------------
    # Inicialização segmentada
    # ------------------------------------------------------------------

    def _init_player_profile(self) -> None:
        # Reusa a instância oficial do app — criar uma nova aqui causaria
        # duas instâncias divergentes: record_attempt/record_death iriam para
        # esta cópia, mas save() chamado por outras cenas (game over, settings)
        # iria pela do app, sobrescrevendo o JSON sem os updates de gameplay.
        self.player_profile = self.app.player_profile
        if self.player_profile.current_session is None:
            self.player_profile.start_session()

    def _init_ship(self) -> None:
        if self.is_side_scroll:
            ship_x = -50.0
            ship_y = (Config.SCREEN_HEIGHT - 35) / 2.0
        else:
            ship_x = Config.SCREEN_WIDTH / 2.0 - 20
            ship_y = float(Config.SCREEN_HEIGHT + 100)

        self.ship = Ship(
            ship_x,
            ship_y,
            mouse_control=self.app.preferences.mouse_control,
            auto_fire=self.app.preferences.auto_fire,
            profile=self.player_profile.get_selected_ship_profile(),
        )
        self.ship.is_entering = True
        self.ship.apply_world_mode(self.is_side_scroll)

        self.first_entry: bool = True

    def _init_game_state(self) -> None:
        """Inicializa o estado de jogo e aplica configurações de dificuldade."""
        self.shoot_cd: float = 0.0
        self.cheat_buffer: str = ""
        self.god_mode: bool = False
        self.state: GameState = GameState.PREPARING
        self.preparation_time_left: float = Config.PREPARATION_TIME
        self._lt_pressed: bool = False
        self._lt_calibrated: bool = False
        self._upgrade_select_mode: bool = False
        self._upgrade_select_index: int = 0
        self.level_start_time: Optional[float] = None
        self.level_start_score: int = 0
        self.level_damage_taken: int = 0
        self.level_powerups_collected: int = 0
        self.level_attempt_recorded: bool = False
        self.transition_phase: TransitionPhase = TransitionPhase.LEVEL_ENTRY
        self._apply_difficulty_settings()

        self.enemies_destroyed_in_level: int = 0
        self.boss_fight_active: bool = False
        self.pre_boss_transition: bool = False
        self.pre_boss_timer: float = 0.0
        self.warning_sound_played: bool = False

        # Sistema de warning em 3 estágios: 0=idle, 1=pre-delay, 2=active, 3=post-delay
        self.warning_stage: int = 0
        self.warning_stage_timer: float = 0.0

        self.music_fade_started: bool = False
        self.boss_music_started: bool = False

        self.screen_shake_timer: float = 0.0
        self.screen_shake_intensity: int = Config.SCREEN_SHAKE_NORMAL
        self.warning_timer: float = 0.0
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)

        self.time_stop_timer: float = 0.0
        self.freeze_active: bool = False
        self._cacador_laser_channel: Any | None = None

        self.enemy_cleanup_active: bool = False
        self.enemy_cleanup_timer: float = 0.0
        self.enemy_cleanup_duration: float = 20.0
        self.enemy_blink_timer: float = 0.0
        self.enemy_blink_interval: float = 0.2
        self.enemy_visible: bool = True

        self.show_fps: bool = False
        self.show_enemy_hitboxes: bool = False

        self._game_over_triggered: bool = False

        self.score_multiplier_timer: float = 0.0
        self.score_multiplier_active: bool = False
        self.score_multiplier_value: float = 1.5

        self.floating_score_batch_threshold: float = 60.0

        # Cache de otimização
        self._boss_type_cache: Optional[str] = None
        self._special_rules: list[str] = self.difficulty_settings.get(
            "special_rules", []
        )
        self._no_powerups_mode: bool = "no_powerups" in self._special_rules
        self._permadeath_mode: bool = "permadeath" in self._special_rules

        # Pré-calcula valores de power-up para evitar lookups repetidos
        self._powerup_values: dict[str, float] = {
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
            "damage_boost_duration": Config.DAMAGE_BOOST_DURATION,
        }

    def _init_transition_state(self) -> None:
        """Inicializa timers e flags de transição de nível/mundo."""
        self.level_transition_timer: float = 0.0
        self.level_transition_delay: float = Config.LEVEL_TRANSITION_DELAY
        self.level_transition_pending_timer: float = 0.0
        self.level_transition_pending_delay: float = (
            Config.LEVEL_TRANSITION_PENDING_DELAY
        )
        self.level_transition_animation_timeout: float = (
            Config.LEVEL_TRANSITION_ANIMATION_TIMEOUT
        )
        self.pending_world_transition: Optional[WorldConfig] = None

        self.world_transition_cutscene_timer: float = 0.0
        self.world_transition_cutscene_duration: float = (
            Config.WORLD_TRANSITION_CUTSCENE_DURATION
        )
        self.world_transition_cutscene_charge_duration: float = (
            Config.WORLD_TRANSITION_CUTSCENE_CHARGE_DURATION
        )
        self.world_transition_cutscene_launch_speed: float = (
            Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED
        )
        self.world_transition_cutscene_origin: tuple[float, float] = (0.0, 0.0)
        self.world_transition_cutscene_recoil_offset: float = 0.0
        self.world_transition_cutscene_launch_distance: float = 0.0
        self.world_transition_cutscene_target_world: Optional[WorldConfig] = None
        self.world_transition_cutscene_debug_mode: bool = False
        self.world_transition_thruster_particles: list[ThrusterParticle] = []

    def _init_fade(self) -> None:
        """Configura o fade-in inicial para evitar corte abrupto."""
        self.start_fade_active: bool = True
        self.start_fade_alpha: float = 255.0
        self.start_fade_elapsed: float = 0.0
        self.start_fade_duration: float = 0.45
        self.start_fade_overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )

    def _init_systems(self) -> None:
        """Instancia sistemas de jogo (EntityManager, spawners, colisões)."""
        self.level_config = self._get_adjusted_level_config(
            self.current_level_index + 1
        )
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))

        self.entity_manager = EntityManager(is_side_scroll=self.is_side_scroll)
        self._apply_world_theme()
        self._cache_level_thresholds()

        is_initial_level = self.current_level_index == 0
        self.enemy_spawner = EnemySpawner(
            self.level_manager,
            self.entity_manager.meteor_pool,
            is_initial_level,
            self.difficulty_preset,
            self.enemy_health_multiplier,
        )
        # Sincroniza o spawner com o starting_level — sem isto o spawner usa o
        # config do nível 1 por default, o que quebra inicializações em mundos
        # diferentes do primeiro (ex.: começar em STARFIELD via world select).
        if not is_initial_level:
            self.enemy_spawner.set_level(self.current_level_index + 1, level_config=self.level_config)
        self.powerup_spawner = PowerUpSpawner(self.difficulty_preset)
        self.collisions = Collisions()
        self.star_spawner = StarSpawner()

        self._base_score_multiplier: float = (
            self.level_config.score_multiplier
            * self.difficulty_settings["rewards_multiplier"]
        )

    # ------------------------------------------------------------------
    # Configuração de dificuldade e cache
    # ------------------------------------------------------------------

    def _apply_difficulty_settings(self) -> None:
        """Aplica configurações globais do preset de dificuldade."""
        settings = self.difficulty_settings
        self.lives: int = settings["lives"]
        self.player_damage_multiplier: float = settings["player_damage_multiplier"]
        self.enemy_health_multiplier: float = settings["enemy_health_multiplier"]

        self.score: int = 0
        self._sync_lives(self.lives)
        self.total_enemies_destroyed: int = 0
        self.shoot_cd = 0.0
        self.cheat_buffer = ""
        self.god_mode = False
        self.state = GameState.PREPARING
        self.preparation_time_left = Config.PREPARATION_TIME
        self.level_start_time = None
        self.level_start_score = 0
        self.level_damage_taken = 0
        self.level_powerups_collected = 0
        self.level_attempt_recorded = False

    def _cache_level_thresholds(self) -> None:
        """Pré-calcula valores usados em verificações frequentes."""
        level_config = self.level_config
        assert level_config is not None
        self.enemies_to_clear = level_config.enemies_to_clear
        self.has_boss = bool(level_config.boss_type)

    def _get_adjusted_level_config(self, level_number: int) -> LevelConfig:
        """Obtém configuração de nível ajustada pelo meta-progression."""
        base_config = get_level_config(level_number, self.difficulty_preset)
        return self.player_profile.get_adjusted_config(base_config)

    def _apply_world_theme(self) -> None:
        """Aplica o tema visual do mundo atual."""
        self.r.set_world_theme(self.current_world.theme)
        self._apply_mountains_progress()
        logger.info(
            "🌍 Mundo aplicado: %s (%s)",
            self.current_world.name,
            self.current_world.theme.value,
        )

    def _apply_mountains_progress(self) -> None:
        """No-op: o progresso warm→night é agora contínuo e automático no
        background das cordilheiras. Mantido por compatibilidade com o fluxo
        de theme changes, mas não faz mais nada."""
        pass

    # ------------------------------------------------------------------
    # Máquina de estados de transição
    # ------------------------------------------------------------------

    def _set_transition_phase(self, phase: TransitionPhase) -> None:
        """Atualiza a fase de transição e sincroniza os flags legados."""
        self.transition_phase = phase

        if phase != TransitionPhase.POST_VICTORY_DELAY:
            self.level_transition_pending_timer = 0.0
        if phase != TransitionPhase.LEVEL_TRANSITION_WAIT:
            self.level_transition_timer = 0.0

    @property
    def level_transition_pending(self) -> bool:
        return self.transition_phase == TransitionPhase.POST_VICTORY_DELAY

    @property
    def level_transition_active(self) -> bool:
        return self.transition_phase == TransitionPhase.LEVEL_TRANSITION_WAIT

    @property
    def world_transition_cutscene_active(self) -> bool:
        return self.transition_phase == TransitionPhase.CUTSCENE_EXIT

    @world_transition_cutscene_active.setter
    def world_transition_cutscene_active(self, value: bool) -> None:
        if value:
            self.transition_phase = TransitionPhase.CUTSCENE_EXIT
        elif self.transition_phase == TransitionPhase.CUTSCENE_EXIT:
            self.transition_phase = (
                TransitionPhase.WORLD_PANEL
                if self.pending_world_transition is not None
                else TransitionPhase.LEVEL_ENTRY
            )

    @property
    def awaiting_world_transition_panel(self) -> bool:
        return self.transition_phase == TransitionPhase.WORLD_PANEL

    def _can_handle_gameplay_actions(self) -> bool:
        """Retorna True quando o jogador pode agir normalmente."""
        return self.transition_phase == TransitionPhase.PLAYING

    def _begin_level_preparation(self) -> None:
        """Coloca a cena em modo de preparação para o próximo nível."""
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
        self.state = GameState.PREPARING
        self.preparation_time_left = Config.PREPARATION_TIME
        self.level_start_time = None
        self.level_start_score = 0
        self.level_damage_taken = 0
        self.level_powerups_collected = 0
        self.level_attempt_recorded = False
        self._reset_ship_for_level_entry()

    def _reset_ship_for_level_entry(self) -> None:
        """Reposiciona a nave para a posição de entrada do nível atual."""
        if self.is_side_scroll:
            self.ship.x = -50.0
            self.ship.y = (Config.SCREEN_HEIGHT - 35) / 2.0
            self.ship.set_rotation(90.0)
        else:
            self.ship.x = Config.SCREEN_WIDTH / 2.0 - 20
            self.ship.y = float(Config.SCREEN_HEIGHT + 100)
        self.ship.is_entering = True
        self.ship.apply_world_mode(self.is_side_scroll)

    def _begin_playing_state(self) -> None:
        """Ativa o gameplay e registra a tentativa do nível uma única vez."""
        self._set_transition_phase(TransitionPhase.PLAYING)
        self.state = GameState.PLAYING
        self.ship.is_entering = False
        if self.level_start_time is None:
            self.level_start_time = time.time()
            self.level_start_score = self.score
        if not self.level_attempt_recorded:
            self.player_profile.record_attempt(self.current_level_index + 1)
            self.level_attempt_recorded = True

    def _apply_pending_world_transition(self) -> None:
        """Aplica o mundo pendente após o painel de transição finalizar."""
        if (
            self.pending_world_transition is None
            and self.transition_phase == TransitionPhase.PLAYING
        ):
            return

        if self.pending_world_transition is None:
            self._begin_playing_state()
            return

        new_world = self.pending_world_transition
        self.current_world = new_world
        self.is_side_scroll = is_side_scroll_mode(new_world.theme)
        self.pending_world_transition = None
        self._apply_world_theme()
        # Usa o mesmo fluxo de preparação dos níveis normais — ``_begin_playing_state``
        # direto zerava ``is_entering`` no mesmo frame e a animação de entrada
        # nunca tocava. ``_begin_level_preparation`` mantém ``state=PREPARING``
        # até ``_update_preparing_state`` consumir ``Config.PREPARATION_TIME``,
        # garantindo que a nave deslize da borda até a posição alvo.
        self._begin_level_preparation()

    # ------------------------------------------------------------------
    # Cutscene de transição de mundo
    # ------------------------------------------------------------------

    def _find_next_world_for_debug_preview(
        self,
    ) -> tuple[Optional[WorldConfig], Optional[int]]:
        """Encontra o próximo mundo diferente para o preview de debug."""
        for offset in range(1, 20):
            candidate_level = self.current_level_index + 1 + offset
            candidate_world = get_world_for_level(candidate_level)
            if candidate_world.theme != self.current_world.theme:
                return candidate_world, candidate_level
        return None, None

    def _spawn_world_transition_thruster_particles(self, intensity: int) -> None:
        """Gera partículas extras para o impulso da cutscene."""
        if self.ship.ship_image is not None:
            sprite_w, sprite_h = self.ship.ship_image.get_size()
        else:
            sprite_w, sprite_h = self.ship.w, self.ship.h

        for _ in range(intensity):
            if self.is_side_scroll:
                particle: ThrusterParticle = {
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
        """Atualiza e filtra partículas da cutscene (list comprehension imutável)."""
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
        self.ship.is_entering = True
        self.ship.is_side_scroll = self.is_side_scroll
        # Força o sprite a apontar na direção do launch — evita que uma rotação
        # CTRL anterior do jogador faça a nave voar de costas/de lado durante a
        # cutscene. O facing volta ao default no próximo mundo via apply_world_mode.
        self.ship.set_facing("east" if self.is_side_scroll else "north")
        logger.info(
            "[CUTSCENE] Iniciando saída da nave para %s (debug=%s)",
            target_world.name,
            debug_mode,
        )

    def _finish_world_transition_cutscene(self) -> None:
        """Finaliza a cutscene e abre o painel de transição."""
        if not self.world_transition_cutscene_active:
            return

        target_world = self.world_transition_cutscene_target_world
        debug_mode = self.world_transition_cutscene_debug_mode

        self.world_transition_cutscene_timer = 0.0
        self.world_transition_cutscene_target_world = None
        self.world_transition_cutscene_debug_mode = False
        self.world_transition_thruster_particles.clear()
        self.world_transition_cutscene_recoil_offset = 0.0
        self.world_transition_cutscene_launch_distance = 0.0

        if target_world is None:
            return

        if debug_mode:
            self._begin_level_preparation()
        else:
            self._set_transition_phase(TransitionPhase.WORLD_PANEL)

        logger.info(
            "[CUTSCENE] Saída concluída, abrindo painel de transição (%s)",
            target_world.name,
        )

        from .world_transition import WorldTransitionScene

        self.app.states.push(WorldTransitionScene(self.app, target_world))

        if debug_mode:
            logger.info("[CUTSCENE] Preview visual completo executado via F8")

    def _update_world_transition_cutscene(self, dt: float) -> None:
        """Atualiza a cinemática de saída da nave (charge → launch)."""
        if not self.world_transition_cutscene_active:
            return

        self.world_transition_cutscene_timer += dt
        t = self.world_transition_cutscene_timer
        charge_end = self.world_transition_cutscene_charge_duration
        charge_progress = min(1.0, max(0.0, t / charge_end))

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
            "[DEBUG] Preview de transição: %s -> %s (nível alvo %s)",
            self.current_world.name,
            world.name,
            level,
        )
        self._start_world_transition_cutscene(world, debug_mode=True)

    # ------------------------------------------------------------------
    # Ciclo de vida da cena
    # ------------------------------------------------------------------

    def enter(self) -> None:
        pygame.mouse.set_visible(False)
        if self.first_entry:
            sound_manager.music_state_manager.transition_to(MusicState.GAME)
            self.first_entry = False
        if self.transition_phase == TransitionPhase.WORLD_PANEL:
            self._apply_pending_world_transition()

    def exit(self) -> None:
        pygame.mouse.set_visible(True)

    # ------------------------------------------------------------------
    # Update principal
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        if self._game_over_triggered:
            return

        self.last_dt = dt
        self._update_start_fade(dt)

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

        self._update_preparing_state(dt)
        self._update_timers(dt)
        self._update_ship(dt)
        self._apply_environmental_effects(dt)
        self._update_spawners(dt)

        self.entity_manager.update(
            dt,
            self.ship.rect.centerx,
            self.ship.rect.centery,
            freeze_enemies=self.freeze_active,
            screen_width=Config.SCREEN_WIDTH,
            screen_height=Config.SCREEN_HEIGHT,
            attraction_mult=self.ship.profile.pickup_radius_mult,
        )

        if self._cacador_laser_channel is not None:
            has_alive_cacador_laser = any(
                getattr(laser, "state", "") == "alive"
                for laser in self.entity_manager.cacador_lasers
            )
            if not has_alive_cacador_laser:
                self._cacador_laser_channel.stop()
                self._cacador_laser_channel = None

        # Sincronizar volume do laser carregado se estiver ativo (opcional, mantendo compatibilidade)

        if self.transition_phase in (
            TransitionPhase.PLAYING,
            TransitionPhase.LEVEL_ENTRY,
        ):
            self._handle_collisions()
            if self._game_over_triggered:
                return

        # self.entity_manager.cleanup()  # Removido: já chamado internamente em entity_manager.update()
        self._update_level_logic(dt)
        self.player_profile.auto_save()

    def _update_start_fade(self, dt: float) -> None:
        if not self.start_fade_active:
            return
        self.start_fade_elapsed = min(
            self.start_fade_duration, self.start_fade_elapsed + dt
        )
        progress = self.start_fade_elapsed / self.start_fade_duration
        eased = 1.0 - (1.0 - progress) ** 3  # ease-out cúbico
        self.start_fade_alpha = 255.0 * (1.0 - eased)
        if self.start_fade_elapsed >= self.start_fade_duration:
            self.start_fade_alpha = 0.0
            self.start_fade_active = False

    def _update_preparing_state(self, dt: float) -> None:
        if self.state != GameState.PREPARING:
            return

        self.preparation_time_left -= dt

        if self.is_side_scroll:
            initial_x = -50.0
            target_x = float(_SIDE_SCROLL_SHIP_ENTRY_X)
            target_y = (Config.SCREEN_HEIGHT - 35) / 2.0

            if self.preparation_time_left > 0:
                elapsed = Config.PREPARATION_TIME - self.preparation_time_left
                progress = min(1.0, elapsed / Config.PREPARATION_TIME)
                self.ship.x = initial_x + (target_x - initial_x) * progress
                self.ship.y = target_y
            else:
                self.ship.x = target_x
                self.ship.y = target_y
                self._begin_playing_state()
        else:
            initial_y = float(Config.SCREEN_HEIGHT + 100)
            target_y = float(Config.SCREEN_HEIGHT - _TOP_DOWN_SHIP_TARGET_Y_OFFSET)

            if self.preparation_time_left > 0:
                elapsed = Config.PREPARATION_TIME - self.preparation_time_left
                progress = min(1.0, elapsed / Config.PREPARATION_TIME)
                self.ship.y = initial_y + (target_y - initial_y) * progress
            else:
                self.ship.y = target_y
                self._begin_playing_state()

    def _update_timers(self, dt: float) -> None:
        self.time_stop_timer = max(0.0, self.time_stop_timer - dt)
        self.freeze_active = self.time_stop_timer > 0.0
        self.shoot_cd = max(0.0, self.shoot_cd - dt)
        self.warning_timer = max(0.0, self.warning_timer - dt)

        if self.score_multiplier_active:
            self.score_multiplier_timer -= dt
            if self.score_multiplier_timer <= 0.0:
                self.score_multiplier_timer = 0.0
                self.score_multiplier_active = False

        self._update_upgrades(dt)

        boss = cast(Any, self.entity_manager.boss)
        if boss and (
            getattr(boss, "state", None) == "entering"
            or getattr(boss, "current_state", None) == SlimeBossState.ENTERING
        ):
            self.screen_shake_timer = 0.1
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

    def _update_ship(self, dt: float) -> None:
        self.ship.update(dt, self.entity_manager, is_side_scroll=self.is_side_scroll)
        if self.ship.mini_ships_timer == 0.0 and self.entity_manager.mini_ships:
            # Powerup expirou: se há mini-naves temporárias, troca-as pelas
            # permanentes do Engenheiro (se a nave atual tiver alguma).
            has_temps = any(
                not getattr(m, "permanent", False)
                for m in self.entity_manager.mini_ships
            )
            if has_temps:
                self.entity_manager.mini_ships.clear()
                self._build_permanent_mini_ships()

        boss_pausing = False
        if self._boss_type_cache == "spike" and self.entity_manager.boss:
            from ..entities.spike_boss import SpikeBoss

            boss_pausing = cast(SpikeBoss, self.entity_manager.boss).is_pausing_game()

        if self._can_handle_gameplay_actions() and not self.ship.is_entering:
            held = self.app.input.poll_held(self.app.gamepad)
            gamepad_vec = self.app.input.gamepad_movement_vector(self.app.gamepad)
            self.ship.move(
                held,
                dt,
                is_side_scroll=self.is_side_scroll,
                gamepad_vec=gamepad_vec,
            )

            # Caçador: enquanto a carga está acumulando, suprime auto-fire/hold-shoot.
            # O disparo carregado sai no MOUSEBUTTONUP.
            charging = (
                self.ship.profile.has_charge_shot and self.ship.charge_shot_active
            )
            if (
                ("hold_shoot" in held or self.ship.should_auto_fire())
                and self.shoot_cd == 0.0
                and not boss_pausing
                and self.ship.speed_modifier_timer <= 0.0
                and not charging
            ):
                self._fire_bullets()

    def _apply_environmental_effects(self, dt: float) -> None:
        """Aplica efeitos ambientais (como vento) à nave do jogador."""
        if not self._can_handle_gameplay_actions() or self.ship.is_entering:
            return

        # Vento do MountainPropeller
        wind_slow_factor = 1.0
        for prop in self.entity_manager.mountain_propellers:
            if prop.is_blowing():
                wind_rect = prop.get_wind_rect()
                if self.ship.rect.colliderect(wind_rect):
                    self.ship.x -= prop.PUSH_FORCE * dt
                    wind_slow_factor = prop.SLOW_SPEED_MULT


        self.ship.wind_slow_factor = wind_slow_factor

    def _update_spawners(self, dt: float) -> None:
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

            if not self._no_powerups_mode:
                self.powerup_spawner.update(dt, self.entity_manager.powerups)

            self.star_spawner.update(self.entity_manager.stars)

    def _update_level_logic(self, dt: float) -> None:
        if self.boss_fight_active:
            if self.entity_manager.boss and self.entity_manager.boss.dead:
                self._end_boss_fight()
        elif self.pre_boss_transition:
            if not self.entity_manager.enemies and self.warning_stage == 0:
                self.warning_stage = 1
                self.warning_stage_timer = 0.0
                self.warning_sound_played = False
            self._update_warning_system(dt)
        elif self.transition_phase == TransitionPhase.PLAYING:
            if self._game_over_triggered:
                return
            self._update_enemy_cleanup(dt)
            self._check_level_progression()

    def _update_enemy_cleanup(self, dt: float) -> None:
        if not self.enemy_cleanup_active:
            return

        self.enemy_cleanup_timer += dt
        time_remaining = max(
            0.0, self.enemy_cleanup_duration - self.enemy_cleanup_timer
        )

        if 0.0 < time_remaining <= 5.0:
            blink_t = max(0.0, min(1.0, time_remaining / 5.0))
            self.enemy_blink_interval = 0.05 + (0.4 - 0.05) * blink_t
            self.enemy_blink_timer += dt
            if self.enemy_blink_timer >= self.enemy_blink_interval:
                self.enemy_blink_timer = 0.0
                self.enemy_visible = not self.enemy_visible
        elif time_remaining <= 0.0:
            self.enemy_visible = True
            self._force_kill_stage_hostiles()
            self.enemy_cleanup_active = False

    def _force_kill_stage_hostiles(self) -> None:
        em = self.entity_manager
        for e in em.enemies:
            if not getattr(e, "dead", False):
                e.dead = True
        for f in em.formations:
            if not getattr(f, "dead", False):
                for e in f.get_enemies():
                    if not getattr(e, "dead", False):
                        e.dead = True
        for m in em.boulders:
            if not m.dead:
                m.dead = True
        for s in em.attack_debris:
            if not s.dead:
                s.dead = True
        for r in em.orbital_debris:
            if not r.dead and getattr(r, "causes_damage", False):
                r.dead = True

    # ------------------------------------------------------------------
    # Tiro
    # ------------------------------------------------------------------

    def _get_shoot_cooldown(self) -> float:
        """Calcula e retorna o cooldown de tiro baseado na attack speed da nave."""
        return 1.0 / (self.ship.attack_speed_multiplier * Config.FIRE_RATE)

    def _fire_bullets(self) -> None:
        """Dispara as balas da nave e reinicia o cooldown.

        Para o Caçador, o tiro carregado vira um laser especial separado.
        """
        bullet_specs = self.ship.bullet_spawn()
        # Caçador: se há carga ativa, consome o fator e ativa o tiro carregado.
        charge_factor = self.ship.consume_charge()
        # `ship.damage_multiplier` já compõe o profile da nave com o damage_boost
        # ativo (powerup multiplicativo sobre o stat da nave).
        adjusted_damage = int(
            Config.BULLET_BASE_DAMAGE
            * self.player_damage_multiplier
            * self.ship.damage_multiplier
            * charge_factor
        )

        # Charge shot: behavior depends on ship type. Magneto => laser, Caçador => 5 homing bullets.
        is_charge_shot = self.ship.profile.has_charge_shot and charge_factor > 1.0
        if is_charge_shot:
            ship_id = getattr(self.ship.profile, "id", "")
            # Magneto keeps the continuous boss-laser behaviour
            if ship_id == "magneto":
                if self._cacador_laser_channel is not None:
                    self._cacador_laser_channel.stop()
                self._cacador_laser_channel = sound_manager.play_boss_laser_fire(
                    return_channel=True
                )
                for x, y, direction, *_ in bullet_specs:
                    dx, dy = direction
                    mag = math.hypot(dx, dy)
                    if mag == 0.0:
                        continue
                    unit_dir = (dx / mag, dy / mag)
                    self.entity_manager.spawn_cacador_laser(
                        x,
                        y,
                        direction=unit_dir,
                        damage=adjusted_damage,
                    )
                self.shoot_cd = self._get_shoot_cooldown()
                return

            # Caçador: dispara múltiplos tiros teleguiados com alvos independentes.
            # Cada projétil recebe um alvo exclusivo (round-robin sobre os inimigos
            # vivos em tela), evitando que todos persigam o mesmo inimigo.
            # Não dispara se já há projéteis teleguiados vivos — evita acúmulo.
            if ship_id == "cacador":
                if self.entity_manager.homing_bullets:
                    self.shoot_cd = self._get_shoot_cooldown()
                    return
                count = 5
                spread = math.radians(90)
                divisor = max(1, count - 1)

                # Coletar inimigos válidos para distribuição de alvos.
                live_enemies = [
                    e for e in self.entity_manager.enemies
                    if not getattr(e, "dead", False)
                ]
                if self.entity_manager.boss and not getattr(
                    self.entity_manager.boss, "dead", False
                ):
                    live_enemies.append(self.entity_manager.boss)

                for x, y, direction, *_ in bullet_specs:
                    dx, dy = direction
                    mag = math.hypot(dx, dy)
                    if mag == 0.0:
                        continue
                    base_angle = math.atan2(dy, dx)
                    for i in range(count):
                        t = i / divisor
                        angle = base_angle - spread / 2 + t * spread
                        dir_vec = (math.cos(angle), math.sin(angle))
                        # Distribuição round-robin: projétil i persegue inimigo i % n.
                        # Se não há inimigos, locked_target=None e o projétil busca
                        # o mais próximo dinamicamente (comportamento padrão).
                        target = live_enemies[i % len(live_enemies)] if live_enemies else None
                        self.entity_manager.spawn_homing_bullet(
                            x,
                            y,
                            damage=adjusted_damage,
                            direction=dir_vec,
                            locked_target=target,
                        )
                self.shoot_cd = self._get_shoot_cooldown()
                return

        # Tocar som de tiro (uma vez por salva de tiros)
        sound_manager.play_shot()

        for (
            x,
            y,
            direction,
            is_piercing,
            is_homing,
            is_explosive,
            is_low_ammo,
        ) in bullet_specs:
            # Tiros teleguiados levam multiplicador de dano direto.
            # Quando combinados com explosivo, o impacto direto fica mais forte
            # (a explosão em área usa EXPLOSIVE_BULLET_DAMAGE no collision system).
            bullet_damage = (
                int(adjusted_damage * HOMING_DAMAGE_MULTIPLIER)
                if is_homing
                else adjusted_damage
            )
            self.entity_manager.spawn_bullet(
                x,
                y,
                damage=bullet_damage,
                piercing=is_piercing,
                homing=is_homing,
                explosive=is_explosive,
                low_ammo=is_low_ammo,
                direction=direction,
                ship_id=self.ship.profile.id,
            )
            if is_explosive:
                self.ship.consume_explosive_shot()
        self.shoot_cd = self._get_shoot_cooldown()

    # ------------------------------------------------------------------
    # Sistema de warning
    # ------------------------------------------------------------------

    def _update_warning_system(self, dt: float) -> None:
        """Atualiza o sistema de warning em 3 estágios."""
        self.warning_stage_timer += dt

        if self.warning_stage == 1:
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
                if not self.warning_sound_played:
                    sound_manager.play_warning()
                    self.warning_sound_played = True

        elif self.warning_stage == 2:
            if self.warning_stage_timer >= Config.BOSS_WARNING_DURATION:
                self.warning_stage = 3
                self.warning_stage_timer = 0.0
                self.warning_timer = 0.0
                self.screen_shake_timer = 0.0
                sound_manager.stop_warning()

        elif self.warning_stage == 3:
            if self.warning_stage_timer >= Config.BOSS_POST_WARNING_DELAY:
                self._start_boss_fight()

    # ------------------------------------------------------------------
    # Cache de boss
    # ------------------------------------------------------------------

    def _cache_boss_type(self) -> None:
        """Cacheia o tipo do boss assim que ele é spawnado."""
        boss = self.entity_manager.boss
        if not boss:
            self._boss_type_cache = None
            return

        from ..entities.cloud_archmage_boss import CloudArchmageBoss
        from ..entities.giant_meteor_boss import GiantMeteorBoss
        from ..entities.mountain_serpent_boss import MountainSerpentBoss
        from ..entities.slime_boss import SlimeBoss
        from ..entities.spike_boss import SpikeBoss
        from ..entities.stone_golem_boss import StoneGolemBoss

        type_map: dict[type, str] = {
            SpikeBoss: "spike",
            SlimeBoss: "slime",
            GiantMeteorBoss: "giant_meteor",
            StoneGolemBoss: "stone_golem",
            MountainSerpentBoss: "mountain_serpent",
            CloudArchmageBoss: "archmage",
        }
        for cls, name in type_map.items():
            if isinstance(boss, cls):
                self._boss_type_cache = name
                return
        self._boss_type_cache = "normal"

    def _all_animations_finished(self) -> bool:
        """Verifica se todas as explosões finalizaram (para transição de nível)."""
        pool_stats = self.entity_manager.explosion_pool.get_stats()
        return (
            not self.entity_manager.explosive_effects
            and pool_stats.get("active", 0) == 0
        )

    # ------------------------------------------------------------------
    # Cheat code
    # ------------------------------------------------------------------

    def _process_cheat_input(self, event: pygame.event.Event) -> None:
        """Detecta o cheat code '271195' para ativar/desativar god mode, adicionar 9999 estrelas e desbloquear todos os mundos."""
        if not pygame.K_0 <= event.key <= pygame.K_9:
            # Se apertar uma tecla que não é número, reseta o buffer
            self.cheat_buffer = ""
            return

        self.cheat_buffer += chr(event.key)
        logger.debug("Cheat buffer: '%s'", self.cheat_buffer)
        if len(self.cheat_buffer) > _CHEAT_BUFFER_MAX:
            self.cheat_buffer = self.cheat_buffer[-_CHEAT_BUFFER_MAX:]

        if self.cheat_buffer == _CHEAT_CODE:
            self.god_mode = not self.god_mode
            self.cheat_buffer = ""
            if self.god_mode:
                logger.info("GOD MODE ATIVADO - Invulnerabilidade ligada!")
                self._apply_god_mode_cooldowns()
                self.player_profile.add_stars(9999)
                self.player_profile.unlock_all_worlds()
                self.player_profile.save()  # Força save imediato
                logger.info("⭐ CHEAT ATIVADO - +9999 Estrelas e todos os mundos desbloqueados!")
                if hasattr(sound_manager, "play_powerup"):
                    sound_manager.play_powerup()  # type: ignore
            else:
                logger.info("GOD MODE DESATIVADO - Invulnerabilidade desligada!")

    # ------------------------------------------------------------------
    # Batching de floating scores
    # ------------------------------------------------------------------

    def _batch_floating_scores(
        self,
        score_events: list[tuple[float, float, int]],
        proximity_threshold: float = 60.0,
    ) -> list[tuple[float, float, int]]:
        """Agrupa score events próximos num único evento somado.

        Para poucos eventos (≤8), usa O(n²) simples.
        Para muitos eventos, usa grid spatial para melhor performance.
        """
        if not score_events:
            return []

        # Para poucos eventos, o custo O(n²) é negligenciável
        if len(score_events) <= 8:
            return self._batch_floating_scores_quadratic(
                score_events, proximity_threshold
            )

        # Grid binning para muitos eventos (picos de dano)
        cell_size = proximity_threshold
        buckets: dict[tuple[int, int], list[tuple[float, float, int]]] = {}

        for x, y, pts in score_events:
            key = (int(x // cell_size), int(y // cell_size))
            if key not in buckets:
                buckets[key] = []
            buckets[key].append((x, y, pts))

        # Agregar pontos dentro de cada célula
        batched: list[tuple[float, float, int]] = []
        for events in buckets.values():
            if not events:
                continue
            avg_x = sum(e[0] for e in events) / len(events)
            avg_y = sum(e[1] for e in events) / len(events)
            total_pts = sum(e[2] for e in events)
            batched.append((avg_x, avg_y, total_pts))

        return batched

    def _batch_floating_scores_quadratic(
        self,
        score_events: list[tuple[float, float, int]],
        proximity_threshold: float,
    ) -> list[tuple[float, float, int]]:
        """Batching O(n²) para poucos eventos (manutenção de compatibilidade)."""
        batched: list[tuple[float, float, int]] = []
        used = [False] * len(score_events)

        for i, (x1, y1, pts1) in enumerate(score_events):
            if used[i]:
                continue
            batch_x, batch_y, batch_pts, batch_count = x1, y1, pts1, 1
            used[i] = True

            for j, (x2, y2, pts2) in enumerate(score_events):
                if used[j] or i == j:
                    continue
                dist = math.hypot(x2 - x1, y2 - y1)
                if dist <= proximity_threshold:
                    batch_x = (batch_x * batch_count + x2) / (batch_count + 1)
                    batch_y = (batch_y * batch_count + y2) / (batch_count + 1)
                    batch_pts += pts2
                    batch_count += 1
                    used[j] = True

            batched.append((batch_x, batch_y, batch_pts))

        return batched

    # ------------------------------------------------------------------
    # Colisões
    # ------------------------------------------------------------------

    def _check_projectile_vs_enemies(
        self, enemy_grid: "SpatialGrid[Any]"
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        """Projéteis da nave vs. inimigos normais. Retorna (score, kills, events, ship_hit)."""
        enemies_view = cast(Sequence["Enemy"], self.entity_manager.enemies)

        gain, destroyed, score_events = self.collisions.bullets_vs_enemies(
            self.entity_manager.bullets,
            enemy_grid,
            self.entity_manager,
            ship=self.ship,
        )

        vector_gain, vector_destroyed, vector_events = (
            self.collisions.mini_ship_bullets_vs_enemies(
                self.entity_manager.mini_ship_bullets,
                enemy_grid,
                self.entity_manager,
            )
        )
        gain += vector_gain
        destroyed += vector_destroyed
        score_events.extend(vector_events)

        laser_gain, laser_destroyed, laser_events = (
            self.collisions.player_lasers_vs_enemies(
                self.entity_manager.player_lasers,
                enemies_view,
                self.entity_manager.floating_scores,
                self.entity_manager,
                enemy_grid,
            )
        )
        gain += laser_gain
        destroyed += laser_destroyed
        score_events.extend(laser_events)

        cacador_gain, cacador_destroyed, cacador_events = (
            self.collisions.cacador_lasers_vs_enemies(
                self.entity_manager.cacador_lasers,
                enemies_view,
                self.entity_manager.floating_scores,
                self.entity_manager,
                enemy_grid,
            )
        )
        gain += cacador_gain
        destroyed += cacador_destroyed
        score_events.extend(cacador_events)

        homing_gain, homing_destroyed, homing_events = (
            self.collisions.homing_bullets_vs_enemies(
                self.entity_manager.homing_bullets,
                enemy_grid,
                self.entity_manager,
            )
        )
        gain += homing_gain
        destroyed += homing_destroyed
        score_events.extend(homing_events)

        mine_gain, mine_destroyed, mine_events, ship_hit = (
            self.collisions.check_mine_explosions(
                enemies_view,
                self.entity_manager.mine_explosions,
                self.ship,
                self.entity_manager,
            )
        )
        gain += mine_gain
        destroyed += mine_destroyed
        score_events.extend(mine_events)

        if self.entity_manager.ice_poison_zones:
            iz_gain, iz_dest, iz_events = self.collisions.ice_poison_zones_vs_entities(
                self.entity_manager.ice_poison_zones,
                enemies_view,
                self.ship,
                self.entity_manager,
            )
            gain += iz_gain
            destroyed += iz_dest
            score_events.extend(iz_events)

        if self.entity_manager.fire_zones:
            fz_gain, fz_dest, fz_events, fz_ship_hit = (
                self.collisions.fire_zones_vs_entities(
                    self.entity_manager.fire_zones,
                    enemies_view,
                    self.ship,
                    self.entity_manager,
                )
            )
            gain += fz_gain
            destroyed += fz_dest
            score_events.extend(fz_events)
            ship_hit = ship_hit or fz_ship_hit

        return gain, destroyed, score_events, ship_hit

    def _check_formation_collisions(
        self, gain: int, destroyed: int, score_events: list[tuple[float, float, int]]
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        """Colisões de área vs. formações e inimigos avulsos."""
        ship_hit = False

        formation_enemy_ids = {
            id(enemy)
            for formation in self.entity_manager.formations
            for enemy in formation.get_enemies()
        }
        enemies_view = [
            enemy
            for enemy in self.entity_manager.enemies
            if id(enemy) not in formation_enemy_ids
        ]

        for formation in self.entity_manager.formations:
            fe = formation.get_enemies()

            f_gain, f_dest, f_events, f_ship_hit = (
                self.collisions.check_mine_explosions(
                    fe,
                    self.entity_manager.mine_explosions,
                    self.ship,
                    self.entity_manager,
                )
            )
            gain += f_gain
            destroyed += f_dest
            score_events.extend(f_events)
            ship_hit = ship_hit or f_ship_hit

            if self.entity_manager.ice_poison_zones:
                iz_gain, iz_dest, iz_events = (
                    self.collisions.ice_poison_zones_vs_entities(
                        self.entity_manager.ice_poison_zones,
                        fe,
                        self.ship,
                        self.entity_manager,
                    )
                )
                gain += iz_gain
                destroyed += iz_dest
                score_events.extend(iz_events)

            if self.entity_manager.fire_zones:
                fz_gain, fz_dest, fz_events, fz_ship_hit = (
                    self.collisions.fire_zones_vs_entities(
                        self.entity_manager.fire_zones,
                        fe,
                        self.ship,
                        self.entity_manager,
                    )
                )
                gain += fz_gain
                destroyed += fz_dest
                score_events.extend(fz_events)
                ship_hit = ship_hit or fz_ship_hit

            if self.entity_manager.cannon_mines:
                cg, cd, ce = self.collisions.cannon_mines_vs_enemies(
                    self.entity_manager.cannon_mines, fe, self.entity_manager
                )
                gain += cg
                destroyed += cd
                score_events.extend(ce)

            if self.entity_manager.explosive_effects:
                eg, ed, ee = self.collisions.explosive_effects_vs_enemies(
                    self.entity_manager.explosive_effects, fe, self.entity_manager
                )
                gain += eg
                destroyed += ed
                score_events.extend(ee)

            if self.entity_manager.air_strike_bombs:
                ag, ad, ae = self.collisions.air_strike_bombs_vs_enemies(
                    self.entity_manager.air_strike_bombs, fe, self.entity_manager
                )
                gain += ag
                destroyed += ad
                score_events.extend(ae)

        if self.entity_manager.explosive_effects:
            eg, ed, ee = self.collisions.explosive_effects_vs_enemies(
                self.entity_manager.explosive_effects, enemies_view, self.entity_manager
            )
            gain += eg
            destroyed += ed
            score_events.extend(ee)

        if self.entity_manager.air_strike_bombs:
            ag, ad, ae = self.collisions.air_strike_bombs_vs_enemies(
                self.entity_manager.air_strike_bombs, enemies_view, self.entity_manager
            )
            gain += ag
            destroyed += ad
            score_events.extend(ae)

        if self.entity_manager.cannon_mines:
            mg, md, me = self.collisions.cannon_mines_vs_enemies(
                self.entity_manager.cannon_mines, enemies_view, self.entity_manager
            )
            gain += mg
            destroyed += md
            score_events.extend(me)

        if self.entity_manager.fire_zones:
            fz_gain, fz_dest, fz_events, fz_ship_hit = (
                self.collisions.fire_zones_vs_entities(
                    self.entity_manager.fire_zones,
                    enemies_view,
                    self.ship,
                    self.entity_manager,
                )
            )
            gain += fz_gain
            destroyed += fz_dest
            score_events.extend(fz_events)
            ship_hit = ship_hit or fz_ship_hit

        return gain, destroyed, score_events, ship_hit

    def _check_boss_collisions(self, gain: int) -> int:
        """Todas as colisões envolvendo o boss. Retorna score_gain total."""
        score_gain = 0
        boss = self.entity_manager.boss

        if not (boss and self._boss_type_cache):
            return gain

        score_gain = self.collisions.bullets_vs_boss(
            self.entity_manager.bullets,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.mini_ship_bullets_vs_boss(
            self.entity_manager.mini_ship_bullets,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.player_lasers_vs_boss(
            self.entity_manager.player_lasers,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.cacador_lasers_vs_boss(
            self.entity_manager.cacador_lasers,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.homing_bullets_vs_boss(
            self.entity_manager.homing_bullets,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )

        if self.entity_manager.explosive_effects:
            score_gain += self.collisions.explosive_effects_vs_boss(
                self.entity_manager.explosive_effects,
                boss,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

        if self.entity_manager.air_strike_bombs:
            score_gain += self.collisions.air_strike_bombs_vs_boss(
                self.entity_manager.air_strike_bombs,
                boss,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

        if self.entity_manager.cannon_mines:
            score_gain += self.collisions.cannon_mines_vs_boss(
                self.entity_manager.cannon_mines,
                boss,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

        if self._boss_type_cache == "slime":
            from ..entities.slime_boss import SlimeBoss

            slime_boss = cast(SlimeBoss, boss)
            drip_damage = slime_boss.check_drip_damage(
                self.ship.rect, self.entity_manager
            )
            if drip_damage > 0:
                self._handle_ship_hit()
                self.level_damage_taken += drip_damage

        score_gain = self._apply_score_multiplier(score_gain)

        return gain + score_gain

    def _check_ship_damage(self) -> None:
        """Verifica todas as colisões que causam dano à nave."""
        em = self.entity_manager

        if self.collisions.alien_bullets_vs_ship(self.ship, em.alien_bullets):
            self._handle_ship_hit()
        if self.collisions.serpent_bullets_vs_ship(self.ship, em.serpent_bullets):
            self._handle_ship_hit()
        if self.collisions.eye_laser_vs_ship(self.ship, em.eye_lasers):
            self._handle_ship_hit()

        orb_hit = self.collisions.energy_orbs_vs_ship(self.ship, em.energy_orbs)
        if orb_hit:
            self._handle_ship_hit()
            if self.ship.invuln > 0:
                orb_hit.apply_effect(self.ship)

        from ..entities.boss_laser import BossLaser

        boss_lasers = [
            laser for laser in em.boss_lasers if isinstance(laser, BossLaser)
        ]
        if self.collisions.laser_vs_ship(self.ship, boss_lasers):
            self._handle_ship_hit()

        spike_lasers: list[SpikeBossLaser] = [
            laser for laser in em.boss_lasers if isinstance(laser, SpikeBossLaser)
        ]
        if spike_lasers and self.collisions.spike_boss_laser_vs_ship(
            self.ship, spike_lasers
        ):
            self._handle_ship_hit()

        if self.collisions.ship_vs_spikes(self.ship, em.spikes, em):
            self._handle_ship_hit()
        if self.collisions.ship_vs_boss_squares(self.ship, em.boss_squares):
            self._handle_ship_hit()

        if self._boss_type_cache == "stone_golem" and em.boss:
            self._check_stone_golem_sweep(em)

        if self._boss_type_cache == "mountain_serpent" and em.boss:
            if self.collisions.ship_vs_boss(self.ship, em.boss, self.entity_manager):
                self._handle_ship_hit()

    def _check_stone_golem_sweep(self, em: EntityManager) -> None:
        """Verifica dano do feixe sweep do StoneGolemBoss."""
        from ..entities.stone_golem_boss import StoneGolemBoss

        golem = cast(StoneGolemBoss, em.boss)
        beam = golem.get_sweep_beam()
        if not beam or self.ship.invuln > 0:
            return

        px, py, ex, ey = beam
        sx = float(self.ship.rect.centerx)
        sy = float(self.ship.rect.centery)
        dx, dy = ex - px, ey - py
        len_sq = dx * dx + dy * dy
        if len_sq <= 0:
            return

        t = max(0.0, min(1.0, ((sx - px) * dx + (sy - py) * dy) / len_sq))
        closest_x = px + t * dx
        closest_y = py + t * dy
        dist = math.hypot(sx - closest_x, sy - closest_y)
        if dist < golem.SCALE * 2 + self.ship.rect.width * 0.4:
            self._handle_ship_hit()

    def _apply_score_multiplier(self, pts: int) -> int:
        """Aplica multiplicador de score base + eventual bônus ativo."""
        multiplier = self._base_score_multiplier
        if self.score_multiplier_active:
            multiplier *= self.score_multiplier_value
        return int(pts * multiplier)

    def _handle_collisions(self) -> None:
        """
        Orquestrador de colisões. Delega para métodos especializados:
        1. Projéteis vs. inimigos normais
        2. Formações e efeitos de área vs. inimigos
        3. Score e floating scores dos inimigos
        4. Mini ships vs. spikes
        5. Nave vs. inimigos (físico)
        6. Boss (projéteis, efeitos, físico, slime drips)
        7. Balas vs. objetos indestrutíveis
        8. Dano à nave
        9. Power-ups e estrelas
        """
        enemy_grid = self.entity_manager.enemy_spatial_grid

        gain, destroyed, score_events, ship_hit_proj = (
            self._check_projectile_vs_enemies(enemy_grid)
        )
        gain, destroyed, score_events, ship_hit_form = self._check_formation_collisions(
            gain, destroyed, score_events
        )

        if ship_hit_proj or ship_hit_form:
            self._handle_ship_hit()
            self.level_damage_taken += 1

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
            # Reverberador: cada inimigo abatido conta para o combo.
            for _ in range(destroyed):
                self.ship.register_kill()

        if self.entity_manager.spikes:
            spike_gain = self.collisions.mini_ship_bullets_vs_spikes(
                self.entity_manager.mini_ship_bullets,
                self.entity_manager.spike_spatial_grid,
                self.entity_manager,
            )
            if self.score_multiplier_active:
                spike_gain = int(spike_gain * self.score_multiplier_value)
            self.score += spike_gain

        # Nave vs. inimigos (físico)
        ship_vs_grid_hit = self.collisions.ship_vs_enemies(
            self.ship, enemy_grid, self.entity_manager
        )
        if ship_vs_grid_hit:
            self._handle_ship_hit()

        self.score += self._check_boss_collisions(0)

        # Balas vs. objetos indestrutíveis
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

        self._check_ship_damage()
        self._process_powerups_and_stars()

    # ------------------------------------------------------------------
    # Power-ups
    # ------------------------------------------------------------------

    def _build_mini_ships(self) -> None:
        """Cria o par temporário do powerup `mini_ships` (left + right).

        Remove qualquer mini-nave existente — inclusive as permanentes do
        Engenheiro — para evitar sobreposição visual. As permanentes voltam
        automaticamente quando o timer do powerup expira.
        """
        self.entity_manager.mini_ships.clear()
        for side in ("left", "right"):
            self.entity_manager.mini_ships.append(
                MiniShip(self.ship, side, is_side_scroll=self.is_side_scroll)
            )

    def _build_permanent_mini_ships(self) -> None:
        """Spawn das mini-naves permanentes conforme `profile.permanent_mini_ships`."""
        count = self.ship.profile.permanent_mini_ships
        if count <= 0:
            return
        # Alterna lados começando pela esquerda; com 1 = só esquerda, 2 = ambas.
        sides = ("left", "right")
        for i in range(min(count, len(sides))):
            self.entity_manager.mini_ships.append(
                MiniShip(
                    self.ship,
                    sides[i],
                    is_side_scroll=self.is_side_scroll,
                    permanent=True,
                )
            )

    def _apply_powerup(self, kind: str) -> None:
        """Aplica o efeito de um power-up coletado via dict-dispatch."""
        pv = self._powerup_values

        def _apply_shield() -> None:
            self.ship.invuln = max(self.ship.invuln, pv["shield_duration"])

        def _apply_double_shot() -> None:
            self.ship.double_shot_timer = max(
                self.ship.double_shot_timer, pv["double_shot_duration"]
            )

        def _apply_speed() -> None:
            self.ship.speed_boost_timer = max(
                self.ship.speed_boost_timer, pv["speed_boost_duration"]
            )

        def _apply_score_bonus() -> None:
            self.score_multiplier_timer = _SCORE_MULTIPLIER_DURATION
            self.score_multiplier_active = True

        def _apply_piercing() -> None:
            self.ship.piercing_shot_timer = max(
                self.ship.piercing_shot_timer, pv["piercing_shot_duration"]
            )

        def _apply_mini_ships() -> None:
            self.ship.mini_ships_timer = max(
                self.ship.mini_ships_timer, pv["mini_ships_duration"]
            )
            self._build_mini_ships()

        def _apply_cooldown_haste() -> None:
            self._apply_cooldown_reduction(pv["cooldown_haste_reduction"])

        def _apply_time_stop() -> None:
            self.time_stop_timer = max(self.time_stop_timer, pv["time_stop_duration"])
            self.freeze_active = True

        def _apply_damage_boost() -> None:
            self.ship.damage_boost_timer = max(
                self.ship.damage_boost_timer, pv["damage_boost_duration"]
            )

        def _apply_chain_shot() -> None:
            self.ship.activate_chain_shot()

        def _apply_repulsion_shield() -> None:
            self.ship.activate_repulsion_shield()

        def _apply_life() -> None:
            self._change_lives(1)

        def _apply_rainbow() -> None:
            _apply_life()
            _apply_shield()
            _apply_double_shot()
            _apply_speed()
            _apply_mini_ships()
            rainbow_score = int(pv["rainbow_score"])
            if self.score_multiplier_active:
                rainbow_score = int(rainbow_score * self.score_multiplier_value)
            self.score += rainbow_score

        dispatch: dict[str, Any] = {
            "life": _apply_life,
            "shield": _apply_shield,
            "double_shot": _apply_double_shot,
            "speed": _apply_speed,
            "score": _apply_score_bonus,
            "piercing_shot": _apply_piercing,
            "mini_ships": _apply_mini_ships,
            "cooldown_haste": _apply_cooldown_haste,
            "time_stop": _apply_time_stop,
            "rainbow": _apply_rainbow,
            "damage_boost": _apply_damage_boost,
            "chain_shot": _apply_chain_shot,
            "repulsion_shield": _apply_repulsion_shield,
        }

        handler = dispatch.get(kind)
        if handler:
            handler()

    def _process_powerups_and_stars(self) -> None:
        """Processa coleta de power-ups e estrelas."""
        collected_stars = self.collisions.ship_vs_stars(
            self.ship, self.entity_manager.stars
        )
        if collected_stars > 0:
            self.player_profile.add_stars(collected_stars)
            sound_manager.play_powerup()

        collected_powerups = self.collisions.ship_vs_powerups(
            self.ship, self.entity_manager.powerups
        )
        if self._no_powerups_mode:
            collected_powerups = []

        for kind in collected_powerups:
            sound_manager.play_powerup()
            # Cofre: guarda no slot livre em vez de aplicar imediato. Se todos
            # estão ocupados, cai no comportamento padrão (consumo imediato)
            # para não desperdiçar o powerup coletado.
            if not (
                self.ship.has_storage_slots() and self.ship.try_store_powerup(kind)
            ):
                self._apply_powerup(kind)
            self.level_powerups_collected += 1

    # ------------------------------------------------------------------
    # Dano à nave / game over
    # ------------------------------------------------------------------

    def _handle_ship_hit(self) -> None:
        """Processa um acerto na nave: god mode, escudo, vidas, game over."""
        if self._game_over_triggered or self.god_mode or self.ship.invuln > 0:
            return

        sound_manager.play_boss_damage()

        # Reverberador: qualquer hit que efetivamente conta reseta o combo.
        self.ship.reset_combo()

        if self.ship.has_shield:
            self.ship.shield_hp -= 1
            if self.ship.shield_hp <= 0:
                self.ship.shield_timer = 0.0
            sound_manager.play_powerup()
            return

        self._change_lives(-1)
        is_game_over = self.lives <= 0
        # No game over, persistir o ganho da fase incompleta (record_clear não
        # roda nesse caso). Em perdas de vida com vidas restantes, deixar para
        # record_clear capturar o total quando a fase for concluída.
        level_gain_on_death = (
            self.score - self.level_start_score if is_game_over else 0
        )
        self.player_profile.record_death(
            self.current_level_index + 1,
            cause="collision",
            score=level_gain_on_death,
        )

        if not is_game_over:
            self.ship.invuln = Config.INVULN_TIME * 1000
        else:
            # Captura o score final ANTES de qualquer zeragem para a tela de
            # Game Over exibir o valor real (sem isso, permadeath mostraria 0).
            final_score = self.score
            if self._permadeath_mode:
                self.score = 0
            next_level = self.player_profile.reset_to_checkpoint()
            logger.info("Game Over! Reinício preparado para nível %d", next_level)
            self._game_over_triggered = True

            from .game_over import GameOverScene

            self.app.states.switch(
                GameOverScene(self.app, final_score, self, next_level)
            )

    # ------------------------------------------------------------------
    # Progressão de nível
    # ------------------------------------------------------------------

    def _count_active_stage_hostiles(self) -> int:
        """Conta hostis ativos relevantes para concluir a fase."""
        em = self.entity_manager

        active_enemies = sum(1 for e in em.enemies if not getattr(e, "dead", False))
        active_formation_enemies = sum(
            1
            for f in em.formations
            if not getattr(f, "dead", False)
            for e in f.get_enemies()
            if not getattr(e, "dead", False)
        )
        active_boulders = sum(1 for m in em.boulders if not m.dead)
        active_attack_debris = sum(1 for s in em.attack_debris if not s.dead)
        active_orbital_debris = sum(
            1
            for r in em.orbital_debris
            if not r.dead and getattr(r, "causes_damage", False)
        )

        return (
            active_enemies
            + active_formation_enemies
            + active_boulders
            + active_attack_debris
            + active_orbital_debris
        )

    def _check_level_progression(self) -> None:
        if self.enemies_destroyed_in_level < self.enemies_to_clear:
            return

        self.enemy_spawner.stop()
        active_hostiles = self._count_active_stage_hostiles()

        if active_hostiles > 0:
            if not self.enemy_cleanup_active:
                self.enemy_cleanup_active = True
                self.enemy_cleanup_timer = 0.0
                logger.info(
                    "🧹 Aguardando limpeza final: %d hostis ainda ativos.",
                    active_hostiles,
                )
        else:
            self.enemy_cleanup_active = False
            if self.has_boss:
                self.pre_boss_transition = True
            else:
                self._advance_to_next_level(with_delay=False)

    def _start_boss_fight(self) -> None:
        level_config = self.level_config
        assert level_config is not None

        self.pre_boss_transition = False
        self.pre_boss_timer = 0.0
        self.warning_sound_played = False
        self.warning_stage = 0
        self.warning_stage_timer = 0.0
        self.warning_timer = 0.0
        self.music_fade_started = False
        self.boss_music_started = False
        self.boss_fight_active = True
        self.screen_shake_timer = Config.BOSS_ENTRY_SHAKE_DURATION
        self.enemy_visible = True
        self.enemy_blink_timer = 0.0

        sound_manager.stop_warning()
        sound_manager.stop_all_sfx()

        if not level_config.boss_type:
            return

        from ..entities.cloud_archmage_boss import CloudArchmageBoss
        from ..entities.giant_meteor_boss import GiantMeteorBoss
        from ..entities.mountain_serpent_boss import MountainSerpentBoss
        from ..entities.stone_golem_boss import StoneGolemBoss

        if level_config.boss_type == StoneGolemBoss:
            boss = StoneGolemBoss(
                Config.SCREEN_WIDTH / 2 - 50,
                50,
                difficulty_multiplier=self.enemy_health_multiplier,
            )
            self.entity_manager.boss = boss
        elif level_config.boss_type == MountainSerpentBoss:
            # spawn_mountain_serpent_boss cria a cabeça E os blocos laterais
            # Não passa x/y para usar os valores padrão centrados da classe
            scaled_health = int(
                MountainSerpentBoss.DEFAULT_HEALTH * self.enemy_health_multiplier
            )
            boss = self.entity_manager.spawn_mountain_serpent_boss(
                health=scaled_health,
                block_health_multiplier=self.enemy_health_multiplier,
            )
        elif level_config.boss_type == GiantMeteorBoss:
            # spawn_giant_meteor_boss seta is_side_scroll corretamente
            boss = self.entity_manager.spawn_giant_meteor_boss()
            boss.health = int(boss.health * self.enemy_health_multiplier)
            boss.max_health = boss.health
        elif level_config.boss_type == CloudArchmageBoss:
            # Archmage precisa do pace interno (intervalo de estalagmites/fire
            # zones + cap de zonas ativas), não só HP escalado — sem isso a
            # phase 3 fica idêntica em Casual e Pesadelo.
            boss = CloudArchmageBoss(
                difficulty_multiplier=self.enemy_health_multiplier,
            )
            self.entity_manager.boss = boss
        else:
            boss = level_config.boss_type(Config.SCREEN_WIDTH / 2 - 50, 50)
            boss.health = int(boss.health * self.enemy_health_multiplier)
            boss.max_health = boss.health
            self.entity_manager.boss = boss

        self._cache_boss_type()

        _boss_music_map = {
            "spike": MusicState.SPIKE_BOSS,
            "slime": MusicState.SLIME_BOSS,
            "giant_meteor": MusicState.GIANT_METEOR_BOSS,
            "mountain_serpent": MusicState.MOUNTAIN_SERPENT_BOSS,
            "archmage": MusicState.CLOUD_ARCHMAGE_BOSS,
        }
        boss_type = self._boss_type_cache or "normal"
        boss_music_state = getattr(type(boss), "MUSIC_STATE", None)
        if boss_music_state is None:
            boss_music_state = _boss_music_map.get(boss_type, MusicState.BOSS)
        sound_manager.music_state_manager.transition_to(boss_music_state)
        self.boss_music_started = True

    def _explode_entities(self, entities: list[Any], size: int = 15) -> None:
        """Cria explosões para uma lista de entidades e as remove."""
        for entity in entities:
            cx = float(getattr(entity, "x", 0.0)) + getattr(entity, "w", 0) / 2
            cy = float(getattr(entity, "y", 0.0)) + getattr(entity, "h", 0) / 2
            self.entity_manager.spawn_explosion(cx, cy, size=size)

    def _end_boss_fight(self) -> None:
        from ..entities.giant_meteor_boss import GiantMeteorBoss
        from ..entities.mountain_serpent_boss import MountainSerpentBoss

        boss = self.entity_manager.boss
        if not boss:
            return

        if isinstance(boss, MountainSerpentBoss):
            boss_center = (boss.head_x, boss.head_y)
        else:
            boss_center = (boss.x + boss.w / 2, boss.y + boss.h / 2)
        self.screen_shake_timer = Config.SCREEN_SHAKE_BOSS_DEATH_DURATION
        self.screen_shake_intensity = Config.SCREEN_SHAKE_BOSS_DEATH
        sound_manager.play_explosion_boss()

        # Explosões em anel
        num_exp = Config.BOSS_EXPLOSION_COUNT
        radius = Config.BOSS_EXPLOSION_RADIUS
        for i in range(num_exp):
            angle = math.radians((360 / num_exp) * i)
            ex = boss_center[0] + radius * math.cos(angle)
            ey = boss_center[1] + radius * math.sin(angle)
            self.entity_manager.spawn_explosion(
                ex, ey, size=Config.BOSS_EXPLOSION_SMALL_SIZE
            )

        self.entity_manager.spawn_explosion(
            boss_center[0], boss_center[1], size=Config.BOSS_EXPLOSION_LARGE_SIZE
        )

        # Limpar spikes com explosões
        for spike in self.entity_manager.spikes:
            if spike.state != "respawning":
                self.entity_manager.spawn_explosion(
                    spike.center_x, spike.center_y, size=15
                )
        self.entity_manager.spikes.clear()

        # Para GiantMeteorBoss: destruir meteoros ativos
        if isinstance(boss, GiantMeteorBoss):
            for meteor in self.entity_manager.meteor_pool.active:
                self.entity_manager.spawn_explosion(
                    meteor.x + meteor.w / 2,
                    meteor.y + meteor.h / 2,
                    size=max(12, int(meteor.w // 2)),
                )
            self.entity_manager.meteor_pool.clear_active()

        # Limpar inimigos e formações restantes
        self._explode_entities(list(self.entity_manager.enemies))
        self.entity_manager.enemies.clear()

        for formation in self.entity_manager.formations:
            self._explode_entities(list(formation.enemies))
            formation.dead = True
        self.entity_manager.formations.clear()

        self.entity_manager.boss = None
        self.boss_fight_active = False
        self._boss_type_cache = None

        boss_score = Config.BOSS_DEFEAT_SCORE
        if self.score_multiplier_active:
            boss_score = int(boss_score * self.score_multiplier_value)
        self.score += boss_score

        self.music_fade_started = False
        self.boss_music_started = False
        sound_manager.music_state_manager.transition_to(MusicState.GAME)

        current_level_number = self.current_level_index + 1
        if current_level_number == self.current_world.boss_level:
            self.player_profile.unlock_next_world(self.current_world.world_id)

        self._advance_to_next_level()

    def _advance_to_next_level(self, with_delay: bool = True) -> None:
        if self.level_start_time is not None:
            clear_time = time.time() - self.level_start_time
            self.player_profile.record_clear(
                level_number=self.current_level_index + 1,
                time_taken=clear_time,
                score=self.score - self.level_start_score,
                enemies_killed=self.total_enemies_destroyed,
                damage_taken=self.level_damage_taken,
                powerups_collected=self.level_powerups_collected,
            )

        if with_delay:
            if self.transition_phase == TransitionPhase.PLAYING:
                self._set_transition_phase(TransitionPhase.POST_VICTORY_DELAY)
        else:
            self._start_next_level()

    def _start_next_level(self) -> None:
        self.player_profile.set_checkpoint_on_level_start(self.current_level_index + 1)
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
        self.current_level_index += 1

        self.level_config = self._get_adjusted_level_config(
            self.current_level_index + 1
        )

        new_world = get_world_for_level(self.current_level_index + 1)
        theme_changed = new_world.theme != self.current_world.theme

        if theme_changed:
            self.pending_world_transition = new_world
        else:
            self.current_world = new_world
            self.pending_world_transition = None

        self._cache_level_thresholds()
        self._base_score_multiplier = (
            self.level_config.score_multiplier
            * self.difficulty_settings["rewards_multiplier"]
        )

        # Avanço dentro do mesmo mundo (sem theme change) atualiza só o
        # progress visual; troca de tema delega para _apply_world_theme
        # após a cutscene de transição.
        if not theme_changed:
            self._apply_mountains_progress()

        self.enemy_spawner.set_level(self.current_level_index + 1, is_world_transition=theme_changed, level_config=self.level_config)
        self.enemies_destroyed_in_level = 0
        self.level_start_time = None
        self.level_start_score = 0
        self.level_damage_taken = 0
        self.level_powerups_collected = 0
        self.level_attempt_recorded = False

        # Reset do sistema de limpeza
        self.enemy_cleanup_active = False
        self.enemy_cleanup_timer = 0.0
        self.enemy_blink_timer = 0.0
        self.enemy_visible = True

        self.entity_manager.clear_for_level_transition()

        # Restaura mini-naves após a limpeza:
        #  - Powerup `mini_ships` ainda ativo → recria o par temporário (left+right).
        #  - Senão → restaura as permanentes do Engenheiro (se a nave tiver).
        if self.ship.mini_ships_timer > 0.0:
            self._build_mini_ships()
        else:
            self._build_permanent_mini_ships()

        if theme_changed:
            self._start_world_transition_cutscene(new_world)
        else:
            self._begin_playing_state()

    # ------------------------------------------------------------------
    # Eventos de entrada
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                from .paused import PausedScene

                self.app.states.push(PausedScene(self.app, previous_scene=self))
            elif event.key == pygame.K_F3:
                self.show_fps = not self.show_fps
                logger.info(
                    "Debug FPS: %s", "ATIVADO" if self.show_fps else "DESATIVADO"
                )
            elif event.key == pygame.K_F7:
                self.show_enemy_hitboxes = not self.show_enemy_hitboxes
                logger.info(
                    "Debug Hitbox: %s",
                    "ATIVADO" if self.show_enemy_hitboxes else "DESATIVADO",
                )
            elif event.key == pygame.K_F8:
                self._trigger_world_transition_debug_preview()
            elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                if not self.ship.is_entering and self._can_handle_gameplay_actions():
                    self.ship.cycle_facing()
            elif event.key in (pygame.K_q, pygame.K_e):
                # Cofre: Q usa slot 0, E usa slot 1.
                if not self.ship.is_entering and self._can_handle_gameplay_actions():
                    slot = 0 if event.key == pygame.K_q else 1
                    self._activate_stored_powerup(slot)
            elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                # Fantasma: dash com i-frames.
                if (
                    not self.ship.is_entering
                    and self._can_handle_gameplay_actions()
                    and self.ship.profile.has_dash
                ):
                    held = self.app.input.poll_held()
                    move_vec = pygame.math.Vector2(0, 0)
                    if "hold_left" in held:
                        move_vec.x -= 1
                    if "hold_right" in held:
                        move_vec.x += 1
                    if "hold_up" in held:
                        move_vec.y -= 1
                    if "hold_down" in held:
                        move_vec.y += 1
                    self.ship.try_dash(move_vec)
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if not self.ship.is_entering and self._can_handle_gameplay_actions():
                    if self.ship.profile.has_charge_shot and (
                        event.mod & pygame.KMOD_ALT
                    ):
                        # Só ativa charge com Space + Alt pressionados juntos.
                        self.ship.start_charge()

            self._process_cheat_input(event)

            if self._can_handle_gameplay_actions() and not self.ship.is_entering:
                self._handle_upgrade_key(event)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if not self.ship.is_entering and self._can_handle_gameplay_actions():
                    if (
                        self.ship.profile.has_charge_shot
                        and not self.ship.charge_shot_active
                        and pygame.key.get_mods() & pygame.KMOD_ALT
                    ):
                        # Botão esquerdo + Alt: inicia charge (espelho do Space+Alt).
                        self.ship.start_charge()
                    elif not self.ship.auto_fire and self.shoot_cd == 0.0:
                        self._fire_bullets()
            elif event.button == 2:
                if not self.ship.is_entering and self._can_handle_gameplay_actions():
                    self.ship.cycle_facing()
            elif event.button == 3:
                # Botão direito: inicia charge no Caçador/Magneto.
                if (
                    not self.ship.is_entering
                    and self._can_handle_gameplay_actions()
                    and self.ship.profile.has_charge_shot
                    and not self.ship.charge_shot_active
                ):
                    self.ship.start_charge()

        elif event.type == pygame.MOUSEBUTTONUP:
            # Caçador/Magneto: soltar botão esquerdo ou direito dispara o charge.
            if (
                event.button in (1, 3)
                and self.ship.profile.has_charge_shot
                and self.ship.charge_shot_active
                and not self.ship.is_entering
                and self._can_handle_gameplay_actions()
            ):
                if self.ship.charge_shot_progress >= 1.0:
                    self._fire_bullets()
                else:
                    self.ship.cancel_charge()

        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if (
                    self.ship.profile.has_charge_shot
                    and self.ship.charge_shot_active
                    and not self.ship.is_entering
                    and self._can_handle_gameplay_actions()
                ):
                    if self.ship.charge_shot_progress >= 1.0:
                        self._fire_bullets()
                    else:
                        self.ship.cancel_charge()

        elif event.type == pygame.JOYBUTTONDOWN:
            self._handle_gamepad_button(event.button)
        elif event.type == pygame.JOYHATMOTION:
            self._handle_gamepad_hat(event.value)
        elif event.type == pygame.JOYAXISMOTION:
            self._handle_gamepad_axis(event.axis, event.value)

    # ------------------------------------------------------------------
    # Mapeamento de botões do controle Xbox para ações de gameplay
    # ------------------------------------------------------------------

    def _handle_gamepad_button(self, button: int) -> None:
        from ..core.gamepad import XboxButton

        # Start sempre abre pausa, mesmo se a nave está entrando ou em modo de seleção.
        if button == XboxButton.START:
            self._upgrade_select_mode = False
            from .paused import PausedScene

            self.app.states.push(PausedScene(self.app, previous_scene=self))
            return

        if self.ship.is_entering or not self._can_handle_gameplay_actions():
            return

        # Modo de seleção de upgrade: LB/RB navegam, A confirma, B cancela.
        # Outros botões ficam inativos até sair do modo para evitar inputs
        # acidentais enquanto o jogador escolhe.
        if self._upgrade_select_mode:
            if button == XboxButton.A:
                self._confirm_upgrade_select()
            elif button == XboxButton.B:
                self._upgrade_select_mode = False
            elif button == XboxButton.LB:
                # HUD desenha os slots da direita pra esquerda (slot 0 = mais à
                # direita, slot N = mais à esquerda), então LB precisa ANDAR pra
                # frente no índice pra ir visualmente pra esquerda.
                self._navigate_upgrade_select(+1)
            elif button == XboxButton.RB:
                self._navigate_upgrade_select(-1)
            return

        # O tiro normal saiu dos botões e foi para o RT (gatilho direito):
        # ``hold_shoot`` em ``_poll_held_gamepad`` é o único caminho, então
        # ``button == XboxButton.A`` fora do modo de seleção fica livre para
        # outro propósito (Cofre E). Habilidades especiais (dash, charge shot
        # do Caçador, laser do Magneto) ficam no LT analógico, tratadas em
        # ``_handle_gamepad_axis`` baseado no perfil da nave.
        if button == XboxButton.A:
            self._activate_stored_powerup(1)  # Cofre E (era R3 antes)
        elif button == XboxButton.X:
            self.ship.cycle_facing()
        elif button == XboxButton.Y:
            self._activate_stored_powerup(0)  # Cofre Q
        # LB/RB fora do modo de seleção não fazem nada — esses botões só
        # ganham função quando o modo está aberto (navegar entre slots).
        # L3/R3 ficam livres por requisito do usuário: ``configurações dos
        # analógicos RS e LS removidas``. O Cofre E migrou de R3 para A.

    def _handle_gamepad_hat(self, value: tuple[int, int]) -> None:
        """D-pad ↑ alterna o modo de seleção de upgrades.

        Outras direções do D-pad ficam reservadas para o próprio modo (não
        executam ação fora dele — usar LB/RB para navegar dentro do modo).
        """
        if self.ship.is_entering or not self._can_handle_gameplay_actions():
            return
        _x, y = value
        if y > 0:
            self._toggle_upgrade_select_mode()

    # ------------------------------------------------------------------
    # Modo de seleção de upgrade via controle
    # ------------------------------------------------------------------

    def _toggle_upgrade_select_mode(self) -> None:
        """Liga/desliga o modo de seleção. Ao ligar, alinha o cursor para um
        slot válido, priorizando upgrades fora de cooldown."""
        if self._upgrade_select_mode:
            self._upgrade_select_mode = False
            return
        if not any(s is not None for s in self.upgrade_slots):
            return  # Sem upgrades equipados — nada para selecionar.
        self._upgrade_select_mode = True
        self._snap_upgrade_select_to_valid()

    def _upgrade_slot_is_ready(self, upg: ActiveUpgrade | None) -> bool:
        if upg is None:
            return False
        return upg.cooldown_left <= 0.0

    def _get_upgrade_select_order(self) -> list[int]:
        """Retorna índices de slots com upgrades prontos primeiro."""
        ready_slots = [
            i
            for i, upg in enumerate(self.upgrade_slots)
            if self._upgrade_slot_is_ready(upg)
        ]
        cooling_slots = [
            i
            for i, upg in enumerate(self.upgrade_slots)
            if upg is not None and not self._upgrade_slot_is_ready(upg)
        ]
        return ready_slots + cooling_slots

    def _snap_upgrade_select_to_valid(self) -> None:
        """Garante que ``_upgrade_select_index`` priorize um upgrade pronto."""
        ordered_slots = self._get_upgrade_select_order()
        if not ordered_slots:
            return
        self._upgrade_select_index = ordered_slots[0]

    def _navigate_upgrade_select(self, delta: int) -> None:
        """Move o cursor entre upgrades ocupados, priorizando os prontos."""
        ordered_slots = self._get_upgrade_select_order()
        if not ordered_slots:
            return
        try:
            current_pos = ordered_slots.index(self._upgrade_select_index)
        except ValueError:
            self._upgrade_select_index = ordered_slots[0]
            return

        next_pos = (current_pos + delta) % len(ordered_slots)
        self._upgrade_select_index = ordered_slots[next_pos]

    def _confirm_upgrade_select(self) -> None:
        """Ativa o slot atualmente destacado e sai do modo."""
        idx = self._upgrade_select_index
        self._upgrade_select_mode = False
        if 0 <= idx < len(self.upgrade_slots) and self.upgrade_slots[idx] is not None:
            self._activate_upgrade_slot(idx)

    def _handle_gamepad_axis(self, axis: int, value: float) -> None:
        """LT analógico é o botão único de habilidade especial.

        - Naves com ``has_dash`` (Fantasma): aperto do LT executa dash na
          direção atual do stick esquerdo.
        - Naves com ``has_charge_shot`` (Caçador, Magneto): segurar o LT
          carrega o tiro; soltar com a carga cheia dispara o laser/teleguiado,
          soltar antes cancela.

        Caso ambos os perfis coexistam (não acontece hoje), dash tem
        prioridade no aperto e o charge segue em paralelo.
        """
        from ..core.gamepad import GamepadManager

        # Layout é detectado em runtime no GamepadManager — pode não ser axis 2
        # em controles PS4-like. Usar o índice do manager garante que dash/charge
        # sai do gatilho físico correto.
        if axis != self.app.gamepad.axis_lt:
            return
        # Defesa adicional contra falsa detecção: só confiamos como gatilho
        # depois de ver pelo menos um evento abaixo de -0.5 (estado solto).
        if value <= -0.5:
            self._lt_calibrated = True
        if not self._lt_calibrated:
            return
        normalized = (value + 1.0) * 0.5
        pressed = normalized > GamepadManager.TRIGGER_THRESHOLD
        if pressed == self._lt_pressed:
            return
        self._lt_pressed = pressed

        if self.ship.is_entering or not self._can_handle_gameplay_actions():
            return

        profile = self.ship.profile

        # Dash dispara no instante do press, sem segurar.
        if pressed and profile.has_dash:
            move_vec = self._gamepad_dash_vector()
            self.ship.try_dash(move_vec)

        # Charge shot precisa de hold/release.
        if profile.has_charge_shot:
            if pressed and not self.ship.charge_shot_active:
                self.ship.start_charge()
            elif not pressed and self.ship.charge_shot_active:
                if self.ship.charge_shot_progress >= 1.0:
                    self._fire_bullets()
                else:
                    self.ship.cancel_charge()

    def _gamepad_dash_vector(self) -> pygame.math.Vector2:
        """Direção do dash via stick esquerdo (fallback para hold actions)."""
        gx, gy = self.app.input.gamepad_movement_vector(self.app.gamepad)
        if gx != 0.0 or gy != 0.0:
            vec = pygame.math.Vector2(gx, gy)
            if vec.length() > 0:
                vec.normalize_ip()
            return vec
        # Fallback: usa o WASD se o usuário estiver com teclado em paralelo.
        held = self.app.input.poll_held(self.app.gamepad)
        move_vec = pygame.math.Vector2(0, 0)
        if "hold_left" in held:
            move_vec.x -= 1
        if "hold_right" in held:
            move_vec.x += 1
        if "hold_up" in held:
            move_vec.y -= 1
        if "hold_down" in held:
            move_vec.y += 1
        return move_vec

    def _activate_stored_powerup(self, slot_index: int) -> None:
        """Consome o powerup do slot indicado e aplica seu efeito (Cofre)."""
        if not self.ship.has_storage_slots():
            return
        kind = self.ship.consume_stored_powerup(slot_index)
        if kind is None:
            return
        sound_manager.play_powerup()
        self._apply_powerup(kind)

    def _handle_upgrade_key(self, event: pygame.event.Event) -> None:
        """Ativa o slot de upgrade correspondente à tecla pressionada."""
        try:
            keybinds = self.player_profile.upgrade_keybindings
            for i, keycode in enumerate(keybinds[:UPGRADE_SLOT_COUNT]):
                if event.key == keycode:
                    self._activate_upgrade_slot(i)
                    return
        except (AttributeError, TypeError):
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
                    return

    # ------------------------------------------------------------------
    # Debug / hitboxes
    # ------------------------------------------------------------------

    @staticmethod
    def _get_enemy_contact_hitboxes(enemy: Any) -> tuple[pygame.Rect, ...]:
        """Retorna hitboxes de contato para debug visual, com fallback para rect."""
        getter = getattr(enemy, "get_ship_contact_hitboxes", None)
        if callable(getter):
            raw_hitboxes = cast(Any, getter)()
            hitboxes = tuple(
                r
                for r in raw_hitboxes
                if isinstance(r, pygame.Rect) and r.width > 0 and r.height > 0
            )
            if hitboxes:
                return hitboxes

        enemy_rect = getattr(enemy, "rect", pygame.Rect(0, 0, 0, 0))
        if (
            isinstance(enemy_rect, pygame.Rect)
            and enemy_rect.width > 0
            and enemy_rect.height > 0
        ):
            return (enemy_rect,)
        return ()

    def _draw_enemy_hitboxes(self, surface: pygame.Surface) -> None:
        """Overlay de hitboxes (amarelo = bounding rect; vermelho = máscara pixel-perfect)."""
        enemies_in_view = self.entity_manager.enemy_spatial_grid.query(
            0, 0, Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        )
        seen: set[int] = set()
        for enemy in enemies_in_view:
            eid = id(enemy)
            if eid in seen or getattr(enemy, "dead", False):
                continue
            seen.add(eid)

            mask_getter = getattr(enemy, "get_collision_mask_data", None)
            has_mask = False
            if callable(mask_getter):
                raw = cast(
                    "tuple[pygame.mask.Mask, tuple[int, int]] | None",
                    mask_getter(),
                )
                if raw is not None:
                    mask, offset = raw
                    mask_w, mask_h = mask.get_size()
                    if mask_w > 0 and mask_h > 0:
                        outline_surf = pygame.Surface((mask_w, mask_h), pygame.SRCALPHA)
                        for px, py in mask.outline():
                            pygame.draw.circle(
                                outline_surf, (255, 200, 40, 220), (px, py), 1
                            )
                        surface.blit(outline_surf, offset)
                        has_mask = True

            if not has_mask and not callable(
                getattr(enemy, "get_collision_mask_data", None)
            ):
                for idx, rect in enumerate(self._get_enemy_contact_hitboxes(enemy)):
                    color = (255, 200, 40) if idx == 0 else (40, 220, 255)
                    pygame.draw.rect(surface, color, rect, 2)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _compute_shake_offset(self) -> tuple[int, int]:
        """Retorna o deslocamento de screen-shake para o frame atual."""
        if self.screen_shake_timer <= 0:
            return (0, 0)
        intensity = self.screen_shake_intensity
        return (
            random.randint(-intensity, intensity),
            random.randint(-intensity, intensity),
        )

    def render(self, surface: pygame.Surface) -> None:
        dt = self.last_dt
        speed_multiplier = 1.0
        boss_active = False

        if self.state == GameState.PREPARING:
            progress = min(
                1.0,
                max(
                    0.0,
                    (Config.PREPARATION_TIME - self.preparation_time_left)
                    / Config.PREPARATION_TIME,
                ),
            )
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

        current_fps = self.r.current_fps if self.r.current_fps > 0 else 60.0
        intro_active = bool(
            self.entity_manager.boss
            and getattr(self.entity_manager.boss, "is_intro_active", False)
        )
        self.entity_manager.draw(
            self.game_surface,
            self.ship.rect.centerx,
            self.ship.rect.centery,
            self.enemy_visible,
            fps=current_fps,
            draw_boss=not intro_active,
        )

        if self.show_enemy_hitboxes:
            self._draw_enemy_hitboxes(self.game_surface)

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

        if intro_active:
            boss = self.entity_manager.boss
            if boss:
                from ..entities.cloud_archmage_boss import CloudArchmageBoss

                archmage = cast(CloudArchmageBoss, boss)
                overlay_alpha = archmage.get_intro_dim_alpha()
                if overlay_alpha > 0:
                    overlay = pygame.Surface(
                        (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
                    )
                    overlay.fill((0, 0, 0, overlay_alpha))
                    self.game_surface.blit(overlay, (0, 0))
                archmage.draw(self.game_surface)

        self.r.update_fps(dt)

        level_config = self.level_config
        assert level_config is not None
        stage_name = format_stage_name(level_config.level_number)
        self.r.hud(
            self.game_surface,
            self.score,
            self.lives,
            self.total_enemies_destroyed,
            self.ship,
            stage_name,
            self.difficulty_preset,
            score_multiplier_active=self.score_multiplier_active,
            score_multiplier_timer=self.score_multiplier_timer,
            mini_ships_active=self.ship.mini_ships_timer > 0,
            mini_ships_timer=self.ship.mini_ships_timer,
            explosive_shots_active=self.ship.explosive_shots_active,
            explosive_shots_remaining=self.ship.explosive_shots_remaining,
        )

        self._render_upgrades_hud(self.game_surface)
        self._render_storage_slots_hud(self.game_surface)
        self._render_combo_hud(self.game_surface)

        if self.show_fps:
            fps_stats = self.r.get_fps_stats()
            fps_text = (
                f"FPS: {fps_stats['fps']:.1f} | "
                f"Avg: {fps_stats['avg_frame_time']:.1f}ms | "
                f"Max: {fps_stats['max_frame_time']:.1f}ms"
            )
            fps_surface = self.r.font_small.render(fps_text, True, colors.YELLOW)
            self.game_surface.blit(fps_surface, (10, Config.SCREEN_HEIGHT - 30))

        if self.show_enemy_hitboxes:
            hitbox_text = self.r.font_small.render(
                "F7 Hitbox Debug: ON", True, (255, 200, 40)
            )
            self.game_surface.blit(hitbox_text, (10, Config.SCREEN_HEIGHT - 50))

        surface.blit(self.game_surface, self._compute_shake_offset())

        if self.warning_timer > 0 and int(self.warning_timer * 5) % 2 == 1:
            warning_text = self.warning_font.render("WARNING!", True, colors.RED)
            text_rect = warning_text.get_rect(
                center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2)
            )
            surface.blit(warning_text, text_rect)

        if self.state == GameState.PREPARING:
            self.r.preparation(surface, self.preparation_time_left)

        if self.start_fade_active:
            self.start_fade_overlay.fill((0, 0, 0, int(self.start_fade_alpha)))
            surface.blit(self.start_fade_overlay, (0, 0))

    # ===================== Upgrades (helpers) =====================

    def _init_upgrades_from_profile(self) -> None:
        self.upgrade_slots: list[ActiveUpgrade | None] = []
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

    def _build_upgrade_ctx(self) -> UpgradeContext:
        """Constrói o contexto tipado para upgrades."""
        return UpgradeContext(
            ship=self.ship,
            entity_manager=self.entity_manager,
            difficulty_settings=self.difficulty_settings,
            sound_manager=sound_manager,
            scene=self,
            god_mode=self.god_mode,
            permadeath_mode=self._permadeath_mode,
        )

    def _update_upgrades(self, dt: float) -> None:
        if not self.upgrade_slots:
            return
        ctx = self._build_upgrade_ctx()
        for upg in self.upgrade_slots:
            if upg is not None:
                upg.update(dt, ctx)

    def _sync_lives(self, lives: int) -> None:
        self.lives = max(0, lives)
        self.ship.lives = self.lives

    def _change_lives(self, delta: int) -> None:
        self._sync_lives(self.lives + delta)

    def _apply_cooldown_reduction(self, reduction: float) -> None:
        """Reduz instantaneamente o cooldown de todos os upgrades ativos."""
        for upg in self.upgrade_slots:
            if upg is not None and upg.cooldown_left > 0:
                upg.cooldown_left = max(0.0, upg.cooldown_left - reduction)

    def _apply_god_mode_cooldowns(self) -> None:
        """Reduz todos os cooldowns ativos para 1 segundo ao ativar god mode."""
        for upg in self.upgrade_slots:
            if upg is not None and upg.cooldown_left > 0:
                upg.cooldown_left = min(upg.cooldown_left, 1.0)

    def _activate_upgrade_slot(self, idx: int) -> None:
        if not 0 <= idx < len(self.upgrade_slots):
            return
        upg = self.upgrade_slots[idx]
        if upg is None:
            return
        ctx = self._build_upgrade_ctx()
        try:
            upg.activate(ctx)
            if isinstance(upg, HealUpgrade):
                self.app.heal_usage_count = upg.usage_count
        except (AttributeError, TypeError):
            pass

    def _render_combo_hud(self, surface: pygame.Surface) -> None:
        """Indicador do combo do Reverberador (canto inferior esquerdo).

        Mostra contagem de abates consecutivos sem dano e bônus de dano resultante.
        Só aparece para naves com `combo_damage_per_kill > 0`.
        """
        if self.ship.profile.combo_damage_per_kill <= 0:
            return

        from ..core import colors as _colors

        kills = self.ship.combo_kills
        bonus = self.ship.combo_damage_bonus
        cap = self.ship.profile.combo_damage_cap

        font_label = get_font(14)
        font_value = get_font(22)

        # Cores: cinza se sem combo, dourado em escala conforme se aproxima do cap.
        if kills == 0:
            color = (160, 160, 160)
        elif 0 < cap <= bonus:
            # Cap atingido: pulso amarelo brilhante.
            pulse = int(40 + 40 * abs(math.sin(time.time() * 6)))
            color = (255, 220 - pulse // 4, 60)
        else:
            fade = min(1.0, bonus / cap) if cap > 0 else min(1.0, bonus)
            color = (
                int(180 + 75 * fade),
                int(180 + 40 * fade),
                int(140 - 80 * fade),
            )

        x = 16
        y = Config.SCREEN_HEIGHT - 70

        label = font_label.render("COMBO", True, _colors.WHITE)
        surface.blit(label, (x, y))

        bonus_pct = int(round(bonus * 100))
        text = font_value.render(f"x{kills}  +{bonus_pct}%", True, color)
        surface.blit(text, (x, y + 16))

    def _render_storage_slots_hud(self, surface: pygame.Surface) -> None:
        """Desenha as caixas dos slots de powerup do Cofre (estilo Mario World).

        Cada slot mostra o ícone colorido do powerup armazenado, espelhando a
        aparência do PowerUp coletável (círculo colorido + símbolo).
        """
        if not self.ship.has_storage_slots():
            return

        from ..core import colors as _colors
        from ..core.colors import (
            POWERUP_COOLDOWN_HASTE,
            POWERUP_DAMAGE_BOOST,
            POWERUP_DOUBLE_SHOT,
            POWERUP_LIFE,
            POWERUP_MINI_SHIPS,
            POWERUP_PIERCING_SHOT,
            POWERUP_RAINBOW,
            POWERUP_SCORE,
            POWERUP_SHIELD,
            POWERUP_SPEED,
            POWERUP_TIME_STOP,
        )

        font_label = get_font(20)
        font_hint = get_font(12)
        font_icon = get_font(18)

        slot_size = 56
        gap = 12
        slots = self.ship.stored_powerups
        total_w = len(slots) * slot_size + (len(slots) - 1) * gap

        start_x = (Config.SCREEN_WIDTH - total_w) // 2
        y = 8

        # Cor e símbolo de cada powerup — alinhados com PowerUp.draw.
        powerup_colors: dict[str, tuple[int, int, int]] = {
            "life": POWERUP_LIFE,
            "shield": POWERUP_SHIELD,
            "double_shot": POWERUP_DOUBLE_SHOT,
            "speed": POWERUP_SPEED,
            "score": POWERUP_SCORE,
            "piercing_shot": POWERUP_PIERCING_SHOT,
            "mini_ships": POWERUP_MINI_SHIPS,
            "rainbow": POWERUP_RAINBOW,
            "cooldown_haste": POWERUP_COOLDOWN_HASTE,
            "time_stop": POWERUP_TIME_STOP,
            "damage_boost": POWERUP_DAMAGE_BOOST,
            "chain_shot": (80, 220, 255),
            "repulsion_shield": (100, 255, 80),
        }
        powerup_symbols: dict[str, str] = {
            "life": "+",
            "shield": "S",
            "double_shot": "2X",
            "speed": "V",
            "score": "$",
            "piercing_shot": "P",
            "mini_ships": "M",
            "rainbow": "*",
            "cooldown_haste": "CD",
            "time_stop": "T",
            "damage_boost": "DMG",
            "chain_shot": "⚡",
            "repulsion_shield": "🛡",
        }
        hint_keys = ("Q", "E")

        for i, kind in enumerate(slots):
            x = start_x + i * (slot_size + gap)
            slot_surface = pygame.Surface((slot_size, slot_size), pygame.SRCALPHA)

            # Fundo escuro semi-transparente
            pygame.draw.rect(
                slot_surface,
                (20, 20, 30, 200),
                (0, 0, slot_size, slot_size),
                border_radius=8,
            )
            # Borda amarela (cheia) ou cinza (vazia)
            border_color = (
                (*_colors.YELLOW, 230) if kind is not None else (*_colors.GRAY, 160)
            )
            pygame.draw.rect(
                slot_surface,
                border_color,
                (0, 0, slot_size, slot_size),
                2,
                border_radius=8,
            )

            # Letra de tecla no canto superior esquerdo
            key_label = hint_keys[i] if i < len(hint_keys) else str(i + 1)
            slot_surface.blit(font_hint.render(key_label, True, _colors.WHITE), (5, 3))

            if kind is not None:
                # Círculo colorido com a cor do powerup (mesma usada no drop).
                color = powerup_colors.get(kind, (200, 200, 200))
                center = (slot_size // 2, slot_size // 2 + 4)
                pygame.draw.circle(slot_surface, color, center, 16)
                pygame.draw.circle(slot_surface, _colors.WHITE, center, 16, 2)
                # Símbolo central
                symbol = powerup_symbols.get(kind, kind[:2].upper())
                content = font_icon.render(symbol, True, _colors.BLACK)
                slot_surface.blit(content, content.get_rect(center=center))
            else:
                # Slot vazio: traço discreto
                dash = font_label.render("—", True, (90, 90, 90))
                slot_surface.blit(
                    dash, dash.get_rect(center=(slot_size // 2, slot_size // 2))
                )

            surface.blit(slot_surface, (x, y))

    def _render_upgrades_hud(self, surface: pygame.Surface) -> None:
        from ..core import colors as _colors

        active_slots = [
            (i, upg) for i, upg in enumerate(self.upgrade_slots) if upg is not None
        ]
        if not active_slots:
            return

        font = get_font(20)
        font_small = get_font(12)
        pad = 8
        slot_w = slot_h = _HUD_UPGRADE_SLOT_SIZE
        x = Config.SCREEN_WIDTH - pad - slot_w
        y = 44

        for display_index, (i, upg) in enumerate(active_slots):
            slot_surface = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)

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

            try:
                keycode = self.player_profile.upgrade_keybindings[i]
                key_label = pygame.key.name(keycode).upper()
            except (AttributeError, IndexError, TypeError):
                key_label = str(i + 1)
            slot_surface.blit(font_small.render(key_label, True, _colors.WHITE), (4, 2))

            ui = upg.get_ui_state()  # type: ignore[attr-defined]
            name_str = str(ui.get("name", ""))
            icon_id = str(ui.get("icon_id", "")) if ui.get("icon_id") else None
            icon = get_upgrade_icon(name_str, icon_id)
            icon_txt = font.render(icon, True, _colors.CYAN)
            slot_surface.blit(
                icon_txt, icon_txt.get_rect(center=(slot_w // 2, slot_h // 2))
            )

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

            charges = ui.get("charges_left")
            if charges is not None:
                c_txt = font_small.render(f"{charges}", True, _colors.WHITE)
                c_rect = c_txt.get_rect()
                c_rect.bottomright = (slot_w - 3, slot_h - 3)
                slot_surface.blit(c_txt, c_rect)

            slot_x = x - display_index * (slot_w + _HUD_UPGRADE_SLOT_GAP)
            surface.blit(slot_surface, (slot_x, y))

            if ui["active"]:
                pygame.draw.rect(
                    surface,
                    _colors.GREEN,
                    pygame.Rect(slot_x, y, slot_w, slot_h),
                    3,
                    border_radius=8,
                )

            # Destaque dourado vibrando quando o slot está selecionado no
            # modo de seleção via controle (D-pad ↑ → LB/RB → A). Só a
            # MOLDURA dourada balança — o conteúdo interno (fundo do slot,
            # ícone do upgrade e label da tecla) já foi blitado acima e fica
            # estático, então o texto não treme junto.
            if self._upgrade_select_mode and i == self._upgrade_select_index:
                t = pygame.time.get_ticks()
                shake_x = int(math.sin(t / 35.0) * 2)
                shake_y = int(math.cos(t / 42.0) * 2)
                pygame.draw.rect(
                    surface,
                    _colors.CUSTOM_GOLD,
                    pygame.Rect(
                        slot_x - 3 + shake_x,
                        y - 3 + shake_y,
                        slot_w + 6,
                        slot_h + 6,
                    ),
                    3,
                    border_radius=10,
                )

        # Dica de controles quando em modo de seleção via gamepad.
        if self._upgrade_select_mode:
            hint = font_small.render(
                "LB/RB navegar  A confirmar  B cancelar",
                True,
                _colors.CUSTOM_GOLD,
            )
            hint_x = Config.SCREEN_WIDTH - pad - hint.get_width()
            hint_y = y + slot_h + 6
            surface.blit(hint, (hint_x, hint_y))