"""Contrato do recuo de impacto da Tríade (`triad_recoil`).

Lógica pura, testada sem pygame e sem boss (§16). O que se trava aqui é o que
não dá para ver no olho: a direção em ângulos que não sejam "de baixo", o teto
sob fogo automático e a independência de frame rate do retorno.
"""

from __future__ import annotations

import math

import pytest

from game.entities.bosses.city.triad_recoil import (
    IMPULSE,
    MAX_OFFSET,
    HitRecoil,
)


def test_a_parte_foge_do_ponto_de_impacto():
    """Em qualquer ângulo, o recuo aponta do impacto PARA fora."""
    for graus in range(0, 360, 15):
        rad = math.radians(graus)
        # Impacto num ponto a 30px do centro, no ângulo `graus`.
        hit_x, hit_y = 30.0 * math.cos(rad), 30.0 * math.sin(rad)
        r = HitRecoil()
        r.kick(0.0, 0.0, hit_x, hit_y)
        # O recuo tem de ser antiparalelo ao vetor centro→impacto.
        assert r.x == pytest.approx(-math.cos(rad) * IMPULSE, abs=1e-6)
        assert r.y == pytest.approx(-math.sin(rad) * IMPULSE, abs=1e-6)


def test_impacto_no_centro_exato_empurra_para_cima():
    """Dano em área é ancorado no centro: sem direção a extrair, sobe.

    Zero seria pior que um palpite — o AoE é justamente o caminho que mais
    acerta o centro, e ele ficaria sendo o único sem feedback de impacto.
    """
    r = HitRecoil()
    r.kick(100.0, 100.0, 100.0, 100.0)
    assert r.x == 0.0
    assert r.y == pytest.approx(-IMPULSE)


def test_fogo_sustentado_nao_desmonta_o_boss():
    """O impulso acumula, mas o módulo satura — a peça nunca sai do desenho."""
    r = HitRecoil()
    for _ in range(200):
        r.kick(0.0, 0.0, 0.0, 30.0)
        assert math.hypot(r.x, r.y) <= MAX_OFFSET + 1e-6
    assert math.hypot(r.x, r.y) == pytest.approx(MAX_OFFSET)


def test_retorno_e_independente_de_frame_rate():
    """A 30, 60 ou 144 fps o recuo assenta na MESMA janela de tempo.

    É a razão de o decaimento ser exponencial e não `x -= vel * dt`: o segundo
    passa do zero num frame longo e a peça oscila em vez de assentar.
    """
    tempos = []
    for fps in (30, 60, 144):
        r = HitRecoil()
        r.kick(0.0, 0.0, 0.0, 30.0)
        t = 0.0
        while (r.x or r.y) and t < 2.0:
            r.update(1.0 / fps)
            t += 1.0 / fps
        assert t < 2.0, f"o recuo não assentou a {fps}fps"
        tempos.append(t)
    assert max(tempos) - min(tempos) < 0.05, f"janelas divergentes: {tempos}"


def test_assenta_exatamente_no_zero():
    """Sem cauda infinita: o piso zera de vez e livra os frames seguintes."""
    r = HitRecoil()
    r.kick(0.0, 0.0, 0.0, 30.0)
    for _ in range(60):
        r.update(1 / 60)
    assert (r.x, r.y) == (0.0, 0.0)
    assert r.offset == (0, 0)


def test_recuo_em_repouso_nao_desloca_o_desenho():
    """Sem acerto, offset zero — o boss em paz desenha na origem exata."""
    assert HitRecoil().offset == (0, 0)


# ── Tremor da morte ───────────────────────────────────────────────────────────
from game.entities.bosses.city.triad_recoil import (  # noqa: E402
    DEATH_SHAKE_ART_PIXELS,
    death_shake,
)

_ESCALA = 5  # pmap.PIXEL_SCALE
_DUR = 8 / 12.0  # 8 frames de `Morrendo` a 12 fps


def _amostras(dur=_DUR, fps=60):
    n = int(dur * fps)
    return [death_shake(i / fps, dur, _ESCALA) for i in range(n + 1)]


def test_o_tremor_decai_ate_parar():
    """Forte enquanto a cabeça é estrutura, nulo quando virou poeira.

    Tremor constante até o último frame faria as faíscas já dispersas pularem
    juntas, como se ainda fossem um corpo só.
    """
    amostras = _amostras()
    metade = len(amostras) // 2
    pico_inicio = max(max(abs(x), abs(y)) for x, y in amostras[:metade])
    pico_fim = max(max(abs(x), abs(y)) for x, y in amostras[metade:])
    assert pico_inicio > pico_fim, "o tremor não decaiu"
    assert death_shake(_DUR, _DUR, _ESCALA) == (0, 0), "ainda treme no fim"
    assert death_shake(_DUR * 2, _DUR, _ESCALA) == (0, 0), "treme depois do fim"


def test_o_tremor_anda_na_grade_do_pixel_art():
    """Todo deslocamento é múltiplo de `PIXEL_SCALE`.

    Sub-pixel viraria borrão trêmulo — o efeito de "sprite mal ancorado", que é
    o oposto de um impacto.
    """
    for x, y in _amostras():
        assert x % _ESCALA == 0 and y % _ESCALA == 0, f"fora da grade: {(x, y)}"


def test_o_tremor_respeita_a_amplitude_declarada():
    limite = DEATH_SHAKE_ART_PIXELS * _ESCALA
    for x, y in _amostras():
        assert abs(x) <= limite and abs(y) <= limite, f"estourou: {(x, y)}"


def test_os_dois_eixos_nao_tremem_juntos():
    """Frequências incomensuráveis: com a mesma, o tremor vira deslize diagonal."""
    amostras = [a for a in _amostras() if a != (0, 0)]
    diagonais = sum(1 for x, y in amostras if x == y or x == -y)
    assert diagonais < len(amostras) * 0.6, (
        "o tremor está preso na diagonal — os eixos batem em fase"
    )


def test_o_tremor_e_o_mesmo_em_qualquer_frame_rate():
    """Função pura do tempo decorrido: nada de aleatório por frame."""
    for t in (0.0, 0.05, 0.21, 0.4):
        assert death_shake(t, _DUR, _ESCALA) == death_shake(t, _DUR, _ESCALA)
    # E uma parte sem arte de morte (duração 0) não treme.
    assert death_shake(0.1, 0.0, _ESCALA) == (0, 0)
