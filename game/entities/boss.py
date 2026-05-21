import logging
import math
import random
from collections import deque
from typing import Any, List, Literal

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.time import Timer
from .boss_cannon import BossCannon
from .boss_hit_mixin import BossHitMixin
from .boss_laser import BossLaser
from .boss_particles import BossParticleSystem
from .boss_square import BossSquare
from .boss_state import BossState
from .draw_utils import rotated_square_corners

# Sound events emitted by Boss.update() — executed by EntityManager
BossSoundEvent = Literal[
    "play_charging",
    "stop_charging",
    "play_fire",
    "stop_fire",
]


class Boss(BossHitMixin):
    """
    Boss entity with face-oriented combat system.

    Features:
    - Face orientation system that tracks the player
    - State machine for complex behavior patterns
    - Particle effects for charging and firing
    - Delayed laser firing for better gameplay
    - Frenzy mode with enhanced attacks
    """

    # Attack constants (boss-specific values)
    FRENZY_LASER_ANGLES: List[float] = [-0.349, 0, 0.349]  # 20 degrees in radians
    LASER_DISTANCE: int = 2000  # Maximum laser reach (visual, boss-specific)
    FACE_DISTANCE_RATIO: float = 0.5  # Face distance from center as ratio of size
    MAX_CHARGE_RADIUS: float = 15.0  # Maximum charging circle radius
    LASER_SPREAD_OFFSET: int = 10  # Offset between frenzy lasers
    FACE_INDICATOR_SIZE: int = 8  # Size of face indicator rectangle
    FACE_DIRECTION_LINE_LENGTH: int = 15  # Length of face direction indicator

    def __init__(
        self, x: float, y: float, health: int = Config.BOSS_HEALTH, hit_score: int = 50
    ):
        # Position and size
        self.w = 150  # 100 * 1.5
        self.h = 120  # 80 * 1.5
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
        self.player_x: float = 0.0
        self.player_y: float | None = None

        # State machine
        self.state = BossState.ENTERING
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0
        self._shake_offset_x: int = 0
        self._shake_offset_y: int = 0
        self._frenzy_square_green: int = 0
        self.pending_frenzy = (
            False  # Flag para ativar frenzy quando action atual acabar
        )
        self.square_attack_timer = Timer(random.uniform(2.0, 3.5))
        self.can_spawn_meteors = False

        # Attack system
        self.attack_timer: Timer
        self.charge_duration: float
        self.charge_timer: Timer
        self.fire_duration: float
        self.fire_timer: Timer
        self._init_attack_system()

        # Manual charge progress tracking
        self.charge_progress = 0.0

        # Aiming line animation
        self.aim_anim_offset: float = 0.0
        self.aim_anim_base_speed: float = 50.0  # Velocidade base da animação
        self.aim_anim_charge_speed: float = 500.0  # Velocidade máxima durante charging

        # Visual effects - using new systems
        self.particle_system = BossParticleSystem()
        self.fired_lasers: List[BossLaser] = []

        # Orientation system - face always facing player
        self.rotation_angle = 0.0  # Ângulo de rotação em radianos
        self.facing_direction = pygame.Vector2(
            0, 1
        )  # Direção que a face principal está voltada
        self.face_center = pygame.Vector2(0, 0)  # Centro da face principal

        # Laser delay system for better player reaction time
        self.laser_delay_timer = 0.0
        self.laser_delay_duration = Config.BOSS_LASER_DELAY
        self.pending_laser_data: dict[str, Any] | None = (
            None  # Dados do laser que será disparado após o delay
        )

        # Substituir sistema de canhão antigo pelo novo
        self.cannon = BossCannon()

        # Sistema de quadrados flutuantes (seguem o boss com delay)
        self.position_history: deque[tuple[float, float]] = deque(
            maxlen=30
        )  # Histórico de posições
        self.floating_squares: List[BossSquare] = []
        self._init_floating_squares()

        # Animação de pulsação para os quadrados flutuantes
        self.squares_animation_timer = 0.0

        # Sistema de lançamento sequencial de quadrados
        self.square_launch_queue: List[
            BossSquare
        ] = []  # Fila de quadrados prontos para lançar
        self.square_launch_timer = 0.0  # Timer para lançamento sequencial
        self.square_launch_delay = 0.15  # 150ms entre cada lançamento

        # Animação da borda pixelada
        self.border_anim_offset: float = 0.0
        self.border_anim_speed: float = 30.0  # Pixels por segundo

    def _init_floating_squares(self) -> None:
        """Inicializa os quadrados flutuantes orbitando ao redor do boss."""
        # Criar 14 quadrados em órbitas ao redor do boss
        num_squares = 14

        # Calcular posição inicial do boss (centro)
        boss_center_x = self.x + self.w / 2
        boss_center_y = self.y + self.h / 2

        for _ in range(num_squares):
            # Distância orbital aleatória (raio da órbita)
            orbit_radius = random.uniform(60, 120)

            # Ângulo inicial aleatório (posição na órbita)
            orbit_angle = random.uniform(0, 360)

            # Velocidade angular aleatória (velocidade de rotação)
            # Positivo = sentido horário, negativo = anti-horário
            orbit_speed = random.choice(
                [
                    random.uniform(30, 60),  # Horário rápido
                    random.uniform(15, 30),  # Horário lento
                    random.uniform(-60, -30),  # Anti-horário rápido
                    random.uniform(-30, -15),  # Anti-horário lento
                ]
            )

            # Tamanho aleatório
            size = random.uniform(14, 25)

            # Calcular posição inicial na órbita (para evitar bug visual)
            angle_rad = math.radians(orbit_angle)
            initial_x = boss_center_x + math.cos(angle_rad) * orbit_radius
            initial_y = boss_center_y + math.sin(angle_rad) * orbit_radius

            # Criar BossSquare orbital com posição inicial correta
            square = BossSquare(
                x=initial_x,
                y=initial_y,
                vx=0,
                vy=0,
                size=size,
                is_orbital=True,
                orbit_radius=orbit_radius,
                orbit_angle=orbit_angle,
                orbit_speed=orbit_speed,
                speed_var=random.uniform(0.85, 1.18),
            )

            self.floating_squares.append(square)

    def _update_orientation(self, player_x: float, player_y: float) -> None:
        """Update cannon orientation to face the player."""
        # Atualizar posição do canhão
        self.cannon.update_position(self.x, self.y, self.w, self.h)

        # Fazer o canhão mirar no jogador
        self.cannon.aim_at(player_x, player_y)

        # Atualizar face_center para usar a ponta do cano (onde o laser sai)
        self.face_center.x, self.face_center.y = self.cannon.get_barrel_tip_position()
        self.facing_direction = self.cannon.get_direction()

    def _get_face_position(self) -> tuple[float, float]:
        """Get the position of the cannon barrel tip (where the laser fires from)."""
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

    def _is_in_attack_sequence(self) -> bool:
        """Check if boss is currently in an attack sequence that shouldn't be interrupted."""
        # Estados que representam uma sequência de ataque em andamento
        return self.state in (
            BossState.AIMING,
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
            BossState.FIRING,
        )

    def _can_activate_frenzy_now(self) -> bool:
        """Check if frenzy mode can be activated immediately."""
        # Só pode ativar frenzy se não estiver em uma sequência de ataque
        return not self._is_in_attack_sequence()

    def _activate_frenzy_mode(self) -> None:
        """Activate frenzy mode immediately."""
        self.frenzy_mode = True
        self.pending_frenzy = False
        self.speed = Config.BOSS_FRENZY_SPEED
        self.frenzy_shake_timer = Config.BOSS_FRENZY_SHAKE_DURATION

        # Acelerar órbita dos quadrados em modo frenzy
        for square in self.floating_squares:
            square.set_frenzy_mode(True)

        # Atualizar todos os timings para o modo frenzy
        self._update_frenzy_timings()

        # Limpar ataques apenas se estiver em estado ativo
        if self.state == BossState.ACTIVE:
            # Se está em estado ativo, pode resetar normalmente
            self.fired_lasers.clear()
            # Parar sons do boss laser
            self._sound_events.append("stop_charging")
            self._sound_events.append("stop_fire")
            self.particle_system.clear_all()

            # Resetar timers de ataque para começar após o tremor
            self.attack_timer = Timer(
                Config.BOSS_FRENZY_SHAKE_DURATION
                + random.uniform(*Config.BOSS_FRENZY_ATTACK_INTERVAL)
            )
            self.attack_timer.start()
        else:
            # Se não está ativo, apenas ajustar para quando voltar a ficar ativo
            # O timer será resetado quando a ação atual terminar
            pass

        self.fire_timer.duration = Config.BOSS_FRENZY_LASER_LIFETIME

        logging.info("💀 Boss entrou em modo FRENZY!")

    def _check_pending_frenzy(self) -> None:
        """Check if there's a pending frenzy activation and activate if possible."""
        if self.pending_frenzy and self._can_activate_frenzy_now():
            self._activate_frenzy_mode()

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
        return self._create_laser_pattern(
            face_x, face_y, laser_lifetime, self.frenzy_mode
        )

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

            # Criar na ordem: direita, esquerda, centro (centro por último para desenhar por cima)
            laser_order = [2, 0, 1]  # direita, esquerda, centro

            for i in laser_order:
                angle_offset = self.FRENZY_LASER_ANGLES[i]
                cos_offset = math.cos(angle_offset)
                sin_offset = math.sin(angle_offset)

                rotated_x = face_normal.x * cos_offset - face_normal.y * sin_offset
                rotated_y = face_normal.x * sin_offset + face_normal.y * cos_offset

                # Laser sai da ponta do canhão (face_x, face_y já é a ponta)
                start_x = face_x
                start_y = face_y

                target_x = start_x + rotated_x * self.LASER_DISTANCE
                target_y = start_y + rotated_y * self.LASER_DISTANCE

                laser = BossLaser(
                    start_x, start_y, target_x, target_y, lifetime=lifetime
                )
                lasers.append(laser)

            return lasers

        # Modo calmo: laser único saindo da ponta do canhão
        target_x = face_x + face_normal.x * self.LASER_DISTANCE
        target_y = face_y + face_normal.y * self.LASER_DISTANCE

        return [BossLaser(face_x, face_y, target_x, target_y, lifetime=lifetime)]

    def _enter_charging(self) -> None:
        """Ações executadas ao entrar no estado CHARGING."""
        self._sound_events.append("stop_charging")
        self._sound_events.append("play_charging")
        self.charge_duration = self._get_charge_duration()
        self.charge_timer.duration = self.charge_duration
        self.charge_timer.start()
        self.charge_progress = 0.0
        self.particle_system.clear_all()
        self.state = BossState.CHARGING

    def _update_aiming_state(self) -> None:
        """AIMING é um estado de transição — entra em CHARGING imediatamente."""
        self._enter_charging()

    def _update_entering_state(self, dt: float) -> None:
        """Handle boss entry animation."""
        self.y += self.entry_speed * dt
        if self.y >= self.target_y:
            self.y = self.target_y
            self.state = BossState.ACTIVE
            self.attack_timer.start()

            # Verificar se há frenzy pendente
            self._check_pending_frenzy()

    def _update_active_state(self, dt: float) -> None:
        """Handle boss movement and attack timing."""
        self.x += self.speed * self.direction
        if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
            self.direction *= -1

        # Só atualizar timer de ataque e permitir novos ataques se não estiver tremendo
        if self.frenzy_shake_timer <= 0:
            self.attack_timer.update(dt)
            if self.attack_timer.done():
                self.state = BossState.AIMING

    def _update_charging_state(self, dt: float) -> None:
        """Handle charging animation."""
        # Usar delta time acelerado para acelerar toda a animação no frenzy
        accelerated_dt = self._get_accelerated_dt(dt)

        self.charge_timer.update(dt)  # Timer mantém velocidade normal para consistência
        # Update manual progress tracking com velocidade acelerada
        self.charge_progress = min(
            1.0, self.charge_progress + accelerated_dt / self.charge_duration
        )

        # Atualizar efeito de brilho do canhão
        self.cannon.set_charging(True, self.charge_progress)

        self._generate_charging_particles()
        self._update_charging_particles(dt)  # Já usa accelerated_dt internamente

        if self.charge_timer.done():
            # Parar o som de carregamento quando a animação termina
            self._sound_events.append("stop_charging")
            self.state = BossState.CONVERGING

    def _get_charge_circle_radius(self) -> float:
        """Calculate the charging circle radius based on charge progress."""
        if self.state not in (BossState.CHARGING, BossState.CONVERGING):
            return 0.0

        # During charging, grows from 0 to max radius
        if self.state == BossState.CHARGING:
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

        # Manter brilho máximo durante convergência
        self.cannon.set_charging(True, 1.0)

        if not self.particle_system.charging_particles:
            # Criar partículas de desaparecimento do círculo
            if not self.particle_system.circle_disappear_particles:  # Só criar uma vez
                self._create_circle_disappear_particles()

            # Preparar dados do laser para disparo atrasado
            self.pending_laser_data = self._prepare_laser_data()
            self.state = BossState.PREPARING_TO_FIRE
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

        # Manter brilho máximo durante preparação (piscar)
        blink = (int(self.laser_delay_timer * 10) % 2) == 0
        self.cannon.set_charging(True, 1.0 if blink else 0.7)

        # Continuar atualizando partículas de desaparecimento durante o delay
        self._update_circle_disappear_particles(dt)

        if self.laser_delay_timer <= 0 and self.pending_laser_data:
            # Disparar o laser usando os dados preparados
            new_lasers = self._create_lasers_from_data(self.pending_laser_data)

            # Tocar som de disparo do laser
            self._sound_events.append("play_fire")

            self.fired_lasers.extend(new_lasers)
            self.fire_timer = Timer(self.pending_laser_data["lifetime"])
            self.fire_timer.start()

            self.state = BossState.FIRING
            self.pending_laser_data = None

            return new_lasers

        return []

    def _create_lasers_from_data(self, laser_data: dict[str, Any]) -> List[BossLaser]:
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

        # Desativar efeito de brilho do canhão durante o disparo
        self.cannon.set_charging(False, 0.0)

        for laser in self.fired_lasers:
            laser.update(dt)
        self.fired_lasers = [laser for laser in self.fired_lasers if not laser.dead]
        if not self.fired_lasers:
            self._sound_events.append("stop_fire")

        if self.fire_timer.done() and all(
            laser.is_animation_finished() for laser in self.fired_lasers
        ):
            self.state = BossState.ACTIVE
            self._reset_attack_timer()
            self.fired_lasers.clear()
            # Garantir que o som pare quando limpar todos os lasers
            self._sound_events.append("stop_fire")

            # Verificar se há frenzy pendente
            self._check_pending_frenzy()

    def _reset_attack_timer(self) -> None:
        """Reset attack timer based on current mode."""
        if self.frenzy_mode:
            self.attack_timer = Timer(
                random.uniform(*Config.BOSS_FRENZY_ATTACK_INTERVAL)
            )
        else:
            self.attack_timer = Timer(random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL))
        self.attack_timer.start()

    def _create_square_projectile(
        self, square: BossSquare, player_x: float, player_y: float
    ) -> BossSquare:
        """Cria um projétil a partir de um quadrado flutuante."""
        # Posição inicial do quadrado
        start_x = square.x
        start_y = square.y

        # Calcular direção para o jogador com imprecisão
        dx = player_x - start_x
        dy = player_y - start_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance > 0:
            # Normalizar
            dx /= distance
            dy /= distance

            # Adicionar imprecisão (±30 graus aproximadamente)
            inaccuracy = random.uniform(-0.5, 0.5)
            dx += inaccuracy
            dy += inaccuracy

            # Normalizar novamente
            new_distance = math.sqrt(dx * dx + dy * dy)
            if new_distance > 0:
                dx /= new_distance
                dy /= new_distance
        else:
            dx, dy = 0, 1  # Fallback: para baixo

        # Velocidade do projétil
        speed = 250.0
        vx = dx * speed
        vy = dy * speed

        # Criar projétil
        return BossSquare(start_x, start_y, vx, vy, square.base_size)

    def update(
        self, dt: float, player_x: float, player_y: float | None = None
    ) -> tuple[List[BossLaser], List[BossSquare], List[BossSoundEvent]]:
        """Main update method - state machine."""
        spawned_squares: List[BossSquare] = []
        lasers_fired: List[BossLaser] = []
        self._sound_events: List[BossSoundEvent] = []
        self.frenzy_shake_timer = max(0.0, self.frenzy_shake_timer - dt)

        # Pre-compute shake offset for draw()
        if self.frenzy_shake_timer > 0:
            self._shake_offset_x = random.randint(-3, 3)
            self._shake_offset_y = random.randint(-3, 3)
        else:
            self._shake_offset_x = 0
            self._shake_offset_y = 0

        # Store player position for drawing
        self.player_x = player_x
        self.player_y = player_y

        # Atualizar histórico de posições para os quadrados flutuantes
        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2
        self.position_history.append((center_x, center_y))

        # Atualizar animação de pulsação dos quadrados (mesma lógica do power-up)
        self.squares_animation_timer += dt * 5  # Velocidade da pulsação
        pulse_scale = 1.0 + 0.2 * abs(math.cos(self.squares_animation_timer))

        # Atualizar posições e estados dos quadrados flutuantes
        for square in self.floating_squares:
            if square.state == "orbiting":
                # Atualizar ângulo orbital
                square.orbit_angle += square.orbit_speed * dt

                # Manter ângulo entre 0 e 360
                square.orbit_angle %= 360

                # Calcular posição alvo com base no ângulo orbital
                angle_rad = math.radians(square.orbit_angle)
                target_x = center_x + math.cos(angle_rad) * square.orbit_radius
                target_y = center_y + math.sin(angle_rad) * square.orbit_radius

                # Aplicar lerp para suavizar o movimento (efeito de delay/arrasto)
                lerp_speed = 7.0 * square.speed_var  # Usa velocidade variada
                square.x += (target_x - square.x) * lerp_speed * dt
                square.y += (target_y - square.y) * lerp_speed * dt

                # Aplicar pulsação ao tamanho
                square.size = square.base_size * pulse_scale
                square.rotation = 0.0  # Sem rotação própria

            elif square.state == "preparing":
                # Quadrado está se preparando para ser lançado (girando no lugar)
                square.prepare_timer += dt
                square.rotation += (
                    dt * 720
                )  # Gira 720 graus por segundo (2 rotações/seg)

                # Pulsação mais rápida e intensa durante preparação
                prepare_pulse = 1.0 + 0.4 * abs(math.sin(square.prepare_timer * 10))
                square.size = square.base_size * prepare_pulse

                # Após 1 segundo de preparação, marca como pronto para lançamento
                if square.prepare_timer >= 1.0:
                    square.state = "ready_to_launch"

            elif square.state == "launching":
                # Quadrado está na fila de lançamento, continua girando
                square.prepare_timer += dt
                square.rotation += dt * 720

                # Manter pulsação intensa
                prepare_pulse = 1.0 + 0.4 * abs(math.sin(square.prepare_timer * 10))
                square.size = square.base_size * prepare_pulse

        # Update orientation to face player
        if player_y is not None:
            self._update_orientation(player_x, player_y)

        # Verificar se há frenzy pendente (somente se não está tremendo)
        if self.frenzy_shake_timer <= 0:
            self._check_pending_frenzy()

        # Sistema de lançamento sequencial de quadrados
        if self.frenzy_mode and self.frenzy_shake_timer <= 0 and player_y is not None:
            # Atualizar timer de lançamento sequencial
            if self.square_launch_queue:
                self.square_launch_timer += dt

                # Lançar próximo quadrado da fila quando o timer completar
                if self.square_launch_timer >= self.square_launch_delay:
                    square = self.square_launch_queue.pop(0)
                    projectile = self._create_square_projectile(
                        square, player_x, player_y
                    )
                    spawned_squares.append(projectile)

                    # Resetar quadrado para orbitar o boss novamente
                    square.state = "orbiting"
                    square.prepare_timer = 0.0
                    square.rotation = 0.0

                    # Resetar timer para próximo lançamento
                    self.square_launch_timer = 0.0

            # Adicionar quadrados prontos à fila de lançamento
            ready_squares = [
                sq for sq in self.floating_squares if sq.state == "ready_to_launch"
            ]
            if ready_squares:
                for square in ready_squares:
                    # Marcar como "launching" para não adicionar novamente
                    square.state = "launching"
                    self.square_launch_queue.append(square)

        # Atualiza o timer de ataque de quadrados no modo frenético
        # Timer apenas PREPARA novos quadrados (não lança)
        if (
            self.frenzy_mode
            and self.frenzy_shake_timer <= 0
            and self.state
            in (
                BossState.ACTIVE,
                BossState.AIMING,
            )  # Só quando não está atacando com laser
            and not self.pending_laser_data
            and player_y is not None
        ):  # E não tem laser pendente
            # Timer para selecionar novos quadrados para preparar
            self.square_attack_timer.update(dt)
            if self.square_attack_timer.done():
                # Apenas preparar novos quadrados se não houver nenhum em preparação/pronto/lançando
                preparing_or_ready = [
                    sq
                    for sq in self.floating_squares
                    if sq.state in ("preparing", "ready_to_launch", "launching")
                ]
                if not preparing_or_ready:
                    # Escolher 3-6 quadrados aleatórios para começar a preparar
                    orbiting_squares = [
                        sq for sq in self.floating_squares if sq.state == "orbiting"
                    ]
                    if orbiting_squares:
                        num_to_prepare = random.randint(
                            3, min(6, len(orbiting_squares))
                        )
                        squares_to_prepare = random.sample(
                            orbiting_squares, num_to_prepare
                        )

                        for square in squares_to_prepare:
                            square.state = "preparing"
                            square.prepare_timer = 0.0

                # Timer para próximo ciclo
                self.square_attack_timer.start(random.uniform(2.0, 3.5))

        # Sempre atualizar partículas de desaparecimento do círculo
        self._update_circle_disappear_particles(dt)

        if self.state == BossState.ENTERING:
            self._update_entering_state(dt)
        elif self.state == BossState.ACTIVE:
            self._update_active_state(dt)
        elif self.state == BossState.AIMING:
            self._update_aiming_state()
        elif self.state == BossState.CHARGING:
            self._update_charging_state(dt)
        elif self.state == BossState.CONVERGING:
            lasers_fired = self._update_converging_state(dt)
        elif self.state == BossState.PREPARING_TO_FIRE:
            lasers_fired = self._update_preparing_to_fire_state(dt)
        elif self.state == BossState.FIRING:
            self._update_firing_state(dt)

        # Atualizar animação da linha de mira (acelera gradualmente com o progresso)
        if self.state in (
            BossState.AIMING,
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
        ):
            # Interpolar velocidade baseado no charge_progress
            current_speed = (
                self.aim_anim_base_speed
                + (self.aim_anim_charge_speed - self.aim_anim_base_speed)
                * self.charge_progress
            )
            self.aim_anim_offset += dt * current_speed
        else:
            # Velocidade base quando não está carregando
            self.aim_anim_offset += dt * self.aim_anim_base_speed

        # Atualizar animação da borda pixelada (acelera no frenzy)
        border_speed = self.border_anim_speed * (2.0 if self.frenzy_mode else 1.0)
        self.border_anim_offset += dt * border_speed

        # Pre-compute frenzy square color variation for draw()
        self._frenzy_square_green = random.randint(0, 100) if self.frenzy_mode else 0

        return (lasers_fired, spawned_squares, self._sound_events)

    def _draw_aiming_line(self, surface: pygame.Surface) -> None:
        """Draw the animated aiming line(s)."""
        face_x, face_y = self._get_face_position()
        face_normal = self._get_face_normal()

        # Usar offset animado que acelera com o progresso do carregamento
        total_cycle = Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
        time_based_offset = int(self.aim_anim_offset) % total_cycle

        if self.frenzy_mode:
            # Modo frenzy: desenhar múltiplas linhas de mira
            self._draw_frenzy_aiming_lines(
                surface, face_x, face_y, face_normal, time_based_offset
            )
        else:
            # Modo normal: desenhar linha única
            self._draw_single_aiming_line(
                surface, face_x, face_y, face_normal, time_based_offset
            )

    def _draw_single_aiming_line(
        self,
        surface: pygame.Surface,
        face_x: float,
        face_y: float,
        face_normal: pygame.Vector2,
        time_based_offset: int,
    ) -> None:
        """Draw a single aiming line for normal mode."""
        # Laser sai da base do canhão (face_x, face_y já é a posição correta)
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

                pygame.draw.line(
                    surface,
                    colors.BOSS_AIM_LINE,
                    (start_line_x, start_line_y),
                    (end_line_x, end_line_y),
                    2,
                )

            current_distance += Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH

    def _draw_frenzy_aiming_lines(
        self,
        surface: pygame.Surface,
        face_x: float,
        face_y: float,
        face_normal: pygame.Vector2,
        time_based_offset: int,
    ) -> None:
        """Draw multiple aiming lines for frenzy mode."""

        # Desenhar na ordem: Direita -> Esquerda -> Centro (centro por último para ficar por cima)
        self._draw_single_frenzy_laser_line(
            surface, face_x, face_y, face_normal, time_based_offset, 2
        )  # Direita
        self._draw_single_frenzy_laser_line(
            surface, face_x, face_y, face_normal, time_based_offset, 0
        )  # Esquerda
        self._draw_single_frenzy_laser_line(
            surface, face_x, face_y, face_normal, time_based_offset, 1
        )  # Centro

    def _draw_single_frenzy_laser_line(
        self,
        surface: pygame.Surface,
        face_x: float,
        face_y: float,
        face_normal: pygame.Vector2,
        time_based_offset: int,
        laser_index: int,
    ) -> None:
        """Draw a single laser line for frenzy mode."""
        i = laser_index
        angle_offset = self.FRENZY_LASER_ANGLES[i]

        # Calcular direção rotacionada para este laser
        cos_offset = math.cos(angle_offset)
        sin_offset = math.sin(angle_offset)

        rotated_x = face_normal.x * cos_offset - face_normal.y * sin_offset
        rotated_y = face_normal.x * sin_offset + face_normal.y * cos_offset
        rotated_normal = pygame.Vector2(rotated_x, rotated_y)

        # Laser sai da base do canhão (face_x, face_y já é a posição correta)
        laser_start_x = face_x
        laser_start_y = face_y

        # Cor e espessura diferentes para cada linha
        if i == 1:  # Laser central
            line_color = colors.BOSS_AIM_LINE
            line_width = 4  # Ainda mais grosso para garantir destaque
        else:  # Lasers laterais
            line_color = tuple(
                min(255, max(50, int(c * 0.6))) for c in colors.BOSS_AIM_LINE
            )
            line_width = 2

        # Desenhar linha tracejada para este laser
        current_distance = time_based_offset - (
            Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
        )

        while current_distance < self.LASER_DISTANCE:
            start_distance = current_distance
            end_distance = current_distance + Config.BOSS_AIM_DASH_LENGTH

            if end_distance > 0:
                actual_start_distance = max(0, start_distance)
                actual_end_distance = min(self.LASER_DISTANCE, end_distance)

                # Calcular posições reais da linha
                start_line_x = laser_start_x + rotated_normal.x * actual_start_distance
                start_line_y = laser_start_y + rotated_normal.y * actual_start_distance
                end_line_x = laser_start_x + rotated_normal.x * actual_end_distance
                end_line_y = laser_start_y + rotated_normal.y * actual_end_distance

                pygame.draw.line(
                    surface,
                    line_color,
                    (start_line_x, start_line_y),
                    (end_line_x, end_line_y),
                    line_width,
                )

            current_distance += Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH

    def _draw_floating_squares(
        self, surface: pygame.Surface, offset_x: float, offset_y: float, behind: bool
    ) -> None:
        """Desenha os quadrados flutuantes ao redor do boss."""
        for i, square in enumerate(self.floating_squares):
            # Alternar quais quadrados desenhar na frente ou atrás
            # Quadrados com índice par ficam atrás, ímpares na frente
            if (i % 2 == 0) != behind:
                continue

            # Calcular cor baseada no modo e estado
            if square.state in ("preparing", "launching"):
                # Quadrado se preparando ou na fila de lançamento: cor amarela/laranja pulsante
                pulse_intensity = 0.5 + 0.5 * abs(math.sin(square.prepare_timer * 8))
                color = (255, int(200 * pulse_intensity), 0)
                border_color: tuple[int, int, int] = (255, 255, 0)
            elif self.frenzy_mode:
                # No frenzy, cores mais intensas e variadas
                base_red = 255
                base_green = self._frenzy_square_green
                base_blue = 0
                intensity = 0.7 + (i / len(self.floating_squares)) * 0.3
                color = (
                    int(base_red * intensity),
                    int(base_green * intensity),
                    int(base_blue * intensity),
                )
                r, g, b = color
                border_color = (min(255, r + 50), min(255, g + 50), min(255, b + 50))
            else:
                # Modo normal, vermelho mais escuro
                base_red = 200
                base_green = 0
                base_blue = 0
                intensity = 0.7 + (i / len(self.floating_squares)) * 0.3
                color = (
                    int(base_red * intensity),
                    int(base_green * intensity),
                    int(base_blue * intensity),
                )
                r, g, b = color
                border_color = (min(255, r + 50), min(255, g + 50), min(255, b + 50))

            # Se o quadrado está girando, desenhar com rotação
            if square.rotation > 0:
                self._draw_rotated_square(
                    surface, square, color, border_color, offset_x, offset_y
                )
            else:
                # Desenhar o quadrado normalmente
                square_x = square.x - square.size / 2 + offset_x
                square_y = square.y - square.size / 2 + offset_y

                pygame.draw.rect(
                    surface,
                    color,
                    (int(square_x), int(square_y), square.size, square.size),
                )

                # Desenhar borda mais clara
                pygame.draw.rect(
                    surface,
                    border_color,
                    (int(square_x), int(square_y), square.size, square.size),
                    2,
                )

    def _draw_rotated_square(
        self,
        surface: pygame.Surface,
        square: BossSquare,
        color: tuple[int, int, int],
        border_color: tuple[int, int, int],
        offset_x: float,
        offset_y: float,
    ) -> None:
        """Desenha um quadrado rotacionado."""
        size = square.size
        center_x = square.x + offset_x
        center_y = square.y + offset_y
        angle_rad = math.radians(square.rotation)

        rotated = rotated_square_corners(center_x, center_y, size / 2, angle_rad)
        pygame.draw.polygon(surface, color, rotated)
        pygame.draw.polygon(surface, border_color, rotated, 2)

    def _draw_pixelated_boss(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Desenha o boss com bordas serrilhadas/pixeladas animadas (efeito retro vazado)."""
        x = int(self.x + offset_x)
        y = int(self.y + offset_y)

        # Criar superfície temporária com suporte a transparência
        temp_surface = pygame.Surface((int(self.w), int(self.h)), pygame.SRCALPHA)

        # Corpo principal vermelho (preencher toda a superfície)
        main_red = (255, 0, 0, 255)
        temp_surface.fill(main_red)

        # Criar efeito de borda serrilhada/pixelada TRANSPARENTE (vazado)
        pixel_size = 6
        transparent = (0, 0, 0, 0)  # Completamente transparente

        # Padrão irregular para as bordas (assimétrico)
        pattern = [1, 1, 0, 1, 0, 1, 1, 0, 0, 1]  # Padrão irregular que se repete
        pattern_len = len(pattern)

        # Calcular offset animado (em pixels)
        anim_offset = int(self.border_anim_offset) % (pattern_len * pixel_size)
        anim_idx_offset = anim_offset // pixel_size

        # Borda superior (serrilhada irregular vazada - desliza para a direita)
        for i in range(0, int(self.w), pixel_size):
            idx = ((i // pixel_size) + anim_idx_offset) % pattern_len
            if pattern[idx]:
                pygame.draw.rect(
                    temp_surface, transparent, (i, 0, pixel_size, pixel_size)
                )

        # Borda inferior (serrilhada irregular vazada - desliza para a esquerda)
        for i in range(0, int(self.w), pixel_size):
            idx = ((i // pixel_size) - anim_idx_offset + 3) % pattern_len
            if pattern[idx]:
                pygame.draw.rect(
                    temp_surface,
                    transparent,
                    (i, int(self.h) - pixel_size, pixel_size, pixel_size),
                )

        # Borda esquerda (serrilhada irregular vazada - desliza para baixo)
        for i in range(0, int(self.h), pixel_size):
            idx = ((i // pixel_size) + anim_idx_offset + 1) % pattern_len
            if pattern[idx]:
                pygame.draw.rect(
                    temp_surface, transparent, (0, i, pixel_size, pixel_size)
                )

        # Borda direita (serrilhada irregular vazada - desliza para cima)
        for i in range(0, int(self.h), pixel_size):
            idx = ((i // pixel_size) - anim_idx_offset + 5) % pattern_len
            if pattern[idx]:
                pygame.draw.rect(
                    temp_surface,
                    transparent,
                    (int(self.w) - pixel_size, i, pixel_size, pixel_size),
                )

        # Desenhar a superfície temporária na posição final
        surface.blit(temp_surface, (x, y))

    def draw(self, surface: pygame.Surface) -> None:
        """Render the boss and its effects."""
        offset_x = self._shake_offset_x
        offset_y = self._shake_offset_y

        # Lasers são desenhados pelo entity_manager ANTES do boss

        # Desenhar quadrados flutuantes ATRÁS do corpo principal
        self._draw_floating_squares(surface, offset_x, offset_y, behind=True)

        # Boss rendering com design pixelado
        self._draw_pixelated_boss(surface, offset_x, offset_y)

        # Desenhar quadrados flutuantes NA FRENTE do corpo principal
        self._draw_floating_squares(surface, offset_x, offset_y, behind=False)

        # Desenhar o canhão usando a nova classe
        self.cannon.draw(surface, offset_x, offset_y)

        # Health bar (except during entry)
        if self.state != BossState.ENTERING:
            self._draw_health_bar(surface)

        # Aiming line (desaparece antes do disparo)
        if self.state in (BossState.AIMING, BossState.CHARGING, BossState.CONVERGING):
            self._draw_aiming_line(surface)

        # Charging circle - círculo que cresce durante o carregamento
        if self.state in (
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
        ):
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
        if self.state in (
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
        ):
            self._draw_particles(surface, offset_x, offset_y)

        # Efeito visual de "prestes a disparar" durante o delay
        if self.state == BossState.PREPARING_TO_FIRE:
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
        self.particle_system.draw_circle_disappear_particles(
            surface, offset_x, offset_y
        )

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        """Draw boss health bar."""
        if self.health > 0:
            health_ratio = self.health / self.max_health

            # Largura da barra baseada na vida máxima (proporcional)
            bar_max_width = min(200, self.w * 2)  # Limita a largura máxima
            bar_width = bar_max_width * health_ratio
            bar_height = 10

            # Centralizar a barra em relação ao boss
            bar_x = self.x + (self.w - bar_max_width) / 2
            bar_y = self.y - 20

            # Barra vermelha (fundo)
            pygame.draw.rect(
                surface, (255, 0, 0), (bar_x, bar_y, bar_max_width, bar_height)
            )
            # Barra verde (vida atual)
            pygame.draw.rect(
                surface, (0, 255, 0), (bar_x, bar_y, bar_width, bar_height)
            )

    def can_take_damage(self) -> bool:
        """Check if boss can currently take damage."""
        if self.state == BossState.ENTERING:
            return False
        return not self.dead

    def get_rect(self) -> pygame.Rect:
        """Get the boss collision rectangle."""
        if not self.can_take_damage():
            # Return an empty rect if boss can't take damage
            return pygame.Rect(-1000, -1000, 0, 0)
        return pygame.Rect(self.x, self.y, self.w, self.h)

    @property
    def rect(self) -> pygame.Rect:
        """Pygame-compatible rect property."""
        return self.get_rect()

    def collision_circle(self) -> tuple[float, float, float]:
        if not self.can_take_damage():
            # Off-screen sentinel: chamadores calculam distância e ficam fora
            # de qualquer raio plausível. Coerente com get_rect() vazio.
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

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
            and not self.pending_frenzy
            and self.health <= self.max_health * Config.BOSS_FRENZY_THRESHOLD
        ):
            # Verificar se pode ativar frenzy imediatamente ou precisa aguardar
            if self._can_activate_frenzy_now():
                self._activate_frenzy_mode()
            else:
                # Marcar frenzy como pendente para ativar quando possível
                self.pending_frenzy = True
                logging.warning(
                    "⚠️ Frenzy mode pendente - aguardando fim da ação atual..."
                )

    def is_off_screen(self) -> bool:
        """Check if boss is completely off screen."""
        return self.y > Config.SCREEN_HEIGHT

    def get_explosion_duration(self) -> float:
        """Return the explosion duration for this boss."""
        return Config.BOSS_EXPLOSION_DURATION
