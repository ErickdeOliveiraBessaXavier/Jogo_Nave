from typing import Optional, TYPE_CHECKING
import pygame

if TYPE_CHECKING:
    from ..app import GameApp

from ..core import colors
from ..core.config import Config
from ..core.assets import get_font
from ..core.meta_progression import PlayerProfile, ProfileVisualizer
from ..core.state import Scene


class StatisticsScene(Scene):
    """Cena de estatísticas do jogador."""

    def __init__(self, game_app: "GameApp"):
        super().__init__(game_app)
        self.profile: Optional[PlayerProfile] = None

    def enter(self):
        """Chamado quando a cena é ativada."""
        super().enter()
        # Carregar perfil do jogador
        from pathlib import Path
        profile_path = Path("player_profile.json")
        self.profile = PlayerProfile(profile_path)

    def exit(self):
        """Chamado quando a cena é desativada."""
        super().exit()

    def update(self, dt: float):
        """Atualiza lógica da cena."""
        # Verificar input para voltar
        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE] or keys[pygame.K_RETURN]:
            self.app.states.pop()

    def render(self, surface: pygame.Surface):
        """Renderiza a cena."""
        # Fundo
        surface.fill(colors.BLACK)

        if not self.profile:
            # Mensagem de erro
            font = get_font(24)
            text = font.render("Erro ao carregar perfil!", True, colors.RED)
            surface.blit(text, (50, 50))
            return

        # Renderizar estatísticas completas
        ProfileVisualizer.render_statistics_screen(surface, self.profile)

        # Instruções
        font = get_font(16)
        instructions = font.render("Pressione ESC ou ENTER para voltar", True, colors.GRAY)
        surface.blit(instructions, (50, Config.SCREEN_HEIGHT - 30))