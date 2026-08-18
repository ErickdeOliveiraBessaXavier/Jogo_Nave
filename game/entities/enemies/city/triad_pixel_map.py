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
PIXEL_SCALE: int = 4

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
CROWN_HEAD_CENTER = _rel(31.5, 26.0)
HALO_CENTER = _rel(31.5, 8.0)
CORE_CENTER = _rel(31.5, 44.0)
LEFT_HEAD_CENTER = _rel(15.5, 28.0)
RIGHT_HEAD_CENTER = _rel(48.5, 28.0)

# Raios de hitbox, em pixels de tela.
#
# Os centros ficam a 64,5px um do outro (√(64² + 8²)), então 34 + 28 = 62 mantém
# os círculos SEM sobreposição — o roteamento por proximidade (`TriadBoss.on_hit`)
# não tem zona ambígua. A cabeça principal é 20px de sprite de largura (=80 de
# tela), então 34 é levemente apertado; as laterais são 15 (=60), e 28 é
# levemente generoso. A folga vai para o lado das laterais de propósito: elas são
# o alvo obrigatório da Fase 1, e o erro deve favorecer o jogador.
CROWN_HEAD_RADIUS: float = 8.5 * PIXEL_SCALE  # 34
SIDE_HEAD_RADIUS: float = 7.0 * PIXEL_SCALE  # 28

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


# ── Carga de sprites ──────────────────────────────────────────────────────────
# Cache de classe: os 12 PNGs são carregados e escalados UMA vez por processo.
# `get_image` já memoiza a leitura do disco; o que memoizamos aqui é o
# `transform.scale`, que de outro modo rodaria a cada instância de boss.
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

    def frame(self, index: int, attacking: bool, white: bool = False) -> pygame.Surface | None:
        if attacking:
            hit = self.white_attack if white else self.attack
            if hit is not None:
                return hit
        pool = self.white_idle if white else self.idle
        if not pool:
            return None
        return pool[index % len(pool)]


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

    sprites = PartSprites(
        idle=tuple(idle),
        attack=attack,
        white_idle=tuple(_whiten(f) for f in idle),
        white_attack=_whiten(attack) if attack is not None else None,
    )
    _part_cache[part] = sprites
    return sprites
