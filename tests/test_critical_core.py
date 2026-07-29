"""Upgrade Critical Core — chance de cada bala sair crítica.

Entrega chapada por decisão: chance × multiplicador, sem perfurar nem explodir
no crítico. A "melhoria" que dá identidade a ele fica para depois de jogar.

O que estes testes guardam, em ordem de importância:

1. **a rolagem é por BALA, não por salva** — é a decisão de design do upgrade, e
   a que some sem ninguém perceber se alguém "otimizar" o sorteio para fora da
   compreensão do `bullet_spawn`;
2. **a bala do pool não herda o crítico** — o modo de falha desta base de código
   (ver `control_marks` e o resíduo da Implosão): campo novo não reescrito no
   `reset()` vaza para a próxima vida do objeto;
3. **o produto chance × multiplicador**, que é o que realmente define a força do
   upgrade — mexer em um dos dois isolado muda a força sem parecer que mudou.
"""

import random

import pytest

from game.core.ship_types import get_ship_profile
from game.core.upgrades import (
    UPGRADES_META,
    UpgradeCategory,
    UpgradeType,
    get_upgrade_icon,
    upgrade_factory,
)
from game.core.upgrades_config import (
    CRITICAL_CORE_CHANCE,
    CRITICAL_CORE_IMPACT_SCALE,
    CRITICAL_CORE_MULTIPLIER,
    DEFAULT_UNLOCKED,
)
from game.entities._shared.impact_styles import impact_scale_for_projectile
from game.entities.player.ship import Ship
from game.systems.entity_manager import EntityManager
from game.systems.shooting_system import ShootingSystem


class Bus:
    def emit(self, event):
        pass


def nave(crit: bool = False, **kw) -> Ship:
    ship = Ship(600.0, 400.0, profile=get_ship_profile("padrao"), **kw)
    if crit:
        ship.activate_critical_core(10.0)
    return ship


def rolar(ship: Ship, salvas: int = 400) -> list[list[bool]]:
    """Devolve o flag `critical` de cada bala, agrupado por salva."""
    return [[spec.critical for spec in ship.bullet_spawn()] for _ in range(salvas)]


class Ctx:
    """Contexto mínimo do `activate` (mesma forma dos outros testes)."""

    entity_manager = None
    difficulty_settings: dict = {}
    sound_manager = None
    god_mode = False
    scene = None


# ---------------------------------------------------------------------------
# Registro do upgrade
# ---------------------------------------------------------------------------


class TestRegistro:
    def test_e_construivel(self):
        assert upgrade_factory(UpgradeType.CRITICAL_CORE).meta.type is (
            UpgradeType.CRITICAL_CORE
        )

    def test_e_ofensivo(self):
        """Dano puro, sem nenhum efeito de controle — não é UTILITY."""
        assert (
            UPGRADES_META[UpgradeType.CRITICAL_CORE].category
            is UpgradeCategory.OFFENSIVE
        )

    def test_esta_desbloqueado_por_padrao(self):
        assert UpgradeType.CRITICAL_CORE in DEFAULT_UNLOCKED

    def test_tem_icone_proprio_no_hud(self):
        """Letra fora do mapa cai no fallback do nome EM SILÊNCIO — foi assim
        que Torre de Canhão e Link mostraram 'C' os dois."""
        meta = UPGRADES_META[UpgradeType.CRITICAL_CORE]
        letra = get_upgrade_icon(meta.name, meta.icon_id)
        outras = {
            get_upgrade_icon(m.name, m.icon_id)
            for t, m in UPGRADES_META.items()
            if t is not UpgradeType.CRITICAL_CORE
        }
        assert letra not in outras, f"letra '{letra}' já usada"

    def test_descricao_traduzida_nos_dois_idiomas(self):
        from game.core.translations import TABLES

        for lang, tabela in TABLES.items():
            assert "upgrade.critical_core.desc" in tabela, lang

    def test_ativar_liga_o_timer_da_nave(self):
        ship = nave()
        assert ship.has_critical_core is False

        up = upgrade_factory(UpgradeType.CRITICAL_CORE)
        Ctx.ship = ship
        assert up.activate(Ctx()) is True
        assert ship.critical_core_timer == pytest.approx(up.meta.base_duration)

        ship._powerups.update_timers(up.meta.base_duration + 0.1)
        assert ship.has_critical_core is False


# ---------------------------------------------------------------------------
# A rolagem
# ---------------------------------------------------------------------------


class TestRolagem:
    def test_sem_o_upgrade_nenhuma_bala_crita(self):
        assert not any(any(salva) for salva in rolar(nave(), salvas=500))

    def test_com_o_upgrade_a_frequencia_bate_a_chance(self):
        random.seed(20260728)
        balas = [c for salva in rolar(nave(crit=True), salvas=2000) for c in salva]
        medido = sum(balas) / len(balas)
        assert medido == pytest.approx(CRITICAL_CORE_CHANCE, abs=0.03), (
            f"{medido:.3f} de críticos contra {CRITICAL_CORE_CHANCE} pedidos"
        )

    def test_a_rolagem_e_POR_BALA_e_nao_por_salva(self):
        """A decisão de design do upgrade.

        Com o leque, uma salva de 5 balas tem que poder sair MISTA. Se o sorteio
        subisse para o disparo, toda salva seria 5 críticos ou 5 normais — um
        evento raro e mudo, em vez da cintilação contínua que mostra ao jogador
        que o upgrade está ativo.
        """
        random.seed(1234)
        ship = nave(crit=True)
        ship.spread_shot_timer = 10.0  # leque: 5 balas por salva

        salvas = rolar(ship, salvas=300)
        assert all(len(s) == 5 for s in salvas), "premissa: o leque saiu com 5 balas"
        assert any(0 < sum(s) < len(s) for s in salvas), (
            "nenhuma salva mista: o sorteio virou por disparo"
        )

    def test_cada_bala_sorteia_sozinha_mesmo_sem_leque(self):
        """Sem leque a salva tem 1 bala, então a prova é ao longo do tempo:
        algumas puxadas critam e outras não."""
        random.seed(99)
        salvas = rolar(nave(crit=True), salvas=200)
        criticas = sum(1 for s in salvas if s[0])
        assert 0 < criticas < len(salvas)


# ---------------------------------------------------------------------------
# O dano
# ---------------------------------------------------------------------------


class TestDano:
    @staticmethod
    def _disparar(ship: Ship) -> list:
        em = EntityManager()
        ShootingSystem(em, Bus()).fire(ship, player_damage_multiplier=1.0)
        return list(em.bullets)

    def _primeira_critica(self, ship: Ship, tentativas: int = 200):
        """Dispara até sair uma bala crítica. LIMITADO de propósito.

        Um `while` sem teto aqui trava a suíte inteira em vez de falhar quando o
        crítico para de acontecer — que é exatamente o cenário que estes testes
        existem para pegar. Com 200 tentativas a 25%, a chance de um falso
        negativo é ~1e-25.
        """
        for _ in range(tentativas):
            for bala in self._disparar(ship):
                if bala.critical:
                    return bala
        pytest.fail(f"nenhuma bala crítica em {tentativas} disparos")

    def test_critico_multiplica_o_dano_da_bala(self):
        base = self._disparar(nave())
        assert base and all(not b.critical for b in base)
        dano_normal = base[0].damage

        random.seed(7)
        critica = self._primeira_critica(nave(crit=True))

        assert critica.damage == round(dano_normal * CRITICAL_CORE_MULTIPLIER)
        assert critica.damage > dano_normal

    def test_a_bala_carrega_a_marca_de_critico(self):
        """A flag existe para o IMPACTO, não para recalcular dano: o `damage` da
        bala já vem multiplicado. Se alguém multiplicar de novo lendo a flag no
        sistema de colisão, o crítico vira 6,25×."""
        random.seed(7)
        assert self._primeira_critica(nave(crit=True)).critical is True

    def test_o_produto_chance_x_multiplicador_fica_na_faixa(self):
        """Invariante de balanceamento (§16): faixa, não número exato.

        O que define a força do upgrade é o dano médio enquanto ativo,
        `1 + chance × (mult - 1)`. Mexer só na chance ou só no multiplicador
        muda essa força sem que a mudança pareça grande no diff.
        """
        medio = 1.0 + CRITICAL_CORE_CHANCE * (CRITICAL_CORE_MULTIPLIER - 1.0)
        assert 1.25 <= medio <= 1.60, f"dano médio {medio:.3f}× fora da faixa"

    def test_o_critico_e_raro_e_grande_e_nao_frequente_e_pequeno(self):
        """A repartição é o que dá o pico perceptível. Um crítico de 1,2× em
        80% das balas daria o mesmo dano médio e não se leria como nada."""
        assert CRITICAL_CORE_CHANCE <= 0.35
        assert CRITICAL_CORE_MULTIPLIER >= 2.0


# ---------------------------------------------------------------------------
# Resíduo no pool
# ---------------------------------------------------------------------------


class TestSemResiduoNoPool:
    def test_bala_reciclada_nao_nasce_critica(self):
        """O modo de falha desta base de código: campo novo que o `reset()` não
        reescreve fica na bala e vaza para o próximo disparo — que sairia com
        impacto de crítico sem ter critado."""
        em = EntityManager()
        antiga = em.spawn_bullet(100.0, 100.0, critical=True)
        assert antiga.critical is True

        antiga.dead = True
        em.cleanup()
        nova = em.spawn_bullet(200.0, 200.0)

        assert nova is antiga, "premissa: o pool devolveu o mesmo objeto"
        assert nova.critical is False


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


class TestFeedback:
    def test_o_impacto_do_critico_e_maior(self):
        """Um dos dois feedbacks do upgrade (o outro é a cor do score)."""
        em = EntityManager()
        normal = em.spawn_bullet(100.0, 100.0)
        critica = em.spawn_bullet(100.0, 100.0, critical=True)

        assert impact_scale_for_projectile(critica) == pytest.approx(
            impact_scale_for_projectile(normal) * CRITICAL_CORE_IMPACT_SCALE
        )

    def test_projetil_sem_a_flag_nao_quebra(self):
        """Nem todo projétil é `Bullet` (laser do Magneto, teleguiado do
        Caçador). Quem não tem a flag segue na escala de sempre."""

        class ProjetilQualquer:
            size_multiplier = 1.0

        assert impact_scale_for_projectile(ProjetilQualquer()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# A cor do score — o feedback do abate
# ---------------------------------------------------------------------------


class TestCorDoScore:
    """Abate crítico pinta o número flutuante de vermelho.

    O impacto aumentado só se vê em hit NÃO-letal (é a regra do
    `impact_styles`): no abate ele dá lugar à explosão de morte do inimigo.
    Ou seja, o crítico que MATA — o mais satisfatório — era o único que não
    aparecia. A cor do número cobre exatamente esse buraco.

    O que estes testes travam é a fiação (a marca sai da bala que matou e chega
    à cor), não o tom exato do vermelho, que é estética e pode mudar.
    """

    @staticmethod
    def _abater(*, critical: bool):
        """Mata um inimigo com uma bala pelo caminho real de colisão."""
        import pygame

        from game.core.spatial_grid import SpatialGrid
        from game.systems.collisions import Collisions
        from game.systems.hit_result import HitResult

        class Alvo:
            def __init__(self):
                self.x, self.y = 600.0, 300.0
                self.w = self.h = 30
                self.dead = False
                self.health = 1

            @property
            def rect(self):
                return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

            def collision_circle(self):
                return (self.x + 15, self.y + 15, 15)

            def on_hit(self, damage, hx, hy):
                self.dead = True
                return HitResult(killed=True, points=100, explosion_size=0)

            def get_points_value(self):
                return 100

        em = EntityManager()
        alvo = Alvo()
        em.enemies = [alvo]
        bala = em.spawn_bullet(alvo.x + 10, alvo.y + 10, damage=50, critical=critical)

        grid: SpatialGrid = SpatialGrid(cell_size=200)
        r = alvo.rect
        grid.insert(alvo, r.x, r.y, r.width, r.height)
        _, _, eventos = Collisions(event_bus=Bus()).projectiles_vs_enemies(
            [bala], grid, em
        )
        assert eventos, "premissa: o abate gerou um score event"
        return eventos[0]

    def test_abate_critico_marca_o_evento(self):
        assert self._abater(critical=True).critical is True

    def test_abate_comum_nao_marca(self):
        assert self._abater(critical=False).critical is False

    def test_a_marca_vira_vermelho_e_o_resto_amarelo(self):
        from game.entities.effects.floating_score import (
            COMBAT_COLOR,
            CRITICAL_COLOR,
            score_color,
        )

        assert score_color(True) == CRITICAL_COLOR
        assert score_color(False) == COMBAT_COLOR
        assert CRITICAL_COLOR != COMBAT_COLOR

    def test_o_vermelho_do_critico_e_legivel(self):
        """O número é pequeno e fica sobre explosões laranja. Vermelho escuro
        ou puro some ali — o tom precisa de brilho e de dominância clara."""
        from game.entities.effects.floating_score import CRITICAL_COLOR

        r, g, b = CRITICAL_COLOR
        assert r >= 220, "vermelho apagado demais para ler sobre explosão"
        assert r - max(g, b) >= 100, "sem dominância de vermelho: lê como branco"

    def test_a_animacao_do_score_nao_muda_com_a_cor(self):
        """Só a COR muda. Se o crítico ganhasse vida/velocidade própria, dois
        números lado a lado sairiam dessincronizados e o efeito viraria ruído."""
        from game.entities.effects.floating_score import (
            COMBAT_COLOR,
            CRITICAL_COLOR,
            FloatingScore,
        )

        comum = FloatingScore(10.0, 20.0, 100, COMBAT_COLOR)
        critico = FloatingScore(10.0, 20.0, 100, CRITICAL_COLOR)
        for _ in range(10):
            comum.update()
            critico.update()

        assert (comum.y, comum.alpha, comum.lifetime) == (
            critico.y,
            critico.alpha,
            critico.lifetime,
        )
