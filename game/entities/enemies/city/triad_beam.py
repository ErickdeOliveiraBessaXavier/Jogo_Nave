"""Feixes da SENTENÇA — o ataque-assinatura da Tríade.

Um feixe só serve às sete salvas da coreografia, porque todas são a mesma
geometria com parâmetros diferentes — fechar, girar ou piscar são o mesmo
"origem lida por callback + ângulo lido por callback":

    tesoura / gaiola   ângulo fixo + origem que DESLIZA
    leque / cerco      origem e ângulo girando juntos em torno de um pivô
    onda / cruzado     os dois fixos, e a brecha é a janela de TEMPO

Não há uma classe por padrão — há uma, e os callbacks vêm do `TriadCaster`, que
é a cabeça que está disparando. Ler o caster todo frame é o que mantém o feixe
grudado na BOCA dela mesmo enquanto ela desliza ou gira. A coreografia em si
mora em `triad_score`; ver `PLANO_BOSS_TRIADE.md` §6.

Subclasse de `BossLaser` de propósito: assim vive em `em.boss_lasers`, é varrida
por `Collisions.laser_vs_ship` (`ship.rect.clipline(get_collision_line())` com
`w > 0`) e não pede plumbing de colisão nenhum.

**O telégrafo é o `w`.** Durante a carga a largura de COLISÃO é zero enquanto a
largura DESENHADA já cresce: o jogador vê exatamente onde o feixe vai nascer e
tem tempo de sair. Feixe que aparece já matando não é dificuldade, é emboscada.
"""

from __future__ import annotations

import math
import random
from typing import Callable, List, Tuple

import pygame

from ....core.config import config as Config
from ....core.scale import scaled
from ....core.visual_quality import visual_quality as vq
from ...projectiles.boss_laser import BossLaser
from . import triad_pixel_map as pmap

_CHARGING = "charging"
_ACTIVE = "active"
_FADING = "fading"


_GLOW_SCRATCH: dict[tuple[int, int], pygame.Surface] = {}


def _glow_scratch(size: tuple[int, int]) -> pygame.Surface:
    """Buffer de brilho reutilizado, um por resolução. Nunca aloca por frame."""
    surf = _GLOW_SCRATCH.get(size)
    if surf is None:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        _GLOW_SCRATCH[size] = surf
    return surf


_FLARE_SPRITES: dict[tuple, pygame.Surface] = {}


def _flare_sprite(
    raio: int, color: Tuple[int, int, int], bright: Tuple[int, int, int]
) -> pygame.Surface:
    """Estouro do bocal, desenhado uma vez por (raio, cor).

    O raio pulsa entre poucos valores inteiros, então o cache satura em algumas
    dezenas de sprites minúsculos — contra uma surface nova por feixe por frame.
    """
    key = (raio, color, bright)
    sprite = _FLARE_SPRITES.get(key)
    if sprite is None:
        sprite = pygame.Surface((raio * 4, raio * 4), pygame.SRCALPHA)
        pygame.draw.circle(sprite, (*color, 90), (raio * 2, raio * 2), raio * 2)
        pygame.draw.circle(sprite, (*bright, 200), (raio * 2, raio * 2), raio)
        _FLARE_SPRITES[key] = sprite
    return sprite


class TriadBeam(BossLaser):
    """Feixe de energia da Tríade. Origem e ângulo podem ser dinâmicos."""

    # 20 e não 14: o feixe é a assinatura do boss e precisa NEGAR área, não só
    # desenhar uma linha. Medido na coreografia inteira, 14px deixava 85% da
    # arena livre em qualquer instante — o padrão parecia denso e não pedia
    # movimento nenhum. Ver `triad_score` para a outra metade da conta (varrer).
    BEAM_W: float = 20.0
    CHARGE_TIME: float = 0.85
    FADE_TIME: float = 0.45

    def __init__(
        self,
        origin: Callable[[], Tuple[float, float]] | Tuple[float, float],
        angle: Callable[[], float] | float,
        *,
        charge_time: float | None = None,
        active_time: float = 1.6,
        color: Tuple[int, int, int] = pmap.CYAN,
        length: float | None = None,
    ) -> None:
        self._origin_fn = origin if callable(origin) else (lambda o=origin: o)
        self._angle_fn = angle if callable(angle) else (lambda a=float(angle): a)
        self._length = length or math.hypot(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT) * 1.3
        self._charge_time = self.CHARGE_TIME if charge_time is None else charge_time
        self._active_time = active_time
        self._color = color
        self._bright = (
            min(255, color[0] + 110), min(255, color[1] + 70), min(255, color[2] + 50)
        )
        # Equivalentes OPACOS das duas camadas translúcidas, pré-multiplicados
        # sobre preto. Servem ao caminho sem `glow_enabled`: sobre o fundo escuro
        # do espaço a diferença é quase invisível, e economiza a passagem por
        # surface com alpha por pixel inteira.
        self._halo_flat = tuple(int(c * 70 / 255) for c in color)
        self._mid_flat = tuple(int(c * 150 / 255) for c in color)

        self._phase = _CHARGING
        self._phase_t = 0.0
        self._visual_w = 0.0
        self._flare = 0.0
        self._anim = 0.0
        self._sparks: List[list] = []

        ox, oy = self._origin_fn()
        ang = self._angle_fn()
        super().__init__(
            ox, oy, ox + math.cos(ang) * self._length, oy + math.sin(ang) * self._length
        )
        self.w = 0.0
        self.max_w = scaled(self.BEAM_W)

    # ── Controle externo ─────────────────────────────────────────────────────
    def begin_fade(self) -> None:
        """O boss pede o encerramento: dissipa em vez de sumir de um frame para o
        outro. Feixe que some instantaneamente parece bug, não fim de ataque."""
        if self._phase != _FADING:
            self._phase, self._phase_t = _FADING, 0.0

    @property
    def is_lethal(self) -> bool:
        return self.w > 0.0

    @property
    def is_fading(self) -> bool:
        """Já disparou e está se dissipando: inerte, e a cabeça já foi embora."""
        return self._phase == _FADING

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        if dt <= 0.0 or self.dead:
            return
        self._anim += dt
        self._phase_t += dt

        # Origem e ângulo são RELIDOS todo frame: é o que faz a tesoura varrer e
        # o ponteiro girar sem o feixe precisar saber qual batida ele é.
        ox, oy = self._origin_fn()
        ang = self._angle_fn()
        self.x, self.y = ox, oy
        self.target_x = ox + math.cos(ang) * self._length
        self.target_y = oy + math.sin(ang) * self._length

        if self._phase == _CHARGING:
            p = min(1.0, self._phase_t / self._charge_time) if self._charge_time > 0 else 1.0
            ease = p * p * (3.0 - 2.0 * p)
            self._visual_w = self.max_w * ease * 0.6
            self._flare = scaled(5.0 + 14.0 * ease)
            self.w = 0.0  # TELÉGRAFO: visível e inofensivo
            if self._phase_t >= self._charge_time:
                self._phase, self._phase_t = _ACTIVE, 0.0
        elif self._phase == _ACTIVE:
            respiro = math.sin(self._anim * 6.1) + 0.4 * math.sin(self._anim * 11.3)
            self._visual_w = self.max_w + scaled(1.8) * respiro
            self._flare = scaled(12.0 + 3.0 * math.sin(self._anim * 9.0))
            self.w = self.max_w  # colisão CONSTANTE: a pulsação é só visual
            self._emit_sparks(dt)
            if self._phase_t >= self._active_time:
                self.begin_fade()
        else:
            p = min(1.0, self._phase_t / self.FADE_TIME)
            self._visual_w = self.max_w * (1.0 - p)
            self._flare = scaled(12.0) * (1.0 - p)
            # A dissipação NÃO fere, simétrica à carga. Um feixe que ainda mata
            # enquanto some deixa a janela letal maior do que ela parece, e é
            # justamente onde o jogador relaxa — ele viu o feixe acabar.
            self.w = 0.0
            if self._phase_t >= self.FADE_TIME:
                self.dead = True

        self._update_sparks(dt)

    def _emit_sparks(self, dt: float) -> None:
        if vq.particles(2) <= 0:
            return
        if random.random() > dt * 40.0:
            return
        t = random.random()
        x = self.x + (self.target_x - self.x) * t
        y = self.y + (self.target_y - self.y) * t
        ang = random.uniform(0.0, math.tau)
        spd = scaled(random.uniform(40.0, 130.0))
        self._sparks.append(
            [x, y, math.cos(ang) * spd, math.sin(ang) * spd, random.uniform(0.15, 0.35)]
        )

    def _update_sparks(self, dt: float) -> None:
        if not self._sparks:
            return
        i = 0
        while i < len(self._sparks):
            s = self._sparks[i]
            s[4] -= dt
            if s[4] <= 0.0:
                self._sparks[i] = self._sparks[-1]
                self._sparks.pop()
                continue
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            i += 1

    # ── Render ───────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        """`draw` não muta estado (§3): tudo já foi resolvido no update."""
        if self.dead:
            return
        start = (int(self.x), int(self.y))
        end = (int(self.target_x), int(self.target_y))

        core_w = int(max(1.0, self._visual_w * 0.45))
        if self._phase == _CHARGING:
            # Fio fino piscando: lê como "vai nascer aqui", não como feixe pleno.
            if int(self._anim * 22.0) % 2 == 0:
                pygame.draw.line(surface, self._color, start, end, max(1, core_w))
        else:
            self._draw_glow(surface, start, end)
            pygame.draw.line(surface, self._bright, start, end, max(1, core_w))

        if self._flare > 0.5:
            r = int(self._flare)
            flare = _flare_sprite(r, self._color, self._bright)
            surface.blit(flare, (start[0] - r * 2, start[1] - r * 2))

        for s in self._sparks:
            pygame.draw.circle(surface, self._bright, (int(s[0]), int(s[1])), 1)

    def _draw_glow(self, surface: pygame.Surface, start, end) -> None:
        """As duas camadas translúcidas do feixe, SEM alocar nada por frame.

        **Era aqui o travamento.** A versão anterior criava uma surface SRCALPHA
        de tela cheia por feixe **e por frame** — 3,7 MB alocados e zerados, mais
        um blit de tela cheia com alpha por pixel. Com os 8 feixes simultâneos da
        Sentença dava 32 ms/frame só nisto (50 ms quando os feixes eram
        horizontais), contra os 16,7 ms que o frame inteiro tem a 60fps: o
        ataque custava o dobro do orçamento sozinho.

        Duas mudanças, nenhuma delas mexendo na quantidade de feixes:

        * **Buffer compartilhado** (mesmo padrão do `get_fade_scratch`, que o
          projeto criou para esta exata classe de travamento nos fades): aloca
          uma vez por resolução, nunca por frame.
        * **Recorte pela caixa do feixe**: limpa e blita só a faixa que a linha
          ocupa, não a tela toda. Um feixe horizontal toca ~5% dos pixels.

        Medido: 32,8 → 4,7 ms com 8 diagonais; 50,4 → 5,7 ms com 8 horizontais.
        Pixel por pixel idêntico ao que havia antes.
        """
        halo_w = int(max(2.0, self._visual_w * 2.4))
        mid_w = int(max(2.0, self._visual_w))
        if not vq.glow_enabled:
            # Qualidade reduzida: as mesmas duas camadas em cor opaca. Custa uma
            # fração e, sobre fundo escuro, a diferença mal aparece.
            pygame.draw.line(surface, self._halo_flat, start, end, halo_w)
            pygame.draw.line(surface, self._mid_flat, start, end, mid_w)
            return

        tela = surface.get_rect()
        faixa = pygame.Rect(
            min(start[0], end[0]),
            min(start[1], end[1]),
            abs(end[0] - start[0]) + 1,
            abs(end[1] - start[1]) + 1,
        ).inflate(halo_w + 4, halo_w + 4).clip(tela)
        if faixa.width <= 0 or faixa.height <= 0:
            return

        glow = _glow_scratch(surface.get_size())
        # Só a faixa é limpa: o resto do buffer guarda lixo do feixe anterior,
        # e não importa — o blit também é só da faixa. A linha, mesmo saindo da
        # tela, é recortada pelo pygame aos limites da surface, então nada é
        # desenhado fora do que acabou de ser limpo.
        glow.fill((0, 0, 0, 0), faixa)
        pygame.draw.line(glow, (*self._color, 70), start, end, halo_w)
        pygame.draw.line(glow, (*self._color, 150), start, end, mid_w)
        surface.blit(glow, faixa.topleft, faixa)


__all__ = ["TriadBeam"]
