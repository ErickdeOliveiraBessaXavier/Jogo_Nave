"""Escudo concede 1s de invulnerabilidade ao absorver um hit.

Protege contra dano consecutivo imediato: dois acertos no mesmo instante não
podem gastar duas cargas nem vazar para a vida.
"""

from game.core.config import config as Config
from game.core.ship_types import get_ship_profile
from game.entities.player.ship import Ship


def _ship():
    return Ship(100, 100, profile=get_ship_profile("padrao"))


def test_absorver_concede_invuln_de_um_segundo():
    s = _ship()
    s.activate_shield(9999.0, shield_hp=2)
    assert s.take_damage(1) is False  # absorvido, não perde vida
    assert s.invuln == Config.SHIELD_ABSORB_INVULN_MS == 1000.0
    assert s.shield_hp == 1


def test_hit_durante_invuln_nao_consome_segunda_carga():
    s = _ship()
    s.activate_shield(9999.0, shield_hp=2)
    s.take_damage(1)  # gasta 1 carga, entra em invuln
    s.take_damage(1)  # imediato: is_invulnerable bloqueia
    assert s.shield_hp == 1  # a 2ª carga sobrevive


def test_invuln_nao_encurta_um_maior_ja_ativo():
    s = _ship()
    s.activate_shield(9999.0, shield_hp=1)
    s.invuln = 5000.0  # já invulnerável por mais tempo (ex.: respawn)
    # is_invulnerable bloqueia o dano antes de tocar o escudo — invuln intacto.
    s.take_damage(1)
    assert s.invuln == 5000.0
    assert s.shield_hp == 1
