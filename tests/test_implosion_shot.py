"""Upgrade Implosão — zona de controle criada em cada acerto.

Cada tiro que conecta abre um círculo de 2s. Quem está dentro fica lento (75%,
com 3s de sobrevida) e sofre dano contínuo pequeno.

Houve uma versão com SUCÇÃO de verdade, puxando os inimigos para o impacto, e
ela foi removida — cobrava um caso especial por família de inimigo e ainda
arremessava alvos para fora da tela quando os pulsos se sobrepunham. Os testes
que sobraram guardam o que a substituiu, com atenção ao mesmo erro de fundo que
derrubou o puxão: **efeito que empilha com o número de pulsos vivos**. Sob fogo
sustentado são dezenas ao mesmo tempo, e é por isso que o cooldown de dano mora
no inimigo, não no pulso.
"""

import math

import pygame
import pytest

from game.core.upgrades import (
    UPGRADES_META,
    UpgradeCategory,
    UpgradeType,
    get_upgrade_icon,
    upgrade_factory,
)
from game.core.upgrades_config import (
    DEFAULT_UNLOCKED,
    IMPLOSION_DAMAGE,
    IMPLOSION_DAMAGE_INTERVAL,
    IMPLOSION_DURATION,
    IMPLOSION_OPEN_TIME,
    IMPLOSION_RADIUS,
    IMPLOSION_SLOW_FACTOR,
    IMPLOSION_SLOW_LINGER,
)
from game.core.spatial_grid import SpatialGrid
from game.entities.effects.implosion_pulse import (
    ImplosionPulse,
    ImplosionPulsePool,
    accepts_control,
    suction_radius,
)
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager
from game.systems.hit_result import HitResult

CX, CY = 600.0, 300.0


class FakeEnemy:
    """Inimigo mínimo com o contrato que a zona usa."""

    def __init__(self, x: float, y: float, w: int = 30, h: int = 30, health: int = 999):
        self.x = float(x)
        self.y = float(y)
        self.w = w
        self.h = h
        self.dead = False
        self.health = health
        self.hits = 0

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self):
        return (self.x + self.w / 2, self.y + self.h / 2, self.w / 2)

    def on_hit(self, damage, hx, hy):
        self.hits += 1
        self.health -= damage
        killed = self.health <= 0
        self.dead = killed
        return HitResult(killed=killed, points=0, explosion_size=0)

    def get_points_value(self):
        return 0


class Bus:
    def emit(self, event):
        pass


def at_distance(d: float, cx: float = CX, cy: float = CY, **kw) -> FakeEnemy:
    """Inimigo cujo CENTRO fica `d` px acima de `(cx, cy)`."""
    e = FakeEnemy(0, 0, **kw)
    e.x = cx - e.w / 2
    e.y = cy - d - e.h / 2
    return e


def at_fraction(f: float, **kw) -> FakeEnemy:
    """Inimigo a `f` do raio da zona. Fração e não pixels: o raio escala por
    resolução (§12) e é alvo de ajuste — um `100.0` cravado cairia fora do raio
    no dia em que qualquer um dos dois mudasse."""
    return at_distance(suction_radius() * f, **kw)


def grid_com(*enemies) -> SpatialGrid:
    g: SpatialGrid = SpatialGrid(cell_size=200)
    for e in enemies:
        g.insert(e, e.x, e.y, e.w, e.h)
    return g


def rodar_zona(
    enemies,
    segundos: float = IMPLOSION_DURATION,
    fps: float = 60.0,
    pulsos: int = 1,
    cx: float = CX,
    cy: float = CY,
):
    """Abre `pulsos` zonas em (cx, cy) e roda o mundo por `segundos`.

    Devolve (entity_manager, score_gain, destroyed). Faz o que o jogo faz por
    frame: tick do pool, handler de colisão, e decaimento dos timers.
    """
    em = EntityManager()
    em.enemies = list(enemies)
    col = Collisions(event_bus=Bus())
    for _ in range(pulsos):
        em.spawn_implosion_pulse(cx, cy)

    dt = 1.0 / fps
    gain = destroyed = 0
    # +1 frame: com `segundos == IMPLOSION_DURATION` o acumulado em ponto
    # flutuante fica um epsilon abaixo do limiar e a zona sobreviveria ao laço.
    for _ in range(int(segundos * fps) + 1):
        g = grid_com(*[e for e in em.enemies if not e.dead])
        gg, dd, _ = col.implosion_pulses_vs_enemies(
            em.implosion_pool.active, g, em
        )
        gain += gg
        destroyed += dd
        em.implosion_pool.update(dt)
        for e in em.enemies:
            EntityManager._update_implosion_linger(e, dt)
    return em, gain, destroyed


# ---------------------------------------------------------------------------
# Alcance
# ---------------------------------------------------------------------------


class TestAlcance:
    def test_pega_quem_esta_dentro(self):
        e = at_fraction(0.6)
        rodar_zona([e], segundos=0.5)
        assert e.hits > 0

    def test_ignora_quem_esta_fora(self):
        e = at_distance(suction_radius() + 60.0)
        rodar_zona([e], segundos=0.5)
        assert e.hits == 0
        assert getattr(e, "implosion_slow_timer", 0.0) == 0.0

    def test_raio_e_pequeno(self):
        """Pega o alvo e a vizinhança imediata, não varre a tela. Referência do
        próprio jogo: a explosão do tiro explosivo tem 60px."""
        assert 50.0 < IMPLOSION_RADIUS < 200.0

    def test_a_area_de_efeito_E_o_circulo_desenhado(self):
        """`covers` == `current_radius`, frame a frame.

        Enquanto isto lia o raio de pico, a zona freava e sangrava num alcance
        que o anel já não mostrava: no último terço da vida ele vale menos de
        metade do raio, e no frame final some com o efeito ainda ativo. O
        círculo existe para o jogador saber onde mirar — se ele mente, não
        serve para nada.
        """
        pool = ImplosionPulsePool()
        pool.get(CX, CY)
        p = pool.active[0]
        amostras = 0
        while not p.dead:
            pool.update(1 / 120)
            r = p.current_radius()
            if r <= 2.0:
                continue
            amostras += 1
            assert p.covers(CX + r * 0.98, CY), f"não pega dentro do anel (r={r})"
            assert not p.covers(CX + r + 1.0, CY), f"pega fora do anel (r={r})"
        assert amostras > 60, "amostragem rasa demais para valer como prova"

    def test_e_area_e_nao_lista_congelada(self):
        """Zona é ÁREA: quem entra depois é pego.

        Era o oposto na versão com sucção (alvos resolvidos no spawn), e essa
        diferença é justamente o que sumiu junto com o puxão.
        """
        em = EntityManager()
        retardatario = at_fraction(0.5)
        em.enemies = [retardatario]
        col = Collisions(event_bus=Bus())
        em.spawn_implosion_pulse(CX, CY)

        # Fora do alcance no primeiro instante...
        retardatario.y -= 400.0
        for _ in range(20):
            col.implosion_pulses_vs_enemies(
                em.implosion_pool.active, grid_com(retardatario), em
            )
            em.implosion_pool.update(1 / 60)
        assert retardatario.hits == 0

        # ...e entra na zona depois.
        retardatario.y += 400.0
        for _ in range(20):
            col.implosion_pulses_vs_enemies(
                em.implosion_pool.active, grid_com(retardatario), em
            )
            em.implosion_pool.update(1 / 60)
            EntityManager._update_implosion_linger(retardatario, 1 / 60)
        assert retardatario.hits > 0


# ---------------------------------------------------------------------------
# Dano contínuo
# ---------------------------------------------------------------------------


class TestDanoContinuo:
    def test_causa_dano_ao_longo_do_tempo(self):
        e = at_fraction(0.5)
        rodar_zona([e])
        assert e.hits >= 2, "não tiquetou mais de uma vez em 2s"

    def test_o_dano_e_pequeno(self):
        """Menos que UMA bala (10) na vida inteira da zona: é pressão de fundo,
        não a forma de matar. O upgrade é UTILITY."""
        e = at_fraction(0.5)
        rodar_zona([e])
        assert e.hits * IMPLOSION_DAMAGE < 10

    def test_respeita_o_intervalo_entre_tiques(self):
        e = at_fraction(0.5)
        rodar_zona([e])
        teto = int(IMPLOSION_DURATION / IMPLOSION_DAMAGE_INTERVAL) + 1
        assert e.hits <= teto

    def test_dano_NAO_escala_com_pulsos_sobrepostos(self):
        """O erro que derrubou o puxão, na versão dano.

        Sob fogo sustentado há dezenas de zonas vivas. Com o cooldown por PULSO,
        cada uma tiquetaria por conta própria e o DPS escalaria com a cadência
        de tiro. O cooldown mora no inimigo justamente para travar isso.
        """
        um = at_fraction(0.5)
        rodar_zona([um], pulsos=1)
        muitos = at_fraction(0.5)
        rodar_zona([muitos], pulsos=30)
        assert muitos.hits == um.hits, (
            f"30 zonas causaram {muitos.hits} tiques contra {um.hits} de uma só"
        )

    def test_dano_passa_pelo_roteador_de_dano(self):
        """§8: dano vai por `apply_hit` → `on_hit` → `HitResult`, não por
        escrita direta em `health`."""
        e = at_fraction(0.5)
        rodar_zona([e], segundos=0.5)
        assert e.hits > 0
        assert e.health == 999 - e.hits * IMPLOSION_DAMAGE

    def test_morte_pela_zona_e_contabilizada(self):
        e = at_fraction(0.5, health=IMPLOSION_DAMAGE)
        _, _, destroyed = rodar_zona([e])
        assert e.dead
        assert destroyed == 1

    def test_para_de_bater_em_quem_morreu(self):
        e = at_fraction(0.5, health=IMPLOSION_DAMAGE)
        rodar_zona([e])
        assert e.hits == 1


# ---------------------------------------------------------------------------
# Lentidão
# ---------------------------------------------------------------------------


class TestLentidao:
    def test_marca_quem_esta_no_raio(self):
        e = at_fraction(0.6)
        rodar_zona([e], segundos=0.2)
        assert e.implosion_slow_timer > 0.0

    def test_e_um_quarto_da_velocidade(self):
        """'Lentidão de 75%' = o inimigo anda a 25% do normal."""
        assert IMPLOSION_SLOW_FACTOR == 0.25

    def test_dura_tres_segundos_APOS_o_fim_da_zona(self):
        """O linger é o valor cravado a cada frame dentro da zona, NÃO a soma
        com a duração dela: o timer é reposto por frame, então somar daria 5s de
        sobrevida em vez dos 3 pedidos."""
        assert IMPLOSION_SLOW_LINGER == 3.0

    def test_sobrevive_ao_fim_da_zona(self):
        """O requisito central: a zona fecha e a lentidão continua.

        Alvo no CENTRO de propósito: o anel encolhe, e só quem está no meio
        continua coberto até o último frame — é o caso em que o linger sai
        cheio. Quem está na borda é solto antes (teste seguinte).
        """
        e = at_fraction(0.0)
        em, _, _ = rodar_zona([e])
        assert em.implosion_pool.get_active_count() == 0, "a zona não fechou"
        assert EntityManager._implosion_multiplier(e) == IMPLOSION_SLOW_FACTOR
        assert e.implosion_slow_timer == pytest.approx(IMPLOSION_SLOW_LINGER, abs=0.1)

    def test_quem_esta_na_borda_e_solto_quando_o_anel_passa(self):
        """A área de efeito é o anel DESENHADO, então ela aperta ao fechar.

        Consequência direta de `covers` seguir `current_radius`: o alvo na
        borda para de ser remarcado no instante em que o círculo passa por ele
        — e sai de lá com o linger já correndo, não com os 3s cheios.
        """
        borda = at_fraction(0.85)
        em, _, _ = rodar_zona([borda])
        assert borda.implosion_slow_timer > 0.0, "nem chegou a ser marcado"
        assert borda.implosion_slow_timer < IMPLOSION_SLOW_LINGER - 0.5, (
            "continuou sendo marcado depois de o anel passar por ele"
        )

    def test_expira_no_tempo_certo(self):
        e = at_fraction(0.5)
        rodar_zona([e], segundos=0.2)
        for _ in range(int(IMPLOSION_SLOW_LINGER * 60) + 30):
            EntityManager._update_implosion_linger(e, 1 / 60)
        assert e.implosion_slow_timer == 0.0
        assert EntityManager._implosion_multiplier(e) == 1.0

    def test_renova_em_vez_de_acumular(self):
        e = at_fraction(0.5)
        rodar_zona([e], pulsos=10, segundos=0.5)
        assert e.implosion_slow_timer <= IMPLOSION_SLOW_LINGER + 1e-9

    def test_compoe_com_os_outros_slows_em_vez_de_disputar(self):
        """EMP, gelo, vórtice e implosão multiplicam. Se a implosão escrevesse
        velocidade direto, o último a marcar apagaria os outros."""
        from game.entities.effects.ice_poison_zone import IcePoisonZone
        from game.entities.enemies.space.black_hole import BlackHole

        e = at_fraction(0.5)
        rodar_zona([e], segundos=0.2)
        e._ice_slow_timer = 5.0
        e.vortex_slow_timer = 5.0

        combinado = (
            EntityManager._implosion_multiplier(e)
            * EntityManager._ice_multiplier(e)
            * EntityManager._vortex_multiplier(e)
        )
        esperado = (
            IMPLOSION_SLOW_FACTOR
            * IcePoisonZone.SLOW_FACTOR
            * BlackHole.VORTEX_SLOW_FACTOR
        )
        assert combinado == pytest.approx(esperado)
        assert combinado < IMPLOSION_SLOW_FACTOR

    def test_sem_marca_nao_ha_penalidade(self):
        assert EntityManager._implosion_multiplier(FakeEnemy(0, 0)) == 1.0


# ---------------------------------------------------------------------------
# Quem fica de fora
# ---------------------------------------------------------------------------


class TestOptOuts:
    def test_boss_fica_fora(self):
        """Um boss lento e sangrando a cada acerto seria buff de dano
        disfarçado de utilitário."""
        boss = at_fraction(0.5)
        boss.is_boss = True
        rodar_zona([boss])
        assert boss.hits == 0
        assert getattr(boss, "implosion_slow_timer", 0.0) == 0.0

    def test_position_locked_fica_fora(self):
        """Estruturas ancoradas (estalagmite, estalactite) têm o tempo próprio
        no ciclo RISE→LINGER→SHATTER: freá-las faz a AMEAÇA durar 4x mais."""
        travado = at_fraction(0.5)
        travado.position_locked = True
        rodar_zona([travado])
        assert travado.hits == 0
        assert getattr(travado, "implosion_slow_timer", 0.0) == 0.0

    def test_estalactite_e_estalagmite_reais_ficam_intactas(self):
        """Contra as classes de verdade, não contra um stub meu."""
        from game.entities.enemies.mountain.mountain_mage import (
            MountainStalactite,
            MountainStalagmite,
        )

        for criar in (
            lambda: MountainStalagmite(600.0, 400.0, 300.0),
            lambda: MountainStalactite(600.0, -10.0, 300.0),
        ):
            e = criar()
            # `y` é derivado (property sem setter) — mira no centro REAL.
            ecx = e.x + getattr(e, "w", 0) / 2
            ecy = e.y + getattr(e, "h", 0) / 2
            pos = (e.x, e.y)
            rodar_zona([e], segundos=0.5, cx=ecx, cy=ecy)
            assert getattr(e, "implosion_slow_timer", 0.0) == 0.0, type(e).__name__
            assert (e.x, e.y) == pos, type(e).__name__

    def test_entidade_com_slots_nao_derruba_o_jogo(self):
        """O crash real: `SerpentBlock` usa `__slots__` e não declara o campo,
        então `enemy.implosion_slow_timer = ...` estourava AttributeError no
        meio do combate. Não era boss nem `position_locked`."""

        class PecaComSlots:
            __slots__ = ("x", "y", "w", "h", "dead", "emp_linger_timer")

            def __init__(self):
                self.x, self.y = CX - 15, CY - 55
                self.w = self.h = 30
                self.dead = False
                self.emp_linger_timer = 0.0

            def collision_circle(self):
                return (self.x + 15, self.y + 15, 15)

        assert accepts_control(PecaComSlots()) is False
        rodar_zona([PecaComSlots()], segundos=0.3)  # não estoura

    def test_serpent_block_real_nao_derruba_o_jogo(self):
        from game.entities.bosses.mountain_serpent_boss import SerpentBlock

        bloco = SerpentBlock(x=CX, y=CY + 40.0, side="left", boss=None, row_index=0)
        assert accepts_control(bloco) is False
        rodar_zona([bloco], segundos=0.3)

    def test_slots_que_DECLARAM_o_campo_participam(self):
        """O opt-in é declarar o slot, como já fazem com `emp_linger_timer`."""

        class PecaQueAceita:
            __slots__ = ("x", "y", "w", "h", "dead", "implosion_slow_timer")

            def __init__(self):
                self.x = self.y = 0.0
                self.w = self.h = 30
                self.dead = False
                self.implosion_slow_timer = 0.0

        assert accepts_control(PecaQueAceita()) is True

    def test_morto_e_ignorado(self):
        morto = at_fraction(0.5)
        morto.dead = True
        rodar_zona([morto])
        assert morto.hits == 0


class TestContratoDeGeometria:
    """Nem todo inimigo tem `w`/`h`. O contrato confiável é `collision_circle()`.

    O puxão antigo lia `enemy.x + enemy.w * 0.5` e derrubava o jogo no
    `MountainGeode`, que não tem `w` — e, pior, cujo `x`/`y` é o CENTRO, não o
    canto: mesmo com `w` presente a conta daria a posição errada. Estas duas
    suposições eram invisíveis até um inimigo do tipo entrar no raio.
    """

    def test_geode_real_atravessa_a_zona_sem_estourar(self):
        from game.entities.enemies.mountain.mountain_geode import MountainGeode

        geode = MountainGeode(CX, CY)
        assert not hasattr(geode, "w"), "premissa do teste mudou: agora tem .w"
        assert geode.collision_circle()[:2] == (CX, CY), "x/y é o centro"

        hp0 = geode.health
        em = EntityManager()
        em.enemies = [geode]
        col = Collisions(event_bus=Bus())
        em.spawn_implosion_pulse(CX, CY)
        for _ in range(int(IMPLOSION_DURATION * 60) + 1):
            g: SpatialGrid = SpatialGrid(cell_size=200)
            if not geode.dead:
                r = geode.rect
                g.insert(geode, r.x, r.y, r.width, r.height)
            col.implosion_pulses_vs_enemies(em.implosion_pool.active, g, em)
            em.implosion_pool.update(1 / 60)
            EntityManager._update_implosion_linger(geode, 1 / 60)

        assert geode.health < hp0, "não levou o dano da zona"
        assert EntityManager._implosion_multiplier(geode) == IMPLOSION_SLOW_FACTOR

    def test_a_zona_nunca_le_w_ou_h_de_inimigo(self):
        """Varredura de fonte: reintroduzir `enemy.w` traz o crash de volta,
        e só para a família de inimigos que não tem esse atributo — o tipo de
        bug que passa por todos os testes até alguém jogar a fase certa."""
        import inspect

        import game.entities.effects.implosion_pulse as mod

        fontes = (
            inspect.getsource(Collisions.implosion_pulses_vs_enemies),
            inspect.getsource(mod),
        )
        achados = [
            ln.strip()
            for src in fontes
            for ln in src.splitlines()
            if ("enemy.w" in ln or "enemy.h" in ln) and not ln.strip().startswith("#")
        ]
        assert not achados, "voltou a ler w/h de inimigo: " + "; ".join(achados)


# ---------------------------------------------------------------------------
# Ciclo de vida da zona
# ---------------------------------------------------------------------------


class TestCicloDeVida:
    def test_dura_cerca_de_dois_segundos(self):
        assert 1.5 <= IMPLOSION_DURATION <= 2.5

    def test_acaba_sozinha(self):
        em, _, _ = rodar_zona([at_fraction(0.5)])
        assert em.implosion_pool.get_active_count() == 0

    def test_para_de_agir_depois_de_fechar(self):
        e = at_fraction(0.5)
        em, _, _ = rodar_zona([e])
        antes = e.hits
        col = Collisions(event_bus=Bus())
        for _ in range(60):
            col.implosion_pulses_vs_enemies(
                em.implosion_pool.active, grid_com(e), em
            )
        assert e.hits == antes

    def test_recem_chegado_nao_pega_zona_de_ativacao_ANTERIOR(self):
        """O sintoma relatado: a zona fechou, mas o LUGAR continuava freando.

        Diferente de `test_para_de_agir_depois_de_fechar` (mesmo inimigo, que
        pode carregar linger legítimo): aqui o inimigo chega ao ponto exato
        DEPOIS de a zona morrer, sem nunca ter passado por ela.
        """
        em, _, _ = rodar_zona([at_fraction(0.5)])
        col = Collisions(event_bus=Bus())

        recem_chegado = at_fraction(0.3)
        for _ in range(60):
            col.implosion_pulses_vs_enemies(
                em.implosion_pool.active, grid_com(recem_chegado), em
            )
        assert recem_chegado.hits == 0
        assert getattr(recem_chegado, "implosion_slow_timer", 0.0) == 0.0
        assert EntityManager._implosion_multiplier(recem_chegado) == 1.0


# ---------------------------------------------------------------------------
# Resíduo entre ativações
# ---------------------------------------------------------------------------


class TestSemResiduoEntreAtivacoes:
    """A marca de lentidão não pode atravessar o pool.

    O timer só decai enquanto a entidade está viva no loop de update. Um
    meteoro marcado que morre volta ao pool com o resíduo CONGELADO — e o
    próximo spawn nascia lento, muito depois de o upgrade ter acabado e sem
    nenhum círculo na tela para explicar. É o mesmo objeto reaproveitado, e por
    isso o sintoma parecia preso ao LUGAR da zona antiga.
    """

    @staticmethod
    def _marcar_e_reciclar(em, spawn):
        alvo = spawn()
        alvo.implosion_slow_timer = IMPLOSION_SLOW_LINGER
        alvo.implosion_damage_cd = IMPLOSION_DAMAGE_INTERVAL
        alvo.dead = True
        em.cleanup()
        return alvo

    def test_meteoro_reciclado_nao_nasce_lento(self):
        em = EntityManager()
        antigo = self._marcar_e_reciclar(
            em, lambda: em.spawn_meteor(size=20, x=CX, y=CY, vx=0.0, vy=0.0)
        )
        novo = em.spawn_meteor(size=20, x=100.0, y=100.0, vx=0.0, vy=0.0)

        assert novo is antigo, "premissa: o pool devolveu o mesmo objeto"
        assert novo.implosion_slow_timer == 0.0
        assert novo.implosion_damage_cd == 0.0
        assert EntityManager._implosion_multiplier(novo) == 1.0

    def test_rock_glider_reciclado_nao_nasce_lento(self):
        """O RockGlider é o swarm da montanha e passa pelo mesmo `reset`."""
        em = EntityManager()
        pool = em.rock_glider_pool
        antigo = pool.get(x=CX, y=CY)
        antigo.implosion_slow_timer = IMPLOSION_SLOW_LINGER
        antigo.dead = True
        pool.release(antigo)

        novo = pool.get(x=100.0, y=100.0)
        assert novo is antigo, "premissa: o pool devolveu o mesmo objeto"
        assert novo.implosion_slow_timer == 0.0
        assert EntityManager._implosion_multiplier(novo) == 1.0

    def test_reset_limpa_TODAS_as_marcas_de_controle(self):
        """EMP, gelo e vórtice vazam pelo mesmo caminho — a lista é uma só."""
        from game.entities._shared.control_marks import CONTROL_MARKS

        em = EntityManager()
        antigo = em.spawn_meteor(size=20, x=CX, y=CY, vx=0.0, vy=0.0)
        for marca in CONTROL_MARKS:
            setattr(antigo, marca, 5.0)
        antigo.dead = True
        em.cleanup()

        novo = em.spawn_meteor(size=20, x=100.0, y=100.0, vx=0.0, vy=0.0)
        assert novo is antigo
        residuos = {m: getattr(novo, m) for m in CONTROL_MARKS if getattr(novo, m)}
        assert not residuos, f"marcas atravessaram o pool: {residuos}"

    def test_ciclo_completo_pela_zona_de_verdade(self):
        """Ponta a ponta: zona real marca o meteoro, ele morre, é reciclado.

        Sem stub de marca — quem escreve o timer aqui é o handler de colisão.
        """
        em = EntityManager()
        meteoro = em.spawn_meteor(size=20, x=CX - 20, y=CY - 20, vx=0.0, vy=0.0)
        col = Collisions(event_bus=Bus())
        em.spawn_implosion_pulse(CX, CY)

        for _ in range(10):
            g: SpatialGrid = SpatialGrid(cell_size=200)
            r = meteoro.rect
            g.insert(meteoro, r.x, r.y, r.width, r.height)
            col.implosion_pulses_vs_enemies(em.implosion_pool.active, g, em)
            em.implosion_pool.update(1 / 60)
        assert meteoro.implosion_slow_timer > 0.0, "a zona não marcou o meteoro"

        meteoro.dead = True
        em.cleanup()
        em.implosion_pool.clear_active()

        novo = em.spawn_meteor(size=20, x=100.0, y=100.0, vx=0.0, vy=0.0)
        assert EntityManager._implosion_multiplier(novo) == 1.0


# ---------------------------------------------------------------------------
# Escala por resolução (§12)
# ---------------------------------------------------------------------------


class TestEscalaPorResolucao:
    """O efeito ocupa a MESMA fração de tela em qualquer resolução lógica.

    Sem isto o raio é um número fixo de pixels: em 1080p cobre 2/3 da área que
    cobria em 720p, e o upgrade fica silenciosamente mais fraco para quem joga
    em resolução maior.
    """

    RESOLUCOES = ((1024, 576), (1280, 720), (1920, 1080))

    def test_raio_e_fracao_fixa_da_tela(self):
        from game.core.config import set_screen_resolution

        try:
            medidos = []
            for w, h in self.RESOLUCOES:
                set_screen_resolution(w, h)
                medidos.append((w, suction_radius()))
            fracoes = {round(r / w, 6) for w, r in medidos}
            assert len(fracoes) == 1, f"raio não é fração fixa: {medidos}"
            assert medidos[0][1] < medidos[-1][1]
        finally:
            set_screen_resolution(1280, 720)

    def test_o_circulo_desenhado_acompanha(self):
        """O círculo é a área de efeito — não pode divergir fora de 720p."""
        from game.core.config import set_screen_resolution

        try:
            for w, h in self.RESOLUCOES:
                set_screen_resolution(w, h)
                pool = ImplosionPulsePool()
                pool.get(CX, CY)
                assert pool.active[0].radius == suction_radius(), f"{w}x{h}"
        finally:
            set_screen_resolution(1280, 720)

    def test_em_720p_o_valor_e_a_constante_crua(self):
        from game.core.config import set_screen_resolution

        set_screen_resolution(1280, 720)
        assert suction_radius() == IMPLOSION_RADIUS


# ---------------------------------------------------------------------------
# Visual
# ---------------------------------------------------------------------------


def amostrar(fps: float = 240.0):
    """Roda uma zona devolvendo (t, raio, alpha) de cada frame."""
    pool = ImplosionPulsePool()
    pool.get(CX, CY)
    p = pool.active[0]
    amostras = []
    while not p.dead:
        pool.update(1.0 / fps)
        amostras.append((p.t, p.current_radius(), p.current_alpha()))
    return amostras


class TestVisual:
    """'Apenas um círculo', abrindo e fechando."""

    def test_atinge_o_raio_da_zona_e_depois_fecha(self):
        raios = [r for _, r, _ in amostrar()]
        assert max(raios) == pytest.approx(suction_radius(), rel=0.02)
        assert raios[-1] == pytest.approx(0.0, abs=1e-6)

    def test_o_fechamento_e_monotonico(self):
        depois = [r for t, r, _ in amostrar() if t >= IMPLOSION_OPEN_TIME]
        assert depois == sorted(depois, reverse=True)

    def test_nao_nasce_no_tamanho_cheio(self):
        assert amostrar()[0][1] < suction_radius() * 0.5

    def test_abre_e_so_depois_fecha(self):
        abertura = [r for t, r, _ in amostrar() if t <= IMPLOSION_OPEN_TIME]
        assert abertura == sorted(abertura)
        assert abertura[-1] == pytest.approx(suction_radius(), rel=0.01)

    def test_entra_transparente_e_fica_opaco(self):
        amostras = amostrar()
        assert amostras[0][2] < 128
        for t, _, alpha in amostras:
            assert alpha == 255 if t >= IMPLOSION_OPEN_TIME else alpha < 255

    def test_o_alpha_so_sobe(self):
        alphas = [a for _, _, a in amostrar()]
        assert alphas == sorted(alphas)

    def test_abertura_e_curta_perto_da_vida(self):
        assert 0.05 <= IMPLOSION_OPEN_TIME <= 0.25
        assert IMPLOSION_OPEN_TIME < IMPLOSION_DURATION * 0.15

    def test_a_abertura_sai_de_dentro_da_duracao(self):
        assert amostrar(fps=60.0)[-1][0] == pytest.approx(
            IMPLOSION_DURATION, abs=1 / 60
        )

    def test_sem_degrau_entre_abrir_e_fechar(self):
        """A abertura é máscara sobre a curva de fechamento, não uma fase com
        timer próprio — dois relógios dariam um salto na emenda."""
        raios = [r for _, r, _ in amostrar(fps=240.0)]
        saltos = [abs(b - a) for a, b in zip(raios, raios[1:])]
        assert max(saltos) < suction_radius() * 0.15

    def test_o_fechamento_acelera_ate_o_fim(self):
        assert ImplosionPulse._eased(0.5) < 0.25
        ultimo = ImplosionPulse._eased(1.0) - ImplosionPulse._eased(0.75)
        primeiro = ImplosionPulse._eased(0.25) - ImplosionPulse._eased(0.0)
        assert ultimo > primeiro * 10

    def test_a_curva_e_monotonica_e_completa(self):
        assert ImplosionPulse._eased(0.0) == 0.0
        assert ImplosionPulse._eased(1.0) == 1.0
        valores = [ImplosionPulse._eased(i / 50) for i in range(51)]
        assert valores == sorted(valores)

    def test_desenha_um_circulo_e_nada_mais(self):
        """Trava a simplificação pedida: sem partículas, sem estrias."""
        from unittest import mock

        surface = pygame.Surface((1280, 720))
        pool = ImplosionPulsePool()
        pool.get(CX, CY)
        pool.update(0.5)

        with (
            mock.patch.object(pygame.draw, "circle") as circulo,
            mock.patch.object(pygame.draw, "line") as linha,
            mock.patch.object(pygame.draw, "polygon") as poligono,
        ):
            pool.draw_all(surface)

        assert circulo.call_count == 1
        assert linha.call_count == 0
        assert poligono.call_count == 0
        assert circulo.call_args.args[-1] > 0  # contorno, não disco cheio

    def test_draw_nao_quebra_em_nenhum_ponto_da_vida(self):
        surface = pygame.Surface((1280, 720))
        pool = ImplosionPulsePool()
        pool.get(CX, CY)
        for _ in range(140):
            pool.update(1 / 60)
            pool.draw_all(surface)

    def test_o_centro_e_preso_a_tela(self):
        """A zona precisa ser VISTA para ser lida: um acerto num inimigo ainda
        entrando pela borda teria o centro fora do campo visível."""
        from game.core.config import config as Config

        em = EntityManager()
        em.spawn_implosion_pulse(-500.0, -500.0)
        p = em.implosion_pool.active[0]
        assert 0.0 <= p.cx <= Config.SCREEN_WIDTH
        assert 0.0 <= p.cy <= Config.SCREEN_HEIGHT


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------


class TestPool:
    def test_reaproveita_em_vez_de_alocar(self):
        pool = ImplosionPulsePool(initial_size=4)
        vistos = set()
        for _ in range(20):
            pool.get(CX, CY)
            while pool.get_active_count():
                pool.update(1 / 60)
            vistos.add(id(pool.free[-1]))
        assert len(vistos) <= 4, "o pool cresceu em vez de reciclar"

    def test_clear_active_esvazia(self):
        pool = ImplosionPulsePool()
        for _ in range(5):
            pool.get(CX, CY)
        assert pool.get_active_count() == 5
        pool.clear_active()
        assert pool.get_active_count() == 0

    def test_frame_longo_nao_deixa_zona_zumbi(self):
        pool = ImplosionPulsePool()
        pool.get(CX, CY)
        pool.update(5.0)
        assert pool.get_active_count() == 0


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


class TestUpgrade:
    def test_e_construivel(self):
        assert upgrade_factory(UpgradeType.IMPLOSION_SHOT).meta.type is (
            UpgradeType.IMPLOSION_SHOT
        )

    def test_e_utilitario_nao_ofensivo(self):
        """O dano é pressão de fundo; o valor está no controle."""
        assert (
            UPGRADES_META[UpgradeType.IMPLOSION_SHOT].category
            is UpgradeCategory.UTILITY
        )

    def test_tem_icone_proprio_no_hud(self):
        """Um `icon_id` fora do mapa cai no fallback do nome, em silêncio — foi
        assim que Torre de Canhão e Link mostraram 'C' os dois."""
        meta = UPGRADES_META[UpgradeType.IMPLOSION_SHOT]
        letra = get_upgrade_icon(meta.name, meta.icon_id)
        outras = {
            get_upgrade_icon(m.name, m.icon_id)
            for t, m in UPGRADES_META.items()
            if t is not UpgradeType.IMPLOSION_SHOT
        }
        assert letra not in outras, f"letra '{letra}' já usada"

    def test_esta_desbloqueado_por_padrao(self):
        assert UpgradeType.IMPLOSION_SHOT in DEFAULT_UNLOCKED

    def test_descricao_traduzida_nos_dois_idiomas(self):
        from game.core.translations import TABLES

        for lang, tabela in TABLES.items():
            assert "upgrade.implosion_shot.desc" in tabela, lang

    def test_ativar_liga_o_timer_da_nave(self):
        from game.core.ship_types import get_ship_profile
        from game.entities.player.ship import Ship

        ship = Ship(100, 100, profile=get_ship_profile("padrao"))
        assert ship.has_implosion_shot is False

        up = upgrade_factory(UpgradeType.IMPLOSION_SHOT)

        class Ctx:
            entity_manager = None
            difficulty_settings: dict = {}
            sound_manager = None
            god_mode = False
            scene = None

        Ctx.ship = ship
        assert up.activate(Ctx()) is True
        assert ship.implosion_shot_timer == pytest.approx(up.meta.base_duration)

        ship._powerups.update_timers(up.meta.base_duration + 0.1)
        assert ship.has_implosion_shot is False


# ---------------------------------------------------------------------------
# Integração com o tiro
# ---------------------------------------------------------------------------


class TestIntegracaoComOTiro:
    """O caminho real: bala acerta inimigo → zona nasce."""

    def cenario(self, *, com_upgrade: bool, piercing: bool = False, extras=()):
        from game.core.ship_types import get_ship_profile
        from game.entities.player.ship import Ship

        em = EntityManager()
        alvo = FakeEnemy(CX - 15, CY - 15)
        em.enemies = [alvo, *extras]

        ship = Ship(CX, CY + 200, profile=get_ship_profile("padrao"))
        if com_upgrade:
            ship.activate_implosion_shots(10.0)

        bala = em.spawn_bullet(
            alvo.x + 10, alvo.y + 10, damage=5, piercing=piercing, owner_ship=ship
        )
        g = grid_com(*em.enemies)
        Collisions(event_bus=Bus()).projectiles_vs_enemies([bala], g, em)
        return em, alvo

    def test_acerto_com_upgrade_abre_a_zona(self):
        em, _ = self.cenario(com_upgrade=True)
        assert em.implosion_pool.get_active_count() == 1

    def test_acerto_sem_upgrade_nao_abre_nada(self):
        em, _ = self.cenario(com_upgrade=False)
        assert em.implosion_pool.get_active_count() == 0

    def test_uma_zona_por_bala_mesmo_perfurando_varios(self):
        """Bala perfurante atravessa vários no mesmo frame; três zonas no mesmo
        ponto seriam custo triplicado por um efeito visual só."""
        extras = (FakeEnemy(CX - 10, CY - 13), FakeEnemy(CX - 5, CY - 11))
        em, _ = self.cenario(com_upgrade=True, piercing=True, extras=extras)
        assert em.implosion_pool.get_active_count() == 1

    def test_o_vizinho_e_freado_e_sangra(self):
        vizinho = at_fraction(0.5)
        em, _ = self.cenario(com_upgrade=True, extras=(vizinho,))
        col = Collisions(event_bus=Bus())
        for _ in range(120):
            col.implosion_pulses_vs_enemies(
                em.implosion_pool.active, grid_com(*em.enemies), em
            )
            em.implosion_pool.update(1 / 60)
            for e in em.enemies:
                EntityManager._update_implosion_linger(e, 1 / 60)
        assert vizinho.implosion_slow_timer > 0.0
        assert vizinho.hits > 0


def test_sem_resquicio_da_api_de_succao():
    """A atração foi removida; nada deve ter ficado para trás importável.

    Um `apply_suction`/`pull_distance` sobrevivente seria código morto que
    ninguém chama e que o próximo leitor tentaria entender.
    """
    import game.entities.effects.implosion_pulse as mod

    for sumiu in ("apply_suction", "pull_distance", "Target", "gather_targets"):
        assert not hasattr(mod, sumiu), f"{sumiu} ainda existe"
    assert not hasattr(ImplosionPulse, "_targets")

    import game.core.upgrades_config as cfg

    assert not hasattr(cfg, "IMPLOSION_PULL_DISTANCE")


def test_nenhuma_referencia_a_succao_no_codigo():
    """Varredura de fonte: nomes da API antiga não podem reaparecer."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "game"
    mortos = ("apply_suction", "IMPLOSION_PULL_DISTANCE", "gather_targets")
    achados = []
    for py in raiz.rglob("*.py"):
        texto = py.read_text(encoding="utf-8", errors="ignore")
        for nome in mortos:
            if nome in texto:
                achados.append(f"{py.name}: {nome}")
    assert not achados, "referências à API removida: " + ", ".join(achados)


def test_math_disponivel():
    assert math.isclose(IMPLOSION_SLOW_FACTOR, 0.25)
