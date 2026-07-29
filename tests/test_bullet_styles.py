"""Registro de estilos de tiro (`bullet_styles`) — o visual por nave.

Era uma cascata de nove `elif self.ship_id == ...` no `draw` da bala, com a
identidade de cada nave repartida em DOIS lugares distantes: o corpo do tiro na
cascata e a cor do halo numa tabela cem linhas acima, cujo comentário pedia
sincronização à mão. Pedido de sincronização manual é dessincronização com data
marcada.

O que estes testes guardam:

1. **corpo e halo saem da mesma entrada** — a dessincronização que o comentário
   antigo tentava evitar agora é impossível por construção;
2. **a bala não conhece nave nenhuma** — uma nave registrada em runtime já
   desenha com o estilo dela; se a cascata voltar, o teste quebra;
3. **cada nave desenha algo, e algo DIFERENTE das outras** — o tiro é como o
   jogador reconhece a própria nave em campo;
4. **as exceções do Berserk continuam válidas** — não respira sob o Giant Shot
   (estouraria o cache de frames) e gira no próprio eixo.
"""

import pygame
import pytest

from game.core import colors
from game.core.ship_types import SHIP_REGISTRY
from game.entities.projectiles import bullet_styles
from game.entities.projectiles.bullet import Bullet

# Ids que o registro cobre + os que caem no default de propósito.
IDS_DO_ELENCO = tuple(p.id for p in SHIP_REGISTRY)


def _bala(ship_id: str, **kwargs) -> Bullet:
    b = Bullet(0.0, 0.0, ship_id=ship_id, direction=(1.0, 0.0), **kwargs)
    b.x, b.y = 40.0, 40.0
    return b


def _pintar(bala) -> set:
    canvas = pygame.Surface((120, 120))
    canvas.fill((0, 0, 0))
    # Só o corpo: o halo é outro passe e mudaria a comparação entre estilos.
    bala._draw_ship_specific_bullet(canvas)
    return {
        (x, y, canvas.get_at((x, y))[:3])
        for x in range(120)
        for y in range(120)
        if canvas.get_at((x, y))[:3] != (0, 0, 0)
    }


class TestRegistro:
    def test_toda_nave_do_elenco_tem_estilo_resolvido(self):
        for ship_id in IDS_DO_ELENCO:
            estilo = bullet_styles.style_for(ship_id)
            assert callable(estilo.draw), ship_id
            assert callable(estilo.glow), ship_id

    def test_id_desconhecido_cai_no_estilo_padrao(self):
        assert bullet_styles.style_for("nave_que_nao_existe") is (
            bullet_styles.DEFAULT_STYLE
        )

    def test_a_padrao_usa_o_estilo_padrao(self):
        """Não é esquecimento: o tiro da Padrão É o retângulo chapado."""
        assert bullet_styles.style_for("padrao") is bullet_styles.DEFAULT_STYLE

    def test_corpo_e_halo_vem_da_MESMA_entrada(self):
        """O ponto do módulo. Antes eram duas tabelas distantes que um
        comentário pedia para manter em sincronia à mão."""
        for ship_id, estilo in bullet_styles.SHOT_STYLES.items():
            assert callable(estilo.draw) and callable(estilo.glow), ship_id

    def test_o_halo_de_cada_nave_tem_cor_propria(self):
        """Se dois tiros compartilham o halo, o jogador perde a informação que
        o halo existe para dar."""
        cores = [
            estilo.glow(_bala(ship_id))
            for ship_id, estilo in bullet_styles.SHOT_STYLES.items()
        ]
        assert len(set(cores)) == len(cores), cores


class TestDesenho:
    def test_cada_nave_desenha_alguma_coisa(self):
        for ship_id in IDS_DO_ELENCO + ("berserk",):
            assert _pintar(_bala(ship_id)), f"{ship_id} desenhou um tiro vazio"

    def test_os_tiros_sao_visualmente_distintos(self):
        """Não exige que TODOS diferem (Cofre e Padrão podem convergir), mas o
        elenco precisa de variedade real — é como se reconhece a nave em campo.
        """
        assinaturas = {
            frozenset(_pintar(_bala(ship_id))) for ship_id in IDS_DO_ELENCO
        }
        assert len(assinaturas) >= 6, f"só {len(assinaturas)} tiros distintos"

    def test_nave_nova_desenha_sem_tocar_na_bala(self):
        """A prova de que a cascata morreu: um estilo registrado em runtime já
        é usado pelo `draw`. Com `if/elif` por id, cairia no default."""
        marcados: list[str] = []

        def desenho_fake(bullet, surface, rect):
            marcados.append(bullet.ship_id)
            pygame.draw.rect(surface, (1, 2, 3), rect)

        original = bullet_styles.SHOT_STYLES
        bullet_styles.SHOT_STYLES = dict(original)
        bullet_styles.SHOT_STYLES["nave_ficticia"] = bullet_styles.ShotStyle(
            desenho_fake, lambda _b: (1, 2, 3)
        )
        try:
            pintado = _pintar(_bala("nave_ficticia"))
        finally:
            bullet_styles.SHOT_STYLES = original

        assert marcados == ["nave_ficticia"], "o draw ignorou o registro"
        assert any(cor == (1, 2, 3) for _x, _y, cor in pintado)

    def test_o_desenho_nao_muta_a_bala(self):
        """§3: `draw()` desenha. Estilo que mexesse no estado quebraria a pausa
        e a câmera lenta, como todo relógio próprio no render."""
        for ship_id in IDS_DO_ELENCO:
            b = _bala(ship_id)
            antes = (b.x, b.y, b.w, b.h, b.vx, b.vy, b.rotation_angle)
            _pintar(b)
            depois = (b.x, b.y, b.w, b.h, b.vx, b.vy, b.rotation_angle)
            assert antes == depois, ship_id

    def test_a_seta_do_cacador_aponta_para_o_voo(self):
        """O único estilo cujo desenho depende da direção: virar o tiro tem de
        virar a seta."""
        direita = _pintar(_bala("cacador"))
        esquerda_bala = Bullet(0.0, 0.0, ship_id="cacador", direction=(-1.0, 0.0))
        esquerda_bala.x, esquerda_bala.y = 40.0, 40.0
        assert direita != _pintar(esquerda_bala)


class TestHalo:
    def test_o_halo_padrao_reage_ao_perfurante(self):
        comum = bullet_styles.DEFAULT_STYLE.glow(_bala("padrao"))
        perfurante = bullet_styles.DEFAULT_STYLE.glow(_bala("padrao", piercing=True))
        assert comum == colors.YELLOW
        assert perfurante == colors.PURPLE

    def test_o_halo_do_reverberador_esquenta_com_o_combo(self):
        estilo = bullet_styles.style_for("reverberador")
        frio = _bala("reverberador")
        frio.combo_intensity = 0.0
        quente = _bala("reverberador")
        quente.combo_intensity = 1.0
        assert estilo.glow(frio) != estilo.glow(quente)
        assert sum(estilo.glow(quente)) > sum(estilo.glow(frio)), (
            "o combo cheio devia clarear o tiro"
        )

    def test_o_halo_do_reverberador_e_quantizado(self):
        """A rampa do combo é contínua e cada cor vira uma entrada no cache de
        glow — sem quantizar, o cache cresce sem teto."""
        estilo = bullet_styles.style_for("reverberador")
        cores = set()
        for i in range(101):
            b = _bala("reverberador")
            b.combo_intensity = i / 100.0
            cores.add(estilo.glow(b))
        assert len(cores) <= 5, f"{len(cores)} cores distintas no cache"


class TestExcecoesDoBerserk:
    def test_o_berserk_nao_respira_sob_o_giant_shot(self):
        """Tamanho variável estouraria o cache de frames pré-rotacionados."""
        assert bullet_styles.style_for("berserk").breathes is False
        assert bullet_styles.style_for("estilete").breathes is True

    def test_o_berserk_gira_e_os_outros_nao(self):
        assert bullet_styles.style_for("berserk").spin_speed > 0.0
        for ship_id in IDS_DO_ELENCO:
            assert bullet_styles.style_for(ship_id).spin_speed == 0.0, ship_id

    def test_o_update_aplica_o_giro_do_estilo(self):
        """A fiação: o `spin_speed` do registro tem de chegar no `update`."""
        b = _bala("berserk")
        b.update(0.1)
        esperado = bullet_styles.style_for("berserk").spin_speed * 0.1
        assert b.rotation_angle == pytest.approx(esperado)

    def test_tiro_comum_nao_acumula_rotacao(self):
        b = _bala("estilete")
        b.update(0.5)
        assert b.rotation_angle == 0.0
