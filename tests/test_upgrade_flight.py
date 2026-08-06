"""Voo do medalhão entre card e slot (`UpgradeFlight` / `FlightTrack`).

A animação é cosmética, mas duas coisas nela têm consequência visível e são o
que este arquivo trava:

- **O gate de animações.** Com as animações desligadas em Settings, nenhum voo
  pode nascer — senão a tela anima justamente para quem pediu que não animasse.
- **O slot pendente.** Enquanto há voo a caminho, o slot desenha vazio. Se essa
  resposta vier errada, o upgrade aparece nos DOIS lugares ao mesmo tempo.
"""

import math

import pygame
import pytest

from game.core.upgrades import UpgradeType, list_all_upgrades_meta
from game.scenes.upgrade_flight import FlightTrack, UpgradeFlight, ease_in_out_cubic

META = next(u for u in list_all_upgrades_meta() if u.type is UpgradeType.HEAL)
COR = (200, 100, 100)
CARD = pygame.Rect(600, 100, 300, 100)
SLOT = pygame.Rect(100, 500, 80, 80)


def voo(**kwargs) -> UpgradeFlight:
    base = dict(slot_index=0)
    base.update(kwargs)
    return UpgradeFlight(META, CARD, SLOT, 30, 25, COR, **base)


def avanca(alvo, segundos: float, passo: float = 1 / 60) -> None:
    """Roda ``segundos`` de animação em passos de 60fps.

    Arredonda o número de passos para CIMA: com `int()`, 0,56s a 60fps dava 33
    passos (0,550s) e a animação parava a um triz do fim — o teste media o
    penúltimo frame e acusava falha onde não havia."""
    for _ in range(math.ceil(segundos / passo)):
        alvo.update(passo)


# ── trajetória ──────────────────────────────────────────────────────────────


def test_comeca_no_card_e_termina_no_slot():
    f = voo()
    assert f.position() == pytest.approx(CARD.center)
    avanca(f, UpgradeFlight.DURATION)
    assert f.position() == pytest.approx(SLOT.center, abs=1.0)


def test_raio_interpola_do_card_ao_slot():
    f = voo()
    assert f.radius() == pytest.approx(30)
    avanca(f, UpgradeFlight.DURATION + UpgradeFlight.SNAP_DURATION)
    assert f.radius() == pytest.approx(25, abs=0.5)


def test_arco_sai_da_linha_reta():
    """Sem o arco a animação lê como um deslize; o desvio é o efeito."""
    f = voo()
    avanca(f, UpgradeFlight.DURATION / 2)
    x, y = f.position()
    meio_reto_y = (CARD.centery + SLOT.centery) / 2
    assert y < meio_reto_y - 5, "o voo deveria arquear para cima da reta"


def test_easing_tem_extremos_presos():
    assert ease_in_out_cubic(0.0) == 0.0
    assert ease_in_out_cubic(1.0) == pytest.approx(1.0)
    assert ease_in_out_cubic(0.5) == pytest.approx(0.5)


# ── ciclo de vida ───────────────────────────────────────────────────────────


def test_snap_estica_e_volta():
    """O pop de chegada passa do raio final e volta — é o "encaixou"."""
    f = voo()
    avanca(f, UpgradeFlight.DURATION)
    assert f.arrived and not f.snap_finished

    raios = []
    for _ in range(math.ceil(UpgradeFlight.SNAP_DURATION / (1 / 60))):
        f.update(1 / 60)
        raios.append(f.radius())

    assert max(raios) > 25, "o snap deveria passar do raio final"
    assert raios[-1] == pytest.approx(25, abs=0.5), "e assentar no raio do slot"


def test_medalhao_some_quando_o_slot_assume():
    f = voo()
    assert f.medallion_visible
    avanca(f, UpgradeFlight.DURATION + UpgradeFlight.SNAP_DURATION)
    assert not f.medallion_visible


def test_voo_de_volta_sem_destino_se_apaga():
    f = voo(slot_index=None, fade_out=True)
    assert f.alpha() == 255
    avanca(f, UpgradeFlight.DURATION + UpgradeFlight.SNAP_DURATION)
    assert f.alpha() == 0


def test_rastro_nasce_e_morre():
    f = voo()
    avanca(f, 0.1)
    assert f.particles, "o voo deveria estar deixando rastro"
    avanca(f, 3.0)
    assert not f.particles
    assert f.done


# ── FlightTrack ─────────────────────────────────────────────────────────────


def test_animacoes_desligadas_nao_lancam_voo():
    track = FlightTrack(lambda: False)
    track.launch_to_slot(META, COR, CARD, SLOT, 30, 25, 0)
    assert len(track) == 0
    assert not track.is_slot_pending(0)


def test_slot_fica_pendente_ate_a_chegada():
    track = FlightTrack(lambda: True)
    track.launch_to_slot(META, COR, CARD, SLOT, 30, 25, 0)

    assert track.is_slot_pending(0)
    assert not track.is_slot_pending(1)

    avanca(track, UpgradeFlight.DURATION + 0.05)
    assert not track.is_slot_pending(0), "chegou: o slot já desenha o ícone"


def test_novo_voo_para_o_mesmo_slot_descarta_o_anterior():
    """O conteúdo do slot mudou no meio do caminho — o voo velho mente."""
    track = FlightTrack(lambda: True)
    track.launch_to_slot(META, COR, CARD, SLOT, 30, 25, 0)
    track.launch_to_slot(META, COR, CARD, SLOT, 30, 25, 0)
    assert len(track) == 1


def test_desequipar_sem_card_visivel_usa_o_fallback_e_apaga():
    track = FlightTrack(lambda: True)
    fallback = pygame.Rect(900, 300, 1, 1)
    track.launch_to_card(META, COR, SLOT, None, 25, 0, 0, fallback)

    assert len(track) == 1
    voo_atual = track.flights[0]
    assert voo_atual.fade_out
    assert voo_atual.slot_index is None, "voltar não reserva slot nenhum"
    avanca(track, UpgradeFlight.DURATION + UpgradeFlight.SNAP_DURATION)
    assert voo_atual.alpha() == 0


def test_track_limpa_voos_terminados():
    track = FlightTrack(lambda: True)
    track.launch_to_slot(META, COR, CARD, SLOT, 30, 25, 0)
    avanca(track, 3.0)
    assert len(track) == 0
