"""Ritmo das fusões City Drone → FusedDrone (`systems/fusion_governor.py`).

O `FusedDrone` é o único inimigo que nasce de um gatilho emergente (4 drones
próximos + sorteio), sem passar pelo spawner — ninguém controlava quantos
apareciam nem com que espaçamento. As regras travadas aqui: no máximo 2
mini-chefes vivos, uma fusão por vez e pelo menos 15s entre uma e a seguinte.

Metade dos testes exercita o governador sozinho (aritmética do relógio) e a
outra metade o caminho real do `CityDrone._maybe_start_channel` — é lá que o
gate precisa estar de fato ligado, e um governador correto que ninguém
consulta seria um no-op verde na suíte.
"""

import pytest

from game.entities.enemies.city.channeling import ChannelingGroup
from game.entities.enemies.city.city_drone import CityDrone
from game.entities.enemies.city.fused_drone import FusedDrone
from game.systems.entity_context import EnemyUpdateContext
from game.systems.fusion_governor import FusionGovernor

LEAD = ChannelingGroup.DURATION


class _Fused:
    """Mini-chefe mínimo: o governador só lê a marca de tipo (§5) e `dead`."""

    is_fused_drone = True

    def __init__(self, dead=False):
        self.dead = dead


def _drone(x, y=300.0):
    # size_tier=0: nem carrier nem homing, os dois excluídos do ritual.
    return CityDrone(x, y, side_scroll=True, size_tier=0)


def _ctx(enemies, governor, dt=1 / 60):
    return EnemyUpdateContext(
        dt=dt,
        sdt=dt,
        player_x=200.0,
        player_y=300.0,
        is_side_scroll=True,
        screen_width=1280,
        screen_height=720,
        other_enemies=enemies,
        fusion_governor=governor,
    )


def _cluster(x0, y0=300.0, n=4):
    """4 drones dentro do CHANNEL_RADIUS um do outro — grupo elegível."""
    return [_drone(x0 + i * 20.0, y0) for i in range(n)]


def _scan(drones, ctx):
    """Roda o scan como o `update_in_context` faz: só quem está livre."""
    for d in drones:
        d._scan_timer = 0.0
        if d.channel_group is None:
            d._maybe_start_channel(ctx)


# ── Governador isolado ───────────────────────────────────────────────────────
def test_arena_limpa_libera_a_primeira_fusao():
    assert FusionGovernor().allows_new_ritual([], LEAD)


def test_teto_de_dois_mini_chefes_vivos():
    gov = FusionGovernor()
    assert gov.allows_new_ritual([_Fused()], LEAD)
    assert not gov.allows_new_ritual([_Fused(), _Fused()], LEAD)


def test_mini_chefe_morto_nao_ocupa_vaga():
    # Morto ainda na lista (filtrado só no fim do frame) não segura o teto.
    gov = FusionGovernor()
    assert gov.allows_new_ritual([_Fused(), _Fused(dead=True)], LEAD)


def test_ritual_em_andamento_bloqueia_outro():
    """A regra central do pedido: duas fusões que poderiam sair juntas viram uma."""
    gov = FusionGovernor()
    membros = _cluster(100.0)
    ChannelingGroup(membros, 130.0, 300.0, side_scroll=True)
    assert not gov.allows_new_ritual(membros, LEAD)


def test_ritual_conta_uma_vez_pelos_quatro_membros():
    membros = _cluster(100.0)
    ChannelingGroup(membros, 130.0, 300.0, side_scroll=True)
    assert FusionGovernor.count_state(membros) == (0, 1)


def test_ritual_quebrado_libera_a_vaga():
    gov = FusionGovernor()
    membros = _cluster(100.0)
    grupo = ChannelingGroup(membros, 130.0, 300.0, side_scroll=True)
    membros[2].dead = True
    grupo.tick(membros[0], 0.016)  # abate de um membro quebra o ritual
    assert grupo.broken
    assert gov.allows_new_ritual(membros, LEAD)


def test_intervalo_minimo_e_medido_entre_fusoes():
    """Um ritual pode COMEÇAR no fim do cooldown, desde que só complete depois
    dele — o que o jogador não pode ver é a fusão em si antes dos 15s."""
    gov = FusionGovernor()
    gov.commit_fusion()
    assert gov.cooldown == pytest.approx(FusionGovernor.MIN_INTERVAL)

    gov.tick(FusionGovernor.MIN_INTERVAL - LEAD - 0.1)
    assert not gov.allows_new_ritual([], LEAD)  # ainda cedo: fusão cairia < 15s

    gov.tick(0.1)
    assert gov.allows_new_ritual([], LEAD)  # começa agora → funde exatamente aos 15s


def test_sem_lead_time_o_cooldown_e_o_intervalo_cheio():
    gov = FusionGovernor()
    gov.commit_fusion()
    gov.tick(FusionGovernor.MIN_INTERVAL - 0.01)
    assert not gov.allows_new_ritual([])
    gov.tick(0.01)
    assert gov.allows_new_ritual([])


def test_matar_o_mini_chefe_nao_devolve_o_cooldown():
    """Pedido explícito: derrubar a primeira fusão rápido não antecipa a segunda."""
    gov = FusionGovernor()
    gov.commit_fusion()
    gov.tick(1.0)  # mini-chefe abatido logo depois de nascer → lista vazia
    assert not gov.allows_new_ritual([], LEAD)
    assert gov.cooldown == pytest.approx(FusionGovernor.MIN_INTERVAL - 1.0)


def test_relogio_nao_fica_negativo():
    gov = FusionGovernor()
    gov.commit_fusion()
    gov.tick(FusionGovernor.MIN_INTERVAL * 3)
    assert gov.cooldown == 0.0


def test_reset_zera_o_relogio():
    gov = FusionGovernor()
    gov.commit_fusion()
    gov.reset()
    assert gov.allows_new_ritual([], LEAD)


def test_governador_e_obrigatorio_no_contexto():
    """Campo sem default de propósito: um governador novo por frame nunca
    acumularia o intervalo, e o no-op seria silencioso (§11)."""
    with pytest.raises(TypeError):
        EnemyUpdateContext(  # type: ignore[call-arg]
            dt=0.016,
            sdt=0.016,
            player_x=0.0,
            player_y=0.0,
            is_side_scroll=True,
            screen_width=1280,
            screen_height=720,
            other_enemies=[],
        )


# ── Caminho real do CityDrone ────────────────────────────────────────────────
def test_marca_de_tipo_do_mini_chefe_existe():
    # O governador conta mini-chefes por getattr (§5); renomear a marca sem
    # atualizar o contador desligaria o teto em silêncio.
    assert FusedDrone.is_fused_drone is True
    assert getattr(CityDrone(0.0, 0.0, size_tier=0), "is_fused_drone", False) is False


def test_dois_grupos_no_mesmo_frame_so_um_canaliza(monkeypatch):
    """Dois aglomerados elegíveis ao mesmo tempo: o primeiro abre o ritual, o
    segundo nem começa (sem o gate, os dois fundiriam juntos aos 4,5s)."""
    monkeypatch.setattr(CityDrone, "CHANNEL_CHANCE", 1.0)
    gov = FusionGovernor()
    a, b = _cluster(100.0), _cluster(800.0)
    todos = a + b
    _scan(todos, _ctx(todos, gov))

    grupos = {id(d.channel_group) for d in todos if d.channel_group is not None}
    assert len(grupos) == 1
    assert all(d.channel_group is None for d in b)


def test_fusao_consumada_trava_a_proxima(monkeypatch):
    """Fim a fim: ritual completa → mini-chefe no buffer → cooldown corre e o
    aglomerado vizinho fica sem canalizar até o intervalo fechar."""
    monkeypatch.setattr(CityDrone, "CHANNEL_CHANCE", 1.0)
    gov = FusionGovernor()
    a, b = _cluster(100.0), _cluster(800.0)
    todos = a + b
    ctx = _ctx(todos, gov)
    _scan(todos, ctx)

    grupo = a[0].channel_group
    assert grupo is not None
    grupo.progress = 1.0
    grupo.done = True
    grupo.spawn_boss(ctx)

    assert len(ctx.new_enemies) == 1
    assert getattr(ctx.new_enemies[0], "is_fused_drone", False)
    assert gov.cooldown == pytest.approx(FusionGovernor.MIN_INTERVAL)

    # Membros consumidos saem da lista; sobra o aglomerado B + o mini-chefe.
    vivos = [d for d in todos if not d.dead] + list(ctx.new_enemies)
    ctx_b = _ctx(vivos, gov)
    _scan(b, ctx_b)
    assert all(d.channel_group is None for d in b)

    gov.tick(FusionGovernor.MIN_INTERVAL - LEAD)
    _scan(b, _ctx(vivos, gov))
    assert b[0].channel_group is not None  # segunda fusão liberada, e só ela


def test_segundo_mini_chefe_vivo_fecha_o_teto(monkeypatch):
    """Com 2 mini-chefes em campo o cooldown vencido não basta: nenhum ritual
    novo começa enquanto um deles não morrer."""
    monkeypatch.setattr(CityDrone, "CHANNEL_CHANCE", 1.0)
    gov = FusionGovernor()
    grupo = _cluster(100.0)
    vivos = grupo + [_Fused(), _Fused()]
    _scan(grupo, _ctx(vivos, gov))
    assert all(d.channel_group is None for d in grupo)

    vivos[-1].dead = True  # uma vaga abre
    _scan(grupo, _ctx(vivos, gov))
    assert grupo[0].channel_group is not None
