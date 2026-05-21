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
from typing import TYPE_CHECKING, Dict, Optional, Tuple

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

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult

from .bot_elemental_attacks import ChargeParticle, EnergyOrb, clamp, ease_out_cubic

logger = logging.getLogger(__name__)

# Alias de cor RGB — espelha o tipo definido no pixel map
RGB = Tuple[int, int, int]

# ============================================================================
# CACHE ESTÁTICO DE SUPERFÍCIES (compartilhado entre instâncias)
# ============================================================================

# Body cache: pré-renderiza o corpo + braços por paleta. Chave inclui os 4
# campos dinâmicos do corpo (outline, main, dark, light) e a escala S.
# Valor: (body_surf, left_arm_surf, right_arm_surf).
_BOT_BODY_CACHE: Dict[
    Tuple[RGB, RGB, RGB, RGB, int],
    Tuple[pygame.Surface, pygame.Surface, pygame.Surface],
] = {}

# Cells dos braços — constante, evita reconstruir `{0, PIXEL_COLS-1}` por frame.
_BODY_ARM_COL_LEFT: int = 0
_BODY_ARM_COL_RIGHT: int = _PIXEL_COLS - 1


def _resolve_pixel_color(
    cell: str, outline: RGB, main: RGB, dark: RGB, light: RGB
) -> RGB:
    if cell == "A":
        return outline
    if cell == "B" or cell == "D":
        return main
    if cell == "F":
        return light
    if cell == "G":
        return dark
    if cell == "C":
        return _C["C"]
    if cell == "E":
        return _C["E"]
    if cell == "H":
        return _C["H"]
    if cell == "I":
        return _C["I"]
    return (255, 0, 255)  # célula desconhecida


def _build_bot_body_surfaces(
    outline: RGB, main: RGB, dark: RGB, light: RGB, S: int
) -> Tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    """Pré-renderiza corpo (sem olhos, sem braços) + dois braços separados."""
    body_w = _PIXEL_COLS * S
    body_h = _PIXEL_ROWS * S
    body_surf = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
    left_arm = pygame.Surface((S, body_h), pygame.SRCALPHA)
    right_arm = pygame.Surface((S, body_h), pygame.SRCALPHA)

    eye_left_start = _EYE_LEFT_COL_START
    eye_left_end = _EYE_LEFT_COL_END
    eye_right_start = _EYE_RIGHT_COL_START
    eye_right_end = _EYE_RIGHT_COL_END
    eye_row_start = _EYE_ROW_START
    eye_row_end = _EYE_ROW_END

    for row_i, row in enumerate(_PIXEL_MAP):
        in_eye_row = eye_row_start <= row_i <= eye_row_end
        py = row_i * S
        for col_i, cell in enumerate(row):
            if cell is None:
                continue
            # Olhos são desenhados separadamente em _draw_eyes
            if in_eye_row and (
                eye_left_start <= col_i <= eye_left_end
                or eye_right_start <= col_i <= eye_right_end
            ):
                continue

            color = _resolve_pixel_color(cell, outline, main, dark, light)

            if col_i == _BODY_ARM_COL_LEFT:
                pygame.draw.rect(left_arm, color, (0, py, S, S))
            elif col_i == _BODY_ARM_COL_RIGHT:
                pygame.draw.rect(right_arm, color, (0, py, S, S))
            else:
                pygame.draw.rect(body_surf, color, (col_i * S, py, S, S))

    try:
        body_surf = body_surf.convert_alpha()
        left_arm = left_arm.convert_alpha()
        right_arm = right_arm.convert_alpha()
    except pygame.error:
        pass

    return body_surf, left_arm, right_arm


def _get_bot_body_surfaces(
    outline: RGB, main: RGB, dark: RGB, light: RGB, S: int
) -> Tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    key = (outline, main, dark, light, S)
    cached = _BOT_BODY_CACHE.get(key)
    if cached is not None:
        return cached
    built = _build_bot_body_surfaces(outline, main, dark, light, S)
    _BOT_BODY_CACHE[key] = built
    return built


# Aura cache: chave (theme_name, base_r, S). Cada surface contém os 13 fills
# do glow já compostos — em vez de 1 alloc + 13 fills por frame, só 1 blit.
_AURA_CACHE: Dict[Tuple[str, int, int], pygame.Surface] = {}


def _build_aura_surface(theme: str, base_r: int, _S: int) -> pygame.Surface:
    palette = _ATTACK_PALETTES[theme]
    sz = base_r * 6 + 1
    surf = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
    center = sz
    half_r = base_r // 2

    def fill_px(dx: int, dy: int, color: RGB, alpha: int = 255) -> None:
        r, g, b = color
        surf.fill(
            (r, g, b, alpha),
            (center + dx - half_r, center + dy - half_r, base_r, base_r),
        )

    fill_px(0, 0, palette["core"])
    for dx, dy in ((0, -base_r), (0, base_r), (-base_r, 0), (base_r, 0)):
        fill_px(dx, dy, palette["mid"])
    for dx, dy in (
        (-base_r, -base_r),
        (base_r, -base_r),
        (-base_r, base_r),
        (base_r, base_r),
    ):
        fill_px(dx, dy, palette["outer"], 200)
    ext2 = base_r * 2
    for dx, dy in ((0, -ext2), (0, ext2), (-ext2, 0), (ext2, 0)):
        fill_px(dx, dy, palette["outer"], 160)

    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    return surf


def _get_aura_surface(theme: str, base_r: int, S: int) -> pygame.Surface:
    key = (theme, base_r, S)
    cached = _AURA_CACHE.get(key)
    if cached is not None:
        return cached
    built = _build_aura_surface(theme, base_r, S)
    _AURA_CACHE[key] = built
    return built


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
    MAX_HEALTH = 200
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
        self._charge_particles: list[ChargeParticle] = []

        # ── Aura / núcleo da antena ───────────────────────────────────────────
        self._aura_scale = 0.0
        self._aura_visible = False

        # ── Pulso da antena (antennaPulse em IDLE) ────────────────────────────
        self._antenna_pulse_alpha = 0  # 0-255; sobe/desce a cada 1.25 s

        # ── Fade out (DYING) ──────────────────────────────────────────────────
        self._alpha = 255

        # Colisão é desativada assim que a morte começa; a animação continua.
        self._collision_disabled = False

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

        # Antenna pulse — alpha é constante (64 / 26), dimensões dependem só
        # de S e da geometria da antena. Pré-renderiza para evitar alocar 2
        # Surfaces SRCALPHA por frame enquanto a pulse está ativa em IDLE.
        tip_w = (_ANTENNA_COL_END - _ANTENNA_COL_START + 1) * _s
        tip_h = (_ANTENNA_ROW_END - _ANTENNA_ROW_START + 1) * _s
        pw = tip_w + _s * 2
        ph = tip_h + _s * 2
        self._antenna_pulse_inner = pygame.Surface((pw, ph), pygame.SRCALPHA)
        pygame.draw.rect(self._antenna_pulse_inner, (92, 225, 230, 64), (0, 0, pw, ph))
        pw2 = pw + _s * 2
        ph2 = ph + _s * 2
        self._antenna_pulse_outer = pygame.Surface((pw2, ph2), pygame.SRCALPHA)
        pygame.draw.rect(
            self._antenna_pulse_outer, (92, 225, 230, 26), (0, 0, pw2, ph2)
        )
        try:
            self._antenna_pulse_inner = self._antenna_pulse_inner.convert_alpha()
            self._antenna_pulse_outer = self._antenna_pulse_outer.convert_alpha()
        except pygame.error:
            pass

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
            self._collision_disabled = True
            self.rect.width = 0
            self.rect.height = 0
            self.rect.x = int(self.x)
            self.rect.y = int(self.y)

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
            frac = ease_out_cubic(self._fsm_timer / self._DUR_RECOIL)
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
        progress = clamp(self._fsm_timer / self._DUR_CHARGING, 0.0, 1.0)
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
                    ChargeParticle(ax, ay, self._palette, self._attack_theme)
                )

        ax, ay = self._antenna_tip_center()
        # Sweep in-place — atualiza e filtra mortos em uma única passagem,
        # sem rebuild de lista por frame.
        particles = self._charge_particles
        write = 0
        for p in particles:
            p.update(dt, ax, ay)
            if not p.dead:
                particles[write] = p
                write += 1
        del particles[write:]

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

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        emitted = self.update(ctx.dt, ctx.sdt, ctx.player_x, ctx.player_y)
        if emitted:
            ctx.new_energy_orbs.extend(emitted)

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
        if self._collision_disabled:
            self.rect.width = 0
            self.rect.height = 0
            self.rect.x = int(self.x)
            self.rect.y = int(self.y)
        else:
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

    def collision_circle(self) -> tuple[float, float, float]:
        r = self.rect
        return r.centerx, r.centery, max(r.width, r.height) / 2

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.fsm_state == "DYING" and self.just_died:
            self.just_died = False  # consome a flag
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=55,
                explosion_type=self.get_explosion_type(),
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead

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
        Renderiza corpo + braços a partir de surfaces pré-renderizadas por
        paleta. Os braços ficam separados pois o offset vertical (_arm_dy)
        muda em IDLE/CHARGING — desenho fica em 3 blits em vez de iterar o
        pixel map completo por frame.
        """
        body_surf, left_arm, right_arm = _get_bot_body_surfaces(
            self._body_outline,
            self._body_main,
            self._body_dark,
            self._body_light,
            S,
        )

        surface.blit(body_surf, (ox, oy))

        arm_dy = int(self._arm_dy)
        surface.blit(left_arm, (ox, oy + arm_dy))
        surface.blit(right_arm, (ox + _BODY_ARM_COL_RIGHT * S, oy + arm_dy))

        # ── Pulso da antena (antennaPulse em IDLE) ────────────────────────────
        if self._antenna_pulse_alpha > 0 and self.fsm_state == "IDLE":
            tip_x = ox + _ANTENNA_COL_START * S
            tip_y = oy + _ANTENNA_ROW_START * S
            surface.blit(self._antenna_pulse_inner, (tip_x - S, tip_y - S))
            surface.blit(self._antenna_pulse_outer, (tip_x - S * 2, tip_y - S * 2))

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
            cr, cg, cb = color
            pygame.draw.rect(rs, (cr, cg, cb, alpha), (0, 0, w, h), S)
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
        Composição (13 fills) pré-renderizada por (theme, base_r) — em vez
        de alocar surface + 13 fills por frame, só 1 blit.
        """
        if not self._aura_visible or self._aura_scale < 0.1:
            return

        base_r = max(1, int(S * self._aura_scale))
        aura_surf = _get_aura_surface(self._attack_theme, base_r, S)
        ax, ay = self._antenna_tip_center()
        half = base_r * 6 + 1
        surface.blit(aura_surf, (int(ax) - half, int(ay) - half))

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
