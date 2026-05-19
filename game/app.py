import logging

import pygame

from .core.assets import load_custom_cursor
from .core.config import config as Config
from .core.config import set_screen_resolution
from .core.difficulty import DifficultyPreset
from .core.gamepad import GamepadManager, XboxButton
from .core.input import Input
from .core.levels import FIXED_LEVELS, LevelManager
from .core.meta_progression import PlayerProfile
from .core.paths import get_preferences_path, get_profile_path
from .core.preferences import UserPreferences
from .core.state import Scene, StateManager
from .scenes.main_menu import MainMenuScene

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

        sprite_loader.register("slime_boss", SlimeBoss.load_frames_for_preload)
        sprite_loader.register(
            "mountain_serpent_boss", MountainSerpentBoss.load_frames_for_preload
        )
        sprite_loader.register("serpent_block", SerpentBlock.load_frames_for_preload)
        sprite_loader.load_all()

        pygame.display.set_caption("Space Shooter")
        self.clock = pygame.time.Clock()
        self.running = True

        self.states: StateManager = StateManager()
        self.level_manager = LevelManager(FIXED_LEVELS)
        self.input: Input = Input()

        # Suporte a controle Xbox: singleton compartilhado com a Input e cenas.
        self.gamepad: GamepadManager = GamepadManager()
        self.gamepad.init()
        # Primeira execução com controle plugado: ativa por padrão pra evitar
        # que o jogador precise abrir Settings antes de jogar. Sessões
        # posteriores respeitam o toggle (mesmo que ele tenha sido desligado).
        if is_first_run and self.gamepad.connected and not self.preferences.gamepad_enabled:
            self.preferences.gamepad_enabled = True
            self.preferences.save()
            logger.info("Primeira execução com controle conectado — gamepad ativado por padrão.")
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

        from .render.renderer import Renderer

        self.renderer = Renderer()

        self.selected_difficulty = DifficultyPreset.NORMAL
        self.heal_usage_count = 0

        self.states.push(MainMenuScene(self))

    # ------------------------------------------------------------------
    # Suporte a controle (eventos sintéticos para cenas não-gameplay)
    # ------------------------------------------------------------------

    def _scene_is_gameplay(self, scene: Scene) -> bool:
        """True se a cena trata eventos JOY nativamente (gameplay). Cenas de
        gameplay devem definir o atributo de classe ``is_gameplay_scene``."""
        return bool(getattr(scene, "is_gameplay_scene", False))

    def _synthesize_menu_events(
        self, event: pygame.event.Event, scene: Scene
    ) -> None:
        """Despacha eventos sintéticos KEYDOWN equivalentes ao apertar botões
        Xbox em menus (Camada A do plano de gamepad).

        Em gameplay esta tradução é pulada — a PlayingScene processa os
        eventos JOY diretamente para preservar semântica (botão A = tiro etc).
        """
        if not self.gamepad.is_active or self._scene_is_gameplay(scene):
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

    def _snap_focus_to_direction(
        self, scene: Scene, dx: int, dy: int
    ) -> bool:
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
        # Dispara MOUSEMOTION sintético pra cena atualizar hover imediato.
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
        """Move o cursor virtual pelo stick direito e dispara MOUSEMOTION
        sintéticos para que cenas só-mouse (settings, paused, etc) reajam
        ao hover. Só ativo fora de gameplay.

        O stick esquerdo é IGNORADO aqui de propósito — cursor só responde ao
        stick direito (RS) conforme requisito do usuário. Em gameplay esta
        função retorna cedo; o LS continua livre para mover a nave.
        """
        if not self.gamepad.is_active or self._scene_is_gameplay(scene):
            return

        # Usa dead zone customizada com reescala linear: sem isso, drift
        # mecânico do stick (>0.18 padrão) empurraria o cursor lentamente
        # para uma borda mesmo com o usuário sem tocar no controle.
        rx, ry = self.gamepad.get_stick_rescaled("right", _VIRTUAL_CURSOR_DEAD_ZONE)

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
            sound_manager.shutdown()
            pygame.quit()


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
