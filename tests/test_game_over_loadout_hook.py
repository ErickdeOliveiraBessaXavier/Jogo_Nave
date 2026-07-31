"""Atalho para a Central de Loadout no Game Over.

Duas coisas diferentes convivem no mesmo lugar da tela, e o que os testes
travam é a separação entre elas:

- **O botão é permanente.** Trocar de nave ou mexer no loadout entre duas
  tentativas custava menu → aprimoramentos → mundo → dificuldade → jogar. Esse
  pedágio desestimula o ajuste pequeno, que é justamente o que faz o jogador
  experimentar builds. Só a geometria pode suprimir o botão (sem vão para um
  terceiro botão legível, três botões espremidos são piores que dois).
- **A legenda acima dele é contextual.** O menu principal é o pior lugar para
  vender aprimoramentos: antes de jogar, "Aprimoramentos" é só uma palavra.
  Depois de morrer, não é. O convite só tem peso enquanto for sinal — se
  aparecesse sempre viraria mobília, e mentiria ("você jogou sem nenhum
  equipado" para quem tem o loadout cheio). Sem convite a linha vira o atalho
  de teclado.

O terceiro invariante é a frescura: a legenda descreve o perfil AGORA, não o
do instante da morte — senão o próprio atalho a deixa obsoleta na primeira
viagem de ida e volta.
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
        self.go_to_calls: list[dict] = []

    def go_to(self, factory, **kwargs):
        self.go_to_calls.append(kwargs)
        return True


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


def _equipa_loadout(profile: PlayerProfile) -> None:
    """Perfil de quem já usa o sistema: nada a anunciar, atalho ainda útil."""
    profile.equip_upgrade(UpgradeType.HEAL, 0)
    profile.equip_upgrade(UpgradeType.BLINK_DASH, 1)


def test_atalho_existe_mesmo_sem_nada_a_anunciar(profile):
    """O caso que antes escondia o botão é o caso que mais o justifica.

    Quem já equipou e não tem saldo é exatamente quem quer TROCAR o que está
    equipado entre uma tentativa e outra — e era quem pagava o menu inteiro
    para fazer isso. O botão fica; o que some é a legenda de convite.
    """
    _equipa_loadout(profile)

    scene = _scene(profile)

    assert scene.show_loadout_hook
    assert scene.upgrades_button.width > 0
    assert scene.loadout_hook_key is None


def test_loadout_vazio_explica_o_porque(profile):
    """Quem nunca equipou nada precisa saber que o sistema existe."""
    scene = _scene(profile)

    assert scene.show_loadout_hook
    assert scene.loadout_hook_key == "game_over.hook_empty"


def test_saldo_para_o_proximo_slot_usa_a_outra_frase(profile):
    """Já equipou, mas pode ampliar: a razão muda de 'existe isso' para 'dá
    para crescer'."""
    _equipa_loadout(profile)
    profile.add_stars(SLOT_UNLOCK_COSTS[profile.unlocked_slots])

    scene = _scene(profile)

    assert scene.loadout_hook_key == "game_over.hook_slot"


def test_uma_estrela_a_menos_nao_promete_slot(profile):
    """Fronteira do saldo: a legenda promete um slot, então só aparece quando
    o slot é realmente pagável. O botão, esse, continua lá."""
    _equipa_loadout(profile)
    profile.add_stars(SLOT_UNLOCK_COSTS[profile.unlocked_slots] - 1)

    scene = _scene(profile)

    assert scene.loadout_hook_key is None
    assert scene.show_loadout_hook


def test_legenda_acompanha_o_perfil_ao_voltar_do_loadout(profile):
    """Frescura da legenda — o invariante que o atalho permanente cria.

    `StateManager.pop` re-entra na cena de baixo, então voltar da Central de
    Loadout passa pelo `enter()`. Sem recalcular ali, o jogador equipava o
    primeiro upgrade, voltava, e a tela continuava dizendo "você jogou sem
    nenhum equipado" — descrevendo a partida que acabou, mas lida como o
    estado atual do loadout.
    """
    scene = _scene(profile)
    assert scene.loadout_hook_key == "game_over.hook_empty"

    _equipa_loadout(profile)  # o que a Central de Loadout faria
    scene.enter()

    assert scene.loadout_hook_key is None


def test_abrir_o_loadout_empilha_para_nao_perder_a_run(profile):
    """`push`, não `switch`: é o que mantém este Game Over vivo embaixo.

    Trocar a cena levaria junto `restart_level`, `level_manager` e o preset de
    dificuldade — o jogador voltaria do loadout sem ter para onde continuar, que
    é o menu inteiro de novo, exatamente o atrito que o atalho remove.
    """
    scene = _scene(profile)

    scene._open_upgrades()

    assert scene.app.go_to_calls == [{"push": True}]


def test_estrelas_da_run_vem_da_partida_nao_do_acumulado(profile):
    """O número exibido é o ganho DESTA partida.

    O `stars_collected` do perfil é cumulativo e nunca zera; mostrar ele aqui
    daria "532 estrelas nesta partida" na segunda run de um veterano.
    """
    profile.add_stars(500)  # histórico de outras partidas

    scene = _scene(profile, stars_earned=7)

    assert scene.stars_earned == 7


@pytest.mark.parametrize("ja_equipou", [False, True])
def test_botao_entra_na_navegacao_por_controle(profile, ja_equipou):
    """Sem isto o atalho existiria só para quem joga no mouse — e ele tem de
    estar na navegação nos DOIS estados de legenda, não só quando convida.

    `entry_submitted` é forçado porque na primeira morte o placar ainda está
    vazio: qualquer pontuação entra no ranking, o widget de iniciais toma o
    foco e os botões só existem depois dele. É a ordem real da tela.
    """
    if ja_equipou:
        _equipa_loadout(profile)
    scene = _scene(profile)
    scene.entry_submitted = True

    rects = scene.get_focusable_rects()

    assert len(rects) == 3
    assert scene.upgrades_button in rects


def test_tecla_u_abre_o_loadout(profile):
    """O teclado não pode depender do mouse justamente no atalho rápido; o
    controle já chega lá pelo `get_focusable_rects`."""
    scene = _scene(profile)
    scene.entry_submitted = True

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u))

    assert scene.app.go_to_calls == [{"push": True}]


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


def test_sem_vao_suficiente_o_atalho_some(profile):
    """A geometria é a ÚNICA coisa que ainda pode suprimir o botão.

    Se os botões das pontas crescerem a ponto de não sobrar espaço legível
    (tradução longa, resolução menor), é melhor ficar sem o atalho do que
    espremer três botões ilegíveis.
    """
    scene = _scene(profile)
    # Simula rótulos gigantes: as pontas ocupam quase toda a largura.
    scene.back_to_menu_button.width = Config.SCREEN_WIDTH // 2
    scene.continue_button.left = scene.back_to_menu_button.right + 10
    scene.upgrades_button = scene._center_between_buttons(
        scene.continue_button.top, scene.continue_button.height
    )

    assert scene.upgrades_button.width == 0
