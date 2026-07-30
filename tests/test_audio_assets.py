"""Testes do contrato entre os arquivos de áudio no disco e o que o código espera.

Existem por uma falha que passou anos invisível: `button_click` era tocado em 19
lugares, em 8 telas, e o arquivo **nunca existiu** — nenhum commit o adicionou.
Dois guards em série engoliam isso sem uma linha de log: a carga pulava o som
(`if os.path.exists(...)`, sem `else`) e `play_sound` é no-op em chave
desconhecida. Resultado: todo clique do jogo era mudo enquanto o hover
funcionava, o que fazia o bug parecer design.

Nada aqui abre janela, toca som ou inicializa o mixer — são testes de disco e de
nome de arquivo, então rodam no CI de graça.
"""

import re
import unicodedata
from pathlib import Path

from game.core.sfx_manager import AUDIO_EXTS, discover_sfx
from game.core.sound_config import (
    AUDIO_BOSSES_ROOT,
    AUDIO_MENU_ROOT,
    AUDIO_SFX_ROOT,
    AUDIO_THEMES_ROOT,
    SFX_FAMILIES,
    SFX_OPTIONAL,
    SFX_REQUIRED,
)

_ROOT = Path(__file__).resolve().parent.parent
_SFX = _ROOT / AUDIO_SFX_ROOT
_MUSICA_ROOTS = (
    _ROOT / AUDIO_THEMES_ROOT,
    _ROOT / AUDIO_BOSSES_ROOT,
    _ROOT / AUDIO_MENU_ROOT,
)


def _arquivos_de_audio(raiz: Path):
    for p in raiz.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            yield p


# ─────────────────────────────────────────────────────────────────────────────
# O contrato: chave exigida pelo código existe no disco
# ─────────────────────────────────────────────────────────────────────────────
def test_todo_sfx_obrigatorio_existe_no_disco():
    """A regressão exata do `button_click`: chave usada, arquivo inexistente."""
    catalogo = discover_sfx(str(_SFX))
    faltando = sorted(SFX_REQUIRED - catalogo.keys())
    assert not faltando, (
        "SFX obrigatório sem arquivo em "
        f"{_SFX.relative_to(_ROOT).as_posix()} (o som não vai tocar):\n  "
        + "\n  ".join(faltando)
    )


def test_todo_arquivo_de_sfx_tem_uso_declarado():
    """O outro lado: arquivo no disco que nenhuma chave reclama é peso morto.

    Órfão vira conteúdo esquecido — havia três aqui, um deles um asset de banco
    ainda com o nome de origem (`sci-fi-weapon-...-233851.mp3`). Se o arquivo é
    proposital mas ainda não está ligado, declare em `SFX_OPTIONAL` com o motivo.
    """
    catalogo = discover_sfx(str(_SFX))
    familias = {
        re.compile(re.escape(molde.split("{}")[0]) + r"\d+$")
        for molde in SFX_FAMILIES.values()
    }
    orfaos = sorted(
        chave
        for chave in catalogo
        if chave not in SFX_REQUIRED
        and chave not in SFX_OPTIONAL
        and not any(p.match(chave) for p in familias)
    )
    assert not orfaos, (
        "SFX no disco sem uso declarado (registre em SFX_REQUIRED, em "
        "SFX_OPTIONAL com o motivo, ou apague):\n  " + "\n  ".join(orfaos)
    )


def test_familias_numeradas_nao_tem_buraco():
    """`shot_1, shot_3` sem o `2` é arquivo perdido no rename, não escolha.

    O grupo continua sorteando — só com uma variação a menos, o que ninguém
    percebe de ouvido.
    """
    catalogo = discover_sfx(str(_SFX))
    problemas = []
    for grupo, molde in SFX_FAMILIES.items():
        padrao = re.compile(re.escape(molde.split("{}")[0]) + r"(\d+)$")
        indices = sorted(
            int(m.group(1)) for c in catalogo if (m := padrao.match(c)) is not None
        )
        if not indices:
            problemas.append(f"{grupo}: nenhum arquivo casa '{molde}'")
            continue
        esperado = list(range(indices[0], indices[0] + len(indices)))
        if indices != esperado:
            problemas.append(f"{grupo}: índices {indices}, esperado contíguo {esperado}")
    assert not problemas, "famílias de SFX com buraco:\n  " + "\n  ".join(problemas)


# ─────────────────────────────────────────────────────────────────────────────
# Nomenclatura — ASCII, minúsculo, sem espaço (ver audio/README.md)
# ─────────────────────────────────────────────────────────────────────────────
def _fora_do_padrao(nome: str) -> str | None:
    if any(ord(c) > 127 for c in nome):
        return "não-ASCII"
    if " " in nome:
        return "espaço"
    if nome != nome.lower():
        return "maiúscula"
    return None


def test_nomes_de_audio_sao_ascii_minusculos_sem_espaco():
    """Nome de arquivo é contrato (no SFX, é a própria chave) e viaja por
    PyInstaller, build Linux, zip e pygbag (fetch por URL).

    Havia 19 arquivos com acento e 10 com espaço; o git guardava os acentuados
    escapados (`explis\\303\\243o_boss.wav`).
    """
    violacoes = []
    for raiz in (_SFX, *_MUSICA_ROOTS):
        for p in _arquivos_de_audio(raiz):
            motivo = _fora_do_padrao(p.stem)
            if motivo:
                violacoes.append(f"{p.relative_to(_ROOT).as_posix()}  ({motivo})")
    assert not violacoes, (
        "nome de arquivo de áudio fora do padrão lower_snake ASCII:\n  "
        + "\n  ".join(sorted(violacoes))
    )


def test_pastas_de_audio_sao_ascii_minusculas():
    """A pasta é a chave da música (`WorldTheme` / `BOSS_TYPE_NAME`), então um
    acento ou maiúscula ali quebra a descoberta em silêncio: a chave não casa e
    o jogo cai no fallback sem avisar."""
    violacoes = []
    for raiz in (_SFX, *_MUSICA_ROOTS):
        for p in raiz.rglob("*"):
            if p.is_dir() and _fora_do_padrao(p.name):
                violacoes.append(
                    f"{p.relative_to(_ROOT).as_posix()}  ({_fora_do_padrao(p.name)})"
                )
    assert not violacoes, "pasta de áudio fora do padrão:\n  " + "\n  ".join(
        sorted(violacoes)
    )


def test_sfx_nao_tem_nome_de_arquivo_repetido_entre_pastas():
    """A chave do SFX é o nome do arquivo, então o mesmo nome em duas pastas é
    ambíguo — qual vence depende da ordem de varredura do sistema de arquivos."""
    por_nome: dict[str, list[str]] = {}
    for p in _arquivos_de_audio(_SFX):
        por_nome.setdefault(p.stem, []).append(p.relative_to(_ROOT).as_posix())
    repetidos = {k: v for k, v in por_nome.items() if len(v) > 1}
    assert not repetidos, "nome de SFX repetido em pastas diferentes:\n  " + "\n  ".join(
        f"{k}: {', '.join(v)}" for k, v in sorted(repetidos.items())
    )


# ─────────────────────────────────────────────────────────────────────────────
# Duplicata de conteúdo — sons distintos que na verdade são o mesmo arquivo
# ─────────────────────────────────────────────────────────────────────────────
# Pares byte-idênticos CONHECIDOS, aguardando gravação de som próprio. Some da
# lista quando o áudio novo entrar; não cresça a lista para calar o teste.
_DUPLICATAS_ACEITAS: set[frozenset[str]] = {
    frozenset({"explosion_boss", "explosion_ship"}),
    frozenset({"explosion_alien", "boss_damage"}),
}


def test_sfx_com_intencao_distinta_nao_sao_o_mesmo_arquivo():
    """Chaves diferentes existem porque o design quer sons diferentes.

    `explosion_boss` == `explosion_ship` byte a byte significa que a morte da
    sua nave soa igual à explosão do boss — justamente o par que mais precisa
    ser distinguível. Passa hoje pela allowlist acima; o teste está aqui para
    não aparecer um par NOVO sem ninguém notar.
    """
    import hashlib

    por_hash: dict[str, list[str]] = {}
    for chave, caminho in discover_sfx(str(_SFX)).items():
        h = hashlib.md5(Path(caminho).read_bytes()).hexdigest()
        por_hash.setdefault(h, []).append(chave)

    novos = [
        sorted(chaves)
        for chaves in por_hash.values()
        if len(chaves) > 1 and frozenset(chaves) not in _DUPLICATAS_ACEITAS
    ]
    assert not novos, (
        "chaves de SFX distintas apontando para arquivos byte-idênticos:\n  "
        + "\n  ".join(", ".join(c) for c in novos)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Música — a pasta é a chave, e as chaves vêm do código
# ─────────────────────────────────────────────────────────────────────────────
def test_pasta_de_musica_de_boss_casa_com_um_BOSS_TYPE_NAME():
    """Pasta cujo nome não é `BOSS_TYPE_NAME` de nenhum boss nunca toca.

    A descoberta é por chave exata; errar o nome não dá erro — cai na música
    genérica (`bosses/normal/`) e o boss fica sem tema, silenciosamente.
    """
    declarados = {"normal"}
    padrao = re.compile(r"^\s*BOSS_TYPE_NAME\s*:\s*str\s*=\s*[\"']([\w]+)[\"']", re.M)
    for py in (_ROOT / "game").rglob("*.py"):
        declarados.update(padrao.findall(py.read_text(encoding="utf-8")))

    pastas = {p.name for p in (_ROOT / AUDIO_BOSSES_ROOT).iterdir() if p.is_dir()}
    orfas = sorted(pastas - declarados)
    assert not orfas, (
        "pasta de música de boss sem BOSS_TYPE_NAME correspondente "
        f"(nunca vai tocar): {orfas}\nBOSS_TYPE_NAME conhecidos: "
        f"{sorted(declarados)}"
    )


def test_pasta_de_musica_de_tema_casa_com_um_WorldTheme():
    """Mesma armadilha do teste acima, do lado dos temas."""
    from game.core.world_config import WorldTheme

    validos = {t.value for t in WorldTheme}
    pastas = {p.name for p in (_ROOT / AUDIO_THEMES_ROOT).iterdir() if p.is_dir()}
    orfas = sorted(pastas - validos)
    assert not orfas, (
        f"pasta de música de tema sem WorldTheme correspondente: {orfas}\n"
        f"WorldTheme válidos: {sorted(validos)}"
    )


def test_nenhum_nome_de_audio_depende_de_normalizacao_unicode():
    """Acento pode ser gravado composto (NFC) ou decomposto (NFD), e macOS
    normaliza diferente de Windows/Linux. Um nome que só casa numa das formas
    quebra a descoberta ao trocar de máquina — o teste ASCII acima já barra
    isso, este trava a porta pelo outro lado (inclui `.gitkeep` e READMEs)."""
    problemas = []
    for raiz in (_SFX, *_MUSICA_ROOTS):
        for p in raiz.rglob("*"):
            nome = p.name
            if unicodedata.normalize("NFC", nome) != nome:
                problemas.append(p.relative_to(_ROOT).as_posix())
    assert not problemas, "nome não normalizado (NFC):\n  " + "\n  ".join(problemas)
