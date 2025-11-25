#!/usr/bin/env python3
"""
Script de profiling detalhado para Jogo Nave.

Executa o jogo com cProfile para identificar gargalos de performance.

Uso:
    python profile_game.py [--duration SECONDS] [--output FILE]

Exemplo:
    python profile_game.py --duration 10 --output profile_results.prof
"""

import cProfile
import pstats
import io
import sys
import os
import argparse
from typing import List, Tuple

# Adicionar o diretório do jogo ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from performance_test import AutomatedGameApp
from game.core.difficulty import DifficultyPreset


def profile_game(duration: float = 10.0, output_file: str = "profile_results.prof"):
    """Executa profiling do jogo."""
    print(f"🔍 Iniciando profiling ({duration}s)...")

    # Configurar modo headless para evitar interferência visual
    os.environ["SDL_VIDEODRIVER"] = "dummy"

    # Criar profiler
    profiler = cProfile.Profile()

    try:
        # Iniciar profiling
        profiler.enable()

        # Executar teste automatizado
        app = AutomatedGameApp(DifficultyPreset.NORMAL, duration)
        results = app.run_performance_test()

        # Parar profiling
        profiler.disable()

        # Salvar resultados de profiling
        profiler.dump_stats(output_file)

        # Analisar e exibir top 20 funções mais custosas
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
        ps.print_stats(20)

        print("\n" + "=" * 60)
        print("🔬 TOP 20 FUNÇÕES MAIS CUSTOSAS (tempo cumulativo)")
        print("=" * 60)
        print(s.getvalue())

        # Salvar análise em arquivo de texto
        analysis_file = output_file.replace(".prof", "_analysis.txt")
        with open(analysis_file, "w", encoding="utf-8") as f:
            f.write("ANÁLISE DE PERFORMANCE - JOGO NAVE\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Duração do teste: {duration}s\n")
            f.write(f"FPS Médio: {results['fps']['average']:.1f}\n")
            f.write(
                f"Frame Time Médio: {results['frame_time_ms']['average']:.2f}ms\n\n"
            )
            f.write("TOP 20 FUNÇÕES MAIS CUSTOSAS:\n")
            f.write("-" * 30 + "\n")
            f.write(s.getvalue())

        print(f"💾 Arquivo de profiling salvo: {output_file}")
        print(f"📄 Análise salva em: {analysis_file}")

        # Recomendações baseadas nos resultados
        print("\n" + "=" * 60)
        print("💡 RECOMENDAÇÕES PARA OTIMIZAÇÃO")
        print("=" * 60)

        # Analisar funções críticas
        stats: pstats.Stats = pstats.Stats(profiler)
        stats.sort_stats("cumulative")

        # Obter as 10 funções mais custosas
        top_functions: List[Tuple[Tuple[str, int, str], float]] = []
        for func in stats.fcn_list[:10]:
            _, _, _, ct, _ = stats.stats[func]
            top_functions.append((func, ct))

        # Procurar por funções suspeitas
        collision_time: float = 0
        render_time: float = 0
        update_time: float = 0

        for func, cum_time in top_functions:
            func_name = str(func[2])
            if "collision" in func_name.lower():
                collision_time += cum_time
            elif "render" in func_name.lower() or "draw" in func_name.lower():
                render_time += cum_time
            elif "update" in func_name.lower():
                update_time += cum_time

        total_profiled_time = sum(ct for _, ct in top_functions)

        if collision_time > total_profiled_time * 0.3:
            print(
                "⚠️  ALTO: Colisões consomem muito tempo. Considere otimizar spatial grid."
            )
        if render_time > total_profiled_time * 0.4:
            print(
                "⚠️  ALTO: Renderização consome muito tempo. Verifique cache de texturas."
            )
        if update_time > total_profiled_time * 0.3:
            print("⚠️  ALTO: Updates consomem muito tempo. Otimize loops de entidades.")

        if results["fps"]["average"] < 50:
            print("🎯 PRIORIDADE: FPS baixo. Foco em otimizações gerais.")
        elif results["frame_time_ms"]["maximum"] > 30:
            print(
                "🎯 PRIORIDADE: Stuttering detectado. Verifique picos de performance."
            )

    except Exception as e:
        print(f"❌ Erro durante profiling: {e}")
        return 1

    return 0


def main():
    parser = argparse.ArgumentParser(description="Profiling detalhado do Jogo Nave")
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Duração do profiling em segundos (padrão: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="profile_results.prof",
        help="Arquivo de saída para os dados de profiling (padrão: profile_results.prof)",
    )

    args = parser.parse_args()
    return profile_game(args.duration, args.output)


if __name__ == "__main__":
    exit(main())
