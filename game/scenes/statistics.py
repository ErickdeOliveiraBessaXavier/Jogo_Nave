from typing import Optional, TYPE_CHECKING, Callable, List
import pygame

if TYPE_CHECKING:
    from ..app import GameApp

from ..core import colors
from ..core.colors import Color
from ..core.config import Config
from ..core.assets import get_font
from ..core.meta_progression import PlayerProfile, ProfileVisualizer
from ..core.state import Scene


class Button:
    """Um botão de UI simples."""

    def __init__(self, rect: pygame.Rect, text: str, on_click: Callable[[], None]):
        self.rect = rect
        self.on_click = on_click
        self.font = get_font(24)
        self.text_surf = self.font.render(text, True, colors.WHITE)
        self.text_rect = self.text_surf.get_rect(center=self.rect.center)
        self.hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.on_click()
            return True
        return False

    def update(self) -> None:
        self.hovered = self.rect.collidepoint(pygame.mouse.get_pos())

    def render(self, surface: pygame.Surface, color_normal: Color, color_hover: Color) -> None:
        color = color_hover if self.hovered else color_normal
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, colors.WHITE, self.rect, 2, border_radius=10)
        surface.blit(self.text_surf, self.text_rect)


class ConfirmationDialog:
    """Um diálogo de confirmação."""

    def __init__(self, question_lines: List[str], on_yes: Callable[[], None], on_no: Callable[[], None]):
        self.on_yes = on_yes
        self.on_no = on_no
        self.font = get_font(24)

        self.lines = [self.font.render(line, True, colors.WHITE) for line in question_lines]
        total_height = sum(line.get_height() for line in self.lines) + (len(self.lines) - 1) * 10
        start_y = Config.SCREEN_HEIGHT // 2 - 50 - total_height // 2

        self.line_rects: List[pygame.Rect] = []
        current_y = start_y
        for line in self.lines:
            rect = line.get_rect(center=(Config.SCREEN_WIDTH // 2, current_y + line.get_height() // 2))
            self.line_rects.append(rect)
            current_y += line.get_height() + 10

        self.yes_button = Button(pygame.Rect(0, 0, 100, 40), "Sim", self._on_yes_click)
        self.yes_button.rect.center = (Config.SCREEN_WIDTH // 2 - 60, Config.SCREEN_HEIGHT // 2 + 40)
        self.yes_button.text_surf = get_font(24).render("Sim", True, colors.BLACK)
        self.yes_button.text_rect = self.yes_button.text_surf.get_rect(center=self.yes_button.rect.center)

        self.no_button = Button(pygame.Rect(0, 0, 100, 40), "Não", self._on_no_click)
        self.no_button.rect.center = (Config.SCREEN_WIDTH // 2 + 60, Config.SCREEN_HEIGHT // 2 + 40)
        self.no_button.text_surf = get_font(24).render("Não", True, colors.BLACK)
        self.no_button.text_rect = self.no_button.text_surf.get_rect(center=self.no_button.rect.center)

        self.box_rect = pygame.Rect(Config.SCREEN_WIDTH // 2 - 250, Config.SCREEN_HEIGHT // 2 - 100, 500, 200)
        self.overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        self.overlay.set_alpha(128)
        self.overlay.fill(colors.BLACK)

    def _on_yes_click(self) -> None:
        self.on_yes()

    def _on_no_click(self) -> None:
        self.on_no()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.yes_button.handle_event(event)
        self.no_button.handle_event(event)

    def update(self) -> None:
        self.yes_button.update()
        self.no_button.update()

    def render(self, surface: pygame.Surface) -> None:
        surface.blit(self.overlay, (0, 0))
        pygame.draw.rect(surface, colors.GRAY, self.box_rect, border_radius=10)
        pygame.draw.rect(surface, colors.WHITE, self.box_rect, 3, border_radius=10)

        for line, rect in zip(self.lines, self.line_rects):
            surface.blit(line, rect)

        self.yes_button.render(surface, colors.GREEN, colors.BRIGHT_GREEN)
        self.no_button.render(surface, colors.RED, colors.BRIGHT_RED)


class StatisticsScene(Scene):
    """Cena de estatísticas do jogador."""

    def __init__(self, game_app: "GameApp"):
        super().__init__(game_app)
        self.profile: Optional[PlayerProfile] = None
        self.dialog: Optional[ConfirmationDialog] = None

        self.reset_button = Button(
            pygame.Rect(0, 0, 350, 50),
            "Resetar Perfil",
            self.show_confirmation
        )
        self.reset_button.rect.center = (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT - 100)
        self.reset_button.text_rect = self.reset_button.text_surf.get_rect(
            center=self.reset_button.rect.center
        )

    def enter(self) -> None:
        super().enter()
        self.load_profile()

    def load_profile(self) -> None:
        from pathlib import Path
        profile_path = Path("player_profile.json")
        self.profile = PlayerProfile(profile_path)

    def update(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        if not self.dialog and (keys[pygame.K_ESCAPE] or keys[pygame.K_RETURN]):
            self.app.states.pop()

        if self.dialog:
            self.dialog.update()
        else:
            self.reset_button.update()

        # Auto-save profile if needed
        if self.profile:
            self.profile.auto_save()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.dialog:
            self.dialog.handle_event(event)
        else:
            self.reset_button.handle_event(event)

    def render(self, surface: pygame.Surface) -> None:
        surface.fill(colors.BLACK)

        if not self.profile:
            font = get_font(24)
            text = font.render("Erro ao carregar perfil!", True, colors.RED)
            surface.blit(text, (50, 50))
            return

        ProfileVisualizer.render_statistics_screen(surface, self.profile)

        self.reset_button.render(surface, colors.RED, colors.BRIGHT_RED)

        font = get_font(16)
        instructions = font.render("Pressione ESC ou ENTER para voltar", True, colors.GRAY)
        surface.blit(instructions, (50, Config.SCREEN_HEIGHT - 30))

        if self.dialog:
            self.dialog.render(surface)

    def show_confirmation(self) -> None:
        self.dialog = ConfirmationDialog(
            ["Tem certeza que deseja", "resetar seu perfil?"],
            self.reset_profile,
            self.close_confirmation
        )

    def close_confirmation(self) -> None:
        self.dialog = None

    def reset_profile(self) -> None:
        if self.profile:
            self.profile.reset()
            self.load_profile()
        self.close_confirmation()