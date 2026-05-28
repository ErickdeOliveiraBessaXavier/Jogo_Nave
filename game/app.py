import logging

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
        # Melhor qualidade/latência para o mixer antes do pygame.init()
        pygame.mixer.pre_init(44100, -16, 2, 1024)
        pygame.init()

        # EventBus central para comunicação desacoplada
        self.event_bus = EventBus()

        # Carregar preferências de sistema (vídeo, áudio, controles)
        # Detecta se é a primeira execução do jogo ANTES de carregar — útil
        # para decidir auto-ativação de gamepad em quem nunca abriu Settings.
        prefs_path = get_preferences_path()
        is_first_run = not prefs_path.exists()
        self.preferences = UserPreferences(prefs_path)
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
        flags = 0
        if self.preferences.fullscreen:
            flags |= pygame.FULLSCREEN
        flags |= pygame.SCALED

        self.screen = pygame.display.set_mode((base_width, base_height), flags)
        self.screen_width = base_width
        self.screen_height = base_height

        load_custom_cursor()

        # Registrar sprites para pré-carregamento
        from .core.sprite_loader import sprite_loader
        from .entities.mountain_serpent_boss import MountainSerpentBoss, SerpentBlock
        from .entities.slime_boss import SlimeBoss
        from .entities.satellite import Satellite

        sprite_loader.register("slime_boss", SlimeBoss.load_frames_for_preload)
        sprite_loader.register(
            "mountain_serpent_boss", MountainSerpentBoss.load_frames_for_preload
        )
        sprite_loader.register("serpent_block", SerpentBlock.load_frames_for_preload)
        sprite_loader.register("Satellite", Satellite.load_animation_frames)
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
        # Primeira execução com controle plugado: ativa por padrão pra evitar
        # que o jogador precise abrir Settings antes de jogar. Sessões
        # posteriores respeitam o toggle (mesmo que ele tenha sido desligado).
        if (
            is_first_run
            and self.gamepad.connected
            and not self.preferences.gamepad_enabled
        ):
            self.preferences.gamepad_enabled = True
            self.preferences.save()
            logger.info(
                "Primeira execução com controle conectado — gamepad ativado por padrão."
            )
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

        from .render.renderer import Renderer

        self.renderer = Renderer()

        self.selected_difficulty = DifficultyPreset.NORMAL

        self.states.push(MainMenuScene(self))

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
            # Ignora MOUSEMOTION sintético do próprio snap-focus — ele tem
            # ``rel`` calculado, mas o sintético do snap também. Diferenciar
            # via mode atual: se acabamos de entrar em focus, o sintético
            # que sai do _snap_focus_to_direction não deveria reverter.
            # Aqui um movimento ``real`` do mouse tem buttons preenchidos
            # ou pelo menos rel > 0 não-sintético — heurística: ignoramos
            # se ``rel`` for exatamente o esperado pelo snap. Como não dá
            # pra distinguir 100%, simples: qualquer MOUSEMOTION reabilita
            # cursor. Snap só dispara em DPad, então o flick para focus
            # acontece ANTES do MOUSEMOTION sintético — o set_pos posterior
            # gera um motion que reverte. Para evitar isso, marcamos uma
            # flag no snap (vide _snap_focus_to_direction).
            if not getattr(self, "_suppress_next_motion_mode_switch", False):
                self._set_cursor_mode("cursor")
            self._suppress_next_motion_mode_switch = False

    def _synthesize_menu_events(self, event: pygame.event.Event, scene: Scene) -> None:
        """Despacha eventos sintéticos KEYDOWN equivalentes ao apertar botões
        Xbox em menus (Camada A do plano de gamepad).

        Em gameplay esta tradução é pulada — a PlayingScene processa os
        eventos JOY diretamente para preservar semântica (botão A = tiro etc).
        """
        if not self._any_gamepad_active() or self._scene_is_gameplay(scene):
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

        new_x, new_y = best_rect.center
        new_x = max(0, min(self.screen_width - 1, new_x))
        new_y = max(0, min(self.screen_height - 1, new_y))
        try:
            pygame.mouse.set_pos((new_x, new_y))
        except pygame.error:
            return False
        # Atualiza estado do cursor virtual para a sincronização do
        # _update_virtual_cursor não puxar o cursor de volta no frame
        # seguinte (ela lê pygame.mouse.get_pos, então fica coerente).
        self._virtual_cursor_x = float(new_x)
        self._virtual_cursor_y = float(new_y)
        # Marca a flag pro próximo MOUSEMOTION (gerado pelo set_pos acima OU
        # pelo sintético abaixo) não reverter o modo de focus para cursor.
        self._suppress_next_motion_mode_switch = True
        motion = pygame.event.Event(
            pygame.MOUSEMOTION,
            {
                "pos": (new_x, new_y),
                "rel": (new_x - cursor_x, new_y - cursor_y),
                "buttons": (0, 0, 0),
            },
        )
        scene.handle_event(motion)
        return True

    def _update_virtual_cursor(self, dt: float, scene: Scene) -> None:
        """Move o cursor virtual pelos sticks analógicos e dispara MOUSEMOTION
        sintéticos para que cenas só-mouse (settings, paused, etc) reajam
        ao hover. Só ativo fora de gameplay.

        RS e LS de qualquer slot ativo funcionam simultaneamente — pega o
        stick com maior magnitude.
        Em gameplay esta função retorna cedo; o LS continua livre para
        mover a nave (PlayingScene lê LS direto via input.gamepad_movement_vector).
        """
        if not self._any_gamepad_active() or self._scene_is_gameplay(scene):
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

    def run(self):
        from .core.sound import sound_manager

        try:
            while self.running:
                dt = self.clock.tick(Config.FPS) / 1000.0

                current_scene = self.states.current()

                for event in pygame.event.get():
                    # Hot-plug e cache de hat antes de qualquer dispatch.
                    self.gamepad.handle_event(event)
                    # Atualiza modo cursor/focus ANTES do dispatch — assim a
                    # cena já recebe o estado correto se quiser consultar.
                    self._track_input_mode(event)

                    if event.type == pygame.QUIT:
                        self.running = False
                    # Removido: ESC global que fechava o jogo
                    # elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    #     self.running = False
                    elif current_scene:
                        current_scene.handle_event(event)
                        # Camada A: traduz eventos JOY em KEYDOWN equivalentes
                        # para cenas que já reagem ao teclado (não-gameplay).
                        self._synthesize_menu_events(event, current_scene)

                # Camada B: cursor virtual via stick direito (fora de gameplay).
                if current_scene:
                    self._update_virtual_cursor(dt, current_scene)
                    current_scene.update(dt)
                    current_scene.render(self.screen)

                pygame.display.flip()
        finally:
            self.sound_system.cleanup()
            sound_manager.shutdown()
            pygame.quit()


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
