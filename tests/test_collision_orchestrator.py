"""Testes do CollisionOrchestrator (extraído da PlayingScene, §9).

A lógica dos passes é verbatim do original (a equivalência de comportamento é
garantida pela transcrição + a suíte inteira verde). Aqui travamos os helpers
puros que mudaram de casa (multiplicador de score, batching de floating scores) e
um smoke de `run()` sobre um EntityManager REAL — prova de que a orquestração roda
ponta-a-ponta sem crashar e devolve um CollisionResult zerado quando nada colide.
"""

from game.systems.collision_orchestrator import CollisionOrchestrator, CollisionResult
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager


class _LevelControllerStub:
    base_score_multiplier = 2.0


class _BossControllerStub:
    boss_type = None


class _RosterStub:
    def __init__(self, slots=()):
        self._slots = list(slots)

    def alive_slots(self):
        return list(self._slots)


def _orch(*, em=None, roster=None, mult=(False, 1.5), collisions=None):
    return CollisionOrchestrator(
        entity_manager=em,
        collisions=collisions or Collisions(),
        roster=roster or _RosterStub(),
        boss_controller=_BossControllerStub(),
        level_controller=_LevelControllerStub(),
        on_ship_hit=lambda slot: None,
        get_last_dt=lambda: 0.016,
        get_multiplier_state=lambda: mult,
        get_batch_threshold=lambda: 60.0,
    )


class TestScoreMultiplier:
    def test_base_vezes_bonus_quando_ativo(self):
        # base 2.0 * bônus 1.5 = 3.0 → 10 pts vira 30.
        assert _orch(mult=(True, 1.5))._apply_score_multiplier(10) == 30

    def test_so_base_quando_bonus_inativo(self):
        assert _orch(mult=(False, 1.5))._apply_score_multiplier(10) == 20


class TestBatchFloatingScores:
    def test_agrupa_proximos_e_soma_pontos(self):
        o = _orch()
        events = [(100.0, 100.0, 5), (110.0, 105.0, 7), (500.0, 500.0, 3)]
        batched = o._batch_floating_scores(events, proximity_threshold=60.0)
        # Os dois próximos (dist ~11) viram um só (5+7=12); o distante fica sozinho.
        assert sorted(b[2] for b in batched) == [3, 12]

    def test_lista_vazia(self):
        assert _orch()._batch_floating_scores([]) == []

    def test_distantes_nao_agrupam(self):
        o = _orch()
        events = [(0.0, 0.0, 1), (1000.0, 1000.0, 1)]
        assert len(o._batch_floating_scores(events, proximity_threshold=60.0)) == 2


class TestRunSmoke:
    def test_run_em_vazio_retorna_resultado_zerado(self):
        em = EntityManager()
        result = _orch(em=em, roster=_RosterStub([])).run()
        assert isinstance(result, CollisionResult)
        assert result.score_gain == 0
        assert result.enemies_destroyed == 0
        assert result.floating_scores == []
