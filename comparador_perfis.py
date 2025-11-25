#!/usr/bin/env python3
"""
Comparador de Perfis de Performance - Jogo Nave
==============================================

Este script compara dois arquivos de perfil (.prof) gerados pelo cProfile
para medir o impacto de otimizações no desempenho do jogo.

Uso:
    python comparador_perfis.py perfil_antes.prof perfil_depois.prof

Exemplo:
    python comparador_perfis.py jogo_original.prof jogo_otimizado.prof

O script gera um relatório detalhado mostrando:
- Funções que melhoraram performance
- Funções que pioraram performance
- Estatísticas gerais (tempo total, chamadas, etc.)
- Impacto percentual nas funções críticas
"""

import sys
import pstats
from typing import Dict, Any, Tuple, cast
import os


def load_profile(filename: str) -> pstats.Stats:
    """Carrega um arquivo de perfil do cProfile."""
    if not os.path.exists(filename):
        print(f"Erro: Arquivo '{filename}' não encontrado.")
        sys.exit(1)

    stats = pstats.Stats(filename)
    return stats


def get_function_stats(stats: pstats.Stats) -> Dict[str, Dict[str, Any]]:
    """Extrai estatísticas por função do perfil usando pstats.Stats diretamente."""
    function_data: Dict[str, Dict[str, Any]] = {}

    # Usar sort_stats e print_stats para obter dados estruturados
    stats.calc_callees()  # Calcular estatísticas completas

    # Acessar dados internos do pstats (cast para tipo conhecido)
    stats_dict = cast(
        Dict[Tuple[str, int, str], Tuple[int, int, float, float, Any]],
        getattr(stats, "stats"),
    )

    for func, func_vals in stats_dict.items():
        # func é (filename, line, name)
        filename = func[0]
        line = func[1]
        name = func[2]
        cc, nc, tt, ct, callers = func_vals
        cc = int(cc)
        nc = int(nc)
        tt = float(tt)
        ct = float(ct)

        func_name = f"{filename}:{line}({name})"

        function_data[func_name] = {
            "ncalls": nc,
            "tottime": tt,
            "percall": tt / nc if nc > 0 else 0.0,
            "cumtime": ct,
            "percall_cum": ct / nc if nc > 0 else 0.0,
            "filename_lineno": func_name,
        }

    return function_data


def compare_profiles(
    before_stats: pstats.Stats, after_stats: pstats.Stats
) -> Dict[str, Any]:
    """Compara dois perfis e calcula diferenças."""
    before_data: Dict[str, Dict[str, Any]] = get_function_stats(before_stats)
    after_data: Dict[str, Dict[str, Any]] = get_function_stats(after_stats)

    comparison: Dict[str, Any] = {
        "improved": [],
        "worsened": [],
        "new_functions": [],
        "removed_functions": [],
        "unchanged": [],
        "summary": {},
    }

    # Calcular tempo total (assegurar float)
    before_total: float = sum(float(func["tottime"]) for func in before_data.values())
    after_total: float = sum(float(func["tottime"]) for func in after_data.values())

    comparison["summary"] = {
        "before_total_time": before_total,
        "after_total_time": after_total,
        "time_difference": after_total - before_total,
        "time_improvement_percent": (
            ((before_total - after_total) / before_total * 100)
            if before_total > 0
            else 0.0
        ),
        "total_calls_before": int(
            sum(int(func["ncalls"]) for func in before_data.values())
        ),
        "total_calls_after": int(
            sum(int(func["ncalls"]) for func in after_data.values())
        ),
    }

    # Comparar funções comuns
    common_functions = set(before_data.keys()) & set(after_data.keys())

    for func_name in common_functions:
        before = before_data[func_name]
        after = after_data[func_name]

        time_diff: float = float(after["tottime"]) - float(before["tottime"])
        time_percent: float = (
            (time_diff / float(before["tottime"]) * 100)
            if float(before["tottime"]) > 0
            else 0.0
        )

        calls_diff: int = int(after["ncalls"]) - int(before["ncalls"])

        result: Dict[str, Any] = {
            "function": func_name,
            "before_time": float(before["tottime"]),
            "after_time": float(after["tottime"]),
            "time_difference": time_diff,
            "time_percent_change": time_percent,
            "before_calls": int(before["ncalls"]),
            "after_calls": int(after["ncalls"]),
            "calls_difference": calls_diff,
        }

        if abs(time_percent) < 1.0:  # Menos de 1% mudança
            comparison["unchanged"].append(result)
        elif time_diff < 0:  # Melhorou
            comparison["improved"].append(result)
        else:  # Piorou
            comparison["worsened"].append(result)

    # Funções novas
    for func_name in set(after_data.keys()) - common_functions:
        comparison["new_functions"].append(
            {
                "function": func_name,
                "time": float(after_data[func_name]["tottime"]),
                "calls": int(after_data[func_name]["ncalls"]),
            }
        )

    # Funções removidas
    for func_name in set(before_data.keys()) - common_functions:
        comparison["removed_functions"].append(
            {
                "function": func_name,
                "time": float(before_data[func_name]["tottime"]),
                "calls": int(before_data[func_name]["ncalls"]),
            }
        )

    # Ordenar por impacto - usar função com anotação para Pylance
    def _key_abs_time_percent(item: Dict[str, Any]) -> float:
        return abs(float(item.get("time_percent_change", 0.0)))

    comparison["improved"].sort(key=_key_abs_time_percent, reverse=True)
    comparison["worsened"].sort(key=_key_abs_time_percent, reverse=True)

    return comparison


def print_comparison_report(comparison: Dict[str, Any]):
    """Imprime um relatório detalhado da comparação."""
    print("=" * 80)
    print("RELATÓRIO DE COMPARAÇÃO DE PERFORMANCE - JOGO NAVE")
    print("=" * 80)

    summary = comparison["summary"]
    print(
        f"""
📊 RESUMO GERAL:
Tempo total - Antes: {summary['before_total_time']:.2f}s, Depois: {summary['after_total_time']:.2f}s
Diferença: {summary['time_difference']:+.2f}s
Melhoria: {summary['time_improvement_percent']:+.1f}%
Chamadas totais - Antes: {summary['total_calls_before']:.0f}, Depois: {summary['total_calls_after']:.0f}
"""
    )

    if summary["time_improvement_percent"] > 0:
        print(f"🟢 Performance melhorou em {summary['time_improvement_percent']:.1f}%")
    elif summary["time_improvement_percent"] < 0:
        print(
            f"🔴 Performance piorou em {abs(summary['time_improvement_percent']):.1f}%"
        )
    else:
        print("⚪ Performance mantida (sem mudança significativa)")

    print("\n" + "=" * 80)

    # Funções que melhoraram
    if comparison["improved"]:
        print("\n✅ FUNÇÕES QUE MELHORARAM PERFORMANCE:")
        print("-" * 80)
        for func in comparison["improved"][:10]:  # Top 10
            print(f"📈 {func['function']}")
            print(
                f"   Tempo: {func['before_time']:.3f}s → {func['after_time']:.3f}s ({func['time_difference']:+.3f}s)"
            )
            print(f"   Melhoria: {func['time_percent_change']:+.1f}%")
            print()

    # Funções que pioraram
    if comparison["worsened"]:
        print("\n❌ FUNÇÕES QUE PIORARAM PERFORMANCE:")
        print("-" * 80)
        for func in comparison["worsened"][:10]:  # Top 10
            print(f"📉 {func['function']}")
            print(
                f"   Tempo: {func['before_time']:.3f}s → {func['after_time']:.3f}s ({func['time_difference']:+.3f}s)"
            )
            print(f"   Piora: {func['time_percent_change']:+.1f}%")
            print()

    # Funções novas
    if comparison["new_functions"]:
        print("\n🆕 FUNÇÕES NOVAS:")
        print("-" * 80)
        for func in sorted(
            comparison["new_functions"], key=lambda x: x["time"], reverse=True
        )[:5]:
            print(
                f"➕ {func['function']}: {func['time']:.3f}s ({func['calls']:.0f} chamadas)"
            )
            print()

    # Funções removidas
    if comparison["removed_functions"]:
        print("\n🗑️  FUNÇÕES REMOVIDAS:")
        print("-" * 80)
        for func in sorted(
            comparison["removed_functions"], key=lambda x: x["time"], reverse=True
        )[:5]:
            print(
                f"➖ {func['function']}: {func['time']:.3f}s ({func['calls']:.0f} chamadas)"
            )
            print()

    print("\n" + "=" * 80)
    print("💡 RECOMENDAÇÕES:")
    print("-" * 80)

    if summary["time_improvement_percent"] > 5:
        print("🎉 Excelente! Otimizações trouxeram melhoria significativa!")
    elif summary["time_improvement_percent"] > 1:
        print("👍 Bom trabalho! Melhoria modesta mas positiva.")
    elif summary["time_improvement_percent"] < -5:
        print("⚠️  Atenção: Performance piorou significativamente. Revisar otimizações.")
    else:
        print(
            "🤔 Performance estável. Verificar se otimizações foram aplicadas corretamente."
        )

    # Análise específica do StarField
    starfield_improved = any(
        "StarField.draw" in func["function"] for func in comparison["improved"]
    )
    if starfield_improved:
        print("⭐ Otimização do StarField detectada e funcionando!")

    print("\nPara análise mais detalhada, execute:")
    print("python analisador_profundo.py <arquivo.prof>")


def main():
    if len(sys.argv) != 3:
        print(
            "Uso: python comparador_perfis.py <perfil_antes.prof> <perfil_depois.prof>"
        )
        print("\nExemplo:")
        print("python comparador_perfis.py jogo_original.prof jogo_otimizado.prof")
        sys.exit(1)

    before_file = sys.argv[1]
    after_file = sys.argv[2]

    print(f"Carregando perfil antes: {before_file}")
    before_stats = load_profile(before_file)

    print(f"Carregando perfil depois: {after_file}")
    after_stats = load_profile(after_file)

    print("Comparando perfis...")
    comparison = compare_profiles(before_stats, after_stats)

    print_comparison_report(comparison)


if __name__ == "__main__":
    main()
