import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.entities.rock_glider import RockGlider


def test_rock_glider_always_moves_left_even_without_side_scroll_flag() -> None:
    enemy = RockGlider(x=1000.0, y=200.0)
    initial_x = enemy.x

    enemy.update(0.2, is_side_scroll=False)

    assert enemy.x < initial_x


def test_rock_glider_keeps_horizontal_direction_when_positive_vx_is_passed() -> None:
    enemy = RockGlider(x=900.0, y=220.0, vx=150.0)
    initial_x = enemy.x

    enemy.update(0.2, is_side_scroll=True)

    assert enemy.x < initial_x


def test_rock_glider_uses_oscillation_without_falling_downward_like_top_down() -> None:
    enemy = RockGlider(x=800.0, y=250.0)
    initial_y = enemy.y

    for _ in range(10):
        enemy.update(0.1)

    # Oscillation can move up or down, but should stay in bounded band around spawn Y.
    assert abs(enemy.y - initial_y) < 120.0
