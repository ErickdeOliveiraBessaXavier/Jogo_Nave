import pygame
from typing import TYPE_CHECKING, List, Optional

from ..core.state import Scene
from ..core.config import config as Config
from ..core.colors import WHITE, BLACK, GRAY, GREEN, BLUE
from ..core.assets import get_font
from ..core.upgrades import list_all_upgrades_meta, UpgradeType
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from ..render.renderer import Renderer
from ..core.meta_progression import PlayerProfile
from pathlib import Path

if TYPE_CHECKING:
    from ..app import GameApp


class UpgradesSelectionScene(Scene):
    """Cena simples de seleção/equipamento de aprimoramentos (MVP).

    Controles:
    - Setas Cima/Baixo: navegar na lista de upgrades
    - 1 / 2: escolhe o slot (exibido no canto superior esquerdo da caixa)
    - Enter: equipa o upgrade selecionado no slot escolhido
    - Backspace: limpa o slot escolhido
    - Esc: voltar e salvar
    """

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = Renderer()
        self.title_font = get_font(40)
        self.item_font = get_font(20)
        self.help_font = get_font(16)
        self.slot_font = get_font(14)  # Fonte menor para slots

        self.upgrades = list_all_upgrades_meta()
        self.selected_index = 0
        self.selected_slot = 0  # 0..UPGRADE_SLOT_COUNT-1

        # Carregar/instanciar perfil
        self.player_profile = PlayerProfile(Path("player_profile.json"))
        # Garantir tamanho do loadout
        if len(self.player_profile.upgrade_loadout) != UPGRADE_SLOT_COUNT:
            base: List[Optional[UpgradeType]] = list(
                self.player_profile.upgrade_loadout[:UPGRADE_SLOT_COUNT]
            )
            while len(base) < UPGRADE_SLOT_COUNT:
                base.append(None)
            self.player_profile.upgrade_loadout = base

    def enter(self):
        pygame.mouse.set_visible(True)

    def exit(self):
        pygame.mouse.set_visible(True)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.player_profile.save()
                self.app.states.pop()
            elif event.key == pygame.K_DOWN:
                self.selected_index = (self.selected_index + 1) % len(self.upgrades)
            elif event.key == pygame.K_UP:
                self.selected_index = (self.selected_index - 1) % len(self.upgrades)
            elif event.key == pygame.K_1:
                self.selected_slot = 0
            elif event.key == pygame.K_2 and UPGRADE_SLOT_COUNT >= 2:
                self.selected_slot = 1
            elif event.key == pygame.K_RETURN:
                meta = self.upgrades[self.selected_index]
                # Equipar somente se desbloqueado
                if meta.type in self.player_profile.unlocked_upgrades:
                    self.player_profile.upgrade_loadout[self.selected_slot] = meta.type
                    self.player_profile.save()
            elif event.key == pygame.K_BACKSPACE:
                self.player_profile.upgrade_loadout[self.selected_slot] = None
                self.player_profile.save()

    def update(self, dt: float):
        self.r.starfield.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        # Título
        title = self.title_font.render("Aprimoramentos", True, WHITE)
        surface.blit(title, (40, 30))

        # Ajuda (mostra teclas atuais para ativação)
        key_names = [
            pygame.key.name(k).upper()
            for k in self.player_profile.upgrade_keybindings[:UPGRADE_SLOT_COUNT]
        ]
        keys_display = "/".join(key_names) if key_names else "1/2"
        help_lines = [
            f"Cima/Baixo: navegar | {keys_display}: escolher slot | Enter: equipar",
            "Backspace: limpar slot | Esc: voltar",
        ]
        for i, line in enumerate(help_lines):
            txt = self.help_font.render(line, True, WHITE)
            surface.blit(txt, (40, 80 + i * 20))

        # Slots
        slot_y = 130
        for slot in range(UPGRADE_SLOT_COUNT):
            rect = pygame.Rect(40 + slot * 220, slot_y, 200, 70)
            color = BLUE if slot == self.selected_slot else GRAY
            pygame.draw.rect(surface, color, rect, border_radius=10)
            pygame.draw.rect(surface, WHITE, rect, 2, border_radius=10)

            # Tecla vinculada no canto superior esquerdo
            try:
                keycode = self.player_profile.upgrade_keybindings[slot]
                key_label = pygame.key.name(keycode).upper()
            except Exception:
                key_label = str(slot + 1)
            num_txt = self.slot_font.render(key_label, True, WHITE)
            surface.blit(num_txt, (rect.x + 8, rect.y + 6))

            # Nome do aprimoramento no centro
            equipped = self.player_profile.upgrade_loadout[slot]
            if equipped:
                name = equipped.name
                if len(name) > 15:  # Truncar se necessário
                    name = name[:13] + ".."
            else:
                name = "--"

            name_txt = self.slot_font.render(name, True, WHITE)
            # Centralizar no meio da caixa
            name_x = rect.x + (rect.width - name_txt.get_width()) // 2
            name_y = rect.y + (rect.height - name_txt.get_height()) // 2
            surface.blit(name_txt, (name_x, name_y))

        # Lista de upgrades
        list_x, list_y = 40, 230
        item_h = 34
        visible = 15
        start = max(0, self.selected_index - visible // 2)
        end = min(len(self.upgrades), start + visible)
        start = max(0, end - visible)

        for i in range(start, end):
            meta = self.upgrades[i]
            y = list_y + (i - start) * item_h
            is_sel = i == self.selected_index

            # Fundo
            row_rect = pygame.Rect(list_x, y, 560, item_h - 4)
            pygame.draw.rect(
                surface, (50, 50, 50) if is_sel else (35, 35, 35), row_rect
            )
            pygame.draw.rect(surface, WHITE if is_sel else GRAY, row_rect, 1)

            # Nome + estado
            unlocked = meta.type in self.player_profile.unlocked_upgrades
            name_color = GREEN if unlocked else GRAY
            name_txt = self.item_font.render(meta.name, True, name_color)
            surface.blit(name_txt, (row_rect.x + 10, row_rect.y + 6))

            # Descrição (apenas quando selecionado)
            if is_sel:
                desc_lines = [meta.desc]
                for j, line in enumerate(desc_lines):
                    d_txt = self.help_font.render(line, True, WHITE)
                    surface.blit(d_txt, (list_x + 600, list_y + j * 18))

        # Legenda do selecionado
        meta = self.upgrades[self.selected_index]
        footer_lines = [
            f"Selecionado: {meta.name}",
            f"Cooldown base: {meta.base_cooldown:.0f}s | Duração: {meta.base_duration:.1f}s",
        ]
        for i, line in enumerate(footer_lines):
            f_txt = self.item_font.render(line, True, WHITE)
            surface.blit(f_txt, (40, Config.SCREEN_HEIGHT - 80 + i * 24))
