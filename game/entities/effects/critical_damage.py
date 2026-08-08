"""Fogo e fumaça de quem está prestes a cair — reutilizável por qualquer boss.

Quando a vida cruza um limiar, o alvo passa a soltar pequenas explosões (círculos
quentes estourando) e fumaça (esferas translúcidas em cinzas claros e escuros). A
intensidade **rampa** conforme a vida desce: perto do limiar é um estalo
ocasional; perto de zero é fogo contínuo. É o que faz o efeito dizer "quanto
falta" sem número na tela.

Uso — o host compõe e repassa dados; o efeito não conhece boss nenhum (§1):

    self.critical_fx = CriticalDamageFX()                       # __init__

    self.critical_fx.update(dt, self.health / self.max_health,  # update()
                            self.body_area())

    self.critical_fx.draw(surface, off_x, off_y)                # draw()

Nada aqui lê atributo de entidade: a vida entra como RAZÃO (0..1) e a região de
emissão como `pygame.Rect`. Um boss de geometria irregular passa o rect que
quiser — menor que o corpo para concentrar o fogo no casco, ou o rect de uma
parte específica para queimar só ela.

**Composição e não `EventBus`** (§2 vs §9): o barramento é para reações
DESACOPLADAS a fatos pontuais ("morreu", "levou dano"). Isto é um visual
CONTÍNUO derivado do estado próprio da entidade a cada frame — mesma natureza do
`ShipRenderer`/`ShipPowerups`, que são componentes compostos na fachada. Um
evento por frame só para redesenhar seria ruído no barramento.
"""

import math
import random
from typing import List, Sequence, Tuple

import pygame

from ...core.config import config as Config
from ...core.fire_timer import carry_interval
from ...core.visual_quality import visual_quality

Color = Tuple[int, int, int]

# Explosões: rampa quente do vermelho ao amarelo. O núcleo de cada estouro sai
# sempre mais claro que a borda — é o que lê como "estourando" e não como bolha.
DEFAULT_BURST_COLORS: Tuple[Color, ...] = (
    (255, 70, 35),
    (255, 120, 40),
    (255, 165, 45),
)
DEFAULT_BURST_CORE: Color = (255, 230, 130)

# Fumaça: cinzas claros e escuros misturados. A variação é o que dá volume —
# uma cinza só vira mancha chapada.
DEFAULT_SMOKE_COLORS: Tuple[Color, ...] = (
    (205, 205, 212),
    (160, 160, 168),
    (105, 105, 114),
    (65, 65, 72),
)

# Buffer com alpha por pixel, compartilhado por TODAS as partículas de todos os
# efeitos vivos. Alocar uma Surface por partícula por frame é exatamente o que
# §7 proíbe; `pygame.draw.circle` direto na tela não aplica transparência.
# Mesmo desenho do `implosion_pulse`.
_alpha_scratch: pygame.Surface | None = None


def _get_alpha_scratch(size: int) -> pygame.Surface:
    """Buffer quadrado de pelo menos `size` px, realocado só quando cresce."""
    global _alpha_scratch
    if _alpha_scratch is None or _alpha_scratch.get_width() < size:
        _alpha_scratch = pygame.Surface((size, size), pygame.SRCALPHA)
    return _alpha_scratch


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def area_from_box(
    x: float,
    y: float,
    w: float,
    h: float,
    inset: float = 0.22,
    clip_to_screen: bool = False,
) -> pygame.Rect:
    """Área de emissão a partir da caixa do corpo, encolhida por `inset`.

    Atalho para o caso comum. Sprites de boss são silhuetas arredondadas dentro
    de uma caixa retangular: emitir na caixa CHEIA acende fogo nos cantos vazios,
    fora do desenho. O padrão de 22% mantém o fogo sobre o casco.

    `clip_to_screen` recorta pela resolução lógica. É o que bosses grandes
    demais para a tela precisam (SlimeBoss e GiantMeteorBoss ficam com a maior
    parte do corpo ACIMA do topo): sem o recorte, a maioria das partículas
    nasceria fora da vista e o efeito pareceria fraco justamente em quem tem o
    maior corpo.

    Não use `self.rect` como fonte sem olhar: vários bosses devolvem um rect
    fora da tela quando não podem levar dano (`can_take_damage`), e o efeito
    precisa da caixa real. Passe `x/y/w/h` crus.
    """
    area = pygame.Rect(int(x), int(y), int(w), int(h)).inflate(
        int(-w * inset), int(-h * inset)
    )
    if clip_to_screen:
        area = area.clip(
            pygame.Rect(0, 0, Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        )
    return area


class _Burst:
    """Círculo quente que abre e some. Vida curta — é um estalo, não uma chama."""

    __slots__ = ("x", "y", "radius", "max_radius", "life", "max_life", "color")

    def __init__(
        self, x: float, y: float, max_radius: float, max_life: float, color: Color
    ) -> None:
        self.x = x
        self.y = y
        self.radius = max_radius * 0.25
        self.max_radius = max_radius
        self.life = max_life
        self.max_life = max_life
        self.color = color


class _Smoke:
    """Esfera translúcida que sobe, incha e esmaece."""

    __slots__ = (
        "x", "y", "vx", "vy", "radius", "growth",
        "life", "max_life", "color", "alpha",
    )

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        radius: float,
        growth: float,
        max_life: float,
        color: Color,
        alpha: int,
    ) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        self.growth = growth
        self.life = max_life
        self.max_life = max_life
        self.color = color
        self.alpha = alpha


class CriticalDamageFX:
    """Efeito de dano crítico: estouros quentes + fumaça, com intensidade em rampa.

    Instancie um por entidade. `update` decide o que emitir a partir da razão de
    vida; `draw` só desenha (§3).
    """

    # Vida (0..1) a partir da qual o efeito começa. Acima disso: nada.
    THRESHOLD: float = 0.30

    # Cadência: intervalo no limiar (FAR) → intervalo com a vida zerada (NEAR).
    BURST_INTERVAL_FAR: float = 0.55
    BURST_INTERVAL_NEAR: float = 0.13
    SMOKE_INTERVAL_FAR: float = 0.22
    SMOKE_INTERVAL_NEAR: float = 0.07

    # Tetos de partículas vivas (escalados pela Qualidade Visual).
    MAX_BURSTS: int = 16
    MAX_SMOKE: int = 44

    BURST_RADIUS: Tuple[float, float] = (7.0, 17.0)
    BURST_LIFE: Tuple[float, float] = (0.18, 0.34)

    SMOKE_RADIUS: Tuple[float, float] = (5.0, 11.0)
    SMOKE_GROWTH: Tuple[float, float] = (10.0, 22.0)  # px/s
    SMOKE_RISE: Tuple[float, float] = (-38.0, -15.0)  # px/s (negativo = sobe)
    SMOKE_DRIFT: float = 18.0  # px/s lateral, para os dois lados
    SMOKE_ALPHA: Tuple[int, int] = (55, 125)
    SMOKE_FADE_IN: float = 0.15  # fração da vida usada para aparecer

    def __init__(
        self,
        threshold: float | None = None,
        burst_colors: Sequence[Color] = DEFAULT_BURST_COLORS,
        burst_core: Color = DEFAULT_BURST_CORE,
        smoke_colors: Sequence[Color] = DEFAULT_SMOKE_COLORS,
        scale: float = 1.0,
    ) -> None:
        """`scale` engorda raios e velocidades — bosses maiores pedem fogo maior.

        `threshold` sobrescreve o limiar da classe (um boss de vida curta pode
        querer começar a fumegar mais cedo).
        """
        self.threshold = self.THRESHOLD if threshold is None else threshold
        self.burst_colors = tuple(burst_colors)
        self.burst_core = burst_core
        self.smoke_colors = tuple(smoke_colors)
        self.scale = scale

        self._bursts: List[_Burst] = []
        self._smoke: List[_Smoke] = []
        self._burst_timer = 0.0
        self._smoke_timer = 0.0
        self._intensity = 0.0

    # ── Consulta ────────────────────────────────────────────────────────────
    @property
    def intensity(self) -> float:
        """0.0 no limiar → 1.0 com a vida zerada. Fora do limiar, 0.0."""
        return self._intensity

    @property
    def emitting(self) -> bool:
        """Está gerando partículas neste momento."""
        return self._intensity > 0.0

    @property
    def has_particles(self) -> bool:
        """Ainda há algo na tela (mesmo já sem emitir)."""
        return bool(self._bursts or self._smoke)

    def clear(self) -> None:
        """Apaga tudo na hora (troca de fase, reinício)."""
        self._bursts.clear()
        self._smoke.clear()
        self._burst_timer = 0.0
        self._smoke_timer = 0.0
        self._intensity = 0.0

    # ── Update ──────────────────────────────────────────────────────────────
    def update(
        self, dt: float, health_ratio: float, area: pygame.Rect | None
    ) -> None:
        """Avança o efeito. `health_ratio` em 0..1; `area` é onde emitir."""
        self._intensity = self._ramp(health_ratio)

        # Área vazia = corpo inteiro fora da tela (o `clip_to_screen` do
        # `area_from_box` devolve um rect degenerado). Emitir ali empilharia
        # partículas num ponto da borda.
        if area is not None and (area.width <= 0 or area.height <= 0):
            area = None

        if self._intensity > 0.0 and area is not None:
            self._emit(dt, area)
        else:
            # Sem emissão o relógio não acumula dívida: quem volta a fumegar
            # (revive, cura) recomeça a cadência, não dispara uma rajada.
            self._burst_timer = 0.0
            self._smoke_timer = 0.0

        # As partículas vivas terminam a animação mesmo depois de o alvo parar de
        # emitir (ou morrer) — senão o fogo sumiria num corte seco.
        self._advance(dt)

    def _ramp(self, health_ratio: float) -> float:
        if self.threshold <= 0.0:
            return 0.0
        ratio = min(1.0, max(0.0, health_ratio))
        if ratio >= self.threshold:
            return 0.0
        return min(1.0, (self.threshold - ratio) / self.threshold)

    def _emit(self, dt: float, area: pygame.Rect) -> None:
        i = self._intensity

        # §14: a sobra do frame é PRESERVADA (`carry_interval`). Reatribuir o
        # intervalo cheio faria o período real virar um número inteiro de frames
        # e o efeito render menos que o configurado.
        self._burst_timer -= dt
        if self._burst_timer <= 0.0:
            self._burst_timer = carry_interval(
                self._burst_timer,
                _lerp(self.BURST_INTERVAL_FAR, self.BURST_INTERVAL_NEAR, i),
            )
            if len(self._bursts) < visual_quality.particles(self.MAX_BURSTS):
                self._spawn_burst(area)

        self._smoke_timer -= dt
        if self._smoke_timer <= 0.0:
            self._smoke_timer = carry_interval(
                self._smoke_timer,
                _lerp(self.SMOKE_INTERVAL_FAR, self.SMOKE_INTERVAL_NEAR, i),
            )
            if len(self._smoke) < visual_quality.smoke(self.MAX_SMOKE):
                self._spawn_smoke(area)

    def _spawn_burst(self, area: pygame.Rect) -> None:
        lo, hi = self.BURST_RADIUS
        self._bursts.append(
            _Burst(
                x=random.uniform(area.left, area.right),
                y=random.uniform(area.top, area.bottom),
                max_radius=random.uniform(lo, hi) * self.scale,
                max_life=random.uniform(*self.BURST_LIFE),
                color=random.choice(self.burst_colors),
            )
        )

    def _spawn_smoke(self, area: pygame.Rect) -> None:
        lo, hi = self.SMOKE_RADIUS
        self._smoke.append(
            _Smoke(
                x=random.uniform(area.left, area.right),
                y=random.uniform(area.top, area.bottom),
                vx=random.uniform(-self.SMOKE_DRIFT, self.SMOKE_DRIFT) * self.scale,
                vy=random.uniform(*self.SMOKE_RISE) * self.scale,
                radius=random.uniform(lo, hi) * self.scale,
                growth=random.uniform(*self.SMOKE_GROWTH) * self.scale,
                max_life=random.uniform(0.7, 1.5),
                color=random.choice(self.smoke_colors),
                alpha=random.randint(*self.SMOKE_ALPHA),
            )
        )

    def _advance(self, dt: float) -> None:
        """Avança e compacta as duas listas in-place (§6), sem alocar cópia."""
        bursts = self._bursts
        w = 0
        for b in bursts:
            b.life -= dt
            if b.life > 0.0:
                # Abre rápido e desacelera: `1-(1-p)^2` dá o estalo.
                p = 1.0 - b.life / b.max_life
                b.radius = b.max_radius * (0.25 + 0.75 * (1.0 - (1.0 - p) ** 2))
                bursts[w] = b
                w += 1
        del bursts[w:]

        smoke = self._smoke
        w = 0
        for s in smoke:
            s.life -= dt
            if s.life > 0.0:
                s.x += s.vx * dt
                s.y += s.vy * dt
                s.radius += s.growth * dt
                # Desacelera enquanto sobe — fumaça perde impulso.
                s.vx *= 1.0 - min(1.0, 0.9 * dt)
                s.vy *= 1.0 - min(1.0, 0.6 * dt)
                smoke[w] = s
                w += 1
        del smoke[w:]

    # ── Render (§3: só desenha) ─────────────────────────────────────────────
    def draw(
        self, surface: pygame.Surface, off_x: float = 0.0, off_y: float = 0.0
    ) -> None:
        """Fumaça primeiro (fundo), estouros por cima (frente)."""
        for s in self._smoke:
            p = 1.0 - s.life / s.max_life
            # Aparece rápido e some devagar: nascer opaco denuncia o spawn.
            fade = p / self.SMOKE_FADE_IN if p < self.SMOKE_FADE_IN else 1.0 - p
            alpha = int(s.alpha * max(0.0, min(1.0, fade)))
            if alpha > 0:
                self._blit_circle(
                    surface, s.x + off_x, s.y + off_y, s.radius, s.color, alpha
                )

        for b in self._bursts:
            p = 1.0 - b.life / b.max_life
            alpha = int(255 * (1.0 - p * p))  # segura o brilho e cai no fim
            if alpha <= 0:
                continue
            bx, by = b.x + off_x, b.y + off_y
            self._blit_circle(surface, bx, by, b.radius, b.color, alpha)
            core_r = b.radius * 0.45
            if core_r >= 1.0:
                self._blit_circle(
                    surface, bx, by, core_r, self.burst_core, min(255, alpha + 40)
                )

    @staticmethod
    def _blit_circle(
        surface: pygame.Surface,
        x: float,
        y: float,
        radius: float,
        color: Color,
        alpha: int,
    ) -> None:
        r = int(math.ceil(radius))
        if r < 1:
            return
        size = r * 2 + 2
        buf = _get_alpha_scratch(size)
        area = pygame.Rect(0, 0, size, size)
        # `fill` com RGBA zera o alpha POR PIXEL. `set_alpha` não serviria: é
        # alpha de superfície, persiste no objeto e o próximo consumidor do
        # buffer herdaria o valor (a armadilha documentada em §17).
        buf.fill((0, 0, 0, 0), area)
        pygame.draw.circle(buf, (*color, alpha), (size // 2, size // 2), r)
        surface.blit(buf, (int(x) - size // 2, int(y) - size // 2), area)
