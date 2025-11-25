#!/usr/bin/env python3
"""
Analisador Profundo de Profiling - Jogo Nave

Este script analisa arquivos .prof gerados pelo cProfile,
fornecendo insights detalhados sobre performance.
"""

import pstats
import io
from pathlib import Path
from typing import Any, cast


def analisar_prof_file(prof_file: str):
    """Analisa arquivo .prof com pstats para insights detalhados."""
    if not Path(prof_file).exists():
        print(f"❌ Arquivo não encontrado: {prof_file}")
        return

    print("=" * 80)
    print("🔬 ANÁLISE PROFUNDA DE PROFILING - JOGO NAVE")
    print("=" * 80)

    # Carregar dados de profiling
    stats: pstats.Stats = pstats.Stats(prof_file)

    # 1. Estatísticas gerais
    print("\n📊 ESTATÍSTICAS GERAIS:")
    print("-" * 40)

    # Capturar output do print_stats
    output = io.StringIO()
    stats.stream = output
    stats.print_stats(0)  # Apenas header
    header = output.getvalue().split("\n")[0]
    print(header)

    # Número total de chamadas
    total_calls = cast(int, stats.total_calls)
    print(f"📞 Total de chamadas de função: {total_calls:,}")

    # Tempo total
    total_time = cast(float, stats.total_tt)
    print(f"⏱️  Tempo total de execução: {total_time:.3f}s")
    print()

    # 2. Top 10 funções por tempo cumulativo
    print("🏆 TOP 10 FUNÇÕES POR TEMPO CUMULATIVO:")
    print("-" * 50)

    output = io.StringIO()
    stats.stream = output
    stats.sort_stats("cumulative").print_stats(10)
    lines = output.getvalue().split("\n")

    # Pular header e processar linhas de função
    for line in lines[4:14]:  # Linhas 4-13 contêm as top 10 funções
        if line.strip() and not line.startswith("   ncalls"):
            print(line)

    print()

    # 3. Top 10 funções por tempo próprio (excluindo chamadas)
    print("⚡ TOP 10 FUNÇÕES POR TEMPO PRÓPRIO:")
    print("-" * 50)

    output = io.StringIO()
    stats.stream = output
    stats.sort_stats("time").print_stats(10)
    lines = output.getvalue().split("\n")

    for line in lines[4:14]:
        if line.strip() and not line.startswith("   ncalls"):
            print(line)

    print()

    # 4. Análise de funções específicas
    print("🎯 ANÁLISE DE FUNÇÕES ESPECÍFICAS:")
    print("-" * 50)

    # Procurar por funções críticas
    critical_functions = [
        "pygame.display.flip",
        "fill",
        "blit",
        "draw",
        "update",
        "render",
    ]

    for func_name in critical_functions:
        func_stats: tuple[tuple[str, int, str], int, int, float, float] | None = None
        for func, (cc, nc, tt, ct, callers) in stats.stats.items():
            func = cast(tuple[str, int, str], func)
            if func_name in str(func[2]):
                func_stats = cast(
                    tuple[tuple[str, int, str], int, int, float, float],
                    (func, cc, nc, tt, ct),
                )
                break

        if func_stats:
            func: Any
            cc: int
            nc: int
            tt: float
            ct: float
            func, cc, nc, tt, ct = func_stats
            func_name_display = str(func[2]).split("/")[-1]  # Apenas nome da função
            print(
                f"   {func_name_display:<20} {cc:>6d} calls {tt:>6.3f}s own {ct:>6.3f}s cum ({ct/total_time*100:>5.1f}%)"
            )
    print()

    # 5. Recomendações baseadas na análise
    print("💡 RECOMENDAÇÕES DE OTIMIZAÇÃO:")
    print("-" * 50)

    # Analisar principais gargalos
    output = io.StringIO()
    stats.stream = output
    stats.sort_stats("cumulative").print_stats(5)
    top_functions = output.getvalue().split("\n")[4:9]

    pygame_time = 0
    render_time = 0
    update_time = 0

    for line in top_functions:
        if "pygame" in line.lower():
            pygame_time += 1
        if "render" in line.lower() or "draw" in line.lower():
            render_time += 1
        if "update" in line.lower():
            update_time += 1

    if pygame_time >= 2:
        print("🎨 PRIORIDADE: Operações Pygame consomem muito tempo")
        print("   → Considere reduzir chamadas de blit/fill")
        print("   → Implemente cache de surfaces")

    if render_time >= 2:
        print("🖼️  PRIORIDADE: Renderização é o gargalo principal")
        print("   → Otimize loops de renderização")
        print("   → Use surface pooling")

    if update_time >= 2:
        print("🔄 PRIORIDADE: Updates consomem muito tempo")
        print("   → Otimize lógica de entidades")
        print("   → Implemente spatial partitioning")

    # Calcular eficiência
    fps_estimado: float = total_calls / total_time if total_time > 0 else 0.0
    print("\n📈 EFICIÊNCIA GERAL:")
    print(f"   Chamadas por segundo: {fps_estimado:.0f}")
    print(f"   Tempo médio por chamada: {total_time/total_calls*1000:.3f}ms")
    print()
    print("🛠️  PRÓXIMAS AÇÕES:")
    print("-" * 50)
    print("1. Focar nas top 3 funções mais custosas")
    print("2. Implementar cache para operações repetitivas")
    print("3. Usar profiling para validar melhorias")
    print("4. Considerar algoritmos mais eficientes")

    print("\n" + "=" * 80)


def comparar_prof_files(file1: str, file2: str):
    """Compara dois arquivos de profiling."""
    print("=" * 80)
    print("⚖️  COMPARAÇÃO DE PROFILING")
    print("=" * 80)

    if not (Path(file1).exists() and Path(file2).exists()):
        print("❌ Um ou ambos os arquivos não existem")
        return

    stats1: pstats.Stats = pstats.Stats(file1)
    stats2: pstats.Stats = pstats.Stats(file2)

    # Comparar tempos totais
    time1 = cast(float, stats1.total_tt)
    time2 = cast(float, stats2.total_tt)

    calls1 = cast(int, stats1.total_calls)
    calls2 = cast(int, stats2.total_calls)

    print(f"📊 Arquivo 1 ({file1}):")
    print(f"   Tempo: {time1:.3f}s")
    print(f"   Chamadas: {calls1:,}")

    print(f"\n📊 Arquivo 2 ({file2}):")
    print(f"   Tempo: {time2:.3f}s")
    print(f"   Chamadas: {calls2:,}")

    # Diferenças
    time_diff: float = time2 - time1
    calls_diff: int = calls2 - calls1

    print("\n🔄 DIFERENÇAS:")
    print(f"   Tempo: {time_diff:+.3f}s")
    print(f"   Chamadas: {calls_diff:+,}")

    if time_diff < 0:
        print("✅ MELHORIA detectada no tempo de execução!")
    elif time_diff > 0:
        print("⚠️  REGRESSÃO detectada no tempo de execução!")
    else:
        print("➡️  Sem mudança significativa no tempo")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Análise profunda de profiling")
    parser.add_argument("prof_file", help="Arquivo .prof para analisar")
    parser.add_argument("--compare", help="Arquivo .prof para comparar")

    args = parser.parse_args()

    analisar_prof_file(args.prof_file)

    if args.compare:
        comparar_prof_files(args.prof_file, args.compare)


if __name__ == "__main__":
    main()
