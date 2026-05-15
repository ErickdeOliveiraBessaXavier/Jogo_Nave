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

        # Áudio — defaults vindos de VOLUME_CONFIG (fonte única de verdade)
        self.music_volume: float = VOLUME_CONFIG["music"]
        self.sfx_volume: float = VOLUME_CONFIG["sfx"]
        self.shot_volume: float = VOLUME_CONFIG["shots"]

        # Controles
        self.mouse_control: bool = False
        self.auto_fire: bool = False
        self.show_controls_modal: bool = True

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

                # Áudio
                self.music_volume = float(data.get("music_volume", self.music_volume))
                self.sfx_volume = float(data.get("sfx_volume", self.sfx_volume))
                self.shot_volume = float(data.get("shot_volume", self.shot_volume))

                # Controles
                self.mouse_control = data.get("mouse_control", self.mouse_control)
                self.auto_fire = data.get("auto_fire", self.auto_fire)
                self.show_controls_modal = data.get("show_controls_modal", self.show_controls_modal)

        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error("Erro ao carregar preferências: %s", e)

    def save(self):
        """Salva preferências no disco."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {
                "resolution": list(self.resolution),
                "fullscreen": self.fullscreen,
                "music_volume": self.music_volume,
                "sfx_volume": self.sfx_volume,
                "shot_volume": self.shot_volume,
                "mouse_control": self.mouse_control,
                "auto_fire": self.auto_fire,
                "show_controls_modal": self.show_controls_modal,
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (OSError, ValueError) as e:
            logger.error("Erro ao salvar preferências: %s", e)

    def reset(self):
        """Redefine para os padrões de fábrica."""
        self.resolution = (1280, 720)
        self.fullscreen = True
        self.music_volume = VOLUME_CONFIG["music"]
        self.sfx_volume = VOLUME_CONFIG["sfx"]
        self.shot_volume = VOLUME_CONFIG["shots"]
        self.mouse_control = False
        self.auto_fire = False
        self.show_controls_modal = True
        self.save()
