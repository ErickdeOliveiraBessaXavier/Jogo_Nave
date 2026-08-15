"""Ciclo de cooldown do upgrade: recarga começa ao FIM do efeito, não na ativação.

Trava o comportamento pedido — a janela de cooldown vem DEPOIS da duração, não
em paralelo. O tempo total indisponível = duração + cooldown.
"""

from game.core.upgrades import (
    UPGRADES_META,
    ActiveUpgrade,
    ExplosiveShotUpgrade,
    OrbitalDischargeUpgrade,
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


# --- Upgrades por munição: cooldown espera a última carga, não o relógio -----


class _FakeExplosiveShip:
    """Nave mínima: só o contrato de munição do tiro explosivo."""

    def __init__(self) -> None:
        self.explosive_shots_active = False
        self.explosive_shots_remaining = 0

    def activate_explosive_shots(self, charges: int) -> None:
        self.explosive_shots_active = True
        self.explosive_shots_remaining = charges

    def consume_explosive_shot(self) -> bool:
        if self.explosive_shots_remaining > 0:
            self.explosive_shots_remaining -= 1
            if self.explosive_shots_remaining <= 0:
                self.explosive_shots_active = False
            return True
        return False


class _FakeLaserShip:
    def __init__(self) -> None:
        self.orbital_discharge_active = False

    def activate_orbital_discharge(self, _duration: float) -> None:
        self.orbital_discharge_active = True


def test_explosive_shot_cooldown_so_parte_quando_municao_acaba():
    # base_duration é 0, mas o efeito é medido em BALAS: enquanto restar munição,
    # o efeito segue ATIVO e o cooldown fica ZERADO (não conta em paralelo).
    upg = ExplosiveShotUpgrade(UPGRADES_META[UpgradeType.EXPLOSIVE_SHOT])
    ship = _FakeExplosiveShip()
    ctx = _Ctx()
    ctx.ship = ship

    assert upg.activate(ctx)
    assert upg.active
    assert ship.explosive_shots_active
    assert upg.cooldown_left == 0.0

    # Vários ticks com balas ainda no cano: efeito ativo, cooldown parado.
    for _ in range(20):
        upg.update(0.5, ctx)
    assert upg.active
    assert upg.cooldown_left == 0.0

    # Gasta toda a munição (fora do timer): efeito termina.
    while ship.consume_explosive_shot():
        pass
    assert not ship.explosive_shots_active

    # O próximo tick detecta o fim do efeito → cooldown parte CHEIO.
    upg.update(0.016, ctx)
    assert not upg.active
    assert upg.cooldown_left == upg.get_effective_cooldown(ctx)
    assert upg.cooldown_left > 0.0


def test_orbital_discharge_cooldown_espera_cargas_dos_orbes():
    upg = OrbitalDischargeUpgrade(UPGRADES_META[UpgradeType.ORBITAL_DISCHARGE])
    ship = _FakeLaserShip()
    ctx = _Ctx()
    ctx.ship = ship

    assert upg.activate(ctx)
    assert upg.active
    assert upg.cooldown_left == 0.0

    # Enquanto os orbes têm carga, o cooldown não anda.
    for _ in range(10):
        upg.update(0.5, ctx)
    assert upg.active
    assert upg.cooldown_left == 0.0

    # Orbes descarregam → efeito termina → cooldown parte.
    ship.orbital_discharge_active = False
    upg.update(0.016, ctx)
    assert not upg.active
    assert upg.cooldown_left == upg.get_effective_cooldown(ctx)


# ── disponibilidade (o que a HUD e o cursor do gamepad consultam) ────────────


def test_em_execucao_nao_esta_disponivel_mesmo_com_cooldown_zero():
    """`is_ready` cobre a janela que `cooldown_left` sozinho não vê.

    Entre ativar e o efeito acabar, o cooldown ainda é ZERO (é o contrato
    testado acima). Quem lia só o cooldown enxergava o upgrade recém-usado como
    pronto — foi assim que a seleção rápida do gamepad parou de pular para o
    próximo disponível.
    """
    upg = ActiveUpgrade(_meta(cooldown=5.0, duration=2.0))
    ctx = _Ctx()
    assert upg.is_ready
    upg.activate(ctx)

    assert upg.cooldown_left == 0.0
    assert not upg.is_ready, "em execução não pode contar como disponível"

    upg.update(2.0, ctx)  # fim da duração → cooldown parte
    assert not upg.is_ready
    upg.update(5.0, ctx)  # fim da recarga
    assert upg.is_ready


def test_can_activate_e_is_ready_nao_divergem():
    """`can_activate` é `is_ready` + a parte que depende do mundo.

    Duas listas de condições em paralelo era o que deixava a HUD e a ativação
    discordando; aqui a de cima passa a ser a de baixo mais o contexto.
    """
    upg = ActiveUpgrade(_meta(cooldown=5.0, duration=2.0))
    ctx = _Ctx()
    for _ in range(3):
        assert upg.can_activate(ctx) == upg.is_ready
        upg.activate(ctx)
        assert upg.can_activate(ctx) == upg.is_ready
        upg.update(2.0, ctx)
        assert upg.can_activate(ctx) == upg.is_ready
        upg.update(5.0, ctx)
