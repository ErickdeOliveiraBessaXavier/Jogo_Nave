"""AtmosphereState — estado de runtime da fase de atmosfera.

Um dataclass de estado consolidado (extraído da PlayingScene). Não tem
comportamento, então os testes travam o CONTRATO de que a cena depende: os
defaults de um estado fresco = "fora da atmosfera, tudo zerado", e que
`death_ships` não é compartilhado entre instâncias (o clássico bug de default
mutável, que aqui derrubaria a cinemática de nocaute de uma partida na outra).
"""

from game.core.atmosphere_phase import AtmosphereState


def test_defaults_de_estado_fresco():
    a = AtmosphereState()
    assert a.in_atmosphere is False
    assert a.route is None
    assert a.progress == 0.0
    assert a.phase_done is False
    assert a.regressing is False
    assert (a.regress_from, a.regress_to, a.regress_elapsed, a.regress_duration) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert a.death_active is False
    assert a.death_phase == "out"
    assert a.death_timer == 0.0
    assert a.death_ships == []


def test_death_ships_nao_compartilha_entre_instancias():
    a, b = AtmosphereState(), AtmosphereState()
    a.death_ships.append(("ship", 0.0, 0.0, 1.0))
    assert b.death_ships == []
