import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.entities.rock_glider import RockGlider


def _part_center(enemy: RockGlider, part: str) -> tuple[float, float]:
    enemy._update_collision_regions()
    return enemy._rock_center if part == "rock" else enemy._bot_center


def test_rock_glider_rock_needs_three_hits_independent_from_bot() -> None:
    enemy = RockGlider(x=900.0, y=220.0, vx=120.0, vy=0.0)
    rock_hit = _part_center(enemy, "rock")

    for _ in range(2):
        points, part_destroyed, fully_destroyed, _center, part_name = enemy.take_part_damage(
            rock_hit[0], rock_hit[1], amount=1
        )
        assert points == 0
        assert part_destroyed is False
        assert fully_destroyed is False
        assert part_name == "rock"

    points, part_destroyed, fully_destroyed, _center, part_name = enemy.take_part_damage(
        rock_hit[0], rock_hit[1], amount=1
    )
    assert points == enemy.get_part_points_value("rock")
    assert part_destroyed is True
    assert fully_destroyed is False
    assert part_name == "rock"
    assert enemy._rock_destroyed is True
    assert enemy._bot_destroyed is False


def test_rock_glider_bot_needs_two_hits_independent_from_rock() -> None:
    enemy = RockGlider(x=900.0, y=240.0, vx=120.0, vy=0.0)
    bot_hit = _part_center(enemy, "bot")

    points, part_destroyed, fully_destroyed, _center, part_name = enemy.take_part_damage(
        bot_hit[0], bot_hit[1], amount=1
    )
    assert points == 0
    assert part_destroyed is False
    assert fully_destroyed is False
    assert part_name == "bot"

    points, part_destroyed, fully_destroyed, _center, part_name = enemy.take_part_damage(
        bot_hit[0], bot_hit[1], amount=1
    )
    assert points == enemy.get_part_points_value("bot")
    assert part_destroyed is True
    assert fully_destroyed is False
    assert part_name == "bot"
    assert enemy._bot_destroyed is True
    assert enemy._rock_destroyed is False


def test_rock_glider_entity_only_fully_dies_after_both_parts_break() -> None:
    enemy = RockGlider(x=920.0, y=260.0, vx=120.0, vy=0.0)
    rock_hit = _part_center(enemy, "rock")
    bot_hit = _part_center(enemy, "bot")

    for _ in range(3):
        enemy.take_part_damage(rock_hit[0], rock_hit[1], amount=1)

    assert enemy._fully_destroyed is False
    assert enemy.dead is False

    for _ in range(2):
        enemy.take_part_damage(bot_hit[0], bot_hit[1], amount=1)

    assert enemy._fully_destroyed is True
    assert enemy.dead is False

    # Permite finalizar a janela de animação final e remoção.
    for _ in range(8):
        enemy.update(0.1)

    assert enemy.dead is True


def test_rock_glider_rock_falls_with_gravity_if_bot_breaks_first() -> None:
    enemy = RockGlider(x=920.0, y=260.0, vx=120.0, vy=0.0)
    bot_hit = _part_center(enemy, "bot")

    # Destroi o bot primeiro (2 tiros).
    enemy.take_part_damage(bot_hit[0], bot_hit[1], amount=1)
    enemy.take_part_damage(bot_hit[0], bot_hit[1], amount=1)

    assert enemy._bot_destroyed is True
    assert enemy._rock_destroyed is False
    assert enemy._rock_falling is True

    y0 = enemy.y
    vy0 = enemy._rock_fall_vy
    enemy.update(0.2)
    y1 = enemy.y
    vy1 = enemy._rock_fall_vy
    enemy.update(0.2)
    y2 = enemy.y
    vy2 = enemy._rock_fall_vy

    # Em queda gravitacional: y aumenta (desce) e vy cresce ao longo do tempo.
    assert y1 > y0
    assert y2 > y1
    assert vy1 >= vy0
    assert vy2 > vy1


def test_rock_glider_clears_collision_box_when_fully_destroyed() -> None:
    enemy = RockGlider(x=920.0, y=260.0, vx=120.0, vy=0.0)
    enemy._update_collision_regions()
    rock_hit = _part_center(enemy, "rock")
    bot_hit = _part_center(enemy, "bot")

    for _ in range(3):
        enemy.take_part_damage(rock_hit[0], rock_hit[1], amount=1)
    for _ in range(2):
        enemy.take_part_damage(bot_hit[0], bot_hit[1], amount=1)

    assert enemy._fully_destroyed is True
    assert enemy.w == 0
    assert enemy.h == 0
    assert enemy.rect.width == 0
    assert enemy.rect.height == 0
