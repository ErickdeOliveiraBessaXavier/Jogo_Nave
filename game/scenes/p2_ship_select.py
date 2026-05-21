"""p2_ship_select.py — Modal de seleção de nave para o Jogador 2.

Empurrado sobre `PlayingScene` quando P2 aperta Start no segundo controle.
A partida pausa enquanto este modal está ativo. Mostra um carrossel com
apenas as naves desbloqueadas pelo perfil de P1 (regra do plano de coop:
P2 herda desbloqueios).

Operado exclusivamente pelo controle do slot 1 (gamepad de P2):
- D-pad ⬅/➡ ou LS X — navegar entre naves
- A — confirmar e spawnar P2
- B — cancelar e voltar à partida sem juntar P2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List

import pygame

from ..core.assets import get_font
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE, WHITE
from ..core.config import config as Config
from ..core.gamepad import XboxButton
from ..core.ship_types import ShipProfile, all_ship_profiles
from ..core.sound import sound_manager
from ..core.state import Scene

if TYPE_CHECKING:
    from ..app import GameApp
    from .playing import PlayingScene

logger = logging.getLogger(__name__)

# Slot do gamepad de P2 no GamepadManager. P2 é obrigatoriamente o segundo
# controle conectado — multiplayer não usa teclado dividido.
P2_GAMEPAD_SLOT: int = 1

# Velocidade do stick esquerdo a partir da qual contamos como "navegação"
# (evita repetição inadvertida por drift do analógico).
_LS_NAV_THRESHOLD: float = 0.6


class P2ShipSelectScene(Scene):
    """Modal de seleção de nave do Jogador 2."""

    def __init__(
        self,
        app: "GameApp",
        playing_scene: "PlayingScene",
        on_confirm: Callable[[ShipProfile], None],
    ) -> None:
        super().__init__(app)
        self.r = app.renderer
        self.playing_scene = playing_scene
        self.on_confirm = on_confirm
        self.title_font = get_font(48)
        self.name_font = get_font(36)
        self.desc_font = get_font(18)
        self.hint_font = get_font(14)

        unlocked_ids = playing_scene.player_profile.unlocked_ships
        self.profiles: List[ShipProfile] = [
            p for p in all_ship_profiles() if p.id in unlocked_ids
        ]
        if not self.profiles:
            # Defensivo: nave padrão sempre está desbloqueada pelo construtor
            # do PlayerProfile. Esse fallback evita crash se algum perfil corrompido
            # chegar até aqui — apenas fecha o modal.
            self.profiles = list(all_ship_profiles())[:1]

        self.index: int = 0
        # Estado anterior do LS para detectar "presses" (transições neutro→inclinado).
        self._ls_prev_x_pressed: int = 0  # -1, 0 ou +1
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def enter(self) -> None:
        sound_manager.pause_music()

    def exit(self) -> None:
        sound_manager.resume_music()

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._closed:
            return
        if event.type == pygame.JOYBUTTONDOWN:
            self._handle_button(event)
        elif event.type == pygame.JOYHATMOTION:
            self._handle_hat(event)
        elif event.type == pygame.KEYDOWN:
            # Fallback no teclado para depuração — ESC fecha o modal.
            if event.key == pygame.K_ESCAPE:
                self._cancel()
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._navigate(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._navigate(+1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._confirm()

    def _handle_button(self, event: pygame.event.Event) -> None:
        # Aceitamos apenas botões do gamepad atribuído ao slot 1 (P2).
        slot = self.app.gamepad.slot_of_instance_id(event.instance_id)
        if slot != P2_GAMEPAD_SLOT:
            return
        if event.button == XboxButton.A:
            self._confirm()
        elif event.button == XboxButton.B:
            self._cancel()

    def _handle_hat(self, event: pygame.event.Event) -> None:
        slot = self.app.gamepad.slot_of_instance_id(event.instance_id)
        if slot != P2_GAMEPAD_SLOT:
            return
        x, _y = event.value
        if x < 0:
            self._navigate(-1)
        elif x > 0:
            self._navigate(+1)

    # ------------------------------------------------------------------
    # Update / Render
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        if self._closed:
            return
        # LS do P2 também navega — detectamos transições neutro→inclinado.
        ls_x, _ = self.app.gamepad.get_stick("left", slot=P2_GAMEPAD_SLOT)
        ls_pressed = (
            -1 if ls_x < -_LS_NAV_THRESHOLD else (1 if ls_x > _LS_NAV_THRESHOLD else 0)
        )
        if ls_pressed != 0 and ls_pressed != self._ls_prev_x_pressed:
            self._navigate(ls_pressed)
        self._ls_prev_x_pressed = ls_pressed

    def render(self, surface: pygame.Surface) -> None:
        # Renderiza a cena de gameplay em pausa por baixo (preserva contexto visual).
        try:
            self.playing_scene.render(surface)
        except Exception:  # noqa: BLE001 — proteger o modal de erros de render
            logger.exception("Falha ao desenhar cena por baixo do modal P2")
            surface.fill((0, 0, 0))

        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        title_surf = self.title_font.render(
            "JOGADOR 2 — escolha sua nave", True, CUSTOM_GOLD
        )
        surface.blit(
            title_surf,
            (
                (Config.SCREEN_WIDTH - title_surf.get_width()) // 2,
                Config.SCREEN_HEIGHT // 2 - 200,
            ),
        )

        profile = self.profiles[self.index]
        name_surf = self.name_font.render(profile.display_name, True, WHITE)
        surface.blit(
            name_surf,
            (
                (Config.SCREEN_WIDTH - name_surf.get_width()) // 2,
                Config.SCREEN_HEIGHT // 2 - 90,
            ),
        )

        # Descrição quebrada em linhas (heurística simples por palavras).
        self._draw_wrapped(
            surface,
            profile.description,
            y_start=Config.SCREEN_HEIGHT // 2 - 30,
            max_width=int(Config.SCREEN_WIDTH * 0.65),
        )

        counter = self.hint_font.render(
            f"{self.index + 1} / {len(self.profiles)}", True, CUSTOM_PURPLE
        )
        surface.blit(
            counter,
            (
                (Config.SCREEN_WIDTH - counter.get_width()) // 2,
                Config.SCREEN_HEIGHT // 2 + 110,
            ),
        )

        hints = "⬅ ➡ navegar     A confirmar     B cancelar"
        hint_surf = self.hint_font.render(hints, True, WHITE)
        surface.blit(
            hint_surf,
            (
                (Config.SCREEN_WIDTH - hint_surf.get_width()) // 2,
                Config.SCREEN_HEIGHT - 60,
            ),
        )

    def _draw_wrapped(
        self,
        surface: pygame.Surface,
        text: str,
        y_start: int,
        max_width: int,
    ) -> None:
        words = text.split()
        lines: List[str] = []
        current: List[str] = []
        for word in words:
            tentative = " ".join(current + [word])
            if self.desc_font.size(tentative)[0] <= max_width:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))

        line_h = self.desc_font.get_linesize()
        for i, line in enumerate(lines):
            surf = self.desc_font.render(line, True, WHITE)
            surface.blit(
                surf,
                (
                    (Config.SCREEN_WIDTH - surf.get_width()) // 2,
                    y_start + i * line_h,
                ),
            )

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _navigate(self, direction: int) -> None:
        self.index = (self.index + direction) % len(self.profiles)

    def _confirm(self) -> None:
        if self._closed:
            return
        self._closed = True
        chosen = self.profiles[self.index]
        logger.info("P2 escolheu nave: %s", chosen.id)
        self.app.states.pop()
        self.on_confirm(chosen)

    def _cancel(self) -> None:
        if self._closed:
            return
        self._closed = True
        logger.info("P2 cancelou seleção de nave")
        self.app.states.pop()

    # Compat com base Scene caso o motor exija get_focusable_rects.
    def get_focusable_rects(self) -> List[pygame.Rect]:
        return []
