"""MountainPropeller vive em `em.enemies` como todos os outros inimigos.

Ele tinha lista própria (`em.mountain_propellers`) e um loop de update paralelo
que passava o **`dt` cru** — sem `enemy_dt` e sem a cadeia de multiplicadores.
O resultado era um inimigo que levava tiro normalmente mas era imune a parada do
tempo, a zonas de veneno/fogo e a toda lentidão. Três sistemas carregavam
remendos para compensar a separação (contagem de hostis na progressão de fase,
force-kill no fim de boss, cap do spawner).

O teste mede o **dt que a entidade de fato recebe**, e não o estado interno: o
`timer` do propeller zera a cada troca de estado, então delta de timer daria
número enganoso (mediu 68% quando o valor real era 25%).
"""

import pytest

from game.core.spatial_grid import SpatialGrid
from game.core.upgrades_config import IMPLOSION_SLOW_FACTOR
from game.entities.enemies.mountain.mountain_propeller import MountainPropeller
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager


class Bus:
    def emit(self, event):
        pass


def espiao(**kw) -> MountainPropeller:
    """Propeller que soma todo `dt` recebido em `update()`."""
    prop = MountainPropeller(**kw)
    prop._dt_recebido = 0.0
    original = prop.update

    def update(dt, *a, **k):
        prop._dt_recebido += dt
        return original(dt, *a, **k)

    prop.update = update
    return prop


def dt_em_1s(cenario: str, frames: int = 60) -> float:
    """Roda o mundo real por 1s e devolve o dt total que o propeller recebeu."""
    prop = espiao(y=300.0)
    em = EntityManager()
    em.enemies = [prop]
    col = Collisions(event_bus=Bus())

    if cenario == "implosao":
        cx, cy, _ = prop.collision_circle()
        em.spawn_implosion_pulse(cx, cy)

    for _ in range(frames):
        if cenario == "implosao":
            grid: SpatialGrid = SpatialGrid(cell_size=200)
            if not prop.dead:
                grid.insert_from_rect(prop)
            col.implosion_pulses_vs_enemies(em.implosion_pool.active, grid, em)
        em.update(
            1 / 60,
            640.0,
            600.0,
            enemy_time_scale=0.0 if cenario == "timestop" else 1.0,
            screen_width=1280,
            screen_height=720,
        )
    return prop._dt_recebido


class TestVivEmEnemies:
    def test_spawn_vai_para_a_lista_comum(self):
        em = EntityManager()
        prop = em.spawn_mountain_propeller(y=300.0)
        assert prop in em.enemies

    def test_nao_existe_mais_lista_propria(self):
        """A lista separada era a causa de tudo; se voltar, os efeitos somem de
        novo e os três remendos precisam voltar junto."""
        assert not hasattr(EntityManager(), "mountain_propellers")

    def test_sobrevive_ao_proprio_spawn(self):
        """Nasce em `x = SCREEN_WIDTH + BODY_W`, fora da tela à direita. Sem
        `offscreen_cull_exempt` o backstop de limpeza o mata no primeiro frame —
        que é o preço de entrar na lista comum."""
        em = EntityManager()
        prop = em.spawn_mountain_propeller(y=300.0)
        assert prop.x > 1280, "premissa mudou: já não nasce fora da tela"
        for _ in range(10):
            em.update(1 / 60, 640.0, 600.0, screen_width=1280, screen_height=720)
        assert not prop.dead

    def test_declara_os_dois_opt_ins_de_classe(self):
        assert MountainPropeller.offscreen_cull_exempt is True
        assert MountainPropeller.draws_offscreen is True


class TestEfeitosAgoraPegam:
    def test_ritmo_normal_e_o_dt_cheio(self):
        assert dt_em_1s("normal") == pytest.approx(1.0, abs=0.02)

    def test_parada_do_tempo_congela(self):
        """`enemy_dt = dt * enemy_time_scale`. O loop paralelo passava `dt`
        cru, então a hélice seguia girando com o tempo parado."""
        assert dt_em_1s("timestop") == pytest.approx(0.0, abs=1e-6)

    def test_lentidao_em_area_freia(self):
        """A zona da Implosão já marcava `implosion_slow_timer` nele (ele está
        no grid espacial) — o que faltava era alguém consumir a marca."""
        assert dt_em_1s("implosao") == pytest.approx(IMPLOSION_SLOW_FACTOR, abs=0.05)

    def test_zonas_de_area_passam_a_visita_lo(self):
        """`ice_poison_zones_vs_entities` itera `em.enemies`. Fora dela, o
        propeller não era sequer visitado — nem veneno, nem marca de gelo."""
        em = EntityManager()
        prop = em.spawn_mountain_propeller(y=300.0)
        assert prop in em.enemies


class TestRemendosRemovidos:
    """Os três sistemas que compensavam a lista separada não devem mais
    mencioná-la. Um resquício significa contagem dupla ou código morto."""

    def test_progressao_nao_conta_por_fora(self):
        import inspect

        from game.systems import level_progression_controller as mod

        assert "em.mountain_propellers" not in inspect.getsource(mod)

    def test_boss_nao_force_killa_por_fora(self):
        import inspect

        from game.systems import boss_fight_controller as mod

        assert "em.mountain_propellers" not in inspect.getsource(mod)

    def test_spawner_conta_pelo_caminho_comum(self):
        import inspect

        from game.systems import spawner as mod

        assert "entity_manager.mountain_propellers" not in inspect.getsource(mod)

    def test_o_vento_ainda_encontra_as_helices(self):
        """A cena filtra por duck typing (§5) em vez da lista removida."""
        import inspect

        from game.scenes import playing as mod

        src = inspect.getsource(mod)
        assert "mountain_propellers" not in src
        assert "is_blowing" in src

    def test_helice_soprando_e_descoberta_por_duck_typing(self):
        em = EntityManager()
        prop = em.spawn_mountain_propeller(y=300.0)
        soprando = [
            e
            for e in em.enemies
            if not e.dead and getattr(e, "is_blowing", None) and e.is_blowing()
        ]
        assert soprando == []  # ainda entrando, não sopra

        from game.entities.enemies.mountain.mountain_propeller import (
            _PropellerState,
        )

        prop.state = _PropellerState.BLOWING
        soprando = [
            e
            for e in em.enemies
            if not e.dead and getattr(e, "is_blowing", None) and e.is_blowing()
        ]
        assert soprando == [prop]
