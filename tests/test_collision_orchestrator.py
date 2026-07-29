"""Testes do CollisionOrchestrator (extraído da PlayingScene, §9).

A lógica dos passes é verbatim do original (a equivalência de comportamento é
garantida pela transcrição + a suíte inteira verde). Aqui travamos os helpers
puros que mudaram de casa (multiplicador de score, batching de floating scores) e
um smoke de `run()` sobre um EntityManager REAL — prova de que a orquestração roda
ponta-a-ponta sem crashar e devolve um CollisionResult zerado quando nada colide.
"""

from game.systems.collision_orchestrator import CollisionOrchestrator, CollisionResult
from game.systems.collision_protocols import ScoreEvent
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
        events = [
            ScoreEvent(100.0, 100.0, 5),
            ScoreEvent(110.0, 105.0, 7),
            ScoreEvent(500.0, 500.0, 3),
        ]
        batched = o._batch_floating_scores(events, proximity_threshold=60.0)
        # Os dois próximos (dist ~11) viram um só (5+7=12); o distante fica sozinho.
        assert sorted(b.points for b in batched) == [3, 12]

    def test_lista_vazia(self):
        assert _orch()._batch_floating_scores([]) == []

    def test_distantes_nao_agrupam(self):
        o = _orch()
        events = [ScoreEvent(0.0, 0.0, 1), ScoreEvent(1000.0, 1000.0, 1)]
        assert len(o._batch_floating_scores(events, proximity_threshold=60.0)) == 2


class TestCriticalNoAgrupamento:
    """O vermelho do crítico tem que sobreviver ao agrupamento.

    O grupo vira UM número só; se o `critical` se perdesse na soma, o feedback
    sumiria exatamente quando há mais coisa morrendo na tela — o momento em que
    o upgrade mais precisa aparecer.
    """

    @staticmethod
    def _perto(n: int, critical_no_indice: int | None):
        return [
            ScoreEvent(100.0 + i, 100.0, 5, critical_no_indice == i)
            for i in range(n)
        ]

    def test_um_critico_pinta_o_grupo(self):
        batched = _orch()._batch_floating_scores(self._perto(3, 1), 60.0)
        assert len(batched) == 1
        assert batched[0].critical is True

    def test_grupo_sem_critico_fica_normal(self):
        batched = _orch()._batch_floating_scores(self._perto(3, None), 60.0)
        assert batched[0].critical is False

    def test_vale_tambem_no_caminho_de_grid(self):
        """Acima de 8 eventos o batching troca de algoritmo — os dois precisam
        propagar a marca, senão o crítico some só nos picos de combate."""
        eventos = self._perto(12, 7)
        batched = _orch()._batch_floating_scores(eventos, 60.0)
        assert any(b.critical for b in batched)

    def test_grupos_distantes_nao_contaminam(self):
        o = _orch()
        eventos = [
            ScoreEvent(100.0, 100.0, 5, True),
            ScoreEvent(900.0, 900.0, 5, False),
        ]
        batched = sorted(o._batch_floating_scores(eventos, 60.0), key=lambda b: b.x)
        assert [b.critical for b in batched] == [True, False]

    def test_o_multiplicador_de_score_preserva_a_marca(self):
        """`_replace` do NamedTuple: trocar os pontos não pode zerar a cor."""
        evento = ScoreEvent(10.0, 20.0, 7, True)
        aplicado = evento._replace(points=_orch()._apply_score_multiplier(evento.points))
        assert (aplicado.points, aplicado.critical) == (14, True)


class TestRunSmoke:
    def test_run_em_vazio_retorna_resultado_zerado(self):
        em = EntityManager()
        result = _orch(em=em, roster=_RosterStub([])).run()
        assert isinstance(result, CollisionResult)
        assert result.score_gain == 0
        assert result.enemies_destroyed == 0
        assert result.floating_scores == []
