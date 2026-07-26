"""p2_ship_select.py — Modal de seleção de nave para o Jogador 2.

Empurrado sobre `PlayingScene` quando P2 aperta Start no segundo controle.
A partida pausa enquanto este modal está ativo. Mostra um carrossel com
apenas as naves desbloqueadas pelo perfil de P1 (regra do plano de coop:
P2 herda desbloqueios).

Operado exclusivamente pelo controle do slot 1 (gamepad de P2):
- D-pad ⬅/➡ ou LS X — navegar entre naves
- LB/RB — navegar entre naves
- A — confirmar e spawnar P2
- B — cancelar e voltar à partida sem juntar P2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List

import pygame

from ..core.assets import BASE_DIR, get_font, get_image
from ..core.colors import CUSTOM_DARK_BG, CUSTOM_GOLD, CUSTOM_PURPLE, WHITE, GRAY
from ..core.config import config as Config
from ..core.gamepad import XboxButton
from ..core.i18n import t
from ..core.ship_types import (
    ShipProfile,
    all_ship_profiles,
    format_ship_description,
    ship_display_name,
    ship_tags,
)
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import get_fade_scratch

if TYPE_CHECKING:
    from ..app import GameApp
    from .playing import PlayingScene

logger = logging.getLogger(__name__)

# Slot do gamepad de P2 no GamepadManager.
P2_GAMEPAD_SLOT: int = 1
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
        self.playing_scene = playing_scene
        self.on_confirm = on_confirm

        # Fontes escalonadas
        self.title_font = get_font(max(8, int(42 * self.ui_scale)))
        self.name_font = get_font(max(8, int(32 * self.ui_scale)))
        self.tag_font = get_font(max(8, int(12 * self.ui_scale)))
        self.desc_font = get_font(max(8, int(18 * self.ui_scale)))
        self.hint_font = get_font(max(8, int(16 * self.ui_scale)))

        unlocked_ids = playing_scene.player_profile.unlocked_ships
        self.profiles: List[ShipProfile] = [
            p for p in all_ship_profiles() if p.id in unlocked_ids
        ]
        if not self.profiles:
            self.profiles = list(all_ship_profiles())[:1]

        self.index: int = 0
        self._ls_prev_x_pressed: int = 0
        self._closed: bool = False
        # Snapshot do instance_id do gamepad do P2 — usado pra detectar
        # desconexão durante a seleção (cancela como se fosse B).
        self._p2_instance_id: int | None = self.app.gamepad.slot_instance_id(
            P2_GAMEPAD_SLOT
        )

        # Configurações de layout
        self.card_w = self._s(600)
        self.card_h = self._s(450)
        self.card_rect = pygame.Rect(
            (Config.SCREEN_WIDTH - self.card_w) // 2,
            (Config.SCREEN_HEIGHT - self.card_h) // 2 + self._s(20),
            self.card_w,
            self.card_h,
        )

    def enter(self) -> None:
        sound_manager.pause_music()

    def exit(self) -> None:
        sound_manager.resume_music()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._closed:
            return
        if event.type == pygame.JOYBUTTONDOWN:
            self._handle_button(event)
        elif event.type == pygame.JOYHATMOTION:
            self._handle_hat(event)
        elif event.type == pygame.JOYDEVICEREMOVED:
            if (
                self._p2_instance_id is not None
                and event.instance_id == self._p2_instance_id
            ):
                logger.info(
                    "Gamepad de P2 desconectou durante seleção — cancelando modal"
                )
                self._cancel()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._cancel()
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._navigate(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._navigate(+1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._confirm()

    def _handle_button(self, event: pygame.event.Event) -> None:
        slot = self.app.gamepad.slot_of_instance_id(event.instance_id)
        if slot != P2_GAMEPAD_SLOT:
            return
        if event.button == XboxButton.A:
            self._confirm()
        elif event.button == XboxButton.B:
            self._cancel()
        elif event.button == XboxButton.LB:
            self._navigate(-1)
        elif event.button == XboxButton.RB:
            self._navigate(+1)

    def _handle_hat(self, event: pygame.event.Event) -> None:
        slot = self.app.gamepad.slot_of_instance_id(event.instance_id)
        if slot != P2_GAMEPAD_SLOT:
            return
        x, _y = event.value
        if x < 0:
            self._navigate(-1)
        elif x > 0:
            self._navigate(+1)

    def update(self, dt: float) -> None:
        if self._closed:
            return
        ls_x, _ = self.app.gamepad.get_stick("left", slot=P2_GAMEPAD_SLOT)
        ls_pressed = (
            -1 if ls_x < -_LS_NAV_THRESHOLD else (1 if ls_x > _LS_NAV_THRESHOLD else 0)
        )
        if ls_pressed != 0 and ls_pressed != self._ls_prev_x_pressed:
            self._navigate(ls_pressed)
        self._ls_prev_x_pressed = ls_pressed

    def render(self, surface: pygame.Surface) -> None:
        try:
            self.playing_scene.render(surface)
        except Exception:
            logger.exception("Falha ao desenhar cena por baixo do modal P2")
            surface.fill((0, 0, 0))

        # Overlay escuro, animado pelo relógio do `SceneTransition` (DIM, como
        # a pausa): sobe ao abrir, cai ao fechar. Sem ler `overlay_progress` o
        # modal ficaria parado durante a saída e sumiria de um frame para o
        # outro no fim dela — pior que o corte seco que havia antes.
        # Scratch compartilhado: nada de SRCALPHA de tela cheia por frame com a
        # partida do P1 rodando por baixo.
        enter = self.app.transition.overlay_progress
        overlay = get_fade_scratch((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        overlay.fill((0, 0, 0, int(210 * enter)))
        surface.blit(overlay, (0, 0))

        # Título
        title_surf = self.title_font.render(t("p2.title"), True, CUSTOM_GOLD)
        surface.blit(
            title_surf, ((Config.SCREEN_WIDTH - title_surf.get_width()) // 2, self._s(60))
        )

        # Card Central
        card_radius = self._s(15)
        pygame.draw.rect(surface, CUSTOM_DARK_BG, self.card_rect, border_radius=card_radius)
        pygame.draw.rect(
            surface, CUSTOM_PURPLE, self.card_rect, width=3, border_radius=card_radius
        )

        profile = self.profiles[self.index]

        # 1. Sprite da Nave (Escalado — fator base ×4 ajustado pela ui_scale)
        icon_path = BASE_DIR / "assets" / "icons" / profile.sprite_filename
        icon_surf = get_image(icon_path)
        if icon_surf:
            preview_factor = 4 * self.ui_scale
            scaled_size = (
                int(icon_surf.get_width() * preview_factor),
                int(icon_surf.get_height() * preview_factor),
            )
            ship_preview = pygame.transform.scale(icon_surf, scaled_size)
            surface.blit(
                ship_preview,
                (
                    self.card_rect.centerx - ship_preview.get_width() // 2,
                    self.card_rect.top + self._s(40),
                ),
            )

        # 2. Nome da Nave
        name_surf = self.name_font.render(ship_display_name(profile).upper(), True, WHITE)
        surface.blit(
            name_surf,
            (
                self.card_rect.centerx - name_surf.get_width() // 2,
                self.card_rect.top + self._s(160),
            ),
        )

        # 3. Tags
        tags = ship_tags(profile)
        if tags:
            tag_y = self.card_rect.top + self._s(210)
            total_tags_w = (
                sum(self.tag_font.size(tg)[0] + self._s(20) for tg in tags)
                - self._s(10)
            )
            start_x = self.card_rect.centerx - total_tags_w // 2

            curr_x = start_x
            for tag in tags:
                tag_surf = self.tag_font.render(tag, True, CUSTOM_GOLD)
                tag_bg = pygame.Rect(
                    curr_x,
                    tag_y,
                    tag_surf.get_width() + self._s(16),
                    tag_surf.get_height() + self._s(8),
                )
                pygame.draw.rect(surface, (40, 40, 60), tag_bg, border_radius=self._s(5))
                surface.blit(tag_surf, (tag_bg.x + self._s(8), tag_bg.y + self._s(4)))
                curr_x += tag_bg.width + self._s(10)

        # 4. Descrição (Formatada e com Wrap)
        desc_text = format_ship_description(profile, gamepad_active=True)
        self._draw_wrapped_centered(
            surface,
            desc_text,
            y_start=self.card_rect.top + self._s(260),
            max_width=self.card_w - self._s(60),
        )

        # Setas de navegação
        arrow_color = (
            CUSTOM_GOLD if (pygame.time.get_ticks() // 500) % 2 == 0 else WHITE
        )
        # Esquerda
        self._draw_arrow(
            surface,
            (self.card_rect.left - self._s(40), self.card_rect.centery),
            -1,
            arrow_color,
        )
        # Direita
        self._draw_arrow(
            surface,
            (self.card_rect.right + self._s(40), self.card_rect.centery),
            1,
            arrow_color,
        )

        # Contador
        counter = self.hint_font.render(
            f"{self.index + 1} / {len(self.profiles)}", True, GRAY
        )
        surface.blit(
            counter,
            (
                self.card_rect.centerx - counter.get_width() // 2,
                self.card_rect.bottom + self._s(15),
            ),
        )

        # Dicas de controles
        hint_y = Config.SCREEN_HEIGHT - self._s(60)
        hints = [
            ("L/R", t("common.navigate")),
            ("A", t("common.confirm")),
            ("B", t("common.cancel")),
        ]

        hint_x_start = Config.SCREEN_WIDTH // 2 - self._s(200)
        for btn, action in hints:
            b_surf = self.hint_font.render(btn, True, CUSTOM_GOLD)
            a_surf = self.hint_font.render(action, True, WHITE)
            surface.blit(b_surf, (hint_x_start, hint_y))
            surface.blit(a_surf, (hint_x_start + b_surf.get_width() + self._s(10), hint_y))
            hint_x_start += self._s(160)

    def _draw_arrow(
        self,
        surface: pygame.Surface,
        pos: tuple[int, int],
        direction: int,
        color: tuple[int, int, int],
    ) -> None:
        x, y = pos
        size = self._s(20)
        points = [(x, y - size), (x + direction * size, y), (x, y + size)]
        pygame.draw.polygon(surface, color, points)

    def _draw_wrapped_centered(
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

        line_h = self.desc_font.get_linesize() + self._s(4)
        for i, line in enumerate(lines):
            surf = self.desc_font.render(line, True, WHITE)
            surface.blit(
                surf,
                (
                    self.card_rect.centerx - surf.get_width() // 2,
                    y_start + i * line_h,
                ),
            )

    def _navigate(self, direction: int) -> None:
        self.index = (self.index + direction) % len(self.profiles)
        sound_manager.play_sound("button_hover")

    def _confirm(self) -> None:
        if self._closed:
            return
        self._closed = True
        chosen = self.profiles[self.index]
        logger.info("P2 escolheu nave: %s", chosen.id)
        sound_manager.play_sound("button_click")
        # Overlay (DIM): fecha sem véu preto, a partida segue viva por baixo.
        self.app.close_overlay()
        self.on_confirm(chosen)

    def _cancel(self) -> None:
        if self._closed:
            return
        self._closed = True
        logger.info("P2 cancelou seleção de nave")
        self.app.close_overlay()

    def get_focusable_rects(self) -> List[pygame.Rect]:
        return []
