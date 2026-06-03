"""Bound methods do sound_manager para uso em HitResult.sound.

Evita dispatch por string (ex.: getattr(sound_manager, f"play_{name}")) e
dá completion no IDE. Cada constante é um Callable[[], None] já bound — o
custo de chamada é idêntico a sound_manager.play_X().
"""

from __future__ import annotations

from collections.abc import Callable

from ..core.sound import sound_manager

EXPLOSION_ALIEN: Callable[[], None] = sound_manager.play_explosion_alien
EXPLOSION_ASTEROID: Callable[[], None] = sound_manager.play_explosion_asteroid
EXPLOSION_BOSS: Callable[[], None] = sound_manager.play_explosion_boss
BOSS_DAMAGE: Callable[[], None] = sound_manager.play_boss_damage
WARNING: Callable[[], None] = sound_manager.play_warning  # ex.: "Heavy Unit Incoming"
STOP_WARNING: Callable[[], None] = sound_manager.stop_warning  # encerra o loop do warning

# StoneGolemBoss
GOLEM_MINE_TIMER: Callable[[], None] = sound_manager.play_golem_mine_timer
GOLEM_STOP_MINE_TIMER: Callable[[], None] = sound_manager.stop_golem_mine_timer
GOLEM_CHARGING: Callable[[], None] = sound_manager.play_boss_laser_charging
GOLEM_STOP_CHARGING: Callable[[], None] = sound_manager.stop_boss_laser_charging
GOLEM_SWEEP_LASER: Callable[[], None] = sound_manager.play_boss_laser_fire
GOLEM_STOP_SWEEP_LASER: Callable[[], None] = sound_manager.stop_boss_laser_fire
GOLEM_ORB_PURPLE: Callable[[], None] = sound_manager.play_golem_orb_purple
GOLEM_ERUPTION: Callable[[], None] = sound_manager.play_golem_eruption
