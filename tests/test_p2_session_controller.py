"""Testes do P2SessionController (extraído da PlayingScene, §9).

Prova da extração: o ciclo de vida do co-op (entrada/saída/desconexão + spawn/HUD)
roda com stubs mínimos de roster/gamepad/entity_manager e callbacks, sem instanciar
a cena. Trava o contrato: os gatilhos consomem o evento certo, o despawn descarta
companheiros e reescala jogadores, o spawn adiciona e escala, o HUD reflete o co-op.
"""

import pygame

from game.core.gamepad import XboxButton
from game.core.ship_types import get_ship_profile
from game.systems.p2_session_controller import P2SessionController


class _FakeShip:
    def __init__(self):
        self.x = 100.0
        self.y = 100.0
        self.is_entering = False
        self.entry_target_pos = (100.0, 100.0)


class _FakeSlot:
    def __init__(self, ship, gamepad_slot=0):
        self.ship = ship
        self.gamepad_slot = gamepad_slot
        self.revival_beacon = None
        self.lives = 3
        self.is_dead = False


class _FakeRoster:
    def __init__(self, slots):
        self._slots = list(slots)

    def all_slots(self):
        return list(self._slots)

    def count(self):
        return len(self._slots)

    def primary(self):
        return self._slots[0]

    def add(self, slot):
        self._slots.append(slot)

    def remove(self, slot):
        self._slots.remove(slot)


class _FakeGamepad:
    def __init__(self, *, secondary=True, slot1_connected=True):
        self.secondary_connected = secondary
        self._slot1_connected = slot1_connected

    def slot_of_instance_id(self, iid):
        return 1 if iid == 1 else 0

    def is_slot_connected(self, slot):
        return self._slot1_connected if slot == 1 else True


class _FakeEM:
    def __init__(self):
        self.removed = []

    def remove_companions_of_ship(self, ship):
        self.removed.append(ship)


def _make(roster, gamepad, **over):
    kw = dict(
        roster=roster,
        gamepad=gamepad,
        entity_manager=_FakeEM(),
        get_is_side_scroll=lambda: False,
        get_lives=lambda: 3,
        set_player_count=lambda c: None,
        open_p2_modal=lambda cb: None,
        build_permanent_mini_ships=lambda s: None,
    )
    kw.update(over)
    return P2SessionController(**kw)


def _btn(button, iid=1):
    return pygame.event.Event(
        pygame.JOYBUTTONDOWN, {"button": button, "instance_id": iid}
    )


class TestTriggers:
    def test_start_abre_modal_com_spawn_como_callback(self):
        captured = {}
        ctrl = _make(
            _FakeRoster([_FakeSlot(_FakeShip())]),
            _FakeGamepad(),
            open_p2_modal=lambda cb: captured.update(cb=cb),
        )
        assert ctrl.try_handle_event(_btn(XboxButton.START)) is True
        assert captured["cb"] == ctrl.spawn_p2

    def test_start_nao_abre_se_ja_ha_dois(self):
        ctrl = _make(
            _FakeRoster([_FakeSlot(_FakeShip()), _FakeSlot(_FakeShip(), 1)]),
            _FakeGamepad(),
        )
        # START com 2 slots não é join (nem leave/disconnect) → não consome.
        assert ctrl.try_handle_event(_btn(XboxButton.START)) is False

    def test_back_remove_p2(self):
        p1, p2 = _FakeSlot(_FakeShip()), _FakeSlot(_FakeShip(), gamepad_slot=1)
        roster, em, counts = _FakeRoster([p1, p2]), _FakeEM(), []
        ctrl = _make(roster, _FakeGamepad(), entity_manager=em, set_player_count=counts.append)
        assert ctrl.try_handle_event(_btn(XboxButton.BACK)) is True
        assert roster.count() == 1
        assert em.removed == [p2.ship]  # companheiros do P2 descartados
        assert counts == [1]  # reescalou para solo

    def test_desconexao_remove_p2(self):
        p1, p2 = _FakeSlot(_FakeShip()), _FakeSlot(_FakeShip(), gamepad_slot=1)
        roster = _FakeRoster([p1, p2])
        ctrl = _make(roster, _FakeGamepad(slot1_connected=False), entity_manager=_FakeEM())
        ev = pygame.event.Event(pygame.JOYDEVICEREMOVED, {})
        assert ctrl.try_handle_event(ev) is True
        assert roster.count() == 1

    def test_evento_alheio_nao_consome(self):
        ctrl = _make(_FakeRoster([_FakeSlot(_FakeShip())]), _FakeGamepad())
        ev = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE})
        assert ctrl.try_handle_event(ev) is False


class TestHud:
    def test_none_em_solo(self):
        ctrl = _make(_FakeRoster([_FakeSlot(_FakeShip())]), _FakeGamepad())
        assert ctrl.build_hud_info() is None

    def test_info_em_coop(self):
        p2 = _FakeSlot(_FakeShip(), gamepad_slot=1)
        p2.lives = 2
        ctrl = _make(_FakeRoster([_FakeSlot(_FakeShip()), p2]), _FakeGamepad())
        info = ctrl.build_hud_info()
        assert info is not None
        assert info.lives == 2
        assert info.ship is p2.ship


class TestSpawn:
    def test_spawn_adiciona_escala_e_constroi_minis(self):
        primary = _FakeSlot(_FakeShip())
        roster, counts, built = _FakeRoster([primary]), [], []
        ctrl = _make(
            roster,
            _FakeGamepad(),
            set_player_count=counts.append,
            build_permanent_mini_ships=built.append,
            get_lives=lambda: 2,
        )
        ctrl.spawn_p2(get_ship_profile("padrao"))
        assert roster.count() == 2
        new_slot = roster.all_slots()[1]
        assert new_slot.ship.player_index == 1  # nave de P2 (ciano)
        assert new_slot.lives == 2
        assert built == [new_slot]  # mini-naves permanentes construídas
        assert counts == [2]  # escala de co-op propagada
