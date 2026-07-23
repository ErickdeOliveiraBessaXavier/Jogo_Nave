"""Ciclo de cooldown do upgrade: recarga começa ao FIM do efeito, não na ativação.

Trava o comportamento pedido — a janela de cooldown vem DEPOIS da duração, não
em paralelo. O tempo total indisponível = duração + cooldown.
"""

from game.core.upgrades import (
    ActiveUpgrade,
    UpgradeCategory,
    UpgradeMeta,
    UpgradeType,
)


def _meta(cooldown=5.0, duration=2.0, charges=None):
    return UpgradeMeta(
        type=UpgradeType.EMP,
        name="Test",
        desc="",
        icon_id="",
        category=UpgradeCategory.UTILITY,
        base_cooldown=cooldown,
        base_duration=duration,
        base_charges=charges,
    )


class _Ctx:
    ship = None
    entity_manager = None
    difficulty_settings = {}
    sound_manager = None
    god_mode = False
    scene = None


def test_cooldown_nao_comeca_na_ativacao():
    upg = ActiveUpgrade(_meta(cooldown=5.0, duration=2.0))
    ctx = _Ctx()
    assert upg.activate(ctx)
    # Logo após ativar: efeito ATIVO, cooldown ainda ZERO (não conta em paralelo).
    assert upg.active
    assert upg.cooldown_left == 0.0


def test_cooldown_comeca_ao_fim_da_duracao():
    upg = ActiveUpgrade(_meta(cooldown=5.0, duration=2.0))
    ctx = _Ctx()
    upg.activate(ctx)

    # Durante a duração, cooldown segue zero.
    upg.update(1.0, ctx)
    assert upg.active
    assert upg.cooldown_left == 0.0

    # No tick que zera a duração, o cooldown parte com o valor cheio.
    upg.update(1.0, ctx)
    assert not upg.active
    assert upg.cooldown_left == 5.0


def test_indisponivel_durante_duracao_e_cooldown():
    upg = ActiveUpgrade(_meta(cooldown=5.0, duration=2.0))
    ctx = _Ctx()
    upg.activate(ctx)
    # Durante a duração: indisponível (active bloqueia).
    assert not upg.can_activate(ctx)
    upg.update(2.0, ctx)  # termina a duração → cooldown parte
    # Durante o cooldown: indisponível.
    assert upg.cooldown_left > 0.0
    assert not upg.can_activate(ctx)
    # Ao fim do cooldown: disponível de novo.
    upg.update(5.0, ctx)
    assert upg.cooldown_left == 0.0
    assert upg.can_activate(ctx)


def test_upgrade_instantaneo_ganha_cooldown_no_tick_seguinte():
    # Duração 0 (efeito instantâneo, ex.: Heal): expira no 1º update e o
    # cooldown parte aí.
    upg = ActiveUpgrade(_meta(cooldown=3.0, duration=0.0))
    ctx = _Ctx()
    upg.activate(ctx)
    assert upg.active  # ativo por 1 tick
    upg.update(0.016, ctx)
    assert not upg.active
    assert upg.cooldown_left == 3.0
