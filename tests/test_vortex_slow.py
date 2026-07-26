"""Testes da lentidão e do dano por vórtice (GRAVITY_BOMB).

Existem porque um merge descartou as constantes `VORTEX_SLOW_*` de `BlackHole`
mas manteve os usos, em `EntityManager._vortex_multiplier` e no próprio
`BlackHole.process_all_enemies`. A suíte inteira ficou verde e o `ruff` também:
nada exercitava o caminho, e o `getattr(entity, "vortex_slow_timer", 0.0)`
esconde a ausência da marca — só o acesso à constante estourava, em runtime,
no instante em que um inimigo entrava no campo.

Travam o contrato mínimo: as constantes existem, o multiplicador as devolve, o
linger decai até zerar, e o dano por tick entra UMA vez só (o `_apply_vortex_damage`
tinha um caminho que debitava a vida duas vezes quando o dano chegava a 1,0).
"""

from game.entities.enemies.space.black_hole import BlackHole
from game.systems.entity_manager import EntityManager


class _Enemy:
    """Inimigo mínimo — o multiplicador só lê `vortex_slow_timer`."""


def test_constantes_de_slow_existem():
    # O merge que motivou este arquivo removeu exatamente estas duas.
    assert isinstance(BlackHole.VORTEX_SLOW_FACTOR, float)
    assert isinstance(BlackHole.VORTEX_SLOW_LINGER, float)


def test_fator_de_slow_desacelera_sem_congelar():
    # Faixa, não número exato (§16): trava outlier grosseiro, não o micro-ajuste.
    assert 0.0 < BlackHole.VORTEX_SLOW_FACTOR < 1.0


def test_linger_cobre_a_ordem_de_frame_a_30fps():
    """`_update_environment` roda depois de `_update_enemies`, então a marca só
    é lida no frame seguinte. O linger precisa sobreviver a um frame do pior
    caso — 1/30s, o piso do clamp de dt (§14)."""
    assert BlackHole.VORTEX_SLOW_LINGER > 1.0 / 30.0


def test_slow_sobrevive_ao_contato_como_debuff():
    """O campo reaplica a marca a cada frame, então o linger é o slow contado a
    partir do ÚLTIMO contato. É debuff de controle de vários segundos, não a
    margem técnica de um frame que a constante já foi um dia."""
    assert BlackHole.VORTEX_SLOW_LINGER >= 5.0


def test_multiplicador_neutro_sem_marca():
    assert EntityManager._vortex_multiplier(_Enemy()) == 1.0


def test_multiplicador_aplica_o_fator_com_marca_ativa():
    enemy = _Enemy()
    enemy.vortex_slow_timer = BlackHole.VORTEX_SLOW_LINGER
    assert EntityManager._vortex_multiplier(enemy) == BlackHole.VORTEX_SLOW_FACTOR


def test_linger_decai_e_zera_sem_ficar_negativo():
    enemy = _Enemy()
    enemy.vortex_slow_timer = BlackHole.VORTEX_SLOW_LINGER

    # Um passo curto mantém a marca viva.
    EntityManager._update_vortex_linger(enemy, BlackHole.VORTEX_SLOW_LINGER / 2)
    assert enemy.vortex_slow_timer > 0.0
    assert EntityManager._vortex_multiplier(enemy) == BlackHole.VORTEX_SLOW_FACTOR

    # Um passo longo zera exatamente, sem estourar para negativo.
    EntityManager._update_vortex_linger(enemy, 999.0)
    assert enemy.vortex_slow_timer == 0.0
    assert EntityManager._vortex_multiplier(enemy) == 1.0


# ── Dano ────────────────────────────────────────────────────────────────────


class _DamageableEnemy:
    """Inimigo com `on_hit` E `health` — o par que expunha o dano em dobro."""

    def __init__(self, health: float = 100.0):
        self.x = self.y = 0.0
        self.w = self.h = 10
        self.health = health
        self.dead = False
        self.on_hit_damages: list[int] = []

    def on_hit(self, damage, hit_x, hit_y):
        # Imita um inimigo real: `on_hit` debita a própria vida.
        self.on_hit_damages.append(damage)
        self.health -= damage
        if self.health <= 0:
            self.dead = True
        return None


def _vortex() -> BlackHole:
    return BlackHole(0.0, 0.0, duration=15.0, is_vortex=True)


def test_dano_por_segundo_esta_na_faixa_projetada():
    """Faixa, não número exato (§16). Trava outlier grosseiro: o vórtice é
    controle de área com dano de veneno, não a fonte principal de dano."""
    bh = _vortex()
    dps = bh.damage_per_tick / bh.damage_interval
    assert 1.0 <= dps <= 3.0, f"dps={dps}"


def test_dano_total_nao_mata_inimigo_grande_sozinho():
    """Ao longo dos 15s de duração o vórtice não pode limpar um Dreadnought
    (200 HP) sozinho — senão deixa de ser controle e vira arma principal."""
    bh = _vortex()
    total = (bh.damage_per_tick / bh.damage_interval) * 15.0
    assert total < 100.0, f"total={total}"


def test_dano_entra_uma_vez_so_com_on_hit_presente():
    """O bug: `on_hit` recebia o dano real quando >= 1 e debitava a vida, e o
    fallback debitava DE NOVO. Agora `on_hit` é só feedback visual (dano 0) e o
    débito acontece num lugar só."""
    bh = _vortex()
    enemy = _DamageableEnemy(health=100.0)

    bh._apply_vortex_damage(enemy, bh.damage_per_tick)

    assert enemy.health == 100.0 - bh.damage_per_tick
    assert enemy.on_hit_damages == [0], "on_hit deve receber 0 (só flash visual)"


def test_dano_entra_uma_vez_so_mesmo_acima_de_1_hp():
    """Trava o degrau: historicamente `damage >= 1` dobrava o débito. Qualquer
    ajuste futuro do `damage_per_tick` para cima continua linear."""
    bh = _vortex()
    enemy = _DamageableEnemy(health=100.0)

    bh._apply_vortex_damage(enemy, 5.0)

    assert enemy.health == 95.0, "dano aplicado em dobro"
    assert enemy.on_hit_damages == [0]


def test_dano_fracionario_nao_e_truncado():
    """`on_hit` recebe int; se o dano fracionário passasse por ele viraria 0 e o
    veneno não faria nada. O débito direto na vida preserva a fração."""
    bh = _vortex()
    enemy = _DamageableEnemy(health=10.0)

    for _ in range(4):
        bh._apply_vortex_damage(enemy, 0.25)

    assert enemy.health == 9.0
