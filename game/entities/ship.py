import math
import random
import time
from typing import TYPE_CHECKING, Any, Optional, Tuple, TypedDict

import pygame

from ..core.config import config as Config
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


# Constantes para configuração
PARTICLE_ENTRY_COUNT = Config.PARTICLE_ENTRY_COUNT
PARTICLE_THRUSTER_COUNT = Config.PARTICLE_THRUSTER_COUNT
PARTICLE_ENTRY_VELOCITY = Config.PARTICLE_ENTRY_VELOCITY
PARTICLE_ENTRY_LIFETIME = Config.PARTICLE_ENTRY_LIFETIME
PARTICLE_ENTRY_SIZE = Config.PARTICLE_ENTRY_SIZE
PARTICLE_THRUSTER_VELOCITY_X = Config.PARTICLE_THRUSTER_VELOCITY_X
PARTICLE_THRUSTER_VELOCITY_Y = Config.PARTICLE_THRUSTER_VELOCITY_Y
PARTICLE_THRUSTER_LIFETIME = Config.PARTICLE_THRUSTER_LIFETIME
PARTICLE_THRUSTER_SIZE = Config.PARTICLE_THRUSTER_SIZE
ORBITAL_ROTATION_SPEED = 2.0
ORBITAL_COOLDOWN_MIN = 2.0
ORBITAL_COOLDOWN_MAX = 4.0
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
    def __init__(
        self, x: float, y: float, mouse_control: bool = False, auto_fire: bool = False
    ):
        # Dimensões da nave (baseadas na imagem)
        self.w = 35
        self.h = 35
        self.x = x
        self.y = y
        self.speed = 250
        self.invuln = 0  # ms
        self.lives = Config.INITIAL_LIVES
        self.visible = True
        self.move_vec = pygame.math.Vector2(0, 0)

        # Configurações de controle
        self.mouse_control = mouse_control
        self.auto_fire = auto_fire
        self.auto_fire_timer = 0.0

        # Elemental Debuffs (Timers)
        self.fire_rate_modifier_timer: float = 0.0  # Inferno: sobreaquecimento
        self.invert_controls_timer: float = 0.0  # Toxina: interferência
        self.speed_modifier_timer: float = 0.0  # Nevasca: congelamento

        # Carregar imagem da nave
        try:
            from ..core.assets import BASE_DIR, get_image

            icon_path = BASE_DIR / "assets" / "icons" / "ship_icon.png"
            self.ship_image = get_image(icon_path).convert_alpha()
            # Redimensionar para o tamanho apropriado (manter proporções)
            original_size = self.ship_image.get_size()
            scale_factor = min(self.w / original_size[0], self.h / original_size[1])
            new_size = (
                int(original_size[0] * scale_factor),
                int(original_size[1] * scale_factor),
            )
            self.ship_image = pygame.transform.scale(self.ship_image, new_size)
        except pygame.error:
            # Imagem não carregada - nave não será visível
            self.ship_image = None

        # Power-ups
        self.double_shot_timer: float = 0.0
        self.speed_boost_timer: float = 0.0
        self.piercing_shot_timer: float = 0.0
        self.mini_ships_timer: float = 0.0
        self.is_entering = False
        self.entry_particles: list[ParticleDict] = []
        self.thruster_particles: list[ParticleDict] = []

        # NOVO: Rotação visual da nave (para side-scroll)
        self.rotation_angle: float = (
            0.0  # 0° = vertical (top-down), 90° = horizontal (side-scroll)
        )
        self.ship_image_rotated = self.ship_image  # Cache da imagem rotacionada
        self.is_side_scroll: bool = False  # Modo de jogo (top-down vs side-scroll)

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
        self.orbital_current_ball: int = 0  # Índice da bola que vai disparar próxima
        self.orbital_global_cooldown: float = 0.0  # Cooldown global entre disparos
        self.orbital_laser_charges: list[int] = [
            0,
            0,
            0,
        ]  # Cargas restantes por bolinha
        self.orbital_ball_fade: list[float] = [
            0.0,
            0.0,
            0.0,
        ]  # Timer de fade para cada bolinha (quando acaba)
        self.orbital_ball_entry: list[float] = [
            0.0,
            0.0,
            0.0,
        ]  # Timer de animação de entrada (0.0 = completo, >0 = animando)
        self.orbital_ball_shake: list[float] = [
            0.0,
            0.0,
            0.0,
        ]  # Timer de tremor após disparo (0.0 = sem tremor, >0 = tremendo)
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
            multiplier *= (
                Config.SPEED_ATTACK_MULTIPLIER
            )  # Usar configuração personalizada
        if self.piercing_shot_timer > 0.0:
            multiplier *= Config.PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER
        if self.homing_shots_active:
            multiplier *= self.homing_fire_rate_penalty  # Penalidade de cadência
        if self.explosive_shots_active:
            multiplier *= (
                Config.EXPLOSIVE_SHOT_FIRE_RATE_PENALTY
            )  # Tiros explosivos são mais lentos

        # Inferno debuff: Sobreaquecimento reduz cadência em 50%
        if self.fire_rate_modifier_timer > 0.0:
            multiplier *= 0.5

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

    def activate_homing_shots(
        self,
        duration: float,
        speed_penalty: float = 0.75,
        fire_rate_penalty: float = 0.8,
    ) -> None:
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
        # Inicializar cargas para cada bolinha
        self.orbital_laser_charges = [
            self.orbital_charges_per_ball for _ in range(self.num_orbital_balls)
        ]
        self.orbital_ball_fade = [0.0 for _ in range(self.num_orbital_balls)]
        # Animação de entrada: cada orb entra com delay sequencial
        entry_delay = 0.2  # 0.2s entre cada orb
        self.orbital_ball_entry = [
            0.5 + (i * entry_delay) for i in range(self.num_orbital_balls)
        ]
        self.orbital_ball_shake = [0.0 for _ in range(self.num_orbital_balls)]
        # Sistema sequencial: começar pela primeira bola com cooldown inicial
        self.orbital_current_ball = 0
        self.orbital_global_cooldown = random.uniform(
            ORBITAL_INITIAL_COOLDOWN_MIN, ORBITAL_INITIAL_COOLDOWN_MAX
        )

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

    def set_rotation(self, angle: float) -> None:
        """Define o ângulo de rotação visual da nave.

        Args:
            angle: Ângulo em graus (0° = vertical/top-down, 90° = horizontal/side-scroll)
        """
        if self.rotation_angle != angle and self.ship_image is not None:
            self.rotation_angle = angle
            # Rotacionar imagem: pygame.transform.rotate() usa rotação no sentido contrário
            # Então rotacionamos -angle para obter a rotação desejada
            self.ship_image_rotated = pygame.transform.rotate(self.ship_image, -angle)

    def _get_enemy_center(self, enemy: Any) -> Optional[Tuple[float, float]]:
        """Calcula o centro de um inimigo independente do tipo."""
        if hasattr(enemy, "w") and hasattr(enemy, "h"):
            return float(enemy.x + enemy.w / 2), float(enemy.y + enemy.h / 2)
        elif hasattr(enemy, "radius"):
            return float(enemy.x), float(enemy.y)
        return None

    def _find_nearest_enemy(
        self, from_x: float, from_y: float, entity_manager: "EntityManager"
    ) -> Optional[Any]:
        """Encontra o inimigo mais próximo de uma posição."""
        nearest_enemy: Optional[Any] = None
        nearest_dist = float("inf")

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
        """Atualiza todos os timers de power-ups e debuffs."""
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

        # Update elemental debuffs
        self.fire_rate_modifier_timer = max(0.0, self.fire_rate_modifier_timer - dt)
        self.invert_controls_timer = max(0.0, self.invert_controls_timer - dt)
        self.speed_modifier_timer = max(0.0, self.speed_modifier_timer - dt)

    def _update_orbital_lasers(
        self, dt: float, entity_manager: Optional["EntityManager"]
    ) -> None:
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

        # Atualizar fade e entrada das bolinhas
        for i in range(self.num_orbital_balls):
            # Atualizar animação de entrada
            if self.orbital_ball_entry[i] > 0.0:
                self.orbital_ball_entry[i] = max(0.0, self.orbital_ball_entry[i] - dt)

            # Atualizar tremor após disparo
            if self.orbital_ball_shake[i] > 0.0:
                self.orbital_ball_shake[i] = max(0.0, self.orbital_ball_shake[i] - dt)

            # Atualizar fade quando acabam as cargas
            if self.orbital_laser_charges[i] <= 0 and self.orbital_ball_fade[i] > 0.0:
                self.orbital_ball_fade[i] = max(0.0, self.orbital_ball_fade[i] - dt)

        if entity_manager is None:
            return

        # Sistema sequencial: apenas a bola atual pode disparar
        # Decrementar cooldown global
        self.orbital_global_cooldown = max(0.0, self.orbital_global_cooldown - dt)

        # Se ainda em cooldown, não processar disparo
        if self.orbital_global_cooldown > 0.0:
            return

        # Encontrar a próxima bola com cargas disponíveis
        attempts = 0
        while attempts < self.num_orbital_balls:
            i = self.orbital_current_ball

            # Se esta bola tem cargas, tentar disparar
            if self.orbital_laser_charges[i] > 0:
                # Obter tamanho real do sprite para centralizar corretamente
                if self.ship_image is not None:
                    sprite_w, sprite_h = self.ship_image.get_size()
                else:
                    sprite_w, sprite_h = self.w, self.h

                # Calcular posição desta bola específica
                angle = self.orbital_angle + (i * 2 * math.pi / self.num_orbital_balls)
                ball_x = self.x + sprite_w / 2 + math.cos(angle) * self.orbital_radius
                ball_y = self.y + sprite_h / 2 + math.sin(angle) * self.orbital_radius

                # Encontrar inimigo mais próximo desta bola
                nearest_enemy = self._find_nearest_enemy(ball_x, ball_y, entity_manager)

                # Spawnar laser se houver inimigo com alvo válido
                if nearest_enemy is not None:
                    target = self._get_enemy_center(nearest_enemy)
                    # Verificar se o alvo está dentro dos limites da tela (ou perto)
                    if (
                        target is not None
                        and -50 < target[0] < Config.SCREEN_WIDTH + 50
                        and -50 < target[1] < Config.SCREEN_HEIGHT + 50
                    ):
                        entity_manager.spawn_player_laser(
                            ball_x,
                            ball_y,
                            target[0],
                            target[1],
                            ship=self,
                            ball_index=i,
                            target_entity=nearest_enemy,
                        )

                        # Tocar som do laser
                        sound_manager.play_laser_shot()

                        # Ativar tremor na bolinha que disparou (0.8s = duração do laser)
                        self.orbital_ball_shake[i] = 0.8

                        #
                        # Consumir carga
                        self.orbital_laser_charges[i] -= 1

                        # Se acabou as cargas, iniciar fade (1.5s de piscar)
                        if self.orbital_laser_charges[i] <= 0:
                            self.orbital_ball_fade[i] = 1.5

                        # Avançar para próxima bola na sequência
                        self.orbital_current_ball = (
                            self.orbital_current_ball + 1
                        ) % self.num_orbital_balls

                        # Resetar cooldown global para próximo disparo
                        self.orbital_global_cooldown = random.uniform(
                            ORBITAL_COOLDOWN_MIN, ORBITAL_COOLDOWN_MAX
                        )
                        return

                # Se não há alvo válido, avançar para próxima bola
                self.orbital_current_ball = (
                    self.orbital_current_ball + 1
                ) % self.num_orbital_balls
                attempts += 1
            else:
                # Esta bola não tem cargas, avançar para próxima
                self.orbital_current_ball = (
                    self.orbital_current_ball + 1
                ) % self.num_orbital_balls
                attempts += 1

    def _update_particles(self, dt: float, is_side_scroll: bool = False) -> None:
        """Atualiza o sistema de partículas."""
        # Obter tamanho real do sprite (ou fallback para dimensões lógicas)
        if self.ship_image is not None:
            sprite_w, sprite_h = self.ship_image.get_size()
        else:
            sprite_w, sprite_h = self.w, self.h

        # Partículas de entrada (desabilitar em side-scroll)
        if self.is_entering and not is_side_scroll:
            for _ in range(PARTICLE_ENTRY_COUNT):
                min_size, max_size = PARTICLE_ENTRY_SIZE
                particle = ParticleDict(
                    x=self.x + sprite_w / 2,
                    y=self.y,
                    vx=random.uniform(*PARTICLE_ENTRY_VELOCITY),
                    vy=random.uniform(80, 80),
                    lifetime=random.uniform(*PARTICLE_ENTRY_LIFETIME),
                    size=random.uniform(min_size, max_size),
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
            if is_side_scroll:
                # Side-scroll: Thruster apontando para esquerda (direção oposta ao movimento)
                particle = ParticleDict(
                    x=self.x + random.uniform(-5, 5),  # Posição frontal da nave
                    y=self.y
                    + sprite_h / 2
                    + random.uniform(-5, 5),  # Centrado verticalmente
                    vx=-random.uniform(100, 200),  # Movimento para esquerda (negativo)
                    vy=random.uniform(-50, 50),  # Pequena variação vertical
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            else:
                # Top-down: Thruster apontando para baixo (comportamento original)
                particle = ParticleDict(
                    x=self.x
                    + sprite_w / 2
                    + random.uniform(-5, 5),  # Offset com variação para efeito natural
                    y=self.y + sprite_h,
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

    def update(
        self,
        dt: float,
        entity_manager: Optional["EntityManager"] = None,
        is_side_scroll: bool = False,
    ):
        self._update_timers(dt)
        self._update_orbital_lasers(dt, entity_manager)
        self._update_particles(dt, is_side_scroll)

        # Atualizar timer de tiro automático
        if self.auto_fire:
            self.auto_fire_timer += dt
            # Disparar a cada 0.1 segundos (10 tiros por segundo)
            if self.auto_fire_timer >= 0.1:
                self.auto_fire_timer = 0.0

    def move(self, held_actions: set[str], dt: float, is_side_scroll: bool = False):
        """
        Move a nave baseado nas ações pressionadas.

        Args:
            held_actions: Conjunto de ações sendo pressionadas
            dt: Delta time
            is_side_scroll: Se True, usa movimentação horizontal (left-right com up-down)
                           Se False, usa movimentação vertical (top-down)
        """
        # Calcular velocidade atual considerando boost e debuff de congelamento (Nevasca)
        base_speed_multiplier = 1.0
        if self.speed_boost_timer > 0:
            base_speed_multiplier = 1.5
        if self.speed_modifier_timer > 0.0:
            base_speed_multiplier *= 0.3  # Nevasca: 70% de redução

        current_speed = self.speed * base_speed_multiplier
        move_vec = pygame.math.Vector2(0, 0)

        if self.mouse_control:
            # Mover em direção ao mouse com precisão
            mouse_x, mouse_y = pygame.mouse.get_pos()
            ship_center_x = self.x + self.w / 2
            ship_center_y = self.y + self.h / 2
            # Usar sensibilidade para movimento proporcional à distância
            sensitivity = 0.02  # 2% de sensibilidade

            # Toxina debuff: Inverte a direção do movimento em relação ao mouse
            dir_mult = -1.0 if self.invert_controls_timer > 0.0 else 1.0

            move_vec.x = (mouse_x - ship_center_x) * sensitivity * dir_mult
            move_vec.y = (mouse_y - ship_center_y) * sensitivity * dir_mult
        else:
            # Movimento por teclado
            # Toxina debuff: Inverte mapeamento de teclas
            left = "hold_right" if self.invert_controls_timer > 0.0 else "hold_left"
            right = "hold_left" if self.invert_controls_timer > 0.0 else "hold_right"
            up = "hold_down" if self.invert_controls_timer > 0.0 else "hold_up"
            down = "hold_up" if self.invert_controls_timer > 0.0 else "hold_down"

            if left in held_actions:
                move_vec.x -= 1
            if right in held_actions:
                move_vec.x += 1
            if up in held_actions:
                move_vec.y -= 1
            if down in held_actions:
                move_vec.y += 1

            if move_vec.length() > 0:
                move_vec.normalize_ip()

        self.x += move_vec.x * current_speed * dt
        self.y += move_vec.y * current_speed * dt

        self._keep_in_bounds(is_side_scroll=is_side_scroll)

    def should_auto_fire(self) -> bool:
        """Retorna True se deve disparar automaticamente neste frame."""
        return self.auto_fire and self.auto_fire_timer == 0.0

    def _keep_in_bounds(self, is_side_scroll: bool = False):
        """Mantém a nave dentro dos limites da tela.

        Args:
            is_side_scroll: Se True, permite movimento livre em todos os eixos
        """
        if self.x < 0:
            self.x = 0
        if self.y < 0:
            self.y = 0
        if self.x + self.w > Config.SCREEN_WIDTH:
            self.x = Config.SCREEN_WIDTH - self.w
        if self.y + self.h > Config.SCREEN_HEIGHT and not self.is_entering:
            # Em top-down, permitir sair pela parte inferior durante entrada
            self.y = Config.SCREEN_HEIGHT - self.h

    def bullet_spawn(self) -> list[tuple[float, float, bool, bool, bool, bool]]:
        """Retorna posições para spawn de balas.

        Returns:
            Lista de tuplas (x, y, is_piercing, is_homing, is_explosive, is_low_ammo)
        """
        is_piercing = self.piercing_shot_timer > 0
        is_homing = self.homing_shots_active
        is_explosive = (
            self.explosive_shots_active and self.explosive_shots_remaining > 0
        )
        is_low_ammo = is_explosive and self.explosive_shots_remaining <= 5

        # Obter tamanho real do sprite (ou fallback para dimensões lógicas)
        if self.ship_image is not None:
            sprite_w, sprite_h = self.ship_image.get_size()
        else:
            sprite_w = self.w
            sprite_h = self.h

        # Em side-scroll, tiros saem pela frente (direita) da nave
        if self.is_side_scroll:
            # Side-scroll: tiros saem da direita da nave, verticalmente distribuídos
            if self.double_shot_timer > 0:
                return [
                    (
                        self.x + sprite_w + 5,  # Sair pela direita (frente)
                        self.y + sprite_h * 0.3,  # Parte superior da nave
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                    (
                        self.x + sprite_w + 5,  # Sair pela direita (frente)
                        self.y + sprite_h * 0.7,  # Parte inferior da nave
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
            else:
                return [
                    (
                        self.x + sprite_w + 5,  # Sair pela direita (frente)
                        self.y + sprite_h / 2,  # Centro da nave
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
        else:
            # Top-down: tiros saem da frente (cima) da nave (comportamento original)
            # Offset de -3.5 para centralizar a bala no canhão da nave, +1 para mover um píxel à direita
            if self.double_shot_timer > 0:
                return [
                    (
                        self.x + sprite_w * 0.2 - 3.5 + 2.2,
                        self.y,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                    (
                        self.x + sprite_w * 0.8 - 3.5 + 2.2,
                        self.y,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
            else:
                return [
                    (
                        self.x + sprite_w / 2 - 3.5 + 2.2,
                        self.y,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]

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

            # Calcular centro baseado no tamanho real do sprite (se existir)
            if self.ship_image is not None:
                sprite_w, sprite_h = self.ship_image.get_size()
                # Centralizar escudo no sprite real
                center_x = int(self.x + sprite_w / 2)
                center_y = int(self.y + sprite_h / 2)
                base_radius = max(sprite_w, sprite_h) / 2 + 8
            else:
                # Fallback para dimensões lógicas
                center_x = int(self.x + self.w / 2)
                center_y = int(self.y + self.h / 2)
                base_radius = max(self.w, self.h) / 2 + 8

            radius = int(base_radius + pulse * 4)

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

        # Desenhar a nave (usar imagem rotacionada se houver rotação)
        if self.ship_image is not None:
            # Usar imagem rotacionada se houver uma diferente da original
            image_to_draw = (
                self.ship_image_rotated
                if (self.rotation_angle != 0.0 and self.ship_image_rotated is not None)
                else self.ship_image
            )
            surface.blit(image_to_draw, (self.x + shake_x, self.y + shake_y))

        # Desenhar bolas elétricas orbitais
        if self.orbital_lasers_active:
            current_time = time.time()

            # Obter tamanho real do sprite para centralizar corretamente
            if self.ship_image is not None:
                sprite_w, sprite_h = self.ship_image.get_size()
            else:
                sprite_w, sprite_h = self.w, self.h

            # Desenhar cada bola orbital
            for i in range(self.num_orbital_balls):
                charges = self.orbital_laser_charges[i]
                fade = self.orbital_ball_fade[i]
                entry = self.orbital_ball_entry[i]
                shake = self.orbital_ball_shake[i]

                # Pular bolinhas completamente exauridas (sem fade restante)
                if charges <= 0 and fade <= 0.0:
                    continue

                angle = self.orbital_angle + (i * 2 * math.pi / self.num_orbital_balls)

                # Calcular posição com animação de entrada
                if entry > 0.0:
                    # Durante entrada: interpolar do centro da nave até posição orbital
                    entry_progress = 1.0 - (entry / 0.9)  # 0.0 = início, 1.0 = completo
                    # Easing suave (ease-out)
                    entry_progress = 1.0 - (1.0 - entry_progress) ** 3
                    current_radius = self.orbital_radius * entry_progress
                else:
                    current_radius = self.orbital_radius

                # Adicionar tremor se estiver tremendo
                shake_x, shake_y = 0, 0
                if shake > 0.0:
                    # Tremor mais intenso no início, diminui com o tempo
                    shake_intensity = int(5 * (shake / 0.8))
                    if shake_intensity > 0:
                        shake_x = random.randint(-shake_intensity, shake_intensity)
                        shake_y = random.randint(-shake_intensity, shake_intensity)

                ball_x = int(
                    self.x + sprite_w / 2 + math.cos(angle) * current_radius + shake_x
                )
                ball_y = int(
                    self.y + sprite_h / 2 + math.sin(angle) * current_radius + shake_y
                )

                # Se está em fade (última carga usada), piscar e diminuir
                if charges <= 0 and fade > 0.0:
                    # Piscar rápido
                    blink = int(current_time * 10) % 2 == 0
                    if blink:
                        # Cor vermelha piscante
                        fade_alpha = fade / 1.5  # 0.0 a 1.0
                        ball_radius = int(3 + fade_alpha * 3)
                        pygame.draw.circle(
                            surface,
                            (255, 100, 100),
                            (ball_x, ball_y),
                            ball_radius + 2,
                            1,
                        )
                        pygame.draw.circle(
                            surface, (255, 150, 150), (ball_x, ball_y), ball_radius
                        )
                    continue

                # Última carga - piscar amarelo/vermelho como aviso
                if charges == 1:
                    blink = int(current_time * 6) % 2 == 0
                    pulse = abs((current_time * 8 + i) % 2 - 1)
                    ball_radius = int(4 + pulse * 2)
                    if blink:
                        # Amarelo/laranja aviso
                        pygame.draw.circle(
                            surface,
                            (255, 180, 50),
                            (ball_x, ball_y),
                            ball_radius + 3,
                            1,
                        )
                        pygame.draw.circle(
                            surface,
                            (255, 200, 100),
                            (ball_x, ball_y),
                            ball_radius + 2,
                            1,
                        )
                        pygame.draw.circle(
                            surface, (255, 220, 150), (ball_x, ball_y), ball_radius
                        )
                    else:
                        pygame.draw.circle(
                            surface,
                            (255, 100, 50),
                            (ball_x, ball_y),
                            ball_radius + 2,
                            1,
                        )
                        pygame.draw.circle(
                            surface, (255, 150, 100), (ball_x, ball_y), ball_radius
                        )

                # Cargas normais (2 ou 3)
                else:
                    # Verificar se esta bola é a próxima a disparar
                    is_ready_to_fire = (
                        self.orbital_current_ball == i
                        and self.orbital_global_cooldown < 1.0
                    )

                    # Durante entrada, usar cor diferente (pulsação suave)
                    if entry > 0.0:
                        entry_alpha = 1.0 - (entry / 0.9)
                        pulse = abs((current_time * 8 + i) % 2 - 1)
                        ball_radius = int(2 + entry_alpha * 4 + pulse * 1)
                        # Branco/ciano aparecendo gradualmente
                        alpha_color = int(255 * entry_alpha)
                        pygame.draw.circle(
                            surface,
                            (100, 200, alpha_color),
                            (ball_x, ball_y),
                            ball_radius + 2,
                            1,
                        )
                        pygame.draw.circle(
                            surface,
                            (150, 255, alpha_color),
                            (ball_x, ball_y),
                            ball_radius,
                        )
                    elif is_ready_to_fire:
                        # Pulsar mais rápido quando prestes a disparar - Branco intenso
                        pulse = abs((current_time * 12 + i) % 2 - 1)
                        ball_radius = int(4 + pulse * 3)
                        # Branco brilhante quando carregando (mesma cor do núcleo do laser)
                        pygame.draw.circle(
                            surface,
                            (150, 255, 255),  # Ciano muito claro
                            (ball_x, ball_y),
                            ball_radius + 4,
                            1,
                        )
                        pygame.draw.circle(
                            surface,
                            (200, 240, 255),  # Azul muito claro (cor dos sparks)
                            (ball_x, ball_y),
                            ball_radius + 3,
                            1,
                        )
                        pygame.draw.circle(
                            surface,
                            (255, 255, 255),
                            (ball_x, ball_y),
                            ball_radius + 1,  # Núcleo branco
                        )
                    else:
                        pulse = abs((current_time * 6 + i) % 2 - 1)
                        ball_radius = int(4 + pulse * 2)
                        # Azul ciano elétrico normal (mesmas cores do brilho do laser)
                        pygame.draw.circle(
                            surface,
                            (100, 200, 255),  # Brilho externo do laser
                            (ball_x, ball_y),
                            ball_radius + 3,
                            1,
                        )
                        pygame.draw.circle(
                            surface,
                            (150, 255, 255),  # Brilho médio do laser
                            (ball_x, ball_y),
                            ball_radius + 2,
                            1,
                        )
                        pygame.draw.circle(
                            surface,
                            (200, 240, 255),
                            (ball_x, ball_y),
                            ball_radius,  # Cor dos sparks
                        )

        # Desenhar partículas de entrada (acima da nave)
        for p in self.entry_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])
