#!/usr/bin/env python3
"""
Exemplo de como integrar profiling no jogo principal.

Este arquivo mostra como adicionar profiling ao loop principal do jogo
para monitorar performance em tempo real.
"""

import pygame
import sys
import time
from typing import Optional

# Import do profiler
from profiler import profiler

# Import do jogo (ajuste conforme necessário)
try:
    from game.app import Game
except ImportError:
    print(
        "❌ Não foi possível importar o jogo. Execute este script da pasta raiz do projeto."
    )
    sys.exit(1)


class ProfilingGame:
    """Versão do jogo com profiling integrado."""

    def __init__(self, enable_profiling: bool = True):
        self.enable_profiling = enable_profiling
        self.game: Optional[Game] = None
        self.running = False
        self.clock = pygame.time.Clock()

        # Controles de profiling
        self.profile_key_pressed = False
        self.memory_key_pressed = False

        # Estatísticas
        self.frame_count = 0
        self.last_fps_update = time.time()

    def initialize(self):
        """Inicializa o jogo e profiling."""
        print("🚀 Inicializando jogo com profiling...")

        if self.enable_profiling:
            profiler.start_memory_profiling()
            profiler.take_memory_snapshot("Game Start")

        # Inicializa Pygame e jogo
        pygame.init()
        self.game = Game()

        if self.enable_profiling:
            profiler.take_memory_snapshot("Game Initialized")

        print("✅ Jogo inicializado com sucesso!")

    def handle_profiling_input(self, event):
        """Processa input relacionado ao profiling."""
        if not self.enable_profiling:
            return

        if event.type == pygame.KEYDOWN:
            # F1: Toggle CPU profiling
            if event.key == pygame.K_F1:
                if not profiler.is_profiling:
                    profiler.start_cpu_profiling()
                    print(
                        "🔍 CPU profiling INICIADO (pressione F1 novamente para parar)"
                    )
                else:
                    profiler.stop_cpu_profiling("gameplay_profile.prof")
                    print("✅ CPU profiling FINALIZADO")

            # F2: Memory snapshot
            elif event.key == pygame.K_F2:
                profiler.take_memory_snapshot(f"Frame {self.frame_count}")
                print(f"📸 Memory snapshot tirado (frame {self.frame_count})")

            # F3: Performance report
            elif event.key == pygame.K_F3:
                profiler.print_performance_report()

            # F4: Force garbage collection
            elif event.key == pygame.K_F4:
                import gc

                collected = gc.collect()
                print(f"🗑️  Garbage collection: {collected} objetos coletados")

    @profiler.measure_function_time("main_loop")
    def run(self):
        """Loop principal do jogo com profiling."""
        self.running = True
        print("🎮 Iniciando loop principal...")
        print("📋 Controles de profiling:")
        print("   F1: Toggle CPU profiling")
        print("   F2: Tirar memory snapshot")
        print("   F3: Mostrar relatório de performance")
        print("   F4: Forçar garbage collection")
        print("   ESC: Sair")
        print()

        while self.running:
            dt = self.clock.tick(60) / 1000.0  # Delta time em segundos

            # Registra frame time para análise de FPS
            if self.enable_profiling:
                profiler.record_frame_time(dt)

            # Processa eventos
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    else:
                        self.handle_profiling_input(event)

            # Atualiza jogo
            if self.game:
                self.game.update(dt)

            # Renderiza
            if self.game:
                self.game.draw()

            # Atualiza display
            pygame.display.flip()

            # Estatísticas periódicas
            self.frame_count += 1
            current_time = time.time()
            if current_time - self.last_fps_update >= 5.0:  # A cada 5 segundos
                fps_stats = profiler.get_fps_stats()
                if fps_stats:
                    print(
                        f"📊 FPS: {fps_stats['fps_avg']:.1f} "
                        f"(min: {fps_stats['fps_min']:.1f}, "
                        f"max: {fps_stats['fps_max']:.1f})"
                    )
                self.last_fps_update = current_time

        self.cleanup()

    def cleanup(self):
        """Limpa recursos e finaliza profiling."""
        print("\n🔚 Finalizando jogo...")

        if self.enable_profiling:
            profiler.take_memory_snapshot("Game End")
            profiler.stop_memory_profiling()
            profiler.print_performance_report()

        pygame.quit()
        print("✅ Jogo finalizado!")


def main():
    """Função principal."""
    import argparse

    parser = argparse.ArgumentParser(description="Space Shooter com Profiling")
    parser.add_argument(
        "--no-profile", action="store_true", help="Desabilita profiling"
    )
    parser.add_argument(
        "--duration", type=int, default=0, help="Duração em segundos (0 = até ESC)"
    )

    args = parser.parse_args()

    # Cria jogo com profiling
    profiling_game = ProfilingGame(enable_profiling=not args.no_profile)

    try:
        profiling_game.initialize()
        profiling_game.run()
    except KeyboardInterrupt:
        print("\n⏹️  Interrompido pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro durante execução: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if profiling_game.enable_profiling:
            profiler.stop_cpu_profiling("final_profile.prof")


if __name__ == "__main__":
    main()
