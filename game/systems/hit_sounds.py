"""Bound methods do sound_manager para uso em HitResult.sound.

Evita dispatch por string (ex.: getattr(sound_manager, f"play_{name}")) e
dá completion no IDE. Cada constante é um Callable[[], None] já bound — o
custo de chamada é idêntico a sound_manager.play_X().
"""

from __future__ import annotations

from ..core.sound import sound_manager

EXPLOSION_ALIEN = sound_manager.play_explosion_alien
EXPLOSION_ASTEROID = sound_manager.play_explosion_asteroid
EXPLOSION_BOSS = sound_manager.play_explosion_boss
BOSS_DAMAGE = sound_manager.play_boss_damage

# StoneGolemBoss
GOLEM_MINE_TIMER = sound_manager.play_golem_mine_timer
GOLEM_STOP_MINE_TIMER = sound_manager.stop_golem_mine_timer
GOLEM_CHARGING = sound_manager.play_boss_laser_charging
GOLEM_STOP_CHARGING = sound_manager.stop_boss_laser_charging
GOLEM_SWEEP_LASER = sound_manager.play_boss_laser_fire
GOLEM_ORB_PURPLE = sound_manager.play_golem_orb_purple
GOLEM_ERUPTION = sound_manager.play_golem_eruption
