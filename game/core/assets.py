from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import pygame

# Caminho base para o jogo
BASE_DIR = Path(__file__).resolve().parents[1]  # .../game
DEFAULT_FONT_PATH = BASE_DIR / "assets" / "fonts" / "PressStart2P-Regular.ttf"
CURSOR_PATH = BASE_DIR / "assets" / "cursors" / "cursor.png"


class _PixelGridFont(pygame.font.Font):
    """Fonte pixel (PressStart2P) com cache de rasterização por instância.

    A PressStart2P tem grade nativa de 8px: renderiza SEM anti-aliasing (bordas
    cristalinas) exatamente nos tamanhos múltiplos de 8 e COM AA (bordas suaves)
    em qualquer outro tamanho.

    **Histórico — por que esta classe já borrou o texto de propósito.** Durante um
    tempo ela aplicava um par de `smoothscale` (`_SOFTEN_FRAC = 0.97`) ao texto
    on-grid, para igualar a quantidade de AA dos tamanhos off-grid. O objetivo era
    a pixelização de frame inteiro (`PixelizePost`, sempre ativa) cair uniforme em
    todo texto, em vez de parecer "aplicada só em parte".

    **Removido.** O efeito colateral era pior que o problema: medido, o texto
    on-grid saía MAIS suavizado que o off-grid que ele tentava imitar (16px:
    20,65% de pixels suavizados contra 17,34% do 13px; 24px: 27,59% contra 13,10%
    do 18px) e custava 2–4× mais por render. O alvo virou o oposto — letra na
    grade, cristalina, que é o que pixel art quer dizer. A uniformidade que a
    suavização buscava é responsabilidade de levar os tamanhos de fonte para a
    grade de 8, não de borrar quem já está nela.

    O que sobrou (e é o valor real da classe) é o **cache de rasterização**: a UI
    redesenha os mesmos rótulos a cada frame, e o cache de texto do web
    (`web/main.py`) não alcança esta subclasse porque ela sobrescreve `render`.
    """

    # Teto do cache POR INSTÂNCIA de fonte. A UI repete um punhado de rótulos
    # fixos; o que varia (score, contadores) rotaciona por poucos valores. 256
    # cobre isso com folga e limita a memória — importante no WASM, onde o heap
    # é finito e o `get_font` mantém até 64 fontes vivas.
    _RENDER_CACHE_MAX = 256

    def __init__(self, path: str, size: int) -> None:
        super().__init__(path, size)
        # Cache POR INSTÂNCIA (e não global chaveado por `id(self)`): o `get_font`
        # é um `lru_cache` que despeja fontes, e um `id()` reciclado pelo GC
        # devolveria a surface da fonte ERRADA. Aqui o cache morre junto com a
        # fonte, sem chave ambígua possível.
        self._render_cache: "OrderedDict[tuple, pygame.Surface]" = OrderedDict()

    def render(self, text, antialias, color, *args, **kwargs):  # type: ignore[override]
        """Como `Font.render`, memoizando a surface rasterizada.

        A UI redesenha os mesmos rótulos a cada frame. O cache de texto do web
        (`web/main.py`) NÃO cobre este caminho: ele substitui
        `pygame.font.Font.render`, mas esta subclasse sobrescreve `render`, então
        a chamada entra aqui e só o `super().render()` lá dentro o veria.
        Memoizar no nível certo é aqui.

        **A surface devolvida é COMPARTILHADA** entre chamadas iguais. O padrão
        do código é `surf = render(...); surf.set_alpha(a); blit(surf)` — o alpha
        é escrito imediatamente antes de cada blit, então compartilhar é seguro.
        Quem guardar a surface para mutar depois precisa copiá-la. É a mesma
        semântica que o cache do web já impõe a todo o texto off-grid.
        """
        # Caminho com `background` ou outros extras: raro e com espaço de chaves
        # aberto — não cacheia, para o cache não virar depósito.
        if args or kwargs:
            return super().render(text, antialias, color, *args, **kwargs)

        try:
            key = (text, bool(antialias), tuple(color))
        except TypeError:  # cor não iterável (int de índice de paleta, etc.)
            return super().render(text, antialias, color)

        cache = self._render_cache
        surf = cache.get(key)
        if surf is not None:
            cache.move_to_end(key)
            return surf

        surf = super().render(text, antialias, color)
        cache[key] = surf
        if len(cache) > self._RENDER_CACHE_MAX:
            cache.popitem(last=False)  # LRU: descarta o menos usado recentemente
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
