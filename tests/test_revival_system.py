"""RevivalSystem — beacons de revive cooperativo.

O fato de estes testes rodarem com stubs mínimos (sem `PlayingScene`, sem o
jogo) é a prova do §1: o sistema depende só de roster, gamepad e dois
callbacks. Cobrem o fluxo completo — spawn condicionado a coop, detecção de
parceiro no raio, gate pelo botão, e revive com os callbacks certos.
"""

import pygame
import pytest

from game.entities.player.revival_beacon import RevivalBeacon
from game.systems.revival_system import RevivalSystem


class _Ship:
    def __init__(self, cx, cy):
        self.rect = pygame.Rect(cx - 10, cy - 10, 20, 20)
        self.w = self.h = 20
        self.x = cx - 10
        self.y = cy - 10
        self.invuln = 0
        self.ship_image = pygame.Surface((20, 20))


class _Slot:
    def __init__(self, cx, cy, dead=False, gamepad_slot=0):
        self.ship = _Ship(cx, cy)
        self.is_dead = dead
        self.gamepad_slot = gamepad_slot
        self.revival_beacon = None
        self.lives = 0


class _Roster:
    def __init__(self, slots):
        self._slots = slots

    def count(self):
        return len(self._slots)

    def dead_slots(self):
        return [s for s in self._slots if s.is_dead]

    def alive_slots(self):
        return [s for s in self._slots if not s.is_dead]


class _Gamepad:
    def __init__(self):
        self.held = False

    def is_button_pressed(self, _button, slot=0):
        return self.held


@pytest.fixture
def scenario():
    """Um morto e um vivo SOBREPOSTOS (portanto no raio um do outro)."""
    dead = _Slot(100, 100, dead=True)
    alive = _Slot(100, 100, dead=False, gamepad_slot=1)
    gamepad = _Gamepad()
    synced = []
    rebuilt = []
    system = RevivalSystem(
        roster=_Roster([dead, alive]),
        gamepad=gamepad,
        sync_lives=lambda s, lives: synced.append((s, lives)),
        rebuild_mini_ships=lambda s: rebuilt.append(s),
    )
    return system, dead, alive, gamepad, synced, rebuilt


def test_single_player_nao_spawna_beacon():
    dead = _Slot(100, 100, dead=True)
    system = RevivalSystem(
        roster=_Roster([dead]),
        gamepad=_Gamepad(),
        sync_lives=lambda s, lives: None,
        rebuild_mini_ships=lambda s: None,
    )
    system.spawn_beacon(dead)
    assert dead.revival_beacon is None


def test_coop_spawna_beacon_na_nave(scenario):
    system, dead, *_ = scenario
    system.spawn_beacon(dead)
    assert dead.revival_beacon is not None
    assert dead.revival_beacon.x == 100
    assert dead.revival_beacon.y == 100


def test_sem_botao_nao_revive(scenario):
    system, dead, _alive, gamepad, synced, _ = scenario
    system.spawn_beacon(dead)
    gamepad.held = False
    for _ in range(600):
        system.update(1 / 60)
    assert dead.is_dead
    assert synced == []


def test_parceiro_no_raio_detectado(scenario):
    system, dead, alive, *_ = scenario
    system.spawn_beacon(dead)
    assert system.slot_inside_any_beacon(alive)


def test_segurando_botao_revive_com_callbacks(scenario):
    system, dead, _alive, gamepad, synced, rebuilt = scenario
    system.spawn_beacon(dead)
    gamepad.held = True
    for _ in range(600):
        system.update(1 / 60)
        if not dead.is_dead:
            break
    assert not dead.is_dead
    assert len(synced) == 1
    assert synced[0][1] == RevivalBeacon.LIVES_ON_REVIVE
    assert len(rebuilt) == 1
    assert dead.revival_beacon is None
