import math
import random
from typing import List, Any

import pygame

from ..core import colors
from ..core.config import Config
from ..core.time import Timer
from .boss_laser import BossLaser
from .boss_cannon import BossCannon, BossAttackSystem
from .boss_particles import BossParticleSystem
from .meteor import Meteor


class Boss:
    """
    Boss entity with face-oriented combat system.

    Features:
    - Face orientation system that tracks the player
    - State machine for complex behavior patterns
    - Particle effects for charging and firing
    - Delayed laser firing for better gameplay
    - Frenzy mode with enhanced attacks
    """

    # Use constants from BossAttackSystem
    FRENZY_LASER_ANGLES = BossAttackSystem.FRENZY_LASER_ANGLES
    LASER_DISTANCE = BossAttackSystem.LASER_DISTANCE
    FACE_DISTANCE_RATIO: float = 0.5  # Face distance from center as ratio of size
    MAX_CHARGE_RADIUS: float = 15.0  # Maximum charging circle radius
    LASER_SPREAD_OFFSET: int = 10  # Offset between frenzy lasers
    FACE_INDICATOR_SIZE: int = 8  # Size of face indicator rectangle
    FACE_DIRECTION_LINE_LENGTH: int = 15  # Length of face direction indicator

    def __init__(
            self,
            x: float,
            y: float,
            health: int = Config.BOSS_HEALTH,
            hit_score: int = 50):
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
        self.speed = Config.BOSS_NORMAL_SPEED
        self.direction = 1
        self.entry_speed = Config.BOSS_ENTRY_SPEED

        # State machine
        self.state = "entering"
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0
        self.meteor_attack_timer = Timer(random.uniform(3.0, 5.0))
        self.can_spawn_meteors = False

        # Attack system
        self._init_attack_system()

        # Manual charge progress tracking
        self.charge_progress = 0.0

        # Visual effects - using new systems
        self.particle_system = BossParticleSystem()
        self.fired_lasers: List[BossLaser] = []

        # Orientation system - face always facing player
        self.rotation_angle = 0.0  # Ângulo de rotação em radianos
        self.facing_direction = pygame.Vector2(
            0, 1
        )  # Direção que a face principal está voltada
        self.face_center = pygame.Vector2(0, 0)  # Centro da face principal

        # Cannon position (fixed at the top center of the boss)
        self.cannon_x = self.x + self.w / 2
        self.cannon_y = self.y  # Canhão sempre no topo
        self.cannon_rotation = 0.0  # Ângulo de rotação do canhão

        # Laser delay system for better player reaction time
        self.laser_delay_timer = 0.0
        self.laser_delay_duration = Config.BOSS_LASER_DELAY
        self.pending_laser_data: dict[str, Any] | None = (
            None  # Dados do laser que será disparado após o delay
        )

        # Substituir sistema de canhão antigo pelo novo
        self.cannon = BossCannon()

    def _update_orientation(self, player_x: float, player_y: float) -> None:
        """Update cannon orientation to face the player."""
        # Atualizar posição do canhão
        self.cannon.update_position(self.x, self.y, self.w, self.h)

        # Fazer o canhão mirar no jogador
        self.cannon.aim_at(player_x, player_y)

        # Atualizar face_center e facing_direction para manter compatibilidade
        self.face_center.x, self.face_center.y = self.cannon.get_position()
        self.facing_direction = self.cannon.get_direction()

    def _get_face_position(self) -> tuple[float, float]:
        """Get the position of the main face (facing the player)."""
        return (self.face_center.x, self.face_center.y)

    def _get_face_normal(self) -> pygame.Vector2:
        """Get the normal vector of the main face (pointing towards player)."""
        return self.facing_direction.copy()

    def _init_attack_system(self) -> None:
        """Initialize attack timing and states."""
        self.attack_timer = Timer(
            random.uniform(
                *Config.BOSS_CALM_ATTACK_INTERVAL))
        self.charge_duration = Config.BOSS_CHARGE_DURATION
        self.charge_timer = Timer(self.charge_duration)
        self.fire_duration = Config.BOSS_LASER_LIFETIME
        self.fire_timer = Timer(self.fire_duration)

    def _get_charge_duration(self) -> float:
        """Get charge duration based on frenzy mode."""
        return (
            Config.BOSS_FRENZY_CHARGE_DURATION 
            if self.frenzy_mode 
            else Config.BOSS_CHARGE_DURATION
        )

    def _get_laser_delay(self) -> float:
        """Get laser delay based on frenzy mode."""
        return (
            Config.BOSS_FRENZY_LASER_DELAY 
            if self.frenzy_mode 
            else Config.BOSS_LASER_DELAY
        )

    def _get_aim_blink_interval(self) -> int:
        """Get aim blink interval based on frenzy mode."""
        return (
            Config.BOSS_FRENZY_AIM_BLINK_INTERVAL 
            if self.frenzy_mode 
            else Config.BOSS_AIM_BLINK_INTERVAL
        )

    def _get_aim_blink_duration(self) -> int:
        """Get aim blink duration based on frenzy mode."""
        return (
            Config.BOSS_FRENZY_AIM_BLINK_ON_DURATION 
            if self.frenzy_mode 
            else Config.BOSS_AIM_BLINK_ON_DURATION
        )

    def _get_animation_speed_multiplier(self) -> float:
        """Get animation speed multiplier based on frenzy mode."""
        return (
            Config.BOSS_FRENZY_ANIMATION_SPEED_MULTIPLIER 
            if self.frenzy_mode 
            else Config.BOSS_ANIMATION_SPEED_MULTIPLIER
        )

    def _get_accelerated_dt(self, dt: float) -> float:
        """Get delta time accelerated by animation speed multiplier."""
        return dt * self._get_animation_speed_multiplier()

    def _update_frenzy_timings(self) -> None:
        """Update all timing values when entering frenzy mode."""
        # Atualizar duração do carregamento
        self.charge_duration = self._get_charge_duration()
        self.charge_timer.duration = self.charge_duration
        
        # Atualizar delay do laser
        self.laser_delay_duration = self._get_laser_delay()

    def _update_charging_particles(self, dt: float) -> None:
        """Update particle convergence animation."""
        face_x, face_y = self._get_face_position()
        # Usar delta time acelerado para animações mais rápidas no frenzy
        accelerated_dt = self._get_accelerated_dt(dt)
        self.particle_system.update_charging_particles(accelerated_dt, face_x, face_y)

    def _generate_charging_particles(self) -> None:
        """Generate new charging particles."""
        face_x, face_y = self._get_face_position()
        self.particle_system.generate_charging_particles(face_x, face_y)

    def _create_lasers(self) -> List[BossLaser]:
        """Create laser objects based on current mode."""
        face_x, face_y = self._get_face_position()
        laser_lifetime = (
            Config.BOSS_FRENZY_LASER_LIFETIME
            if self.frenzy_mode
            else Config.BOSS_LASER_LIFETIME
        )

        if self.frenzy_mode:
            return self._create_frenzy_lasers(face_x, face_y, laser_lifetime)
        else:
            return self._create_normal_laser(face_x, face_y, laser_lifetime)

    def _create_laser_pattern(
        self,
        face_x: float,
        face_y: float,
        lifetime: float,
        is_frenzy: bool,
        face_normal: pygame.Vector2 | None = None,
    ) -> List[BossLaser]:
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
                start_x = face_x + offset * \
                    math.cos(self.rotation_angle + math.pi / 2)
                start_y = face_y + offset * \
                    math.sin(self.rotation_angle + math.pi / 2)

                target_x = start_x + rotated_x * self.LASER_DISTANCE
                target_y = start_y + rotated_y * self.LASER_DISTANCE

                laser = BossLaser(
                    start_x, start_y, target_x, target_y, lifetime=lifetime
                )
                lasers.append(laser)

            return lasers
        else:
            # Modo calmo: laser único
            target_x = face_x + face_normal.x * self.LASER_DISTANCE
            target_y = face_y + face_normal.y * self.LASER_DISTANCE

            return [
                BossLaser(
                    face_x,
                    face_y,
                    target_x,
                    target_y,
                    lifetime=lifetime)]

    def _create_frenzy_lasers(
        self, face_x: float, face_y: float, lifetime: float
    ) -> List[BossLaser]:
        """Create multiple lasers for frenzy mode."""
        return self._create_laser_pattern(
            face_x, face_y, lifetime, is_frenzy=True)

    def _create_normal_laser(
        self, face_x: float, face_y: float, lifetime: float
    ) -> List[BossLaser]:
        """Create single laser for normal mode."""
        return self._create_laser_pattern(
            face_x, face_y, lifetime, is_frenzy=False)

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

        # Só atualizar timer de ataque e permitir novos ataques se não estiver tremendo
        if self.frenzy_shake_timer <= 0:
            self.attack_timer.update(dt)
            if self.attack_timer.done():
                self.state = "aiming"

    def _update_charging_state(self, dt: float) -> None:
        """Handle charging animation."""
        # Usar delta time acelerado para acelerar toda a animação no frenzy
        accelerated_dt = self._get_accelerated_dt(dt)
        
        self.charge_timer.update(dt)  # Timer mantém velocidade normal para consistência
        # Update manual progress tracking com velocidade acelerada
        self.charge_progress = min(
            1.0, self.charge_progress + accelerated_dt / self.charge_duration
        )

        self._generate_charging_particles()
        self._update_charging_particles(dt)  # Já usa accelerated_dt internamente

        if self.charge_timer.done():
            self.state = "converging"

    def _get_charge_circle_radius(self) -> float:
        """Calculate the charging circle radius based on charge progress."""
        if self.state not in ("charging", "converging"):
            return 0.0

        # During charging, grows from 0 to max radius
        if self.state == "charging":
            return self.charge_progress * Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS

        # During converging, maintains max radius
        return Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS

    def _create_circle_disappear_particles(self) -> None:
        """Create small particles when the charging circle disappears."""
        face_x, face_y = self._get_face_position()
        radius = self._get_charge_circle_radius()
        self.particle_system.create_circle_disappear_particles(face_x, face_y, radius)

    def _update_circle_disappear_particles(self, dt: float) -> None:
        """Update the circle disappear particles."""
        # Usar delta time acelerado para partículas de desaparecimento mais rápidas
        accelerated_dt = self._get_accelerated_dt(dt)
        self.particle_system.update_circle_disappear_particles(accelerated_dt)

    def _update_converging_state(self, dt: float) -> List[BossLaser]:
        """Handle particle convergence and preparation for laser firing."""
        self._update_charging_particles(dt)

        if not self.particle_system.charging_particles:
            # Criar partículas de desaparecimento do círculo
            if not self.particle_system.circle_disappear_particles:  # Só criar uma vez
                self._create_circle_disappear_particles()

            # Preparar dados do laser para disparo atrasado
            self.pending_laser_data = self._prepare_laser_data()
            self.state = "preparing_to_fire"
            # Usar delay dinâmico baseado no modo frenzy
            self.laser_delay_timer = self._get_laser_delay()

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
        laser_lifetime = (
            Config.BOSS_FRENZY_LASER_LIFETIME
            if self.frenzy_mode
            else Config.BOSS_LASER_LIFETIME
        )

        return {
            "face_x": face_x,
            "face_y": face_y,
            "face_normal": face_normal.copy(),  # Captured direction for consistent aiming
            "lifetime": laser_lifetime,
            "frenzy_mode": self.frenzy_mode,
        }

    def _update_preparing_to_fire_state(self, dt: float) -> List[BossLaser]:
        """Handle the delay before firing lasers."""
        self.laser_delay_timer -= dt
        
        # Continuar atualizando partículas de desaparecimento durante o delay
        self._update_circle_disappear_particles(dt)

        if self.laser_delay_timer <= 0 and self.pending_laser_data:
            # Disparar o laser usando os dados preparados
            new_lasers = self._create_lasers_from_data(self.pending_laser_data)

            self.fired_lasers.extend(new_lasers)
            self.fire_timer = Timer(self.pending_laser_data["lifetime"])
            self.fire_timer.start()

            self.state = "firing"
            self.pending_laser_data = None

            return new_lasers

        return []

    def _create_lasers_from_data(
            self, laser_data: dict[str, Any]) -> List[BossLaser]:
        """Create lasers from prepared data."""
        return self._create_laser_pattern(
            laser_data["face_x"],
            laser_data["face_y"],
            laser_data["lifetime"],
            laser_data["frenzy_mode"],
            laser_data[
                "face_normal"
            ],  # Use the saved direction from when the attack started
        )

    def _update_firing_state(self, dt: float) -> None:
        """Handle laser firing and cleanup."""
        self.fire_timer.update(dt)

        for laser in self.fired_lasers[:]:
            laser.update(dt)
            if laser.dead:
                self.fired_lasers.remove(laser)

        if self.fire_timer.done() and all(
            l.is_animation_finished() for l in self.fired_lasers
        ):
            self.state = "active"
            self._reset_attack_timer()
            self.fired_lasers.clear()

    def _reset_attack_timer(self) -> None:
        """Reset attack timer based on current mode."""
        if self.frenzy_mode:
            self.attack_timer = Timer(
                random.uniform(*Config.BOSS_FRENZY_ATTACK_INTERVAL)
            )
        else:
            self.attack_timer = Timer(
                random.uniform(
                    *Config.BOSS_CALM_ATTACK_INTERVAL))
        self.attack_timer.start()



    def update(
        self, dt: float, player_x: float, player_y: float | None = None
    ) -> tuple[List[BossLaser], List["Meteor"]]:
        """Main update method - state machine."""
        spawned_meteors: List["Meteor"] = []
        lasers_fired: List[BossLaser] = []
        self.frenzy_shake_timer = max(0.0, self.frenzy_shake_timer - dt)

        # Store player position for drawing
        self.player_x = player_x
        self.player_y = player_y

        # Update orientation to face player
        if player_y is not None:
            self._update_orientation(player_x, player_y)

        # Atualiza o timer de spawn de meteoros e spawna se estiver em modo frenético
        # METEOROS SÃO CRIADOS QUANDO O BOSS NÃO ESTÁ ATACANDO (LASER)
        if (self.frenzy_mode and self.frenzy_shake_timer <= 0 and 
            self.state in ("active", "aiming") and  # Só quando não está atacando com laser
            not self.pending_laser_data):  # E não tem laser pendente
            
            self.meteor_attack_timer.update(dt)
            if self.meteor_attack_timer.done() and player_y is not None:
                # Spawn meteoros dos lados em movimento de arco
                side_meteors = BossAttackSystem.spawn_side_meteors(
                    self.x, self.y, self.w, self.h, player_x, player_y
                )
                spawned_meteors.extend(side_meteors)
                
                # Ocasionalmente, spawn um meteoro adicional do centro
                if random.random() < 0.4:  # 40% de chance
                    target_x = player_x + random.uniform(-30, 30)
                    target_y = player_y + random.uniform(-20, 20)
                    center_meteor = BossAttackSystem.spawn_aimed_meteor(
                        self.x, self.y, self.w, self.h, target_x, target_y
                    )
                    spawned_meteors.append(center_meteor)
                
                # No modo frenzy, spawnar meteoros guiados ocasionalmente
                if random.random() < Config.GUIDED_METEOR_SPAWN_CHANCE:
                    guided_meteor = BossAttackSystem.spawn_guided_meteor(
                        self.x, self.y, self.w, self.h, player_x, player_y
                    )
                    spawned_meteors.append(guided_meteor)
                
                # Timer mais curto para meteoros mais frequentes quando não atacando
                self.meteor_attack_timer.start(random.uniform(1.5, 2.5))

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
            # Atualizar duração do carregamento baseada no modo frenzy
            self.charge_duration = self._get_charge_duration()
            self.charge_timer.duration = self.charge_duration
            self.charge_timer.start()
            self.charge_progress = 0.0 # Reset progress
            self.particle_system.clear_all()
        elif self.state == "charging":
            self._update_charging_state(dt)
        elif self.state == "converging":
            lasers_fired = self._update_converging_state(dt)
        elif self.state == "preparing_to_fire":
            lasers_fired = self._update_preparing_to_fire_state(dt)
        elif self.state == "firing":
            self._update_firing_state(dt)

        return (lasers_fired, spawned_meteors)

    def _draw_aiming_line(self, surface: pygame.Surface) -> None:
        """Draw the animated aiming line."""
        if (
            pygame.time.get_ticks() % self._get_aim_blink_interval()
        ) < self._get_aim_blink_duration():
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
                    actual_end_distance = min(
                        self.LASER_DISTANCE, end_distance)

                    # Calcular posições reais da linha
                    start_line_x = face_x + face_normal.x * actual_start_distance
                    start_line_y = face_y + face_normal.y * actual_start_distance
                    end_line_x = face_x + face_normal.x * actual_end_distance
                    end_line_y = face_y + face_normal.y * actual_end_distance

                    pygame.draw.line(
                        surface,
                        colors.BOSS_AIM_LINE,
                        (start_line_x, start_line_y),
                        (end_line_x, end_line_y),
                        2,
                    )

                current_distance += (
                    Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
                )

    def _draw_cannon(self, surface: pygame.Surface, offset_x: float, offset_y: float) -> None:
        """Draw the boss's cannon."""
        if self.state != "entering":
            # Desenhar base do canhão (círculo)
            pygame.draw.circle(
                surface,
                (200, 200, 200),
                (int(self.cannon_x + offset_x), int(self.cannon_y + offset_y)),
                10
            )
            
            # Desenhar cano do canhão (linha na direção do alvo)
            cannon_length = 20
            end_x = self.cannon_x + math.cos(self.cannon_rotation) * cannon_length
            end_y = self.cannon_y + math.sin(self.cannon_rotation) * cannon_length
            
            pygame.draw.line(
                surface,
                (200, 200, 200),
                (int(self.cannon_x + offset_x), int(self.cannon_y + offset_y)),
                (int(end_x + offset_x), int(end_y + offset_y)),
                4
            )

    def draw(self, surface: pygame.Surface) -> None:
        """Render the boss and its effects."""
        offset_x, offset_y = 0, 0
        if self.frenzy_shake_timer > 0:
            offset_x = random.randint(-3, 3)
            offset_y = random.randint(-3, 3)

        # Normal boss rendering (corpo vermelho)
        pygame.draw.rect(surface, (255, 0, 0), (self.x + offset_x, self.y + offset_y, self.w, self.h))

        # Desenhar o canhão usando a nova classe
        self.cannon.draw(surface, offset_x, offset_y)

        # Desenhar indicação da face principal (pequeno retângulo na direção do
        # jogador)
        if hasattr(self, "face_center") and self.state != "entering":
            face_x, face_y = self._get_face_position()
            face_normal = self._get_face_normal()

            # Pequeno retângulo indicando a face principal
            face_rect_x = face_x + offset_x - self.FACE_INDICATOR_SIZE // 2
            face_rect_y = face_y + offset_y - self.FACE_INDICATOR_SIZE // 2
            pygame.draw.rect(
                surface,
                (255, 255, 255),
                (
                    int(face_rect_x),
                    int(face_rect_y),
                    self.FACE_INDICATOR_SIZE,
                    self.FACE_INDICATOR_SIZE,
                ),
            )

            # Linha pequena indicando direção
            line_end_x = (
                face_x +
                face_normal.x *
                self.FACE_DIRECTION_LINE_LENGTH +
                offset_x)
            line_end_y = (
                face_y +
                face_normal.y *
                self.FACE_DIRECTION_LINE_LENGTH +
                offset_y)
            pygame.draw.line(
                surface,
                (255, 255, 255),
                (face_x + offset_x, face_y + offset_y),
                (int(line_end_x), int(line_end_y)),
                2,
            )

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
                pygame.draw.circle(
                    surface,
                    (255, 255, 100),
                    (int(circle_x), int(circle_y)),
                    int(charge_radius),
                    4,  # Aumentar espessura da borda
                )

                # Círculo interno
                inner_radius = max(0, int(charge_radius - 8))
                if inner_radius > 0:
                    pygame.draw.circle(
                        surface,
                        (255, 255, 0),
                        (int(circle_x), int(circle_y)),
                        inner_radius,
                        2,  # Aumentar espessura do círculo interno
                    )

        # Charging particles
        if self.state in ("charging", "converging", "preparing_to_fire"):
            self._draw_particles(surface, offset_x, offset_y)

        # Efeito visual de "prestes a disparar" durante o delay
        if self.state in ("preparing_to_fire"):
            self._draw_firing_warning(surface, offset_x, offset_y)

        # Circle disappear particles
        self._draw_circle_disappear_particles(surface, offset_x, offset_y)

    def _draw_particles(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Draw charging particles."""
        self.particle_system.draw_particles(surface, offset_x, offset_y)

    def _draw_firing_warning(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Draw blinking warning before firing."""
        face_x, face_y = self._get_face_position()
        if (pygame.time.get_ticks() % 200) < 100:  # Piscar a cada 200ms
            pygame.draw.circle(
                surface,
                (255, 255, 255),
                (int(face_x + offset_x), int(face_y + offset_y)),
                12,
                3,
            )

    def _draw_circle_disappear_particles(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Draw circle disappearing particles."""
        self.particle_system.draw_circle_disappear_particles(surface, offset_x, offset_y)

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        """Draw boss health bar."""
        if self.health > 0:
            health_ratio = self.health / self.max_health
            bar_width = self.w * health_ratio
            pygame.draw.rect(
                surface, (255, 0, 0), (self.x, self.y - 20, self.w, 10))
            pygame.draw.rect(
                surface, (0, 255, 0), (self.x, self.y - 20, bar_width, 10))

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
        if (
            not self.frenzy_mode
            and self.health <= self.max_health * Config.BOSS_FRENZY_THRESHOLD
        ):
            # Entrar em modo frenético e interromper qualquer ataque em andamento
            self.frenzy_mode = True
            self.speed = Config.BOSS_FRENZY_SPEED
            self.frenzy_shake_timer = Config.BOSS_FRENZY_SHAKE_DURATION
            
            # Atualizar todos os timings para o modo frenzy
            self._update_frenzy_timings()
            
            # Interromper qualquer ataque em andamento
            self.state = "active"
            self.fired_lasers.clear()
            self.particle_system.clear_all()
            
            # Resetar timers de ataque para começar após o tremor
            self.attack_timer = Timer(Config.BOSS_FRENZY_SHAKE_DURATION + random.uniform(
                *Config.BOSS_FRENZY_ATTACK_INTERVAL
            ))
            self.fire_timer.duration = Config.BOSS_FRENZY_LASER_LIFETIME
            self.attack_timer.start()

    def is_off_screen(self) -> bool:
        """Check if boss is completely off screen."""
        return self.y > Config.SCREEN_HEIGHT

    def get_explosion_duration(self) -> float:
        """Return the explosion duration for this boss."""
        return Config.BOSS_EXPLOSION_DURATION
        return Config.BOSS_EXPLOSION_DURATION
