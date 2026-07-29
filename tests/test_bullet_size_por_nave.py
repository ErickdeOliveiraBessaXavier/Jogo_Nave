"""Tamanho do tiro por nave — mora no `ShipProfile`, não numa cascata na bala.

Era um `if/elif` por `ship_id` dentro de `Bullet._configure_shape_and_velocity`,
enquanto TODO o resto do combate por nave (dano, cadência, velocidade do
projétil, perfuração) já vivia no perfil. O preço apareceu no elenco: Cofre,
Fantasma e Reverberador nunca ganharam um `elif` e atiravam com a forma da
Padrão **por omissão**. Nada avisava — é o mesmo modo de falha da letra de ícone
ausente, que fez Canhão e Link mostrarem "C" os dois.

O que estes testes guardam:

1. **toda nave do registry declara o próprio tamanho** — nave nova sem tamanho
   não passa despercebida;
2. **a bala lê o perfil** — se alguém reintroduzir a cascata, o teste da nave
   fictícia quebra, porque um id novo não estaria no `if`;
3. **o Berserk continua com forma própria** — ele dispara com `ship_id`
   próprio e não pode herdar o formato de quem o ativou;
4. **a ordem de aplicação não mudou**: perfil → bônus global → Giant Shot.
"""

import pytest

from game.core.config import config as Config
from game.core.ship_types import (
    DEFAULT_SHIP_ID,
    SHIP_REGISTRY,
    ShipProfile,
    get_ship_profile,
)
from game.entities.projectiles.bullet import Bullet

# Naves que atiram na forma de referência. Explícito no teste para que MUDAR o
# tiro de uma delas seja uma decisão, e não um efeito colateral silencioso.
FORMA_DA_PADRAO = {"padrao", "cofre", "fantasma", "reverberador"}


def _bala(ship_id: str, **kwargs) -> Bullet:
    return Bullet(0.0, 0.0, ship_id=ship_id, direction=(1.0, 0.0), **kwargs)


class TestRegistry:
    def test_toda_nave_declara_o_proprio_tamanho(self):
        for perfil in SHIP_REGISTRY:
            w, h = perfil.bullet_size
            assert w > 0 and h > 0, perfil.id

    def test_as_tres_naves_esquecidas_agora_tem_tamanho_explicito(self):
        """Cofre, Fantasma e Reverberador — o buraco que motivou a mudança."""
        for ship_id in ("cofre", "fantasma", "reverberador"):
            perfil = get_ship_profile(ship_id)
            assert perfil.id == ship_id, f"{ship_id} sumiu do registry"
            assert perfil.bullet_size == get_ship_profile(DEFAULT_SHIP_ID).bullet_size

    def test_o_elenco_tem_formas_distintas(self):
        """Se todas convergirem para o mesmo retângulo, o campo perdeu o sentido
        e o tiro deixa de dizer qual nave está em jogo."""
        formas = {p.bullet_size for p in SHIP_REGISTRY}
        assert len(formas) >= 4, f"só {len(formas)} formas no elenco: {formas}"

    def test_o_tamanho_e_faixa_sensata(self):
        # Faixa, não número exato (§16): trava outlier grosseiro, não o ajuste.
        for perfil in SHIP_REGISTRY:
            w, h = perfil.bullet_size
            assert 2 <= w <= 24, f"{perfil.id}: {w}"
            assert 2 <= h <= 24, f"{perfil.id}: {h}"


class TestBalaLeDoPerfil:
    def test_a_bala_usa_o_tamanho_do_perfil(self):
        bonus = Config.BULLET_BASE_SIZE_BONUS
        for perfil in SHIP_REGISTRY:
            b = _bala(perfil.id)
            esperado_w = perfil.bullet_size[0] + bonus
            esperado_h = perfil.bullet_size[1] + bonus
            assert (b.w, b.h) == (esperado_w, esperado_h), perfil.id

    def test_nave_nova_nao_precisa_tocar_na_bala(self):
        """A prova de que a cascata morreu: um perfil que a bala nunca viu já
        atira com o tamanho declarado. Com `if/elif` por id, cairia no default.
        """
        inedito = ShipProfile(
            id="nave_de_teste",
            display_name="Teste",
            description="",
            bullet_size=(21, 5),
        )
        # Registrada só para esta consulta — o teste não altera o elenco real.
        import game.core.ship_types as st

        original = st._SHIPS_BY_ID
        st._SHIPS_BY_ID = dict(original)
        st._SHIPS_BY_ID[inedito.id] = inedito
        try:
            b = _bala("nave_de_teste")
        finally:
            st._SHIPS_BY_ID = original

        bonus = Config.BULLET_BASE_SIZE_BONUS
        assert (b.w, b.h) == (21 + bonus, 5 + bonus), (
            "a bala ignorou o perfil — a cascata por id voltou?"
        )

    def test_id_desconhecido_cai_na_forma_de_referencia(self):
        padrao = get_ship_profile(DEFAULT_SHIP_ID).bullet_size
        bonus = Config.BULLET_BASE_SIZE_BONUS
        b = _bala("nave_que_nao_existe")
        assert (b.w, b.h) == (padrao[0] + bonus, padrao[1] + bonus)

    def test_o_berserk_tem_forma_PROPRIA_e_nao_a_da_nave(self):
        """Ele dispara com `ship_id="berserk"` mas passa a nave real como dono.
        Resolver pelo dono faria a Estrela Espiral herdar o formato de cada
        nave — e o tiro do Berserk é o mesmo para o elenco inteiro."""
        from game.core.ship_types import get_ship_profile as perfil_de

        class DonoFalso:
            profile = perfil_de("estilete")
            player_index = 0

        b = _bala("berserk", owner_ship=DonoFalso())
        padrao = get_ship_profile(DEFAULT_SHIP_ID).bullet_size
        bonus = Config.BULLET_BASE_SIZE_BONUS
        assert (b.w, b.h) == (padrao[0] + bonus, padrao[1] + bonus), (
            "o tiro do Berserk herdou a forma da nave que o ativou"
        )

    def test_a_orientacao_troca_com_a_direcao(self):
        """`(comprimento, espessura)` é no eixo do VOO: o mesmo tiro é deitado
        no side-scroll e em pé no top-down."""
        deitado = _bala("estilete")
        em_pe = Bullet(0.0, 0.0, ship_id="estilete", direction=(0.0, -1.0))
        assert (deitado.w, deitado.h) == (em_pe.h, em_pe.w)

    def test_o_giant_shot_escala_a_partir_do_perfil(self):
        """Ordem preservada: perfil → bônus global → Giant Shot."""
        normal = _bala("ariete")
        gigante = _bala("ariete", size_multiplier=3.0)
        assert gigante.w > normal.w and gigante.h > normal.h
        # Área ~9x (mult²), independente da forma — ver `_giant_dims`.
        razao = (gigante.w * gigante.h) / (normal.w * normal.h)
        assert razao == pytest.approx(9.0, rel=0.25)

    def test_o_fragmento_de_gelo_ignora_a_nave(self):
        """Ele não saiu do canhão de ninguém: geometria própria, antes de tudo."""
        from game.core.upgrades_config import CRYO_SHARD_SIZE

        caco = _bala("estilete", ice_shard=True)
        assert (caco.w, caco.h) == (CRYO_SHARD_SIZE, CRYO_SHARD_SIZE)
