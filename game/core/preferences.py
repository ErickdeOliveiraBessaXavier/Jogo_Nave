import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

from .sound_config import VOLUME_CONFIG

logger = logging.getLogger(__name__)


class UserPreferences:
    """Gerencia as preferências do usuário (sistema, áudio, controles)."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

        # Valores padrão
        self.resolution: Tuple[int, int] = (1280, 720)
        self.fullscreen: bool = True

        # Idioma da interface: "pt" | "en". String vazia = ainda não escolhido
        # → o 1º boot mostra a tela de seleção de idioma.
        self.language: str = ""

        # Qualidade visual: "high" | "medium" | "low" (default: high).
        self.visual_quality: str = "high"

        # Pixelização (pós-processamento): "light" | "medium" | "strong".
        # Sempre ativa (sem "off"); piso nativo = "light".
        self.pixelization: str = "light"

        # Fundo retrô: temas pesados (Mountains/City/Volcanic) renderizados em
        # meia-resolução + upscale — visual pixel-art mais "chunky" e mais leve.
        self.retro_background: bool = True

        # Animações da UI: transições/fades/entradas. False = mudanças
        # instantâneas (opção de desempenho para FPS baixo). No web (WASM) o
        # padrão é DESLIGADO (desempenho); no desktop, ligado. Um valor salvo
        # em disco (load) sobrepõe este padrão.
        import sys as _sys

        self.ui_animations: bool = _sys.platform != "emscripten"

        # Áudio — defaults vindos de VOLUME_CONFIG (fonte única de verdade)
        self.music_volume: float = VOLUME_CONFIG["music"]
        self.sfx_volume: float = VOLUME_CONFIG["sfx"]
        self.shot_volume: float = VOLUME_CONFIG["shots"]

        # Controles
        #
        # No WEB os QUATRO nascem LIGADOS, porque o build web É o build do
        # celular e lá nenhum deles é opcional:
        #   - `mouse_control`/`virtual_joystick`: sem um dos dois a nave não sai
        #     do lugar — teclado não existe;
        #   - `auto_fire`: manter um botão apertado ocuparia o único ponteiro,
        #     que é o mesmo que pilota;
        #   - `touch_mode`: alvos tocáveis no HUD (coluna de upgrades, pausa,
        #     girar). Sem ele, upgrades e pausa ficam inalcançáveis.
        #
        # Nascer desligado significava abrir Configurações ANTES de conseguir
        # jogar — e quem chega por um link não faz isso, fecha a aba.
        #
        # Como preferência não persiste no web (`save` é no-op em emscripten,
        # MEMFS volátil), "padrão" e "sempre ligado" são a mesma coisa na
        # prática: toda sessão recomeça daqui. Continuam sendo DEFAULT e não
        # trava — os toggles seguem lá para quem abrir a build web num
        # navegador de PC e preferir mouse e gatilho.
        _web = _sys.platform == "emscripten"
        # `mouse_control` fica DESMARCADO no web: quem move a nave no celular e o
        # joystick. Os dois marcados era redundancia com um anulando o outro — a
        # `PlayingScene` desliga o `mouse_control` enquanto o joystick existe,
        # entao a caixa aparecia marcada descrevendo algo que nao acontecia.
        #
        # Continua na tela e continua funcionando: quem desmarcar o joystick
        # marca este e recupera a mira por ponteiro. O que ele nao e mais e
        # reserva automatica — desligar o joystick deixa a nave parada ate a
        # troca ser feita, e isso e explicito em vez de silencioso.
        self.mouse_control: bool = False
        self.auto_fire: bool = _web
        # MODO TOQUE (celular): a nave voa ACIMA do ponteiro (o dedo é uma
        # mancha de ~1cm e cobre a nave inteira) e o HUD ganha alvos tocáveis,
        # saindo de baixo do polegar que pilota. É um interruptor só porque
        # para o jogador é uma decisão só — "estou no celular".
        self.touch_mode: bool = _web
        # JOYSTICK VIRTUAL: direcional analógico no canto inferior esquerdo, no
        # lugar da mira absoluta do `mouse_control`.
        #
        # Resolve pela raiz o que o offset do modo toque remenda: com o polegar
        # ancorado num canto, a nave nunca fica debaixo da mão. Por isso os dois
        # são mutuamente exclusivos — ligado o joystick, o offset nem chega a
        # rodar (ele só existe no caminho do `mouse_control`, que o joystick
        # desliga em `PlayingScene`).
        self.virtual_joystick: bool = _web
        self.show_controls_modal: bool = True
        # False até o modal de controles fechar pela 1ª vez. Enquanto False, o
        # modal roda em modo "onboarding": esconde o checkbox "não mostrar mais"
        # (para o novato não matar a própria descoberta por reflexo) e destaca os
        # ajustes de controle. Uma vez True, o modal volta ao comportamento normal.
        self.controls_modal_seen: bool = False
        self.gamepad_enabled: bool = False
        # True depois que o usuário marca/desmarca o checkbox do controle na
        # tela de opções. Enquanto False, o jogo pode LIGAR o gamepad sozinho
        # quando um controle é detectado (inclusive por hot-plug, cobrindo a
        # corrida de enumeração do SDL no startup). Uma vez feita a escolha,
        # a preferência do usuário nunca é sobrescrita automaticamente.
        self.gamepad_choice_made: bool = False
        # Multiplayer local: roteamento de gamepads recém-conectados.
        # Quando `p1_prefers_keyboard=True`, gamepads novos vão pro slot 1 (P2)
        # mesmo que o slot 0 esteja vazio — P1 fica forçado ao teclado.
        # Quando `p2_coop_enabled=False`, qualquer gamepad vai pro slot 0;
        # P2 não pode se juntar via 2º controle.
        self.p1_prefers_keyboard: bool = False
        self.p2_coop_enabled: bool = True

        self.load()

    def load(self):
        """Carrega preferências do disco."""
        if not self.file_path.exists():
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

                if not isinstance(raw_data, dict):
                    return

                data = cast(Dict[str, Any], raw_data)

                # Resolução
                res = data.get("resolution")
                if isinstance(res, list):
                    res_list = cast(List[Any], res)
                    if len(res_list) == 2:
                        try:
                            self.resolution = (int(res_list[0]), int(res_list[1]))
                        except (ValueError, TypeError):
                            pass

                self.fullscreen = data.get("fullscreen", self.fullscreen)

                # Idioma (vazio/ausente = ainda não escolhido)
                lang = data.get("language", self.language)
                if lang in ("pt", "en"):
                    self.language = lang

                # Qualidade visual
                vq = data.get("visual_quality", self.visual_quality)
                if vq in ("high", "medium", "low"):
                    self.visual_quality = vq

                # Pixelização (pós-processamento). Configs antigas com "off" já
                # não são válidas → caem no piso "light" (default).
                px = data.get("pixelization", self.pixelization)
                if px in ("light", "medium", "strong"):
                    self.pixelization = px

                self.retro_background = bool(
                    data.get("retro_background", self.retro_background)
                )
                self.ui_animations = bool(
                    data.get("ui_animations", self.ui_animations)
                )

                # Áudio
                self.music_volume = float(data.get("music_volume", self.music_volume))
                self.sfx_volume = float(data.get("sfx_volume", self.sfx_volume))
                self.shot_volume = float(data.get("shot_volume", self.shot_volume))

                # Controles
                self.mouse_control = data.get("mouse_control", self.mouse_control)
                self.auto_fire = data.get("auto_fire", self.auto_fire)
                self.touch_mode = data.get("touch_mode", self.touch_mode)
                self.virtual_joystick = data.get(
                    "virtual_joystick", self.virtual_joystick
                )
                self.show_controls_modal = data.get(
                    "show_controls_modal", self.show_controls_modal
                )
                self.controls_modal_seen = data.get(
                    "controls_modal_seen", self.controls_modal_seen
                )
                self.gamepad_enabled = data.get("gamepad_enabled", self.gamepad_enabled)
                self.gamepad_choice_made = data.get(
                    "gamepad_choice_made", self.gamepad_choice_made
                )
                self.p1_prefers_keyboard = data.get(
                    "p1_prefers_keyboard", self.p1_prefers_keyboard
                )
                self.p2_coop_enabled = data.get("p2_coop_enabled", self.p2_coop_enabled)

        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error("Erro ao carregar preferências: %s", e)

    def save(self):
        """Salva preferências no disco."""
        import sys as _sys

        # Web (emscripten): MEMFS volátil + I/O bloqueante no loop. Não persiste
        # entre reloads, então escrever só custa stutter. Ver PlayerProfile.save.
        if _sys.platform == "emscripten":
            return
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {
                "resolution": list(self.resolution),
                "fullscreen": self.fullscreen,
                "language": self.language,
                "visual_quality": self.visual_quality,
                "pixelization": self.pixelization,
                "retro_background": self.retro_background,
                "ui_animations": self.ui_animations,
                "music_volume": self.music_volume,
                "sfx_volume": self.sfx_volume,
                "shot_volume": self.shot_volume,
                "mouse_control": self.mouse_control,
                "auto_fire": self.auto_fire,
                "touch_mode": self.touch_mode,
                "virtual_joystick": self.virtual_joystick,
                "show_controls_modal": self.show_controls_modal,
                "controls_modal_seen": self.controls_modal_seen,
                "gamepad_enabled": self.gamepad_enabled,
                "gamepad_choice_made": self.gamepad_choice_made,
                "p1_prefers_keyboard": self.p1_prefers_keyboard,
                "p2_coop_enabled": self.p2_coop_enabled,
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (OSError, ValueError) as e:
            logger.error("Erro ao salvar preferências: %s", e)

    def reset(self):
        """Redefine para os padrões de fábrica."""
        self.resolution = (1280, 720)
        self.fullscreen = True
        self.language = ""
        self.visual_quality = "high"
        self.pixelization = "light"
        self.retro_background = True
        import sys as _sys

        self.ui_animations = _sys.platform != "emscripten"
        self.music_volume = VOLUME_CONFIG["music"]
        self.sfx_volume = VOLUME_CONFIG["sfx"]
        self.shot_volume = VOLUME_CONFIG["shots"]
        # Mesmos defaults do `__init__`, e não `False` cru: no web um "restaurar
        # padrões" que desligasse os dois deixaria o jogador de celular sem
        # conseguir mover a nave, sem teclado para desfazer e sem persistência
        # para o próximo boot corrigir — dentro da própria tela de opções.
        _web = _sys.platform == "emscripten"
        self.mouse_control = False
        self.auto_fire = _web
        self.touch_mode = _web
        self.virtual_joystick = _web
        self.show_controls_modal = True
        self.controls_modal_seen = False
        self.gamepad_enabled = False
        self.gamepad_choice_made = False
        self.p1_prefers_keyboard = False
        self.p2_coop_enabled = True
        self.save()
