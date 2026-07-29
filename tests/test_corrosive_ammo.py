"""Upgrade Corrosive Ammo — pilha de ácido por acertos no MESMO inimigo.

A identidade é **alvo único e cumulativo**, e é ela que separa o Corrosive da
Implosão (área, sem escada) e do Cryo (controle, não dano). Se essa distinção
sumir, o certo é cortar um dos dois — não ajustar números.

O que estes testes guardam:

1. **a pilha sobe por acerto, até o teto, e mora no INIMIGO** — é o que faz P1 e
   P2 alimentarem a mesma pilha em coop e o que a mata junto com o alvo;
2. **o DPS não escala com a cadência de tiro** — o acumulador do tique é do
   alvo. Se alguém movê-lo para a nave ou para a bala, a Estrela (rápida) passa
   a ter um upgrade diferente do Aríete (lento), e nada mais avisaria;
3. **dano cresce com a pilha** — insistir no mesmo alvo é o upgrade inteiro;
4. **funciona em CHEFE** — é contra ele que existe. Só paga o nerf global;
5. **não vaza pelo pool** nem estoura em entidade com `__slots__`;
6. **o dano passa pelo roteador de colisão** (§8), nunca aplicado no update.
"""

import pygame
import pytest

from game.core.ship_types import get_ship_profile
from game.core.spatial_grid import SpatialGrid
from game.core.upgrades import (
    UPGRADES_META,
    UpgradeCategory,
    UpgradeType,
    get_upgrade_icon,
    upgrade_factory,
)
from game.core.upgrades_config import (
    CORROSIVE_DAMAGE_PER_STACK,
    CORROSIVE_DURATION,
    CORROSIVE_MAX_STACKS,
    CORROSIVE_TICK_INTERVAL,
    DEFAULT_UNLOCKED,
)
from game.entities._shared.control_marks import CONTROL_MARKS, clear_control_marks
from game.entities.player.ship import Ship
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager


class Bus:
    def emit(self, event):
        pass


class Alvo:
    """Inimigo mínimo: só precisa aceitar as marcas e responder ao guard."""

    def __init__(self):
        self.dead = False

    def collision_circle(self):
        return (100.0, 100.0, 15.0)


class InimigoReal:
    """Alvo com o contrato completo que o caminho de colisão exige."""

    def __init__(self, x: float, y: float, health: int = 999):
        self.x, self.y = float(x), float(y)
        self.w = self.h = 30
        self.dead = False
        self.health = health

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self):
        return (self.x + 15, self.y + 15, 15)

    def on_hit(self, damage, hx, hy):
        from game.systems.hit_result import HitResult

        self.health -= damage
        if self.health <= 0:
            self.dead = True
        return HitResult(killed=self.dead, points=0, explosion_size=0)

    def get_points_value(self):
        return 0


def corroer(alvo, vezes: int = 1, dono=None) -> None:
    col = Collisions(event_bus=Bus())
    for _ in range(vezes):
        col._apply_corrosion(alvo, dono)


def rodar(em: EntityManager, alvo, segundos: float, fps: float = 60.0) -> int:
    """Roda o relógio do ácido fora do jogo. Devolve o dano TOTAL enfileirado."""
    dt = 1.0 / fps
    total = 0
    for _ in range(int(round(segundos * fps))):
        em._tick_corrosion(alvo, dt)
        for _t, _cx, _cy, damage, _owner in em.take_corrosion_ticks():
            total += damage
    return total


def tempos_de_tique(janela: float, fps: float, pilha: int = 1) -> list[float]:
    """Instantes (s) em que o ácido tiquetaqueou. Janela dentro da duração."""
    em = EntityManager()
    alvo = Alvo()
    corroer(alvo, vezes=pilha)
    dt = 1.0 / fps
    t = 0.0
    tempos: list[float] = []
    for _ in range(int(round(janela * fps))):
        em._tick_corrosion(alvo, dt)
        t += dt
        if em.take_corrosion_ticks():
            tempos.append(t)
    return tempos


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
        up = upgrade_factory(UpgradeType.CORROSIVE_AMMO)
        assert up.meta.type is UpgradeType.CORROSIVE_AMMO

    def test_e_ofensivo(self):
        """O ácido não freia nem atrapalha ninguém: é dano ao longo do tempo."""
        meta = UPGRADES_META[UpgradeType.CORROSIVE_AMMO]
        assert meta.category is UpgradeCategory.OFFENSIVE

    def test_esta_desbloqueado_por_padrao(self):
        assert UpgradeType.CORROSIVE_AMMO in DEFAULT_UNLOCKED

    def test_tem_icone_proprio_no_hud(self):
        """Letra ausente no mapa cai no fallback do nome EM SILÊNCIO — foi assim
        que Canhão e Link mostraram 'C' os dois."""
        meta = UPGRADES_META[UpgradeType.CORROSIVE_AMMO]
        letra = get_upgrade_icon(meta.name, meta.icon_id)
        outras = {
            get_upgrade_icon(m.name, m.icon_id)
            for t, m in UPGRADES_META.items()
            if t is not UpgradeType.CORROSIVE_AMMO
        }
        assert letra not in outras, f"letra '{letra}' já usada"

    def test_descricao_traduzida_nos_dois_idiomas(self):
        from game.core.translations import TABLES

        for lang, tabela in TABLES.items():
            assert "upgrade.corrosive_ammo.desc" in tabela, lang

    def test_ativar_liga_o_timer_da_nave(self):
        ship = Ship(100, 100, profile=get_ship_profile("padrao"))
        assert ship.has_corrosive_ammo is False

        up = upgrade_factory(UpgradeType.CORROSIVE_AMMO)
        Ctx.ship = ship
        assert up.activate(Ctx()) is True
        assert ship.corrosive_timer == pytest.approx(up.meta.base_duration)

        ship._powerups.update_timers(up.meta.base_duration + 0.1)
        assert ship.has_corrosive_ammo is False


# ---------------------------------------------------------------------------
# A pilha
# ---------------------------------------------------------------------------


class TestPilha:
    def test_sobe_uma_carga_por_acerto(self):
        alvo = Alvo()
        for esperado in range(1, CORROSIVE_MAX_STACKS + 1):
            corroer(alvo)
            assert alvo.corrosive_stacks == esperado

    def test_nao_passa_do_teto(self):
        alvo = Alvo()
        corroer(alvo, vezes=20)
        assert alvo.corrosive_stacks == CORROSIVE_MAX_STACKS

    def test_a_pilha_mora_no_INIMIGO_e_nao_na_nave(self):
        a, b = Alvo(), Alvo()
        corroer(a, vezes=2)
        corroer(b, vezes=1)
        assert (a.corrosive_stacks, b.corrosive_stacks) == (2, 1)

    def test_a_duracao_e_reposta_e_nao_somada(self):
        """Somar deixaria um alvo muito castigado corroendo por meio minuto
        depois de o jogador já ter ido embora."""
        alvo = Alvo()
        corroer(alvo, vezes=5)
        assert alvo.corrosive_timer == pytest.approx(CORROSIVE_DURATION)

    def test_a_pilha_cai_INTEIRA_ao_expirar(self):
        em = EntityManager()
        alvo = Alvo()
        corroer(alvo, vezes=CORROSIVE_MAX_STACKS)
        rodar(em, alvo, CORROSIVE_DURATION + 0.5)
        assert alvo.corrosive_stacks == 0
        assert alvo.corrosive_timer == 0.0

    def test_a_pilha_sobrevive_enquanto_o_jogador_insiste(self):
        em = EntityManager()
        alvo = Alvo()
        corroer(alvo, vezes=CORROSIVE_MAX_STACKS)
        for _ in range(5):
            rodar(em, alvo, CORROSIVE_DURATION * 0.5)
            corroer(alvo)  # reacerto renova
        assert alvo.corrosive_stacks == CORROSIVE_MAX_STACKS


# ---------------------------------------------------------------------------
# O dano — e o que o mantém honesto
# ---------------------------------------------------------------------------


class TestDano:
    def test_o_dano_por_tique_cresce_com_a_pilha(self):
        """Insistir no mesmo alvo é o upgrade inteiro: a pilha cheia vale 3× a
        primeira carga."""
        for pilha in range(1, CORROSIVE_MAX_STACKS + 1):
            em = EntityManager()
            alvo = Alvo()
            corroer(alvo, vezes=pilha)
            # Uma janela de dois intervalos → dois tiques.
            total = rodar(em, alvo, CORROSIVE_TICK_INTERVAL * 2)
            assert total == pilha * CORROSIVE_DAMAGE_PER_STACK * 2

    def test_o_DPS_NAO_escala_com_a_cadencia_de_tiro(self):
        """O requisito central. O acumulador do tique mora no ALVO: reacertar
        renova a duração e sobe a pilha, mas nunca aperta os tiques.

        Se alguém mover o cooldown para a nave (ou reiniciá-lo no acerto), o
        jogador que atira 10× mais rápido passa a causar 10× mais DoT — e
        nenhum outro teste notaria.
        """
        janela = CORROSIVE_TICK_INTERVAL * 4

        em_calmo = EntityManager()
        calmo = Alvo()
        corroer(calmo, vezes=CORROSIVE_MAX_STACKS)
        dano_calmo = rodar(em_calmo, calmo, janela)

        # Mesma janela, mas metralhando o alvo a cada frame.
        em_rapido = EntityManager()
        rapido = Alvo()
        corroer(rapido, vezes=CORROSIVE_MAX_STACKS)
        dt = 1.0 / 60.0
        dano_rapido = 0
        for _ in range(int(round(janela * 60))):
            corroer(rapido)
            em_rapido._tick_corrosion(rapido, dt)
            for _t, _cx, _cy, damage, _owner in em_rapido.take_corrosion_ticks():
                dano_rapido += damage

        assert dano_rapido == dano_calmo, (
            f"metralhar rendeu {dano_rapido} contra {dano_calmo}: "
            "o acumulador do tique saiu do inimigo"
        )

    def test_o_periodo_medio_e_o_intervalo_configurado(self):
        """§14: reatribuir o intervalo cheio descarta a sobra do frame, o período
        real vira um número INTEIRO de frames e o DoT rende menos que o
        configurado — pouco, sistematicamente, e sem nada na tela denunciando.

        O invariante é o período MÉDIO, não a contagem: onde o primeiro tique
        cai depende de alinhamento sub-frame, mas o espaçamento entre eles não
        pode derivar. O fps é escolhido para o dt NÃO dividir o intervalo (45fps
        → 22,5 frames por tique); num fps que divide, os dois caminhos empatam e
        o teste não guardaria nada.
        """
        fps = 45.0
        assert (CORROSIVE_TICK_INTERVAL * fps) % 1.0 != 0.0, "fps não discrimina"

        tempos = tempos_de_tique(janela=3.5, fps=fps)
        assert len(tempos) >= 4, "poucos tiques para medir o período"

        gaps = [b - a for a, b in zip(tempos, tempos[1:])]
        medio = sum(gaps) / len(gaps)
        assert medio == pytest.approx(CORROSIVE_TICK_INTERVAL, abs=0.005), (
            f"período médio de {medio:.4f}s contra {CORROSIVE_TICK_INTERVAL}s "
            "configurados: a sobra do frame está sendo descartada"
        )

    def test_sem_pilha_nao_ha_tique(self):
        em = EntityManager()
        assert rodar(em, Alvo(), 5.0) == 0

    def test_o_dano_passa_pelo_roteador_de_colisao(self):
        """§8: o update ENFILEIRA, quem fere é o passe de colisão via `apply_hit`.
        Se alguém aplicar o dano direto no tick, escudo, som, pontuação e o
        evento de kill deixam de acontecer, e nada aqui falharia sem este teste.
        """
        em = EntityManager()
        alvo = InimigoReal(600.0, 300.0, health=100)
        em.enemies = [alvo]
        corroer(alvo, vezes=CORROSIVE_MAX_STACKS)

        em._tick_corrosion(alvo, CORROSIVE_TICK_INTERVAL)
        assert alvo.health == 100, "o tick feriu o alvo fora do roteador"
        assert len(em.corrosion_ticks) == 1

        Collisions(event_bus=Bus()).corrosion_vs_enemies(em)
        assert alvo.health == 100 - CORROSIVE_MAX_STACKS * CORROSIVE_DAMAGE_PER_STACK
        assert em.corrosion_ticks == [], "a fila não foi drenada"

    def test_a_fila_nunca_atravessa_o_frame(self):
        """Item que envelhece pode apontar para uma entidade que já voltou ao
        pool — e o dano cairia em quem herdou o slot."""
        em = EntityManager()
        alvo = Alvo()
        corroer(alvo, vezes=1)
        em._tick_corrosion(alvo, CORROSIVE_TICK_INTERVAL)
        assert em.corrosion_ticks

        em.update(1 / 60, 100.0, 100.0)
        assert em.corrosion_ticks == []

    def test_alvo_ja_morto_nao_leva_o_tique(self):
        em = EntityManager()
        alvo = InimigoReal(600.0, 300.0, health=100)
        corroer(alvo, vezes=1)
        em._tick_corrosion(alvo, CORROSIVE_TICK_INTERVAL)

        alvo.dead = True  # morreu para as balas do mesmo frame
        Collisions(event_bus=Bus()).corrosion_vs_enemies(em)
        assert alvo.health == 100


# ---------------------------------------------------------------------------
# Quem fica de dentro e quem fica de fora
# ---------------------------------------------------------------------------


class TestAlvos:
    def test_CHEFE_corroi(self):
        """É contra ele que o upgrade existe: alvo único, muita vida, muito
        tempo em tela. Excluí-lo apagaria o Corrosive inteiro."""
        boss = Alvo()
        boss.is_boss = True
        corroer(boss, vezes=CORROSIVE_MAX_STACKS)
        assert boss.corrosive_stacks == CORROSIVE_MAX_STACKS

    def test_chefe_paga_o_nerf_global_de_upgrade(self):
        from game.core.config import config as Config

        em = EntityManager()
        boss = InimigoReal(600.0, 300.0, health=999)
        boss.is_boss = True
        corroer(boss, vezes=CORROSIVE_MAX_STACKS)
        em._tick_corrosion(boss, CORROSIVE_TICK_INTERVAL)
        Collisions(event_bus=Bus()).corrosion_vs_enemies(em)

        cheio = CORROSIVE_MAX_STACKS * CORROSIVE_DAMAGE_PER_STACK
        esperado = max(1, int(cheio * Config.BOSS_UPGRADE_DAMAGE_MULTIPLIER))
        assert boss.health == 999 - esperado

    def test_position_locked_fica_fora(self):
        travado = Alvo()
        travado.position_locked = True
        corroer(travado, vezes=3)
        assert getattr(travado, "corrosive_stacks", 0) == 0

    def test_morto_fica_fora(self):
        morto = Alvo()
        morto.dead = True
        corroer(morto, vezes=3)
        assert getattr(morto, "corrosive_stacks", 0) == 0

    def test_entidade_com_slots_nao_derruba_o_jogo(self):
        """O crash real da Implosão, na versão Corrosive: escrever num
        `__slots__` que não declarou o campo estoura em pleno combate."""

        class PecaComSlots:
            __slots__ = ("dead",)

            def __init__(self):
                self.dead = False

        corroer(PecaComSlots(), vezes=3)  # não estoura

    def test_serpent_block_real_nao_derruba_o_jogo(self):
        from game.entities.bosses.mountain_serpent_boss import SerpentBlock

        bloco = SerpentBlock(x=600.0, y=300.0, side="left", boss=None, row_index=0)
        corroer(bloco, vezes=3)


# ---------------------------------------------------------------------------
# Resíduo entre vidas da entidade poolada
# ---------------------------------------------------------------------------


class TestPool:
    def test_as_marcas_estao_registradas_em_CONTROL_MARKS(self):
        """Sem isto a marca atravessa o pool de meteoro/RockGlider e o próximo
        spawn nasce corroendo — bug que só aparece em jogo, minutos depois."""
        for marca in (
            "corrosive_timer",
            "corrosive_stacks",
            "corrosive_damage_cd",
            "corrosive_owner",
        ):
            assert marca in CONTROL_MARKS, marca

    def test_limpar_marcas_zera_a_corrosao(self):
        alvo = Alvo()
        corroer(alvo, vezes=CORROSIVE_MAX_STACKS)
        clear_control_marks(alvo)
        assert alvo.corrosive_stacks == 0
        assert alvo.corrosive_timer == 0.0

    def test_meteoro_reciclado_nao_nasce_corroido(self):
        from game.entities.enemies.space.meteor_pool import MeteorPool

        pool = MeteorPool()
        m = pool.get(x=100.0, y=100.0)
        corroer(m, vezes=CORROSIVE_MAX_STACKS)
        pool.release(m)

        reciclado = pool.get(x=500.0, y=200.0)
        assert getattr(reciclado, "corrosive_stacks", 0) == 0
        assert getattr(reciclado, "corrosive_timer", 0.0) == 0.0


# ---------------------------------------------------------------------------
# A fiação: bala da nave → pilha no inimigo
# ---------------------------------------------------------------------------


class TestIntegracaoComOTiro:
    """Os testes acima chamam `_apply_corrosion` direto: provam a MECÂNICA, não
    a fiação. Esta classe é a que quebra se o gancho sair do lugar."""

    @staticmethod
    def cenario(*, com_upgrade: bool, alvos):
        em = EntityManager()
        em.enemies = list(alvos)

        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        if com_upgrade:
            ship.activate_corrosive_ammo(10.0)

        primeiro = alvos[0]
        bala = em.spawn_bullet(
            primeiro.x + 10,
            primeiro.y + 10,
            damage=5,
            piercing=len(alvos) > 1,
            owner_ship=ship,
        )
        grid: SpatialGrid = SpatialGrid(cell_size=200)
        for e in em.enemies:
            r = e.rect
            grid.insert(e, r.x, r.y, r.width, r.height)
        Collisions(event_bus=Bus()).projectiles_vs_enemies([bala], grid, em)
        return em

    def test_acerto_com_upgrade_empilha_acido(self):
        alvo = InimigoReal(600.0, 300.0)
        self.cenario(com_upgrade=True, alvos=[alvo])
        assert alvo.corrosive_stacks == 1
        assert alvo.corrosive_timer == pytest.approx(CORROSIVE_DURATION)

    def test_acerto_sem_upgrade_nao_corroi(self):
        alvo = InimigoReal(600.0, 300.0)
        self.cenario(com_upgrade=False, alvos=[alvo])
        assert getattr(alvo, "corrosive_stacks", 0) == 0

    def test_bala_perfurante_corroi_TODOS_que_atravessa(self):
        alvos = [
            InimigoReal(600.0, 300.0),
            InimigoReal(605.0, 302.0),
            InimigoReal(610.0, 304.0),
        ]
        self.cenario(com_upgrade=True, alvos=alvos)
        corroidos = [a for a in alvos if getattr(a, "corrosive_stacks", 0) == 1]
        assert len(corroidos) == len(alvos)

    def test_a_bala_do_pool_nao_nasce_corrosiva_por_residuo(self):
        """`reset()` que esquece um campo faz a próxima bala herdar o visual do
        disparo anterior — o bug que o Critical Core já pagou uma vez."""
        em = EntityManager()
        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        ship.activate_corrosive_ammo(10.0)
        primeira = em.spawn_bullet(10.0, 10.0, owner_ship=ship, corrosive=True)
        assert primeira.corrosive is True

        em.bullet_pool.release(primeira)
        segunda = em.spawn_bullet(10.0, 10.0, owner_ship=ship)
        assert segunda is primeira, "o teste não reusou a bala; pool mudou"
        assert segunda.corrosive is False


# ---------------------------------------------------------------------------
# Feedback visual
# ---------------------------------------------------------------------------


class TestBolhas:
    """O critério é VISIBILIDADE (pixels aparecem, e só quando devem), não o
    desenho exato, que é estética e vai mudar."""

    @staticmethod
    def _pintar(alvo) -> int:
        from game.entities.effects.corrosion_stain import draw_corroded

        canvas = pygame.Surface((300, 300))
        canvas.fill((0, 0, 0))
        draw_corroded(canvas, [alvo])
        return sum(
            1
            for x in range(0, 300, 2)
            for y in range(0, 300, 2)
            if canvas.get_at((x, y))[:3] != (0, 0, 0)
        )

    def test_o_inimigo_corroido_ganha_bolhas(self):
        alvo = InimigoReal(135.0, 135.0)
        corroer(alvo, vezes=1)
        assert self._pintar(alvo) > 0

    def test_sem_acido_nao_desenha_nada(self):
        assert self._pintar(InimigoReal(135.0, 135.0)) == 0

    def test_mais_cargas_mostram_mais_acido(self):
        """A pilha é a única decisão que o upgrade pede do jogador; ele precisa
        conseguir LER em quantas cargas o alvo está."""
        from game.entities.effects.corrosion_stain import bubble_count

        assert bubble_count(1) < bubble_count(CORROSIVE_MAX_STACKS)
        assert bubble_count(CORROSIVE_MAX_STACKS + 5) == bubble_count(
            CORROSIVE_MAX_STACKS
        ), "pilha acima do teto não pode desenhar mais"

    def test_o_acido_some_quando_a_pilha_cai(self):
        em = EntityManager()
        alvo = InimigoReal(135.0, 135.0)
        corroer(alvo, vezes=CORROSIVE_MAX_STACKS)
        rodar(em, alvo, CORROSIVE_DURATION + 0.5)
        assert self._pintar(alvo) == 0


# ---------------------------------------------------------------------------
# O projétil
# ---------------------------------------------------------------------------


class TestProjetil:
    """O tiro tem que se anunciar como ácido antes de acertar qualquer coisa."""

    @staticmethod
    def _bala(corrosive: bool, w: int = 12, h: int = 16):
        from game.entities.projectiles.bullet import Bullet

        b = Bullet(100.0, 100.0, corrosive=corrosive)
        b.w, b.h = w, h
        b.vx, b.vy = 0.0, -400.0
        return b

    @staticmethod
    def _pintar(bala) -> set:
        canvas = pygame.Surface((300, 300))
        canvas.fill((0, 0, 0))
        bala.draw(canvas)
        return {
            canvas.get_at((x, y))[:3]
            for x in range(0, 300)
            for y in range(0, 300)
            if canvas.get_at((x, y))[:3] != (0, 0, 0)
        }

    def test_o_projetil_e_MAIOR_que_o_comum(self):
        from game.core.upgrades_config import CORROSIVE_SHOT_SIZE_MULTIPLIER

        assert CORROSIVE_SHOT_SIZE_MULTIPLIER > 1.0

        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        normal = ship.bullet_size_multiplier
        ship.activate_corrosive_ammo(10.0)
        assert ship.bullet_size_multiplier > normal

    def test_o_tamanho_compoe_com_o_giant_shot(self):
        """Todo modificador de tamanho se compõe por multiplicação — nenhum
        caso especial por combinação."""
        from game.core.upgrades_config import (
            CORROSIVE_SHOT_SIZE_MULTIPLIER,
            GIANT_SHOT_SIZE_MULTIPLIER,
        )

        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        ship.activate_corrosive_ammo(10.0)
        ship.activate_giant_shots(10.0)
        assert ship.bullet_size_multiplier == pytest.approx(
            GIANT_SHOT_SIZE_MULTIPLIER * CORROSIVE_SHOT_SIZE_MULTIPLIER
        )

    def test_tem_sprite_proprio_e_nao_o_tiro_da_nave(self):
        cores_acido = self._pintar(self._bala(corrosive=True))
        cores_comum = self._pintar(self._bala(corrosive=False))
        assert cores_acido != cores_comum, "o tiro corrosivo desenha igual ao comum"

    def test_a_paleta_e_esverdeada_e_nao_saturada(self):
        """Verde musgo: o verde neon já é do teleguiado. Sem isso os dois tiros
        ficam indistinguíveis num combo."""
        from game.entities.projectiles.bullet import (
            _CORROSIVE_EDGE,
            _CORROSIVE_FILL,
            _CORROSIVE_PIT,
        )

        for cor in (_CORROSIVE_FILL, _CORROSIVE_EDGE, _CORROSIVE_PIT):
            r, g, b = cor
            assert g > r and g > b, f"{cor} não é predominantemente verde"
            assert g < 255, f"{cor} está no verde puro (neon)"

    def test_o_sprite_tem_poco_escuro_e_brilho(self):
        """Os dois detalhes que fazem a bolha ler como ácido e não como cápsula:
        o poço (o ácido comendo a gota) e o brilho úmido."""
        from game.entities.projectiles.bullet import _get_corrosive_bullet_surface

        surf = _get_corrosive_bullet_surface(14, 18, 0)
        cores = {
            surf.get_at((x, y))[:3]
            for x in range(14)
            for y in range(18)
            if surf.get_at((x, y))[3] > 0
        }
        # Corpo, contorno, poço e brilho: quatro tons distintos no mínimo.
        assert len(cores) >= 4, f"sprite chapado demais: {cores}"
        claros = [c for c in cores if sum(c) > 450]
        escuros = [c for c in cores if sum(c) < 220]
        assert claros, "sem brilho úmido"
        assert escuros, "sem poço de corrosão"

    def test_o_sprite_minusculo_nao_some(self):
        """O Estilete tem 2px de largura: a receita de elipse+poço não cabe, e
        sem o caminho degradado o tiro vira uma mancha invisível."""
        from game.entities.projectiles.bullet import _get_corrosive_bullet_surface

        surf = _get_corrosive_bullet_surface(2, 3, 0)
        visiveis = sum(
            1 for x in range(2) for y in range(3) if surf.get_at((x, y))[3] > 0
        )
        assert visiveis == 6, "o tiro minúsculo ficou vazado"

    def test_o_sprite_e_memoizado(self):
        """Um `Surface` por bala por frame seria alocação no hot path (§7)."""
        from game.entities.projectiles.bullet import _get_corrosive_bullet_surface

        a = _get_corrosive_bullet_surface(12, 16, 0)
        b = _get_corrosive_bullet_surface(12, 16, 0)
        assert a is b

    def test_deixa_rastro_de_pingos(self):
        """O rastro é o que comunica 'líquido' durante o deslocamento."""
        parada = self._bala(corrosive=True)
        parada.vx = parada.vy = 0.0
        andando = self._bala(corrosive=True)

        canvas_p = pygame.Surface((300, 300))
        canvas_p.fill((0, 0, 0))
        parada.draw(canvas_p)
        canvas_a = pygame.Surface((300, 300))
        canvas_a.fill((0, 0, 0))
        andando.draw(canvas_a)

        def pintados(c):
            return sum(
                1
                for x in range(300)
                for y in range(300)
                if c.get_at((x, y))[:3] != (0, 0, 0)
            )

        assert pintados(canvas_a) > pintados(canvas_p)

    def test_o_gelo_tem_prioridade_no_corpo_do_tiro(self):
        """Decisão registrada: com Cryo + Corrosive o corpo é o cristal (o gelo
        comunica mecânica de controle), e o ácido segue visível no INIMIGO."""
        combinada = self._bala(corrosive=True)
        combinada.cryo = True
        so_gelo = self._bala(corrosive=False)
        so_gelo.cryo = True
        assert self._pintar(combinada) == self._pintar(so_gelo)
