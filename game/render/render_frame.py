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

import pygame

if TYPE_CHECKING:
    from ..core.difficulty import DifficultyPreset
    from ..core.upgrades import ActiveUpgrade
    from ..entities.revival_beacon import RevivalBeacon
    from ..entities.ship import Ship
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

    # Fade inicial
    start_fade_active: bool
    start_fade_alpha: float
    start_fade_overlay: pygame.Surface

    # Debug overlays
    show_fps: bool
    show_enemy_hitboxes: bool

    # Upgrade HUD
    upgrade_select_mode: bool
    upgrade_select_index: int
    upgrade_slots: list["ActiveUpgrade | None"]
    upgrade_keybindings: list[int]

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
