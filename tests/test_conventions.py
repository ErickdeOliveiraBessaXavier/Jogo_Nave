"""Testes de convenção — o checklist de PR do CLAUDE.md como código executável.

Estes testes varrem o código-fonte procurando os anti-padrões que as convenções
proíbem. São a rede que impede a erosão de voltar: sem eles, uma reintrodução
de `lst[:] + .remove()` no hot path ou de acesso a `_privado` entre sistemas
passa despercebida na próxima sessão.

Cada teste que falhar aponta arquivo:linha e cita a seção violada. Se uma
ocorrência for legítima (raro), adicione-a à allowlist explícita do próprio
teste, com o motivo — nunca afrouxe a varredura.
"""

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GAME = _ROOT / "game"


def _py_files(*subdirs):
    for sub in subdirs:
        yield from (_GAME / sub).rglob("*.py")


# ─────────────────────────────────────────────────────────────────────────────
# §6 — nenhum `for x in lst[:]: ... lst.remove(x)` no hot path
# ─────────────────────────────────────────────────────────────────────────────
def test_sem_copia_mais_remove_no_hot_path():
    """`for x in coll[:]` seguido de `coll.remove(` no mesmo bloco = O(n²)."""
    padrao_for = re.compile(r"for\s+\w+\s+in\s+([\w.]+)\[:\]")
    violacoes = []
    for f in _py_files("systems", "entities"):
        linhas = f.read_text(encoding="utf-8").split("\n")
        for i, linha in enumerate(linhas):
            # Ignora linhas de comentário/docstring (o próprio §6 cita o padrão).
            despido = linha.strip()
            if despido.startswith("#") or despido.startswith("`"):
                continue
            m = padrao_for.search(linha)
            if not m:
                continue
            coll = m.group(1)
            bloco = "\n".join(linhas[i : i + 14])
            if re.search(rf"{re.escape(coll)}\.remove\(", bloco):
                rel = f.relative_to(_ROOT)
                violacoes.append(f"{rel}:{i + 1}  for ... in {coll}[:] + {coll}.remove()")
    assert not violacoes, "§6 violado (use _filter_dead_inplace ou rebuild):\n" + "\n".join(
        violacoes
    )


# ─────────────────────────────────────────────────────────────────────────────
# §1 — sistema não lê atributo privado de OUTRO objeto
# ─────────────────────────────────────────────────────────────────────────────
# Acessos legítimos a privado de outro objeto, com justificativa. Vazio hoje.
_PRIVADO_PERMITIDO: set[str] = set()


def test_sem_acesso_a_privado_entre_objetos_em_systems():
    """`self.<obj>._priv` onde <obj> != self expõe estado interno alheio.

    Detecção por AST: `self.attr._priv`. `self._priv` (privado da própria
    classe) é legítimo e não casa. Dunder (`__x__`) é ignorado.
    """
    violacoes = []
    for f in _py_files("systems"):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            # Casa: <algo>._nome  onde <algo> == self.<attr>
            if not isinstance(node, ast.Attribute):
                continue
            if not node.attr.startswith("_") or node.attr.startswith("__"):
                continue
            base = node.value
            if not (
                isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id == "self"
            ):
                continue
            chave = f"{f.name}:{base.attr}.{node.attr}"
            if chave in _PRIVADO_PERMITIDO:
                continue
            rel = f.relative_to(_ROOT)
            violacoes.append(f"{rel}:{node.lineno}  self.{base.attr}.{node.attr}")
    assert not violacoes, "§1 violado (exponha contrato público):\n" + "\n".join(violacoes)


# ─────────────────────────────────────────────────────────────────────────────
# §2 — todo sistema que faz bus.on(...) tem cleanup() com bus.off()
# ─────────────────────────────────────────────────────────────────────────────
def test_handlers_de_evento_tem_cleanup_pareado():
    for f in _py_files("systems", "scenes"):
        src = f.read_text(encoding="utf-8")
        n_on = len(re.findall(r"\b(?:_bus|bus|event_bus)\.on\(", src))
        if n_on == 0:
            continue
        n_off = len(re.findall(r"\b(?:_bus|bus|event_bus)\.off\(", src))
        assert n_off >= n_on, (
            f"{f.relative_to(_ROOT)}: {n_on} bus.on() mas só {n_off} bus.off() "
            "— handler sem remoção é memory leak (§2)."
        )
