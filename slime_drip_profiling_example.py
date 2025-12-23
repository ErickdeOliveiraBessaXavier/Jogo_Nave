#!/usr/bin/env python3
"""
Exemplo de como adicionar profiling a funções específicas do jogo.

Este arquivo demonstra como instrumentar o sistema de slime drip
com profiling para identificar gargalos.
"""

# Exemplo 1: Adicionando profiling ao SlimeDripPool.update()
# Modifique o arquivo slime_drip.py:

import time
from typing import List, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass

# Adicione import do profiler no topo
from ..core.profiler import profiler  # Supondo que profiler.py esteja em core/

# ... resto dos imports ...

class SlimeDripPool:
    # ... código existente ...

    def update(self, dt: float) -> None:
        """Atualiza todas as gotas ativas e reconstrói spatial grid."""
        start_time = time.perf_counter()

        # Atualizar todas as gotas
        drip_update_time = 0.0
        to_release: List[SlimeDrip] = []

        for drip in self.active:
            drip_start = time.perf_counter()
            drip.update(dt)
            drip_update_time += time.perf_counter() - drip_start

            if drip.dead:
                to_release.append(drip)

        # Liberar gotas mortas
        release_time = time.perf_counter()
        for drip in to_release:
            self.release(drip)
        release_time = time.perf_counter() - release_time

        # Reconstruir spatial grid se houver gotas ativas
        spatial_time = 0.0
        if self.active:
            spatial_start = time.perf_counter()
            self.spatial_grid.clear()
            batch_data: List[Tuple[SlimeDrip, float, float, float, float]] = []
            for drip in self.active:
                x, y, w, h = drip.get_bounds()
                batch_data.append((drip, x, y, w, h))
            self.spatial_grid.insert_batch(batch_data)
            spatial_time = time.perf_counter() - spatial_start

        total_time = time.perf_counter() - start_time

        # Registra tempos para análise (apenas se profiling estiver ativo)
        if profiler.is_profiling:
            profiler.function_times.setdefault('SlimeDripPool.update', []).append(total_time)
            profiler.function_times.setdefault('SlimeDripPool.drips', []).append(drip_update_time)
            profiler.function_times.setdefault('SlimeDripPool.spatial', []).append(spatial_time)
            profiler.function_times.setdefault('SlimeDripPool.release', []).append(release_time)

        # Log detalhado se tempo for alto (> 16ms = 60 FPS)
        if total_time > 0.016:
            print(f"⚠️  SlimeDripPool.update lento: {total_time:.4f}s "
                  f"(drips: {drip_update_time:.4f}s, "
                  f"spatial: {spatial_time:.4f}s, "
                  f"release: {release_time:.4f}s)")

    # ... resto do código ...


# Exemplo 2: Profiling com decorator (mais limpo)

from profiler import profile_function

class SlimeDripPool:
    # ... código existente ...

    @profile_function("SlimeDripPool.update")
    def update(self, dt: float) -> None:
        """Atualiza todas as gotas ativas e reconstrói spatial grid."""
        # ... código existente (sem mudanças) ...

    @profile_function("SlimeDripPool.draw")
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha as gotas."""
        # ... código existente ...

    # ... resto do código ...


# Exemplo 3: Profiling condicional baseado em configuração

class SlimeDripPool:
    # ... código existente ...

    def update(self, dt: float) -> None:
        """Atualiza todas as gotas ativas e reconstrói spatial grid."""

        # Profiling condicional (apenas em debug mode)
        if Config.DEBUG_MODE and profiler.is_profiling:
            start_time = time.perf_counter()
            # ... lógica de update ...
            total_time = time.perf_counter() - start_time

            if total_time > 0.016:  # Log apenas se lento
                print(f"🐌 SlimeDripPool lento: {total_time:.4f}s "
                      f"({len(self.active)} gotas ativas)")
        else:
            # Código normal sem profiling
            # ... lógica de update ...

    # ... resto do código ...


# Exemplo 4: Profiling de memória para detectar leaks

class SlimeDripPool:
    # ... código existente ...

    def update(self, dt: float) -> None:
        """Atualiza todas as gotas ativas e reconstrói spatial grid."""

        # Snapshot de memória antes
        if profiler.memory_profiling_active:
            profiler.take_memory_snapshot(f"SlimeDripPool.update_start_{len(self.active)}")

        # ... lógica normal ...

        # Snapshot de memória depois
        if profiler.memory_profiling_active:
            profiler.take_memory_snapshot(f"SlimeDripPool.update_end_{len(self.active)}")

    # ... resto do código ...


# Exemplo 5: Função utilitária para benchmarking

def benchmark_slime_drip_system():
    """Benchmark específico do sistema de slime drip."""
    from game.entities.slime_drip import SlimeDrippingEffect

    print("🧪 Benchmarking SlimeDrip system...")

    # Teste com diferentes quantidades de gotas
    test_scenarios = [
        (5, "Poucas gotas"),
        (15, "Quantidade normal"),
        (30, "Muitas gotas - stress test")
    ]

    for max_drips, description in test_scenarios:
        print(f"\n📊 Testando: {description} (max {max_drips} gotas)")

        # Override config temporariamente
        original_max = Config.SLIME_DRIP_MAX_ACTIVE
        Config.SLIME_DRIP_MAX_ACTIVE = max_drips

        effect = SlimeDrippingEffect(800, 600)

        # Benchmark por 10 segundos
        frame_times = []
        start_time = time.time()

        while time.time() - start_time < 10.0:
            frame_start = time.perf_counter()

            # Simula boss position
            effect.update(1/60, 400, 300, 50, 400, 300)

            frame_end = time.perf_counter()
            frame_times.append(frame_end - frame_start)

        # Calcula estatísticas
        avg_frame_time = sum(frame_times) / len(frame_times)
        fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0

        print(f"   FPS médio: {fps:.1f}")
        print(f"   Frame time médio: {avg_frame_time*1000:.2f}ms")
        print(f"   Gotas ativas: {effect.drip_pool.get_active_count()}")

        # Restaura config
        Config.SLIME_DRIP_MAX_ACTIVE = original_max

    print("\n✅ Benchmark concluído!")


if __name__ == "__main__":
    benchmark_slime_drip_system()