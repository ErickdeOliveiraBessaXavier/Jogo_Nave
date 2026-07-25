"""
playing.py — Cena principal de gameplay.

Orquestra todo o ciclo de jogo: entrada de jogador, atualização de entidades,
colisões, renderização e progresso de nível.

Responsabilidades principais:
  - Gerenciar máquina de estados (preparation, playing, defeat, victory, boss_intro)
  - Instanciar e coordenar EntityManager (entidades), Collisions (física),
    GameRenderer (renderização), BossFightController e ShootingSystem
  - Atualizar DeltaTime para slow-motion (game over, boss warning)
  - Emitir eventos de progresso (level complete, score milestones) para EventBus
  - Sincronizar estado com metaprogression (level_config dinâmico)

Arquitetura:
  - EntityManager: concentra todas as entidades (inimigos, projéteis, efeitos)
  - Systems extraídos: LevelProgressionController, BossFightController, ShootingSystem
  - RenderFrame DTO: desacopla necessidades de renderização da lógica de jogo
  - Context objects: EnemyUpdateContext, BossUpdateContext (unificam assinaturas)
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

import pygame

from ..core.assets import get_font
from ..core.config import SlimeBossState
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.levels import (
    LevelConfig,
    LevelManager,
    get_level_config,
    set_run_variety_salt,
)
from ..core.meta_progression_service import MetaProgressionService
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..core.state import Scene
from ..core.upgrades import ActiveUpgrade, create_upgrade
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from ..core.atmosphere_phase import (
    ATMOSPHERE_PHASE_ENABLED,
    AtmosphereState,
    build_spawn_config,
    classify_route,
    get_phase_config,
)
from ..core.world_config import (
    WorldConfig,
    format_stage_name,
    get_world_for_level,
    is_side_scroll_mode,
    resolve_theme_key,
)
from ..entities.player.mini_ship import MiniShip
from ..entities.player.revival_beacon import RevivalBeacon
from ..entities.player.ship import Ship
from ..events import game_events as events
from ..render.game_renderer import GameRenderer
from ..render.boss_backdrop_dim import BossBackdropDim
from ..render.damage_vignette import DamageVignette
from ..render.render_frame import RenderFrame
from ..systems.boss_fight_controller import BossFightController
from ..systems.cheat_input import CheatBuffer
from ..systems.collision_orchestrator import CollisionOrchestrator
from ..systems.collisions import Collisions
from ..systems.effects_system import EffectsSystem
from ..systems.entity_manager import EntityManager
from ..systems.gameplay_input_handler import GameplayInputHandler
from ..systems.level_progression_controller import (
    LevelProgressionController,
    ProgressionStatus,
)
from ..systems.p2_session_controller import P2SessionController
from ..systems.player_slot import PlayerRoster, PlayerSlot
from ..systems.powerup_system import PowerupSystem
from ..systems.revival_system import RevivalSystem
from ..systems.shooting_system import ShootingSystem
from ..systems.upgrade_selector import UpgradeSelector
from ..systems.spawner import EnemySpawner, PowerUpSpawner, StarSpawner
from ..systems.transition_controller import TransitionController, TransitionPhase
from ..systems.world_transition_cutscene import (
    ThrusterParticle,
    WorldTransitionCutscene,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..app import GameApp

# ---------------------------------------------------------------------------
# Constantes de módulo (eliminam "magic numbers" espalhados pela classe)
# ---------------------------------------------------------------------------
_SIDE_SCROLL_SHIP_ENTRY_X = 100
_TOP_DOWN_SHIP_TARGET_Y_OFFSET = 80
# Regressão de altitude ao morrer na atmosfera (animada, não corte seco).
_ATMOSPHERE_REGRESS_RATE = 0.5  # progresso (0-1) revertido por segundo
_ATMOSPHERE_REGRESS_MIN_DURATION = 0.8  # piso para sempre ler como animação
# Nocaute na atmosfera: a nave "desmaia", gira e mergulha pra fora da tela, e
# segundos depois re-entra de cima (estilo "entering").
_ATMOSPHERE_DEATH_OUT_DURATION = 1.6  # desmaio: gira e mergulha pra fora + beat
_ATMOSPHERE_DEATH_RETURN_DURATION = 1.2  # re-entrada deslizando do topo
_ATMOSPHERE_DEATH_SWOON_HSPEED = 700.0  # px/s rumo ao lado oposto
_ATMOSPHERE_DEATH_SWOON_VY0 = -340.0  # px/s inicial (sobe antes de mergulhar)
_ATMOSPHERE_DEATH_SWOON_GRAVITY = 1700.0  # px/s² puxando para o mergulho
_ATMOSPHERE_DEATH_SWOON_SPIN = 600.0  # graus/s (a "volta"/tumbling)
_HUD_UPGRADE_SLOT_SIZE = 50
_HUD_UPGRADE_SLOT_GAP = 6


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------


# Encerramento de fase: após este tempo (s) magnetizando os coletáveis, os que
# ainda sobraram na tela começam a dissolver (fade), garantindo que a transição
# não fique presa nem carregue power-ups/estrelas para a fase seguinte. Cabe com
# folga na janela de espera (LEVEL_TRANSITION_DELAY 2.0s + timeout 1.2s).
CLOSING_FADE_AFTER: float = 1.2


class GameState(Enum):
    """Estado de jogo interno da cena (fase de preparação vs gameplay ativo)."""

    PREPARING = auto()
    PLAYING = auto()


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
        p2_profile: Optional[Any] = None,
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
        self.is_side_scroll = is_side_scroll_mode(self.current_world.theme)

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

        # P2 sobrevive ao "Continuar" do game over. A cena é recriada do zero a
        # cada continue, então quem estava jogando precisa ser reconstruído
        # aqui — sem isto o P2 era silenciosamente largado e tinha que apertar
        # START de novo a cada morte. Depende de `_init_systems` (entity_manager,
        # spawners e o `_p2_session` que `spawn_p2` usa).
        if p2_profile is not None and self.app.gamepad.secondary_connected:
            self._p2_session.spawn_p2(p2_profile)

    @property
    def is_side_scroll(self) -> bool:
        return self._is_side_scroll

    @is_side_scroll.setter
    def is_side_scroll(self, value: bool) -> None:
        """Fonte de verdade do modo de jogo. Propaga para o `EntityManager`
        (e seus pools) para manter as regras de culling/movimento coerentes ao
        cruzar mundos side-scroll↔top-down. O guard cobre o `__init__`, em que
        o modo é definido antes de `entity_manager` existir."""
        self._is_side_scroll = value
        em = getattr(self, "entity_manager", None)
        if em is not None:
            em.set_side_scroll(value)

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
        # Cursor de seleção de upgrade (gamepad). Getter lazy porque
        # `upgrade_slots` é reatribuído a cada fase (§1).
        self.upgrade_selector = UpgradeSelector(
            get_slots=lambda: self.upgrade_slots,
            activate=self.activate_upgrade_slot,
        )
        # Slot → tempo de tremor restante ao tentar usar poder indisponível.
        self._upgrade_denied_timers: dict[int, float] = {}
        self._apply_difficulty_settings()

        self.screen_shake_timer: float = 0.0
        self.screen_shake_intensity: int = Config.SCREEN_SHAKE_NORMAL
        # Impact flash (white frames): clarão branco curto p/ momentos importantes.
        self.impact_flash_timer: float = 0.0
        self.impact_flash_duration: float = 0.0
        self.impact_flash_alpha: int = 0
        # Vinheta de dano (feedback de HUD ao tomar hit). Estado na cena, igual ao
        # screen shake; atualizada no update e desenhada pelo GameRenderer.
        self.damage_vignette = DamageVignette()
        # Escurecimento de fundo durante lutas de boss (padrão p/ todos os bosses).
        self.boss_backdrop_dim = BossBackdropDim()
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

        # Tempo acumulado no encerramento de fase (POST_VICTORY_DELAY +
        # LEVEL_TRANSITION_WAIT). Dispara o fade dos coletáveis retardatários.
        self._closing_elapsed: float = 0.0

        # Cinemática de saída da nave (charge→launch + partículas). O estado da
        # animação e a lógica vivem no controller (§9); a cena guarda a fachada
        # fina — `world_transition_cutscene_active` (derivado do FSM) + as
        # properties de leitura `world_transition_cutscene_timer`/
        # `world_transition_thruster_particles` que o DTO de render consome — e o
        # callback de FLUXO `_on_world_cutscene_complete` (painel/atmosfera/prep).
        self._world_cutscene = WorldTransitionCutscene(
            get_ship=lambda: self.ship,
            get_side_scroll=lambda: self.is_side_scroll,
            get_entity_manager=lambda: self.entity_manager,
            is_active=lambda: self.transitions.is_cutscene_exit,
            enter_cutscene_phase=lambda: self._set_transition_phase(
                TransitionPhase.CUTSCENE_EXIT
            ),
            on_complete=self._on_world_cutscene_complete,
        )

        # Interstício "Entering/Exiting the Atmosphere". Todo o estado de runtime
        # (rota, altitude, regressão, cinemática de nocaute, flag in_atmosphere)
        # vive num único `AtmosphereState`; a lógica que o muda fica nos métodos
        # `_*_atmosphere_*` desta cena (FSM acoplado — ver core/atmosphere_phase.py
        # e código_teste/PLANO_FASE_ATMOSFERA.md).
        self._atmosphere = AtmosphereState()

    def _init_fade(self) -> None:
        """Configura o fade-in inicial para evitar corte abrupto.

        Com "Animações da Interface" desligado (padrão no web), o fade preto de
        tela cheia é pulado: a fase aparece instantânea, sem o overlay SRCALPHA
        por vários frames — evita um pico de fillrate justo na transição de fase.
        """
        from ..core.visual_quality import visual_quality

        anim_on = visual_quality.ui_animations
        self.start_fade_active: bool = anim_on
        self.start_fade_alpha: float = 255.0 if anim_on else 0.0
        self.start_fade_elapsed: float = 0.0
        self.start_fade_duration: float = self._start_fade_duration
        self.start_fade_overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )

    # Contrato PÚBLICO de feedback de tela (§1): o `EffectsSystem` reage a
    # eventos do bus e precisa pedir shake/flash à cena. Enquanto estes métodos
    # eram privados, ele os chamava por `hasattr` + acesso a `_privado`, com
    # fallback escrevendo atributos direto — fronteira borrada e quebra
    # silenciosa se o nome mudasse. Ver `ScreenFeedback` em `effects_system`.
    def request_screen_shake(self, duration: float, intensity: int) -> None:
        self.screen_shake_timer = duration
        self.screen_shake_intensity = intensity

    def request_impact_flash(self, duration: float, alpha: int) -> None:
        """Flash branco de impacto (white frames). Não acumula: um flash em curso
        só é substituído por outro de pico >= (evita que um fraco corte um forte)."""
        if self.impact_flash_timer > 0.0 and alpha < self.impact_flash_alpha:
            return
        self.impact_flash_timer = duration
        self.impact_flash_duration = duration
        self.impact_flash_alpha = alpha

    def _get_background(self) -> Any | None:
        return getattr(self.r, "current_background", None)

    def _init_systems(self) -> None:
        """Instancia sistemas de jogo (EntityManager, spawners, colisões)."""
        # Semente de variedade por-partida: sorteada UMA vez por sessão de jogo,
        # antes de gerar qualquer fase. Faz a seleção de inimigos variar entre runs
        # (rejogar traz specials diferentes; todo tipo ganha chance real ao longo
        # das tentativas) sem quebrar a anti-repetição ENTRE fases da mesma run.
        set_run_variety_salt(random.randrange(1, 2**31))
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
            screen_shake_request=self.request_screen_shake,
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

        # Revive cooperativo: a cena mantém a lógica de vidas e mini-naves (via
        # callbacks); o beacon em si é do sistema. Não referencia a cena (§1).
        self.revival_system = RevivalSystem(
            roster=self.roster,
            gamepad=self.app.gamepad,
            sync_lives=self._sync_lives_for,
            rebuild_mini_ships=self._build_permanent_mini_ships,
        )

        # Sessão de co-op local (P2): entrada/saída/desconexão + spawn/HUD. Não
        # referencia a cena (§1); o modal e o trio set_player_count entram por
        # callback (o modal precisa da cena p/ render de fundo e perfil).
        self._p2_session = P2SessionController(
            roster=self.roster,
            gamepad=self.app.gamepad,
            entity_manager=self.entity_manager,
            get_is_side_scroll=lambda: self.is_side_scroll,
            get_lives=lambda: int(self.difficulty_settings.get("lives", 3)),
            set_player_count=self._set_active_player_count,
            open_p2_modal=self._open_p2_modal,
            build_permanent_mini_ships=self._build_permanent_mini_ships,
        )

        # Orquestração de colisões: roda todos os passes do frame e RETORNA um
        # CollisionResult (score/kills/floating scores) que a cena aplica. Ship-hits
        # são roteados via callback durante o run (ordem/invuln preservadas). §9.
        self._collision_orch = CollisionOrchestrator(
            entity_manager=self.entity_manager,
            collisions=self.collisions,
            roster=self.roster,
            boss_controller=self.boss_controller,
            level_controller=self.level_controller,
            on_ship_hit=self._handle_ship_hit,
            get_last_dt=lambda: self.last_dt,
            get_multiplier_state=lambda: (
                self.score_multiplier_active,
                self.score_multiplier_value,
            ),
            get_batch_threshold=lambda: self.floating_score_batch_threshold,
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
        # 'Pop' do número do score no HUD, no mesmo espírito do combo do
        # Reverberador. Detectamos a variação uma vez por frame em vez de
        # instrumentar cada `self.score +=` (são vários pontos: abates, spikes,
        # boss); assim nenhum caminho novo de pontuação esquece de disparar.
        self._score_pop_timer: float = 0.0
        self._score_pop_last: int = 0
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

    # Fachada fina de leitura para o DTO de render (§9): o estado da animação
    # mora no controller; o render lê estes valores via `RenderFrame`.
    @property
    def world_transition_cutscene_timer(self) -> float:
        return self._world_cutscene.timer

    @property
    def world_transition_thruster_particles(self) -> list[ThrusterParticle]:
        return self._world_cutscene.particles

    @property
    def awaiting_world_transition_panel(self) -> bool:
        return self.transitions.is_world_panel

    def can_handle_gameplay_actions(self) -> bool:
        """Retorna True quando o jogador pode agir normalmente."""
        return self.transitions.can_handle_gameplay_actions

    def _next_transition_is_theme_change(self) -> bool:
        """True se a PRÓXIMA transição de nível cruza a fronteira de TEMA (mundo).

        Peek puro (sem avançar), idêntico ao cálculo do LevelProgressionController
        (`new_world.theme != current_world.theme`). Distingue a transição "grande"
        — mudança de tema, com cutscene/atmosfera + limpeza total da fase — da
        transição CONTÍNUA dentro do mesmo mundo (1-1→1-2), que preserva projéteis,
        coletáveis e escoltas para não quebrar a continuidade do gameplay."""
        next_level = self.level_controller.current_level_number + 1
        return get_world_for_level(next_level).theme != self.current_world.theme

    def _is_closing_level(self) -> bool:
        """True durante o ENCERRAMENTO de fase — SÓ quando a próxima transição é
        mudança de tema.

        Janela (pós-vitória + espera) em que não há spawns nem tiro do jogador,
        os projéteis já em tela seguem voando e os coletáveis são magnetizados/
        dissolvidos antes da transição concluir. Dentro do mesmo tema não há
        encerramento: a sequência é contínua (§ continuidade de mundo)."""
        return (
            self.level_transition_pending or self.level_transition_active
        ) and self._next_transition_is_theme_change()

    def _begin_level_preparation(self) -> None:
        """Coloca a cena em modo de preparação para o próximo nível."""
        self._set_transition_phase(TransitionPhase.LEVEL_ENTRY)
        self.state = GameState.PREPARING
        self.preparation_time_left = Config.PREPARATION_TIME
        self._closing_elapsed = 0.0
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
            # Reinicia o estado do interstício para esta transição.
            self._atmosphere.phase_done = False
            self._atmosphere.route = None
            self._atmosphere.progress = 0.0
            self._atmosphere.regressing = False
            self._atmosphere.death_active = False
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

        if theme_changed:
            # Mudança de TEMA = transição "grande": limpa a fase inteira
            # (projéteis, coletáveis pendentes, referências de IA, estados
            # temporários) e reconstrói as escoltas com a orientação do novo modo.
            # Dentro do MESMO tema (1-1→1-2) NADA disso ocorre — os elementos
            # persistentes seguem contínuos, preservando a sequência do mundo.
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

            self._world_cutscene.start(new_world)
        else:
            self._begin_playing_state()

    def _reset_ship_for_level_entry(self) -> None:
        """Reposiciona a nave para a posição de entrada do nível atual e inicia animação."""
        if self._atmosphere.in_atmosphere and self._atmosphere.route == "entering":
            # Entering (descida na atmosfera): a nave entra pela borda SUPERIOR e
            # atira pra baixo (facing "south", setado em _start_atmosphere_interstitial);
            # os meteoros sobem de baixo. Espelha o ramo top-down, mas pelo topo.
            start_x = Config.SCREEN_WIDTH / 2.0 - 20
            start_y = -100.0
            target_x = start_x
            target_y = float(_TOP_DOWN_SHIP_TARGET_Y_OFFSET)
        elif self.is_side_scroll:
            start_x = -100.0
            start_y = (Config.SCREEN_HEIGHT - 35) / 2.0
            target_x = float(_SIDE_SCROLL_SHIP_ENTRY_X)
            target_y = start_y
        else:
            start_x = Config.SCREEN_WIDTH / 2.0 - 20
            start_y = float(Config.SCREEN_HEIGHT + 100)
            target_x = start_x
            target_y = float(Config.SCREEN_HEIGHT - _TOP_DOWN_SHIP_TARGET_Y_OFFSET)

        # Garante que a animação de entrada comece do zero com as posições corretas
        # para o modo de jogo atual (evita "pular" de posições de temas anteriores).
        self.ship.start_entering_animation(
            (start_x, start_y), (target_x, target_y), Config.PREPARATION_TIME
        )
        self.ship.apply_world_mode(self.is_side_scroll)

    def _begin_playing_state(self) -> None:
        """Ativa o gameplay e registra a tentativa do nível uma única vez."""
        self._set_transition_phase(TransitionPhase.PLAYING)
        self.state = GameState.PLAYING
        self._closing_elapsed = 0.0
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
        # Música ambiente do tema novo (data-driven): a descoberta por pasta
        # troca a rotação para `audio/themes/<tema>/`. Re-emissão do mesmo tema
        # é deduplicada no MusicManager (não corta a faixa em andamento).
        self.app.event_bus.emit(
            events.MusicStateChange(
                state=MusicState.GAME,
                key=resolve_theme_key(new_world),
                fade_ms=0,
            )
        )
        # Usa o mesmo fluxo de preparação dos níveis normais — ``_begin_playing_state``
        # direto zerava ``is_entering`` no mesmo frame e a animação de entrada
        # nunca tocava. ``_begin_level_preparation`` mantém ``state=PREPARING``
        # até ``_update_preparing_state`` consumir ``Config.PREPARATION_TIME``,
        # garantindo que a nave deslize da borda até a posição alvo.
        self._begin_level_preparation()

    # ------------------------------------------------------------------
    # Cutscene de transição de mundo — cinemática/partículas no
    # `WorldTransitionCutscene` (systems/, §9). Aqui fica só o FLUXO de
    # conclusão, que depende de estado da partida (mundo, atmosfera, pilha).
    # ------------------------------------------------------------------

    def _on_world_cutscene_complete(
        self, target_world: Optional[WorldConfig], debug_mode: bool
    ) -> None:
        """Callback disparado pelo controller quando a cutscene termina.

        Decide o próximo passo do fluxo: interstício de atmosfera (se a rota
        qualifica), preparação de nível (debug/F8) ou abertura do painel de
        transição de mundo.
        """
        if target_world is None:
            return

        if (
            ATMOSPHERE_PHASE_ENABLED
            and not debug_mode
            and not self._atmosphere.phase_done
            and self.pending_world_transition is not None
        ):
            route = classify_route(self.current_world, target_world)
            if route is not None:
                # Cutscene 1 concluída → interstício jogável (não abre o painel
                # ainda). Ao terminar, dispara a cutscene 2 → painel → Mundo Y.
                self._start_atmosphere_interstitial(route)
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

    # ------------------------------------------------------------------
    # Interstício "Entering / Exiting the Atmosphere" (esqueleto de fluxo)
    # ------------------------------------------------------------------

    def _start_atmosphere_interstitial(self, route: str) -> None:
        """Entra na fase de atmosfera (jogável) após a cutscene de saída.

        Reaproveita o loop normal: monta uma "level config" de atmosfera (chuva
        de meteoros), orienta a nave e entra em PREPARING→PLAYING. A progressão
        de nível fica gateada por `_in_atmosphere` (ver `_update_level_logic`);
        o fim é por altitude → cutscene 2.
        """
        config = get_phase_config(route)
        self._atmosphere.in_atmosphere = True
        self._atmosphere.route = route
        self._atmosphere.progress = 0.0
        self._atmosphere.regressing = False
        self._atmosphere.death_active = False
        self._atmosphere.death_ships = []

        # Atmosfera é sempre vertical (top-down), independente dos mundos vizinhos.
        self.is_side_scroll = False
        self.r.set_atmosphere_mode(route)

        # Trigger pop-up de mudança de fase
        is_exiting = route == "exiting"
        self.level_popup_text = "SAINDO DA ATMOSFERA" if is_exiting else "ENTRANDO NA ATMOSFERA"
        self.level_popup_timer = self.level_popup_duration

        level_number = self.level_controller.current_level_number
        self.enemy_spawner.set_level(
            level_number,
            is_world_transition=True,
            level_config=LevelConfig(
                level_number=level_number,
                enemy_spawn_config=build_spawn_config(route),
                enemies_to_clear=10_000,  # fim é por altitude, não por kills
                theme_name="Atmosfera",
            ),
            inverted_vertical=config.inverted_vertical if config else False,
        )

        # Entrada da nave + orientação. `_begin_level_preparation` posiciona a
        # nave para a entrada top-down (is_side_scroll=False) e roda
        # PREPARING→PLAYING. Exiting = facing "north" (sobe de baixo, atira pra cima).
        self._begin_level_preparation()
        self.ship.set_facing(config.facing if config else "north")
        logger.info("[ATMOSPHERE] Interstício jogável iniciado: %s", route)

        # Intro estilo "novo mundo" (fundo preto + texto central) para a fase.
        # Reaproveita WorldTransitionScene com texto custom; some a linha de
        # estágios. Ao fechar, a PlayingScene retoma na entrada da nave (PREPARING).
        if self.pending_world_transition is not None:
            from .world_transition import WorldTransitionScene

            is_exiting = route == "exiting"
            self.app.states.push(
                WorldTransitionScene(
                    self.app,
                    self.pending_world_transition,
                    title_override=(
                        "SAINDO DA ATMOSFERA" if is_exiting else "ENTRANDO NA ATMOSFERA"
                    ),
                    description_override=(
                        "Rumo ao espaço sideral."
                        if is_exiting
                        else "Atravessando a atmosfera do planeta."
                    ),
                    stage_text_override="",
                )
            )

    def _apply_atmosphere_death_penalty(self) -> None:
        """Morte no interstício: em vez de game over, a nave leva um NOCAUTE —
        desmaia (gira e mergulha pra fora da tela) e segundos depois re-entra
        pelo topo, estilo "entering". Ao mesmo tempo a altitude REGRIDE pela
        metade (o background/HUD seguem `_atmosphere_progress`). Revive todos os
        slots e limpa a tela; a fase continua.
        """
        if self._atmosphere.death_active:
            return  # já em nocaute — não reinicia

        from_progress = self._atmosphere.progress
        target = max(0.0, from_progress * 0.5)

        # Regressão de altitude concorrente: `_update_atmosphere_regression`
        # interpola `_atmosphere_progress` de `from` até `target` (background e
        # barra seguem sozinhos). Duração proporcional à queda, com piso.
        self._atmosphere.regressing = True
        self._atmosphere.regress_from = from_progress
        self._atmosphere.regress_to = target
        self._atmosphere.regress_elapsed = 0.0
        drop = from_progress - target
        self._atmosphere.regress_duration = max(
            _ATMOSPHERE_REGRESS_MIN_DURATION, drop / _ATMOSPHERE_REGRESS_RATE
        )

        # Pausa a chuva durante o nocaute (religada quando a nave volta ao
        # controle, em `_finish_atmosphere_death`). Tranco do impacto.
        self.enemy_spawner.stopped = True
        self.request_screen_shake(0.4, Config.SCREEN_SHAKE_NORMAL)

        initial_lives = int(self.difficulty_settings["lives"])
        for slot in self.roster.all_slots():
            slot.is_dead = False
            slot.revival_beacon = None
            self._sync_lives_for(slot, initial_lives)
            # Invuln cobre todo o cinematic + uma folga após o retorno.
            slot.ship.invuln = (
                _ATMOSPHERE_DEATH_OUT_DURATION + _ATMOSPHERE_DEATH_RETURN_DURATION
            ) * 1000.0 + RevivalBeacon.POST_REVIVE_INVULN_MS
            self._build_permanent_mini_ships(slot)

        # Recomeço limpo: remove meteoros/hostis em tela. Invalida antes de
        # esvaziar para nenhum companheiro (mini/wingman) ficar mirando fantasma.
        self.entity_manager.invalidate_enemy_targets()
        self.entity_manager.meteor_pool.clear_active()
        self.entity_manager.enemies.clear()

        # Inicia o desmaio: captura posição e a direção do mergulho (rumo ao
        # lado oposto) de cada nave viva.
        self._atmosphere.death_active = True
        self._atmosphere.death_phase = "out"
        self._atmosphere.death_timer = 0.0
        center_x = Config.SCREEN_WIDTH / 2.0
        self._atmosphere.death_ships = [
            (
                slot.ship,
                float(slot.ship.x),
                float(slot.ship.y),
                1.0 if slot.ship.x < center_x else -1.0,
            )
            for slot in self.roster.alive_slots()
        ]

        logger.info(
            "[ATMOSPHERE] Morte: regressão %.0f%% -> %.0f%% em %.1fs, revive com %d vidas.",
            from_progress * 100.0,
            target * 100.0,
            self._atmosphere.regress_duration,
            initial_lives,
        )

    def _update_atmosphere_progress(self, dt: float) -> None:
        """Avança o medidor de altitude."""
        if self._atmosphere.progress >= 1.0:
            return

        config = get_phase_config(self._atmosphere.route)
        length = config.altitude_length if config else 40.0
        self._atmosphere.progress = min(
            1.0, self._atmosphere.progress + dt / max(0.1, length)
        )
        if self._atmosphere.progress >= 1.0:
            self.enemy_spawner.stopped = True
            logger.info("[ATMOSPHERE] Altitude atingida, aguardando limpeza de tela...")

    def _update_atmosphere_regression(self, dt: float) -> None:
        """Anima a perda de altitude após morte na atmosfera (pano de fundo do
        nocaute). Interpola `_atmosphere_progress` de `from` até `to` com
        ease-out — o background (cor, planeta, nuvens) e a barra de altitude
        regridem juntos. O religamento da chuva fica a cargo do cinematic
        (`_finish_atmosphere_death`), que dura mais que esta regressão.
        """
        self._atmosphere.regress_elapsed += dt
        duration = max(1e-3, self._atmosphere.regress_duration)
        t = min(1.0, self._atmosphere.regress_elapsed / duration)
        eased = 1.0 - (1.0 - t) ** 3  # ease-out cúbico (rápido no início)
        self._atmosphere.progress = (
            self._atmosphere.regress_from
            + (self._atmosphere.regress_to - self._atmosphere.regress_from) * eased
        )
        if t >= 1.0:
            self._atmosphere.progress = self._atmosphere.regress_to
            self._atmosphere.regressing = False

    def _update_atmosphere_death_cinematic(self, dt: float) -> None:
        """Conduz o nocaute da nave: desmaio (gira + mergulha pra fora) e, em
        seguida, re-entrada deslizando do topo (estilo "entering")."""
        self._atmosphere.death_timer += dt

        if self._atmosphere.death_phase == "out":
            t = self._atmosphere.death_timer
            for ship, start_x, start_y, dir_x in self._atmosphere.death_ships:
                # Trajetória de desmaio: leve subida e mergulho (gravidade) com
                # deriva horizontal rumo ao lado oposto, girando (tumbling).
                ship.x = start_x + dir_x * _ATMOSPHERE_DEATH_SWOON_HSPEED * t
                ship.y = (
                    start_y
                    + _ATMOSPHERE_DEATH_SWOON_VY0 * t
                    + 0.5 * _ATMOSPHERE_DEATH_SWOON_GRAVITY * t * t
                )
                ship.set_rotation((dir_x * _ATMOSPHERE_DEATH_SWOON_SPIN * t) % 360.0)
            if self._atmosphere.death_timer >= _ATMOSPHERE_DEATH_OUT_DURATION:
                self._begin_atmosphere_death_return()
        elif self._atmosphere.death_phase == "return":
            # A re-entrada é tocada pela animação de entering de cada nave
            # (rodada em `_update_ship`). Só aguardamos a duração acabar.
            if self._atmosphere.death_timer >= _ATMOSPHERE_DEATH_RETURN_DURATION:
                self._finish_atmosphere_death()

    def _begin_atmosphere_death_return(self) -> None:
        """Transição desmaio → re-entrada: cada nave ressurge pela mesma borda
        do fluxo da rota. Entering (de cima pra baixo) volta deslizando do topo;
        exiting (de baixo pra cima) ressurge subindo pela base — sempre até a
        posição de jogo, com o nariz no sentido da rota."""
        self._atmosphere.death_phase = "return"
        self._atmosphere.death_timer = 0.0

        config = get_phase_config(self._atmosphere.route)
        facing = config.facing if config else "north"
        if self._atmosphere.route == "entering":
            # Re-entry: joga no topo, ressurge pelo topo (nariz pra baixo).
            play_y = float(_TOP_DOWN_SHIP_TARGET_Y_OFFSET)
            start_y = -120.0
        else:
            # Exiting (de baixo pra cima): joga no rodapé, ressurge pela base
            # (nariz pra cima).
            play_y = float(Config.SCREEN_HEIGHT - _TOP_DOWN_SHIP_TARGET_Y_OFFSET)
            start_y = float(Config.SCREEN_HEIGHT + 120.0)

        margin = 40.0
        for ship, start_x, _start_y, _dir_x in self._atmosphere.death_ships:
            target_x = max(margin, min(Config.SCREEN_WIDTH - margin, start_x))
            ship.set_facing(facing)  # endireita o tumbling no sentido da rota
            ship.start_entering_animation(
                (target_x, start_y),
                (target_x, play_y),
                _ATMOSPHERE_DEATH_RETURN_DURATION,
            )

    def _finish_atmosphere_death(self) -> None:
        """Encerra o nocaute: restaura a orientação da rota, devolve o controle
        e religa a chuva de meteoros."""
        self._atmosphere.death_active = False
        self._atmosphere.death_ships = []
        config = get_phase_config(self._atmosphere.route)
        route_facing = config.facing if config else "north"
        for slot in self.roster.alive_slots():
            slot.ship.is_entering = False
            slot.ship.set_facing(route_facing)
        self.enemy_spawner.stopped = False

    def _finish_atmosphere_interstitial(self) -> None:
        """Conclui a fase e dispara a cutscene de chegada (cutscene 2)."""
        self._atmosphere.in_atmosphere = False
        self._atmosphere.phase_done = True
        is_entering = self._atmosphere.route == "entering"
        self._atmosphere.route = None
        logger.info("[ATMOSPHERE] Interstício concluído")

        # Restaura o spawner para o nível destino (a fase tinha parado ele
        # ao atingir 100% de altitude). O entity_manager.clear_for_level_transition
        # aqui é salvaguarda caso algo tenha restado.
        self.boss_controller.reset()
        self.entity_manager.clear_for_level_transition()
        for slot in self.roster.alive_slots():
            if slot.ship.mini_ships_timer > 0.0:
                self.build_mini_ships(slot)
            else:
                self._build_permanent_mini_ships(slot)
        self.enemy_spawner.set_level(
            self.level_controller.current_level_number,
            is_world_transition=True,
            level_config=self.level_controller.level_config,
        )

        target = self.pending_world_transition
        if target is None:
            # Salvaguarda: sem destino, aplica direto (não deveria ocorrer).
            self._apply_pending_world_transition()
            return
        # Re-entry (Entering): a nave desce na atmosfera — cutscene lança pra baixo.
        self._world_cutscene.start(target, launch_down=is_entering)

    def debug_force_world_transition(self) -> None:
        """[DEBUG/F8] Força a transição para o próximo mundo via fluxo REAL.

        Pula o controller de nível para o fim do mundo atual e avança — o
        próximo nível cruza a fronteira de mundo, disparando o fluxo normal
        (theme change → cutscene 1 → interstício de atmosfera se a rota
        qualificar → cutscene 2 → destino corretamente configurado).
        
        Se já estiver no interstício de atmosfera, pula ele instantaneamente.
        """
        if self.world_transition_cutscene_active:
            logger.info("[DEBUG] Transição já em andamento")
            return

        if self._atmosphere.in_atmosphere:
            logger.info("[DEBUG] F8: pulando interstício de atmosfera")
            self._finish_atmosphere_interstitial()
            return

        boss_level = self.current_world.boss_level
        self.level_controller.current_level_index = boss_level - 1
        logger.info(
            "[DEBUG] F8: pulando para o fim de %s (nível %s) e avançando de mundo",
            self.current_world.name,
            boss_level,
        )
        self._start_next_level()

    # ------------------------------------------------------------------
    # Ciclo de vida da cena
    # ------------------------------------------------------------------

    def enter(self) -> None:
        pygame.mouse.set_visible(False)
        self._init_fade()
        if self.first_entry:
            self.app.event_bus.emit(
                events.MusicStateChange(
                    state=MusicState.GAME,
                    key=resolve_theme_key(self.current_world),
                    fade_ms=0,
                )
            )
            self.first_entry = False
        if self.transition_phase == TransitionPhase.WORLD_PANEL:
            self._apply_pending_world_transition()

    def exit(self) -> None:
        pygame.mouse.set_visible(True)
        # Para só os SFX em loop/sustentados; one-shots (explosão da nave, som do
        # raio) seguem soando até o fim — senão a morte fica muda, cortada pela
        # troca de cena (GameOver toca a explosão ANTES deste exit rodar).
        sound_manager.stop_looping_sfx()
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
            self._world_cutscene.update(dt)
            return

        self.transitions.update_post_victory(dt)

        self._update_preparing_state(dt)
        self._update_timers(dt)
        self._update_ship(dt)
        self.revival_system.update(dt)
        self._apply_environmental_effects(dt)
        self._apply_gravity_wells(dt)
        self._update_spawners(dt)

        self.entity_manager.update(
            dt,
            self.ship.rect.centerx,
            self.ship.rect.centery,
            freeze_enemies=self.freeze_active,
            screen_width=Config.SCREEN_WIDTH,
            screen_height=Config.SCREEN_HEIGHT,
            attraction_mult=self.ship.profile.pickup_radius_mult,
            closing_pull_target=(
                (self.ship.rect.centerx, self.ship.rect.centery)
                if self._is_closing_level()
                else None
            ),
        )

        if self.transition_phase in (
            TransitionPhase.PLAYING,
            TransitionPhase.LEVEL_ENTRY,
        ):
            self._handle_collisions()
            if self._game_over_triggered:
                return
        elif self._is_closing_level():
            # Encerramento de fase: as colisões normais não rodam fora do PLAYING,
            # então processamos aqui a coleta dos coletáveis magnetizados e o fade
            # dos retardatários — nada de power-up/estrela atravessando a transição.
            self._update_level_closing(dt)

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

    SCORE_POP_DURATION = 0.25

    @property
    def score_pop(self) -> float:
        """Intensidade do 'pop' do score, 1.0 no instante da pontuação → 0.0.

        Fração do timer, não tempo absoluto: o renderer não precisa de relógio
        e a animação acompanha pausa e slow-motion de graça (§3).
        """
        return self._score_pop_timer / self.SCORE_POP_DURATION

    def _update_score_pop(self, dt: float) -> None:
        if self.score > self._score_pop_last:
            self._score_pop_timer = self.SCORE_POP_DURATION
        elif self._score_pop_timer > 0.0:
            self._score_pop_timer = max(0.0, self._score_pop_timer - dt)
        # Também sincroniza quando o score CAI (reset de game over): só
        # subida dispara o pop, queda apenas realinha a referência.
        self._score_pop_last = self.score

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

        self._update_score_pop(dt)

        self._update_upgrades(dt)

        boss = cast(Any, self.entity_manager.boss)
        if boss and (
            getattr(boss, "state", None) == "entering"
            or getattr(boss, "current_state", None) == SlimeBossState.ENTERING
        ):
            self.screen_shake_timer = 0.1
        else:
            self.screen_shake_timer = max(0.0, self.screen_shake_timer - dt)

        if self.impact_flash_timer > 0.0:
            self.impact_flash_timer = max(0.0, self.impact_flash_timer - dt)

        self.damage_vignette.update(dt, self._primary_is_critical())

        # Escurecimento de fundo: ativo enquanto o boss vive e luta (exceto durante
        # a cutscene de entrada, que tem seu próprio dim de tela cheia).
        boss = self.entity_manager.boss
        boss_dim_active = bool(
            boss is not None
            and not boss.dead
            and self.boss_controller.active
            and not getattr(boss, "is_intro_active", False)
        )
        self.boss_backdrop_dim.update(dt, boss_dim_active)

        if self.transitions.update_level_transition_wait(
            dt, self._ready_for_level_transition()
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
            from ..entities.bosses.spike_boss import SpikeBoss

            boss_pausing = cast(SpikeBoss, self.entity_manager.boss).is_pausing_game()

        if self.can_handle_gameplay_actions() and not self._atmosphere.death_active:
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
        """Aplica efeitos ambientais (como vento) às naves de TODOS os jogadores.

        O vento do MountainPropeller precisa afetar cada nave viva por conta
        própria — antes só o primário (`self.ship`) era empurrado/desacelerado, e
        o P2 em co-op ficava imune. O `wind_slow_factor` é por-nave (ship.py), lido
        no movimento de cada nave (ship_movement.py).
        """
        if not self.can_handle_gameplay_actions():
            return

        # Só as hélices soprando importam — calculado uma vez p/ todas as naves.
        blowing = [
            prop for prop in self.entity_manager.mountain_propellers if prop.is_blowing()
        ]

        for slot in self.roster.alive_slots():
            ship = slot.ship
            if ship.is_entering:
                ship.wind_slow_factor = 1.0
                continue
            wind_slow_factor = 1.0
            for prop in blowing:
                if ship.rect.colliderect(prop.get_wind_rect()):
                    ship.x -= prop.PUSH_FORCE * dt
                    wind_slow_factor = prop.SLOW_SPEED_MULT
            ship.wind_slow_factor = wind_slow_factor

    def _apply_gravity_wells(self, dt: float) -> None:
        """Gravity Well: arrasta cada nave viva para o centro de cada poço ativo
        (força radial com falloff). Efeito de MOVIMENTO (mesma categoria do vento
        do MountainPropeller), consumido e limpo por frame. Sempre esvazia a lista
        para não acumular quando a jogabilidade está pausada."""
        wells = self.entity_manager.gravity_wells
        if not wells:
            return

        # Resetar o estado de atração de cada poço antes de recalcular
        for w in wells:
            if len(w) > 5 and w[5] is not None:
                w[5].is_pulling_something = False

        if self.can_handle_gameplay_actions() and not self._atmosphere.death_active:
            # Projéteis (jogador e inimigos) têm a rota curvada pela anomalia.
            self.entity_manager.apply_gravity_to_projectiles(dt)
            for slot in self.roster.alive_slots():
                ship = slot.ship
                if ship.is_entering:
                    continue
                for wx, wy, radius, strength, _bend, *extra in wells:
                    scx = ship.x + ship.w / 2
                    scy = ship.y + ship.h / 2
                    dx, dy = wx - scx, wy - scy
                    dist = math.hypot(dx, dy)
                    if dist >= radius or dist < 1e-3:
                        continue
                    if extra:
                        extra[0].is_pulling_something = True
                    # Falloff LINEAR: força já perceptível ao passar pela borda e
                    # cresce continuamente rumo ao centro (aceleração progressiva,
                    # sem "liga/desliga"). No centro > velocidade base da nave, mas
                    # a borda é vencível acelerando para fora (counterplay).
                    falloff = 1.0 - dist / radius
                    step = strength * falloff * dt
                    ship.x += (dx / dist) * step
                    ship.y += (dy / dist) * step
                # Mantém em tela (mesmo clamp de ShipMovement._keep_in_bounds).
                if ship.x < 0:
                    ship.x = 0
                if ship.y < 0:
                    ship.y = 0
                if ship.x + ship.w > Config.SCREEN_WIDTH:
                    ship.x = Config.SCREEN_WIDTH - ship.w
                if ship.y + ship.h > Config.SCREEN_HEIGHT:
                    ship.y = Config.SCREEN_HEIGHT - ship.h
        wells.clear()

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
        if self._atmosphere.in_atmosphere:
            # Fase de atmosfera: progride por altitude e ignora a progressão
            # normal de nível (sem boss, sem "enemies_to_clear").
            if self.transition_phase == TransitionPhase.PLAYING:
                if self._atmosphere.death_active:
                    # Nocaute: nave desmaia, sai de tela e re-entra; a altitude
                    # regride junto como pano de fundo.
                    self._update_atmosphere_death_cinematic(dt)
                    if self._atmosphere.regressing:
                        self._update_atmosphere_regression(dt)
                else:
                    self._update_atmosphere_progress(dt)
                    # Atingida a altitude máxima, só transiciona quando a tela
                    # estiver limpa. Os hostis da fase (Meteor/Satellite) saem
                    # sozinhos pelo eixo Y — com o culling respeitando o modo
                    # top-down, nenhum fica preso, então não há mais timeout.
                    if (
                        self._atmosphere.progress >= 1.0
                        and not self.entity_manager.enemies
                    ):
                        self._finish_atmosphere_interstitial()
            return
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

    def _player_projectiles_pending(self) -> bool:
        """True se ainda há projéteis do jogador em tela — a transição espera eles
        saírem/colidirem (§ encerramento limpo)."""
        em = self.entity_manager
        return bool(
            em.bullets
            or em.homing_bullets
            or em.cacador_lasers
            or em.mini_ship_bullets
        )

    def _collectibles_pending(self) -> bool:
        """True enquanto houver power-up/estrela na tela (sendo coletado ou em fade)."""
        return bool(self.entity_manager.powerups or self.entity_manager.stars)

    def _ready_for_level_transition(self) -> bool:
        """Gate de conclusão da espera de transição.

        MESMO tema (transição contínua): comportamento original — só espera as
        animações de morte, sem segurar por projéteis/coletáveis (eles atravessam
        para o próximo nível normalmente).

        MUDANÇA de tema (encerramento limpo): também exige que nenhum projétil do
        jogador reste e que os coletáveis tenham sido resolvidos (coletados ou
        dissolvidos). O timeout duro do `TransitionController` é a rede de segurança."""
        if not self._next_transition_is_theme_change():
            return self._all_animations_finished()
        return (
            self._all_animations_finished()
            and not self._player_projectiles_pending()
            and not self._collectibles_pending()
        )

    def _update_level_closing(self, dt: float) -> None:
        """Encerramento de fase: coleta os coletáveis magnetizados (as colisões
        normais não rodam fora do PLAYING) e, após `CLOSING_FADE_AFTER`, dissolve
        os retardatários. A magnetização em si vem do `closing_pull_target` passado
        ao `entity_manager.update`."""
        self._closing_elapsed += dt
        self.powerup_system.process_collection()
        if self._closing_elapsed >= CLOSING_FADE_AFTER:
            for p in self.entity_manager.powerups:
                p.begin_fade_out()
            for s in self.entity_manager.stars:
                s.begin_fade_out()

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
    # Colisões — orquestração em CollisionOrchestrator (systems/, §9)
    # ------------------------------------------------------------------

    def _handle_collisions(self) -> None:
        """Roda o orquestrador de colisões e aplica o resultado ao estado da cena
        (score, kills, floating scores). Ship-hits já foram roteados no run."""
        result = self._collision_orch.run()

        self.score += result.score_gain
        self.total_enemies_destroyed += result.enemies_destroyed
        self.level_controller.notify_enemies_destroyed(result.enemies_destroyed)
        if result.enemies_destroyed > 0:
            self.star_spawner.add_kills(
                result.enemies_destroyed, self.entity_manager.stars
            )

        for x, y, pts in result.floating_scores:
            self.app.event_bus.emit(
                events.SpawnFloatingScore(
                    x=x,
                    y=y,
                    score=pts,
                    color=(255, 255, 0),  # Amarelo para pontos de combate
                )
            )

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

    def _primary_is_critical(self) -> bool:
        """True quando o slot primário está no limite crítico (1 vida) e vivo.

        Libera o pulso de alerta contínuo da vinheta de dano; acima disso o
        efeito é só o flash transiente ao tomar hit."""
        slot = self.roster.primary()
        return (not slot.is_dead) and slot.lives <= 1

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
            # 1s de invulnerabilidade após absorver: protege contra dano
            # consecutivo imediato (dois acertos no mesmo frame/instante
            # gastariam duas cargas ou vazariam pra vida). `max` não encurta um
            # invuln maior já em curso.
            ship.invuln = max(ship.invuln, Config.SHIELD_ABSORB_INVULN_MS)
            # Emit powerup event for shield absorption
            self.app.event_bus.emit(events.PlaySound(sound_name="powerup", volume=1.0))
            return

        self.change_lives_for(slot, -1)
        # Vinheta de dano: flash transiente momentâneo ao tomar hit. O alerta
        # contínuo (1 vida) é decidido no update via `_primary_is_critical`.
        self.damage_vignette.trigger(damage=1)
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
            self.revival_system.spawn_beacon(slot)
        # Game over quando ninguém tem vidas. Em single-player, com 1 slot,
        # equivale ao comportamento original (vida zero = game over imediato).
        # Em coop, se restar pelo menos um vivo, o beacon do morto pode ser
        # ativado — o slot reviverá no próximo update sem disparar game over.
        is_game_over = all(s.lives <= 0 for s in self.roster.all_slots())

        # Interstício de atmosfera: perder todas as vidas NÃO é game over — corta
        # o progresso pela metade e a fase continua (regra própria da fase).
        if is_game_over and self._atmosphere.in_atmosphere:
            self._apply_atmosphere_death_penalty()
            return

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
            ended_attempt=is_game_over,
        )

        if not is_game_over:
            ship.invuln = Config.INVULN_TIME * 1000
        else:
            # Captura o score final ANTES de qualquer zeragem para a tela de
            # Game Over exibir o valor real (sem isso, permadeath mostraria 0).
            final_score = self.score
            # Recorde do checkpoint atual: melhor run que chegou a este mundo.
            self.player_profile.record_run_best_score(final_score)
            if self._permadeath_mode:
                self.score = 0
            # Continuar reinicia a PRÓPRIA fase onde o jogador morreu (não o
            # início do mundo). `reset_to_checkpoint` é leitura pura; ignoramos
            # o retorno dele de propósito em favor do nível atual.
            next_level = self.current_level_index + 1
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
        # Sessão de co-op (P2): entrada (START), saída (BACK) e desconexão do
        # controle. Se o controller consumiu o evento, não repassa ao input de P1.
        if self._p2_session.try_handle_event(event):
            return
        self.input_handler.handle(event)

    def _set_active_player_count(self, count: int) -> None:
        """Callback do `P2SessionController`: propaga a contagem de jogadores ao
        controlador de nível e aos spawners (afeta scaling da PRÓXIMA fase e o cap
        de tela imediatamente)."""
        self.level_controller.set_player_count(count)
        self.enemy_spawner.set_player_count(count)
        self.powerup_spawner.set_player_count(count)

    def _open_p2_modal(self, on_confirm: Callable[[Any], None]) -> None:
        """Callback do `P2SessionController`: empurra o modal de seleção de nave de
        P2 sobre a partida. Fica na cena porque o modal usa `playing_scene` para o
        render de fundo e o perfil (unlocked_ships)."""
        from .p2_ship_select import P2ShipSelectScene

        modal = P2ShipSelectScene(
            self.app, playing_scene=self, on_confirm=on_confirm
        )
        self.app.states.push(modal)

    # ------------------------------------------------------------------
    # Modo de seleção de upgrade via controle
    # ------------------------------------------------------------------

    # Fachadas (§9) para o input handler — delegam ao UpgradeSelector.
    @property
    def upgrade_select_mode(self) -> bool:
        """True enquanto o cursor de seleção de upgrade está ativo (só leitura)."""
        return self.upgrade_selector.mode

    def toggle_upgrade_select_mode(self) -> None:
        self.upgrade_selector.toggle()

    def navigate_upgrade_select(self, delta: int) -> None:
        self.upgrade_selector.navigate(delta)

    def confirm_upgrade_select(self) -> None:
        self.upgrade_selector.confirm()

    def cancel_upgrade_select(self) -> None:
        self.upgrade_selector.cancel()

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
        """Fachada (§9) para o input handler — delega ao RevivalSystem."""
        return self.revival_system.slot_inside_any_beacon(slot)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface) -> None:
        # Se uma cena-filha (ex.: WorldTransitionScene) foi empilhada durante o
        # update DESTE mesmo frame, o app.run() ainda chama o render da cena
        # capturada ANTES do update — esta. Sem o guard, a PlayingScene vaza um
        # único frame: notadamente o background da atmosfera recém-ativado em
        # `_start_atmosphere_interstitial` (set_atmosphere_mode) aparece por um
        # instante antes do painel cobrir a tela — o "blink" da transição
        # mundo→atmosfera. Como o app só renderiza a cena do topo, esta condição
        # só é verdadeira nesse frame de borda.
        if self.app.states.current() is not self:
            return
        self.render_world(surface)

    def render_world(self, surface: pygame.Surface) -> None:
        """Renderiza o mundo do jogo SEM o guard de cena-topo.

        Usado por cenas-overlay (ex.: `PausedScene`) que desenham a
        `PlayingScene` como fundo via delegação — o guard de `render` aborta
        nesse caso (a overlay é o topo), deixando o fundo preto. Chamar este
        método direto preserva o fundo (background da atmosfera/tema, HUD, etc.).
        """
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
            score_pop=self.score_pop,
            lives=self.lives,
            total_enemies_destroyed=self.total_enemies_destroyed,
            difficulty_preset=self.difficulty_preset,
            stage_name=stage_name,
            score_multiplier_active=self.score_multiplier_active,
            score_multiplier_timer=self.score_multiplier_timer,
            shake_timer=self.screen_shake_timer,
            shake_intensity=self.screen_shake_intensity,
            flash_timer=self.impact_flash_timer,
            flash_duration=self.impact_flash_duration,
            flash_alpha=self.impact_flash_alpha,
            start_fade_active=self.start_fade_active,
            start_fade_alpha=self.start_fade_alpha,
            start_fade_overlay=self.start_fade_overlay,
            show_fps=self.show_fps,
            show_enemy_hitboxes=self.show_enemy_hitboxes,
            upgrade_select_mode=self.upgrade_selector.mode,
            upgrade_select_index=self.upgrade_selector.index,
            upgrade_slots=self.upgrade_slots,
            upgrade_keybindings=list(keybindings),
            upgrade_denied_timers=dict(self._upgrade_denied_timers),
            world_transition_cutscene_active=(
                self.transitions.phase == TransitionPhase.CUTSCENE_EXIT
                or self.state == GameState.PREPARING
            ),
            world_transition_cutscene_timer=self.world_transition_cutscene_timer,
            is_arrival_cutscene=self.state == GameState.PREPARING,
            world_transition_thruster_particles=self.world_transition_thruster_particles,
            ship=self.ship,
            entity_manager=self.entity_manager,
            boss_controller=self.boss_controller,
            damage_vignette=self.damage_vignette,
            boss_backdrop_dim=self.boss_backdrop_dim,
            extra_ships=tuple(
                slot.ship for slot in self.roster.all_slots()[1:] if not slot.is_dead
            ),
            revival_beacons=tuple(
                slot.revival_beacon
                for slot in self.roster.dead_slots()
                if slot.revival_beacon is not None
            ),
            primary_alive=not self.roster.primary().is_dead,
            p2_hud=self._p2_session.build_hud_info(),
            level_popup_text=self.level_popup_text,
            level_popup_timer=self.level_popup_timer,
            level_popup_duration=self.level_popup_duration,
            in_atmosphere=self._atmosphere.in_atmosphere,
            atmosphere_progress=self._atmosphere.progress,
            atmosphere_route=self._atmosphere.route,
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
        self._update_upgrade_denied_timers(dt)
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
            # `activate` devolve False quando recusou (cooldown, sem cargas,
            # já ativo) e o som de negação sai lá dentro, em `on_denied`. O
            # retorno era descartado: agora arma o tremor do slot, para a
            # recusa ter resposta VISUAL além da sonora — no caos, som some.
            if not upg.activate(ctx):
                self._upgrade_denied_timers[idx] = Config.UPGRADE_DENIED_SHAKE_TIME
        except (AttributeError, TypeError):
            pass

    def _update_upgrade_denied_timers(self, dt: float) -> None:
        """Escoa os tremores de uso negado (tempo real: é feedback de UI)."""
        if not self._upgrade_denied_timers:
            return
        self._upgrade_denied_timers = {
            idx: t - dt
            for idx, t in self._upgrade_denied_timers.items()
            if t - dt > 0.0
        }
