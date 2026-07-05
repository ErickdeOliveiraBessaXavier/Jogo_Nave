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

        # Qualidade visual: "high" | "medium" | "low" (default: high).
        self.visual_quality: str = "high"

        # Áudio — defaults vindos de VOLUME_CONFIG (fonte única de verdade)
        self.music_volume: float = VOLUME_CONFIG["music"]
        self.sfx_volume: float = VOLUME_CONFIG["sfx"]
        self.shot_volume: float = VOLUME_CONFIG["shots"]

        # Controles
        self.mouse_control: bool = False
        self.auto_fire: bool = False
        self.show_controls_modal: bool = True
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

                # Qualidade visual
                vq = data.get("visual_quality", self.visual_quality)
                if vq in ("high", "medium", "low"):
                    self.visual_quality = vq

                # Áudio
                self.music_volume = float(data.get("music_volume", self.music_volume))
                self.sfx_volume = float(data.get("sfx_volume", self.sfx_volume))
                self.shot_volume = float(data.get("shot_volume", self.shot_volume))

                # Controles
                self.mouse_control = data.get("mouse_control", self.mouse_control)
                self.auto_fire = data.get("auto_fire", self.auto_fire)
                self.show_controls_modal = data.get(
                    "show_controls_modal", self.show_controls_modal
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
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {
                "resolution": list(self.resolution),
                "fullscreen": self.fullscreen,
                "visual_quality": self.visual_quality,
                "music_volume": self.music_volume,
                "sfx_volume": self.sfx_volume,
                "shot_volume": self.shot_volume,
                "mouse_control": self.mouse_control,
                "auto_fire": self.auto_fire,
                "show_controls_modal": self.show_controls_modal,
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
        self.visual_quality = "high"
        self.music_volume = VOLUME_CONFIG["music"]
        self.sfx_volume = VOLUME_CONFIG["sfx"]
        self.shot_volume = VOLUME_CONFIG["shots"]
        self.mouse_control = False
        self.auto_fire = False
        self.show_controls_modal = True
        self.gamepad_enabled = False
        self.gamepad_choice_made = False
        self.p1_prefers_keyboard = False
        self.p2_coop_enabled = True
        self.save()
