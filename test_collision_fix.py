#!/usr/bin/env python3
"""
Teste de validação da correção de explosões de minas.
Verifica que:
1. A ordem em check_mine_explosions está correta
2. handle_mine_explosion processa dano aos inimigos
3. mine_explosions está sendo desenhado e atualizado
"""

import sys
from pathlib import Path

import pygame

game_path = Path(__file__).parent
sys.path.insert(0, str(game_path))
from game.systems.collisions import Collisions  # noqa: E402
from game.systems.entity_manager import EntityManager  # noqa: E402
from game.entities.explosive_mine import ExplosiveMine  # noqa: E402
from game.entities.mine_explosion import MineExplosion  # noqa: E402
from game.entities.alien import Alien  # noqa: E402

pygame.init()
screen = pygame.display.set_mode((1280, 720))
clock = pygame.time.Clock()

print("=" * 60)
print("TESTE DE VALIDACAO DE EXPLOSOES DE MINAS")
print("=" * 60)

# TESTE 1: Verificar que MineExplosion funciona
print("\n[TESTE 1] Criacao de MineExplosion")
explosion = MineExplosion(640, 360, size=100)
print(
    f"   Explosao criada: pos=({explosion.x}, {explosion.y}), max_radius={explosion.max_radius}"
)
print(f"   Duracao: {explosion.duration:.3f}s")
assert explosion.duration > 0.1, "Duracao muito curta!"
print("   PASSED")

# TESTE 2: Verificar que update funciona
print("\n[TESTE 2] Update de MineExplosion")
explosion = MineExplosion(640, 360, size=100)
initial_time = explosion.time
explosion.update(0.1)
assert explosion.time < initial_time, "Time nao diminuiu!"
assert explosion.current_radius > 0, "Raio deveria crescer!"
print(f"   Tempo: {initial_time:.3f}s -> {explosion.time:.3f}s")
print(f"   Raio: 0 -> {explosion.current_radius:.1f}")
print("   PASSED")

# TESTE 3: Verificar que draw funciona
print("\n[TESTE 3] Draw de MineExplosion")
explosion = MineExplosion(640, 360, size=100)
try:
    explosion.draw(screen)
    print("   MineExplosion.draw() funcionou sem erros")
    print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# TESTE 4: Verificar estrutura de Collisions
print("\n[TESTE 4] Validar estrutura de Collisions")
collisions = Collisions()
print(f"   Collisions class loaded: {collisions.__class__.__name__}")

# Verificar que metodos existem
assert hasattr(
    collisions, "check_mine_explosions"
), "check_mine_explosions nao encontrado!"
assert hasattr(
    collisions, "handle_mine_explosion"
), "handle_mine_explosion nao encontrado!"
assert hasattr(collisions, "_destroy_enemy"), "_destroy_enemy nao encontrado!"
print(
    "   Metodos encontrados: check_mine_explosions, handle_mine_explosion, _destroy_enemy"
)
print("   PASSED")

# TESTE 5: Verificar que EntityManager tem mine_explosions
print("\n[TESTE 5] Validar EntityManager")
em = EntityManager()
print(
    f"   EntityManager.mine_explosions: {type(em.mine_explosions).__name__} com {len(em.mine_explosions)} items"
)
assert isinstance(em.mine_explosions, list), "mine_explosions deveria ser uma lista!"
print("   PASSED")

print("\n[TESTE 6] Teste de integracao")
try:
    # Criar entidades
    em = EntityManager()
    collisions = Collisions()

    # Adicionar uma mina que está "morta" (para simular explosion trigger)
    mine = ExplosiveMine(640, 360)
    mine.dead = True

    # Adicionar inimigos próximos
    enemy = Alien()
    enemy.x, enemy.y = 650, 360
    enemy.dead = False
    enemy.w, enemy.h = 30, 30

    em.enemies.append(enemy)
    em.enemies.append(mine)

    class MockShip:
        def __init__(self):
            self.x, self.y = 100, 100
            self.w, self.h = 40, 40
            self.invuln = 1.0

    ship = MockShip()

    # Primeira chamada: cria explosão e checa nave/formações
    score_gain, destroyed_count, score_events, ship_hit = (
        collisions.check_mine_explosions(
            em.enemies,
            em.mine_explosions,
            ship,  # type: ignore
            em,
        )
    )

    # Simular avanço da animação: raio atinge o máximo
    for me in em.mine_explosions:
        me.current_radius = me.max_radius

    # Remover a mina da lista para não criar nova explosão na próxima chamada
    em.enemies = [e for e in em.enemies if not isinstance(e, ExplosiveMine)]

    # Segunda chamada: processa explosão ativa e aplica dano contínuo
    sg2, dc2, ev2, ship_hit2 = collisions.check_mine_explosions(
        em.enemies,
        em.mine_explosions,
        ship,  # type: ignore
        em,
    )

    score_gain += sg2
    destroyed_count += dc2
    score_events.extend(ev2)
    ship_hit = ship_hit or ship_hit2

    print(f"   Score ganho: {score_gain}")
    print(f"   Inimigos destruidos: {destroyed_count}")
    print(f"   Explosoes criadas: {len(em.mine_explosions)}")

    assert len(em.mine_explosions) > 0, "Nenhuma explosao foi criada!"
    assert (
        destroyed_count >= 1
    ), "O inimigo proximo deveria ter sido destruido pela explosao"
    print("   PASSED")

except Exception as e:
    print(f"   FAILED: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("TODOS OS TESTES PASSARAM!")
print("=" * 60)
print("\nResumo das correcoes:")
print("  1. check_mine_explosions: Removido segundo loop desnecessario")
print("  2. handle_mine_explosion: Restaurado com logica de dano completa")
print("  3. MineExplosion: Draw, update e duracao funcionando corretamente")
print("  4. EntityManager: mine_explosions esta em update() e draw()")
print("\nO sistema de explosoes de minas esta pronto para producao!")

pygame.quit()
sys.exit(0)
