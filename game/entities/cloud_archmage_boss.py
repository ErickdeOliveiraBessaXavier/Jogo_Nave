from __future__ import annotations

import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Final, List, Tuple, Any, Dict

import pygame

from ..core import colors
from ..core.config import config as Config
from .mountain_mage import MountainStalagmite

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult

# ---------------------------------------------------------------------------
# Enums & Blueprints
# ---------------------------------------------------------------------------

class ArchmageState(Enum):
    APPEARING = auto()
    IDLE = auto()
    PHASE1_TWIN_ORBS = auto()
    PHASE1_EXPANSION = auto()
    PHASE2_MAZE = auto()
    PHASE2_SIPHON = auto()
    PHASE3_SINGULARITY = auto()
    PHASE3_RESONANCE = auto()
    TELEPORT = auto()
    DEFEATED = auto()

class OrbType(Enum):
    CYAN = auto()    
    PURPLE = auto()  
    ORANGE = auto()  
    WHITE = auto()   

HAT_MAP: Final[List[str]] = [
    ".........H........",
    "........HH........",
    ".......H*H........",
    "......H**H........",
    ".....HH**H........",
    "....H***HH........",
    "...HH****H........",
    "..HHHHHHHHHHHHHH..",
    ".HOOOOOOOOOOOOOOH.",
    "H****************H"
]

BODY_MAP: Final[List[str]] = [

    "....GGGGGGGG....", 
    "...GBBBBBBBBG...",
    "..GBBMMMMMMBBG..",
    "..BBMEEEEEEMBB..", # Área 'E' agora renderiza binários
    "..BBMEEEEEEMBB..",
    "..BBOOOOOOOOBB.", 
    "..BBBB....BBBB..",
    ".BBBB......BBBB.",
]

ARM_MAP: Final[List[str]] = [
    "..GG..",
    ".GBBG.",
    ".BBBB.",
    "..MM..",
    ".MOOM.", 
    ".MDDM.",
    "..DD.."
]

class CloudArchmageBoss:
    MAX_HEALTH: Final[int] = 450
    WIDTH: Final = 80
    HEIGHT: Final = 110 
    
    PHASE2_THRESHOLD: Final = 0.7
    PHASE3_THRESHOLD: Final = 0.3
    ORBIT_RADIUS: Final = 130.0
    ORB_SIZE: Final = 18

    def __init__(self, x: float | None = None, y: float | None = None) -> None:
        _screen_w = Config.SCREEN_WIDTH
        self.w, self.h = self.WIDTH, self.HEIGHT
        self.x = x if x is not None else _screen_w / 2 - self.w / 2
        self.y = y if y is not None else -self.h - 50 

        # Componentes com Lerp
        self._hat_x, self._hat_y = self.x, self.y
        self._body_x, self._body_y = self.x, self.y
        self._l_arm_x, self._l_arm_y = self.x, self.y
        self._r_arm_x, self._r_arm_y = self.x, self.y
        
        # Olhos Amarelos (flutuam entre chapéu e corpo)
        self._eye_l_x, self._eye_l_y = self.x, self.y
        self._eye_r_x, self._eye_r_y = self.x, self.y

        self.max_health = self.MAX_HEALTH
        self.health = self.MAX_HEALTH
        self.dead = False
        self.active = False

        self._state = ArchmageState.APPEARING
        self._state_timer = 2.5 
        self._hit_flash = 0.0
        self._pulse_timer = 0.0
        self._orb_angle = 0.0
        
        # Partículas de binário (x_offset, y_offset, speed, char)
        self._binary_bits = [[random.randint(5, 75), random.randint(40, 70), random.uniform(20, 40), random.choice([0, 1])] for _ in range(16)]

        self._orbs = [
            {"type": OrbType.CYAN, "color": (0, 255, 255)},
            {"type": OrbType.PURPLE, "color": (180, 50, 255)},
            {"type": OrbType.ORANGE, "color": (255, 140, 0)},
            {"type": OrbType.WHITE, "color": (220, 240, 255)},
        ]

        self._target_pos = (_screen_w / 2, 160.0)
        self._scale = 4 
        self._sprites: Dict[str, Dict[str, pygame.Surface]] = {'hat': {}, 'body': {}, 'arm': {}}
        self._render_all_parts()

    def _render_all_parts(self):
        palettes = {
            'normal': {'robe': (60, 45, 110), 'metal': (100, 105, 115), 'visor': (10, 10, 20), 
                       'core': (30, 25, 45), 'hat': (45, 30, 85), 'hat_hl': (80, 60, 150), 
                       'joint': (30, 30, 35), 'gold': (212, 175, 55), 'gola': (80, 70, 140)},
            'phase3': {'robe': (40, 10, 60), 'metal': (60, 65, 80), 'visor': (20, 0, 0), 
                       'core': (25, 5, 30), 'hat': (30, 5, 50), 'hat_hl': (100, 20, 50), 
                       'joint': (20, 10, 15), 'gold': (180, 130, 40), 'gola': (60, 20, 80)},
            'flash':  {k: (255, 255, 255) for k in ['robe', 'metal', 'visor', 'core', 'hat', 'hat_hl', 'joint', 'gold', 'gola']}
        }

        for state_name, pal in palettes.items():
            self._sprites['hat'][state_name] = self._create_part_surface(HAT_MAP, pal)
            self._sprites['body'][state_name] = self._create_part_surface(BODY_MAP, pal)
            self._sprites['arm'][state_name] = self._create_part_surface(ARM_MAP, pal)

    def _create_part_surface(self, pixelmap: List[str], pal: dict) -> pygame.Surface:
        cols, rows = len(pixelmap[0]), len(pixelmap)
        surf = pygame.Surface((cols * self._scale, rows * self._scale), pygame.SRCALPHA)
        for r_idx, row in enumerate(pixelmap):
            for c_idx, char in enumerate(row):
                if char == '.': continue
                c = pal['robe']
                if char == 'H': c = pal['hat']
                elif char == '*': c = pal['hat_hl']
                elif char == 'M': c = pal['metal']
                elif char == 'V': c = pal['visor']
                elif char == 'E': c = pal['core']
                elif char == 'D': c = pal['joint']
                elif char == 'O': c = pal['gold']
                elif char == 'G': c = pal['gola']
                pygame.draw.rect(surf, c, (c_idx * self._scale, r_idx * self._scale, self._scale, self._scale))
        return surf

    def _update_lerp_physics(self, dt: float):
        bx, by = self.x + self.w/2, self.y + 20
        
        # Corpo
        txb = bx - (self._sprites['body']['normal'].get_width() / 2)
        tyb = by + math.sin(self._pulse_timer * 4) * 4
        self._body_x += (txb - self._body_x) * 10 * dt
        self._body_y += (tyb - self._body_y) * 10 * dt

        # Chapéu (Flutua bem solto)
        txh = bx - (self._sprites['hat']['normal'].get_width() / 2)
        tyh = by - 60 + math.sin(self._pulse_timer * 3) * 10
        self._hat_x += (txh - self._hat_x) * 5 * dt
        self._hat_y += (tyh - self._hat_y) * 5 * dt

        # Olhos Amarelos (Posicionados entre o chapéu e o visor)
        target_eye_y = (self._hat_y + self._body_y + 20) / 2
        self._eye_l_x += (bx - 18 - self._eye_l_x) * 8 * dt
        self._eye_l_y += (target_eye_y - self._eye_l_y) * 8 * dt
        self._eye_r_x += (bx + 10 - self._eye_r_x) * 8 * dt
        self._eye_r_y += (target_eye_y - self._eye_r_y) * 8 * dt

        # Braços
        arm_w = self._sprites['arm']['normal'].get_width()
        self._l_arm_x += (bx - 55 - self._l_arm_x) * 7 * dt
        self._l_arm_y += (by + 20 + math.cos(self._pulse_timer * 3) * 10 - self._l_arm_y) * 7 * dt
        self._r_arm_x += (bx + 55 - arm_w - self._r_arm_x) * 7 * dt
        self._r_arm_y += (by + 20 + math.sin(self._pulse_timer * 3) * 10 - self._r_arm_y) * 7 * dt

        # Atualiza Binários
        for bit in self._binary_bits:
            bit[1] += bit[2] * dt # Move para baixo
            if bit[1] > 70: # Reset
                bit[1] = 40
                bit[3] = random.choice([0, 1])

    def update(self, dt: float, player_pos: Tuple[float, float] | None = None) -> List[Any]:
        if self.dead: return []
        self._pulse_timer += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        hp_ratio = self.health / self.max_health
        self._orb_angle += dt * 1.2 * (1.0 + (1.0 - hp_ratio) * 2.0)
        
        if self._state == ArchmageState.APPEARING: self._update_appearing(dt)
        elif self._state == ArchmageState.IDLE: self._update_idle(dt, hp_ratio)
        elif self._state == ArchmageState.TELEPORT: self._update_teleport(dt)
        
        self._update_lerp_physics(dt)
        return []

    def _update_appearing(self, dt: float):
        self._state_timer -= dt
        tx, ty = self._target_pos
        self.x += (tx - self.x - self.w/2) * 2.0 * dt
        self.y += (ty - self.y) * 2.5 * dt
        if self._state_timer <= 0:
            self._state = ArchmageState.IDLE
            self.active = True

    def _update_idle(self, dt: float, hp_ratio: float):
        self._state_timer -= dt
        if self._state_timer <= 0:
            self._state = ArchmageState.TELEPORT
            self._state_timer = 2.0

    def _update_teleport(self, dt: float):
        self._state_timer -= dt
        if self._state_timer <= 0:
            self.x = random.randint(100, Config.SCREEN_WIDTH - 100)
            self.y = random.randint(50, 200)
            self._state = ArchmageState.IDLE
            self._state_timer = 3.0

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead and self._state != ArchmageState.DEFEATED: return
        hp_ratio = self.health / self.max_health
        state_key = 'flash' if self._hit_flash > 0 else ('normal' if hp_ratio > 0.3 else 'phase3')

        self._draw_orbs(surface)
        self._draw_grimório(surface)
        
        if self._state != ArchmageState.DEFEATED:
            self._draw_flowing_mantle(surface, state_key)

        # Desenho das partes
        surface.blit(self._sprites['arm'][state_key], (int(self._l_arm_x), int(self._l_arm_y)))
        surface.blit(self._sprites['arm'][state_key], (int(self._r_arm_x), int(self._r_arm_y)))
        surface.blit(self._sprites['body'][state_key], (int(self._body_x), int(self._body_y)))
        
        # Desenha os Olhos Amarelos (Atrás do chapéu, na frente do corpo)
        if self._hit_flash <= 0:
            eye_color = (255, 230, 0)
            pygame.draw.rect(surface, eye_color, (int(self._eye_l_x), int(self._eye_l_y), 8, 8))
            pygame.draw.rect(surface, eye_color, (int(self._eye_r_x), int(self._eye_r_y), 8, 8))

        surface.blit(self._sprites['hat'][state_key], (int(self._hat_x), int(self._hat_y)))
        
        # Desenha o Binário na barriga
        self._draw_binary_core(surface, hp_ratio)

    def _draw_binary_core(self, surface: pygame.Surface, hp_ratio: float):
        if self._hit_flash > 0: return
        color = (0, 255, 200) if hp_ratio > 0.3 else (255, 50, 50)
        
        for bx, by, spd, char in self._binary_bits:
            # Renderiza um 0 ou 1 simplificado (pequenos traços)
            draw_x = self._body_x + bx
            draw_y = self._body_y + by
            if char == 1:
                pygame.draw.rect(surface, color, (draw_x, draw_y, 2, 6))
            else:
                pygame.draw.rect(surface, color, (draw_x, draw_y, 4, 6), 1)

    def _draw_flowing_mantle(self, surface: pygame.Surface, state_key: str):
        color = (80, 60, 150) if state_key == 'normal' else (100, 20, 50)
        if state_key == 'flash': color = (255, 255, 255)
        base_y = self._body_y + (len(BODY_MAP) * self._scale) - 5
        for i in range(4):
            offset_x = (i * 12) + 6
            wave = math.sin(self._pulse_timer * 4 + i) * 12
            pts = [(self._body_x + offset_x, base_y), (self._body_x + offset_x + 10, base_y), (self._body_x + offset_x + 5 + wave, base_y + 35)]
            pygame.draw.polygon(surface, color, pts)

    def _draw_grimório(self, surface: pygame.Surface):
        if self._state == ArchmageState.DEFEATED: return
        gx = self._body_x + 60 + math.sin(self._pulse_timer * 2) * 5
        gy = self._body_y + 20 + math.cos(self._pulse_timer * 2) * 5
        s = pygame.Surface((30, 40), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 200, 255, 60), (0, 0, 30, 40), border_radius=3)
        pygame.draw.rect(s, (0, 255, 255, 150), (0, 0, 30, 40), 1, border_radius=3)
        for i in range(5):
            w = random.randint(10, 20)
            pygame.draw.line(s, (0, 255, 255, 180), (5, 8 + i*7), (5 + w, 8 + i*7), 2)
        surface.blit(s, (gx, gy))

    def _draw_orbs(self, surface: pygame.Surface):
        cx, cy = self.x + self.w/2, self.y + self.h/2
        for i, orb in enumerate(self._orbs):
            angle = self._orb_angle + (i * (math.tau / len(self._orbs)))
            ox = cx + math.cos(angle) * self.ORBIT_RADIUS
            oy = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
            pygame.draw.circle(surface, (*orb["color"], 40), (int(ox), int(oy)), self.ORB_SIZE + 8)
            pygame.draw.circle(surface, orb["color"], (int(ox), int(oy)), self.ORB_SIZE)
            rune_surf = pygame.Surface((12, 12), pygame.SRCALPHA)
            pygame.draw.rect(rune_surf, (255, 255, 255), (0, 0, 12, 12), 2)
            rotated_rune = pygame.transform.rotate(rune_surf, self._orb_angle * 100 + i * 45)
            surface.blit(rotated_rune, (ox - rotated_rune.get_width()/2, oy - rotated_rune.get_height()/2))

    def take_damage(self, amount: int = 1) -> None:
        if self.dead or not self.active: return
        self.health -= amount
        self._hit_flash = 0.15
        if self.health <= 0:
            self.dead = True
            self._state = ArchmageState.DEFEATED

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult
        self.take_damage(damage)
        if self.dead: return HitResult(killed=True, points=5000, explosion_size=100, sound=hit_sounds.EXPLOSION_ALIEN)
        return HitResult(explosion_size=20, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool: return self.dead