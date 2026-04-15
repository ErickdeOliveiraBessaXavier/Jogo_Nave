"""
Elemental Robot — Inimigo Voador de Sobrecarga Elemental

Inimigo de nível intermediário. Padrão Arc (sem herança):
- Classe independente, sem herança
- Retorna projéteis para o EntityManager adicionar
- Visual pixel-art com pygame.draw (sem sprites)
- EMP slowdown automático via enemy_dt

Sistema de dano ao jogador:
- EnergyOrb: projétil lançado na direção do jogador, remove 1 vida
- A detecção é feita via rect collision em playing.py/_check_ship_damage()
- Todas as entidades expõem .rect, .dead e .causes_damage

FSM de estados (fiel ao arquivo HTML de referência):
  IDLE       → flutua (3 steps discretos, 2 s, igual ao idleFloat CSS),
               olho varre lateralmente (idleLookInner), pisca (idleBlink) (3 s)
  CHARGING   → corpo vibra (shake), braços sobem, partículas convergem para a antena,
               aura cresce de 0.5× a 3.5× (growSphere) (1.5 s)
  FIRING     → dispara EnergyOrb + recuo com rotação (recoil) → RECOIL
  RECOIL     → decai o deslocamento de recuo (0.35 s) → IDLE
  DYING      → flash + fade out (0.8 s) → dead = True

Ataque: sorteia aleatoriamente entre 3 temas visuais:
  'inferno'  → projétil laranja/vermelho
  'toxina'   → projétil verde neon
  'nevasca'  → projétil azul gelo

Movimento:
  - Flutua verticalmente em 3 degraus discretos: 0 px → −3 px → −5 px (período 2 s)
    fiel ao CSS: animation: idleFloat 2s infinite steps(3)
  - Flutuação pausada durante CHARGING / FIRING / RECOIL (HTML: animation: none)
  - Deriva horizontalmente para se manter em tela (bounce nas bordas)

Animações implementadas (mapeamento HTML → Python):
  idleFloat       → _float_y discretizado (3 steps, 2 s)
  idleBlink       → _blink_open + squish Y do olho
  idleLookInner   → _scan_step (−1, 0, +1)
  idleArms        → _arm_dy oscilação ±4 px em IDLE
  antennaPulse    → glow ciano pulsante no topo da antena em IDLE
  shake           → _jitter_x/_jitter_y em CHARGING
  chargeArmLeft/R → _arm_dy = −2 px progressivo em CHARGING
  growSphere      → _aura_scale 0.5 → 3.5 em CHARGING
  shootSphere     → aura ocultada + EnergyOrb em FIRING
  recoil          → _recoil_x/_recoil_y/_recoil_rot em RECOIL
  thrustRings     → anéis dinâmicos (estilo StoneGolemBoss) em _draw_thruster
"""

import logging
import math
import random
from typing import Optional, Tuple

import pygame

from ..core.config import config as Config
from ..entities.bot_elemental_pixel_map import ANTENNA_COL_END as _ANTENNA_COL_END
from ..entities.bot_elemental_pixel_map import ANTENNA_COL_START as _ANTENNA_COL_START
from ..entities.bot_elemental_pixel_map import ANTENNA_ROW_END as _ANTENNA_ROW_END
from ..entities.bot_elemental_pixel_map import ANTENNA_ROW_START as _ANTENNA_ROW_START
from ..entities.bot_elemental_pixel_map import ATTACK_PALETTES as _ATTACK_PALETTES
from ..entities.bot_elemental_pixel_map import EYE_LEFT_COL_END as _EYE_LEFT_COL_END
from ..entities.bot_elemental_pixel_map import EYE_LEFT_COL_START as _EYE_LEFT_COL_START
from ..entities.bot_elemental_pixel_map import EYE_RIGHT_COL_END as _EYE_RIGHT_COL_END
from ..entities.bot_elemental_pixel_map import (
    EYE_RIGHT_COL_START as _EYE_RIGHT_COL_START,
)
from ..entities.bot_elemental_pixel_map import EYE_ROW_END as _EYE_ROW_END
from ..entities.bot_elemental_pixel_map import EYE_ROW_START as _EYE_ROW_START
from ..entities.bot_elemental_pixel_map import PIXEL_COLS as _PIXEL_COLS
from ..entities.bot_elemental_pixel_map import PIXEL_MAP as _PIXEL_MAP
from ..entities.bot_elemental_pixel_map import PIXEL_ROWS as _PIXEL_ROWS
from ..entities.bot_elemental_pixel_map import THRUSTER_NEUTRAL as _THRUSTER_NEUTRAL
from ..entities.bot_elemental_pixel_map import C as _C

logger = logging.getLogger(__name__)

# Alias de cor RGB — espelha o tipo definido no pixel map
RGB = Tuple[int, int, int]

# ============================================================================


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ============================================================================
# PROJÉTIL: ENERGY ORB
# ============================================================================


class EnergyOrb:
    """
    Orbe de energia disparado pelo robô em direção ao jogador.

    Visual: Estrela de pixels multicamada (core, mid, outer) idêntica à aura
    de carregamento, mantendo o tamanho final atingido na antena.
    Causa 1 vida de dano por colisão.
    """

    SPEED = 420.0  # px/s

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        color_core: RGB,
        color_mid: RGB,
        color_outer: RGB,
        pixel_size: int,
        theme: str,
        speed_multiplier: float = 1.0,
    ):
        self.x = float(x)
        self.y = float(y)
        self.dead = False
        self.causes_damage = True
        self.theme = theme
        self.color_core = color_core
        self.color_mid = color_mid
        self.color_outer = color_outer
        self.p_s = pixel_size

        # Raio de colisão balanceado: cobre o núcleo e a camada média (2x pixel_size)
        self.size = pixel_size * 2

        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy) or 1.0
        actual_speed = self.SPEED * speed_multiplier
        self.vx = (dx / dist) * actual_speed
        self.vy = (dy / dist) * actual_speed

        self._angle = 0.0
        self._trail: list[list[float]] = []  # [x, y, alpha]

        self.rect = pygame.Rect(
            int(self.x) - self.size,
            int(self.y) - self.size,
            self.size * 2,
            self.size * 2,
        )

        # Pré-alocação de superfícies
        # O glow (halo) deve ser grande o suficiente para envolver as pontas axiais (2.5x pixel_size)
        g_size = int(pixel_size * 3)
        self._glow_surf = pygame.Surface((g_size * 2, g_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            self._glow_surf,
            (*self.color_outer, 40),
            (g_size, g_size),
            g_size,
        )
        self._trail_surf = pygame.Surface((self.p_s, self.p_s), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Rastro baseado na cor outer
        if random.random() < 0.4:
            self._trail.append([self.x, self.y, 180.0])
        for t in self._trail:
            t[2] -= 500.0 * dt
        self._trail = [t for t in self._trail if t[2] > 0]

        self.rect.x = int(self.x) - self.size
        self.rect.y = int(self.y) - self.size

        sw = getattr(Config, "SCREEN_WIDTH", 480)
        sh = getattr(Config, "SCREEN_HEIGHT", 800)
        if self.x < -100 or self.x > sw + 100 or self.y < -100 or self.y > sh + 100:
            self.dead = True

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        # Rastro
        r, g, b = self.color_outer
        for tx, ty, alpha in self._trail:
            self._trail_surf.fill((r, g, b, int(alpha * 0.4)))
            surface.blit(
                self._trail_surf,
                (int(tx) - self.p_s // 2, int(ty) - self.p_s // 2),
            )

        cx, cy = int(self.x), int(self.y)
        s = self.p_s

        # Glow (Halo)
        g_radius = self._glow_surf.get_width() // 2
        surface.blit(self._glow_surf, (cx - g_radius, cy - g_radius))

        # Estrela de energia pixelada (mesma geometria da aura)

        # 1. Camada OUTER: Diagonais ±1 e Pontas Axiais ±2
        for dx, dy in (
            (-s, -s),
            (s, -s),
            (-s, s),
            (s, s),  # diagonais
            (0, -s * 2),
            (0, s * 2),
            (-s * 2, 0),
            (s * 2, 0),  # pontas axiais
        ):
            pygame.draw.rect(
                surface, self.color_outer, (cx + dx - s // 2, cy + dy - s // 2, s, s)
            )

        # 2. Camada MID: Cruz central ±1
        for dx, dy in ((0, -s), (0, s), (-s, 0), (s, 0)):
            pygame.draw.rect(
                surface, self.color_mid, (cx + dx - s // 2, cy + dy - s // 2, s, s)
            )

        # 3. Camada CORE: Pixel central
        pygame.draw.rect(surface, self.color_core, (cx - s // 2, cy - s // 2, s, s))


# ============================================================================
# PARTÍCULA DE CARGA (visual, não causa dano)
# ============================================================================


class _ChargeParticle:
    """Partícula que converge para a ponta da antena durante CHARGING.

    Forma e comportamento variam por tema para espelhar as animações CSS:
      inferno  → quadrado 4×4 com cruz de 'mid'     (suckInInferno)
      toxina   → quadrado 6×6 com dois diagonais    (suckInToxina)
      nevasca  → floco de neve 2×2 com 12 sombras   (suckInNevasca) + rotação
    """

    def __init__(
        self,
        antenna_x: float,
        antenna_y: float,
        palette: dict[str, RGB],
        theme: str,
    ):
        self.theme = theme
        self.angle = random.uniform(0, math.pi * 2)
        self.dist = 80.0 + random.uniform(0, 40)
        self._start_dist = self.dist
        self._orbit_speed = 0.06 + random.uniform(0, 0.07)
        self._radial_speed = 70.0 + random.uniform(0, 60)
        self._spin = 0.0  # rotação para nevasca

        # Tamanho por tema (espelha width/height CSS da .particle)
        if theme == "inferno":
            self.size = 4
        elif theme == "toxina":
            self.size = 6
        else:  # nevasca
            self.size = 2
            self._spin = random.uniform(1.5, 3.0)  # suckInNevasca gira

        self.color_core = palette["core"]
        self.color_mid = palette["mid"]
        self.color_outer = palette["outer"]

        self.ax = antenna_x
        self.ay = antenna_y
        self.px = antenna_x + math.cos(self.angle) * self.dist
        self.py = antenna_y + math.sin(self.angle) * self.dist
        self.dead = False
        self._rot_angle = random.uniform(0, math.pi * 2)

        sz = max(self.size * 6, 20)
        self._surf = pygame.Surface((sz, sz), pygame.SRCALPHA)

    def _rebuild_surf(self, alpha: int) -> None:
        """Redesenha a superfície da partícula com o alpha correto."""
        self._surf.fill((0, 0, 0, 0))
        sz = self._surf.get_width()
        cx = sz // 2
        cy = sz // 2
        s = self.size
        a = max(0, min(255, alpha))

        if self.theme == "inferno":
            # Quadrado central + cruz de 'mid' (4 direções)
            pygame.draw.rect(
                self._surf, (*self.color_core, a), (cx - s // 2, cy - s // 2, s, s)
            )
            for dx, dy in ((s, 0), (-s, 0), (0, s), (0, -s)):
                pygame.draw.rect(
                    self._surf,
                    (*self.color_mid, a),
                    (cx + dx - s // 2, cy + dy - s // 2, s, s),
                )

        elif self.theme == "toxina":
            # Quadrado central + 2 diagonais
            pygame.draw.rect(
                self._surf, (*self.color_core, a), (cx - s // 2, cy - s // 2, s, s)
            )
            pygame.draw.rect(
                self._surf,
                (*self.color_mid, a),
                (cx + 2 - s // 2, cy + 2 - s // 2, s, s),
            )
            pygame.draw.rect(
                self._surf,
                (*self.color_outer, a),
                (cx - 2 - s // 2, cy - 2 - s // 2, s, s),
            )

        else:  # nevasca — floco de neve 2×2 com projeções
            # Centro
            pygame.draw.rect(self._surf, (*self.color_core, a), (cx - 1, cy - 1, 2, 2))
            # Eixos ±4 px (mid) e ±8 px (outer)
            for dist_px, col in ((4, self.color_mid), (8, self.color_outer)):
                for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    pygame.draw.rect(
                        self._surf,
                        (*col, a),
                        (cx + ddx * dist_px - 1, cy + ddy * dist_px - 1, 2, 2),
                    )
            # Diagonais ±4 px (outer)
            for ddx, ddy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                pygame.draw.rect(
                    self._surf,
                    (*self.color_outer, a),
                    (cx + ddx * 4 - 1, cy + ddy * 4 - 1, 2, 2),
                )

    def update(self, dt: float, antenna_x: float, antenna_y: float) -> None:
        # Multiplicador de velocidade que aumenta conforme a distância diminui (espiral acelerada)
        speed_mul = 1.0 + (1.0 - _clamp(self.dist / self._start_dist, 0, 1)) * 3.0

        self.dist -= self._radial_speed * speed_mul * dt
        self.angle += self._orbit_speed * speed_mul * (dt * 60)
        self._rot_angle += self._spin * dt

        if self.dist < 2:
            self.dead = True
            return
        self.ax = antenna_x
        self.ay = antenna_y
        self.px = antenna_x + math.cos(self.angle) * self.dist
        self.py = antenna_y + math.sin(self.angle) * self.dist

    def draw(self, surface: pygame.Surface) -> None:
        ratio = _clamp(self.dist / self._start_dist * 2, 0, 1)
        if ratio < 0.05:
            return
        self._rebuild_surf(int(ratio * 220))
        sz = self._surf.get_width()

        if self.theme == "nevasca" and self._rot_angle != 0:
            rotated = pygame.transform.rotate(self._surf, math.degrees(self._rot_angle))
            rw, rh = rotated.get_size()
            surface.blit(rotated, (int(self.px) - rw // 2, int(self.py) - rh // 2))
        else:
            surface.blit(self._surf, (int(self.px) - sz // 2, int(self.py) - sz // 2))


# ============================================================================
# INIMIGO PRINCIPAL
# ============================================================================


class ElementalRobot:
    """
    Inimigo voador de sobrecarga elemental.

    Padrão Arc:
    - update(dt, enemy_dt, player_x, player_y) → list[EnergyOrb]
    - draw(surface)
    - Expõe .rect, .dead, .health, .causes_damage
    """

    SCALE = 6  # px por "pixel" do mapa
    # Mini-boss: precisa de 25 tiros para ser eliminado.
    MAX_HEALTH = 25
    HIT_SCORE = 5000

    # Durações dos estados (segundos)
    _DUR_IDLE = 3.0
    _DUR_CHARGING = 1.5
    _DUR_RECOIL = 0.35
    _DUR_DYING = 0.8

    # Parâmetros de movimento
    # idleFloat CSS: period=2s, steps(3) → 0px / -3px / -5px
    _FLOAT_PERIOD = 2.0  # segundos por ciclo completo
    _FLOAT_STEPS = (0, -3, -5)  # px — 3 posições discretas
    _DRIFT_SPEED = 55.0  # px/s — deriva horizontal
    _ENTRY_SPEED = 180.0  # px/s — descida inicial

    # Arm idle: translateY(0 → 4px) em steps(1) a 1 s
    _ARM_IDLE_OFFSETS = (0, 4)  # px — posições do braço em IDLE

    def __init__(
        self,
        x: float,
        y: float,
        health: Optional[int] = None,
        difficulty_multiplier: float = 1.0,
        start_visible: bool = False,
    ):
        S = self.SCALE
        self._screen_w = getattr(Config, "SCREEN_WIDTH", 280)
        self._screen_h = getattr(Config, "SCREEN_HEIGHT", 400)

        self.w = _PIXEL_COLS * S  # largura em px
        self.h = _PIXEL_ROWS * S  # altura em px

        # Posição inicial acima da tela
        self.x = float(x)
        self.y = float(y) if start_visible else -float(self.h)
        self._target_y = float(y)  # onde para após entrar

        # Aplicar multiplicador de dificuldade
        self.difficulty_multiplier = difficulty_multiplier
        self.max_health = int(self.MAX_HEALTH * difficulty_multiplier)
        self.health = health if health is not None else self.max_health
        self.dead = False
        self.just_died = False  # True por um ciclo quando entra em DYING
        self.causes_damage = False  # contato não causa dano direto
        self.hit_score = self.HIT_SCORE

        # Ajustar durações e velocidades com base na dificuldade
        # (mais difícil = menos tempo parado, projéteis mais rápidos)
        self._dur_idle = self._DUR_IDLE / (1.0 + (difficulty_multiplier - 1.0) * 0.5)
        self._orb_speed_mult = 1.0 + (difficulty_multiplier - 1.0) * 0.3

        # Velocidade de deriva horizontal
        self._drift_vx = (
            self._DRIFT_SPEED
            * random.choice([-1, 1])
            * (1.0 + (difficulty_multiplier - 1.0) * 0.2)
        )

        # ── FSM ──────────────────────────────────────────────────────────────
        self.fsm_state = "ENTERING"
        self._fsm_timer = 0.0

        # ── Tema do ataque atual ──────────────────────────────────────────────
        self._attack_theme: str = "nevasca"
        self._palette: dict[str, RGB] = _ATTACK_PALETTES["nevasca"]

        # Cores dinâmicas do corpo (mudam ao carregar; espelham as CSS vars)
        # Neutro inicial corresponde ao :root do HTML
        self._body_outline: RGB = _C["A"]  # --robot-outline-neutral #0b0c10
        self._body_main: RGB = _C["B"]  # --robot-body-neutral    #3a4f63
        self._body_dark: RGB = _C["DARK_NEUTRAL"]  # --robot-dark-neutral    #263442
        self._body_light: RGB = _C["LIGHT_NEUTRAL"]  # --robot-light-neutral   #637a8c
        self._thruster_colors: list[RGB] = list(_THRUSTER_NEUTRAL)

        # ── Olho: abertura, piscar e varredura ───────────────────────────────
        self._eye_squish = 1.0  # 1.0 = aberto, 0.6 = charging, 0.1 = firing
        self._blink_timer = 0.0
        self._blink_open = True
        self._blink_interval = random.uniform(3.5, 6.0)
        self._scan_step = 0  # -1, 0, +1 — posição horizontal da íris

        # ── Braço ─────────────────────────────────────────────────────────────
        # _arm_dy: deslocamento vertical do braço em pixels de tela
        #  IDLE:     oscila entre 0 e +4 px (idleArms)
        #  CHARGING: move progressivamente para -16px (chargeArmLeft/Right)
        #  Outras:   0
        self._arm_dy: float = 0.0

        # ── Recoil (recuo ao disparar) ────────────────────────────────────────
        self._recoil_x = 0.0
        self._recoil_y = 0.0
        self._recoil_rot = 0.0  # graus — espelha --recoil-rotate
        self._recoil_x0 = 0.0  # valor inicial (para interpolação limpa)
        self._recoil_y0 = 0.0
        self._recoil_rot0 = 0.0

        # ── Flutuação discreta (idleFloat steps(3)) ───────────────────────────
        self._float_phase = random.uniform(0, self._FLOAT_PERIOD)  # offset de fase
        self._float_y = 0.0

        # ── Jitter (vibração durante CHARGING — shake CSS) ────────────────────
        self._jitter_x = 0.0
        self._jitter_y = 0.0

        # ── Partículas de carga ───────────────────────────────────────────────
        self._charge_particles: list[_ChargeParticle] = []

        # ── Aura / núcleo da antena ───────────────────────────────────────────
        self._aura_scale = 0.0
        self._aura_visible = False

        # ── Pulso da antena (antennaPulse em IDLE) ────────────────────────────
        self._antenna_pulse_alpha = 0  # 0-255; sobe/desce a cada 1.25 s

        # ── Fade out (DYING) ──────────────────────────────────────────────────
        self._alpha = 255

        # ── Tempo global ─────────────────────────────────────────────────────
        self._time = 0.0

        # ── Colisão ───────────────────────────────────────────────────────────
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # ── Superfícies pré-alocadas ──────────────────────────────────────────
        _s = self.SCALE
        # Otimização do propulsor (anéis dinâmicos similares ao StoneGolemBoss)
        self._thruster_surfs = [
            pygame.Surface((_s * 10 + 2, _s * 4 + 2), pygame.SRCALPHA) for _ in range(5)
        ]
        self._aura_surf = pygame.Surface((_s * 24, _s * 24), pygame.SRCALPHA)
        self._pulse_surf = pygame.Surface((_s * 6, _s * 6), pygame.SRCALPHA)

    # =========================================================================
    # PROPRIEDADES CALCULADAS
    # =========================================================================

    def _antenna_tip_center(self) -> Tuple[float, float]:
        """Centro da ponta da antena (onde a aura aparece)."""
        S = self.SCALE
        ox = self.x + self._jitter_x
        oy = self.y + self._float_y + self._jitter_y
        tip_cx = ox + (_ANTENNA_COL_START + 2) * S
        tip_cy = oy + (_ANTENNA_ROW_START + 2) * S
        return tip_cx, tip_cy

    def _draw_x(self) -> float:
        return self.x + self._jitter_x + self._recoil_x

    def _draw_y(self) -> float:
        return self.y + self._float_y + self._jitter_y + self._recoil_y

    # =========================================================================
    # FSM
    # =========================================================================

    def _transition(self, new_state: str) -> None:
        self.fsm_state = new_state
        self._fsm_timer = 0.0
        if new_state == "DYING":
            self.just_died = True  # sinaliza para o sistema externo disparar a explosão

    def _run_fsm(
        self,
        dt: float,
        player_x: float,
        player_y: float,
    ) -> list[EnergyOrb]:
        spawned: list[EnergyOrb] = []
        self._fsm_timer += dt

        if self.fsm_state == "ENTERING":
            self.y += self._ENTRY_SPEED * dt
            if self.y >= self._target_y:
                self.y = self._target_y
                self._transition("IDLE")

        elif self.fsm_state == "IDLE":
            self._tick_idle(dt)
            if self._fsm_timer >= self._DUR_IDLE:
                self._start_charging()

        elif self.fsm_state == "CHARGING":
            self._tick_charging(dt)
            # Transição: Tempo mínimo passado E todas as partículas aglomeradas no centro
            if self._fsm_timer >= self._DUR_CHARGING and not self._charge_particles:
                self._transition("FIRING")

        elif self.fsm_state == "FIRING":
            orbs = self._fire(player_x, player_y)
            spawned.extend(orbs)
            self._transition("RECOIL")

        elif self.fsm_state == "RECOIL":
            # Decaimento limpo a partir dos valores iniciais (ease-out-cubic)
            frac = _ease_out_cubic(self._fsm_timer / self._DUR_RECOIL)
            inv = 1.0 - frac
            self._recoil_x = self._recoil_x0 * inv
            self._recoil_y = self._recoil_y0 * inv
            self._recoil_rot = self._recoil_rot0 * inv
            self._eye_squish = max(
                1.0, self._eye_squish + (1.0 - self._eye_squish) * frac
            )
            if self._fsm_timer >= self._DUR_RECOIL:
                self._recoil_x = self._recoil_y = self._recoil_rot = 0.0
                self._eye_squish = 1.0
                self._arm_dy = 0.0
                self._reset_palette()
                self._transition("IDLE")

        elif self.fsm_state == "DYING":
            # Dispara explosão no primeiro frame de DYING e marca dead imediatamente.
            # A animação de morte é delegada ao ExplosionPool (gerenciado externamente).
            if self._fsm_timer == dt:  # primeiro tick após transição
                pass  # sinal já foi dado via just_died (ver abaixo)
            if self._fsm_timer >= self._DUR_DYING:
                self.dead = True

        return spawned

    # ── Helpers de estado ────────────────────────────────────────────────────

    def _tick_idle(self, dt: float) -> None:
        """
        Varredura lateral dos olhos (idleLookInner) e piscar (idleBlink).
        Braço oscila ±4 px (idleArms steps(1) a 1 s).
        """
        # Varredura: keyframes 0%=0, 15%=-1, 30%=0, 65%=+1, 80%=0 → cosseno
        t_cycle = self._time % 4.0  # período visual ~4 s
        if t_cycle < 0.6:
            self._scan_step = 0
        elif t_cycle < 1.2:
            self._scan_step = -1
        elif t_cycle < 2.0:
            self._scan_step = 0
        elif t_cycle < 3.2:
            self._scan_step = 1
        else:
            self._scan_step = 0

        # Piscar (idleBlink): 92% → scaleY(0.1), 95% → abre
        self._blink_timer += dt
        if self._blink_timer >= self._blink_interval:
            self._blink_open = not self._blink_open
            self._blink_timer = 0.0
            if not self._blink_open:
                self._blink_interval = 0.12
                self._eye_squish = 0.1  # olho quase fechado durante piscar
            else:
                self._blink_interval = random.uniform(3.5, 6.0)
                self._eye_squish = 1.0

        # Braço oscila (idleArms 1 s steps(1))
        arm_step = int(self._time / 0.5) % 2
        self._arm_dy = float(self._ARM_IDLE_OFFSETS[arm_step])

        # Pulso da antena (antennaPulse 2.5 s steps(2))
        pulse_step = int(self._time / 1.25) % 2
        self._antenna_pulse_alpha = 64 if pulse_step == 1 else 0

    def _start_charging(self) -> None:
        self._attack_theme = random.choice(["inferno", "toxina", "nevasca"])
        self._palette = dict(_ATTACK_PALETTES[self._attack_theme])
        self._body_outline = self._palette["body_outline"]
        self._body_main = self._palette["body_main"]
        self._body_dark = self._palette["body_dark"]
        self._body_light = self._palette["body_light"]
        self._thruster_colors = [
            self._palette["thruster_1"],
            self._palette["thruster_2"],
            self._palette["thruster_3"],
        ]
        self._aura_visible = True
        self._aura_scale = 0.0
        self._eye_squish = 0.6  # charging .eye { transform: scaleY(0.6) }
        self._scan_step = 0  # charging .pupil: sem varredura
        self._blink_open = True
        self._antenna_pulse_alpha = 0
        self._charge_particles.clear()
        self._transition("CHARGING")

    def _tick_charging(self, dt: float) -> None:
        """
        Vibração (shake), crescimento da aura (growSphere),
        braços sobem (chargeArmLeft/Right), spawn de partículas.
        """
        # Shake: translate entre (0,0) e (±2px) em steps(2) a 0.15 s
        self._jitter_x = random.choice((-2, 0, 2))
        self._jitter_y = random.choice((-2, 0, 2))

        # Aura cresce 0.5 → 3.5 (growSphere 0 → 100 %)
        progress = _clamp(self._fsm_timer / self._DUR_CHARGING, 0.0, 1.0)
        self._aura_scale = 0.5 + progress * 3.0

        # Braços sobem progressivamente: 0 → -16 px (chargeArmLeft/Right steps(3))
        step = int(progress * 3)
        arm_targets = (0, -8, -16)
        self._arm_dy = float(arm_targets[min(step, 2)])

        # Spawn de partículas (somente nos primeiros 60% do carregamento)
        if self._fsm_timer < self._DUR_CHARGING * 0.6:
            if random.random() < 0.6:
                ax, ay = self._antenna_tip_center()
                self._charge_particles.append(
                    _ChargeParticle(ax, ay, self._palette, self._attack_theme)
                )

        ax, ay = self._antenna_tip_center()
        for p in self._charge_particles:
            p.update(dt, ax, ay)
        self._charge_particles = [p for p in self._charge_particles if not p.dead]

    def _fire(self, player_x: float, player_y: float) -> list[EnergyOrb]:
        """
        Cria o projétil e define recoil com rotação.
        Fiel ao JS: recoil = 18 px, recoilDeg = -sin(angle) * 8°.
        """
        ax, ay = self._antenna_tip_center()

        # Reduzido de 3.5 para 2.5 para uma esfera de ataque um pouco menor e mais elegante
        pixel_size = int(self.SCALE * 2.5)

        orb = EnergyOrb(
            x=ax,
            y=ay,
            target_x=player_x,
            target_y=player_y,
            color_core=self._palette["core"],
            color_mid=self._palette["mid"],
            color_outer=self._palette["outer"],
            pixel_size=pixel_size,
            theme=self._attack_theme,
            speed_multiplier=self._orb_speed_mult,
        )

        dx = player_x - ax
        dy = player_y - ay
        dist = math.hypot(dx, dy) or 1.0
        sin_a = dx / dist  # seno do ângulo horizontal
        cos_a = dy / dist

        recoil_mag = 18.0
        self._recoil_x0 = -sin_a * recoil_mag
        self._recoil_y0 = cos_a * recoil_mag
        self._recoil_rot0 = -sin_a * 8.0  # --recoil-rotate: -sin(angle)*8deg
        self._recoil_x = self._recoil_x0
        self._recoil_y = self._recoil_y0
        self._recoil_rot = self._recoil_rot0

        # Olho: firing .eye { transform: scaleY(0.1) }
        self._eye_squish = 0.1

        # Oculta aura e para jitter
        self._aura_visible = False
        self._aura_scale = 0.0
        self._jitter_x = 0.0
        self._jitter_y = 0.0
        self._charge_particles.clear()

        return [orb]

    def _reset_palette(self) -> None:
        """Volta ao visual neutro após o ataque (espelha resetArmor() do JS)."""
        self._body_outline = _C["A"]
        self._body_main = _C["B"]
        self._body_dark = _C["DARK_NEUTRAL"]
        self._body_light = _C["LIGHT_NEUTRAL"]
        self._thruster_colors = list(_THRUSTER_NEUTRAL)

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update(
        self,
        dt: float,
        enemy_dt: float,
        player_x: float,
        player_y: float,
    ) -> list[EnergyOrb]:
        """
        Atualiza lógica do inimigo.

        dt        : delta-time real (s)
        enemy_dt  : delta-time com EMP aplicado
        player_x/y: posição do jogador para mira
        """
        self._time += dt
        self.just_died = False  # limpa o flag — só fica True no frame da transição

        # ── Flutuação discreta (idleFloat 2s steps(3)) ────────────────────────
        # Somente em IDLE e ENTERING (charging/firing param: animation:none)
        if self.fsm_state == "IDLE":
            phase = (
                (self._time + self._float_phase) % self._FLOAT_PERIOD
            ) / self._FLOAT_PERIOD
            step = int(phase * len(self._FLOAT_STEPS))
            step = min(step, len(self._FLOAT_STEPS) - 1)
            self._float_y = float(self._FLOAT_STEPS[step])
        else:
            self._float_y = 0.0

        # ── Deriva horizontal com bounce ──────────────────────────────────────
        if self.fsm_state not in ("ENTERING", "DYING"):
            self.x += self._drift_vx * enemy_dt
            margin = 20
            if self.x < margin:
                self.x = margin
                self._drift_vx = abs(self._drift_vx)
            elif self.x + self.w > self._screen_w - margin:
                self.x = self._screen_w - margin - self.w
                self._drift_vx = -abs(self._drift_vx)

        # ── FSM ───────────────────────────────────────────────────────────────
        spawned = self._run_fsm(enemy_dt, player_x, player_y)

        # ── Colisão ───────────────────────────────────────────────────────────
        # A sprite tem 18 colunas, mas o corpo sólido ocupa das cols 1 a 16.
        # A altura sólida vai do topo (row 0) até a base strip (row 19).
        # O propulsor (rows 20+) é tratado como efeito visual sem colisão.
        S = self.SCALE
        self.rect.width = 15 * S  # cols 1 a 16 aprox.
        self.rect.height = 20 * S  # rows 0 a 19

        # Centraliza o rect reduzido na posição visual
        self.rect.x = int(self.x + self._jitter_x + self._recoil_x) + S
        self.rect.y = int(self.y + self._float_y + self._jitter_y + self._recoil_y)

        return spawned

    def take_damage(self, amount: int = 1) -> None:
        """Reduz a vida pelo valor de 'amount' (mini-boss balanceado)."""
        if self.fsm_state == "DYING":
            return  # Ignora dano durante animação de morte
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self._transition("DYING")

    def get_points_value(self) -> int:
        return self.hit_score

    def get_explosion_type(self) -> list[RGB]:
        """Retorna a paleta atual para a explosão."""
        return [self._palette["core"], self._palette["mid"], self._palette["outer"]]

    # =========================================================================
    # DRAW
    # =========================================================================

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead or self.fsm_state == "DYING":
            return

        S = self.SCALE
        ox = int(self._draw_x())
        oy = int(self._draw_y())
        self._draw_sprite(surface, ox, oy, S)

    # ── Sub-rotinas de desenho ───────────────────────────────────────────────

    def _draw_sprite(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Renderiza a sprite completa.

        Rotação de recoil: desenha em superfície auxiliar e rotaciona.
        Fiel ao CSS: .firing .robot-sprite { transform: translate(...) rotate(...) }
        """
        if abs(self._recoil_rot) > 0.5:
            # Dimensão generosa para não clipar cantos após rotação
            tmp_w = self.w + S * 4
            tmp_h = self.h + S * 10
            tmp = pygame.Surface((tmp_w, tmp_h), pygame.SRCALPHA)
            local_ox = S * 2
            local_oy = S * 2
            self._draw_body(tmp, local_ox, local_oy, S)
            self._draw_eyes(tmp, local_ox, local_oy, S)
            self._draw_thruster(tmp, local_ox, local_oy, S)
            self._draw_aura(tmp, local_ox, local_oy, S)
            self._draw_particles(surface)  # partículas em world space
            rotated = pygame.transform.rotate(tmp, -self._recoil_rot)
            rw, rh = rotated.get_size()
            surface.blit(rotated, (ox - (rw - self.w) // 2, oy - (rh - self.h) // 2))
        else:
            self._draw_body(surface, ox, oy, S)
            self._draw_eyes(surface, ox, oy, S)
            self._draw_thruster(surface, ox, oy, S)
            self._draw_aura(surface, ox, oy, S)
            self._draw_particles(surface)

    def _draw_body(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Itera o PIXEL_MAP e pinta cada bloco com a cor adequada.

        Inset-shadow do HTML (body-main::box-shadow):
          inset 0  12px 0 current-light  → top ~2 linhas de "D" usam _body_light
          inset 0 -12px 0 current-dark   → bot ~2 linhas de "D" usam _body_dark
          meio                           → _body_main

        Braço (cols 0 e 17): offset vertical _arm_dy aplicado individualmente.
        """
        arm_cols = {0, _PIXEL_COLS - 1}

        for row_i, row in enumerate(_PIXEL_MAP):
            for col_i, cell in enumerate(row):
                if cell is None:
                    continue
                # Células dos olhos desenhadas em _draw_eyes
                if _EYE_ROW_START <= row_i <= _EYE_ROW_END and (
                    _EYE_LEFT_COL_START <= col_i <= _EYE_LEFT_COL_END
                    or _EYE_RIGHT_COL_START <= col_i <= _EYE_RIGHT_COL_END
                ):
                    continue

                # Escolha de cor
                if cell == "A":
                    color = self._body_outline
                elif cell == "B" or cell == "D":
                    color = self._body_main
                elif cell == "C":
                    color = _C["C"]
                elif cell == "E":
                    color = _C["E"]
                elif cell == "F":
                    color = self._body_light
                elif cell == "G":
                    color = self._body_dark
                elif cell == "H":
                    color = _C["H"]
                elif cell == "I":
                    color = _C["I"]
                else:
                    color = (255, 0, 255)  # magenta = letra desconhecida

                # Offset do braço
                dy_extra = int(self._arm_dy) if col_i in arm_cols else 0

                pygame.draw.rect(
                    surface,
                    color,
                    (ox + col_i * S, oy + row_i * S + dy_extra, S, S),
                )

        # ── Pulso da antena (antennaPulse em IDLE) ────────────────────────────
        if self._antenna_pulse_alpha > 0 and self.fsm_state == "IDLE":
            tip_w = (_ANTENNA_COL_END - _ANTENNA_COL_START + 1) * S
            tip_h = (_ANTENNA_ROW_END - _ANTENNA_ROW_START + 1) * S
            tip_x = ox + _ANTENNA_COL_START * S
            tip_y = oy + _ANTENNA_ROW_START * S
            # Anel interno (4 px) e externo (8 px) de glow ciano translúcido
            cyan_inner = (92, 225, 230, min(64, self._antenna_pulse_alpha))
            cyan_outer = (92, 225, 230, min(26, self._antenna_pulse_alpha // 2))
            self._pulse_surf.fill((0, 0, 0, 0))
            pw = tip_w + S * 2
            ph = tip_h + S * 2
            ps = pygame.Surface((pw, ph), pygame.SRCALPHA)
            ps.fill((0, 0, 0, 0))
            pygame.draw.rect(ps, cyan_inner, (0, 0, pw, ph))
            surface.blit(ps, (tip_x - S, tip_y - S))
            ps2 = pygame.Surface((pw + S * 2, ph + S * 2), pygame.SRCALPHA)
            ps2.fill((0, 0, 0, 0))
            pygame.draw.rect(ps2, cyan_outer, (0, 0, pw + S * 2, ph + S * 2))
            surface.blit(ps2, (tip_x - S * 2, tip_y - S * 2))

    def _draw_eyes(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Desenha os dois olhos com íris, reflexo e squish vertical.

        Squish espelha o CSS:
          IDLE     → scaleY(1.0)
          piscar   → scaleY(0.1) com fundo _body_dark (idleBlink)
          CHARGING → scaleY(0.6) com pupila da cor do tema (eye_iris)
          FIRING   → scaleY(0.1) com fundo _body_dark, pupila transparente
        """
        eye_full_h = (_EYE_ROW_END - _EYE_ROW_START + 1) * S  # altura total
        eye_h = max(1, int(eye_full_h * self._eye_squish))
        eye_y_offset = (eye_full_h - eye_h) // 2  # centraliza verticalmente

        # Cores por estado
        if self.fsm_state in ("CHARGING", "FIRING", "RECOIL"):
            bg_col = self._palette["eye_bg"]
            iris_col = self._palette["eye_iris"]
        else:
            bg_col = _C["EYE_BG_DEFAULT"]
            iris_col = _C["EYE_IRIS_DEFAULT"]

        # Em firing/blink o fundo usa current-dark
        if self.fsm_state == "FIRING" or (
            not self._blink_open and self.fsm_state == "IDLE"
        ):
            bg_col = self._body_dark

        for col_start, col_end in (
            (_EYE_LEFT_COL_START, _EYE_LEFT_COL_END),
            (_EYE_RIGHT_COL_START, _EYE_RIGHT_COL_END),
        ):
            ew = (col_end - col_start + 1) * S
            ex = ox + col_start * S
            ey = oy + _EYE_ROW_START * S + eye_y_offset

            # Fundo do olho
            pygame.draw.rect(surface, bg_col, (ex, ey, ew, eye_h))

            # Íris: oculta em FIRING e piscar fechado
            if self.fsm_state == "FIRING" or not self._blink_open:
                continue

            iris_w = S * 2
            iris_x = ex + S + self._scan_step * S
            # Íris: bottom: 2px no HTML → 1 pixel acima do fundo
            iris_y = ey + max(0, eye_h - S * 2)
            iris_h = min(eye_h, S * 2)
            pygame.draw.rect(surface, iris_col, (iris_x, iris_y, iris_w, iris_h))

            # Reflexo branco (pupil::before — canto superior esquerdo da íris)
            pygame.draw.rect(surface, _C["PUPIL"], (iris_x + 1, iris_y + 1, S, S))

    def _draw_thruster(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Propulsor dinâmico com anéis de energia que descem e diminuem.
        Fiel ao efeito do StoneGolemBoss, mas usando a paleta do ElementalRobot.
        """
        cx = ox + self.w // 2
        # O corpo visual termina na Row 19. Começamos o thruster logo abaixo (Row 20).
        start_y = oy + 20 * S

        # Pequena base fixa
        pygame.draw.rect(surface, self._thruster_colors[0], (cx - S, start_y, S * 2, S))

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

            # Cores interpoladas baseadas na paleta
            if phase < 0.15:
                color = self._thruster_colors[0]
            elif phase < 0.50:
                color = self._thruster_colors[1]
            else:
                color = self._thruster_colors[2]

            # ── Otimização: Reutiliza Surface pré-alocada ──────────────────
            rs = self._thruster_surfs[i]
            rs.fill((0, 0, 0, 0))
            pygame.draw.rect(rs, (*color, alpha), (0, 0, w, h), S)
            surface.blit(rs, (cx - w // 2, y - h // 2))

    def _draw_aura(
        self,
        surface: pygame.Surface,
        _ox: int,
        _oy: int,
        S: int,
    ) -> None:
        """
        Núcleo de energia pixel-art que cresce na ponta da antena.

        Espelha o CSS .aura com box-shadow (12 sombras):
          ±4px X/Y → cor mid    (4 direções)
          ±4px diag → cor outer  (4 cantos)
          ±8px X/Y → cor outer   (4 extremidades axiais)

        Correção: raio externo axial = 2 × base_r (era 1.5 × — incorreto).
        """
        if not self._aura_visible or self._aura_scale < 0.1:
            return

        ax, ay = self._antenna_tip_center()
        p = self._palette
        scale = self._aura_scale

        base_r = max(1, int(S * scale))
        sz = base_r * 6 + 1
        self._aura_surf = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
        self._aura_surf.fill((0, 0, 0, 0))
        center = sz

        def blit_px(dx: int, dy: int, color: RGB, alpha: int = 255) -> None:
            r, g, b = color
            self._aura_surf.fill(
                (r, g, b, max(0, min(255, alpha))),
                (center + dx - base_r // 2, center + dy - base_r // 2, base_r, base_r),
            )

        # Núcleo central (branco/core)
        blit_px(0, 0, p["core"])

        # Anel médio: ±4 px (espelha ±4px do box-shadow)
        for dx, dy in ((0, -base_r), (0, base_r), (-base_r, 0), (base_r, 0)):
            blit_px(dx, dy, p["mid"])

        # Anel externo diagonal: ±4 px (mesma distância que mid)
        for dx, dy in (
            (-base_r, -base_r),
            (base_r, -base_r),
            (-base_r, base_r),
            (base_r, base_r),
        ):
            blit_px(dx, dy, p["outer"], 200)

        # Anel externo axial: ±8 px = 2 × base_r (espelha ±8px do box-shadow)
        ext2 = base_r * 2
        for dx, dy in ((0, -ext2), (0, ext2), (-ext2, 0), (ext2, 0)):
            blit_px(dx, dy, p["outer"], 160)

        half = sz
        surface.blit(self._aura_surf, (int(ax) - half, int(ay) - half))

    def _draw_particles(self, surface: pygame.Surface) -> None:
        """Desenha todas as partículas de carga ativas."""
        for p in self._charge_particles:
            p.draw(surface)

    def _draw_health_bar(
        self,
        surface: pygame.Surface,
        _ox: int,
        _oy: int,
    ) -> None:
        # Barra de vida oculta: mini-boss sem indicador visível de HP.
        pass
