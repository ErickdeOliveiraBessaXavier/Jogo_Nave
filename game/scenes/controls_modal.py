from typing import TYPE_CHECKING, Callable

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE, WHITE
from ..core.config import config as Config
from ..core.i18n import t
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import (
    FOCUS_HIGHLIGHT,
    draw_bordered_button,
    layout_flow_buttons,
    wrap_text,
)

if TYPE_CHECKING:
    from ..app import GameApp


class ControlsModalScene(Scene):
    """Modal de instruções exibido antes do início da gameplay.

    Enquanto o jogador ainda não escolheu como quer jogar, oferece dois ajustes
    ao vivo (método de controle e tiro automático) no exato momento em que eles
    fazem sentido — logo antes de voar — sem exigir uma ida a Configurações.
    Escolhido isso (`controls_configured`), os atalhos SOMEM e o modal fica só
    com as instruções de voo: repetir uma pergunta já respondida é ruído, e
    quem quiser mudar de ideia muda em Configurações (a dica no rodapé diz).

    Navegação por FOCO próprio (`owns_gamepad_navigation`), como a tela de
    Aprimoramentos: D-pad/analógico/setas movem um foco explícito, A/Enter
    aciona e B/ESC fecha. Antes o modal dependia do cursor virtual do app — o
    ponteiro entrava onde a tela anterior o tinha deixado, então nada aparecia
    focado e o A caía no `_finish` por não ter nada sob o cursor: apertar A
    "para escolher" começava a partida.
    """

    # A cena tem foco próprio; o app não move cursor virtual nem sintetiza
    # setas aqui (ver app._update_virtual_cursor / _synthesize_menu_events).
    owns_gamepad_navigation = True

    # Cadência da repetição ao segurar o analógico (igual à de Aprimoramentos).
    NAV_STICK_THRESHOLD = 0.5
    NAV_INITIAL_DELAY = 0.32
    NAV_REPEAT_RATE = 0.12

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
        # Atalhos de controle: só enquanto a escolha não foi feita. Decidido UMA
        # vez, na construção — a preferência vira True no primeiro toggle, e o
        # bloco não pode sumir debaixo da mão de quem acabou de usá-lo.
        self.show_quick_toggles = not self.app.preferences.controls_configured
        # Vira True na 1ª interação deliberada (toggle/checkbox) e congela o
        # timer: fechar sozinho no meio de uma decisão seria frustrante.
        self.interacted = False

        # Índice do elemento focado em `_focus_nodes()`. Ordem visual, de cima
        # para baixo — o botão "Entendi" é o primeiro foco quando não há
        # atalhos, para o caminho de quem já configurou ser um A só.
        self.focus_index = 0
        self._nav_stick_dir = 0
        self._nav_repeat_timer = 0.0

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
        if not self.show_quick_toggles:
            # Sem os atalhos, a faixa que eles ocupavam sai junto — senão sobra
            # um vazio no meio do modal do tamanho exato do que foi escondido.
            tg_block_h = 0
            # Encolhe pela ALTURA DOS ATALHOS, não pelo bloco inteiro: o vão que
            # ficava entre eles e a dica continua servindo de respiro entre as
            # instruções e o botão, que sem isso quase se encostam.
            self.modal_h = self._s(460) - tg_h
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
        self.toggle_rects = (
            {
                key: rel.move(block_x, block_top)
                for key, rel in zip(self._toggle_order, tg_rel_rects)
            }
            if self.show_quick_toggles
            else {}
        )

        # Checkbox "Não mostrar mais" - Abaixo do botão
        cb_size = self._s(18)
        self.checkbox_rect = pygame.Rect(
            self.modal_rect.centerx - self._s(110),
            self.button_rect.bottom + self._s(15),
            cb_size,
            cb_size,
        )

    def enter(self):
        # O ponteiro NÃO é forçado a aparecer aqui: quem manda na visibilidade
        # é o modo de navegação do app (`_sync_cursor_visibility`, chamado na
        # troca de cena). Forçar `set_visible(True)` deixava o cursor na tela
        # durante a navegação por controle, e o app não o escondia de volta
        # porque, para ele, o modo não tinha mudado.
        # Com controle ativo o modal já abre em modo foco, com o primeiro
        # elemento destacado: o ponteiro entra onde a tela anterior o deixou
        # (fora do modal, quase sempre), e é isso que fazia parecer que nada
        # estava selecionado.
        if self._any_gamepad_active():
            self.focus_index = 0
            self.app.set_cursor_mode("focus")

    def _any_gamepad_active(self) -> bool:
        from ..core.gamepad import MAX_GAMEPAD_SLOTS

        gp = getattr(self.app, "gamepad", None)
        if gp is None:
            return False
        return any(gp.is_slot_active(slot) for slot in range(MAX_GAMEPAD_SLOTS))

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
        # Travado enquanto o Modo Controle Xbox está ligado: a nave não pode ter
        # duas fontes de movimento (ver `UserPreferences.set_gamepad_enabled`).
        # O modal e a tela de Configurações consultam a MESMA propriedade — se
        # cada um decidisse por conta, marcar aqui desfaria a regra de lá.
        if self.app.preferences.mouse_control_locked:
            sound_manager.play_sound("button_hover")
            return
        self.app.preferences.mouse_control = not self.app.preferences.mouse_control
        self._apply_control_live()
        self._on_tweak()

    def _toggle_auto_fire(self) -> None:
        self.app.preferences.auto_fire = not self.app.preferences.auto_fire
        self._apply_control_live()
        self._on_tweak()

    def _on_tweak(self) -> None:
        self.interacted = True  # congela o timer de auto-início
        # A escolha foi feita: nas próximas partidas o modal não repete a
        # pergunta (ver `show_quick_toggles`). Persistido no `_finish`, junto
        # com o resto — salvar por tecla apertada seria escrita por frame.
        self.app.preferences.controls_configured = True
        sound_manager.play_sound("button_click")

    # ── Foco (mouse, teclado e controle no MESMO modelo) ─────────────────────

    def _focus_nodes(self) -> list[tuple[str, pygame.Rect]]:
        """Elementos interativos como (ação, rect), em ordem visual.

        Reconstruído a cada consulta porque o conjunto depende do que está na
        tela: os atalhos só existem antes da escolha (`show_quick_toggles`), o
        de método de controle sai quando o Modo Controle Xbox o trava (não há o
        que alternar), e o checkbox não existe no onboarding.
        """
        nodes: list[tuple[str, pygame.Rect]] = []
        if self.show_quick_toggles:
            if not self.app.preferences.mouse_control_locked:
                nodes.append(("control", self.toggle_rects["control"]))
            nodes.append(("autofire", self.toggle_rects["autofire"]))
        nodes.append(("button", self.button_rect))
        if not self.first_time:
            nodes.append(("checkbox", self._checkbox_click_rect()))
        return nodes

    def _checkbox_click_rect(self) -> pygame.Rect:
        """Alvo do checkbox — inclui o rótulo ao lado, que é o que se lê."""
        return self.checkbox_rect.inflate(self._s(200), self._s(10))

    def _focused_action(self) -> str:
        nodes = self._focus_nodes()
        if not nodes:
            return ""
        self.focus_index = max(0, min(self.focus_index, len(nodes) - 1))
        return nodes[self.focus_index][0]

    def _move_focus(self, delta: int) -> None:
        """Anda na ordem visual, circular. Ordem linear (e não geométrica) de
        propósito: são no máximo quatro elementos, e previsibilidade aqui vale
        mais que esperteza."""
        nodes = self._focus_nodes()
        if not nodes:
            return
        self.app.set_cursor_mode("focus")
        self.focus_index = (self.focus_index + delta) % len(nodes)
        sound_manager.play_sound("button_hover")

    def _activate_focused(self) -> None:
        self._activate(self._focused_action())

    def _activate(self, action: str) -> None:
        """Roteador único de ação — clique, Enter e A do controle passam aqui."""
        if action == "control":
            self._toggle_control_method()
        elif action == "autofire":
            self._toggle_auto_fire()
        elif action == "checkbox":
            self._toggle_checkbox()
        elif action == "button":
            self._finish()

    def _node_at_pos(self, pos: tuple[int, int]) -> str:
        for action, rect in self._focus_nodes():
            if rect.collidepoint(pos):
                return action
        return ""

    def _sync_focus_to_cursor(self, pos: tuple[int, int]) -> None:
        """Hover move o foco, para mouse e controle nunca discordarem de quem
        está selecionado (mesmo contrato da tela de Aprimoramentos)."""
        if self.app.cursor_navigation_mode != "cursor":
            return
        for i, (_action, rect) in enumerate(self._focus_nodes()):
            if rect.collidepoint(pos):
                self.focus_index = i
                return

    def _poll_stick_nav(self, dt: float) -> None:
        """Analógico move o foco, com atraso inicial + repetição.

        O modal tem foco próprio, então o app não move cursor virtual aqui —
        sem este polling o analógico simplesmente não faria nada.
        """
        from ..core.gamepad import MAX_GAMEPAD_SLOTS

        gp = getattr(self.app, "gamepad", None)
        if gp is None:
            return
        melhor = 0.0
        for slot in range(MAX_GAMEPAD_SLOTS):
            if not gp.is_slot_active(slot):
                continue
            for lado in ("left", "right"):
                _sx, sy = gp.get_stick(lado, slot=slot)
                if abs(sy) > abs(melhor):
                    melhor = sy
        if abs(melhor) < self.NAV_STICK_THRESHOLD:
            self._nav_stick_dir, self._nav_repeat_timer = 0, 0.0
            return
        direcao = 1 if melhor > 0 else -1
        if direcao != self._nav_stick_dir:
            self._nav_stick_dir = direcao
            self._nav_repeat_timer = self.NAV_INITIAL_DELAY
            self._move_focus(direcao)
        else:
            self._nav_repeat_timer -= dt
            if self._nav_repeat_timer <= 0.0:
                self._nav_repeat_timer = self.NAV_REPEAT_RATE
                self._move_focus(direcao)

    # ── Eventos ──────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEMOTION:
            self._sync_focus_to_cursor(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Clique no vazio dentro do modal não faz nada; fora só ignora.
            self._activate(self._node_at_pos(event.pos))
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._finish()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._activate_focused()
            elif event.key in (pygame.K_UP, pygame.K_LEFT):
                self._move_focus(-1)
            elif event.key == pygame.K_TAB:
                # Shift+TAB volta, como em qualquer formulário.
                self._move_focus(-1 if event.mod & pygame.KMOD_SHIFT else 1)
            elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                self._move_focus(1)
            return

        # D-pad: mesma fonte do analógico (`_move_focus`). Hat y +1 = cima.
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if y:
                self._move_focus(-1 if y > 0 else 1)
            elif x:
                self._move_focus(1 if x > 0 else -1)
            return

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            # A aciona o elemento FOCADO — não mais "o que estiver sob o
            # cursor", que era como o A começava a partida sem querer.
            if event.button == XboxButton.A:
                self._activate_focused()
                return
            if event.button == XboxButton.X:
                self._toggle_checkbox()
                return
            if event.button in (XboxButton.B, XboxButton.BACK, XboxButton.START):
                self._finish()
                return

    def _toggle_checkbox(self) -> None:
        if self.first_time:
            return
        self.show_again = not self.show_again
        self.interacted = True
        sound_manager.play_sound("button_hover")

    def get_focusable_rects(self):
        """Rects interativos. A cena navega o próprio foco
        (`owns_gamepad_navigation`), mas a lista segue pública — é o contrato da
        `Scene` e o que descreve a tela para quem consulta de fora."""
        return [rect for _action, rect in self._focus_nodes()]

    def _finish(self):
        sound_manager.play_sound("button_click")
        # Salvar preferências. controls_modal_seen encerra o modo onboarding;
        # show_controls_modal continua controlando se o modal reaparece.
        self.app.preferences.show_controls_modal = self.show_again
        self.app.preferences.controls_modal_seen = True
        self.app.preferences.save()

        # Não se desempilha: `on_finish` chama `go_to`, que SUBSTITUI este modal
        # pela cena seguinte dentro do fade. Um `pop()` aqui esvaziaria a pilha
        # por um frame e ainda deixaria o modal sumir antes do fade começar.
        self.on_finish()

    def update(self, dt: float):
        self._poll_stick_nav(dt)
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

        # Atalhos de ajuste rápido — só enquanto a escolha não foi feita. Com o
        # Modo Controle Xbox ligado, o método de movimento é o analógico e o
        # toggle fica esmaecido: o mesmo estado que a tela de Configurações
        # mostra, lido da mesma propriedade.
        focado = self._focused_action()
        if self.show_quick_toggles:
            control_locked = prefs.mouse_control_locked
            control_val = (
                t("controls.method.gamepad")
                if control_locked
                else t("controls.method.mouse")
                if prefs.mouse_control
                else t("controls.method.keyboard")
            )
            autofire_val = t("controls.on") if prefs.auto_fire else t("controls.off")
            draw_bordered_button(
                surface,
                self.toggle_rects["control"],
                t("controls.toggle.control", v=control_val),
                self.toggle_font,
                colors.GRAY if control_locked else CUSTOM_PURPLE,
                focused=focado == "control",
            )
            draw_bordered_button(
                surface,
                self.toggle_rects["autofire"],
                t("controls.toggle.autofire", v=autofire_val),
                self.toggle_font,
                CUSTOM_PURPLE,
                focused=focado == "autofire",
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
            surface,
            self.button_rect,
            t("controls.got_it"),
            self.item_font,
            CUSTOM_PURPLE,
            focused=focado == "button",
        )

        # Checkbox "Não mostrar mais" — oculto na 1ª exibição (onboarding).
        if not self.first_time:
            cb_focado = focado == "checkbox"
            # Foco muda a borda que o checkbox já tem, sem moldura extra (§19).
            pygame.draw.rect(
                surface,
                FOCUS_HIGHLIGHT if cb_focado else CUSTOM_GOLD,
                self.checkbox_rect,
                2 if cb_focado else 1,
                border_radius=self._s(3),
            )
            if not self.show_again:
                inner_rect = self.checkbox_rect.inflate(-self._s(6), -self._s(6))
                pygame.draw.rect(
                    surface, CUSTOM_GOLD, inner_rect, border_radius=self._s(1)
                )

            tiny_font = get_font(max(8, int(12 * self.ui_scale)))
            label_surf = tiny_font.render(
                t("controls.dont_show"),
                True,
                FOCUS_HIGHLIGHT if cb_focado else colors.GRAY,
            )
            surface.blit(
                label_surf,
                (
                    self.checkbox_rect.right + self._s(8),
                    self.checkbox_rect.centery - label_surf.get_height() // 2,
                ),
            )
