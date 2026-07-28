"""Upgrade Cryo Shot — escada de lentidão por acertos no MESMO inimigo.

25% → 50% → 75% mais lento, e o nível inteiro cai se o jogador soltar o alvo.
Entregue sem o 4º nível (congelar): parar um inimigo dessincroniza padrões
roteirizados e peças coreografadas de boss — a mesma classe de bug que derrubou
o puxão da Implosão.

O que estes testes guardam:

1. **a escada sobe por acerto e o nível mora no INIMIGO** — é o que faz P1 e P2
   alimentarem a mesma escada em coop, e o que faz o nível morrer com o alvo;
2. **a queda é TOTAL** — soltar o alvo custa o nível inteiro. Se alguém trocar
   por decaimento degrau a degrau, o upgrade deixa de ser condicional e vira
   bônus permanente com atraso, que é justamente o que o separa da Implosão;
3. **compõe por multiplicação** com EMP/gelo/vórtice/implosão, em vez de
   disputar o mesmo campo;
4. **não vaza pelo pool** nem estoura em entidade com `__slots__`.
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
    CRYO_CRYSTAL_FADE,
    CRYO_FREEZE_DURATION,
    CRYO_MAX_STACKS,
    CRYO_SLOW_DURATION,
    CRYO_SLOW_STEPS,
    DEFAULT_UNLOCKED,
)
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


class InimigoReal:
    """Alvo com o contrato completo que o caminho de colisão exige."""

    def __init__(self, x: float, y: float):
        self.x, self.y = float(x), float(y)
        self.w = self.h = 30
        self.dead = False
        self.health = 999

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self):
        return (self.x + 15, self.y + 15, 15)

    def on_hit(self, damage, hx, hy):
        from game.systems.hit_result import HitResult

        self.health -= damage
        return HitResult(killed=False, points=0, explosion_size=0)

    def get_points_value(self):
        return 0


def gelar(alvo, vezes: int = 1) -> None:
    col = Collisions(event_bus=Bus())
    for _ in range(vezes):
        col._apply_cryo(alvo)


def passar_tempo(alvo, segundos: float, fps: float = 60.0) -> None:
    dt = 1.0 / fps
    for _ in range(int(segundos * fps)):
        EntityManager._update_cryo_linger(alvo, dt)


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
        assert upgrade_factory(UpgradeType.CRYO_SHOT).meta.type is UpgradeType.CRYO_SHOT

    def test_e_utilitario(self):
        """Não soma dano: o valor é controle, como a Implosão."""
        assert (
            UPGRADES_META[UpgradeType.CRYO_SHOT].category is UpgradeCategory.UTILITY
        )

    def test_esta_desbloqueado_por_padrao(self):
        assert UpgradeType.CRYO_SHOT in DEFAULT_UNLOCKED

    def test_tem_icone_proprio_no_hud(self):
        meta = UPGRADES_META[UpgradeType.CRYO_SHOT]
        letra = get_upgrade_icon(meta.name, meta.icon_id)
        outras = {
            get_upgrade_icon(m.name, m.icon_id)
            for t, m in UPGRADES_META.items()
            if t is not UpgradeType.CRYO_SHOT
        }
        assert letra not in outras, f"letra '{letra}' já usada"

    def test_descricao_traduzida_nos_dois_idiomas(self):
        from game.core.translations import TABLES

        for lang, tabela in TABLES.items():
            assert "upgrade.cryo_shot.desc" in tabela, lang

    def test_ativar_liga_o_timer_da_nave(self):
        ship = Ship(100, 100, profile=get_ship_profile("padrao"))
        assert ship.has_cryo_shot is False

        up = upgrade_factory(UpgradeType.CRYO_SHOT)
        Ctx.ship = ship
        assert up.activate(Ctx()) is True
        assert ship.cryo_shot_timer == pytest.approx(up.meta.base_duration)

        ship._powerups.update_timers(up.meta.base_duration + 0.1)
        assert ship.has_cryo_shot is False


# ---------------------------------------------------------------------------
# A escada
# ---------------------------------------------------------------------------


class TestEscada:
    def test_sobe_um_degrau_por_acerto(self):
        alvo = Alvo()
        for esperado, fator in enumerate(CRYO_SLOW_STEPS, start=1):
            gelar(alvo)
            assert alvo.cryo_stacks == esperado
            assert EntityManager._cryo_multiplier(alvo) == fator

    def test_os_degraus_sao_25_50_75_por_cento(self):
        """O que o upgrade promete na descrição."""
        assert CRYO_SLOW_STEPS == (0.75, 0.50, 0.25)

    def test_nao_passa_do_teto(self):
        alvo = Alvo()
        gelar(alvo, vezes=20)
        assert alvo.cryo_stacks == CRYO_MAX_STACKS
        assert EntityManager._cryo_multiplier(alvo) == CRYO_SLOW_STEPS[-1]

    def test_sem_marca_nao_ha_penalidade(self):
        assert EntityManager._cryo_multiplier(Alvo()) == 1.0

    def test_o_nivel_mora_no_INIMIGO_e_nao_na_nave(self):
        """É o que faz P1 e P2 alimentarem a mesma escada em coop — e o que faz
        o nível morrer junto com o alvo em vez de sobreviver a ele."""
        a, b = Alvo(), Alvo()
        gelar(a, vezes=2)
        gelar(b, vezes=1)
        assert (a.cryo_stacks, b.cryo_stacks) == (2, 1)


# ---------------------------------------------------------------------------
# A queda — a identidade do upgrade
# ---------------------------------------------------------------------------


class TestQueda:
    def test_o_nivel_sobrevive_enquanto_o_jogador_insiste(self):
        alvo = Alvo()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        for _ in range(5):
            passar_tempo(alvo, CRYO_FREEZE_DURATION * 0.5)
            gelar(alvo)  # reacerto renova
        assert alvo.cryo_stacks == CRYO_MAX_STACKS

    def test_a_escada_cai_INTEIRA_ao_expirar(self):
        """Não degrau a degrau. Escada que desce sozinha vira um número que o
        jogador não consegue ler na tela; 'gelado' ou 'não gelado' ele lê."""
        alvo = Alvo()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.5)

        assert alvo.cryo_stacks == 0
        assert alvo.cryo_slow_timer == 0.0
        assert EntityManager._cryo_multiplier(alvo) == 1.0

    def test_trocar_de_alvo_custa_o_nivel(self):
        """O requisito central: o upgrade é CONDICIONAL."""
        antigo, novo = Alvo(), Alvo()
        gelar(antigo, vezes=CRYO_MAX_STACKS)

        # O jogador passa a atirar no outro pelo tempo da duração.
        for _ in range(CRYO_MAX_STACKS):
            gelar(novo)
        passar_tempo(antigo, CRYO_FREEZE_DURATION + 0.1)

        assert EntityManager._cryo_multiplier(antigo) == 1.0
        assert novo.cryo_stacks == CRYO_MAX_STACKS

    def test_a_duracao_e_reposta_e_nao_somada(self):
        alvo = Alvo()
        gelar(alvo, vezes=5)
        assert alvo.cryo_slow_timer == pytest.approx(CRYO_FREEZE_DURATION)

    def test_o_congelamento_dura_5s_e_os_degraus_de_baixo_menos(self):
        """O topo da escada é o estágio CONGELADO e vale mais tempo — é a
        recompensa por ter mantido a pressão nos três acertos."""
        assert CRYO_FREEZE_DURATION == 5.0
        assert CRYO_FREEZE_DURATION > CRYO_SLOW_DURATION

        meio = Alvo()
        gelar(meio, vezes=CRYO_MAX_STACKS - 1)
        assert meio.cryo_slow_timer == pytest.approx(CRYO_SLOW_DURATION)

        cheio = Alvo()
        gelar(cheio, vezes=CRYO_MAX_STACKS)
        assert cheio.cryo_slow_timer == pytest.approx(CRYO_FREEZE_DURATION)


# ---------------------------------------------------------------------------
# Convivência com os outros controles
# ---------------------------------------------------------------------------


class TestComposicao:
    def test_compoe_por_multiplicacao_com_os_outros_slows(self):
        """Se o Cryo escrevesse velocidade direto, o último a marcar apagaria os
        outros. Todos são marcas lidas como multiplicador no tick."""
        from game.core.upgrades_config import IMPLOSION_SLOW_FACTOR

        alvo = Alvo()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        alvo.implosion_slow_timer = 5.0

        combinado = EntityManager._cryo_multiplier(
            alvo
        ) * EntityManager._implosion_multiplier(alvo)
        assert combinado == pytest.approx(CRYO_SLOW_STEPS[-1] * IMPLOSION_SLOW_FACTOR)
        assert combinado < CRYO_SLOW_STEPS[-1]


# ---------------------------------------------------------------------------
# Quem fica de fora
# ---------------------------------------------------------------------------


class TestOptOuts:
    def test_boss_fica_fora(self):
        boss = Alvo()
        boss.is_boss = True
        gelar(boss, vezes=3)
        assert getattr(boss, "cryo_stacks", 0) == 0

    def test_position_locked_fica_fora(self):
        travado = Alvo()
        travado.position_locked = True
        gelar(travado, vezes=3)
        assert getattr(travado, "cryo_stacks", 0) == 0

    def test_morto_fica_fora(self):
        morto = Alvo()
        morto.dead = True
        gelar(morto, vezes=3)
        assert getattr(morto, "cryo_stacks", 0) == 0

    def test_entidade_com_slots_nao_derruba_o_jogo(self):
        """O crash real da Implosão, na versão Cryo: escrever num `__slots__`
        que não declarou o campo estoura AttributeError em pleno combate."""

        class PecaComSlots:
            __slots__ = ("dead",)

            def __init__(self):
                self.dead = False

        gelar(PecaComSlots(), vezes=3)  # não estoura

    def test_serpent_block_real_nao_derruba_o_jogo(self):
        from game.entities.bosses.mountain_serpent_boss import SerpentBlock

        bloco = SerpentBlock(x=600.0, y=300.0, side="left", boss=None, row_index=0)
        gelar(bloco, vezes=3)


# ---------------------------------------------------------------------------
# Resíduo entre ativações
# ---------------------------------------------------------------------------


class TestIntegracaoComOTiro:
    """O caminho real: bala da nave acerta o inimigo → escada sobe.

    Os testes acima chamam `_apply_cryo` direto, então provam a MECÂNICA mas não
    a fiação. Esta classe é a que quebra se o gancho no `projectiles_vs_enemies`
    sair do lugar.
    """

    @staticmethod
    def cenario(*, com_upgrade: bool, alvos):
        em = EntityManager()
        em.enemies = list(alvos)

        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        if com_upgrade:
            ship.activate_cryo_shots(10.0)

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

    def test_acerto_com_upgrade_sobe_a_escada(self):
        alvo = InimigoReal(600.0, 300.0)
        self.cenario(com_upgrade=True, alvos=[alvo])
        assert alvo.cryo_stacks == 1
        assert EntityManager._cryo_multiplier(alvo) == CRYO_SLOW_STEPS[0]

    def test_acerto_sem_upgrade_nao_gela(self):
        alvo = InimigoReal(600.0, 300.0)
        self.cenario(com_upgrade=False, alvos=[alvo])
        assert getattr(alvo, "cryo_stacks", 0) == 0

    def test_bala_perfurante_gela_TODOS_que_atravessa(self):
        """Decisão registrada no código: diferente da Implosão e da cadeia — que
        travam em UMA por bala para não duplicar efeito no mundo —, o Cryo marca
        cada alvo. Alinhar inimigos é o prêmio de mirar bem.
        """
        alvos = [
            InimigoReal(600.0, 300.0),
            InimigoReal(605.0, 302.0),
            InimigoReal(610.0, 304.0),
        ]
        self.cenario(com_upgrade=True, alvos=alvos)

        gelados = [a for a in alvos if getattr(a, "cryo_stacks", 0) == 1]
        assert len(gelados) == len(alvos), (
            f"só {len(gelados)} de {len(alvos)} gelaram: "
            "a marca virou 'uma por bala'"
        )


class TestCristaisDeGelo:
    """O feedback visual do estágio congelado.

    O critério do pedido é "identificar instantaneamente" — então o que estes
    testes travam é a VISIBILIDADE (pixels de gelo aparecem, e só quando devem),
    não o desenho exato, que é estética e vai mudar.
    """

    @staticmethod
    def _pintar(alvo) -> int:
        """Desenha num canvas preto e devolve quantos pixels deixaram de ser."""
        from game.entities.effects.cryo_crystals import draw_frozen

        canvas = pygame.Surface((300, 300))
        canvas.fill((0, 0, 0))
        draw_frozen(canvas, [alvo])
        return sum(
            1
            for x in range(0, 300, 2)
            for y in range(0, 300, 2)
            if canvas.get_at((x, y))[:3] != (0, 0, 0)
        )

    @staticmethod
    def _alvo_no_centro():
        alvo = InimigoReal(135.0, 135.0)
        return alvo

    def test_o_inimigo_congelado_ganha_cristais(self):
        alvo = self._alvo_no_centro()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        assert self._pintar(alvo) > 0, "nada foi desenhado no inimigo congelado"

    def test_degraus_intermediarios_NAO_ganham_cristais(self):
        """Os cristais marcam o estágio congelado — se aparecessem no primeiro
        acerto, deixariam de distinguir coisa alguma."""
        for acertos in range(1, CRYO_MAX_STACKS):
            alvo = self._alvo_no_centro()
            gelar(alvo, vezes=acertos)
            assert self._pintar(alvo) == 0, f"cristais apareceram com {acertos} acerto(s)"

    def test_sem_gelo_nao_desenha_nada(self):
        assert self._pintar(self._alvo_no_centro()) == 0

    def test_o_gelo_some_quando_o_congelamento_acaba(self):
        alvo = self._alvo_no_centro()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.5)
        assert self._pintar(alvo) == 0

    def test_o_gelo_nao_cobre_o_centro_do_inimigo(self):
        """'sem esconder completamente seu sprite': o miolo tem que continuar
        visível, senão o jogador perde de vista o que está congelado."""
        from game.entities.effects.cryo_crystals import draw_frozen

        alvo = self._alvo_no_centro()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        cx, cy, _ = alvo.collision_circle()

        canvas = pygame.Surface((300, 300))
        canvas.fill((0, 0, 0))
        draw_frozen(canvas, [alvo])
        assert canvas.get_at((int(cx), int(cy)))[:3] == (0, 0, 0), (
            "o centro do inimigo foi coberto pelo gelo"
        )

    def test_a_forma_e_estavel_entre_frames(self):
        """Cristal que se redesenha diferente a cada frame vira ruído piscando.
        A forma sai do `id()` do inimigo, então é a mesma enquanto ele viver."""
        from game.entities.effects.cryo_crystals import draw_frozen

        alvo = self._alvo_no_centro()
        gelar(alvo, vezes=CRYO_MAX_STACKS)

        quadros = []
        for _ in range(2):
            canvas = pygame.Surface((300, 300))
            canvas.fill((0, 0, 0))
            draw_frozen(canvas, [alvo])
            quadros.append(pygame.image.tostring(canvas, "RGB"))
        assert quadros[0] == quadros[1]

    def test_a_dissolucao_final_reduz_a_opacidade(self):
        """'os cristais devem desaparecer suavemente' — o alpha cai no fim em
        vez de o gelo sumir num frame."""
        from game.entities.effects.cryo_crystals import crystal_alpha

        cheio = crystal_alpha(CRYO_FREEZE_DURATION)
        meio_fade = crystal_alpha(CRYO_CRYSTAL_FADE * 0.5)
        fim = crystal_alpha(0.01)

        assert cheio > 200
        assert 0 < meio_fade < cheio
        assert fim < meio_fade

    def test_boss_congelado_nao_existe(self):
        """Boss não recebe a marca, então nunca há gelo nele — o guard é o mesmo
        `can_be_controlled` do resto do controle."""
        boss = self._alvo_no_centro()
        boss.is_boss = True
        gelar(boss, vezes=CRYO_MAX_STACKS)
        assert self._pintar(boss) == 0

    def test_geometria_vem_do_collision_circle_e_nao_de_w_h(self):
        """`MountainGeode` não tem `w`, e nele `x`/`y` é o CENTRO — as duas
        suposições que já derrubaram o jogo quando a Implosão as fez."""
        from game.entities.effects.cryo_crystals import draw_frozen
        from game.entities.enemies.mountain.mountain_geode import MountainGeode

        geode = MountainGeode(150.0, 150.0)
        assert not hasattr(geode, "w"), "premissa do teste mudou: agora tem .w"
        gelar(geode, vezes=CRYO_MAX_STACKS)

        canvas = pygame.Surface((300, 300))
        draw_frozen(canvas, [geode])  # não estoura


class TestProjetilDeGelo:
    def test_a_bala_do_cryo_sai_marcada(self):
        """O visual é decidido no disparo: a bala carrega a marca em vez de
        perguntar ao dono a cada frame de draw."""
        em = EntityManager()
        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        ship.activate_cryo_shots(10.0)
        assert all(spec.cryo for spec in ship.bullet_spawn())

        sem = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        assert not any(spec.cryo for spec in sem.bullet_spawn())
        del em

    def test_bala_reciclada_nao_nasce_gelada(self):
        """Mesmo modo de falha do `critical`: campo que o `reset()` não reescreve
        vaza para o próximo disparo."""
        em = EntityManager()
        antiga = em.spawn_bullet(100.0, 100.0, cryo=True)
        assert antiga.cryo is True

        antiga.dead = True
        em.cleanup()
        nova = em.spawn_bullet(200.0, 200.0)
        assert nova is antiga, "premissa: o pool devolveu o mesmo objeto"
        assert nova.cryo is False

    def test_o_cristal_e_desenhado_e_difere_do_tiro_comum(self):
        em = EntityManager()
        comum = em.spawn_bullet(100.0, 100.0)
        gelada = em.spawn_bullet(100.0, 100.0, cryo=True)

        def pintar(bala):
            canvas = pygame.Surface((200, 200))
            canvas.fill((0, 0, 0))
            bala.draw(canvas)
            return pygame.image.tostring(canvas, "RGB")

        assert pintar(gelada) != pintar(comum), "o tiro de gelo saiu igual ao comum"

    def test_o_sprite_do_cristal_e_cacheado(self):
        """Um `Surface` novo por bala por frame é exatamente o que §7 proíbe."""
        from game.entities.projectiles.bullet import _get_cryo_bullet_surface

        a = _get_cryo_bullet_surface(6, 12, 0)
        b = _get_cryo_bullet_surface(6, 12, 0)
        assert a is b

    def test_desenha_em_qualquer_tamanho_e_orientacao(self):
        """O tiro tem tamanhos bem diferentes por nave (o Estilete é 2px de
        largura) e vira 90° no side-scroll."""
        from game.entities.projectiles.bullet import _get_cryo_bullet_surface

        for w, h in ((2, 14), (14, 2), (6, 6), (4, 10), (24, 24)):
            surf = _get_cryo_bullet_surface(w, h, 0)
            assert surf.get_size() == (w, h)


class TestSemResiduo:
    def test_a_marca_esta_registrada_em_CONTROL_MARKS(self):
        """Marca fora da lista atravessa o pool e o próximo meteoro nasce
        gelado, muito depois de o upgrade acabar."""
        from game.entities._shared.control_marks import CONTROL_MARKS

        assert "cryo_slow_timer" in CONTROL_MARKS
        assert "cryo_stacks" in CONTROL_MARKS

    def test_meteoro_reciclado_nao_nasce_gelado(self):
        em = EntityManager()
        antigo = em.spawn_meteor(size=20, x=600.0, y=300.0, vx=0.0, vy=0.0)
        gelar(antigo, vezes=CRYO_MAX_STACKS)
        assert EntityManager._cryo_multiplier(antigo) < 1.0

        antigo.dead = True
        em.cleanup()
        novo = em.spawn_meteor(size=20, x=100.0, y=100.0, vx=0.0, vy=0.0)

        assert novo is antigo, "premissa: o pool devolveu o mesmo objeto"
        assert EntityManager._cryo_multiplier(novo) == 1.0
        assert novo.cryo_stacks == 0
