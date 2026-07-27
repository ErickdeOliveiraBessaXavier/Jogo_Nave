"""Testes da piscada acelerada (`core/blink.py`).

Lógica pura, sem pygame: `visible()` é função só do tempo restante.

O que travam é o que o jogador de fato lê na tela — acelera de verdade, não
sobra piscada depois do fim, e a fase nunca anda para trás (o engasgo que
aparece quando se varia a frequência sem integrá-la).
"""

import math

import pytest

from game.core.blink import SHIP_INVULN_BLINK, BlinkProfile

FPS = 60
DT = 1.0 / FPS


def _frames(profile: BlinkProfile, total: float) -> list[bool]:
    """Estado de visibilidade quadro a quadro, do início ao fim do efeito."""
    out: list[bool] = []
    remaining = total
    while remaining > 0.0:
        out.append(profile.visible(remaining, total))
        remaining = max(0.0, remaining - DT)
    return out


def _runs(frames: list[bool]) -> list[int]:
    """Duração (em frames) de cada trecho aceso/apagado, em ordem."""
    runs: list[int] = []
    atual, n = frames[0], 0
    for f in frames:
        if f == atual:
            n += 1
        else:
            runs.append(n)
            atual, n = f, 1
    runs.append(n)
    return runs


TOTAIS = [3.0, 1.0, 12.0, 0.35]


# ── O requisito visível ─────────────────────────────────────────────────────


@pytest.mark.parametrize("total", TOTAIS)
def test_pisca_mais_rapido_no_fim(total):
    """O ponto do efeito: os últimos trechos são nitidamente mais curtos."""
    runs = _runs(_frames(SHIP_INVULN_BLINK, total))
    if len(runs) < 6:
        pytest.skip(f"efeito curto demais para medir aceleração (total={total})")

    inicio = sum(runs[:2]) / 2
    fim = sum(runs[-2:]) / 2
    assert fim < inicio, f"não acelerou: início {inicio:.1f}f, fim {fim:.1f}f"
    assert inicio / fim >= 1.8, (
        f"aceleração fraca demais para ser percebida: {inicio / fim:.1f}×"
    )


@pytest.mark.parametrize("total", TOTAIS)
def test_sem_piscada_residual_depois_do_fim(total):
    """"No instante em que a invulnerabilidade terminar, a nave deve voltar
    imediatamente ao estado normal." Nada de um frame apagado sobrando."""
    assert SHIP_INVULN_BLINK.visible(0.0, total)
    assert SHIP_INVULN_BLINK.visible(-1.0, total)
    # E o último frame ANTES do fim também já está aceso — sem salto na virada.
    assert SHIP_INVULN_BLINK.visible(DT / 2, total)


@pytest.mark.parametrize("total", TOTAIS)
def test_comeca_com_a_nave_visivel(total):
    """O frame do dano não pode pegar a nave apagada: some junto com o clarão
    do impacto e o jogador perde a nave de vista."""
    frames = _frames(SHIP_INVULN_BLINK, total)
    assert frames[0], "primeiro frame apagado"


@pytest.mark.parametrize("total", TOTAIS)
def test_nenhum_trecho_curto_demais_para_o_olho(total):
    """Abaixo de ~2 frames a 60fps a piscada vira cintilação e some a leitura
    de ritmo (e incomoda quem tem sensibilidade)."""
    runs = _runs(_frames(SHIP_INVULN_BLINK, total))
    assert min(runs) >= 2, f"trecho de {min(runs)} frame(s): {runs}"


# ── Por que a implementação é integral, e não `int(t*hz)` ───────────────────


@pytest.mark.parametrize("total", TOTAIS)
def test_fase_nunca_anda_para_tras(total):
    """A razão de integrar a frequência.

    Com `int(tempo * hz)` e um `hz` crescente, a fase salta e chega a
    RETROCEDER entre frames — a piscada engasga em vez de acelerar. Aqui a fase
    é monótona por construção, e este teste é o que impede alguém de
    "simplificar" de volta.
    """
    fases = [
        SHIP_INVULN_BLINK._phase(total * k / 400.0, total) for k in range(400, -1, -1)
    ]
    for anterior, seguinte in zip(fases, fases[1:]):
        assert seguinte <= anterior + 1e-9, "a fase retrocedeu"


@pytest.mark.parametrize("total", TOTAIS)
def test_frequencia_cresce_monotonicamente(total):
    freqs = [
        SHIP_INVULN_BLINK.frequency_at(total * k / 100.0, total)
        for k in range(100, -1, -1)
    ]
    for anterior, seguinte in zip(freqs, freqs[1:]):
        assert seguinte >= anterior - 1e-9


# ── Parametrização (o pedido explícito de reutilização) ─────────────────────


def test_perfil_respeita_as_frequencias_configuradas():
    p = BlinkProfile(slow_hz=1.0, fast_hz=8.0, ramp_seconds=2.0, ramp_fraction=1.0)
    assert p.frequency_at(10.0, 10.0) == pytest.approx(1.0)
    assert p.frequency_at(0.0, 10.0) == pytest.approx(8.0)
    # Na entrada da rampa ainda é a frequência lenta.
    assert p.frequency_at(p.ramp_for(10.0), 10.0) == pytest.approx(1.0)


def test_rampa_e_o_menor_entre_o_teto_e_a_fracao():
    """Efeito curto usa a fração (não acelera do início ao fim); efeito longo
    bate no teto (não passa meio minuto acelerando)."""
    p = BlinkProfile(ramp_seconds=4.0, ramp_fraction=0.5)
    assert p.ramp_for(2.0) == pytest.approx(1.0)   # fração manda
    assert p.ramp_for(60.0) == pytest.approx(4.0)  # teto manda
    assert p.ramp_for(0.0) == 0.0


def test_perfil_sem_rampa_pisca_em_frequencia_constante():
    """`ramp_fraction=0` degrada para o comportamento antigo — útil para um
    efeito que não deva comunicar urgência."""
    p = BlinkProfile(slow_hz=5.0, fast_hz=20.0, ramp_seconds=0.0, ramp_fraction=0.0)
    runs = _runs(_frames(p, 3.0))
    # Todos os trechos com a mesma duração (±1 frame de arredondamento).
    assert max(runs) - min(runs) <= 1, runs


def test_duracao_zero_ou_negativa_nao_pisca():
    """Guarda contra divisão por zero e contra piscar sem efeito ativo."""
    assert SHIP_INVULN_BLINK.visible(0.0, 0.0)
    assert SHIP_INVULN_BLINK.visible(1.0, 0.0)
    assert SHIP_INVULN_BLINK.visible(-1.0, -1.0)
    assert not math.isnan(SHIP_INVULN_BLINK.frequency_at(1.0, 0.0))
