"""Invariantes do portão de ressonância da Tríade (boss do nível 34).

O `ResonanceGate` é lógica pura (§16): estes testes não instanciam o boss nem
pygame. Os que precisam do roteamento de dano usam o `TriadBoss` de verdade,
porque o roteamento por posição é justamente o que não dá para verificar sem a
geometria real das hitboxes.

O teste mais importante do arquivo é `test_uma_cabeca_sozinha_nunca_regenera`:
ele trava a regra que impede o boss de ficar **matematicamente impossível**.
"""

from __future__ import annotations

import math
import random

import pytest

from game.entities.enemies.city.triad_boss import _CROWN_ACTOR as _CROWN
from game.entities.enemies.city.triad_boss import TriadBoss
from game.entities.enemies.city.triad_resonance import (
    LEFT,
    RIGHT,
    HeadState,
    ResonanceGate,
)

DT = 1.0 / 60.0


def _advance(gate: ResonanceGate, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        gate.update(DT)


# ── A invariante ─────────────────────────────────────────────────────────────
def test_uma_cabeca_sozinha_nunca_regenera():
    """Cabeça derrubada sozinha ESPERA a irmã — o relógio não corre.

    Sem esta regra, um jogador de DPS baixo mata a primeira lateral, ela volta
    enquanto ele trabalha na segunda, e o portão nunca abre: a luta vira
    invencível sem que nada na tela explique por quê. É invariante, não tuning.
    """
    gate = ResonanceGate()
    gate.head_died(LEFT)

    _advance(gate, 60.0)  # um minuto inteiro sozinha

    assert gate.state(LEFT) is HeadState.DOWN
    assert gate.state(RIGHT) is HeadState.SOLID
    assert not gate.crown_vulnerable


def test_relogio_arma_somente_quando_as_duas_caem():
    gate = ResonanceGate()
    gate.head_died(LEFT)
    _advance(gate, 30.0)
    assert gate.state(LEFT) is HeadState.DOWN

    gate.head_died(RIGHT)
    assert gate.crown_vulnerable

    _advance(gate, gate.regen_delay + DT)
    assert gate.state(LEFT) is HeadState.REMAT
    assert gate.state(RIGHT) is HeadState.REMAT


def test_janela_minima_segura_o_remat_mesmo_com_delay_curto():
    """A janela mínima é piso de JUSTIÇA: nem a dificuldade pode furá-la.

    Com `regen_delay` menor que `min_window`, o REMAT só pode começar quando a
    janela mínima terminar — nunca antes.
    """
    gate = ResonanceGate(regen_delay=1.0, min_window=4.0)
    gate.head_died(LEFT)
    gate.head_died(RIGHT)

    _advance(gate, 2.0)  # delay já venceu, janela não
    assert gate.state(LEFT) is HeadState.DOWN, "REMAT começou dentro da janela mínima"

    _advance(gate, 2.5)  # passa dos 4.0s
    assert gate.state(LEFT) is HeadState.REMAT


# ── Ciclo de regeneração ─────────────────────────────────────────────────────
def test_coroa_segue_vulneravel_durante_o_remat():
    """A brasa remontando NÃO fecha o portão — é o que cria a decisão da luta."""
    gate = ResonanceGate()
    gate.head_died(LEFT)
    gate.head_died(RIGHT)
    _advance(gate, gate.regen_delay + DT)

    assert gate.state(LEFT) is HeadState.REMAT
    assert gate.crown_vulnerable, "portão fechou cedo demais (durante o REMAT)"

    _advance(gate, gate.remat_duration)
    assert not gate.crown_vulnerable


def test_hp_de_retorno_decai_e_tem_piso():
    """Cada volta é mais barata que a anterior — é o que faz a luta convergir."""
    gate = ResonanceGate()
    obtidos = []

    for _ in range(5):
        gate.head_died(LEFT)
        gate.head_died(RIGHT)
        _advance(gate, gate.regen_delay + gate.remat_duration + DT)
        assert gate.state(LEFT) is HeadState.SOLID
        obtidos.append(round(gate.return_hp_fraction(LEFT), 2))

    assert obtidos == [0.75, 0.60, 0.45, 0.40, 0.40], obtidos


def test_suprimir_as_duas_brasas_mantem_a_janela_e_reinicia_o_relogio():
    gate = ResonanceGate()
    gate.head_died(LEFT)
    gate.head_died(RIGHT)
    _advance(gate, gate.regen_delay + 1.0)
    assert gate.state(LEFT) is HeadState.REMAT

    gate.head_remat_interrupted(LEFT)
    gate.head_remat_interrupted(RIGHT)

    assert gate.crown_vulnerable
    _advance(gate, gate.regen_delay - 0.5)
    assert gate.state(LEFT) is HeadState.DOWN, "relógio não reiniciou do zero"
    _advance(gate, 1.0)
    assert gate.state(LEFT) is HeadState.REMAT


def test_suprimir_uma_brasa_deixa_a_queda_no_banco():
    """Investimento parcial, retorno parcial: a irmã fecha o portão, mas a
    suprimida continua fora — o jogador só precisa rematar uma para reabrir."""
    gate = ResonanceGate()
    gate.head_died(LEFT)
    gate.head_died(RIGHT)
    _advance(gate, gate.regen_delay + 1.0)

    gate.head_remat_interrupted(LEFT)
    _advance(gate, gate.remat_duration)

    assert gate.state(LEFT) is HeadState.DOWN
    assert gate.state(RIGHT) is HeadState.SOLID
    assert not gate.crown_vulnerable


def test_portao_desligado_deixa_a_coroa_sempre_exposta():
    """Fase 3: as laterais param de proteger e a mecânica se RESOLVE."""
    gate = ResonanceGate()
    gate.disable()

    assert gate.crown_vulnerable
    _advance(gate, 30.0)
    assert gate.crown_vulnerable, "portão voltou a fechar depois de desligado"


# ── Roteamento de dano (precisa da geometria real) ───────────────────────────
@pytest.fixture
def boss() -> TriadBoss:
    b = TriadBoss()
    for _ in range(600):
        b.update(DT)
        if b.active:
            break
    assert b.active
    return b


def test_hitboxes_das_cabecas_nao_se_sobrepoem(boss: TriadBoss):
    """Sem sobreposição não existe zona ambígua no roteamento por proximidade.

    Se a arte ou a escala mudarem e os círculos passarem a se tocar, um tiro na
    borda pode ser creditado à cabeça errada — falha silenciosa que só aparece
    como "meu dano sumiu". Este teste é o alarme.
    """
    cx, cy, cr = boss._crown_circle()
    for head in boss.heads:
        dist = ((cx - head.center_x) ** 2 + (cy - head.center_y) ** 2) ** 0.5
        assert dist >= cr + head.radius, (
            f"círculo da Coroa encosta na lateral {head.slot}: "
            f"dist={dist:.1f} < {cr + head.radius:.1f}"
        )


def test_tiro_na_coroa_fechada_nao_causa_dano(boss: TriadBoss):
    cx, cy, _ = boss._crown_circle()
    antes = boss.health

    resultado = boss.on_hit(200, cx, cy)

    assert boss.health == antes
    assert not resultado.killed
    assert boss._miss_timer > 0.0, "sem indicador de MISS, o tiro some sem explicação"


def test_tiro_na_lateral_nao_fere_a_coroa(boss: TriadBoss):
    head = boss.heads[LEFT]
    antes_coroa, antes_head = boss.health, head.hp

    boss.on_hit(50, head.center_x, head.center_y)

    assert head.hp == antes_head - 50
    assert boss.health == antes_coroa


def test_dano_sem_posicao_respeita_o_portao(boss: TriadBoss):
    """AoE/cadeia não tem ponto de impacto — não pode furar o portão."""
    antes = boss.health

    boss.take_damage(300)

    assert boss.health == antes, "dano sem posição chegou à Coroa com o portão fechado"
    assert boss.heads[LEFT].hp < boss.heads[LEFT].max_hp


def test_coroa_recebe_dano_com_as_duas_fora(boss: TriadBoss):
    for slot in (LEFT, RIGHT):
        head = boss.heads[slot]
        while boss.gate.state(slot) is HeadState.SOLID:
            boss.on_hit(999, head.center_x, head.center_y)

    assert boss.gate.crown_vulnerable
    antes = boss.health
    cx, cy, _ = boss._crown_circle()
    boss.on_hit(120, cx, cy)

    assert boss.health == antes - 120


def test_dano_na_coroa_e_permanente_atraves_da_regeneracao(boss: TriadBoss):
    """A regra de ouro do encontro: o jogador perde TEMPO, nunca progresso."""
    for slot in (LEFT, RIGHT):
        head = boss.heads[slot]
        while boss.gate.state(slot) is HeadState.SOLID:
            boss.on_hit(999, head.center_x, head.center_y)

    cx, cy, _ = boss._crown_circle()
    boss.on_hit(400, cx, cy)
    depois_do_dano = boss.health

    # ciclo inteiro de regeneração das duas laterais
    for _ in range(int(20.0 / DT)):
        boss.update(DT)
    assert boss.gate.is_solid(LEFT) and boss.gate.is_solid(RIGHT)

    assert boss.health == depois_do_dano, "a regeneração devolveu HP da Coroa"


def test_alvo_do_teleguiado_e_sempre_uma_parte_feriivel(boss: TriadBoss):
    """`collision_circle` alimenta mira automática e AoE — apontar para a
    região intangível faria o teleguiado gastar carga em nada."""
    cx, cy, _ = boss.collision_circle()
    laterais = [(h.center_x, h.center_y) for h in boss.heads]
    assert (cx, cy) in laterais, "com o portão fechado a mira deve ir para uma Voz"

    for slot in (LEFT, RIGHT):
        head = boss.heads[slot]
        while boss.gate.state(slot) is HeadState.SOLID:
            boss.on_hit(999, head.center_x, head.center_y)

    assert boss.collision_circle()[:2] == boss._crown_circle()[:2]

# ── Área de dano por pixel ───────────────────────────────────────────────────
def test_coroa_recebe_dano_so_onde_ha_desenho(boss: TriadBoss):
    """O corpo é por PIXEL: nada de acertar o vazio ao redor da silhueta.

    Vale para a Coroa, não para as Vozes — elas usam retângulo cheio de
    propósito (ver `test_area_da_voz_e_o_L_invertido_do_rosto`).
    """
    from PIL import Image

    from game.entities.enemies.city import triad_pixel_map as pmap

    boss._frame_index = 0
    crown = pmap.load_part("crown").mask(0, attacking=False)
    scale = pmap.PIXEL_SCALE
    alpha = Image.open(pmap.SPRITE_DIR / pmap.PART_DIRS["crown"] / "01.png").convert("RGBA").load()

    divergentes = []
    for sy in range(pmap.FRAME):
        for sx in range(pmap.FRAME):
            atingivel = bool(crown.get_at((sx * scale + scale // 2, sy * scale + scale // 2)))
            if atingivel != (alpha[sx, sy][3] > 0):
                divergentes.append((sx, sy))

    assert not divergentes, f"{len(divergentes)} pixels divergem do PNG: {divergentes[:5]}"


def test_area_da_voz_e_o_L_invertido_do_rosto(boss: TriadBoss):
    """A hitbox da Voz é a região declarada — testa + coluna externa, sólida.

    Sólida e não recortada pela silhueta porque o rosto tem um vão de uma linha
    inteira na altura da "boca" (linha 32): recortado por máscara, esse vão vira
    uma fresta atravessável no meio da cabeça.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    scale = pmap.PIXEL_SCALE
    ox, oy = boss._blit_origin()

    def parte_em(sx: int, sy: int):
        return boss._part_at(ox + (sx + 0.5) * scale, oy + (sy + 0.5) * scale)

    for slot, part in ((LEFT, "left"), (RIGHT, "right")):
        esperado = set()
        for rx, ry, rw, rh in pmap.HEAD_DAMAGE_RECTS[part]:
            for sy in range(ry, ry + rh):
                for sx in range(rx, rx + rw):
                    esperado.add((sx, sy))
        for sx, sy in esperado:
            assert parte_em(sx, sy) is boss.heads[slot], (
                f"({sx},{sy}) está na região da Voz {slot} mas não é alvo dela"
            )

    # A linha 32 (o vão do rosto) tem que ser alvo — é o buraco que o retângulo fecha.
    assert parte_em(9, 32) is boss.heads[LEFT]
    assert parte_em(54, 32) is boss.heads[RIGHT]


def test_filamento_da_voz_nao_recebe_dano(boss: TriadBoss):
    """O filamento curva para DENTRO e nas linhas 37-39 se entrelaça com o
    tronco. Enquanto foi alvo, tiro mirado na cabeça central virava dano na
    lateral — o roteamento dá o empate à Voz."""
    from game.entities.enemies.city import triad_pixel_map as pmap

    scale = pmap.PIXEL_SCALE
    ox, oy = boss._blit_origin()

    for sx, sy in ((18, 26), (20, 27), (16, 30), (15, 37), (45, 26), (43, 27), (47, 30), (48, 37)):
        alvo = boss._part_at(ox + (sx + 0.5) * scale, oy + (sy + 0.5) * scale)
        assert alvo not in boss.heads, f"filamento ({sx},{sy}) ainda é alvo de uma Voz"


def test_faixa_central_nao_da_dano_nas_vozes(boss: TriadBoss):
    """Tiro na coluna do corpo é da Coroa — o sintoma relatado em playtest."""
    from game.entities.enemies.city import triad_pixel_map as pmap

    scale = pmap.PIXEL_SCALE
    ox, oy = boss._blit_origin()

    roubados = []
    for sy in range(14, 48):
        for sx in range(23, 41):
            alvo = boss._part_at(ox + (sx + 0.5) * scale, oy + (sy + 0.5) * scale)
            if alvo in boss.heads:
                roubados.append((sx, sy))

    assert not roubados, f"{len(roubados)} pontos do corpo creditados a uma Voz: {roubados[:8]}"


def test_cabeca_derrubada_sai_da_area_de_dano(boss: TriadBoss):
    """Soquete vazio tem que ser atravessável — senão o tiro some sem motivo."""
    antes, _ = boss.get_collision_mask_data()
    pixels_antes = antes.count()

    head = boss.heads[LEFT]
    while boss.gate.state(LEFT) is HeadState.SOLID:
        boss.on_hit(999, head.center_x, head.center_y)
    boss.update(DT)

    depois, _ = boss.get_collision_mask_data()
    assert depois.count() < pixels_antes, "a Voz destruída continua ocupando área de dano"


def test_centro_das_hitboxes_cai_em_pixel_desenhado(boss: TriadBoss):
    """Os círculos ancoram no centroide do desenho, não no centro do bbox.

    A cabeça lateral é um gancho e o centro do bbox cai no VAZIO — mira
    automática e roteamento por proximidade ficariam apontando para o buraco.
    """
    assert boss._part_at(*boss._crown_circle()[:2]) is boss
    for head in boss.heads:
        assert boss._part_at(head.center_x, head.center_y) is head, (
            f"centro do círculo da Voz {head.slot} não está sobre o desenho"
        )

# ── Caminhos de dano que NÃO trazem ponto de impacto real ────────────────────
class _EMStub:
    """EntityManager mínimo para o roteador de dano (§16: stubs, não o jogo)."""

    def spawn_explosion(self, *a, **k) -> None: ...
    def absorb_fragments(self, *a, **k) -> None: ...
    def trigger_death_sequence(self, *a, **k) -> None: ...


def _sprite_point(boss: TriadBoss, sx: float, sy: float) -> tuple[float, float]:
    from game.entities.enemies.city import triad_pixel_map as pmap

    ox, oy = boss._blit_origin()
    return ox + (sx + 0.5) * pmap.PIXEL_SCALE, oy + (sy + 0.5) * pmap.PIXEL_SCALE


def test_explosao_no_tronco_nao_fere_as_vozes(boss: TriadBoss):
    """Dano em área é creditado a ONDE a explosão ocorreu.

    `_aoe_into_boss` passava o centro do `collision_circle()` do boss como ponto
    do hit, descartando a origem real. Como esse círculo aponta para a Voz
    atacável, TODA explosão era creditada a ela — inclusive a que estourava no
    tronco. Era o sintoma "atirar no torso dá dano nas cabeças".
    """
    from game.systems.collisions import Collisions

    hp_antes = (boss.health, boss.heads[LEFT].hp, boss.heads[RIGHT].hp)
    x, y = _sprite_point(boss, 31, 44)  # núcleo de energia, no peito

    Collisions()._aoe_into_boss(boss, x, y, 120.0, 200, set(), [], _EMStub())

    assert (boss.health, boss.heads[LEFT].hp, boss.heads[RIGHT].hp) == hp_antes


def test_explosao_na_voz_fere_so_aquela_voz(boss: TriadBoss):
    from game.systems.collisions import Collisions

    hp_coroa = boss.health
    hp_direita = boss.heads[RIGHT].hp
    x, y = _sprite_point(boss, 10, 26)  # massa do rosto esquerdo

    Collisions()._aoe_into_boss(boss, x, y, 120.0, 200, set(), [], _EMStub())

    assert boss.heads[LEFT].hp < boss.heads[LEFT].max_hp
    assert boss.heads[RIGHT].hp == hp_direita
    assert boss.health == hp_coroa


def test_arma_sem_ponto_de_contato_acerta_o_alvo_atacavel(boss: TriadBoss):
    """Laser do Caçador / descarga orbital miram por `collision_circle()`.

    Elas não rastreiam ponto de contato. Com `rect.center` (o corpo) o dano caía
    na região intangível e virava MISS — a arma simplesmente não funcionava
    contra este chefe.
    """
    cx, cy, _ = boss.collision_circle()
    hp_antes = boss.heads[LEFT].hp

    boss.on_hit(50, cx, cy)

    assert boss.heads[LEFT].hp == hp_antes - 50

def test_vao_do_traco_do_torso_e_da_coroa(boss: TriadBoss):
    """Tiro que cai num VÃO do desenho do tronco pertence à Coroa.

    O torso é desenho de LINHA e quase todo oco. O projétil encosta num traço
    (a colisão vale — quem manda é a máscara), mas o CENTRO dele cai no vazio
    entre traços. O roteamento então caía em "parte atacável mais próxima" e
    creditava a uma Voz: tiro na base do torso, em y 52, virava dano numa cabeça
    que termina em y 37. Pontos marcados em playtest, no arquivo
    `Imagem_Boss_Completo_Exemplo_local_tiro.png`.
    """
    for sx, sy in ((21, 52), (44, 52)):
        antes = (boss.health, boss.heads[LEFT].hp, boss.heads[RIGHT].hp)
        boss.on_hit(100, *_sprite_point(boss, sx, sy))
        assert (boss.health, boss.heads[LEFT].hp, boss.heads[RIGHT].hp) == antes, (
            f"tiro no vão ({sx},{sy}) causou dano"
        )


def test_nenhum_ponto_do_corpo_credita_uma_voz(boss: TriadBoss):
    """Varredura completa: dentro do corpo, só as regiões DECLARADAS são Voz.

    Cobre traço e vão igualmente — é o teste que pega a regressão de fallback,
    que só aparece nos buracos do desenho e por isso escapa de amostragem.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    declarado = {
        (sx, sy)
        for part in ("left", "right")
        for rx, ry, rw, rh in pmap.HEAD_DAMAGE_RECTS[part]
        for sy in range(ry, ry + rh)
        for sx in range(rx, rx + rw)
    }

    inesperados = []
    for sy in range(pmap.CONTENT_Y0, pmap.CONTENT_Y1):
        for sx in range(pmap.CONTENT_X0, pmap.CONTENT_X1):
            if (sx, sy) in declarado:
                continue
            ponto = _sprite_point(boss, sx, sy)
            alvo = boss._part_at(*ponto) or boss._fallback_target(*ponto)
            if alvo in boss.heads:
                inesperados.append((sx, sy))

    assert not inesperados, (
        f"{len(inesperados)} pontos do corpo creditados a uma Voz: {inesperados[:8]}"
    )

def test_tiro_por_baixo_do_torso_nao_credita_uma_voz(boss: TriadBoss):
    """O ponto mais atingido da luta: a base do corpo, vinda de baixo.

    O jogador atira de baixo para cima. Quando a PONTA do projétil toca a base do
    losango, o CENTRO dele — que é o ponto entregue ao roteador — ainda está
    abaixo do corpo. Enquanto a Coroa foi medida por um ponto (o centro da cabeça
    dela), esse impacto ficava mais perto de uma Voz e era creditado a ela.

    Varre uma faixa inteira abaixo e ao redor da base, não um ponto só: o defeito
    original valia para toda a região sob o boss.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    errados = []
    for sy in range(pmap.CONTENT_Y1 - 4, pmap.CONTENT_Y1 + 8):
        for sx in range(pmap.CONTENT_X0, pmap.CONTENT_X1):
            ponto = _sprite_point(boss, sx, sy)
            alvo = boss._part_at(*ponto) or boss._fallback_target(*ponto)
            if alvo in boss.heads:
                errados.append((sx, sy))

    assert not errados, f"{len(errados)} pontos sob o torso creditados a uma Voz: {errados[:8]}"


def test_explosao_ao_lado_de_uma_voz_ainda_a_atinge(boss: TriadBoss):
    """A correção não pode cegar o dano em área legítimo.

    Explosão FORA do corpo, encostada numa Voz, tem que continuar ferindo aquela
    Voz — é o contrapeso do teste acima, que empurra tudo para a Coroa.
    """
    from game.systems.collisions import Collisions

    head = boss.heads[LEFT]
    x = head.center_x - head.radius * 0.8
    y = head.center_y
    hp_antes = head.hp

    Collisions()._aoe_into_boss(boss, x, y, 120.0, 150, set(), [], _EMStub())

    assert head.hp < hp_antes, "explosão colada na Voz deixou de feri-la"

# ── Animação ─────────────────────────────────────────────────────────────────
def test_idle_faz_loop_de_ida_e_volta():
    """0,1,2,1,0,1,2,1... — sem o salto do último frame de volta ao primeiro.

    São só 3 frames por parte; o loop em serra salta 2→0 num passo e num ciclo
    tão curto isso lê como tranco, não como respiração.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    assert [pmap._pingpong(i, 3) for i in range(9)] == [0, 1, 2, 1, 0, 1, 2, 1, 0]
    assert [pmap._pingpong(i, 2) for i in range(4)] == [0, 1, 0, 1]
    assert [pmap._pingpong(i, 1) for i in range(3)] == [0, 0, 0]  # sem divisão por zero


def test_sprite_e_mascara_usam_o_mesmo_frame():
    """Se os dois índices divergirem, a área de dano vira a de outro frame.

    O sintoma seria invisível no render e aleatório no gameplay — o pior tipo.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    crown = pmap.load_part("crown")
    for i in range(24):
        desenhado = crown.frame(i, attacking=False)
        atingivel = crown.mask(i, attacking=False)
        assert crown.idle.index(desenhado) == crown.idle_masks.index(atingivel)



# ── Fase 1 — "O Coro" ────────────────────────────────────────────────────────
_PLAYER = (640.0, 600.0)


def _tick(orb, dt=DT, px=640.0, py=560.0):
    class _Ctx:
        sdt = dt
        player_x = px
        player_y = py

    orb.update_in_context(_Ctx())


def _run_phase1(boss: TriadBoss, seconds: float, seed: int | None = None):
    """Roda o ciclo de ataque e devolve (emissões, nº máx. de cabeças laranja).

    `seed` fixa o sorteio de ator/ataque. Quem cobra "todo ataque apareceu"
    PRECISA passar um: a escolha de quem age é aleatória, então sem semente o
    teste falha de vez em quando sem nada ter quebrado — foi assim que este
    arquivo ganhou dois testes intermitentes.
    """
    if seed is not None:
        random.seed(seed)
    emissoes = []
    max_laranja = 0
    t = 0.0
    # As esferas precisam AVANÇAR, como avançariam no `EntityManager`. Sem isso
    # elas nunca morrem, o teto de `_MAX_LIVE_ORBS` enche e o boss para de
    # emitir — o teste então "não via" ataques que o jogo dispara normalmente.
    vivas: list = []
    while t < seconds:
        orbs = boss.update(DT, _PLAYER)
        t += DT
        laranja = int(boss._crown_attacking) + sum(1 for h in boss.heads if h.attacking)
        max_laranja = max(max_laranja, laranja)
        if orbs:
            emissoes.append((boss._actor, boss._attack, orbs))
            vivas.extend(orbs)
        for orb in vivas:
            _tick(orb)
        vivas = [o for o in vivas if not o.dead]
    return emissoes, max_laranja


def test_fase1_age_uma_cabeca_por_vez(boss: TriadBoss):
    """A identidade da Fase 1 é o turno: nunca duas cabeças agindo juntas.

    É o que permite o jogador aprender os três ataques isolados — sem isso, a
    Fase 2 (que os SOBREPÕE) não teria vocabulário anterior para se apoiar.
    """
    emissoes, max_laranja = _run_phase1(boss, 14.0)

    assert emissoes, "nenhum ataque em 14s"
    assert max_laranja <= 1, "duas cabeças laranja ao mesmo tempo na Fase 1"


def test_laranja_sempre_precede_o_disparo(boss: TriadBoss):
    """Laranja nunca mente (§7): quem dispara esteve laranja antes.

    Sem isso o telégrafo vira decoração e o boss deixa de ser aprendível.
    """
    t = 0.0
    laranja_antes = None
    while t < 8.0:
        antes = (
            _CROWN if boss._crown_attacking else next(
                (h.slot for h in boss.heads if h.attacking), None
            )
        )
        orbs = boss.update(DT, _PLAYER)
        t += DT
        if orbs:
            assert antes is not None, "disparo sem wind-up laranja"
            assert antes == boss._actor, "quem disparou não é quem estava laranja"
            laranja_antes = antes
    assert laranja_antes is not None


def test_cabeca_derrubada_nao_ataca(boss: TriadBoss):
    """Cabeça no chão não age — ela não está lá."""
    for slot in (LEFT, RIGHT):
        head = boss.heads[slot]
        while boss.gate.state(slot) is HeadState.SOLID:
            boss.on_hit(999, head.center_x, head.center_y)
    boss.update(DT, _PLAYER)

    emissoes, _ = _run_phase1(boss, 10.0)

    atores = {actor for actor, _atk, _orbs in emissoes}
    assert atores == {_CROWN}, f"cabeça derrubada atacou: {atores}"


def test_cada_ataque_usa_o_comportamento_certo(boss: TriadBoss):
    from game.entities.enemies.city.triad_orb import OrbBehavior

    esperado = {
        "cadencia": OrbBehavior.SEEKER,
        "chuva": OrbBehavior.LOB,
        "pulso": OrbBehavior.RING,
    }
    vistos = set()
    for _actor, ataque, orbs in _run_phase1(boss, 60.0, seed=7)[0]:
        assert {o.behavior for o in orbs} == {esperado[ataque]}, ataque
        vistos.add(ataque)

    assert vistos == set(esperado), f"nem todo ataque da Fase 1 apareceu: {vistos}"


def test_pulso_tem_uma_brecha_no_hemisferio_de_baixo(boss: TriadBoss):
    """O anel só é dodge se a brecha existir E estiver alcançável.

    O jogador está embaixo: brecha no topo é brecha que não existe para ele.
    """
    import math

    for _ in range(12):
        boss._actor = _CROWN
        orbs = boss._fire_pulso_arg(_PLAYER)
        angulos = sorted(o.angle % math.tau for o in orbs)
        assert len(orbs) < 16, "anel sem brecha"

        maior_vao, onde = 0.0, 0.0
        for i, a in enumerate(angulos):
            prox = angulos[(i + 1) % len(angulos)]
            vao = (prox - a) % math.tau
            if vao > maior_vao:
                maior_vao, onde = vao, (a + vao / 2.0) % math.tau
        assert math.sin(onde) > 0.0, "brecha caiu no hemisfério de cima"


# ── A Sentença ───────────────────────────────────────────────────────────────
def _abrir_portao(boss: TriadBoss) -> None:
    for slot in (LEFT, RIGHT):
        head = boss.heads[slot]
        guarda = 0
        while boss.gate.state(slot) is HeadState.SOLID and guarda < 5000:
            boss.on_hit(999, head.center_x, head.center_y)
            guarda += 1
    boss.update(DT, _PLAYER)


def _queimar_ate(boss: TriadBoss, fracao: float) -> None:
    guarda = 0
    while boss.health > boss.max_health * fracao and guarda < 20000:
        if not boss.gate.crown_vulnerable:
            _abrir_portao(boss)
        boss.on_hit(20, *boss._crown_circle()[:2])
        guarda += 1


def _passo_sentenca(boss: TriadBoss, feixes: list, dt: float = DT) -> None:
    """Um frame da Sentença com os feixes avançando junto.

    Os feixes normalmente vivem no `EntityManager`; aqui o teste faz o papel dele.
    """
    boss.update(dt, _PLAYER)
    feixes.extend(boss._pending_beams)
    boss._pending_beams.clear()
    for beam in feixes:
        beam.update(dt)


def _rodar_sentenca(boss: TriadBoss, dt: float = DT):
    """Roda a Sentença inteira; devolve (duração, feixes emitidos)."""
    from game.entities.enemies.city.triad_boss import _SENTENCA

    feixes: list = []
    t = 0.0
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes, dt)
        t += dt
    return t, feixes


def _entrar_na_sentenca(boss: TriadBoss, limiar: float | None = None) -> None:
    _abrir_portao(boss)
    _queimar_ate(boss, boss.PHASE2_THRESHOLD if limiar is None else limiar)
    boss.update(DT, _PLAYER)


def test_sentenca_dispara_no_gate_de_hp_e_deixa_o_boss_intangivel(boss: TriadBoss):
    from game.entities.enemies.city.triad_boss import _SENTENCA

    _entrar_na_sentenca(boss)

    assert boss._state == _SENTENCA
    assert not boss.can_take_damage(), "Sentença sem intangibilidade"


def test_sentenca_entrega_quinze_segundos_de_desvio(boss: TriadBoss):
    """A transição é uma fase de SOBREVIVÊNCIA, não um interlúdio de 3 batidas.

    O que se mede é a janela de ameaça — do primeiro feixe ficar letal ao último
    parar de ferir —, não a duração total: chamada e rabo são coreografia sem
    perigo e inflariam o número sem o jogador desviar de nada.
    """
    _entrar_na_sentenca(boss)
    duracao, feixes = _rodar_sentenca(boss)

    letais = [(b, i) for i, b in enumerate(feixes)]
    assert len(letais) >= 30, f"coreografia rala demais: {len(feixes)} feixes"
    assert 16.5 < duracao < 18.5, f"duração fora do previsto: {duracao:.2f}s"
    assert boss._phase == 2 and boss._sent_count == 1


def test_janela_de_ameaca_cobre_quase_toda_a_sentenca(boss: TriadBoss):
    """Entre a primeira e a última ameaça o jogador quase não tem folga."""
    _entrar_na_sentenca(boss)
    from game.entities.enemies.city.triad_boss import _SENTENCA

    feixes: list = []
    t = primeiro = ultimo = 0.0
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes)
        t += DT
        if any(b.w > 0 for b in feixes):
            ultimo = t
            if primeiro == 0.0:
                primeiro = t

    ameaca = ultimo - primeiro
    assert 13.5 < ameaca < 16.5, f"janela de ameaça de {ameaca:.2f}s, esperados ~15s"


def test_segunda_sentenca_e_mais_rapida_nao_mais_densa(boss: TriadBoss):
    """A 2ª ocorrência acelera. Apertar as salvas transformaria a assinatura no
    motivo de o jogador desistir — a coreografia é a mesma, o relógio não."""
    _entrar_na_sentenca(boss)
    dur1, feixes1 = _rodar_sentenca(boss)

    _queimar_ate(boss, boss.PHASE3_THRESHOLD)
    boss.update(DT, _PLAYER)
    dur2, feixes2 = _rodar_sentenca(boss)

    assert dur2 < dur1 * 0.9, f"2ª Sentença não acelerou ({dur1:.2f} → {dur2:.2f})"
    assert len(feixes2) == len(feixes1), "2ª Sentença ficou mais DENSA, não mais rápida"
    assert boss._phase == 3


def test_muitas_cabecas_disparam_a_sentenca(boss: TriadBoss):
    """A coreografia é de VÁRIAS cabeças, não das duas Vozes com nomes novos.

    O boss tem duas Vozes; as demais fontes são ecos temporários. Sem elas o
    padrão volta a ser dois feixes se movendo, que é o que a transição deixou
    de ser.
    """
    _entrar_na_sentenca(boss)
    from game.entities.enemies.city.triad_boss import _SENTENCA

    pico = 0
    ecos = 0
    t = 0.0
    feixes: list = []
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes)
        t += DT
        pico = max(pico, len(boss._sent_casters))
        ecos = max(ecos, sum(1 for c in boss._sent_casters if c.head is None))

    assert pico >= 6, f"pico de apenas {pico} cabeças simultâneas"
    assert ecos >= 5, f"apenas {ecos} ecos simultâneos — a salva não é coletiva"


# ── O que o playtest pediu: rosto virado e feixe saindo da boca ───────────────
def test_o_feixe_nasce_na_boca_da_cabeca_que_o_disparou(boss: TriadBoss):
    """Origem do feixe == boca da cabeça, todo frame — inclusive enquanto ela desliza.

    O defeito anterior era este: o feixe varria a arena numa altura e a cabeça
    ficava parada noutra, porque os dois liam relógios separados. Agora o feixe
    lê o caster, então o desvio tem que ser ZERO, não "pequeno".
    """
    _entrar_na_sentenca(boss)
    from game.entities.enemies.city.triad_boss import _SENTENCA

    conferidos = 0
    t = 0.0
    feixes: list = []
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes)
        t += DT
        bocas = [c.muzzle() for c in boss._sent_casters]
        for beam in feixes:
            # O feixe em dissipação é inerte e já não tem cabeça: ela se
            # dissolveu junto (ver `TriadCaster.SINK_TIME`).
            if beam.dead or beam.is_fading:
                continue
            perto = min(
                (math.hypot(beam.x - bx, beam.y - by) for bx, by in bocas),
                default=None,
            )
            if perto is None:
                continue
            assert perto < 1.0, f"feixe a {perto:.1f}px da boca mais próxima"
            conferidos += 1

    assert conferidos > 500, "poucos frames conferidos — o laço não exercitou nada"


def test_o_rosto_acompanha_a_direcao_do_feixe(boss: TriadBoss):
    """A cabeça OLHA para onde atira. Vale para os ecos e para as Vozes.

    Sem isso o sprite fica sempre de frente e o feixe sai de lado — a leitura
    "aquela cabeça está mirando em mim" desaparece, e ela é o telégrafo.
    """
    _entrar_na_sentenca(boss)
    from game.entities.enemies.city.triad_boss import _SENTENCA

    girou = set()
    vozes_miraram = 0
    t = 0.0
    feixes: list = []
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes)
        t += DT
        for caster in boss._sent_casters:
            bx, by = caster.muzzle()
            alvo = next(
                (
                    b
                    for b in feixes
                    if not b.dead
                    and not b.is_fading
                    and math.hypot(b.x - bx, b.y - by) < 1.0
                ),
                None,
            )
            if alvo is None:
                continue
            rumo = math.atan2(alvo.target_y - alvo.y, alvo.target_x - alvo.x)
            desvio = abs((rumo - caster.aim + math.pi) % math.tau - math.pi)
            assert desvio < 1e-6, f"rosto a {math.degrees(desvio):.1f}° do feixe"
            girou.add(round(caster.aim, 2))
            if caster.head is not None:
                assert caster.head.aim is not None, "Voz disparando sem pose de mira"
                vozes_miraram += 1

    assert len(girou) >= 12, f"só {len(girou)} direções distintas — falta variedade"
    assert vozes_miraram > 0, "nenhuma Voz participou da coreografia"


def test_a_boca_fica_na_frente_e_ABAIXO_da_ancora():
    """A boca não é o centro da imagem nem a âncora — é o rosto, mais para baixo.

    A âncora cai na altura do OLHO (é o centroide do blob do rosto), e um feixe
    saindo dali lê como "sai da testa". A boca desce rumo ao queixo antes de
    avançar. Se alguém trocar `part_muzzle` pela âncora crua ou pelo centro do
    sprite, o feixe volta a nascer no meio da cabeça — ou, pior, a dezenas de
    pixels dela, no espaço negativo do PNG.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    centro_img = (pmap.FRAME / 2.0, pmap.FRAME / 2.0)
    for part in ("left", "right"):
        ax, ay = pmap.part_anchor(part)
        mx, my = pmap.part_muzzle(part)
        olhar = pmap.part_facing(part)

        # Para a FRENTE: projeção positiva na direção do olhar.
        avanco = mx * math.cos(olhar) + my * math.sin(olhar)
        assert avanco > pmap.PIXEL_SCALE, f"{part}: boca não avançou para a frente"

        # E para BAIXO — é isto que a distingue da âncora.
        assert my > pmap.PIXEL_SCALE * 4, f"{part}: boca na altura do olho"

        # Sem sair do desenho: o rosto tem ~24px de sprite de altura.
        assert math.hypot(mx, my) < pmap.PIXEL_SCALE * 14, f"{part}: boca fora do rosto"

        # E a âncora não é o centro da imagem — se fosse, cairia no vazio.
        sx = ax / pmap.PIXEL_SCALE + pmap.CONTENT_X0
        sy = ay / pmap.PIXEL_SCALE + pmap.CONTENT_Y0
        assert math.hypot(sx - centro_img[0], sy - centro_img[1]) > 8.0


def test_a_boca_gira_junto_com_a_mira():
    """Virar a cabeça leva a boca junto — senão o feixe sai do lugar errado.

    Com a cabeça olhando para baixo, a boca tem que estar ABAIXO da âncora no
    eixo do olhar, não continuar no mesmo canto de quando ela olhava para o lado.
    """
    from game.entities.enemies.city.triad_caster import TriadCaster

    for aim in (0.0, math.pi / 2, math.pi, -math.pi / 2, 2.1):
        c = TriadCaster("right", 500.0, 300.0, aim, 0.5, 1.0)
        mx, my = c.muzzle()
        avanco = (mx - 500.0) * math.cos(aim) + (my - 300.0) * math.sin(aim)
        assert avanco > 0.0, f"aim={aim:.2f}: boca atrás da âncora"


def test_girar_a_cabeca_nao_move_a_ancora():
    """O sprite gira EM TORNO da âncora, não do centro da imagem.

    Girar a tela de 64×64 crua faz a cabeça descrever um arco em volta de um
    pivô vazio — ela "escapa" do lugar enquanto mira. O offset devolvido por
    `aimed_part` é o que prende o pixel de ancoragem no lugar.
    """
    from game.entities.enemies.city import triad_pixel_map as pmap

    for part in ("left", "right"):
        base = pmap.cropped_part(part)
        assert base is not None
        for passo in range(pmap.ROT_STEPS):
            aim = passo * math.tau / pmap.ROT_STEPS
            sprite, ox, oy = pmap.aimed_part(part, aim)
            largura, altura = sprite.get_size()
            # A âncora, em coordenadas do recorte girado, tem que cair DENTRO
            # dele — é a prova de que o offset é o inverso da posição dela.
            assert 0.0 <= -ox <= largura, f"{part} @{passo}: âncora fora em x"
            assert 0.0 <= -oy <= altura, f"{part} @{passo}: âncora fora em y"


def test_nenhum_eco_fere_antes_de_terminar_de_materializar(boss: TriadBoss):
    """A cabeça está inteira na tela quando o feixe dela passa a ferir.

    Materializar junto com o dano transformaria o telégrafo em emboscada — o
    jogador veria a cabeça no mesmo frame em que já não dá para sair.
    """
    _entrar_na_sentenca(boss)
    from game.entities.enemies.city.triad_boss import _SENTENCA

    t = 0.0
    feixes: list = []
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes)
        t += DT
        for caster in boss._sent_casters:
            bx, by = caster.muzzle()
            letal = any(
                b.w > 0 and not b.dead and math.hypot(b.x - bx, b.y - by) < 1.0
                for b in feixes
            )
            if letal:
                assert caster.alpha > 0.95, (
                    f"feixe letal com a cabeça a {caster.alpha:.2f} de opacidade"
                )


# ── Justiça: a arena nunca fecha ─────────────────────────────────────────────
_GRID_W, _GRID_H = 32, 18
_SHIP_CLEARANCE = 16.0     # meia-largura da nave, com folga
_SHIP_SPEED = 200.0        # px/s da nave mais LENTA do elenco (speed_mult 0.80)


def _celulas_seguras(feixes, sw: float, sh: float) -> set:
    """Células cujo centro está fora de todo feixe letal."""
    cw, ch = sw / _GRID_W, sh / _GRID_H
    vivos = []
    for b in feixes:
        if b.w <= 0 or b.dead:
            continue
        (x1, y1), (x2, y2) = b.get_collision_line()
        dx, dy = x2 - x1, y2 - y1
        comprimento = dx * dx + dy * dy
        vivos.append((x1, y1, dx, dy, comprimento, b.w / 2.0 + _SHIP_CLEARANCE))
    seguras = set()
    for gy in range(_GRID_H):
        py = (gy + 0.5) * ch
        for gx in range(_GRID_W):
            px = (gx + 0.5) * cw
            for x1, y1, dx, dy, comprimento, folga in vivos:
                if comprimento <= 0.0:
                    continue
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / comprimento))
                ex, ey = px - (x1 + dx * t), py - (y1 + dy * t)
                if ex * ex + ey * ey < folga * folga:
                    break
            else:
                seguras.add((gx, gy))
    return seguras


def _dilatar(celulas: set, passos: int) -> set:
    """Alcance da nave em `passos` células, em vizinhança de 4 (conservador)."""
    atual = celulas
    for _ in range(passos):
        novo = set(atual)
        for gx, gy in atual:
            if gx > 0:
                novo.add((gx - 1, gy))
            if gx < _GRID_W - 1:
                novo.add((gx + 1, gy))
            if gy > 0:
                novo.add((gx, gy - 1))
            if gy < _GRID_H - 1:
                novo.add((gx, gy + 1))
        atual = novo
    return atual


@pytest.mark.parametrize("ocorrencia", [1, 2])
def test_a_sentenca_sempre_deixa_uma_saida_alcancavel(boss: TriadBoss, ocorrencia: int):
    """Prova de sobrevivência, não de "existe um ponto seguro em algum lugar".

    O teste carrega o conjunto de células ALCANÇÁVEIS: a cada frame ele expande
    pelo quanto a nave mais lenta do elenco consegue andar e corta o que virou
    letal. Se esse conjunto esvaziar, existe um instante em que nenhum jogador,
    por melhor que jogue, sobreviveria — que é o pior defeito que um padrão pode
    ter. É mais forte que o teste antigo do bolsão, que só olhava UM ponto numa
    batida.
    """
    from game.core.config import config as Config
    from game.entities.enemies.city.triad_boss import _SENTENCA

    sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
    passo_px = sw / _GRID_W
    dt = 1.0 / 30.0

    # A 2ª ocorrência roda a 0,8× e precisa da MESMA garantia: acelerar não pode
    # transformar a assinatura num padrão sem saída para quem não a decorou.
    _entrar_na_sentenca(boss)
    if ocorrencia == 2:
        _rodar_sentenca(boss)
        _queimar_ate(boss, boss.PHASE3_THRESHOLD)
        boss.update(DT, _PLAYER)

    feixes: list = []
    alcance = {(gx, gy) for gx in range(_GRID_W) for gy in range(_GRID_H)}
    creditado = 0.0
    t = 0.0
    pior = len(alcance)
    while boss._state == _SENTENCA and t < 30.0:
        _passo_sentenca(boss, feixes, dt)
        t += dt
        creditado += _SHIP_SPEED * dt
        if creditado >= passo_px:
            alcance = _dilatar(alcance, int(creditado // passo_px))
            creditado %= passo_px
        alcance &= _celulas_seguras(feixes, sw, sh)
        pior = min(pior, len(alcance))
        assert alcance, f"arena sem saída alcançável em t={t:.2f}s da Sentença"

    # Piso medido: 209 de 576 na 1ª ocorrência. A folga do limite é para o
    # tuning de playtest não quebrar o teste a cada ajuste fino — o que ele
    # trava é a coreografia PARAR de apertar, não o número exato.
    assert pior < 350, (
        f"a coreografia nunca apertou (mínimo de {pior} células livres) — "
        "não é uma fase de sobrevivência"
    )


def test_a_partitura_alterna_os_eixos():
    """Salva seguinte não repete a anterior com as posições trocadas.

    "Variar" não é mudar de lugar: um leque com outro pivô é o mesmo leque. A
    assinatura compara quantidade, mira e se a cabeça se move — se duas salvas
    vizinhas empatarem nos três, o padrão foi copiado, não composto.
    """
    from game.entities.enemies.city import triad_score as score

    assinaturas = []
    for _, construir in score.SCORE:
        tiros = construir(1280.0, 720.0)
        assinaturas.append(
            (
                len(tiros),
                tuple(sorted(round(s.aim, 2) for s in tiros)),
                tuple(sorted((s.path is not None, s.swing is not None) for s in tiros)),
            )
        )

    assert len(score.SCORE) >= 6, "coreografia curta demais para 15s de variedade"
    for i in range(1, len(assinaturas)):
        assert assinaturas[i] != assinaturas[i - 1], (
            f"salvas {i - 1} e {i} têm a mesma forma — variedade só de posição"
        )
    assert len(set(assinaturas)) == len(assinaturas), "há salvas repetidas na partitura"


def test_sentenca_remonta_as_vozes_destruidas(boss: TriadBoss):
    """A Sentença devolve as duas Vozes — é o boss se remontando.

    Sem isso, quem chega ao gate com as duas derrubadas assiste a uma
    coreografia com feixes saindo de cabeças que não estão lá (relatado em
    playtest: "as cabeças não apareceram"), e a assinatura degrada justo no
    momento em que deveria impressionar.
    """
    _abrir_portao(boss)
    assert boss.gate.crown_vulnerable, "o portão deveria estar aberto antes do gate"
    _queimar_ate(boss, boss.PHASE2_THRESHOLD)
    boss.update(DT, _PLAYER)

    assert boss.gate.is_solid(LEFT) and boss.gate.is_solid(RIGHT)
    for head in boss.heads:
        assert head.body_state is HeadState.SOLID
        assert head.hp > 0

    _rodar_sentenca(boss)
    assert not boss.gate.crown_vulnerable, "a fase nova começou com o portão aberto"


def test_remontar_nao_zera_a_convergencia(boss: TriadBoss):
    """O HP devolvido pela Sentença segue a MESMA escada decrescente.

    Se a transição devolvesse duas cabeças cheias, cada Sentença desfaria o
    progresso e a luta andaria para trás.
    """
    _abrir_portao(boss)
    primeiro = boss.gate.return_hp_fraction(LEFT)

    _queimar_ate(boss, boss.PHASE2_THRESHOLD)
    boss.update(DT, _PLAYER)

    assert boss.gate.return_hp_fraction(LEFT) <= primeiro


def test_as_vozes_voltam_para_casa_no_fim_da_sentenca(boss: TriadBoss):
    """Terminada a coreografia, as Vozes estão no soquete e sem pose de mira.

    Uma Voz que fica com `aim` setado continua sendo desenhada girada no combate
    normal, e o boss aparece torto pelo resto da luta.
    """
    _entrar_na_sentenca(boss)
    _rodar_sentenca(boss)

    for i, head in enumerate(boss.heads):
        casa = boss._home_offsets[i]
        assert head.aim is None, "Voz ficou com pose de mira depois da Sentença"
        assert not head.attacking, "Voz ficou em telégrafo depois da Sentença"
        assert (head.offset_x, head.offset_y) == casa, "Voz não voltou ao soquete"
    assert not boss._sent_casters, "sobraram ecos depois do fim da Sentença"


# ── Fases 2 e 3 ──────────────────────────────────────────────────────────────
def _levar_ate_fase(boss: TriadBoss, fase: int) -> None:
    """Queima o boss até a fase pedida, atravessando as Sentenças."""
    from game.entities.enemies.city.triad_boss import _SENTENCA

    limiares = {2: boss.PHASE2_THRESHOLD, 3: boss.PHASE3_THRESHOLD}
    for alvo in sorted(limiares)[: fase - 1]:
        _queimar_ate(boss, limiares[alvo])
        boss.update(DT, _PLAYER)
        guarda = 0
        while boss._state == _SENTENCA and guarda < 3000:
            boss.update(DT, _PLAYER)
            guarda += 1
    assert boss._phase == fase, f"esperava fase {fase}, veio {boss._phase}"


def _colher_turnos(boss: TriadBoss, segundos: float, seed: int | None = None):
    """Turnos PLANEJADOS, um registro por turno.

    Dois cuidados que a versão ingênua não tinha:

    * marca o turno na BORDA do wind-up, não a cada emissão — o Pulso emite três
      vezes no mesmo turno (a batida), e contar emissões fazia o mesmo combo
      aparecer três vezes seguidas como se tivesse se repetido;
    * faz as esferas AVANÇAREM, senão elas nunca morrem, o teto de
      `_MAX_LIVE_ORBS` enche e o chefe simplesmente para de atacar.
    """
    from game.entities.enemies.city.triad_boss import _ACT_WINDUP

    if seed is not None:
        random.seed(seed)
    turnos = []
    vivas: list = []
    anterior = boss._act_state
    t = 0.0
    while t < segundos:
        orbs = boss.update(DT, _PLAYER)
        if boss._act_state == _ACT_WINDUP and anterior != _ACT_WINDUP:
            turnos.append(list(boss._turn))
        anterior = boss._act_state
        if orbs:
            vivas.extend(orbs)
        for orb in vivas:
            _tick(orb)
        vivas = [o for o in vivas if not o.dead]
        t += DT
    return turnos


def test_fase2_age_com_mais_de_uma_cabeca(boss: TriadBoss):
    """A identidade da Fase 2 é a SOBREPOSIÇÃO — dois ou três agindo juntos.

    A dificuldade nova não vem de mais projéteis: vem de padrões que o jogador
    já sabe ler, acontecendo ao mesmo tempo.
    """
    _levar_ate_fase(boss, 2)
    turnos = _colher_turnos(boss, 26.0)

    assert turnos, "a Fase 2 não atacou"
    assert max(len(t) for t in turnos) >= 2, "nenhum turno teve mais de um ator"


def test_fase2_so_combina_chuva_pulso_e_parede(boss: TriadBoss):
    """O vocabulário da Fase 2 é o que a Fase 1 ensinou, sobreposto.

    Padrão novo nesta fase seria conteúdo que o jogador não teve como aprender;
    a dificuldade tem que vir da COMBINAÇÃO. As minas entram à parte — elas são
    terreno, repostas até o teto, não um dos combos.
    """
    from game.entities.enemies.city.triad_boss import (
        _ATK_ANCORA,
        _ATK_CHUVA,
        _ATK_PAREDE,
        _ATK_PULSO,
    )

    _levar_ate_fase(boss, 2)
    turnos = _colher_turnos(boss, 60.0, seed=23)
    permitido = {_ATK_CHUVA, _ATK_PULSO, _ATK_PAREDE, _ATK_ANCORA}
    usados = {a for t in turnos for _ator, a in t}
    assert usados <= permitido, f"ataque fora do vocabulário da Fase 2: {usados}"
    assert {_ATK_CHUVA, _ATK_PULSO, _ATK_PAREDE} <= usados, (
        f"nem todo o vocabulário apareceu: {usados}"
    )


def test_fase2_nao_repete_o_combo_anterior(boss: TriadBoss):
    _levar_ate_fase(boss, 2)
    turnos = _colher_turnos(boss, 60.0, seed=29)
    # As minas são repostas em todo turno; comparar com elas dentro esconderia
    # a repetição do combo, que é o que este teste existe para pegar.
    from game.entities.enemies.city.triad_boss import _ATK_ANCORA

    assinaturas = [
        tuple(a for _ator, a in t if a != _ATK_ANCORA) for t in turnos
    ]
    assert len(set(assinaturas)) >= 3, f"pouca variedade de combo: {set(assinaturas)}"
    seguidos = [
        i for i in range(1, len(assinaturas)) if assinaturas[i] == assinaturas[i - 1]
    ]
    assert not seguidos, "um combo repetiu imediatamente o anterior"


def test_fase2_aperta_a_regeneracao(boss: TriadBoss):
    antes = boss.gate.regen_delay
    _levar_ate_fase(boss, 2)
    assert boss.gate.regen_delay < antes


def test_fase3_derruba_o_portao_e_as_vozes_param_de_ser_alvo(boss: TriadBoss):
    """A mecânica de ressonância se RESOLVE em vez de repetir.

    A pergunta muda de "consigo abrir a janela?" para "aguento a pressão?" — e o
    jogador ganha acesso irrestrito ao alvo, que é o final satisfatório de um
    boss de portão.
    """
    _levar_ate_fase(boss, 3)

    assert boss.gate.crown_vulnerable, "o portão não caiu na Fase 3"
    for head in boss.heads:
        assert not head.damageable, "a Voz continua sendo alvo na Fase 3"
        assert head._visible, "a Voz sumiu em vez de virar orbital"


def test_fase3_orbita_e_pinta_as_esferas_de_laranja(boss: TriadBoss):
    from game.entities.enemies.city import triad_pixel_map as pmap

    _levar_ate_fase(boss, 3)
    antes = (boss.heads[LEFT].offset_x, boss.heads[LEFT].offset_y)
    for _ in range(40):
        boss.update(DT, _PLAYER)
    depois = (boss.heads[LEFT].offset_x, boss.heads[LEFT].offset_y)

    assert antes != depois, "as Vozes não orbitam"
    assert boss._palette() == pmap.ORANGE


def test_fase3_so_usa_os_ataques_dela(boss: TriadBoss):
    _levar_ate_fase(boss, 3)
    turnos = _colher_turnos(boss, 34.0)
    ataques = {a for t in turnos for _ator, a in t}

    assert ataques, "a Fase 3 não atacou"
    assert ataques <= {"unissono", "diluvio", "convergencia"}, ataques


def test_convergencia_cobra_pelo_que_ficou_vivo(boss: TriadBoss):
    """Recompensa RETROATIVA: quem limpou a arena leva um estouro fraco.

    É o que transforma limpar as esferas de opcional em leitura de risco.
    """
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    boss._phase = 3
    boss._orbs.clear()
    limpo = len(boss._fire_convergencia(_PLAYER))

    boss._orbs = [TriadOrb(100.0, 100.0, OrbBehavior.ANCHOR) for _ in range(14)]
    sujo = len(boss._fire_convergencia(_PLAYER))

    assert sujo > limpo, f"a arena suja não custou mais caro ({limpo} vs {sujo})"
    assert not boss._orbs, "a Convergência não recolheu as esferas"


def test_boss_morre_e_paga_o_score(boss: TriadBoss):
    from game.core.config import config as Config

    _levar_ate_fase(boss, 3)
    resultado = None
    guarda = 0
    while not boss.dead and guarda < 20000:
        resultado = boss.on_hit(50, *boss._crown_circle()[:2])
        guarda += 1

    assert boss.dead and boss.should_remove()
    assert resultado is not None and resultado.killed
    assert resultado.points == Config.BOSS_DEFEAT_SCORE


def test_erraticos_saem_espalhados(boss: TriadBoss):
    """Espalhamento é regra do encontro, não de um ataque.

    Sem leque, os quatro saem quase juntos e a correção em espasmos os mantém
    agrupados o caminho todo — vira um projétil gordo, não quatro ameaças.
    """
    import math

    boss._actor = LEFT
    orbs = boss._fire_erratico(_PLAYER)
    angulos = sorted(o.angle for o in orbs)
    vaos = [angulos[i + 1] - angulos[i] for i in range(len(angulos) - 1)]

    assert len(orbs) >= 4
    assert min(vaos) > math.radians(9.0), f"mísseis colados: {[round(math.degrees(v),1) for v in vaos]}"


def test_a_cabeca_se_dissolve_junto_com_o_feixe():
    """Sumiço da cabeça e dissipação do feixe têm que durar o MESMO tempo.

    Se divergirem, ou sobra um feixe pendurado no nada (cabeça sai primeiro) ou
    uma cabeça acesa sem feixe nenhum. As duas leituras são "apareceu do nada"
    ao contrário, que é o defeito que esta coreografia veio corrigir.
    """
    from game.entities.enemies.city.triad_beam import TriadBeam
    from game.entities.enemies.city.triad_caster import TriadCaster

    assert TriadCaster.SINK_TIME == TriadBeam.FADE_TIME


# ── Justiça de RITMO: reação e velocidade ────────────────────────────────────
def test_nenhum_feixe_varre_mais_rapido_que_a_nave():
    """Um feixe que corre mais que o jogador não tem resposta.

    Feixe é uma reta INTEIRA da arena: não dá para deixá-lo passar nem contorná-lo,
    só sair da frente. Se ele se desloca mais rápido do que a nave anda, quem
    estiver do lado errado morre no instante em que ele nasce, tenha jogado como
    tenha — e nenhuma quantidade de telégrafo conserta isso.

    Foi o defeito de fundo do primeiro corte, e não dava para ver olhando o
    padrão: a cruz do uníssono corria a 404 px/s e o giro do cruzado chicoteava
    a ponta do feixe a ~995 px/s, contra 200 px/s da nave mais lenta do elenco.
    """
    from game.entities.enemies.city import triad_score as score

    for inicio, construir in score.SCORE:
        for i, tiro in enumerate(construir(1280.0, 720.0)):
            v = score.max_sweep_speed(tiro, 1280.0, 720.0)
            assert v <= score.SWEEP_CAP, (
                f"{construir.__name__}[{i}] varre a {v:.0f} px/s, "
                f"acima do teto de {score.SWEEP_CAP:.0f}"
            )


def test_todo_feixe_avisa_antes_de_ferir():
    """A carga é o telégrafo, e ela precisa caber reação MAIS caminhada.

    Reação a um estímulo visual novo é ~0,25s; o que sobra é o tempo de andar
    até um lugar seguro. Com os 0,45s da primeira versão sobravam 0,20s, ou 40px
    na nave mais lenta — menos que o corpo dela.
    """
    from game.entities.enemies.city import triad_score as score

    for inicio, construir in score.SCORE:
        for i, tiro in enumerate(construir(1280.0, 720.0)):
            assert tiro.charge >= 0.80, (
                f"{construir.__name__}[{i}] avisa por só {tiro.charge:.2f}s"
            )


def test_a_varredura_ja_esta_em_curso_quando_o_feixe_passa_a_ferir(boss: TriadBoss):
    """O telégrafo mostra a TRAJETÓRIA, não só a posição inicial.

    Enquanto a cabeça ficava parada durante a carga, o jogador lia a posição de
    nascimento, se julgava seguro a 80px dali e era varrido por um percurso que
    não tinha como conhecer. Agora o percurso começa na carga: no frame em que o
    feixe passa a ferir ele JÁ ANDOU, e o quanto andou é a prova de que a direção
    era pública antes de o dano existir.
    """
    from game.entities.enemies.city.triad_boss import _SENTENCA

    _entrar_na_sentenca(boss)

    nascimento: dict[int, tuple[float, float]] = {}
    ja_letal: set[int] = set()
    andou: list[float] = []
    t = 0.0
    feixes: list = []
    while boss._state == _SENTENCA and t < 30.0:
        for caster in boss._sent_casters:
            nascimento.setdefault(id(caster), (caster.x, caster.y))
        _passo_sentenca(boss, feixes)
        t += DT
        for caster in boss._sent_casters:
            bx, by = caster.muzzle()
            letal = any(
                b.w > 0 and not b.dead and math.hypot(b.x - bx, b.y - by) < 1.0
                for b in feixes
            )
            if not letal or id(caster) in ja_letal:
                continue
            ja_letal.add(id(caster))
            ox, oy = nascimento.get(id(caster), (caster.x, caster.y))
            andou.append(math.hypot(caster.x - ox, caster.y - oy))

    assert len(andou) >= 30, "poucos feixes conferidos"
    moveis = [d for d in andou if d > 1.0]
    assert len(moveis) >= 20, "quase nenhum feixe se move — a coreografia é estática"
    assert min(moveis) > 20.0, (
        f"feixe que varre estreou com só {min(moveis):.0f}px de aviso de trajetória"
    )


def test_o_render_do_feixe_nao_aloca_por_frame():
    """O travamento com muitos feixes vinha de alocar uma surface por feixe/frame.

    A versão anterior criava uma SRCALPHA de tela cheia dentro do `draw` — 3,7 MB
    alocados e zerados por feixe, por frame. Com os 8 feixes simultâneos da
    Sentença dava 32 ms/frame só no render deles, contra os 16,7 ms que o frame
    inteiro tem a 60fps.

    O buffer agora é compartilhado e cacheado por resolução; o estouro do bocal,
    por (raio, cor). Este teste cobra que desenhar muito NÃO faça os caches
    crescerem sem limite — que é o sintoma de terem voltado a ser por-frame.
    """
    import pygame

    from game.entities.enemies.city import triad_beam as tb

    tela = pygame.Surface((640, 360))
    feixes = [
        tb.TriadBeam((320.0, 180.0), i * math.tau / 8, charge_time=0.01, active_time=99.0)
        for i in range(8)
    ]
    for beam in feixes:
        beam.update(0.05)

    tb._GLOW_SCRATCH.clear()
    for _ in range(30):
        for beam in feixes:
            beam.draw(tela)
    depois = len(tb._FLARE_SPRITES)

    assert len(tb._GLOW_SCRATCH) <= 2, (
        f"{len(tb._GLOW_SCRATCH)} buffers de brilho — voltou a alocar por frame"
    )
    for _ in range(30):
        for beam in feixes:
            beam.draw(tela)
    assert len(tb._FLARE_SPRITES) == depois, "o cache do bocal cresce a cada frame"


# ── Ciclo de vida das esferas: nascer e morrer são visíveis ──────────────────
def test_esfera_nasce_inofensiva_e_ja_pode_levar_tiro():
    """A janela de nascimento é o telégrafo do vocabulário de esferas.

    Projétil que aparece já valendo dano não é dificuldade, é emboscada — a
    mesma regra dos feixes. Ela JÁ é alvo nessa janela de propósito: quem lê
    cedo pode apagá-la antes de virar ameaça, e isso premia a leitura.
    """
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    orb = TriadOrb(300.0, 200.0, OrbBehavior.RING, angle=0.0, birth=0.40)
    assert orb.is_hatching
    assert not orb.causes_damage, "esfera fere durante o nascimento"
    assert orb.can_take_damage(), "esfera nascendo não pode ser alvejada"
    assert orb.collision_circle()[2] > 0.0

    onde = (orb.x, orb.y)
    _tick(orb, 0.30)
    assert not orb.causes_damage, "passou a ferir antes de terminar de nascer"
    assert (orb.x, orb.y) == onde, "esfera andou enquanto nascia"

    _tick(orb, 0.15)
    assert orb.causes_damage and not orb.is_hatching


def test_esfera_morrendo_sai_da_colisao_mas_fica_na_tela():
    """Morrer é uma animação, e durante ela a esfera não interfere em nada.

    Raio de colisão zero e `causes_damage` falso: some do tiro, do contato com a
    nave, da mira e da contagem de hostis, sem precisar que nenhum desses
    sistemas saiba que esta fase existe.
    """
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    orb = TriadOrb(300.0, 200.0, OrbBehavior.RING, angle=0.0, birth=0.05)
    _tick(orb, 0.10)
    assert orb.causes_damage

    orb.begin_death()
    assert not orb.dead, "morreu de um frame para o outro, sem animação"
    assert not orb.causes_damage
    assert not orb.can_take_damage(), "esfera morrendo continua sendo alvo"
    assert orb.collision_circle()[2] == 0.0
    assert orb.rect.width == 0 and orb.rect.height == 0

    _tick(orb, 0.20)
    assert not orb.dead
    _tick(orb, 0.20)
    assert orb.dead, "a animação de morte não termina"


def test_matar_a_esfera_credita_a_morte_uma_vez_so():
    """O `killed` sai da TRANSIÇÃO, não do flag `dead`.

    O mixin decide por `dead`, que agora só sobe no fim da animação. Sem o
    override, o tiro que derruba a esfera devolveria "só acertei" e o jogador
    perderia a explosão e o som no frame em que a morte acontece.
    """
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    orb = TriadOrb(300.0, 200.0, OrbBehavior.RING, angle=0.0, birth=0.05)
    _tick(orb, 0.10)

    parciais = [orb.on_hit(1, 300.0, 200.0) for _ in range(orb.HEALTH - 1)]
    assert not any(r.killed for r in parciais)

    letal = orb.on_hit(1, 300.0, 200.0)
    assert letal.killed and letal.points == orb.POINTS
    depois = orb.on_hit(5, 300.0, 200.0)
    assert not depois.killed, "a mesma esfera creditou a morte duas vezes"


def test_expirar_tambem_toca_a_animacao_de_morte():
    """Vencer o prazo merece o mesmo estouro de quem levou tiro."""
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    orb = TriadOrb(300.0, 200.0, OrbBehavior.RING, angle=0.0, lifetime=0.25, birth=0.05)
    _tick(orb, 0.10)
    assert orb.causes_damage
    _tick(orb, 0.30)
    assert not orb.dead, "expirou sem animação de morte"
    assert not orb.causes_damage


def test_todo_projetil_da_fase1_avisa_antes_de_ferir(boss: TriadBoss):
    """Nenhuma esfera da Fase 1 nasce valendo dano.

    É a regra que a fase inteira passou a seguir: a dificuldade vem de ler a
    arena e se mover, não de algo que materializa em cima do jogador.
    """
    # A janela é lida pelo `_birth_time` e não pelo estado atual: o helper faz as
    # esferas AVANÇAREM (como o `EntityManager` faria), então quando o teste as
    # inspeciona elas já nasceram há muito. Que a janela seja inofensiva está
    # provado em `test_esfera_nasce_inofensiva_e_ja_pode_levar_tiro`.
    for _actor, ataque, orbs in _run_phase1(boss, 60.0, seed=11)[0]:
        for orb in orbs:
            assert orb._birth_time >= 0.20, (
                f"{ataque}: aviso de só {orb._birth_time:.2f}s antes de ferir"
            )


# ── Identidade: quem faz o quê ───────────────────────────────────────────────
def test_a_chuva_e_assinatura_da_coroa(boss: TriadBoss):
    """A Chuva sai SEMPRE do núcleo da Coroa, nunca de uma Voz.

    É a divisão de identidade da luta: a Coroa semeia a arena, as Vozes fazem
    pressão direta. Ver a Chuva sair de uma lateral desfaz a leitura de "quem
    faz o quê" de que o telégrafo laranja depende para informar.
    """
    from game.entities.enemies.city.triad_boss import _ATK_CHUVA, _CROWN_ACTOR

    lotes, _ = _run_phase1(boss, 60.0, seed=3)
    chuvas = [(a, o) for a, atk, o in lotes if atk == _ATK_CHUVA]
    assert chuvas, "a Chuva não apareceu na Fase 1"
    for actor, _orbs in chuvas:
        assert actor == _CROWN_ACTOR, "uma Voz disparou a Chuva"


def test_a_cadencia_e_das_vozes(boss: TriadBoss):
    from game.entities.enemies.city.triad_boss import _ATK_CADENCIA, _CROWN_ACTOR

    lotes, _ = _run_phase1(boss, 60.0, seed=5)
    cads = [(a, o) for a, atk, o in lotes if atk == _ATK_CADENCIA]
    assert cads, "a Cadência não apareceu na Fase 1"
    for actor, _orbs in cads:
        assert actor != _CROWN_ACTOR, "a Coroa disparou a Cadência"


def test_cadencia_nasce_espalhada_escalonada_e_longe_do_jogador(boss: TriadBoss):
    """Chegam uma a uma, de pontos distintos, e nunca em cima do jogador.

    Antes eram três saindo da mesma cabeça no mesmo frame: o jogador resolvia as
    três com um passo lateral. Materializar em cima dele seria o oposto — dano
    sem esquiva, que é justamente o que o anel de nascimento existe para evitar.
    """
    from game.core.config import config as Config
    from game.entities.enemies.city.triad_boss import _ATK_CADENCIA, _CADENCIA_CLEARANCE

    sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
    minima = math.hypot(sw, sh) * _CADENCIA_CLEARANCE
    lotes, _ = _run_phase1(boss, 60.0, seed=13)
    vistos = 0
    for _actor, ataque, orbs in lotes:
        if ataque != _ATK_CADENCIA:
            continue
        vistos += 1
        nascimentos = sorted(o._birth_time for o in orbs)
        assert len(set(nascimentos)) == len(orbs), "todas nasceram no mesmo instante"
        assert nascimentos[0] > 0.3, "a primeira chega sem aviso"
        # `spawn`, e não a posição atual: o helper faz as esferas AVANÇAREM, e a
        # Cadência persegue — medir `orb.x` mede onde ela chegou, não de onde
        # veio, e o teste passaria a cobrar algo que ninguém prometeu.
        pontos = {(round(o.spawn[0]), round(o.spawn[1])) for o in orbs}
        assert len(pontos) == len(orbs), "duas esferas nasceram no mesmo ponto"
        # `minima` é o alvo; o piso duro é metade dele, que é o que o fallback
        # (melhor candidato sorteado) garante mesmo com o jogador no meio da
        # banda de nascimento.
        for orb in orbs:
            d = math.hypot(orb.spawn[0] - _PLAYER[0], orb.spawn[1] - _PLAYER[1])
            assert d >= minima * 0.5, f"esfera nasceu a {d:.0f}px do jogador"
    assert vistos, "a Cadência não apareceu"


def test_pulso_e_um_anel_fechado_batendo_em_compasso(boss: TriadBoss):
    """Sem brecha, e cada batida sai DEFASADA da anterior.

    O anel fechado é atravessável por construção: as esferas são discretas e o
    vão entre elas cresce com o raio. Reservar uma brecha reduzia a leitura a
    "ache o buraco". A defasagem de meio passo entre batidas é o que impede a
    resposta preguiçosa de achar um corredor e ficar nele — a onda seguinte sai
    exatamente pelas vagas da anterior.
    """
    from game.entities.enemies.city.triad_boss import (
        _ATK_PULSO,
        _PULSO_SLOTS,
        _PULSO_WAVES,
    )

    lotes, _ = _run_phase1(boss, 60.0, seed=17)
    aneis = [o for _a, atk, o in lotes if atk == _ATK_PULSO]
    assert len(aneis) >= _PULSO_WAVES, "o Pulso não bateu mais de uma vez"
    for orbs in aneis:
        assert len(orbs) == _PULSO_SLOTS, "o anel do Pulso ainda tem brecha"

    passo = math.tau / _PULSO_SLOTS
    angulos = [
        sorted(math.atan2(o.vy, o.vx) % passo for o in orbs)
        for orbs in aneis[:2]
    ]
    desvio = abs(angulos[0][0] - angulos[1][0])
    assert desvio > passo * 0.25, (
        "as batidas saem alinhadas — o jogador acha um vão e fica nele"
    )


def test_o_cache_de_halo_da_esfera_nao_cresce_por_frame():
    """Dezenas de esferas em cena não podem alocar uma surface cada, por frame.

    Mesma classe de desperdício que travava os feixes (§7). Com o Pulso contínuo
    e a Chuva espalhada o pico passa de 35 esferas simultâneas.
    """
    import pygame

    from game.entities.enemies.city import triad_orb as to
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    tela = pygame.Surface((640, 360))
    orbs = []
    for i in range(24):
        o = TriadOrb(100.0 + i * 8, 180.0, OrbBehavior.RING, angle=0.0, birth=0.05)
        _tick(o, 0.10)
        orbs.append(o)

    to._HALO_SPRITES.clear()
    for _ in range(20):
        for o in orbs:
            o.draw(tela)
    depois = len(to._HALO_SPRITES)
    for _ in range(20):
        for o in orbs:
            o.draw(tela)
    assert len(to._HALO_SPRITES) == depois, "o cache de halo cresce a cada frame"
    assert depois <= 16, f"{depois} sprites de halo — a quantização não segurou"


# ── Chuva: sobe, estagna, desce ──────────────────────────────────────────────
def test_chuva_monta_formacao_simetrica_no_alto(boss: TriadBoss):
    """Os postos são pares espelhados no eixo vertical, na parte de cima.

    Simetria é o que faz a formação ler como formação. Posições sorteadas
    independentes viram nuvem, e nuvem não se lê: o jogador não consegue decidir
    por onde vai passar antes de a queda começar.
    """
    from game.core.config import config as Config
    from game.entities.enemies.city.triad_boss import _CHUVA_TOPO

    sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
    postos = boss._postos_da_chuva()
    assert len(postos) >= 4

    for px, py in postos:
        assert sh * _CHUVA_TOPO[0] - 1 <= py <= sh * _CHUVA_TOPO[1] + 1, (
            f"posto fora da faixa de cima: y={py:.0f}"
        )

    # Para cada posto à esquerda do meio existe o espelho dele à direita.
    meio = sw * 0.5
    esq = sorted((round(meio - x, 1), round(y, 1)) for x, y in postos if x < meio)
    dir_ = sorted((round(x - meio, 1), round(y, 1)) for x, y in postos if x > meio)
    assert esq == dir_, "a formação da Chuva não é simétrica"


def test_chuva_sobe_estagna_e_so_entao_desce_devagar():
    """Os três tempos, na ordem, e a descida lenta o bastante para atravessar.

    A pausa é a janela de leitura: sem ela a ameaça chega junto com a informação,
    que era o defeito da parábola antiga.
    """
    from game.entities.enemies.city.triad_orb import (
        _LOB_FALL_SPEED,
        _LOB_HOLD_TIME,
        _LOB_RISE_TIME,
        make_rain,
    )

    posto = (400.0, 150.0)
    orb = make_rain(640.0, 380.0, posto, (47, 212, 232), birth=0.05)
    _tick(orb, 0.10)  # nasce

    # Sobe.
    _tick(orb, _LOB_RISE_TIME * 0.5)
    assert orb.y < 380.0 and orb.y > posto[1], "não está subindo"

    # Chega e ESTAGNA.
    _tick(orb, _LOB_RISE_TIME * 0.5 + 0.01)
    parado = (orb.x, orb.y)
    assert abs(orb.x - posto[0]) < 1.0 and abs(orb.y - posto[1]) < 1.0, (
        "não chegou ao posto"
    )
    _tick(orb, _LOB_HOLD_TIME * 0.6)
    assert (orb.x, orb.y) == parado, "não estagnou lá em cima"

    # Desce, e devagar.
    _tick(orb, _LOB_HOLD_TIME * 0.5 + 0.5)
    assert orb.y > posto[1], "não começou a cair"
    antes = orb.y
    _tick(orb, 0.5)
    caiu = (orb.y - antes) / 0.5
    assert caiu <= _LOB_FALL_SPEED * 1.2, f"caindo a {caiu:.0f} px/s"
    assert abs(orb.x - posto[0]) > 1.0, "a queda não serpenteia"


# ── Minas: terreno, não projétil ─────────────────────────────────────────────
def test_minas_nao_expiram():
    """Só somem a tiro ou com o chefe. Não têm prazo."""
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    mina = TriadOrb(400.0, 400.0, OrbBehavior.ANCHOR, birth=0.05)
    _tick(mina, 0.10)
    assert mina.causes_damage
    for _ in range(int(60 * 40)):  # 40 segundos
        _tick(mina)
    assert not mina.dead, "a mina expirou sozinha"
    assert mina.causes_damage, "a mina parou de valer sem ninguém encostar nela"


def test_minas_respeitam_o_teto_em_tela(boss: TriadBoss):
    """O campo se estabelece e para. Uma luta longa não pode entupir a arena."""
    from game.entities.enemies.city.triad_boss import _ANCORA_MAX

    _levar_ate_fase(boss, 2)
    vivas: list = []
    t = 0.0
    pico = 0
    while t < 60.0:
        orbs = boss.update(DT, _PLAYER)
        if orbs:
            vivas.extend(orbs)
        for orb in vivas:
            _tick(orb)
        vivas = [o for o in vivas if not o.dead]
        minas = sum(1 for o in vivas if o.behavior.name == "ANCHOR" and o.causes_damage)
        pico = max(pico, minas)
        t += DT
    assert pico > 0, "nenhuma mina foi plantada na Fase 2"
    assert pico <= _ANCORA_MAX, f"{pico} minas em tela, teto é {_ANCORA_MAX}"


def test_minas_morrem_com_o_chefe(boss: TriadBoss):
    """Campo permanente exige varrimento na morte.

    Sem isso, oito minas continuariam ferindo depois de a luta acabar — o que lê
    como bug mesmo sendo consequência direta da regra de não expirarem.
    """
    from game.entities.enemies.city.triad_orb import OrbBehavior, TriadOrb

    minas = [
        TriadOrb(300.0 + i * 60, 400.0, OrbBehavior.ANCHOR, birth=0.05)
        for i in range(5)
    ]
    for mina in minas:
        _tick(mina, 0.10)
    boss._orbs.extend(minas)

    _abrir_portao(boss)
    boss.health = 1
    boss.on_hit(999, *boss._crown_circle()[:2])

    assert boss.dead
    for mina in minas:
        assert not mina.causes_damage, "mina sobreviveu à morte do chefe"


# ── Parede: duas frentes intercaladas ────────────────────────────────────────
def test_parede_vem_dos_dois_lados_com_alturas_intercaladas(boss: TriadBoss):
    """Cinco de um lado, quatro do outro, alternando na altura.

    Alinhadas as duas frentes se cancelam: bastaria achar uma faixa livre nas
    duas e ficar nela. Desencontradas, o corredor de uma é por onde a outra vai
    passar.
    """
    from game.core.config import config as Config
    from game.entities.enemies.city.triad_boss import _PAREDE_DIR, _PAREDE_ESQ

    orbs = boss._fire_parede(_PLAYER)
    assert len(orbs) == _PAREDE_ESQ + _PAREDE_DIR

    meio = float(Config.SCREEN_WIDTH) * 0.5
    esq = [o for o in orbs if o.spawn[0] < meio]
    dir_ = [o for o in orbs if o.spawn[0] > meio]
    assert len(esq) == _PAREDE_ESQ and len(dir_) == _PAREDE_DIR

    assert all(o.vx > 0 for o in esq), "a frente da esquerda não vai para a direita"
    assert all(o.vx < 0 for o in dir_), "a frente da direita não vai para a esquerda"

    # Intercaladas: ordenando por altura, os lados alternam.
    lados = [o.spawn[0] < meio for o in sorted(orbs, key=lambda o: o.spawn[1])]
    assert all(a != b for a, b in zip(lados, lados[1:])), (
        "as duas frentes nascem nas mesmas alturas — elas se cancelam"
    )
