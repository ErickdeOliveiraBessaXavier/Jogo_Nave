"""Registro de marcas de disparo (`systems/shot_marks`) e as sinergias que ele dá.

Um modificador de tiro que MARCA o alvo é propriedade da NAVE, não da bala —
então vale para tudo que aquela nave fere. Antes, cada caminho de acerto tinha o
seu par "booleano + chamada" por upgrade, e um caminho novo que esquecesse de
repetir um deles teria uma sinergia que simplesmente não acontece, sem erro
nenhum para denunciar.

O que estes testes guardam:

1. **o registro é a fonte única** — quem entra nele passa a valer em todos os
   caminhos de acerto sem que nenhum deles mude. É o teste que quebra se alguém
   voltar a escrever um `if has_<upgrade>` solto num passe de colisão;
2. **o Chain Lightning propaga as marcas** para cada inimigo do encadeamento e
   muda de cor para dizer o que está carregando;
3. **as marcas se acumulam** — gelo E ácido no mesmo alvo, sem uma apagar a outra;
4. **fragmento da bomba de gelo não propaga nada** — é dano de estouro, não tiro
   do jogador, e realimentaria a própria bomba.
"""

import pygame
import pytest

from game.core.config import config as Config
from game.core.ship_types import get_ship_profile
from game.core.spatial_grid import SpatialGrid
from game.core.upgrades_config import CORROSIVE_COLOR
from game.entities.effects.chain_lightning import ChainLightning
from game.entities.player.ship import Ship
from game.systems import shot_marks
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager


class Bus:
    def emit(self, event):
        pass


class Inimigo:
    def __init__(self, x: float, y: float, health: int = 999):
        self.x, self.y = float(x), float(y)
        self.w = self.h = 26
        self.dead = False
        self.health = health

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self):
        return (self.x + 13, self.y + 13, 13)

    def on_hit(self, damage, hx, hy):
        from game.systems.hit_result import HitResult

        self.health -= damage
        if self.health <= 0:
            self.dead = True
        return HitResult(killed=self.dead, points=0, explosion_size=0)

    def get_points_value(self):
        return 0


def _nave(*, cryo=False, corrosive=False, chain=False) -> Ship:
    ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
    if cryo:
        ship.activate_cryo_shots(20.0)
    if corrosive:
        ship.activate_corrosive_ammo(20.0)
    if chain:
        ship.activate_chain_shot(20.0)
    return ship


# ---------------------------------------------------------------------------
# O registro
# ---------------------------------------------------------------------------


class TestRegistro:
    def test_toda_marca_aponta_para_uma_property_real_da_nave(self):
        """`flag` errada seria uma marca que nunca ativa — `getattr` devolve
        False para nome inexistente e nada acusaria."""
        ship = _nave()
        for mark in shot_marks.SHOT_MARKS:
            assert hasattr(ship, mark.flag), mark.flag
            assert getattr(ship, mark.flag) is False

    def test_cada_marca_tem_cor_propria(self):
        """A cor é o que o efeito propagador usa para dizer o que carrega; duas
        marcas com a mesma cor apagariam a informação."""
        cores = [m.color for m in shot_marks.SHOT_MARKS]
        assert len(set(cores)) == len(cores)

    def test_sem_dono_nao_ha_marca(self):
        assert shot_marks.active_marks(None) == ()

    def test_dono_sem_upgrade_nao_tem_marca(self):
        assert shot_marks.active_marks(_nave()) == ()

    def test_so_as_marcas_ativas_entram(self):
        marcas = shot_marks.active_marks(_nave(corrosive=True))
        assert [m.flag for m in marcas] == ["has_corrosive_ammo"]

    def test_as_marcas_ACUMULAM_e_nao_se_excluem(self):
        alvo = Inimigo(100.0, 100.0)
        shot_marks.apply_all(alvo, _nave(cryo=True, corrosive=True))
        assert alvo.cryo_stacks == 1
        assert alvo.corrosive_stacks == 1

    def test_a_cor_de_propagacao_e_a_da_primeira_marca_ativa(self):
        padrao = (1, 2, 3)
        assert shot_marks.propagation_color((), padrao) == padrao

        marcas = shot_marks.active_marks(_nave(corrosive=True))
        assert shot_marks.propagation_color(marcas, padrao) == CORROSIVE_COLOR

    def test_a_cor_nao_e_misturada_quando_ha_duas(self):
        """Dois tons somados dariam um terceiro que não é de ninguém."""
        marcas = shot_marks.active_marks(_nave(cryo=True, corrosive=True))
        cor = shot_marks.propagation_color(marcas, (0, 0, 0))
        assert cor in {m.color for m in marcas}


# ---------------------------------------------------------------------------
# A sinergia pedida: Corrosive + Chain Lightning
# ---------------------------------------------------------------------------


class TestChainPropagaMarcas:
    @staticmethod
    def cenario(ship: Ship, n_alvos: int = 3):
        """Uma bala acerta o primeiro alvo; os demais ficam ao alcance da cadeia."""
        em = EntityManager()
        passo = min(60, int(Config.CHAIN_SHOT_RADIUS) - 10)
        alvos = [Inimigo(400.0 + i * passo, 300.0) for i in range(n_alvos)]
        em.enemies = list(alvos)

        bala = em.spawn_bullet(405.0, 305.0, damage=40, owner_ship=ship)
        grid: SpatialGrid = SpatialGrid(cell_size=200)
        for e in alvos:
            r = e.rect
            grid.insert(e, r.x, r.y, r.width, r.height)
        Collisions(event_bus=Bus()).projectiles_vs_enemies([bala], grid, em)
        return em, alvos

    def test_o_raio_corroi_cada_inimigo_do_encadeamento(self):
        """O pedido: todo inimigo atingido pelo salto recebe o debuff."""
        em, alvos = self.cenario(_nave(corrosive=True, chain=True))
        assert em.chain_lightnings, "a cadeia não saltou; cenário inválido"

        for i, alvo in enumerate(alvos):
            assert getattr(alvo, "corrosive_stacks", 0) == 1, f"alvo {i} sem ácido"

    def test_sem_o_corrosive_a_cadeia_nao_corroi(self):
        _em, alvos = self.cenario(_nave(chain=True))
        assert all(getattr(a, "corrosive_stacks", 0) == 0 for a in alvos)

    def test_sem_a_cadeia_so_o_alvo_da_bala_corroi(self):
        _em, alvos = self.cenario(_nave(corrosive=True))
        assert alvos[0].corrosive_stacks == 1
        assert all(getattr(a, "corrosive_stacks", 0) == 0 for a in alvos[1:])

    def test_o_raio_fica_VERDE_quando_carrega_acido(self):
        em, _alvos = self.cenario(_nave(corrosive=True, chain=True))
        assert all(bolt.color == CORROSIVE_COLOR for bolt in em.chain_lightnings)

    def test_o_raio_comum_continua_ciano(self):
        em, _alvos = self.cenario(_nave(chain=True))
        assert all(bolt.color == ChainLightning.DEFAULT_COLOR for bolt in em.chain_lightnings)

    def test_a_sinergia_vale_para_QUALQUER_marca_do_registro(self):
        """O ponto da arquitetura: a cadeia não conhece upgrade nenhum pelo nome.

        Se alguém trocar o laço genérico por um `if has_corrosive_ammo`, o gelo
        para de propagar e só este teste avisa.
        """
        em, alvos = self.cenario(_nave(cryo=True, chain=True))
        assert em.chain_lightnings, "a cadeia não saltou; cenário inválido"
        for i, alvo in enumerate(alvos):
            assert getattr(alvo, "cryo_stacks", 0) == 1, f"alvo {i} sem gelo"

    def test_upgrade_novo_herda_a_sinergia_sem_tocar_na_cadeia(self):
        """Prova executável da promessa: uma marca registrada em runtime já
        propaga pelo raio, sem nenhuma linha nova em `_trigger_chain_shot`."""
        marcados: list[int] = []

        def marcar(enemy, owner=None):
            marcados.append(id(enemy))

        nova = shot_marks.ShotMark("has_upgrade_ficticio", marcar, (255, 0, 255))
        original = shot_marks.SHOT_MARKS
        shot_marks.SHOT_MARKS = original + (nova,)
        try:
            ship = _nave(chain=True)
            ship.has_upgrade_ficticio = True  # type: ignore[attr-defined]
            _em, alvos = self.cenario(ship)
        finally:
            shot_marks.SHOT_MARKS = original

        assert len(marcados) == len(alvos), (
            f"{len(marcados)} de {len(alvos)} alvos marcados: a propagação "
            "está presa a upgrades específicos"
        )


# ---------------------------------------------------------------------------
# Quem NÃO propaga
# ---------------------------------------------------------------------------


class TestOptOuts:
    def test_fragmento_da_bomba_de_gelo_nao_propaga_marcas(self):
        """Ele é dano de estouro, não tiro do jogador: propagar realimentaria a
        própria bomba enquanto o alvo estivesse no alcance."""
        em = EntityManager()
        alvo = Inimigo(400.0, 300.0)
        em.enemies = [alvo]

        ship = _nave(cryo=True, corrosive=True)
        caco = em.spawn_bullet(
            405.0, 305.0, damage=5, owner_ship=ship, ice_shard=True
        )
        grid: SpatialGrid = SpatialGrid(cell_size=200)
        r = alvo.rect
        grid.insert(alvo, r.x, r.y, r.width, r.height)
        Collisions(event_bus=Bus()).projectiles_vs_enemies([caco], grid, em)

        assert getattr(alvo, "cryo_stacks", 0) == 0
        assert getattr(alvo, "corrosive_stacks", 0) == 0

    def test_alvo_que_nao_aceita_marca_nao_derruba_a_propagacao(self):
        class PecaComSlots:
            __slots__ = ("dead",)

            def __init__(self):
                self.dead = False

        shot_marks.apply_all(PecaComSlots(), _nave(cryo=True, corrosive=True))


# ---------------------------------------------------------------------------
# A fachada antiga continua valendo
# ---------------------------------------------------------------------------


class TestFachada:
    def test_collisions_ainda_expoe_os_aplicadores(self):
        """Vários call sites e testes chamam por `Collisions._apply_*`; a regra
        mudou de casa, o nome não."""
        col = Collisions(event_bus=Bus())
        alvo = Inimigo(100.0, 100.0)
        col._apply_cryo(alvo)
        col._apply_corrosion(alvo)
        assert alvo.cryo_stacks == 1
        assert alvo.corrosive_stacks == 1

    def test_o_dono_fica_gravado_no_alvo(self):
        """Crédito de kill e cor do jogador no estouro dependem disso."""
        ship = _nave(cryo=True, corrosive=True)
        alvo = Inimigo(100.0, 100.0)
        shot_marks.apply_all(alvo, ship)
        assert alvo.cryo_owner is ship
        assert alvo.corrosive_owner is ship


def test_marcas_registradas_batem_com_a_lista_conhecida():
    """Guarda contra marca adicionada sem cor/flag pensadas. Atualizar de
    propósito ao registrar uma nova."""
    assert [m.flag for m in shot_marks.SHOT_MARKS] == [
        "has_cryo_shot",
        "has_corrosive_ammo",
    ]


def test_apply_marks_com_tupla_vazia_nao_faz_nada():
    alvo = Inimigo(100.0, 100.0)
    shot_marks.apply_marks((), alvo, None)
    assert getattr(alvo, "cryo_stacks", 0) == 0
    assert pytest.approx(getattr(alvo, "corrosive_timer", 0.0)) == 0.0
