"""Remoção de mortos por swap-and-pop (§6) — `EntityManager._filter_dead_inplace`."""

from game.systems.entity_manager import EntityManager


class _Ent:
    def __init__(self, dead=False, tag=None):
        self.dead = dead
        self.tag = tag


def _filter(lst, fn=None):
    # Método estático; chamável sem instanciar o EntityManager (que puxaria o
    # jogo inteiro).
    EntityManager._filter_dead_inplace(lst, fn)


def test_remove_mortos_mantem_vivos():
    lst = [_Ent(dead=i % 2 == 0) for i in range(6)]
    vivos = {id(e) for e in lst if not e.dead}
    _filter(lst)
    assert {id(e) for e in lst} == vivos


def test_lista_toda_viva_intacta():
    lst = [_Ent(dead=False) for _ in range(4)]
    antes = list(lst)
    _filter(lst)
    assert set(map(id, lst)) == set(map(id, antes))


def test_lista_toda_morta_esvazia():
    lst = [_Ent(dead=True) for _ in range(4)]
    _filter(lst)
    assert lst == []


def test_lista_vazia_nao_quebra():
    lst = []
    _filter(lst)
    assert lst == []


def test_predicado_customizado():
    lst = [_Ent(tag=t) for t in ("keep", "drop", "keep", "drop")]
    _filter(lst, lambda e: e.tag == "drop")
    assert [e.tag for e in lst] == ["keep", "keep"]


def test_preserva_exatamente_o_conjunto_vivo_em_lote():
    # Swap-and-pop não preserva ordem; o contrato é preservar o CONJUNTO.
    a, b, c, d = _Ent(), _Ent(dead=True), _Ent(), _Ent(dead=True)
    lst = [a, b, c, d]
    _filter(lst)
    assert set(map(id, lst)) == {id(a), id(c)}
