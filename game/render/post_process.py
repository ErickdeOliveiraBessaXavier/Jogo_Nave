"""Pós-processamento de frame inteiro — efeitos aplicados após todo o render.

Opera sobre os pixels finais do frame, não sobre entidades. Depois que a cena
já desenhou tudo (nave, inimigos, bosses, poderes — sejam sprites, `Rect` ou
`draw.*`), a superfície vira uma imagem chapada e o efeito trata todos por igual.
Por isso o custo é O(1) por frame e não exige tocar em nenhuma entidade.
"""

from __future__ import annotations

import pygame


class PixelizePost:
    """Pixeliza o frame inteiro via downscale→upscale, com blocos ``~fator``px.

    O truque clássico do look retrô: encolhe o frame e o reamplia, virando cada
    região de origem num bloco. Detalhe importante do downscale:

    - **Downscale com `smoothscale` (média de área):** feições finas (bordas de
      1px, texto) são *mediadas* para dentro do pixel menor em vez de puladas.
      Um downscale `scale` (nearest) point-sampleia e **descarta** linhas/colunas
      inteiras — é o que fazia bordas de 1px aparecerem "comidas"/fragmentadas.
    - **Upscale com `scale` (nearest):** preserva as bordas duras dos blocos —
      é o que dá o visual pixelizado (não borrado).

    Buffer intermediário pré-alocado e reaproveitado enquanto tamanho/fator não
    mudam — evita alocar surfaces por frame. O upscale escreve de volta no
    próprio surface de destino (in-place).
    """

    def __init__(self) -> None:
        self._buffer: pygame.Surface | None = None
        self._buffer_key: tuple[int, int, int] | None = None
        import sys

        # Web (WASM) usa render por software: smoothscale (média de área) de tela
        # cheia por frame é caríssimo. No web caímos pra nearest no downscale —
        # mantém o look pixelizado, custo bem menor.
        self._is_web = sys.platform == "emscripten"

    def apply(self, surface: pygame.Surface, factor: float) -> None:
        """Aplica a pixelização in-place. ``factor <= 1`` é no-op (desligado).

        Aceita fator fracionário (ex.: 1.3) para pixelizações mais finas/suaves
        que o menor bloco inteiro (2×2): o downscale para um tamanho intermediário
        e o reupscale nearest produzem blocos de ~``factor`` px.
        """
        if factor <= 1.0:
            return

        w, h = surface.get_size()
        sw = max(1, round(w / factor))
        sh = max(1, round(h / factor))

        key = (sw, sh, surface.get_bitsize())
        if self._buffer is None or self._buffer_key != key:
            # convert() casa o formato de pixel do frame → scale mais rápido.
            self._buffer = pygame.Surface((sw, sh)).convert(surface)
            self._buffer_key = key

        # Downscale: no desktop usa média de área (preserva feições finas); no
        # web usa nearest (bem mais barato no render por software). Upscale sempre
        # nearest (mantém as bordas duras dos blocos = look pixelizado).
        if self._is_web:
            pygame.transform.scale(surface, (sw, sh), self._buffer)
        else:
            pygame.transform.smoothscale(surface, (sw, sh), self._buffer)
        pygame.transform.scale(self._buffer, (w, h), surface)
