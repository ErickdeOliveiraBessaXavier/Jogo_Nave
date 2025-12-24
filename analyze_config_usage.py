#!/usr/bin/env python3
"""
Script para analisar o uso das configurações definidas em config.py.

Este script:
1. Extrai todas as configurações definidas na classe Config
2. Busca por referências a essas configurações em todos os arquivos Python do projeto
3. Gera um relatório detalhado sobre o uso das configurações
"""

import ast
import re
from pathlib import Path
from typing import Set, Dict, List


def extract_config_attributes(config_file_path: str) -> Set[str]:
    """
    Extrai todos os nomes dos atributos da classe Config usando AST.

    Args:
        config_file_path: Caminho para o arquivo config.py

    Returns:
        Conjunto com os nomes dos atributos da classe Config
    """
    config_attrs = set()

    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Config":
                for item in node.body:
                    # Atributos com anotação de tipo (AnnAssign)
                    if isinstance(item, ast.AnnAssign) and isinstance(
                        item.target, ast.Name
                    ):
                        config_attrs.add(item.target.id)
                    # Atributos sem anotação (Assign) - para casos como PARTICLE_ENTRY_COUNT = 3
                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                config_attrs.add(target.id)

                break  # Só precisamos da classe Config

    except Exception as e:
        print(f"Erro ao analisar {config_file_path}: {e}")
        return set()

    return config_attrs


def find_config_references(
    project_root: str, config_attrs: Set[str]
) -> Dict[str, List[str]]:
    """
    Busca por referências às configurações em todos os arquivos Python do projeto.

    Args:
        project_root: Diretório raiz do projeto
        config_attrs: Conjunto com os nomes dos atributos da Config

    Returns:
        Dicionário mapeando nome da configuração para lista de arquivos onde é usada
    """
    references = {attr: [] for attr in config_attrs}
    references["UNKNOWN"] = (
        []
    )  # Para referências que não correspondem a atributos conhecidos

    # Percorrer todos os arquivos .py, exceto __pycache__ e .venv
    for py_file in Path(project_root).rglob("*.py"):
        if "__pycache__" in str(py_file) or ".venv" in str(py_file):
            continue

        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            file_rel_path = str(py_file.relative_to(project_root))

            # Para cada configuração conhecida, procurar por qualquer menção dela no arquivo
            for config in config_attrs:
                # Padrões para detectar uso da configuração:
                # 1. Config.NOME_DA_CONFIG
                # 2. from config import ... NOME_DA_CONFIG
                # 3. Uso direto da configuração (após import)
                # 4. Uso em dicionários, listas, etc.
                patterns = [
                    rf'Config\.({re.escape(config)})\b',  # Config.NOME_DA_CONFIG
                    rf'from config import.*\b{re.escape(config)}\b',  # import direto
                    rf'\b{re.escape(config)}\b',  # uso direto (mais permissivo)
                ]

                found = False
                for pattern in patterns:
                    if re.search(pattern, content):
                        found = True
                        break

                if found and file_rel_path not in references[config]:
                    references[config].append(file_rel_path)

        except Exception as e:
            print(f"Erro ao processar {py_file}: {e}")

    return references


def generate_report(config_attrs: Set[str], references: Dict[str, List[str]]) -> str:
    """
    Gera o relatório detalhado sobre o uso das configurações.

    Args:
        config_attrs: Conjunto com os nomes dos atributos da Config
        references: Dicionário com as referências encontradas

    Returns:
        String com o relatório formatado
    """
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("RELATÓRIO DE ANÁLISE DE CONFIGURAÇÕES")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Configurações utilizadas
    used_configs = [attr for attr in config_attrs if references.get(attr)]
    report_lines.append(
        f"CONFIGURAÇÕES UTILIZADAS ({len(used_configs)}/{len(config_attrs)}):"
    )
    report_lines.append("-" * 50)

    if used_configs:
        for attr in sorted(used_configs):
            files = references[attr]
            report_lines.append(f"• {attr}")
            for file in sorted(files):
                report_lines.append(f"  - {file}")
            report_lines.append("")
    else:
        report_lines.append("Nenhuma configuração utilizada encontrada.")
        report_lines.append("")

    # Configurações não utilizadas
    unused_configs = [attr for attr in config_attrs if not references.get(attr)]
    report_lines.append(
        f"CONFIGURAÇÕES DEFINIDAS MAS NÃO UTILIZADAS ({len(unused_configs)}/{len(config_attrs)}):"
    )
    report_lines.append("-" * 50)

    if unused_configs:
        for attr in sorted(unused_configs):
            report_lines.append(f"• {attr}")
        report_lines.append("")
    else:
        report_lines.append("Todas as configurações estão sendo utilizadas!")
        report_lines.append("")

    # Problemas encontrados
    problems = []
    unknown_refs = references.get("UNKNOWN", [])

    if unknown_refs:
        problems.append("REFERÊNCIAS DESCONHECIDAS ENCONTRADAS:")
        problems.append(
            "Essas referências usam 'Config.' mas o atributo não foi encontrado na classe Config:"
        )
        for ref in sorted(unknown_refs):
            problems.append(f"• {ref}")
        problems.append("")

    # Verificar se há propriedades computadas sendo acessadas incorretamente
    computed_properties = {"BOSS_MUSIC_SILENCE_DURATION", "POWERUP_WEIGHTS"}
    incorrectly_used_computed = []
    for prop in computed_properties:
        if prop in config_attrs and references.get(prop):
            incorrectly_used_computed.append(prop)

    if incorrectly_used_computed:
        problems.append("PROPRIEDADES COMPUTADAS SENDO ACESSADAS DIRETAMENTE:")
        problems.append(
            "Estas são propriedades @property e devem ser acessadas sem 'Config.':"
        )
        for prop in sorted(incorrectly_used_computed):
            problems.append(f"• {prop} (usada em: {', '.join(references[prop])})")
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
    total_configs = len(config_attrs)
    used_count = len(used_configs)
    unused_count = len(unused_configs)
    usage_percentage = (used_count / total_configs * 100) if total_configs > 0 else 0

    report_lines.append(f"• Total de configurações definidas: {total_configs}")
    report_lines.append(
        f"• Configurações utilizadas: {used_count} ({usage_percentage:.1f}%)"
    )
    report_lines.append(
        f"• Configurações não utilizadas: {unused_count} ({100 - usage_percentage:.1f}%)"
    )
    if unknown_refs:
        report_lines.append(f"• Referências desconhecidas: {len(unknown_refs)}")

    return "\n".join(report_lines)


def main():
    """Função principal do script."""
    # Caminhos
    project_root = Path(__file__).parent
    config_file = project_root / "game" / "core" / "config.py"

    if not config_file.exists():
        print(f"Erro: Arquivo config.py não encontrado em {config_file}")
        return

    print("Analisando configurações...")
    print(f"Arquivo config: {config_file}")
    print(f"Diretório raiz: {project_root}")
    print()

    # Extrair configurações
    config_attrs = extract_config_attributes(str(config_file))
    if not config_attrs:
        print("Erro: Não foi possível extrair as configurações da classe Config.")
        return

    print(f"Encontradas {len(config_attrs)} configurações definidas.")

    # Buscar referências
    print("Procurando por referências nas arquivos Python...")
    references = find_config_references(str(project_root), config_attrs)

    # Gerar relatório
    report = generate_report(config_attrs, references)

    # Salvar relatório
    report_file = project_root / "config_usage_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nRelatório salvo em: {report_file}")
    print("\n" + "=" * 80)
    print(report)


if __name__ == "__main__":
    main()
