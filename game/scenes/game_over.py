import math
import random
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.config import config as Config
from ..core.i18n import fmt_num, t
from ..core.meta_progression import HighScoreEntry
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp
    from .playing import PlayingScene


_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class InitialsEntryWidget:
    """Modal estilo arcade com 3 colunas-roleta de letras.

    Cada coluna mantém um índice no alfabeto; DPad/LS vertical troca a letra
    da coluna ativa (com wrap A↔Z), DPad/LS horizontal alterna a coluna ativa,
    A confirma. Animação de scroll dá sensação de rotação contínua.

    O nome ``InitialsEntryWidget`` foi preservado pra não quebrar referências
    no GameOverScene — a interface (``handle_event``, ``get_initials``,
    ``update``, ``render``, ``save_button``, ``skip_button``) segue idêntica.
    """

    MAX_LEN = 3
    COL_W = 80
    COL_H = 220
    COL_GAP = 32
    LETTER_HEIGHT = 64  # espaço vertical entre letras na roleta
    VISIBLE_RADIUS = 2  # quantas letras acima/abaixo da ativa mostrar

    def __init__(self, score: int, app: "GameApp"):
        # Índices no alfabeto (0=A, 25=Z) por posição. Começa em AAA.
        self.indices: List[int] = [0, 0, 0]
        self.active_pos: int = 0
        self.score = score
        self.app = app

        # Escala de UI (convenções do projeto §12). Este widget não é uma Scene, então
        # mantém seu próprio fator e helper. As COL_*/LETTER_HEIGHT de classe
        # são o design base 1280×720; aqui derivamos as versões escaladas.
        self.ui_scale = Config.SCREEN_WIDTH / 1280.0
        self.col_w = self._s(self.COL_W)
        self.col_h = self._s(self.COL_H)
        self.col_gap = self._s(self.COL_GAP)
        self.letter_height = self._s(self.LETTER_HEIGHT)

        # Offset de scroll por coluna (px). 0 = letra centrada. Animado a cada
        # mudança e amortecido para 0 em update() criando o efeito de rolagem.
        self._scroll_offset: List[float] = [0.0, 0.0, 0.0]

        self.font_letter = get_font(max(8, int(60 * self.ui_scale)))
        self.font_letter_small = get_font(max(8, int(36 * self.ui_scale)))
        self.font_letter_tiny = get_font(max(8, int(22 * self.ui_scale)))
        self.font_label = get_font(max(8, int(16 * self.ui_scale)))
        self.font_button = get_font(max(8, int(16 * self.ui_scale)))
        self.font_rank = get_font(max(8, int(18 * self.ui_scale)))

        self.entry_anim_timer = 0.0
        self.highlight_pulse_timer = 0.0

        self.predicted_rank = self.app.player_profile.get_predicted_rank(self.score)

        # Layout auto-fit: monta verticalmente seção por seção, soma alturas
        # reais (medidas via Font.get_linesize / size) + paddings consistentes,
        # define modal_h pelo total. Antes era altura fixa 420 e a legenda
        # se sobrepunha ao botão quando a fonte renderizava em tamanho maior.
        self._build_layout()

    def _s(self, value: float) -> int:
        """Escala um valor de pixel do design base (1280×720)."""
        return int(value * self.ui_scale)

    def _build_layout(self) -> None:
        """Calcula posições e tamanho do modal a partir das alturas reais
        dos elementos, garantindo que nada se sobreponha em qualquer fonte.
        """
        # Paddings consistentes — única fonte de espaçamento (escalados).
        pad_top = self._s(24)
        pad_bottom = self._s(24)
        gap_title_rank = self._s(8)
        gap_rank_cols = self._s(28)
        gap_cols_label = self._s(24)
        gap_label_btn = self._s(22)
        line_gap = self._s(6)
        arrow_to_col = self._s(6)  # espaço entre seta ▲▼ e a borda da coluna

        # Alturas medidas das fontes
        title_h = self.font_label.get_linesize()
        rank_h = self.font_rank.get_linesize() if self.predicted_rank > 0 else 0
        arrow_h = self.font_label.get_linesize()
        label_line_h = self.font_label.get_linesize()
        label_total_h = label_line_h * 2 + line_gap  # 2 linhas de legenda
        btn_h = self._s(40)
        col_h = self.col_h

        # Acumula altura total
        total_h = (
            pad_top
            + title_h
            + (gap_title_rank + rank_h if rank_h else 0)
            + gap_rank_cols
            + arrow_h
            + arrow_to_col  # ▲ acima das colunas
            + col_h
            + arrow_to_col
            + arrow_h  # ▼ abaixo das colunas
            + gap_cols_label
            + label_total_h
            + gap_label_btn
            + btn_h
            + pad_bottom
        )

        # Largura: cobre as 3 colunas + paddings laterais. Mantém mínimo
        # confortável para a legenda em 2 linhas.
        total_cols_w = self.col_w * self.MAX_LEN + self.col_gap * (self.MAX_LEN - 1)
        side_pad = self._s(32)
        self.modal_w = max(self._s(540), total_cols_w + side_pad * 2)
        self.modal_h = total_h

        self.rect = pygame.Rect(
            (Config.SCREEN_WIDTH - self.modal_w) // 2,
            (Config.SCREEN_HEIGHT - self.modal_h) // 2,
            self.modal_w,
            self.modal_h,
        )

        # Posiciona seções top→bottom, guarda Y de cada uma pra render
        y = self.rect.top + pad_top
        self._title_y = y
        y += title_h
        if rank_h:
            y += gap_title_rank
            self._rank_y = y
            y += rank_h
        else:
            self._rank_y = None
        y += gap_rank_cols
        # Linha das setas ▲ fica ACIMA do col_y; col_y é o topo real das colunas
        y += arrow_h + arrow_to_col
        col_y = y

        cols_x0 = self.rect.centerx - total_cols_w // 2
        self.col_rects = [
            pygame.Rect(
                cols_x0 + i * (self.col_w + self.col_gap),
                col_y,
                self.col_w,
                col_h,
            )
            for i in range(self.MAX_LEN)
        ]

        y = col_y + col_h + arrow_to_col + arrow_h
        y += gap_cols_label
        self._label_y = y
        y += label_total_h
        y += gap_label_btn

        btn_w = self._s(160)
        btn_gap = self._s(20)
        self.save_button = pygame.Rect(
            self.rect.centerx - btn_w - btn_gap // 2, y, btn_w, btn_h
        )
        self.skip_button = pygame.Rect(
            self.rect.centerx + btn_gap // 2, y, btn_w, btn_h
        )

    # ------------------------------------------------------------------
    # Atualização e input analógico
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.entry_anim_timer = min(1.0, self.entry_anim_timer + dt * 2)
        self.highlight_pulse_timer += dt * 4

        # Amortecimento exponencial dos offsets de scroll — letra desliza
        # suavemente para a posição central após cada mudança.
        for i in range(self.MAX_LEN):
            off = self._scroll_offset[i]
            if abs(off) > 0.5:
                self._scroll_offset[i] = off * max(0.0, 1.0 - dt * 12.0)
            else:
                self._scroll_offset[i] = 0.0
        # Roleta responde apenas a DPad/setas digitais — LS foi removido a
        # pedido do usuário para evitar mudanças acidentais durante
        # movimentos involuntários do stick. DPad chega como KEYDOWN
        # sintético via app.py e é tratado em handle_event.

    # ------------------------------------------------------------------
    # Operações de roleta
    # ------------------------------------------------------------------

    def _change_letter(self, direction: int) -> None:
        """direction +1 = próxima letra (desce visualmente), -1 = anterior."""
        idx = self.active_pos
        self.indices[idx] = (self.indices[idx] + direction) % len(_ALPHABET)
        # Offset começa onde a letra antiga estava → anima de volta a 0.
        self._scroll_offset[idx] = -direction * self.letter_height
        sound_manager.play_sound("button_hover")

    def _change_column(self, direction: int) -> None:
        """direction +1 = coluna à direita, -1 = à esquerda. Sem wrap entre
        colunas — cap nas pontas evita ``passar`` acidentalmente.
        """
        new_pos = max(0, min(self.MAX_LEN - 1, self.active_pos + direction))
        if new_pos != self.active_pos:
            self.active_pos = new_pos
            sound_manager.play_sound("button_click")

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        # DPad chega como KEYDOWN K_UP/K_DOWN/K_LEFT/K_RIGHT (sintetizado
        # pelo app.py quando a cena não expõe focusable_rects), então o
        # bloco abaixo cobre teclado E controle DPad simultaneamente.
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                sound_manager.play_upgrade_activate()
                return "submit"
            if event.key == pygame.K_ESCAPE:
                sound_manager.play_sound("button_click")
                return "skip"
            if event.key == pygame.K_UP:
                self._change_letter(-1)
                return None
            if event.key == pygame.K_DOWN:
                self._change_letter(+1)
                return None
            if event.key == pygame.K_LEFT:
                self._change_column(-1)
                return None
            if event.key == pygame.K_RIGHT:
                self._change_column(+1)
                return None
            # Atalho de teclado: digitar letra direta substitui a coluna ativa
            # e avança automaticamente. Mantém compatibilidade com fluxo antigo.
            ch = (event.unicode or "").upper()
            if len(ch) == 1 and "A" <= ch <= "Z":
                self.indices[self.active_pos] = ord(ch) - ord("A")
                if self.active_pos < self.MAX_LEN - 1:
                    self.active_pos += 1
                sound_manager.play_sound("button_click")
            return None

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                sound_manager.play_upgrade_activate()
                return "submit"
            if event.button in (XboxButton.B, XboxButton.BACK):
                sound_manager.play_sound("button_click")
                return "skip"

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.save_button.collidepoint(event.pos):
                sound_manager.play_upgrade_activate()
                return "submit"
            if self.skip_button.collidepoint(event.pos):
                sound_manager.play_sound("button_click")
                return "skip"
            # Click em uma coluna seleciona ela (útil pra mouse + controle).
            for i, rect in enumerate(self.col_rects):
                if rect.collidepoint(event.pos):
                    self.active_pos = i
                    sound_manager.play_sound("button_hover")
                    return None
        return None

    def get_initials(self) -> str:
        return "".join(_ALPHABET[i] for i in self.indices)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface, alpha: int) -> None:
        # Overlay escuro de fundo para o modal
        modal_overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        modal_overlay.fill((0, 0, 0, int(alpha * 0.7)))
        surface.blit(modal_overlay, (0, 0))

        modal_radius = self._s(15)
        pygame.draw.rect(surface, (15, 15, 25, alpha), self.rect, border_radius=modal_radius)
        pygame.draw.rect(
            surface, (*CUSTOM_GOLD, alpha), self.rect, 2, border_radius=modal_radius
        )

        title_text = self.font_label.render(
            t("game_over.initials_title"), True, colors.WHITE
        )
        title_text.set_alpha(alpha)
        surface.blit(
            title_text,
            title_text.get_rect(centerx=self.rect.centerx, top=self._title_y),
        )

        if self.predicted_rank > 0 and self._rank_y is not None:
            rank_text = self.font_rank.render(
                t("game_over.rank", n=self.predicted_rank), True, CUSTOM_GOLD
            )
            rank_text.set_alpha(alpha)
            surface.blit(
                rank_text,
                rank_text.get_rect(centerx=self.rect.centerx, top=self._rank_y),
            )

        for i, rect in enumerate(self.col_rects):
            self._render_column(surface, i, rect, alpha)

        # Legenda em 2 linhas, posicionada pelo Y calculado em _build_layout.
        label_y = self._label_y
        for line in (t("game_over.legend_move"), t("game_over.legend_action")):
            line_surf = self.font_label.render(line, True, (180, 180, 180))
            line_surf.set_alpha(alpha)
            surface.blit(
                line_surf,
                line_surf.get_rect(centerx=self.rect.centerx, top=label_y),
            )
            label_y += line_surf.get_height() + self._s(6)

        draw_bordered_button(
            surface, self.save_button, t("game_over.save"), self.font_button, CUSTOM_GOLD, alpha
        )
        draw_bordered_button(
            surface, self.skip_button, t("game_over.skip"), self.font_button, CUSTOM_PURPLE, alpha
        )

    def _render_column(
        self, surface: pygame.Surface, idx: int, rect: pygame.Rect, alpha: int
    ) -> None:
        is_active = idx == self.active_pos
        # Entry animation: escala vertical conforme o widget surge.
        entry_scale = math.sin(self.entry_anim_timer * math.pi / 2)
        if entry_scale <= 0:
            return

        cx = rect.centerx
        cy = rect.centery
        scroll = self._scroll_offset[idx]

        # Clip vertical para não vazar pra fora da coluna durante o scroll.
        clip_rect = pygame.Rect(
            rect.x - self._s(4), rect.y, rect.width + self._s(8), rect.height
        )
        previous_clip = surface.get_clip()
        surface.set_clip(clip_rect)
        try:
            # Desenha letras de -VISIBLE_RADIUS a +VISIBLE_RADIUS. A letra 0
            # é a ativa; offset = k * LETTER_HEIGHT + scroll. Fade conforme
            # distância da centro.
            for k in range(-self.VISIBLE_RADIUS, self.VISIBLE_RADIUS + 1):
                letter_idx = (self.indices[idx] + k) % len(_ALPHABET)
                letter = _ALPHABET[letter_idx]
                y = cy + k * self.letter_height + scroll

                # Distância normalizada do centro pra graduar tamanho/alpha.
                normalized = abs(k * self.letter_height + scroll) / (
                    self.letter_height * self.VISIBLE_RADIUS + 1
                )
                normalized = min(1.0, normalized)

                if k == 0 and abs(scroll) < self.letter_height * 0.5:
                    font = self.font_letter
                    base_color = CUSTOM_GOLD if is_active else colors.WHITE
                    letter_alpha = alpha
                elif abs(k) == 1:
                    font = self.font_letter_small
                    base_color = (210, 210, 230) if is_active else (140, 140, 160)
                    letter_alpha = int(alpha * 0.6)
                else:
                    font = self.font_letter_tiny
                    base_color = (160, 160, 180) if is_active else (90, 90, 110)
                    letter_alpha = int(alpha * 0.3)

                surf = font.render(letter, True, base_color)
                surf.set_alpha(letter_alpha)
                surface.blit(surf, surf.get_rect(center=(cx, int(y))))
        finally:
            surface.set_clip(previous_clip)

        # Caixa visual da coluna ativa: pulso suave + setas pra cima/baixo.
        if is_active:
            pulse = 0.7 + 0.3 * (1.0 + math.sin(self.highlight_pulse_timer)) / 2.0
            grow = self._s(8)
            box = pygame.Rect(0, 0, rect.width + grow, rect.height + grow)
            box.center = rect.center
            border = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
            pygame.draw.rect(
                border,
                (*CUSTOM_GOLD, int(alpha * pulse)),
                border.get_rect(),
                3,
                border_radius=self._s(10),
            )
            surface.blit(border, box.topleft)
            # Setinhas indicadoras (▲ ▼) em cima e embaixo.
            arrow_gap = self._s(4)
            arrow_up = self.font_label.render("▲", True, CUSTOM_GOLD)
            arrow_up.set_alpha(int(alpha * pulse))
            surface.blit(
                arrow_up,
                arrow_up.get_rect(centerx=cx, bottom=rect.top - arrow_gap),
            )
            arrow_dn = self.font_label.render("▼", True, CUSTOM_GOLD)
            arrow_dn.set_alpha(int(alpha * pulse))
            surface.blit(
                arrow_dn,
                arrow_dn.get_rect(centerx=cx, top=rect.bottom + arrow_gap),
            )
        else:
            grow = self._s(4)
            box = pygame.Rect(0, 0, rect.width + grow, rect.height + grow)
            box.center = rect.center
            border = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
            pygame.draw.rect(
                border,
                (100, 100, 120, alpha),
                border.get_rect(),
                1,
                border_radius=self._s(8),
            )
            surface.blit(border, box.topleft)


class GameOverScene(Scene):
    def __init__(
        self,
        app: "GameApp",
        score: int,
        playing_scene: "PlayingScene",
        restart_level: int = 1,
    ):
        super().__init__(app)
        self.score = score
        self.playing_scene = playing_scene
        self.restart_level = max(1, restart_level)
        self.r = playing_scene.r

        self.game_over_timer = 0.0
        self.game_over_font_title = get_font(max(8, int(80 * self.ui_scale)))
        self.game_over_font_score = get_font(max(8, int(36 * self.ui_scale)))
        self.game_over_font_prompt = get_font(max(8, int(18 * self.ui_scale)))
        self.game_over_font_button = get_font(max(8, int(16 * self.ui_scale)))

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

        # Layout padronizado: menu no canto inferior esquerdo, continuar no
        # canto inferior direito (mais largo para acomodar o rótulo).
        btn_w, btn_h = self._s(280), self._s(40)
        continue_w = self._s(420)
        margin = self._s(40)
        bottom_y = Config.SCREEN_HEIGHT - self._s(60)
        self.back_to_menu_button = pygame.Rect(margin, bottom_y, btn_w, btn_h)
        self.continue_button = pygame.Rect(
            Config.SCREEN_WIDTH - margin - continue_w,
            bottom_y,
            continue_w,
            btn_h,
        )

        self.high_score_qualified = self.app.player_profile.qualifies_for_high_score(
            self.score
        )
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

        if (
            self.high_score_qualified
            and self.game_over_timer > Config.GAME_OVER_RESTART_DELAY
        ):
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
            self._continue_run()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.back_to_menu_button.collidepoint(event.pos):
                self._return_to_menu()
            elif self.continue_button.collidepoint(event.pos):
                self._continue_run()
        elif event.type == pygame.JOYBUTTONDOWN:
            # Suporte ao controle: A ativa o botão sob o cursor. Sem a mira
            # sobre nenhum botão, A dispara Continuar como ação padrão. Y é
            # atalho explícito de continuar; B volta ao menu (consistente com
            # "B = cancelar/voltar" no resto do jogo).
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                if self.back_to_menu_button.collidepoint(pygame.mouse.get_pos()):
                    self._return_to_menu()
                else:
                    self._continue_run()
            elif event.button == XboxButton.B:
                self._return_to_menu()
            elif event.button == XboxButton.Y:
                self._continue_run()

    def get_focusable_rects(self) -> list[pygame.Rect]:
        """Continuar (direita) e Voltar ao Menu (esquerda) — DPad alterna entre
        eles. Durante a entrada de iniciais, nenhum (o widget tem foco)."""
        if self.entry_widget is not None and not self.entry_submitted:
            return []
        return [self.continue_button, self.back_to_menu_button]

    def _continue_run(self) -> None:
        """Continua a run reiniciando a fase onde o jogador morreu (passada como
        `restart_level`) com a pontuação ZERADA — a `PlayingScene` é recriada do
        zero, então o score recomeça em 0. O high score já foi submetido antes
        desta tela.
        """
        from .playing import PlayingScene

        sound_manager.duck_music(False)  # desfaz o ducking do Game Over
        sound_manager.stop_all_sfx()
        self.app.states.switch(
            PlayingScene(
                self.app,
                self.playing_scene.level_manager,
                self.playing_scene.difficulty_preset,
                starting_level=self.restart_level,
            )
        )

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
        sound_manager.duck_music(False)  # desfaz o ducking do Game Over
        sound_manager.stop_music()
        sound_manager.stop_all_sfx()
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
                random.randint(
                    -self.playing_scene.screen_shake_intensity,
                    self.playing_scene.screen_shake_intensity,
                ),
                random.randint(
                    -self.playing_scene.screen_shake_intensity,
                    self.playing_scene.screen_shake_intensity,
                ),
            )
        surface.blit(self.game_surface, shake_offset)

        # Overlay escurecido
        progress = min(1.0, self.game_over_timer / Config.GAME_OVER_FADE_DURATION)
        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, int(progress * 200)))
        surface.blit(overlay, (0, 0))

        text_alpha = int(progress * 255)
        center_x = Config.SCREEN_WIDTH // 2
        center_y = Config.SCREEN_HEIGHT // 2

        # Título: GAME OVER
        title_surf = self.game_over_font_title.render(
            t("game_over.title"), True, colors.WHITE
        )
        title_surf.set_alpha(text_alpha)
        title_rect = title_surf.get_rect(center=(center_x, center_y - self._s(140)))
        surface.blit(title_surf, title_rect)

        # Score
        if self.game_over_timer > Config.GAME_OVER_RESTART_DELAY:
            sub_progress = min(
                1.0, (self.game_over_timer - Config.GAME_OVER_RESTART_DELAY) / 0.8
            )
            sub_alpha = int(sub_progress * 255)

            score_surf = self.game_over_font_score.render(
                t("game_over.score", score=fmt_num(self.score)), True, colors.WHITE
            )
            score_surf.set_alpha(sub_alpha)
            score_rect = score_surf.get_rect(center=(center_x, center_y - self._s(40)))
            surface.blit(score_surf, score_rect)

            if self.entry_widget is not None and not self.entry_submitted:
                self.entry_widget.render(surface, sub_alpha)
            else:
                hint_surf = self.game_over_font_prompt.render(
                    t("game_over.continue_hint"),
                    True,
                    (180, 180, 180),
                )
                hint_surf.set_alpha(sub_alpha)
                surface.blit(
                    hint_surf,
                    hint_surf.get_rect(center=(center_x, center_y + self._s(40))),
                )

                # Botão "Voltar ao Menu" (canto inferior esquerdo)
                draw_bordered_button(
                    surface,
                    self.back_to_menu_button,
                    t("game_over.back_to_menu"),
                    self.game_over_font_button,
                    CUSTOM_PURPLE,
                    sub_alpha,
                )

                # Botão "Continuar de onde parou" (canto inferior direito) —
                # recomeça a fase onde morreu, com a pontuação zerada.
                draw_bordered_button(
                    surface,
                    self.continue_button,
                    t("game_over.continue"),
                    self.game_over_font_button,
                    CUSTOM_GOLD,
                    sub_alpha,
                )

                # Legenda do atalho de teclado para Continuar (tecla R).
                r_hint_surf = self.game_over_font_button.render(
                    t("game_over.press_r"), True, (150, 150, 160)
                )
                r_hint_surf.set_alpha(sub_alpha)
                surface.blit(
                    r_hint_surf,
                    r_hint_surf.get_rect(
                        center=(
                            self.continue_button.centerx,
                            self.continue_button.top - self._s(16),
                        )
                    ),
                )

    def exit(self):
        pygame.mouse.set_visible(False)
        self.playing_scene.ship.visible = True
        self.playing_scene.screen_shake_timer = 0.0
        self.playing_scene.screen_shake_intensity = 0
