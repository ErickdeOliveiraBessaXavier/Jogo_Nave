"""Feixe orbital rotativo do Metropolis Overlord — ataque PRINCIPAL da Fase 2.

Três feixes contínuos (um por núcleo/orb) que partem do corpo do boss parado no
centro da arena e GIRAM numa direção (varrendo a tela, obrigando o jogador a se
reposicionar). A DIREÇÃO INICIAL (`base_angle`) de cada feixe é a ESTRUTURAL do seu
núcleo — do centroide do triângulo para fora, passando pela orb (superior p/ cima,
inferiores p/ as pontas da base) — então os três giram preservando a relação de
120°. A velocidade do giro é configurável por `ang_speed` (0.0 = feixe fixo).

É subclasse de `BossLaser` de propósito: assim vive em `em.boss_lasers`, é incluído
pelo filtro `isinstance(laser, BossLaser)` e atinge a nave via
`Collisions.laser_vs_ship` (`ship.rect.clipline(get_collision_line())` com `w > 0`) —
zero plumbing de colisão nova.

Ciclo de vida próprio com apresentação elaborada (estética neon/energética):
  CHARGING — o feixe se CONSTRÓI: energia condensa na origem (flare crescendo +
    cacos convergindo), o feixe materializa de fino→cheio. NÃO causa dano (`w=0`):
    é telégrafo justo da varredura.
  ACTIVE   — feixe pleno girando; flare pulsante na origem, filamentos de distorção
    e faíscas correndo pelo feixe.
  FADING   — o boss pede `begin_fade()` (em vez de matar abrupto): o feixe DISSIPA
    progressivamente (largura encolhe, energia se espalha em partículas, flare
    apaga), depois `.dead=True`.

Cada feixe usa a COR do seu núcleo (cyan/magenta/amber); todos têm a MESMA espessura.
`draw` não muta estado (§3): partículas/flare avançam só no `update`; o flicker dos
filamentos usa random no draw (crepitar puramente visual, padrão já usado nos drones).
"""

from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

import pygame

from ...core.config import config as Config
from ...core.scale import scaled
from ...core.visual_quality import visual_quality as vq
from . import metropolis_overlord_pixel_map as pmap
from ..boss_laser import BossLaser

_CHARGING = "charging"
_ACTIVE = "active"
_FADING = "fading"


class MetropolisOrbitalBeam(BossLaser):
    """Feixe neon contínuo (cor do núcleo) que GIRA a partir de uma direção inicial
    estrutural; `ang_speed` controla a velocidade do giro (0.0 = fixo)."""

    BEAM_W: float = 13.0          # largura/raio de colisão do feixe — IGUAL p/ os 3
    ANG_SPEED: float = 0.42       # rad/s — giro LENTO/cadenciado (legível, antecipável)
    CHARGE_TIME: float = 0.7      # s do build-up (telegrafo, sem dano)
    FADE_TIME: float = 0.6        # s da dissipação (perdendo energia)

    _CORE = (255, 255, 255)       # núcleo branco-quente comum

    def __init__(
        self,
        origin_x: float,
        origin_y: float,
        base_angle: float,
        theme: str = "cyan",
        aggressiveness_multiplier: float = 1.0,
        length: float | None = None,
        ang_speed: float | None = None,
        origin_provider: Optional[Callable[[], Tuple[float, float]]] = None,
    ) -> None:
        if length is None:
            length = math.hypot(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT) * 1.2
        self._length = length
        # Âncora ao orb emissor: se fornecida, a origem é RELIDA a cada frame (o feixe
        # acompanha o orb/boss e nunca memoriza posição fixa no mundo). Sem provider,
        # usa a origem fixa passada (compat. com outros usos).
        self._origin_provider = origin_provider
        if origin_provider is not None:
            origin_x, origin_y = origin_provider()
        self._origin_x = float(origin_x)
        self._origin_y = float(origin_y)
        self._angle = float(base_angle)
        # `ang_speed=0.0` → feixe de direção FIXA (descarga estrutural). None → giro
        # padrão escalado pela agressividade (compat. com outros usos).
        if ang_speed is None:
            self._ang_speed = self.ANG_SPEED * max(0.5, aggressiveness_multiplier)
        else:
            self._ang_speed = ang_speed
        # Multiplicador de giro dinâmico (Fase 2): o boss o aumenta gradualmente a cada
        # mina recebida (sobrecarga/urgência crescente). 1.0 = velocidade base.
        self._spin_mult = 1.0

        # Cores do núcleo: glow vívido (bright), camada média (mid) e versão dim p/ halo.
        _dark, self._mid, self._glow = pmap.PLASMA_THEMES.get(theme, pmap.PLASMA_THEMES["cyan"])
        self._glow_dim = tuple(int(c * 0.45) for c in self._glow)

        # Espessura/colisão do feixe escala pela resolução (§12): presença e
        # legibilidade consistentes. Vira instância → todo `self.BEAM_W` segue.
        self.BEAM_W = scaled(self.BEAM_W)

        # Ciclo de vida próprio.
        self._phase = _CHARGING
        self._phase_t = 0.0
        self._visual_w = 0.0         # largura desenhada (cresce/encolhe)
        self._flare = 0.0            # raio do flare de energia na origem
        self._anim = 0.0             # relógio p/ pulsos
        self._spark_timer = 0.0
        # Partículas energéticas: [x, y, vx, vy, life, maxlife, hot].
        self._particles: List[list] = []

        tx = origin_x + math.cos(self._angle) * length
        ty = origin_y + math.sin(self._angle) * length
        super().__init__(origin_x, origin_y, tx, ty)
        self.w = 0.0                 # colisão: nula até terminar a carga
        self.max_w = self.BEAM_W

    # ── Controle externo ────────────────────────────────────────────────────
    def set_spin_multiplier(self, mult: float) -> None:
        """Ajusta o multiplicador de velocidade de giro (Fase 2: ramp por minas)."""
        self._spin_mult = max(0.0, float(mult))

    def begin_fade(self) -> None:
        """Pedido do boss p/ encerrar: dissipa progressivamente em vez de sumir."""
        if self._phase != _FADING:
            self._phase = _FADING
            self._phase_t = 0.0

    # ── Update (cinemática + apresentação; §3: muta só aqui) ─────────────────
    def update(self, dt: float) -> None:
        if dt <= 0.0 or self.dead:
            return
        self._anim += dt
        self._phase_t += dt

        # Âncora dinâmica: relê a posição ATUAL do orb emissor (acompanha o boss).
        if self._origin_provider is not None:
            self._origin_x, self._origin_y = self._origin_provider()

        # Giro contínuo a partir da direção estrutural (também durante carga/dissipação).
        # `_spin_mult` cresce com as minas recebidas (Fase 2): urgência crescente.
        self._angle += self._ang_speed * self._spin_mult * dt
        self.x = self._origin_x
        self.y = self._origin_y
        self.target_x = self._origin_x + math.cos(self._angle) * self._length
        self.target_y = self._origin_y + math.sin(self._angle) * self._length

        if self._phase == _CHARGING:
            p = min(1.0, self._phase_t / self.CHARGE_TIME)
            ease = p * p * (3.0 - 2.0 * p)             # smoothstep
            self._visual_w = self.BEAM_W * ease
            self._flare = scaled(6.0 + 16.0 * ease)
            self.w = 0.0                               # telégrafo: sem dano ainda
            self._emit_charge_particles(dt, p)
            if self._phase_t >= self.CHARGE_TIME:
                self._phase, self._phase_t = _ACTIVE, 0.0
        elif self._phase == _ACTIVE:
            # Pulsação VISUAL contínua: espessura oscila de leve (a colisão `self.w`
            # fica CONSTANTE — pulsação não altera a jogabilidade). Soma de duas senóides
            # p/ um respirar orgânico, não mecânico.
            breathe = math.sin(self._anim * 6.3) + 0.4 * math.sin(self._anim * 11.7)
            self._visual_w = self.BEAM_W + scaled(1.7) * breathe
            self._flare = scaled(13.0 + 3.5 * math.sin(self._anim * 9.0))
            self.w = self.BEAM_W
            self._emit_active_sparks(dt)
        else:  # _FADING
            p = min(1.0, self._phase_t / self.FADE_TIME)
            self._visual_w = self.BEAM_W * (1.0 - p)
            self._flare = scaled(13.0) * (1.0 - p)
            self.w = self._visual_w
            self._emit_fade_particles(dt, p)
            if self._phase_t >= self.FADE_TIME:
                self.dead = True

        self._update_particles(dt)

    # ── Partículas ───────────────────────────────────────────────────────────
    def _emit_charge_particles(self, dt: float, p: float) -> None:
        """Cacos convergindo p/ a origem (energia condensando)."""
        self._spark_timer -= dt
        if self._spark_timer > 0.0:
            return
        self._spark_timer = 0.03
        for _ in range(vq.particles(2)):
            ang = random.uniform(0.0, math.tau)
            d = (1.2 - p) * random.uniform(30.0, 80.0) + 18.0
            sx = self._origin_x + math.cos(ang) * d
            sy = self._origin_y + math.sin(ang) * d
            spd = d / 0.3
            self._particles.append([
                sx, sy, -math.cos(ang) * spd, -math.sin(ang) * spd,
                0.3, 0.3, random.random() < 0.5,
            ])

    def _emit_active_sparks(self, dt: float) -> None:
        """Faíscas correndo p/ fora ao longo do feixe (energia escorrendo)."""
        self._spark_timer -= dt
        if self._spark_timer > 0.0:
            return
        self._spark_timer = 0.05
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        for _ in range(vq.particles(2)):
            t = random.uniform(0.05, 0.55) * self._length
            bx = self._origin_x + ca * t
            by = self._origin_y + sa * t
            perp = random.uniform(-1.0, 1.0)
            spd = random.uniform(60.0, 160.0)
            self._particles.append([
                bx, by,
                ca * spd * 0.3 - sa * perp * spd, sa * spd * 0.3 + ca * perp * spd,
                random.uniform(0.18, 0.4), 0.4, random.random() < 0.4,
            ])

    def _emit_fade_particles(self, dt: float, p: float) -> None:
        """Energia se espalhando enquanto o feixe perde força."""
        self._spark_timer -= dt
        if self._spark_timer > 0.0:
            return
        self._spark_timer = 0.025
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        for _ in range(vq.particles(3)):
            t = random.uniform(0.0, 0.6) * self._length
            bx = self._origin_x + ca * t
            by = self._origin_y + sa * t
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(40.0, 140.0)
            self._particles.append([
                bx, by, math.cos(ang) * spd, math.sin(ang) * spd,
                random.uniform(0.2, 0.5), 0.5, random.random() < 0.5,
            ])

    def _update_particles(self, dt: float) -> None:
        ps = self._particles
        w = 0
        for s in ps:
            s[4] -= dt
            if s[4] > 0.0:
                s[0] += s[2] * dt
                s[1] += s[3] * dt
                ps[w] = s
                w += 1
        del ps[w:]

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        start = (int(self.x), int(self.y))
        end = (int(self.target_x), int(self.target_y))
        vw = self._visual_w

        # Pulsação de BRILHO (suave/contínua) só na fase ativa: o glow respira entre
        # ~78% e 100% + um leve jitter (sensação de feixe sendo constantemente alimentado).
        if self._phase == _ACTIVE:
            pulse = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(self._anim * 5.5))
            pulse *= random.uniform(0.96, 1.04)  # instabilidade energética sutil
        else:
            pulse = 1.0
        glow = tuple(min(255, int(c * pulse)) for c in self._glow)

        if vw >= 1.0:
            ca = math.cos(self._angle)
            sa = math.sin(self._angle)
            # Halo largo (dim) → glow (cor do núcleo, pulsante) → núcleo branco-quente.
            pygame.draw.line(surface, self._glow_dim, start, end, int(vw) + 10)
            pygame.draw.line(surface, glow, start, end, int(vw) + 4)
            pygame.draw.line(surface, self._CORE, start, end, max(1, int(vw) - 3))

            # Raiz mais luminosa: intensifica a origem (extremidade visível do feixe).
            root_len = scaled(70.0)
            root = (int(self._origin_x + ca * root_len), int(self._origin_y + sa * root_len))
            pygame.draw.line(surface, glow, start, root, int(vw) + 7)
            pygame.draw.line(surface, self._CORE, start, root, max(1, int(vw) - 1))

            # Energia PERCORRENDO o feixe (nós brilhantes correndo p/ fora) — só ativo.
            if self._phase == _ACTIVE:
                self._draw_energy_pulses(surface, ca, sa, vw)

            # Filamentos de distorção energética (flicker visual — crepitar, §3).
            if self._phase != _FADING or random.random() < 0.6:
                self._draw_filament(surface)

        # Partículas (cacos/faíscas de energia).
        for s in self._particles:
            a = max(0.0, s[4] / s[5])
            base = self._CORE if s[6] else self._glow
            col = (int(base[0] * a), int(base[1] * a), int(base[2] * a))
            surface.fill(col, (int(s[0]), int(s[1]), 2, 2))

        # Flare de energia na origem (condensa na carga, pulsa ativo, apaga no fade).
        fr = int(self._flare)
        if fr > 0:
            ox, oy = int(self._origin_x), int(self._origin_y)
            pygame.draw.circle(surface, self._glow_dim, (ox, oy), fr + 4)
            pygame.draw.circle(surface, glow, (ox, oy), fr)
            pygame.draw.circle(surface, self._CORE, (ox, oy), max(1, fr // 2))

    def _draw_energy_pulses(self, surface: pygame.Surface, ca: float, sa: float, vw: float) -> None:
        """Nós de energia correndo da origem p/ fora (feixe sendo alimentado)."""
        span = math.hypot(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        r = max(2, int(vw * 0.7))
        for k in range(3):
            frac = ((self._anim * 0.5) + k / 3.0) % 1.0
            d = frac * span
            x = int(self._origin_x + ca * d)
            y = int(self._origin_y + sa * d)
            pygame.draw.circle(surface, self._glow, (x, y), r + 2)
            pygame.draw.circle(surface, self._CORE, (x, y), max(1, r - 1))

    def _draw_filament(self, surface: pygame.Surface) -> None:
        """Polilinha em ziguezague ao longo do feixe (distorção elétrica)."""
        x1, y1 = self._origin_x, self._origin_y
        x2, y2 = self.target_x, self.target_y
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        segs = 7
        amp = scaled(5.0) + self._visual_w * 0.5
        pts = [(int(x1), int(y1))]
        for i in range(1, segs):
            t = i / segs
            off = random.uniform(-amp, amp)
            pts.append((int(x1 + dx * t + nx * off), int(y1 + dy * t + ny * off)))
        pts.append((int(x2), int(y2)))
        col = self._CORE if random.random() < 0.5 else self._glow
        pygame.draw.lines(surface, col, False, pts, 1)
