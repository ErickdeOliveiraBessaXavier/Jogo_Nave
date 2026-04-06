"""
Stone Golem Boss — Mundo 1: Cordilheira Celestial (Montanhas)

Boss do nível 10. Padrão Arc (como Boss original):
- Classe independente, sem herança
- Spawna entidades EXTERNAS (Boulder e RockShard)
- Retorna entidades para o EntityManager adicionar
- Visual pixel-art com pygame.draw (sem sprites), inspirado no arquivo HTML de referência
- EMP slowdown automático via enemy_dt

Sistema de dano ao jogador:
- O jogo usa VIDAS, não barra de HP
- GolemMine: contato direto ou explosão (shards) remove 1 vida
- RockShard e OrbitalRock (fase 'fired') também causam dano por rect collision
- A detecção é feita via rect collision em playing.py/_check_ship_damage()
- Todas as entidades expõem .rect, .dead e .causes_damage

FSM de estados (inspirada no arquivo HTML de referência):
  ENTERING    → entra pela parte superior da tela
  SCAN        → idle, olho fechado, move verticalmente (2 s)
  OPENING     → olho abre com easing (1.5 s) → CHARGE
  CHARGE      → núcleo pulsa, partículas de carga (1.5 s) → FIRE
  FIRE        → Planta 3 GolemMines na posição do jogador → CLOSING
  EARTH_SHAKE → tremor + jitter (0.8 s) → EARTH_PULL
  EARTH_PULL  → pedras sobem da borda inferior até a órbita → EARTH_ORBIT
  EARTH_ORBIT → pedras orbitam o boss (~1.2 s) → EARTH_FIRE
  EARTH_FIRE  → pedras arremessadas uma a uma no jogador → SCAN
  SWEEP_CHARGE→ olho abre para sweep (1.2 s) → SWEEP_FIRE
  SWEEP_FIRE  → cone de shards varrendo → CLOSING
  ORB_SPAWN   → olho abre roxo (0.8 s) → ORB_HOLD
  ORB_HOLD    → orbes prontos (0.6 s) → ORB_FIRE
  ORB_FIRE    → shards em rosa-dos-ventos → CLOSING
  CLOSING     → olho fecha com easing → SCAN
"""

import logging
import math
import random
from typing import List, Optional, Tuple

import pygame

from ..core.config import config as Config
from ..entities.stone_golem_pixel_map import (
    EYE_COL_END as _EYE_COL_END,
)
from ..entities.stone_golem_pixel_map import (
    EYE_COL_START as _EYE_COL_START,
)
from ..entities.stone_golem_pixel_map import (
    EYE_ROW as _EYE_ROW,
)
from ..entities.stone_golem_pixel_map import (
    EYE_ROW_ABOVE as _EYE_ROW_ABOVE,
)
from ..entities.stone_golem_pixel_map import (
    EYE_ROW_BELOW as _EYE_ROW_BELOW,
)
from ..entities.stone_golem_pixel_map import (
    ORBITAL_ROCK_COLORS as _ORBITAL_ROCK_COLORS,
)
from ..entities.stone_golem_pixel_map import (
    PIXEL_COLS as _PIXEL_COLS,
)
from ..entities.stone_golem_pixel_map import (
    PIXEL_MAP as _PIXEL_MAP,
)
from ..entities.stone_golem_pixel_map import (
    PIXEL_ROWS as _PIXEL_ROWS,
)
from ..entities.stone_golem_pixel_map import (
    C as _C,
)

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS MATEMATICOS
# ============================================================================


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ============================================================================
# ENTIDADES PROJETADAS PELO GOLEM
# ============================================================================


class GolemMine:
    """
    Mina de energia vermelha plantada pelo boss na posição do jogador.

    Fases:
      'landing'  → cai rapidamente do olho do boss até a posição alvo
      'armed'    → fica parada na tela por FUSE_TIME segundos, pulsando
      'exploded' → dispara RockShards em todas as direções e morre

    A explosão é gerada via update() retornando shards — o caller
    (StoneGolemBoss._run_fsm) coleta e repassa ao EntityManager.
    """

    FUSE_TIME = 5.0  # segundos até explodir
    LAND_SPEED = 900.0  # px/s durante a queda
    RADIUS = 12
    EXPL_SHARDS = 16  # fragmentos na explosão

    _COLOR_BODY = (200, 40, 40)
    _COLOR_RING = (255, 100, 100)
    _COLOR_PULSE = (255, 200, 200)

    def __init__(self, x: float, y: float, target_x: float, target_y: float):
        self.x = float(x)
        self.y = float(y)
        self.target_x = float(target_x)
        self.target_y = float(target_y)
        self.dead = False
        self.causes_damage = True  # contato direto também remove vida

        self._phase = "landing"
        self._fuse_timer = 0.0
        self._pulse_t = 0.0  # oscilação visual do pulso

        self.rect = pygame.Rect(
            int(self.x - self.RADIUS),
            int(self.y - self.RADIUS),
            self.RADIUS * 2,
            self.RADIUS * 2,
        )

        # ── Otimização: Pré-alocação de superfícies ──────────────────────────
        r = self.RADIUS
        max_glow_r = int(r * 2.2)  # r * 1.6 + 0.6 * r
        self._glow_surf = pygame.Surface(
            (max_glow_r * 2, max_glow_r * 2), pygame.SRCALPHA
        )
        self._arc_surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    def update(self, dt: float) -> list["RockShard"]:
        """Retorna lista de RockShards criados neste frame (vazia até explodir)."""
        self._pulse_t += dt
        spawned: list[RockShard] = []

        if self._phase == "landing":
            # Move em linha reta do olho até o alvo
            dx = self.target_x - self.x
            dy = self.target_y - self.y
            dist = math.hypot(dx, dy)
            if dist < self.LAND_SPEED * dt:
                self.x, self.y = self.target_x, self.target_y
                self._phase = "armed"
            else:
                nx, ny = dx / dist, dy / dist
                self.x += nx * self.LAND_SPEED * dt
                self.y += ny * self.LAND_SPEED * dt

        elif self._phase == "armed":
            self._fuse_timer += dt
            if self._fuse_timer >= self.FUSE_TIME:
                self._phase = "exploded"
                # Gera shards em todas as direções
                for i in range(self.EXPL_SHARDS):
                    angle_deg = (360.0 / self.EXPL_SHARDS) * i + random.uniform(-5, 5)
                    spawned.append(
                        RockShard(
                            self.x,
                            self.y,
                            angle_deg,
                            speed_mult=1.4,
                            color=(255, 100, 60),
                        )
                    )
                self.dead = True

        self.rect.x = int(self.x - self.RADIUS)
        self.rect.y = int(self.y - self.RADIUS)
        return spawned

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        if self._phase == "exploded":
            return

        cx, cy = int(self.x), int(self.y)
        r = self.RADIUS

        # ── Urgência: pisca mais rápido conforme o fusível encurta ──────────
        fuse_ratio = (
            self._fuse_timer / self.FUSE_TIME if self._phase == "armed" else 0.0
        )
        blink_freq = 4.0 + fuse_ratio * 14.0  # 4 Hz → 18 Hz
        blink_on = math.sin(self._pulse_t * blink_freq * math.pi * 2) > 0

        # ── Glow pulsante (Reutiliza Surface) ────────────────────────────────
        pulse = abs(math.sin(self._pulse_t * blink_freq * math.pi))
        glow_r = int(r * 1.6 + pulse * r * 0.6)
        glow_alpha = int(60 + pulse * 80)

        self._glow_surf.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self._glow_surf, (*self._COLOR_RING, glow_alpha), (glow_r, glow_r), glow_r
        )
        surface.blit(self._glow_surf, (cx - glow_r, cy - glow_r))

        # ── Corpo da mina (pixel-art: cruz + quadrado central) ───────────────
        S = max(2, r // 3)
        body_color = self._COLOR_PULSE if blink_on else self._COLOR_BODY

        pygame.draw.rect(
            surface, body_color, (cx - S, cy - S * 3, S * 2, S * 6)
        )  # vertical
        pygame.draw.rect(
            surface, body_color, (cx - S * 3, cy - S, S * 6, S * 2)
        )  # horizontal
        pygame.draw.rect(
            surface, body_color, (cx - S * 2, cy - S * 2, S * 4, S * 4)
        )  # centro

        # ── Timer visual: arco que some conforme o fusível queima ────────────
        if self._phase == "armed":
            remaining = 1.0 - fuse_ratio
            arc_end = int(remaining * 360)
            if arc_end > 2:
                self._arc_surf.fill((0, 0, 0, 0))
                arc_col = (
                    int(255 * fuse_ratio + 60 * remaining),
                    int(200 * remaining),
                    40,
                    200,
                )
                pygame.draw.arc(
                    self._arc_surf,
                    arc_col,
                    (4, 4, r * 4 - 8, r * 4 - 8),
                    math.radians(90),
                    math.radians(90 + arc_end),
                    max(1, S),
                )
                surface.blit(self._arc_surf, (cx - r * 2, cy - r * 2))


# Alias de retrocompatibilidade — entity_manager importa 'Boulder'
Boulder = GolemMine


class RockShard:
    """
    Fragmento de pedra disparado em leque, terra ou rosa dos ventos.
    Ao colidir com a nave, remove 1 vida (processado em playing.py).
    """

    def __init__(
        self,
        x: float,
        y: float,
        angle_deg: float,
        speed_mult: float = 1.0,
        color: Optional[Tuple[int, int, int]] = None,
    ):
        self.x = x
        self.y = y
        self.size = random.randint(10, 16)  # Fragmentos um pouco maiores
        self.dead = False
        # Cor: roxa para orbes mágicos, ciano para sweep — ou customizada pelo chamador
        self.color = color if color is not None else (217, 66, 255)

        speed = getattr(Config, "GOLEM_SHARD_SPEED", 420) * speed_mult
        rad = math.radians(angle_deg)
        self.vx = math.cos(rad) * speed
        self.vy = math.sin(rad) * speed

        self._angle = angle_deg
        self._spin = random.uniform(-220, 220)

        self.rect = pygame.Rect(
            int(self.x - self.size),
            int(self.y - self.size),
            self.size * 2,
            self.size * 2,
        )

        # ── Otimização: Pré-alocação do glow ─────────────────────────────────
        s = self.size // 2
        self._glow_surf = pygame.Surface((s * 4, s * 4), pygame.SRCALPHA)
        self._glow_surf.fill((*self.color, 60))

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self._angle += self._spin * dt

        self.rect.x = int(self.x - self.size)
        self.rect.y = int(self.y - self.size)

        screen_h = getattr(Config, "SCREEN_HEIGHT", 800)
        screen_w = getattr(Config, "SCREEN_WIDTH", 480)
        if (
            self.y > screen_h + 40
            or self.y < -40
            or self.x < -40
            or self.x > screen_w + 40
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """
        Visual pixel-art estilo "orbe de energia" — coerente com a estética
        bloquinha do Boss. Roxo para ataques de orbe, ciano para sweep laser.
        """
        cx = int(self.x)
        cy = int(self.y)
        s = self.size // 2
        c = self.color
        core = (255, 255, 255)

        # Camada externa (glow) - Reutiliza Surface
        surface.blit(self._glow_surf, (cx - s * 2, cy - s * 2))

        # Corpo principal do orbe
        pygame.draw.rect(surface, c, (cx - s, cy - s, s * 2, s * 2))
        # Núcleo brilhante
        pygame.draw.rect(surface, core, (cx - s // 2, cy - s // 2, s, s))


class OrbitalRock:
    """
    Pedra de terra usada no ataque Earth do Golem.
    Fiel ao HTML de referência:

    Fases:
      'pulling'  → lerp lento da borda inferior até a elipse de órbita
      'orbiting' → lerp rápido + ângulo avança → "cola" na elipse
      'fired'    → arremessada em direção ao jogador (causa dano)

    Órbita ELÍPTICA (rx largo, ry estreito) → efeito de disco 3D.
    Depth-sort: sin(angle)<0 = atrás do boss; >=0 = na frente.
    Visual pixel-art: blocos retangulares, sem rotação — igual ao drawRock do HTML.
    """

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        orbit_cx: float,
        orbit_cy: float,
        target_rx: float,  # raio elipse horizontal
        target_ry: float,  # raio elipse vertical (menor → disco achatado)
        orbit_angle_start: float,
        rock_size: int,  # 2 ou 3 — escala pixel-art (como o HTML)
        color: Tuple[int, int, int],
        S: int,  # SCALE do boss
    ):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.dead = False

        # Posição de nascimento: espalhada na borda inferior
        self.x = orbit_cx + (random.random() - 0.5) * screen_w * 0.8
        self.y = screen_h + 50 + random.random() * 150

        # Parâmetros de órbita elíptica
        self.orbit_cx = orbit_cx
        self.orbit_cy = orbit_cy
        self.target_rx = target_rx
        self.target_ry = target_ry
        self.orbit_angle = orbit_angle_start
        self.orbit_speed = 0.03 + random.random() * 0.04  # rad/frame ≈ 1.8–2.4 rad/s

        # Visual pixel-art
        self._S = S
        self._size = rock_size  # 2 ou 3
        self.color = color

        # Flutuação orgânica individual (phase offset único por pedra → órbita viva)
        self.bob_offset = random.uniform(0, math.pi * 2)

        # Rotação ao ser disparada (tumbling pelo ar)
        self.spin = random.uniform(0, 360)
        self.spin_speed = random.uniform(200, 450) * random.choice([-1, 1])

        # Rastro de poeira: lista de [x, y, alpha]
        self.trail: list[list[float]] = []

        # Estado
        self.phase = "pulling"  # 'pulling' | 'orbiting' | 'fired'
        self.fire_delay = 0.0  # segundos antes de disparar (setado em EARTH_FIRE)

        # Velocidade de disparo
        self._fire_vx = 0.0
        self._fire_vy = 0.0
        self._fire_perp_x = 0.0  # componente de arco perpendicular
        self._fire_perp_y = 0.0
        self._fire_perp_decay = 3.5
        self._fire_gravity = getattr(Config, "GOLEM_BOULDER_GRAVITY", 30)

        # Rect de colisão — atualizado em update()
        hit = S * self._size
        self.rect = pygame.Rect(int(self.x) - hit, int(self.y) - hit, hit * 2, hit * 2)

        # ── Otimização: Pré-bake do shape e rastro ───────────────────────────
        canvas_size = (self._size + 2) * S * 2
        self._rock_surf = pygame.Surface((canvas_size, canvas_size), pygame.SRCALPHA)
        ox = canvas_size // 2 - (self._size * S) // 2
        oy = canvas_size // 2 - S
        if self._size == 2:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 2, S * 2))
        else:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 3, S * 2))
            pygame.draw.rect(self._rock_surf, self.color, (ox + S, oy - S, S, S))
            pygame.draw.rect(self._rock_surf, self.color, (ox - S, oy + S, S, S))

        self._dust_surf = pygame.Surface((S * 2, S * 2), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    def _orbit_target(self) -> Tuple[float, float]:
        """Ponto atual na elipse com flutuação vertical orgânica por pedra."""
        bobbing_y = math.sin(self.orbit_angle * 2 + self.bob_offset) * 15
        return (
            self.orbit_cx + math.cos(self.orbit_angle) * self.target_rx,
            self.orbit_cy + math.sin(self.orbit_angle) * self.target_ry + bobbing_y,
        )

    def fire_at(self, target_x: float, target_y: float) -> None:
        """Arremessa em direção geral ao alvo, mas com espalhamento e curva caóticos."""
        self.phase = "fired"
        base_speed = getattr(Config, "GOLEM_BOULDER_SPEED", 340) * 1.15

        # Espalhamento severo da mira ao redor do jogador
        spread_x = target_x + random.uniform(-250, 250)
        spread_y = target_y + random.uniform(-100, 250)

        dx = spread_x - self.x
        dy = spread_y - self.y
        dist = math.hypot(dx, dy) or 1.0
        nx, ny = dx / dist, dy / dist

        self._fire_vx = nx * base_speed
        self._fire_vy = ny * base_speed

        # Força perpendicular caótica → pedras curvam individualmente ao cair
        perp_strength = random.uniform(-400, 400)
        self._fire_perp_x = -ny * perp_strength
        self._fire_perp_y = nx * perp_strength
        self._fire_perp_decay = random.uniform(1.8, 3.5)  # decay diferente por pedra

    # ------------------------------------------------------------------
    def update(
        self,
        dt: float,
        orbit_cx: float,
        orbit_cy: float,
        player_x: float = 0.0,
        player_y: float = 0.0,
    ) -> None:
        self.orbit_cx = orbit_cx
        self.orbit_cy = orbit_cy

        # Ângulo avança sempre (mesmo no pull) — cria o "turbilhão" de chegada
        self.orbit_angle += self.orbit_speed * 60 * dt

        if self.phase == "pulling":
            # Lerp lento em direção ao ponto na elipse — 0.05 * 60 = 3.0/s
            tx, ty = self._orbit_target()
            self.x += (tx - self.x) * min(1.0, 3.0 * dt)
            self.y += (ty - self.y) * min(1.0, 3.0 * dt)

        elif self.phase == "orbiting":
            # Lerp rápido — cola na elipse — 0.2 * 60 = 12.0/s
            tx, ty = self._orbit_target()
            self.x += (tx - self.x) * min(1.0, 12.0 * dt)
            self.y += (ty - self.y) * min(1.0, 12.0 * dt)

            # Countdown do disparo (setado pelo boss em EARTH_FIRE)
            if self.fire_delay > 0:
                self.fire_delay -= dt
                if self.fire_delay <= 0:
                    self.fire_at(player_x, player_y)

        elif self.phase == "fired":
            # Decai o componente perpendicular → curva em arco que endireita
            decay = math.exp(-self._fire_perp_decay * dt)
            self._fire_perp_x *= decay
            self._fire_perp_y *= decay
            self._fire_vy += self._fire_gravity * dt
            self.x += (self._fire_vx + self._fire_perp_x) * dt
            self.y += (self._fire_vy + self._fire_perp_y) * dt
            # Gira violentamente pelo ar (tumbling)
            self.spin += self.spin_speed * dt
            # Deposita rastro de poeira
            if random.random() < 0.4:
                self.trail.append([self.x, self.y, 255.0])
            if (
                self.y > self.screen_h + 80
                or self.x < -80
                or self.x > self.screen_w + 80
            ):
                self.dead = True

        # Esvai o rastro independentemente de fase
        for t in self.trail:
            t[2] -= 800 * dt
        self.trail = [t for t in self.trail if t[2] > 0]

        hit = self._S * self._size
        self.rect.x = int(self.x) - hit
        self.rect.y = int(self.y) - hit
        self.rect.w = hit * 2
        self.rect.h = hit * 2

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        """
        Desenho pixel-art com rastro de poeira e rotação ao ser disparada.
        - Fase orbiting/pulling: retângulos estáticos (fiel ao HTML).
        - Fase fired: Surface rotacionada + rastro de alpha para velocidade.
        """
        S = self._S
        c = self.color

        # ── 1. Rastro de poeira (apenas quando disparada) ──────────────────
        for tx, ty, alpha in self.trail:
            self._dust_surf.fill((*c, int(alpha * 0.6)))
            surface.blit(self._dust_surf, (int(tx) - S, int(ty) - S))

        # ── 2. Usa shape pré-baked ─────────────────────────────────────────
        if self.phase == "fired":
            img = pygame.transform.rotate(self._rock_surf, self.spin)
        else:
            img = self._rock_surf

        rect = img.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(img, rect)

    # ------------------------------------------------------------------
    @property
    def causes_damage(self) -> bool:
        """Só causa dano quando arremessada."""
        return self.phase == "fired"

    @property
    def behind_boss(self) -> bool:
        """True quando a pedra está 'atrás' do boss na órbita (sin < 0)."""
        return math.sin(self.orbit_angle) < 0 and self.phase != "fired"


# ============================================================================
# PARTICULA DE CARGA (visual, nao causa dano)
# ============================================================================


class _ChargeParticle:
    """Particula que orbita o nucleo do olho durante o estado CHARGE."""

    def __init__(self, pupil_x: float, pupil_y: float, color: Tuple[int, int, int]):
        self.angle = random.uniform(0, math.pi * 2)
        self.dist = 120 + random.uniform(0, 40)  # Distância maior para boss maior
        self.start_dist = self.dist
        self.orbit_speed = 0.05 + random.uniform(0, 0.08)
        self.radial_speed = 80 + random.uniform(0, 80)
        self.color = color
        self.size = random.randint(3, 6)
        self.px = pupil_x
        self.py = pupil_y
        self.dead = False

        # ── Otimização: Pré-alocação de superfície ──────────────────────────
        self._surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)

    def update(self, dt: float, pupil_x: float, pupil_y: float) -> None:
        self.dist -= self.radial_speed * dt
        speed_mul = 1.0 + (1.0 - _clamp(self.dist / self.start_dist, 0, 1)) * 2.0
        self.angle += self.orbit_speed * speed_mul * (dt * 60)
        if self.dist < 2:
            self.dead = True
            return
        self.px = pupil_x + math.cos(self.angle) * self.dist
        self.py = pupil_y + math.sin(self.angle) * self.dist

    def draw(self, surface: pygame.Surface) -> None:
        alpha_ratio = _clamp(self.dist / self.start_dist * 2, 0, 1)
        if alpha_ratio < 0.05:
            return

        r, g, b = self.color
        self._surf.fill((r, g, b, int(alpha_ratio * 220)))
        surface.blit(self._surf, (int(self.px) - self.size, int(self.py) - self.size))


class StoneGolemBoss:
    """
    Boss do Mundo 1 — Cordilheira Celestial (tema MOUNTAINS).
    Aparece no nivel 10 (boss_level do WorldConfig do Mundo 1).

    Padrao Arc:
    - update() retorna (boulders_criados, shards_criados)
    - Nao recebe entity_manager
    - Visual pixel-art escalavel com pygame.draw
    - EMP aplicado automaticamente via enemy_dt
    """

    SCALE = 12  # px por "pixel" do mapa (Aumentado de 8 para 12 = 1.5x)

    def __init__(
        self,
        x: float,
        y: float,
        health: Optional[int] = None,
        difficulty_multiplier: float = 1.0,
    ):
        S = self.SCALE
        self._screen_w = getattr(Config, "SCREEN_WIDTH", 480)
        self._screen_h = getattr(Config, "SCREEN_HEIGHT", 800)

        self.w = _PIXEL_COLS * S  # 19*12 = 228
        self.h = _PIXEL_ROWS * S  # 22*12 = 264

        # Posicionamento na lateral direita, com margem grande
        margin_x = 70
        self.x = self._screen_w - self.w - margin_x
        self.y = -self.h
        self.target_y = y  # Onde ele para ao entrar

        base_health = getattr(Config, "GOLEM_HEALTH", 350)
        self.max_health = int(base_health * difficulty_multiplier)
        self.health = health if health is not None else self.max_health
        self.dead = False
        self.hit_score = 60

        # Direção inicial para movimento vertical
        self.direction = 1
        self.entry_speed = getattr(Config, "GOLEM_ENTRY_SPEED", 160)

        # ── FSM ──────────────────────────────────────────────────────────────
        self.fsm_state = "ENTERING"
        self.fsm_ticks = 0.0
        self._prev_fsm_state = "ENTERING"

        # ── Olho ─────────────────────────────────────────────────────────────
        self.eye_growth = 0.0  # 0 = fechado, 1 = totalmente aberto
        # scan_step: -1, 0 ou +1 — movimento da iris (Math.round(cos(t*3)) no JS)
        self._scan_step = 0

        # ── Flutuacao suave (currentFloatY do JS) ────────────────────────────
        self._current_float_y = 0.0

        # ── Tremor / jitter ──────────────────────────────────────────────────
        self.stomp_shake = 0.0
        self.stomp_shake_timer = 0.0
        self._jitter_x = 0.0
        self._jitter_y = 0.0

        # ── Sweep ────────────────────────────────────────────────────────────
        self._sweep_angle = math.pi / 2
        self._sweep_total = math.radians(30)
        self._shards_fired_at: set[int] = set()
        # Ângulo travado quando o carregamento atinge o limiar (jogador tem tempo de escapar)
        self._sweep_locked_angle: float = math.pi / 2
        self._sweep_lock_done: bool = False

        # ── Earth attack — pedras orbitais ───────────────────────────────────
        self._orbital_rocks: List[OrbitalRock] = []

        # ── Minas de energia (ataque FIRE) ───────────────────────────────────
        self._mines: List[GolemMine] = []
        self._fire_shots_count: int = 0
        self._fire_shot_timer: float = 0.0
        self._cycles_since_fire: int = (
            0  # garante que FIRE ocorre a cada 3 ciclos no máximo
        )

        # ── Particulas de carga ───────────────────────────────────────────────
        self._charge_particles: List[_ChargeParticle] = []

        # ── Tempo global ─────────────────────────────────────────────────────
        self._time = 0.0

        # ── Colisao ───────────────────────────────────────────────────────────
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        self.emp_linger_timer = 0.0

        # ── Otimização: Pré-alocação e Pre-bake ──────────────────────────────
        self._body_surf_top: Optional[pygame.Surface] = None
        self._body_surf_bottom: Optional[pygame.Surface] = None
        self._pre_bake_body()

        self._thruster_surfs = [
            pygame.Surface((S * 10 + 2, S * 4 + 2), pygame.SRCALPHA) for _ in range(5)
        ]

        self._cone_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )
        self._beam_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )
        self._halo_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )

        logger.debug(
            "StoneGolemBoss criado em (%.0f, %.0f) | HP=%d | dif=%.2f",
            self.x,
            self.y,
            self.max_health,
            difficulty_multiplier,
        )

    def _pre_bake_body(self) -> None:
        """Cria superfícies pré-renderizadas para as partes estáticas do boss."""
        S = self.SCALE
        # Topo: linhas 0 até EYE_ROW_ABOVE - 1 (linhas 0-5)
        top_h = _EYE_ROW_ABOVE * S
        self._body_surf_top = pygame.Surface((self.w, top_h), pygame.SRCALPHA)
        for row_idx in range(_EYE_ROW_ABOVE):
            for col_idx, key in enumerate(_PIXEL_MAP[row_idx]):
                if key:
                    pygame.draw.rect(
                        self._body_surf_top, _C[key], (col_idx * S, row_idx * S, S, S)
                    )

        # Base: linhas EYE_ROW_BELOW + 1 até o fim (linhas 9-21)
        bottom_start_row = _EYE_ROW_BELOW + 1
        bottom_h = (_PIXEL_ROWS - bottom_start_row) * S
        self._body_surf_bottom = pygame.Surface((self.w, bottom_h), pygame.SRCALPHA)
        for row_idx in range(bottom_start_row, _PIXEL_ROWS):
            draw_row = row_idx - bottom_start_row
            for col_idx, key in enumerate(_PIXEL_MAP[row_idx]):
                if key:
                    pygame.draw.rect(
                        self._body_surf_bottom,
                        _C[key],
                        (col_idx * S, draw_row * S, S, S),
                    )

    # =========================================================================
    # COORDENADAS COMPARTILHADAS (updateShared do JS)
    # =========================================================================

    def _shared_center(self) -> Tuple[float, float]:
        """
        Centro geometrico do boss com flutuacao aplicada.
        Equivale a sharedCenterX/Y do JS (sem jitter — jitter e aplicado no draw).
        """
        cx = self.x + self.w / 2
        cy = self.y + self._current_float_y
        return cx, cy

    def _pupil_pos(self) -> Tuple[float, float]:
        """
        Centro da pupila no mundo.
        """
        S = self.SCALE
        vx = self.x + _EYE_COL_START * S + self._jitter_x
        px = vx + S * 2.5 + self._scan_step * S
        _, cy = self._shared_center()
        py = cy + self._jitter_y
        return px, py

    # =========================================================================
    # FSM — mudanca de estado
    # =========================================================================

    def _change_fsm(self, new_state: str) -> None:
        old = self.fsm_state
        self._prev_fsm_state = old  # rastreia origem para CLOSING
        self.fsm_state = new_state
        self.fsm_ticks = 0.0
        logger.debug("StoneGolemBoss FSM: %s → %s", old, new_state)

        if new_state == "CHARGE":
            self._charge_particles.clear()

        if new_state == "FIRE":
            self._fire_shots_count = 0
            self._fire_shot_timer = 0.0
            self._cycles_since_fire = 0

        if new_state == "ORB_SPAWN":
            self._orb_rotation = 0.0

        if new_state == "SWEEP_CHARGE":
            self._sweep_base_angle = math.pi / 2  # Posição segura inicial
            self._sweep_locked_angle = math.pi / 2
            self._sweep_lock_done = False

        if new_state == "SWEEP_FIRE":
            # Usa o ângulo já travado em SWEEP_CHARGE — mira não muda mais aqui
            self._sweep_angle = self._sweep_locked_angle - self._sweep_total / 2
            self._shards_fired_at = set()

        if new_state == "EARTH_PULL":
            # Invoca 15 pedras fora da tela — raios elípticos escalados pelo boss
            self._orbital_rocks.clear()
            cx, cy = self._shared_center()
            S = self.SCALE
            for _ in range(15):
                rx = self.w * 0.45 + random.random() * self.w * 0.2
                ry = self.w * 0.12 + random.random() * self.w * 0.1
                angle = random.random() * math.pi * 2
                size = 2 if random.random() > 0.5 else 3
                color = random.choice(_ORBITAL_ROCK_COLORS)
                self._orbital_rocks.append(
                    OrbitalRock(
                        screen_w=self._screen_w,
                        screen_h=self._screen_h,
                        orbit_cx=cx,
                        orbit_cy=cy,
                        target_rx=rx,
                        target_ry=ry,
                        orbit_angle_start=angle,
                        rock_size=size,
                        color=color,
                        S=S,
                    )
                )

        if new_state == "EARTH_ORBIT":
            # Transita todas as pedras para fase orbiting (lerp rápido)
            for r in self._orbital_rocks:
                r.phase = "orbiting"

        if new_state == "EARTH_FIRE":
            # Cada pedra recebe um fireDelay aleatório (0 a ~0.67 s)
            for r in self._orbital_rocks:
                if r.phase == "orbiting":
                    r.fire_delay = random.uniform(0.1, 1.2)

    # =========================================================================
    # UPDATE PRINCIPAL
    # =========================================================================

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
    ) -> Tuple[List["GolemMine"], List[RockShard], List[OrbitalRock]]:
        """
        Atualiza o boss e retorna entidades novas para o EntityManager.

        Args:
            dt:       Delta time ja modificado pelo EMP (enemy_dt)
            player_x: Posicao X central do jogador
            player_y: Posicao Y central do jogador

        Returns:
            (mines_novas, shards_novos, orbital_rocks_ativos)
            mines_novas: GolemMines recém-plantadas neste frame
            shards_novos: RockShards emitidos por explosões de minas + sweep + orbs
            orbital_rocks_ativos: pedras em fase 'fired' com .causes_damage=True
        """
        new_mines: List[GolemMine] = []
        new_shards: List[RockShard] = []

        self._time += dt
        self.fsm_ticks += dt

        # ── Flutuacao suave (JS: lerp currentFloatY → targetFloat) ───────────
        _anchored = {
            "CHARGE",
            "FIRE",
            "EARTH_SHAKE",
            "EARTH_PULL",
            "EARTH_ORBIT",
            "EARTH_FIRE",
            "ORB_SPAWN",
            "ORB_HOLD",
            "ORB_FIRE",
            "SWEEP_CHARGE",
            "SWEEP_FIRE",
        }
        target_float = (
            0.0
            if self.fsm_state in _anchored
            else round(math.sin(self._time * 2.5) * 12)
        )
        self._current_float_y += (target_float - self._current_float_y) * min(
            1.0, 6.0 * dt
        )

        # ── Scan step: iris se move -1/0/+1 pixel horizontalmente ─────────────
        _scanning = self.fsm_state in {"SCAN", "OPENING", "ORB_SPAWN"}
        self._scan_step = round(math.cos(self._time * 3)) if _scanning else 0

        # ── Jitter (apenas EARTH_SHAKE e SWEEP_FIRE — igual JS) ──────────────
        S = self.SCALE
        if self.fsm_state in ("EARTH_SHAKE", "EARTH_PULL", "SWEEP_FIRE"):
            self._jitter_x = random.uniform(-0.5, 0.5) * S
            self._jitter_y = random.uniform(-0.5, 0.5) * S
        else:
            self._jitter_x = 0.0
            self._jitter_y = 0.0
        self.stomp_shake = self._jitter_y

        # ── FSM ───────────────────────────────────────────────────────────────
        self._run_fsm(dt, player_x, player_y, new_mines, new_shards)

        # ── Particulas de carga ───────────────────────────────────────────────
        px, py = self._pupil_pos()
        for p in self._charge_particles:
            p.update(dt, px, py)
        self._charge_particles = [p for p in self._charge_particles if not p.dead]

        # ── Minas ativas: limpa mortas e sincroniza referências ───────────────
        # O update() de cada mina é feito pelo entity_manager (via self.boulders).
        # O boss só precisa manter a lista para draw() e para saber quais explodiram.
        # Os shards de explosão são coletados pelo entity_manager no mesmo loop.
        self._mines = [m for m in self._mines if not m.dead]

        # ── Pedras orbitais ───────────────────────────────────────────────────
        cx, cy = self._shared_center()
        for rock in self._orbital_rocks:
            rock.update(dt, cx, cy, player_x, player_y)
        self._orbital_rocks = [r for r in self._orbital_rocks if not r.dead]

        # ── Rect de colisao (sem jitter — hitbox estavil) ────────────────────
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

        return new_mines, new_shards, self._orbital_rocks

    # =========================================================================
    # FSM — logica de cada estado
    # =========================================================================

    def _run_fsm(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        new_mines: List["GolemMine"],
        new_shards: List[RockShard],
    ) -> None:
        t = self.fsm_ticks
        state = self.fsm_state

        # ── ENTRADA ───────────────────────────────────────────────────────────
        if state == "ENTERING":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._change_fsm("SCAN")

        # ── SCAN (idle) ───────────────────────────────────────────────────────
        elif state == "SCAN":
            self._move_vertical(dt)
            self.eye_growth = 0.0
            if t > 2.0:
                r = random.random()
                # Após 2 ciclos sem FIRE, força o ataque de minas no próximo SCAN
                if self._cycles_since_fire >= 2:
                    self._change_fsm("OPENING")
                elif r < 0.40:
                    self._change_fsm("OPENING")
                elif r < 0.60:
                    self._change_fsm("EARTH_SHAKE")
                elif r < 0.80:
                    self._change_fsm("ORB_SPAWN")
                else:
                    self._change_fsm("SWEEP_CHARGE")

        # ── LASER / MINAS ─────────────────────────────────────────────────────
        elif state == "OPENING":
            self._move_vertical(dt)
            self.eye_growth = _ease_out_cubic(_clamp(t / 1.5, 0, 1))
            if t > 2.5:
                self._change_fsm("CHARGE")

        elif state == "CHARGE":
            self._move_vertical(dt)
            px, py = self._pupil_pos()
            if len(self._charge_particles) < 150:
                for _ in range(3):
                    color = random.choice([(255, 77, 77), (255, 153, 153)])
                    self._charge_particles.append(_ChargeParticle(px, py, color))
            if t > 1.5:
                self._change_fsm("FIRE")

        elif state == "FIRE":
            self._fire_shot_timer -= dt

            # Planta até 3 minas, uma por vez, com intervalo de 0.6 s
            if self._fire_shot_timer <= 0 and self._fire_shots_count < 3:
                px, py = self._pupil_pos()
                # Pequeno espalhamento ao redor do jogador
                offset_x = random.uniform(-40, 40)
                offset_y = random.uniform(-40, 40)
                mine = GolemMine(px, py, player_x + offset_x, player_y + offset_y)
                new_mines.append(mine)
                self._mines.append(mine)  # boss mantém referência para update/draw
                self._fire_shots_count += 1
                self._fire_shot_timer = 0.6

            # Fecha o olho após plantar todas as minas
            if self._fire_shots_count >= 3 and self._fire_shot_timer <= -0.3:
                self._change_fsm("CLOSING")

        # ── TERRA ─────────────────────────────────────────────────────────────
        elif state == "EARTH_SHAKE":
            # Fase 1: tremor intenso por 0.8 s
            self._move_vertical(dt)
            if t > 0.8:
                self._change_fsm("EARTH_PULL")

        elif state == "EARTH_PULL":
            # Fase 2: pedras sobem da borda inferior em lerp lento (~1.3 s)
            self._move_vertical(dt)
            if t > 1.33:
                self._change_fsm("EARTH_ORBIT")

        elif state == "EARTH_ORBIT":
            # Fase 3: pedras orbitam em lerp rápido (~1.5 s)
            self._move_vertical(dt)
            if t > 1.5:
                self._change_fsm("EARTH_FIRE")

        elif state == "EARTH_FIRE":
            # Fase 4: cada pedra dispara quando seu fire_delay zera (via update)
            self._move_vertical(dt)
            # Termina quando todas saíram da tela (dead) ou timeout
            all_gone = not self._orbital_rocks or all(
                r.phase == "fired" and r.dead for r in self._orbital_rocks
            )
            if all_gone or t > 5.0:
                self._cycles_since_fire += 1
                self._change_fsm("SCAN")

        # ── ORBES ─────────────────────────────────────────────────────────────
        elif state == "ORB_SPAWN":
            self.eye_growth = _ease_out_cubic(_clamp(t / 0.8, 0, 1))
            if t > 0.8:
                self._change_fsm("ORB_HOLD")

        elif state == "ORB_HOLD":
            px, py = self._pupil_pos()
            # Dispara 4 shards (90° de espaçamento) a cada 0.5 s, com rotação
            # progressiva de 22.5° por salva — o "corredor seguro" gira
            # continuamente, forçando o jogador a se mover em vez de ficar parado.
            if int(t * 2.5) != int((t - dt) * 2):
                for i in range(4):
                    angle_deg = i * 90.0 + self._orb_rotation
                    new_shards.append(
                        RockShard(
                            px, py, angle_deg, speed_mult=5, color=_C["EYE_IRIS_ORB"]
                        )
                    )
                self._orb_rotation += (
                    22.5  # metade do espaçamento → nunca repete posição
                )
            if t > 8.0:
                self._change_fsm("CLOSING")

        # ── SWEEP ─────────────────────────────────────────────────────────────
        elif state == "SWEEP_CHARGE":
            self._move_vertical(dt)
            self.eye_growth = _ease_out_cubic(_clamp(t / 1.2, 0, 1))

            # Rastreia o jogador continuamente APENAS até 70% do carregamento.
            # A partir daí a mira trava — o jogador tem ~0.5 s para sair da área.
            _LOCK_THRESHOLD = 0.70
            charge_progress = t / 1.8  # 1.8 s = duração total do SWEEP_CHARGE
            if charge_progress < _LOCK_THRESHOLD:
                px, py = self._pupil_pos()
                raw = math.atan2(player_y - py, player_x - px)
                # Normaliza para [0, 2π] antes de clampar, evitando que ângulos
                # negativos (jogador acima do boss) sejam espelhados para a direita
                raw_norm = raw % (2 * math.pi)
                self._sweep_base_angle = raw_norm
                self._sweep_locked_angle = self._sweep_base_angle
            elif not self._sweep_lock_done:
                # Primeira vez que cruza o limiar: grava posição do jogador e trava
                self._sweep_base_angle = self._sweep_locked_angle
                self._sweep_lock_done = True

            if t > 1.8:
                self._change_fsm("SWEEP_FIRE")

        elif state == "SWEEP_FIRE":
            px, py = self._pupil_pos()

            # (A trava de mira "Frame 1" foi removida daqui porque
            # a mira já está perfeitamente cravada do SWEEP_CHARGE)

            fire_duration = 0.9
            delay = 0.2  # fragmentos saem 0.2 s "atrás" do feixe visual
            progress = _clamp(t / fire_duration, 0, 1)

            # 1. O LASER VISUAL varre imediatamente a partir da mira travada
            self._sweep_angle = (
                self._sweep_locked_angle
                - self._sweep_total / 2
                + progress * self._sweep_total
            )

            # 2. OS FRAGMENTOS CIANO saem com delay, seguindo o mesmo arco
            if t > delay:
                shoot_progress = _clamp((t - delay) / fire_duration, 0, 1)
                shoot_angle = (
                    self._sweep_locked_angle
                    - self._sweep_total / 2
                    + shoot_progress * self._sweep_total
                )
                bucket = int(math.degrees(shoot_angle) / 4)
                if bucket not in self._shards_fired_at:
                    self._shards_fired_at.add(bucket)
                    new_shards.append(
                        RockShard(
                            px,
                            py,
                            math.degrees(shoot_angle),
                            speed_mult=1.3,
                            color=_C["SWEEP_BEAM"],
                        )
                    )

            if t > fire_duration + delay + 0.3:
                self._change_fsm("CLOSING")

        # ── FECHAMENTO ────────────────────────────────────────────────────────
        elif state == "CLOSING":
            self._move_vertical(dt)
            self.eye_growth = 1.0 - _ease_out_cubic(_clamp(t / 0.6, 0, 1))
            if self.eye_growth <= 0.01:
                self.eye_growth = 0.0
                # Atualiza contador de ciclos sem FIRE
                if self._prev_fsm_state == "FIRE":
                    self._cycles_since_fire = 0
                else:
                    self._cycles_since_fire += 1
                self._change_fsm("SCAN")

    # =========================================================================
    # MOVIMENTO VERTICAL
    # =========================================================================

    def _move_vertical(self, dt: float) -> None:
        margin_y = 40
        speed = getattr(Config, "GOLEM_SPEED", 75)
        self.y += self.direction * speed * dt
        # Limita movimento entre a parte superior e metade da tela (ou um pouco mais)
        # Ajustado para não descer demais e atrapalhar o jogador
        if self.y <= margin_y or self.y >= self._screen_h // 2:
            self.direction *= -1

    # =========================================================================
    # DANO
    # =========================================================================

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.dead = True
            logger.info("StoneGolemBoss derrotado!")

    # =========================================================================
    # DESENHO
    # =========================================================================

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        S = self.SCALE
        ox = int(self.x + self._jitter_x)
        oy = int(self.y + self._current_float_y + self._jitter_y)

        # ── Pedras orbitais ATRÁS do boss (sin < 0) ───────────────────────────
        for rock in self._orbital_rocks:
            if rock.behind_boss:
                rock.draw(surface)

        # ── 1. Corpo pré-baked (Topo e Base) ───────────────────────────────────
        if self._body_surf_top:
            surface.blit(self._body_surf_top, (ox, oy))
        if self._body_surf_bottom:
            surface.blit(self._body_surf_bottom, (ox, oy + (_EYE_ROW_BELOW + 1) * S))

        # ── 2. Linhas adjacentes ao olho (redesenhadas por frame) ─────────────
        eye_offset = int(self.eye_growth * S)
        for row_idx in (_EYE_ROW_ABOVE, _EYE_ROW, _EYE_ROW_BELOW):
            for col_idx, key in enumerate(_PIXEL_MAP[row_idx]):
                if key is None:
                    continue
                if row_idx == _EYE_ROW and _EYE_COL_START <= col_idx <= _EYE_COL_END:
                    continue

                color = _C[key]
                px_draw = ox + col_idx * S
                py_draw = oy + row_idx * S

                if _EYE_COL_START <= col_idx <= _EYE_COL_END:
                    if row_idx == _EYE_ROW_ABOVE:
                        py_draw -= eye_offset
                    elif row_idx == _EYE_ROW_BELOW:
                        py_draw += eye_offset

                pygame.draw.rect(surface, color, (px_draw, py_draw, S, S))

        # ── Visor / olho ──────────────────────────────────────────────────────
        self._draw_eye(surface, ox, oy, S, eye_offset)

        # ── Thruster ──────────────────────────────────────────────────────────
        self._draw_thruster(surface, ox, oy, S)

        # ── Particulas de carga ───────────────────────────────────────────────
        for p in self._charge_particles:
            p.draw(surface)

        # ── Cone de sweep ─────────────────────────────────────────────────────
        if self.fsm_state in ("SWEEP_CHARGE", "SWEEP_FIRE"):
            self._draw_sweep_cone(surface)
        if self.fsm_state == "SWEEP_FIRE":
            self._draw_sweep_beam(surface)

        # ── Nucleo pulsante (CHARGE / SWEEP_CHARGE) ───────────────────────────
        if self.fsm_state in ("CHARGE", "SWEEP_CHARGE"):
            self._draw_charge_core(surface)

        # ── Pedras orbitais NA FRENTE do boss (sin >= 0) ou disparadas ────────
        for rock in self._orbital_rocks:
            if not rock.behind_boss:
                rock.draw(surface)

        # ── Barra de vida ─────────────────────────────────────────────────────
        self._draw_health_bar(surface, ox, oy)

    def _draw_eye(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
        eye_offset: int,
    ) -> None:
        state = self.fsm_state

        if state in {"OPENING", "CHARGE", "FIRE"}:
            bg_col, iris_col = _C["EYE_BG_LASER"], _C["EYE_IRIS_LASER"]
        elif state in {"EARTH_SHAKE", "EARTH_PULL", "EARTH_ORBIT", "EARTH_FIRE"}:
            bg_col, iris_col = _C["EYE_BG_EARTH"], _C["EYE_IRIS_EARTH"]
        elif state in {"ORB_SPAWN", "ORB_HOLD", "ORB_FIRE"}:
            bg_col, iris_col = _C["EYE_BG_ORB"], _C["EYE_IRIS_ORB"]
        elif state in {"SWEEP_CHARGE", "SWEEP_FIRE"}:
            bg_col, iris_col = _C["EYE_BG_SWEEP"], _C["EYE_IRIS_SWEEP"]
        else:
            bg_col, iris_col = _C["EYE_BG_DEFAULT"], _C["EYE_IRIS_DEFAULT"]

        visor_x = ox + _EYE_COL_START * S
        eye_y = oy + _EYE_ROW * S
        visor_h = S + eye_offset * 2
        visor_y = eye_y - eye_offset

        pygame.draw.rect(surface, bg_col, (visor_x, visor_y, S * 5, visor_h))

        iris_x = visor_x + S + self._scan_step * S
        pygame.draw.rect(surface, iris_col, (iris_x, visor_y, S * 3, visor_h))

        reflex_x = visor_x + S * 2 + self._scan_step * S
        reflex_y = visor_y + 1
        pygame.draw.rect(surface, _C["PUPIL"], (reflex_x, reflex_y, S, S))

    def _draw_thruster(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        cx = ox + self.w // 2
        start_y = oy + self.h
        pygame.draw.rect(surface, (255, 255, 255), (cx - S, start_y, S * 2, S))

        rings = 5
        max_drop = S * 14
        speed = 2.0
        t = self._time
        for i in range(rings):
            phase = ((t * speed) + (i / rings)) % 1.0
            w = int(S * 10 * (1 - phase))
            h = max(S, int(S * 4 * (1 - phase)))
            y = start_y + int(phase * max_drop) + S
            alpha = max(0, int(255 * (1 - phase**2)))
            if w < S:
                continue
            if phase < 0.15:
                color = (255, 255, 255)
            elif phase < 0.50:
                color = (157, 212, 240)
            else:
                color = (91, 159, 200)

            # ── Otimização: Reutiliza Surface pré-alocada ──────────────────
            rs = self._thruster_surfs[i]
            rs.fill((0, 0, 0, 0))
            pygame.draw.rect(rs, (*color, alpha), (0, 0, w, h), S)
            surface.blit(rs, (cx - w // 2, y - h // 2))

    def _draw_sweep_cone(self, surface: pygame.Surface) -> None:
        px, py = self._pupil_pos()
        # Aumentado para garantir que saia da tela em qualquer ângulo
        cone_len = max(self._screen_w, self._screen_h) * 2.5
        half = self._sweep_total / 2
        alpha = (
            int(38 + math.sin(self._time * 20) * 12)
            if self.fsm_state == "SWEEP_CHARGE"
            else 40
        )

        # Pega a mira atual: usa o ângulo travado se já foi cravado, senão o base
        base_angle = getattr(self, "_sweep_locked_angle", None)
        if base_angle is None or not getattr(self, "_sweep_lock_done", False):
            base_angle = getattr(self, "_sweep_base_angle", math.pi / 2)

        # ── Otimização: Reutiliza Surface pré-alocada ──────────────────
        self._cone_surf.fill((0, 0, 0, 0))
        r, g, b = _C["SWEEP_BEAM"]

        pts = [
            (int(px), int(py)),
            (
                int(px + math.cos(base_angle - half) * cone_len),
                int(py + math.sin(base_angle - half) * cone_len),
            ),
            (
                int(px + math.cos(base_angle + half) * cone_len),
                int(py + math.sin(base_angle + half) * cone_len),
            ),
        ]
        pygame.draw.polygon(self._cone_surf, (r, g, b, alpha), pts)
        surface.blit(self._cone_surf, (0, 0))

    def get_sweep_beam(self) -> Optional[Tuple[float, float, float, float]]:
        """
        Retorna (px, py, ex, ey) da linha do feixe sweep quando ativo,
        ou None se o boss não está em SWEEP_FIRE.
        Usado por playing.py para detecção de colisão com a nave.
        """
        if self.fsm_state != "SWEEP_FIRE":
            return None
        px, py = self._pupil_pos()
        beam_len = max(self._screen_w, self._screen_h) * 2.5
        ex = px + math.cos(self._sweep_angle) * beam_len
        ey = py + math.sin(self._sweep_angle) * beam_len
        return px, py, ex, ey

    def _draw_sweep_beam(self, surface: pygame.Surface) -> None:
        px, py = self._pupil_pos()
        angle = self._sweep_angle
        # Aumentado para consistência com o cone
        beam_len = max(self._screen_w, self._screen_h) * 2.5
        ex = px + math.cos(angle) * beam_len
        ey = py + math.sin(angle) * beam_len
        r, g, b = _C["SWEEP_BEAM"]

        # ── Otimização: Reutiliza Surfaces pré-alocadas ──────────────────
        self._halo_surf.fill((0, 0, 0, 0))
        pygame.draw.line(
            self._halo_surf,
            (r, g, b, 77),
            (int(px), int(py)),
            (int(ex), int(ey)),
            self.SCALE * 3,
        )
        surface.blit(self._halo_surf, (0, 0))

        pygame.draw.line(
            surface,
            (255, 255, 255),
            (int(px), int(py)),
            (int(ex), int(ey)),
            max(1, self.SCALE),
        )

    def _draw_charge_core(self, surface: pygame.Surface) -> None:
        px, py = self._pupil_pos()
        S = self.SCALE
        t = self.fsm_ticks
        color = (
            _C["EYE_IRIS_LASER"] if self.fsm_state == "CHARGE" else _C["EYE_IRIS_SWEEP"]
        )
        rot = self._time * (10 if self.fsm_state == "CHARGE" else 20)

        if t > 1.0:
            idx = 2
        elif t > 0.6:
            idx = 1
        else:
            idx = 0

        if idx == 0:
            pygame.draw.rect(surface, color, (int(px) - S // 2, int(py) - S // 2, S, S))
        elif idx == 1:
            pygame.draw.rect(
                surface, color, (int(px) - S // 2, int(py) - S * 2, S, S * 4)
            )
            pygame.draw.rect(
                surface, color, (int(px) - S * 2, int(py) - S // 2, S * 4, S)
            )
            pygame.draw.rect(
                surface, _C["PUPIL"], (int(px) - S // 2, int(py) - S // 2, S, S)
            )
        else:
            pygame.draw.rect(
                surface, color, (int(px) - S // 2, int(py) - S * 3, S, S * 6)
            )
            pygame.draw.rect(
                surface, color, (int(px) - S * 3, int(py) - S // 2, S * 6, S)
            )
            pygame.draw.rect(
                surface, color, (int(px) - S * 2, int(py) - S * 2, S * 4, S * 4)
            )
            for i in range(4):
                a = math.radians(rot + i * 90)
                bx = int(px + math.cos(a) * S * 2)
                by = int(py + math.sin(a) * S * 2)
                pygame.draw.rect(surface, _C["PUPIL"], (bx - S // 2, by - S // 2, S, S))

    def _draw_health_bar(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
    ) -> None:
        bar_w = self.w + 16
        bar_x = ox - 8
        bar_y = oy - 14
        bar_h = 7
        pygame.draw.rect(
            surface, (30, 30, 30), (bar_x, bar_y, bar_w, bar_h), border_radius=3
        )
        hp = max(0.0, self.health / self.max_health)
        hp_color = (
            int(220 * (1 - hp) + 60 * hp),
            int(200 * hp),
            40,
        )
        fw = int(bar_w * hp)
        if fw > 0:
            pygame.draw.rect(
                surface, hp_color, (bar_x, bar_y, fw, bar_h), border_radius=3
            )
        pygame.draw.rect(
            surface, (180, 180, 180), (bar_x, bar_y, bar_w, bar_h), 1, border_radius=3
        )
