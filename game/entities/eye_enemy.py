import pygame
import random
import math
from typing import List, Tuple, TypedDict
from ..core.config import Config
from ..core import colors
from .eye_laser import EyeLaser

class ChargingParticle(TypedDict):
    pos: pygame.Vector2
    speed: float
    color: Tuple[int, int, int]
    size: float

class EyeEnemy:
    def __init__(self, x: float, y: float):
        self.w = 40
        self.h = 40
        self.x = x
        self.y = -self.h # Start off-screen
        self.target_y = y
        self.health = 20
        self.speed_x = 75
        self.dead = False

        self.state = "entering"  # entering, moving, aiming, charging, firing, waiting
        self.timer = random.uniform(1.0, 3.0) # Time until next action

        self.aim_duration = 1.0
        self.charge_duration = 1.5
        self.active_laser: EyeLaser | None = None
        self.locked_player_pos: tuple[float, float] | None = None

        self.charging_particles: List[ChargingParticle] = []

        # Aiming line properties
        self.aim_dash_length = Config.BOSS_AIM_DASH_LENGTH
        self.aim_gap_length = Config.BOSS_AIM_GAP_LENGTH
        # Torna o tracejado mais longo e o espaço menor
        self.aim_dash_length = 15  # valor maior para traço
        self.aim_gap_length = 15    # valor menor para espaço
        self.aim_distance = 400

        self.aim_anim_offset = 0.0  # Para animar a linha de mira
        self.aim_anim_base_speed = 120
        self.aim_anim_charge_speed = 320  # velocidade maior para "charging"

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float, player_x: float, player_y: float) -> list[EyeLaser] | None:
        if self.state == "entering":
            self.y += 150 * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "moving"
                self.timer = random.uniform(1.0, 3.0)
            return None

        if self.state == "moving":
            self.x += self.speed_x * dt
            if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
                self.speed_x *= -1
            
            self.timer -= dt
            if self.timer <= 0:
                self.state = "aiming"
                self.timer = self.aim_duration
                self.locked_player_pos = (player_x, player_y)
        
        elif self.state == "aiming":
            self.timer -= dt
            if self.timer <= 0:
                self.state = "charging"
                self.timer = self.charge_duration # Timeout for charging
                self._initialize_charging_particles()

        elif self.state == "charging":
            self._update_charging_particles(dt)
            self.timer -= dt
            
            if not self.charging_particles or self.timer <= 0:
                self.state = "firing"
                self.charging_particles.clear()
                if self.locked_player_pos is not None:
                    start_x = self.x + self.w/2
                    start_y = self.y + self.h/2
                    px, py = self.locked_player_pos

                    dir_x = px - start_x
                    dir_y = py - start_y
                    
                    length = math.hypot(dir_x, dir_y)
                    if length == 0:
                        extended_px = start_x
                        extended_py = Config.SCREEN_HEIGHT
                    else:
                        dir_x /= length
                        dir_y /= length
                        max_screen_distance = math.hypot(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
                        extended_px = start_x + dir_x * max_screen_distance * 2
                        extended_py = start_y + dir_y * max_screen_distance * 2

                    laser = EyeLaser(start_x, start_y, extended_px, extended_py)
                    self.active_laser = laser
                    return [laser]

        elif self.state == "firing":
            self.state = "waiting"

        elif self.state == "waiting":
            if self.active_laser and self.active_laser.dead:
                self.active_laser = None
                self.state = "moving"
                self.timer = random.uniform(2.0, 4.0)
        
        # Animação da linha de mira: velocidade depende do estado
        if self.state == "charging":
            self.aim_anim_offset += dt * self.aim_anim_charge_speed
        elif self.state == "aiming":
            self.aim_anim_offset += dt * self.aim_anim_base_speed
        # Mantém o offset dentro do ciclo do dash+gap
        total_cycle = self.aim_dash_length + self.aim_gap_length
        if self.aim_anim_offset > total_cycle:
            self.aim_anim_offset -= total_cycle

        return None

    def _update_charging_particles(self, dt: float):
        for particle in self.charging_particles[:]:
            direction = pygame.Vector2(self.rect.center) - particle["pos"]
            if direction.length() > 1:
                direction.normalize_ip()
                particle["pos"] += direction * particle["speed"] * dt
            else:
                self.charging_particles.remove(particle)

    def _initialize_charging_particles(self):
        self.charging_particles.clear()
        for _ in range(25):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(40, 80)
            pos = pygame.Vector2(self.rect.centerx + math.cos(angle) * distance, self.rect.centery + math.sin(angle) * distance)
            # Selecionar cor explicitamente como tupla
            particle_color: Tuple[int, int, int] = random.choice([colors.MAGENTA, colors.PURPLE])
            particle: ChargingParticle = {
                "pos": pos,
                "speed": random.uniform(50, 80),
                "color": particle_color,
                "size": random.uniform(1, 4),
            }
            self.charging_particles.append(particle)

    def _draw_dashed_line(self, surface: pygame.Surface, start_pos: tuple[float, float], end_pos: tuple[float, float], color: Tuple[int, int, int], width: int = 1, anim_offset: float = 0.0) -> None:
        x1, y1 = start_pos
        x2, y2 = end_pos
        dl = pygame.math.Vector2(x2 - x1, y2 - y1)
        length = dl.length()
        if length == 0: return
        dl.normalize_ip()

        current_distance = anim_offset % (self.aim_dash_length + self.aim_gap_length)
        while current_distance < length:
            start_segment = pygame.math.Vector2(x1, y1) + dl * current_distance
            end_segment = pygame.math.Vector2(x1, y1) + dl * min(current_distance + self.aim_dash_length, length)
            pygame.draw.line(surface, color, (int(start_segment.x), int(start_segment.y)), (int(end_segment.x), int(end_segment.y)), width)
            current_distance += self.aim_dash_length + self.aim_gap_length

    def _draw_pixel_eye(self, surface: pygame.Surface, player_x: float | None, player_y: float | None):
        """Desenha um olho pixel art assustador"""
        eye_center_x = self.rect.centerx
        eye_center_y = self.rect.centery
        iris_offset_x = 0
        iris_offset_y = 0
        
        # Calcular direção do olhar
        if player_x is not None and player_y is not None:
            dx = player_x - eye_center_x
            dy = player_y - eye_center_y
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance > 0:
                dx = dx / distance
                dy = dy / distance
                max_offset = 6
                iris_offset_x = dx * max_offset
                iris_offset_y = dy * max_offset

        # Cores
        sclera_color = (240, 235, 220)  # Branco amarelado
        vein_color = (180, 40, 40)  # Vermelho escuro para veias
        iris_color = colors.RED if self.state in ("charging", "ready", "aiming") else (60, 80, 120)
        pupil_color = (20, 20, 25)
        highlight_color = (255, 255, 255)
        shadow_color = (100, 100, 110)

        # Escala do pixel (cada "pixel" tem esse tamanho)
        pixel_size = 2
        
        # Base da esclerótica com forma oval pixelada
        base_x = int(self.x)
        base_y = int(self.y)
        
        # Desenhar esclerótica com bordas pixeladas
        for py in range(0, self.h, pixel_size):
            for px in range(0, self.w, pixel_size):
                # Criar forma oval
                norm_x = (px - self.w/2) / (self.w/2)
                norm_y = (py - self.h/2) / (self.h/2)
                if norm_x*norm_x + norm_y*norm_y <= 1.0:
                    # Sombra nas bordas
                    edge_dist = math.sqrt(norm_x*norm_x + norm_y*norm_y)
                    if edge_dist > 0.85:
                        color = shadow_color
                    else:
                        color = sclera_color
                    pygame.draw.rect(surface, color, (base_x + px, base_y + py, pixel_size, pixel_size))

        # Veias sangrentas (mais visíveis quando charging/aiming/ready)
        num_veins = 6 if self.state in ("charging", "ready", "aiming") else 4
        vein_intensity = 1.0 if self.state in ("charging", "ready", "aiming") else 0.5
        
        for i in range(num_veins):
            angle = (i / num_veins) * math.pi * 2 + self.aim_anim_offset * 0.1
            start_dist = 8
            end_dist = self.w/2 - 4
            
            for dist in range(int(start_dist), int(end_dist), pixel_size):
                vein_x = eye_center_x + math.cos(angle) * dist + random.uniform(-1, 1)
                vein_y = eye_center_y + math.sin(angle) * dist + random.uniform(-1, 1)
                
                # Cor da veia com intensidade variável
                vein_draw_color = tuple(int(vein_color[i] * vein_intensity) for i in range(3))
                
                # Veias mais grossas e escuras quando carregando
                vein_thickness = pixel_size * 2 if self.state in ("charging", "aiming") else pixel_size
                pygame.draw.rect(surface, vein_draw_color, (int(vein_x), int(vein_y), vein_thickness, vein_thickness))

        # Íris pixelada
        iris_center_x = int(eye_center_x + iris_offset_x)
        iris_center_y = int(eye_center_y + iris_offset_y)
        iris_radius = int(self.w * 0.3)
        
        for py in range(-iris_radius, iris_radius, pixel_size):
            for px in range(-iris_radius, iris_radius, pixel_size):
                if px*px + py*py <= iris_radius*iris_radius:
                    # Gradiente radial na íris
                    dist = math.sqrt(px*px + py*py) / iris_radius
                    if dist < 0.3:
                        color = pupil_color
                    elif dist < 0.7:
                        # Mistura para criar textura
                        mix = (dist - 0.3) / 0.4
                        color = tuple(int(pupil_color[i] * (1-mix) + iris_color[i] * mix) for i in range(3))
                    else:
                        color = iris_color
                    
                    pygame.draw.rect(surface, color, 
                                   (iris_center_x + px, iris_center_y + py, pixel_size, pixel_size))

        # Pupila (maior e mais assustadora)
        pupil_radius = int(self.w * 0.15)
        for py in range(-pupil_radius, pupil_radius, pixel_size):
            for px in range(-pupil_radius, pupil_radius, pixel_size):
                if px*px + py*py <= pupil_radius*pupil_radius:
                    pygame.draw.rect(surface, pupil_color,
                                   (iris_center_x + px, iris_center_y + py, pixel_size, pixel_size))

        # Reflexo de luz (highlight) - apenas quando não está em ataque
        if self.state not in ("charging", "ready", "aiming"):
            highlight_offset_x = -6
            highlight_offset_y = -6
            highlight_radius = 4
            for py in range(0, highlight_radius, pixel_size):
                for px in range(0, highlight_radius, pixel_size):
                    if px*px + py*py <= highlight_radius*highlight_radius:
                        pygame.draw.rect(surface, highlight_color,
                                       (iris_center_x + highlight_offset_x + px, 
                                        iris_center_y + highlight_offset_y + py, 
                                        pixel_size, pixel_size))

        # Brilho vermelho quando preparando para atacar
        if self.state in ("charging", "ready", "aiming"):
            # Brilho pulsante (mais intenso no estado "ready")
            pulse_multiplier = 1.5 if self.state == "ready" else 1.0
            pulse = abs(math.sin(self.aim_anim_offset * 0.1)) * 0.5 + 0.5
            pulse *= pulse_multiplier
            glow_color = (255, int(50 * pulse), int(50 * pulse))
            glow_radius = int(self.w * 0.45)
            
            for py in range(-glow_radius, glow_radius, pixel_size):
                for px in range(-glow_radius, glow_radius, pixel_size):
                    dist_sq = px*px + py*py
                    if dist_sq <= glow_radius*glow_radius and dist_sq > iris_radius*iris_radius:
                        alpha = (1 - math.sqrt(dist_sq) / glow_radius) * pulse
                        if alpha > 0.3:
                            pygame.draw.rect(surface, glow_color,
                                           (iris_center_x + px, iris_center_y + py, pixel_size, pixel_size))

    def draw(self, surface: pygame.Surface, player_x: float | None = None, player_y: float | None = None):
        # Draw charging particles
        for particle in self.charging_particles:
            pygame.draw.circle(surface, particle["color"], (int(particle["pos"].x), int(particle["pos"].y)), int(particle["size"]))

        # Desenhar olho pixel art assustador
        self._draw_pixel_eye(surface, player_x, player_y)

        # Aiming line
        if self.state in ("aiming", "charging") and self.locked_player_pos:
            start_pos = (self.x + self.w/2, self.y + self.h/2)
            end_pos = self.locked_player_pos
            
            # Calculate the direction vector
            dir_x = end_pos[0] - start_pos[0]
            dir_y = end_pos[1] - start_pos[1]
            
            length = math.hypot(dir_x, dir_y)
            if length == 0:
                extended_end_pos = (start_pos[0], Config.SCREEN_HEIGHT)
            else:
                dir_x /= length
                dir_y /= length
                max_screen_distance = math.hypot(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
                extended_end_pos = (start_pos[0] + dir_x * max_screen_distance * 2, start_pos[1] + dir_y * max_screen_distance * 2)

            self._draw_dashed_line(surface, start_pos, extended_end_pos, (255, 60, 60), 2, anim_offset=self.aim_anim_offset)

    def get_points_value(self) -> int:
        return 200

    def take_damage(self, amount: int):
        self.health -= amount
        if self.health <= 0:
            self.destroy()

    def destroy(self):
        self.dead = True
        if self.active_laser:
            self.active_laser.dead = True