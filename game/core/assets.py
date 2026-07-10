from functools import lru_cache
from pathlib import Path

import pygame

# Caminho base para o jogo
BASE_DIR = Path(__file__).resolve().parents[1]  # .../game
DEFAULT_FONT_PATH = BASE_DIR / "assets" / "fonts" / "PressStart2P-Regular.ttf"
CURSOR_PATH = BASE_DIR / "assets" / "cursors" / "cursor.png"


class _PixelGridFont(pygame.font.Font):
    """Fonte pixel (PressStart2P) que uniformiza a nitidez das bordas do texto.

    A PressStart2P tem grade nativa de 8px: renderiza SEM anti-aliasing (bordas
    cristalinas) exatamente nos tamanhos múltiplos de 8 e COM AA (bordas suaves)
    em qualquer outro tamanho. A UI mistura on-grid (16px) e off-grid (13/18/36),
    então parte do texto saía pixel-perfect e parte suave. Sob a pixelização de
    frame inteiro (§ `PixelizePost`, sempre ativa) esse contraste vira a impressão
    de "efeito aplicado só em parte": o texto já cristalino quase não muda, o
    suave borra mais.

    Aqui o texto on-grid recebe a MESMA leve suavização que os off-grid já têm de
    graça, para a pixelização cair uniforme em todos. Off-grid não é tocado (já é
    AA). Só afeta a rasterização de bordas — `size()`/métricas não mudam, logo o
    layout é idêntico. Como a pixelização não tem estado "off" (piso `light`), a
    suavização é incondicional.
    """

    # Encolher→ampliar por esta fração introduz ~1px de feathering, calibrado para
    # o texto on-grid casar com a quantidade de AA dos tamanhos off-grid vizinhos.
    _SOFTEN_FRAC = 0.97

    def __init__(self, path: str, size: int) -> None:
        super().__init__(path, size)
        self._grid_size = size

    def render(self, text, antialias, color, *args, **kwargs):  # type: ignore[override]
        surf = super().render(text, antialias, color, *args, **kwargs)
        # Só o caso cristalino (on-grid + AA pedido) precisa de suavização; texto
        # off-grid já vem suave e aliased (antialias=False) deve permanecer duro.
        if antialias and self._grid_size % 8 == 0:
            w, h = surf.get_size()
            if w > 1 and h > 1:
                frac = self._SOFTEN_FRAC
                small = pygame.transform.smoothscale(
                    surf, (max(1, round(w * frac)), max(1, round(h * frac)))
                )
                surf = pygame.transform.smoothscale(small, (w, h))
        return surf


@lru_cache(maxsize=64)
def get_font(size: int, path: str | Path | None = None) -> pygame.font.Font:
    """
    Retorna uma fonte cacheada pelo tamanho.
    Se não encontrar a TTF, cai na fonte padrão do sistema.

    A fonte padrão (pixel, PressStart2P) usa `_PixelGridFont` para uniformizar a
    nitidez sob a pixelização; fontes customizadas ou o fallback do sistema usam a
    `Font` normal (a grade de 8px é específica da PressStart2P).
    """
    if path is None:
        try:
            return _PixelGridFont(str(DEFAULT_FONT_PATH), size)
        except (OSError, pygame.error):
            return pygame.font.Font(None, size)
    try:
        return pygame.font.Font(str(Path(path)), size)
    except (OSError, pygame.error):
        return pygame.font.Font(None, size)


@lru_cache(maxsize=128)
def _get_image_cached(image_path: str, alpha: bool = True) -> pygame.Surface:
    """
    Carrega e retorna uma imagem, com cache para evitar recarregar a mesma imagem.
    Converte a imagem para ter um canal alpha se 'alpha' for True.
    Retorna uma Surface vazia em caso de erro.
    """
    normalized_path = Path(image_path)
    try:
        image = pygame.image.load(str(normalized_path))
        if alpha:
            return image.convert_alpha()
        return image.convert()
    except pygame.error as e:
        print(f"❌ Erro ao carregar imagem {normalized_path}: {e}")
        # Retorna uma Surface vazia em caso de erro de carregamento
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    except FileNotFoundError:
        print(f"⚠️ Imagem não encontrada: {normalized_path}")
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Erro inesperado ao carregar imagem {normalized_path}: {e}")
        return pygame.Surface((1, 1), pygame.SRCALPHA)


def get_image(path: str | Path, alpha: bool = True) -> pygame.Surface:
    """
    Carrega e retorna uma imagem, com cache para evitar recarregar a mesma imagem.

    Normaliza o caminho absoluto para aumentar hits de cache quando o mesmo
    arquivo é referenciado por caminhos equivalentes.
    """
    normalized_path = str(Path(path).resolve())
    return _get_image_cached(normalized_path, alpha)


def load_custom_cursor() -> None:
    """Carrega o cursor customizado em pixel art."""
    try:
        if CURSOR_PATH.exists():
            # Carregar a imagem do cursor
            cursor_image = get_image(CURSOR_PATH)  # Using the new get_image function
            # O cursor já está no tamanho correto (36x36)
            # Definir o cursor (hotspot no centro)
            hotspot = (cursor_image.get_width() // 2, cursor_image.get_height() // 2)
            cursor = pygame.cursors.Cursor(hotspot, cursor_image)
            pygame.mouse.set_cursor(cursor)
        else:
            print(f"⚠️ Cursor não encontrado em {CURSOR_PATH}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Erro ao carregar cursor: {e}")
