import math
import random
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.config import config as Config
from ..core.meta_progression import HighScoreEntry
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp
    from .playing import PlayingScene


_ALLOWED_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")


class InitialsEntryWidget:
    """Modal arcade para digitar 3 iniciais. Retorna 'submit'|'skip'|None."""

    MAX_LEN = 3
    SLOT_W = 60
    SLOT_H = 80
    SLOT_GAP = 16
    CURSOR_PERIOD = 0.5

    def __init__(self, score: int, app: "GameApp"):
        self.chars: List[str] = []
        self.cursor_visible = True
        self.cursor_timer = 0.0
        self.score = score
        self.app = app

        self.font_slot = get_font(60)
        self.font_label = get_font(16)
        self.font_button = get_font(16)
        self.font_rank = get_font(18)

        # Dimensões do Modal
        self.modal_w, self.modal_h = 500, 360
        self.rect = pygame.Rect(
            (Config.SCREEN_WIDTH - self.modal_w) // 2,
            (Config.SCREEN_HEIGHT - self.modal_h) // 2,
            self.modal_w,
            self.modal_h
        )

        total_slots_w = self.SLOT_W * self.MAX_LEN + self.SLOT_GAP * (self.MAX_LEN - 1)
        slots_x0 = self.rect.centerx - total_slots_w // 2
        slot_y = self.rect.top + 100
        
        self.slot_rects: List[pygame.Rect] = [
            pygame.Rect(
                slots_x0 + i * (self.SLOT_W + self.SLOT_GAP),
                slot_y,
                self.SLOT_W,
                self.SLOT_H,
            )
            for i in range(self.MAX_LEN)
        ]

        # Animações
        self.pulse_timer = 0.0
        self.slot_pop_timers = [0.0] * self.MAX_LEN
        self.entry_anim_timer = 0.0

        btn_w, btn_h = 160, 40
        btn_gap = 20
        btn_y = self.rect.bottom - 70
        self.save_button = pygame.Rect(
            self.rect.centerx - btn_w - btn_gap // 2, btn_y, btn_w, btn_h
        )
        self.skip_button = pygame.Rect(
            self.rect.centerx + btn_gap // 2, btn_y, btn_w, btn_h
        )

        self.predicted_rank = self.app.player_profile.get_predicted_rank(self.score)

    def update(self, dt: float) -> None:
        self.cursor_timer += dt
        if self.cursor_timer >= self.CURSOR_PERIOD:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0.0

        self.pulse_timer += dt * 5
        self.entry_anim_timer = min(1.0, self.entry_anim_timer + dt * 2)

        for i in range(self.MAX_LEN):
            if self.slot_pop_timers[i] > 0:
                self.slot_pop_timers[i] = max(0.0, self.slot_pop_timers[i] - dt * 5)

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if self.chars:
                    sound_manager.play_upgrade_activate()
                    return "submit"
                return None
            if event.key == pygame.K_ESCAPE:
                sound_manager.play_sound("button_click")
                return "skip"
            if event.key == pygame.K_BACKSPACE:
                if self.chars:
                    self.chars.pop()
                    sound_manager.play_sound("button_hover")
                return None
            ch = (event.unicode or "").upper()
            if ch in _ALLOWED_CHARS and len(self.chars) < self.MAX_LEN:
                idx = len(self.chars)
                self.chars.append(ch)
                self.slot_pop_timers[idx] = 1.0
                sound_manager.play_sound("button_click")
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.save_button.collidepoint(event.pos) and self.chars:
                sound_manager.play_upgrade_activate()
                return "submit"
            if self.skip_button.collidepoint(event.pos):
                sound_manager.play_sound("button_click")
                return "skip"
        return None

    def get_initials(self) -> str:
        return "".join(self.chars)

    def render(self, surface: pygame.Surface, alpha: int) -> None:
        # Overlay de fundo escuro para o modal
        modal_overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
        modal_overlay.fill((0, 0, 0, int(alpha * 0.7)))
        surface.blit(modal_overlay, (0, 0))

        # Fundo do Modal
        pygame.draw.rect(surface, (15, 15, 25, alpha), self.rect, border_radius=15)
        pygame.draw.rect(surface, (*CUSTOM_GOLD, alpha), self.rect, 2, border_radius=15)

        # Título do Modal
        title_text = self.font_label.render("DIGITE SUAS INICIAIS", True, colors.WHITE)
        title_text.set_alpha(alpha)
        surface.blit(title_text, title_text.get_rect(centerx=self.rect.centerx, top=self.rect.top + 25))

        # Posição prevista
        if self.predicted_rank > 0:
            rank_text = self.font_rank.render(
                f"RECORDE: #{self.predicted_rank} LUGAR!", True, CUSTOM_GOLD
            )
            rank_text.set_alpha(alpha)
            rank_y = self.slot_rects[0].top - 35
            surface.blit(
                rank_text,
                rank_text.get_rect(center=(self.rect.centerx, rank_y)),
            )

        active_idx = min(len(self.chars), self.MAX_LEN - 1)
        for i, rect in enumerate(self.slot_rects):
            pop_scale = 1.0 + 0.15 * self.slot_pop_timers[i]
            entry_scale = math.sin(self.entry_anim_timer * math.pi / 2)
            scale = pop_scale * entry_scale

            slot_w = int(rect.width * scale)
            slot_h = int(rect.height * scale)
            draw_rect = pygame.Rect(0, 0, slot_w, slot_h)
            draw_rect.center = rect.center

            slot_bg = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)
            slot_bg.fill((20, 20, 30, int(alpha * 0.8)))
            surface.blit(slot_bg, draw_rect.topleft)

            border_color = (
                colors.CUSTOM_GOLD if i == active_idx else (100, 100, 100)
            )
            border_surf = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)
            pygame.draw.rect(
                border_surf,
                (*border_color, alpha),
                border_surf.get_rect(),
                3 if i == active_idx else 1,
                border_radius=10,
            )
            surface.blit(border_surf, draw_rect.topleft)

            if i < len(self.chars):
                glyph = self.font_slot.render(self.chars[i], True, CUSTOM_GOLD)
                glyph.set_alpha(alpha)
                surface.blit(glyph, glyph.get_rect(center=rect.center))
            elif i == active_idx and self.cursor_visible:
                caret = self.font_slot.render("_", True, CUSTOM_GOLD)
                caret.set_alpha(int(alpha * 0.6))
                surface.blit(caret, caret.get_rect(center=(rect.centerx, rect.centery + 10)))

        label = self.font_label.render(
            "ENTER: SALVAR   ESC: PULAR",
            True,
            (180, 180, 180),
        )
        label.set_alpha(alpha)
        label_y = self.slot_rects[0].bottom + 25
        surface.blit(label, label.get_rect(center=(self.rect.centerx, label_y)))

        draw_bordered_button(surface, self.save_button, "SALVAR", self.font_button, CUSTOM_GOLD, alpha)
        draw_bordered_button(surface, self.skip_button, "PULAR", self.font_button, CUSTOM_PURPLE, alpha)


class GameOverScene(Scene):
    def __init__(self, app: "GameApp", score: int, playing_scene: "PlayingScene", restart_level: int = 1):
        super().__init__(app)
        self.score = score
        self.playing_scene = playing_scene
        self.restart_level = max(1, restart_level)
        self.r = playing_scene.r

        self.game_over_timer = 0.0
        self.game_over_font_title = get_font(80)
        self.game_over_font_score = get_font(36)
        self.game_over_font_prompt = get_font(18)
        self.game_over_font_button = get_font(16)
        
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))

        # Game over effects
        self.playing_scene.ship.visible = False
        sound_manager.play_ship_explosion()
        self.playing_scene.entity_manager.spawn_explosion(
            self.playing_scene.ship.rect.centerx,
            self.playing_scene.ship.rect.centery,
            size=120,
        )
        self.playing_scene.screen_shake_timer = 0.6
        self.playing_scene.screen_shake_intensity = Config.SCREEN_SHAKE_GAME_OVER

        # Layout padronizado
        btn_w, btn_h = 220, 40
        self.back_to_menu_button = pygame.Rect(
            40, 
            Config.SCREEN_HEIGHT - 60, 
            btn_w, btn_h
        )

        self.high_score_qualified = self.app.player_profile.qualifies_for_high_score(self.score)
        self.entry_submitted = not self.high_score_qualified
        self.entry_widget: Optional[InitialsEntryWidget] = None
        
        if self.high_score_qualified:
            self.entry_widget = InitialsEntryWidget(
                score=self.score,
                app=self.app,
            )

        self.ranking_sound_played = False

    def enter(self):
        pygame.mouse.set_visible(True)

    def update(self, dt: float):
        self.game_over_timer += dt
        slow_mo_dt = dt * 0.15

        self.playing_scene.entity_manager.update_for_game_over_slow_motion(
            slow_mo_dt,
            self.playing_scene.ship.rect.centerx,
            self.playing_scene.ship.rect.centery,
        )

        if self.high_score_qualified and self.game_over_timer > Config.GAME_OVER_RESTART_DELAY:
            if not self.ranking_sound_played:
                sound_manager.play_powerup()
                self.ranking_sound_played = True

        if self.entry_widget is not None and not self.entry_submitted:
            self.entry_widget.update(dt)

    def handle_event(self, event: pygame.event.Event):
        if self.entry_widget is not None and not self.entry_submitted:
            if self.game_over_timer > Config.GAME_OVER_RESTART_DELAY:
                result = self.entry_widget.handle_event(event)
                if result == "submit":
                    self._submit_high_score(self.entry_widget.get_initials())
                    self.entry_submitted = True
                elif result == "skip":
                    self.entry_submitted = True
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            from .playing import PlayingScene
            self.app.states.switch(
                PlayingScene(
                    self.app,
                    self.playing_scene.level_manager,
                    self.playing_scene.difficulty_preset,
                    starting_level=self.restart_level,
                )
            )
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.back_to_menu_button.collidepoint(event.pos):
                self._return_to_menu()

    def _submit_high_score(self, initials_raw: str) -> None:
        initials = (initials_raw or "AAA").upper()[:3].ljust(3, "A")
        entry = HighScoreEntry(
            initials=initials,
            score=self.score,
            level_reached=self.playing_scene.current_level_index + 1,
            difficulty=self.playing_scene.difficulty_preset.value,
            achieved_at=datetime.now(),
        )
        self.app.player_profile.submit_high_score(entry)
        self.app.player_profile.save()

    def _return_to_menu(self):
        sound_manager.stop_music()
        from ..core.sound_config import MusicState
        sound_manager.music_state_manager.transition_to(MusicState.MENU, force=True)
        from .main_menu import MainMenuScene
        self.app.states.switch(MainMenuScene(self.app))

    def render(self, surface: pygame.Surface):
        dt = getattr(self.playing_scene, "last_dt", 1.0 / Config.FPS)
        self.r.background(self.game_surface, dt=dt, speed_multiplier=1.0)
        self.playing_scene.entity_manager.draw(
            self.game_surface,
            self.playing_scene.ship.rect.centerx,
            self.playing_scene.ship.rect.centery,
            enemy_visible=True,
        )
        
        shake_offset = (0, 0)
        if self.playing_scene.screen_shake_timer > 0:
            shake_offset = (
                random.randint(-self.playing_scene.screen_shake_intensity, self.playing_scene.screen_shake_intensity),
                random.randint(-self.playing_scene.screen_shake_intensity, self.playing_scene.screen_shake_intensity),
            )
        surface.blit(self.game_surface, shake_offset)

        # Overlay escurecido
        progress = min(1.0, self.game_over_timer / Config.GAME_OVER_FADE_DURATION)
        overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(progress * 200)))
        surface.blit(overlay, (0, 0))

        text_alpha = int(progress * 255)
        center_x = Config.SCREEN_WIDTH // 2
        center_y = Config.SCREEN_HEIGHT // 2
        
        # Título: GAME OVER
        title_surf = self.game_over_font_title.render("GAME OVER", True, colors.WHITE)
        title_surf.set_alpha(text_alpha)
        title_rect = title_surf.get_rect(center=(center_x, center_y - 140))
        surface.blit(title_surf, title_rect)

        # Score
        if self.game_over_timer > Config.GAME_OVER_RESTART_DELAY:
            sub_progress = min(1.0, (self.game_over_timer - Config.GAME_OVER_RESTART_DELAY) / 0.8)
            sub_alpha = int(sub_progress * 255)

            score_surf = self.game_over_font_score.render(f"PONTUAÇÃO: {self.score:,}".replace(",", "."), True, colors.WHITE)
            score_surf.set_alpha(sub_alpha)
            score_rect = score_surf.get_rect(center=(center_x, center_y - 40))
            surface.blit(score_surf, score_rect)

            if self.entry_widget is not None and not self.entry_submitted:
                self.entry_widget.render(surface, sub_alpha)
            else:
                restart_surf = self.game_over_font_prompt.render("PRESSIONE 'R' PARA REINICIAR", True, colors.WHITE)
                restart_surf.set_alpha(sub_alpha)
                surface.blit(restart_surf, restart_surf.get_rect(center=(center_x, center_y + 40)))

                # Botão "Voltar ao Menu"
                draw_bordered_button(
                    surface,
                    self.back_to_menu_button,
                    "VOLTAR AO MENU",
                    self.game_over_font_button,
                    CUSTOM_PURPLE,
                    sub_alpha
                )

    def exit(self):
        pygame.mouse.set_visible(False)
        self.playing_scene.ship.visible = True
        self.playing_scene.screen_shake_timer = 0.0
        self.playing_scene.screen_shake_intensity = 0
