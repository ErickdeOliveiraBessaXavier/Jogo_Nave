"""
Seleção de Mundo - Sistema de Savepoints

Permite ao jogador escolher em qual mundo iniciar o jogo.
Mostra status de desbloqueio e checkpoint atual.
"""

import math
import random
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

import pygame

from ..core.assets import BASE_DIR, get_font, get_image
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.config import config as Config
from ..core.i18n import fmt_num, t, t_or
from ..core.sound import sound_manager
from ..core.levels.fixed_levels import TEST_ARENA_ENABLED
from ..core.world_config import WorldConfig, get_all_worlds, resolve_theme_key
from ..render.backgrounds import Background, create_background
from .ui_helpers import UIParticle, draw_bordered_button

if TYPE_CHECKING:
    from ..render.renderer import Renderer


# Backgrounds dependem só de (tema, largura, altura) — tudo estático. Construir
# um MountainsBackground custa ~77ms (medido), o que estourava o frame da
# transição menu→seleção de mundo a CADA entrada. Memoizamos por (tema, W, H)
# no nível do módulo: construído no máximo uma vez por processo e reusado por
# qualquer instância da view (o menu é recriado a cada retorno do jogo). Só uma
# view existe por vez, então compartilhar a instância animada é seguro.
_background_memo: Dict[Tuple[str, int, int], Background] = {}


def _get_cached_background(theme: str, width: int, height: int) -> Background:
    key = (theme, width, height)
    bg = _background_memo.get(key)
    if bg is None:
        bg = create_background(theme, width, height)
        _background_memo[key] = bg
    return bg


def render_text_wrapped(
    text: str,
    font: pygame.font.Font,
    color: Tuple[int, int, int],
    surface: pygame.Surface,
    center_x: int,
    start_y: int,
    max_width: int,
) -> int:
    """Renderiza texto com quebra de linha automática, centralizado."""
    words: list[str] = text.split(" ")
    lines: list[str] = []
    current_line: list[str] = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # Verifica a largura da linha com a nova palavra
        width, _ = font.size(test_line)
        if width <= max_width and current_line:
            current_line.append(word)
        elif not current_line:
            current_line.append(word)  # Garante que pelo menos uma palavra entre
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    y_offset = start_y
    for line in lines:
        rendered_line = font.render(line, True, color)
        line_rect = rendered_line.get_rect(centerx=center_x, top=y_offset)
        surface.blit(rendered_line, line_rect)
        y_offset += (
            font.get_linesize() + 2
        )  # +2 para um pequeno espaçamento entre linhas

    return y_offset


class WorldCardState(Enum):
    """Estados possíveis de um card de mundo."""

    LOCKED = 0
    UNLOCKED = 1
    CHECKPOINT = 2


class WorldCard:
    """Card visual representando um mundo."""

    def __init__(
        self,
        world_config: WorldConfig,
        state: WorldCardState,
        best_score: int = 0,
        ui_scale: float = 1.0,
    ):
        self.world_config = world_config
        self.state = state
        self.best_score = best_score
        self.hover = False
        self.ui_scale = ui_scale

        # Dimensões base do card, escaladas para a resolução (design = 1280×720).
        self.base_width = int(340 * ui_scale)
        self.base_height = int(220 * ui_scale)
        self.rect = pygame.Rect(0, 0, self.base_width, self.base_height)

        # Cores baseadas no estado
        self._update_colors()

        # Fontes (escaladas junto com o card para manter a proporção).
        self.title_font = get_font(max(8, int(18 * ui_scale)))
        self.desc_font = get_font(max(8, int(13 * ui_scale)))
        self.score_font = get_font(max(8, int(16 * ui_scale)))
        self.checkpoint_font = get_font(max(8, int(13 * ui_scale)))

    def _update_colors(self) -> None:
        """Atualiza cores baseadas no estado atual."""
        if self.state == WorldCardState.CHECKPOINT:
            self.border_color = CUSTOM_GOLD
            self.bg_color = (30, 30, 30)
            self.title_color = CUSTOM_GOLD
        elif self.state == WorldCardState.UNLOCKED:
            self.border_color = CUSTOM_PURPLE
            self.bg_color = (20, 20, 20)
            self.title_color = CUSTOM_PURPLE
        else:  # LOCKED
            self.border_color = (60, 60, 60)
            self.bg_color = (15, 15, 15)
            self.title_color = (100, 100, 100)

    def render(
        self,
        surface: pygame.Surface,
        center_pos: Tuple[int, int],
        scale: float,
        alpha: int,
        time: float,
        is_focused: bool,
    ) -> None:
        """
        Renderiza o card com escala e alpha dinâmicos.

        Args:
            surface: Superfície de destino
            center_pos: Posição central do card
            scale: Escala do card (1.0 = normal)
            alpha: Transparência (0-255)
            time: Tempo global para animações
            is_focused: Se o card é o que está no centro (selecionado)
        """
        # Calcular dimensões escalonadas
        w = int(self.base_width * scale)
        h = int(self.base_height * scale)
        self.rect = pygame.Rect(0, 0, w, h)
        self.rect.center = center_pos

        # Criar superfície temporária para o card para facilitar escala e alpha
        card_surf = pygame.Surface((self.base_width, self.base_height), pygame.SRCALPHA)

        # Offsets/raios internos seguem a escala da resolução.
        s = self.ui_scale
        radius = max(4, int(12 * s))

        # Fundo
        bg_color = self.bg_color
        if self.state != WorldCardState.LOCKED and is_focused:
            # Sutil pulsação de brilho no fundo se não estiver bloqueado E estiver focado
            pulse = (math.sin(time * 3) + 1) * 0.5
            bg_bright = 20 * pulse
            bg_color = tuple(min(255, int(c + bg_bright)) for c in self.bg_color)

        # Desenhar fundo translúcido (RGBA)
        pygame.draw.rect(
            card_surf, (*bg_color, 200), card_surf.get_rect(), border_radius=radius
        )

        # Borda dinâmica
        border_thickness = max(2, int(3 * s))
        current_border_color = self.border_color

        if self.state == WorldCardState.CHECKPOINT:
            if is_focused:
                # Brilho dourado pulsante apenas se focado
                pulse = (math.sin(time * 5) + 1) * 0.5
                current_border_color = tuple(
                    int(c * (0.7 + pulse * 0.3)) for c in CUSTOM_GOLD
                )
                border_thickness = max(3, int(4 * s))
        elif self.state == WorldCardState.UNLOCKED:
            if is_focused:
                # Brilho roxo suave apenas se focado
                pulse = (math.sin(time * 2) + 1) * 0.5
                current_border_color = tuple(
                    int(c * (0.8 + pulse * 0.2)) for c in CUSTOM_PURPLE
                )

        pygame.draw.rect(
            card_surf,
            current_border_color,
            card_surf.get_rect(),
            border_thickness,
            border_radius=radius,
        )

        # Conteúdo do Card (Texto)
        padding = int(25 * s)
        max_text_width = self.base_width - (padding * 2)

        # Título
        title_bottom = render_text_wrapped(
            text=t_or(f"world.{self.world_config.world_id}.name", self.world_config.name),
            font=self.title_font,
            color=self.title_color,
            surface=card_surf,
            center_x=self.base_width // 2,
            start_y=int(25 * s),
            max_width=max_text_width,
        )

        # Descrição
        desc_color = (
            (120, 120, 120) if self.state == WorldCardState.LOCKED else (200, 200, 200)
        )
        render_text_wrapped(
            text=t_or(
                f"world.{self.world_config.world_id}.desc",
                self.world_config.description,
            ),
            font=self.desc_font,
            color=desc_color,
            surface=card_surf,
            center_x=self.base_width // 2,
            start_y=title_bottom + int(12 * s),
            max_width=max_text_width,
        )

        # Status/Score ou Cadeado
        if self.state == WorldCardState.LOCKED:
            # Desenhar ícone de cadeado asset
            lock_s = int(40 * s)
            try:
                lock_img = get_image(
                    BASE_DIR / "assets" / "images" / "icons" / "icon_bloqueado.png"
                )
                lock_img = pygame.transform.scale(lock_img, (lock_s, lock_s))
                lock_rect = lock_img.get_rect(
                    center=(self.base_width // 2, self.base_height - int(50 * s))
                )
                card_surf.blit(lock_img, lock_rect)
            except (OSError, pygame.error, ValueError):
                # Fallback para o ícone desenhado se falhar
                lock_x, lock_y = self.base_width // 2, self.base_height - int(50 * s)
                pygame.draw.rect(
                    card_surf,
                    (80, 80, 80),
                    (lock_x - int(12 * s), lock_y, int(24 * s), int(20 * s)),
                    border_radius=max(2, int(3 * s)),
                )
                pygame.draw.arc(
                    card_surf,
                    (80, 80, 80),
                    (lock_x - int(10 * s), lock_y - int(12 * s), int(20 * s), int(20 * s)),
                    math.pi,
                    0,
                    max(2, int(3 * s)),
                )
        elif self.state == WorldCardState.CHECKPOINT:
            line1 = self.checkpoint_font.render(t("world.checkpoint"), True, CUSTOM_GOLD)
            line2 = self.checkpoint_font.render(
                t("world.best", score=fmt_num(self.best_score)), True, CUSTOM_GOLD
            )

            card_surf.blit(
                line2,
                line2.get_rect(
                    centerx=self.base_width // 2, bottom=self.base_height - int(15 * s)
                ),
            )
            card_surf.blit(
                line1,
                line1.get_rect(
                    centerx=self.base_width // 2, bottom=self.base_height - int(35 * s)
                ),
            )
        else:
            status_text = self.score_font.render(t("world.unlocked"), True, CUSTOM_PURPLE)
            status_rect = status_text.get_rect(
                centerx=self.base_width // 2, bottom=self.base_height - int(20 * s)
            )
            card_surf.blit(status_text, status_rect)

        # Aplicar escala e blitar na superfície principal
        if scale != 1.0:
            final_surf = pygame.transform.smoothscale(card_surf, (w, h))
        else:
            final_surf = card_surf

        final_surf.set_alpha(alpha)
        surface.blit(final_surf, self.rect.topleft)


class WorldSelectionView:
    """View para seleção de mundo com layout de carrossel focado."""

    def __init__(
        self,
        on_world_selected: Callable[[int], None],
        on_back: Callable[[], None],
        renderer: "Renderer",
        player_profile: Any,
    ) -> None:
        self.on_world_selected = on_world_selected
        self.on_back = on_back
        self.renderer = renderer
        self.player_profile = player_profile

        # Cards de mundo
        self.world_cards: List[WorldCard] = []
        self.selected_index = 0

        # Animação do Carrossel
        self.visual_scroll_index = 0.0  # Para interpolação suave
        self.scroll_speed = 10.0

        # Escala de UI relativa ao design base (1280×720). Todas as resoluções
        # ofertadas são 16:9, então um único fator (largura) cobre os dois
        # eixos. Sem ele, cards/setas/fontes ficavam com tamanho fixo e
        # desproporcionais fora de 720p (carrossel "estranho").
        self.ui_scale = Config.SCREEN_WIDTH / 1280.0

        # Layout — espaçamento entre centros no carrossel, escalado.
        self.card_spacing = int(400 * self.ui_scale)

        # Navegação por teclado
        self.last_key_time = 0
        self.key_repeat_delay = 200  # ms

        # Background dinâmico
        self.current_background = None
        self.previous_background = None
        self.last_selected = -1

        # O botão A do controle é tratado nativamente aqui (cursor-aware: sobre
        # seta cicla, sobre card seleciona). Mas o app também traduz A → KEYDOWN
        # K_RETURN sintético (Camada A, ver app._synthesize_menu_events), que
        # cairia em `_select_current_world` e SELECIONAVA o mundo mesmo com a
        # mira sobre a seta. Esta flag, setada no A nativo e consumida pelo
        # K_RETURN sintético que vem logo em seguida, evita o disparo duplo.
        self._suppress_synthetic_confirm = False

        # Transição de fade
        self.transition_progress = 0.0  # 0.0 a 1.0
        self.transition_duration = 0.3  # segundos
        self.is_transitioning = False

        # Superfícies reutilizáveis — evita malloc por frame
        self._bg_scratch_a = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        self._bg_scratch_b = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        # Buffer meia-res para o upscale do fundo retrô (mesmo do jogo).
        self._bg_scratch_half = pygame.Surface(
            (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2), pygame.SRCALPHA
        )

        # Fontes cacheadas fora do caminho de render (escaladas).
        self.title_font = get_font(max(12, int(36 * self.ui_scale)))
        self._inst_font = get_font(max(8, int(16 * self.ui_scale)))

        # Título
        self.title_text = self.title_font.render(t("world.title"), True, CUSTOM_GOLD)
        self.title_rect = self.title_text.get_rect(
            center=(Config.SCREEN_WIDTH // 2, int(80 * self.ui_scale))
        )

        # Botão Voltar (Canto inferior esquerdo)
        btn_w = int(160 * self.ui_scale)
        btn_h = int(40 * self.ui_scale)
        self.back_button_rect = pygame.Rect(
            int(40 * self.ui_scale),
            Config.SCREEN_HEIGHT - int(60 * self.ui_scale),
            btn_w,
            btn_h,
        )

        # Hitboxes das Setas
        arrow_box_size = int(100 * self.ui_scale)
        arrow_margin = int(10 * self.ui_scale)
        center_y = Config.SCREEN_HEIGHT // 2
        self.left_arrow_rect = pygame.Rect(
            arrow_margin, center_y - arrow_box_size // 2, arrow_box_size, arrow_box_size
        )
        self.right_arrow_rect = pygame.Rect(
            Config.SCREEN_WIDTH - arrow_box_size - arrow_margin,
            center_y - arrow_box_size // 2,
            arrow_box_size,
            arrow_box_size,
        )
        self.left_arrow_hover = False
        self.right_arrow_hover = False

        # Sistema de partículas
        self.particles: List[UIParticle] = []

        # Tremor ambiental
        self._focused_shake = (0.0, 0.0)

        # Tempo global para animações de bordas
        self.time = 0.0

        # Cache de backgrounds pré-construídos por índice de card
        self._background_cache: List[Any] = []

        # Pré-aquece o memo de backgrounds agora (fora da transição visível).
        self._prewarm_backgrounds()

    @staticmethod
    def _resolve_theme(world_config: Any) -> str:
        """Retorna o theme_str resolvido (expande 'procedural').

        Delega para `world_config.resolve_theme_key` — fonte única compartilhada
        com a música ambiente, garantindo pasta de tema == bioma visual."""
        return resolve_theme_key(world_config)

    def _build_background_for(self, index: int) -> None:
        """Aponta current_background para a entrada pré-construída do cache."""
        if 0 <= index < len(self._background_cache):
            self.current_background = self._background_cache[index]

    def _prebuild_all_backgrounds(self) -> None:
        """Popula o cache por índice de card a partir do memo (sem reconstruir).

        Backgrounds já vêm do memo de módulo — pré-aquecido no ``__init__`` —,
        então isto é O(n) de lookups, sem o custo de geração que estourava o
        frame da transição.
        """
        self._background_cache = []
        for card in self.world_cards:
            theme_str = self._resolve_theme(card.world_config)
            if theme_str == "starfield":
                self._background_cache.append(None)
            else:
                try:
                    bw, bh = self._bg_build_dims()
                    self._background_cache.append(
                        _get_cached_background(theme_str, bw, bh)
                    )
                except (ValueError, OSError):
                    self._background_cache.append(None)

    def _prewarm_backgrounds(self) -> None:
        """Gera os backgrounds dos temas existentes uma vez, no momento da
        criação da view (startup / transição de retorno ao menu), tirando o
        custo do caminho da transição menu→seleção de mundo."""
        for world_config in get_all_worlds():
            theme_str = self._resolve_theme(world_config)
            if theme_str == "starfield":
                continue
            try:
                bw, bh = self._bg_build_dims()
                _get_cached_background(theme_str, bw, bh)
            except (ValueError, OSError):
                pass

    def reset(self) -> None:
        """Reinicia a view com dados atualizados."""
        self.world_cards.clear()

        # Encontrar checkpoint atual para iniciar nele
        worlds = get_all_worlds()
        checkpoint_idx = 0

        for i, world_config in enumerate(worlds):
            # Modo arena de teste (dev): todos os mundos destravados para pular
            # direto a qualquer tema sem percorrer a campanha.
            if TEST_ARENA_ENABLED:
                state = WorldCardState.UNLOCKED
                best_score = 0
            elif world_config.world_id in self.player_profile.world_unlocks:
                unlock_status = self.player_profile.world_unlocks[world_config.world_id]
                if unlock_status.is_unlocked:
                    if (
                        world_config.world_id
                        == self.player_profile.current_checkpoint_world
                    ):
                        state = WorldCardState.CHECKPOINT
                        checkpoint_idx = i
                    else:
                        state = WorldCardState.UNLOCKED
                    best_score = unlock_status.last_best_score_at_checkpoint
                else:
                    state = WorldCardState.LOCKED
                    best_score = 0
            else:
                state = WorldCardState.LOCKED
                best_score = 0

            card = WorldCard(world_config, state, best_score, ui_scale=self.ui_scale)
            self.world_cards.append(card)

        self.selected_index = checkpoint_idx
        self.visual_scroll_index = float(checkpoint_idx)
        self.time = 0.0

        # Constrói todos os backgrounds
        self._prebuild_all_backgrounds()
        self._build_background_for(self.selected_index)
        self.last_selected = self.selected_index
        self.previous_background = None
        self.is_transitioning = False

    def handle_event(self, event: pygame.event.Event) -> None:
        """Processa eventos de entrada."""
        if event.type == pygame.KEYDOWN:
            current_time = pygame.time.get_ticks()

            if (
                event.key == pygame.K_LEFT
                and current_time - self.last_key_time > self.key_repeat_delay
            ):
                self.selected_index = (self.selected_index - 1) % len(self.world_cards)
                self.last_key_time = current_time
                sound_manager.play_sound("button_hover")

            elif (
                event.key == pygame.K_RIGHT
                and current_time - self.last_key_time > self.key_repeat_delay
            ):
                self.selected_index = (self.selected_index + 1) % len(self.world_cards)
                self.last_key_time = current_time
                sound_manager.play_sound("button_hover")

            elif event.key == pygame.K_RETURN:
                # K_RETURN sintético logo após um A do controle: o handler nativo
                # do A já resolveu a ação cursor-aware (seta/card/voltar). Ignora
                # este para não sobrepor com uma seleção de mundo. Enter real do
                # teclado nunca vem precedido de A → flag False → seleciona normal.
                if self._suppress_synthetic_confirm:
                    self._suppress_synthetic_confirm = False
                    return
                self._select_current_world()

            elif event.key == pygame.K_ESCAPE:
                self.on_back()

        elif event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                # Tratamos o A por completo aqui (cursor-aware). Suprime o
                # K_RETURN sintético que o app dispara em seguida — senão ele
                # selecionaria o mundo por cima da ação da seta sob a mira.
                self._suppress_synthetic_confirm = True
                pos = pygame.mouse.get_pos()
                if self.back_button_rect.collidepoint(pos):
                    sound_manager.play_sound("button_click")
                    self.on_back()
                elif self.left_arrow_rect.collidepoint(pos):
                    self._cycle_world(-1)
                elif self.right_arrow_rect.collidepoint(pos):
                    self._cycle_world(+1)
                else:
                    # Cursor sobre card ou neutro: confirma o mundo focado.
                    self._select_current_world()
                return
            if event.button == XboxButton.B:
                self.on_back()
                return
            # LB/RB ciclam mundos sem precisar mirar nas setinhas — pedido do
            # usuário ("permitir troca de mundos diretamente usando LB e RB").
            if event.button == XboxButton.LB:
                self._cycle_world(-1)
                return
            if event.button == XboxButton.RB:
                self._cycle_world(+1)
                return

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Verificar botão voltar
            if self.back_button_rect.collidepoint(event.pos):
                sound_manager.play_sound("button_click")
                self.on_back()
                return

            # Verificar Setas de Navegação
            if self.left_arrow_rect.collidepoint(event.pos):
                self.selected_index = (self.selected_index - 1) % len(self.world_cards)
                sound_manager.play_sound("button_hover")
                return

            if self.right_arrow_rect.collidepoint(event.pos):
                self.selected_index = (self.selected_index + 1) % len(self.world_cards)
                sound_manager.play_sound("button_hover")
                return

            # Verificar clique nos cards
            for i, card in enumerate(self.world_cards):
                if card.rect.collidepoint(event.pos):
                    if i == self.selected_index:
                        # Se já estiver focado, entrar
                        self._select_current_world()
                    else:
                        # Se não, focar
                        self.selected_index = i
                        sound_manager.play_sound("button_hover")
                    break

    def _select_current_world(self) -> None:
        """Seleciona o mundo atualmente focado."""
        if 0 <= self.selected_index < len(self.world_cards):
            card = self.world_cards[self.selected_index]
            if card.state != WorldCardState.LOCKED:
                self.on_world_selected(card.world_config.world_id)
                sound_manager.play_sound("button_click")

    def _cycle_world(self, direction: int) -> None:
        """Avança/retrocede no carrossel. Wrap nos extremos (igual ao DPad esq/dir
        sintetizado), pra rotação natural entre todos os mundos."""
        if not self.world_cards:
            return
        self.selected_index = (self.selected_index + direction) % len(self.world_cards)
        sound_manager.play_sound("button_hover")

    def get_focusable_rects(self) -> list[pygame.Rect]:
        """Cards visíveis + setas + botão Voltar. Snap-focus do DPad usa
        a lista pra calcular o vizinho mais próximo na direção apertada.

        Apertar baixo a partir das setas/card central naturalmente vai cair
        no botão Voltar (o único rect na parte inferior da tela)."""
        rects: list[pygame.Rect] = []
        for card in self.world_cards:
            if hasattr(card, "rect"):
                rects.append(card.rect)
        rects.append(self.left_arrow_rect)
        rects.append(self.right_arrow_rect)
        rects.append(self.back_button_rect)
        return rects

    def update(self, _dt: float) -> None:
        """Atualiza a lógica da view."""
        self.time += _dt

        # Rede de segurança: o A nativo e seu K_RETURN sintético são processados
        # no mesmo frame (antes deste update), então a flag já foi consumida.
        # Se o sintético não chegar a disparar (ex.: gamepad conectado mas
        # desabilitado), zerar aqui evita que ela suprima um Enter futuro.
        self._suppress_synthetic_confirm = False

        # Detectar hover nas setas
        mouse_pos = pygame.mouse.get_pos()
        self.left_arrow_hover = self.left_arrow_rect.collidepoint(mouse_pos)
        self.right_arrow_hover = self.right_arrow_rect.collidepoint(mouse_pos)

        # Interpolação suave do carrossel com lógica de loop (caminho mais curto).
        # Animações off: sem deslize — snap direto no card selecionado.
        num_cards = len(self.world_cards)
        from ..core.visual_quality import visual_quality

        if not visual_quality.ui_animations:
            self.visual_scroll_index = float(self.selected_index)
        else:
            diff = self.selected_index - self.visual_scroll_index

            # Ajustar para o caminho mais curto no loop
            if abs(diff) > num_cards / 2:
                if diff > 0:
                    diff -= num_cards
                else:
                    diff += num_cards

            if abs(diff) > 0.01:
                self.visual_scroll_index += diff * _dt * self.scroll_speed
                # Normalizar para manter dentro do range [0, num_cards)
                self.visual_scroll_index = self.visual_scroll_index % num_cards
            else:
                self.visual_scroll_index = float(self.selected_index)

        # Atualizar background se seleção mudou
        if self.selected_index != self.last_selected:
            self.last_selected = self.selected_index
            # Iniciar transição: salvar background antigo
            self.previous_background = self.current_background
            self.is_transitioning = True
            self.transition_progress = 0.0
            self._build_background_for(self.selected_index)

        # Animar transição de fade do background (instantânea se animações off).
        if self.is_transitioning:
            from ..core.visual_quality import visual_quality

            if visual_quality.ui_animations:
                self.transition_progress += _dt / self.transition_duration
            else:
                self.transition_progress = 1.0
            if self.transition_progress >= 1.0:
                self.transition_progress = 1.0
                self.is_transitioning = False
                self.previous_background = None
            else:
                if self.previous_background is not None:
                    try:
                        self.previous_background.update(_dt, 0.5)
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

        # Atualizar animação do background atual
        if self.current_background is not None:
            try:
                self.current_background.update(_dt, 0.5)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Emitir partículas para o card focado
        if 0 <= self.selected_index < len(self.world_cards):
            card = self.world_cards[self.selected_index]
            # Usar a cor da borda do card para as partículas
            p_color = card.border_color

            # Tremor ambiental leve no focado
            # amplitude reduzida para ser "atmosférico"
            amp_x, amp_y = 3, 2
            freq = 4.0
            from ..core.visual_quality import visual_quality

            if visual_quality.ui_animations:
                card_shake_x = math.sin(self.time * freq) * amp_x
                card_shake_y = math.cos(self.time * freq * 1.1) * amp_y
            else:
                card_shake_x = card_shake_y = 0.0

            # Armazenar temporariamente no objeto view para o render usar
            # (Poderia ser um atributo do card, mas vamos injetar no render)
            self._focused_shake = (card_shake_x, card_shake_y)

            # Emitir partículas nas bordas do card central (focado)
            num_p = 2
            for _ in range(num_p):
                # Posição visual central
                center_x = Config.SCREEN_WIDTH // 2
                center_y = Config.SCREEN_HEIGHT // 2

                # Escolher um lado aleatório da borda (baseado no tamanho real do card focado)
                side = random.randint(0, 3)
                half_w, half_h = card.base_width // 2, card.base_height // 2

                if side == 0:  # Top
                    px = center_x + random.uniform(-half_w, half_w)
                    py = center_y - half_h
                elif side == 1:  # Bottom
                    px = center_x + random.uniform(-half_w, half_w)
                    py = center_y + half_h
                elif side == 2:  # Left
                    px = center_x - half_w
                    py = center_y + random.uniform(-half_h, half_h)
                else:  # Right
                    px = center_x + half_w
                    py = center_y + random.uniform(-half_h, half_h)

                self.particles.append(UIParticle(px, py, p_color))
        else:
            self._focused_shake = (0, 0)

        # Atualizar partículas
        for p in self.particles[:]:
            p.update(_dt)
            if p.life <= 0:
                self.particles.remove(p)

    def render(self, surface: pygame.Surface) -> None:
        """Renderiza a view com carrossel dinâmico."""
        # Fundo preto
        surface.fill((0, 0, 0))

        # 1. Renderizar Background
        self._render_background(surface)

        # Título
        surface.blit(self.title_text, self.title_rect)

        # Renderizar Partículas (atrás dos cards)
        for p in self.particles:
            p.draw(surface)

        # 2. Renderizar Cards do Carrossel
        center_x = Config.SCREEN_WIDTH // 2
        center_y = Config.SCREEN_HEIGHT // 2

        # Renderizar cards em ordem de profundidade
        num_cards = len(self.world_cards)
        indices = list(range(num_cards))

        # Helper para calcular distância modular correta para ordenação de profundidade
        def modular_dist(idx: int) -> float:
            d = abs(idx - self.visual_scroll_index)
            return min(d, num_cards - d)

        indices.sort(key=modular_dist, reverse=True)

        for i in indices:
            card = self.world_cards[i]

            # rel_idx modular para posicionamento correto no loop
            rel_idx = i - self.visual_scroll_index
            if rel_idx > num_cards / 2:
                rel_idx -= num_cards
            elif rel_idx < -num_cards / 2:
                rel_idx += num_cards

            dist = abs(rel_idx)

            # Curva de escala e alpha
            scale = max(0.6, 1.0 - (dist * 0.25))
            alpha = int(max(100, 255 - (dist * 150)))

            # Posição X com perspectiva
            x = center_x + (rel_idx * self.card_spacing * (0.8 + scale * 0.2))

            # Um card é focado se for o mais próximo do visual_scroll_index (arredondado)
            is_focused = i == self.selected_index

            # Aplicar tremor se focado
            final_center_x = int(x)
            final_center_y = center_y
            if is_focused:
                final_center_x += int(self._focused_shake[0])
                final_center_y += int(self._focused_shake[1])

            if -400 < x < Config.SCREEN_WIDTH + 400:
                card.render(
                    surface,
                    (final_center_x, final_center_y),
                    scale,
                    alpha,
                    self.time,
                    is_focused,
                )

        # 3. Instruções e Botão Voltar
        self._render_ui_elements(surface)

    def _bg_build_dims(self) -> tuple[int, int]:
        """Dims de construção do background do tema. Com fundo retrô (lowres),
        meia-res — igual ao jogo (que aplica upscale)."""
        from ..core.visual_quality import visual_quality

        if visual_quality.lowres_background:
            return Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2
        return Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

    def _draw_themed_bg(self, bg: Background, scratch: pygame.Surface) -> None:
        """Desenha o background do tema no scratch full-size com o MESMO upscale
        do jogo: em fundo retrô, desenha em meia-res e amplia (nearest)."""
        from ..core.visual_quality import visual_quality

        if visual_quality.lowres_background:
            self._bg_scratch_half.fill((0, 0, 0, 0))
            bg.draw(self._bg_scratch_half)
            pygame.transform.scale(
                self._bg_scratch_half, scratch.get_size(), scratch
            )
        else:
            scratch.fill((0, 0, 0, 0))
            bg.draw(scratch)

    def _render_background(self, surface: pygame.Surface) -> None:
        """Renderiza o background com transição de fade."""
        if self.is_transitioning:
            if self.previous_background is not None:
                try:
                    self._draw_themed_bg(self.previous_background, self._bg_scratch_a)
                    self._bg_scratch_a.set_alpha(
                        int(76 * (1.0 - self.transition_progress))
                    )
                    surface.blit(self._bg_scratch_a, (0, 0))
                except Exception:
                    pass
            else:
                try:
                    self._bg_scratch_a.fill((0, 0, 0, 0))
                    self.renderer.starfield.draw(self._bg_scratch_a)
                    self._bg_scratch_a.set_alpha(
                        int(76 * (1.0 - self.transition_progress))
                    )
                    surface.blit(self._bg_scratch_a, (0, 0))
                except Exception:
                    pass

            if self.current_background is not None:
                try:
                    self._draw_themed_bg(self.current_background, self._bg_scratch_b)
                    self._bg_scratch_b.set_alpha(int(76 * self.transition_progress))
                    surface.blit(self._bg_scratch_b, (0, 0))
                except Exception:
                    pass
            else:
                try:
                    self._bg_scratch_b.fill((0, 0, 0, 0))
                    self.renderer.starfield.draw(self._bg_scratch_b)
                    self._bg_scratch_b.set_alpha(int(76 * self.transition_progress))
                    surface.blit(self._bg_scratch_b, (0, 0))
                except Exception:
                    pass
        else:
            if self.current_background is not None:
                try:
                    self._draw_themed_bg(self.current_background, self._bg_scratch_a)
                    self._bg_scratch_a.set_alpha(76)
                    surface.blit(self._bg_scratch_a, (0, 0))
                except Exception:
                    self.renderer.starfield.draw(surface)
            else:
                self.renderer.starfield.draw(surface)

    def _render_ui_elements(self, surface: pygame.Surface) -> None:
        """Renderiza botões e elementos de navegação."""
        # Botão Voltar
        draw_bordered_button(
            surface,
            self.back_button_rect,
            t("common.back"),
            self._inst_font,
            CUSTOM_PURPLE,
            255,
            0,
        )

        # Desenhar Setas Chevron Pixel Art (Indicação Visual)
        center_y = Config.SCREEN_HEIGHT // 2

        # Pulsação suave
        pulse = (math.sin(self.time * 4) + 1) * 0.5
        arrow_alpha = int(120 + 135 * pulse)

        # Helper para desenhar chevron pixelado
        def draw_pixel_chevron(
            surf: pygame.Surface,
            x_tip: int,
            direction: int,
            color: Tuple[int, int, int],
            alpha: int,
            scale: float = 1.0,
        ):
            # direction: -1 para apontar para a esquerda (<), 1 para apontar para a direita (>)
            length = int(30 * scale)
            pixel_size = int(5 * scale)

            # Criar superfície temporária para o chevron
            chevron_surf = pygame.Surface(
                (length + pixel_size, length * 2), pygame.SRCALPHA
            )

            for i in range(0, length, pixel_size):
                # px: Se aponta para a direita (>), o x aumenta conforme i se aproxima do centro vertical (length)
                # Se aponta para a esquerda (<), o x diminui conforme i se aproxima do centro
                px = i if direction == -1 else length - i

                # Parte superior da chevron
                py_sup = length - i
                pygame.draw.rect(
                    chevron_surf, (*color, alpha), (px, py_sup, pixel_size, pixel_size)
                )

                # Parte inferior da chevron
                py_inf = length + i
                pygame.draw.rect(
                    chevron_surf, (*color, alpha), (px, py_inf, pixel_size, pixel_size)
                )

            # Blitar centralizado verticalmente
            dest_rect = chevron_surf.get_rect(centery=center_y)
            if direction == -1:
                dest_rect.left = x_tip
            else:
                dest_rect.right = x_tip

            surf.blit(chevron_surf, dest_rect.topleft)

        # Desenhar Setas com escala dinâmica se houver hover. A escala base
        # acompanha a resolução (ui_scale) para casar com cards e hitboxes.
        left_scale = (1.4 if self.left_arrow_hover else 1.0) * self.ui_scale
        right_scale = (1.4 if self.right_arrow_hover else 1.0) * self.ui_scale
        tip_x = int(60 * self.ui_scale)

        draw_pixel_chevron(surface, tip_x, -1, CUSTOM_GOLD, arrow_alpha, left_scale)
        draw_pixel_chevron(
            surface,
            Config.SCREEN_WIDTH - tip_x,
            1,
            CUSTOM_GOLD,
            arrow_alpha,
            right_scale,
        )
