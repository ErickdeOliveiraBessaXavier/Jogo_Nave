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


class TestWingmanSemSobreposicao:
    """As três escoltas do upgrade não podem voar empilhadas.

    Antes elas compartilhavam o destino: em FOLLOW um ponto fixo atrás do
    jogador (o lado era sorteado entre DOIS valores, então duas caíam no mesmo
    lugar em metade das partidas) e em HUNT a mesma órbita, no mesmo raio, em
    volta do mesmo alvo — o mais próximo é o mesmo para todas.

    O que estes testes travam é a SEPARAÇÃO, não as posições exatas: vagas
    distintas, formação que fecha quando uma expira, e a repulsão que cobre o
    que a formação não prevê.
    """

    @staticmethod
    def _esquadrao(n: int, player=None):
        player = player or _FakeShip()
        escoltas = []
        for _ in range(n):
            w = Wingman(player, duration=30.0)
            w.spawn_timer = w.spawn_duration  # pula a animação de nascimento
            w.scale = 1.0
            escoltas.append(w)
        return player, escoltas

    @staticmethod
    def _voar(escoltas, enemies=(), passos=180, dt=1 / 60):
        for _ in range(passos):
            for w in escoltas:
                w.update(dt, list(enemies), [], escoltas)

    @staticmethod
    def _menor_distancia(escoltas) -> float:
        import math

        return min(
            math.hypot(
                (a.x + a.w / 2) - (b.x + b.w / 2),
                (a.y + a.h / 2) - (b.y + b.h / 2),
            )
            for i, a in enumerate(escoltas)
            for b in escoltas[i + 1 :]
        )

    def test_cada_escolta_recebe_uma_vaga_diferente(self):
        _, escoltas = self._esquadrao(3)
        self._voar(escoltas, passos=1)
        assert sorted(w.slot for w in escoltas) == [0, 1, 2]

    def test_as_vagas_tem_destinos_distintos(self):
        """A raiz do empilhamento: destino igual = equilíbrio no mesmo ponto."""
        _, escoltas = self._esquadrao(3)
        self._voar(escoltas, passos=1)
        destinos = {(w.follow_offset_x, w.follow_offset_y) for w in escoltas}
        assert len(destinos) == 3

    def test_em_repouso_elas_se_espalham(self):
        _, escoltas = self._esquadrao(3)
        self._voar(escoltas)
        assert self._menor_distancia(escoltas) > escoltas[0].w, (
            "escoltas paradas uma em cima da outra"
        )

    def test_perseguindo_o_MESMO_alvo_elas_nao_empilham(self):
        """O caso que a formação sozinha não resolve: em HUNT todas escolhem o
        inimigo mais próximo, que é o mesmo para as três."""
        _, escoltas = self._esquadrao(3)
        alvo = _FakeEnemy(400, 300)
        self._voar(escoltas, enemies=[alvo], passos=240)

        assert all(w.state == "HUNT" for w in escoltas), "premissa: todas caçando"
        assert self._menor_distancia(escoltas) > escoltas[0].w

    def test_a_formacao_FECHA_quando_uma_expira(self):
        """Vaga é recalculada por frame: sem isso a que sobra fica no lugar dela
        e o buraco da que morreu permanece na formação."""
        _, escoltas = self._esquadrao(3)
        self._voar(escoltas, passos=1)
        antes = escoltas[-1].follow_offset_x

        escoltas.pop(0)
        self._voar(escoltas, passos=1)
        assert escoltas[-1].follow_offset_x != antes
        assert sorted(w.slot for w in escoltas) == [0, 1]

    def test_nascer_EXATAMENTE_em_cima_de_outra_se_resolve(self):
        """Empate perfeito: `dx = dy = 0` não tem direção de fuga, e sem o
        desempate por vaga as duas ficariam grudadas para sempre."""
        _, escoltas = self._esquadrao(2)
        a, b = escoltas
        b.x, b.y = a.x, a.y

        self._voar(escoltas, passos=90)
        assert self._menor_distancia(escoltas) > a.w

    def test_a_repulsao_ignora_o_dono_mas_a_formacao_nao(self):
        """Sobreposição é visual: escolta do P1 e do P2 também não se empilham.
        Já a VAGA é relativa à nave dona, então cada esquadrão forma no seu.
        """
        _, p1 = self._esquadrao(2)
        _, p2 = self._esquadrao(2)
        todas = p1 + p2

        for w in todas:
            w.update(1 / 60, [], [], todas)

        assert sorted(w.slot for w in p1) == [0, 1]
        assert sorted(w.slot for w in p2) == [0, 1], (
            "vaga contou escoltas de outro jogador"
        )

    def test_escolta_sozinha_fica_centrada(self):
        _, escoltas = self._esquadrao(1)
        self._voar(escoltas, passos=1)
        assert escoltas[0].follow_offset_x == 0.0

    def test_update_sem_esquadrao_nao_quebra(self):
        """Chamada antiga (3 argumentos) continua válida — o parâmetro é
        opcional, e os testes de mira acima passam por este caminho."""
        w = Wingman(_FakeShip(), duration=30.0)
        w.update(1 / 60, [], [])


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
