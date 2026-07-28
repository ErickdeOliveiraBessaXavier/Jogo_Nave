"""Testes da aplicação dos volumes configurados pelo jogador.

Existem por uma regressão silenciosa: a tela de configurações exibia o volume
salvo, mas o jogo tocava os efeitos no volume de fábrica em todo boot. Nada
falhava — os *números* estavam certos em toda parte; o que estava errado era o
volume gravado DENTRO de cada `pygame.mixer.Sound`, que ninguém inspecionava.

São testes de estado real do mixer (não de campos), porque o campo é justamente
o que estava certo enquanto o jogador ouvia outra coisa.
"""

import pytest

from game.core.sound import sound_manager
from game.core.sound_config import VOLUME_CONFIG


def _loaded_sounds():
    sounds = sound_manager.loaded_sound_names()
    if not sounds:
        pytest.skip("nenhum SFX carregado neste ambiente (mixer dummy sem assets)")
    return sounds


def _restore():
    """Devolve o singleton ao estado de fábrica — é global entre testes."""
    sound_manager.load_config(
        VOLUME_CONFIG["music"], VOLUME_CONFIG["sfx"], VOLUME_CONFIG["shots"]
    )


def test_load_config_aplica_o_volume_aos_sons_ja_carregados():
    """A regressão exata: `load_config` mudava os campos e parava por aí.

    Os `Sound` guardam o volume dentro do objeto (gravado na carga, com o valor
    PADRÃO — o singleton nasce antes das preferências existirem). Sem reaplicar,
    o jogador ouvia o volume de fábrica a cada boot.
    """
    _loaded_sounds()
    try:
        sound_manager.load_config(0.5, 0.1, 0.2)
        esperado = 0.1 * sound_manager.master_volume

        for nome in _loaded_sounds():
            if nome.startswith("shot_"):
                continue  # escala própria — ver teste abaixo
            real = sound_manager.get_sound(nome).get_volume()
            # O pygame quantiza o volume em passos de 1/128.
            assert abs(real - esperado) < 0.02, (
                f"'{nome}' ficou em {real:.4f}, configurado {esperado:.4f}"
            )
    finally:
        _restore()


def test_load_config_preserva_a_escala_propria_dos_tiros():
    """Tiros são disparados sem parar e têm volume próprio, mais baixo. O
    reaplicar geral não pode achatá-los no volume de SFX."""
    _loaded_sounds()
    try:
        sound_manager.load_config(0.5, 0.9, 0.1)
        tiros = [n for n in _loaded_sounds() if n.startswith("shot_")]
        if not tiros:
            pytest.skip("sons de tiro não carregados neste ambiente")

        esperado_tiro = 0.1 * sound_manager.master_volume
        for nome in tiros:
            real = sound_manager.get_sound(nome).get_volume()
            assert abs(real - esperado_tiro) < 0.02, (
                f"tiro '{nome}' em {real:.4f}, esperado {esperado_tiro:.4f}"
            )
    finally:
        _restore()


def test_set_sfx_volume_tambem_alcanca_os_sons():
    """Caminho do slider — este já funcionava, e é o que mascarava o bug:
    mexer no volume 'consertava' a sessão até o próximo boot."""
    _loaded_sounds()
    try:
        sound_manager.set_sfx_volume(0.25)
        esperado = 0.25 * sound_manager.master_volume
        for nome in _loaded_sounds():
            if nome.startswith("shot_"):
                continue
            real = sound_manager.get_sound(nome).get_volume()
            assert abs(real - esperado) < 0.02, f"'{nome}' em {real:.4f}"
    finally:
        _restore()


def test_volume_zero_realmente_silencia():
    """Caso de borda que o jogador percebe na hora: mudo tem de ser mudo."""
    _loaded_sounds()
    try:
        sound_manager.load_config(0.0, 0.0, 0.0)
        for nome in _loaded_sounds():
            assert sound_manager.get_sound(nome).get_volume() == 0.0, nome
    finally:
        _restore()


def test_preferencias_da_tela_de_config_sao_as_do_app():
    """Uma instância de `UserPreferences` por arquivo.

    Duas cópias sobre o mesmo JSON era a segunda dessincronização: a tela
    editava e salvava a dela, o app seguia com o valor antigo em memória, e um
    `app.preferences.save()` posterior (hot-plug de controle, por exemplo)
    regravava o valor velho por cima da escolha do jogador.
    """
    from game.core.paths import get_preferences_path
    from game.core.preferences import UserPreferences
    from game.scenes.settings import SettingsView

    class _AppStub:
        def __init__(self):
            self.preferences = UserPreferences(get_preferences_path())

    app = _AppStub()
    view = SettingsView(on_back=lambda: None, app=app)

    assert view.preferences is app.preferences, (
        "a tela de configurações voltou a criar a própria cópia das preferências"
    )


def test_boot_sem_placa_de_som_nao_derruba_o_jogo():
    """O caminho de fallback tem que continuar EXECUTÁVEL.

    Quando `pygame.mixer.init()` falha, o `__init__` desvia para um `except` que
    monta o estado mínimo e segue sem som. Esse trecho não roda em nenhuma
    máquina de desenvolvimento nem no CI (ambos têm mixer, mesmo o dummy), então
    nada o exercitava: `music_duck_factor` virou property sem setter e a
    atribuição que ficou para trás passou a levantar AttributeError DENTRO do
    except — a máquina sem áudio deixou de abrir o jogo em vez de abrir muda.
    """
    import importlib
    import sys
    from unittest import mock

    import pygame

    with (
        mock.patch.object(pygame.mixer, "get_init", return_value=None),
        mock.patch.object(
            pygame.mixer, "init", side_effect=pygame.error("sem placa de som")
        ),
    ):
        modulo = importlib.reload(importlib.import_module("game.core.sound"))
        try:
            mudo = modulo.sound_manager
            assert mudo.audio_available is False
            # As duas leituras que o boot faz logo em seguida — ambas passam
            # pelo dict de ducks que precisa existir mesmo sem áudio.
            assert mudo.music_duck_factor == 1.0
            assert 0.0 <= mudo.music_target_volume() <= 1.0
        finally:
            # O módulo é singleton global; devolve a instância com áudio para os
            # outros testes (a ordem entre arquivos não é garantida).
            sys.modules.pop("game.core.sound", None)
            importlib.import_module("game.core.sound")
