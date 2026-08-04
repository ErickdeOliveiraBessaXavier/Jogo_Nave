"""Alinhamento do disparo com a nave, nas quatro direções.

O jogador gira a nave (Ctrl/mouse) e o tiro nascia deslocado — de um jeito
diferente em cada direção. A causa era uma só: o produtor entregava o CENTRO de
onde o tiro sai, e o projétil usava esse ponto como `topleft` do próprio rect.
Como `w`/`h` trocam entre si conforme a orientação, o erro de meio-tamanho
mudava ao girar. Medido antes da correção: +0,7px atirando para cima contra
+2,0px para o lado no Padrão; +5,2 contra +6,5 no Magneto; e o tiro para cima
nascia 11px DENTRO do casco.

O que estes testes guardam:

1. **o centro da bala fica no eixo central da nave**, em todas as naves e nas
   quatro direções. É o invariante que o jogador percebe;
2. **a conversão centro→canto é do PROJÉTIL** (`_anchor_on_center`), porque só
   ele conhece o próprio tamanho. Um `-3.5` cravado no produtor foi o que
   segurou o bug por tanto tempo;
3. **uma regra só, rotacionada** — nenhuma direção com fórmula própria para
   divergir das outras;
4. **o Berserk não salta** ao cruzar 45°, onde a orientação do projétil inverte.
"""

import math

import pytest

from game.core.ship_types import SHIP_REGISTRY, get_ship_profile
from game.entities.player.ship import (
    MUZZLE_DUAL_SPREAD,
    MUZZLE_STANDOFF,
    Ship,
)
from game.entities.projectiles.bullet import Bullet

FACINGS = ("north", "south", "east", "west")
# 1px de tolerância: `Rect` trunca para inteiro (`_sync_rect`), então um projétil
# de lado par centrado num inteiro cai meio pixel para um lado. É a grade de
# pixels, não divergência de fórmula.
TOL = 1.0


def _nave(ship_id: str = "padrao", x: float = 300.0, y: float = 200.0) -> Ship:
    return Ship(x, y, profile=get_ship_profile(ship_id))


def _bala_da_boca(ship: Ship, dual: bool = False) -> list[Bullet]:
    sw, sh = ship.get_rendered_sprite_size()
    return [
        Bullet(
            mx,
            my,
            ship_id=ship.profile.id,
            direction=ship.get_facing_vector(),
            owner_ship=ship,
        )
        for mx, my in ship._muzzle_positions(sw, sh, dual=dual)
    ]


def _erro_transversal(ship: Ship, bala: Bullet) -> float:
    """Distância do centro da bala ao eixo central da nave, no eixo que importa."""
    cx, cy = ship.x + ship.w / 2.0, ship.y + ship.h / 2.0
    bcx, bcy = bala.x + bala.w / 2.0, bala.y + bala.h / 2.0
    return bcx - cx if ship.facing in ("north", "south") else bcy - cy


class TestAlinhamento:
    def test_o_tiro_sai_no_eixo_da_nave_em_todas_as_direcoes(self):
        """O invariante central: girar a nave não desloca a origem do tiro."""
        for perfil in SHIP_REGISTRY:
            ship = _nave(perfil.id)
            for facing in FACINGS:
                ship.set_facing(facing)
                (bala,) = _bala_da_boca(ship)
                erro = _erro_transversal(ship, bala)
                assert abs(erro) <= TOL, f"{perfil.id} {facing}: {erro:+.2f}px"

    def test_o_erro_nao_MUDA_entre_direcoes(self):
        """Era o sintoma exato: um viés constante o jogador não nota, mas um que
        muda ao girar lê como 'o canhão mudou de lugar'."""
        for perfil in SHIP_REGISTRY:
            ship = _nave(perfil.id)
            erros = []
            for facing in FACINGS:
                ship.set_facing(facing)
                (bala,) = _bala_da_boca(ship)
                erros.append(_erro_transversal(ship, bala))
            assert max(erros) - min(erros) <= TOL, f"{perfil.id}: {erros}"

    def test_vale_com_os_upgrades_que_mudam_o_tamanho(self):
        """Giant, Cryo e Corrosive escalam o projétil — e o alinhamento depende
        do tamanho. Se a conversão saísse do projétil, cada upgrade precisaria
        da própria compensação no produtor."""
        for kwargs in (
            {"size_multiplier": 3.0},
            {"cryo": True},
            {"corrosive": True},
            {"size_multiplier": 3.0, "cryo": True},
        ):
            for facing in FACINGS:
                ship = _nave("ariete")
                ship.set_facing(facing)
                sw, sh = ship.get_rendered_sprite_size()
                (mx, my), = ship._muzzle_positions(sw, sh, dual=False)
                bala = Bullet(
                    mx,
                    my,
                    ship_id="ariete",
                    direction=ship.get_facing_vector(),
                    owner_ship=ship,
                    **kwargs,
                )
                erro = _erro_transversal(ship, bala)
                assert abs(erro) <= TOL, f"{kwargs} {facing}: {erro:+.2f}px"

    def test_o_double_shot_abre_simetrico_em_volta_do_eixo(self):
        for facing in FACINGS:
            ship = _nave()
            ship.set_facing(facing)
            a, b = _bala_da_boca(ship, dual=True)
            ea, eb = _erro_transversal(ship, a), _erro_transversal(ship, b)
            assert ea * eb < 0, f"{facing}: as duas bocas do mesmo lado"
            assert abs(ea + eb) <= TOL, f"{facing}: assimétrico ({ea}, {eb})"

    def test_o_double_shot_abre_igual_nos_dois_eixos(self):
        """Antes eram 0.3 do sprite na vertical e 0.2 na horizontal: a mesma arma
        abria diferente só por causa da direção."""
        aberturas = []
        for facing in FACINGS:
            ship = _nave()
            ship.set_facing(facing)
            a, b = _bala_da_boca(ship, dual=True)
            aberturas.append(
                abs(_erro_transversal(ship, a) - _erro_transversal(ship, b))
            )
        assert max(aberturas) - min(aberturas) <= TOL, aberturas


class TestFolgaAxial:
    def test_o_tiro_nasce_FORA_do_casco_nas_quatro_direcoes(self):
        """O pior caso antigo: atirando para cima a bala nascia 11px dentro do
        sprite e só emergia ao viajar — lia como 'o tiro não sai do canhão'."""
        for perfil in SHIP_REGISTRY:
            ship = _nave(perfil.id)
            for facing in FACINGS:
                ship.set_facing(facing)
                (bala,) = _bala_da_boca(ship)
                r = bala.rect
                folga = {
                    "north": ship.y - r.bottom,
                    "south": r.top - (ship.y + ship.h),
                    "east": r.left - (ship.x + ship.w),
                    "west": ship.x - r.right,
                }[facing]
                assert folga >= 0, f"{perfil.id} {facing}: nasce {-folga:.0f}px dentro"

    def test_a_folga_e_a_MESMA_nas_quatro_direcoes(self):
        """Era -11 / 0 / +5 / +4 — quatro fórmulas manuais divergindo."""
        for perfil in SHIP_REGISTRY:
            ship = _nave(perfil.id)
            folgas = []
            for facing in FACINGS:
                ship.set_facing(facing)
                (bala,) = _bala_da_boca(ship)
                r = bala.rect
                folgas.append(
                    {
                        "north": ship.y - r.bottom,
                        "south": r.top - (ship.y + ship.h),
                        "east": r.left - (ship.x + ship.w),
                        "west": ship.x - r.right,
                    }[facing]
                )
            assert max(folgas) - min(folgas) <= TOL, f"{perfil.id}: {folgas}"

    def test_o_recuo_e_um_numero_unico_e_positivo(self):
        assert MUZZLE_STANDOFF > 0.0
        assert 0.0 < MUZZLE_DUAL_SPREAD < 0.5


class TestBerserkRotacaoLivre:
    def test_a_origem_nao_salta_ao_cruzar_45_graus(self):
        """A prova mais direta: é em 45° que `abs(dx) >= abs(dy)` inverte e o
        projétil troca `w` com `h`. Antes a origem saltava 3,5px nos dois eixos.
        """
        ship = _nave()
        cx, cy = ship.x + ship.w / 2.0, ship.y + ship.h / 2.0
        erros = []
        for deg in range(0, 360, 2):
            d = (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
            b = Bullet(cx, cy, ship_id="berserk", direction=d, owner_ship=ship)
            erros.append((b.x + b.w / 2.0 - cx, b.y + b.h / 2.0 - cy))

        pior = max(max(abs(ex), abs(ey)) for ex, ey in erros)
        assert pior <= TOL, f"origem desloca até {pior:.2f}px ao girar"


class TestContrato:
    def test_a_bala_ancora_pelo_CENTRO_recebido(self):
        """O contrato do construtor: o ponto que entra é o centro do projétil."""
        b = Bullet(100.0, 200.0, ship_id="padrao", direction=(1.0, 0.0))
        assert b.x + b.w / 2.0 == pytest.approx(100.0)
        assert b.y + b.h / 2.0 == pytest.approx(200.0)

    def test_vale_tambem_para_a_bala_reciclada_do_pool(self):
        """`reset` passa pelo mesmo caminho; se não passasse, só a primeira bala
        de cada slot sairia alinhada."""
        from game.entities.projectiles.bullet_pool import BulletPool

        pool = BulletPool(initial_size=1)
        primeira = pool.get(50.0, 50.0, direction=(1.0, 0.0))
        pool.release(primeira)
        segunda = pool.get(100.0, 200.0, direction=(0.0, -1.0))
        assert segunda is primeira, "o teste não reusou a bala; pool mudou"
        assert segunda.x + segunda.w / 2.0 == pytest.approx(100.0)
        assert segunda.y + segunda.h / 2.0 == pytest.approx(200.0)

    def test_o_fragmento_de_gelo_tambem_nasce_centrado(self):
        """Ele nasce no corpo do alvo que estilhaçou — um centro, como os outros."""
        b = Bullet(300.0, 400.0, ship_id="padrao", direction=(0.0, 1.0), ice_shard=True)
        assert b.x + b.w / 2.0 == pytest.approx(300.0)
        assert b.y + b.h / 2.0 == pytest.approx(400.0)

    def test_o_teleguiado_do_cacador_tambem_nasce_centrado(self):
        from game.entities.projectiles.homing_bullet import HomingBullet

        h = HomingBullet(120.0, 340.0, direction=(0.0, -1.0))
        assert h.x + h.w / 2.0 == pytest.approx(120.0)
        assert h.y + h.h / 2.0 == pytest.approx(340.0)

    def test_o_tiro_da_escolta_tambem_nasce_centrado(self):
        from game.entities.projectiles.mini_ship_bullet import MiniShipBullet

        m = MiniShipBullet(70.0, 80.0, vx=0.0, vy=-300.0)
        assert m.x + m.w / 2.0 == pytest.approx(70.0)
        assert m.y + m.h / 2.0 == pytest.approx(80.0)

    def test_a_compensacao_sub_frame_continua_no_eixo_do_voo(self):
        """§14: o `overshoot` desloca a bala ao longo da velocidade. Não pode ter
        virado deslocamento transversal com a mudança de ancoragem.

        Com a NAVE PARADA — que é o caso que este teste sempre cobriu. A
        compensação passou a usar velocidade relativa, então com a nave em
        movimento o deslocamento lateral é esperado e correto; ver o caso
        irmão abaixo e `tests/test_subframe_emission.py`.
        """
        from game.systems.shooting_system import ShootingSystem

        b = Bullet(100.0, 200.0, ship_id="padrao", direction=(0.0, -1.0))
        x0, y0 = b.x, b.y
        ShootingSystem._apply_subframe_catchup(b, 0.01, (0.0, 0.0))
        assert b.x == pytest.approx(x0), "deslocou de lado com a nave parada"
        assert b.y < y0, "não adiantou no eixo do voo"

    def test_nave_em_movimento_desloca_de_lado_de_proposito(self):
        """O complemento do teste acima: andando de lado, a bala NASCE atrás.

        A bala é emitida onde a boca estava quando o tiro era devido, e não
        onde ela está agora — é isso que mantém o rastro equidistante durante
        o strafe.
        """
        from game.systems.shooting_system import ShootingSystem

        b = Bullet(100.0, 200.0, ship_id="padrao", direction=(0.0, -1.0))
        x0 = b.x
        ShootingSystem._apply_subframe_catchup(b, 0.01, (275.0, 0.0))
        assert b.x == pytest.approx(x0 - 2.75), "não compensou o eixo da nave"
