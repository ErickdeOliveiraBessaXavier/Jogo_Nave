"""Pausar não pode reposicionar a nave pilotada pelo mouse.

A nave segue o cursor por **spring-follow** (`ShipMovement._move_impl`): a
velocidade é proporcional à DISTÂNCIA até o ponteiro. Com o jogo parado a nave
não anda, mas o mouse continua livre — então mexer nele durante a pausa aumenta
essa distância, e ao retomar a nave ARRANCA para a posição nova.

A correção tem duas metades, testadas separadamente aqui:

  1. `PlayingScene.freeze_pointer`/`restore_pointer` guardam e devolvem a
     posição do ponteiro (contrato + uso de `app.warp_cursor`, §19).
  2. `PausedScene` chama esses ganchos nos momentos certos — e NÃO os chama ao
     sair para o menu ou ao passar por Configurações.

A terceira classe mede o efeito no movimento real, com `ShipMovement` de
verdade: é a prova de que o salto some.
"""

import pygame
import pytest

from game.core.config import config as Config
from game.entities.player.ship import Ship
from game.scenes.paused import PausedScene


# ── Stubs mínimos ───────────────────────────────────────────────────────────


class _App:
    """App mínimo: só o que a pausa e o gancho de ponteiro tocam."""

    def __init__(self):
        self.warps: list[tuple[int, int]] = []
        self.renderer = None
        self._mode = "cursor"

    def warp_cursor(self, pos):
        self.warps.append((int(pos[0]), int(pos[1])))
        return True

    @property
    def cursor_navigation_mode(self):
        return self._mode

    def set_cursor_mode(self, mode):
        self._mode = mode


class _CenaComPonteiro:
    """Cena de gameplay falsa que registra as chamadas dos ganchos."""

    def __init__(self):
        self.chamadas: list[str] = []

    def freeze_pointer(self):
        self.chamadas.append("freeze")

    def restore_pointer(self):
        self.chamadas.append("restore")


def _pausa(previous):
    return PausedScene(_App(), previous_scene=previous)


# ── 1. Contrato da PlayingScene (sem instanciar a cena inteira) ─────────────


class _PlayingLike:
    """Empresta os métodos reais da `PlayingScene` a um objeto mínimo.

    Instanciar a `PlayingScene` de verdade exigiria meia dúzia de sistemas; o
    que está sob teste é a lógica dos dois métodos, que só depende de `ship`,
    `app` e do campo guardado.
    """

    from game.scenes.playing import PlayingScene

    _mouse_drives_ship = PlayingScene._mouse_drives_ship
    freeze_pointer = PlayingScene.freeze_pointer
    restore_pointer = PlayingScene.restore_pointer

    def __init__(self, mouse_control: bool):
        self.app = _App()
        self.ship = Ship(100.0, 100.0, mouse_control=mouse_control)
        self._frozen_pointer = None


class TestGanchosDaPartida:
    """`pygame.mouse.set_pos` não tem efeito no driver dummy (o `get_pos` fica
    em (0,0)), então o ponteiro é simulado por monkeypatch."""

    def _cursor(self, monkeypatch, pos):
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)

    def test_congela_a_posicao_do_ponteiro(self, monkeypatch):
        cena = _PlayingLike(mouse_control=True)
        self._cursor(monkeypatch, (300, 200))
        cena.freeze_pointer()
        assert cena._frozen_pointer == (300, 200)

    def test_restaura_pelo_warp_cursor_e_nao_pelo_set_pos(self, monkeypatch):
        """§19: `set_pos` cru faz o app achar que o jogador pegou no mouse."""
        cena = _PlayingLike(mouse_control=True)
        self._cursor(monkeypatch, (300, 200))
        cena.freeze_pointer()
        self._cursor(monkeypatch, (900, 600))  # jogador mexeu durante a pausa
        cena.restore_pointer()
        assert cena.app.warps == [(300, 200)]

    def test_restaurar_consome_o_valor(self, monkeypatch):
        """Uma segunda chamada não pode reposicionar o ponteiro de novo."""
        cena = _PlayingLike(mouse_control=True)
        self._cursor(monkeypatch, (300, 200))
        cena.freeze_pointer()
        cena.restore_pointer()
        cena.restore_pointer()
        assert cena.app.warps == [(300, 200)]

    def test_sem_controle_por_mouse_nao_guarda_nem_move(self, monkeypatch):
        """Quem joga no teclado/controle não pode ter o ponteiro puxado."""
        cena = _PlayingLike(mouse_control=False)
        self._cursor(monkeypatch, (300, 200))
        cena.freeze_pointer()
        assert cena._frozen_pointer is None
        cena.restore_pointer()
        assert cena.app.warps == []

    def test_restaurar_sem_congelar_nao_faz_nada(self):
        cena = _PlayingLike(mouse_control=True)
        cena.restore_pointer()
        assert cena.app.warps == []


# ── 2. Quando a pausa aciona cada gancho ────────────────────────────────────


class TestFiacaoDaPausa:
    def test_congela_ao_abrir(self):
        prev = _CenaComPonteiro()
        _pausa(prev).enter()
        assert prev.chamadas == ["freeze"]

    def test_restaura_ao_retomar(self):
        prev = _CenaComPonteiro()
        cena = _pausa(prev)
        cena.enter()
        cena.exit()
        assert prev.chamadas == ["freeze", "restore"]

    def test_nao_restaura_ao_sair_para_o_menu(self):
        """Saiu da partida: não há nave para preservar."""
        prev = _CenaComPonteiro()
        cena = _pausa(prev)
        cena.enter()
        cena.go_to_menu = True
        cena.exit()
        assert prev.chamadas == ["freeze"]

    def test_passar_por_configuracoes_preserva_o_ponto_original(self):
        """Pausa → Configurações → volta → retoma.

        O `enter` roda de novo na volta; re-congelar ali guardaria onde o mouse
        ficou na tela de Configurações, que é justamente o que não se quer.
        """
        prev = _CenaComPonteiro()
        cena = _pausa(prev)
        cena.enter()
        cena.go_to_settings = True
        cena.exit()  # empurrou Configurações: nada a restaurar ainda
        assert prev.chamadas == ["freeze"]

        cena.enter()  # voltou de Configurações
        assert prev.chamadas == ["freeze"], "re-congelou e perdeu a posição"

        cena.exit()  # agora sim, retomando
        assert prev.chamadas == ["freeze", "restore"]

    def test_cena_de_baixo_sem_os_ganchos_nao_quebra(self):
        """A pausa cobre qualquer cena; só as de gameplay têm ponteiro a salvar."""
        cena = _pausa(object())
        cena.enter()
        cena.exit()


# ── 3. O efeito medido no movimento real ────────────────────────────────────


class TestSaltoDaNave:
    """Spring-follow de verdade, com `ShipMovement`."""

    DT = 1 / 60

    def _nave_parada_sob_o_cursor(self, monkeypatch, cursor):
        """Nave já convergida para o cursor (estado normal de gameplay)."""
        nave = Ship(0.0, 0.0, mouse_control=True)
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: cursor)
        for _ in range(600):
            nave.move(set(), self.DT)
        return nave

    def _andar(self, nave, monkeypatch, cursor, frames=12):
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: cursor)
        antes = (nave.x, nave.y)
        for _ in range(frames):
            nave.move(set(), self.DT)
        return pygame.math.Vector2(nave.x - antes[0], nave.y - antes[1]).length()

    def test_a_nave_repousa_sob_o_cursor(self):
        """Sanidade do arranjo: com o cursor parado a nave para embaixo dele."""
        mp = pytest.MonkeyPatch()
        try:
            nave = self._nave_parada_sob_o_cursor(mp, (400, 300))
            assert abs(nave.x + nave.w / 2 - 400) < 5
            assert abs(nave.y + nave.h / 2 - 300) < 5
        finally:
            mp.undo()

    def test_sem_restaurar_o_ponteiro_a_nave_salta(self):
        """O defeito, medido: mouse movido na pausa = arranco ao retomar."""
        mp = pytest.MonkeyPatch()
        try:
            nave = self._nave_parada_sob_o_cursor(mp, (400, 300))
            deslocamento = self._andar(nave, mp, (900, 620))
            assert deslocamento > 40, "sem o salto não há o que corrigir"
        finally:
            mp.undo()

    def test_restaurar_o_ponteiro_elimina_o_salto(self):
        mp = pytest.MonkeyPatch()
        try:
            nave = self._nave_parada_sob_o_cursor(mp, (400, 300))
            # A pausa devolveu o ponteiro ao ponto de antes.
            deslocamento = self._andar(nave, mp, (400, 300))
            assert deslocamento < 1.0
        finally:
            mp.undo()

    def test_o_movimento_em_curso_e_preservado(self):
        """A distância guardada nem sempre é zero: se a nave ainda estava indo
        para o cursor, ela tem de CONTINUAR indo, não parar."""
        mp = pytest.MonkeyPatch()
        try:
            nave = Ship(0.0, 0.0, mouse_control=True)
            alvo = (Config.SCREEN_WIDTH * 0.6, Config.SCREEN_HEIGHT * 0.6)
            mp.setattr(pygame.mouse, "get_pos", lambda: alvo)
            for _ in range(10):  # ainda a caminho
                nave.move(set(), self.DT)
            restante = pygame.math.Vector2(
                alvo[0] - (nave.x + nave.w / 2), alvo[1] - (nave.y + nave.h / 2)
            ).length()
            assert restante > 20, "o arranjo precisa de uma nave em trânsito"

            # Retomada com o ponteiro restaurado: segue rumo ao mesmo alvo.
            deslocamento = self._andar(nave, mp, alvo, frames=10)
            assert deslocamento > 5
        finally:
            mp.undo()
