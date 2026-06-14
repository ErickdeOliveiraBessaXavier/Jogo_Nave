"""Metropolis Overlord — primeiro chefe nativo do tema CITY (nível 30).

Fortaleza voadora cyberpunk com luta em três fases. Utiliza o sistema de
`Layered Pixel-Maps` para destruição visual progressiva.

Contratos (CLAUDE.md): adere ao BossProtocol (§5, despacho polimórfico);
`draw()` só desenha (§3); projéteis/adds roteados por `BossUpdateResult`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ...core.config import config as Config
from ..boss_hit_mixin import BossHitMixin
from ..boss_laser import BossLaser
from .metropolis_projectiles import NeonBurstShot
from .metropolis_sentinel import MetropolisSentinel
from . import metropolis_overlord_pixel_map as pmap

if TYPE_CHECKING:
    from ...systems.boss_context import BossUpdateContext, BossUpdateResult

# Estados da FSM.
_INTRO_RISE = "intro_rise"
_INTRO_DESCEND = "intro_descend"
_PHASE1 = "phase1_sentinels"
_PHASE2 = "phase2_armor"
_PHASE3 = "phase3_core"

# Caracteres do pixel-map que compõem a CARCAÇA externa destrutível (placas que
# se fragmentam ao tomar dano, revelando o frame interno já desenhado). O
# contorno neon ("E") e o frame escuro ("G") persistem.
_SHELL_CHARS = ("P",)

# Gradientes de plasma dos 3 núcleos (escuro → brilho), neon de alto contraste.
# Cada núcleo tem uma cor própria para variedade e contraste — coerentes com a
# paleta da Cidade (cyan / magenta / âmbar).
_PLASMA_THEMES: dict[str, tuple] = {
    "cyan": ((4, 26, 54), (0, 150, 205), (150, 255, 255)),
    "magenta": ((46, 4, 52), (205, 25, 165), (255, 165, 240)),
    "amber": ((54, 28, 0), (225, 120, 15), (255, 232, 150)),
}


def _grad3(stops: tuple, v: float) -> tuple:
    """Interpola um gradiente de 3 paradas (dark → mid → bright) em v∈[0,1]."""
    if v <= 0.0:
        return stops[0]
    if v >= 1.0:
        return stops[2]
    if v < 0.5:
        t, a, b = v / 0.5, stops[0], stops[1]
    else:
        t, a, b = (v - 0.5) / 0.5, stops[1], stops[2]
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class _ArmorFragment:
    """Pedaço de blindagem que se desprende da carcaça e voa (cosmético).

    Vive no boss (não em `em.*`): é animação, não causa dano e não segura
    progressão. Atualizado no `update` e desenhado no `draw` (§3).
    """

    __slots__ = ("x", "y", "vx", "vy", "angle", "spin", "size", "color", "life", "max_life")

    def __init__(self, x: float, y: float, vx: float, vy: float, size: float, color: tuple) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.angle = random.uniform(0.0, 360.0)
        self.spin = random.uniform(-360.0, 360.0)
        self.size = size
        self.color = color
        self.max_life = random.uniform(0.6, 1.2)
        self.life = self.max_life

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.vy += 620.0 * dt  # gravidade
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        alpha = max(0.0, min(1.0, self.life / self.max_life))
        s = max(2, int(self.size))
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.fill((*self.color, int(255 * alpha)))
        rot = pygame.transform.rotate(surf, self.angle)
        surface.blit(rot, (int(self.x - rot.get_width() / 2), int(self.y - rot.get_height() / 2)))


class MetropolisOverlordBoss(BossHitMixin):
    """Reator triangular da Cidade: carcaça destrutível + 3 núcleos de plasma."""

    BOSS_TYPE_NAME: str = "metropolis_overlord"
    is_boss: bool = True

    WIDTH: int = 240
    HEIGHT: int = 200
    DEFAULT_HEALTH: int = 1200

    RISE_SPEED: float = 40.0
    DESCENT_SPEED: float = 120.0

    # Frações de HP que marcam as camadas de blindagem.
    ARMOR_MID_FRACTION: float = 0.75
    ARMOR_INTERNAL_FRACTION: float = 0.45
    CORE_FRACTION: float = 0.20

    # Escala do pixel map (24 col * 10 = 240px ; 20 lin * 10 = 200px).
    PIXEL_SCALE = 10

    # Os TRÊS núcleos energéticos, em arranjo triangular estável (tipo triforce)
    # dentro do triângulo. (rel_x, rel_y, rel_r, tema_de_plasma, fase_de_animação)
    # rel_* são frações da caixa do boss; rel_r é fração da LARGURA.
    SPHERE_DEFS: tuple = (
        (0.50, 0.40, 0.135, "cyan", 0.0),
        (0.32, 0.72, 0.135, "magenta", 2.0),
        (0.68, 0.72, 0.135, "amber", 4.0),
    )

    def __init__(
        self,
        x: float,
        y: float,
        health: int | None = None,
        difficulty_multiplier: float = 1.0,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.x = float(x)
        self.y = float(Config.SCREEN_HEIGHT + 50)
        self.target_y = float(y)

        base = health if health is not None else self.DEFAULT_HEALTH
        self.max_health = int(base * difficulty_multiplier)
        self.health = self.max_health
        self.dead = False

        self.aggressiveness_multiplier = max(0.5, aggressiveness_multiplier)
        self.state = _INTRO_RISE
        self.anim_time = 0.0

        # Movimento e Intro.
        self.speed = 80.0
        self.direction = 1
        self._intro_scale = 0.4
        self._intro_alpha = 100

        # Fase 1: Sentinelas.
        self._sentinels: List[MetropolisSentinel] = []
        self._sentinels_spawned = False

        # Fase 2: Atiradores.
        self._leak_timer = 1.5

        # Fase 3: Núcleo.
        self._beam_state = "idle"
        self._beam_timer = 4.0
        self._beam_charge_t = 0.0
        self._beam_target = (0.0, 0.0)
        self._add_timer = 7.0
        self._regen_timer = 15.0
        self._phase3_entered = False

        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Destruição por camadas: células da carcaça externa (P/H) ordenadas de
        # FORA para dentro (placas externas caem primeiro — "descascando a
        # blindagem"). À medida que o HP cai, vão sendo removidas e viram fragmentos.
        self._shell_cells: List[tuple[int, int, str]] = [
            (r, c, ch)
            for r, row in enumerate(pmap.PIXEL_MAP)
            for c, ch in enumerate(row)
            if ch in _SHELL_CHARS
        ]
        ccx, ccy = pmap.PIXEL_COLS / 2.0, pmap.PIXEL_ROWS / 2.0
        self._shell_order: List[tuple[int, int, str]] = sorted(
            self._shell_cells,
            key=lambda cell: -((cell[1] - ccx) ** 2 + (cell[0] - ccy) ** 2),
        )
        self._removed_set: set[tuple[int, int]] = set()
        self._removed_idx: int = 0
        self._fragments: List[_ArmorFragment] = []

    @property
    def rect(self) -> pygame.Rect:
        if not self.can_take_damage() or self.state in (_INTRO_RISE, _INTRO_DESCEND):
            return pygame.Rect(-1000, -1000, 0, 0)
        self._rect.update(int(self.x), int(self.y), self.w, self.h)
        return self._rect

    def collision_circle(self) -> tuple[float, float, float]:
        if not self.can_take_damage():
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def can_take_damage(self) -> bool:
        return self.state in (_PHASE2, _PHASE3) and not self.dead

    def take_damage(self, amount: int) -> None:
        if not self.can_take_damage():
            return
        self.health -= amount
        if self.health <= 0:
            self.health, self.dead = 0, True

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def _hp_fraction(self) -> float:
        return self.health / self.max_health if self.max_health else 0.0

    def _armor_tier(self) -> int:
        frac = self._hp_fraction
        if frac > self.ARMOR_MID_FRACTION: return 0
        if frac > self.ARMOR_INTERNAL_FRACTION: return 1
        return 2

    def _update_shell_destruction(self) -> None:
        """Remove placas da carcaça conforme o HP cai (de fora para dentro).

        Cada placa que sai vira um fragmento. Roda só quando o corpo é vulnerável
        (Fase 2/3); a geração de fragmentos fica no update, nunca no draw (§3).
        """
        if self.state not in (_PHASE2, _PHASE3):
            return
        span = 1.0 - self.CORE_FRACTION
        # progresso 0 (HP cheio) → 1 (HP no limiar do núcleo): toda carcaça caiu.
        progress = 0.0 if span <= 0 else (1.0 - self._hp_fraction) / span
        progress = max(0.0, min(1.0, progress))
        target = int(progress * len(self._shell_order))
        while self._removed_idx < target:
            r, c, ch = self._shell_order[self._removed_idx]
            self._removed_idx += 1
            self._removed_set.add((r, c))
            self._spawn_armor_fragment(r, c, ch)

    def _spawn_armor_fragment(self, r: int, c: int, ch: str) -> None:
        px = self.x + (c + 0.5) * self.PIXEL_SCALE
        py = self.y + (r + 0.5) * self.PIXEL_SCALE
        bcx, bcy = self._center
        ang = math.atan2(py - bcy, px - bcx)
        spd = random.uniform(70.0, 200.0)
        vx = math.cos(ang) * spd + random.uniform(-50.0, 50.0)
        vy = math.sin(ang) * spd - random.uniform(40.0, 160.0)  # tende a saltar p/ cima
        color = pmap.COLORS.get(ch, (200, 205, 215))
        self._fragments.append(
            _ArmorFragment(px, py, vx, vy, self.PIXEL_SCALE, color)
        )

    def _update_fragments(self, dt: float) -> None:
        frags = self._fragments
        write = 0
        for f in frags:
            f.update(dt)
            if not f.dead:
                frags[write] = f
                write += 1
        del frags[write:]

    def update_boss(self, dt: float, ctx: "BossUpdateContext") -> "BossUpdateResult":
        from ...systems.boss_context import BossUpdateResult
        result = BossUpdateResult()
        if dt <= 0.0: return result
        self.anim_time += dt
        self._update_shell_destruction()
        self._update_fragments(dt)

        if self.state == _INTRO_RISE:
            self.y -= self.RISE_SPEED * dt
            if self.y <= 150:
                self.state, self.y = _INTRO_DESCEND, -self.h
        elif self.state == _INTRO_DESCEND:
            self._intro_scale = min(1.0, self._intro_scale + 1.2 * dt)
            self._intro_alpha = min(255, self._intro_alpha + 400 * dt)
            self.y += self.DESCENT_SPEED * dt
            if self.y >= self.target_y:
                self.y, self.state, self._intro_scale, self._intro_alpha = self.target_y, _PHASE1, 1.0, 255
        elif self.state == _PHASE1:
            self._update_phase1(dt, ctx)
        elif self.state == _PHASE2:
            player_y = ctx.player_y if ctx.player_y is not None else Config.SCREEN_HEIGHT / 2
            self._update_phase2(dt, ctx.player_x, player_y, result)
        elif self.state == _PHASE3:
            player_y = ctx.player_y if ctx.player_y is not None else Config.SCREEN_HEIGHT / 2
            self._update_phase3(dt, ctx, ctx.player_x, player_y, result)

        return result

    def _update_phase1(self, dt: float, ctx: "BossUpdateContext") -> None:
        if not self._sentinels_spawned:
            self._spawn_sentinels(ctx)
            self._sentinels_spawned = True
        self.x += math.sin(self.anim_time) * 15.0 * dt
        if self._sentinels and all(s.dead for s in self._sentinels):
            self._sentinels, self.state = [], _PHASE2

    def _spawn_sentinels(self, ctx: "BossUpdateContext") -> None:
        roles = ["neon", "missile", "laser", "emp"]
        for i, role in enumerate(roles):
            s = MetropolisSentinel(role=role, start_t=i * 0.25, aggressiveness_multiplier=self.aggressiveness_multiplier, activation_delay=1.0 + i * 0.5)
            self._sentinels.append(s)
            ctx.entity_manager.enemies.append(s)

    def _update_phase2(self, dt: float, px: float, py: float, result: "BossUpdateResult") -> None:
        tier = self._armor_tier()
        self._patrol(dt, 1.0 + 0.5 * tier)
        self._leak_timer -= dt
        if self._leak_timer <= 0.0:
            self._leak_timer = max(0.3, (1.5 - 0.4 * tier) / self.aggressiveness_multiplier)
            cx, cy = self._center
            for k in range(1 + tier):
                result.spawned_enemies.append(NeonBurstShot(cx, cy, px + (k - tier/2) * 80, py))
        if self._hp_fraction <= self.CORE_FRACTION: self.state = _PHASE3

    def _update_phase3(self, dt: float, ctx: "BossUpdateContext", px: float, py: float, result: "BossUpdateResult") -> None:
        if not self._phase3_entered:
            self._phase3_entered, self._beam_state, self._beam_timer = True, "idle", 1.5
        self._patrol(dt, 1.8)
        if self._beam_state == "idle":
            self._beam_timer -= dt
            if self._beam_timer <= 0.0:
                self._beam_state, self._beam_charge_t, self._beam_target = "charging", 1.4, (px, py)
        elif self._beam_state == "charging":
            self._beam_charge_t -= dt
            self._beam_target = (self._beam_target[0] + (px - self._beam_target[0]) * 4 * dt, self._beam_target[1] + (py - self._beam_target[1]) * 4 * dt)
            if self._beam_charge_t <= 0.0:
                result.new_lasers.append(self._fire_city_beam())
                self._beam_state, self._beam_timer = "idle", 4.0 / self.aggressiveness_multiplier
        self._add_timer -= dt
        if self._add_timer <= 0.0:
            self._add_timer = 7.0
            self._spawn_city_drones(ctx)
        self._regen_timer -= dt
        if self._regen_timer <= 0.0:
            self._regen_timer, role = 15.0, random.choice(["neon", "missile", "laser", "emp"])
            ctx.entity_manager.enemies.append(MetropolisSentinel(role=role, start_t=random.random()))

    def _fire_city_beam(self) -> BossLaser:
        cx, cy = self._center
        tx, ty = self._beam_target
        ang = math.atan2(ty - cy, tx - cx)
        return BossLaser(cx, cy, cx + math.cos(ang) * 2000, cy + math.sin(ang) * 2000, lifetime=1.2)

    def _spawn_city_drones(self, ctx: "BossUpdateContext") -> None:
        from .city_drone import CityDrone
        cx, _ = self._center
        for dx in (-80, 80):
            ctx.entity_manager.enemies.append(CityDrone(cx + dx, self.y + self.h, aggressiveness_multiplier=self.aggressiveness_multiplier))

    def _patrol(self, dt: float, speed_mult: float) -> None:
        self.x += self.speed * speed_mult * self.direction * dt
        if self.x <= 20: self.x, self.direction = 20, 1
        elif self.x + self.w >= Config.SCREEN_WIDTH - 20: self.x, self.direction = Config.SCREEN_WIDTH - self.w - 20, -1

    def draw(self, surface: pygame.Surface) -> None:
        draw_w, draw_h = int(self.w * self._intro_scale), int(self.h * self._intro_scale)
        draw_x, draw_y = int(self.x + (self.w - draw_w) / 2), int(self.y + (self.h - draw_h) / 2)
        
        if self.state in (_INTRO_RISE, _INTRO_DESCEND):
            temp_surf = pygame.Surface((draw_w, draw_h), pygame.SRCALPHA)
            self._draw_pixel_map(temp_surf, 0, 0, self.PIXEL_SCALE * self._intro_scale)
            temp_surf.set_alpha(int(self._intro_alpha))
            surface.blit(temp_surf, (draw_x, draw_y))
        else:
            self._draw_pixel_map(surface, draw_x, draw_y, self.PIXEL_SCALE)

        # Fragmentos da carcaça (por cima do corpo).
        for frag in self._fragments:
            frag.draw(surface)

        if self.can_take_damage():
            self._draw_health_bar(surface)

    def _draw_pixel_map(self, surface: pygame.Surface, x: float, y: float, scale: float) -> None:
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 4.0)
        fast_pulse = 0.5 + 0.5 * math.sin(self.anim_time * 12.0)
        cell = int(scale + 1)

        # 1) CAMADA INTERNA — frame escuro (G) + contorno neon (E), sempre
        #    desenhada (o que está "embaixo" já visível quando a placa cai).
        for r, row in enumerate(pmap.PIXEL_MAP_INTERNAL):
            for c, char in enumerate(row):
                if char == ".": continue
                color = pmap.COLORS.get(char, (255, 0, 255))
                if char == "E":  # contorno neon pulsante (silhueta)
                    color = pmap.EDGE_GLOW if pulse > 0.6 else pmap.COLORS["E"]
                pygame.draw.rect(surface, color, (int(x + c * scale), int(y + r * scale), cell, cell))

        # 2) CARCAÇA EXTERNA (placas P) por cima — menos as já fragmentadas.
        #    Conforme o HP cai, células saem de `_removed_set` revelando o frame.
        for r, c, char in self._shell_cells:
            if (r, c) in self._removed_set:
                continue
            pygame.draw.rect(
                surface, pmap.COLORS["P"],
                (int(x + c * scale), int(y + r * scale), cell, cell),
            )

        # 3) NÚCLEOS DE PLASMA — o foco visual, por cima da carcaça.
        self._draw_plasma_cores(surface, x, y, scale)

        # Mira do Laser
        if self.state == _PHASE3 and self._beam_state == "charging":
            tx, ty = self._beam_target
            blink = 0.5 + 0.5 * math.sin(self.anim_time * 40.0)
            pygame.draw.line(surface, pmap.COLORS["E"], (int(self.x + self.w/2), int(self.y + self.h/2)), (int(tx), int(ty)), 2 + int(2 * blink))

    def _draw_plasma_cores(self, surface: pygame.Surface, x: float, y: float, scale: float) -> None:
        """Desenha os 3 núcleos com plasma vivo, posicionados no triângulo."""
        grid_w = pmap.PIXEL_COLS * scale
        grid_h = pmap.PIXEL_ROWS * scale
        intensity = 0.85 + 0.15 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0))
        if self.state == _PHASE3:
            intensity *= 1.2  # núcleos sobrecarregados na fase final
        for rx, ry, rr, theme, phase in self.SPHERE_DEFS:
            cx = int(x + rx * grid_w)
            cy = int(y + ry * grid_h)
            radius = rr * grid_w
            self._draw_plasma_sphere(surface, cx, cy, radius, theme, phase, intensity)

    def _draw_plasma_sphere(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        radius: float,
        theme: str,
        phase: float,
        intensity: float,
    ) -> None:
        """Esfera de contenção com fluido energético VIVO (metaballs animadas).

        O fluido é renderizado em células chunky (estética pixel art) cuja cor vem
        de um campo de metaballs que orbitam dentro da esfera — dá a sensação de
        plasma condensado em movimento constante. `draw()` puro (§3): toda a
        animação vem de `self.anim_time` + a fase fixa do núcleo.
        """
        grad = _PLASMA_THEMES.get(theme, _PLASMA_THEMES["cyan"])
        t = self.anim_time

        # Halo de energia irradiada (aditivo) — "distribuição de energia".
        halo_r = int(radius * 1.5)
        if halo_r > 0:
            halo = pygame.Surface((halo_r * 2, halo_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(halo, (*grad[1], 55), (halo_r, halo_r), halo_r)
            surface.blit(
                halo, (cx - halo_r, cy - halo_r), special_flags=pygame.BLEND_RGBA_ADD
            )

        # Centros das metaballs orbitando dentro da esfera (fluido em movimento).
        blobs = []
        for k in range(3):
            ang = t * (0.6 + 0.25 * k) + phase + k * 2.1
            orbit = radius * 0.5 * (0.4 + 0.6 * abs(math.sin(t * 0.7 + phase + k * 1.3)))
            blobs.append((math.cos(ang) * orbit, math.sin(ang) * orbit))

        # Fluido em células chunky (pixel art): cor pelo campo de metaballs.
        res = max(6, int(radius * 2 / 6))  # ~6px por célula
        cell = radius * 2 / res
        r2 = radius * radius
        base_x = cx - radius
        base_y = cy - radius
        for gy in range(res):
            ly = (gy + 0.5) / res * 2.0 * radius - radius
            for gx in range(res):
                lx = (gx + 0.5) / res * 2.0 * radius - radius
                if lx * lx + ly * ly > r2:
                    continue
                field = 0.16
                for bx, by in blobs:
                    d2 = (lx - bx) ** 2 + (ly - by) ** 2 + 30.0
                    field += (r2 * 0.16) / d2
                v = max(0.0, min(1.0, field * intensity))
                pygame.draw.rect(
                    surface,
                    _grad3(grad, v),
                    (int(base_x + gx * cell), int(base_y + gy * cell), int(cell + 1), int(cell + 1)),
                )

        # Vidro de contenção (aro): aro neon claro + brilho do tema.
        pygame.draw.circle(surface, (210, 250, 255), (cx, cy), int(radius), 2)
        pygame.draw.circle(surface, grad[2], (cx, cy), int(radius - 2), 1)

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        bw, bh = 300, 8
        bx, by = (Config.SCREEN_WIDTH - bw) // 2, 20
        pygame.draw.rect(surface, (60, 20, 30), (bx, by, bw, bh))
        pygame.draw.rect(surface, (90, 200, 255), (bx, by, int(bw * self._hp_fraction), bh))
        pygame.draw.rect(surface, (200, 200, 200), (bx, by, bw, bh), 1)

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + 200

    def get_explosion_duration(self) -> float:
        return 4.0
