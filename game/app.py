import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from .core.assets import load_custom_cursor
from .core.config import config as Config
from .core.config import set_screen_resolution
from .core.difficulty import DifficultyPreset
from .core.events import EventBus
from .core.gamepad import MAX_GAMEPAD_SLOTS, GamepadManager, XboxButton
from .core.input import Input
from .core.levels import FIXED_LEVELS, LevelManager
from .core.meta_progression import PlayerProfile
from .core.paths import get_preferences_path, get_profile_path
from .core.preferences import UserPreferences
from .core.state import Scene, StateManager
from .scenes.main_menu import MainMenuScene
from .systems.sound_system import SoundSystem

if TYPE_CHECKING:
    from .core.scene_transition import TransitionStyle

logger = logging.getLogger(__name__)


# Velocidade do cursor virtual movido pelo stick direito (px/s a magnitude 1.0).
_VIRTUAL_CURSOR_SPEED = 900.0

# Dead zone maior que a padrão de gameplay: sticks com drift acima de
# ``GamepadManager.DEAD_ZONE`` (0.18) ainda produziriam movimento constante
# do cursor, prendendo-o em uma borda. 0.30 + reescala linear cobre folga
# mecânica típica sem perder resposta perto do centro.
_VIRTUAL_CURSOR_DEAD_ZONE = 0.30

# Cap de dt para o cursor: frames muito longos (carregamento de cena, GC)
# produziam saltos enormes (e.g. dt=0.5s × stick=1.0 × 900 = 450 px) que
# levavam o cursor instantaneamente para a borda superior da tela.
_VIRTUAL_CURSOR_MAX_DT = 1.0 / 30.0

# Folga (px) ao reconhecer o MOUSEMOTION que o SDL emite depois de um
# `warp_cursor`. Com `pygame.SCALED` a coordenada faz um ida-e-volta
# lógico→físico→lógico e volta 1px deslocada quando o fator de escala não é
# inteiro. Pequena de propósito: movimento humano de verdade cobre bem mais.
_WARP_MATCH_TOLERANCE = 2

# Seta → direção (dx, dy) na convenção da tela: dy +1 é para BAIXO.
_ARROW_DIRECTIONS: dict[int, tuple[int, int]] = {
    pygame.K_LEFT: (-1, 0),
    pygame.K_RIGHT: (1, 0),
    pygame.K_UP: (0, -1),
    pygame.K_DOWN: (0, 1),
}

# Clamp do passo de tempo do loop. Um frame lento (construção da PlayingScene +
# carga de assets na 1ª partida, alt-tab, breakpoint) gera um dt enorme no frame
# seguinte que fast-forwarda animações e física — era o que "comia" o fade-in de
# início de partida só na primeira vez (depois do game over os assets já estão em
# cache, o frame é rápido e o fade roda suave). Limitar o passo a ~30fps absorve o
# pico sem teleportar o mundo.
_MAX_FRAME_DT = 1.0 / 30.0

# Mapeamento de botões Xbox para teclas equivalentes em menus (Camada A).
# Permite que cenas que já tratam K_RETURN/K_ESCAPE/K_P/setas ganhem suporte
# a controle sem mudança no handle_event delas.
_BUTTON_TO_KEY = {
    XboxButton.A: pygame.K_RETURN,
    XboxButton.B: pygame.K_ESCAPE,
    XboxButton.BACK: pygame.K_ESCAPE,
    XboxButton.START: pygame.K_p,
}


class GameApp:
    def __init__(self):
        # Melhor qualidade/latência para o mixer antes do pygame.init().
        # No web (WASM) o jogo é CPU-bound (~30fps): um frame cheio segura a
        # thread principal por ~33ms, mais que os 23ms de um buffer de 1024
        # samples → o áudio estoura (picote). Buffer maior no web dá folga pra
        # sobreviver a frames longos (custa ~latência, tolerável p/ música).
        import sys as _sys

        _mixer_buffer = 4096 if _sys.platform == "emscripten" else 1024
        pygame.mixer.pre_init(44100, -16, 2, _mixer_buffer)
        pygame.init()

        # EventBus central para comunicação desacoplada
        self.event_bus = EventBus()

        # Carregar preferências de sistema (vídeo, áudio, controles)
        prefs_path = get_preferences_path()
        self.preferences = UserPreferences(prefs_path)

        # Aplica a qualidade visual escolhida ao singleton global no boot, antes
        # de qualquer sistema de efeitos consultar os multiplicadores.
        from .core.visual_quality import visual_quality

        visual_quality.set_from_name(self.preferences.visual_quality)
        visual_quality.set_pixelization(self.preferences.pixelization)
        visual_quality.set_lowres_background(self.preferences.retro_background)
        visual_quality.set_ui_animations(self.preferences.ui_animations)

        # Idioma da interface aplicado ao singleton i18n no boot, ANTES de
        # qualquer cena montar textos (botões pré-renderizam glifos). Vazio →
        # cai no idioma base; a escolha real acontece na tela de seleção.
        from .core.i18n import i18n

        i18n.set_language(self.preferences.language or "pt")

        # Pós-processamento de frame inteiro (pixelização), aplicado no único
        # choke point de render, antes do flip. Reutiliza buffer entre frames.
        from .render.post_process import PixelizePost

        self._pixelize_post = PixelizePost()

        base_width, base_height = self.preferences.resolution

        # Carregar perfil de progressão
        self.player_profile = PlayerProfile(get_profile_path())

        # Garantir proporção 16:9 se necessário
        target_ratio = 16 / 9
        current_ratio = base_width / base_height
        if abs(current_ratio - target_ratio) > 0.1:
            base_height = int(base_width / target_ratio)

        # Garante que a configuração global use a resolução detectada.
        set_screen_resolution(base_width, base_height)

        # Sincronizar volumes do SoundManager com as preferências
        from .core.sound import sound_manager

        sound_manager.load_config(
            self.preferences.music_volume,
            self.preferences.sfx_volume,
            self.preferences.shot_volume,
        )

        # Define as flags da tela.
        import sys

        flags = 0
        if sys.platform == "emscripten":
            # Web: o jogo roda no canvas da página. NÃO forçar fullscreen (só via
            # gesto do usuário) e NÃO usar SCALED — o canvas do pygbag já escala
            # pro tamanho de exibição, e o SCALED do pygame por cima desalinha a
            # posição do mouse (hit-test) quando a janela é redimensionada.
            pass
        else:
            if self.preferences.fullscreen:
                flags |= pygame.FULLSCREEN
            flags |= pygame.SCALED

        self.screen = pygame.display.set_mode((base_width, base_height), flags)
        self.screen_width = base_width
        self.screen_height = base_height

        load_custom_cursor()

        # Registrar sprites para pré-carregamento
        from .core.sprite_loader import sprite_loader
        from .entities.bosses.mountain_serpent_boss import MountainSerpentBoss, SerpentBlock
        from .entities.bosses.slime_boss import SlimeBoss
        from .entities.enemies.space.satellite import Satellite

        sprite_loader.register("slime_boss", SlimeBoss.load_frames_for_preload)
        sprite_loader.register(
            "mountain_serpent_boss", MountainSerpentBoss.load_frames_for_preload
        )
        sprite_loader.register("serpent_block", SerpentBlock.load_frames_for_preload)
        sprite_loader.register("Satellite", Satellite.load_animation_frames)
        # No desktop carrega tudo aqui (síncrono). No web (emscripten) o
        # carregamento é feito de forma cooperativa pelo entrypoint, via
        # GameApp.preload(), para não congelar o navegador (tela de loading).
        import sys

        if sys.platform != "emscripten":
            sprite_loader.load_all()

        pygame.display.set_caption("Pixel Patrol")
        self.clock = pygame.time.Clock()
        self.running = True

        self.states: StateManager = StateManager()
        self.level_manager = LevelManager(FIXED_LEVELS)
        self.input: Input = Input()

        # Instanciar sistemas que ouvem o EventBus
        self.sound_system = SoundSystem(self.event_bus)
        # O EffectsSystem será criado na PlayingScene, pois depende do EntityManager.

        # Suporte a controle Xbox: singleton compartilhado com a Input e cenas.
        self.gamepad: GamepadManager = GamepadManager()
        self.gamepad.init(prefer_slot_1=self.preferences.p1_prefers_keyboard)
        # Auto-ativação do gamepad: liga sozinho quando há controle conectado e o
        # usuário nunca fez uma escolha explícita (checkbox nunca tocado). Isto
        # substitui o antigo gate por `is_first_run`, que perdia a corrida de
        # enumeração do SDL — o controle costuma chegar via JOYDEVICEADDED alguns
        # frames APÓS o init, quando a checagem inicial já passou, deixando o
        # checkbox desmarcado mesmo com controle presente. `_maybe_autoenable_gamepad`
        # é reexecutado no hot-plug (ver `run`), cobrindo qualquer timing. Feita a
        # escolha, ela é sempre respeitada.
        self._maybe_autoenable_gamepad()
        self.gamepad.set_enabled(self.preferences.gamepad_enabled)

        if self.gamepad.connected:
            if self.gamepad.is_active:
                logger.info("Controle pronto para uso.")
            else:
                logger.info(
                    "Controle detectado mas desativado — ligue em Settings → Controle Xbox."
                )
        else:
            logger.info("Nenhum controle detectado no startup.")

        # Cursor virtual movido pelo stick direito em cenas não-gameplay.
        self._virtual_cursor_x: float = base_width / 2
        self._virtual_cursor_y: float = base_height / 2

        # Auto-hide do cursor: DPad/LB/RB/teclado escondem; mouse/stick mostram.
        # Sem isso, focus navigation por DPad coexistia com cursor visível e
        # criava o conflito ``mira aponta em A, focus está em B``.
        self._cursor_navigation_mode: str = "cursor"  # ``cursor`` ou ``focus``
        # Posições para onde o JOGO moveu o ponteiro (ver `warp_cursor`): o eco
        # em MOUSEMOTION delas não conta como "o usuário mexeu no mouse".
        self._warp_targets: list[tuple[int, int]] = []
        # Última cena para a qual a visibilidade do ponteiro foi reaplicada.
        self._cursor_synced_scene: Optional[Scene] = None

        from .render.renderer import Renderer

        self.renderer = Renderer()

        # Fade global de troca de tela. Fonte única — nenhuma cena desenha o
        # próprio fade de navegação; todas pedem por `go_to`/`go_back`.
        from .core.scene_transition import SceneTransition

        self.transition = SceneTransition()

        self.selected_difficulty = DifficultyPreset.NORMAL

        # 1º boot (idioma ainda não escolhido) → tela de seleção de idioma, que
        # ao confirmar troca para o menu. Depois disso, vai direto ao menu.
        if self.preferences.language in ("pt", "en"):
            self.states.push(MainMenuScene(self))
        else:
            from .scenes.language_selection import LanguageSelectionScene

            self.states.push(LanguageSelectionScene(self))

    # ------------------------------------------------------------------
    # Navegação entre cenas (único caminho — não chamar states.* direto)
    # ------------------------------------------------------------------

    def go_to(
        self,
        factory: "Callable[[], Scene]",
        *,
        push: bool = False,
        style: "TransitionStyle | None" = None,
        fade_out: bool = True,
        fade_in: bool = True,
        duration: Optional[float] = None,
    ) -> bool:
        """Navega para uma cena nova, encoberto pelo fade global.

        `factory` é uma **fábrica**, não uma cena pronta: a construção acontece
        no pico do fade (tela preta), não no clique. Além de manter a semântica
        de "só existe a partir daqui", isso esconde o custo de montar cenas
        caras (a `PlayingScene` carrega nível, sprites e sistemas) atrás do
        preto, em vez de travar um frame com a tela ainda visível.

        `push` empilha (a cena de baixo continua viva, para voltar com
        `go_back`); o padrão substitui. Devolve False se outra transição já
        estava em curso — ver `SceneTransition.request`.
        """
        from .core.scene_transition import TransitionStyle

        def _apply() -> None:
            scene = factory()
            if push:
                self.states.push(scene)
            else:
                self.states.switch(scene)

        return self.transition.request(
            _apply,
            style=style or TransitionStyle.BLACK,
            fade_out=fade_out,
            fade_in=fade_in,
            duration=duration,
        )

    def go_back(
        self,
        *,
        style: "TransitionStyle | None" = None,
        fade_out: bool = True,
        fade_in: bool = True,
        duration: Optional[float] = None,
    ) -> bool:
        """Desempilha a cena atual (voltar), encoberto pelo fade global."""
        from .core.scene_transition import TransitionStyle

        return self.transition.request(
            self.states.pop,
            style=style or TransitionStyle.BLACK,
            fade_out=fade_out,
            fade_in=fade_in,
            duration=duration,
        )

    def open_overlay(self, factory: "Callable[[], Scene]") -> bool:
        """Empilha uma cena que **continua mostrando** a de baixo (pausa).

        Estilo DIM (sem véu preto — piscar para abrir a pausa é pior que o
        corte que estamos removendo) e **só a metade de entrada**: não há o que
        despedir, a cena de baixo segue na tela. A que entra anima a própria
        escurecida lendo `app.transition.overlay_progress`.
        """
        from .core.scene_transition import TransitionStyle

        return self.go_to(
            factory, push=True, style=TransitionStyle.DIM, fade_out=False
        )

    def close_overlay(self) -> bool:
        """Fecha uma cena aberta por `open_overlay` (sem véu preto).

        Espelho do `open_overlay`: **só a metade de saída**. A cena do topo
        desaparece animada (`overlay_progress` caindo 1→0) e só é desempilhada
        no FIM — é isso que faz o jogo voltar ao normal depois da animação, não
        antes. A cena de baixo não "entra": nunca saiu da tela.
        """
        from .core.scene_transition import TransitionStyle

        return self.go_back(style=TransitionStyle.DIM, fade_in=False)

    # ------------------------------------------------------------------
    # Suporte a controle (eventos sintéticos para cenas não-gameplay)
    # ------------------------------------------------------------------

    def _scene_is_gameplay(self, scene: Scene) -> bool:
        """True se a cena trata eventos JOY nativamente (gameplay). Cenas de
        gameplay devem definir o atributo de classe ``is_gameplay_scene``."""
        return bool(getattr(scene, "is_gameplay_scene", False))

    def _any_gamepad_active(self) -> bool:
        """True quando pelo menos um controle ativo está disponível."""
        return any(
            self.gamepad.is_slot_active(slot) for slot in range(MAX_GAMEPAD_SLOTS)
        )

    def _maybe_autoenable_gamepad(self) -> None:
        """Liga o gamepad automaticamente ao detectar um controle, desde que o
        usuário ainda não tenha feito uma escolha explícita.

        Chamado no boot e a cada `JOYDEVICEADDED` (hot-plug). Cobre a corrida de
        enumeração do SDL: se o controle só é reconhecido alguns frames após o
        init, o auto-ativar do boot é reexecutado quando ele de fato conecta —
        marcando o checkbox sem exigir ação manual. Assim que o usuário marca ou
        desmarca o toggle (`gamepad_choice_made`), nunca sobrescrevemos a escolha.
        """
        if self.preferences.gamepad_choice_made:
            return
        if not self.gamepad.connected or self.preferences.gamepad_enabled:
            return
        # Pelo setter: ligar o controle desliga o `mouse_control` (a nave não
        # pode ter duas fontes de movimento). Vale também aqui, no auto-ligar —
        # atribuir o campo direto deixaria o hot-plug fora da regra.
        self.preferences.set_gamepad_enabled(True)
        self.input.mouse_control = self.preferences.mouse_control
        self.preferences.save()
        logger.info("Controle detectado — gamepad ativado automaticamente.")

    @property
    def cursor_navigation_mode(self) -> str:
        """``cursor`` (mouse manda) ou ``focus`` (DPad/teclado/analógico mandam).

        Leitura pública: as cenas precisam saber se podem deixar o hover do
        mouse mexer na seleção, e liam o `_cursor_navigation_mode` privado —
        acesso a privado entre objetos que o §1 proíbe.
        """
        return self._cursor_navigation_mode

    def set_cursor_mode(self, mode: str) -> None:
        """API pública do modo de navegação (ver `_set_cursor_mode`).

        Cenas com navegação por foco próprio (`owns_gamepad_navigation`) chamam
        `set_cursor_mode("focus")` quando o controle move o foco: sem isso o
        modo continua em ``cursor`` — o app só troca sozinho no D-pad e no
        LB/RB, e o analógico dessas cenas não passa por evento nenhum — e o
        hover do mouse, parado onde o jogador o deixou, rouba de volta a
        seleção a cada frame.
        """
        self._set_cursor_mode(mode)

    def _set_cursor_mode(self, mode: str) -> None:
        """Alterna entre ``cursor`` (mouse/stick) e ``focus`` (DPad/teclado).

        Em modo focus o ponteiro do mouse fica oculto — evita o conflito
        visual ``a mira aponta em A mas o focus está em B``. Cenas de
        gameplay são imunes (mantêm a própria política via set_visible).
        """
        if mode == self._cursor_navigation_mode:
            return
        self._cursor_navigation_mode = mode
        current = self.states.current()
        if current is not None and self._scene_is_gameplay(current):
            return
        try:
            pygame.mouse.set_visible(mode == "cursor")
        except pygame.error:
            pass

    def _sync_cursor_visibility(self, scene: Optional[Scene]) -> None:
        """Reaplica no ponteiro a visibilidade que o MODO atual pede.

        Roda a cada troca de cena. Existe porque `_set_cursor_mode` só chama
        `set_visible` quando o modo MUDA: bastava uma cena forçar
        `set_visible(True)` no `enter()` para o estado real passar a contradizer
        o modo — o jogador navegando no controle (modo focus) via o ponteiro na
        tela, e apertar LB/RB de novo não o escondia, porque para o app nada
        havia mudado. Mesmo tipo de defeito do §18: o campo certo, o recurso
        aplicado errado.

        Cena de gameplay é pulada — ela tem política própria (esconde sempre).
        """
        if scene is None or self._scene_is_gameplay(scene):
            return
        try:
            pygame.mouse.set_visible(self._cursor_navigation_mode == "cursor")
        except pygame.error:
            pass

    def warp_cursor(self, pos: tuple[int, int]) -> bool:
        """Move o PONTEIRO em nome da navegação por controle/teclado.

        Use isto, e não `pygame.mouse.set_pos`, em qualquer tela que reposiciona
        a mira por causa de um input discreto (LB/RB, D-pad, setas). O `set_pos`
        emite um `MOUSEMOTION` que o `_track_input_mode` não tem como distinguir
        de um movimento humano: ele devolvia o modo para ``cursor`` e o ponteiro
        **reaparecia no meio da navegação por controle** — o defeito era visível
        na seleção de dificuldade (LB/RB) e valia para toda tela que faz isso.

        A posição de destino fica registrada; o `MOUSEMOTION` que chegar
        exatamente nela é consumido como sintético. Casar por POSIÇÃO (e não uma
        flag de "próximo evento") é o que sobrevive a dois warps seguidos e ao
        warp que não gera evento nenhum — qualquer movimento real limpa a lista.
        """
        try:
            pygame.mouse.set_pos(pos)
        except pygame.error:
            return False
        alvo = (int(pos[0]), int(pos[1]))
        self._warp_targets.append(alvo)
        # Teto pequeno: warps pendentes não se acumulam entre frames.
        if len(self._warp_targets) > 4:
            del self._warp_targets[0]
        return True

    def _consume_warp_motion(self, pos: tuple[int, int]) -> bool:
        """True se este `MOUSEMOTION` é o eco de um `warp_cursor`.

        Casa com folga de `_WARP_MATCH_TOLERANCE` px: com `pygame.SCALED` a
        posição faz um ida-e-volta lógico→físico→lógico, e em fator de escala
        não inteiro (576p numa tela 1080p) ela pode voltar 1px deslocada. Exigir
        igualdade exata deixaria justamente essas resoluções sem proteção.
        """
        x, y = int(pos[0]), int(pos[1])
        for i, (ax, ay) in enumerate(self._warp_targets):
            if (
                abs(ax - x) <= _WARP_MATCH_TOLERANCE
                and abs(ay - y) <= _WARP_MATCH_TOLERANCE
            ):
                del self._warp_targets[i]
                return True
        self._warp_targets.clear()
        return False

    def _track_input_mode(self, event: pygame.event.Event) -> None:
        """Inspeciona cada evento pra decidir se o usuário está em modo
        cursor (mira livre) ou focus (navegação discreta).

        Discreto → focus → esconde cursor: DPad, LB/RB, KEYDOWN de setas/Tab.
        Contínuo → cursor → mostra cursor: MOUSEMOTION com movimento real.
        Stick analógico também ativa cursor (ele move o ponteiro).
        """
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if x or y:
                self._set_cursor_mode("focus")
        elif event.type == pygame.JOYBUTTONDOWN:
            from .core.gamepad import XboxButton

            if event.button in (XboxButton.LB, XboxButton.RB):
                self._set_cursor_mode("focus")
        elif event.type == pygame.KEYDOWN:
            nav_keys = (
                pygame.K_UP,
                pygame.K_DOWN,
                pygame.K_LEFT,
                pygame.K_RIGHT,
                pygame.K_TAB,
            )
            if event.key in nav_keys:
                self._set_cursor_mode("focus")
        elif event.type == pygame.MOUSEMOTION:
            # Só movimento REAL do mouse devolve o controle ao cursor. O
            # ponteiro também é movido pelo próprio jogo quando o controle
            # navega (`warp_cursor`), e o `set_pos` gera um MOUSEMOTION
            # indistinguível do humano — foi ele que fazia o cursor reaparecer
            # no meio de uma navegação por LB/RB.
            if self._consume_warp_motion(event.pos):
                return
            self._set_cursor_mode("cursor")

    def _synthesize_menu_events(self, event: pygame.event.Event, scene: Scene) -> None:
        """Despacha eventos sintéticos KEYDOWN equivalentes ao apertar botões
        Xbox em menus (Camada A do plano de gamepad).

        Em gameplay esta tradução é pulada — a PlayingScene processa os
        eventos JOY diretamente para preservar semântica (botão A = tiro etc).
        Cenas com `owns_gamepad_navigation` também são puladas: elas tratam o
        DPad/analógico/botões nativamente (foco próprio), sem cursor virtual.
        """
        if (
            not self._any_gamepad_active()
            or self._scene_is_gameplay(scene)
            or getattr(scene, "owns_gamepad_navigation", False)
        ):
            return

        if event.type == pygame.JOYBUTTONDOWN:
            key = _BUTTON_TO_KEY.get(event.button)
            if key is not None:
                synthetic = pygame.event.Event(
                    pygame.KEYDOWN, {"key": key, "mod": 0, "unicode": ""}
                )
                scene.handle_event(synthetic)

        elif event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if not (x or y):
                return

            # Tab-style navigation: se a cena expõe rects clicáveis, o DPad
            # pula o cursor pro elemento mais próximo na direção apertada.
            # Sem rects (cenas como main_menu que usam ``focused_button_index``
            # próprio), cai no fallback de sintetizar setas — preserva fluxo.
            if self._snap_focus_to_direction(scene, x, -y):
                return

            # Ordem importa: trata cada eixo independente para diagonais.
            if x < 0:
                scene.handle_event(
                    pygame.event.Event(
                        pygame.KEYDOWN,
                        {"key": pygame.K_LEFT, "mod": 0, "unicode": ""},
                    )
                )
            elif x > 0:
                scene.handle_event(
                    pygame.event.Event(
                        pygame.KEYDOWN,
                        {"key": pygame.K_RIGHT, "mod": 0, "unicode": ""},
                    )
                )
            if y > 0:
                scene.handle_event(
                    pygame.event.Event(
                        pygame.KEYDOWN,
                        {"key": pygame.K_UP, "mod": 0, "unicode": ""},
                    )
                )
            elif y < 0:
                scene.handle_event(
                    pygame.event.Event(
                        pygame.KEYDOWN,
                        {"key": pygame.K_DOWN, "mod": 0, "unicode": ""},
                    )
                )

    def _handle_tab_navigation(self, event: pygame.event.Event, scene: Scene) -> bool:
        """TAB / Shift+TAB percorrem os elementos focáveis da cena.

        Um lugar só para o jogo inteiro: quase toda tela já publica
        `get_focusable_rects()` (era o que o snap-focus do D-pad consumia), e o
        TAB percorre essa MESMA lista, na ordem em que a cena a declarou. Assim
        o teclado ganha a navegação sem que cada tela precise implementar a sua.

        Pulamos gameplay (TAB não navega no meio de uma partida) e cenas com
        foco próprio (`owns_gamepad_navigation`): lá o TAB é tratado pela
        própria cena, que tem um índice de foco em vez de um cursor.
        """
        if event.type != pygame.KEYDOWN or event.key != pygame.K_TAB:
            return False
        if self._scene_is_gameplay(scene) or getattr(
            scene, "owns_gamepad_navigation", False
        ):
            return False
        try:
            rects = scene.get_focusable_rects()
        except (AttributeError, NotImplementedError):
            return False
        if not rects:
            return False

        passo = -1 if (event.mod & pygame.KMOD_SHIFT) else 1
        cursor = pygame.mouse.get_pos()
        atual = next(
            (i for i, r in enumerate(rects) if r.collidepoint(cursor)), None
        )
        # Sem cursor sobre nada (entrou na tela agora), TAB começa do primeiro e
        # Shift+TAB do último — o comportamento que todo formulário tem.
        alvo = rects[0] if passo > 0 else rects[-1]
        if atual is not None:
            alvo = rects[(atual + passo) % len(rects)]
        return self._focus_rect(scene, alvo)

    def _handle_arrow_navigation(
        self, event: pygame.event.Event, scene: Scene
    ) -> bool:
        """Setas movem a mira entre os focáveis, nas telas que pedem (§19).

        Mesma busca geométrica do D-pad (`_snap_focus_to_direction`): seta é
        direção, e numa tela em grade (cards de dificuldade, cartões de
        Configurações) "o de cima" é o que está por cima na tela, não o
        anterior na lista — que é o serviço do TAB.

        Só age em cena que declara `arrow_keys_navigate_focus`. As demais usam
        as setas para o que é delas (iniciais do game over, abas, rolagem).
        """
        if event.type != pygame.KEYDOWN:
            return False
        direcao = _ARROW_DIRECTIONS.get(event.key)
        if direcao is None:
            return False
        if self._scene_is_gameplay(scene):
            return False
        modo = getattr(scene, "arrow_keys_navigate_focus", False)
        if not modo:
            return False
        # "vertical": a cena reservou o eixo horizontal para si (ver `Scene`).
        if modo == "vertical" and direcao[0] != 0:
            return False
        return self._snap_focus_to_direction(scene, *direcao)

    def _focus_rect(self, scene: Scene, rect: pygame.Rect) -> bool:
        """Leva a mira ao centro de ``rect`` e avisa a cena, em modo focus.

        Caminho comum do snap por D-pad e do TAB: mover pelo `warp_cursor` (o
        eco não pode reacender o ponteiro) e entregar à cena um MOUSEMOTION
        sintético, que é como as telas de cursor atualizam o hover.
        """
        cursor_x, cursor_y = pygame.mouse.get_pos()
        new_x = max(0, min(self.screen_width - 1, rect.centerx))
        new_y = max(0, min(self.screen_height - 1, rect.centery))
        if not self.warp_cursor((new_x, new_y)):
            return False
        self._set_cursor_mode("focus")
        self._virtual_cursor_x = float(new_x)
        self._virtual_cursor_y = float(new_y)
        scene.handle_event(
            pygame.event.Event(
                pygame.MOUSEMOTION,
                {
                    "pos": (new_x, new_y),
                    "rel": (new_x - cursor_x, new_y - cursor_y),
                    "buttons": (0, 0, 0),
                },
            )
        )
        return True

    def _snap_focus_to_direction(self, scene: Scene, dx: int, dy: int) -> bool:
        """Move o cursor para o rect focusable mais próximo na direção (dx, dy).

        Convenção de eixos: dx +1 = direita, dy +1 = baixo (pygame screen).
        ``dy`` chega já invertido do hat (hat y +1 = cima vira dy -1 = cima).

        Retorna True se houve snap (cena tinha rects e achou um candidato),
        False se a cena não implementou ``get_focusable_rects`` ou nenhum
        rect serve para a direção dada. Em caso False, o caller sintetiza
        setas como fallback.
        """
        try:
            rects = scene.get_focusable_rects()
        except (AttributeError, NotImplementedError):
            return False
        if not rects:
            return False

        cursor_x, cursor_y = pygame.mouse.get_pos()
        best_rect: pygame.Rect | None = None
        best_score = float("inf")

        for rect in rects:
            # Se o cursor já está dentro do rect, ele não conta como
            # destino válido — DPad sempre move para "outro" elemento.
            if rect.collidepoint(cursor_x, cursor_y):
                continue
            tx, ty = rect.centerx, rect.centery
            vx, vy = tx - cursor_x, ty - cursor_y

            # Projeção na direção desejada. Negativo = atrás do cursor;
            # rect descartado nesse eixo. Cardinais (dx=0 ou dy=0) aceitam
            # qualquer rect cujo deslocamento principal seja positivo.
            if dx != 0 and vx * dx <= 0:
                continue
            if dy != 0 and vy * dy <= 0:
                continue

            # Score = distância na direção principal + penalidade pelo
            # desvio lateral. Penalidade 2× incentiva escolhas alinhadas
            # com o eixo apertado em vez de ``pular`` diagonalmente.
            if dx != 0 and dy == 0:
                primary = abs(vx)
                lateral = abs(vy)
            elif dy != 0 and dx == 0:
                primary = abs(vy)
                lateral = abs(vx)
            else:
                # Diagonal: usa distância euclidiana com viés direcional.
                primary = abs(vx) + abs(vy)
                lateral = 0
            score = primary + lateral * 2.0
            if score < best_score:
                best_score = score
                best_rect = rect

        if best_rect is None:
            return False
        # Mesmo caminho do TAB (`_focus_rect`): warp registrado + MOUSEMOTION
        # sintético para a cena atualizar o hover no mesmo frame.
        return self._focus_rect(scene, best_rect)

    def _draw_rotate_hint(self) -> None:
        """Faixa pedindo para girar o aparelho, quando a tela está em retrato.

        Faixa e não tela cheia de propósito: o jogo continua rodando e visível
        por baixo. Um bloqueio modal aqui seria pior — se a detecção errar (é
        uma API do navegador que não controlamos, ver `orientation`), um véu
        opaco tornaria o jogo INJOGÁVEL por causa de um palpite errado, enquanto
        uma faixa apenas incomoda.
        """
        from .core.orientation import is_portrait

        if not is_portrait():
            return

        from .core.assets import get_font
        from .core.i18n import t

        w, h = self.screen.get_size()
        band_h = max(28, h // 8)
        band = pygame.Surface((w, band_h), pygame.SRCALPHA)
        band.fill((0, 0, 0, 210))
        self.screen.blit(band, (0, (h - band_h) // 2))

        font = get_font(max(10, int(w / 36)))
        text = font.render(t("web.rotate_device"), True, (255, 255, 255))
        self.screen.blit(text, text.get_rect(center=(w // 2, h // 2)))

    def _update_virtual_cursor(self, dt: float, scene: Scene) -> None:
        """Move o cursor virtual pelos sticks analógicos e dispara MOUSEMOTION
        sintéticos para que cenas só-mouse (settings, paused, etc) reajam
        ao hover. Só ativo fora de gameplay.

        RS e LS de qualquer slot ativo funcionam simultaneamente — pega o
        stick com maior magnitude.
        Em gameplay esta função retorna cedo; o LS continua livre para
        mover a nave (PlayingScene lê LS direto via input.gamepad_movement_vector).
        Cenas com `owns_gamepad_navigation` também: o analógico move o FOCO
        discreto delas, não o cursor (ver UpgradesSelectionScene).
        """
        if (
            not self._any_gamepad_active()
            or self._scene_is_gameplay(scene)
            or getattr(scene, "owns_gamepad_navigation", False)
        ):
            return

        # Dead zone customizada com reescala linear: sem isso, drift mecânico
        # do stick (>0.18 padrão) empurraria o cursor lentamente para uma
        # borda mesmo com o usuário sem tocar no controle.
        rx, ry = 0.0, 0.0
        best_mag_sq = 0.0
        for slot in range(MAX_GAMEPAD_SLOTS):
            if not self.gamepad.is_slot_active(slot):
                continue
            for side in ("right", "left"):
                sx, sy = self.gamepad.get_stick_rescaled(
                    side, _VIRTUAL_CURSOR_DEAD_ZONE, slot=slot
                )
                mag_sq = (sx * sx) + (sy * sy)
                if mag_sq > best_mag_sq:
                    best_mag_sq = mag_sq
                    rx, ry = sx, sy

        # Sincroniza o cursor virtual com a posição real do mouse a cada
        # frame. Sem isso, ao entrar numa cena nova (e.g. pausa após
        # gameplay) o estado interno ficava preso no último valor escrito
        # pelo stick, fazendo a próxima leve inclinação ``teleportar`` o
        # cursor para a posição antiga (frequentemente perto do topo).
        actual_x, actual_y = pygame.mouse.get_pos()
        self._virtual_cursor_x = float(actual_x)
        self._virtual_cursor_y = float(actual_y)

        if rx == 0.0 and ry == 0.0:
            return

        # Stick ativo → modo cursor (controle livre da mira). Sem isso, depois
        # de navegar via DPad o stick ficaria movendo um cursor invisível.
        self._set_cursor_mode("cursor")

        # dt cap evita saltos grandes após frames lentos (carregamento de
        # cena, GC longo) — sem isso o cursor pulava direto pra borda
        # superior se ry fosse negativo no primeiro frame pós-transição.
        capped_dt = min(dt, _VIRTUAL_CURSOR_MAX_DT)

        prev_x, prev_y = self._virtual_cursor_x, self._virtual_cursor_y
        self._virtual_cursor_x = max(
            0.0,
            min(
                float(self.screen_width - 1),
                prev_x + rx * _VIRTUAL_CURSOR_SPEED * capped_dt,
            ),
        )
        self._virtual_cursor_y = max(
            0.0,
            min(
                float(self.screen_height - 1),
                prev_y + ry * _VIRTUAL_CURSOR_SPEED * capped_dt,
            ),
        )

        new_x = int(self._virtual_cursor_x)
        new_y = int(self._virtual_cursor_y)
        if new_x != actual_x or new_y != actual_y:
            try:
                pygame.mouse.set_pos((new_x, new_y))
            except pygame.error:
                pass
            motion = pygame.event.Event(
                pygame.MOUSEMOTION,
                {
                    "pos": (new_x, new_y),
                    "rel": (new_x - actual_x, new_y - actual_y),
                    "buttons": (0, 0, 0),
                },
            )
            scene.handle_event(motion)

    async def preload(self, on_progress=None) -> None:
        """Carrega os sprites cedendo ao event loop, para a tela de loading web.
        No desktop já foram carregados no __init__, então aqui vira no-op."""
        from .core.sprite_loader import sprite_loader

        await sprite_loader.load_all_async(on_progress)

    async def run(self):
        from .core.sound import MUSIC_END_EVENT, sound_manager
        from .core.visual_quality import visual_quality

        try:
            while self.running:
                dt = self.clock.tick(Config.FPS) / 1000.0
                dt = min(dt, _MAX_FRAME_DT)

                current_scene = self.states.current()

                for event in pygame.event.get():
                    # Hot-plug e cache de hat antes de qualquer dispatch.
                    self.gamepad.handle_event(event)
                    # Controle recém-conectado: reexecuta o auto-ativar (cobre a
                    # corrida de enumeração do startup e o hot-plug em jogo).
                    if event.type == pygame.JOYDEVICEADDED:
                        self._maybe_autoenable_gamepad()
                        self.gamepad.set_enabled(self.preferences.gamepad_enabled)
                    # Atualiza modo cursor/focus ANTES do dispatch — assim a
                    # cena já recebe o estado correto se quiser consultar.
                    self._track_input_mode(event)

                    if event.type == pygame.QUIT:
                        self.running = False
                    # Fim de uma faixa de música → avança a rotação data-driven
                    # do tema/boss ativo (rotação contínua e suave).
                    elif event.type == MUSIC_END_EVENT:
                        sound_manager.advance_current()
                    # Removido: ESC global que fechava o jogo
                    # elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    #     self.running = False
                    # Durante o escurecimento a cena já está de saída: entregar
                    # input a ela enfileiraria uma segunda navegação (dois
                    # cliques rápidos = duas telas puladas). QUIT acima segue
                    # valendo, para o jogo sempre poder fechar.
                    elif current_scene and not self.transition.busy:
                        # TAB é do app: percorre os focáveis da cena antes que
                        # ela veja a tecla (nenhuma tela de cursor usa TAB para
                        # outra coisa; as que usam têm foco próprio e são
                        # puladas lá dentro).
                        if self._handle_tab_navigation(event, current_scene):
                            continue
                        # Setas: só nas telas que declaram o opt-in (as outras
                        # já usam as setas para coisa própria).
                        if self._handle_arrow_navigation(event, current_scene):
                            continue
                        current_scene.handle_event(event)
                        # Camada A: traduz eventos JOY em KEYDOWN equivalentes
                        # para cenas que já reagem ao teclado (não-gameplay).
                        self._synthesize_menu_events(event, current_scene)

                # Avança transições de música pendentes (crossfade cooperativo,
                # na thread principal — pygame não é thread-safe).
                sound_manager.update_music(dt)

                # Avança o fade global. A troca de cena acontece DENTRO deste
                # update (no pico do escurecimento), por isso a cena é relida
                # logo abaixo — senão o frame do commit ainda renderizaria a
                # cena antiga, que já saiu da pilha.
                self.transition.update(dt)
                current_scene = self.states.current()

                # Trocou de cena → o ponteiro volta a obedecer ao modo. O
                # `enter()` da cena nova roda antes disto (dentro do commit da
                # transição), então esta é a última palavra.
                if current_scene is not self._cursor_synced_scene:
                    self._cursor_synced_scene = current_scene
                    self._sync_cursor_visibility(current_scene)

                # Camada B: cursor virtual via stick direito (fora de gameplay).
                if current_scene:
                    self._update_virtual_cursor(dt, current_scene)
                    current_scene.update(dt)
                    current_scene.render(self.screen)

                # Véu do fade por cima da cena, antes da pixelização — assim a
                # transição também é pixelizada e não destoa do resto.
                self.transition.draw(self.screen)

                # Pós-processamento: pixeliza o frame inteiro já renderizado
                # (todas as cenas passam por aqui) antes de mostrar na tela.
                if visual_quality.pixelization_enabled:
                    self._pixelize_post.apply(
                        self.screen, visual_quality.pixelization_factor
                    )

                # Aviso de girar o aparelho: DEPOIS da pixelização, porque é
                # instrução de interface e não conteúdo do jogo — pixelizar o
                # texto que pede para girar a tela é justamente o que o deixaria
                # ilegível em quem já está com a tela pequena.
                self._draw_rotate_hint()

                pygame.display.flip()

                # pygbag/web: cede o controle ao event loop do navegador uma
                # vez por frame. No desktop é praticamente um no-op instantâneo.
                await asyncio.sleep(0)
        finally:
            self.sound_system.cleanup()
            sound_manager.shutdown()
            pygame.quit()


def main():
    app = GameApp()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
