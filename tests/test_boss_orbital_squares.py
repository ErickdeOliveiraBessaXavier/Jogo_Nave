"""Quadrados orbitais do Boss somem junto com o dono.

Os 14 orbitais eram a única entidade do jogo **sem caminho próprio de morte**:
a remoção por borda em `BossSquare.update` é restrita a `not self.is_orbital`,
porque um orbital nunca sai da tela — ele fica preso ao boss. Resultado: depois
que o boss morria eles seguiam em `em.boss_squares`, colidindo e desenhando, até
a limpeza da transição de fase varrer a lista.

A causa era propriedade dividida: o **boss** dirigia a posição deles a cada
frame, mas o **EntityManager** controlava o ciclo de vida, e nenhum dos dois
sabia da regra "sem boss, sem órbita".
"""

import pytest

from game.entities.bosses.boss import Boss
from game.entities.bosses.boss_square import BossSquare
from game.systems.entity_manager import EntityManager


def cenario() -> tuple[EntityManager, Boss]:
    em = EntityManager()
    boss = Boss(550.0, 120.0)
    em.boss = boss
    return em, boss


def tick(em: EntityManager, n: int = 1) -> None:
    for _ in range(n):
        em.update(1 / 60, 640.0, 600.0, screen_width=1280, screen_height=720)


def orbitais(em: EntityManager) -> list:
    return [q for q in em.boss_squares if q.is_orbital and not q.dead]


class TestBossVivo:
    def test_os_orbitais_entram_no_entity_manager(self):
        """Eles precisam estar em `em.boss_squares` para colisão e render os
        capturarem — é essa dupla propriedade que criava o problema."""
        em, boss = cenario()
        tick(em, 5)
        assert len(boss.floating_squares) == 14
        assert len(orbitais(em)) == 14

    def test_todo_orbital_conhece_o_dono(self):
        em, boss = cenario()
        assert all(q.owner is boss for q in boss.floating_squares)

    def test_seguem_vivos_enquanto_o_boss_vive(self):
        em, _ = cenario()
        tick(em, 60)
        assert len(orbitais(em)) == 14


class TestBossDerrotado:
    def test_se_desprendem_e_somem_apos_a_animacao(self):
        em, boss = cenario()
        tick(em, 5)
        assert orbitais(em)

        boss.dead = True
        tick(em, 1)
        # Ainda em cena: agora se espalham antes de sumir.
        assert len(orbitais(em)) == 14
        assert all(q.state == "scattering" for q in orbitais(em))

        tick(em, int(BossSquare.SCATTER_DURATION * 60) + 2)
        assert orbitais(em) == []

    def test_nao_sao_ressuscitados_na_janela_pos_morte(self):
        """Entre o boss zerar a vida e o controlador soltar `em.boss`, o
        `update_boss` ainda roda e re-registrava os orbitais em
        `em.boss_squares` — o vazamento voltaria por essa porta.

        O que se mede aqui é a CONTAGEM nunca crescer: com o boss ainda em
        `em.boss`, cada frame era uma chance de re-inserir um quadrado já morto.
        """
        em, boss = cenario()
        tick(em, 5)
        boss.dead = True

        maximo = 0
        for _ in range(int(BossSquare.SCATTER_DURATION * 60) + 30):
            tick(em, 1)  # `em.boss` continua apontando para o boss morto
            maximo = max(maximo, len(em.boss_squares))

        assert maximo <= 14, f"quadrados foram re-inseridos: pico de {maximo}"
        assert orbitais(em) == []
        assert em.boss_squares == []

    def test_somem_tambem_quando_o_boss_e_apenas_solto(self):
        """`boss_fight_controller` faz `em.boss = None` sem passar por um
        handler de morte. A regra tem que valer para esse caminho também."""
        em, boss = cenario()
        tick(em, 5)
        boss.dead = True
        em.boss = None
        tick(em, int(BossSquare.SCATTER_DURATION * 60) + 2)
        assert orbitais(em) == []

    def test_orfao_sem_dono_tambem_morre(self):
        """Defesa contra o dono ser desanexado sem morrer."""
        em, boss = cenario()
        tick(em, 5)
        for q in boss.floating_squares:
            q.owner = None
        tick(em, int(BossSquare.SCATTER_DURATION * 60) + 2)
        assert orbitais(em) == []


class TestEspalhamentoNaoMachuca:
    """A nave fica parada e sem controle durante a sequência de morte do boss.

    Um quadrado que ainda causasse dano ali cobraria um golpe que o jogador não
    tinha como evitar — é o ponto central do ajuste.
    """

    class NaveFake:
        def __init__(self, x, y):
            self.x, self.y = x, y
            self.w = self.h = 40
            self.invuln = 0

        @property
        def rect(self):
            import pygame

            return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def colisor(self):
        from game.systems.collisions import Collisions

        class Bus:
            def emit(self, e):
                pass

        return Collisions(event_bus=Bus())

    def test_com_boss_vivo_o_quadrado_ainda_machuca(self):
        """Controle: sem isto, um teste que só verifica 'não machuca' passaria
        mesmo se o dano tivesse sido quebrado de vez."""
        em, boss = cenario()
        tick(em, 5)
        alvo = boss.floating_squares[0]
        nave = self.NaveFake(alvo.x - 20, alvo.y - 20)
        assert self.colisor().ship_vs_boss_squares(nave, em.boss_squares) is True

    def test_para_de_machucar_no_mesmo_frame_da_morte(self):
        em, boss = cenario()
        tick(em, 5)
        alvo = boss.floating_squares[0]
        nave = self.NaveFake(alvo.x - 20, alvo.y - 20)

        boss.dead = True
        tick(em, 1)
        assert all(not q.causes_damage for q in em.boss_squares)
        assert self.colisor().ship_vs_boss_squares(nave, em.boss_squares) is False

    def test_nunca_machuca_durante_o_espalhamento_inteiro(self):
        """A nave é colocada no caminho e o espalhamento roda inteiro por cima."""
        em, boss = cenario()
        tick(em, 5)
        centro_x = boss.x + boss.w / 2
        centro_y = boss.y + boss.h / 2
        nave = self.NaveFake(centro_x - 20, centro_y - 20)
        col = self.colisor()

        boss.dead = True
        for _ in range(int(BossSquare.SCATTER_DURATION * 60) + 10):
            tick(em, 1)
            assert col.ship_vs_boss_squares(nave, em.boss_squares) is False

    def test_bala_atravessa_quadrado_que_ja_se_espalha(self):
        """Espalhando, o quadrado deixa de ser obstáculo: não pode comer uma
        bala em voo se já é só animação."""
        em, boss = cenario()
        tick(em, 5)
        col = self.colisor()

        alvo = em.boss_squares[0]
        bala = em.spawn_bullet(alvo.x - 2, alvo.y - 2, damage=10)
        assert col.bullets_vs_boss_squares([bala], em.boss_squares, em) > 0

        boss.dead = True
        tick(em, 1)
        alvo2 = em.boss_squares[0]
        bala2 = em.spawn_bullet(alvo2.x - 2, alvo2.y - 2, damage=10)
        assert col.bullets_vs_boss_squares([bala2], em.boss_squares, em) == 0

    def test_se_afastam_do_boss_enquanto_encolhem(self):
        em, boss = cenario()
        tick(em, 5)
        cx = boss.x + boss.w / 2
        cy = boss.y + boss.h / 2

        def dist_media():
            import math

            vivos = [q for q in em.boss_squares if not q.dead]
            return sum(math.hypot(q.x - cx, q.y - cy) for q in vivos) / len(vivos)

        boss.dead = True
        tick(em, 1)
        d0, t0 = dist_media(), max(q.size for q in em.boss_squares)
        tick(em, 30)
        d1, t1 = dist_media(), max(q.size for q in em.boss_squares)

        assert d1 > d0, "não se afastaram"
        assert t1 < t0, "não encolheram"


class TestRotacaoContinua:
    """Antes o estado 'orbiting' forçava `rotation = 0.0` em DOIS lugares —
    `BossSquare.update` e `Boss._update_lerps` — e os 14 blocos ficavam parados
    enquanto orbitavam."""

    def test_nenhuma_velocidade_de_giro_e_zero(self):
        for nome in ("SPIN_ORBITING", "SPIN_PREPARING", "SPIN_FLYING",
                     "SPIN_SCATTERING"):
            assert getattr(BossSquare, nome) > 0.0, nome

    def test_gira_enquanto_orbita(self):
        em, boss = cenario()
        tick(em, 5)
        q = boss.floating_squares[0]
        assert q.state == "orbiting"
        antes = q.rotation
        tick(em, 20)
        assert q.rotation != antes

    def test_nenhum_quadrado_fica_parado(self):
        em, boss = cenario()
        tick(em, 40)
        parados = [q for q in boss.floating_squares if q.rotation == 0.0]
        assert parados == []

    def test_o_giro_e_constante_e_previsivel(self):
        """'Suave e constante': avanço proporcional ao tempo, sem solavanco."""
        em, boss = cenario()
        tick(em, 5)
        q = boss.floating_squares[0]
        q.rotation = 0.0
        tick(em, 30)
        esperado = BossSquare.SPIN_ORBITING * (30 / 60)
        assert q.rotation == pytest.approx(esperado, rel=0.05)

    def test_o_boss_nao_zera_mais_a_rotacao(self):
        """Só linhas de CÓDIGO — o comentário que explica a remoção cita a
        expressão de propósito, e não pode fazer o teste falhar."""
        import inspect

        from game.entities.bosses import boss as mod

        codigo = [
            ln
            for ln in inspect.getsource(mod.Boss).splitlines()
            if not ln.lstrip().startswith("#")
        ]
        culpadas = [ln.strip() for ln in codigo if "rotation = 0.0" in ln]
        assert culpadas == [], culpadas

    def test_disparo_gira_mais_rapido_que_a_orbita(self):
        """O usuário permitiu manter a velocidade maior do estado de disparo."""
        assert BossSquare.SPIN_PREPARING > BossSquare.SPIN_ORBITING

    def test_a_rotacao_fica_normalizada(self):
        """Sem o módulo, o ângulo cresceria sem limite ao longo da luta."""
        em, boss = cenario()
        tick(em, 600)
        assert all(0.0 <= q.rotation < 360.0 for q in boss.floating_squares)


class TestProjetilLancadoNaoRegride:
    """O quadrado LANÇADO é outro objeto: `_create_square_projectile` cria um
    novo e devolve o orbital à órbita. Ele não tem dono e morre pela borda,
    como sempre — a correção não pode encostar nele."""

    def test_projetil_nasce_sem_dono_e_nao_orbital(self):
        proj = BossSquare(x=600, y=300, vx=0, vy=-100, size=20)
        assert proj.is_orbital is False
        assert proj.owner is None

    def test_projetil_sobrevive_ao_update(self):
        proj = BossSquare(x=600, y=300, vx=0, vy=-100, size=20)
        proj.update(1 / 60, 1280, 720)
        assert not proj.dead

    def test_projetil_ainda_morre_pela_borda(self):
        proj = BossSquare(x=600, y=300, vx=0, vy=-100, size=20)
        proj.y = -5000
        proj.update(1 / 60, 1280, 720)
        assert proj.dead

    def test_orbital_nao_morre_pela_borda(self):
        """Premissa da correção: por não ter caminho de morte por borda, o
        orbital dependia inteiramente do dono. Se isso mudar, a regra do dono
        deixa de ser a única linha de defesa e este teste avisa."""
        orb = BossSquare(
            x=-9999, y=-9999, vx=0, vy=0, size=20, is_orbital=True, owner=object()
        )
        orb.owner = type("Vivo", (), {"dead": False})()
        orb.update(1 / 60, 1280, 720)
        assert not orb.dead, "orbital passou a morrer por borda; revisar a regra"


def test_o_boss_nao_re_registra_quadrado_morto():
    """Trava o filtro `not q.dead` no `update_boss`."""
    import inspect

    from game.entities.bosses import boss as mod

    src = inspect.getsource(mod.Boss.update_boss)
    assert "not q.dead" in src, "o filtro que impede a ressurreição sumiu"


def test_quadrado_orbital_exige_dono_explicito():
    """`owner` tem default None de propósito (projéteis não têm dono), então
    esquecer de passá-lo no boss não daria erro — daria o vazamento de volta."""
    em, boss = cenario()
    assert all(q.owner is not None for q in boss.floating_squares), (
        "algum orbital foi criado sem dono"
    )
    del em


@pytest.mark.parametrize("frames_antes_da_morte", [0, 1, 10, 120])
def test_some_independente_de_quando_o_boss_morre(frames_antes_da_morte: int):
    """A órbita passa por estados (orbiting/preparing/launching); a regra não
    pode depender do estado em que o quadrado estava."""
    em, boss = cenario()
    tick(em, frames_antes_da_morte)
    boss.dead = True
    tick(em, int(BossSquare.SCATTER_DURATION * 60) + 2)
    assert orbitais(em) == []
