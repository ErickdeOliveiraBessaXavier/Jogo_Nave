from functools import lru_cache
from pathlib import Path
import pygame

# Caminho base para o jogo
BASE_DIR = Path(__file__).resolve().parents[1]  # .../game
DEFAULT_FONT_PATH = BASE_DIR / "assets" / "fonts" / "PressStart2P-Regular.ttf"


@lru_cache(maxsize=64)
def get_font(size: int, path: str | Path | None = None) -> pygame.font.Font:
    """
    Retorna uma fonte cacheada pelo tamanho.
    Se não encontrar a TTF, cai na fonte padrão do sistema.
    """
    font_path = Path(path) if path else DEFAULT_FONT_PATH
    try:
        return pygame.font.Font(str(font_path), size)
    except Exception:
        return pygame.font.Font(None, size)
