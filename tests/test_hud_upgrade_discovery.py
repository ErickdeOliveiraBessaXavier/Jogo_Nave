"""Guarda a descoberta do sistema de aprimoramentos no HUD (FTUE).

O `_render_upgrades_hud` tinha um early-return quando nada estava equipado, e o
efeito era que a PRIMEIRA partida — a de quem nunca abriu a Central de Loadout —
corria sem uma única menção aos aprimoramentos: sem slots, sem as teclas que os
acionam, sem o saldo de estrelas que compra capacidade de slot. O único ponto de
contato com o sistema era o botão do menu principal, exatamente o que o jogador
novo ignora.

Estes testes travam as duas metades: os contornos vazios no rodapé e o contador
de estrelas na caixa de score. São testes de PIXEL porque o defeito original era
"não desenha nada" — asserir sobre o estado interno não o teria pego.
"""

import pygame
import pytest

from game.core.config import config as Config, set_screen_resolution
from game.render.game_renderer import GameRenderer


class _StubFrame:
    """Só os campos que os dois métodos de HUD leem (§1: o renderer consome DTO)."""

    def __init__(self, *, stars: int = 0, slots: int = 2, score: int = 0, kills: int = 0):
        self.available_stars = stars
        self.unlocked_upgrade_slots = slots
        self.upgrade_keybindings = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4]
        self.upgrade_slots = [None] * 8
        self.upgrade_select_mode = False
        self.upgrade_select_index = 0
        self.upgrade_denied_timers = {}
        self.score = score
        self.total_enemies_destroyed = kills
        self.score_pop = 0.0


@pytest.fixture
def renderer():
    """Renderer em 720p (ui_scale 1.0), restaurando a resolução no teardown."""
    original = (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    set_screen_resolution(1280, 720)
    yield GameRenderer(None)
    set_screen_resolution(*original)


def _blank(w: int, h: int) -> pygame.Surface:
    surf = pygame.Surface((w, h))
    surf.fill((0, 0, 0))
    return surf


def _bottom_strip_is_painted(surface: pygame.Surface) -> bool:
    """Algum pixel não-preto na faixa central inferior (onde a fileira mora)."""
    h = surface.get_height()
    w = surface.get_width()
    for y in range(h - 70, h - 5, 4):
        for x in range(w // 2 - 90, w // 2 + 90, 4):
            if surface.get_at((x, y))[:3] != (0, 0, 0):
                return True
    return False


def test_loadout_vazio_ainda_desenha_a_fileira(renderer):
    """Loadout vazio não pode apagar o HUD de aprimoramentos — era o bug."""
    surface = _blank(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    renderer._render_upgrades_hud(_StubFrame(slots=2), surface)

    assert _bottom_strip_is_painted(surface), (
        "Com o loadout vazio o rodapé ficou em branco: o jogador que nunca "
        "equipou nada não vê que o sistema existe."
    )


def test_sem_slot_destravado_nao_desenha_nada(renderer):
    """Perfil sem nenhum slot: não há o que anunciar, e não pode quebrar."""
    surface = _blank(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    renderer._render_upgrades_hud(_StubFrame(slots=0), surface)

    assert not _bottom_strip_is_painted(surface)


def test_numero_de_contornos_acompanha_os_slots_destravados(renderer):
    """Mais slots destravados → fileira mais larga (um contorno por slot)."""
    def painted_width(slots: int) -> int:
        surface = _blank(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        renderer._render_upgrades_hud(_StubFrame(slots=slots), surface)
        y = Config.SCREEN_HEIGHT - 30
        xs = [
            x
            for x in range(Config.SCREEN_WIDTH)
            if surface.get_at((x, y))[:3] != (0, 0, 0)
        ]
        return (max(xs) - min(xs)) if xs else 0

    assert painted_width(4) > painted_width(2) > 0


def test_saldo_de_estrelas_aparece_na_caixa_de_score(renderer):
    """A moeda que compra slot precisa ser visível DURANTE a partida.

    Antes ela só existia na tela de Estatísticas e na própria Central de
    Loadout — as duas telas que o jogador em questão nunca abriu.
    """
    sem_estrelas = _blank(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    renderer._render_score_kills_box(_StubFrame(stars=0, kills=42), sem_estrelas)

    com_estrelas = _blank(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    renderer._render_score_kills_box(_StubFrame(stars=777, kills=42), com_estrelas)

    assert pygame.image.tostring(sem_estrelas, "RGB") != pygame.image.tostring(
        com_estrelas, "RGB"
    ), "O saldo de estrelas não mudou nada na tela — o contador não está sendo desenhado."
