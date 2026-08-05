"""Trava de reutilização da habilidade especial (charge shot).

O laser do Magneto e a rajada teleguiada do Caçador duram um tempo depois do
disparo. Reativar a habilidade nesse intervalo empilhava um segundo efeito por
cima do primeiro; o Caçador tinha um gate para isso escondido dentro do próprio
disparo (e o Magneto, nenhum), que recusava **em silêncio** — o jogador segurava
a carga inteira e não recebia nada, sem uma linha na tela explicando.

Estes testes travam as duas metades da correção: a habilidade fica indisponível
enquanto o efeito anterior roda, e a tentativa recusada produz feedback
(evento + timer da nave), nunca silêncio.
"""

import pytest

from game.core.config import config as Config
from game.core.ship_types import get_ship_profile
from game.entities.player.ship import Ship
from game.events import game_events as events
from game.systems.shooting_system import ShootingSystem


class _FakeLaser:
    """`BossLaser` na medida do gate: dono, estado e morte."""

    def __init__(self, owner_ship, state="alive", dead=False):
        self.owner_ship = owner_ship
        self.state = state
        self.dead = dead


class _FakeHoming:
    def __init__(self, source_ship, dead=False):
        self.source_ship = source_ship
        self.dead = dead


class _FakeEM:
    def __init__(self):
        self.cacador_lasers: list = []
        self.homing_bullets: list = []
        self.enemies: list = []
        self.boss = None

    def spawn_cacador_laser(self, x, y, direction, damage, owner_ship=None):
        laser = _FakeLaser(owner_ship)
        self.cacador_lasers.append(laser)
        return laser

    def spawn_homing_bullet(
        self, x, y, damage, direction=None, locked_target=None, source_ship=None
    ):
        homing = _FakeHoming(source_ship)
        self.homing_bullets.append(homing)
        return homing


class _FakeBus:
    def __init__(self):
        self.events: list = []

    def emit(self, event):
        self.events.append(event)


def make_ship(ship_id: str) -> Ship:
    return Ship(100, 100, profile=get_ship_profile(ship_id))


@pytest.fixture
def magneto() -> Ship:
    return make_ship("magneto")


@pytest.fixture
def cacador() -> Ship:
    return make_ship("cacador")


@pytest.fixture
def system_and_em():
    em = _FakeEM()
    bus = _FakeBus()
    return ShootingSystem(em, bus), em, bus


class TestDisponibilidade:
    def test_livre_quando_nada_esta_em_curso(self, system_and_em, magneto):
        system, _em, _bus = system_and_em
        assert system.ability_busy(magneto) is False
        assert system.try_start_charge(magneto) is True
        assert magneto.charge_shot_active is True

    def test_laser_vivo_bloqueia_o_magneto(self, system_and_em, magneto):
        system, em, _bus = system_and_em
        em.cacador_lasers.append(_FakeLaser(magneto))
        assert system.ability_busy(magneto) is True
        assert system.try_start_charge(magneto) is False
        assert magneto.charge_shot_active is False

    def test_teleguiado_vivo_bloqueia_o_cacador(self, system_and_em, cacador):
        system, em, _bus = system_and_em
        em.homing_bullets.append(_FakeHoming(cacador))
        assert system.ability_busy(cacador) is True
        assert system.try_start_charge(cacador) is False
        assert cacador.charge_shot_active is False

    def test_laser_morrendo_ja_libera(self, system_and_em, magneto):
        """`dying` é só a poeira de partículas — sem colisão. Travar a
        habilidade nela seria atraso sem causa visível na tela."""
        system, em, _bus = system_and_em
        em.cacador_lasers.append(_FakeLaser(magneto, state="dying"))
        assert system.ability_busy(magneto) is False

    def test_projetil_morto_nao_bloqueia(self, system_and_em, cacador):
        system, em, _bus = system_and_em
        em.homing_bullets.append(_FakeHoming(cacador, dead=True))
        assert system.ability_busy(cacador) is False

    def test_efeito_do_outro_jogador_nao_bloqueia(self, system_and_em, cacador):
        """Coop: dois Caçadores atiram ao mesmo tempo. O gate é por DONO — pelo
        tamanho da lista, o burst do P1 travaria o P2."""
        system, em, _bus = system_and_em
        outro = make_ship("cacador")
        em.homing_bullets.append(_FakeHoming(outro))
        em.cacador_lasers.append(_FakeLaser(outro))
        assert system.ability_busy(cacador) is False
        assert system.try_start_charge(cacador) is True

    def test_nave_sem_habilidade_nunca_e_bloqueada(self, system_and_em):
        system, em, _bus = system_and_em
        padrao = make_ship("padrao")
        em.homing_bullets.append(_FakeHoming(padrao))
        # `start_charge` recusa por perfil (sem `has_charge_shot`), mas o gate
        # em si não pode inventar um bloqueio para quem não tem habilidade.
        assert system.ability_busy(padrao) is True
        assert system.try_start_charge(padrao) is False


class TestFeedbackDaRecusa:
    def test_recusa_emite_evento(self, system_and_em, magneto):
        system, em, bus = system_and_em
        em.cacador_lasers.append(_FakeLaser(magneto))
        system.try_start_charge(magneto)
        negados = [e for e in bus.events if isinstance(e, events.AbilityDenied)]
        assert len(negados) == 1
        assert negados[0].ship_type == "magneto"

    def test_recusa_arma_o_feedback_visual(self, system_and_em, cacador):
        system, em, _bus = system_and_em
        em.homing_bullets.append(_FakeHoming(cacador))
        assert cacador.ability_denied_timer == 0.0
        system.try_start_charge(cacador)
        assert cacador.ability_denied_timer == pytest.approx(
            Config.ABILITY_DENIED_FEEDBACK_TIME
        )

    def test_ativacao_aceita_nao_arma_feedback(self, system_and_em, magneto):
        system, _em, bus = system_and_em
        system.try_start_charge(magneto)
        assert magneto.ability_denied_timer == 0.0
        assert not [e for e in bus.events if isinstance(e, events.AbilityDenied)]

    def test_feedback_escoa_no_update(self, magneto):
        magneto.deny_ability()
        total = Config.ABILITY_DENIED_FEEDBACK_TIME
        magneto.update(total * 0.5)
        assert magneto.ability_denied_timer == pytest.approx(total * 0.5)
        magneto.update(total)
        assert magneto.ability_denied_timer == 0.0

    def test_som_de_recusa_esta_ligado_ao_evento(self):
        """§2: quem reage é o `SoundSystem`, e o handler tem `off` no cleanup."""
        from game.systems.sound_system import SoundSystem

        registrados: list = []
        removidos: list = []

        class _Bus:
            def on(self, evt, handler):
                registrados.append(evt)

            def off(self, evt, handler):
                removidos.append(evt)

        system = SoundSystem(_Bus())
        assert events.AbilityDenied in registrados
        system.cleanup()
        assert events.AbilityDenied in removidos


class TestRedeDeSeguranca:
    """O disparo em si também recusa — cobre a carga iniciada antes do gate."""

    def carregar(self, ship: Ship) -> None:
        ship.charge_shot_active = True
        ship.charge_shot_timer = ship.profile.charge_shot_max_time

    def test_laser_em_curso_nao_spawna_um_segundo(self, system_and_em, magneto):
        system, em, _bus = system_and_em
        em.cacador_lasers.append(_FakeLaser(magneto))
        self.carregar(magneto)
        system.fire(magneto, player_damage_multiplier=1.0)
        assert len(em.cacador_lasers) == 1
        assert magneto.ability_denied_timer > 0.0

    def test_burst_em_curso_nao_spawna_um_segundo(self, system_and_em, cacador):
        system, em, _bus = system_and_em
        em.homing_bullets.append(_FakeHoming(cacador))
        self.carregar(cacador)
        system.fire(cacador, player_damage_multiplier=1.0)
        assert len(em.homing_bullets) == 1
        assert cacador.ability_denied_timer > 0.0

    def test_com_a_habilidade_livre_o_disparo_sai_inteiro(self, system_and_em, cacador):
        system, em, _bus = system_and_em
        self.carregar(cacador)
        system.fire(cacador, player_damage_multiplier=1.0)
        assert len(em.homing_bullets) == 5
        assert cacador.ability_denied_timer == 0.0

    def test_magneto_livre_dispara_o_laser(self, system_and_em, magneto):
        system, em, _bus = system_and_em
        self.carregar(magneto)
        system.fire(magneto, player_damage_multiplier=1.0)
        assert len(em.cacador_lasers) == 1
        assert em.cacador_lasers[0].owner_ship is magneto
