"""Detecção de retrato — o aviso de girar o aparelho.

O risco aqui não é errar a conta de proporção; é **estourar**. A fonte da
verdade no web é o objeto `window` do navegador, exposto pelo pygbag por um
módulo que não controlamos e que muda entre versões. Um `AttributeError` ali
mataria o loop de render num frame qualquer, no aparelho do jogador, por causa
de um aviso cosmético.

Por isso os testes cobrem menos a matemática e mais o **degradar**: sem
informação, sem aviso — nunca uma exceção.
"""

from unittest.mock import patch

import pytest

from game.core import orientation


class TestProporcao:
    @pytest.mark.parametrize(
        "size,esperado",
        [
            ((1280, 720), False),  # paisagem 16:9 — o alvo
            ((720, 1280), True),  # celular em pé
            ((1080, 1920), True),
            ((1024, 768), False),  # 4:3 — apertado, mas jogável
        ],
    )
    def test_classifica_pela_proporcao(self, size, esperado):
        with patch.object(orientation, "viewport_size", return_value=size):
            assert orientation.is_portrait() is esperado

    def test_quadrado_nao_grita(self):
        """O aviso pede para GIRAR, e girar uma tela quadrada não muda nada.

        Ela letterboxa feio, mas isso é outro problema — mandar o jogador fazer
        algo que comprovadamente não resolve é pior que ficar calado.
        """
        with patch.object(orientation, "viewport_size", return_value=(800, 800)):
            assert not orientation.is_portrait()

    def test_quase_quadrado_nao_grita(self):
        """Aviso que aparece quando não precisa ensina o jogador a ignorá-lo —
        e aí ele não é lido quando precisa."""
        with patch.object(orientation, "viewport_size", return_value=(1000, 1030)):
            assert not orientation.is_portrait()


class TestDegradar:
    def test_sem_informacao_nao_avisa(self):
        with patch.object(orientation, "viewport_size", return_value=None):
            assert orientation.is_portrait() is False

    def test_viewport_zerado_vira_desconhecido(self):
        """Canvas ainda não medido (primeiros frames do web) devolve 0 — dividir
        por ele seria `ZeroDivisionError` no meio do loop de render."""
        with patch("pygame.display.get_window_size", return_value=(0, 0)):
            assert orientation.viewport_size() is None

    def test_api_do_navegador_quebrada_nao_derruba_o_jogo(self):
        """O cenário real: o pygbag muda o `platform` e o atributo some."""
        with patch.object(orientation.sys, "platform", "emscripten"):
            with patch.dict("sys.modules", {"platform": object()}):
                assert orientation.viewport_size() is None
                assert orientation.is_portrait() is False

    def test_pygame_quebrado_nao_derruba_o_jogo(self):
        with patch("pygame.display.get_window_size", side_effect=pygame_error()):
            assert orientation.viewport_size() is None


def pygame_error():
    import pygame

    return pygame.error("display not initialized")
