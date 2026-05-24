"""
playing.py — Cena principal de gameplay.

Melhorias aplicadas (boas práticas Python / Pygame):
  1. Constantes de módulo extraídas do __init__ para evitar "magic numbers".
  2. __init__ dividido em métodos _init_* coesos (Single Responsibility).
  3. UpgradeContext substituído por dataclass tipada (elimina `type(..., (), ...)(...)`).
  4. build_mini_ships() elimina duplicação em _process_powerups_and_stars.
  5. _apply_powerup() com dict-dispatch substitui cadeia de elif crescente.
  6. Progressão de nível extraída em LevelProgressionController.
  7. Boss fight extraído em BossFightController (systems/boss_fight_controller.py).
  8. _compute_shake_offset() encapsula lógica de screen-shake.
  9. Sistema de tiro extraído em ShootingSystem (systems/shooting_system.py).
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
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional, Sequence, TypedDict, cast

import pygame

from ..core.assets import get_font
from ..core.config import SlimeBossState
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.levels import LevelConfig, LevelManager, get_level_config
from ..core.meta_progression_service import MetaProgressionService
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..core.state import Scene
from ..core.upgrades import ActiveUpgrade, HealUpgrade, create_upgrade
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from ..core.world_config import (
    WorldConfig,
    format_stage_name,
    get_world_for_level,
    is_side_scroll_mode,
)
from ..entities.mini_ship import MiniShip
from ..entities.revival_beacon import RevivalBeacon
from ..entities.ship import Ship
from ..entities.spike_boss_laser import SpikeBossLaser
from ..events import game_events as events
from ..render.game_renderer import GameRenderer
from ..render.render_frame import P2HudInfo, RenderFrame
from ..systems.boss_fight_controller import BossFightController
from ..systems.cheat_input import CheatBuffer
from ..systems.collisions import Collisions
from ..systems.effects_system import EffectsSystem
from ..systems.entity_manager import EntityManager
from ..systems.gameplay_input_handler import GameplayInputHandler
from ..systems.level_progression_controller import (
    LevelProgressionController,
    ProgressionStatus,
)
from ..systems.player_slot import PlayerRoster, PlayerSlot
from ..systems.powerup_system import PowerupSystem
from ..systems.shooting_system import ShootingSystem
from ..systems.spawner import EnemySpawner, PowerUpSpawner, StarSpawner
from ..systems.transition_controller import TransitionController, TransitionPhase

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..app import GameApp
    from ..core.spatial_grid import SpatialGrid
    from ..systems.collision_protocols import Enemy

# ---------------------------------------------------------------------------
# Constantes de módulo (eliminam "magic numbers" espalhados pela classe)
# ---------------------------------------------------------------------------
_SIDE_SCROLL_SHIP_ENTRY_X = 100
_TOP_DOWN_SHIP_TARGET_Y_OFFSET = 80
_HUD_UPGRADE_SLOT_SIZE = 50
_HUD_UPGRADE_SLOT_GAP = 6


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------


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
        start_fade_duration: float = 0.45,
    ) -> None:
        super().__init__(app)
        self.level_manager = level_manager
        self.difficulty_preset = difficulty_preset
        self.difficulty_settings = DifficultySettings.get_settings(difficulty_preset)
        self._start_fade_duration = start_fade_duration
        self.last_dt: float = 1.0 / Config.FPS
        self.r = app.renderer

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

    @property
    def level_config(self) -> Optional[LevelConfig]:
        return self.level_controller.level_config

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
            target_x = float(_SIDE_SCROLL_SHIP_ENTRY_X)
            target_y = ship_y
        else:
            ship_x = Config.SCREEN_WIDTH / 2.0 - 20
            ship_y = float(Config.SCREEN_HEIGHT + 100)
            target_x = ship_x
            target_y = float(Config.SCREEN_HEIGHT - _TOP_DOWN_SHIP_TARGET_Y_OFFSET)

        ship_obj = Ship(
            ship_x,
            ship_y,
            mouse_control=self.app.preferences.mouse_control,
            auto_fire=self.app.preferences.auto_fire,
            profile=self.player_profile.get_selected_ship_profile(),
        )

        # Ativa animação de entrada sincronizada com o contador de preparação
        ship_obj.start_entering_animation(
            (ship_x, ship_y), (target_x, target_y), Config.PREPARATION_TIME
        )
        ship_obj.apply_world_mode(self.is_side_scroll)

        # Roster mantém slots de jogador.
        self.roster: PlayerRoster = PlayerRoster.with_primary(
            PlayerSlot(ship=ship_obj, lives=0, gamepad_slot=0)
        )

        self.first_entry: bool = True

    @property
    def ship(self) -> Ship:
        """Backward compat: nave do P1 (slot primário).

        Mantida como property para que call sites legados (`self.ship.x`,
        `self.ship.lives`, etc.) continuem funcionando enquanto a refatoração
        multiplayer é incremental. Para iterar sobre todos os jogadores ativos,
        usar `self.roster.alive_slots()`.
        """
        return self.roster.primary().ship

    def _init_game_state(self) -> None:
        """Inicializa o estado de jogo e aplica configurações de dificuldade."""
        self.cheat: CheatBuffer = CheatBuffer()
        self.powerup_system: PowerupSystem = PowerupSystem(self)
        self.input_handler: GameplayInputHandler = GameplayInputHandler(self)
        self.transitions: TransitionController = TransitionController(
            post_victory_delay=Config.LEVEL_TRANSITION_PENDING_DELAY,
            level_transition_delay=Config.LEVEL_TRANSITION_DELAY,
            animation_timeout=Config.LEVEL_TRANSITION_ANIMATION_TIMEOUT,
        )
        self.god_mode: bool = False
        self.state: GameState = GameState.PREPARING
        self.preparation_time_left: float = Config.PREPARATION_TIME
        self.upgrade_select_mode: bool = False
        self._upgrade_select_index: int = 0
        self._apply_difficulty_settings()

        self.screen_shake_timer: float = 0.0
        self.screen_shake_intensity: int = Config.SCREEN_SHAKE_NORMAL
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)

        self.time_stop_timer: float = 0.0
        self.freeze_active: bool = False

        self.show_fps: bool = False
        self.show_enemy_hitboxes: bool = False

        self._game_over_triggered: bool = False

        self.score_multiplier_timer: float = 0.0
        self.score_multiplier_active: bool = False
        self.score_multiplier_value: float = 1.5

        self.floating_score_batch_threshold: float = 60.0

        # Pop-up de início de nível (sub-fases)
        self.level_popup_text: str = ""
        self.level_popup_timer: float = 0.0
        self.level_popup_duration: float = 2.5

        self._special_rules: list[str] = self.difficulty_settings.get(
            "special_rules", []
        )
        self.no_powerups_mode: bool = "no_powerups" in self._special_rules
        self._permadeath_mode: bool = "permadeath" in self._special_rules

    def _init_transition_state(self) -> None:
        """Inicializa timers e flags de transição de nível/mundo.

        FSM e timers de fase vivem em `self.transitions` (TransitionController).
        Aqui ficam apenas os dados de cutscene (visual/animação).
        """
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
        self.start_fade_duration: float = self._start_fade_duration
        self.start_fade_overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )

    def _request_screen_shake(self, duration: float, intensity: int) -> None:
        self.screen_shake_timer = duration
        self.screen_shake_intensity = intensity

    def _get_background(self) -> Any | None:
        return getattr(self.r, "current_background", None)

    def _init_systems(self) -> None:
        """Instancia sistemas de jogo (EntityManager, spawners, colisões)."""
        player_count = len(self.roster.all_slots())
        initial_level_number = self.current_level_index + 1
        base_config = get_level_config(
            initial_level_number,
            self.difficulty_preset,
            player_count=player_count,
        )
        level_config = MetaProgressionService.get_adjusted_config(
            self.player_profile, base_config
        )
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))

        self.entity_manager = EntityManager(
            sound_manager=sound_manager,
            is_side_scroll=self.is_side_scroll,
            aggressiveness_multiplier=self.difficulty_settings.get(
                "aggressiveness_multiplier", 1.0
            ),
        )
        self._apply_world_theme()

        self.boss_controller = BossFightController(
            entity_manager=self.entity_manager,
            event_bus=self.app.event_bus,
            screen_shake_request=self._request_screen_shake,
            background_getter=self._get_background,
        )

        # Instanciar EffectsSystem que escuta eventos do jogo
        self.effects_system = EffectsSystem(
            self.app.event_bus, self.entity_manager, scene=self
        )

        self.game_renderer = GameRenderer(self.r)

        is_initial_level = self.current_level_index == 0
        self.enemy_spawner = EnemySpawner(
            self.level_manager,
            self.entity_manager.meteor_pool,
            is_initial_level,
            self.difficulty_preset,
            self.enemy_health_multiplier,
            self.difficulty_settings.get("aggressiveness_multiplier", 1.0),
            player_count=len(self.roster.all_slots()),
        )
        # Sincroniza o spawner com o starting_level — sem isto o spawner usa o
        # config do nível 1 por default, o que quebra inicializações em mundos
        # diferentes do primeiro (ex.: começar em STARFIELD via world select).
        if not is_initial_level:
            self.enemy_spawner.set_level(
                initial_level_number, level_config=level_config
            )
        self.powerup_spawner = PowerUpSpawner(
            self.difficulty_preset,
            player_count=len(self.roster.all_slots()),
        )
        self.collisions = Collisions(self.app.event_bus)
        self.star_spawner = StarSpawner()

        self.level_controller = LevelProgressionController(
            entity_manager=self.entity_manager,
            event_bus=self.app.event_bus,
            enemy_spawner=self.enemy_spawner,
            player_profile=self.player_profile,
            difficulty_preset=self.difficulty_preset,
            difficulty_settings=self.difficulty_settings,
            player_count=player_count,
        )
        self.level_controller.setup(
            level_index=self.current_level_index,
            level_config=level_config,
            current_world=self.current_world,
        )

        self.shooting = ShootingSystem(
            entity_manager=self.entity_manager,
            event_bus=self.app.event_bus,
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
        self.cheat.reset()
        self.god_mode = False
        self.state = GameState.PREPARING
        self.preparation_time_left = Config.PREPARATION_TIME

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
        self.transitions.set_phase(phase)

    @property
    def transition_phase(self) -> TransitionPhase:
        return self.transitions.phase

    @property
    def level_transition_pending(self) -> bool:
        return self.transitions.is_post_victory_delay

    @property
    def level_transition_active(self) -> bool:
        return self.transitions.is_level_transition_wait

    @property
    def world_transition_cutscene_active(self) -> bool:
        return self.transitions.is_cutscene_exit

    @world_transition_cutscene_active.setter
    def world_transition_cutscene_active(self, value: bool) -> None:
        if value:
            self.transitions.phase = TransitionPhase.CUTSCENE_EXIT
        elif self.transitions.is_cutscene_exit:
            self.transitions.phase = (
                TransitionPhase.WORLD_PANEL
                if self.pending_world_transition is not None
                else TransitionPhase.LEVEL_ENTRY
            )

    @property
    def awaiting_world_transition_panel(self) -> bool:
        return self.transitions.is_world_panel

    def can_handle_gameplay_actions(self) -> bool:
        """Retorna True quando o jogador pode agir normalmente."""
        return self.transitions.can_handle_gameplay_actions

    def _begin_level_preparation(self) -> None:
        """Coloca a cena em modo de preparação para o próximo nível."""
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
        self.state = GameState.PREPARING
        self.preparation_time_left = Config.PREPARATION_TIME
        self.level_controller.reset_level_stats()
        self._reset_ship_for_level_entry()

    def _on_level_cleared(self, with_delay: bool) -> None:
        """Sinal do LevelProgressionController: fase concluída."""
        if with_delay:
            if self.transition_phase == TransitionPhase.PLAYING:
                self._set_transition_phase(TransitionPhase.POST_VICTORY_DELAY)
        else:
            self._start_next_level()

    def _on_boss_threshold_reached(self) -> None:
        """Sinal do LevelProgressionController: threshold atingido, boss pendente."""
        self.boss_controller.enemy_cleanup_active = False
        self.boss_controller.pre_boss_transition = True

    def _on_cleanup_needed(self) -> None:
        """Sinal do LevelProgressionController: hostis ainda ativos, iniciar blink."""
        self.boss_controller.begin_cleanup()

    def _on_advance_level(self, theme_changed: bool, new_world: WorldConfig) -> None:
        """Sinal do LevelProgressionController: novo nível iniciado."""
        # Sincroniza o current_level_index da cena com o do controlador
        self.current_level_index = self.level_controller.current_level_index

        if theme_changed:
            self.pending_world_transition = new_world
        else:
            self.current_world = new_world
            self.pending_world_transition = None
            self._apply_mountains_progress()

            # Trigger pop-up de sub-fase (ex: 1-1 -> 1-2)
            level_config = self.level_config
            if level_config:
                self.level_popup_text = format_stage_name(level_config.level_number)
                self.level_popup_timer = self.level_popup_duration

        self.boss_controller.reset()
        self.entity_manager.clear_for_level_transition()

        # Em coop, cada slot pode ter perfil próprio (ex: Engenheiro como P2).
        # Itera sobre todos os slots vivos para rebuildar permanentes de cada
        # um — chamada legada sem slot só restaurava o primário, perdendo as
        # mini-naves de outros Engenheiros na transição.
        for slot in self.roster.alive_slots():
            if slot.ship.mini_ships_timer > 0.0:
                self.build_mini_ships(slot)
            else:
                self._build_permanent_mini_ships(slot)

        if theme_changed:
            self._start_world_transition_cutscene(new_world)
        else:
            self._begin_playing_state()

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
        self.level_controller.start_level_timer(self.score)
        self.level_controller.record_attempt_if_needed()

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

    def trigger_world_transition_debug_preview(self) -> None:
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
        self._init_fade()
        if self.first_entry:
            self.app.event_bus.emit(
                events.MusicStateChange(state=MusicState.GAME, fade_ms=0)
            )
            self.first_entry = False
        if self.transition_phase == TransitionPhase.WORLD_PANEL:
            self._apply_pending_world_transition()

    def exit(self) -> None:
        pygame.mouse.set_visible(True)
        if hasattr(self, "effects_system"):
            self.effects_system.cleanup()

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

        self.transitions.update_post_victory(dt)

        self._update_preparing_state(dt)
        self._update_timers(dt)
        self._update_ship(dt)
        self._update_revival_beacons(dt)
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
        """Gerencia o estado de preparação e o início da partida."""
        if self.state != GameState.PREPARING:
            return

        # O início do gameplay ocorre quando o timer atinge 0
        if self.preparation_time_left <= 0:
            self._begin_playing_state()

    def _update_timers(self, dt: float) -> None:
        self.time_stop_timer = max(0.0, self.time_stop_timer - dt)
        self.freeze_active = self.time_stop_timer > 0.0
        self.shooting.update(dt)

        # Timer de preparação (continua negativo para animação de saída)
        if self.preparation_time_left > -1.5:
            self.preparation_time_left -= dt

        # Pop-up de início de nível
        if self.level_popup_timer > 0:
            self.level_popup_timer = max(0.0, self.level_popup_timer - dt)

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

        if self.transitions.update_level_transition_wait(
            dt, self._all_animations_finished()
        ):
            self._start_next_level()

    def _update_ship(self, dt: float) -> None:
        # Atualiza apenas naves vivas — slots mortos não precisam de física,
        # invuln, ou timer de powerups (são removidos de tela até revive).
        for slot in self.roster.alive_slots():
            slot.ship.update(
                dt, self.entity_manager, is_side_scroll=self.is_side_scroll
            )

        # Powerup `mini_ships` expirou para algum slot: troca as temporárias
        # daquela nave pelas permanentes (se o profile tiver), preservando as
        # mini-naves de outros slots.
        for slot in self.roster.all_slots():
            if slot.ship.mini_ships_timer != 0.0:
                continue
            ship_minis = [
                m for m in self.entity_manager.mini_ships if m.player is slot.ship
            ]
            if not ship_minis:
                continue
            has_temps = any(not getattr(m, "permanent", False) for m in ship_minis)
            if has_temps:
                self.entity_manager.mini_ships = [
                    m
                    for m in self.entity_manager.mini_ships
                    if m.player is not slot.ship
                ]
                self._build_permanent_mini_ships(slot)

        boss_pausing = False
        if self.boss_controller.boss_type == "spike" and self.entity_manager.boss:
            from ..entities.spike_boss import SpikeBoss

            boss_pausing = cast(SpikeBoss, self.entity_manager.boss).is_pausing_game()

        if self.can_handle_gameplay_actions():
            for slot in self.roster.alive_slots():
                ship = slot.ship
                if ship.is_entering:
                    continue
                slot_idx = slot.gamepad_slot if slot.gamepad_slot is not None else 0
                held = self.app.input.poll_held_for(self.app.gamepad, slot=slot_idx)
                gamepad_vec = self.app.input.gamepad_movement_vector_for(
                    self.app.gamepad, slot=slot_idx
                )
                ship.move(
                    held,
                    dt,
                    is_side_scroll=self.is_side_scroll,
                    gamepad_vec=gamepad_vec,
                )

                # Berserk: disparo em todas as direções (Rosa dos ventos)
                if getattr(ship, "berserk_timer", 0.0) > 0.0:
                    self.shooting.fire_berserk(ship, self.player_damage_multiplier, dt)

                # Caçador: enquanto a carga está acumulando, suprime auto-fire/hold-shoot.
                # O disparo carregado sai no MOUSEBUTTONUP.
                charging = ship.profile.has_charge_shot and ship.charge_shot_active
                if (
                    ("hold_shoot" in held or ship.should_auto_fire())
                    and self.shooting.is_ready(ship)
                    and not boss_pausing
                    and ship.speed_modifier_timer <= 0.0
                    and not charging
                ):
                    self.shooting.fire(ship, self.player_damage_multiplier)

    def _apply_environmental_effects(self, dt: float) -> None:
        """Aplica efeitos ambientais (como vento) à nave do jogador."""
        if not self.can_handle_gameplay_actions() or self.ship.is_entering:
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
            not self.boss_controller.active
            and not self.boss_controller.pre_boss_transition
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

            if not self.no_powerups_mode:
                self.powerup_spawner.update(dt, self.entity_manager.powerups)

            self.star_spawner.update(self.entity_manager.stars)

    def _update_level_logic(self, dt: float) -> None:
        if self.boss_controller.active:
            if self.entity_manager.boss and self.entity_manager.boss.dead:
                self._end_boss_fight()
        elif self.boss_controller.pre_boss_transition:
            has_active = bool(self.entity_manager.enemies)
            if self.boss_controller.update_warning(dt, has_active):
                self._start_boss_fight()
        elif self.transition_phase == TransitionPhase.PLAYING:
            if self._game_over_triggered:
                return
            self.boss_controller.update_cleanup(dt)
            self._check_level_progression()

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

    def process_cheat_input(self, event: pygame.event.Event) -> None:
        """Detecta o cheat code '271195' para ativar/desativar god mode, adicionar 9999 estrelas e desbloquear todos os mundos."""
        if not self.cheat.feed(event):
            return

        self.god_mode = not self.god_mode
        if self.god_mode:
            logger.info("GOD MODE ATIVADO - Invulnerabilidade ligada!")
            self._apply_god_mode_cooldowns()
            self.player_profile.add_stars(9999)
            self.player_profile.unlock_all_worlds()
            self.player_profile.save()  # Força save imediato
            logger.info(
                "⭐ CHEAT ATIVADO - +9999 Estrelas e todos os mundos desbloqueados!"
            )
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
        for event_list in buckets.values():
            if not event_list:
                continue
            avg_x = sum(e[0] for e in event_list) / len(event_list)
            avg_y = sum(e[1] for e in event_list) / len(event_list)
            total_pts = sum(e[2] for e in event_list)
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
    ) -> tuple[int, int, list[tuple[float, float, int]], set[int]]:
        """Projéteis da nave vs. inimigos normais. Retorna (score, kills, events, ship_hits).

        `ship_hits` é um set de `id(ship)` para naves atingidas por mine/fire zones.
        """
        enemies_view = cast(Sequence["Enemy"], self.entity_manager.enemies)
        alive_ships = [slot.ship for slot in self.roster.alive_slots()]

        all_player_projectiles = (
            self.entity_manager.bullets + self.entity_manager.mini_ship_bullets
        )
        gain, destroyed, score_events = self.collisions.projectiles_vs_enemies(
            all_player_projectiles,
            enemy_grid,
            self.entity_manager,
            ship=self.ship,
        )

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

        upgrade_dt = self.last_dt
        if self.entity_manager.orbital_shields:
            os_gain, os_destroyed, os_events = (
                self.collisions.orbital_shields_vs_enemies(
                    self.entity_manager.orbital_shields,
                    enemy_grid,
                    upgrade_dt,
                    self.entity_manager,
                )
            )
            gain += os_gain
            destroyed += os_destroyed
            score_events.extend(os_events)

        if self.entity_manager.plasma_beams:
            pb_gain, pb_destroyed, pb_events = (
                self.collisions.plasma_beams_vs_enemies(
                    self.entity_manager.plasma_beams,
                    enemy_grid,
                    upgrade_dt,
                    self.entity_manager,
                )
            )
            gain += pb_gain
            destroyed += pb_destroyed
            score_events.extend(pb_events)

        if self.entity_manager.coop_links:
            cl_gain, cl_destroyed, cl_events = (
                self.collisions.coop_links_vs_enemies(
                    self.entity_manager.coop_links,
                    enemy_grid,
                    upgrade_dt,
                    self.entity_manager,
                )
            )
            gain += cl_gain
            destroyed += cl_destroyed
            score_events.extend(cl_events)

        mine_gain, mine_destroyed, mine_events, ship_hits = (
            self.collisions.check_mine_explosions(
                enemies_view,
                self.entity_manager.mine_explosions,
                alive_ships,
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
                alive_ships,
                self.entity_manager,
            )
            gain += iz_gain
            destroyed += iz_dest
            score_events.extend(iz_events)

        if self.entity_manager.fire_zones:
            fz_gain, fz_dest, fz_events, fz_ship_hits = (
                self.collisions.fire_zones_vs_entities(
                    self.entity_manager.fire_zones,
                    enemies_view,
                    alive_ships,
                    self.entity_manager,
                )
            )
            gain += fz_gain
            destroyed += fz_dest
            score_events.extend(fz_events)
            ship_hits |= fz_ship_hits

        return gain, destroyed, score_events, ship_hits

    def _check_formation_collisions(
        self, gain: int, destroyed: int, score_events: list[tuple[float, float, int]]
    ) -> tuple[int, int, list[tuple[float, float, int]], set[int]]:
        """Colisões de área vs. formações e inimigos avulsos.

        Retorna ship_hits como set de `id(ship)` para naves atingidas por
        mine/fire zones (varredura de formações e inimigos avulsos).
        """
        ship_hits: set[int] = set()
        alive_ships = [slot.ship for slot in self.roster.alive_slots()]

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

            f_gain, f_dest, f_events, f_ship_hits = (
                self.collisions.check_mine_explosions(
                    fe,
                    self.entity_manager.mine_explosions,
                    alive_ships,
                    self.entity_manager,
                )
            )
            gain += f_gain
            destroyed += f_dest
            score_events.extend(f_events)
            ship_hits |= f_ship_hits

            if self.entity_manager.ice_poison_zones:
                iz_gain, iz_dest, iz_events = (
                    self.collisions.ice_poison_zones_vs_entities(
                        self.entity_manager.ice_poison_zones,
                        fe,
                        alive_ships,
                        self.entity_manager,
                    )
                )
                gain += iz_gain
                destroyed += iz_dest
                score_events.extend(iz_events)

            if self.entity_manager.fire_zones:
                fz_gain, fz_dest, fz_events, fz_ship_hits = (
                    self.collisions.fire_zones_vs_entities(
                        self.entity_manager.fire_zones,
                        fe,
                        alive_ships,
                        self.entity_manager,
                    )
                )
                gain += fz_gain
                destroyed += fz_dest
                score_events.extend(fz_events)
                ship_hits |= fz_ship_hits

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
            fz_gain, fz_dest, fz_events, fz_ship_hits = (
                self.collisions.fire_zones_vs_entities(
                    self.entity_manager.fire_zones,
                    enemies_view,
                    alive_ships,
                    self.entity_manager,
                )
            )
            gain += fz_gain
            destroyed += fz_dest
            score_events.extend(fz_events)
            ship_hits |= fz_ship_hits

        return gain, destroyed, score_events, ship_hits

    def _check_boss_collisions(self, gain: int) -> int:
        """Todas as colisões envolvendo o boss. Retorna score_gain total."""
        score_gain = 0
        boss = self.entity_manager.boss

        if not (boss and self.boss_controller.boss_type):
            return gain

        all_player_projectiles = (
            self.entity_manager.bullets + self.entity_manager.mini_ship_bullets
        )
        score_gain = self.collisions.projectiles_vs_boss(
            all_player_projectiles,
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

        if self.boss_controller.boss_type == "slime":
            from ..entities.slime_boss import SlimeBoss

            # Slime drip per-slot: cada gota só pode atingir um ship (consumida
            # ao colidir). Iterar slots vivos resolve sem double-damage.
            slime_boss = cast(SlimeBoss, boss)
            for slot in self.roster.alive_slots():
                drip_damage = slime_boss.check_drip_damage(
                    slot.ship.rect, self.entity_manager
                )
                if drip_damage > 0:
                    self._handle_ship_hit(slot)
                    self.level_controller.notify_damage_taken(drip_damage)

        score_gain = self._apply_score_multiplier(score_gain)

        return gain + score_gain

    def _check_ship_damage(self, slot: PlayerSlot) -> None:
        """Verifica todas as colisões que causam dano à nave do slot."""
        em = self.entity_manager
        ship = slot.ship

        if self.collisions.enemy_projectiles_vs_ship(
            ship, em.alien_bullets, em.enemy_projectile_grid
        ):
            self._handle_ship_hit(slot)
        if self.collisions.enemy_projectiles_vs_ship(
            ship, em.serpent_bullets, em.enemy_projectile_grid
        ):
            self._handle_ship_hit(slot)
        if self.collisions.eye_laser_vs_ship(ship, em.eye_lasers):
            self._handle_ship_hit(slot)

        orb_hit = self.collisions.energy_orbs_vs_ship(
            ship, em.energy_orbs, em.enemy_projectile_grid
        )
        if orb_hit:
            self._handle_ship_hit(slot)
            if ship.invuln > 0:
                orb_hit.apply_effect(ship)

        from ..entities.boss_laser import BossLaser

        boss_lasers = [
            laser for laser in em.boss_lasers if isinstance(laser, BossLaser)
        ]
        if self.collisions.laser_vs_ship(ship, boss_lasers):
            self._handle_ship_hit(slot)

        spike_lasers: list[SpikeBossLaser] = [
            laser for laser in em.boss_lasers if isinstance(laser, SpikeBossLaser)
        ]
        if spike_lasers and self.collisions.spike_boss_laser_vs_ship(
            ship, spike_lasers
        ):
            self._handle_ship_hit(slot)

        if self.collisions.ship_vs_spikes(ship, em.spikes, em):
            self._handle_ship_hit(slot)
        if self.collisions.ship_vs_boss_squares(ship, em.boss_squares):
            self._handle_ship_hit(slot)

        if self.boss_controller.boss_type == "stone_golem" and em.boss:
            self._check_stone_golem_sweep(em, slot)

        if self.boss_controller.boss_type == "mountain_serpent" and em.boss:
            if self.collisions.ship_vs_boss(ship, em.boss, self.entity_manager):
                self._handle_ship_hit(slot)

    def _check_stone_golem_sweep(self, em: EntityManager, slot: PlayerSlot) -> None:
        """Verifica dano do feixe sweep do StoneGolemBoss contra o slot."""
        from ..entities.stone_golem_boss import StoneGolemBoss

        golem = cast(StoneGolemBoss, em.boss)
        beam = golem.get_sweep_beam()
        ship = slot.ship
        if not beam or ship.invuln > 0:
            return

        px, py, ex, ey = beam
        sx = float(ship.rect.centerx)
        sy = float(ship.rect.centery)
        dx, dy = ex - px, ey - py
        len_sq = dx * dx + dy * dy
        if len_sq <= 0:
            return

        t = max(0.0, min(1.0, ((sx - px) * dx + (sy - py) * dy) / len_sq))
        closest_x = px + t * dx
        closest_y = py + t * dy
        dist = math.hypot(sx - closest_x, sy - closest_y)
        if dist < golem.SCALE * 2 + ship.rect.width * 0.4:
            self._handle_ship_hit(slot)

    def _apply_score_multiplier(self, pts: int) -> int:
        """Aplica multiplicador de score base + eventual bônus ativo."""
        multiplier = self.level_controller.base_score_multiplier
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

        gain, destroyed, score_events, ship_hits_proj = (
            self._check_projectile_vs_enemies(enemy_grid)
        )
        gain, destroyed, score_events, ship_hits_form = (
            self._check_formation_collisions(gain, destroyed, score_events)
        )

        # Mine/fire zones devolvem set de `id(ship)` atingidos. Rotear o hit
        # ao slot dono — ambos os players tomam dano em armadilhas.
        zone_ship_hits = ship_hits_proj | ship_hits_form
        if zone_ship_hits:
            for slot in self.roster.alive_slots():
                if id(slot.ship) in zone_ship_hits:
                    self._handle_ship_hit(slot)

        batched_events = self._batch_floating_scores(
            score_events, proximity_threshold=self.floating_score_batch_threshold
        )
        for x, y, pts in batched_events:
            # Emit event to display floating score
            self.app.event_bus.emit(
                events.SpawnFloatingScore(
                    x=x,
                    y=y,
                    score=self._apply_score_multiplier(pts),
                    color=(255, 255, 0),  # Amarelo para pontos de combate
                )
            )

        self.score += self._apply_score_multiplier(gain)
        self.total_enemies_destroyed += destroyed
        self.level_controller.notify_enemies_destroyed(destroyed)

        if destroyed > 0:
            self.star_spawner.add_kills(destroyed, self.entity_manager.stars)
            # Reverberador: o combo agora é creditado per-projétil dentro de
            # cada `collisions.*_vs_enemies`, via `_credit_kill(b)` que lê o
            # `owner_ship` da bala/laser/feixe. Em coop, P1 não rouba combo
            # do P2 e vice-versa. AoE sem owner rastreável (mine_explosion,
            # air_strike) não atribui — combo é prêmio por skill, não por
            # spray-and-pray.

        if self.entity_manager.spikes:
            all_player_projectiles = (
                self.entity_manager.bullets + self.entity_manager.mini_ship_bullets
            )
            spike_gain = self.collisions.projectiles_vs_spikes(
                all_player_projectiles,
                self.entity_manager.spike_spatial_grid,
                self.entity_manager,
            )
            if self.score_multiplier_active:
                spike_gain = int(spike_gain * self.score_multiplier_value)
            self.score += spike_gain

        # Nave vs. inimigos (físico) — per-slot
        for slot in self.roster.alive_slots():
            if self.collisions.ship_vs_enemies(
                slot.ship, enemy_grid, self.entity_manager
            ):
                self._handle_ship_hit(slot)

        self.score += self._check_boss_collisions(0)

        # Balas vs. objetos indestrutíveis
        self.collisions.bullets_vs_boss_squares(
            self.entity_manager.bullets,
            self.entity_manager.boss_squares,
            self.entity_manager,
        )

        if self.boss_controller.boss_type == "slime":
            self.collisions.bullets_vs_slime_drips(
                self.entity_manager.bullets,
                self.entity_manager.slime_drips,
                self.entity_manager,
            )

        # Damage per-slot: cada nave recebe os ataques que efetivamente acertam.
        for slot in self.roster.alive_slots():
            self._check_ship_damage(slot)
        self._process_powerups_and_stars()

    # ------------------------------------------------------------------
    # Power-ups
    # ------------------------------------------------------------------

    def build_mini_ships(self, slot: Optional[PlayerSlot] = None) -> None:
        """Cria o par temporário do powerup `mini_ships` (left + right) para o slot.

        Remove apenas as mini-naves vinculadas à nave deste slot (inclusive as
        permanentes — para evitar sobreposição visual). Mini-naves de outros
        slots permanecem intactas. As permanentes deste slot voltam quando o
        timer expira (`_update_ship`).
        """
        if slot is None:
            slot = self.roster.primary()
        parent = slot.ship
        self.entity_manager.mini_ships = [
            m for m in self.entity_manager.mini_ships if m.player is not parent
        ]
        for side in ("left", "right"):
            self.entity_manager.mini_ships.append(
                MiniShip(parent, side, is_side_scroll=self.is_side_scroll)
            )

    def _build_permanent_mini_ships(self, slot: Optional[PlayerSlot] = None) -> None:
        """Spawn das mini-naves permanentes do slot conforme `profile.permanent_mini_ships`."""
        if slot is None:
            slot = self.roster.primary()
        parent = slot.ship
        count = parent.profile.permanent_mini_ships
        if count <= 0:
            return
        # Alterna lados começando pela esquerda; com 1 = só esquerda, 2 = ambas.
        sides = ("left", "right")
        for i in range(min(count, len(sides))):
            self.entity_manager.mini_ships.append(
                MiniShip(
                    parent,
                    sides[i],
                    is_side_scroll=self.is_side_scroll,
                    permanent=True,
                )
            )

    def _apply_powerup(self, kind: str, slot: Optional[PlayerSlot] = None) -> None:
        if slot is None:
            slot = self.roster.primary()
        self.powerup_system.apply(kind, slot)

    def _process_powerups_and_stars(self) -> None:
        self.powerup_system.process_collection()

    # ------------------------------------------------------------------
    # Dano à nave / game over
    # ------------------------------------------------------------------

    def _handle_ship_hit(self, slot: Optional[PlayerSlot] = None) -> None:
        """Processa um acerto na nave do slot: god mode, escudo, vidas, game over.

        Slot opcional para retrocompat — call sites antigos podem chamar sem
        argumento e cai no slot primário (P1).
        """
        if slot is None:
            slot = self.roster.primary()
        ship = slot.ship
        if self._game_over_triggered or self.god_mode or ship.invuln > 0:
            return
        # Slots mortos (esperando revive) não tomam dano — caso algum call
        # site não-filtrado chame _handle_ship_hit pra um slot já morto
        # (ex.: mine explosion, slime drip que ainda usam o primário direto).
        if slot.is_dead:
            return

        # Emit PlayerDamaged event
        self.app.event_bus.emit(
            events.PlayerDamaged(
                damage=1,
                remaining_lives=slot.lives,
                is_game_over=False,  # Will update if game over
            )
        )

        # Reverberador: qualquer hit que efetivamente conta reseta o combo.
        ship.reset_combo()

        if ship.has_shield:
            ship.shield_hp -= 1
            if ship.shield_hp <= 0:
                ship.shield_timer = 0.0
            # Emit powerup event for shield absorption
            self.app.event_bus.emit(events.PlaySound(sound_name="powerup", volume=1.0))
            return

        self.change_lives_for(slot, -1)
        self.level_controller.notify_damage_taken()
        if slot.lives <= 0:
            # Marca o slot como morto — filtragem em alive_slots() impede que
            # o slot continue tomando dano, atirando, ou sendo renderizado.
            slot.is_dead = True
            # Mini-naves do slot somem junto com a nave (sem orbitar fantasma).
            # As permanentes voltam no revive via `_build_permanent_mini_ships`.
            self.entity_manager.mini_ships = [
                m for m in self.entity_manager.mini_ships if m.player is not slot.ship
            ]
            self._spawn_revival_beacon(slot)
        # Game over quando ninguém tem vidas. Em single-player, com 1 slot,
        # equivale ao comportamento original (vida zero = game over imediato).
        # Em coop, se restar pelo menos um vivo, o beacon do morto pode ser
        # ativado — o slot reviverá no próximo update sem disparar game over.
        is_game_over = all(s.lives <= 0 for s in self.roster.all_slots())
        # No game over, persistir o ganho da fase incompleta (record_clear não
        # roda nesse caso). Em perdas de vida com vidas restantes, deixar para
        # record_clear capturar o total quando a fase for concluída.
        level_gain_on_death = (
            self.score - self.level_controller.level_start_score if is_game_over else 0
        )
        self.player_profile.record_death(
            self.current_level_index + 1,
            cause="collision",
            score=level_gain_on_death,
        )

        if not is_game_over:
            ship.invuln = Config.INVULN_TIME * 1000
        else:
            # Captura o score final ANTES de qualquer zeragem para a tela de
            # Game Over exibir o valor real (sem isso, permadeath mostraria 0).
            final_score = self.score
            if self._permadeath_mode:
                self.score = 0
            next_level = self.player_profile.reset_to_checkpoint()
            logger.info("Game Over! Reinício preparado para nível %d", next_level)
            self._game_over_triggered = True

            # Emit GameOver event
            self.app.event_bus.emit(
                events.GameOver(
                    final_score=final_score, level_reached=self.current_level_index + 1
                )
            )

            from .game_over import GameOverScene

            self.app.states.switch(
                GameOverScene(self.app, final_score, self, next_level)
            )

    # ------------------------------------------------------------------
    # Progressão de nível
    # ------------------------------------------------------------------

    def _check_level_progression(self) -> None:
        status = self.level_controller.check_level_progression(
            current_score=self.score,
            enemy_cleanup_active=self.boss_controller.enemy_cleanup_active,
        )
        if status == ProgressionStatus.CLEANUP_NEEDED:
            self._on_cleanup_needed()
        elif status == ProgressionStatus.BOSS_READY:
            self._on_boss_threshold_reached()
        elif status == ProgressionStatus.LEVEL_CLEARED:
            self._on_level_cleared(with_delay=False)

    # Bônus de HP do boss por jogador adicional no roster (regra do plano de
    # coop: P2 ativo adiciona 40% de vida pra compensar DPS dobrado). Aplicado
    # no momento do spawn — bosses já em campo não reescalam se P2 entrar
    # durante a luta.
    _COOP_BOSS_HP_PER_EXTRA_PLAYER: float = 0.40

    def _start_boss_fight(self) -> None:
        level_config = self.level_config
        assert level_config is not None
        player_count = len(self.roster.all_slots())
        coop_hp_scale = 1.0 + self._COOP_BOSS_HP_PER_EXTRA_PLAYER * (player_count - 1)
        effective_multiplier = self.enemy_health_multiplier * coop_hp_scale
        if player_count > 1:
            logger.info(
                "Boss spawnando com escala coop ×%.2f (%d jogadores).",
                coop_hp_scale,
                player_count,
            )
        self.boss_controller.start(level_config, effective_multiplier)

    def _end_boss_fight(self) -> None:
        boss_score = self.boss_controller.end(
            score_multiplier_active=self.score_multiplier_active,
            score_multiplier_value=self.score_multiplier_value,
        )
        self.score += boss_score

        if self.level_controller.current_level_number == self.current_world.boss_level:
            self.player_profile.unlock_next_world(self.current_world.world_id)

        status = self.level_controller.advance_after_boss(self.score)
        if status == ProgressionStatus.LEVEL_CLEARED:
            self._on_level_cleared(with_delay=True)

    def _start_next_level(self) -> None:
        # Checkpoint usa o número 1-based do nível recém-concluído.
        self.player_profile.set_checkpoint_on_level_start(
            self.level_controller.current_level_number
        )
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)

        theme_changed, new_world = self.level_controller.start_next_level(
            self.current_world
        )
        self._on_advance_level(theme_changed, new_world)

    # ------------------------------------------------------------------
    # Eventos de entrada
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        # Intercepta Start no gamepad de slot 1 quando P2 ainda não juntou:
        # abre o modal de seleção de nave de P2. Demais eventos seguem para
        # o handler padrão (que opera somente sobre P1).
        if event.type == pygame.JOYBUTTONDOWN and self._is_p2_join_trigger(event):
            self._open_p2_select_modal()
            return
        # Saída voluntária do P2: Back/Select no controle de P2 remove ele
        # do roster. Score compartilhado fica preservado.
        if event.type == pygame.JOYBUTTONDOWN and self._is_p2_leave_trigger(event):
            self._remove_p2_slot(reason="voluntary")
            return
        # Desconexão do controle do P2: remove P2 do roster pra evitar nave
        # parada na tela sem input. P2 pode rejoinar reconectando o controle.
        if event.type == pygame.JOYDEVICEREMOVED and self._is_p2_disconnect(event):
            self._remove_p2_slot(reason="disconnect")
            return
        self.input_handler.handle(event)

    def _is_p2_leave_trigger(self, event: pygame.event.Event) -> bool:
        """True se BACK foi pressionado no gamepad atribuído ao P2."""
        from ..core.gamepad import XboxButton

        if event.button != XboxButton.BACK:
            return False
        if self.roster.count() < 2:
            return False
        return self.app.gamepad.slot_of_instance_id(event.instance_id) == 1

    def _is_p2_disconnect(self, event: pygame.event.Event) -> bool:
        """True se o gamepad desconectado era o atribuído ao P2."""
        if self.roster.count() < 2:
            return False
        p2_slot = self.roster.all_slots()[1]
        if p2_slot.gamepad_slot != 1:
            return False
        # GamepadManager já processou o JOYDEVICEREMOVED neste momento
        # (handle_event() do app.py despacha pra cá depois de chamar
        # gamepad.handle_event). Então slot 1 já está vazio se era o P2.
        return not self.app.gamepad.is_slot_connected(1)

    def _remove_p2_slot(self, *, reason: str) -> None:
        """Remove o slot do P2 do roster. Beacon e mini-naves são descartados."""
        all_slots = self.roster.all_slots()
        if len(all_slots) < 2:
            return
        p2 = all_slots[1]
        p2.revival_beacon = None
        # Mini-naves do P2 (permanentes do Engenheiro ou temporárias do powerup)
        # somem junto — sem a nave delas, ficariam orbitando entidade fantasma.
        self.entity_manager.mini_ships = [
            m for m in self.entity_manager.mini_ships if m.player is not p2.ship
        ]
        self.roster.remove(p2)
        # Volta ao escalonamento solo na próxima fase.
        self.level_controller.set_player_count(self.roster.count())
        self.enemy_spawner.set_player_count(self.roster.count())
        self.powerup_spawner.set_player_count(self.roster.count())
        logger.info("P2 saiu da partida (motivo=%s).", reason)

    def _is_p2_join_trigger(self, event: pygame.event.Event) -> bool:
        """True se o evento é START no segundo controle, e P2 ainda não juntou."""
        from ..core.gamepad import XboxButton

        if event.button != XboxButton.START:
            return False
        if self.roster.count() >= 2:
            return False
        gp = self.app.gamepad
        if not gp.secondary_connected:
            return False
        return gp.slot_of_instance_id(event.instance_id) == 1

    def _open_p2_select_modal(self) -> None:
        """Empurra o modal de seleção de nave de P2 sobre a partida."""
        from .p2_ship_select import P2ShipSelectScene

        modal = P2ShipSelectScene(
            self.app, playing_scene=self, on_confirm=self._spawn_p2
        )
        self.app.states.push(modal)

    def _spawn_p2(self, profile: Any) -> None:
        """Cria a nave de P2 e adiciona ao roster com animação de entrada."""
        primary_ship = self.roster.primary().ship

        # Define alvos de spawn baseados em P1
        if self.is_side_scroll:
            target_x = primary_ship.x
            target_y = primary_ship.y + 80.0
            start_x = -100.0
            start_y = target_y
        else:
            target_x = primary_ship.x + 80.0
            target_y = primary_ship.y
            start_x = target_x
            start_y = float(Config.SCREEN_HEIGHT + 100)

        p2_ship = Ship(
            start_x,
            start_y,
            mouse_control=False,
            auto_fire=False,
            profile=profile,
        )

        # Ativa animação de entrada similar ao P1
        p2_ship.start_entering_animation(
            (start_x, start_y),
            (target_x, target_y),
            1.5,  # Duração da animação
        )
        p2_ship.invuln = float(Config.INVULN_TIME * 1000)
        p2_ship.apply_world_mode(self.is_side_scroll)

        lives = int(self.difficulty_settings.get("lives", 3))
        p2_slot = PlayerSlot(
            ship=p2_ship,
            lives=lives,
            gamepad_slot=1,
            apply_permanent_upgrades=False,
        )
        p2_ship.lives = lives
        self.roster.add(p2_slot)
        self._build_permanent_mini_ships(p2_slot)
        # Atualiza scaling de coop pra próxima fase (a fase atual mantém o
        # valor antigo — mudar inimigos vivos seria confuso pro jogador).
        self.level_controller.set_player_count(self.roster.count())
        # Cap de inimigos na tela cresce imediatamente (afeta próximos spawns).
        self.enemy_spawner.set_player_count(self.roster.count())
        # Frequência de powerups também aumenta a partir do próximo spawn.
        self.powerup_spawner.set_player_count(self.roster.count())

        logger.info(
            "P2 entrou na partida com a nave '%s' (vidas=%d) e animação de entrada.",
            profile.id,
            lives,
        )

    # ------------------------------------------------------------------
    # Modo de seleção de upgrade via controle
    # ------------------------------------------------------------------

    def toggle_upgrade_select_mode(self) -> None:
        """Liga/desliga o modo de seleção. Ao ligar, alinha o cursor para um
        slot válido, priorizando upgrades fora de cooldown."""
        if self.upgrade_select_mode:
            self.upgrade_select_mode = False
            return
        if not any(s is not None for s in self.upgrade_slots):
            return  # Sem upgrades equipados — nada para selecionar.
        self.upgrade_select_mode = True
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

    def navigate_upgrade_select(self, delta: int) -> None:
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

    def confirm_upgrade_select(self) -> None:
        """Ativa o slot atualmente destacado e sai do modo."""
        idx = self._upgrade_select_index
        self.upgrade_select_mode = False
        if 0 <= idx < len(self.upgrade_slots) and self.upgrade_slots[idx] is not None:
            self.activate_upgrade_slot(idx)

    def activate_stored_powerup(self, slot_index: int) -> None:
        """Compat: ativa Cofre do slot primário (P1). Mantido para
        callers de teclado (Q/E) e outros pontos legados.
        """
        self.activate_stored_powerup_for(self.roster.primary(), slot_index)

    def activate_stored_powerup_for(self, slot: PlayerSlot, slot_index: int) -> None:
        """Consome o powerup armazenado do Cofre do `slot` e aplica em si próprio."""
        ship = slot.ship
        if not ship.has_storage_slots():
            return
        kind = ship.consume_stored_powerup(slot_index)
        if kind is None:
            return
        self.app.event_bus.emit(events.PlaySound(sound_name="powerup"))
        self._apply_powerup(kind, slot)

    def slot_inside_any_beacon(self, slot: PlayerSlot) -> bool:
        """True se o slot vivo está dentro do raio de algum beacon ativo.

        Usado pelo input handler pra suprimir a ativação do Cofre slot 0
        (botão Y) quando o jogador está tentando reviver alguém — o Y é
        compartilhado entre as duas ações e o revive (held) tem precedência.
        """
        ship = slot.ship
        px, py = float(ship.rect.centerx), float(ship.rect.centery)
        for dead in self.roster.dead_slots():
            beacon = dead.revival_beacon
            if beacon is not None and beacon.contains_point(px, py):
                return True
        return False

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface) -> None:
        self.game_renderer.render(self._build_render_frame(), surface)

    def _build_render_frame(self) -> RenderFrame:
        """Monta o snapshot do estado que o GameRenderer consome neste frame."""
        level_config = self.level_config
        assert level_config is not None
        stage_name = format_stage_name(level_config.level_number)

        keybindings = getattr(self.player_profile, "upgrade_keybindings", []) or []

        return RenderFrame(
            dt=self.last_dt,
            state=self.state,
            preparation_time_left=self.preparation_time_left,
            score=self.score,
            lives=self.lives,
            total_enemies_destroyed=self.total_enemies_destroyed,
            difficulty_preset=self.difficulty_preset,
            stage_name=stage_name,
            score_multiplier_active=self.score_multiplier_active,
            score_multiplier_timer=self.score_multiplier_timer,
            shake_timer=self.screen_shake_timer,
            shake_intensity=self.screen_shake_intensity,
            start_fade_active=self.start_fade_active,
            start_fade_alpha=self.start_fade_alpha,
            start_fade_overlay=self.start_fade_overlay,
            show_fps=self.show_fps,
            show_enemy_hitboxes=self.show_enemy_hitboxes,
            upgrade_select_mode=self.upgrade_select_mode,
            upgrade_select_index=self._upgrade_select_index,
            upgrade_slots=self.upgrade_slots,
            upgrade_keybindings=list(keybindings),
            world_transition_thruster_particles=self.world_transition_thruster_particles,
            ship=self.ship,
            entity_manager=self.entity_manager,
            boss_controller=self.boss_controller,
            extra_ships=tuple(
                slot.ship for slot in self.roster.all_slots()[1:] if not slot.is_dead
            ),
            revival_beacons=tuple(
                slot.revival_beacon
                for slot in self.roster.dead_slots()
                if slot.revival_beacon is not None
            ),
            primary_alive=not self.roster.primary().is_dead,
            p2_hud=self._build_p2_hud_info(),
            level_popup_text=self.level_popup_text,
            level_popup_timer=self.level_popup_timer,
            level_popup_duration=self.level_popup_duration,
        )

    def _build_p2_hud_info(self) -> Optional[P2HudInfo]:
        """Monta o snapshot do P2 para o HUD secundário (None em single-player)."""
        all_slots = self.roster.all_slots()
        if len(all_slots) < 2:
            return None
        p2 = all_slots[1]
        beacon_progress = (
            p2.revival_beacon.progress_ratio if p2.revival_beacon is not None else 0.0
        )
        return P2HudInfo(
            lives=p2.lives,
            is_dead=p2.is_dead,
            ship=p2.ship,
            beacon_progress=beacon_progress,
        )

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
        """Backward compat: sincroniza vidas do P1 e mirror para HUD."""
        self._sync_lives_for(self.roster.primary(), lives)

    def _sync_lives_for(self, slot: PlayerSlot, lives: int) -> None:
        """Vidas per-slot. Se for o slot primário, espelha em ``self.lives``
        (campo legado lido pelo HUD e por GameOver — quem migrar a leitura para
        ``self.roster`` em fase futura remove esse mirror)."""
        new_lives = max(0, lives)
        slot.lives = new_lives
        slot.ship.lives = new_lives
        if slot is self.roster.primary():
            self.lives = new_lives

    def _change_lives(self, delta: int) -> None:
        self.change_lives_for(self.roster.primary(), delta)

    def change_lives_for(self, slot: PlayerSlot, delta: int) -> None:
        self._sync_lives_for(slot, slot.lives + delta)

    # ------------------------------------------------------------------
    # Beacon de revive (multiplayer)
    # ------------------------------------------------------------------

    def _spawn_revival_beacon(self, slot: PlayerSlot) -> None:
        """Cria o beacon na posição da nave do slot que acabou de morrer."""
        if self.roster.count() < 2:
            return
        ship = slot.ship
        slot.revival_beacon = RevivalBeacon(
            x=float(ship.rect.centerx),
            y=float(ship.rect.centery),
            for_slot=slot,
            ship_image=ship.ship_image,
        )
        logger.info(
            "Beacon de revive spawnou em (%.0f, %.0f) para slot morto.",
            slot.revival_beacon.x,
            slot.revival_beacon.y,
        )

    def _update_revival_beacons(self, dt: float) -> None:
        """Processa todos os beacons ativos: detecta hold, acumula timer, revive."""
        dead_with_beacon = [
            s for s in self.roster.dead_slots() if s.revival_beacon is not None
        ]
        if not dead_with_beacon:
            return

        alive = self.roster.alive_slots()
        for dead_slot in dead_with_beacon:
            beacon = dead_slot.revival_beacon
            assert beacon is not None
            beacon.update_visual(dt)

            # Proximidade visual: mostra a dica se qualquer player vivo estiver no raio
            near_any = any(
                beacon.contains_point(
                    float(s.ship.rect.centerx), float(s.ship.rect.centery)
                )
                for s in alive
            )
            beacon.set_hint_visible(near_any)

            qualifying_helper = self._find_revive_helper(beacon, alive)
            if qualifying_helper is not None:
                beacon.tick_hold(dt)
                if beacon.is_complete:
                    self._revive_slot(dead_slot)
            else:
                beacon.reset_progress()

    def _find_revive_helper(
        self, beacon: RevivalBeacon, alive_slots: list[PlayerSlot]
    ) -> Optional[PlayerSlot]:
        """Retorna o primeiro slot vivo dentro do raio segurando Y, ou None."""
        for helper in alive_slots:
            ship = helper.ship
            if not beacon.contains_point(
                float(ship.rect.centerx), float(ship.rect.centery)
            ):
                continue
            if self._is_revive_button_held(helper):
                return helper
        return None

    def _is_revive_button_held(self, slot: PlayerSlot) -> bool:
        """Checa se o slot está segurando o botão de revive (Y / tecla Y)."""
        from ..core.gamepad import XboxButton

        gp = self.app.gamepad
        slot_idx = slot.gamepad_slot if slot.gamepad_slot is not None else 0
        if gp.is_button_pressed(XboxButton.Y, slot=slot_idx):
            return True
        # Fallback teclado só para P1 (slot 0 inclui teclado por convenção).
        if slot_idx == 0:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_y]:
                return True
        return False

    def _revive_slot(self, slot: PlayerSlot) -> None:
        """Ressuscita o slot na posição do beacon com vida e invuln inicial."""
        beacon = slot.revival_beacon
        if beacon is None:
            return
        ship = slot.ship
        # Reposiciona a nave no beacon para o player "renascer" no local.
        ship.x = beacon.x - ship.w / 2.0
        ship.y = beacon.y - ship.h / 2.0
        ship.invuln = RevivalBeacon.POST_REVIVE_INVULN_MS
        slot.is_dead = False
        slot.revival_beacon = None
        self._sync_lives_for(slot, RevivalBeacon.LIVES_ON_REVIVE)
        # Restaura mini-naves permanentes (Engenheiro): foram removidas na morte.
        self._build_permanent_mini_ships(slot)
        logger.info(
            "Slot revivido em (%.0f, %.0f) com %d vida.",
            beacon.x,
            beacon.y,
            RevivalBeacon.LIVES_ON_REVIVE,
        )

    def apply_cooldown_reduction(self, reduction: float) -> None:
        """Reduz instantaneamente o cooldown de todos os upgrades ativos."""
        for upg in self.upgrade_slots:
            if upg is not None and upg.cooldown_left > 0:
                upg.cooldown_left = max(0.0, upg.cooldown_left - reduction)

    def _apply_god_mode_cooldowns(self) -> None:
        """Reduz todos os cooldowns ativos para 1 segundo ao ativar god mode."""
        for upg in self.upgrade_slots:
            if upg is not None and upg.cooldown_left > 0:
                upg.cooldown_left = min(upg.cooldown_left, 1.0)

    def activate_upgrade_slot(self, idx: int) -> None:
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
