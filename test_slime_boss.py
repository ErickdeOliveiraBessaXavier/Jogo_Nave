import pygame
from game.entities.slime_boss import SlimeBoss
from game.core.config import config as Config


def test_slime_boss_draw_and_update():
    pygame.init()
    surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
    boss = SlimeBoss(0, 10)

    # Simulate entry finished
    boss.state = "active"
    boss.y = boss.target_y

    # Update and draw should not raise
    boss.update(0.016, Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2)
    boss.draw(surface)

    pygame.quit()
