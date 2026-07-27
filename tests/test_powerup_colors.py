"""Fonte única da identidade visual dos power-ups.

Cada power-up aparece em dois lugares — o pickup no chão
(`entities/pickups/powerup.py`) e a faixa de efeitos ativos do HUD
(`render/game_renderer.py`). Os dois tinham tabelas de cor independentes, então
o mesmo power-up podia estar em duas cores ao mesmo tempo na tela, e um
power-up novo podia entrar em um lado e não no outro.

Estes testes travam as três formas de a divergência voltar: cor diferente entre
os dois lados, tipo sem registro, e registro órfão.
"""

import itertools

import pytest

from game.core import colors
from game.core.config import PowerUpType
from game.entities.pickups.powerup import PowerUp
from game.render.game_renderer import GameRenderer


def powerup_kinds() -> list[str]:
    return [t.value for t in PowerUpType]


class TestCobertura:
    def test_todo_powerup_tem_cor_registrada(self):
        """O esquecimento que deixou dois pickups BRANCOS.

        `chain_shot` e `repulsion_shield` tinham constante de cor definida em
        `colors.py` e nenhum leitor — o mapa do pickup não os listava, então
        caíam no fallback branco no chão.
        """
        faltando = [k for k in powerup_kinds() if k not in colors.POWERUP_COLORS]
        assert not faltando

    def test_todo_powerup_tem_rotulo_no_pickup(self):
        faltando = [k for k in powerup_kinds() if k not in PowerUp.LABELS]
        assert not faltando

    def test_todo_powerup_aparece_no_hud(self):
        faltando = [k for k in powerup_kinds() if k not in GameRenderer.POWERUP_UI_DATA]
        assert not faltando

    def test_sem_registro_orfao(self):
        """Chave que não corresponde a nenhum `PowerUpType` é erro de digitação
        silencioso — o power-up real cai no fallback."""
        conhecidos = set(powerup_kinds())
        assert set(colors.POWERUP_COLORS) <= conhecidos
        assert set(PowerUp.LABELS) <= conhecidos


class TestUnificacao:
    def test_hud_usa_a_mesma_cor_do_pickup(self):
        """O pedido que originou este arquivo.

        O HUD usava a paleta genérica (PURPLE, CYAN, ...) e o pickup usava as
        constantes `POWERUP_*`. `time_stop` era (180,120,255) no chão e
        (200,0,255) no HUD.
        """
        for kind in powerup_kinds():
            assert (
                GameRenderer.POWERUP_UI_DATA[kind]["color"]
                == colors.POWERUP_COLORS[kind]
            ), kind

    def test_pickup_usa_a_fonte_unica(self):
        for kind in powerup_kinds():
            pickup = PowerUp(PowerUpType(kind))
            assert pickup._border_color() == colors.POWERUP_COLORS[kind], kind

    def test_cores_sao_distintas_entre_si(self):
        """`piercing_shot` e `time_stop` eram ambos PURPLE no HUD — dois
        power-ups diferentes, ícone da mesma cor."""
        vistos: dict[tuple[int, int, int], str] = {}
        for kind, cor in colors.POWERUP_COLORS.items():
            assert cor not in vistos, f"{kind} tem a mesma cor de {vistos.get(cor)}"
            vistos[cor] = kind


# ---------------------------------------------------------------------------
# Separação perceptual
# ---------------------------------------------------------------------------

# Distância mínima em CIELAB (ΔE76) entre quaisquer duas cores de power-up.
# Igualdade exata não basta: `cooldown_haste` (80,200,255) e `chain_shot`
# (80,220,255) eram tecnicamente diferentes e o mesmo azul na tela — ΔE 13.
# 40 é folgado o bastante para ícones pequenos em movimento sobre fundo escuro.
DELTA_E_MINIMO = 40.0


def _srgb_para_linear(canal: float) -> float:
    c = canal / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _para_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_srgb_para_linear(v) for v in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    l1, a1, b1 = _para_lab(c1)
    l2, a2, b2 = _para_lab(c2)
    return ((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5


class TestSeparacaoPerceptual:
    def test_metrica_confere_com_referencias_conhecidas(self):
        """Sanidade da implementação de ΔE antes de confiar nela."""
        assert delta_e((0, 0, 0), (0, 0, 0)) == 0.0
        assert delta_e((0, 0, 0), (255, 255, 255)) == pytest.approx(100.0, abs=0.5)

    def test_nenhum_par_e_confundivel(self):
        proximos = [
            (delta_e(c1, c2), k1, k2)
            for (k1, c1), (k2, c2) in itertools.combinations(
                colors.POWERUP_COLORS.items(), 2
            )
            if delta_e(c1, c2) < DELTA_E_MINIMO
        ]
        assert not proximos, "pares perceptualmente próximos: " + ", ".join(
            f"{k1}x{k2} (dE={d:.1f})" for d, k1, k2 in sorted(proximos)
        )


class TestEfeitosNaoPowerup:
    def test_explosive_shot_e_upgrade_e_nao_pickup(self):
        """Está no HUD mas não é `PowerUpType`: é o upgrade
        (`core/upgrades.py`), que aparece na faixa de efeitos ativos e não
        existe como pickup no chão. Por isso a cor dele mora no renderer.
        """
        assert "explosive_shot" in GameRenderer.POWERUP_UI_DATA
        assert "explosive_shot" not in powerup_kinds()
        assert "explosive_shot" not in colors.POWERUP_COLORS
