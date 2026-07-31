"""Convite à Central de Loadout no Game Over (FTUE, item 2 do plano).

O menu principal é o pior lugar para vender aprimoramentos: antes de jogar,
"Aprimoramentos" é só uma palavra e o jogador não tem como avaliar um upgrade
que nunca viu em uso. Depois de morrer, tem. Esta tela é o momento em que o
convite significa alguma coisa — e é também a primeira vez que o jogo diz
quanto a partida rendeu em estrelas, a moeda que compra capacidade de slot.

O que os testes travam é a REGRA de quando convidar: o botão não pode virar
mobília permanente de uma tela cuja ação principal é voltar a jogar. Ele
aparece só quando há algo a fazer lá (loadout vazio ou saldo que paga o
próximo slot) e some quando não há.
"""

from pathlib import Path

import pygame
import pytest

from game.core.config import config as Config, set_screen_resolution
from game.core.meta_progression import PlayerProfile
from game.core.upgrades import UpgradeType
from game.core.upgrades_config import SLOT_UNLOCK_COSTS
from game.scenes.game_over import GameOverScene


class _StubEntityManager:
    def spawn_explosion(self, *_args, **_kwargs):
        pass


class _StubShip:
    def __init__(self):
        self.visible = True
        self.rect = pygame.Rect(100, 100, 40, 40)


class _StubPlayingScene:
    """Só o que o `GameOverScene.__init__` toca da cena de gameplay."""

    def __init__(self, stars_earned: int):
        self.r = None
        self.ship = _StubShip()
        self.entity_manager = _StubEntityManager()
        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = 0
        self.stars_earned_this_run = stars_earned


class _StubApp:
    def __init__(self, profile: PlayerProfile):
        self.player_profile = profile


@pytest.fixture
def profile(tmp_path: Path) -> PlayerProfile:
    """Perfil novo em disco temporário: loadout vazio, 2 slots, 0 estrelas."""
    return PlayerProfile(tmp_path / "profile.json")


@pytest.fixture(autouse=True)
def _res_720p():
    original = (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
    set_screen_resolution(1280, 720)
    yield
    set_screen_resolution(*original)


def _scene(profile: PlayerProfile, stars_earned: int = 0) -> GameOverScene:
    return GameOverScene(
        _StubApp(profile), score=1234, playing_scene=_StubPlayingScene(stars_earned)
    )


def test_loadout_vazio_convida_e_explica_o_porque(profile):
    """Quem nunca equipou nada é exatamente o jogador que o item 2 persegue."""
    scene = _scene(profile)

    assert scene.show_loadout_hook
    assert scene.loadout_hook_key == "game_over.hook_empty"


def test_loadout_cheio_e_sem_saldo_nao_convida(profile):
    """Sem loadout vazio e sem estrelas para o próximo slot, não há o que
    oferecer — o botão seria ruído numa tela cuja ação é voltar a jogar."""
    profile.equip_upgrade(UpgradeType.HEAL, 0)
    profile.equip_upgrade(UpgradeType.BLINK_DASH, 1)

    scene = _scene(profile)

    assert not scene.show_loadout_hook
    assert scene.upgrades_button.width == 0


def test_saldo_para_o_proximo_slot_convida_com_a_outra_frase(profile):
    """Já equipou, mas pode ampliar: a razão do convite muda de 'existe isso'
    para 'dá para crescer'."""
    profile.equip_upgrade(UpgradeType.HEAL, 0)
    profile.equip_upgrade(UpgradeType.BLINK_DASH, 1)
    profile.add_stars(SLOT_UNLOCK_COSTS[profile.unlocked_slots])

    scene = _scene(profile)

    assert scene.show_loadout_hook
    assert scene.loadout_hook_key == "game_over.hook_slot"


def test_uma_estrela_a_menos_nao_convida(profile):
    """Fronteira do saldo: o convite promete um slot, então só aparece quando
    o slot é realmente pagável."""
    profile.equip_upgrade(UpgradeType.HEAL, 0)
    profile.equip_upgrade(UpgradeType.BLINK_DASH, 1)
    profile.add_stars(SLOT_UNLOCK_COSTS[profile.unlocked_slots] - 1)

    assert not _scene(profile).show_loadout_hook


def test_estrelas_da_run_vem_da_partida_nao_do_acumulado(profile):
    """O número exibido é o ganho DESTA partida.

    O `stars_collected` do perfil é cumulativo e nunca zera; mostrar ele aqui
    daria "532 estrelas nesta partida" na segunda run de um veterano.
    """
    profile.add_stars(500)  # histórico de outras partidas

    scene = _scene(profile, stars_earned=7)

    assert scene.stars_earned == 7


def test_botao_entra_na_navegacao_por_controle(profile):
    """Sem isto o convite existiria só para quem joga no mouse.

    `entry_submitted` é forçado porque na primeira morte o placar ainda está
    vazio: qualquer pontuação entra no ranking, o widget de iniciais toma o
    foco e os botões só existem depois dele. É a ordem real da tela.
    """
    com = _scene(profile)
    com.entry_submitted = True

    profile.equip_upgrade(UpgradeType.HEAL, 0)
    profile.equip_upgrade(UpgradeType.BLINK_DASH, 1)
    sem = _scene(profile)
    sem.entry_submitted = True

    assert len(com.get_focusable_rects()) == len(sem.get_focusable_rects()) + 1
    assert com.upgrades_button in com.get_focusable_rects()


def test_botoes_nao_se_sobrepoem(profile):
    """Três botões numa fileira só: o do meio não pode invadir os das pontas."""
    scene = _scene(profile)

    assert not scene.back_to_menu_button.colliderect(scene.upgrades_button)
    assert not scene.upgrades_button.colliderect(scene.continue_button)
    assert scene.upgrades_button.right <= Config.SCREEN_WIDTH


@pytest.mark.parametrize("resolution", [(1024, 576), (1280, 720), (1920, 1080)])
def test_vaos_entre_os_tres_botoes_sao_iguais(profile, resolution):
    """O botão do meio se alinha pelos vizinhos, não pelo centro da tela.

    Os das pontas têm larguras bem diferentes (280 contra 420), então centrar
    o do meio na tela dava 170px de folga à esquerda e 30px à direita — três
    botões visivelmente tortos. Medir a partir dos rects vizinhos corrige e
    continua correto se um rótulo mudar de tamanho.
    """
    set_screen_resolution(*resolution)
    scene = _scene(profile)

    folga_esq = scene.upgrades_button.left - scene.back_to_menu_button.right
    folga_dir = scene.continue_button.left - scene.upgrades_button.right

    assert folga_esq > 0 and folga_dir > 0
    # 1px de tolerância: a divisão inteira do vão pode sobrar um pixel.
    assert abs(folga_esq - folga_dir) <= 1


@pytest.mark.parametrize("resolution", [(1024, 576), (1280, 720), (1920, 1080)])
def test_os_tres_botoes_tem_a_mesma_largura(profile, resolution):
    """Fileira uniforme.

    O Continuar já foi mais largo (420 contra 280) para caber "CONTINUAR DE
    ONDE PAROU"; com o rótulo curto essa exceção deixou de ter motivo, e três
    larguras diferentes leem como desalinho mesmo com os vãos certos.
    """
    set_screen_resolution(*resolution)
    scene = _scene(profile)

    larguras = {
        scene.back_to_menu_button.width,
        scene.upgrades_button.width,
        scene.continue_button.width,
    }
    assert len(larguras) == 1


def test_sem_vao_suficiente_o_convite_some(profile, monkeypatch):
    """Se os botões das pontas crescerem a ponto de não sobrar espaço legível,
    é melhor não convidar do que espremer três botões ilegíveis."""
    scene = _scene(profile)
    # Simula rótulos gigantes: as pontas ocupam quase toda a largura.
    scene.back_to_menu_button.width = Config.SCREEN_WIDTH // 2
    scene.continue_button.left = scene.back_to_menu_button.right + 10
    scene.upgrades_button = scene._center_between_buttons(
        scene.continue_button.top, scene.continue_button.height
    )

    assert scene.upgrades_button.width == 0
