import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.entities.bot_elemental import ElementalRobot


def test_elemental_robot_clears_collision_box_on_dying_transition() -> None:
    enemy = ElementalRobot(120.0, 140.0, start_visible=True)

    assert enemy.rect.width > 0
    assert enemy.rect.height > 0

    enemy._transition("DYING")
    enemy.update(0.1, 0.1, 0.0, 0.0)

    assert enemy.fsm_state == "DYING"
    assert enemy.dead is False
    assert enemy.rect.width == 0
    assert enemy.rect.height == 0
