"""Invariantes de balanceamento das naves.

Não fixa números exatos (que mudam a cada ajuste), e sim as **fronteiras** que
não devem ser cruzadas sem uma decisão consciente: dano com piso, cadência
positiva, e o índice composto de poder de cada nave dentro de uma faixa. É a
rede que teria pego, de graça, os desvios silenciosos desta base.
"""

import math

import pytest

from game.core.config import config as Config
from game.core.ship_types import SHIP_REGISTRY, get_ship_profile
from game.systems.shooting_system import _round_damage

# Tiers de HP representativos, ignorando inimigos de 1 tiro (o combate onde as
# diferenças entre naves realmente aparecem).
LOW = [15, 18]
MID = [45, 50, 55, 70, 80, 100, 130]
HIGH = [240, 320, 950]


def _kills_per_second(shots_per_s, damage, hp):
    return shots_per_s / math.ceil(hp / damage)


def _composite_index(profile, baseline):
    """Índice de abates/s ponderado por mix de encontro, relativo à baseline."""
    from game.entities.ship import Ship

    def rate(prof):
        ship = Ship(0, 0, profile=prof)
        sps = Config.FIRE_RATE * ship.attack_speed_multiplier
        dmg = _round_damage(Config.BULLET_BASE_DAMAGE * ship.damage_multiplier)

        def avg(group):
            return sum(_kills_per_second(sps, dmg, h) for h in group) / len(group)

        return 0.4 * avg(LOW) + 0.45 * avg(MID) + 0.15 * avg(HIGH)

    return rate(profile) / rate(baseline)


class TestRoundDamage:
    def test_meio_para_cima(self):
        assert _round_damage(6.5) == 7
        assert _round_damage(8.5) == 9

    def test_piso_um(self):
        # Nenhum tiro causa 0 de dano, por menor que seja o multiplicador.
        assert _round_damage(0.2) == 1
        assert _round_damage(0.0) == 1

    def test_nao_trunca_como_int(self):
        # O bug corrigido: int(8.5)==8 comia a fração de toda nave com
        # multiplicador quebrado. round_damage devolve 9.
        assert _round_damage(8.5) != int(8.5)


class TestShipProfiles:
    def test_todas_tem_dano_e_cadencia_positivos(self):
        for p in SHIP_REGISTRY:
            assert p.damage_mult > 0, p.id
            assert p.fire_rate_mult > 0, p.id

    def test_nenhuma_nave_causa_dano_zero(self):
        for p in SHIP_REGISTRY:
            dmg = _round_damage(Config.BULLET_BASE_DAMAGE * p.damage_mult)
            assert dmg >= 1, p.id

    def test_bullet_speed_e_pierce_sao_sensatos(self):
        for p in SHIP_REGISTRY:
            assert 0.5 <= p.bullet_speed_mult <= 2.0, p.id
            assert 0 <= p.pierce_count <= 3, p.id

    @pytest.mark.parametrize("ship_id", [p.id for p in SHIP_REGISTRY])
    def test_indice_composto_na_faixa(self, ship_id):
        # Nenhuma nave deve ser dominante nem inútil. A faixa é folgada de
        # propósito — trava outliers grosseiros (um 2x ou 0.5x acidental de um
        # ajuste), não micro-balanceamento.
        baseline = get_ship_profile("padrao")
        idx = _composite_index(get_ship_profile(ship_id), baseline)
        assert 0.7 <= idx <= 1.5, f"{ship_id} fora da faixa: {idx:.2f}"

    def test_padrao_e_a_referencia(self):
        # A nave inicial é o 1.00 por definição do modelo.
        baseline = get_ship_profile("padrao")
        assert math.isclose(_composite_index(baseline, baseline), 1.0)
