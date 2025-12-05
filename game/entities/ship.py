import pygame
import random
import math
import time
from ..core.config import config as Config
from typing import Tuple, TypedDict, Union, TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


# Constantes para configuração
PARTICLE_ENTRY_COUNT = 3
PARTICLE_THRUSTER_COUNT = 2
PARTICLE_ENTRY_VELOCITY = (-80, 80)
PARTICLE_ENTRY_LIFETIME = (0.2, 0.6)
PARTICLE_ENTRY_SIZE = (1, 3)
PARTICLE_THRUSTER_VELOCITY_X = (-10, 10)
PARTICLE_THRUSTER_VELOCITY_Y = (100, 200)
PARTICLE_THRUSTER_LIFETIME = (0.05, 0.15)
PARTICLE_THRUSTER_SIZE = (2, 4)
ORBITAL_ROTATION_SPEED = 2.0  # radianos/s
ORBITAL_COOLDOWN_MIN = 5.0
ORBITAL_COOLDOWN_MAX = 10.0
ORBITAL_INITIAL_COOLDOWN_MIN = 2.0
ORBITAL_INITIAL_COOLDOWN_MAX = 5.0


class ParticleDict(TypedDict):
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    size: float
    color: Tuple[int, int, int]


class Ship:
    PIXEL_ART_SPRITE = [
        "   W   ",
        "  WWW  ",
        "  WGW  ",
        " WWGWW ",
        "WWWRWWW",
        "  RRR  ",
    ]
    COLOR_MAP: dict[str, Union[Tuple[int, int, int], Tuple[int, int, int, int]]] = {
        "W": (255, 255, 255),  # White
        "G": (150, 150, 150),  # Gray
        "R": (255, 0, 0),  # Red (thruster)
        " ": (0, 0, 0, 0),  # Transparent
    }
    PIXEL_SIZE = 5  # Size of each pixel in the sprite

    def __init__(self, x: float, y: float):
        self.w = len(self.PIXEL_ART_SPRITE[0]) * self.PIXEL_SIZE
        self.h = len(self.PIXEL_ART_SPRITE) * self.PIXEL_SIZE
        self.x = x
        self.y = y
        self.speed = 250
        self.invuln = 0  # ms
        self.lives = Config.INITIAL_LIVES
        self.visible = True
        self.move_vec = pygame.math.Vector2(0, 0)

        # Power-ups
        self.double_shot_timer: float = 0.0
        self.speed_boost_timer: float = 0.0
        self.piercing_shot_timer: float = 0.0
        self.mini_ships_timer: float = 0.0
        self.is_entering = False
        self.entry_particles: list[ParticleDict] = []
        self.thruster_particles: list[ParticleDict] = []

        # Shield system (from upgrades)
        self.shield_timer: float = 0.0
        self.shield_hp: int = 0  # Hits the shield can absorb
        
        # Homing shots system (from upgrades)
        self.homing_shots_active: bool = False
        self.homing_shots_timer: float = 0.0
        self.homing_speed_penalty: float = 1.0
        self.homing_fire_rate_penalty: float = 1.0
        self.original_speed: float = self.speed
        
        # Orbital lasers system (from upgrades)
        self.orbital_lasers_active: bool = False
        self.orbital_angle: float = 0.0  # Ângulo de rotação das bolas
        self.orbital_laser_cooldowns: list[float] = [0.0, 0.0, 0.0]  # Cooldown independente para cada bola
        self.orbital_laser_charges: list[int] = [0, 0, 0]  # Cargas restantes por bolinha
        self.orbital_ball_fade: list[float] = [0.0, 0.0, 0.0]  # Timer de fade para cada bolinha (quando acaba)
        self.orbital_radius: float = 50.0  # Raio da órbita
        self.num_orbital_balls: int = 3  # Número de bolas orbitais
        self.orbital_charges_per_ball: int = 3  # Cargas por bolinha
        
        # Explosive shots system (from upgrades)
        self.explosive_shots_active: bool = False
        self.explosive_shots_remaining: int = 0

    @property
    def attack_speed_multiplier(self) -> float:
        """Retorna o multiplicador de velocidade de ataque baseado nos power-ups ativos."""
        multiplier = 1.0
        
        if self.speed_boost_timer > 0.0:
            multiplier *= Config.SPEED_ATTACK_MULTIPLIER  # Usar configuração personalizada
        if self.piercing_shot_timer > 0.0:
            multiplier *= Config.PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER
        if self.homing_shots_active:
            multiplier *= self.homing_fire_rate_penalty  # Penalidade de cadência
        if self.explosive_shots_active:
            multiplier *= Config.EXPLOSIVE_SHOT_FIRE_RATE_PENALTY  # Tiros explosivos são mais lentos
            
        return multiplier

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def is_invulnerable(self) -> bool:
        return self.invuln > 0

    def get_invulnerable_time(self) -> float:
        return self.invuln / 1000.0

    @property
    def has_shield(self) -> bool:
        return self.shield_timer > 0.0 and self.shield_hp > 0

    def activate_shield(self, duration: float, shield_hp: int = 1) -> None:
        """Ativa escudo que absorve dano por uma duração."""
        self.shield_timer = max(self.shield_timer, duration)
        self.shield_hp = max(self.shield_hp, shield_hp)
    
    def activate_homing_shots(self, duration: float, speed_penalty: float = 0.75, fire_rate_penalty: float = 0.8) -> None:
        """Ativa modo de tiros teleguiados com penalidades.
        
        Args:
            duration: Duração do efeito em segundos
            speed_penalty: Multiplicador de velocidade de movimento (< 1.0 = mais lento)
            fire_rate_penalty: Multiplicador de cadência de tiro (< 1.0 = mais lento)
        """
        self.homing_shots_active = True
        self.homing_shots_timer = duration
        self.homing_speed_penalty = speed_penalty
        self.homing_fire_rate_penalty = fire_rate_penalty
        # Aplicar penalidade de velocidade
        self.speed = self.original_speed * speed_penalty
    
    def activate_orbital_lasers(self, duration: float) -> None:
        """Ativa sistema de lasers orbitais com cargas por bolinha."""
        self.orbital_lasers_active = True
        self.orbital_angle = 0.0
        # Inicializar cargas e cooldowns para cada bolinha
        self.orbital_laser_charges = [self.orbital_charges_per_ball for _ in range(self.num_orbital_balls)]
        self.orbital_ball_fade = [0.0 for _ in range(self.num_orbital_balls)]
        self.orbital_laser_cooldowns = [
            random.uniform(ORBITAL_INITIAL_COOLDOWN_MIN, ORBITAL_INITIAL_COOLDOWN_MAX) 
            for _ in range(self.num_orbital_balls)
        ]
    
    def activate_explosive_shots(self, charges: int) -> None:
        """Ativa sistema de tiros explosivos com número limitado de cargas."""
        self.explosive_shots_active = True
        self.explosive_shots_remaining = charges
    
    def consume_explosive_shot(self) -> bool:
        """Consome uma carga de tiro explosivo. Retorna True se ainda há cargas."""
        if self.explosive_shots_remaining > 0:
            self.explosive_shots_remaining -= 1
            if self.explosive_shots_remaining <= 0:
                self.explosive_shots_active = False
            return True
        return False

    @property
    def is_homing_shots_active(self) -> bool:
        return self.homing_shots_active

    def get_homing_shots_time(self) -> float:
        return self.homing_shots_timer

    @property
    def is_double_shot_active(self) -> bool:
        return self.double_shot_timer > 0.0

    def get_double_shot_time(self) -> float:
        return self.double_shot_timer

    @property
    def is_speed_boost_active(self) -> bool:
        return self.speed_boost_timer > 0.0

    def get_speed_boost_time(self) -> float:
        return self.speed_boost_timer

    def _get_enemy_center(self, enemy: Any) -> Optional[Tuple[float, float]]:
        """Calcula o centro de um inimigo independente do tipo."""
        if hasattr(enemy, 'w') and hasattr(enemy, 'h'):
            return float(enemy.x + enemy.w / 2), float(enemy.y + enemy.h / 2)
        elif hasattr(enemy, 'radius'):
            return float(enemy.x), float(enemy.y)
        return None

    def _find_nearest_enemy(
        self, from_x: float, from_y: float, entity_manager: 'EntityManager'
    ) -> Optional[Any]:
        """Encontra o inimigo mais próximo de uma posição."""
        nearest_enemy: Optional[Any] = None
        nearest_dist = float('inf')
        
        # Buscar em todos os inimigos normais
        for enemy in entity_manager.enemies:
            center = self._get_enemy_center(enemy)
            if center is None:
                continue
            dx = center[0] - from_x
            dy = center[1] - from_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_enemy = enemy
        
        # Buscar em formações
        for formation in entity_manager.formations:
            for enemy in formation.get_enemies():
                center = self._get_enemy_center(enemy)
                if center is None:
                    continue
                dx = center[0] - from_x
                dy = center[1] - from_y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_enemy = enemy
        
        # Verificar boss
        if entity_manager.boss is not None:
            boss = entity_manager.boss
            dx = boss.x + boss.w / 2 - from_x
            dy = boss.y + boss.h / 2 - from_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < nearest_dist:
                nearest_enemy = boss
        
        return nearest_enemy

    def _update_timers(self, dt: float) -> None:
        """Atualiza todos os timers de power-ups."""
        if self.invuln > 0:
            self.invuln = max(0, self.invuln - dt * 1000)

        self.double_shot_timer = max(0.0, self.double_shot_timer - dt)
        self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)
        self.piercing_shot_timer = max(0.0, self.piercing_shot_timer - dt)
        self.mini_ships_timer = max(0.0, self.mini_ships_timer - dt)

        # Update shield timer
        self.shield_timer = max(0.0, self.shield_timer - dt)
        if self.shield_timer <= 0.0:
            self.shield_hp = 0
        
        # Update homing shots timer
        if self.homing_shots_active:
            self.homing_shots_timer = max(0.0, self.homing_shots_timer - dt)
            if self.homing_shots_timer <= 0.0:
                self.homing_shots_active = False
                self.speed = self.original_speed

    def _update_orbital_lasers(self, dt: float, entity_manager: Optional['EntityManager']) -> None:
        """Atualiza o sistema de lasers orbitais baseado em cargas."""
        if not self.orbital_lasers_active:
            return
        
        # Verificar se todas as bolinhas acabaram (cargas = 0 e fade completo)
        all_done = all(
            charges <= 0 and fade <= 0.0 
            for charges, fade in zip(self.orbital_laser_charges, self.orbital_ball_fade)
        )
        if all_done:
            self.orbital_lasers_active = False
            return
            
        # Girar as bolas ao redor da nave
        self.orbital_angle += dt * ORBITAL_ROTATION_SPEED
        
        # Atualizar fade das bolinhas que acabaram
        for i in range(self.num_orbital_balls):
            if self.orbital_laser_charges[i] <= 0 and self.orbital_ball_fade[i] > 0.0:
                self.orbital_ball_fade[i] = max(0.0, self.orbital_ball_fade[i] - dt)
        
        if entity_manager is None:
            return
            
        # Processar cada bola independentemente
        for i in range(self.num_orbital_balls):
            # Pular bolinhas sem cargas
            if self.orbital_laser_charges[i] <= 0:
                continue
                
            self.orbital_laser_cooldowns[i] = max(0.0, self.orbital_laser_cooldowns[i] - dt)
            
            if self.orbital_laser_cooldowns[i] > 0.0:
                continue
                
            # Calcular posição desta bola específica
            angle = self.orbital_angle + (i * 2 * math.pi / self.num_orbital_balls)
            ball_x = self.x + self.w / 2 + math.cos(angle) * self.orbital_radius
            ball_y = self.y + self.h / 2 + math.sin(angle) * self.orbital_radius
            
            # Encontrar inimigo mais próximo desta bola
            nearest_enemy = self._find_nearest_enemy(ball_x, ball_y, entity_manager)
            
            # Spawnar laser se houver inimigo
            if nearest_enemy is not None:
                target = self._get_enemy_center(nearest_enemy)
                if target is not None:
                    entity_manager.spawn_player_laser(
                        ball_x, ball_y, target[0], target[1], 
                        ship=self, ball_index=i
                    )
                    
                    # Consumir carga
                    self.orbital_laser_charges[i] -= 1
                    
                    # Se acabou as cargas, iniciar fade (1.5s de piscar)
                    if self.orbital_laser_charges[i] <= 0:
                        self.orbital_ball_fade[i] = 1.5
            
            # Resetar cooldown desta bola
            self.orbital_laser_cooldowns[i] = random.uniform(ORBITAL_COOLDOWN_MIN, ORBITAL_COOLDOWN_MAX)

    def _update_particles(self, dt: float) -> None:
        """Atualiza o sistema de partículas."""
        # Partículas de entrada
        if self.is_entering:
            for _ in range(PARTICLE_ENTRY_COUNT):
                particle = ParticleDict(
                    x=self.x + self.w / 2,
                    y=self.y,
                    vx=random.uniform(*PARTICLE_ENTRY_VELOCITY),
                    vy=random.uniform(80, 80),
                    lifetime=random.uniform(*PARTICLE_ENTRY_LIFETIME),
                    size=random.uniform(*PARTICLE_ENTRY_SIZE),
                    color=(255, random.randint(100, 220), 0),
                )
                self.entry_particles.append(particle)

        # Atualizar partículas de entrada (usar list comprehension eficiente)
        self.entry_particles = [
            ParticleDict(
                x=p["x"] + p["vx"] * dt,
                y=p["y"] + p["vy"] * dt,
                vx=p["vx"],
                vy=p["vy"],
                lifetime=p["lifetime"] - dt,
                size=p["size"],
                color=p["color"],
            )
            for p in self.entry_particles
            if p["lifetime"] - dt > 0
        ]

        # Gerar partículas de thruster
        for _ in range(PARTICLE_THRUSTER_COUNT):
            particle = ParticleDict(
                x=self.x + self.w / 2 + random.uniform(-5, 5),
                y=self.y + self.h,
                vx=random.uniform(*PARTICLE_THRUSTER_VELOCITY_X),
                vy=random.uniform(*PARTICLE_THRUSTER_VELOCITY_Y),
                lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                color=(255, random.randint(100, 200), 0),
            )
            self.thruster_particles.append(particle)

        # Atualizar partículas de thruster
        self.thruster_particles = [
            ParticleDict(
                x=p["x"] + p["vx"] * dt,
                y=p["y"] + p["vy"] * dt,
                vx=p["vx"],
                vy=p["vy"],
                lifetime=p["lifetime"] - dt,
                size=max(0, p["size"] - dt),
                color=p["color"],
            )
            for p in self.thruster_particles
            if p["lifetime"] - dt > 0 and p["size"] - dt > 0
        ]

    def update(self, dt: float, entity_manager: Optional['EntityManager'] = None):
        self._update_timers(dt)
        self._update_orbital_lasers(dt, entity_manager)
        self._update_particles(dt)

    def move(self, held_actions: set[str], dt: float):
        current_speed = self.speed * (1.5 if self.speed_boost_timer > 0 else 1.0)
        move_vec = pygame.math.Vector2(0, 0)

        if "hold_left" in held_actions:
            move_vec.x -= 1
        if "hold_right" in held_actions:
            move_vec.x += 1
        if "hold_up" in held_actions:
            move_vec.y -= 1
        if "hold_down" in held_actions:
            move_vec.y += 1

        if move_vec.length() > 0:
            move_vec.normalize_ip()

        self.x += move_vec.x * current_speed * dt
        self.y += move_vec.y * current_speed * dt

        self._keep_in_bounds()

    def _keep_in_bounds(self):
        if self.x < 0:
            self.x = 0
        if self.y < 0:
            self.y = 0
        if self.x + self.w > Config.SCREEN_WIDTH:
            self.x = Config.SCREEN_WIDTH - self.w
        if (
            self.y + self.h > Config.SCREEN_HEIGHT and not self.is_entering
        ):  # Allow going below screen during entry
            self.y = Config.SCREEN_HEIGHT - self.h

    def bullet_spawn(self) -> list[tuple[float, float, bool, bool, bool, bool]]:
        """Retorna posições para spawn de balas.
        
        Returns:
            Lista de tuplas (x, y, is_piercing, is_homing, is_explosive, is_low_ammo)
        """
        is_piercing = self.piercing_shot_timer > 0
        is_homing = self.homing_shots_active
        is_explosive = self.explosive_shots_active and self.explosive_shots_remaining > 0
        is_low_ammo = is_explosive and self.explosive_shots_remaining <= 5
        
        if self.double_shot_timer > 0:
            return [
                (self.x + self.w * 0.2 - 2.5, self.y, is_piercing, is_homing, is_explosive, is_low_ammo),
                (self.x + self.w * 0.8 - 2.5, self.y, is_piercing, is_homing, is_explosive, is_low_ammo),
            ]
        else:
            return [(self.x + self.w / 2 - 2.5, self.y, is_piercing, is_homing, is_explosive, is_low_ammo)]

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return

        if self.invuln > 0 and int(self.invuln / 100) % 2 == 0:
            return

        # Desenhar partículas de thruster (atrás da nave)
        for p in self.thruster_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])

        # Desenhar escudo (se ativo)
        if self.has_shield:
            # Efeito pulsante
            pulse = abs((time.time() * 4) % 2 - 1)  # Oscila entre 0 e 1
            base_radius = max(self.w, self.h) / 2 + 8
            radius = int(base_radius + pulse * 4)
            center_x = int(self.x + self.w / 2)
            center_y = int(self.y + self.h / 2)

            # Círculo azul semi-transparente (desenhar múltiplas camadas para simular transparência)
            shield_color = (100, 150, 255)
            for i in range(3):
                pygame.draw.circle(
                    surface, shield_color, (center_x, center_y), radius - i, 2
                )

        # Calcular tremor
        shake_x, shake_y = 0, 0
        if self.is_entering:
            shake_x = random.randint(-2, 2)
            shake_y = random.randint(-2, 2)

        # Desenha a nave como pixel art com o tremor
        for row_idx, row in enumerate(self.PIXEL_ART_SPRITE):
            for col_idx, char in enumerate(row):
                color = self.COLOR_MAP.get(char)
                if color and len(color) == 4 and color[3] == 0:  # Transparente
                    continue
                if color:
                    pixel_x = self.x + col_idx * self.PIXEL_SIZE + shake_x
                    pixel_y = self.y + row_idx * self.PIXEL_SIZE + shake_y
                    pygame.draw.rect(
                        surface,
                        color,
                        (pixel_x, pixel_y, self.PIXEL_SIZE, self.PIXEL_SIZE),
                    )

        # Desenhar bolas elétricas orbitais
        if self.orbital_lasers_active:
            current_time = time.time()
            
            # Desenhar cada bola orbital
            for i in range(self.num_orbital_balls):
                charges = self.orbital_laser_charges[i]
                fade = self.orbital_ball_fade[i]
                
                # Pular bolinhas completamente exauridas (sem fade restante)
                if charges <= 0 and fade <= 0.0:
                    continue
                
                angle = self.orbital_angle + (i * 2 * math.pi / self.num_orbital_balls)
                ball_x = int(self.x + self.w / 2 + math.cos(angle) * self.orbital_radius)
                ball_y = int(self.y + self.h / 2 + math.sin(angle) * self.orbital_radius)
                
                # Se está em fade (última carga usada), piscar e diminuir
                if charges <= 0 and fade > 0.0:
                    # Piscar rápido
                    blink = int(current_time * 10) % 2 == 0
                    if blink:
                        # Cor vermelha piscante
                        fade_alpha = fade / 1.5  # 0.0 a 1.0
                        ball_radius = int(3 + fade_alpha * 3)
                        pygame.draw.circle(surface, (255, 100, 100), (ball_x, ball_y), ball_radius + 2, 1)
                        pygame.draw.circle(surface, (255, 150, 150), (ball_x, ball_y), ball_radius)
                    continue
                
                # Última carga - piscar amarelo/vermelho como aviso
                if charges == 1:
                    blink = int(current_time * 6) % 2 == 0
                    pulse = abs((current_time * 8 + i) % 2 - 1)
                    ball_radius = int(4 + pulse * 2)
                    if blink:
                        # Amarelo/laranja aviso
                        pygame.draw.circle(surface, (255, 180, 50), (ball_x, ball_y), ball_radius + 3, 1)
                        pygame.draw.circle(surface, (255, 200, 100), (ball_x, ball_y), ball_radius + 2, 1)
                        pygame.draw.circle(surface, (255, 220, 150), (ball_x, ball_y), ball_radius)
                    else:
                        pygame.draw.circle(surface, (255, 100, 50), (ball_x, ball_y), ball_radius + 2, 1)
                        pygame.draw.circle(surface, (255, 150, 100), (ball_x, ball_y), ball_radius)
                
                # Cargas normais (2 ou 3)
                else:
                    time_to_fire = self.orbital_laser_cooldowns[i]
                    if time_to_fire < 1.0:
                        # Pulsar mais rápido quando prestes a disparar
                        pulse = abs((current_time * 12 + i) % 2 - 1)
                        ball_radius = int(4 + pulse * 2)
                        # Amarelo elétrico quando carregando
                        pygame.draw.circle(surface, (255, 255, 100), (ball_x, ball_y), ball_radius + 4, 1)
                        pygame.draw.circle(surface, (255, 255, 150), (ball_x, ball_y), ball_radius + 3, 1)
                        pygame.draw.circle(surface, (255, 255, 200), (ball_x, ball_y), ball_radius + 1)
                    else:
                        pulse = abs((current_time * 6 + i) % 2 - 1)
                        ball_radius = int(4 + pulse * 2)
                        # Azul elétrico normal
                        pygame.draw.circle(surface, (100, 200, 255), (ball_x, ball_y), ball_radius + 3, 1)
                        pygame.draw.circle(surface, (150, 220, 255), (ball_x, ball_y), ball_radius + 2, 1)
                        pygame.draw.circle(surface, (200, 240, 255), (ball_x, ball_y), ball_radius)

        # Desenhar partículas de entrada (acima da nave)
        for p in self.entry_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])
