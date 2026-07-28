"""Leque do Spread Shot (`PowerUpType.SPREAD_SHOT`).

O power-up é a direção do disparo, não a posição: cinco balas saem da MESMA
boca, abertas em ângulo. Esses testes travam o que faz o leque ser leque —
simetria, módulo preservado (mesma velocidade do tiro normal), e o tiro central
idêntico ao padrão — mais as três interações onde ele poderia virar outra coisa:
combinar com o Double Shot (10 balas), com o charge shot (5 lasers) ou com a
carga explosiva (5 cargas por disparo).
"""

import math

import pytest

from game.core.config import PowerUpType
from game.core.config import config as Config
from game.entities.player.ship import Ship
from game.entities.pickups.powerup import PowerUp
from game.render.game_renderer import GameRenderer


@pytest.fixture
def ship() -> Ship:
    from game.core.ship_types import get_ship_profile

    return Ship(100, 100, profile=get_ship_profile("padrao"))


def directions(specs) -> list[tuple[float, float]]:
    return [spec.direction for spec in specs]


def positions(specs) -> list[tuple[float, float]]:
    return [(spec.x, spec.y) for spec in specs]


class TestLeque:
    def test_sem_powerup_o_tiro_e_um_so(self, ship: Ship):
        assert len(ship.bullet_spawn()) == 1

    def test_com_powerup_saem_cinco(self, ship: Ship):
        ship.spread_shot_timer = 5.0
        assert len(ship.bullet_spawn()) == len(Config.SPREAD_SHOT_ANGLES) == 5

    def test_todas_saem_da_mesma_boca(self, ship: Ship):
        """O leque abre em ângulo, não em posição — se as bocas divergissem, o
        padrão viraria uma parede em vez de um leque."""
        ship.spread_shot_timer = 5.0
        assert len(set(positions(ship.bullet_spawn()))) == 1

    def test_boca_e_a_mesma_do_tiro_normal(self, ship: Ship):
        ship.spread_shot_timer = 5.0
        com_leque = positions(ship.bullet_spawn())[0]
        ship.spread_shot_timer = 0.0
        assert com_leque == positions(ship.bullet_spawn())[0]

    def test_tiro_central_e_o_tiro_padrao(self, ship: Ship):
        """O 0.0 do meio de `SPREAD_SHOT_ANGLES` tem que sair intacto: é ele que
        mantém a sensação de mira que o leque não pode perder."""
        ship.spread_shot_timer = 0.0
        base = directions(ship.bullet_spawn())[0]
        ship.spread_shot_timer = 5.0
        central = directions(ship.bullet_spawn())[len(Config.SPREAD_SHOT_ANGLES) // 2]
        assert central == pytest.approx(base)

    def test_mesma_velocidade_do_tiro_normal(self, ship: Ship):
        """Rotação preserva o módulo. Uma bala externa mais lenta (ou mais
        rápida) que a central quebraria o requisito de 'só a direção muda'."""
        ship.spread_shot_timer = 5.0
        for dx, dy in directions(ship.bullet_spawn()):
            assert math.hypot(dx, dy) == pytest.approx(1.0)

    def test_leque_e_simetrico(self, ship: Ship):
        """Assimetria puxaria a mira para um lado — o jogador compensa sem saber
        por quê."""
        ship.spread_shot_timer = 5.0
        angulos = [
            math.degrees(math.atan2(dx, -dy))  # 0° = norte (y cresce para baixo)
            for dx, dy in directions(ship.bullet_spawn())
        ]
        assert angulos == pytest.approx(sorted(angulos))
        for esquerda, direita in zip(angulos, reversed(angulos)):
            assert esquerda == pytest.approx(-direita)

    def test_angulos_batem_com_a_config(self, ship: Ship):
        ship.spread_shot_timer = 5.0
        angulos = [
            math.degrees(math.atan2(dx, -dy))
            for dx, dy in directions(ship.bullet_spawn())
        ]
        assert angulos == pytest.approx(list(Config.SPREAD_SHOT_ANGLES))

    def test_angulos_ficam_na_faixa_de_mira(self):
        """Acima de ~25° o leque vira cone de shotgun e a nave para de acertar
        alvos distantes — deixa de ser 'cobertura com precisão'."""
        assert all(abs(a) <= 25.0 for a in Config.SPREAD_SHOT_ANGLES)

    def test_abre_em_qualquer_facing(self, ship: Ship):
        """Fases side-scroll giram a nave; o leque tem que acompanhar o rumo em
        vez de assumir 'para cima'."""
        ship.spread_shot_timer = 5.0
        for facing, base in (
            ("north", (0.0, -1.0)),
            ("south", (0.0, 1.0)),
            ("east", (1.0, 0.0)),
            ("west", (-1.0, 0.0)),
        ):
            ship.facing = facing
            dirs = directions(ship.bullet_spawn())
            assert len(dirs) == 5
            central = dirs[2]
            assert central == pytest.approx(base)


class TestInteracoes:
    def test_nao_multiplica_com_double_shot(self, ship: Ship):
        """2 bocas x 5 direções seriam 10 balas por disparo. O leque substitui
        as bocas duplas; com os dois ativos vale o leque."""
        ship.double_shot_timer = 5.0
        ship.spread_shot_timer = 5.0
        specs = ship.bullet_spawn()
        assert len(specs) == 5
        assert len(set(positions(specs))) == 1

    def test_double_shot_sozinho_nao_muda(self, ship: Ship):
        ship.double_shot_timer = 5.0
        specs = ship.bullet_spawn()
        assert len(specs) == 2
        assert len(set(positions(specs))) == 2
        assert len(set(directions(specs))) == 1

    def test_charge_shot_nao_abre_em_leque(self, ship: Ship):
        """`apply_spread=False` é o que impede 5 lasers do Magneto e 5x5
        teleguiados do Caçador."""
        ship.spread_shot_timer = 5.0
        assert len(ship.bullet_spawn(apply_spread=False)) == 1

    def test_todas_as_cinco_explodem(self, ship: Ship):
        """Upgrade de disparo COMBINA com o leque, não é substituído por ele."""
        ship.activate_explosive_shots(10)
        ship.spread_shot_timer = 5.0
        assert all(spec.explosive for spec in ship.bullet_spawn())

    def test_perfurante_e_teleguiado_valem_para_todas(self, ship: Ship):
        """Modificadores por tempo seguem valendo no leque inteiro — é o 'mesmo
        comportamento do tiro padrão' aplicado a cada projétil."""
        ship.spread_shot_timer = 5.0
        ship.piercing_shot_timer = 5.0
        ship.homing_shots_active = True
        specs = ship.bullet_spawn()
        assert all(spec.piercing for spec in specs)
        assert all(spec.homing for spec in specs)

    def test_modificadores_empilham_todos_de_uma_vez(self, ship: Ship):
        """A combinação completa: nenhum campo do spec desliga outro."""
        ship.spread_shot_timer = 5.0
        ship.piercing_shot_timer = 5.0
        ship.homing_shots_active = True
        ship.activate_explosive_shots(10)
        ship.activate_giant_shots(5.0)

        specs = ship.bullet_spawn()
        assert len(specs) == 5
        for spec in specs:
            assert spec.piercing and spec.homing and spec.explosive
        # Giant Shot é por disparo (o ShootingSystem repassa a todas as balas),
        # então não é campo do spec — mas tem que estar ativo aqui.
        assert ship.bullet_size_multiplier > 1.0

    def test_cadencia_penalizada_enquanto_ativo(self, ship: Ship):
        """O custo de cadência é o freio de balanceamento do leque; sem ele o
        power-up é um Double Shot estritamente melhor."""
        base = ship.attack_speed_multiplier
        ship.spread_shot_timer = 5.0
        assert ship.attack_speed_multiplier == pytest.approx(
            base * Config.SPREAD_SHOT_FIRE_RATE_PENALTY
        )
        assert 0.5 < Config.SPREAD_SHOT_FIRE_RATE_PENALTY < 1.0


class _FakeBullet:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.vx = 0.0
        self.vy = 0.0


class _FakeEM:
    """EntityManager mínimo: guarda o que `spawn_bullet` recebeu."""

    def __init__(self):
        self.spawned: list[dict] = []
        self.cacador_lasers: list = []

    def spawn_bullet(self, x, y, **kwargs):
        self.spawned.append({"x": x, "y": y, **kwargs})
        return _FakeBullet(x=x, y=y)


class _FakeBus:
    def __init__(self):
        self.events: list = []

    def emit(self, event):
        self.events.append(event)


class TestDisparoCompleto:
    """O caminho real: `ShootingSystem.fire` → `spawn_bullet`.

    `bullet_spawn` sozinho não prova a combinação — o tamanho do Giant Shot e o
    consumo da carga explosiva só acontecem aqui.
    """

    def fire_once(self, ship: Ship) -> _FakeEM:
        from game.systems.shooting_system import ShootingSystem

        em = _FakeEM()
        ShootingSystem(em, _FakeBus()).fire(ship, player_damage_multiplier=1.0)
        return em

    def test_todas_as_balas_do_leque_nascem(self, ship: Ship):
        ship.spread_shot_timer = 5.0
        assert len(self.fire_once(ship).spawned) == 5

    def test_giant_shot_vale_para_as_cinco(self, ship: Ship):
        ship.spread_shot_timer = 5.0
        ship.activate_giant_shots(5.0)
        tamanhos = {b["size_multiplier"] for b in self.fire_once(ship).spawned}
        assert tamanhos == {ship.bullet_size_multiplier}
        assert ship.bullet_size_multiplier > 1.0

    def test_explosivo_e_teleguiado_chegam_em_todas(self, ship: Ship):
        ship.spread_shot_timer = 5.0
        ship.activate_explosive_shots(10)
        ship.homing_shots_active = True
        ship.piercing_shot_timer = 5.0
        for b in self.fire_once(ship).spawned:
            assert b["explosive"] and b["homing"] and b["piercing"]

    def test_carga_explosiva_e_por_disparo_nao_por_bala(self, ship: Ship):
        """Com o consumo por bala, o leque queimava 5 das 10 cargas por puxada
        de gatilho — o upgrade durava 2 disparos em vez de 10."""
        ship.spread_shot_timer = 5.0
        ship.activate_explosive_shots(10)
        self.fire_once(ship)
        assert ship.explosive_shots_remaining == 9

    def test_economia_da_carga_independe_dos_powerups_ativos(self, ship: Ship):
        """Mesmo upgrade, mesma duração, com ou sem power-up de disparo junto."""
        from game.core.ship_types import get_ship_profile

        gastos = []
        for ligar in (
            lambda s: None,
            lambda s: setattr(s, "double_shot_timer", 5.0),
            lambda s: setattr(s, "spread_shot_timer", 5.0),
        ):
            s = Ship(100, 100, profile=get_ship_profile("padrao"))
            s.activate_explosive_shots(10)
            ligar(s)
            self.fire_once(s)
            gastos.append(10 - s.explosive_shots_remaining)
        assert gastos == [1, 1, 1]

    def test_sem_leque_o_disparo_continua_unico(self, ship: Ship):
        assert len(self.fire_once(ship).spawned) == 1


class TestRegistro:
    """O power-up novo precisa aparecer nos três lugares que o jogador vê.

    `tests/test_powerup_colors.py` já varre isso genericamente por
    `PowerUpType`; aqui fica explícito para quem for mexer no leque.
    """

    def test_e_um_powerup_de_verdade(self):
        assert PowerUpType.SPREAD_SHOT.value == "spread_shot"

    def test_tem_identidade_visual(self):
        assert "spread_shot" in PowerUp.LABELS
        assert "spread_shot" in GameRenderer.POWERUP_UI_DATA

    def test_entra_no_sorteio_de_spawn(self):
        from game.core.difficulty import DifficultyPreset
        from game.core.powerup_weights import get_powerup_weights

        for preset in DifficultyPreset:
            pesos = get_powerup_weights(preset)
            assert pesos.get(PowerUpType.SPREAD_SHOT, 0) > 0
            # Mais raro que o Double Shot: vale mais, aparece menos.
            assert pesos[PowerUpType.SPREAD_SHOT] < pesos[PowerUpType.DOUBLE_SHOT]


class TestAtivacao:
    def test_coleta_liga_o_timer_e_renova_sem_somar(self):
        from game.core.ship_types import get_ship_profile
        from game.systems.powerup_system import PowerupSystem

        ship = Ship(100, 100, profile=get_ship_profile("padrao"))
        slot = type("_Slot", (), {"ship": ship})()
        system = PowerupSystem.__new__(PowerupSystem)
        system._powerup_values = {"spread_shot_duration": Config.SPREAD_SHOT_DURATION}

        system._apply_spread_shot(slot)
        assert ship.spread_shot_timer == Config.SPREAD_SHOT_DURATION

        # `max` e não `+=`: coletar dois seguidos renova, não acumula.
        ship.spread_shot_timer = Config.SPREAD_SHOT_DURATION * 3
        system._apply_spread_shot(slot)
        assert ship.spread_shot_timer == Config.SPREAD_SHOT_DURATION * 3

    def test_timer_expira_com_o_tempo(self):
        from game.core.ship_types import get_ship_profile

        ship = Ship(100, 100, profile=get_ship_profile("padrao"))
        ship.spread_shot_timer = 0.5
        ship._powerups.update_timers(0.3)
        assert ship.spread_shot_timer == pytest.approx(0.2)
        ship._powerups.update_timers(1.0)
        assert ship.spread_shot_timer == 0.0
        assert len(ship.bullet_spawn()) == 1
