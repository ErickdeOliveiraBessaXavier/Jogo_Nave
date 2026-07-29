"""Upgrade Cryo Shot — escada de gelo por acertos no MESMO inimigo, e o estouro.

25% → 50% → 75% mais lento, e o nível inteiro cai se o jogador soltar o alvo. No
topo da escada o alvo cristaliza, e os cristais são o pavio de uma **bomba de
gelo**: ao fim do congelamento (ou na morte do alvo, o que vier antes) eles
estilhaçam, ferindo o alvo e cuspindo fragmentos na vizinhança.

O que estes testes guardam:

1. **a escada sobe por acerto e o nível mora no INIMIGO** — é o que faz P1 e P2
   alimentarem a mesma escada em coop, e o que faz o nível morrer com o alvo;
2. **a queda é TOTAL** — soltar o alvo custa o nível inteiro. Se alguém trocar
   por decaimento degrau a degrau, o upgrade deixa de ser condicional e vira
   bônus permanente com atraso, que é justamente o que o separa da Implosão;
3. **o ciclo fecha em estouro** — cargas → cristalizar → bomba → fragmentos. Sem
   isso o upgrade volta a ser um debuff que expira sem evento nenhum;
4. **boss cristaliza mas não congela** — acumula cargas e detona, e nunca é
   freado: frear chefe dessincroniza padrão roteirizado e peça coreografada, a
   mesma classe de bug que derrubou o puxão da Implosão;
5. **compõe por multiplicação** com EMP/gelo/vórtice/implosão, em vez de
   disputar o mesmo campo;
6. **não vaza pelo pool** nem estoura em entidade com `__slots__`.
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
    CRYO_BOMB_DAMAGE,
    CRYO_BOMB_SHARDS,
    CRYO_CRYSTAL_CHARGE,
    CRYO_FREEZE_DURATION,
    CRYO_MAX_STACKS,
    CRYO_SHARD_DAMAGE,
    CRYO_SHARD_LIFETIME,
    CRYO_SHOT_ANGLES,
    CRYO_SHOT_DAMAGE_MULTIPLIER,
    CRYO_SLOW_DURATION,
    CRYO_SLOW_STEPS,
    DEFAULT_UNLOCKED,
)
from game.entities.player.ship import Ship
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager
from game.systems.shooting_system import ShootingSystem


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
        if self.health <= 0:
            self.dead = True
        return HitResult(killed=self.dead, points=0, explosion_size=0)

    def get_points_value(self):
        return 0


def gelar(alvo, vezes: int = 1, dono=None) -> None:
    col = Collisions(event_bus=Bus())
    for _ in range(vezes):
        col._apply_cryo(alvo, dono)


def passar_tempo(alvo, segundos: float, fps: float = 60.0) -> bool:
    """Roda o pavio fora do jogo. Devolve True se a bomba ficou pronta."""
    dt = 1.0 / fps
    pronta = False
    for _ in range(int(segundos * fps)):
        pronta = EntityManager._update_cryo_linger(alvo, dt) or pronta
    return pronta


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
        gelar(alvo, vezes=CRYO_MAX_STACKS - 1)
        passar_tempo(alvo, CRYO_SLOW_DURATION + 0.5)

        assert alvo.cryo_stacks == 0
        assert alvo.cryo_slow_timer == 0.0
        assert EntityManager._cryo_multiplier(alvo) == 1.0

    def test_a_escada_CHEIA_expira_virando_bomba_e_nao_pó(self):
        """No topo, o fim do timer não é 'passou o efeito' — é o estouro.

        As marcas ficam de pé para o `EntityManager` ler a geometria do alvo na
        hora de detonar; quem as consome é `queue_cryo_detonation`.
        """
        alvo = Alvo()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        assert passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.5) is True
        assert alvo.cryo_stacks == CRYO_MAX_STACKS

    def test_trocar_de_alvo_custa_o_nivel(self):
        """O requisito central: o upgrade é CONDICIONAL."""
        antigo, novo = Alvo(), Alvo()
        gelar(antigo, vezes=CRYO_MAX_STACKS - 1)

        # O jogador passa a atirar no outro pelo tempo da duração.
        for _ in range(CRYO_MAX_STACKS):
            gelar(novo)
        passar_tempo(antigo, CRYO_SLOW_DURATION + 0.1)

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
    def test_boss_acumula_cargas_mas_NUNCA_e_freado(self):
        """A regra dos chefes: cristaliza, detona, mas não congela.

        A imunidade mora no multiplicador e não no guard da marca — é a lentidão
        que dessincroniza padrão roteirizado e peça coreografada, não a marca.
        """
        boss = Alvo()
        boss.is_boss = True
        gelar(boss, vezes=CRYO_MAX_STACKS)

        assert boss.cryo_stacks == CRYO_MAX_STACKS
        assert EntityManager._cryo_multiplier(boss) == 1.0, (
            "o boss foi freado: os padrões de ataque dessincronizam"
        )

    def test_boss_no_topo_da_escada_tambem_vira_bomba(self):
        boss = Alvo()
        boss.is_boss = True
        gelar(boss, vezes=CRYO_MAX_STACKS)
        assert passar_tempo(boss, CRYO_FREEZE_DURATION + 0.1) is True

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

    def test_o_gelo_some_quando_a_bomba_e_consumida(self):
        """O pavio zerar não apaga o gelo — quem apaga é o estouro consumindo as
        marcas. Enquanto ninguém detonar, os cristais continuam na tela."""
        em = EntityManager()
        alvo = self._alvo_no_centro()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.5)

        em.queue_cryo_detonation(alvo)
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

    def test_a_carga_final_avisa_o_estouro(self):
        """O gelo não se dissolve mais: ele CARREGA. A rampa final é o aviso de
        que a bomba vai estourar — sem ela o estilhaço chega sem tell."""
        from game.entities.effects.cryo_crystals import charge_ratio

        assert charge_ratio(CRYO_FREEZE_DURATION) == 0.0
        meio = charge_ratio(CRYO_CRYSTAL_CHARGE * 0.5)
        fim = charge_ratio(0.0)

        assert 0.0 < meio < fim
        assert fim == pytest.approx(1.0)

    def test_o_gelo_engorda_conforme_carrega(self):
        """A carga tem duas leituras (cor e silhueta). Esta é a silhueta: perto
        do estouro o alvo cristalizado ocupa mais pixels do que recém-congelado.

        Desenha por `_draw_one` com SEED FIXO e conta pixel a pixel, em vez de
        passar por `draw_frozen` amostrando de 2 em 2. A forma dos cristais sai
        do `id()` do alvo, que muda a cada execução do processo: pela via do
        `draw_frozen` este teste media uma coroa diferente por run e o
        crescimento de 18% às vezes caía inteiro entre as amostras — falhava
        sozinho, sem nada ter mudado no código.
        """
        from game.entities.effects.cryo_crystals import _draw_one

        def pixels(charge: float) -> int:
            canvas = pygame.Surface((300, 300))
            canvas.fill((0, 0, 0))
            _draw_one(canvas, 150.0, 150.0, 22.0, 0x5EED1234, charge)
            return sum(
                1
                for x in range(300)
                for y in range(300)
                if canvas.get_at((x, y))[:3] != (0, 0, 0)
            )

        assert pixels(1.0) > pixels(0.0)

    def test_boss_cristaliza_como_qualquer_alvo(self):
        """Boss não congela, mas GANHA os cristais: é o que avisa o jogador de
        que o upgrade está rendendo contra o chefe."""
        boss = self._alvo_no_centro()
        boss.is_boss = True
        gelar(boss, vezes=CRYO_MAX_STACKS)
        assert self._pintar(boss) > 0

    def test_alvo_gigante_nao_ganha_cristais_gigantes(self):
        """As frações de config são do RAIO. Num boss de 140px de raio um
        cristal de 0.5×raio viraria uma lâmina de 70px cobrindo a arena: acima do
        teto em pixels o gelo cresce em NÚMERO, não em tamanho."""
        from game.entities.effects.cryo_crystals import (
            _crystal_scale,
            crystal_count,
        )
        from game.core.upgrades_config import (
            CRYO_CRYSTAL_COUNT,
            CRYO_CRYSTAL_MAX_LENGTH,
        )

        radius = 140.0
        length, _ = _crystal_scale(radius)
        assert (length - 1.0) * radius <= CRYO_CRYSTAL_MAX_LENGTH + 0.01
        assert crystal_count(radius) > CRYO_CRYSTAL_COUNT
        assert crystal_count(20.0) == CRYO_CRYSTAL_COUNT


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


class TestOTiroDoCryo:
    """A face OFENSIVA do upgrade: trio, área e dano.

    O Cryo não muda só a cor do projétil enquanto dura — a nave atira três
    cristais, maiores e mais fortes. Os testes travam a composição com os outros
    modificadores de disparo (que é onde este tipo de mudança costuma explodir em
    número de projéteis), não os valores, que são tuning.
    """

    @staticmethod
    def _salva(**flags):
        em = EntityManager()
        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        if flags.get("cryo"):
            ship.activate_cryo_shots(10.0)
        if flags.get("spread"):
            ship.spread_shot_timer = 10.0
        if flags.get("giant"):
            ship.big_shot_timer = 10.0
        ShootingSystem(em, Bus()).fire(ship, player_damage_multiplier=1.0)
        return list(em.bullets)

    def test_o_cryo_atira_um_trio(self):
        assert len(self._salva()) == 1, "premissa: o tiro comum é único"
        assert len(self._salva(cryo=True)) == len(CRYO_SHOT_ANGLES) == 3

    def test_o_trio_e_apertado_de_proposito(self):
        """O Cryo é upgrade de ALVO ÚNICO — a escada só sobe insistindo no mesmo
        inimigo. Leque largo espalharia as cargas por três alvos e trabalharia
        contra a própria mecânica do upgrade."""
        from game.core.config import config as Config

        assert max(abs(a) for a in CRYO_SHOT_ANGLES) < max(
            abs(a) for a in Config.SPREAD_SHOT_ANGLES
        )

    def test_o_tiro_do_meio_continua_sendo_o_tiro_padrao(self):
        """O termo central da tabela é (1, 0): quem mira continua acertando onde
        mirou, e o trio só acrescenta cobertura em volta."""
        assert 0.0 in CRYO_SHOT_ANGLES

    def test_o_leque_VENCE_o_trio_em_vez_de_multiplicar(self):
        """5 × 3 = 15 projéteis por puxada de gatilho — uma parede que nenhum dos
        dois upgrades promete. Mesma regra do leque sobre o Double Shot."""
        assert len(self._salva(cryo=True, spread=True)) == 5

    def test_o_charge_shot_nao_abre_em_trio(self):
        """`apply_spread=False` desliga os dois leques: 5 lasers do Magneto ou
        5×5 teleguiados do Caçador já são o 'muitos de uma vez' da nave."""
        ship = Ship(600.0, 500.0, profile=get_ship_profile("magneto"))
        ship.activate_cryo_shots(10.0)
        assert len(ship.bullet_spawn(apply_spread=False)) == 1

    def test_o_cristal_bate_mais_forte_que_a_bala_comum(self):
        comum = self._salva()[0].damage
        gelo = self._salva(cryo=True)[0].damage
        assert gelo > comum
        assert gelo == max(1, int(comum * CRYO_SHOT_DAMAGE_MULTIPLIER + 0.5))

    def test_o_cristal_tem_mais_area(self):
        """Área = hitbox, não só visual: é o que faz o trio conectar inteiro num
        alvo médio em vez de só o tiro do meio."""
        comum = self._salva()[0]
        gelo = self._salva(cryo=True)[0]
        assert gelo.w * gelo.h > comum.w * comum.h

    def test_area_compoe_com_o_giant_shot(self):
        """Modificadores de disparo se compõem por multiplicação nesta base —
        o cristal sob Giant Shot é um bloco, não um dos dois cancelando o outro.
        """
        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        ship.activate_cryo_shots(10.0)
        so_cryo = ship.bullet_size_multiplier
        ship.big_shot_timer = 10.0
        assert ship.bullet_size_multiplier > so_cryo

    def test_o_fragmento_da_bomba_nao_herda_nada_disso(self):
        """O caco não é o tiro da nave: tem tamanho e dano próprios, e a área do
        tiro crescer não pode inflar o leque do estouro junto."""
        em = EntityManager()
        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        ship.activate_cryo_shots(10.0)

        caco = em.spawn_cryo_shards(600.0, 300.0, 20.0, ship)[0]
        tiro = self._salva(cryo=True)[0]

        assert caco.damage == CRYO_SHARD_DAMAGE
        assert (caco.w, caco.h) != (tiro.w, tiro.h)


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


class TestBombaDeGelo:
    """O payoff: cristalizar → estourar → fragmentos.

    É o que separa este upgrade de "um debuff que expira". O que os testes
    travam é o CICLO (o estouro acontece, fere o alvo, cospe cacos) e as travas
    que impedem o ciclo de se realimentar — não os números, que vão mudar.
    """

    @staticmethod
    def _cena(alvo=None):
        em = EntityManager()
        alvo = alvo if alvo is not None else InimigoReal(600.0, 300.0)
        em.enemies = [alvo]
        return em, alvo, Collisions(event_bus=Bus())

    def test_o_pavio_queimado_fere_o_alvo(self):
        em, alvo, col = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        antes = alvo.health

        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.1)
        em.queue_cryo_detonation(alvo)
        col.cryo_bombs_vs_enemies(em)

        assert antes - alvo.health == CRYO_BOMB_DAMAGE

    def test_o_estouro_cospe_o_leque_de_fragmentos(self):
        em, alvo, col = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.1)
        em.queue_cryo_detonation(alvo)
        col.cryo_bombs_vs_enemies(em)

        cacos = [b for b in em.bullets if b.ice_shard]
        assert len(cacos) == CRYO_BOMB_SHARDS
        assert all(c.damage == CRYO_SHARD_DAMAGE for c in cacos)

    def test_os_fragmentos_saem_em_TODAS_as_direcoes(self):
        """Leque fechado, não uma salva para frente: o estouro é radial."""
        em, alvo, col = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.1)
        em.queue_cryo_detonation(alvo)
        col.cryo_bombs_vs_enemies(em)

        cacos = [b for b in em.bullets if b.ice_shard]
        assert any(c.vx > 0 for c in cacos) and any(c.vx < 0 for c in cacos)
        assert any(c.vy > 0 for c in cacos) and any(c.vy < 0 for c in cacos)
        assert all(c.vx or c.vy for c in cacos), "caco parado no lugar"

    def test_o_alvo_que_MORRE_cristalizado_estoura_na_hora(self):
        """Matar no meio do pavio adianta o estouro; não o cancela. Sem isto o
        jogador é PUNIDO por acertar bem — o prêmio some junto com o alvo."""
        em, alvo, _ = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)

        alvo.dead = True
        assert em.burst_cryo_bomb(alvo) is True
        assert len([b for b in em.bullets if b.ice_shard]) == CRYO_BOMB_SHARDS

    def test_a_morte_no_roteador_de_dano_detona(self):
        """A fiação real: quem estoura é o `apply_hit`, o roteador único (§8) —
        assim bala, laser, área e contato entram todos pelo mesmo caminho."""
        em, alvo, col = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        alvo.health = 1

        col._apply_hit(alvo, 999, alvo.x, alvo.y, em)

        assert alvo.dead is True
        assert len([b for b in em.bullets if b.ice_shard]) == CRYO_BOMB_SHARDS

    def test_detona_UMA_vez_so(self):
        """As marcas são consumidas no estouro: sem isso o mesmo alvo enfileira
        de novo no frame seguinte e o leque vira uma metralhadora."""
        em, alvo, _ = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)

        assert em.queue_cryo_detonation(alvo) is True
        assert em.queue_cryo_detonation(alvo) is False
        assert em.burst_cryo_bomb(alvo) is False

    def test_degrau_intermediario_NAO_vira_bomba(self):
        em, alvo, _ = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS - 1)
        passar_tempo(alvo, CRYO_SLOW_DURATION + 0.1)
        assert em.queue_cryo_detonation(alvo) is False

    def test_a_fila_nao_atravessa_o_frame(self):
        """Item pendente que sobra (frame sem passe de colisão) aponta para uma
        entidade que já pode ter voltado ao pool — o dano cairia em quem herdou
        o slot. O `update` limpa a fila antes de qualquer coisa."""
        em, alvo, _ = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        em.queue_cryo_detonation(alvo)
        assert em.cryo_detonations

        em.enemies.clear()  # o alvo já foi: é exatamente o cenário do risco
        em.update(1 / 60, 600.0, 500.0)
        assert em.cryo_detonations == []

    def test_o_fragmento_nao_congela_quem_ele_acerta(self):
        """A trava que impede a cascata: caco que gela cria bomba, que cria
        cacos, que gelam... sem fim. O caco é dano, não aplicação de upgrade."""
        em = EntityManager()
        vizinho = InimigoReal(600.0, 300.0)
        em.enemies = [vizinho]

        ship = Ship(600.0, 500.0, profile=get_ship_profile("padrao"))
        ship.activate_cryo_shots(10.0)
        caco = em.spawn_bullet(
            vizinho.x + 10,
            vizinho.y + 10,
            damage=CRYO_SHARD_DAMAGE,
            direction=(1.0, 0.0),
            owner_ship=ship,
            cryo=True,
            ice_shard=True,
        )

        grid: SpatialGrid = SpatialGrid(cell_size=200)
        r = vizinho.rect
        grid.insert(vizinho, r.x, r.y, r.width, r.height)
        Collisions(event_bus=Bus()).projectiles_vs_enemies([caco], grid, em)

        assert vizinho.health < 999, "o caco não causou dano"
        assert getattr(vizinho, "cryo_stacks", 0) == 0, "o caco gelou: cascata"

    def test_o_fragmento_nao_acerta_quem_o_cuspiu(self):
        """Os cacos nascem colados ao corpo do alvo. Sem a trava, o estouro
        cobraria o dano do alvo duas vezes — num boss, oito."""
        em, alvo, col = self._cena()
        gelar(alvo, vezes=CRYO_MAX_STACKS)
        passar_tempo(alvo, CRYO_FREEZE_DURATION + 0.1)
        em.queue_cryo_detonation(alvo)
        col.cryo_bombs_vs_enemies(em)

        vida = alvo.health
        grid: SpatialGrid = SpatialGrid(cell_size=200)
        r = alvo.rect
        grid.insert(alvo, r.x, r.y, r.width, r.height)
        col.projectiles_vs_enemies(list(em.bullets), grid, em)

        assert alvo.health == vida

    def test_o_fragmento_tem_alcance_curto(self):
        """Vida curta é o que mantém o estouro sendo LIMPEZA DE VIZINHANÇA e não
        uma salva grátis de oito tiros atravessando a tela."""
        em = EntityManager()
        caco = em.spawn_bullet(
            600.0, 300.0, direction=(1.0, 0.0), cryo=True, ice_shard=True
        )
        assert caco.shard_life == pytest.approx(CRYO_SHARD_LIFETIME)

        caco.update(CRYO_SHARD_LIFETIME + 0.01)
        assert caco.dead is True

    def test_o_fragmento_nao_herda_a_perfuracao_da_nave(self):
        """O caco não saiu do canhão: herdar a perfuração multiplicaria o dano
        do estouro pela nave equipada."""
        em = EntityManager()
        ariete = Ship(600.0, 500.0, profile=get_ship_profile("ariete"))
        assert ariete.profile.pierce_count > 0, "premissa: o Aríete perfura"

        caco = em.spawn_bullet(
            600.0,
            300.0,
            direction=(1.0, 0.0),
            owner_ship=ariete,
            cryo=True,
            ice_shard=True,
        )
        assert caco.pierce_remaining == 0

    def test_caco_reciclado_nao_nasce_com_a_vida_do_anterior(self):
        """Mesmo modo de falha do `critical`: campo que o `reset()` não reescreve
        vaza para o próximo disparo — aqui a bala comum morreria em 0.4s."""
        em = EntityManager()
        antigo = em.spawn_bullet(
            100.0, 100.0, direction=(1.0, 0.0), cryo=True, ice_shard=True
        )
        antigo.dead = True
        em.cleanup()

        nova = em.spawn_bullet(200.0, 200.0)
        assert nova is antigo, "premissa: o pool devolveu o mesmo objeto"
        assert nova.ice_shard is False
        assert nova.shard_life == 0.0
        assert nova.shard_source_id == 0


class TestSemResiduo:
    def test_a_marca_esta_registrada_em_CONTROL_MARKS(self):
        """Marca fora da lista atravessa o pool e o próximo meteoro nasce
        gelado, muito depois de o upgrade acabar."""
        from game.entities._shared.control_marks import CONTROL_MARKS

        assert "cryo_slow_timer" in CONTROL_MARKS
        assert "cryo_stacks" in CONTROL_MARKS
        assert "cryo_owner" in CONTROL_MARKS, (
            "o dono das cargas sobrevive ao pool e o próximo meteoro credita "
            "o kill à nave errada"
        )

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
