"""Testes do fade global de troca de cena (`core/scene_transition.py`).

Cobrem o contrato que substituiu SETE implementações de fade espalhadas pelas
cenas, mais a regressão que motivou a revisão: o overlay do Game Over tinha
parado de aparecer porque o buffer compartilhado de fade carregava um
`set_alpha()` residual de outra tela.
"""

import pygame

from game.core.scene_transition import (
    DEFAULT_DURATION,
    SceneTransition,
    TransitionStyle,
)
from game.scenes.ui_helpers import get_fade_scratch


def _idle() -> SceneTransition:
    """Transição já assentada — o construtor começa numa entrada (fade do boot)."""
    tr = SceneTransition()
    tr.update(DEFAULT_DURATION * 2)
    assert not tr.active
    return tr


# ── Ciclo de vida ───────────────────────────────────────────────────────────


def test_boot_comeca_clareando():
    """Sem isto a primeira tela do jogo seria o único corte seco restante."""
    tr = SceneTransition()
    assert tr.active
    assert tr.black_alpha > 0
    assert not tr.busy, "o boot não tem cena anterior para bloquear input"


def test_troca_acontece_no_pico_do_escurecimento():
    tr = _idle()
    marcos: list[str] = []

    tr.request(lambda: marcos.append("trocou"))
    assert tr.busy, "durante a fase OUT o input fica bloqueado"
    assert marcos == [], "a cena não pode trocar no instante do clique"

    # Meio do escurecimento: ainda nada.
    tr.update(DEFAULT_DURATION * 0.5)
    assert marcos == []
    assert not tr.active or tr.busy

    # Fim do escurecimento: troca e emenda na entrada.
    tr.update(DEFAULT_DURATION * 0.6)
    assert marcos == ["trocou"]
    assert not tr.busy, "na fase IN a cena nova já responde a input"
    assert tr.active

    tr.update(DEFAULT_DURATION * 1.1)
    assert not tr.active


def test_veu_escurece_e_depois_clareia():
    tr = _idle()
    tr.request(lambda: None)

    tr.update(DEFAULT_DURATION * 0.95)
    quase_preto = tr.black_alpha

    tr.update(DEFAULT_DURATION * 0.1)  # cruza o pico: commit + início da entrada
    logo_apos = tr.black_alpha

    tr.update(DEFAULT_DURATION * 0.9)
    quase_claro = tr.black_alpha

    assert quase_preto > 200, f"não escureceu o bastante: {quase_preto}"
    assert logo_apos > 200, f"deveria estar preto no pico: {logo_apos}"
    assert quase_claro < 60, f"não clareou: {quase_claro}"


def test_pedido_durante_transicao_e_descartado():
    """Dois cliques rápidos não podem levar o jogador a pular uma tela."""
    tr = _idle()
    marcos: list[str] = []

    assert tr.request(lambda: marcos.append("a")) is True
    assert tr.request(lambda: marcos.append("b")) is False

    tr.update(DEFAULT_DURATION * 1.1)
    assert marcos == ["a"], "o segundo pedido não pode ter sido enfileirado"


def test_abrir_overlay_troca_na_hora_e_nao_desenha_veu():
    """Abrir a pausa: não há o que despedir (a partida segue visível), então
    só a metade de entrada roda. Um véu preto aqui piscaria em vez de suavizar."""
    tr = _idle()
    marcos: list[str] = []

    tr.request(
        lambda: marcos.append("trocou"), style=TransitionStyle.DIM, fade_out=False
    )

    assert marcos == ["trocou"], "sem fade_out, troca imediatamente"
    assert tr.black_alpha == 0, "DIM não pinta véu preto"
    assert tr.active, "mas segue rodando o relógio da entrada"


def test_fechar_overlay_anima_a_saida_antes_de_desempilhar():
    """A regressão que motivou este teste: retomar a partida desempilhava a
    pausa no instante do clique e a animação de saída rodava com a cena já
    fora da pilha — ou seja, sumia de um frame para o outro."""
    tr = _idle()
    marcos: list[str] = []

    tr.request(
        lambda: marcos.append("desempilhou"),
        style=TransitionStyle.DIM,
        fade_in=False,
    )

    assert marcos == [], "não pode desempilhar no clique"
    assert tr.overlay_progress > 0.9, "a pausa ainda está cheia no primeiro frame"

    tr.update(DEFAULT_DURATION * 0.5)
    assert marcos == [], "ainda não — a animação está no meio"
    meio = tr.overlay_progress
    assert 0.1 < meio < 0.9, f"deveria estar desaparecendo: {meio}"

    tr.update(DEFAULT_DURATION * 0.6)
    assert marcos == ["desempilhou"], "desempilha só no FIM da saída"
    assert not tr.active, "sem fade_in: acabou aqui, a cena de baixo nunca saiu"


def test_overlay_progress_sobe_na_entrada_e_satura():
    tr = _idle()
    tr.request(lambda: None, style=TransitionStyle.DIM, fade_out=False)

    assert tr.overlay_progress < 0.1
    tr.update(DEFAULT_DURATION * 0.5)
    meio = tr.overlay_progress
    assert 0.1 < meio < 0.9, meio

    tr.update(DEFAULT_DURATION)
    assert tr.overlay_progress == 1.0


def test_overlay_progress_e_um_fora_de_transicao():
    """As cenas multiplicam alpha por ele todo frame; em repouso precisa ser
    neutro, senão a UI da pausa sumiria depois que o fade acaba."""
    assert _idle().overlay_progress == 1.0


def test_interromper_a_entrada_nao_faz_a_saida_pular():
    """Apertar P duas vezes rápido: a saída tem de continuar de onde a entrada
    parou. Sem isso o overlay saltaria para 'cheio' e piscaria."""
    tr = _idle()
    tr.request(lambda: None, style=TransitionStyle.DIM, fade_out=False)
    tr.update(DEFAULT_DURATION * 0.5)
    antes = tr.overlay_progress

    aceito = tr.request(lambda: None, style=TransitionStyle.DIM, fade_in=False)
    assert aceito, "pedido durante a ENTRADA deve ser aceito (a cena já é a real)"

    depois = tr.overlay_progress
    assert abs(depois - antes) < 0.02, f"saltou de {antes:.3f} para {depois:.3f}"


# ── Regressão do overlay do Game Over ───────────────────────────────────────


def test_scratch_compartilhado_nao_carrega_alpha_residual():
    """A causa raiz do 'fade do Game Over sumiu'.

    O buffer é compartilhado e `set_alpha()` PERSISTE no objeto Surface. Uma
    tela que terminasse um fade-out deixava `set_alpha(0)` gravado; o Game Over
    pegava o mesmo buffer, fazia só `fill()` (alpha por pixel, não de
    superfície) e blitava algo 100% transparente.
    """
    size = (64, 48)

    sujo = get_fade_scratch(size)
    sujo.set_alpha(0)  # o que o fade-out de outra tela deixava para trás

    limpo = get_fade_scratch(size)
    assert limpo is sujo, "o buffer é compartilhado — é por isso que o bug existia"
    assert limpo.get_alpha() == 255, "o alpha residual voltou"


def test_overlay_de_dim_escurece_de_fato_apos_um_fade_out():
    """Prova pelo pixel: o cenário exato do bug, ponta a ponta."""
    size = (64, 48)
    get_fade_scratch(size).set_alpha(0)  # contamina como o fade-out fazia

    tela = pygame.Surface(size)
    tela.fill((60, 60, 60))

    overlay = get_fade_scratch(size)
    overlay.fill((0, 0, 0, 200))
    tela.blit(overlay, (0, 0))

    r, g, b = tela.get_at((32, 24))[:3]
    assert r < 30, f"o overlay não escureceu nada (pixel={r},{g},{b})"
