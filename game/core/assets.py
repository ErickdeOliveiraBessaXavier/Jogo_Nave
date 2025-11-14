from functools import lru_cache
from pathlib import Path
import pygame

# Caminho base para o jogo
BASE_DIR = Path(__file__).resolve().parents[1]  # .../game
DEFAULT_FONT_PATH = BASE_DIR / "assets" / "fonts" / "PressStart2P-Regular.ttf"
CURSOR_PATH = BASE_DIR / "assets" / "cursors" / "cursor.png"


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


def load_custom_cursor() -> None:
    """Carrega o cursor customizado em pixel art."""
    try:
        if CURSOR_PATH.exists():
            # Carregar a imagem do cursor
            cursor_image = pygame.image.load(str(CURSOR_PATH))
            # Converter para escala apropriada se necessário
            cursor_image = pygame.transform.scale(cursor_image, (16, 16))
            # Definir o cursor (hotspot no canto superior esquerdo)
            cursor = pygame.cursors.Cursor((0, 0), cursor_image)
            pygame.mouse.set_cursor(cursor)
        else:
            print(f"⚠️ Cursor não encontrado em {CURSOR_PATH}")
    except Exception as e:
        print(f"❌ Erro ao carregar cursor: {e}")
