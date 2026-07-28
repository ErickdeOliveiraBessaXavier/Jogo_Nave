"""Tremor da parada do tempo — o deslocamento cosmético dos congelados.

`EntityManager.apply_freeze_tremor` escreve `en.x`/`en.y` diretamente. Duas
coisas precisam valer e nenhuma era testada:

- entidade de posição DERIVADA (property sem setter) tem de ser PULADA. Sem
  isso o jogo cai com `AttributeError` no meio da partida — foi o que
  aconteceu com `MountainStalagmite`;
- o deslocamento não pode ACUMULAR: cada frame desfaz o anterior antes de
  aplicar o novo, e amplitude 0 devolve todo mundo ao lugar exato.

O `apply_freeze_tremor` não toca em pygame nem depende do resto do manager, e o
método é chamado desligado da instância (stubs), então nada aqui instancia o
jogo.
"""

import pygame
import pytest

from game.systems.entity_manager import EntityManager


class _InimigoMovel:
    """Inimigo comum: `x`/`y` são atributos graváveis."""

    def __init__(self, x: float = 100.0, y: float = 100.0) -> None:
        self.x = x
        self.y = y
        self.rect = pygame.Rect(int(x), int(y), 10, 10)


class _InimigoAncorado:
    """Estrutura presa ao cenário — o caso `MountainStalagmite`.

    `y` é derivado e não tem setter: `en.y += ...` estoura. Declara o opt-out
    formal do protocolo `Enemy`.
    """

    position_locked = True

    def __init__(self, x: float = 200.0, ground_y: float = 400.0) -> None:
        self.x = x
        self.ground_y = ground_y
        self.altura = 60.0
        self.rect = pygame.Rect(int(x), int(ground_y - 60), 10, 60)

    @property
    def y(self) -> float:
        return self.ground_y - self.altura


class _Gerente:
    """Só o que `apply_freeze_tremor` usa."""

    apply_freeze_tremor = EntityManager.apply_freeze_tremor
    _TREMOR_DX = EntityManager._TREMOR_DX
    _TREMOR_DY = EntityManager._TREMOR_DY

    def __init__(self, *inimigos: object) -> None:
        self.enemies = list(inimigos)


def test_entidade_ancorada_nao_derruba_o_tremor():
    """A regressão: `AttributeError: property 'y' ... has no setter`."""
    pilar = _InimigoAncorado()
    gerente = _Gerente(pilar)

    gerente.apply_freeze_tremor(4.0, 1.23)  # não pode levantar exceção

    assert pilar.y == pytest.approx(340.0), "a posição derivada não pode mudar"
    assert pilar.x == pytest.approx(200.0), "ancorada também não desliza no eixo x"


def test_ancorada_convive_com_movel_na_mesma_lista():
    """O pulo não pode interromper o loop nem deslocar o índice de fase."""
    movel, pilar = _InimigoMovel(), _InimigoAncorado()
    gerente = _Gerente(pilar, movel)

    gerente.apply_freeze_tremor(4.0, 0.5)

    assert (movel.x, movel.y) != (100.0, 100.0), "o inimigo móvel deveria vibrar"
    assert pilar.y == pytest.approx(340.0)


def test_amplitude_zero_devolve_ao_lugar_exato():
    movel = _InimigoMovel()
    gerente = _Gerente(movel)
    rect_original = movel.rect.topleft

    for i in range(30):
        gerente.apply_freeze_tremor(5.0, i / 60.0)
    gerente.apply_freeze_tremor(0.0, 0.5)

    assert movel.x == pytest.approx(100.0)
    assert movel.y == pytest.approx(100.0)
    assert movel.rect.topleft == rect_original


def test_o_tremor_nao_acumula_deriva():
    """O rect anda por offsets ABSOLUTOS arredondados, não por `round(delta)`.

    Arredondar o delta a cada frame acumula erro no inteiro e o congelado
    derivava pixels ao longo do tremor em vez de vibrar no lugar.
    """
    movel = _InimigoMovel()
    gerente = _Gerente(movel)

    for i in range(120):
        gerente.apply_freeze_tremor(3.0, i / 60.0)

    assert abs(movel.x - 100.0) <= 3.0 + 1e-6
    assert abs(movel.y - 100.0) <= 3.0 + 1e-6
