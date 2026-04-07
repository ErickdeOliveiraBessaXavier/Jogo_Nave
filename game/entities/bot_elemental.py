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
  IDLE       → flutua, olho varre lateralmente (3 s)
  CHARGING   → corpo vibra, partículas convergem para a antena (1.5 s)
  FIRING     → dispara EnergyOrb + recuo (recoil) → IDLE
  DYING      → flash + fade out (0.8 s) → dead = True

Ataque: sorteia aleatoriamente entre 3 temas visuais:
  'inferno'  → projétil laranja/vermelho
  'toxina'   → projétil verde neon
  'nevasca'  → projétil azul gelo

Movimento:
  - Flutua verticalmente com senoide suave (idleFloat)
  - Deriva horizontalmente para se manter em tela (bounce nas bordas)
"""

import logging
import math
import random
from typing import Optional, Tuple

import pygame

from ..core.config import config as Config
from ..entities.bot_elemental_pixel_map import (
    ANTENNA_COL_START as _ANTENNA_COL_START,
    ANTENNA_ROW_START as _ANTENNA_ROW_START,
    ATTACK_PALETTES as _ATTACK_PALETTES,
    C as _C,
    EYE_LEFT_COL_END as _EYE_LEFT_COL_END,
    EYE_LEFT_COL_START as _EYE_LEFT_COL_START,
    EYE_RIGHT_COL_END as _EYE_RIGHT_COL_END,
    EYE_RIGHT_COL_START as _EYE_RIGHT_COL_START,
    EYE_ROW_END as _EYE_ROW_END,
    EYE_ROW_START as _EYE_ROW_START,
    PIXEL_COLS as _PIXEL_COLS,
    PIXEL_MAP as _PIXEL_MAP,
    PIXEL_ROWS as _PIXEL_ROWS,
    THRUSTER_NEUTRAL as _THRUSTER_NEUTRAL,
)

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

    Visual: quadrado pixelado com camada de glow, cor baseada no tema do ataque.
    Causa 1 vida de dano por colisão (processado em playing.py).
    """

    SPEED = 420.0  # px/s
    SIZE = 10       # raio em px

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        color: Tuple[int, int, int],
        glow_color: Tuple[int, int, int],
    ):
        self.x = float(x)
        self.y = float(y)
        self.dead = False
        self.causes_damage = True
        self.color = color
        self.glow_color = glow_color

        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy) or 1.0
        self.vx = (dx / dist) * self.SPEED
        self.vy = (dy / dist) * self.SPEED

        self._spin = random.uniform(-180, 180)
        self._angle = 0.0
        self._trail: list[list[float]] = []  # [x, y, alpha]

        self.rect = pygame.Rect(
            int(self.x) - self.SIZE,
            int(self.y) - self.SIZE,
            self.SIZE * 2,
            self.SIZE * 2,
        )

        # Pré-alocação de superfícies
        g = self.SIZE * 2
        self._glow_surf = pygame.Surface((g * 2, g * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            self._glow_surf,
            (*self.glow_color, 60),
            (0, 0, g * 2, g * 2),
        )
        self._trail_surf = pygame.Surface((self.SIZE, self.SIZE), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self._angle += self._spin * dt

        # Rastro
        if random.random() < 0.5:
            self._trail.append([self.x, self.y, 200.0])
        for t in self._trail:
            t[2] -= 600.0 * dt
        self._trail = [t for t in self._trail if t[2] > 0]

        self.rect.x = int(self.x) - self.SIZE
        self.rect.y = int(self.y) - self.SIZE

        sw = getattr(Config, "SCREEN_WIDTH", 480)
        sh = getattr(Config, "SCREEN_HEIGHT", 800)
        if self.x < -50 or self.x > sw + 50 or self.y < -50 or self.y > sh + 50:
            self.dead = True

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        # Rastro
        r, g, b = self.color
        for tx, ty, alpha in self._trail:
            self._trail_surf.fill((r, g, b, int(alpha * 0.5)))
            surface.blit(
                self._trail_surf,
                (int(tx) - self.SIZE // 2, int(ty) - self.SIZE // 2),
            )

        cx, cy = int(self.x), int(self.y)
        s = self.SIZE

        # Glow
        surface.blit(self._glow_surf, (cx - s, cy - s))

        # Corpo pixelado
        pygame.draw.rect(surface, self.color, (cx - s // 2, cy - s // 2, s, s))
        # Núcleo branco
        pygame.draw.rect(
            surface,
            _C["PUPIL"],
            (cx - s // 4, cy - s // 4, s // 2, s // 2),
        )


# ============================================================================
# PARTÍCULA DE CARGA (visual, não causa dano)
# ============================================================================


class _ChargeParticle:
    """Partícula que converge para a ponta da antena durante CHARGING."""

    def __init__(
        self,
        antenna_x: float,
        antenna_y: float,
        color: Tuple[int, int, int],
    ):
        self.angle = random.uniform(0, math.pi * 2)
        self.dist = 80.0 + random.uniform(0, 40)
        self._start_dist = self.dist
        self._orbit_speed = 0.06 + random.uniform(0, 0.07)
        self._radial_speed = 70.0 + random.uniform(0, 60)
        self.color = color
        self.size = random.randint(2, 5)
        self.ax = antenna_x
        self.ay = antenna_y
        self.px = antenna_x + math.cos(self.angle) * self.dist
        self.py = antenna_y + math.sin(self.angle) * self.dist
        self.dead = False

        self._surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)

    def update(self, dt: float, antenna_x: float, antenna_y: float) -> None:
        self.dist -= self._radial_speed * dt
        speed_mul = 1.0 + (1.0 - _clamp(self.dist / self._start_dist, 0, 1)) * 2.0
        self.angle += self._orbit_speed * speed_mul * (dt * 60)
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
        r, g, b = self.color
        self._surf.fill((r, g, b, int(ratio * 220)))
        surface.blit(self._surf, (int(self.px) - self.size, int(self.py) - self.size))


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

    SCALE = 8  # px por "pixel" do mapa
    # Mini-boss: precisa de 25 tiros para ser eliminado.
    # health representa contagem de hits restantes (1 por tiro, igual à lógica
    # de minas que precisam de 4 hits antes de explodir).
    MAX_HEALTH = 25
    HIT_SCORE = 20

    # Durações dos estados (segundos)
    _DUR_IDLE = 3.0
    _DUR_CHARGING = 1.5
    _DUR_RECOIL = 0.35
    _DUR_DYING = 0.8

    # Parâmetros de movimento
    _FLOAT_AMPLITUDE = 6.0   # px — amplitude da flutuação vertical senoidal
    _FLOAT_SPEED = 1.4        # Hz
    _DRIFT_SPEED = 55.0       # px/s — deriva horizontal
    _ENTRY_SPEED = 180.0      # px/s — descida inicial

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

        self.w = _PIXEL_COLS * S  # largura em px
        self.h = _PIXEL_ROWS * S  # altura em px

        # Posição inicial acima da tela
        self.x = float(x)
        self.y = -float(self.h)
        self._target_y = float(y)  # onde para após entrar

        # Mini-boss: 25 tiros para eliminar (independente de difficulty_multiplier).
        # Cada chamada a take_damage() reduz em 1 (igual ao sistema de minas).
        self.max_health = self.MAX_HEALTH
        self.health = health if health is not None else self.max_health
        self.dead = False
        self.causes_damage = False  # contato não causa dano direto
        self.hit_score = self.HIT_SCORE

        # Velocidade de deriva horizontal
        self._drift_vx = self._DRIFT_SPEED * random.choice([-1, 1])

        # ── FSM ──────────────────────────────────────────────────────────────
        self.fsm_state = "ENTERING"
        self._fsm_timer = 0.0  # tempo no estado atual

        # ── Tema do ataque atual ──────────────────────────────────────────────
        self._attack_theme: str = "nevasca"  # 'inferno' | 'toxina' | 'nevasca'
        self._palette: dict[str, RGB] = _ATTACK_PALETTES["nevasca"]

        # Cores "dinâmicas" do corpo (mudam ao carregar)
        self._body_outline: RGB = _C["A"]
        self._body_main: RGB = _C["B"]
        self._body_dark: RGB = _C["A"]
        self._body_light: RGB = _C["D"]
        self._thruster_colors: list[RGB] = list(_THRUSTER_NEUTRAL)

        # ── Olho: abertura e varredura ────────────────────────────────────────
        self._eye_open = 0.0        # 0 = fechado, 1 = aberto
        self._eye_open_dir = 1      # 1 = abrindo, -1 = fechando
        self._scan_step = 0         # -1, 0, +1 — posição horizontal da íris
        self._blink_timer = 0.0
        self._blink_open = True
        self._blink_interval = random.uniform(3.5, 6.0)

        # ── Recoil (recuo ao disparar) ────────────────────────────────────────
        self._recoil_x = 0.0
        self._recoil_y = 0.0
        self._recoil_timer = 0.0

        # ── Flutuação ─────────────────────────────────────────────────────────
        self._float_phase = random.uniform(0, math.pi * 2)
        self._float_y = 0.0  # offset vertical atual

        # ── Jitter (vibração durante CHARGING) ───────────────────────────────
        self._jitter_x = 0.0
        self._jitter_y = 0.0

        # ── Partículas de carga ───────────────────────────────────────────────
        self._charge_particles: list[_ChargeParticle] = []

        # ── Aura / núcleo da antena ───────────────────────────────────────────
        self._aura_scale = 0.0   # 0 = invisível, 3.5 = máximo (como no JS)
        self._aura_visible = False
        self._aura_flying = False    # True quando o tiro está "voando"
        self._aura_fly_t = 0.0
        self._aura_fly_pos: Tuple[float, float] = (0.0, 0.0)
        self._aura_fly_target: Tuple[float, float] = (0.0, 0.0)

        # ── Fade out (DYING) ──────────────────────────────────────────────────
        self._alpha = 255

        # ── Tempo global ─────────────────────────────────────────────────────
        self._time = 0.0

        # ── Colisão ───────────────────────────────────────────────────────────
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # ── Superfícies pré-alocadas ──────────────────────────────────────────
        _s = self.SCALE
        self._thruster_surfs = [
            pygame.Surface((_s * 12 + 2, _s * 5 + 2), pygame.SRCALPHA) for _ in range(4)
        ]
        self._aura_surf = pygame.Surface((_s * 20, _s * 20), pygame.SRCALPHA)
        self._eye_surf = pygame.Surface((_s * 4, _s * 3), pygame.SRCALPHA)

    # =========================================================================
    # PROPRIEDADES CALCULADAS
    # =========================================================================

    def _antenna_tip_center(self) -> Tuple[float, float]:
        """Centro da ponta da antena (onde a aura aparece)."""
        S = self.SCALE
        ox = self.x + self._jitter_x
        oy = self.y + self._float_y + self._jitter_y
        tip_cx = ox + (_ANTENNA_COL_START + 2) * S  # centro horizontal da ponta
        tip_cy = oy + (_ANTENNA_ROW_START + 2) * S  # centro vertical da ponta
        return tip_cx, tip_cy

    def _draw_x(self) -> float:
        """X de desenho, incluindo jitter e recoil."""
        return self.x + self._jitter_x + self._recoil_x

    def _draw_y(self) -> float:
        """Y de desenho, incluindo flutuação, jitter e recoil."""
        return self.y + self._float_y + self._jitter_y + self._recoil_y

    # =========================================================================
    # FSM
    # =========================================================================

    def _transition(self, new_state: str) -> None:
        self.fsm_state = new_state
        self._fsm_timer = 0.0

    def _run_fsm(
        self,
        dt: float,
        player_x: float,
        player_y: float,
    ) -> list[EnergyOrb]:
        spawned: list[EnergyOrb] = []
        self._fsm_timer += dt

        if self.fsm_state == "ENTERING":
            # Desce até a posição-alvo
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
            if self._fsm_timer >= self._DUR_CHARGING:
                self._transition("FIRING")

        elif self.fsm_state == "FIRING":
            orbs = self._fire(player_x, player_y)
            spawned.extend(orbs)
            self._transition("RECOIL")

        elif self.fsm_state == "RECOIL":
            frac = _ease_out_cubic(self._fsm_timer / self._DUR_RECOIL)
            self._recoil_x = self._recoil_x * (1.0 - frac)
            self._recoil_y = self._recoil_y * (1.0 - frac)
            if self._fsm_timer >= self._DUR_RECOIL:
                self._recoil_x = 0.0
                self._recoil_y = 0.0
                self._reset_palette()
                self._transition("IDLE")

        elif self.fsm_state == "DYING":
            frac = self._fsm_timer / self._DUR_DYING
            self._alpha = int(255 * (1.0 - frac))
            if self._fsm_timer >= self._DUR_DYING:
                self.dead = True

        return spawned

    # ── Helpers de estado ────────────────────────────────────────────────────

    def _tick_idle(self, dt: float) -> None:
        """Atualiza a varredura lateral dos olhos e piscar."""
        # Varredura (scan) — cosseno discretizado: -1, 0, +1
        self._scan_step = round(math.cos(self._time * 3))

        # Piscar
        self._blink_timer += dt
        if self._blink_timer >= self._blink_interval:
            self._blink_open = not self._blink_open
            self._blink_timer = 0.0
            if not self._blink_open:
                self._blink_interval = 0.12  # duração do piscar fechado
            else:
                self._blink_interval = random.uniform(3.5, 6.0)

    def _start_charging(self) -> None:
        self._attack_theme = random.choice(["inferno", "toxina", "nevasca"])
        self._palette = dict(_ATTACK_PALETTES[self._attack_theme])  # dict[str, RGB]
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
        self._charge_particles.clear()
        self._transition("CHARGING")

    def _tick_charging(self, dt: float) -> None:
        """Vibração + crescimento da aura + spawn de partículas."""
        # Jitter
        self._jitter_x = random.uniform(-2, 2)
        self._jitter_y = random.uniform(-2, 2)

        # Aura cresce até 3.5× (como no JS: growSphere 0.5 → 3.5)
        progress = self._fsm_timer / self._DUR_CHARGING
        self._aura_scale = 0.5 + progress * 3.0

        # Spawn de partículas
        if random.random() < 0.6:
            ax, ay = self._antenna_tip_center()
            self._charge_particles.append(
                _ChargeParticle(ax, ay, self._palette["core"])
            )

        # Atualiza partículas existentes
        ax, ay = self._antenna_tip_center()
        for p in self._charge_particles:
            p.update(dt, ax, ay)
        self._charge_particles = [p for p in self._charge_particles if not p.dead]

    def _fire(self, player_x: float, player_y: float) -> list[EnergyOrb]:
        """Cria o projétil, define recoil e inicia a aura 'voando'."""
        ax, ay = self._antenna_tip_center()

        orb = EnergyOrb(
            x=ax,
            y=ay,
            target_x=player_x,
            target_y=player_y,
            color=self._palette["mid"],
            glow_color=self._palette["core"],
        )

        # Recoil: empurra o robô na direção oposta ao tiro
        dx = player_x - ax
        dy = player_y - ay
        dist = math.hypot(dx, dy) or 1.0
        recoil_mag = 18.0
        self._recoil_x = -(dx / dist) * recoil_mag
        self._recoil_y = -(dy / dist) * recoil_mag

        # Oculta aura e para jitter
        self._aura_visible = False
        self._aura_scale = 0.0
        self._jitter_x = 0.0
        self._jitter_y = 0.0
        self._charge_particles.clear()

        return [orb]

    def _reset_palette(self) -> None:
        """Volta ao visual neutro após o ataque."""
        self._body_outline = _C["A"]
        self._body_main = _C["B"]
        self._body_dark = _C["A"]
        self._body_light = _C["D"]
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
        Atualiza a lógica do inimigo.

        Parâmetros
        ----------
        dt         : delta-time real (segundos)
        enemy_dt   : delta-time com EMP aplicado (pode ser 0 durante EMP)
        player_x/y : posição do jogador para mira

        Retorna lista de EnergyOrb criados neste frame.
        """
        self._time += dt

        # Flutuação vertical senoidal (fora de ENTERING e CHARGING)
        if self.fsm_state not in ("ENTERING", "DYING"):
            self._float_y = (
                math.sin(self._time * self._FLOAT_SPEED * math.pi * 2 + self._float_phase)
                * self._FLOAT_AMPLITUDE
            )
        else:
            self._float_y = 0.0

        # Deriva horizontal com bounce
        if self.fsm_state not in ("ENTERING", "DYING"):
            self.x += self._drift_vx * enemy_dt
            margin = 20
            if self.x < margin:
                self.x = margin
                self._drift_vx = abs(self._drift_vx)
            elif self.x + self.w > self._screen_w - margin:
                self.x = self._screen_w - margin - self.w
                self._drift_vx = -abs(self._drift_vx)

        # FSM
        spawned = self._run_fsm(enemy_dt, player_x, player_y)

        # Colisão
        self.rect.x = int(self.x)
        self.rect.y = int(self.y + self._float_y)

        return spawned

    def take_damage(self, amount: int = 1) -> None:
        """Reduz 1 hit por tiro (mini-boss: precisa de 25 tiros no total).
        O parâmetro ``amount`` é ignorado — cada acerto conta como 1 hit,
        espelhando o comportamento das minas explosivas."""
        self.health -= 1
        if self.health <= 0 and self.fsm_state != "DYING":
            self.health = 0
            self._transition("DYING")

    def get_points_value(self) -> int:
        """Retorna pontuação ao ser destruído (compatível com a interface Enemy)."""
        return self.hit_score

    # =========================================================================
    # DRAW
    # =========================================================================

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        S = self.SCALE
        ox = int(self._draw_x())
        oy = int(self._draw_y())

        # Superfície auxiliar para suporte ao fade de morte
        if self.fsm_state == "DYING" and self._alpha < 255:
            tmp = pygame.Surface((self.w, self.h + S * 6), pygame.SRCALPHA)
            self._draw_sprite(tmp, 0, 0, S)
            tmp.set_alpha(self._alpha)
            surface.blit(tmp, (ox, oy))
        else:
            self._draw_sprite(surface, ox, oy, S)

    # ── Sub-rotinas de desenho ───────────────────────────────────────────────

    def _draw_sprite(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """Renderiza a sprite completa (corpo + olhos + propulsor + aura)."""
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
        """Itera o PIXEL_MAP e pinta cada bloco com a cor adequada."""
        # Mapa de letra → cor atual (corpo pode ter paleta customizada)
        color_map: dict[str, Tuple[int, int, int]] = {
            "A": self._body_outline,
            "B": self._body_main,
            "C": _C["C"],          # haste antena — cor fixa
            "D": self._body_dark,
            "E": _C["E"],          # topo antena — cor fixa
            "F": _C["E"],
        }

        for row_i, row in enumerate(_PIXEL_MAP):
            for col_i, cell in enumerate(row):
                if cell is None:
                    continue
                # Pula as células dos olhos (desenhadas em _draw_eyes)
                if (
                    _EYE_ROW_START <= row_i <= _EYE_ROW_END
                    and (
                        _EYE_LEFT_COL_START <= col_i <= _EYE_LEFT_COL_END
                        or _EYE_RIGHT_COL_START <= col_i <= _EYE_RIGHT_COL_END
                    )
                ):
                    continue
                color = color_map.get(cell, (255, 0, 255))  # magenta = erro
                pygame.draw.rect(
                    surface,
                    color,
                    (ox + col_i * S, oy + row_i * S, S, S),
                )

    def _draw_eyes(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Desenha os dois olhos com íris, pupila e piscar.
        Íris pode se mover lateralmente (scan) e piscar verticalmente.
        """
        if not self._blink_open and self.fsm_state == "IDLE":
            return  # olho "fechado" — não pinta nada (fundo já é preto)

        # Escolhe as cores do olho pelo tema
        if self.fsm_state in ("CHARGING", "FIRING", "RECOIL"):
            bg_col = self._palette["eye_bg"]
            iris_col = self._palette["eye_iris"]
        else:
            bg_col = _C["EYE_BG_DEFAULT"]
            iris_col = _C["EYE_IRIS_DEFAULT"]

        eye_h = (_EYE_ROW_END - _EYE_ROW_START + 1) * S  # altura total do olho

        for col_start, col_end in (
            (_EYE_LEFT_COL_START, _EYE_LEFT_COL_END),
            (_EYE_RIGHT_COL_START, _EYE_RIGHT_COL_END),
        ):
            ew = (col_end - col_start + 1) * S
            ex = ox + col_start * S
            ey = oy + _EYE_ROW_START * S

            # Fundo do olho
            pygame.draw.rect(surface, bg_col, (ex, ey, ew, eye_h))

            # Íris (metade da largura do olho, pode se mover ±1 bloco)
            iris_w = S * 2
            iris_x = ex + S + self._scan_step * S
            pygame.draw.rect(surface, iris_col, (iris_x, ey, iris_w, eye_h))

            # Reflexo branco (canto superior da íris)
            pygame.draw.rect(surface, _C["PUPIL"], (iris_x, ey + 1, S, S))

    def _draw_thruster(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Propulsor fluido: anel central + 4 anéis que desaparecem à medida
        que descem (fiel ao JS: thrustFlicker com 3 cores).
        """
        cx = ox + self.w // 2
        start_y = oy + _PIXEL_ROWS * S  # base do mapa de pixels

        # Bloco raiz (branco)
        pygame.draw.rect(surface, self._thruster_colors[0], (cx - S, start_y, S * 2, S))

        rings = 4
        max_drop = S * 14
        speed = 2.0
        t = self._time

        c1, c2, c3 = (
            self._thruster_colors[0],
            self._thruster_colors[1] if len(self._thruster_colors) > 1 else self._thruster_colors[0],
            self._thruster_colors[2] if len(self._thruster_colors) > 2 else self._thruster_colors[0],
        )

        for i in range(rings):
            phase = ((t * speed) + (i / rings)) % 1.0
            w = int(S * 9 * (1 - phase))
            h = max(S, int(S * 3 * (1 - phase)))
            y = start_y + int(phase * max_drop) + S
            alpha = max(0, int(255 * (1.0 - phase ** 2)))

            if w < S:
                continue

            if phase < 0.15:
                color = c1
            elif phase < 0.50:
                color = c2
            else:
                color = c3

            rs = self._thruster_surfs[i]
            rs.fill((0, 0, 0, 0))
            pygame.draw.rect(rs, (*color, alpha), (0, 0, w, h), S)
            surface.blit(rs, (cx - w // 2, y - h // 2))

    def _draw_aura(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
        S: int,
    ) -> None:
        """
        Núcleo de energia que cresce na ponta da antena durante CHARGING
        e voa em direção ao alvo durante FIRING (fiel ao JS: shootSphere).
        """
        if not self._aura_visible or self._aura_scale < 0.1:
            return

        ax, ay = self._antenna_tip_center()
        p = self._palette
        scale = self._aura_scale

        # Cruz + halo de 4 px usando box-shadow pixel-art
        base_r = int(S * scale)
        if base_r < 1:
            return

        aura_size = base_r * 2 + 1
        self._aura_surf = pygame.Surface((aura_size * 4, aura_size * 4), pygame.SRCALPHA)
        center = aura_size * 2

        def blit_px(dx: int, dy: int, color: Tuple[int, int, int], alpha: int = 255) -> None:
            r, g, b = color
            self._aura_surf.fill(
                (r, g, b, alpha),
                (center + dx - base_r // 2, center + dy - base_r // 2, base_r, base_r),
            )

        # Núcleo
        blit_px(0, 0, p["core"])
        # Anel médio (4 direções)
        for dx, dy in ((0, -base_r), (0, base_r), (-base_r, 0), (base_r, 0)):
            blit_px(dx, dy, p["mid"])
        # Anel externo (8 direções)
        ext = int(base_r * 1.5)
        for dx, dy in (
            (0, -ext), (0, ext), (-ext, 0), (ext, 0),
            (-base_r, -base_r), (base_r, -base_r),
            (-base_r, base_r), (base_r, base_r),
        ):
            blit_px(dx, dy, p["outer"], 180)

        half = aura_size * 2
        surface.blit(self._aura_surf, (int(ax) - half, int(ay) - half))

    def _draw_particles(self, surface: pygame.Surface) -> None:
        """Desenha todas as partículas de carga ativas."""
        for p in self._charge_particles:
            p.draw(surface)

    def _draw_health_bar(
        self,
        surface: pygame.Surface,
        ox: int,
        oy: int,
    ) -> None:
        # Barra de vida oculta intencionalmente: o BotElemental é um mini-boss
        # sem indicador visível de HP (o jogador não sabe quantos tiros restam).
        pass