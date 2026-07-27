"""render_frame.py — DTO de leitura entre PlayingScene e GameRenderer.

Define o contrato explícito de tudo que o renderizador lê da cena. Em vez de
o renderer acessar `scene.foo_bar` direto (e quebrar silenciosamente quando a
cena renomeia atributos), `PlayingScene._build_render_frame()` monta um
`RenderFrame` por frame e o renderer consome só este DTO.

Scalars/flags são copiados; refs a sistemas estáveis (ship, entity_manager,
boss_controller) são passadas por referência — esses não são "internals" da
cena, são serviços compartilhados. Coleções mutáveis (particles, upgrade
slots) também passam por ref e são tratadas como read-only pelo renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    from ..core.difficulty import DifficultyPreset
    from ..core.upgrades import ActiveUpgrade
    from ..entities.player.revival_beacon import RevivalBeacon
    from ..entities.player.ship import Ship
    from .boss_backdrop_dim import BossBackdropDim
    from .damage_vignette import DamageVignette
    from ..scenes.playing import GameState, ThrusterParticle
    from ..systems.boss_fight_controller import BossFightController
    from ..systems.entity_manager import EntityManager


@dataclass(frozen=True)
class P2HudInfo:
    """Snapshot dos dados do Jogador 2 para o HUD secundário.

    Existe apenas quando há um segundo slot no roster (coop ativo). Quando
    `is_dead=True`, `beacon_progress` está em 0.0-1.0 mostrando o quanto da
    barra de revive já foi acumulada — usado pelo HUD para mostrar
    "REVIVENDO XX%" no lugar das vidas.
    """

    lives: int
    is_dead: bool
    ship: "Ship"
    beacon_progress: float = 0.0


@dataclass(frozen=True)
class RenderFrame:
    """Snapshot imutável do estado relevante para renderização de um frame."""

    # Tempo & FSM
    dt: float
    state: "GameState"
    preparation_time_left: float

    # Score, vidas e dificuldade
    score: int
    lives: int
    total_enemies_destroyed: int
    difficulty_preset: "DifficultyPreset"
    stage_name: str

    # Multiplicador de score
    score_multiplier_active: bool
    score_multiplier_timer: float

    # Screen shake
    shake_timer: float
    shake_intensity: int

    # Debug overlays
    show_fps: bool
    show_enemy_hitboxes: bool

    # Upgrade HUD
    upgrade_select_mode: bool
    upgrade_select_index: int
    upgrade_slots: list["ActiveUpgrade | None"]
    upgrade_keybindings: list[int]
    upgrade_denied_timers: dict[int, float]
    """Índice do slot → segundos restantes de tremor por uso negado.

    Alimenta o feedback de "tentei usar e não deu": sem isto, apertar a tecla de
    um poder em cooldown não produz resposta visual nenhuma.
    """

    # Cutscene de transição de mundo
    world_transition_cutscene_active: bool
    world_transition_cutscene_timer: float
    is_arrival_cutscene: bool
    world_transition_thruster_particles: list["ThrusterParticle"]

    # Refs a sistemas (estáveis — não são internals da cena)
    ship: "Ship"
    entity_manager: "EntityManager"
    boss_controller: "BossFightController"

    # Vinheta de dano (overlay de HUD). Renderer só chama `draw()`; estado é
    # mutado na cena (trigger/update), nunca aqui.
    damage_vignette: "DamageVignette"

    # Escurecimento de fundo em lutas de boss. Renderer só chama `draw()` (após o
    # background); estado é mutado na cena (update).
    boss_backdrop_dim: "BossBackdropDim"

    # Multiplayer: naves adicionais (P2 em diante) renderizadas após `ship`.
    # Vazio em single-player. Renderer apenas draw()-a; não inspeciona estado.
    extra_ships: tuple["Ship", ...] = ()

    # Multiplayer: beacons de revive de slots mortos. Renderer só os desenha.
    revival_beacons: tuple["RevivalBeacon", ...] = ()

    # Multiplayer: False quando o slot primário está morto esperando revive.
    # Renderer pula `frame.ship.draw()` mas mantém o resto do HUD/stats.
    primary_alive: bool = True

    # Multiplayer: dados do P2 para o HUD secundário. None em single-player.
    p2_hud: Optional[P2HudInfo] = None

    # Pop-up de início de nível (sub-fases)
    level_popup_text: str = ""
    level_popup_timer: float = 0.0
    level_popup_duration: float = 2.5

    # Fase de atmosfera (interstício)
    in_atmosphere: bool = False
    atmosphere_progress: float = 0.0
    atmosphere_route: Optional[str] = None

    # Impact flash (white frames): clarão branco curtíssimo sobre o mundo para
    # momentos importantes. Renderer compõe alpha = flash_alpha * (timer/duração).
    flash_timer: float = 0.0
    flash_duration: float = 0.0
    flash_alpha: int = 0

    # 'Pop' do número do score: 1.0 no frame em que pontuou, decaindo a 0.0.
    # A cena mantém o timer; aqui só chega a fração já normalizada.
    score_pop: float = 0.0

    # ── Parada do tempo (power-up TIME_STOP) ──────────────────────────────
    # Já normalizados pela cena a partir do `TimeStopState`; o renderer não
    # conhece durações nem constantes, só desenha as frações.
    time_stop_frozen: bool = False
    """Inimigos parados. Liga a moldura e o rótulo de 'TEMPO PARADO'."""

    time_stop_warning: float = 0.0
    """0→1 conforme o congelamento se aproxima do fim.

    Único canal do aviso de término: a intensidade da pulsação e o quanto a
    moldura 'racha' saem daqui. Sobe em rampa, em vez de ser um liga/desliga,
    para o aviso entrar suave e ir ficando mais aflito.
    """

    time_stop_recovering: bool = False
    """Rampa de volta em curso.

    Existe separado de `time_stop_recovery` porque a fração é AMBÍGUA: ela vale
    0.0 tanto em "não há efeito nenhum" quanto em "a recuperação começou agora".
    Guardar o overlay por `recovery <= 0.0` engolia o primeiro instante da
    rampa — justo o frame do descongelamento, o mais visível de todos.
    """

    time_stop_recovery: float = 0.0
    """0→1 durante a rampa em que os inimigos voltam a acelerar."""

    time_stop_phase: float = 0.0
    """Relógio da pulsação, em segundos de congelamento acumulados.

    Vem da cena porque o render não tem (nem deve ter) relógio próprio: §3.
    Um `time.time()` aqui continuaria correndo durante a pausa e faria a
    moldura reaparecer fora de fase ao despausar.
    """
