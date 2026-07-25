"""Chain shot: a cadeia de ricochete é uma estrutura pai→filho coerente.

Trava o contrato pedido: cada salto parte do ÚLTIMO inimigo atingido (o `end` de
um raio é o `start` do próximo), busca o vivo mais próximo dentro do raio ainda
não atingido, e nenhum inimigo é atingido duas vezes pela mesma cadeia. Sem isso,
os raios "nasciam" de pontos arbitrários (várias cadeias independentes).
"""

from game.systems.collisions import Collisions


class _FakeEnemy:
    def __init__(self, x, y):
        self._c = (float(x), float(y), 10.0)
        self.dead = False

    def collision_circle(self):
        return self._c

    def on_hit(self, damage, hit_x, hit_y):
        from game.systems.hit_result import HitResult

        return HitResult()  # não morre, sem pontos/explosão/som


class _FakeGrid:
    def __init__(self, enemies):
        self._enemies = enemies

    def query(self, x, y, w, h):
        return [
            e
            for e in self._enemies
            if x <= e._c[0] <= x + w and y <= e._c[1] <= y + h
        ]


class _FakeEM:
    def __init__(self):
        self.chain_lightnings = []

    def spawn_explosion(self, *a, **k):
        pass

    def spawn_explosive_effect(self, *a, **k):
        pass


def _run(source, enemies, *, jumps=4, already=None):
    c = Collisions()
    em = _FakeEM()
    already = set() if already is None else already
    sx, sy, _ = source.collision_circle()
    c._trigger_chain_shot(
        hit_x=sx,
        hit_y=sy,
        source_enemy=source,
        bullet_damage=100,
        jumps_left=jumps,
        already_hit=already,
        enemy_grid=_FakeGrid([source, *enemies]),
        entity_manager=em,
        owner_ship=None,
        explosive=False,
    )
    return em.chain_lightnings, already


class TestParentChildChain:
    def test_cada_salto_parte_do_ultimo_atingido(self):
        # A(100) -> B(160) -> C(220); D(900,600) fica fora do raio de C.
        a = _FakeEnemy(100, 100)
        b = _FakeEnemy(160, 100)
        cc = _FakeEnemy(220, 100)
        d = _FakeEnemy(900, 600)
        lns, already = _run(a, [b, cc, d])

        assert len(lns) == 2
        # 1º raio: do inimigo atingido (A) ao mais próximo (B).
        assert lns[0].start_pos == (100.0, 100.0)
        assert lns[0].end_pos == (160.0, 100.0)
        # 2º raio NASCE onde o 1º terminou (B) — continuidade pai→filho.
        assert lns[1].start_pos == lns[0].end_pos
        assert lns[1].end_pos == (220.0, 100.0)

    def test_nenhum_inimigo_atingido_duas_vezes(self):
        a = _FakeEnemy(100, 100)
        b = _FakeEnemy(160, 100)
        cc = _FakeEnemy(220, 100)
        _lns, already = _run(a, [b, cc])
        # A (source) + B + C, cada um uma vez.
        assert already == {id(a), id(b), id(cc)}

    def test_pula_o_ja_atingido(self):
        # Se B já está na cadeia (ex.: perfurado pela bala), o salto de A vai para
        # o próximo válido (C), sem repetir B.
        a = _FakeEnemy(100, 100)
        b = _FakeEnemy(160, 100)
        cc = _FakeEnemy(220, 100)
        lns, _already = _run(a, [b, cc], already={id(b)})
        # A -> C direto (B excluído).
        assert lns[0].start_pos == (100.0, 100.0)
        assert lns[0].end_pos == (220.0, 100.0)

    def test_sem_alvo_no_raio_nao_cria_raio(self):
        # Só um inimigo distante: nada dentro do raio -> nenhuma cadeia.
        a = _FakeEnemy(100, 100)
        far = _FakeEnemy(900, 600)
        lns, _already = _run(a, [far])
        assert lns == []
