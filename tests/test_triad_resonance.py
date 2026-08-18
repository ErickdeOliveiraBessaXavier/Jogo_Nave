"""Invariantes do portão de ressonância da Tríade (boss do nível 34).

O `ResonanceGate` é lógica pura (§16): estes testes não instanciam o boss nem
pygame. Os que precisam do roteamento de dano usam o `TriadBoss` de verdade,
porque o roteamento por posição é justamente o que não dá para verificar sem a
geometria real das hitboxes.

O teste mais importante do arquivo é `test_uma_cabeca_sozinha_nunca_regenera`:
ele trava a regra que impede o boss de ficar **matematicamente impossível**.
"""

from __future__ import annotations

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


def _run_phase1(boss: TriadBoss, seconds: float):
    """Roda o ciclo de ataque e devolve (emissões, nº máx. de cabeças laranja)."""
    emissoes = []
    max_laranja = 0
    t = 0.0
    while t < seconds:
        orbs = boss.update(DT, _PLAYER)
        t += DT
        laranja = int(boss._crown_attacking) + sum(1 for h in boss.heads if h.attacking)
        max_laranja = max(max_laranja, laranja)
        if orbs:
            emissoes.append((boss._actor, boss._attack, orbs))
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
    for _actor, ataque, orbs in _run_phase1(boss, 30.0)[0]:
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
        orbs = boss._fire_pulso()
        angulos = sorted(o.angle % math.tau for o in orbs)
        assert len(orbs) < 16, "anel sem brecha"

        maior_vao, onde = 0.0, 0.0
        for i, a in enumerate(angulos):
            prox = angulos[(i + 1) % len(angulos)]
            vao = (prox - a) % math.tau
            if vao > maior_vao:
                maior_vao, onde = vao, (a + vao / 2.0) % math.tau
        assert math.sin(onde) > 0.0, "brecha caiu no hemisfério de cima"
