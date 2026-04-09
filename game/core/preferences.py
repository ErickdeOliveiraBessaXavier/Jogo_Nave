import json
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


class UserPreferences:
    """Gerencia as preferências do usuário (sistema, áudio, controles)."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

        # Valores padrão
        self.resolution: Tuple[int, int] = (1280, 720)
        self.fullscreen: bool = True

        # Áudio
        self.music_volume: float = 0.5
        self.sfx_volume: float = 0.7
        self.shot_volume: float = 0.4

        # Controles
        self.mouse_control: bool = False
        self.auto_fire: bool = False

        self.load()

    def load(self):
        """Carrega preferências do disco."""
        if not self.file_path.exists():
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Resolução
                res = data.get("resolution")
                if isinstance(res, list) and len(res) == 2:
                    self.resolution = (int(res[0]), int(res[1]))

                self.fullscreen = data.get("fullscreen", self.fullscreen)

                # Áudio
                self.music_volume = float(data.get("music_volume", self.music_volume))
                self.sfx_volume = float(data.get("sfx_volume", self.sfx_volume))
                self.shot_volume = float(data.get("shot_volume", self.shot_volume))

                # Controles
                self.mouse_control = data.get("mouse_control", self.mouse_control)
                self.auto_fire = data.get("auto_fire", self.auto_fire)

        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error("Erro ao carregar preferências: %s", e)

    def save(self):
        """Salva preferências no disco."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "resolution": list(self.resolution),
                "fullscreen": self.fullscreen,
                "music_volume": self.music_volume,
                "sfx_volume": self.sfx_volume,
                "shot_volume": self.shot_volume,
                "mouse_control": self.mouse_control,
                "auto_fire": self.auto_fire,
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (OSError, ValueError) as e:
            logger.error("Erro ao salvar preferências: %s", e)

    def reset(self):
        """Redefine para os padrões de fábrica."""
        self.resolution = (1280, 720)
        self.fullscreen = True
        self.music_volume = 0.5
        self.sfx_volume = 0.7
        self.shot_volume = 0.4
        self.mouse_control = False
        self.auto_fire = False
        self.save()
