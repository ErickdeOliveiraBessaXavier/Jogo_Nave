"""Verificação de paridade das tabelas de tradução.

Roda como script (`python -m game.core.translations.check_parity`) e sai com
código != 0 se houver divergência — pronto pra CI ou pra rodar manualmente após
editar as tabelas. Checa duas coisas:

1. **Chaves**: todo `key` existe em TODOS os idiomas (ninguém sobrando/faltando).
2. **Placeholders**: o conjunto de `{campos}` de cada chave é idêntico entre os
   idiomas — pega tradução que esqueceu (ou renomeou) um `{campo}` de interpolação,
   que quebraria o `.format()` em runtime.

Fonte única dos idiomas: `TABLES` (não hardcoda 'pt'/'en' aqui).
"""

from __future__ import annotations

import string
import sys

from . import TABLES


def _placeholders(text: str) -> set[str]:
    """Campos nomeados de um template `str.format` (ignora `{}` posicional)."""
    names: set[str] = set()
    for _literal, field, _spec, _conv in string.Formatter().parse(text):
        if field:  # None em texto puro; "" em `{}` posicional
            names.add(field)
    return names


def check_parity() -> list[str]:
    """Retorna a lista de problemas encontrados (vazia = tudo certo)."""
    problems: list[str] = []
    all_keys: set[str] = set()
    for table in TABLES.values():
        all_keys |= set(table)

    for lang, table in TABLES.items():
        missing = all_keys - set(table)
        for key in sorted(missing):
            problems.append(f"[{lang}] falta a chave: {key}")

    # Placeholders por chave devem casar entre todos os idiomas.
    for key in sorted(all_keys):
        per_lang = {
            lang: _placeholders(table[key])
            for lang, table in TABLES.items()
            if key in table
        }
        distinct = {frozenset(v) for v in per_lang.values()}
        if len(distinct) > 1:
            detail = ", ".join(
                f"{lang}={sorted(ph)}" for lang, ph in sorted(per_lang.items())
            )
            problems.append(f"placeholders divergentes em '{key}': {detail}")

    return problems


def main() -> int:
    problems = check_parity()
    total = len(next(iter(TABLES.values())))
    if problems:
        print(f"❌ Paridade FALHOU ({len(problems)} problema(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"✅ Paridade OK — {len(TABLES)} idiomas, {total} chaves, placeholders casando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
