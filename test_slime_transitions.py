#!/usr/bin/env python3
"""
Test script for SlimeBoss transitions.
Simulates health reduction to test state transitions.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pygame
pygame.init()
pygame.display.set_mode((1, 1))  # Minimal display for image loading

from game.entities.slime_boss import SlimeBoss
from game.core.config import config as Config, SlimeBossState

def test_transitions():
    """Test SlimeBoss state transitions by simulating health reduction."""
    print("Testing SlimeBoss Transitions")
    print("=" * 40)

    # Create boss
    boss = SlimeBoss(0, 0)
    print("Initial state:", boss.current_state)
    print("Initial health:", boss.health, "/", boss.max_health)
    print()

    # Wait for boss to enter (ENTERING -> STAGE_1_NORMAL)
    print("Waiting for boss to enter...")
    while boss.current_state == SlimeBossState.ENTERING:
        boss.update(0.1, 400.0, 300.0)
    print("Boss entered, state:", boss.current_state)
    print()

    # Test Stage 1: 100% → 75% HP
    print("Stage 1: Reducing health from 100% to 75%")
    target_health = boss.max_health * 0.75
    boss.health = target_health
    boss.update(0.1, 400.0, 300.0)  # Update to trigger transition check
    print("Health:", boss.health, "/", boss.max_health, "(", boss.health/boss.max_health*100, "%)")
    print("State:", boss.current_state)
    print()

    # Wait for drips to finish (WAITING_DRIPS)
    print("Waiting for drips to finish...")
    while boss.current_state == SlimeBossState.WAITING_DRIPS:  # type: ignore
        boss.update(0.1, 400.0, 300.0)
    print("After waiting: State =", boss.current_state)
    print()

    # Should transition to RETREATING
    print("Should transition to RETREATING")
    boss.update(0.1, 400.0, 300.0)
    print("State:", boss.current_state)
    print()

    # Simulate retreating finished (set health or something)
    # Actually, retreating might have a timer, but for test, force to STAGE_2_HOMING
    print("Forcing to STAGE_2_HOMING for test")
    boss.current_state = SlimeBossState.STAGE_2_HOMING
    boss.current_stage_config = Config.SLIME_BOSS_STAGES[boss.current_state]
    print("State:", boss.current_state)
    print()

    # Stage 2 Homing (15s)
    print("Stage 2 Homing: Simulating 15 seconds")
    for _ in range(150):  # 15 seconds at 10 fps
        boss.update(0.1, 400.0, 300.0)
        if boss.current_state != SlimeBossState.STAGE_2_HOMING:
            break
    print("After 15s: State =", boss.current_state)
    print()

    # Stage 3: 75% → 20% HP
    print("Stage 3: Reducing health from 75% to 20%")
    target_health = boss.max_health * 0.20
    boss.health = target_health
    boss.update(0.1, 400.0, 300.0)
    print("Health:", boss.health, "/", boss.max_health, "(", boss.health/boss.max_health*100, "%)")
    print("State:", boss.current_state)
    print()

    # Wait for drips
    print("Waiting for drips...")
    while boss.current_state == SlimeBossState.WAITING_DRIPS:  # type: ignore
        boss.update(0.1, 400.0, 300.0)
    print("After waiting: State =", boss.current_state)
    print()

    # Should transition to RETREATING then STAGE_4_HOMING
    print("Should transition to RETREATING then STAGE_4_HOMING")
    boss.update(0.1, 400.0, 300.0)
    print("State:", boss.current_state)
    print()

    # Force to STAGE_4_HOMING
    boss.current_state = SlimeBossState.STAGE_4_HOMING
    boss.current_stage_config = Config.SLIME_BOSS_STAGES[boss.current_state]
    print("State:", boss.current_state)
    print()

    # Stage 4 Homing (25s)
    print("Stage 4 Homing: Simulating 25 seconds")
    for _ in range(250):  # 25 seconds at 10 fps
        boss.update(0.1, 400.0, 300.0)
        if boss.current_state != SlimeBossState.STAGE_4_HOMING:
            break
    print("After 25s: State =", boss.current_state)
    print()

    # Stage 5 Final: until death
    print("Stage 5 Final: Reducing health to 0")
    boss.health = 0
    boss.update(0.1, 400.0, 300.0)
    print("Health:", boss.health, "/", boss.max_health)
    print("State:", boss.current_state)
    print("Dead:", boss.dead)
    print()

    print("Test completed!")

if __name__ == "__main__":
    test_transitions()