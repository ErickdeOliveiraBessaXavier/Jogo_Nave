"""Robustez de alvo dos companheiros (MiniShip / Wingman).

Trava o bug do "alvo-fantasma": quando um inimigo é removido do jogo (limpeza de
transição/atmosfera, fim de luta de boss, despawn), o companheiro precisa largar a
referência IMEDIATAMENTE e voltar ao repouso/formação — sem girar nem atirar num
inimigo que já não existe.

O gate é `is_targetable` (checa `dead`). O fix sistêmico marca os inimigos como
mortos antes de esvaziar as listas; aqui garantimos que o comportamento do
companheiro responde a isso: alvo morto → sem alvo → sem tiro.
"""

from game.entities.player.mini_ship import MiniShip
from game.entities.player.wingman import Wingman
from game.systems.entity_manager import EntityManager
from game.systems.targeting import is_targetable


class _FakeShip:
    def __init__(self):
        self.x = 100.0
        self.y = 100.0
        self.w = 32
        self.h = 32
        self.player_index = 0
        self.piercing_shot_timer = 0.0
        self.mini_ships_timer = 5.0


class _FakeEnemy:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.w = 20
        self.h = 20
        self.dead = False


class _FakeEM:
    def __init__(self, enemies):
        self.enemies = enemies
        self.formations = []
        self.boss = None


class TestEntityManagerInvalidation:
    """O fix sistêmico: as limpezas marcam os inimigos como mortos antes de
    esvaziar as listas — é isso que faz a referência retida virar não-atacável."""

    def test_invalidate_marca_inimigos_mortos(self):
        em = EntityManager()
        e = _FakeEnemy(0, 0)
        em.enemies.append(e)
        em.invalidate_enemy_targets()
        assert e.dead is True

    def test_clear_for_level_transition_invalida_alvo_retido(self):
        em = EntityManager()
        e = _FakeEnemy(0, 0)
        em.enemies.append(e)
        # Um companheiro guardava esta referência (mira antiga).
        held = e
        em.clear_for_level_transition()
        assert held.dead is True, "referência retida precisa virar não-atacável"
        assert is_targetable(held) is False
        assert em.enemies == []


class TestRemoveCompanionsOfShip:
    """P2 desconectando: mini-naves, wingmen e feixe de coop vinculados à nave
    dele somem — sem referência de dono fantasma."""

    class _Comp:
        def __init__(self, player):
            self.player = player

    class _Link:
        def __init__(self, a, b):
            self.ship1 = a
            self.ship2 = b

    def test_remove_companions_of_ship(self):
        em = EntityManager()
        p1, p2 = object(), object()
        em.mini_ships = [self._Comp(p1), self._Comp(p2), self._Comp(p2)]
        em.wingmen = [self._Comp(p1), self._Comp(p2)]
        em.coop_links = [self._Link(p1, p2)]

        em.remove_companions_of_ship(p2)

        assert [m.player for m in em.mini_ships] == [p1]
        assert [w.player for w in em.wingmen] == [p1]
        assert em.coop_links == [], "feixe de coop tocando P2 deve sumir"


class TestIsTargetable:
    def test_morto_nao_e_atacavel(self):
        e = _FakeEnemy(0, 0)
        assert is_targetable(e) is True
        e.dead = True
        assert is_targetable(e) is False


class TestWingman:
    def _ready_wingman(self):
        w = Wingman(_FakeShip(), duration=30.0)
        w.spawn_timer = w.spawn_duration  # pula a animação de nascimento
        w.scale = 1.0
        return w

    def test_larga_alvo_morto_e_para_de_atirar(self):
        w = self._ready_wingman()
        e = _FakeEnemy(120, 120)
        bullets = []
        w.update(0.016, [e], bullets)
        assert w.target is e and w.state == "HUNT"

        # Inimigo removido do jogo → marcado morto (o que a limpeza faz agora).
        e.dead = True
        bullets.clear()
        for _ in range(5):
            w.update(0.5, [e], bullets)  # dt grande p/ estourar o cooldown
        assert w.target is None
        assert w.state == "FOLLOW"
        assert bullets == [], "Wingman não pode atirar em alvo-fantasma"

    def test_lista_vazia_volta_a_follow(self):
        w = self._ready_wingman()
        e = _FakeEnemy(120, 120)
        w.update(0.016, [e], [])
        assert w.state == "HUNT"
        e.dead = True
        w.update(0.016, [], [])  # nenhum inimigo restante
        assert w.target is None and w.state == "FOLLOW"


class TestMiniShip:
    def test_larga_alvo_morto_e_para_de_atirar(self):
        m = MiniShip(_FakeShip(), side="left")
        e = _FakeEnemy(m.x + 30, m.y + 30)  # dentro do alcance (400px)
        em = _FakeEM([e])
        bullets = []
        m.update(0.016, em, bullets)
        assert m.target is e

        e.dead = True
        bullets.clear()
        for _ in range(3):
            m.update(1.0, em, bullets)
        assert m.target is None
        assert bullets == [], "MiniShip não pode atirar em alvo-fantasma"

    def test_sem_inimigos_fica_idle(self):
        m = MiniShip(_FakeShip(), side="right")
        em = _FakeEM([])
        bullets = []
        m.update(0.016, em, bullets)
        assert m.target is None
        # Ângulo de mira volta ao repouso (sem alvo).
        assert m.target_angle == m._idle_angle
        assert bullets == []
