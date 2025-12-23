#!/usr/bin/env python3
"""
Profiler dedicado para sistema de slime drips.
Baseado no guia de otimização real.
"""

import cProfile
import pstats
import io
import pygame
import sys
from pathlib import Path

# Adicionar path do projeto
sys.path.insert(0, str(Path(__file__).parent))

from game.entities.slime_drip import SlimeDripPool, SlimeDrippingEffect


class SlimeProfiler:
    """Profiler dedicado para sistema de slime drips."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1600, 900))
        self.clock = pygame.time.Clock()

    def profile_pool_operations(self, drip_count: int, duration: float = 10.0):
        """Profile operações do pool com N gotas por X segundos."""
        print(f"\n{'='*60}")
        print(f"PROFILING: {drip_count} gotas por {duration}s")
        print(f"{'='*60}\n")

        pool = SlimeDripPool(initial_size=drip_count)

        # Spawnar gotas
        for i in range(drip_count):
            x = 400 + (i % 800)
            y = 50 + (i // 800) * 20
            pool.get(x, y, 1600, 900)

        # Setup profiler
        profiler = cProfile.Profile()
        profiler.enable()

        # Loop de simulação
        start = pygame.time.get_ticks()
        frames = 0

        while (pygame.time.get_ticks() - start) / 1000.0 < duration:
            dt = self.clock.tick(120) / 1000.0

            # Operações que queremos profilear
            pool.update(dt)

            self.screen.fill((0, 0, 0))
            pool.draw(self.screen)
            pygame.display.flip()

            frames += 1

        # Parar profiler
        profiler.disable()

        # Análise dos resultados
        self._analyze_results(profiler, frames, duration)

        pygame.quit()

    def _analyze_results(self, profiler: cProfile.Profile, frames: int, duration: float):
        """Analisa e apresenta resultados do profiling."""

        # Criar string buffer para output
        s = io.StringIO()

        # Ordenar por tempo cumulativo
        stats = pstats.Stats(profiler, stream=s)
        stats.strip_dirs()
        stats.sort_stats('cumulative')

        print("\n📈 MÉTRICAS GERAIS:")
        print(f"   Frames processados: {frames}")
        print(".1f")
        print(".2f")

        print("\n🔥 TOP 20 FUNÇÕES MAIS LENTAS (tempo cumulativo):")
        stats.print_stats(20)

        # Ordenar por tempo próprio (time)
        stats.sort_stats('time')
        print("\n⚡ TOP 20 FUNÇÕES MAIS LENTAS (tempo próprio):")
        stats.print_stats(20)

        # Funções específicas do slime_drip
        print("\n🎯 ANÁLISE ESPECÍFICA - slime_drip.py:")
        stats.print_stats('slime_drip')

        # Funções de desenho
        print("\n🖌️ ANÁLISE ESPECÍFICA - Operações de Draw:")
        stats.print_stats('draw')

        # Salvar relatório completo
        output_file = f"profile_report_{frames}_frames.txt"
        with open(output_file, 'w') as f:
            stats = pstats.Stats(profiler, stream=f)
            stats.strip_dirs()
            stats.sort_stats('cumulative')
            stats.print_stats()

        print(f"\n💾 Relatório completo salvo em: {output_file}")


def main():
    """Executa suite de profiling."""
    profiler = SlimeProfiler()

    # Testar com diferentes quantidades
    test_cases = [
        (50, 5.0),   # 50 gotas, 5 segundos
        (100, 5.0),  # 100 gotas, 5 segundos
        (200, 5.0),  # 200 gotas, 5 segundos (stress test)
    ]

    for drip_count, duration in test_cases:
        profiler.profile_pool_operations(drip_count, duration)

        input("\nPressione Enter para continuar para o próximo teste...")

    print("\n✅ Profiling completo! Verifique os arquivos profile_report_*.txt")


if __name__ == "__main__":
    main()