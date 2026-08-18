"""Geometria e carga de sprites da Tríade — FONTE ÚNICA das medidas do boss.

A arte (`assets/images/Trio_Head_Energy/`) tem uma propriedade que decide o
desenho inteiro deste boss: **as três partes já vêm alinhadas numa mesma tela de
64×64**. Medido nos arquivos:

    Cabeça_Esquerda    bbox = (8, 16) → (23, 40)
    Cabeça_Direita     bbox = (41, 16) → (56, 40)
    Cabeça_Troco       bbox = (13, 0) → (51, 62)

Ou seja: blitar as três camadas na MESMA origem reproduz o
`Imagem_Boss_Completo_Exemplo.png` sem nenhum offset manual. Todas as constantes
abaixo vivem nesse espaço de 64×64 ("sprite space") e só viram pixels de tela
quando multiplicadas por `PIXEL_SCALE` — assim mudar a escala do boss não exige
recalibrar hitbox nenhuma.

O sprite ganha `PIXEL_SCALE` FIXO (não `core.scale.scaled`), seguindo o corpo dos
outros bosses (`MetropolisOverlordBoss.PIXEL_SCALE`, `MountainSerpentBoss.
HEAD_PIXEL_SCALE`): o corpo do chefe é objeto de mundo desenhado na resolução
lógica, e o pygame escala o frame inteiro (§12). `scaled()` continua valendo para
velocidades e efeitos transitórios.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pygame

from ....core.assets import BASE_DIR, get_image

SPRITE_DIR: Path = BASE_DIR / "assets" / "images" / "Trio_Head_Energy"

# Subpastas por parte. As chaves são os identificadores usados no resto do boss.
PART_DIRS: Dict[str, str] = {
    "crown": "Cabeça_Troco_e-Coroa",  # cabeça principal + tronco + halo
    "left": "Cabeça_Esquerda",
    "right": "Cabeça_Direita",
}

# ── Espaço do sprite (64×64) ──────────────────────────────────────────────────
FRAME: int = 64
# 5 = 1,25× a escala original (4). Múltiplo INTEIRO de propósito: escala
# fracionária em pixel art produz linhas de espessura desigual, e a arte aqui
# tem traços de 1px que ficariam gaguejando.
PIXEL_SCALE: int = 5

# Cadência da animação idle. São só 3 frames por parte, então uma taxa alta
# vira tremor em vez de respiração — a 6 fps o ciclo inteiro durava 0,5s.
# 2,5 fps com o loop de ida e volta (`_pingpong`) dá 1,6s por ciclo — o ritmo
# de uma criatura serena flutuando.
ANIM_FPS: float = 2.5

# Caixa de conteúdo: união dos bboxes das três partes. É ela — e não a tela de
# 64×64 — que define `w`/`h` do boss, para o `rect` não carregar margem vazia
# (ele é o pré-filtro AABB da colisão e a âncora da explosão de morte).
CONTENT_X0, CONTENT_Y0 = 8, 0
CONTENT_X1, CONTENT_Y1 = 56, 62
CONTENT_W: int = CONTENT_X1 - CONTENT_X0  # 48
CONTENT_H: int = CONTENT_Y1 - CONTENT_Y0  # 62

# Origem do blit em relação ao (x, y) do boss: o sprite é uma tela de 64×64, e o
# (x, y) do boss é o canto da caixa de CONTEÚDO.
BLIT_OFFSET_X: int = -CONTENT_X0 * PIXEL_SCALE
BLIT_OFFSET_Y: int = -CONTENT_Y0 * PIXEL_SCALE


def _rel(sx: float, sy: float) -> tuple[float, float]:
    """Ponto do espaço do sprite → offset em pixels a partir do (x, y) do boss."""
    return ((sx - CONTENT_X0) * PIXEL_SCALE, (sy - CONTENT_Y0) * PIXEL_SCALE)


# ── Pontos notáveis, medidos na arte ──────────────────────────────────────────
# Bandas do sprite `crown`, por ocupação de linha:
#   y  2..13  halo (gema em 2..5, anel em 6..12)
#   y 14..38  cabeça principal (x 22..41)
#   y 39..61  tronco/ombros (x 13..50), núcleo de energia em ~42..46
#
# Os centros das cabeças são o CENTROIDE DOS PIXELS DESENHADOS, não o centro do
# bbox. A diferença é grande e não é cosmética: a cabeça lateral é um GANCHO —
# uma massa grossa de um lado e um filamento fino curvando do outro — e o centro
# do bbox, (15.5, 28), cai no VAZIO entre os dois. Um círculo ancorado ali faz a
# mira automática apontar para o buraco e o fallback de roteamento medir
# distância a partir de um ponto onde não há boss.
# A Coroa fica MEDIDA À MÃO porque o alvo dela é a CABEÇA (banda y 14..38), não
# o corpo: o centroide do sprite inteiro cairia no tronco, 6px abaixo do rosto.
CROWN_HEAD_CENTER = _rel(31.5, 26.4)
HALO_CENTER = _rel(31.5, 8.0)
CORE_CENTER = _rel(31.5, 44.0)
# As laterais são DERIVADAS da arte por `part_anchor()` — ver a explicação lá.

# Raios em pixels de tela. **Não são mais a área de dano** — essa saiu para a
# máscara por pixel (ver `PartSprites.mask` e `TriadBoss.get_collision_mask_data`),
# que atinge só onde o PNG tem conteúdo desenhado. Estes raios seguem servindo a
# três consumidores que pedem círculo e não máscara:
#   * `collision_circle()` — mira automática/teleguiado e alcance de dano em área;
#   * o fallback de roteamento quando o impacto cai fora de toda máscara (o AoE
#     aplica o hit no centro de um círculo, não num pixel);
#   * `collision_circles()`, contrato §8 para quem não consulta máscara.
# Dimensionados sobre a massa real: 85% dos pixels de uma lateral cabem em raio
# 9,8 do centroide, e da cabeça da Coroa em 11,4. Os centroides ficam a 18,7 de
# distância, e 8,5 + 8,0 = 16,5 mantém os círculos sem sobreposição — o fallback
# de roteamento continua sem zona ambígua.
CROWN_HEAD_RADIUS: float = 8.5 * PIXEL_SCALE
SIDE_HEAD_RADIUS: float = 8.0 * PIXEL_SCALE

# Círculo envolvente (broadphase / AoE): cobre as três cabeças e o tronco.
ENCLOSING_RADIUS: float = 32.0 * PIXEL_SCALE

# ── Paleta, tirada da própria arte ────────────────────────────────────────────
# Ciano = repouso; laranja = atacando. O contrato de telégrafo do boss (§7 do
# plano) é a troca entre estes dois frames, então as cores derivadas (barra de
# vida, pips, tendões, brasas) saem daqui para não divergirem do sprite.
CYAN = (47, 212, 232)
CYAN_DIM = (24, 116, 130)
CYAN_DARK = (12, 42, 49)
ORANGE = (240, 128, 64)
ORANGE_DIM = (150, 74, 34)
GEM_WHITE = (255, 255, 255)
GEM_HOT = (255, 90, 60)


# ── Região de dano das cabeças laterais ───────────────────────────────────────
# A silhueta de uma Voz tem DUAS partes muito diferentes:
#
#   * o ROSTO — uma barra horizontal no topo (a testa) mais uma coluna vertical
#     descendo pela borda externa. Juntas formam um "L invertido" (Γ);
#   * o FILAMENTO — um traço de 1px que curva para DENTRO, em direção ao tronco,
#     e nas linhas 37-39 chega a ficar entrelaçado com os pixels do corpo.
#
# Só o rosto é alvo. O filamento continua sendo desenhado, mas não recebe dano:
# ele fica no caminho de quem mira a cabeça central, e como o roteamento dá a
# vitória à Voz em caso de empate, tiro no tronco virava dano na lateral.
#
# Retângulos no espaço do sprite, (x, y, w, h), medidos sobre
# `Exemplo_Área_Colisão.jpeg` (o desenho de referência alinhou com o sprite a
# 100%). A da direita saiu da imagem; a da esquerda é o espelho exato (x' = 63-x).
#
# **A região é SÓLIDA — não é interseccionada com a máscara do sprite.** A Coroa
# segue por pixel, as Vozes não, e a diferença é deliberada: o rosto tem um vão de
# uma linha inteira na altura da "boca" (linha 32, onde só o filamento aparece) e
# afina nas linhas 35-36. Recortado por máscara, esse vão vira uma FRESTA
# horizontal atravessável no meio da cabeça — o tiro passa reto e o jogador não
# tem como saber por quê. Retângulo cheio é previsível, e é o que o desenho pede.
HEAD_DAMAGE_RECTS: Dict[str, tuple[tuple[int, int, int, int], ...]] = {
    # testa: x cheio, y 16..19     rosto: coluna EXTERNA, y 20..37
    "left": ((8, 16, 15, 4), (8, 20, 4, 18)),
    "right": ((41, 16, 15, 4), (52, 20, 4, 18)),
}


def _region_mask(rects: tuple[tuple[int, int, int, int], ...]) -> pygame.mask.Mask:
    """Máscara sólida com os retângulos da região, já em pixels de tela."""
    size = FRAME * PIXEL_SCALE
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    for rx, ry, rw, rh in rects:
        surface.fill(
            (255, 255, 255, 255),
            pygame.Rect(
                rx * PIXEL_SCALE, ry * PIXEL_SCALE, rw * PIXEL_SCALE, rh * PIXEL_SCALE
            ),
        )
    return pygame.mask.from_surface(surface)


# ── Carga de sprites ──────────────────────────────────────────────────────────
# Cache de classe: os 12 PNGs são carregados e escalados UMA vez por processo.
# `get_image` já memoiza a leitura do disco; o que memoizamos aqui é o
# `transform.scale`, que de outro modo rodaria a cada instância de boss.
def _pingpong(index: int, count: int) -> int:
    """Índice de frame num loop de IDA E VOLTA (0,1,2,1,0,1,2,...).

    Com 3 frames, o loop em serra (`index % count`) salta do último de volta ao
    primeiro num único passo — num ciclo tão curto esse salto lê como um TRANCO,
    não como respiração. A volta pelo meio remove a descontinuidade sem pedir
    frame novo de arte.

    Período = 2*(count-1): 4 passos para 3 frames.
    """
    if count <= 1:
        return 0
    period = 2 * (count - 1)
    i = index % period
    return i if i < count else period - i


@dataclass(frozen=True)
class PartSprites:
    """Os quatro frames de uma parte, já escalados, mais as versões de flash.

    `idle` são os numerados (`01.png`…), em ordem; `attack` é o frame LARANJA —
    o telégrafo do boss. `white_*` são as cópias saturadas usadas no flash de
    dano. Uma parte sem arte no disco devolve listas vazias e `attack=None`; o
    render trata isso sem quebrar.
    """

    idle: tuple[pygame.Surface, ...]
    attack: pygame.Surface | None
    white_idle: tuple[pygame.Surface, ...]
    white_attack: pygame.Surface | None
    # Máscara de DANO por frame, na mesma tela de 64×64 escalada. É a silhueta
    # opaca do PNG — nada de retângulo ou círculo em volta — recortada pela
    # região da parte (`HEAD_DAMAGE_RECTS`) quando ela tem uma. Pré-calculadas na
    # carga: `from_surface` num frame de 320×320 é caro demais para o hot path.
    #
    # NÃO é a mesma coisa que o que se desenha: o filamento de uma Voz aparece na
    # tela e não está aqui. Área de dano e render são contratos separados.
    idle_masks: tuple[pygame.mask.Mask, ...]
    attack_mask: pygame.mask.Mask | None

    def frame(self, index: int, attacking: bool, white: bool = False) -> pygame.Surface | None:
        if attacking:
            hit = self.white_attack if white else self.attack
            if hit is not None:
                return hit
        pool = self.white_idle if white else self.idle
        if not pool:
            return None
        return pool[_pingpong(index, len(pool))]

    def mask(self, index: int, attacking: bool) -> pygame.mask.Mask | None:
        """Máscara do frame que `frame()` devolveria — as duas seguem juntas.

        O flash de dano não entra na conta: `_whiten` só clareia o RGB e preserva
        o alpha, então a silhueta do frame branco é idêntica à do normal.
        """
        if attacking and self.attack_mask is not None:
            return self.attack_mask
        if not self.idle_masks:
            return None
        # MESMO `_pingpong` do `frame()`: se os dois divergirem, a área de dano
        # passa a ser a de outro frame que não o desenhado.
        return self.idle_masks[_pingpong(index, len(self.idle_masks))]


_part_cache: Dict[str, PartSprites] = {}


def _scaled(path: Path) -> pygame.Surface:
    target = (FRAME * PIXEL_SCALE, FRAME * PIXEL_SCALE)
    image = get_image(path)
    if image.get_size() != target:
        image = pygame.transform.scale(image, target)
    return image


def _whiten(surface: pygame.Surface) -> pygame.Surface:
    """Cópia saturada para o flash de dano (mesmo truque do MountainSerpent)."""
    white = surface.copy()
    white.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
    return white


def load_part(part: str) -> PartSprites:
    """Sprites de uma parte, carregados e escalados uma única vez por processo.

    O frame de ataque é achado por `"Atacando" in name`, não por nome literal: a
    nomenclatura da arte não é uniforme (`Frame_Troco_Atacando` contra
    `Cabeça_Direita_Atacando`), e um literal errado quebraria em silêncio — sem
    exceção, só um boss que nunca fica laranja.
    """
    cached = _part_cache.get(part)
    if cached is not None:
        return cached

    directory = SPRITE_DIR / PART_DIRS[part]
    idle: List[pygame.Surface] = []
    attack: pygame.Surface | None = None

    if directory.is_dir():
        for path in sorted(directory.glob("*.png")):
            if "Atacando" in path.name:
                attack = _scaled(path)
            else:
                idle.append(_scaled(path))

    # Parte COM região declarada (as Vozes) usa o retângulo cheio; parte sem ela
    # (a Coroa) usa a silhueta por pixel do próprio frame.
    rects = HEAD_DAMAGE_RECTS.get(part)
    region = _region_mask(rects) if rects else None

    def damage_mask(surface: pygame.Surface) -> pygame.mask.Mask:
        return region if region is not None else pygame.mask.from_surface(surface)

    sprites = PartSprites(
        idle=tuple(idle),
        attack=attack,
        white_idle=tuple(_whiten(f) for f in idle),
        white_attack=_whiten(attack) if attack is not None else None,
        idle_masks=tuple(damage_mask(f) for f in idle),
        attack_mask=damage_mask(attack) if attack is not None else None,
    )
    _part_cache[part] = sprites
    return sprites


def _blob_anchor(mask: pygame.mask.Mask) -> tuple[float, float]:
    """Ponto representativo de uma silhueta, garantidamente SOBRE o desenho.

    Três tentativas, em ordem de qualidade:

    1. **Maior componente conectado.** A cabeça lateral é uma massa grossa mais
       um filamento fino solto; o centroide da silhueta inteira é puxado para o
       vão entre os dois. O maior blob é a cabeça propriamente dita.
    2. **Centroide desse blob** — que ainda pode cair fora, porque o blob é um
       GANCHO em "C" e o centroide de um "C" fica na concavidade (foi o caso da
       cabeça direita: centroide (50, 22), pixel vazio).
    3. **Encosta no pixel aceso mais próximo.** É o que fecha o buraco.

    Roda uma vez por parte, na carga, sobre a máscara NÃO escalada (64×64).
    """
    if mask.count() == 0:
        w, h = mask.get_size()
        return w / 2.0, h / 2.0

    blob = mask.connected_component()
    if blob.count() == 0:
        blob = mask
    cx, cy = blob.centroid()
    if blob.get_at((cx, cy)):
        return float(cx), float(cy)

    width, height = blob.get_size()
    best: tuple[int, int] = (cx, cy)
    best_d2 = float("inf")
    for y in range(height):
        for x in range(width):
            if not blob.get_at((x, y)):
                continue
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 < best_d2:
                best, best_d2 = (x, y), d2
    return float(best[0]), float(best[1])


_anchor_cache: Dict[str, tuple[float, float]] = {}


def part_anchor(part: str) -> tuple[float, float]:
    """Offset (a partir do x/y do boss) do ponto de ancoragem de uma parte.

    É onde o círculo daquela parte mora — o alvo da mira automática e a origem
    do fallback de roteamento. **Derivado da arte**, não digitado: o centro do
    bbox da cabeça lateral cai no vazio de dentro do gancho, e qualquer número
    escrito à mão aqui envelhece na primeira vez que o sprite for redesenhado.
    """
    cached = _anchor_cache.get(part)
    if cached is not None:
        return cached

    # Sai da máscara de DANO (já escalada), não da silhueta crua: a âncora tem
    # que cair dentro do que realmente recebe tiro — o rosto —, não no filamento.
    sprites = load_part(part)
    mask = sprites.mask(0, attacking=False)
    if mask is not None and mask.count() > 0:
        px, py = _blob_anchor(mask)
        sx, sy = px / PIXEL_SCALE, py / PIXEL_SCALE
    else:
        sx, sy = FRAME / 2.0, FRAME / 2.0

    anchor = _rel(sx, sy)
    _anchor_cache[part] = anchor
    return anchor
