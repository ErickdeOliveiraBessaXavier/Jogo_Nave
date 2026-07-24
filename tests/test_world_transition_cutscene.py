"""Testes do `WorldTransitionCutscene` (extraído da `PlayingScene`, §9).

A prova de que a extração deu certo é esta: o controller roda com **stubs
mínimos** (uma nave falsa, um entity_manager falso e callbacks), sem instanciar a
cena nem o jogo. Trava o contrato: `start` arma a animação e entra na fase de
cutscene; `update` avança a cinemática, gera partículas e, ao fim da duração,
dispara o callback de FLUXO uma única vez com o mundo/debug corretos.
"""

from game.core.config import config as Config
from game.systems.world_transition_cutscene import WorldTransitionCutscene


class _FakeShip:
    def __init__(self):
        self.x = 100.0
        self.y = 200.0
        self.w = 32
        self.h = 32
        self.ship_image = None
        self.is_entering = False
        self.entering_duration = 999.0
        self.is_side_scroll = False
        self.facing = None
        self.update_calls = 0

    def set_facing(self, facing):
        self.facing = facing

    def update(self, dt, entity_manager, is_side_scroll=False):
        self.update_calls += 1


class _FakeWorld:
    def __init__(self, name="Mundo Teste"):
        self.name = name


def _make(active_flag, *, side_scroll=False, completions=None):
    """Cria o controller com stubs. `active_flag` é uma lista de 1 bool mutável
    (o teste liga/desliga a "fase de cutscene"). `completions` coleta as chamadas
    de on_complete."""
    ship = _FakeShip()
    ship.is_side_scroll = side_scroll
    completions = completions if completions is not None else []
    phase_entered = []

    def _on_complete(tw, dbg):
        # Espelha o FSM real: ao concluir, a cena deixa a fase CUTSCENE_EXIT, então
        # `is_active` passa a False (senão a cutscene reiniciaria em loop).
        active_flag[0] = False
        completions.append((tw, dbg))

    ctrl = WorldTransitionCutscene(
        get_ship=lambda: ship,
        get_side_scroll=lambda: side_scroll,
        get_entity_manager=lambda: object(),
        is_active=lambda: active_flag[0],
        enter_cutscene_phase=lambda: phase_entered.append(True),
        on_complete=_on_complete,
    )
    return ctrl, ship, completions, phase_entered


class TestStart:
    def test_arma_animacao_e_entra_na_fase(self):
        ctrl, ship, _, phase_entered = _make([False])
        world = _FakeWorld()
        ctrl.start(world)
        assert phase_entered == [True]  # callback de fase disparado
        assert ctrl.target_world is world
        assert ctrl.origin == (100.0, 200.0)  # origem = posição atual da nave
        assert ship.is_entering is True
        assert ship.entering_duration == 0.0
        assert ship.facing == "north"  # top-down, subindo
        assert ctrl.particles == []

    def test_facing_por_modo(self):
        ctrl, ship, _, _ = _make([False], side_scroll=True)
        ctrl.start(_FakeWorld())
        assert ship.facing == "east"

        ctrl2, ship2, _, _ = _make([False])
        ctrl2.start(_FakeWorld(), launch_down=True)
        assert ship2.facing == "south"  # re-entry desce


class TestUpdate:
    def test_inativo_nao_faz_nada(self):
        ctrl, ship, completions, _ = _make([False])
        ctrl.start(_FakeWorld())
        ship.update_calls = 0
        ctrl.update(0.1)  # is_active() == False → early return
        assert ship.update_calls == 0
        assert completions == []

    def test_gera_particulas_durante_a_carga(self):
        active = [True]
        ctrl, _, _, _ = _make(active)
        ctrl.start(_FakeWorld())
        ctrl.update(0.01)  # início da carga → tremor + thrusters
        assert len(ctrl.particles) > 0

    def test_completa_e_dispara_fluxo_uma_vez(self):
        active = [True]
        completions = []
        ctrl, _, completions, _ = _make(active, completions=completions)
        world = _FakeWorld()
        ctrl.start(world, debug_mode=True)

        # Avança em passos pequenos além da duração total da cutscene.
        steps = int(Config.WORLD_TRANSITION_CUTSCENE_DURATION / 0.016) + 10
        for _ in range(steps):
            ctrl.update(0.016)

        assert len(completions) == 1, "on_complete deveria disparar exatamente uma vez"
        target, debug = completions[0]
        assert target is world
        assert debug is True
        # Estado da animação foi limpo no _finish.
        assert ctrl.target_world is None
        assert ctrl.particles == []

    def test_particulas_decaem_e_somem(self):
        active = [True]
        ctrl, _, _, _ = _make(active)
        ctrl.start(_FakeWorld())
        ctrl.update(0.01)
        assert len(ctrl.particles) > 0
        # Sem novas emissões (fase inativa) e dt grande → todas expiram.
        active[0] = True
        for _ in range(50):
            ctrl._update_particles(1.0)
        assert ctrl.particles == []


class TestActive:
    def test_reflete_o_callback(self):
        flag = [False]
        ctrl, _, _, _ = _make(flag)
        assert ctrl.active is False
        flag[0] = True
        assert ctrl.active is True
