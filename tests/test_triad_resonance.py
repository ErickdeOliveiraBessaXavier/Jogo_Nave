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
