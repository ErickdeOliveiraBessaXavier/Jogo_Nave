"""Cerca elétrica da arena — mecânica EXCLUSIVA da Fase 3 (segmentação) do
Metropolis Overlord.

Quatro orbs azuis FIXOS nos cantos da arena (responsivos à resolução, §12),
ligados em LOOP por feixes de energia VIVOS. Não atacam nem se movem: são um
LIMITE perigoso que encolhe o espaço seguro — encostar (feixe ou orb) causa dano.
Transmite que o boss fragmentou a arena e assumiu o controle do campo.

Cada `FenceBeam` é um `BossLaser` (vive em `em.boss_lasers`): ganha a colisão com
a nave de graça (`Collisions.laser_vs_ship` → `clipline` sobre `get_collision_line`),
sem plumbing de colisão novo. Cada feixe desenha também o orb do seu canto de
ORIGEM — os 4 feixes do loop cobrem os 4 cantos.

Visual "vivo" (§3: animação avança só no `update`; o flicker usa random no draw —
crepitar puramente visual, padrão já usado nos drones/beams):
  - oscilação/tremulação perpendicular ao feixe (senóide + jitter);
  - nós de energia correndo de canto a canto;
  - intensidade luminosa pulsante;
  - pequenos arcos elétricos ocasionais saltando do feixe.

Tudo escala pela resolução (espessura, raio do orb, amplitude, alcance dos arcos)
via `core.scale` — mesma experiência em qualquer resolução.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame

from ....core.scale import scaled
from ....core.visual_quality import visual_quality as vq
from ...projectiles.boss_laser import BossLaser

# Paleta azul-elétrica da cerca (coerente com a energia da Cidade Neon).
_DEEP = (28, 90, 200)
_MID = (80, 170, 255)
_BRIGHT = (190, 235, 255)
_CORE = (255, 255, 255)


def _si(value: float) -> int:
    """Pixel do design base escalado pela resolução, em int (larguras de linha)."""
    return max(1, int(round(scaled(value))))


def _col(base: Tuple[int, int, int], f: float) -> Tuple[int, int, int]:
    """Cor escalada pela intensidade f∈[0,1] (clampada)."""
    f = max(0.0, min(1.0, f))
    return (int(base[0] * f), int(base[1] * f), int(base[2] * f))


# Estágios do ciclo de vida (animação cinematográfica de entrada/saída).
_FORM = "form"      # ativação: orbs surgem, acumulam, raios conectam parcialmente
_ACTIVE = "active"  # barreira viva plena (3–5 raios convergentes)
_FADE = "fade"      # colapso: raios falham, arcos dissipam, orbs implodem, resíduo


class FenceBeam(BossLaser):
    """Um lado da cerca: POUCOS raios (2–3) em ZIGUE-ZAGUE angular entre dois cantos +
    o orb do canto de origem. Elegante e LEGÍVEL, não uma parede poluída — estrutura
    estável (a conexão entre orbs nunca some) com o traçado interno mudando a cada
    poucos frames. Ciclo cinematográfico: ativação (FORM) → barreira plena (ACTIVE) →
    colapso elegante (FADE).

    Colisão = linha reta entre os cantos (centerline herdada), ativa SÓ no ACTIVE
    (telegrafo na entrada e dissipação na saída não machucam — `self.w` é zerado)."""

    BASE_W = 9.0       # espessura de colisão base (px @720p) — escala por resolução
    ORB_R = 16.0       # raio do orb de canto base (px @720p)
    FORM_DUR = 1.0     # ativação curta porém perceptível
    FADE_DUR = 0.9     # colapso elegante (perdendo sustentação)

    # Marca esta classe como origem do debuff elétrico (paralisia). A cena descobre
    # via getattr (§5: class attribute, não isinstance) e aplica o MESMO sistema da
    # Torreta Orbital (`Ship.apply_electric_debuff`) — sem status paralelo novo.
    applies_paralysis: bool = True

    def __init__(self, ax: float, ay: float, bx: float, by: float) -> None:
        super().__init__(ax, ay, bx, by)
        self._base_w = scaled(self.BASE_W)
        self.w = 0.0                   # colisão começa OFF (telegrafo de ativação)
        self.max_w = self._base_w
        self._orb_r = scaled(self.ORB_R)
        self._anim = 0.0
        self._seed = random.uniform(0.0, math.tau)  # cada lado anima fora de sincronia

        # FSM de ciclo de vida.
        self._stage = _FORM
        self._stage_t = 0.0

        # Direção, normal e amostragem (zigue-zague perpendicular ao feixe).
        dx, dy = bx - ax, by - ay
        self._len = math.hypot(dx, dy) or 1.0
        self._nx, self._ny = -dy / self._len, dx / self._len
        # POUCOS segmentos longos = kinks angulares CLAROS (zigue-zague legível), não
        # uma curva suave cheia de pontos.
        self._segs = max(6, int(self._len / scaled(72.0)))
        self._spread = scaled(22.0)   # separação entre as FAIXAS dos raios (espaço)
        self._wob_amp = scaled(9.0)   # amplitude do zigue-zague (kinks visíveis)
        self._ray_w = _si(2)

        # APENAS 2–3 raios bem construídos (legibilidade > quantidade). Cada um numa
        # FAIXA própria (bias) p/ não se sobreporem; amplitude/brilho próprios.
        n = random.randint(2, 3)
        self._rays: List[dict] = []
        for i in range(n):
            base = (i / (n - 1) * 2.0 - 1.0) if n > 1 else 0.0  # faixa relativa [-1,1]
            self._rays.append({
                "bias": base * self._spread,            # deslocamento fixo da faixa (px)
                "amp": random.uniform(0.7, 1.1),        # escala do zigue-zague deste raio
                "bright": random.uniform(0.8, 1.0),
                "connect": random.uniform(0.12, 0.5),   # FORM: quando conecta
                "fail": random.uniform(0.1, 0.5),       # FADE: quando falha
            })

        # Trajetórias de zigue-zague CACHEADAS: regeneradas a cada poucos frames (não
        # por frame) → estrutura estável, traçado interno mudando (sem flicker). §3:
        # a mutação fica no `update`; o `draw` só lê os caminhos.
        self._ray_paths: List[List[Tuple[int, int]]] = []
        self._regen_paths()
        self._path_t = 0.05  # segura o traçado inicial por uma janela antes do 1º regen

        # Partículas (faíscas convergentes na entrada / resíduo disperso na saída):
        # [x, y, vx, vy, life, maxlife, hot].
        self._particles: List[list] = []
        self._spark_t = 0.0

    # ── Controle de fim (boss derrotado): colapso elegante em vez de sumir ─────
    def begin_fade(self) -> None:
        if self._stage != _FADE and not self.dead:
            self._stage, self._stage_t = _FADE, 0.0
            self.w = 0.0  # limite não machuca mais (boss já era)

    # get_collision_line() herdado: linha reta canto→canto (centerline da colisão).

    def update(self, dt: float) -> None:
        if self.dead:
            return
        self._anim += dt
        self._stage_t += dt
        # Regenera o traçado do zigue-zague só a cada poucos frames (estável, sem
        # piscar) — a estrutura/conexão permanecem; só os kinks internos mudam.
        self._path_t -= dt
        if self._path_t <= 0.0:
            self._path_t = 0.05
            self._regen_paths()
        if self._stage == _FORM:
            self.w = 0.0  # telegrafo: a cerca ainda não machuca
            self._spawn_form_sparks(dt)
            if self._stage_t >= self.FORM_DUR:
                self._stage, self._stage_t = _ACTIVE, 0.0
        elif self._stage == _ACTIVE:
            self.w = self._base_w  # barreira perigosa ativa
        else:  # _FADE
            self.w = 0.0
            self._spawn_fade_particles(dt)
            if self._stage_t >= self.FADE_DUR and not self._particles:
                self.dead = True  # colapso completo + resíduo dissipado
        self._update_particles(dt)

    # ── Progressões do ciclo (lidas pelo draw, §3) ─────────────────────────────
    def _intensity(self) -> float:
        if self._stage == _FORM:
            return 0.2 + 0.8 * min(1.0, self._stage_t / self.FORM_DUR)  # sobe
        if self._stage == _ACTIVE:
            return 1.0
        return max(0.0, 1.0 - self._stage_t / self.FADE_DUR)            # cai

    def _orb_scale(self) -> float:
        if self._stage == _FORM:
            return min(1.0, (self._stage_t / self.FORM_DUR) / 0.4)  # surge nos 40% iniciais
        if self._stage == _ACTIVE:
            return 1.0
        fp = self._stage_t / self.FADE_DUR
        return max(0.0, 1.0 - max(0.0, (fp - 0.45) / 0.55))         # implode na 2ª metade

    def _ray_reach(self, ray: dict) -> float:
        """Fração conectada do raio (0=desligado, 1=canto-a-canto)."""
        if self._stage == _FORM:
            fp = self._stage_t / self.FORM_DUR
            return max(0.0, min(1.0, (fp - ray["connect"]) / 0.3))  # cresce após o threshold
        if self._stage == _ACTIVE:
            return 1.0
        fp = self._stage_t / self.FADE_DUR
        return max(0.0, min(1.0, 1.0 - (fp - ray["fail"]) / 0.3))   # encolhe (conexão falha)

    # ── Partículas ─────────────────────────────────────────────────────────────
    def _spawn_form_sparks(self, dt: float) -> None:
        """Faíscas CONVERGINDO para o orb (acúmulo de energia na ativação)."""
        self._spark_t -= dt
        if self._spark_t > 0.0:
            return
        self._spark_t = 0.07  # cadência mais esparsa (menos poluição)
        for _ in range(vq.particles(1)):
            ang = random.uniform(0.0, math.tau)
            d = self._orb_r * random.uniform(1.5, 3.2)
            sx, sy = self.x + math.cos(ang) * d, self.y + math.sin(ang) * d
            life = random.uniform(0.18, 0.34)
            self._particles.append([sx, sy, (self.x - sx) / life, (self.y - sy) / life,
                                    life, life, random.random() < 0.4])

    def _spawn_fade_particles(self, dt: float) -> None:
        """Resíduo DISPERSANDO do orb conforme ele colapsa (perda de sustentação).

        Gera só DURANTE o colapso do orb (45%→100% do fade); ao fim, para de emitir
        para o resíduo existente dissipar e o feixe poder morrer (senão nunca esvazia)."""
        fp = self._stage_t / self.FADE_DUR
        if fp < 0.45 or fp >= 1.0:
            return
        self._spark_t -= dt
        if self._spark_t > 0.0:
            return
        self._spark_t = 0.07
        for _ in range(vq.particles(1)):
            ang = random.uniform(0.0, math.tau)
            spd = scaled(random.uniform(20.0, 80.0))
            life = random.uniform(0.25, 0.5)
            self._particles.append([self.x, self.y, math.cos(ang) * spd, math.sin(ang) * spd,
                                    life, life, random.random() < 0.5])

    def _update_particles(self, dt: float) -> None:
        w = 0
        for p in self._particles:
            p[4] -= dt
            if p[4] > 0.0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                self._particles[w] = p
                w += 1
        del self._particles[w:]

    # ── Traçado do zigue-zague (montado no update, §3) ─────────────────────────
    def _make_zigzag(self, ray: dict) -> List[Tuple[int, int]]:
        """Polilinha ANGULAR em zigue-zague (canto→canto) de um raio. O lado ALTERNA a
        cada vértice (sawtooth elétrico), com magnitude aleatória e quebras eventuais
        do padrão (nunca repetitivo). Envelope sin(πt) zera nas pontas → presa EXATA
        nos orbs (a conexão nunca some). `bias` mantém o raio na sua faixa (sem sobrepor)."""
        ax, ay = self.x, self.y
        dx, dy = self.target_x - ax, self.target_y - ay
        nx, ny = self._nx, self._ny
        segs = self._segs
        a_amp = self._wob_amp * ray["amp"]
        bias = ray["bias"]
        pts: List[Tuple[int, int]] = []
        sign = random.choice((-1.0, 1.0))
        for i in range(segs + 1):
            t = i / segs
            if i == 0 or i == segs:
                off = 0.0  # ponta presa ao orb → conexão garantida
            else:
                sign = -sign  # zigue-zague: alterna o lado a cada kink
                if random.random() < 0.22:
                    sign = -sign  # quebra o padrão perfeito (irregular)
                mag = a_amp * random.uniform(0.5, 1.0)
                off = (bias + sign * mag) * math.sin(math.pi * t)
            pts.append((int(ax + dx * t + nx * off), int(ay + dy * t + ny * off)))
        return pts

    def _regen_paths(self) -> None:
        self._ray_paths = [self._make_zigzag(ray) for ray in self._rays]

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        intensity = self._intensity()
        pulse = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(self._anim * 4.0 + self._seed))
        glow = intensity * pulse

        # 1) Halo dim ao longo do eixo (a "parede" energética) — só com conexão razoável.
        if intensity > 0.1:
            a = (int(self.x), int(self.y))
            b = (int(self.target_x), int(self.target_y))
            pygame.draw.line(surface, _col(_DEEP, glow * 0.8), a, b, self._ray_w + _si(7))

        # 2) Os POUCOS raios em zigue-zague (traçado cacheado, estável entre regens).
        #    Núcleo CONTÍNUO (sem gaps) → a conexão entre os orbs nunca some. Durante
        #    FORM/FADE, desenha-se só o PREFIXO conectado (cresce/retrai pelos orbs).
        mid_w = self._ray_w + _si(1)
        for ray, path in zip(self._rays, self._ray_paths):
            reach = self._ray_reach(ray)
            if reach <= 0.03 or len(path) < 2:
                continue
            n = len(path)
            last = max(2, int(round(n * reach)))
            pts = path[:last]
            rb = ray["bright"] * glow
            pygame.draw.lines(surface, _col(_MID, rb), False, pts, mid_w)   # corpo
            pygame.draw.lines(surface, _col(_CORE, rb), False, pts, self._ray_w)  # núcleo
            # Ramificação RARA (1 por raio, ocasional) — só na barreira plena.
            if self._stage == _ACTIVE and len(pts) >= 3 and random.random() < 0.05:
                bx, by = pts[random.randint(1, len(pts) - 2)]
                rr = scaled(random.uniform(8.0, 16.0))
                ang = random.uniform(0.0, math.tau)
                br = self._jagged(bx, by, bx + math.cos(ang) * rr, by + math.sin(ang) * rr, segs=2)
                if len(br) >= 2:
                    pygame.draw.lines(surface, _col(_BRIGHT, glow), False, br, 1)

        # 3) Arco SECUNDÁRIO entre dois raios — raro (cintilação pontual, sem poluir).
        if self._stage == _ACTIVE and len(self._ray_paths) >= 2 and random.random() < 0.05:
            pa, pb = random.sample(self._ray_paths, 2)
            k = random.randint(1, min(len(pa), len(pb)) - 2)
            arc = self._jagged(pa[k][0], pa[k][1], pb[k][0], pb[k][1], segs=2)
            if len(arc) >= 2:
                pygame.draw.lines(surface, _col(_BRIGHT, glow), False, arc, 1)

        # 4) Um par de nós de energia percorrendo a estrutura (energizada, discreto).
        if self._stage == _ACTIVE:
            for k in range(vq.particles(2)):
                frac = ((self._anim * 0.3) + k * 0.5 + self._seed * 0.1) % 1.0
                nx = self.x + (self.target_x - self.x) * frac
                ny = self.y + (self.target_y - self.y) * frac
                r = max(2, int(scaled(4.0) * glow))
                pygame.draw.circle(surface, _col(_BRIGHT, glow), (int(nx), int(ny)), r + 1)
                pygame.draw.circle(surface, _CORE, (int(nx), int(ny)), max(1, r - 1))

        # 5) Orb do canto de ORIGEM (surge na entrada, implode na saída).
        self._draw_orb(surface, glow)

        # 6) Partículas (faíscas de acúmulo na entrada / resíduo na saída).
        for p in self._particles:
            f = max(0.0, p[4] / p[5])
            base = _CORE if p[6] else _BRIGHT
            surface.fill(_col(base, f), (int(p[0]), int(p[1]), 2, 2))

    def _draw_orb(self, surface: pygame.Surface, glow: float) -> None:
        sc = self._orb_scale()
        if sc <= 0.02:
            return
        r = self._orb_r * sc
        x, y = int(self.x), int(self.y)
        pygame.draw.circle(surface, _col(_DEEP, glow), (x, y), int(r))
        pygame.draw.circle(surface, _col(_MID, glow), (x, y), int(r * 0.7))
        pygame.draw.circle(surface, _col(_BRIGHT, glow), (x, y), int(r * 0.42))
        core_r = int(r * (0.22 + 0.06 * (0.5 + 0.5 * math.sin(self._anim * 5.0))) + 1)
        pygame.draw.circle(surface, _CORE, (x, y), max(1, core_r))
        # Crepitação saindo do orb (não durante o colapso).
        if self._stage != _FADE and random.random() < 0.3:
            ang = random.uniform(0.0, math.tau)
            d = r * random.uniform(0.9, 1.3)
            pygame.draw.line(surface, _BRIGHT, (x, y),
                             (int(x + math.cos(ang) * d), int(y + math.sin(ang) * d)), 1)

    @staticmethod
    def _jagged(x1: float, y1: float, x2: float, y2: float, segs: int = 3) -> List[Tuple[int, int]]:
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        jit = scaled(4.0)
        pts: List[Tuple[int, int]] = [(int(x1), int(y1))]
        for i in range(1, segs):
            t = i / segs
            off = random.uniform(-jit, jit)
            pts.append((int(x1 + dx * t + nx * off), int(y1 + dy * t + ny * off)))
        pts.append((int(x2), int(y2)))
        return pts


# Inset base (px @720p) do orb a cada borda — escala por resolução. Define a
# "grossura" do anel perigoso que encolhe o espaço seguro (sem punir demais).
FENCE_INSET_BASE: float = 38.0


def build_arena_fence() -> List[FenceBeam]:
    """Cria os 4 lados da cerca em LOOP nos cantos da arena (responsivo à resolução).

    Loop: TL→TR, TR→BR, BR→BL, BL→TL. Cada lado nasce no canto de origem (onde
    desenha seu orb), então os 4 orbs cobrem os 4 cantos. Posições derivam de
    `Config.SCREEN_WIDTH/HEIGHT` (já corretas por resolução) + inset escalado (§12)."""
    from ....core.config import config as Config

    inset = scaled(FENCE_INSET_BASE)
    w, h = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
    tl = (inset, inset)
    tr = (w - inset, inset)
    br = (w - inset, h - inset)
    bl = (inset, h - inset)
    loop = ((tl, tr), (tr, br), (br, bl), (bl, tl))
    return [FenceBeam(a[0], a[1], b[0], b[1]) for a, b in loop]
