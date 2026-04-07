#!/usr/bin/env python3
"""
Script para analisar o uso das cores definidas em colors.py.

Este script:
1. Extrai todas as cores definidas no módulo colors
2. Busca por referências a essas cores em todos os arquivos Python do projeto
3. Gera um relatório detalhado sobre o uso das cores
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set


def extract_color_definitions(colors_file_path: str) -> Set[str]:
    """
    Extrai todos os nomes das cores definidas no módulo colors usando AST.

    Args:
        colors_file_path: Caminho para o arquivo colors.py

    Returns:
        Conjunto com os nomes das cores definidas
    """
    color_names: Set[str] = set()

    try:
        with open(colors_file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            # Procurar por Assign nodes (atribuições simples)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Verificar se é uma cor (verificar se o valor é uma tupla de 3 inteiros)
                        if (
                            isinstance(node.value, ast.Tuple)
                            and len(node.value.elts) == 3
                        ):
                            # Verificar se todos os elementos são inteiros
                            if all(
                                isinstance(elt, ast.Constant)
                                and isinstance(elt.value, int)
                                for elt in node.value.elts
                            ):
                                color_names.add(target.id)
                        # Também aceitar RAINBOW_COLORS que é uma lista
                        elif (
                            isinstance(node.value, ast.List)
                            and target.id == "RAINBOW_COLORS"
                        ):
                            color_names.add(target.id)

            # Procurar por AnnAssign nodes (atribuições com anotações de tipo)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                # Verificar se é uma cor (verificar se o valor é uma tupla de 3 inteiros)
                if isinstance(node.value, ast.Tuple) and len(node.value.elts) == 3:
                    # Verificar se todos os elementos são inteiros
                    if all(
                        isinstance(elt, ast.Constant) and isinstance(elt.value, int)
                        for elt in node.value.elts
                    ):
                        color_names.add(node.target.id)
                # Também aceitar RAINBOW_COLORS que é uma lista
                elif (
                    isinstance(node.value, ast.List)
                    and node.target.id == "RAINBOW_COLORS"
                ):
                    color_names.add(node.target.id)

    except Exception as e:
        print(f"Erro ao analisar {colors_file_path}: {e}")
        return set()

    return color_names


def find_color_references(
    project_root: str, color_names: Set[str]
) -> Dict[str, List[str]]:
    """
    Busca por referências às cores em todos os arquivos Python do projeto.

    Args:
        project_root: Diretório raiz do projeto
        color_names: Conjunto com os nomes das cores

    Returns:
        Dicionário mapeando nome da cor para lista de arquivos onde é usada
    """
    references: Dict[str, List[str]] = {color: [] for color in color_names}
    references["UNKNOWN"] = (
        []
    )  # Para referências que não correspondem a cores conhecidas

    # Percorrer todos os arquivos .py, exceto __pycache__ e .venv
    for py_file in Path(project_root).rglob("*.py"):
        if "__pycache__" in str(py_file) or ".venv" in str(py_file):
            continue

        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            file_rel_path = str(py_file.relative_to(project_root))

            # Para cada cor conhecida, procurar por qualquer menção dela no arquivo
            for color in color_names:
                # Padrões para detectar uso da cor:
                # 1. colors.NOME_DA_COR
                # 2. from colors import ... NOME_DA_COR
                # 3. Uso direto da cor (após import)
                # 4. Uso em dicionários, listas, etc.
                patterns = [
                    rf"colors\.{re.escape(color)}\b",  # colors.COLOR_NAME
                    rf"from colors import.*\b{re.escape(color)}\b",  # import direto
                    rf"\b{re.escape(color)}\b",  # uso direto (mais permissivo)
                ]

                found = False
                for pattern in patterns:
                    if re.search(pattern, content):
                        found = True
                        break

                if found and file_rel_path not in references[color]:
                    references[color].append(file_rel_path)

        except Exception as e:
            print(f"Erro ao processar {py_file}: {e}")

    return references


def generate_report(color_names: Set[str], references: Dict[str, List[str]]) -> str:
    """
    Gera o relatório detalhado sobre o uso das cores.

    Args:
        color_names: Conjunto com os nomes das cores
        references: Dicionário com as referências encontradas

    Returns:
        String com o relatório formatado
    """
    report_lines: List[str] = []
    report_lines.append("=" * 80)
    report_lines.append("RELATÓRIO DE ANÁLISE DE CORES")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Cores utilizadas
    used_colors = [color for color in color_names if references.get(color)]
    report_lines.append(f"CORES UTILIZADAS ({len(used_colors)}/{len(color_names)}):")
    report_lines.append("-" * 50)

    if used_colors:
        for color in sorted(used_colors):
            files = references[color]
            report_lines.append(f"• {color}")
            for file in sorted(files):
                report_lines.append(f"  - {file}")
            report_lines.append("")
    else:
        report_lines.append("Nenhuma cor utilizada encontrada.")
        report_lines.append("")

    # Cores não utilizadas
    unused_colors = [color for color in color_names if not references.get(color)]
    report_lines.append(
        f"CORES DEFINIDAS MAS NÃO UTILIZADAS ({len(unused_colors)}/{len(color_names)}):"
    )
    report_lines.append("-" * 50)

    if unused_colors:
        for color in sorted(unused_colors):
            report_lines.append(f"• {color}")
        report_lines.append("")
    else:
        report_lines.append("Todas as cores estão sendo utilizadas!")
        report_lines.append("")

    # Problemas encontrados
    problems: List[str] = []
    unknown_refs = references.get("UNKNOWN", [])

    if unknown_refs:
        problems.append("REFERÊNCIAS DESCONHECIDAS ENCONTRADAS:")
        problems.append(
            "Essas referências usam cores que não foram encontradas no módulo colors:"
        )
        for ref in sorted(unknown_refs):
            problems.append(f"• {ref}")
        problems.append("")

    if problems:
        report_lines.append("PROBLEMAS ENCONTRADOS:")
        report_lines.append("-" * 50)
        report_lines.extend(problems)
    else:
        report_lines.append("NENHUM PROBLEMA ENCONTRADO!")
        report_lines.append("")

    # Estatísticas
    report_lines.append("ESTATÍSTICAS:")
    report_lines.append("-" * 50)
    total_colors = len(color_names)
    used_count = len(used_colors)
    unused_count = len(unused_colors)
    usage_percentage = (used_count / total_colors * 100) if total_colors > 0 else 0

    report_lines.append(f"• Total de cores definidas: {total_colors}")
    report_lines.append(f"• Cores utilizadas: {used_count} ({usage_percentage:.1f}%)")
    report_lines.append(
        f"• Cores não utilizadas: {unused_count} ({100 - usage_percentage:.1f}%)"
    )

    return "\n".join(report_lines)


def main():
    """Função principal do script."""
    # Caminhos
    project_root = Path(__file__).parent
    colors_file = project_root / "game" / "core" / "colors.py"

    if not colors_file.exists():
        print(f"Erro: Arquivo colors.py não encontrado em {colors_file}")
        return

    print("Analisando cores...")
    print(f"Arquivo colors: {colors_file}")
    print(f"Diretório raiz: {project_root}")
    print()

    # Extrair cores
    color_names = extract_color_definitions(str(colors_file))
    if not color_names:
        print("Erro: Não foi possível extrair as cores do módulo colors.")
        return

    print(f"Encontradas {len(color_names)} cores definidas.")

    # Buscar referências
    print("Procurando por referências nas arquivos Python...")
    references = find_color_references(str(project_root), color_names)

    # Gerar relatório
    report = generate_report(color_names, references)

    # Salvar relatório
    report_file = project_root / "colors_usage_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nRelatório salvo em: {report_file}")
    print("\n" + "=" * 80)
    print(report)


if __name__ == "__main__":
    main()
