from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, Any, Optional

import pygame

from ..core.config import config as Config
from ..core.ship_types import ShipProfile, get_ship_profile
from ..core.sound import sound_manager
from .particle_types import ParticleDict

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


class Ship:
    def __init__(
        self,
        x: float,
        y: float,
        mouse_control: bool = False,
        auto_fire: bool = False,
        profile: Optional[ShipProfile] = None,
    ):
        # ShipProfile aplica multiplicadores às stats base (velocidade, fire rate,
        # dano) e habilita mecânicas especiais (Cofre, Fantasma, Caçador, etc).
        self.profile: ShipProfile = profile or get_ship_profile("padrao")

        # Dimensões da nave (baseadas na imagem)
        self.w = 60
        self.h = 60
        self.x = x
        self.y = y
        # Rect persistente — atualizado in-place no acesso para evitar alocação
        # por frame (rect é consultado por colisões, pickup, draw...).
        self._rect = pygame.Rect(int(x), int(y), self.w, self.h)
        # Multiplicadores do profile aplicados sobre os valores-base.
        self.speed = 250 * self.profile.speed_mult
        self.invuln = 0  # ms
        self.lives = max(1, Config.INITIAL_LIVES + self.profile.extra_lives)
        self.max_lives = self.lives
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
        self.wind_slow_factor: float = 1.0  # Vento: lentidão

        # Carregar imagem da nave
        try:
            from ..core.assets import BASE_DIR, get_image

            icon_path = BASE_DIR / "assets" / "icons" / self.profile.sprite_filename
            self.ship_image = get_image(icon_path).convert_alpha()
            # Redimensionar para o tamanho apropriado (manter proporções)
            original_size = self.ship_image.get_size()
            scale_factor = min(self.w / original_size[0], self.h / original_size[1])
            new_size = (
                int(original_size[0] * scale_factor),
                int(original_size[1] * scale_factor),
            )
            self.ship_image = pygame.transform.scale(self.ship_image, new_size)
            self._ship_image_size: tuple[int, int] = self.ship_image.get_size()
        except pygame.error:
            # Imagem não carregada - nave não será visível
            self.ship_image = None
            self._ship_image_size = (self.w, self.h)

        # Power-ups
        self.double_shot_timer: float = 0.0
        self.speed_boost_timer: float = 0.0
        self.piercing_shot_timer: float = 0.0
        self.mini_ships_timer: float = 0.0
        self.damage_boost_timer: float = 0.0
        # Chain Shot power-up
        self.chain_shot_timer: float = 0.0
        # Repulsion Shield power-up (Vento Constante)
        self.repulsion_shield_timer: float = 0.0
        self.repulsion_wind_streaks: list[dict[str, Any]] = []

        self.is_entering = False
        self.entering_timer = 0.0
        self.entering_duration = 0.0
        self.entry_start_pos = (0.0, 0.0)
        self.entry_target_pos = (0.0, 0.0)
        self.entry_particles: list[ParticleDict] = []
        self.thruster_particles: list[ParticleDict] = []

        # NOVO: Rotação visual da nave (para side-scroll)
        self.rotation_angle: float = (
            0.0  # 0° = vertical (top-down), 90° = horizontal (side-scroll)
        )
        self.ship_image_rotated = self.ship_image  # Cache da imagem rotacionada
        self.is_side_scroll: bool = False  # Modo de jogo (top-down vs side-scroll)

        # NOVO: Direção cardinal da nave para tiros e orientação
        self.facing: str = "north"
        self._cardinal_directions: tuple[str, ...] = (
            "north",
            "east",
            "south",
            "west",
        )
        self._cardinal_vectors: dict[str, tuple[float, float]] = {
            "north": (0.0, -1.0),
            "east": (1.0, 0.0),
            "south": (0.0, 1.0),
            "west": (-1.0, 0.0),
        }
        self._cardinal_angles: dict[str, float] = {
            "north": 0.0,
            "east": 90.0,
            "south": 180.0,
            "west": 270.0,
        }
        self.set_facing(self.facing)
        self._refresh_sprite_size()

        # Shield system (from upgrades)
        self.shield_timer: float = 0.0
        self.shield_hp: int = 0  # Hits the shield can absorb

        # Homing shots system (from upgrades)
        self.homing_shots_active: bool = False
        self.homing_shots_timer: float = 0.0
        self.homing_speed_penalty: float = 1.0
        self.homing_fire_rate_penalty: float = 1.0
        # `original_speed` reflete a velocidade base após profile (sem penalidades).
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

        # Cofre (powerup storage): slots para guardar powerups e ativar com Q/E.
        # Lista de strings (kind do PowerUp) ou None para slot vazio.
        self.stored_powerups: list[Optional[str]] = [None] * self.profile.powerup_slots

        # Fantasma: dash com i-frames.
        self.dash_timer: float = 0.0  # tempo restante de dash ativo
        self.dash_cooldown_left: float = 0.0  # cooldown até próximo dash
        self.dash_dir: pygame.math.Vector2 = pygame.math.Vector2(0, -1)
        self.dash_duration: float = 0.2
        self.dash_speed_mult: float = 3.5  # multiplicador da velocidade base no dash
        # Rastro de partículas do dash (decaem após o dash terminar).
        self.dash_trail_particles: list[ParticleDict] = []

        # Caçador: charge shot.
        self.charge_shot_active: bool = False
        self.charge_shot_timer: float = 0.0  # tempo acumulado de carga

        # Buffer de posições do cursor para reaction_delay (x, y, timestamp).
        # Deque: popleft O(1) para descartar entradas vencidas, evitando
        # rebuild da lista por frame.
        self._mouse_history: deque[tuple[float, float, float]] = deque()
        # Cache do tamanho do sprite renderizado — invalidado em set_rotation.
        self._cached_sprite_size: tuple[int, int] = (self.w, self.h)

        # Reverberador: combo de dano sem tomar hit.
        self.combo_kills: int = 0  # abates consecutivos sem dano

        # Acumulador de tempo para animações no draw() — substitui time.time()
        # e garante compatibilidade com pausa/slow-motion.
        self._draw_time: float = 0.0

        # Componentes extraídos: Ship vira fachada e delega.
        from .ship_movement import ShipMovement
        from .ship_powerups import ShipPowerups
        from .ship_renderer import ShipRenderer

        self._renderer = ShipRenderer(self)
        self._powerups = ShipPowerups(self)
        self._movement = ShipMovement(self)

    def has_storage_slots(self) -> bool:
        return self._powerups.has_storage_slots()

    def try_store_powerup(self, kind: str) -> bool:
        return self._powerups.try_store_powerup(kind)

    def consume_stored_powerup(self, slot_index: int) -> Optional[str]:
        return self._powerups.consume_stored_powerup(slot_index)

    @property
    def is_dashing(self) -> bool:
        return bool(self.dash_timer > 0.0)

    @property
    def charge_shot_progress(self) -> float:
        """Progresso da carga normalizado em [0.0, 1.0]."""
        max_t: float = float(self.profile.charge_shot_max_time)
        if max_t <= 0:
            return 0.0
        return float(min(1.0, self.charge_shot_timer / max_t))

    def start_charge(self) -> bool:
        """Inicia acúmulo do charge shot. Retorna True se a nave suporta carga."""
        if not self.profile.has_charge_shot:
            return False
        if self.charge_shot_active:
            return True
        self.charge_shot_active = True
        self.charge_shot_timer = 0.0
        sound_manager.play_boss_laser_charging()
        return True

    def cancel_charge(self) -> None:
        """Cancela o charge sem disparar, caso solte o botão antes de completar."""
        if self.charge_shot_active:
            self.charge_shot_active = False
            self.charge_shot_timer = 0.0
            sound_manager.stop_boss_laser_charging()

    def consume_charge(self) -> float:
        """Encerra o charge e retorna o multiplicador de dano deste disparo.

        Interpola linearmente entre 1.0 (sem carga) e `charge_shot_damage_mult`
        (carga máxima). Reseta o estado.
        """
        if not self.profile.has_charge_shot or not self.charge_shot_active:
            return 1.0
        progress = self.charge_shot_progress
        mult = 1.0 + (self.profile.charge_shot_damage_mult - 1.0) * progress
        self.charge_shot_active = False
        self.charge_shot_timer = 0.0
        sound_manager.stop_boss_laser_charging()
        return mult

    def register_kill(self) -> None:
        """Incrementa o contador de combo do Reverberador (clamped)."""
        if self.profile.combo_damage_per_kill <= 0:
            return
        self.combo_kills += 1

    def reset_combo(self) -> None:
        """Reseta o combo do Reverberador (chamado ao tomar dano)."""
        self.combo_kills = 0

    @property
    def combo_damage_bonus(self) -> float:
        """Bônus aditivo de dano do Reverberador (0.0 a `combo_damage_cap`)."""
        if self.profile.combo_damage_per_kill <= 0:
            return 0.0
        raw: float = float(self.combo_kills * self.profile.combo_damage_per_kill)
        cap: float = float(self.profile.combo_damage_cap)
        return float(min(raw, cap) if cap > 0 else raw)

    def try_dash(self, current_move_vec: pygame.math.Vector2) -> bool:
        return self._movement.try_dash(current_move_vec)

    @property
    def attack_speed_multiplier(self) -> float:
        """Retorna o multiplicador de velocidade de ataque baseado nos power-ups ativos.

        Multiplicativo com o `fire_rate_mult` do `ShipProfile` — powerups herdam
        os stats da nave (Estilete +60% combinado com double_shot, etc).
        """
        multiplier = self.profile.fire_rate_mult

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
    def pickup_rect(self) -> pygame.Rect:
        """Retângulo de coleta de powerups/estrelas, inflado pelo profile.

        Magneto tem `pickup_radius_mult` > 1, resultando em uma hitbox de
        coleta maior que a hitbox de colisão (`rect`).
        """
        mult = self.profile.pickup_radius_mult
        if mult <= 1.0:
            return self.rect
        extra = int(self.w * (mult - 1.0))
        return self.rect.inflate(extra, extra)

    @property
    def damage_multiplier(self) -> float:
        """Multiplicador de dano efetivo: profile × powerup × combo do Reverberador.

        Powerups herdam o stat da nave — Aríete + damage_boost compõem por
        multiplicação (1.80 × Config.DAMAGE_BOOST_MULTIPLIER). O combo do
        Reverberador é aplicado como bônus aditivo no fator final.
        """
        multiplier = self.profile.damage_mult
        if self.damage_boost_timer > 0.0:
            multiplier *= Config.DAMAGE_BOOST_MULTIPLIER
        # Reverberador: bônus aditivo escalando o multiplicador (combo_kills × per_kill).
        bonus = self.combo_damage_bonus
        if bonus > 0:
            multiplier *= 1.0 + bonus
        return multiplier

    @property
    def rect(self) -> pygame.Rect:
        self._rect.update(int(self.x), int(self.y), self.w, self.h)
        return self._rect

    @property
    def is_invulnerable(self) -> bool:
        return self.invuln > 0

    def get_invulnerable_time(self) -> float:
        return self.invuln / 1000.0

    def get_double_shot_time(self) -> float:
        return self.double_shot_timer

    def get_speed_boost_time(self) -> float:
        return self.speed_boost_timer

    def get_piercing_shot_time(self) -> float:
        return self.piercing_shot_timer

    def get_mini_ships_time(self) -> float:
        return self.mini_ships_timer

    def get_damage_boost_time(self) -> float:
        return self.damage_boost_timer

    def get_chain_shot_time(self) -> float:
        return self.chain_shot_timer

    def get_repulsion_shield_time(self) -> float:
        return self.repulsion_shield_timer

    @property
    def has_shield(self) -> bool:
        return self.shield_timer > 0.0 and self.shield_hp > 0

    def activate_shield(self, duration: float, shield_hp: int = 1) -> None:
        self._powerups.activate_shield(duration, shield_hp)

    def activate_homing_shots(
        self,
        duration: float,
        speed_penalty: float = 0.75,
        fire_rate_penalty: float = 0.8,
    ) -> None:
        self._powerups.activate_homing_shots(duration, speed_penalty, fire_rate_penalty)

    def activate_orbital_lasers(self, _duration: float) -> None:
        self._powerups.activate_orbital_lasers()

    def activate_explosive_shots(self, charges: int) -> None:
        self._powerups.activate_explosive_shots(charges)

    def activate_chain_shot(self, duration: float | None = None) -> None:
        self._powerups.activate_chain_shot(duration)

    def activate_repulsion_shield(self, duration: float | None = None) -> None:
        self._powerups.activate_repulsion_shield(duration)

    @property
    def has_chain_shot(self) -> bool:
        return self.chain_shot_timer > 0.0

    @property
    def has_repulsion_shield(self) -> bool:
        return self.repulsion_shield_timer > 0.0

    def consume_explosive_shot(self) -> bool:
        return self._powerups.consume_explosive_shot()

    @property
    def is_homing_shots_active(self) -> bool:
        """True se o modo de tiros teleguiados está ativo."""
        return self.homing_shots_active

    @property
    def is_double_shot_active(self) -> bool:
        """True se o double shot está ativo. Use `double_shot_timer` para o tempo restante."""
        return self.double_shot_timer > 0.0

    @property
    def is_speed_boost_active(self) -> bool:
        """True se o boost de velocidade está ativo. Use `speed_boost_timer` para o tempo restante."""
        return self.speed_boost_timer > 0.0

    def set_rotation(self, angle: float) -> None:
        """Define o ângulo de rotação visual da nave.

        Args:
            angle: Ângulo em graus (0° = vertical/top-down, 90° = horizontal/side-scroll)
        """
        if abs(self.rotation_angle - angle) > 0.01 and self.ship_image is not None:
            self.rotation_angle = angle
            # Rotacionar imagem: pygame.transform.rotate() usa rotação no sentido contrário
            # Então rotacionamos -angle para obter a rotação desejada
            self.ship_image_rotated = pygame.transform.rotate(self.ship_image, -angle)
            self._refresh_sprite_size()

    def set_facing(self, facing: str) -> None:
        """Define a direção cardinal da nave e atualiza sua rotação visual."""
        if facing not in self._cardinal_directions:
            return
        self.facing = facing
        self.set_rotation(self._cardinal_angles[facing])

    def cycle_facing(self) -> None:
        """Avança para a próxima direção cardinal."""
        current_index = self._cardinal_directions.index(self.facing)
        next_index = (current_index + 1) % len(self._cardinal_directions)
        self.set_facing(self._cardinal_directions[next_index])

    def apply_world_mode(self, is_side_scroll: bool) -> None:
        """Sincroniza o modo do mundo e orientação inicial da nave."""
        self.is_side_scroll = is_side_scroll
        default_facing = "east" if is_side_scroll else "north"
        self.set_facing(default_facing)

    def get_facing_vector(self) -> tuple[float, float]:
        return self._cardinal_vectors.get(self.facing, (0.0, -1.0))

    def _get_rendered_sprite_size(self) -> tuple[int, int]:
        """Retorna o tamanho do sprite atualmente desenhado na tela.
        Valor cacheado; invalidado em set_rotation/_refresh_sprite_size."""
        return self._cached_sprite_size

    def _refresh_sprite_size(self) -> None:
        if self.ship_image is None:
            self._cached_sprite_size = (self.w, self.h)
        elif self.rotation_angle != 0.0 and self.ship_image_rotated is not None:
            self._cached_sprite_size = self.ship_image_rotated.get_size()
        else:
            self._cached_sprite_size = self.ship_image.get_size()

    def _get_enemy_center(self, enemy: Any) -> Optional[tuple[float, float]]:
        from ..systems.targeting import enemy_center

        return enemy_center(enemy)

    def _find_nearest_enemy(
        self, from_x: float, from_y: float, entity_manager: "EntityManager"
    ) -> Optional[Any]:
        from ..systems.targeting import find_nearest_enemy

        return find_nearest_enemy(from_x, from_y, entity_manager)

    def _update_particles(self, dt: float, is_side_scroll: bool = False) -> None:
        """Atualiza o sistema de partículas."""
        # Obter tamanho real do sprite (ou fallback para dimensões lógicas)
        if self.ship_image is not None:
            sprite_w, sprite_h = self.ship_image.get_size()
        else:
            sprite_w, sprite_h = self.w, self.h

        thruster_count = max(
            0,
            int(round(PARTICLE_THRUSTER_COUNT * self.profile.thruster_intensity_mult)),
        )

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

        # Gerar partículas de thruster (sempre atrás da direção atual da nave)
        for _ in range(thruster_count):
            if self.facing == "north":
                particle = ParticleDict(
                    x=self.x + sprite_w / 2 + random.uniform(-5, 5),
                    y=self.y + sprite_h + random.uniform(-2, 3),
                    vx=random.uniform(-40, 40),
                    vy=random.uniform(100, 220),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            elif self.facing == "south":
                particle = ParticleDict(
                    x=self.x + sprite_w / 2 + random.uniform(-5, 5),
                    y=self.y + random.uniform(-3, 2),
                    vx=random.uniform(-40, 40),
                    vy=-random.uniform(100, 220),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            elif self.facing == "east":
                particle = ParticleDict(
                    x=self.x + random.uniform(-3, 2),
                    y=self.y + sprite_h / 2 + random.uniform(-5, 5),
                    vx=-random.uniform(100, 220),
                    vy=random.uniform(-40, 40),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            else:  # west
                particle = ParticleDict(
                    x=self.x + sprite_w + random.uniform(-2, 3),
                    y=self.y + sprite_h / 2 + random.uniform(-5, 5),
                    vx=random.uniform(100, 220),
                    vy=random.uniform(-40, 40),
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

    def start_entering_animation(
        self,
        start_pos: tuple[float, float],
        target_pos: tuple[float, float],
        duration: float,
    ) -> None:
        """Inicia a animação de entrada da nave."""
        self.is_entering = True
        self.entering_timer = 0.0
        self.entering_duration = duration
        self.entry_start_pos = start_pos
        self.entry_target_pos = target_pos
        self.x, self.y = start_pos

    def update(
        self,
        dt: float,
        entity_manager: Optional["EntityManager"] = None,
        is_side_scroll: bool = False,
    ):
        self._draw_time += dt

        if self.is_entering:
            self.entering_timer += dt
            progress = min(1.0, self.entering_timer / self.entering_duration)
            eased = 1.0 - (1.0 - progress) ** 3  # ease-out cúbico
            self.x = self.entry_start_pos[0] + (
                self.entry_target_pos[0] - self.entry_start_pos[0]
            ) * eased
            self.y = self.entry_start_pos[1] + (
                self.entry_target_pos[1] - self.entry_start_pos[1]
            ) * eased
            if progress >= 1.0:
                self.is_entering = False

        self._powerups.update_timers(dt)
        self._powerups.update_repulsion_shield(dt, entity_manager)
        self._movement.update_dash(dt)

        # Avança charge do Caçador (cap em charge_shot_max_time).
        if self.charge_shot_active:
            self.charge_shot_timer = min(
                self.profile.charge_shot_max_time,
                self.charge_shot_timer + dt,
            )
        self._powerups.update_orbital_lasers(dt, entity_manager)
        self._update_particles(dt, is_side_scroll)

        # Atualizar timer de tiro automático
        if self.auto_fire:
            self.auto_fire_timer += dt
            # Disparar a cada 0.1 segundos (10 tiros por segundo)
            if self.auto_fire_timer >= 0.1:
                self.auto_fire_timer = 0.0

    def move(
        self,
        held_actions: set[str],
        dt: float,
        is_side_scroll: bool = False,
        gamepad_vec: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self._movement.move(held_actions, dt, is_side_scroll, gamepad_vec)

    def should_auto_fire(self) -> bool:
        """Retorna True se deve disparar automaticamente neste frame."""
        return self.auto_fire and self.auto_fire_timer == 0.0

    def bullet_spawn(
        self,
    ) -> list[tuple[float, float, tuple[float, float], bool, bool, bool, bool]]:
        """Retorna posições para spawn de balas.

        Returns:
            Lista de tuplas (x, y, direction, is_piercing, is_homing, is_explosive, is_low_ammo)
        """
        is_piercing = self.piercing_shot_timer > 0
        is_homing = self.homing_shots_active
        is_explosive = (
            self.explosive_shots_active and self.explosive_shots_remaining > 0
        )
        is_low_ammo = is_explosive and self.explosive_shots_remaining <= 5

        facing_vector = self.get_facing_vector()

        # Obter tamanho visual atual do sprite (leva em conta rotação 90°/270°).
        sprite_w, sprite_h = self._get_rendered_sprite_size()

        if self.facing == "north":
            if self.double_shot_timer > 0:
                return [
                    (
                        self.x + sprite_w * 0.2 - 3.5 + 2.2,
                        self.y,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                    (
                        self.x + sprite_w * 0.8 - 3.5 + 2.2,
                        self.y,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
            return [
                (
                    self.x + sprite_w / 2 - 3.5 + 2.2,
                    self.y,
                    facing_vector,
                    is_piercing,
                    is_homing,
                    is_explosive,
                    is_low_ammo,
                )
            ]
        elif self.facing == "south":
            if self.double_shot_timer > 0:
                return [
                    (
                        self.x + sprite_w * 0.2 - 3.5 + 2.2,
                        self.y + sprite_h,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                    (
                        self.x + sprite_w * 0.8 - 3.5 + 2.2,
                        self.y + sprite_h,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
            return [
                (
                    self.x + sprite_w / 2 - 3.5 + 2.2,
                    self.y + sprite_h,
                    facing_vector,
                    is_piercing,
                    is_homing,
                    is_explosive,
                    is_low_ammo,
                )
            ]
        elif self.facing == "east":
            if self.double_shot_timer > 0:
                return [
                    (
                        self.x + sprite_w + 5,
                        self.y + sprite_h * 0.3,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                    (
                        self.x + sprite_w + 5,
                        self.y + sprite_h * 0.7,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
            return [
                (
                    self.x + sprite_w + 5,
                    self.y + sprite_h / 2,
                    facing_vector,
                    is_piercing,
                    is_homing,
                    is_explosive,
                    is_low_ammo,
                )
            ]
        else:  # west
            offset_x = self.x - 15
            if self.double_shot_timer > 0:
                return [
                    (
                        offset_x,
                        self.y + sprite_h * 0.3,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                    (
                        offset_x,
                        self.y + sprite_h * 0.7,
                        facing_vector,
                        is_piercing,
                        is_homing,
                        is_explosive,
                        is_low_ammo,
                    ),
                ]
            return [
                (
                    offset_x,
                    self.y + sprite_h / 2,
                    facing_vector,
                    is_piercing,
                    is_homing,
                    is_explosive,
                    is_low_ammo,
                )
            ]

    def draw(self, surface: pygame.Surface):
        self._renderer.draw(surface)

    def take_damage(self, amount: int = 1) -> bool:
        """Aplica dano à nave. Retorna True se perdeu uma vida."""
        if self.is_invulnerable:
            return False

        # Absorção pelo escudo
        if self.has_shield:
            self.shield_hp -= amount
            if self.shield_hp <= 0:
                self.shield_timer = 0.0
            sound_manager.play_shield_hit()
            self.invuln = 1000  # Pequena invuln após quebra
            return False

        self.lives -= amount
        self.invuln = Config.INVULN_TIME * 1000
        self.reset_combo()  # Reverberador perde o bônus ao tomar dano.
        return True

    def recover_life(self, amount: int = 1) -> None:
        """Recupera vidas da nave (respeitando o máximo inicial)."""
        self.lives = min(self.max_lives, self.lives + amount)

    def is_dead(self) -> bool:
        return self.lives <= 0
