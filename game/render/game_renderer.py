"""game_renderer.py — Renderizador especializado para a PlayingScene.

Desacopla a lógica de renderização e HUD da cena de gameplay, tratando
o desenho de entidades, efeitos visuais, shake de tela e overlays.

Consome um `RenderFrame` (DTO) construído pela cena por frame. Não acessa
nada de `PlayingScene` diretamente — contrato explícito via `render_frame.py`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, Optional, TypedDict, cast

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_font, get_image
from ..core.config import config as Config
from ..core.i18n import i18n, t
from ..core.difficulty import DifficultyPreset
from ..core.upgrades import get_upgrade_icon

if TYPE_CHECKING:
    from ..entities.player.ship import Ship
    from ..systems.entity_manager import EntityManager
from .hud_layout import (
    UpgradeHudLayout,
    container_corners,
    joystick_center,
    joystick_knob_radius,
    joystick_radius,
    panel_radius,
    pause_button_rect,
    rotate_button_rect,
    slot_radius,
    upgrade_hud_layout,
)
from .render_frame import RenderFrame


class PowerupUiData(TypedDict):
    color: tuple[int, int, int]
    symbol: str
    label: str


class GameRenderer:
    """
    Gerencia a renderização da cena principal de gameplay.
    Responsável por:
    - Desenhar o background dinâmico.
    - Delegar o desenho de entidades ao EntityManager.
    - Renderizar o HUD (score, vidas, upgrades, combo).
    - Aplicar efeitos de tela como screen-shake e fades.
    """

    # Amplitude do 'pop' do número do score. Menor que os 18% do painel de
    # combo porque a fonte do score é bem maior (32px): o mesmo percentual ali
    # invadiria as bordas da caixa nos scores mais largos.
    SCORE_POP_AMPLITUDE = 0.14

    # Símbolos e rótulos dos efeitos ativos no HUD.
    #
    # A COR vem de `colors.POWERUP_COLORS` — a MESMA que o pickup usa no chão
    # (`entities/pickups/powerup.py`). Antes esta tabela trazia cores próprias
    # da paleta genérica, e o mesmo power-up aparecia em duas cores na tela ao
    # mesmo tempo; pior, `piercing_shot` e `time_stop` caíam ambos em PURPLE e
    # ficavam indistinguíveis aqui, embora sejam distintos como pickup.
    #
    # `explosive_shot` não é `PowerUpType`: é o upgrade (`core/upgrades.py`),
    # que aparece nesta faixa de efeitos ativos mas não existe como pickup no
    # chão. Por isso a cor dele mora aqui e não em `POWERUP_COLORS`.
    EXPLOSIVE_SHOT_COLOR = colors.ORANGE

    POWERUP_UI_DATA: dict[str, PowerupUiData] = {
        "shield": {
            "color": colors.POWERUP_COLORS["shield"],
            "symbol": "S",
            "label": "ESCUDO",
        },
        "double_shot": {
            "color": colors.POWERUP_COLORS["double_shot"],
            "symbol": "2X",
            "label": "TIRO DUPLO",
        },
        "spread_shot": {
            "color": colors.POWERUP_COLORS["spread_shot"],
            "symbol": "5X",
            "label": "LEQUE",
        },
        "speed": {
            "color": colors.POWERUP_COLORS["speed"],
            "symbol": "V",
            "label": "VELOCIDADE",
        },
        "score": {
            "color": colors.POWERUP_COLORS["score"],
            "symbol": "$",
            "label": "SCORE X1.5",
        },
        "mini_ships": {
            "color": colors.POWERUP_COLORS["mini_ships"],
            "symbol": "M",
            "label": "MINI-SHIPS",
        },
        "explosive_shot": {
            "color": EXPLOSIVE_SHOT_COLOR,
            "symbol": "EX",
            "label": "EXPLOSIVOS",
        },
        "life": {
            "color": colors.POWERUP_COLORS["life"],
            "symbol": "+",
            "label": "VIDA",
        },
        "piercing_shot": {
            "color": colors.POWERUP_COLORS["piercing_shot"],
            "symbol": "P",
            "label": "PERFURANTE",
        },
        "rainbow": {
            "color": colors.POWERUP_COLORS["rainbow"],
            "symbol": "*",
            "label": "RAINBOW",
        },
        "cooldown_haste": {
            "color": colors.POWERUP_COLORS["cooldown_haste"],
            "symbol": "CD",
            "label": "RECARGA",
        },
        "time_stop": {
            "color": colors.POWERUP_COLORS["time_stop"],
            "symbol": "T",
            "label": "STOP",
        },
        "damage_boost": {
            "color": colors.POWERUP_COLORS["damage_boost"],
            "symbol": "DMG",
            "label": "DANO+",
        },
        "chain_shot": {
            "color": colors.POWERUP_COLORS["chain_shot"],
            "symbol": "Z",
            "label": "RAIO",
        },
        "repulsion_shield": {
            "color": colors.POWERUP_COLORS["repulsion_shield"],
            "symbol": "W",
            "label": "VENTO",
        },
    }

    def __init__(self, base_renderer: Any) -> None:
        self.r = base_renderer
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        # Surface branca reusada para o impact flash (set_alpha por frame; sem alocar).
        self._flash_surface: pygame.Surface | None = None
        # Buffer SRCALPHA reusado da moldura de tempo parado (§7).
        self._time_stop_surface: pygame.Surface | None = None
        # Faixas do perímetro que a moldura ocupa. Calculadas junto com o buffer
        # (mudam só com a resolução) para não alocar 4 Rects por frame.
        self._time_stop_strips: tuple[pygame.Rect, ...] = ()
        self._time_stop_labels: dict[str, pygame.Surface] = {}
        # Fileira de slots de upgrade VAZIOS: peça inerte, rasterizada uma vez e
        # revalidada por chave (ver `_render_empty_upgrade_slots`).
        self._empty_slots_cache_key: tuple[Any, ...] | None = None
        self._empty_slots_cache: tuple[pygame.Surface, tuple[int, int]] = (
            pygame.Surface((1, 1), pygame.SRCALPHA),
            (0, 0),
        )

        # Escala de UI relativa ao design base (1280×720). Como todas as
        # resoluções ofertadas são 16:9, um único fator (largura) cobre os dois
        # eixos. O HUD é desenhado em pixels fixos do design base; sem este
        # fator, fontes/caixas/slots ficavam desproporcionais fora de 720p
        # (mesma convenção dos menus — ver memory/menu-ui-scale-convention).
        # Em 720p ui_scale == 1.0, então o layout é idêntico ao original.
        self.ui_scale = Config.SCREEN_WIDTH / 1280.0

        self.warning_font = get_font(max(8, int(Config.WARNING_FONT_SIZE * self.ui_scale)))

        # Fontes do HUD (escaladas)
        self.hud_font_tiny = get_font(max(8, int(10 * self.ui_scale)))
        self.hud_font_small = get_font(max(8, int(13 * self.ui_scale)))
        self.hud_font_medium = get_font(max(8, int(18 * self.ui_scale)))
        self.hud_font_large = get_font(max(8, int(24 * self.ui_scale)))
        self.hud_font_score = get_font(max(8, int(32 * self.ui_scale)))
        self.hud_font_score_small = get_font(max(8, int(26 * self.ui_scale)))

        # Mesmíssimo asset do pickup (`entities/pickups/star.py`) e da Central
        # de Loadout: é a associação visual que liga "peguei aquilo" a "aquilo
        # compra slot". Escalado uma vez aqui, não por frame (§7).
        star_px = max(8, self._s(13))
        self._star_icon = pygame.transform.scale(
            get_image(BASE_DIR / "assets" / "images" / "icons" / "icon_star.png"),
            (star_px, star_px),
        )

    def _s(self, value: float) -> int:
        """Escala um valor de pixel do design base (1280×720) para a resolução
        lógica atual. Em 720p retorna o valor original (ui_scale == 1.0)."""
        return int(value * self.ui_scale)

    def render(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Método principal de renderização chamado a cada frame."""

        from ..scenes.playing import GameState

        dt = frame.dt
        speed_multiplier = 1.0
        boss_active = False

        if frame.world_transition_cutscene_active:
            if frame.is_arrival_cutscene:
                # Arrival (re-entry/entrada no mundo): Decelera de warp para normal
                progress = min(
                    1.0,
                    max(
                        0.0,
                        (Config.PREPARATION_TIME - frame.preparation_time_left)
                        / Config.PREPARATION_TIME,
                    ),
                )
                speed_multiplier = 1.0 + (Config.WARP_SPEED_MULTIPLIER - 1.0) * (
                    1.0 - progress**2
                )
            else:
                # Departure (saída do mundo): Acelera de normal para warp
                charge_dur = Config.WORLD_TRANSITION_CUTSCENE_CHARGE_DURATION
                total_dur = Config.WORLD_TRANSITION_CUTSCENE_DURATION
                if frame.world_transition_cutscene_timer > charge_dur:
                    launch_time = frame.world_transition_cutscene_timer - charge_dur
                    launch_total = total_dur - charge_dur
                    progress = min(1.0, launch_time / max(0.1, launch_total))
                    # Aceleração quadrática para o efeito visual de "disparo"
                    speed_multiplier = 1.0 + (Config.WARP_SPEED_MULTIPLIER - 1.0) * (
                        progress**2
                    )
        else:
            boss_active = bool(
                frame.boss_controller.active
                and frame.entity_manager.boss
                and not frame.entity_manager.boss.dead
            )
            if boss_active:
                speed_multiplier = Config.BOSS_WARP_SPEED_MULTIPLIER

        # 1. Background
        self.r.background(
            self.game_surface,
            dt=dt,
            speed_multiplier=speed_multiplier,
            draw_celestials=not boss_active,
            atmosphere_progress=frame.atmosphere_progress,
        )

        # 1b. Escurecimento de fundo em luta de boss: aplicado sobre o background
        # e ANTES das entidades, então só o fundo escurece (gameplay segue legível).
        frame.boss_backdrop_dim.draw(self.game_surface)

        # 2. Entidades
        current_fps = self.r.current_fps if self.r.current_fps > 0 else 60.0
        intro_active = bool(
            frame.entity_manager.boss
            and getattr(frame.entity_manager.boss, "is_intro_active", False)
        )
        frame.entity_manager.draw(
            self.game_surface,
            frame.ship.rect.centerx,
            frame.ship.rect.centery,
            frame.boss_controller.enemy_visible,
            fps=current_fps,
            draw_boss=not intro_active,
        )

        if frame.show_enemy_hitboxes:
            self._draw_enemy_hitboxes(frame.entity_manager, self.game_surface)

        # 3. Partículas de transição de mundo
        for p in frame.world_transition_thruster_particles:
            px = frame.ship.x + p["offset_x"]
            py = frame.ship.y + p["offset_y"]
            pygame.draw.circle(
                self.game_surface,
                p["color"],
                (int(px), int(py)),
                max(1, int(p["size"])),
            )

        # 4. Nave do jogador (P1 + naves adicionais em multiplayer local)
        if frame.primary_alive:
            frame.ship.draw(self.game_surface)
        for extra_ship in frame.extra_ships:
            extra_ship.draw(self.game_surface)
        # 4b. Beacons de revive de slots mortos (renderer trata como overlay
        # acima das naves para garantir leitura visual do raio).
        for beacon in frame.revival_beacons:
            beacon.draw(self.game_surface)

        # 5. Efeito de entrada de boss (CloudArchmage)
        if intro_active:
            boss = frame.entity_manager.boss
            if boss:
                from ..entities.bosses.cloud_archmage_boss import CloudArchmageBoss

                archmage = cast(CloudArchmageBoss, boss)
                overlay_alpha = archmage.get_intro_dim_alpha()
                if overlay_alpha > 0:
                    overlay = pygame.Surface(
                        (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
                    )
                    overlay.fill((0, 0, 0, overlay_alpha))
                    self.game_surface.blit(overlay, (0, 0))
                archmage.draw(self.game_surface)

        # Sem argumento de propósito: o medidor lê o relógio de parede. O `dt`
        # daqui vem clampado em 1/30 e saturava o contador em exatamente 30.
        self.r.update_fps()

        # 6. Novo HUD Organizado
        self._render_unified_hud(frame, self.game_surface)

        # 7. Overlays específicos (Upgrades, Cofre, Combo)
        # Upgrades e Combo agora são chamados dentro de unified_hud para melhor posicionamento
        # Mas mantemos aqui se preferir manter a ordem original de camadas.

        # 8. Painel de debug único (F3 perf + estado do F7). As hitboxes em si são
        # desenhadas na camada das entidades; aqui só mostramos o painel, que
        # aparece quando qualquer toggle de debug está ativo — sem overlays soltos.
        if frame.show_fps or frame.show_enemy_hitboxes:
            self._draw_diagnostics(frame, self.game_surface)

        # 9. Blit final com Screen Shake
        surface.blit(self.game_surface, self._compute_shake_offset(frame))

        # 9a. Impact flash (white frames) sobre o mundo, abaixo de HUD/avisos.
        self._draw_impact_flash(frame, surface)

        # 9b. Vinheta de dano (overlay de borda sobre mundo + HUD, abaixo dos
        # avisos). Early-out interno quando não há nada visível.
        frame.damage_vignette.draw(surface)

        # 9c. Parada do tempo: moldura + rótulo. Sobre o mundo e a vinheta,
        # abaixo dos avisos críticos (boss/preparação), que precisam vencer.
        self._draw_time_stop_overlay(frame, surface)

        # 10. Warning de Boss
        warning_timer = frame.boss_controller.warning_timer
        if warning_timer > 0 and int(warning_timer * 5) % 2 == 1:
            warning_text = self.warning_font.render("WARNING!", True, colors.RED)
            text_rect = warning_text.get_rect(
                center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2)
            )
            surface.blit(warning_text, text_rect)

        # 11. Overlay de preparação (estendido para animação de saída)
        if frame.state == GameState.PREPARING or frame.preparation_time_left > -1.0:
            self.r.preparation(
                surface,
                frame.preparation_time_left,
                stage_name=frame.stage_name,
                difficulty=frame.difficulty_preset,
            )

        # 11b. Pop-up de início de nível (sub-fases)
        if frame.level_popup_timer > 0:
            self.r.level_popup(
                surface,
                frame.level_popup_text,
                frame.level_popup_timer,
                frame.level_popup_duration,
            )

    # ── Moldura da parada do tempo ────────────────────────────────────────
    # Medidas em px do design 1280×720, escaladas por `_s` (§12).
    _TIME_STOP_BAND = 34
    """Profundidade do campo de energia na borda, em repouso."""

    _TIME_STOP_BAND_WARNING = 16
    """Quanto a banda avança para dentro no auge do aviso de término."""

    _TIME_STOP_RINGS = 17
    """Anéis concêntricos que compõem o gradiente da banda.

    O gradiente é o que dá PRESENÇA sem atrapalhar: a energia é forte na beirada
    e se apaga antes de chegar na zona de jogo. Um contorno de linha única, por
    mais grosso que seja, ou é invisível ou vira uma faixa dura na tela.
    """

    _TIME_STOP_RIM = 2
    """Fio nítido no limite interno da banda — fecha a moldura."""

    _TIME_STOP_CORNER = 54
    """Braço dos colchetes de canto sobre o fio interno."""

    _TIME_STOP_BREATH_HZ = 0.32
    """Respiração lenta. Dilatação temporal se lê como ritmo LONGO."""

    _TIME_STOP_STUTTER_HZ = 1.15
    _TIME_STOP_STUTTER_STEPS = 5.0
    """Trepidação em degraus — o ponteiro de um relógio travado.

    É o traço que diz "tempo quebrado" em vez de "efeito bonito": um valor
    quantizado avança aos trancos, e o olho lê o salto como falha na passagem
    do tempo. Suave demais viraria um brilho genérico de power-up.
    """

    _TIME_STOP_RIPPLE_WAVES = 2.0
    _TIME_STOP_RIPPLE_HZ = 0.55
    """Ondulação que percorre a banda de fora para dentro."""

    _TIME_STOP_PEAK_ALPHA = 200
    """Alpha do anel mais externo no auge. O resto do gradiente cai a partir daí.

    Alto porque os anéis são ladrilhados e NÃO se somam — o valor é o brilho
    real da beirada da tela, não uma contribuição empilhada.
    """

    def _draw_time_stop_overlay(
        self, frame: RenderFrame, surface: pygame.Surface
    ) -> None:
        """Campo de energia nas bordas que comunica a parada do tempo.

        A leitura tem que ser periférica: o jogador identifica o estado pelo
        canto do olho, sem tirar a atenção do centro. Por isso a energia mora na
        moldura e se apaga para dentro, e por isso nada aqui cobre a zona de
        jogo.

        Quatro camadas, todas moduladas pelos mesmos envelopes:

        - **gradiente** (`_TIME_STOP_RINGS` anéis): o corpo do efeito. Cada anel
          leva a ondulação defasada, então a energia parece escorrer para dentro.
        - **fio interno**: fecha a moldura e dá o acabamento de HUD.
        - **colchetes de canto**: âncora visual; carregam a trepidação.
        - **rótulo**: o texto, só enquanto congelado.

        E três envelopes, todos prontos no DTO (o renderer não tem relógio nem
        conhece durações — §3):

        - `time_stop_openness` **abre e fecha** — 0→1→0. Um só valor para as
          duas pontas, então o fechamento é a abertura rebobinada, e não uma
          segunda animação que recomeça do zero.
        - `time_stop_warning` **aperta** — a respiração calma cede lugar a um
          pisca aflito e acelerado, e a banda avança para dentro. Libera junto
          com a `openness` na saída, sem degrau na virada.

        Abertura e fechamento são cronometrados pelos SFX, não pela rampa dos
        inimigos: o par som+moldura é o que anuncia o estado, e os dois têm de
        chegar juntos.

        **Nada aqui ramifica por fase.** Não há `if frozen:` — todo o desenho é
        função contínua de `openness` e `warning`, e é isso que garante que a
        transição permanência→saída não tenha salto: não existe caminho de
        código novo para ela entrar.
        """
        intensidade = frame.time_stop_openness
        if intensidade <= 0.0:
            return
        warning = frame.time_stop_warning

        fase = frame.time_stop_phase
        cos, sin, tau = math.cos, math.sin, math.tau

        # Respiração lenta + trepidação quantizada. `floor` é o que transforma
        # uma oscilação contínua num avanço aos saltos.
        respiro = 0.5 - 0.5 * cos(fase * self._TIME_STOP_BREATH_HZ * tau)
        travado = (
            math.floor(fase * self._TIME_STOP_STUTTER_HZ * self._TIME_STOP_STUTTER_STEPS)
            / self._TIME_STOP_STUTTER_STEPS
        )
        tremulo = 0.5 - 0.5 * cos(travado * tau)

        pulso = 0.70 + 0.30 * (0.6 * respiro + 0.4 * tremulo)
        if warning > 0.0:
            # Mistura progressiva em vez de troca: o aviso ENTRA por cima da
            # respiração, que vai perdendo peso. Trocar de regime de uma vez
            # dava um salto visível no primeiro frame do aviso.
            hz = 3.0 + 8.0 * warning
            urgencia = 0.5 - 0.5 * cos(fase * hz * tau)
            pulso = pulso * (1.0 - warning) + (0.45 + 0.55 * urgencia) * warning

        banda = self._s(
            (self._TIME_STOP_BAND + self._TIME_STOP_BAND_WARNING * warning)
            # A banda também CRESCE na entrada: parte de ~60% e abre.
            * (0.6 + 0.4 * intensidade)
        )
        if banda <= 0:
            return

        w, h = surface.get_width(), surface.get_height()
        moldura, faixas = self._time_stop_scratch(w, h)

        cor = colors.POWERUP_COLORS["time_stop"]
        acento = self._TIME_STOP_ACCENT
        pico = self._TIME_STOP_PEAK_ALPHA * intensidade * pulso

        # ── Gradiente ondulante ──
        # A onda percorre a banda em DEGRAUS (`travado`), não deslizando: a
        # energia entra aos trancos, como o ponteiro de um relógio parado. É
        # esse detalhe que separa "tempo quebrado" de um brilho genérico de
        # power-up. Uma fração contínua entra na mistura só para o degrau não
        # ficar mecânico demais.
        aneis = self._TIME_STOP_RINGS
        desloc_onda = (0.65 * travado + 0.35 * fase * self._TIME_STOP_RIPPLE_HZ) * tau
        for i in range(aneis):
            # Anéis LADRILHADOS: cada um ocupa exatamente a faixa entre a sua
            # borda e a do próximo. Se as espessuras se sobrepusessem, os alphas
            # se somariam e o gradiente viraria um bloco chapado — que foi
            # exatamente o que apagou a ondulação na primeira versão.
            r0 = (i * banda) // aneis
            r1 = ((i + 1) * banda) // aneis
            esp = r1 - r0
            if esp <= 0:
                continue
            prof = i / (aneis - 1)  # 0 na beirada da tela → 1 no fio interno
            # Queda exponencial para dentro: forte na borda, apagado antes de
            # alcançar a área jogável.
            queda = (1.0 - prof) ** 1.7
            # Modulação RASA de propósito: com amplitude funda a onda abria
            # buracos escuros entre os anéis e o campo lia como listras, não
            # como energia. A onda tem que ondular a intensidade, não recortar
            # o gradiente.
            onda = 0.74 + 0.26 * sin(
                prof * self._TIME_STOP_RIPPLE_WAVES * tau - desloc_onda
            )
            a = int(pico * queda * onda)
            if a <= 0:
                continue
            pygame.draw.rect(
                moldura, (*cor, min(255, a)), (r0, r0, w - 2 * r0, h - 2 * r0), esp
            )

        # ── Fio interno + colchetes de canto ──
        fio_a = int(min(255, 205 * intensidade * (0.55 + 0.45 * pulso)))
        if fio_a > 0:
            pygame.draw.rect(
                moldura,
                (*acento, fio_a),
                (banda, banda, w - 2 * banda, h - 2 * banda),
                max(1, self._s(self._TIME_STOP_RIM)),
            )
            self._draw_time_stop_corners(
                moldura,
                banda,
                w,
                h,
                (*acento, int(min(255, 245 * intensidade * (0.45 + 0.55 * tremulo)))),
            )

        for faixa in faixas:
            surface.blit(moldura, faixa.topleft, faixa)

        # O rótulo esmaece junto com a moldura. Antes ele sumia de estalo no
        # descongelamento — o texto era a única coisa que ainda ramificava por
        # fase, e piscava para fora enquanto a borda ainda estava se dissolvendo.
        texto = t("hud.time_stop.ending") if warning > 0.0 else t("hud.time_stop")
        rotulo = self._time_stop_labels.get(texto)
        if rotulo is None:
            # Rasterizar texto por frame é desperdício: são duas frases fixas e
            # só o ALPHA muda, que `set_alpha` resolve sem re-rasterizar. A
            # chave é o texto já traduzido, então trocar de idioma repovoa o
            # cache sozinho.
            rotulo = self.hud_font_tiny.render(texto, True, acento)
            self._time_stop_labels[texto] = rotulo
        rotulo.set_alpha(int(min(255, 235 * intensidade)))
        surface.blit(rotulo, rotulo.get_rect(center=(w // 2, banda + self._s(12))))

    _TIME_STOP_ACCENT = (206, 176, 255)
    """Lavanda claro para o fio e os colchetes.

    O roxo do power-up (145, 87, 217) é a identidade do efeito, mas some contra
    fundo escuro em traço fino. O acento é o mesmo matiz dessaturado e clareado:
    lê como a mesma energia, só que incandescente na parte nítida.
    """

    def _draw_time_stop_corners(
        self,
        moldura: pygame.Surface,
        banda: int,
        w: int,
        h: int,
        cor: tuple[int, int, int, int],
    ) -> None:
        """Colchetes em L sobre o fio interno, um por canto.

        Nitidamente mais grossos que o fio: encostados nele com a mesma
        espessura, os dois se fundiam e o canto virava só um traço um pouco mais
        longo. O contraste de peso é o que faz o colchete existir como elemento.
        """
        if cor[3] <= 0:
            return
        braco = min(self._s(self._TIME_STOP_CORNER), (w - 2 * banda) // 3)
        if braco <= 0:
            return
        esp = max(3, self._s(5))
        x0, y0 = banda, banda
        x1, y1 = w - banda, h - banda
        for cx, cy, sx, sy in (
            (x0, y0, 1, 1),
            (x1, y0, -1, 1),
            (x0, y1, 1, -1),
            (x1, y1, -1, -1),
        ):
            pygame.draw.line(moldura, cor, (cx, cy), (cx + sx * braco, cy), esp)
            pygame.draw.line(moldura, cor, (cx, cy), (cx, cy + sy * braco), esp)

    def _time_stop_scratch(
        self, w: int, h: int
    ) -> tuple[pygame.Surface, tuple[pygame.Rect, ...]]:
        """Buffer reusado da moldura, já limpo, + as faixas que ele ocupa (§7).

        Só o PERÍMETRO é tocado — na limpeza e, depois, no blit. O miolo do
        buffer é transparente e permanente, então percorrê-lo é trabalho puro.
        Medido a 1080p: o blit de tela cheia de uma surface SRCALPHA custa
        3,49 ms (21% de um frame de 60fps, com o efeito ativo); as quatro
        faixas custam 1,05 ms. O `fill` cai de 1,01 ms para 0,47 ms.

        A profundidade vem das CONSTANTES, não da banda do frame: com a banda
        do frame sobraria resíduo do frame anterior, quando ela era maior.

        As faixas são DISJUNTAS (as laterais não repetem os cantos). Na
        limpeza a sobreposição seria inofensiva, mas o blit compõe alpha, e
        cantos blitados duas vezes sairiam mais fortes que o resto da moldura.
        """
        if self._time_stop_surface is None or self._time_stop_surface.get_size() != (
            w,
            h,
        ):
            self._time_stop_surface = pygame.Surface((w, h), pygame.SRCALPHA)
            d = min(
                min(w, h) // 2,
                self._s(self._TIME_STOP_BAND + self._TIME_STOP_BAND_WARNING)
                + max(1, self._s(self._TIME_STOP_RIM))
                + max(3, self._s(5)),
            )
            self._time_stop_strips = (
                pygame.Rect(0, 0, w, d),
                pygame.Rect(0, h - d, w, d),
                pygame.Rect(0, d, d, h - 2 * d),
                pygame.Rect(w - d, d, d, h - 2 * d),
            )

        moldura = self._time_stop_surface
        vazio = (0, 0, 0, 0)
        for faixa in self._time_stop_strips:
            moldura.fill(vazio, faixa)
        return moldura, self._time_stop_strips

    def _draw_impact_flash(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """White frames: clarão branco curto que esmaece em 1-3 frames (impact frame)."""
        if frame.flash_timer <= 0.0 or frame.flash_duration <= 0.0 or frame.flash_alpha <= 0:
            return
        a = int(frame.flash_alpha * (frame.flash_timer / frame.flash_duration))
        if a <= 0:
            return
        if self._flash_surface is None:
            self._flash_surface = pygame.Surface(
                (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
            )
            self._flash_surface.fill((255, 255, 255))
        self._flash_surface.set_alpha(min(255, a))
        surface.blit(self._flash_surface, (0, 0))

    def _compute_shake_offset(self, frame: RenderFrame) -> tuple[int, int]:
        """Calcula o deslocamento aleatório para o efeito de screen shake."""
        if frame.shake_timer <= 0:
            return (0, 0)
        intensity = frame.shake_intensity
        return (
            random.randint(-intensity, intensity),
            random.randint(-intensity, intensity),
        )

    def _draw_diagnostics(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Overlay de diagnóstico (toggle F): FPS, frame time, partículas, entidades.

        Ajuda a identificar quais sistemas consomem mais — combinado com o seletor
        de Qualidade Visual, dá pra medir o impacto de cada nível.
        """
        from ..core.visual_quality import visual_quality

        stats = self.r.get_fps_stats()
        em = frame.entity_manager

        ship_particles = 0
        for s in (frame.ship, *frame.extra_ships):
            ship_particles += (
                len(s.entry_particles)
                + len(s.thruster_particles)
                + len(s.dash_trail_particles)
            )
        # Quebra por categoria (fonte única). Partículas da nave somam à linha
        # de partículas; o total de entidades exclui partículas (linha própria).
        breakdown = em.debug_entity_breakdown()
        particles = breakdown["Particulas"] + ship_particles
        entities = sum(v for k, v in breakdown.items() if k != "Particulas")

        fps = stats["fps"]
        fps_color = (
            colors.YELLOW
            if fps >= 55
            else (255, 170, 40) if fps >= 30 else (255, 70, 70)
        )
        dim: colors.Color = (170, 170, 180)
        lines: list[tuple[str, colors.Color]] = [
            (f"FPS: {fps:.0f}", fps_color),
            (
                f"Frame: {stats['avg_frame_time']:.1f}ms avg / "
                f"{stats['max_frame_time']:.1f}ms max",
                colors.WHITE,
            ),
            (f"Qualidade: {visual_quality.level.label}", (150, 220, 255)),
            (
                f"Hitboxes (F7): {'ON' if frame.show_enemy_hitboxes else 'OFF'}",
                (255, 200, 40) if frame.show_enemy_hitboxes else dim,
            ),
            (f"Entidades: {entities}", colors.WHITE),
        ]
        # Quebra por categoria, indentada e em tom suave. Particulas usa o valor
        # com as partículas da nave para casar com a soma cosmética total.
        for cat, count in breakdown.items():
            shown = particles if cat == "Particulas" else count
            lines.append((f"  {cat}: {shown}", dim))

        # Detalhe por tipo de classe — aparece quando há entidades não-zero além de
        # partículas. Permite rastrear o que está presente numa arena aparentemente
        # vazia sem precisar de logs externos.
        if entities > 0:
            type_counts = em.debug_active_entity_names()
            if type_counts:
                lines.append(("  Tipos:", (200, 200, 80)))
                for name, count in list(type_counts.items())[:10]:
                    lines.append((f"    {name}: {count}", (150, 170, 150)))

        font = self.r.font_small
        line_h = font.get_linesize()
        pad = self._s(6)
        # Fundo translúcido para legibilidade sobre qualquer cena.
        box_w = max(font.size(t)[0] for t, _ in lines) + pad * 2
        box_h = line_h * len(lines) + pad * 2
        # Canto inferior esquerdo, encostado nas bordas (ferramenta discreta).
        x = self._s(10)
        y = Config.SCREEN_HEIGHT - box_h - self._s(10)
        bg = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 150))
        surface.blit(bg, (x, y))
        for i, (text, color) in enumerate(lines):
            surf = font.render(text, True, color)
            surface.blit(surf, (x + pad, y + pad + i * line_h))

    def _render_unified_hud(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Renderiza todo o HUD de forma integrada e organizada com design simétrico."""

        # 1. Caixa Superior Esquerda (Score e Kills)
        self._render_score_kills_box(frame, surface)

        # 2. Caixa Superior Direita (Vidas e Powerups)
        self._render_players_status_box(frame, surface)

        # 3. Interstício de Atmosfera (Barra de Altitude)
        if frame.in_atmosphere:
            self._render_atmosphere_hud(frame, surface)

        # 4. Cofre (Cofre é centralizado logo abaixo do topo se houver espaço)
        p2_hud = frame.p2_hud
        p2_ship = p2_hud.ship if p2_hud is not None else None
        self._render_storage_slots_hud(frame.ship, surface, p2_ship)

        # 5. Upgrades (Bottom Centralizado)
        self._render_upgrades_hud(frame, surface)

        # 6. Combo (Bottom Right)
        self._render_combo_hud(frame.ship, surface)

        # 7. Botão de pausa — SÓ no modo toque. No desktop a tecla P já resolve,
        # e um botão permanente seria mobília numa tela que precisa de atenção
        # para o combate. No celular não existe tecla P.
        if frame.touch_mode:
            self._render_touch_pause_button(surface, frame.joystick_enabled)
        if frame.joystick_enabled:
            self._render_virtual_joystick(frame, surface)
            self._render_rotate_button(surface)

    def _render_virtual_joystick(
        self, frame: RenderFrame, surface: pygame.Surface
    ) -> None:
        """Disco-base + knob. Translúcido parado, aceso enquanto o polegar está.

        Desenhado com alpha baixo de propósito: ele ocupa um canto da arena a
        partida inteira, e um direcional opaco esconderia inimigos entrando pela
        borda. O realce ao tocar é o que confirma "peguei o direcional" sem
        precisar olhar para ele.
        """
        cx, cy = joystick_center(self.ui_scale)
        r = joystick_radius(self.ui_scale)
        kr = joystick_knob_radius(self.ui_scale)
        ativo = frame.joystick_active

        base = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(base, (0, 0, 0, 90 if ativo else 60), (r, r), r)
        pygame.draw.circle(
            base, (*colors.WHITE, 130 if ativo else 70), (r, r), r, max(2, self._s(2))
        )
        surface.blit(base, (cx - r, cy - r))

        ox, oy = frame.joystick_offset
        knob = pygame.Surface((kr * 2, kr * 2), pygame.SRCALPHA)
        pygame.draw.circle(knob, (*colors.WHITE, 170 if ativo else 100), (kr, kr), kr)
        pygame.draw.circle(
            knob, (*colors.CYAN, 220 if ativo else 120), (kr, kr), kr, max(2, self._s(2))
        )
        surface.blit(knob, (int(cx + ox) - kr, int(cy + oy) - kr))

    def _render_rotate_button(self, surface: pygame.Surface) -> None:
        """Seta circular — o `Ctrl` do teclado, que no celular não existe.

        Sem o botão, girar a nave fica INALCANÇÁVEL no toque: os outros dois
        caminhos são tecla e botão do meio do mouse.
        """
        rect = rotate_button_rect(self.ui_scale)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        radius = panel_radius(self.ui_scale)
        pygame.draw.rect(panel, (0, 0, 0, 150), panel.get_rect(), border_radius=radius)
        pygame.draw.rect(
            panel, (*colors.WHITE, 120), panel.get_rect(), 2, border_radius=radius
        )

        cx, cy = rect.width // 2, rect.height // 2
        r = int(min(rect.width, rect.height) * 0.28)
        # Arco de ~270°: a abertura é o que faz o círculo ler como "girar" em vez
        # de "recarregar" ou "alvo".
        arco = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.arc(panel, (*colors.CYAN, 230), arco, -0.4, 4.3, max(2, self._s(3)))
        ponta = [
            (cx + r, cy - int(r * 0.55)),
            (cx + r + int(r * 0.45), cy + int(r * 0.05)),
            (cx + r - int(r * 0.45), cy + int(r * 0.05)),
        ]
        pygame.draw.polygon(panel, (*colors.CYAN, 230), ponta)
        surface.blit(panel, rect.topleft)

    def _render_touch_pause_button(
        self, surface: pygame.Surface, joystick: bool = False
    ) -> None:
        """Duas barras verticais num quadrado arredondado — o glifo universal.

        Sem texto de propósito: rótulo exigiria tradução, encolheria a fonte
        para caber, e "pausa" é um dos pouquíssimos ícones que todo mundo lê sem
        legenda.
        """
        rect = pause_button_rect(self.ui_scale, joystick=joystick)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        radius = panel_radius(self.ui_scale)
        pygame.draw.rect(panel, (0, 0, 0, 150), panel.get_rect(), border_radius=radius)
        pygame.draw.rect(
            panel, (*colors.WHITE, 120), panel.get_rect(), 2, border_radius=radius
        )

        bar_w = max(2, self._s(7))
        bar_h = max(4, self._s(24))
        gap = max(2, self._s(7))
        top = (rect.height - bar_h) // 2
        left = (rect.width - (bar_w * 2 + gap)) // 2
        for i in range(2):
            pygame.draw.rect(
                panel,
                (*colors.WHITE, 210),
                (left + i * (bar_w + gap), top, bar_w, bar_h),
                border_radius=max(1, self._s(2)),
            )
        surface.blit(panel, rect.topleft)

    def _render_atmosphere_hud(
        self, frame: RenderFrame, surface: pygame.Surface
    ) -> None:
        """Desenha a barra de altitude durante o interstício de atmosfera."""
        bar_w, bar_h = self._s(300), self._s(12)
        x = (Config.SCREEN_WIDTH - bar_w) // 2
        y = self._s(35)  # Logo abaixo do topo, entre as caixas de score/status

        # Determina o label e a direção visual da altitude
        # Exiting: Planeta -> Espaço (Altitude sobe de 0% a 100%)
        # Entering: Espaço -> Planeta (Altitude desce de 100% a 0%)
        is_exiting = frame.atmosphere_route == "exiting"
        label = "ALTITUDE" if is_exiting else "RE-ENTRY"
        display_ratio = (
            frame.atmosphere_progress if is_exiting else 1.0 - frame.atmosphere_progress
        )

        # Fundo da barra
        self._draw_hud_bar(surface, x, y, bar_w, bar_h, 1.0, (20, 20, 30))
        # Preenchimento
        color = colors.CYAN if is_exiting else colors.ORANGE
        self._draw_hud_bar(surface, x, y, bar_w, bar_h, display_ratio, color)
        # Borda
        pygame.draw.rect(
            surface, colors.WHITE, (x, y, bar_w, bar_h), 1, border_radius=bar_h // 2
        )

        # Texto Centralizado acima da barra
        txt_surf = self.hud_font_tiny.render(label, True, colors.WHITE)
        surface.blit(txt_surf, (x + (bar_w - txt_surf.get_width()) // 2, y - self._s(16)))

        # Porcentagem (opcional, pequeno do lado)
        pct_txt = f"{int(display_ratio * 100)}%"
        pct_surf = self.hud_font_tiny.render(pct_txt, True, colors.GRAY)
        surface.blit(pct_surf, (x + bar_w + self._s(10), y - self._s(2)))

    def _render_score_kills_box(
        self, frame: RenderFrame, surface: pygame.Surface
    ) -> None:
        """Renderiza o score e kills em uma caixa adaptativa no canto superior esquerdo."""
        score_text: str = f"{frame.score:06d}"
        kills_text = f"KILLS: {frame.total_enemies_destroyed}"

        # Calcular largura necessária (threshold escalado junto das fontes)
        score_w_limit = self._s(300)
        score_w = self.hud_font_score.size(score_text)[0]
        if score_w > score_w_limit:
            score_text = f"{frame.score:.2e}".replace("e+0", "e+").replace("e-0", "e-")
            score_w = self.hud_font_score.size(score_text)[0]
            if score_w > score_w_limit:
                score_w = self.hud_font_score_small.size(score_text)[0]
        kills_w = self.hud_font_tiny.size(kills_text)[0]

        # Linha de baixo: "KILLS: n" e o saldo de estrelas lado a lado. Ficam na
        # MESMA linha (em vez de uma terceira) para a caixa não mudar de altura
        # — o resto do HUD é posicionado em cima dela.
        stars_text = str(frame.available_stars)
        stars_w = self.hud_font_tiny.size(stars_text)[0]
        star_icon_w = self._star_icon.get_width()
        star_gap = self._s(4)  # entre o ícone e o número
        row_gap = self._s(12)  # entre o bloco de kills e o de estrelas
        bottom_row_w = kills_w + row_gap + star_icon_w + star_gap + stars_w

        content_w = max(score_w, bottom_row_w)

        box_padding = self._s(20)
        box_w = content_w + (box_padding * 2)
        box_h = self._s(85)
        radius = self._s(15)
        rect = pygame.Rect(self._s(15), 0, box_w, box_h)

        # Fundo da Caixa
        overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(
            overlay,
            (0, 0, 0, 160),
            (0, 0, box_w, box_h),
            border_bottom_left_radius=radius,
            border_bottom_right_radius=radius,
        )
        surface.blit(overlay, rect.topleft)

        # Score
        score_font = (
            self.hud_font_score
            if self.hud_font_score.size(score_text)[0] <= score_w_limit
            else self.hud_font_score_small
        )
        score_surf = score_font.render(score_text, True, colors.WHITE)

        # 'Pop' ao pontuar: cresce e relaxa, igual ao indicador de combo do
        # Reverberador. Escala SÓ o número — a caixa e o texto de kills seguem
        # medidos pelo tamanho original, então o HUD não treme junto nem muda
        # de largura a cada abate.
        cx = rect.centerx
        cy = rect.top + self._s(15) + score_surf.get_height() // 2
        if frame.score_pop > 0.0:
            scale = 1.0 + self.SCORE_POP_AMPLITUDE * frame.score_pop
            score_surf = pygame.transform.smoothscale(
                score_surf,
                (
                    int(score_surf.get_width() * scale),
                    int(score_surf.get_height() * scale),
                ),
            )
        surface.blit(
            score_surf,
            (cx - score_surf.get_width() // 2, cy - score_surf.get_height() // 2),
        )

        # Kills + saldo de estrelas, centralizados juntos como uma linha só.
        row_y = rect.top + self._s(60)
        row_x = rect.centerx - bottom_row_w // 2

        kills_surf = self.hud_font_tiny.render(kills_text, True, colors.GRAY)
        surface.blit(kills_surf, (row_x, row_y))

        star_x = row_x + kills_w + row_gap
        # O ícone é maior que a fonte tiny: alinha pelo centro vertical do texto
        # para os dois não parecerem desencontrados.
        text_h = kills_surf.get_height()
        surface.blit(
            self._star_icon,
            (star_x, row_y + (text_h - self._star_icon.get_height()) // 2),
        )
        stars_surf = self.hud_font_tiny.render(stars_text, True, colors.CUSTOM_GOLD)
        surface.blit(stars_surf, (star_x + star_icon_w + star_gap, row_y))

    def _render_players_status_box(
        self, frame: RenderFrame, surface: pygame.Surface
    ) -> None:
        """Renderiza vidas e powerups em uma caixa adaptativa no canto superior direito."""
        p2_hud = frame.p2_hud
        is_coop = p2_hud is not None

        # 1. Calcular larguras dos blocos de conteúdo
        # Bloco P1
        p1_lives_txt = str(frame.lives)
        p1_lives_w = self.hud_font_large.size(p1_lives_txt)[0]
        icon_px = self._s(32)
        block_gap = self._s(8)
        p1_block_w = icon_px + block_gap + p1_lives_w  # Icon + Gap + Text

        # Bloco P2 ou Convite
        if is_coop:
            p2_info = p2_hud
            assert p2_info is not None
            p2_lives_txt = (
                f"{int(p2_info.beacon_progress * 100)}%"
                if p2_info.is_dead
                else str(p2_info.lives)
            )
            p2_lives_w = (
                self.hud_font_small if p2_info.is_dead else self.hud_font_large
            ).size(p2_lives_txt)[0]
            p2_block_w = icon_px + block_gap + p2_lives_w
        else:
            invite_w1 = self.hud_font_tiny.size("P2")[0]
            invite_w2 = self.hud_font_small.size("PRESS START")[0]
            p2_block_w = max(invite_w1, invite_w2)

        # 2. Definir dimensões da caixa com base no conteúdo
        internal_gap = self._s(40)  # Espaço entre P1 e P2 (space-between feeling)
        side_padding = self._s(20)
        box_w = p1_block_w + internal_gap + p2_block_w + (side_padding * 2)
        box_h = self._s(85)
        rect = pygame.Rect(Config.SCREEN_WIDTH - box_w - self._s(15), 0, box_w, box_h)

        # Fundo da Caixa
        overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(
            overlay,
            (0, 0, 0, 160),
            (0, 0, box_w, box_h),
            border_bottom_left_radius=self._s(15),
            border_bottom_right_radius=self._s(15),
        )
        surface.blit(overlay, rect.topleft)

        # 3. Renderizar P1 (Alinhado à esquerda da caixa + padding)
        p1_rect = pygame.Rect(rect.left + side_padding, rect.top, p1_block_w, box_h)
        self._render_player_in_box(
            surface, frame.ship, frame.lives, p1_rect, is_p2=False
        )

        # 4. Renderizar P2 ou Convite (Alinhado à direita da caixa - padding)
        p2_rect = pygame.Rect(
            rect.right - side_padding - p2_block_w, rect.top, p2_block_w, box_h
        )

        if not is_coop:
            # Convite P2 (Piscando)
            if (pygame.time.get_ticks() // 600) % 2 == 0:
                p2_label = self.hud_font_tiny.render("P2", True, colors.CYAN)
                invite_surf = self.hud_font_small.render(
                    "PRESS START", True, colors.WHITE
                )
                surface.blit(
                    p2_label,
                    (p2_rect.centerx - p2_label.get_width() // 2, p2_rect.top + self._s(20)),
                )
                surface.blit(
                    invite_surf,
                    (p2_rect.centerx - invite_surf.get_width() // 2, p2_rect.top + self._s(40)),
                )
        else:
            p2_info = p2_hud
            assert p2_info is not None
            self._render_player_in_box(
                surface,
                p2_info.ship,
                p2_info.lives,
                p2_rect,
                is_p2=True,
                p2_info=p2_info,
            )

    def _render_player_in_box(
        self,
        surface: pygame.Surface,
        ship: Ship,
        lives: int,
        rect: pygame.Rect,
        is_p2: bool,
        p2_info: Any = None,
    ) -> None:
        """Helper para renderizar info de um jogador dentro de sua área alocada."""
        # 0. Etiqueta P1/P2. Sem ela, nada na tela diz qual jogador é qual: quem
        # é P1 sai da ordem de enumeração dos controles pelo SDL, que pode mudar
        # entre execuções. Com a etiqueta, basta mover e ver qual nave responde
        # — e, se estiver trocado, os jogadores trocam de controle entre si.
        tag = "P2" if is_p2 else "P1"
        tag_color = colors.CYAN if is_p2 else colors.WHITE
        tag_surf = self.hud_font_tiny.render(tag, True, tag_color)
        surface.blit(tag_surf, (rect.left, rect.top + self._s(2)))

        # 1. Ícone da Nave + Vidas
        if ship and ship.ship_image:
            icon_px = self._s(32)
            icon = pygame.transform.scale(ship.ship_image, (icon_px, icon_px))

            # Vidas ou Status Morto. Os offsets abrem espaço para a etiqueta
            # P1/P2 acima (que ocupa até y≈13) sem encostar na linha de
            # powerups (y≈55).
            if is_p2 and p2_info and p2_info.is_dead:
                pct = int(p2_info.beacon_progress * 100)
                txt = self.hud_font_small.render(f"{pct}%", True, colors.CYAN)
                txt_y_offset = self._s(24)
            else:
                txt = self.hud_font_large.render(str(lives), True, colors.WHITE)
                txt_y_offset = self._s(18)

            # O rect passado já define a largura exata do bloco (Ícone + Gap + Texto)
            # Então apenas desenhamos a partir da esquerda do rect.
            surface.blit(icon, (rect.left, rect.top + self._s(16)))
            surface.blit(txt, (rect.left + self._s(40), rect.top + txt_y_offset))

        # 2. Powerups Ativos (Mini ícones na parte de baixo do rect)
        self._render_active_powerups_in_box(surface, ship, rect)

    def _render_active_powerups_in_box(
        self, surface: pygame.Surface, ship: Ship, rect: pygame.Rect
    ) -> None:
        """Desenha powerups ativos na linha inferior da caixa do jogador."""
        active: list[tuple[str, float]] = []
        time_checks = [
            (ship.get_invulnerable_time(), "shield", 8.0),
            (ship.get_double_shot_time(), "double_shot", 10.0),
            (
                ship.get_spread_shot_time(),
                "spread_shot",
                Config.SPREAD_SHOT_DURATION,
            ),
            (ship.get_speed_boost_time(), "speed", 8.0),
            (ship.mini_ships_timer, "mini_ships", 25.0),
            (ship.damage_boost_timer, "damage_boost", 8.0),
            (ship.piercing_shot_timer, "piercing_shot", 7.0),
            (ship.chain_shot_timer, "chain_shot", 8.0),
            (ship.repulsion_shield_timer, "repulsion_shield", 8.0),
        ]
        for time_left, key, total in time_checks:
            if time_left > 0:
                active.append((key, time_left / total))

        if ship.explosive_shots_active and ship.explosive_shots_remaining > 0:
            active.append(("explosive_shot", ship.explosive_shots_remaining / 10.0))

        if not active:
            return

        icon_size = self._s(20)
        gap = self._s(4)
        y = rect.top + self._s(55)

        # Centralizar ícones na área do jogador
        total_w = len(active) * (icon_size + gap) - gap
        curr_x = rect.centerx - total_w // 2

        default_data: PowerupUiData = {
            "color": colors.WHITE,
            "symbol": "?",
            "label": "?",
        }
        for key, ratio in active:
            data = self.POWERUP_UI_DATA.get(key, default_data)

            icon_rect = pygame.Rect(curr_x, y, icon_size, icon_size)
            radius = self._s(4)
            pygame.draw.rect(surface, (20, 20, 30, 180), icon_rect, border_radius=radius)
            pygame.draw.rect(
                surface, data["color"], icon_rect, width=1, border_radius=radius
            )

            sym_surf = self.hud_font_tiny.render(data["symbol"], True, data["color"])
            surface.blit(sym_surf, sym_surf.get_rect(center=icon_rect.center))

            # Mini barra de progresso horizontal
            bar_y = y + icon_size + self._s(1)
            bar_h = max(1, self._s(2))
            pygame.draw.rect(surface, (40, 40, 40), (curr_x, bar_y, icon_size, bar_h))
            pygame.draw.rect(
                surface,
                data["color"],
                (curr_x, bar_y, int(icon_size * ratio), bar_h),
            )

            curr_x += icon_size + gap

    def _render_central_hud(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Legado. Agora integrado no _render_score_kills_box."""
        pass

    def _render_player_panel(
        self,
        surface: pygame.Surface,
        label_text: str,
        ship: Ship,
        lives: int,
        x: int,
        y: int,
        is_p2: bool = False,
        is_dead: bool = False,
        beacon_progress: float = 0.0,
        enemies: int | None = None,
        difficulty: DifficultyPreset | None = None,
    ) -> None:
        """Legado. Agora integrado no _render_players_status_box."""
        pass

    def _render_active_powerups(
        self, surface: pygame.Surface, ship: Ship, x: int, y: int, is_p2: bool
    ) -> None:
        """Legado. Agora integrado no _render_active_powerups_in_box."""
        pass

    def _draw_hud_bar(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        ratio: float,
        color: tuple[int, int, int],
    ) -> None:
        """Desenha uma barra de progresso simples."""
        pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h), border_radius=h // 2)
        if ratio > 0:
            fill_w = int(w * ratio)
            pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=h // 2)

    def _draw_enemy_hitboxes(self, em: EntityManager, surface: pygame.Surface) -> None:
        """Overlay de hitboxes para depuração visual (F7).

        Inclui o BOSS. Ele não vive na grade espacial de inimigos — é um slot
        próprio (`em.boss`) —, então percorrer só a grade deixava justamente o
        alvo mais complexo da tela de fora. Chefe com hitbox por máscara ou com
        partes múltiplas (Tríade) é onde este overlay mais vale.
        """
        targets: list[Any] = list(
            em.enemy_spatial_grid.query(0, 0, Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        )
        boss = em.boss
        if boss is not None and not getattr(boss, "dead", False):
            targets.append(boss)

        seen: set[int] = set()
        for enemy in targets:
            eid = id(enemy)
            if eid in seen or getattr(enemy, "dead", False):
                continue
            seen.add(eid)

            mask_getter = getattr(enemy, "get_collision_mask_data", None)
            has_mask = False
            if callable(mask_getter):
                raw = cast(
                    "tuple[pygame.mask.Mask, tuple[int, int]] | None",
                    mask_getter(),
                )
                if raw is not None:
                    mask, offset = raw
                    mask_w, mask_h = mask.get_size()
                    if mask_w > 0 and mask_h > 0:
                        # PREENCHIMENTO, não contorno: `Mask.outline()` devolve o
                        # contorno de UM componente conectado só, então máscara
                        # de várias partes (as duas Vozes + o corpo da Tríade)
                        # aparecia pela metade — justamente o caso em que olhar a
                        # hitbox importa. O preenchimento mostra a área inteira.
                        fill = mask.to_surface(
                            setcolor=(255, 120, 0, 255), unsetcolor=(0, 0, 0, 0)
                        ).convert_alpha()
                        fill.set_alpha(90)
                        surface.blit(fill, offset)
                        has_mask = True

            if not has_mask:
                for idx, rect in enumerate(self._get_enemy_contact_hitboxes(enemy)):
                    color = (255, 200, 40) if idx == 0 else (40, 220, 255)
                    pygame.draw.rect(surface, color, rect, 2)

    @staticmethod
    def _get_enemy_contact_hitboxes(enemy: Any) -> tuple[pygame.Rect, ...]:
        """Retorna hitboxes de contato para debug visual, com fallback para rect."""
        getter = getattr(enemy, "get_ship_contact_hitboxes", None)
        if callable(getter):
            raw_hitboxes = cast(Any, getter)()
            hitboxes = tuple(
                r
                for r in raw_hitboxes
                if isinstance(r, pygame.Rect) and r.width > 0 and r.height > 0
            )
            if hitboxes:
                return hitboxes

        enemy_rect = getattr(enemy, "rect", pygame.Rect(0, 0, 0, 0))
        if (
            isinstance(enemy_rect, pygame.Rect)
            and enemy_rect.width > 0
            and enemy_rect.height > 0
        ):
            return (enemy_rect,)
        return ()

    def _render_p2_hud(self, p2_hud: Any, surface: pygame.Surface) -> None:
        """HUD secundário legado. Agora integrado no _render_unified_hud."""
        pass

    def _render_combo_hud(self, ship: Ship, surface: pygame.Surface) -> None:
        """Indicador compacto do combo do Reverberador (canto inferior direito).

        Painel arredondado com barra de progresso até o cap. Animação por
        ``ship.draw_time`` (acumulador alimentado pelo update — §3, compatível
        com pausa/slow-motion): 'pop' de escala a cada abate e brilho pulsante
        quando o combo atinge o cap. Ancorado pela borda inferior-direita, então
        nunca vaza a tela por mais que o combo cresça.
        """
        if ship.profile.combo_damage_per_kill <= 0:
            return

        kills = ship.combo_kills
        bonus = ship.combo_damage_bonus
        cap = ship.profile.combo_damage_cap
        now = ship.draw_time
        at_cap = cap > 0 and bonus >= cap
        fill = (min(1.0, bonus / cap) if cap > 0 else min(1.0, bonus))

        # Cor de destaque: cinza (sem combo) -> âmbar conforme enche -> dourado
        # pulsante no cap.
        if kills == 0:
            accent = (150, 150, 160)
        elif at_cap:
            p = 0.5 + 0.5 * math.sin(now * 8.0)
            accent = (255, int(200 + 55 * p), int(70 + 70 * p))
        else:
            accent = (
                int(180 + 75 * fill),
                int(190 + 30 * fill),
                int(150 - 90 * fill),
            )

        # Conteúdo (fontes menores que antes: 11/18 vs 14/22).
        f_label, f_value = (
            get_font(max(8, int(11 * self.ui_scale))),
            get_font(max(8, int(18 * self.ui_scale))),
        )
        label = f_label.render("COMBO", True, (200, 200, 210))
        value = f_value.render(f"x{kills}", True, accent)
        pct = f_label.render(f"+{int(round(bonus * 100))}%", True, accent)

        pad, gap, bar_h, value_gap = self._s(8), self._s(3), self._s(4), self._s(6)
        inner_w = max(
            label.get_width(),
            value.get_width() + value_gap + pct.get_width(),
            self._s(60),
        )
        inner_h = label.get_height() + gap + value.get_height() + gap + bar_h
        panel_w, panel_h = inner_w + pad * 2, inner_h + pad * 2

        # Painel próprio: permite escalar no 'pop' sem distorcer o resto do HUD.
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_radius = self._s(8)
        pygame.draw.rect(panel, (16, 16, 24, 205), rect, border_radius=panel_radius)
        border_col = accent if kills > 0 else (70, 70, 82)
        pygame.draw.rect(
            panel, (*border_col, 255), rect, 2 if at_cap else 1, border_radius=panel_radius
        )

        panel.blit(label, (pad, pad))
        vy = pad + label.get_height() + gap
        panel.blit(value, (pad, vy))
        panel.blit(pct, (pad + value.get_width() + value_gap,
                         vy + value.get_height() - pct.get_height()))

        # Barra de progresso até o cap.
        by = vy + value.get_height() + gap
        pygame.draw.rect(panel, (255, 255, 255, 40), pygame.Rect(pad, by, inner_w, bar_h), border_radius=2)
        if fill > 0:
            fill_w = max(2, int(inner_w * fill))
            pygame.draw.rect(panel, (*accent, 255), pygame.Rect(pad, by, fill_w, bar_h), border_radius=2)

        # 'Pop' de escala logo após um abate (estoura e relaxa em ~0.25s).
        elapsed = now - ship.combo_pop_time
        sw, sh = panel_w, panel_h
        if 0.0 <= elapsed < 0.25:
            scale = 1.0 + 0.18 * (1.0 - elapsed / 0.25)
            sw, sh = int(panel_w * scale), int(panel_h * scale)
            panel = pygame.transform.smoothscale(panel, (sw, sh))

        # Âncora na borda inferior-direita: cresce do canto, nunca sai da tela.
        margin = self._s(16)
        surface.blit(panel, (Config.SCREEN_WIDTH - margin - sw,
                             Config.SCREEN_HEIGHT - margin - sh))

    def _render_storage_slots_hud(
        self,
        ship: Ship,
        surface: pygame.Surface,
        p2_ship: Optional[Ship] = None,
    ) -> None:
        """Exibe os slots de powerup armazenados (Cofre)."""

        # Define grupos a renderizar
        groups: list[tuple[Ship, str, tuple[str, ...]]] = []
        if ship.has_storage_slots():
            groups.append((ship, "P1", ("Q", "E")))
        if p2_ship is not None and p2_ship.has_storage_slots():
            groups.append((p2_ship, "P2", ("Y", "A")))
        if not groups:
            return

        font_label, font_hint, font_icon = (
            get_font(max(8, int(20 * self.ui_scale))),
            get_font(max(8, int(12 * self.ui_scale))),
            get_font(max(8, int(18 * self.ui_scale))),
        )
        font_group = get_font(max(8, int(11 * self.ui_scale)))
        slot_size, gap, group_gap = self._s(56), self._s(12), self._s(28)

        # Largura total
        total_w = 0
        for i, (g_ship, _, _) in enumerate(groups):
            n = len(g_ship.stored_powerups)
            total_w += n * slot_size + (n - 1) * gap
            if i < len(groups) - 1:
                total_w += group_gap

        # Centralizado abaixo da barra de score
        start_x, y = (Config.SCREEN_WIDTH - total_w) // 2, self._s(65)

        cur_x = start_x
        for g_ship, group_label, hint_keys in groups:
            slots = g_ship.stored_powerups
            group_w = len(slots) * slot_size + (len(slots) - 1) * gap

            # Label "P1"/"P2" centralizado acima do grupo (apenas em coop).
            if len(groups) > 1:
                label_surf = font_group.render(group_label, True, colors.CYAN)
                surface.blit(
                    label_surf,
                    (cur_x + (group_w - label_surf.get_width()) // 2, y - self._s(14)),
                )

            for i, kind in enumerate(slots):
                x = cur_x + i * (slot_size + gap)
                slot_surface = pygame.Surface((slot_size, slot_size), pygame.SRCALPHA)
                slot_radius_px = slot_radius(self.ui_scale)
                pygame.draw.rect(
                    slot_surface,
                    (20, 20, 30, 200),
                    (0, 0, slot_size, slot_size),
                    border_radius=slot_radius_px,
                )

                border_color = (
                    (*colors.YELLOW, 230) if kind is not None else (*colors.GRAY, 160)
                )
                pygame.draw.rect(
                    slot_surface,
                    border_color,
                    (0, 0, slot_size, slot_size),
                    2,
                    border_radius=slot_radius_px,
                )

                key_label = hint_keys[i] if i < len(hint_keys) else str(i + 1)
                slot_surface.blit(
                    font_hint.render(key_label, True, colors.WHITE),
                    (self._s(5), self._s(3)),
                )

                if kind is not None:
                    data = self.POWERUP_UI_DATA.get(
                        kind,
                        {
                            "color": (200, 200, 200),
                            "symbol": kind[:2].upper(),
                            "label": kind,
                        },
                    )
                    color = data["color"]
                    circle_r = self._s(16)
                    center = (slot_size // 2, slot_size // 2 + self._s(4))
                    pygame.draw.circle(slot_surface, color, center, circle_r)
                    pygame.draw.circle(slot_surface, colors.WHITE, center, circle_r, 2)
                    symbol = data["symbol"]
                    content = font_icon.render(symbol, True, colors.BLACK)
                    slot_surface.blit(content, content.get_rect(center=center))
                else:
                    dash = font_label.render("—", True, (90, 90, 90))
                    slot_surface.blit(
                        dash, dash.get_rect(center=(slot_size // 2, slot_size // 2))
                    )

                surface.blit(slot_surface, (x, y))

            cur_x += group_w + group_gap

    def _apply_cooldown_overlay(
        self,
        slot_surface: pygame.Surface,
        slot_w: int,
        slot_h: int,
        cd_left: float,
        cd_base: float,
        font_cd: pygame.font.Font,
    ) -> pygame.Surface:
        """Marca o slot como indisponível: cinza + contador regressivo.

        O feedback anterior era só uma barrinha de 4px na base do slot — some no
        caos do gameplay. Aqui o slot inteiro perde a cor (leitura periférica
        instantânea de "não posso usar") e ganha os segundos restantes em cima
        (leitura precisa de "quando poderei"). A barra continua, agora colorida
        sobre o cinza, dando o progresso contínuo que o número inteiro não dá.

        Devolve uma surface nova — `grayscale()` não opera in-place.
        """
        # Cinza + escurecido. O cinza sozinho ainda lê como "aceso" contra o
        # fundo escuro do container; o multiply é o que manda para o segundo
        # plano sem apagar a silhueta do ícone.
        out = pygame.transform.grayscale(slot_surface)
        out.fill((115, 115, 115, 255), special_flags=pygame.BLEND_RGB_MULT)

        pct = max(0.0, min(1.0, cd_left / cd_base if cd_base > 0 else 0.0))

        # Contador: segundos arredondados para cima, então nunca mostra "0"
        # enquanto ainda falta tempo (mostrar 0 e não poder usar seria mentira).
        # Cooldowns aqui vão de 15s a 200s, daí o inteiro em vez de decimais:
        # casas decimais a 60fps viram ruído ilegível.
        secs = math.ceil(cd_left)
        label = str(secs)
        # Metade de baixo do slot: o ícone subiu para abrir este espaço (ver
        # `icon_cy` em `_render_upgrades_hud`). O contorno preto garante leitura
        # sobre qualquer coisa que sobre do ícone cinza atrás.
        cd_rect = font_cd.render(label, True, colors.WHITE).get_rect(
            center=(slot_w // 2, slot_h // 2 + self._s(8))
        )
        outline = font_cd.render(label, True, (0, 0, 0))
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            out.blit(outline, cd_rect.move(ox, oy))
        out.blit(font_cd.render(label, True, colors.WHITE), cd_rect)

        # Barra de progresso (colorida, por cima do cinza).
        bar_h = max(1, self._s(4))
        inset = self._s(2)
        bar_inner_w = slot_w - self._s(4)
        bar_y = slot_h - bar_h - inset
        pygame.draw.rect(
            out,
            (120, 120, 120, 150),
            (inset, bar_y, bar_inner_w, bar_h),
            border_radius=self._s(2),
        )
        pygame.draw.rect(
            out,
            (80, 180, 255, 200),
            (inset, bar_y, int(bar_inner_w * pct), bar_h),
            border_radius=self._s(2),
        )
        return out

    def _render_empty_upgrade_slots(
        self, frame: RenderFrame, surface: pygame.Surface
    ) -> None:
        """Contornos apagados dos slots livres, quando NADA está equipado.

        Antes disto, `_render_upgrades_hud` simplesmente retornava com o loadout
        vazio e a partida inteira corria sem uma única menção aos aprimoramentos:
        nem os slots, nem as teclas que os acionam. Quem começou sem equipar nada
        não tinha, dentro do jogo, como descobrir que o sistema existe — o único
        ponto de contato era o botão do menu principal.

        O desenho é deliberadamente inerte: mesma geometria e posição da fileira
        cheia (para ser reconhecido como a mesma peça de HUD quando enfim
        estiver equipado), porém sem ícone, com borda apagada e o número da
        tecla em cada slot. Não pisca, não anima e não pede clique — é um convite
        silencioso, não um tutorial.
        """
        n = frame.unlocked_upgrade_slots
        if n <= 0:
            return

        # Esta peça é INERTE por definição (ver docstring): nada aqui depende do
        # frame — só de quantos slots existem, da escala, do modo toque, das
        # teclas e do idioma. Redesenhá-la a cada frame custava, medido no
        # nível 1, 0,19 ms e ~10 travessias Python→C (2n `draw.rect`, n+1
        # `font.render`, n+2 `blit`) para produzir sempre a MESMA imagem.
        #
        # No desktop isso se perde no ruído; no WASM cada travessia custa
        # múltiplas vezes mais, e o render já é ~93% do frame. Cacheada, a peça
        # inteira vira 1 blit.
        cache_key = (
            n,
            self.ui_scale,
            frame.touch_mode,
            tuple(frame.upgrade_keybindings),
            i18n.language,
        )
        if self._empty_slots_cache_key != cache_key:
            self._empty_slots_cache_key = cache_key
            # Layout e fonte só no miss: nem eles precisam ser resolvidos por frame.
            self._empty_slots_cache = self._build_empty_upgrade_slots(
                frame,
                upgrade_hud_layout(n, self.ui_scale, frame.touch_mode),
                get_font(max(8, int(12 * self.ui_scale))),
            )

        cached, origin = self._empty_slots_cache
        surface.blit(cached, origin)

    def _build_empty_upgrade_slots(
        self, frame: RenderFrame, layout: UpgradeHudLayout, font_small: pygame.font.Font
    ) -> tuple[pygame.Surface, tuple[int, int]]:
        """Rasteriza a fileira de slots vazios uma vez (ver `_render_empty_upgrade_slots`).

        Devolve a surface e o canto onde ela deve ser colada. A surface cobre a
        união do container com o rótulo acima dele — desenhar tudo em coordenadas
        relativas a esse canto é o que permite o blit único.
        """
        container_rect = layout.container
        container_w, container_h = container_rect.width, container_rect.height

        label = font_small.render(t("hud.upgrades_empty"), True, colors.WHITE)
        label.set_alpha(110)
        label_top = container_rect.top - self._s(14)
        label_left = container_rect.centerx - label.get_width() // 2

        # União do container com o rótulo: o rótulo sobe acima do container e
        # pode ser mais largo que ele.
        origin_x = min(container_rect.left, label_left)
        origin_y = min(container_rect.top, label_top)
        total_w = max(container_rect.right, label_left + label.get_width()) - origin_x
        total_h = container_rect.bottom - origin_y

        canvas = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
        cx = container_rect.left - origin_x
        cy = container_rect.top - origin_y

        # Fundo mais discreto que o da fileira cheia (alpha 160): o estado vazio
        # não deve competir com a leitura do combate.
        overlay = pygame.Surface((container_w, container_h), pygame.SRCALPHA)
        pygame.draw.rect(
            overlay,
            (0, 0, 0, 90),
            (0, 0, container_w, container_h),
            **container_corners(self.ui_scale, floating=frame.touch_mode),
        )
        canvas.blit(overlay, (cx, cy))

        slot_radius_px = slot_radius(self.ui_scale)
        for display_index, slot_rect in enumerate(layout.slots):
            slot_x = slot_rect.left - origin_x
            slot_y = slot_rect.top - origin_y
            slot_w, slot_h = slot_rect.width, slot_rect.height

            slot_surface = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)
            pygame.draw.rect(
                slot_surface,
                (30, 30, 30, 110),
                (0, 0, slot_w, slot_h),
                border_radius=slot_radius_px,
            )
            pygame.draw.rect(
                slot_surface,
                (*colors.WHITE, 70),
                (0, 0, slot_w, slot_h),
                2,
                border_radius=slot_radius_px,
            )

            try:
                key_label = pygame.key.name(frame.upgrade_keybindings[display_index]).upper()
            except (IndexError, TypeError):
                key_label = str(display_index + 1)
            key_surf = font_small.render(key_label, True, colors.WHITE)
            key_surf.set_alpha(120)
            slot_surface.blit(key_surf, (self._s(4), self._s(2)))

            canvas.blit(slot_surface, (slot_x, slot_y))

        # Nome do sistema acima da fileira, na MESMA palavra do botão do menu
        # principal (`menu.upgrades`): é o que transforma "duas caixas vazias"
        # em "ah, é aquilo do menu".
        canvas.blit(label, (label_left - origin_x, label_top - origin_y))

        return canvas, (origin_x, origin_y)

    def _render_upgrades_hud(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Exibe os slots de upgrades ativos centralizados na parte inferior."""
        active_slots: list[tuple[int, Any]] = [
            (i, upg) for i, upg in enumerate(frame.upgrade_slots) if upg is not None
        ]
        if not active_slots:
            self._render_empty_upgrade_slots(frame, surface)
            return

        font, font_small = (
            get_font(max(8, int(20 * self.ui_scale))),
            get_font(max(8, int(12 * self.ui_scale))),
        )
        # Contador do cooldown: precisa caber "200" (o maior base_cooldown) na
        # largura do slot, daí ser menor que a fonte do ícone.
        font_cd = get_font(max(8, int(16 * self.ui_scale)))
        layout = upgrade_hud_layout(len(active_slots), self.ui_scale, frame.touch_mode)
        container_rect = layout.container
        container_w, container_h = container_rect.width, container_rect.height

        # Desenhar container (Estilo similar à barra de score)
        overlay = pygame.Surface((container_w, container_h), pygame.SRCALPHA)
        pygame.draw.rect(
            overlay,
            (0, 0, 0, 160),
            (0, 0, container_w, container_h),
            **container_corners(self.ui_scale, floating=frame.touch_mode),
        )
        surface.blit(overlay, container_rect.topleft)

        for display_index, (i, upg) in enumerate(active_slots):
            slot_rect = layout.slots[display_index]
            slot_x, slot_y = slot_rect.topleft
            slot_w, slot_h = slot_rect.width, slot_rect.height

            # Tremor de uso negado: oscilação horizontal que decai até parar.
            # Horizontal e não vertical porque o slot é uma peça de uma fileira
            # — sacudir na transversal destaca sem parecer que a fileira inteira
            # está tremendo. A amplitude decai com o tempo restante, então o
            # movimento "assenta" em vez de cortar seco.
            denied_left = frame.upgrade_denied_timers.get(i, 0.0)
            if denied_left > 0.0:
                decay = denied_left / Config.UPGRADE_DENIED_SHAKE_TIME
                slot_x += int(
                    math.sin(denied_left * 55.0)
                    * self._s(Config.UPGRADE_DENIED_SHAKE_AMPLITUDE)
                    * decay
                )

            slot_surface = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)
            slot_radius_px = slot_radius(self.ui_scale)
            pygame.draw.rect(
                slot_surface,
                (30, 30, 30, 180),
                (0, 0, slot_w, slot_h),
                border_radius=slot_radius_px,
            )
            pygame.draw.rect(
                slot_surface,
                (*colors.WHITE, 200),
                (0, 0, slot_w, slot_h),
                2,
                border_radius=slot_radius_px,
            )

            try:
                keycode = frame.upgrade_keybindings[i]
                key_label = pygame.key.name(keycode).upper()
            except (IndexError, TypeError):
                key_label = str(i + 1)
            slot_surface.blit(
                font_small.render(key_label, True, colors.WHITE),
                (self._s(4), self._s(2)),
            )

            ui = upg.get_ui_state()
            cd_left = (
                float(ui["cooldown_left"])
                if ui.get("cooldown_left") is not None
                else 0.0
            )
            cd_base = float(ui["cooldown"]) if ui.get("cooldown") is not None else 1.0
            on_cooldown = cd_left > 0.0

            icon = get_upgrade_icon(
                str(ui.get("name", "")),
                str(ui.get("icon_id", "")) if ui.get("icon_id") else None,
            )
            # O ícone é um GLIFO centralizado — o contador ocuparia exatamente o
            # mesmo pixel. Em cooldown ele sobe e cede a metade de baixo ao
            # número, senão o slot indisponível viraria um número anônimo e você
            # perderia de vista QUAL poder está recarregando.
            icon_cy = slot_h // 2 - self._s(9) if on_cooldown else slot_h // 2
            icon_txt = font.render(icon, True, colors.CYAN)
            slot_surface.blit(
                icon_txt, icon_txt.get_rect(center=(slot_w // 2, icon_cy))
            )

            charges = ui.get("charges_left")
            if charges is not None:
                c_txt = font_small.render(f"{charges}", True, colors.WHITE)
                slot_surface.blit(
                    c_txt,
                    c_txt.get_rect(
                        bottomright=(slot_w - self._s(3), slot_h - self._s(3))
                    ),
                )

            if on_cooldown:
                slot_surface = self._apply_cooldown_overlay(
                    slot_surface, slot_w, slot_h, cd_left, cd_base, font_cd
                )

            surface.blit(slot_surface, (slot_x, slot_y))

            if ui["active"]:
                pygame.draw.rect(
                    surface,
                    colors.GREEN,
                    pygame.Rect(slot_x, slot_y, slot_w, slot_h),
                    3,
                    border_radius=self._s(8),
                )

            if frame.upgrade_select_mode and i == frame.upgrade_select_index:
                t_ticks = pygame.time.get_ticks()
                shake_x = int(math.sin(t_ticks / 35.0) * 2)
                shake_y = int(math.cos(t_ticks / 42.0) * 2)
                grow = self._s(3)
                pygame.draw.rect(
                    surface,
                    colors.CUSTOM_GOLD,
                    pygame.Rect(
                        slot_x - grow + shake_x,
                        slot_y - grow + shake_y,
                        slot_w + grow * 2,
                        slot_h + grow * 2,
                    ),
                    3,
                    border_radius=self._s(10),
                )

        if frame.upgrade_select_mode:
            hint = font_small.render(
                "LB/RB navegar  A confirmar  B cancelar", True, colors.CUSTOM_GOLD
            )
            surface.blit(
                hint,
                (
                    container_rect.centerx - hint.get_width() // 2,
                    container_rect.top - self._s(25),
                ),
            )
