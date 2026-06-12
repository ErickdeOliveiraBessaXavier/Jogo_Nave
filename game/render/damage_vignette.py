"""Vinheta de dano — feedback de HUD ao receber impacto.

Sobreposição vermelha concentrada nas **bordas** da tela (centro livre, para não
atrapalhar o combate), no estilo "screen damage" de FPS com leitura arcade. Tem
dois modos bem separados:

  - **flash de impacto** (transiente): a cada hit sobe rápido até um pico e
    decai **suavemente até zero** — sem oscilação residual. É só feedback
    momentâneo; terminado o decaimento, a tela volta ao normal. Acompanha
    rachaduras de energia curtas nas extremidades;
  - **alerta crítico** (contínuo, exceção): ativo **apenas** quando o jogador
    está no limite (1 vida restante). Aí sim as bordas pulsam lenta e
    continuamente para comunicar perigo iminente. Acima do limite crítico não
    há nenhum estado permanente — só o flash transiente.

Contratos (CLAUDE.md): a cena chama `trigger()`/`update()` (mutação no update);
`draw()` só lê estado e desenha (§3). A vinheta-base é pré-renderizada e cacheada
por tamanho; o desenho por frame é uma única passada com `set_alpha` blitando só
as 4 bandas de borda (§7), com early-out quando não há nada visível.
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
    MARGIN_FRAC = 0.14          # fração de min(w,h) ocupada pela borda (resto = centro livre)
    COLOR: Tuple[int, int, int] = (205, 35, 35)
    EDGE_FALLOFF = 2.2          # expoente: quanto maior, mais a cor "cola" na borda

    # Intensidade (alpha de borda)
    FLASH_ALPHA = 200           # contribuição do flash no auge de um hit
    CRITICAL_ALPHA = 100        # contribuição do pulso de alerta a 1 vida
    EDGE_ALPHA_MAX = 232        # teto para nunca tampar totalmente a borda

    # Envelope do flash (attack-decay limpo, sem oscilação)
    FLASH_ATTACK = 0.05         # subida rápida (s)
    FLASH_DECAY = 0.34          # constante de decaimento (s)
    FLASH_STRENGTH = 0.9        # pico do flash de um hit normal

    # Pulso do alerta crítico (lento e contínuo)
    CRITICAL_PULSE_SPEED = 2.4  # rad/s — período ~2.6 s

    def __init__(self) -> None:
        self._size: Tuple[int, int] = (0, 0)
        self._base: pygame.Surface | None = None
        self._bands: List[pygame.Rect] = []

        self._flash = 0.0
        self._flash_age = 0.0
        self._critical = False
        self._time = 0.0
        self._cracks: List[Dict[str, object]] = []

    # ── API da cena ─────────────────────────────────────────────────────────
    def trigger(self, damage: int = 1) -> None:
        """Dispara o flash de impacto (feedback momentâneo). `damage` reforça
        levemente a intensidade de golpes maiores; não há mais amplificação por
        vida baixa — o estado crítico é tratado só pelo pulso contínuo."""
        strength = min(1.2, self.FLASH_STRENGTH + 0.2 * max(0, damage - 1))
        self._flash = max(self._flash, strength)
        self._flash_age = 0.0
        self._spawn_cracks(strength)

    def update(self, dt: float, critical: bool) -> None:
        """`critical` = jogador no limite (1 vida): libera o pulso de alerta
        contínuo. Acima disso, só o flash transiente decai e some."""
        self._time += dt
        self._critical = critical

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
        """Attack-decay limpo: sobe até o pico e decai suave até zero, sem
        pulsação — o flash é puramente momentâneo."""
        if self._flash <= 0.0:
            return 0.0
        a = self._flash_age
        if a < self.FLASH_ATTACK:
            e = a / self.FLASH_ATTACK
        else:
            e = math.exp(-(a - self.FLASH_ATTACK) / self.FLASH_DECAY)
        return self._flash * e

    def _critical_env(self) -> float:
        """Pulso lento e contínuo, só quando crítico. Nunca chega a zero (mantém
        um brilho de perigo de base que respira para cima)."""
        if not self._critical:
            return 0.0
        pulse01 = 0.5 + 0.5 * math.sin(self._time * self.CRITICAL_PULSE_SPEED)
        return 0.35 + 0.65 * pulse01  # 0.35 → 1.0

    # ── Render (§3: só lê estado) ───────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        flash = self._flash_env()
        edge_a = flash * self.FLASH_ALPHA + self._critical_env() * self.CRITICAL_ALPHA
        if edge_a < 2.0 and not self._cracks:
            return

        self._ensure_base(surface.get_size())
        base = self._base
        if base is None:
            return

        if edge_a >= 2.0:
            a = int(min(self.EDGE_ALPHA_MAX, edge_a))
            # Uma passada: `set_alpha` modula o per-pixel-alpha do gradiente no
            # próprio blit (SDL2). Blita só as 4 bordas — o centro é transparente,
            # então a tela inteira desperdiçaria pixels por frame (§7).
            base.set_alpha(a)
            for r in self._bands:
                surface.blit(base, r, r)

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

        # As 4 bandas de borda que contêm todo o gradiente (centro = transparente).
        # `draw` blita só estas regiões em vez da tela inteira.
        inner_h = max(0, h - 2 * margin)
        self._bands = [
            pygame.Rect(0, 0, w, margin),                      # topo
            pygame.Rect(0, h - margin, w, margin),             # base
            pygame.Rect(0, margin, margin, inner_h),           # esquerda
            pygame.Rect(w - margin, margin, margin, inner_h),  # direita
        ]

    def _spawn_cracks(self, strength: float) -> None:
        """Rachaduras de energia ancoradas nas 4 bordas, apontando para dentro."""
        self._cracks = []
        w, h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        # Rachaduras decorativas escalam pela Qualidade Visual (o flash de dano
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
