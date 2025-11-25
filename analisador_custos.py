#!/usr/bin/env python3
"""
Analisador de Custos por Componente - Jogo Nave

Este script analisa os custos de performance por componente do jogo,
identificando onde otimizar para melhorar o FPS.
"""

import json
import time
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


def analisar_profiling(prof_file: str):
    """Analisa arquivo de profiling e identifica custos por componente."""
    analysis_file = prof_file.replace('.prof', '_analysis.txt')

    try:
        with open(analysis_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Arquivo de análise não encontrado: {analysis_file}")
        return {}

    # Extrair métricas básicas
    lines = content.split('\n')
    duration = 0
    fps = 0

    for line in lines:
        if 'Duração do teste:' in line:
            duration = float(line.split(':')[1].strip().replace('s', ''))
        elif 'FPS Médio:' in line:
            fps = float(line.split(':')[1].strip())

    # Analisar funções mais custosas
    custos_por_componente = {
        'Renderização': 0,
        'Sistema de Som': 0,
        'Gerenciamento de Entidades': 0,
        'Colisões': 0,
        'Sistema de Partículas': 0,
        'Interface/HUD': 0,
        'Outros': 0
    }

    # Procurar pelas linhas de função (após "filename:lineno(function)")
    in_function_list = False
    for line in lines:
        if 'filename:lineno(function)' in line:
            in_function_list = True
            continue
        elif in_function_list and line.strip() and not line.startswith('   ncalls'):
            if line.strip() == '':  # Linha vazia indica fim da lista
                break

            try:
                # Parse da linha: ncalls tottime percall cumtime percall filename:lineno(function)
                parts = line.split()
                if len(parts) >= 6:
                    cumtime = float(parts[3])  # tempo cumulativo
                    function_info = ' '.join(parts[5:])

                    # Categorizar por componente com mais detalhes
                    if any(x in function_info for x in ['renderer.py', 'blit', 'fill', 'draw']):
                        custos_por_componente['Renderização'] += cumtime
                    elif any(x in function_info.lower() for x in ['sound', 'music', 'audio']):
                        custos_por_componente['Sistema de Som'] += cumtime
                    elif any(x in function_info for x in ['entity_manager', 'meteor.py', 'bullet', 'explosion']):
                        custos_por_componente['Gerenciamento de Entidades'] += cumtime
                    elif any(x in function_info.lower() for x in ['collision', 'collisions']):
                        custos_por_componente['Colisões'] += cumtime
                    elif any(x in function_info.lower() for x in ['explosion', 'particle', 'effect']):
                        custos_por_componente['Sistema de Partículas'] += cumtime
                    elif any(x in function_info.lower() for x in ['hud', 'font', 'text', 'ui']):
                        custos_por_componente['Interface/HUD'] += cumtime
                    elif any(x in function_info for x in ['pygame.display.flip', 'display.flip']):
                        custos_por_componente['Display/Sync'] = custos_por_componente.get('Display/Sync', 0) + cumtime
                    elif any(x in function_info for x in ['threading', 'thread']):
                        custos_por_componente['Threading'] = custos_por_componente.get('Threading', 0) + cumtime
                    elif any(x in function_info for x in ['time.sleep', 'sleep']):
                        custos_por_componente['Sleep/Timing'] = custos_por_componente.get('Sleep/Timing', 0) + cumtime
                    else:
                        custos_por_componente['Outros'] += cumtime
            except (ValueError, IndexError):
                continue

    return {
        'duration': duration,
        'fps': fps,
        'custos_por_componente': custos_por_componente,
        'total_custo': sum(custos_por_componente.values())
    }


def gerar_relatorio_custos(analise):
    """Gera relatório detalhado dos custos por componente."""
    print("=" * 80)
    print("🔍 ANÁLISE DE CUSTOS POR COMPONENTE - JOGO NAVE")
    print("=" * 80)

    if not analise:
        print("❌ Nenhuma análise disponível")
        return

    print(f"⏱️  Duração do teste: {analise['duration']:.1f}s")
    print(f"🎯 FPS Médio: {analise['fps']:.1f}")
    print(f"📊 Total de tempo analisado: {analise['total_custo']:.3f}s")
    print()

    # Ordenar componentes por custo
    custos = analise['custos_por_componente']
    sorted_custos = sorted(custos.items(), key=lambda x: x[1], reverse=True)

    print("🎯 CUSTOS POR COMPONENTE (ordenado por impacto):")
    print("-" * 50)

    for componente, custo in sorted_custos:
        if custo > 0:
            porcentagem = (custo / analise['total_custo']) * 100
            fps_impact = custo / analise['duration'] * analise['fps']
            print(f"{componente:<25} {custo:>6.3f}s ({porcentagem:>5.1f}%) - Impacto: {fps_impact:>6.1f} FPS")
    print()
    print("💡 RECOMENDAÇÕES DE OTIMIZAÇÃO:")
    print("-" * 50)

    # Recomendações baseadas nos custos
    render_custo = custos.get('Renderização', 0)
    som_custo = custos.get('Sistema de Som', 0)
    entidades_custo = custos.get('Gerenciamento de Entidades', 0)

    if render_custo > analise['total_custo'] * 0.4:
        print("🎨 PRIORIDADE: Renderização consome muito tempo")
        print("   → Otimizar operações de blit e fill")
        print("   → Implementar cache de texturas")
        print("   → Reduzir resolução de renderização")

    if som_custo > analise['total_custo'] * 0.2:
        print("🔊 PRIORIDADE: Sistema de som custoso")
        print("   → Otimizar transições de música")
        print("   → Usar streaming para áudio longo")
        print("   → Reduzir frequência de updates de som")

    if entidades_custo > analise['total_custo'] * 0.15:
        print("👾 PRIORIDADE: Gerenciamento de entidades")
        print("   → Otimizar spatial grid")
        print("   → Implementar object pooling")
        print("   → Reduzir entidades simultâneas")

    if analise['fps'] < 50:
        print("⚡ PRIORIDADE GERAL: FPS baixo detectado")
        print("   → Foco em otimizações gerais")
        print("   → Considerar redução de efeitos visuais")

    print()
    print("🛠️ PRÓXIMAS AÇÕES:")
    print("-" * 50)
    print("1. Executar profiling focado no componente mais custoso")
    print("2. Implementar otimizações específicas")
    print("3. Testar impacto das mudanças")
    print("4. Repetir análise para validar melhorias")


def criar_grafico_custos(analise, output_file="custos_componentes.png"):
    """Cria gráfico visual dos custos por componente."""
    try:
        custos = analise['custos_por_componente']

        # Filtrar apenas componentes com custo > 0
        labels = []
        sizes = []
        for componente, custo in custos.items():
            if custo > 0:
                labels.append(componente)
                sizes.append(custo)

        if not sizes:
            print("❌ Nenhum dado para gráfico")
            return

        # Criar gráfico de pizza
        fig, ax = plt.subplots(figsize=(10, 8))
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%',
                                         startangle=90, shadow=True)

        ax.axis('equal')
        plt.title('Distribuição de Custos por Componente\n' +
                 '.1f'                 f'FPS Médio: {analise["fps"]:.1f}')

        # Melhorar aparência
        for text in texts:
            text.set_fontsize(10)
        for autotext in autotexts:
            autotext.set_fontsize(9)

        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"📊 Gráfico salvo em: {output_file}")

    except ImportError:
        print("⚠️  Matplotlib não instalado. Instale com: pip install matplotlib")
    except Exception as e:
        print(f"❌ Erro ao criar gráfico: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Análise de custos por componente")
    parser.add_argument(
        "--profile",
        type=str,
        default="analise_custosa.prof",
        help="Arquivo de profiling para analisar"
    )
    parser.add_argument(
        "--chart",
        action="store_true",
        help="Gerar gráfico visual dos custos"
    )

    args = parser.parse_args()

    # Analisar profiling
    analise = analisar_profiling(args.profile)

    if analise:
        gerar_relatorio_custos(analise)

        if args.chart:
            criar_grafico_custos(analise)
    else:
        print("❌ Falha na análise do arquivo de profiling")


if __name__ == "__main__":
    main()