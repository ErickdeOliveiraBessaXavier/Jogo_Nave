import math
import random
from typing import List, Any, TypedDict, Tuple

import pygame

from ..core import colors
from ..core.config import Config
from ..core.time import Timer
from .boss_laser import BossLaser


class ChargingParticle(TypedDict):
    """Type definition for charging particles."""
    pos: pygame.Vector2
    speed: float
    color: Tuple[int, int, int]
    size: float


class DisappearParticle(TypedDict):
    """Type definition for circle disappear particles."""
    pos: pygame.Vector2
    velocity: pygame.Vector2
    size: float
    color: Tuple[int, int, int]
    lifetime: float
    max_lifetime: float

class Boss:
    """
    Boss entity with face-oriented combat system.
    
    Features:
    - Face orientation system that tracks player
    - State machine for complex behavior patterns
    - Particle effects for charging and firing
    - Delayed laser firing for better gameplay
    - Frenzy mode with enhanced attacks
    """
    # Constants for better maintainability
    FRENZY_LASER_ANGLES: List[float] = [-0.44, 0, 0.44]  # ~25 degrees in radians
    LASER_DISTANCE: int = 2000  # Maximum laser reach
    FACE_DISTANCE_RATIO: float = 0.5  # Face distance from center as ratio of size
    MAX_CHARGE_RADIUS: float = 15.0  # Maximum charging circle radius
    LASER_SPREAD_OFFSET: int = 10  # Offset between frenzy lasers
    FACE_INDICATOR_SIZE: int = 8  # Size of face indicator rectangle
    FACE_DIRECTION_LINE_LENGTH: int = 15  # Length of face direction indicator
    
    def __init__(self, x: float, y: float, health: int = Config.BOSS_HEALTH, hit_score: int = 50):
        # Position and size
        self.w = 100
        self.h = 80
        self.x = x
        self.y = -self.h
        self.target_y = y
        
        # Health and state
        self.health = health
        self.max_health = health
        self.hit_score = hit_score
        self.dead = False
        
        # Movement
        self.speed = Config.BOSS_INITIAL_SPEED
        self.direction = 1
        self.entry_speed = Config.BOSS_ENTRY_SPEED
        
        # State machine
        self.state = "entering"
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0
        
        # Attack system
        self._init_attack_system()
        
        # Manual charge progress tracking
        self.charge_progress = 0.0
        
        # Visual effects
        self.charging_particles: List[ChargingParticle] = []
        self.fired_lasers: List[BossLaser] = []
        self.circle_disappear_particles: List[DisappearParticle] = []
        
        # Orientation system - face always facing player
        self.rotation_angle = 0.0  # Ângulo de rotação em radianos
        self.facing_direction = pygame.Vector2(0, 1)  # Direção que a face principal está voltada
        self.face_center = pygame.Vector2(0, 0)  # Centro da face principal
        
        # Laser delay system for better player reaction time
        self.laser_delay_timer = 0.0
        self.laser_delay_duration = 0.3  # 300ms de delay antes do disparo
        self.pending_laser_data: dict[str, Any] | None = None  # Dados do laser que será disparado após o delay

    def _update_orientation(self, player_x: float, player_y: float) -> None:
        """Update boss orientation to face the player."""
        boss_center_x = self.x + self.w / 2
        boss_center_y = self.y + self.h / 2
        
        # Calcular direção para o jogador
        dx = player_x - boss_center_x
        dy = player_y - boss_center_y
        
        # Normalizar direção
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            self.facing_direction.x = dx / length
            self.facing_direction.y = dy / length
            
            # Calcular ângulo de rotação
            self.rotation_angle = math.atan2(dy, dx)
        
        # Calcular posição do centro da face principal
        # A face principal fica na direção do jogador
        face_distance = min(self.w, self.h) * self.FACE_DISTANCE_RATIO
        self.face_center.x = boss_center_x + self.facing_direction.x * face_distance
        self.face_center.y = boss_center_y + self.facing_direction.y * face_distance
    
    def _get_face_position(self) -> tuple[float, float]:
        """Get the position of the main face (facing the player)."""
        return (self.face_center.x, self.face_center.y)
    
    def _get_face_normal(self) -> pygame.Vector2:
        """Get the normal vector of the main face (pointing towards player)."""
        return self.facing_direction.copy()

    def _init_attack_system(self) -> None:
        """Initialize attack timing and states."""
        self.attack_timer = Timer(random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL))
        self.charge_duration = Config.BOSS_CHARGE_DURATION
        self.charge_timer = Timer(self.charge_duration)
        self.fire_duration = Config.BOSS_LASER_LIFETIME
        self.fire_timer = Timer(self.fire_duration)

    def _update_charging_particles(self, dt: float) -> None:
        """Update particle convergence animation."""
        # As partículas convergem para o centro da face principal
        target_point = pygame.Vector2(self.face_center.x, self.face_center.y)
        
        for p in self.charging_particles[:]:
            direction = (target_point - p['pos'])
            if direction.length() > 0:
                direction.normalize_ip()
            
            p['pos'] += direction * p['speed'] * dt
            p['size'] -= 0.05

            if p['pos'].distance_to(target_point) < 8 or p['size'] <= 0:
                self.charging_particles.remove(p)

    def _generate_charging_particles(self) -> None:
        """Generate new charging particles."""
        if len(self.charging_particles) < 25:
            # Gerar partículas em um padrão circular ao redor da face principal
            face_x, face_y = self._get_face_position()
            
            for _ in range(4):
                # Gerar partículas em posições aleatórias ao redor da face
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(80, 150)
                
                # Posição relativa ao centro da face
                offset_x = math.cos(angle) * distance
                offset_y = math.sin(angle) * distance
                
                start_pos = pygame.Vector2(
                    face_x + offset_x,
                    face_y + offset_y
                )
                
                particle: ChargingParticle = {
                    'pos': start_pos,
                    'speed': random.uniform(200, 350),
                    'color': random.choice([(255,255,100), (255,200,100), (255,255,255)]),
                    'size': random.uniform(5, 10)
                }
                self.charging_particles.append(particle)

    def _create_lasers(self) -> List[BossLaser]:
        """Create laser objects based on current mode."""
        face_x, face_y = self._get_face_position()
        laser_lifetime = Config.BOSS_FRENZY_LASER_LIFETIME if self.frenzy_mode else Config.BOSS_LASER_LIFETIME
        
        if self.frenzy_mode:
            return self._create_frenzy_lasers(face_x, face_y, laser_lifetime)
        else:
            return self._create_normal_laser(face_x, face_y, laser_lifetime)

    def _create_laser_pattern(self, face_x: float, face_y: float, lifetime: float, is_frenzy: bool, face_normal: pygame.Vector2 | None = None) -> List[BossLaser]:
        """Create laser pattern based on mode (unified implementation)."""
        # Use the provided face normal or get current one
        if face_normal is None:
            face_normal = self._get_face_normal()
        
        if is_frenzy:
            # Modo frenesi: 3 lasers em leque
            lasers: List[BossLaser] = []
            
            for i, angle_offset in enumerate(self.FRENZY_LASER_ANGLES):
                cos_offset = math.cos(angle_offset)
                sin_offset = math.sin(angle_offset)
                
                rotated_x = face_normal.x * cos_offset - face_normal.y * sin_offset
                rotated_y = face_normal.x * sin_offset + face_normal.y * cos_offset
                
                offset = (i - 1) * self.LASER_SPREAD_OFFSET  # -10, 0, +10
                start_x = face_x + offset * math.cos(self.rotation_angle + math.pi/2)
                start_y = face_y + offset * math.sin(self.rotation_angle + math.pi/2)
                
                target_x = start_x + rotated_x * self.LASER_DISTANCE
                target_y = start_y + rotated_y * self.LASER_DISTANCE
                
                laser = BossLaser(start_x, start_y, target_x, target_y, lifetime=lifetime)
                lasers.append(laser)
            
            return lasers
        else:
            # Modo calmo: laser único
            target_x = face_x + face_normal.x * self.LASER_DISTANCE
            target_y = face_y + face_normal.y * self.LASER_DISTANCE
            
            return [BossLaser(face_x, face_y, target_x, target_y, lifetime=lifetime)]

    def _create_frenzy_lasers(self, face_x: float, face_y: float, lifetime: float) -> List[BossLaser]:
        """Create multiple lasers for frenzy mode."""
        return self._create_laser_pattern(face_x, face_y, lifetime, is_frenzy=True)

    def _create_normal_laser(self, face_x: float, face_y: float, lifetime: float) -> List[BossLaser]:
        """Create single laser for normal mode."""
        return self._create_laser_pattern(face_x, face_y, lifetime, is_frenzy=False)

    def _update_entering_state(self, dt: float) -> None:
        """Handle boss entry animation."""
        self.y += self.entry_speed * dt
        if self.y >= self.target_y:
            self.y = self.target_y
            self.state = "active"
            self.attack_timer.start()

    def _update_active_state(self, dt: float) -> None:
        """Handle boss movement and attack timing."""
        self.x += self.speed * self.direction
        if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
            self.direction *= -1
        
        self.attack_timer.update(dt)
        if self.attack_timer.done():
            self.state = "aiming"

    def _update_charging_state(self, dt: float) -> None:
        """Handle charging animation."""
        self.charge_timer.update(dt)
        # Update manual progress tracking
        self.charge_progress = min(1.0, self.charge_progress + dt / self.charge_duration)
        
        self._generate_charging_particles()
        self._update_charging_particles(dt)
        
        if self.charge_timer.done():
            self.state = 'converging'

    def _get_charge_circle_radius(self) -> float:
        """Calculate the charging circle radius based on charge progress."""
        if self.state not in ("charging", "converging"):
            return 0.0
        
        # Durante charging, cresce de 0 até o raio máximo
        if self.state == "charging":
            return self.charge_progress * self.MAX_CHARGE_RADIUS
        
        # Durante converging, mantém o raio máximo
        return self.MAX_CHARGE_RADIUS

    def _create_circle_disappear_particles(self) -> None:
        """Create small particles when the charging circle disappears."""
        face_x, face_y = self._get_face_position()
        
        # Criar várias partículas pequenas ao redor da face principal
        for _ in range(12):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(10, 20)
            start_x = face_x + math.cos(angle) * distance
            start_y = face_y + math.sin(angle) * distance
            
            particle: DisappearParticle = {
                'pos': pygame.Vector2(start_x, start_y),
                'velocity': pygame.Vector2(
                    math.cos(angle) * random.uniform(50, 100),
                    math.sin(angle) * random.uniform(50, 100)
                ),
                'size': random.uniform(2, 4),
                'color': random.choice([(255, 255, 200), (255, 255, 100), (255, 200, 100)]),
                'lifetime': random.uniform(0.3, 0.6),
                'max_lifetime': random.uniform(0.3, 0.6)
            }
            particle['max_lifetime'] = particle['lifetime']
            self.circle_disappear_particles.append(particle)

    def _update_circle_disappear_particles(self, dt: float) -> None:
        """Update the circle disappear particles."""
        for p in self.circle_disappear_particles[:]:
            p['pos'] += p['velocity'] * dt
            p['lifetime'] -= dt
            
            # Fade out effect
            fade_ratio = p['lifetime'] / p['max_lifetime']
            p['size'] = fade_ratio * 4
            
            if p['lifetime'] <= 0 or p['size'] <= 0:
                self.circle_disappear_particles.remove(p)

    def _update_converging_state(self, dt: float) -> List[BossLaser]:
        """Handle particle convergence and preparation for laser firing."""
        self._update_charging_particles(dt)
        
        if not self.charging_particles:
            # Criar partículas de desaparecimento do círculo
            if not self.circle_disappear_particles:  # Só criar uma vez
                self._create_circle_disappear_particles()
            
            # Preparar dados do laser para disparo atrasado
            self.pending_laser_data = self._prepare_laser_data()
            self.state = "preparing_to_fire"
            self.laser_delay_timer = self.laser_delay_duration
            
        return []

    def _prepare_laser_data(self) -> dict[str, Any]:
        """
        Prepare laser data for delayed firing.
        
        This captures the boss's orientation at the moment of aiming,
        ensuring that the laser fires in the originally intended direction
        even after the 300ms delay, giving players time to react.
        """
        face_x, face_y = self._get_face_position()
        face_normal = self._get_face_normal()
        laser_lifetime = Config.BOSS_FRENZY_LASER_LIFETIME if self.frenzy_mode else Config.BOSS_LASER_LIFETIME
        
        return {
            'face_x': face_x,
            'face_y': face_y,
            'face_normal': face_normal.copy(),  # Captured direction for consistent aiming
            'lifetime': laser_lifetime,
            'frenzy_mode': self.frenzy_mode
        }
    
    def _update_preparing_to_fire_state(self, dt: float) -> List[BossLaser]:
        """Handle the delay before firing lasers."""
        self.laser_delay_timer -= dt
        
        if self.laser_delay_timer <= 0 and self.pending_laser_data:
            # Disparar o laser usando os dados preparados
            new_lasers = self._create_lasers_from_data(self.pending_laser_data)
            
            self.fired_lasers.extend(new_lasers)
            self.fire_timer = Timer(self.pending_laser_data['lifetime'])
            self.fire_timer.start()
            
            self.state = "firing"
            self.pending_laser_data = None
            
            return new_lasers
        
        return []
    
    def _create_lasers_from_data(self, laser_data: dict[str, Any]) -> List[BossLaser]:
        """Create lasers from prepared data."""
        return self._create_laser_pattern(
            laser_data['face_x'], 
            laser_data['face_y'], 
            laser_data['lifetime'], 
            laser_data['frenzy_mode'],
            laser_data['face_normal']  # Use the saved direction from when the attack started
        )

    def _update_firing_state(self, dt: float) -> None:
        """Handle laser firing and cleanup."""
        self.fire_timer.update(dt)
        
        for laser in self.fired_lasers[:]:
            laser.update(dt)
            if laser.dead:
                self.fired_lasers.remove(laser)

        if self.fire_timer.done() and all(l.is_animation_finished() for l in self.fired_lasers):
            self.state = "active"
            self._reset_attack_timer()
            self.fired_lasers.clear()

    def _reset_attack_timer(self) -> None:
        """Reset attack timer based on current mode."""
        if self.frenzy_mode:
            self.attack_timer = Timer(random.uniform(*Config.BOSS_FRENZY_ATTACK_INTERVAL))
        else:
            self.attack_timer = Timer(random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL))
        self.attack_timer.start()

    def update(self, dt: float, player_x: float, player_y: float | None = None) -> List[BossLaser]:
        """Main update method - state machine."""
        self.frenzy_shake_timer = max(0.0, self.frenzy_shake_timer - dt)
        
        # Store player position for drawing
        self.player_x = player_x
        self.player_y = player_y
        
        # Update orientation to face player
        if player_y is not None:
            self._update_orientation(player_x, player_y)

        # Sempre atualizar partículas de desaparecimento do círculo
        self._update_circle_disappear_particles(dt)

        # Update fired lasers
        for laser in self.fired_lasers[:]:
            laser.update(dt)
            if laser.dead:
                self.fired_lasers.remove(laser)

        if self.state == "entering":
            self._update_entering_state(dt)
        elif self.state == "active":
            self._update_active_state(dt)
        elif self.state == "aiming":
            self.state = "charging"
            self.charge_timer.start()
            self.charge_progress = 0.0  # Reset progress
            self.charging_particles.clear()
        elif self.state == "charging":
            self._update_charging_state(dt)
        elif self.state == 'converging':
            return self._update_converging_state(dt)
        elif self.state == "preparing_to_fire":
            return self._update_preparing_to_fire_state(dt)
        elif self.state == "firing":
            self._update_firing_state(dt)
        
        return []

    def _draw_aiming_line(self, surface: pygame.Surface) -> None:
        """Draw the animated aiming line."""
        if (pygame.time.get_ticks() % Config.BOSS_AIM_BLINK_INTERVAL) < Config.BOSS_AIM_BLINK_ON_DURATION:
            face_x, face_y = self._get_face_position()
            face_normal = self._get_face_normal()
            
            time_based_offset = (pygame.time.get_ticks() // 50) % (
                Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
            )

            # Desenhar linha tracejada na direção da face
            current_distance = time_based_offset - (
                Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
            )
            
            while current_distance < self.LASER_DISTANCE:
                start_distance = current_distance
                end_distance = current_distance + Config.BOSS_AIM_DASH_LENGTH
                
                if end_distance > 0:  # Só desenhar se a linha está à frente da face
                    actual_start_distance = max(0, start_distance)
                    actual_end_distance = min(self.LASER_DISTANCE, end_distance)
                    
                    # Calcular posições reais da linha
                    start_line_x = face_x + face_normal.x * actual_start_distance
                    start_line_y = face_y + face_normal.y * actual_start_distance
                    end_line_x = face_x + face_normal.x * actual_end_distance
                    end_line_y = face_y + face_normal.y * actual_end_distance
                    
                    pygame.draw.line(surface, colors.BOSS_AIM_LINE, 
                                   (start_line_x, start_line_y), 
                                   (end_line_x, end_line_y), 2)
                
                current_distance += Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH

    def draw(self, surface: pygame.Surface) -> None:
        """Render the boss and its effects."""
        offset_x, offset_y = 0, 0
        if self.frenzy_shake_timer > 0:
            offset_x = random.randint(-3, 3)
            offset_y = random.randint(-3, 3)

        # Normal boss rendering
        pygame.draw.rect(surface, (255, 0, 0), (self.x + offset_x, self.y + offset_y, self.w, self.h))
        
        # Desenhar indicação da face principal (pequeno retângulo na direção do jogador)
        if hasattr(self, 'face_center') and self.state != "entering":
            face_x, face_y = self._get_face_position()
            face_normal = self._get_face_normal()
            
            # Pequeno retângulo indicando a face principal
            face_rect_x = face_x + offset_x - self.FACE_INDICATOR_SIZE // 2
            face_rect_y = face_y + offset_y - self.FACE_INDICATOR_SIZE // 2
            pygame.draw.rect(surface, (255, 255, 255), 
                           (int(face_rect_x), int(face_rect_y), self.FACE_INDICATOR_SIZE, self.FACE_INDICATOR_SIZE))
            
            # Linha pequena indicando direção
            line_end_x = face_x + face_normal.x * self.FACE_DIRECTION_LINE_LENGTH + offset_x
            line_end_y = face_y + face_normal.y * self.FACE_DIRECTION_LINE_LENGTH + offset_y
            pygame.draw.line(surface, (255, 255, 255), 
                           (face_x + offset_x, face_y + offset_y), 
                           (int(line_end_x), int(line_end_y)), 2)
        
        # Health bar (except during entry)
        if self.state != "entering":
            self._draw_health_bar(surface)

        # Aiming line
        if self.state in ("aiming", "charging", "converging"):
            self._draw_aiming_line(surface)

        # Charging circle - círculo que cresce durante o carregamento
        if self.state in ("charging", "converging", "preparing_to_fire"):
            # O círculo aparece na face principal do boss
            face_x, face_y = self._get_face_position()
            circle_x = face_x + offset_x
            circle_y = face_y + offset_y
            
            charge_radius = self._get_charge_circle_radius()
            if charge_radius > 0:
                # Círculo externo (borda)
                pygame.draw.circle(surface, (255, 255, 100), 
                                 (int(circle_x), int(circle_y)), 
                                 int(charge_radius), 3)
                
                # Círculo interno semi-transparente (se necessário, pode usar uma surface temporária)
                inner_radius = max(0, int(charge_radius - 10))
                if inner_radius > 0:
                    pygame.draw.circle(surface, (255, 255, 0), 
                                     (int(circle_x), int(circle_y)), 
                                     inner_radius, 1)

        # Charging particles
        if self.state in ("charging", "converging", "preparing_to_fire"):
            self._draw_particles(surface, offset_x, offset_y)

        # Efeito visual de "prestes a disparar" durante o delay
        if self.state in ("preparing_to_fire"):
            self._draw_firing_warning(surface, offset_x, offset_y)

        # Circle disappear particles
        self._draw_circle_disappear_particles(surface, offset_x, offset_y)

    def _draw_particles(self, surface: pygame.Surface, offset_x: float, offset_y: float) -> None:
        """Draw charging particles."""
        for p in self.charging_particles:
            pygame.draw.circle(surface, p['color'], 
                             (int(p['pos'][0] + offset_x), int(p['pos'][1] + offset_y)), 
                             int(p['size']))

    def _draw_firing_warning(self, surface: pygame.Surface, offset_x: float, offset_y: float) -> None:
        """Draw blinking warning before firing."""
        face_x, face_y = self._get_face_position()
        if (pygame.time.get_ticks() % 200) < 100:  # Piscar a cada 200ms
            pygame.draw.circle(surface, (255, 255, 255), 
                             (int(face_x + offset_x), int(face_y + offset_y)), 12, 3)

    def _draw_circle_disappear_particles(self, surface: pygame.Surface, offset_x: float, offset_y: float) -> None:
        """Draw circle disappearing particles."""
        for p in self.circle_disappear_particles:
            pygame.draw.circle(surface, p['color'], 
                             (int(p['pos'][0] + offset_x), int(p['pos'][1] + offset_y)), 
                             max(1, int(p['size'])))

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        """Draw boss health bar."""
        if self.health > 0:
            health_ratio = self.health / self.max_health
            bar_width = self.w * health_ratio
            pygame.draw.rect(surface, (255, 0, 0), (self.x, self.y - 20, self.w, 10))
            pygame.draw.rect(surface, (0, 255, 0), (self.x, self.y - 20, bar_width, 10))

    def can_take_damage(self) -> bool:
        """Check if boss can currently take damage."""
        if self.state == "entering":
            return False
        return not self.dead

    def get_rect(self) -> pygame.Rect:
        """Get the boss collision rectangle."""
        if not self.can_take_damage():
            # Return an empty rect if boss can't take damage
            return pygame.Rect(-1000, -1000, 0, 0)
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, amount: int) -> None:
        """Apply damage and handle frenzy mode transition."""
        if not self.can_take_damage():
            return
            
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.dead = True
        
        # Transition to frenzy mode
        if not self.frenzy_mode and self.health <= self.max_health * Config.BOSS_FRENZY_THRESHOLD:
            self.frenzy_mode = True
            self.speed *= Config.BOSS_FRENZY_SPEED_MULTIPLIER
            self.attack_timer.duration = random.uniform(*Config.BOSS_FRENZY_ATTACK_INTERVAL)
            self.fire_timer.duration = Config.BOSS_FRENZY_LASER_LIFETIME
            self.frenzy_shake_timer = Config.BOSS_FRENZY_SHAKE_DURATION

    def is_off_screen(self) -> bool:
        """Check if boss is completely off screen."""
        return self.y > Config.SCREEN_HEIGHT

    def get_explosion_duration(self) -> float:
        """Return the explosion duration for this boss."""
        return Config.BOSS_EXPLOSION_DURATION