"""Testes da vinheta de dano (`render/damage_vignette.py`).

O foco é o contrato que a cena depende: o flash existe enquanto a nave
sobreviveu ao hit, e desaparece na hora quando ela é destruída. O golpe fatal
não deve iniciar efeito nenhum — a sequência de destruição é que comunica.
"""

import pygame

from game.render.damage_vignette import DamageVignette

DT = 1 / 60


def _visible_alpha(v: DamageVignette) -> float:
    """Intensidade de borda que o `draw` usaria neste frame."""
    return v._flash_env() * v.FLASH_ALPHA + v._critical_env() * v.CRITICAL_ALPHA


def _draws_anything(v: DamageVignette) -> bool:
    """Desenha de fato alguma coisa numa surface limpa?"""
    surf = pygame.Surface((320, 240))
    surf.fill((0, 0, 0))
    v.draw(surf)
    return pygame.transform.average_color(surf)[:3] != (0, 0, 0)


def test_trigger_acende_a_vinheta():
    v = DamageVignette()
    assert not _draws_anything(v), "vinheta acesa sem nenhum hit"

    v.trigger(damage=1)
    v.update(DT, critical=False)
    assert _visible_alpha(v) > 2.0
    assert _draws_anything(v)


def test_clear_apaga_na_hora():
    """Golpe fatal com a partida continuando (coop / atmosfera): o flash de um
    hit anterior não pode decair por cima da destruição da nave."""
    v = DamageVignette()
    v.trigger(damage=1)
    v.update(DT, critical=False)
    assert _draws_anything(v)

    v.clear()
    assert _visible_alpha(v) == 0.0
    assert not _draws_anything(v)


def test_clear_nao_desliga_o_alerta_critico():
    """`_critical` é reavaliado pela cena a cada update; `clear` mexer nele
    seria escrever num campo que o próximo frame sobrescreve."""
    v = DamageVignette()
    v.update(DT, critical=True)
    antes = v._critical_env()
    assert antes > 0.0

    v.clear()
    v.update(DT, critical=True)
    assert v._critical_env() > 0.0, "o pulso de 1 vida foi desligado por engano"


def test_clear_remove_as_rachaduras():
    """As rachaduras têm vida própria (~0,2s) e desenham por cima do mundo;
    sobreviver ao `clear` deixaria detritos piscando na morte."""
    v = DamageVignette()
    v.trigger(damage=1)
    assert v._cracks, "trigger não gerou rachaduras"

    v.clear()
    assert v._cracks == []


def test_flash_decai_ate_sumir_sozinho():
    """Sem novo hit, a vinheta volta ao normal por conta própria — nenhum
    resíduo permanente fora do alerta crítico."""
    v = DamageVignette()
    v.trigger(damage=1)

    for _ in range(int(3.0 / DT)):
        v.update(DT, critical=False)

    assert _visible_alpha(v) == 0.0
    assert not _draws_anything(v)


def test_hit_mais_forte_acende_mais():
    """`damage` reforça o pico — o parâmetro precisa continuar tendo efeito."""
    fraco, forte = DamageVignette(), DamageVignette()
    fraco.trigger(damage=1)
    forte.trigger(damage=4)
    fraco.update(DT, critical=False)
    forte.update(DT, critical=False)

    assert _visible_alpha(forte) > _visible_alpha(fraco)
