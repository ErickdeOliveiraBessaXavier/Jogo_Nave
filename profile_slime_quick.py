#!/usr/bin/env python3
"""
Profiler simplificado para análise rápida de gargalos no slime drip.
"""

import cProfile
import pstats
import io
import pygame
import sys
from pathlib import Path

# Adicionar path do projeto
sys.path.insert(0, str(Path(__file__).parent))

from game.entities.slime_drip import SlimeDripPool


def profile_slime_quick(drip_count: int = 50, duration: float = 3.0):
    """Profile rápido do sistema slime drip."""
    print(f"🎯 Profiling SlimeDrip: {drip_count} gotas por {duration}s")
    print("=" * 60)

    pygame.init()
    screen = pygame.display.set_mode((1600, 900))
    clock = pygame.time.Clock()

    # Criar pool e spawnar gotas
    pool = SlimeDripPool(initial_size=drip_count)
    for i in range(drip_count):
        x = 400 + (i % 800)
        y = 50 + (i // 800) * 20
        pool.get(x, y, 1600, 900)

    # Profiling
    profiler = cProfile.Profile()
    profiler.enable()

    # Loop de teste
    start_time = pygame.time.get_ticks()
    frames = 0

    while (pygame.time.get_ticks() - start_time) / 1000.0 < duration:
        dt = clock.tick(120) / 1000.0

        # Operações críticas
        pool.update(dt)
        screen.fill((0, 0, 0))
        pool.draw(screen)
        pygame.display.flip()

        frames += 1

    profiler.disable()
    pygame.quit()

    # Análise dos resultados
    stats = pstats.Stats(profiler)
    stats.strip_dirs()
    stats.sort_stats('cumulative')

    print("\n📊 RESULTADOS:")
    print(f"Frames processados: {frames}")
    print(f"Duração: {duration:.1f}s")
    print(f"FPS médio: {frames/duration:.2f}")
    print("\n🔥 TOP GARGALOS (tempo cumulativo):")
    stats.print_stats(15)

    print("\n🎯 ANÁLISE slime_drip.py:")
    stats.print_stats('slime_drip')

    print("\n🖌️ ANÁLISE pygame.draw:")
    stats.print_stats('pygame.draw')

    # Identificar gargalos específicos
    print("\n🎯 DIAGNÓSTICO:")
    print("=" * 40)

    # Analisar stats programaticamente
    stats_dict = {}
    for stat in stats.stats.items():
        filename, line, func = stat[0]
        cc, nc, tt, ct, callers = stat[1]
        if 'slime_drip.py' in filename:
            stats_dict[f"{filename}:{line}({func})"] = ct

    if stats_dict:
        # Encontrar função mais lenta do slime_drip
        slowest_func = max(stats_dict.items(), key=lambda x: x[1])
        print(f"Função mais lenta: {slowest_func[0]} - {slowest_func[1]:.4f}s")
        # Verificar se é draw ou update
        if 'draw' in slowest_func[0]:
            print("💡 RECOMENDAÇÃO: Otimizar sistema de rendering (culling/LOD)")
        elif 'update' in slowest_func[0]:
            print("💡 RECOMENDAÇÃO: Investigar física/partículas")
        else:
            print("💡 RECOMENDAÇÃO: Investigar função específica")

    print("=" * 60)


if __name__ == "__main__":
    # Teste único
    profile_slime_quick(50, 3.0)
    print("\n✅ Profiling completo! Analise os gargalos identificados acima.")