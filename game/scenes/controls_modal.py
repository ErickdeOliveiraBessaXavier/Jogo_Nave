from typing import TYPE_CHECKING, Callable

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE, WHITE
from ..core.config import config as Config
from ..core.i18n import t
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import wrap_text, draw_bordered_button, layout_flow_buttons

if TYPE_CHECKING:
    from ..app import GameApp


class ControlsModalScene(Scene):
    """Modal de instruções exibido antes do início da gameplay.

    Além de mostrar os controles, oferece dois ajustes ao vivo (método de
    controle e tiro automático) para que o jogador descubra e mude essas opções
    no exato momento em que elas fazem sentido — logo antes de voar — sem
    precisar caçar o menu de Configurações. As instruções à esquerda se
    redesenham na hora para refletir a escolha.
    """

    def __init__(self, app: "GameApp", on_finish: Callable[[], None]):
        super().__init__(app)
        self.on_finish = on_finish
        self.timer = 10.0
        self.show_again = (
            True  # Estado do checkbox (invertido para salvar em show_controls_modal)
        )

        # 1ª vez que o modal aparece: modo onboarding. Esconde o checkbox
        # "não mostrar mais" (o novato não mata a própria descoberta por reflexo)
        # e o timer de auto-início não corre até o jogador mexer em algo.
        self.first_time = not self.app.preferences.controls_modal_seen
        # Vira True na 1ª interação deliberada (toggle/checkbox) e congela o
        # timer: fechar sozinho no meio de uma decisão seria frustrante.
        self.interacted = False

        self.title_font = get_font(max(8, int(32 * self.ui_scale)))
        self.item_font = get_font(max(8, int(18 * self.ui_scale)))
        self.small_font = get_font(max(8, int(16 * self.ui_scale)))
        # self.toggle_font é definida em _calculate_layout (pode encolher para o
        # rótulo caber, ver layout_flow_buttons).
        self.hint_font = get_font(max(8, int(13 * self.ui_scale)))

        # Rects dos dois toggles de ajuste rápido ("control" e "autofire").
        self.toggle_rects: dict[str, pygame.Rect] = {}

        self._calculate_layout()

    def _calculate_layout(self):
        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

        # Modal mais largo para garantir que as colunas não se sobreponham
        self.modal_w = self._s(760)

        # --- Toggles de ajuste rápido: layout flex-wrap por conteúdo ---------
        # Passamos TODOS os estados possíveis de cada toggle (não só o atual) para
        # a largura ser estável ao alternar em runtime e caber sempre o rótulo
        # mais longo do idioma. O helper devolve a geometria; a posição final é
        # aplicada abaixo, depois de conhecer a altura do modal.
        tg_h = self._s(40)
        tg_gap_y = self._s(14)
        self._toggle_order = ("control", "autofire")
        toggle_states = [
            [
                t("controls.toggle.control", v=t("controls.method.mouse")),
                t("controls.toggle.control", v=t("controls.method.keyboard")),
            ],
            [
                t("controls.toggle.autofire", v=t("controls.on")),
                t("controls.toggle.autofire", v=t("controls.off")),
            ],
        ]
        tg_rel_rects, self.toggle_font, tg_block_w, tg_block_h, _tg_rows = (
            layout_flow_buttons(
                toggle_states,
                get_font,
                base_font_size=max(8, int(17 * self.ui_scale)),
                avail_w=self.modal_w - self._s(80),
                btn_h=tg_h,
                gap_x=self._s(24),
                gap_y=tg_gap_y,
                pad_x=self._s(18),
            )
        )

        # O modal cresce em altura quando os toggles quebram em >1 linha; a base
        # (460) preserva o layout de 720p quando cabem numa linha só. Como o
        # modal é centralizado e o botão é ancorado ao rodapé, o vão entre as
        # instruções e os toggles fica constante (ambos deslocam junto).
        extra_h = max(0, tg_block_h - tg_h)
        self.modal_h = self._s(460) + extra_h
        self.modal_rect = pygame.Rect(
            (screen_w - self.modal_w) // 2,
            (screen_h - self.modal_h) // 2,
            self.modal_w,
            self.modal_h,
        )

        # Botão "Entendi" - Centralizado horizontalmente na parte inferior
        btn_w = self._s(200)
        btn_h = self._s(45)
        self.button_rect = pygame.Rect(
            self.modal_rect.centerx - btn_w // 2,
            self.modal_rect.bottom - self._s(120),
            btn_w,
            btn_h,
        )

        # Posiciona o bloco de toggles: bottom fixo acima do botão (deixando vão
        # para a dica), crescendo para cima conforme as linhas.
        block_bottom = self.button_rect.top - self._s(56)
        block_top = block_bottom - tg_block_h
        block_x = self.modal_rect.centerx - tg_block_w // 2
        self.toggle_block_bottom = block_bottom
        self.toggle_rects = {
            key: rel.move(block_x, block_top)
            for key, rel in zip(self._toggle_order, tg_rel_rects)
        }

        # Checkbox "Não mostrar mais" - Abaixo do botão
        cb_size = self._s(18)
        self.checkbox_rect = pygame.Rect(
            self.modal_rect.centerx - self._s(110),
            self.button_rect.bottom + self._s(15),
            cb_size,
            cb_size,
        )

    def enter(self):
        pygame.mouse.set_visible(True)

    # ── Ajustes ao vivo ──────────────────────────────────────────────────────
    def _apply_control_live(self) -> None:
        """Propaga mouse_control/auto_fire para o app (a nave ainda será criada
        pela PlayingScene lendo estas preferências)."""
        prefs = self.app.preferences
        game_input = getattr(self.app, "input", None)
        if game_input is not None:
            game_input.mouse_control = prefs.mouse_control
            game_input.auto_fire = prefs.auto_fire

    def _toggle_control_method(self) -> None:
        self.app.preferences.mouse_control = not self.app.preferences.mouse_control
        self._apply_control_live()
        self._on_tweak()

    def _toggle_auto_fire(self) -> None:
        self.app.preferences.auto_fire = not self.app.preferences.auto_fire
        self._apply_control_live()
        self._on_tweak()

    def _on_tweak(self) -> None:
        self.interacted = True  # congela o timer de auto-início
        sound_manager.play_sound("button_click")

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self._activate_under_cursor(event.pos):
                # Clique no vazio dentro do modal não faz nada; fora só ignora.
                pass

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._finish()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if not self._activate_under_cursor(pygame.mouse.get_pos()):
                    self._finish()

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            # A: ativa o item sob o cursor (toggle/checkbox/botão). Fora de tudo,
            # fecha o modal. X é atalho dedicado para o checkbox.
            if event.button == XboxButton.A:
                if not self._activate_under_cursor(pygame.mouse.get_pos()):
                    self._finish()
                return
            if event.button == XboxButton.X:
                self._toggle_checkbox()
                return
            if event.button in (XboxButton.B, XboxButton.BACK, XboxButton.START):
                self._finish()
                return

    def _activate_under_cursor(self, pos: tuple[int, int]) -> bool:
        """Ativa o item sob `pos`. Retorna True se algo foi consumido."""
        if self.toggle_rects["control"].collidepoint(pos):
            self._toggle_control_method()
            return True
        if self.toggle_rects["autofire"].collidepoint(pos):
            self._toggle_auto_fire()
            return True
        if not self.first_time:
            click_rect = self.checkbox_rect.inflate(self._s(200), self._s(10))
            if click_rect.collidepoint(pos):
                self._toggle_checkbox()
                return True
        if self.button_rect.collidepoint(pos):
            self._finish()
            return True
        return False

    def _toggle_checkbox(self) -> None:
        if self.first_time:
            return
        self.show_again = not self.show_again
        self.interacted = True
        sound_manager.play_sound("button_hover")

    def get_focusable_rects(self):
        # DPad snap-focus (app.py) percorre estes rects movendo o cursor.
        rects = [
            self.toggle_rects["control"],
            self.toggle_rects["autofire"],
            self.button_rect,
        ]
        if not self.first_time:
            rects.append(self.checkbox_rect.inflate(self._s(200), self._s(10)))
        return rects

    def _finish(self):
        sound_manager.play_sound("button_click")
        # Salvar preferências. controls_modal_seen encerra o modo onboarding;
        # show_controls_modal continua controlando se o modal reaparece.
        self.app.preferences.show_controls_modal = self.show_again
        self.app.preferences.controls_modal_seen = True
        self.app.preferences.save()

        self.app.states.pop()  # Remove a si mesma do stack
        self.on_finish()

    def update(self, dt: float):
        # No modo onboarding (ou após mexer em algo) o timer não corre — o
        # jogador decide quando começar.
        if self.first_time or self.interacted:
            return
        self.timer -= dt
        if self.timer <= 0:
            self._finish()

    def render(self, surface: pygame.Surface):
        # Overlay escuro no fundo da tela toda
        overlay = pygame.Surface(
            (surface.get_width(), surface.get_height()), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        # Fundo do modal (preto)
        modal_radius = self._s(15)
        pygame.draw.rect(surface, BLACK, self.modal_rect, border_radius=modal_radius)
        pygame.draw.rect(
            surface, CUSTOM_GOLD, self.modal_rect, 2, border_radius=modal_radius
        )

        # Título
        title_surf = self.title_font.render(t("controls.title"), True, CUSTOM_GOLD)
        surface.blit(
            title_surf,
            (
                self.modal_rect.centerx - title_surf.get_width() // 2,
                self.modal_rect.y + self._s(25),
            ),
        )

        prefs = self.app.preferences

        # Configuração das colunas
        left_x = self.modal_rect.x + self._s(40)
        right_x = self.modal_rect.centerx + self._s(20)
        max_col_w = (self.modal_w // 2) - self._s(60)

        # Instruções: trocam entre teclado e controle conforme o input ativo
        # (preferência ligada + gamepad conectado) e refletem os ajustes ao vivo.
        gamepad_active = (
            self.app.gamepad.is_active if hasattr(self.app, "gamepad") else False
        )
        if gamepad_active:
            move_line = t("controls.gp.move")
            shoot_line = (
                t("controls.shoot_auto") if prefs.auto_fire else t("controls.gp.shoot")
            )
            pause_line = t("controls.gp.pause")
            right_col_raw = [
                t("controls.gp.rotate"),
                t("controls.gp.dash"),
                t("controls.gp.powers"),
            ]
        else:
            move_line = (
                t("controls.kb.move_mouse")
                if prefs.mouse_control
                else t("controls.kb.move_keys")
            )
            shoot_line = (
                t("controls.shoot_auto") if prefs.auto_fire else t("controls.kb.shoot")
            )
            pause_line = t("controls.kb.pause")
            right_col_raw = [
                t("controls.kb.rotate"),
                t("controls.kb.dash"),
                t("controls.kb.powers"),
            ]
        left_col_raw = [move_line, shoot_line, pause_line]

        def draw_column(items: list[str], start_x: int, start_y: int):
            curr_y = start_y
            for item in items:
                wrapped_lines = wrap_text(self.item_font, item, max_col_w)
                for line in wrapped_lines:
                    text_surf = self.item_font.render(line, True, WHITE)
                    surface.blit(text_surf, (start_x, curr_y))
                    curr_y += self._s(25)  # Espaço entre linhas da mesma instrução
                curr_y += self._s(15)  # Espaço extra entre instruções diferentes

        y_start = self.modal_rect.y + self._s(90)
        draw_column(left_col_raw, left_x, y_start)
        draw_column(right_col_raw, right_x, y_start)

        # Toggles de ajuste rápido
        control_val = (
            t("controls.method.mouse")
            if prefs.mouse_control
            else t("controls.method.keyboard")
        )
        autofire_val = t("controls.on") if prefs.auto_fire else t("controls.off")
        draw_bordered_button(
            surface,
            self.toggle_rects["control"],
            t("controls.toggle.control", v=control_val),
            self.toggle_font,
            CUSTOM_PURPLE,
        )
        draw_bordered_button(
            surface,
            self.toggle_rects["autofire"],
            t("controls.toggle.autofire", v=autofire_val),
            self.toggle_font,
            CUSTOM_PURPLE,
        )

        # Dica sobre Configurações — envolve em várias linhas e centraliza o
        # bloco no espaço entre os toggles e o botão (nunca estoura o modal).
        hint_max_w = self.modal_w - self._s(80)
        hint_lines = wrap_text(
            self.hint_font, t("controls.settings_hint"), hint_max_w
        )
        line_h = self.hint_font.get_height() + self._s(2)
        block_h = line_h * len(hint_lines)
        # Ancorar no fundo do BLOCO de toggles (não em "control", que pode estar
        # na 1ª de várias linhas) para a dica ficar sempre abaixo de todos eles.
        gap_top = self.toggle_block_bottom
        gap_bottom = self.button_rect.top
        hint_y = gap_top + ((gap_bottom - gap_top) - block_h) // 2
        for i, line in enumerate(hint_lines):
            line_surf = self.hint_font.render(line, True, colors.GRAY)
            surface.blit(
                line_surf,
                (
                    self.modal_rect.centerx - line_surf.get_width() // 2,
                    hint_y + i * line_h,
                ),
            )

        # Timer (só é relevante quando está de fato correndo)
        if not self.first_time and not self.interacted:
            timer_text = t("controls.starting_in", n=max(0, int(self.timer + 0.9)))
            timer_surf = self.small_font.render(timer_text, True, colors.GRAY)
            surface.blit(
                timer_surf,
                (
                    self.modal_rect.centerx - timer_surf.get_width() // 2,
                    self.modal_rect.bottom - self._s(25),
                ),
            )

        # Botão Entendi
        draw_bordered_button(
            surface, self.button_rect, t("controls.got_it"), self.item_font, CUSTOM_PURPLE
        )

        # Checkbox "Não mostrar mais" — oculto na 1ª exibição (onboarding).
        if not self.first_time:
            pygame.draw.rect(
                surface, CUSTOM_GOLD, self.checkbox_rect, 1, border_radius=self._s(3)
            )
            if not self.show_again:
                inner_rect = self.checkbox_rect.inflate(-self._s(6), -self._s(6))
                pygame.draw.rect(
                    surface, CUSTOM_GOLD, inner_rect, border_radius=self._s(1)
                )

            tiny_font = get_font(max(8, int(12 * self.ui_scale)))
            label_surf = tiny_font.render(t("controls.dont_show"), True, colors.GRAY)
            surface.blit(
                label_surf,
                (
                    self.checkbox_rect.right + self._s(8),
                    self.checkbox_rect.centery - label_surf.get_height() // 2,
                ),
            )
