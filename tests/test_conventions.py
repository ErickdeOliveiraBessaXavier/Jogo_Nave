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


# ─────────────────────────────────────────────────────────────────────────────
# Transição de cena — navegação passa pelo router, não pelo StateManager cru
# ─────────────────────────────────────────────────────────────────────────────

# `app.py` é o dono do router: é lá que `go_to`/`go_back` de fato chamam o
# StateManager, e é lá que ficam os dois pushes do boot (antes de existir
# qualquer cena para desaparecer com fade).
_NAVEGACAO_DIRETA_PERMITIDA = {"app.py"}


def test_navegacao_de_cena_passa_pelo_router():
    """`states.switch/push/pop` fora do `app.py` volta a cortar a tela seco.

    O fade de troca de tela é único e vive no `SceneTransition`; quem chama o
    `StateManager` direto pula o fade E o bloqueio de input da fase de saída.
    Este teste existe porque a alternativa — cada cena lembrar de fazer o fade —
    já falhou uma vez: sete implementações diferentes e quatro telas sem
    nenhuma. Use `app.go_to` / `app.go_back` / `app.open_overlay`.
    """
    padrao = re.compile(r"\bstates\.(switch|push|pop)\s*\(")
    violacoes = []
    for f in _py_files("scenes", "systems", "core", "render", "entities"):
        if f.name in _NAVEGACAO_DIRETA_PERMITIDA:
            continue
        for i, linha in enumerate(f.read_text(encoding="utf-8").split("\n")):
            if linha.strip().startswith("#"):
                continue
            m = padrao.search(linha)
            if m:
                violacoes.append(
                    f"{f.relative_to(_ROOT)}:{i + 1}  states.{m.group(1)}("
                )
    assert not violacoes, (
        "navegue por app.go_to/go_back/open_overlay — o StateManager cru pula "
        "o fade global:\n" + "\n".join(violacoes)
    )


def test_sem_implementacoes_paralelas_de_fade_de_cena():
    """Impede a volta do `FadeTransitionMixin` / `render_with_fade` e dos campos
    `transitioning`/`fade_out` copiados de cena em cena.

    `main_menu.py` é exceção: o `transitioning` dele é o crossfade ENTRE VIEWS
    da própria cena (menu ↔ mundos ↔ dificuldade), que não empilha nem troca
    cena — não é navegação, então não passa pelo router.
    """
    proibidos = ("FadeTransitionMixin", "render_with_fade", "start_fade_active")
    # `main_menu.py`: crossfade entre views (ver docstring). `ui_helpers.py` e
    # `scene_transition.py` citam os nomes removidos em comentário-lápide, para
    # quem procurar por eles achar o substituto — só código conta, e as linhas
    # de comentário são puladas abaixo.
    excecoes = {"main_menu.py", "scene_transition.py"}
    violacoes = []
    for f in _py_files("scenes", "render", "core"):
        if f.name in excecoes:
            continue
        for i, linha in enumerate(f.read_text(encoding="utf-8").split("\n")):
            despido = linha.strip()
            if despido.startswith("#") or despido.startswith("`"):
                continue
            for nome in proibidos:
                if nome in linha:
                    violacoes.append(f"{f.relative_to(_ROOT)}:{i + 1}: {nome}")
    assert not violacoes, (
        "fade de cena paralelo ao SceneTransition:\n" + "\n".join(violacoes)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Invulnerabilidade — conceder passa por grant_invulnerability
# ─────────────────────────────────────────────────────────────────────────────

# `ship.py` define a API e o campo; `ship_powerups.py` faz a contagem
# regressiva (decrementa e zera). Os dois escrevem `invuln` legitimamente.
_ESCRITA_INVULN_PERMITIDA = {"ship.py", "ship_powerups.py"}


def test_invulnerabilidade_concedida_por_metodo():
    """`ship.invuln = X` cru deixa `invuln_total` para trás.

    A piscada dos i-frames acelera em função da FRAÇÃO decorrida, então precisa
    saber quanto o período todo dura — não só quanto resta. Quem atribui direto
    deixa `invuln_total` com o valor da concessão anterior (ou zero), e a
    piscada acelera na hora errada ou nunca.

    Havia SEIS escritores diretos espalhados por cenas e sistemas quando o
    campo foi introduzido; nenhum teste os exercitava. Use
    `ship.grant_invulnerability(ms)`.
    """
    padrao = re.compile(r"\.invuln\s*=(?!=)")
    violacoes = []
    for f in _py_files("scenes", "systems", "entities", "core"):
        if f.name in _ESCRITA_INVULN_PERMITIDA:
            continue
        for i, linha in enumerate(f.read_text(encoding="utf-8").split("\n")):
            if linha.strip().startswith("#"):
                continue
            if padrao.search(linha):
                violacoes.append(f"{f.relative_to(_ROOT)}:{i + 1}  {linha.strip()}")
    assert not violacoes, (
        "use ship.grant_invulnerability(ms) — atribuir invuln direto "
        "dessincroniza invuln_total:\n" + "\n".join(violacoes)
    )


# ─────────────────────────────────────────────────────────────────────────────
# §5 — posição derivada declara `position_locked`
# ─────────────────────────────────────────────────────────────────────────────
def test_entidade_com_posicao_derivada_declara_position_locked():
    """`x`/`y` como property SEM setter exige `position_locked = True`.

    Sistemas que deslocam inimigos alheios (buraco negro, tremor da parada do
    tempo) fazem `en.y += ...`. Numa property somente-leitura isso estoura
    `AttributeError` — e `hasattr(en, "y")` NÃO protege, porque é verdadeiro
    para property de leitura. O guarda correto é o class attribute (§5), e ele
    só funciona se a entidade o declarar.

    Custou um crash em runtime: `MountainStalagmite` derruba a partida inteira
    quando o tremor da parada do tempo tenta vibrá-la. O tremor é código novo;
    a entidade já existia com o problema, sinalizado só ao buraco negro.
    """
    faltando = []
    for f in _py_files("entities"):
        arvore = ast.parse(f.read_text(encoding="utf-8"))
        for cls in (n for n in ast.walk(arvore) if isinstance(n, ast.ClassDef)):
            getters, setters = set(), set()
            for corpo in cls.body:
                if not isinstance(corpo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if corpo.name not in ("x", "y"):
                    continue
                for dec in corpo.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == "property":
                        getters.add(corpo.name)
                    elif isinstance(dec, ast.Attribute) and dec.attr == "setter":
                        setters.add(corpo.name)
            somente_leitura = getters - setters
            if not somente_leitura:
                continue

            declara = any(
                isinstance(a, ast.AnnAssign)
                and isinstance(a.target, ast.Name)
                and a.target.id == "position_locked"
                or isinstance(a, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "position_locked"
                    for t in a.targets
                )
                for a in cls.body
            )
            if not declara:
                faltando.append(
                    f"{f.relative_to(_ROOT)}:{cls.lineno}  {cls.name} "
                    f"(somente-leitura: {sorted(somente_leitura)})"
                )

    assert not faltando, (
        "posição derivada sem `position_locked = True` — quem mover essa "
        "entidade vai estourar AttributeError:\n" + "\n".join(faltando)
    )
