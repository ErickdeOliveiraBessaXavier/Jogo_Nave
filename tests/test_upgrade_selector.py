"""UpgradeSelector — cursor de seleção de upgrade por gamepad.

Como o RevivalSystem, roda com stubs mínimos (sem cena, sem jogo): a prova do
§1. Cobre a priorização de slots prontos, a navegação circular e o gate de
confirmação.
"""

import pytest

from game.systems.upgrade_selector import UpgradeSelector


class _Upg:
    """Stub com o contrato de disponibilidade do `ActiveUpgrade`.

    `active` existe aqui porque é o estado que o seletor errava: durante a
    execução do efeito o `cooldown_left` ainda é ZERO (a recarga só parte quando
    o efeito acaba), então "cooldown zerado" **não** quer dizer "pode usar".
    """

    def __init__(self, cooldown_left, active=False):
        self.cooldown_left = cooldown_left
        self.active = active

    @property
    def is_ready(self):
        return not self.active and self.cooldown_left <= 0.0


@pytest.fixture
def selector():
    # slot 0 vazio; 1 pronto; 2 em cooldown; 3 pronto.
    slots = [None, _Upg(0.0), _Upg(2.0), _Upg(0.0)]
    activated = []
    sel = UpgradeSelector(get_slots=lambda: slots, activate=activated.append)
    return sel, slots, activated


def test_toggle_alinha_em_slot_pronto(selector):
    sel, *_ = selector
    sel.toggle()
    assert sel.mode
    assert sel.index == 1  # primeiro pronto, não o slot 0 (vazio)


def test_toggle_desliga(selector):
    sel, *_ = selector
    sel.toggle()
    sel.toggle()
    assert not sel.mode


def test_navigate_prioriza_prontos_depois_cooling(selector):
    # Ordem esperada: prontos [1, 3] antes de cooling [2] → [1, 3, 2].
    sel, *_ = selector
    sel.toggle()
    assert sel.index == 1
    sel.navigate(+1)
    assert sel.index == 3
    sel.navigate(+1)
    assert sel.index == 2  # o em cooldown vem por último
    sel.navigate(+1)
    assert sel.index == 1  # circular


def test_navigate_para_tras(selector):
    sel, *_ = selector
    sel.toggle()
    sel.navigate(-1)
    assert sel.index == 2  # de 1, um passo para trás na ordem [1,3,2]


def test_confirm_ativa_e_sai(selector):
    sel, _slots, activated = selector
    sel.toggle()
    sel.index = 1
    sel.confirm()
    assert activated == [1]
    assert not sel.mode


def test_cancel_sai_sem_ativar(selector):
    sel, _slots, activated = selector
    sel.toggle()
    sel.cancel()
    assert not sel.mode
    assert activated == []


def test_toggle_sem_upgrades_e_noop():
    sel = UpgradeSelector(get_slots=lambda: [None, None], activate=lambda i: None)
    sel.toggle()
    assert not sel.mode


def test_confirm_em_slot_vazio_nao_ativa():
    activated = []
    sel = UpgradeSelector(
        get_slots=lambda: [None, _Upg(0.0)], activate=activated.append
    )
    sel.index = 0  # slot vazio
    sel.confirm()
    assert activated == []


def test_upgrade_em_execucao_nao_conta_como_pronto():
    """Seleção rápida: usar um e chamar o cursor leva ao PRÓXIMO disponível.

    O regressão real: o upgrade recém-disparado fica `active` com
    `cooldown_left == 0` durante toda a duração do efeito. Com a checagem antiga
    (só o cooldown) o cursor pousava justamente nele — o único que não responde —
    e o jogador apertava A no vazio.
    """
    slots = [_Upg(0.0, active=True), _Upg(0.0)]
    sel = UpgradeSelector(get_slots=lambda: slots, activate=lambda i: None)
    sel.toggle()
    assert sel.index == 1, "o cursor parou no upgrade que está em execução"


def test_em_execucao_vai_para_o_fim_da_fila_como_o_em_recarga():
    """Ativo (ainda sem cooldown) navega junto dos indisponíveis, não à frente."""
    slots = [_Upg(0.0, active=True), _Upg(3.0), _Upg(0.0)]
    sel = UpgradeSelector(get_slots=lambda: slots, activate=lambda i: None)
    sel.toggle()
    assert sel.index == 2  # o único disponível abre a fila
    sel.navigate(+1)
    assert sel.index == 0  # depois os indisponíveis, na ordem dos slots
    sel.navigate(+1)
    assert sel.index == 1


def test_le_a_lista_fresca_a_cada_chamada():
    # A cena reatribui upgrade_slots por fase; o seletor não pode cachear.
    estado = {"slots": [None, None]}
    sel = UpgradeSelector(get_slots=lambda: estado["slots"], activate=lambda i: None)
    sel.toggle()
    assert not sel.mode  # nada equipado ainda
    estado["slots"] = [_Upg(0.0)]  # nova fase equipa um upgrade
    sel.toggle()
    assert sel.mode and sel.index == 0
