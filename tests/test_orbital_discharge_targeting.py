"""Alvo da Descarga Orbital: nunca seguir um inimigo já destruído.

Bug travado aqui: o `RockGlider` tem uma janela de **outro** de 0,35s em que as
duas partes já explodiram (`_fully_destroyed`, hitboxes vazios, `rect` colapsado
em 0x0, invisível) mas `dead` ainda é False. Como `is_targetable` só olhava
`dead`, o glider seguia sendo alvo válido: a descarga travava no cadáver e mirava o
canto do rect colapsado.

O contrato é `can_take_damage()` (memory `targeting-via-target-point`) — um só
ponto que conserta TODA a seleção de alvo (descarga orbital, mini-naves, Wingman,
teleguiados), não só o consumidor que exibiu o sintoma.
"""

from game.entities.enemies.mountain.rock_glider import RockGlider
from game.entities.projectiles.orbital_discharge import OrbitalDischarge
from game.systems.targeting import is_targetable


def _glider_destruido() -> RockGlider:
    """Glider na janela de outro: partes destruídas, `dead` ainda False."""
    g = RockGlider(size=18, x=400.0, y=300.0)
    # Dano suficiente para derrubar as duas partes, em ordem (rocha e bot).
    g.take_part_damage(*g._rock_center, amount=RockGlider.ROCK_MAX_HP)
    g.take_part_damage(*g._bot_center, amount=RockGlider.BOT_MAX_HP)
    return g


class TestRockGliderJanelaDeOutro:
    def test_destruido_mas_ainda_nao_removido(self):
        g = _glider_destruido()
        assert g._fully_destroyed is True
        assert g.dead is False, "o outro de 0,35s ainda não terminou"

    def test_nao_e_alvejavel_na_janela_de_outro(self):
        g = _glider_destruido()
        assert g.can_take_damage() is False
        assert is_targetable(g) is False

    def test_e_alvejavel_enquanto_tem_parte_viva(self):
        g = RockGlider(size=18, x=400.0, y=300.0)
        assert is_targetable(g) is True
        # Só a rocha cai: o bot continua vivo e o glider segue alvo legítimo.
        g.take_part_damage(*g._rock_center, amount=RockGlider.ROCK_MAX_HP)
        assert g._rock_destroyed is True
        assert is_targetable(g) is True


class TestOrbitalDischargeLargaAlvoInvalido:
    def test_solta_o_glider_destruido_e_congela_a_mira(self):
        g = _glider_destruido()
        descarga = OrbitalDischarge(0.0, 0.0, 400.0, 300.0, target_entity=g)
        alvo_antes = (descarga.target_x, descarga.target_y)

        descarga.update(0.016)

        assert descarga.target_entity is None, "não pode seguir rastreando o cadáver"
        assert (descarga.target_x, descarga.target_y) == alvo_antes, (
            "sem alvo novo, o feixe mantém o último ponto (comportamento padrão)"
        )

    def test_retarget_migra_para_alvo_valido(self):
        morto = _glider_destruido()
        vivo = RockGlider(size=18, x=600.0, y=320.0)
        descarga = OrbitalDischarge(0.0, 0.0, 400.0, 300.0, target_entity=morto)

        descarga.retarget(vivo)

        assert descarga.target_entity is vivo
        cx, cy, _r = vivo.collision_circle()
        assert (descarga.target_x, descarga.target_y) == (float(cx), float(cy))

    def test_retarget_para_alvo_invalido_equivale_a_sem_alvo(self):
        morto = _glider_destruido()
        descarga = OrbitalDischarge(0.0, 0.0, 400.0, 300.0, target_entity=None)
        alvo_antes = (descarga.target_x, descarga.target_y)

        descarga.retarget(morto)

        assert descarga.target_entity is None
        assert (descarga.target_x, descarga.target_y) == alvo_antes


class TestEntityManagerReMira:
    def test_alvo_destruido_migra_para_o_vizinho_vivo(self):
        from game.systems.entity_manager import EntityManager

        em = EntityManager()
        morto = _glider_destruido()
        vivo = RockGlider(size=18, x=430.0, y=310.0)
        em.enemies.extend([morto, vivo])

        descarga = em.spawn_orbital_discharge(
            400.0, 300.0, 400.0, 300.0, target_entity=morto
        )
        em.update(0.016, player_x=400.0, player_y=500.0)

        assert descarga.target_entity is vivo
