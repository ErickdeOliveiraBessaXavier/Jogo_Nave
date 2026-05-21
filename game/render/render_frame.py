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
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..core.difficulty import DifficultyPreset
    from ..core.upgrades import ActiveUpgrade
    from ..entities.ship import Ship
    from ..scenes.playing import GameState, ThrusterParticle
    from ..systems.boss_fight_controller import BossFightController
    from ..systems.entity_manager import EntityManager


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
    world_transition_thruster_particles: list["ThrusterParticle"]

    # Refs a sistemas (estáveis — não são internals da cena)
    ship: "Ship"
    entity_manager: "EntityManager"
    boss_controller: "BossFightController"
