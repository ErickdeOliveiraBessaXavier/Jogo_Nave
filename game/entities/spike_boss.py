import math
import random
from typing import TYPE_CHECKING, List, Optional, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.sound import sound_manager
from .boss_hit_mixin import BossHitMixin
from .spike import Spike
from .spike_boss_laser import SpikeBossLaser
from .spike_boss_pixel_map import (
    COLORS_FRENZY,
    COLORS_NORMAL,
    COLORS_TELEGRAPH,
    EYE_COL_LEFT,
    EYE_COL_RIGHT,
    EYE_COLORS,
    EYE_HEIGHT,
    EYE_ROW,
    EYE_WIDTH,
    PIXEL_COLS,
    PIXEL_MAP,
)

if TYPE_CHECKING:
    from ..systems.boss_context import BossUpdateContext, BossUpdateResult


class SpikeBoss(BossHitMixin):
    """
    Boss que gerencia espinhos nas laterais da tela com design em pixel art e camadas.
    """

    BOSS_TYPE_NAME: str = "spike"

    def __init__(self, x: float, y: float, health: int = Config.SPIKE_BOSS_HEALTH):
        # Posição e tamanho
        self.w = 144
        self.h = 112
        self.pixel_size = self.w / PIXEL_COLS

        self.x = x
        self.y = -self.h
        self.target_y = y

        # Saúde e estado
        self.health = health
        self.max_health = health
        self.dead = False

        # Movimento
        self.speed = Config.SPIKE_BOSS_SPEED
        self.direction = 1
        self.entry_speed = Config.SPIKE_BOSS_ENTRY_SPEED

        # Máquina de estados
        self.state = "entering"
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0

        # Efeitos visuais e Lerp
        self.pulse = 0.0
        self.pulse_speed = 3.0

        # Lerp de cores (Palette)
        self.current_palette = COLORS_NORMAL.copy()
        self.palette_lerp_speed = 5.0

        # Lerp dos olhos
        self.eye_offset_x = 0.0
        self.eye_offset_y = 0.0
        self.eye_lerp_speed = 8.0

        # Animação da boca/núcleo e respiração
        self.mouth_timer = 0.0
        self.breathing_timer = 0.0

        # Sistema de comportamento dos olhos
        self.eye_mode = "tracking"
        self.eye_mode_timer = 0.0
        self.eye_frenetic_timer = 0.0
        self.eye_frenetic_direction = 0

        # Sistema de parede de triângulos
        self.wall_initialized = False

        # Sistema de ondas de ataque
        self.wave_timer = 0.0
        self.active_wave = False
        self.spikes_in_current_wave = 0
        self.current_wave_size = 0
        self.wave_launch_timer = 0.0

        # Posição do jogador
        self.player_x = 0.0
        self.player_y = 0.0

        self.should_launch_all_spikes = False
        self.frenzy_pause_active = False
        self.frenzy_pause_timer = 0.0

        # Sistema de laser gigante
        self.laser_cooldown = 0.0
        self.laser_charging = False
        self.laser_charge_timer = 0.0
        self.laser_active_timer = 0.0

        # Sistema de ataque de proximidade
        self.proximity_attack_cooldown = 0.0
        self.proximity_attack_active = False
        self.proximity_wave_radius = 0.0
        self.proximity_wave_timer = 0.0
        self.proximity_telegraph_active = False
        self.proximity_telegraph_timer = 0.0

        # Superfícies em cache do Pixel Map por camada
        self._cached_layers: dict[str, pygame.Surface] = {}

    def can_take_damage(self) -> bool:
        if self.state == "entering":
            return False
        return not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def take_damage(self, damage: int):
        if not self.can_take_damage():
            return
        self.health -= damage
        if self.health <= 0:
            self.health = 0
            self.dead = True
            self.laser_charging = False
            self.laser_active_timer = 0.0
            sound_manager.play_explosion_boss()
            return
        if not self.frenzy_mode and self.health <= self.max_health * Config.SPIKE_BOSS_FRENZY_THRESHOLD:
            self._enter_frenzy()
        sound_manager.play_boss_damage()

    def _enter_frenzy(self):
        self.frenzy_mode = True
        self.state = "frenzy"
        self.frenzy_shake_timer = Config.SPIKE_BOSS_FRENZY_SHAKE_DURATION
        self.speed = Config.SPIKE_BOSS_FRENZY_SPEED
        self.frenzy_pause_active = True
        self.frenzy_pause_timer = 0.0
        self.should_launch_all_spikes = True
        self._cached_layers.clear()
        if hasattr(sound_manager, "play_boss_frenzy"):
            sound_manager.play_boss_frenzy()  # type: ignore

    def is_pausing_game(self) -> bool:
        return self.frenzy_pause_active

    def _update_lerps(self, dt: float):
        """Atualiza todas as interpolações lineares (lerp) do boss."""
        # 1. Lerp da Paleta de Cores
        target = self._get_target_palette()
        for key in self.current_palette:
            if key in target:
                curr = self.current_palette[key]
                targ = target[key]
                # Calcula nova cor com lerp e garante que são inteiros
                r = int(curr[0] + (targ[0] - curr[0]) * self.palette_lerp_speed * dt)
                g = int(curr[1] + (targ[1] - curr[1]) * self.palette_lerp_speed * dt)
                b = int(curr[2] + (targ[2] - curr[2]) * self.palette_lerp_speed * dt)
                self.current_palette[key] = (r, g, b)

        # 2. Lerp dos Olhos
        target_eye_x = 0.0
        target_eye_y = 0.0
        is_telegraphing = self.proximity_telegraph_active or self.laser_charging or self.laser_active_timer > 0
        if not is_telegraphing:
            p_w, p_h = self.pixel_size, self.pixel_size
            ref_x = self.x + self.w / 2
            ref_y = self.y + EYE_ROW * p_h + (EYE_HEIGHT * p_h) / 2
            pupil_offset_max_x = (EYE_WIDTH * p_w - p_w) / 2
            pupil_offset_max_y = (EYE_HEIGHT * p_h - p_h * 1.5) / 2
            if self.eye_mode == "tracking":
                dx, dy = self.player_x - ref_x, self.player_y - ref_y
                dist = math.sqrt(dx*dx + dy*dy)
                if dist > 0:
                    target_eye_x, target_eye_y = (dx / dist) * pupil_offset_max_x, (dy / dist) * pupil_offset_max_y
            else: # frenetic
                target_eye_x = self.eye_frenetic_direction * pupil_offset_max_x
                target_eye_y = math.sin(self.eye_frenetic_timer * 10) * pupil_offset_max_y
        self.eye_offset_x += (target_eye_x - self.eye_offset_x) * self.eye_lerp_speed * dt
        self.eye_offset_y += (target_eye_y - self.eye_offset_y) * self.eye_lerp_speed * dt

    def update_boss(
        self, dt: float, ctx: "BossUpdateContext"
    ) -> "BossUpdateResult":
        from ..systems.boss_context import BossUpdateResult

        new_spikes, new_lasers = self.update(
            dt, ctx.player_x, ctx.player_y or 0.0, ctx.entity_manager.spikes
        )
        return BossUpdateResult(
            new_spikes=list(new_spikes),
            new_lasers=list(new_lasers),
        )

    def update(self, dt: float, player_x: float, player_y: float, spikes: List[Spike]) -> Tuple[List[Spike], List[SpikeBossLaser]]:
        spawned_spikes: List[Spike] = []
        self.player_x, self.player_y = player_x, player_y
        self._update_lerps(dt)
        self.breathing_timer += dt

        if self.frenzy_pause_active:
            self.frenzy_pause_timer += dt
            self.pulse += self.pulse_speed * dt
            if self.frenzy_pause_timer >= Config.SPIKE_BOSS_FRENZY_PAUSE_DURATION:
                self.frenzy_pause_active = False
                self.should_launch_all_spikes = True
            return (spawned_spikes, [])

        self.pulse += self.pulse_speed * dt
        self.mouth_timer += dt
        if self.mouth_timer >= Config.SPIKE_BOSS_MOUTH_CYCLE_DURATION:
            self.mouth_timer = 0.0

        self._update_eye_behavior(dt)

        if self.state == "entering":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "normal"
                if not self.wall_initialized:
                    spawned_spikes = self._initialize_wall()
                    self.wall_initialized = True
                    self.wave_timer = 2.0
            return (spawned_spikes, [])

        if self.frenzy_shake_timer > 0:
            self.frenzy_shake_timer -= dt
        if self.laser_active_timer > 0:
            self.laser_active_timer -= dt

        if not self.proximity_telegraph_active and not self.laser_charging and self.laser_active_timer <= 0:
            agg = getattr(self, "aggressiveness_multiplier", 1.0)
            self.x += self.speed * agg * self.direction * dt
            if self.x <= 0:
                self.x = 0
                self.direction = 1
            elif self.x >= Config.SCREEN_WIDTH - self.w:
                self.x = Config.SCREEN_WIDTH - self.w
                self.direction = -1

        self._update_waves(dt, spikes)
        self._check_proximity_attack(dt)
        laser = self._update_laser_attack(dt)
        return (spawned_spikes, [laser] if laser else [])

    def _get_target_palette(self) -> dict[str, Tuple[int, int, int]]:
        if self.proximity_telegraph_active or self.laser_charging or self.laser_active_timer > 0:
            return COLORS_TELEGRAPH
        return COLORS_FRENZY if self.frenzy_mode else COLORS_NORMAL

    def _render_layer(self, layer_cells: set[str], row_range: Optional[range] = None) -> pygame.Surface:
        if row_range is None:
            row_range = range(len(PIXEL_MAP))
        surface = pygame.Surface((int(self.w), int(self.h)), pygame.SRCALPHA)
        p_w, p_h = self.pixel_size, self.pixel_size
        for r in row_range:
            if r >= len(PIXEL_MAP):
                continue
            row = PIXEL_MAP[r]
            for c, cell in enumerate(row):
                if cell in layer_cells:
                    pygame.draw.rect(surface, (255, 255, 255), (int(c * p_w), int(r * p_h), int(p_w), int(p_h)))
        return surface

    def _get_layer_surfaces(self) -> dict[str, pygame.Surface]:
        if not self._cached_layers:
            # Shell Top: Rows 0-10
            self._cached_layers["shell_top"] = self._render_layer({"A", "C", "D", "E", "F", "H"}, range(11))
            # Horns: Row 0-10
            self._cached_layers["horns"] = self._render_layer({"G"}, range(11))
            # Jaw: Rows 11-13
            self._cached_layers["jaw"] = self._render_layer({"A", "C", "B"}, range(11, 14))
            # Mouth Interior: Rows 11-13
            self._cached_layers["core_inner"] = self._render_layer({"B", "M"}, range(11, 14))
        return self._cached_layers

    def _draw_layer(self, surface: pygame.Surface, layer_name: str, draw_x: int, draw_y: int, offset_x: float = 0, offset_y: float = 0):
        layers = self._get_layer_surfaces()
        if layer_name not in layers:
            return
        layer_surf = layers[layer_name].copy()
        palette = self.current_palette
        layer_map = {"shell_top": {"A", "C", "D", "E", "F", "H"}, "horns": {"G"}, "jaw": {"A", "C", "B"}, "core_inner": {"B", "M"}}
        cells = layer_map.get(layer_name, set())
        
        # Filtro de linhas para otimização
        row_range = range(11) if layer_name in ("shell_top", "horns") else range(11, 14)
        
        p_w, p_h = self.pixel_size, self.pixel_size
        for r in row_range:
            if r >= len(PIXEL_MAP):
                continue
            row = PIXEL_MAP[r]
            for c, cell in enumerate(row):
                if cell in cells:
                    pygame.draw.rect(layer_surf, palette.get(cell, (255, 0, 255)), (int(c * p_w), int(r * p_h), int(p_w), int(p_h)))
        surface.blit(layer_surf, (int(draw_x + offset_x), int(draw_y + offset_y)))

    def _draw_eyes(self, surface: pygame.Surface, draw_x: int, draw_y: int):
        is_telegraphing = self.proximity_telegraph_active or self.laser_charging or self.laser_active_timer > 0
        if is_telegraphing:
            bg_color, iris_color, eyes_closed = EYE_COLORS["TELEGRAPH_BG"], EYE_COLORS["TELEGRAPH_CLOSED"], True
        elif self.frenzy_mode:
            bg_color, iris_color, eyes_closed = EYE_COLORS["FRENZY_BG"], EYE_COLORS["FRENZY_IRIS"], False
        else:
            bg_color, iris_color, eyes_closed = EYE_COLORS["NORMAL_BG"], EYE_COLORS["NORMAL_IRIS"], False
        p_w, p_h = self.pixel_size, self.pixel_size
        for col_start in (EYE_COL_LEFT, EYE_COL_RIGHT):
            eye_rect = pygame.Rect(int(draw_x + col_start * p_w), int(draw_y + EYE_ROW * p_h), int(EYE_WIDTH * p_w), int(EYE_HEIGHT * p_h))
            if eyes_closed:
                pygame.draw.line(surface, iris_color, (eye_rect.left, int(eye_rect.centery)), (eye_rect.right, int(eye_rect.centery)), max(2, int(p_h)))
                continue
            pygame.draw.rect(surface, bg_color, eye_rect)
            pupil_x, pupil_y = eye_rect.centerx + self.eye_offset_x, eye_rect.centery + self.eye_offset_y
            pupil_rect = pygame.Rect(int(pupil_x - p_w/2), int(pupil_y - (p_h * 1.5)/2), int(p_w), int(p_h * 1.5))
            pygame.draw.rect(surface, iris_color, pupil_rect)

    def _get_mouth_opening(self) -> float:
        """
        Retorna abertura da boca (0.0 a 1.0).
        Abre muito durante o laser.
        """
        if self.laser_charging:
            return self.laser_charge_timer / Config.SPIKE_BOSS_LASER_CHARGE_TIME
        if self.laser_active_timer > 0:
            return 1.0
            
        # Idle/Breathing
        cycle_progress = self.mouth_timer / Config.SPIKE_BOSS_MOUTH_CYCLE_DURATION
        return float((math.sin(cycle_progress * math.pi) + 1.0) / 4.0)

    def draw(self, surface: pygame.Surface):
        mouth_opening = self._get_mouth_opening()
        # Gap de abertura da mandíbula (até 45 pixels)
        jaw_gap = int(mouth_opening * 45)
        
        # O corpo estica levemente para revelar o laser
        body_stretch = int(mouth_opening * 5)

        # Shake effect
        offset_x, offset_y = 0, 0
        if self.frenzy_pause_active or self.laser_charging:
            offset_x, offset_y = random.randint(-5, 5), random.randint(-5, 5)
        elif self.proximity_telegraph_active:
            offset_x, offset_y = random.randint(-1, 1), random.randint(-1, 1)
        elif self.frenzy_shake_timer > 0:
            offset_x, offset_y = random.randint(-3, 3), random.randint(-3, 3)

        draw_x, draw_y = int(self.x + offset_x), float(self.y + offset_y - body_stretch)
        horns_float = math.sin(self.breathing_timer * 4.0) * 3.0
        shell_float = math.sin(self.breathing_timer * 2.5) * 1.5

        # 0. Inner Core Glow (Drawn inside the gap)
        if mouth_opening > 0.1:
            core_color = (255, 100, 0) if self.laser_charging else (255, 50, 0)
            if self.laser_active_timer > 0:
                core_color = (255, 255, 200)
            # Glow vertical no meio da abertura
            glow_rect = pygame.Rect(draw_x + 48, int(draw_y + 80), self.w - 96, jaw_gap + 10)
            pygame.draw.rect(surface, core_color, glow_rect)

        # 1. Head Layers (Fixed)
        self._draw_layer(surface, "shell_top", draw_x, int(draw_y + shell_float))
        self._draw_layer(surface, "horns", draw_x, int(draw_y + horns_float))
        self._draw_eyes(surface, draw_x, int(draw_y + shell_float))

        # 2. Jaw Layers (Animated Down)
        self._draw_layer(surface, "jaw", draw_x, int(draw_y + jaw_gap))
        self._draw_layer(surface, "core_inner", draw_x, int(draw_y + jaw_gap))

        # Efeitos adicionais
        self._draw_effects(surface, draw_x, int(draw_y), body_stretch, jaw_gap)

        if self.state != "entering":
            self._draw_health_bar(surface, draw_x, int(draw_y))

    def _draw_effects(self, surface: pygame.Surface, draw_x: int, draw_y: int, body_stretch: int, jaw_gap: int = 0):
        """Desenha os efeitos ao redor do boss (telegraph, charging laser)."""
        boss_center_x = int(self.x + self.w / 2)
        boss_center_y = int(self.y + self.h / 2)
        bcx, bcy = boss_center_x, boss_center_y

        if self.proximity_telegraph_active:
            progress = self.proximity_telegraph_timer / Config.SPIKE_BOSS_PROXIMITY_TELEGRAPH_DURATION
            alpha = int(0.15 * 255 + (0.6 * 255 - 0.15 * 255) * progress)
            dr = int(Config.SPIKE_BOSS_PROXIMITY_WAVE_MAX_RADIUS)
            ds = pygame.Surface((dr * 2, dr * 2), pygame.SRCALPHA)
            dc = Config.SPIKE_BOSS_PROXIMITY_WARNING_COLOR_FRENZY if self.frenzy_mode else Config.SPIKE_BOSS_PROXIMITY_WARNING_COLOR_NORMAL
            pygame.draw.circle(ds, (*dc, alpha), (dr, dr), dr)
            if int(self.proximity_telegraph_timer * 15) % 2 == 0:
                pygame.draw.circle(ds, (*dc, min(255, alpha + 100)), (dr, dr), dr, width=5)
            surface.blit(ds, (bcx - dr, bcy - dr))
            warning_text = pygame.font.Font(None, 40).render("!", True, dc)
            surface.blit(warning_text, warning_text.get_rect(center=(bcx, bcy - 80)))
        elif self.proximity_attack_active and self.proximity_wave_radius > 0:
            oc = Config.SPIKE_BOSS_PROXIMITY_WAVE_COLOR_FRENZY if self.frenzy_mode else Config.SPIKE_BOSS_PROXIMITY_WAVE_COLOR_NORMAL
            ic = Config.SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_FRENZY if self.frenzy_mode else Config.SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_NORMAL
            pygame.draw.circle(surface, oc, (bcx, bcy), int(self.proximity_wave_radius), width=3)
            if self.proximity_wave_radius > 20:
                pygame.draw.circle(surface, oc, (bcx, bcy), int(self.proximity_wave_radius * 0.7), width=2)
            if self.proximity_wave_radius > 40:
                pygame.draw.circle(surface, ic, (bcx, bcy), int(self.proximity_wave_radius * 0.4), width=4)
        
        # Partículas de carregamento saindo de DENTRO da abertura
        if self.laser_charging:
            mouth_y = draw_y + 88 + (jaw_gap / 2)
            prog = self.laser_charge_timer / Config.SPIKE_BOSS_LASER_CHARGE_TIME
            for i in range(8):
                angle = (i / 8) * 360 + (self.laser_charge_timer * 360)
                radius = 80 * (1 - prog)
                px, py = bcx + int(math.cos(math.radians(angle)) * radius), int(mouth_y + math.sin(math.radians(angle)) * radius)
                pygame.draw.circle(surface, colors.YELLOW, (px, py), int(3 + 3 * prog))

    def _draw_health_bar(self, surface: pygame.Surface, x: int, y: int):
        bmw, bh = min(240, self.w * 2), 8
        bx, by = x + (self.w - bmw) / 2, y - 20
        pygame.draw.rect(surface, colors.DARK_RED, (bx, by, bmw, bh))
        hr = self.health / self.max_health
        hc = colors.GREEN if hr > 0.5 else colors.YELLOW if hr > 0.25 else colors.RED
        pygame.draw.rect(surface, hc, (bx, by, int(bmw * hr), bh))
        pygame.draw.rect(surface, colors.WHITE, (bx, by, bmw, bh), width=1)

    def get_wave_interval(self) -> float:
        return Config.SPIKE_FRENZY_WAVE_INTERVAL if self.frenzy_mode else Config.SPIKE_WAVE_INTERVAL

    def should_start_wave(self, spikes: List[Spike]) -> bool:
        return sum(1 for s in spikes if s.state == "attached") > 0

    def _update_eye_behavior(self, dt: float):
        self.eye_mode_timer += dt
        if self.eye_mode == "tracking":
            if self.eye_mode_timer >= Config.SPIKE_BOSS_EYE_TRACK_DURATION:
                self.eye_mode, self.eye_mode_timer, self.eye_frenetic_timer, self.eye_frenetic_direction = "frenetic", 0.0, 0.0, random.choice([-1, 1])
        elif self.eye_mode == "frenetic":
            self.eye_frenetic_timer += dt
            if self.eye_frenetic_timer >= Config.SPIKE_BOSS_EYE_FRENETIC_SPEED:
                self.eye_frenetic_timer, self.eye_frenetic_direction = 0.0, random.choice([-1, 0, 1])
            if self.eye_mode_timer >= Config.SPIKE_BOSS_EYE_FRENETIC_DURATION:
                self.eye_mode, self.eye_mode_timer = "tracking", 0.0

    def _initialize_wall(self) -> List[Spike]:
        spikes: List[Spike] = []
        spacing = Config.SPIKE_SIZE + Config.SPIKE_WALL_SPACING
        num_spikes_per_side = int(Config.SCREEN_HEIGHT / spacing)
        for from_left in [True, False]:
            for i in range(num_spikes_per_side):
                spike = Spike(i * spacing, from_left=from_left)
                spike.time_until_attack = 999999.0
                spikes.append(spike)
        return spikes

    def _update_waves(self, dt: float, spikes: List[Spike]):
        if self.should_launch_all_spikes:
            self.should_launch_all_spikes = False
            for spike in spikes:
                if spike.state == "attached":
                    spike.time_until_attack = random.uniform(0.0, 0.2)
            self.active_wave = False
            self.wave_timer = self.get_wave_interval()
            return
        self.wave_timer -= dt
        if self.active_wave:
            self.wave_launch_timer -= dt
            if self.wave_launch_timer <= 0 and self.spikes_in_current_wave < self.current_wave_size:
                ready_spikes = [s for s in spikes if s.state == "attached"]
                if ready_spikes:
                    spike = random.choice(ready_spikes)
                    spike.time_until_attack = random.uniform(Config.SPIKE_MIN_ATTACH_TIME, Config.SPIKE_MAX_ATTACH_TIME)
                    self.spikes_in_current_wave += 1
                    self.wave_launch_timer = Config.SPIKE_LAUNCH_COOLDOWN
            if self.spikes_in_current_wave >= self.current_wave_size:
                self.active_wave = False
                self.wave_timer = self.get_wave_interval()
        elif self.wave_timer <= 0 and self.should_start_wave(spikes):
            self.active_wave = True
            self.current_wave_size = random.randint(Config.SPIKE_WAVE_MIN_SIZE, Config.SPIKE_WAVE_MAX_SIZE)
            self.spikes_in_current_wave = 0
            self.wave_launch_timer = 0.0

    def _check_proximity_attack(self, dt: float):
        if self.proximity_attack_cooldown > 0:
            self.proximity_attack_cooldown -= dt
        if self.proximity_telegraph_active:
            self.proximity_telegraph_timer += dt
            if self.proximity_telegraph_timer >= Config.SPIKE_BOSS_PROXIMITY_TELEGRAPH_DURATION:
                self.proximity_telegraph_active = False
                self.proximity_telegraph_timer = 0.0
                self.proximity_attack_active = True
                self.proximity_wave_timer = 0.0
                sound_manager.play_explosion_boss()
            return
        if self.proximity_attack_active:
            self.proximity_wave_timer += dt
            progress = self.proximity_wave_timer / Config.SPIKE_BOSS_PROXIMITY_WAVE_DURATION
            self.proximity_wave_radius = progress * Config.SPIKE_BOSS_PROXIMITY_WAVE_MAX_RADIUS
            if progress >= 1.0:
                self.proximity_attack_active = False
                self.proximity_wave_radius = 0.0
                self.proximity_wave_timer = 0.0
            return
        if self.proximity_attack_cooldown > 0 or self.state == "entering" or self.frenzy_pause_active:
            return
        boss_center_x, boss_center_y = self.x + self.w / 2, self.y + self.h / 2
        dx, dy = self.player_x - boss_center_x, self.player_y - boss_center_y
        if math.sqrt(dx * dx + dy * dy) < Config.SPIKE_BOSS_PROXIMITY_DISTANCE:
            self._trigger_proximity_attack()

    def _trigger_proximity_attack(self):
        self.proximity_telegraph_active = True
        self.proximity_telegraph_timer = 0.0
        agg = getattr(self, "aggressiveness_multiplier", 1.0)
        self.proximity_attack_cooldown = Config.SPIKE_BOSS_PROXIMITY_COOLDOWN / max(0.5, agg)
        if hasattr(sound_manager, "play_boss_warning"):
            sound_manager.play_boss_warning()  # type: ignore

    def _update_laser_attack(self, dt: float) -> Optional[SpikeBossLaser]:
        if self.laser_cooldown > 0:
            self.laser_cooldown -= dt
        if self.laser_charging:
            self.laser_charge_timer += dt
            if self.laser_charge_timer >= Config.SPIKE_BOSS_LASER_CHARGE_TIME:
                self.laser_charging, self.laser_charge_timer, self.laser_cooldown, self.laser_active_timer = False, 0.0, Config.SPIKE_BOSS_LASER_COOLDOWN, Config.SPIKE_BOSS_LASER_LIFETIME
                sound_manager.stop_boss_laser_charging()
                if hasattr(sound_manager, "play_spike_boss_laser"):
                    sound_manager.play_spike_boss_laser()  # type: ignore
                # O laser sai do gap (aproximadamente linha 11 do pixel map)
                jaw_gap = 45 # Abertura máxima fixa quando dispara
                return SpikeBossLaser(
                    x=self.x + self.w / 2,
                    y=self.y + 88 + (jaw_gap / 2),
                    target_y=Config.SCREEN_HEIGHT,
                    width=self.w,
                    lifetime=Config.SPIKE_BOSS_LASER_LIFETIME,
                    owner=self
                )
            else:
                return None
        if not self.frenzy_mode or self.frenzy_pause_active or self.state == "entering" or self.laser_cooldown > 0:
            return None
        self.laser_charging, self.laser_charge_timer = True, 0.0
        sound_manager.play_boss_laser_charging()
        return None

    def get_rect(self) -> pygame.Rect:
        if not self.can_take_damage():
            return pygame.Rect(-1000, -1000, 0, 0)
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    @property
    def rect(self) -> pygame.Rect:
        return self.get_rect()

    def get_proximity_attack_data(self) -> tuple[bool, float, float, float] | None:
        if not self.proximity_attack_active:
            return None
        return (True, self.x + self.w / 2, self.y + self.h / 2, self.proximity_wave_radius)
