
import os
import sys

# Adicionar o diretório raiz ao path para importar o game
sys.path.append(os.getcwd())

import pygame
from game.core.config import config
from game.entities.giant_meteor_boss import GiantMeteorBoss
from game.systems.entity_manager import EntityManager

def test_boss_entry():
    pygame.init()
    # Mock do EntityManager e config
    em = EntityManager(is_side_scroll=True)
    
    boss = GiantMeteorBoss(0, 0)
    boss.is_side_scroll = True
    
    print(f"Initial state: {boss.state}, y: {boss.y}, target_y: {boss.target_y}")
    
    dt = 1/60.0
    for i in range(1200):  # 20 seconds at 60 FPS
        boss.update(dt, em)
        if i % 60 == 0:
            print(f"Time: {i/60}s, y: {boss.y:.2f}, state: {boss.state}")
        
        if boss.state == "falling":
            print(f"Reached falling state at {i/60}s")
            break
    
    if boss.state != "falling":
        print("FAILED to reach falling state")
    else:
        print("SUCCESS: reached falling state")

if __name__ == "__main__":
    test_boss_entry()
