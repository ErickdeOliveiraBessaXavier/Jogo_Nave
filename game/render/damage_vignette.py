"""Vinheta de dano — feedback de HUD ao receber impacto.

Sobreposição vermelha concentrada nas **bordas** da tela (centro praticamente
livre, para não atrapalhar o combate), no estilo "screen damage" de FPS, mas com
leitura arcade. Combina dois sinais:

  - **flash de impacto** (transiente): pico rápido + decaimento suave a cada hit,
    com uma pulsação curta e rachaduras de energia nas extremidades. Mais forte
    em danos maiores e quando a vida já está baixa;
  - **tensão de vida baixa** (persistente): tom vermelho sutil e pulsante nas
    bordas que cresce conforme a vida cai — pressão visual sem texto/aviso.

Contratos (CLAUDE.md): a cena chama `trigger()`/`update()` (mutação no update);
`draw()` só lê estado e desenha (§3). A vinheta-base é pré-renderizada e cacheada
por tamanho; o desenho por frame reusa um scratch (§7), e faz early-out quando
não há nada visível.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import pygame

from ..core.config import config as Config
from ..core.visual_quality import visual_quality


class DamageVignette:
    # Geometria/cor
    MARGIN_FRAC = 0.26          # fração de min(w,h) ocupada pela vinheta (resto = centro livre)
    COLOR: Tuple[int, int, int] = (205, 35, 35)
    EDGE_FALLOFF = 2.2          # expoente: quanto maior, mais a cor "cola" na borda

    # Intensidade
    EDGE_ALPHA_HIT = 200        # alpha de borda no auge de um hit (antes do clamp)
    EDGE_ALPHA_LOW_HP = 72      # alpha de borda da tensão persistente (vida baixa)
    EDGE_ALPHA_MAX = 232        # teto para nunca tampar totalmente a borda

    # Envelope do flash
    FLASH_ATTACK = 0.05         # subida rápida (s)
    FLASH_DECAY = 0.24          # constante de decaimento (s)
    LOW_HP_THRESHOLD = 0.5      # abaixo disso começa a tensão persistente

    def __init__(self) -> None:
        self._size: Tuple[int, int] = (0, 0)
        self._base: pygame.Surface | None = None
        self._scratch: pygame.Surface | None = None

        self._flash = 0.0
        self._flash_age = 0.0
        self._health_fraction = 1.0
        self._time = 0.0
        self._cracks: List[Dict[str, object]] = []

    # ── API da cena ─────────────────────────────────────────────────────────
    def trigger(self, damage: int = 1, health_fraction: float = 1.0) -> None:
        """Dispara o flash de impacto. `damage` reforça a intensidade; vida baixa
        também — um hit perto de morrer 'dói' mais visualmente."""
        health_fraction = max(0.0, min(1.0, health_fraction))
        base = 0.58 + 0.20 * max(0, damage - 1)
        low = (
            0.0
            if health_fraction >= self.LOW_HP_THRESHOLD
            else (self.LOW_HP_THRESHOLD - health_fraction) / self.LOW_HP_THRESHOLD
        )
        strength = min(1.2, base + 0.34 * low)
        self._flash = max(self._flash, strength)
        self._flash_age = 0.0
        self._health_fraction = health_fraction
        self._spawn_cracks(strength)

    def update(self, dt: float, health_fraction: float) -> None:
        self._time += dt
        self._health_fraction = max(0.0, min(1.0, health_fraction))

        if self._flash > 0.0:
            self._flash_age += dt
            if self._flash_age > self.FLASH_ATTACK + self.FLASH_DECAY * 4.0:
                self._flash = 0.0

        if self._cracks:
            for c in self._cracks:
                c["life"] = float(c["life"]) - dt  # type: ignore[arg-type]
            self._cracks = [c for c in self._cracks if float(c["life"]) > 0.0]  # type: ignore[arg-type]

    # ── Envelopes ───────────────────────────────────────────────────────────
    def _flash_env(self) -> float:
        if self._flash <= 0.0:
            return 0.0
        a = self._flash_age
        if a < self.FLASH_ATTACK:
            e = a / self.FLASH_ATTACK
        else:
            e = math.exp(-(a - self.FLASH_ATTACK) / self.FLASH_DECAY)
        pulse = 0.82 + 0.18 * math.sin(a * 46.0)  # pulsação curta pós-impacto
        return self._flash * e * pulse

    def _tension(self) -> float:
        hf = self._health_fraction
        if hf >= self.LOW_HP_THRESHOLD:
            return 0.0
        t = (self.LOW_HP_THRESHOLD - hf) / self.LOW_HP_THRESHOLD
        breath = 0.55 + 0.45 * abs(math.sin(self._time * 3.2))
        return t * breath

    # ── Render (§3: só lê estado) ───────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        flash = self._flash_env()
        tension = self._tension()
        edge_a = flash * self.EDGE_ALPHA_HIT + tension * self.EDGE_ALPHA_LOW_HP
        if edge_a < 2.0 and not self._cracks:
            return

        self._ensure_base(surface.get_size())
        base, scratch = self._base, self._scratch
        if base is None or scratch is None:
            return

        if edge_a >= 2.0:
            a = int(min(self.EDGE_ALPHA_MAX, edge_a))
            scratch.blit(base, (0, 0))
            # Escala o alpha do gradiente por `a` sem mexer no RGB (MULT).
            scratch.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(scratch, (0, 0))

        if self._cracks:
            self._draw_cracks(surface, flash)

    def _draw_cracks(self, surface: pygame.Surface, flash: float) -> None:
        intensity = max(flash, 0.3)
        for c in self._cracks:
            life = float(c["life"])  # type: ignore[arg-type]
            max_life = float(c["max"])  # type: ignore[arg-type]
            ratio = life / max_life if max_life > 0 else 0.0
            # Cintilação: pula o desenho conforme envelhece (interferência tech).
            if random.random() > ratio * intensity:
                continue
            pts = c["pts"]  # type: ignore[assignment]
            col = (255, 255, 255) if random.random() < 0.5 else (255, 95, 95)
            pygame.draw.lines(surface, col, False, pts, 1)  # type: ignore[arg-type]

    # ── Construção/caches ───────────────────────────────────────────────────
    def _ensure_base(self, size: Tuple[int, int]) -> None:
        if self._base is not None and self._size == size:
            return
        self._size = size
        w, h = size
        self._scratch = pygame.Surface(size, pygame.SRCALPHA)

        base = pygame.Surface(size, pygame.SRCALPHA)
        margin = max(1, int(min(w, h) * self.MARGIN_FRAC))
        cr, cg, cb = self.COLOR
        # Bordas retangulares aninhadas: alpha máx. na borda externa → 0 no limite
        # interno (centro totalmente livre). Concentração controlada por EDGE_FALLOFF.
        for i in range(margin):
            t = i / margin
            a = int(255 * (1.0 - t) ** self.EDGE_FALLOFF)
            if a <= 0:
                continue
            rect = pygame.Rect(i, i, w - 2 * i, h - 2 * i)
            if rect.width <= 0 or rect.height <= 0:
                break
            pygame.draw.rect(base, (cr, cg, cb, a), rect, 1)
        self._base = base

    def _spawn_cracks(self, strength: float) -> None:
        """Rachaduras de energia ancoradas nas 4 bordas, apontando para dentro."""
        self._cracks = []
        w, h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        # Rachaduras decorativas escalam pela Qualidade Visual (a vinheta de dano
        # em si permanece — é feedback de gameplay, não puro enfeite).
        n = visual_quality.electric(int(4 + strength * 6))
        for _ in range(n):
            side = random.randint(0, 3)
            if side == 0:
                x, y, nx, ny = random.uniform(0, w), 0.0, 0.0, 1.0
            elif side == 1:
                x, y, nx, ny = random.uniform(0, w), float(h), 0.0, -1.0
            elif side == 2:
                x, y, nx, ny = 0.0, random.uniform(0, h), 1.0, 0.0
            else:
                x, y, nx, ny = float(w), random.uniform(0, h), -1.0, 0.0

            tx, ty = -ny, nx  # tangente para o jitter lateral
            length = random.uniform(20.0, 58.0) * (0.6 + strength)
            steps = random.randint(2, 4)
            pts: List[Tuple[float, float]] = [(x, y)]
            px, py = x, y
            for _s in range(steps):
                px += nx * (length / steps) + tx * random.uniform(-13.0, 13.0)
                py += ny * (length / steps) + ty * random.uniform(-13.0, 13.0)
                pts.append((px, py))
            life = random.uniform(0.12, 0.22)
            self._cracks.append({"pts": pts, "life": life, "max": life})
