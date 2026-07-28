"""Upgrade Shockwave — a morte de cada inimigo vira uma explosão pequena.

Entregue SEM empurrão e SEM interromper ataques, por decisão registrada no
plano: empurrar é escrever posição de fora, e isso já custou cinco bugs.
Também **sem lentidão** — a Implosão e o Cryo já são lentidão, e um terceiro
faria os três lerem como "o upgrade do efeitinho". O que este entrega de único
é apagar os tiros inimigos por perto.

O que estes testes guardam:

1. **o gancho é o `EnemyDestroyed` do bus** e o handler tem `cleanup()` (§2);
2. **o teto de ondas vivas**, que não é orçamento de frame e sim o que garante
   que a cascata termina — a onda mata, a morte gera outra onda, e a nova entra
   na MESMA lista que o passe de dano está percorrendo;
3. **boss não gera onda**, herdado do filtro que já existe na emissão;
4. **os projéteis inimigos por perto morrem**, que é a parte que o jogador
   sente como alívio.
"""

import pygame
import pytest

from game.core.events import EventBus
from game.core.ship_types import get_ship_profile
from game.core.upgrades import (
    UPGRADES_META,
    UpgradeCategory,
    UpgradeType,
    get_upgrade_icon,
    upgrade_factory,
)
from game.core.upgrades_config import (
    DEFAULT_UNLOCKED,
    SHOCKWAVE_DAMAGE,
    SHOCKWAVE_MAX_ACTIVE,
    SHOCKWAVE_RADIUS,
)
from game.entities.player.ship import Ship
from game.events import game_events as events
from game.systems.entity_manager import EntityManager
from game.systems.shockwave_system import ShockwaveSystem

CX, CY = 600.0, 300.0


class Projetil:
    """Projétil inimigo mínimo: o sistema só precisa de `rect` e `dead`."""

    def __init__(self, x: float, y: float):
        self.rect = pygame.Rect(int(x), int(y), 8, 8)
        self.dead = False


def montar(ativo: bool = True):
    em = EntityManager()
    bus = EventBus()
    sistema = ShockwaveSystem(bus, em, is_active=lambda: ativo)
    return em, bus, sistema


def matar(bus, x: float = CX, y: float = CY, points: int = 10) -> None:
    bus.emit(
        events.EnemyDestroyed(enemy_type="Meteor", position=(x, y), points=points)
    )


class Ctx:
    entity_manager = None
    difficulty_settings: dict = {}
    sound_manager = None
    god_mode = False
    scene = None


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------


class TestRegistro:
    def test_e_construivel(self):
        assert upgrade_factory(UpgradeType.SHOCKWAVE).meta.type is UpgradeType.SHOCKWAVE

    def test_e_ofensivo(self):
        """O valor é dano em área e limpeza de tela, não controle."""
        assert (
            UPGRADES_META[UpgradeType.SHOCKWAVE].category is UpgradeCategory.OFFENSIVE
        )

    def test_esta_desbloqueado_por_padrao(self):
        assert UpgradeType.SHOCKWAVE in DEFAULT_UNLOCKED

    def test_tem_icone_proprio_no_hud(self):
        meta = UPGRADES_META[UpgradeType.SHOCKWAVE]
        letra = get_upgrade_icon(meta.name, meta.icon_id)
        outras = {
            get_upgrade_icon(m.name, m.icon_id)
            for t, m in UPGRADES_META.items()
            if t is not UpgradeType.SHOCKWAVE
        }
        assert letra not in outras, f"letra '{letra}' já usada"

    def test_descricao_traduzida_nos_dois_idiomas(self):
        from game.core.translations import TABLES

        for lang, tabela in TABLES.items():
            assert "upgrade.shockwave.desc" in tabela, lang

    def test_ativar_liga_o_timer_da_nave(self):
        ship = Ship(100, 100, profile=get_ship_profile("padrao"))
        assert ship.has_shockwave is False

        up = upgrade_factory(UpgradeType.SHOCKWAVE)
        Ctx.ship = ship
        assert up.activate(Ctx()) is True
        assert ship.shockwave_timer == pytest.approx(up.meta.base_duration)

        ship._powerups.update_timers(up.meta.base_duration + 0.1)
        assert ship.has_shockwave is False


# ---------------------------------------------------------------------------
# O gancho
# ---------------------------------------------------------------------------


class TestGancho:
    def test_morte_com_upgrade_cria_a_explosao(self):
        em, bus, _ = montar(ativo=True)
        matar(bus)
        assert len(em.explosive_effects) == 1
        efeito = em.explosive_effects[0]
        assert (efeito.x, efeito.y) == (CX, CY)
        assert efeito.damage == SHOCKWAVE_DAMAGE

    def test_morte_sem_upgrade_nao_cria_nada(self):
        em, bus, _ = montar(ativo=False)
        matar(bus)
        assert em.explosive_effects == []

    def test_cleanup_remove_o_handler(self):
        """§2: `bus.on` sem `off` é vazamento quando a cena morre — e o handler
        órfão continuaria criando explosões no EntityManager da partida velha."""
        em, bus, sistema = montar(ativo=True)
        sistema.cleanup()
        matar(bus)
        assert em.explosive_effects == []

    def test_a_onda_nasce_no_lugar_da_morte(self):
        em, bus, _ = montar(ativo=True)
        matar(bus, x=123.0, y=456.0)
        assert (em.explosive_effects[0].x, em.explosive_effects[0].y) == (123.0, 456.0)


# ---------------------------------------------------------------------------
# O teto — o que faz a cascata terminar
# ---------------------------------------------------------------------------


class TestTeto:
    def test_respeita_o_teto_de_ondas_vivas(self):
        em, bus, _ = montar(ativo=True)
        for _ in range(SHOCKWAVE_MAX_ACTIVE * 5):
            matar(bus)
        assert len(em.explosive_effects) == SHOCKWAVE_MAX_ACTIVE

    def test_o_teto_libera_quando_as_ondas_morrem(self):
        em, bus, _ = montar(ativo=True)
        for _ in range(SHOCKWAVE_MAX_ACTIVE):
            matar(bus)
        assert len(em.explosive_effects) == SHOCKWAVE_MAX_ACTIVE

        em.explosive_effects.clear()  # como o sweep do frame faria
        matar(bus)
        assert len(em.explosive_effects) == 1

    def test_o_teto_conta_a_lista_inteira_e_nao_so_as_ondas(self):
        """A lista é compartilhada com o tiro explosivo. O que se limita é o
        custo total de efeitos de área vivos, não a origem deles."""
        em, bus, _ = montar(ativo=True)
        for _ in range(SHOCKWAVE_MAX_ACTIVE):
            em.spawn_explosive_effect(0.0, 0.0)
        matar(bus)
        assert len(em.explosive_effects) == SHOCKWAVE_MAX_ACTIVE


# ---------------------------------------------------------------------------
# Limpeza de projéteis — o que o upgrade tem de único
# ---------------------------------------------------------------------------


class TestLimpezaDeProjeteis:
    @staticmethod
    def _com_projeteis(*posicoes):
        em, bus, sistema = montar(ativo=True)
        projeteis = [Projetil(x, y) for x, y in posicoes]
        em.alien_bullets.extend(projeteis)
        em.rebuild_all_grids()
        return em, bus, projeteis

    def test_apaga_os_projeteis_dentro_do_raio(self):
        em, bus, (perto,) = self._com_projeteis((CX + 10, CY + 10))
        matar(bus)
        assert perto.dead is True

    def test_nao_apaga_os_de_fora(self):
        em, bus, (longe,) = self._com_projeteis(
            (CX + SHOCKWAVE_RADIUS * 3, CY)
        )
        matar(bus)
        assert longe.dead is False

    def test_sem_upgrade_nenhum_projetil_e_apagado(self):
        em, bus, sistema = montar(ativo=False)
        proj = Projetil(CX + 5, CY + 5)
        em.alien_bullets.append(proj)
        em.rebuild_all_grids()
        matar(bus)
        assert proj.dead is False


class TestCascata:
    """A reação em cadeia real, pelo caminho de dano de verdade.

    Os testes de teto acima emitem o evento à mão. Este monta o ciclo completo:
    o passe de dano percorre `explosive_effects`, mata inimigos, cada morte
    emite `EnemyDestroyed`, e o handler ACRESCENTA outra onda à mesma lista que
    o passe está percorrendo. É aqui que a falta de teto viraria laço infinito
    dentro de um único frame — não um frame lento, um travamento.

    Detalhe que só apareceu ao montar isto: a onda nasce com raio de dano ZERO
    (`current_damage_radius` cresce a partir de `timer`, que começa em 0), então
    ela só machuca depois de ter sido atualizada ao menos uma vez. A cascata é
    ritmada por frame POR CONSTRUÇÃO: uma onda que nasce no meio do passe não
    mata ninguém naquele mesmo passe. O teto continua sendo a garantia dura — o
    raio zero é o que faz a cadeia se espalhar em vez de detonar de uma vez.
    """

    class Fragil:
        """Morre em qualquer acerto, como o meteoro real."""

        def __init__(self, x: float, y: float):
            self.x, self.y = float(x), float(y)
            self.w = self.h = 20
            self.dead = False

        @property
        def rect(self):
            return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        def collision_circle(self):
            return (self.x + 10, self.y + 10, 10)

        def on_hit(self, damage, hx, hy):
            from game.systems.hit_result import HitResult

            self.dead = True
            return HitResult(killed=True, points=5, explosion_size=0)

        def get_points_value(self):
            return 5

    def test_a_cascata_termina_e_respeita_o_teto(self):
        from game.systems.collisions import Collisions

        em = EntityManager()
        bus = EventBus()
        ShockwaveSystem(bus, em, is_active=lambda: True)
        col = Collisions(event_bus=bus)

        # Enxame colado: cada morte alcança os vizinhos.
        enxame = [
            self.Fragil(CX + i * 12.0, CY + j * 12.0)
            for i in range(6)
            for j in range(6)
        ]
        em.enemies = list(enxame)

        matar(bus)  # a primeira morte, que acende o rastilho
        assert em.explosive_effects, "a onda inicial não nasceu"

        # Frames de verdade: avança os efeitos (como `_update_visual_effects`) e
        # depois roda o passe de dano (como o orquestrador de colisão).
        dt = 1 / 60
        for _ in range(30):
            for efeito in em.explosive_effects:
                efeito.update(dt)
            em.explosive_effects = [e for e in em.explosive_effects if not e.dead]

            col.explosive_effects_vs_enemies(
                em.explosive_effects, [e for e in em.enemies if not e.dead], em
            )
            assert len(em.explosive_effects) <= SHOCKWAVE_MAX_ACTIVE, (
                "o teto não segurou: a lista cresceu dentro do próprio passe"
            )

        mortos = sum(1 for e in enxame if e.dead)
        assert mortos > 1, f"a cascata não encadeou (só {mortos} morto)"


# ---------------------------------------------------------------------------
# Boss
# ---------------------------------------------------------------------------


def test_boss_nao_gera_onda_porque_o_evento_nem_e_emitido():
    """Não é regra deste sistema: `CollisionPhysics.apply_hit` já filtra
    `is_boss` antes de emitir `EnemyDestroyed`. O teste trava o fato de o
    Shockwave DEPENDER desse filtro — se alguém o remover para outro fim, a
    onda passa a sair em peça de boss e isto aqui é o aviso.
    """
    import inspect

    from game.systems.collision_physics import CollisionPhysics

    fonte = inspect.getsource(CollisionPhysics.apply_hit)
    assert 'not getattr(target, "is_boss", False)' in fonte, (
        "o filtro de boss saiu da emissão de EnemyDestroyed: o Shockwave passa "
        "a explodir em peça de boss"
    )
