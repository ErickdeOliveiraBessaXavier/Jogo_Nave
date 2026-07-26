"""Testes da lentidão por vórtice (GRAVITY_BOMB).

Existem porque um merge descartou as constantes `VORTEX_SLOW_*` de `BlackHole`
mas manteve os usos, em `EntityManager._vortex_multiplier` e no próprio
`BlackHole.process_all_enemies`. A suíte inteira ficou verde e o `ruff` também:
nada exercitava o caminho, e o `getattr(entity, "vortex_slow_timer", 0.0)`
esconde a ausência da marca — só o acesso à constante estourava, em runtime,
no instante em que um inimigo entrava no campo.

Travam o contrato mínimo: a constante existe, o multiplicador a devolve, e o
linger decai até zerar.
"""

from game.entities.enemies.space.black_hole import BlackHole
from game.systems.entity_manager import EntityManager


class _Enemy:
    """Inimigo mínimo — o multiplicador só lê `vortex_slow_timer`."""


def test_constantes_de_slow_existem():
    # O merge que motivou este arquivo removeu exatamente estas duas.
    assert isinstance(BlackHole.VORTEX_SLOW_FACTOR, float)
    assert isinstance(BlackHole.VORTEX_SLOW_LINGER, float)


def test_fator_de_slow_desacelera_sem_congelar():
    # Faixa, não número exato (§16): trava outlier grosseiro, não o micro-ajuste.
    assert 0.0 < BlackHole.VORTEX_SLOW_FACTOR < 1.0


def test_linger_cobre_a_ordem_de_frame_a_30fps():
    """`_update_environment` roda depois de `_update_enemies`, então a marca só
    é lida no frame seguinte. O linger precisa sobreviver a um frame do pior
    caso — 1/30s, o piso do clamp de dt (§14)."""
    assert BlackHole.VORTEX_SLOW_LINGER > 1.0 / 30.0


def test_multiplicador_neutro_sem_marca():
    assert EntityManager._vortex_multiplier(_Enemy()) == 1.0


def test_multiplicador_aplica_o_fator_com_marca_ativa():
    enemy = _Enemy()
    enemy.vortex_slow_timer = BlackHole.VORTEX_SLOW_LINGER
    assert EntityManager._vortex_multiplier(enemy) == BlackHole.VORTEX_SLOW_FACTOR


def test_linger_decai_e_zera_sem_ficar_negativo():
    enemy = _Enemy()
    enemy.vortex_slow_timer = BlackHole.VORTEX_SLOW_LINGER

    # Um passo curto mantém a marca viva.
    EntityManager._update_vortex_linger(enemy, BlackHole.VORTEX_SLOW_LINGER / 2)
    assert enemy.vortex_slow_timer > 0.0
    assert EntityManager._vortex_multiplier(enemy) == BlackHole.VORTEX_SLOW_FACTOR

    # Um passo longo zera exatamente, sem estourar para negativo.
    EntityManager._update_vortex_linger(enemy, 999.0)
    assert enemy.vortex_slow_timer == 0.0
    assert EntityManager._vortex_multiplier(enemy) == 1.0
