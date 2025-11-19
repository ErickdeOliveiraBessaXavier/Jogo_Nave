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


@lru_cache(maxsize=128)
def get_image(path: str | Path, alpha: bool = True) -> pygame.Surface:
    """
    Carrega e retorna uma imagem, com cache para evitar recarregar a mesma imagem.
    Converte a imagem para ter um canal alpha se 'alpha' for True.
    Retorna uma Surface vazia em caso de erro.
    """
    image_path = Path(path)
    try:
        image = pygame.image.load(str(image_path))
        if alpha:
            return image.convert_alpha()
        else:
            return image.convert()
    except pygame.error as e:
        print(f"❌ Erro ao carregar imagem {image_path}: {e}")
        # Retorna uma Surface vazia em caso de erro de carregamento
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    except FileNotFoundError:
        print(f"⚠️ Imagem não encontrada: {image_path}")
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    except Exception as e:
        print(f"❌ Erro inesperado ao carregar imagem {image_path}: {e}")
        return pygame.Surface((1, 1), pygame.SRCALPHA)


def load_custom_cursor() -> None:
    """Carrega o cursor customizado em pixel art."""
    try:
        if CURSOR_PATH.exists():
            # Carregar a imagem do cursor
            cursor_image = get_image(CURSOR_PATH) # Using the new get_image function
            # O cursor já está no tamanho correto (36x36)
            # Definir o cursor (hotspot no centro)
            hotspot = (cursor_image.get_width() // 2, cursor_image.get_height() // 2)
            cursor = pygame.cursors.Cursor(hotspot, cursor_image)
            pygame.mouse.set_cursor(cursor)
        else:
            print(f"⚠️ Cursor não encontrado em {CURSOR_PATH}")
    except Exception as e:
        print(f"❌ Erro ao carregar cursor: {e}")

