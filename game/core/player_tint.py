"""Palette swap por jogador (P2 em ciano) — sprites e cores soltas.

As naves são todas 32x32 e compartilham a mesma linguagem de cor: casco
vermelho, cabine cinza metálica e luzes de acento. Isso permite distinguir o P2
girando a MATIZ e preservando saturação/brilho/alpha — o sombreado e a silhueta
do pixel art saem intactos, como um palette swap de verdade, em vez de um filtro
por cima. É também o motivo de não duplicarmos os PNGs à mão: nave nova ou
retoque de arte continuam valendo para os dois jogadores de graça.

`player_shot_color` estende a ideia a cores que não vêm de PNG (tiros e
partículas de impacto, desenhados em código), mas com um giro MUITO menor — ver
`P2_SHOT_HUE_SHIFT` para o porquê.
"""

import colorsys
from pathlib import Path
from typing import Dict, Tuple, TypeVar, cast

import pygame

from .assets import get_image

# Meia volta no círculo de cores: o casco vermelho do P1 vira ciano — o oposto
# natural do vermelho e o maior contraste possível entre os dois jogadores.
P2_HUE_SHIFT: float = 0.5

# Pixels abaixo deste piso de saturação passam intactos. É o que preserva a
# cabine cinza e os brilhos brancos: girar a matiz de um cinza não o colore,
# só o suja de um tom qualquer. Sem o piso, o sprite inteiro vira mancha.
_SAT_FLOOR: float = 0.15

# Multiplicador aplicado ao sprite inteiro quando ele é de corpo NEUTRO (ver
# `cast_neutral`). A mini-nave é 71% branco puro com só um acento vermelho:
# girar a matiz recolore o acento e deixa o corpo branco intacto, então as duas
# minis ficam idênticas em jogo. O cast dá ao branco a cor do jogador
# preservando a sombreadura (branco→ciano claro, cinza→ciano escuro), sem
# achatar o contraste de dois tons da arte.
_P2_NEUTRAL_CAST: tuple[int, int, int] = (150, 255, 255)

# Memo por (arquivo, shift, cast). O custo é ~1-4k pixels em Python por sprite,
# pago uma vez por processo — irrelevante, mas não há motivo para repetir.
_tinted_cache: Dict[tuple[str, float, bool], pygame.Surface] = {}


def hue_shifted(surf: pygame.Surface, shift: float) -> pygame.Surface:
    """Cópia de `surf` com a matiz girada por `shift` (0..1, 0.5 = oposto).

    Saturação, brilho e alpha ficam intactos — só a cor muda. Pixels
    transparentes e cinzas/brancos (ver `_SAT_FLOOR`) não são tocados.
    """
    out = surf.copy()
    width, height = out.get_size()
    rgb_to_hsv = colorsys.rgb_to_hsv
    hsv_to_rgb = colorsys.hsv_to_rgb
    get_at = out.get_at
    set_at = out.set_at
    for x in range(width):
        for y in range(height):
            r, g, b, a = get_at((x, y))
            if a == 0:
                continue
            h, s, v = rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if s < _SAT_FLOOR:
                continue
            nr, ng, nb = hsv_to_rgb((h + shift) % 1.0, s, v)
            set_at((x, y), (int(nr * 255), int(ng * 255), int(nb * 255), a))
    return out


# Memo das cores desviadas. Desviar uma cor é barato, mas o desenho do tiro
# consulta a paleta inteira a cada frame de cada bala — memoizar tira o
# colorsys do hot path e deixa o custo em um lookup de dict.
_color_cache: Dict[Tuple[Tuple[int, ...], float], Tuple[int, ...]] = {}


# Giro aplicado aos TIROS do P2 — deliberadamente pequeno, e não o meia-volta
# dos sprites. O casco funciona com 0.5 porque toda nave parte do mesmo
# vermelho: girar todas junto leva todas ao mesmo ciano. Os tiros já nascem em
# cores diferentes umas das outras, então meia volta manda cada um para um lugar
# diferente e destrói justamente a identidade por nave: o Magneto (azul) cairia
# no amarelo do Padrão e o Reverberador (magenta) no verde do Estilete — dois
# pares de naves indistinguíveis. Um giro curto mantém cada tiro na própria
# família de cor e ainda separa os jogadores.
P2_SHOT_HUE_SHIFT: float = 0.08

# Tiros acinzentados (o prata do Caçador) não têm matiz para girar e passariam
# batido pelo `_SAT_FLOOR`, deixando os dois jogadores idênticos. Para eles, um
# multiplicador frio: esfria o metal sem apagar o sombreado.
_P2_SHOT_GREY_CAST: Tuple[int, int, int] = (200, 235, 255)

# Cor de tiro: RGB ou RGBA. O TypeVar existe para o retorno de
# `player_shot_color` manter o COMPRIMENTO da entrada — ver o docstring de lá.
_ColorT = TypeVar("_ColorT", bound=Tuple[int, ...])


def player_shot_color(color: _ColorT, player_index: int) -> _ColorT:
    """`color` de tiro/impacto na cor do jogador: P1 (0) intacta, P2 (1) desviada.

    Devolve o próprio objeto para o P1 — este caminho roda por cor, por bala,
    por frame, e não há motivo para alocar uma tupla idêntica à entrada.

    Genérica no tipo da cor porque ela **preserva o comprimento**: RGB entra,
    RGB sai; RGBA entra, RGBA sai (o alpha atravessa intacto, ver
    `_shot_shifted`). Anotada como `Tuple[int, ...]` nos dois lados, a saída
    perdia o comprimento e todo consumidor que exige um RGB de três posições
    — os caches de glow do tiro, a paleta de impacto — reclamava ou precisava
    de um `type: ignore`.

    O `cast` é a única parte que o verificador não consegue provar sozinho: a
    reconstrução em `_shot_shifted` monta a tupla a partir do `color[3:]` do
    original, então o comprimento sai igual ao da entrada por construção.
    """
    if player_index != 1:
        return color
    return cast(_ColorT, _shot_shifted(tuple(color)))


def _shot_shifted(color: Tuple[int, ...]) -> Tuple[int, ...]:
    key = (color, P2_SHOT_HUE_SHIFT)
    cached = _color_cache.get(key)
    if cached is not None:
        return cached

    r, g, b = color[0], color[1], color[2]
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if s < _SAT_FLOOR:
        cast = _P2_SHOT_GREY_CAST
        out = (r * cast[0] // 255, g * cast[1] // 255, b * cast[2] // 255) + tuple(
            color[3:]
        )
    else:
        nr, ng, nb = colorsys.hsv_to_rgb((h + P2_SHOT_HUE_SHIFT) % 1.0, s, v)
        out = (int(nr * 255), int(ng * 255), int(nb * 255)) + tuple(color[3:])
    _color_cache[key] = out
    return out


def player_sprite(
    path: str | Path, player_index: int, cast_neutral: bool = False
) -> pygame.Surface:
    """Sprite de `path` na cor do jogador: P1 (0) original, P2 (1) em ciano.

    `cast_neutral` é para sprites de corpo branco/cinza (a mini-nave e a escolta
    Wingman), onde só girar a matiz não muda quase nada — ver `_P2_NEUTRAL_CAST`.
    As naves são coloridas e não usam.

    Não mutar o retorno — é compartilhado (como o de `get_image`). Escalar e
    rotacionar devolvem surfaces novas, então o uso normal é seguro.
    """
    if player_index != 1:
        return get_image(path)

    key = (str(path), P2_HUE_SHIFT, cast_neutral)
    cached = _tinted_cache.get(key)
    if cached is None:
        cached = hue_shifted(get_image(path).convert_alpha(), P2_HUE_SHIFT)
        if cast_neutral:
            cached.fill(_P2_NEUTRAL_CAST, special_flags=pygame.BLEND_RGB_MULT)
        try:
            cached = cached.convert_alpha()
        except pygame.error:
            pass
        _tinted_cache[key] = cached
    return cached
