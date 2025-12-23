#!/usr/bin/env python3
"""
Sistema de profiling simplificado para identificar gargalos de performance.

Esta versão usa apenas bibliotecas padrão do Python.
"""

import cProfile
import pstats
import time
from functools import wraps
from typing import Callable, Dict, List
import tracemalloc


class PerformanceProfiler:
    """Profiler principal para análise de performance."""

    def __init__(self):
        self.cpu_profiler = cProfile.Profile()
        self.memory_snapshots = []
        self.frame_times = []
        self.function_times = {}
        self.is_profiling = False

    def start_cpu_profiling(self):
        """Inicia profiling de CPU."""
        self.cpu_profiler.enable()
        self.is_profiling = True
        print("🔍 CPU profiling iniciado...")

    def stop_cpu_profiling(self, output_file: str = "profile_results.prof"):
        """Para profiling de CPU e salva resultados."""
        if not self.is_profiling:
            return

        self.cpu_profiler.disable()
        self.is_profiling = False

        # Salva dados brutos
        self.cpu_profiler.dump_stats(output_file)

        # Gera relatório simplificado
        stats = pstats.Stats(self.cpu_profiler)
        stats.sort_stats("cumulative")

        print("\n📊 TOP 20 FUNÇÕES MAIS LENTAS:")
        print("-" * 60)
        stats.print_stats(20)

        print(f"\n💾 Dados salvos em: {output_file}")
        print("Para análise detalhada: python -m pstats profile_results.prof")

    def start_memory_profiling(self):
        """Inicia profiling de memória."""
        tracemalloc.start()
        self.memory_snapshots = []
        print("🧠 Memory profiling iniciado...")

    def take_memory_snapshot(self, label: str = ""):
        """Tira snapshot da memória atual."""
        if not tracemalloc.is_tracing():
            return

        snapshot = tracemalloc.take_snapshot()
        self.memory_snapshots.append((label, snapshot, time.time()))

    def stop_memory_profiling(self):
        """Para profiling de memória e mostra relatório."""
        if not tracemalloc.is_tracing():
            return

        print("\n🧠 ANÁLISE DE MEMÓRIA:")
        print("-" * 60)

        if len(self.memory_snapshots) >= 2:
            # Compara primeiro e último snapshot
            first_label, first_snapshot, first_time = self.memory_snapshots[0]
            last_label, last_snapshot, last_time = self.memory_snapshots[-1]

            print(f"Comparando: {first_label} → {last_label}")
            print(".2f")

            # Top 10 alocações
            stats = last_snapshot.statistics("lineno")
            print("\n📈 TOP 10 ALOCAÇÕES DE MEMÓRIA:")
            for stat in stats[:10]:
                print(".1f")

        tracemalloc.stop()

    def measure_function_time(self, func_name: str):
        """Decorator para medir tempo de execução de funções."""

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                end_time = time.perf_counter()

                elapsed = end_time - start_time
                if func_name not in self.function_times:
                    self.function_times[func_name] = []
                self.function_times[func_name].append(elapsed)

                return result

            return wrapper

        return decorator

    def record_frame_time(self, dt: float):
        """Registra tempo de frame."""
        self.frame_times.append(dt)
        if len(self.frame_times) > 1000:  # Mantém apenas últimos 1000
            self.frame_times.pop(0)

    def get_fps_stats(self) -> Dict[str, float]:
        """Retorna estatísticas de FPS."""
        if not self.frame_times:
            return {}

        frame_times = [t for t in self.frame_times if t > 0]
        if not frame_times:
            return {}

        fps_values = [1.0 / t for t in frame_times]

        return {
            "fps_current": fps_values[-1] if fps_values else 0,
            "fps_avg": sum(fps_values) / len(fps_values),
            "fps_min": min(fps_values),
            "fps_max": max(fps_values),
            "frame_time_avg": sum(frame_times) / len(frame_times),
            "frame_time_max": max(frame_times),
        }

    def print_performance_report(self):
        """Imprime relatório completo de performance."""
        print("\n" + "=" * 80)
        print("📊 RELATÓRIO DE PERFORMANCE")
        print("=" * 80)

        # FPS Stats
        fps_stats = self.get_fps_stats()
        if fps_stats:
            print("🎮 FPS STATISTICS:")
            print(".1f")
            print(".1f")
            print(".1f")
            print(".1f")
            print(".3f")
            print(".3f")

        # Function timing
        if self.function_times:
            print("\n⚡ FUNCTION TIMING (últimas execuções):")
            for func_name, times in sorted(self.function_times.items()):
                if times:
                    avg_time = sum(times) / len(times)
                    max_time = max(times)
                    call_count = len(times)
                    print(".4f")

        print("=" * 80)


# Instância global do profiler
profiler = PerformanceProfiler()


def profile_function(func_name: str = None):
    """Decorator para profiling de funções."""

    def decorator(func: Callable) -> Callable:
        name = func_name or f"{func.__module__}.{func.__qualname__}"
        return profiler.measure_function_time(name)(func)

    return decorator


def quick_profile(func: Callable) -> Callable:
    """Decorator simples para profiling rápido."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        print(".4f")
        return result

    return wrapper


def profile_slime_drip():
    """Profile específico do sistema de slime drip."""
    print("🎯 Profiling sistema SlimeDrip...")

    profiler.start_cpu_profiling()
    profiler.start_memory_profiling()

    # Import aqui para evitar circular imports
    from game.entities.slime_drip import SlimeDrippingEffect

    # Simula uso típico
    effect = SlimeDrippingEffect(800, 600)

    # Simula alguns segundos de gameplay
    for i in range(300):  # ~5 segundos a 60 FPS
        effect.update(1 / 60, 400, 300, 50, 400, 300)

        if i % 60 == 0:  # A cada segundo
            profiler.take_memory_snapshot(f"Frame {i}")

    profiler.stop_cpu_profiling("slime_drip_profile.prof")
    profiler.stop_memory_profiling()


def profile_entity_manager():
    """Profile específico do entity manager."""
    print("🎯 Profiling EntityManager...")

    profiler.start_cpu_profiling()

    # Import aqui para evitar circular imports
    from game.systems.entity_manager import EntityManager
    from game.core.config import config as Config

    manager = EntityManager()

    # Simula criação e atualização de entidades
    for i in range(1000):
        # Spawn algumas entidades
        manager.spawn_explosion(400, 300, 20)
        manager.spawn_powerup(400, 300)

        # Update
        manager.update(1 / 60)

        if i % 100 == 0:
            print(f"  Processado {i} frames...")

    profiler.stop_cpu_profiling("entity_manager_profile.prof")


if __name__ == "__main__":
    print("🔧 PERFORMANCE PROFILER PARA SPACE SHOOTER")
    print("=" * 50)
    print("Comandos disponíveis:")
    print("  python profiler.py slime_drip    - Profile sistema de slime")
    print("  python profiler.py entities      - Profile entity manager")
    print("  python profiler.py full          - Profile jogo completo")
    print()

    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "slime_drip":
            profile_slime_drip()
        elif command == "entities":
            profile_entity_manager()
        elif command == "full":
            print("🚧 Full profiling ainda não implementado")
        else:
            print(f"❌ Comando desconhecido: {command}")
    else:
        print("💡 Use: python profiler.py <comando>")
        print("\n📖 Para profiling durante gameplay:")
        print("   1. Importe: from profiler import profiler")
        print("   2. Inicie: profiler.start_cpu_profiling()")
        print("   3. Pare: profiler.stop_cpu_profiling()")
        print("   4. Analise: profiler.print_performance_report()")
