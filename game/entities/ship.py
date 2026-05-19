from __future__ import annotations

import math
import random
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Optional, TypedDict

import pygame

from ..core.config import config as Config
from ..core.ship_types import ShipProfile, get_ship_profile
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

# Controle por mouse — sistema spring
# BASE_STIFFNESS: rigidez base do spring (px/s por px de distância).
#   Suba para resposta mais imediata em geral (range seguro: 6.0–12.0).
# MOUSE_DEAD_ZONE: raio de snap em pixels — elimina jitter próximo ao cursor.
#   Aumente se a nave "vibrar" parada (range seguro: 1.0–4.0).
MOUSE_BASE_STIFFNESS: float = 8.5
MOUSE_DEAD_ZONE: float = 2.0

# Cache estático da surface de brilho do Repulsion Shield — evita alocar
# Surface SRCALPHA e draw.circle por frame quando o escudo está ativo.
_REPULSION_GLOW_CACHE: dict[int, pygame.Surface] = {}


def _get_repulsion_glow(glow_r: int) -> pygame.Surface:
    cached = _REPULSION_GLOW_CACHE.get(glow_r)
    if cached is not None:
        return cached
    surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (200, 255, 255, 40), (glow_r, glow_r), glow_r)
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _REPULSION_GLOW_CACHE[glow_r] = surf
    return surf


# Cores dos sparks do Chain Shot — tuple imutável evita realocação.
_CHAIN_SPARK_COLORS: tuple[tuple[int, int, int], ...] = (
    (100, 200, 255),
    (200, 255, 255),
    (255, 255, 255),
)


class ParticleDict(TypedDict):
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    size: float
    color: tuple[int, int, int]


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

    def has_storage_slots(self) -> bool:
        return self.profile.powerup_slots > 0

    def try_store_powerup(self, kind: str) -> bool:
        """Tenta guardar um powerup no primeiro slot vazio.

        Returns:
            True se o powerup foi armazenado (slot livre encontrado),
            False se a nave não tem slots ou todos estão ocupados.
        """
        if not self.has_storage_slots():
            return False
        for i, slot in enumerate(self.stored_powerups):
            if slot is None:
                self.stored_powerups[i] = kind
                return True
        return False

    def consume_stored_powerup(self, slot_index: int) -> Optional[str]:
        """Remove e retorna o powerup do slot. None se o slot estava vazio."""
        if not (0 <= slot_index < len(self.stored_powerups)):
            return None
        kind = self.stored_powerups[slot_index]
        if kind is not None:
            self.stored_powerups[slot_index] = None
        return kind

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
        """Ativa o dash do Fantasma se o cooldown permitir.

        Args:
            current_move_vec: vetor de movimento atual (do input). Se zero,
                              usa a direção cardinal atual (`facing`).

        Returns:
            True se o dash foi iniciado, False se em cooldown ou nave sem dash.
        """
        if not self.profile.has_dash:
            return False
        if self.dash_cooldown_left > 0.0 or self.is_dashing:
            return False

        if current_move_vec.length_squared() > 0:
            direction = current_move_vec.normalize()
        else:
            # Sem input: dasha na direção em que a nave está apontando.
            vx, vy = self._cardinal_vectors.get(self.facing, (0.0, -1.0))
            direction = pygame.math.Vector2(vx, vy)

        self.dash_dir = direction
        self.dash_timer = self.dash_duration
        self.dash_cooldown_left = self.profile.dash_cooldown
        # I-frames: invuln expressa em ms.
        self.invuln = max(self.invuln, int(self.dash_duration * 1000))
        return True

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

    def activate_orbital_lasers(self, _duration: float) -> None:
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

    def activate_chain_shot(self, duration: float | None = None) -> None:
        """Ativa Chain Shot: balas encadeiam raios entre inimigos próximos."""
        d = duration if duration is not None else Config.CHAIN_SHOT_DURATION
        self.chain_shot_timer = max(self.chain_shot_timer, d)

    def activate_repulsion_shield(self, duration: float | None = None) -> None:
        """Ativa Repulsion Shield: campo de força empurra inimigos próximos."""
        d = duration if duration is not None else Config.REPULSION_SHIELD_DURATION
        self.repulsion_shield_timer = max(self.repulsion_shield_timer, d)

    @property
    def has_chain_shot(self) -> bool:
        return self.chain_shot_timer > 0.0

    @property
    def has_repulsion_shield(self) -> bool:
        return self.repulsion_shield_timer > 0.0

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
        """Calcula o centro de um inimigo independente do tipo."""
        if hasattr(enemy, "w") and hasattr(enemy, "h"):
            return float(enemy.x + enemy.w / 2), float(enemy.y + enemy.h / 2)
        elif hasattr(enemy, "radius"):
            return float(enemy.x), float(enemy.y)
        return None

    def _find_nearest_enemy(
        self, from_x: float, from_y: float, entity_manager: "EntityManager"
    ) -> Optional[Any]:
        """Encontra o inimigo mais próximo de uma posição.

        Usa distância ao quadrado internamente para evitar sqrt por inimigo.
        """
        nearest_enemy: Optional[Any] = None
        nearest_dist_sq = float("inf")

        # Buscar em todos os inimigos normais
        for enemy in entity_manager.enemies:
            if getattr(enemy, "dead", False):
                continue
            center = self._get_enemy_center(enemy)
            if center is None:
                continue
            dx = center[0] - from_x
            dy = center[1] - from_y
            dist_sq = dx * dx + dy * dy
            if dist_sq < nearest_dist_sq:
                nearest_dist_sq = dist_sq
                nearest_enemy = enemy

        # Buscar em formações
        for formation in entity_manager.formations:
            for enemy in formation.get_enemies():
                if getattr(enemy, "dead", False):
                    continue
                center = self._get_enemy_center(enemy)
                if center is None:
                    continue
                dx = center[0] - from_x
                dy = center[1] - from_y
                dist_sq = dx * dx + dy * dy
                if dist_sq < nearest_dist_sq:
                    nearest_dist_sq = dist_sq
                    nearest_enemy = enemy

        # Verificar boss
        if entity_manager.boss is not None:
            boss = entity_manager.boss
            if not getattr(boss, "dead", False):
                dx = boss.x + boss.w / 2 - from_x
                dy = boss.y + boss.h / 2 - from_y
                dist_sq = dx * dx + dy * dy
                if dist_sq < nearest_dist_sq:
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
        self.damage_boost_timer = max(0.0, self.damage_boost_timer - dt)
        self.chain_shot_timer = max(0.0, self.chain_shot_timer - dt)
        self.repulsion_shield_timer = max(0.0, self.repulsion_shield_timer - dt)

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

    def _draw_charge_indicator(self, surface: pygame.Surface) -> None:
        """Anel de progresso da carga ao redor da nave (Caçador)."""
        progress = self.charge_shot_progress
        if progress <= 0:
            return

        cx = int(self.x + self.w / 2)
        cy = int(self.y + self.h / 2)
        radius = max(self.w, self.h) // 2 + 10

        # Cor evolui de azul fraco (carga baixa) para ciano brilhante (carga cheia).
        r = int(60 + 60 * progress)
        g = int(180 + 60 * progress)
        b = 255
        color = (r, g, b)

        # Arco de progresso desenhado como segmentos curtos (fallback portável).
        segments = 36
        active_segments = max(1, int(segments * progress))
        for i in range(active_segments):
            angle = -math.pi / 2 + (i / segments) * math.tau
            px = cx + int(math.cos(angle) * radius)
            py = cy + int(math.sin(angle) * radius)
            pygame.draw.circle(surface, color, (px, py), 2)

        # Quando a carga atinge o máximo, pulso branco indica "pronto para soltar".
        if progress >= 1.0:
            pulse = int(2 + 2 * abs(math.sin(self._draw_time * 8)))
            pygame.draw.circle(surface, (255, 255, 255), (cx, cy), radius + 2, pulse)

    def _update_dash_trail(self, dt: float) -> None:
        """Emite partículas durante o dash do Fantasma e decai as existentes."""
        if self.is_dashing:
            cx = self.x + self.w / 2
            cy = self.y + self.h / 2
            # Velocidade contrária à direção do dash (rastro fica para trás).
            back_x = -self.dash_dir.x * random.uniform(60, 160)
            back_y = -self.dash_dir.y * random.uniform(60, 160)
            for _ in range(3):
                self.dash_trail_particles.append(
                    ParticleDict(
                        x=cx + random.uniform(-4, 4),
                        y=cy + random.uniform(-4, 4),
                        vx=back_x + random.uniform(-30, 30),
                        vy=back_y + random.uniform(-30, 30),
                        lifetime=random.uniform(0.18, 0.32),
                        size=random.uniform(3.0, 5.5),
                        color=(160, 220, 255),
                    )
                )

        if not self.dash_trail_particles:
            return

        self.dash_trail_particles = [
            ParticleDict(
                x=p["x"] + p["vx"] * dt,
                y=p["y"] + p["vy"] * dt,
                vx=p["vx"] * 0.92,
                vy=p["vy"] * 0.92,
                lifetime=p["lifetime"] - dt,
                size=max(0.0, p["size"] - dt * 12.0),
                color=p["color"],
            )
            for p in self.dash_trail_particles
            if p["lifetime"] - dt > 0 and p["size"] - dt * 12.0 > 0
        ]

    def _update_repulsion_shield(self, dt: float, entity_manager: Optional["EntityManager"]) -> None:
        if entity_manager is None:
            return

        # 1. Gerenciar o spawn de rastros de vento (streaks) enquanto o power-up estiver ativo
        if self.repulsion_shield_timer > 0.0:
            # Gerar novos rastros continuamente para dar aspecto de vento constante
            spawn_rate = 60 # Muitos rastros por segundo
            for _ in range(int(spawn_rate * dt) + (1 if random.random() < (spawn_rate * dt) % 1 else 0)):
                sprite_w, sprite_h = self._get_rendered_sprite_size()
                angle = random.uniform(0, math.tau)
                self.repulsion_wind_streaks.append({
                    "angle": angle,
                    "dist": random.uniform(5.0, 30.0), # Começa bem perto da nave
                    "speed": random.uniform(900, 1500),
                    "len": random.uniform(40, 90),
                    "alpha": random.randint(120, 200),
                    "cx": self.x + sprite_w / 2,
                    "cy": self.y + sprite_h / 2
                })

            # 2. Aplicar força de "sopro" CONSTANTE em todos os inimigos no raio
            radius = Config.REPULSION_SHIELD_RADIUS * 1.5
            cx = self.x + self.w / 2
            cy = self.y + self.h / 2
            
            enemies = entity_manager.enemy_spatial_grid.query(
                cx - radius, cy - radius, radius * 2, radius * 2
            )

            for enemy in enemies:
                if getattr(enemy, "dead", False): continue
                class_name = enemy.__class__.__name__
                if (hasattr(enemy, "boss") or "Boss" in class_name or "Mountain" in class_name):
                    continue

                center = self._get_enemy_center(enemy)
                ex = center[0] if center is not None else float(getattr(enemy, "x", 0.0))
                ey = center[1] if center is not None else float(getattr(enemy, "y", 0.0))

                dx = ex - cx; dy = ey - cy
                dist_sq = dx * dx + dy * dy
                
                if 0 < dist_sq < radius**2:
                    dist = math.sqrt(dist_sq)
                    # Força constante: quanto mais perto, mais forte
                    blow_force = Config.REPULSION_FORCE * 2.8 * (1.0 - (dist / radius))
                    try:
                        setattr(enemy, "x", getattr(enemy, "x") + (dx / dist) * blow_force * dt)
                        setattr(enemy, "y", getattr(enemy, "y") + (dy / dist) * blow_force * dt)
                    except (AttributeError, TypeError): continue

        # 3. Atualizar rastros visuais (streaks) - decaem independente do timer do power-up
        for s in self.repulsion_wind_streaks[:]:
            s["dist"] += s["speed"] * dt
            s["alpha"] -= 400 * dt 
            if s["alpha"] <= 0 or s["dist"] > Config.REPULSION_SHIELD_RADIUS * 2.5:
                self.repulsion_wind_streaks.remove(s)

    def update(
        self,
        dt: float,
        entity_manager: Optional["EntityManager"] = None,
        is_side_scroll: bool = False,
    ):
        self._draw_time += dt
        self._update_timers(dt)
        self._update_repulsion_shield(dt, entity_manager)
        # Avança dash/cooldown do Fantasma.
        if self.dash_timer > 0.0:
            self.dash_timer = max(0.0, self.dash_timer - dt)
        if self.dash_cooldown_left > 0.0:
            self.dash_cooldown_left = max(0.0, self.dash_cooldown_left - dt)
        # Emite e atualiza partículas do rastro do dash.
        self._update_dash_trail(dt)

        # Avança charge do Caçador (cap em charge_shot_max_time).
        if self.charge_shot_active:
            self.charge_shot_timer = min(
                self.profile.charge_shot_max_time,
                self.charge_shot_timer + dt,
            )
        self._update_orbital_lasers(dt, entity_manager)
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
    ):
        """
        Move a nave baseado nas ações pressionadas.

        Args:
            held_actions: Conjunto de ações sendo pressionadas
            dt: Delta time
            is_side_scroll: Se True, usa movimentação horizontal (left-right com up-down)
                           Se False, usa movimentação vertical (top-down)
            gamepad_vec: Vetor do stick esquerdo do controle (já com dead zone).
                Quando diferente de (0,0) precede mouse_control e teclado,
                permitindo velocidade proporcional à inclinação do stick.
        """
        # Fantasma em dash: força velocidade alta na direção travada e ignora input.
        if self.is_dashing:
            dash_speed = self.speed * self.dash_speed_mult
            self.x += self.dash_dir.x * dash_speed * dt
            self.y += self.dash_dir.y * dash_speed * dt
            self._keep_in_bounds(is_side_scroll)
            return

        # Calcular velocidade atual considerando boost e debuff de congelamento (Nevasca)
        base_speed_multiplier = 1.0
        if self.speed_boost_timer > 0:
            base_speed_multiplier = 1.5
        if self.speed_modifier_timer > 0.0:
            base_speed_multiplier *= 0.3  # Nevasca: 70% de redução
        base_speed_multiplier *= self.wind_slow_factor  # Vento: lentidão adicional

        current_speed = self.speed * base_speed_multiplier
        move_vec = pygame.math.Vector2(0, 0)

        gp_x, gp_y = gamepad_vec
        if gp_x != 0.0 or gp_y != 0.0:
            # Movimento proporcional à inclinação do stick. invert_controls_timer
            # (Toxina) espelha o vetor inteiro.
            if self.invert_controls_timer > 0.0:
                gp_x, gp_y = -gp_x, -gp_y
            move_vec.x = gp_x
            move_vec.y = gp_y
            mag = move_vec.length()
            if mag > 1.0:
                move_vec /= mag
        elif self.mouse_control:
            # Spring-follow: velocidade proporcional à distância ao cursor,
            # escalada por agility_mult do profile. Sem input lag.
            mouse_x, mouse_y = pygame.mouse.get_pos()

            if self.invert_controls_timer > 0.0:
                screen_cx = getattr(Config, "SCREEN_WIDTH", 480) / 2
                screen_cy = getattr(Config, "SCREEN_HEIGHT", 800) / 2
                target_x = 2 * screen_cx - mouse_x
                target_y = 2 * screen_cy - mouse_y
            else:
                target_x = mouse_x
                target_y = mouse_y

            # Reaction delay: registrar posição atual e buscar posição atrasada.
            delay = self.profile.reaction_delay
            if delay > 0.0:
                now = time.time()
                history = self._mouse_history
                history.append((target_x, target_y, now))
                # Descartar entradas vencidas — popleft O(1) por entrada.
                cutoff = now - (delay + 0.1)
                while history and history[0][2] < cutoff:
                    history.popleft()
                # Buscar a posição mais próxima de `delay` segundos atrás.
                for x, y, t in reversed(history):
                    if now - t >= delay:
                        target_x, target_y = x, y
                        break

            ship_center_x = self.x + self.w / 2
            ship_center_y = self.y + self.h / 2

            dx = target_x - ship_center_x
            dy = target_y - ship_center_y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist >= MOUSE_DEAD_ZONE:
                # Sensitivity proporcional à distância, escalada por agility_mult.
                # Resgata a sensação "flutuante" do código original:
                # velocidade = distância × sensitivity × agility × current_speed.
                sensitivity = MOUSE_BASE_STIFFNESS * 0.002 * self.profile.agility_mult
                move_vec.x = dx * sensitivity
                move_vec.y = dy * sensitivity
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

        self._keep_in_bounds(is_side_scroll)

    def should_auto_fire(self) -> bool:
        """Retorna True se deve disparar automaticamente neste frame."""
        return self.auto_fire and self.auto_fire_timer == 0.0

    def _keep_in_bounds(self, _is_side_scroll: bool = False):
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
        if not self.visible:
            return

        # Rastro do dash: desenhado antes do blink de invuln para garantir visibilidade
        # mesmo quando a nave em si está piscando durante os i-frames.
        for p in self.dash_trail_particles:
            pygame.draw.circle(
                surface, p["color"], (int(p["x"]), int(p["y"])), int(p["size"])
            )

        # Indicador de carga do Caçador: anel de progresso ao redor da nave.
        if self.charge_shot_active:
            self._draw_charge_indicator(surface)

        if self.invuln > 0 and int(self.invuln / 100) % 2 == 0:
            return

        # Desenhar partículas de thruster (atrás da nave)
        for p in self.thruster_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])

        # Desenhar escudo (se ativo)
        if self.has_shield:
            # Efeito pulsante
            pulse = abs((self._draw_time * 4) % 2 - 1)  # Oscila entre 0 e 1

            sprite_w, sprite_h = self._ship_image_size
            center_x = int(self.x + sprite_w / 2)
            center_y = int(self.y + sprite_h / 2)
            base_radius = max(sprite_w, sprite_h) / 2 + 8

            radius = int(base_radius + pulse * 4)

            # Círculo azul semi-transparente (desenhar múltiplas camadas para simular transparência)
            shield_color = (100, 150, 255)
            for i in range(3):
                pygame.draw.circle(
                    surface, shield_color, (center_x, center_y), radius - i, 2
                )

        # Repulsion Shield (Vento)
        if self.has_repulsion_shield:
            sprite_w, sprite_h = self._ship_image_size
            cx = int(self.x + sprite_w / 2)
            cy = int(self.y + sprite_h / 2)

            # Visual suave de brilho no centro durante o sopro
            pulse = abs((self._draw_time * 6) % 2 - 1)
            glow_r = 30 + int(pulse * 10)

            # Surface cacheada (módulo) — sem alocação por frame.
            glow_surf = _get_repulsion_glow(glow_r)
            surface.blit(glow_surf, (cx - glow_r, cy - glow_r))

        # Chain Shot (Efeito Estático/Elétrico)
        if self.has_chain_shot:
            sprite_w, sprite_h = self._cached_sprite_size
            cx, cy = int(self.x + sprite_w / 2), int(self.y + sprite_h / 2)
            radius = max(sprite_w, sprite_h) // 2 + 5

            # Apenas em alguns frames para efeito de flickering (estático)
            if random.random() < 0.8:
                # Locals — atributos/globals viram lookup mais barato em loops quentes.
                cos = math.cos
                sin = math.sin
                uniform = random.uniform
                choice = random.choice
                draw_lines = pygame.draw.lines
                colors_pool = _CHAIN_SPARK_COLORS
                tau = math.tau

                num_arcs = random.randint(2, 4)
                for _ in range(num_arcs):
                    angle1 = uniform(0, tau)
                    angle2 = angle1 + uniform(0.2, 0.8)
                    mid_angle = (angle1 + angle2) * 0.5
                    mid_radius = radius + uniform(2, 8)

                    p1 = (cx + cos(angle1) * radius, cy + sin(angle1) * radius)
                    p_mid = (cx + cos(mid_angle) * mid_radius, cy + sin(mid_angle) * mid_radius)
                    p2 = (cx + cos(angle2) * radius, cy + sin(angle2) * radius)

                    draw_lines(surface, choice(colors_pool), False, [p1, p_mid, p2], 1)

        # Rastros de Vento Constante (Omnidirecional)
        if self.repulsion_wind_streaks:
            cos = math.cos
            sin = math.sin
            draw_line = pygame.draw.line
            for s in self.repulsion_wind_streaks:
                angle = s["angle"]
                dist = s["dist"]
                length = s["len"]
                ca = cos(angle)
                sa = sin(angle)
                base_x = s["cx"]
                base_y = s["cy"]
                start_x = base_x + ca * dist
                start_y = base_y + sa * dist
                end_x = base_x + ca * (dist + length)
                end_y = base_y + sa * (dist + length)
                draw_line(
                    surface,
                    (255, 255, 255, int(s["alpha"])),
                    (start_x, start_y),
                    (end_x, end_y),
                    1,
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
            current_time = self._draw_time

            # Tamanho do sprite — cache não-rotacionado para centralização.
            sprite_w, sprite_h = self._ship_image_size

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
