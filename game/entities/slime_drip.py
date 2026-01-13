import pygame
import random
import math
from typing import List, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass

from ..core.config import config as Config

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


class SlimeDripParticle:
    """Partícula pequena que se despende da gota principal."""

    def __init__(self, x: float, y: float, color: tuple[int, int, int, int]):
        self.x: float = x
        self.y: float = y
        self.color: tuple[int, int, int, int] = color

        # Tamanho dinâmico
        self.size_start: float = Config.SLIME_DRIP_DETACH_PARTICLE_SIZE_START
        self.size_end: float = Config.SLIME_DRIP_DETACH_PARTICLE_SIZE_END
        self.current_size: float = self.size_start

        # Tempo de vida
        self.lifetime: float = Config.SLIME_DRIP_DETACH_PARTICLE_LIFETIME
        self.age: float = 0.0

        # Movimento
        angle = random.uniform(0, 2 * math.pi)  # Ângulo aleatório
        speed = random.uniform(
            Config.SLIME_DRIP_DETACH_PARTICLE_SPEED_MIN,
            Config.SLIME_DRIP_DETACH_PARTICLE_SPEED_MAX,
        )
        self.vx: float = speed * math.cos(angle)
        self.vy: float = speed * math.sin(angle)

        # Estado
        self.active: bool = True

    def update(self, dt: float) -> None:
        """Atualiza a partícula."""
        if not self.active:
            return

        self.age += dt

        # Calcular tamanho atual (interpola linearmente)
        t = min(self.age / self.lifetime, 1.0)  # 0.0 a 1.0
        self.current_size = self.size_start + (self.size_end - self.size_start) * t

        # Movimento
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Desativar quando tempo acabar ou tamanho muito pequeno
        if self.age >= self.lifetime or self.current_size <= 0.05:
            self.active = False


from ..core.spatial_grid import SpatialGrid


@dataclass
class DripParams:
    """Parâmetros calculados para uma gota baseados em sua escala."""

    scale: float
    radius: float
    damage: int
    speed_x: float
    speed_y: float
    gravity: float
    color: Tuple[int, int, int, int]

    @classmethod
    def generate(cls, scale: float | None = None) -> "DripParams":
        """Gera parâmetros aleatórios para uma gota."""
        if scale is None:
            scale = random.uniform(0.5, 1.5)

        radius = Config.SLIME_DRIP_RADIUS_MAX * scale
        damage = max(1, int(scale * 2))

        # Física melhorada: gotas maiores caem mais devagar (mais realista)
        # Usa raiz quadrada para suavizar o efeito
        size_factor = (scale / 1.0) ** 0.5
        base_speed = random.uniform(100.0, 300.0)
        speed_multiplier = 1.0 / size_factor  # Inversão: maior = mais lento

        speed_x = random.uniform(-20.0, 20.0) * speed_multiplier
        speed_y = base_speed * speed_multiplier
        gravity = 200.0 * speed_multiplier

        color = random.choice(Config.SLIME_DRIP_COLORS)

        return cls(scale, radius, damage, speed_x, speed_y, gravity, color)


class SlimeDrip:
    """Gota de slime com física e renderização otimizadas."""

    __slots__ = (
        "active",
        "dead",
        "x",
        "y",
        "params",
        "speed_x",
        "speed_y",
        "effect_width",
        "effect_height",
        "_cached_int_pos",
        "pulse_timer",
        "pulse_radius",
        "detach_particles",
        "detach_timer",
        "is_homing",
        "homing_locked",  # NOVO: flag para indicar se travou a direção
        "target_x",
        "target_y",
        "homing_speed",
        "homing_timer",
        "max_speed",
        "acceleration",
        "slow_timer",  # Sistema de slow (lentidão) causado por balas
        "slow_factor",  # Fator de multiplicação da velocidade (1.0 = normal, 0.0 = parado)
    )

    def __init__(self):
        self.active: bool = False
        self.dead: bool = True
        self.x: float = 0.0
        self.y: float = 0.0
        self.speed_x: float = 0.0
        self.speed_y: float = 0.0
        self.effect_width: int = 800
        self.effect_height: int = 600
        self.params: DripParams = DripParams.generate()
        self._cached_int_pos: Tuple[int, int] = (0, 0)

        # Sistema de pulso sutil
        self.pulse_timer: float = random.uniform(0, Config.SLIME_DRIP_PULSE_PERIOD)
        self.pulse_radius: float = self.params.radius

        # Sistema de partículas desprendidas
        self.detach_particles: List[SlimeDripParticle] = []
        self.detach_timer: float = 0.0

        # Modo homing
        self.is_homing: bool = False
        self.homing_locked: bool = False  # NOVO
        self.target_x: float = 0.0
        self.target_y: float = 0.0
        self.homing_speed: float = 300.0
        self.homing_timer: float = 0.0
        self.max_speed: float = Config.SLIME_DRIP_HOMING_MAX_SPEED
        self.acceleration: float = Config.SLIME_DRIP_HOMING_ACCELERATION

        # Sistema de slow (lentidão) causado por balas
        self.slow_timer: float = 0.0  # Tempo restante de slow em segundos
        self.slow_factor: float = (
            1.0  # Fator de multiplicação da velocidade (1.0 = normal, 0.0 = parado)
        )

    def reset(self, x: float, y: float, effect_width: int, effect_height: int) -> None:
        """Reseta a gota para reutilização no pool."""
        self.active = True
        self.dead = False
        self.x = x
        self.y = y
        self.effect_width = effect_width
        self.effect_height = effect_height

        # Gera novos parâmetros
        self.params = DripParams.generate()
        self.speed_x = self.params.speed_x
        self.speed_y = self.params.speed_y
        self._cached_int_pos = (int(x), int(y))

        # Reset pulso
        self.pulse_timer = random.uniform(0, Config.SLIME_DRIP_PULSE_PERIOD)
        self.pulse_radius = self.params.radius

        # Reset partículas desprendidas
        self.detach_particles.clear()
        self.detach_timer = 0.0

        # Reset homing
        self.is_homing = False
        self.homing_locked = False  # NOVO
        self.target_x = 0.0
        self.target_y = 0.0
        self.homing_timer = 0.0

        # Reset slow
        self.slow_timer = 0.0
        self.slow_factor = 1.0

    def update(self, dt: float) -> None:
        """Atualiza física da gota."""
        if not self.active or self.dead:
            return

        # Aplicar gravidade ou homing
        if self.is_homing:
            # Timer para homing
            self.homing_timer += dt

            # Verificar se deve destravar (por tempo ou distância)
            if not self.homing_locked:
                distance_to_target = math.sqrt(
                    (self.target_x - self.x) ** 2 + (self.target_y - self.y) ** 2
                )

                # Destravar se chegou perto OU se passou do tempo limite
                if (
                    distance_to_target <= Config.SLIME_DRIP_HOMING_DISENGAGE_DISTANCE
                    or self.homing_timer > Config.SLIME_DRIP_HOMING_DISENGAGE_TIME
                ):
                    self.homing_locked = True  # Trava a direção atual

            # Verificar timeout total
            if self.homing_timer > Config.SLIME_DRIP_HOMING_MAX_DURATION:
                self.dead = True
                self.active = False
                return

            # Se não travou ainda, continua perseguindo
            if not self.homing_locked:
                self._update_guidance(dt)
            # Se travou, apenas continua com velocidade atual (não atualiza direção)
        else:
            # Gravidade normal
            self.speed_y += self.params.gravity * dt

        # Aplicar slow (lentidão) se ativo
        if self.slow_timer > 0:
            self.slow_timer -= dt
            if self.slow_timer < 0:
                self.slow_timer = 0.0
                self.slow_factor = 1.0  # Reset para velocidade normal
        else:
            self.slow_factor = 1.0  # Velocidade normal

        # Movimento (aplicando slow)
        self.x += self.speed_x * dt * self.slow_factor
        self.y += self.speed_y * dt * self.slow_factor

        # Cache posição inteira para renderização
        self._cached_int_pos = (int(self.x), int(self.y))

        # Sistema de pulso sutil
        self.pulse_timer += dt
        if self.pulse_timer >= Config.SLIME_DRIP_PULSE_PERIOD:
            self.pulse_timer = 0.0

        # Calcula raio pulsante usando seno para movimento suave
        pulse_ratio = (
            math.sin(self.pulse_timer / Config.SLIME_DRIP_PULSE_PERIOD * 2 * math.pi)
            + 1
        ) / 2
        self.pulse_radius = self.params.radius * (
            1.0 + Config.SLIME_DRIP_PULSE_AMPLITUDE * (pulse_ratio - 0.5) * 2
        )

        # Sistema de partículas desprendidas - produção contínua
        self.detach_timer += dt
        if (
            self.detach_timer >= Config.SLIME_DRIP_DETACH_PARTICLE_SPAWN_INTERVAL
        ):  # Intervalo consistente
            self.detach_timer = 0.0
            # Sempre spawnar partícula (produção contínua)
            if (
                len(self.detach_particles)
                < Config.SLIME_DRIP_DETACH_PARTICLE_MAX_PER_DRIP
            ):
                self._spawn_detach_particle()

        # Atualizar partículas desprendidas
        self.detach_particles = [p for p in self.detach_particles if p.active]
        for particle in self.detach_particles:
            particle.update(dt)

        # Verificação de limites - morte imediata se sair da tela
        margin = Config.SLIME_DRIP_DEATH_MARGIN

        # Morte imediata se sair da tela (todas as gotas, incluindo homing)
        if (
            self.y > self.effect_height + margin
            or self.x < -margin
            or self.x > self.effect_width + margin
        ):
            self.dead = True
            self.active = False

    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica colisão circular otimizada com o jogador."""
        if not self.active or self.dead:
            return False

        # Distância ao centro do jogador (squared para evitar sqrt)
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance_squared = dx * dx + dy * dy

        # Raio total (jogador + gota)
        total_radius = player_rect.width * 0.5 + self.params.radius
        return distance_squared <= total_radius * total_radius

    def _spawn_detach_particle(self) -> None:
        """Cria uma partícula desprendida da gota."""
        # Posição ligeiramente offset da gota
        offset_angle = random.uniform(0, 2 * math.pi)
        offset_distance = random.uniform(0, self.params.radius * 0.5)
        particle_x = self.x + math.cos(offset_angle) * offset_distance
        particle_y = self.y + math.sin(offset_angle) * offset_distance

        # Criar partícula
        particle = SlimeDripParticle(particle_x, particle_y, self.params.color)
        self.detach_particles.append(particle)

    def _update_guidance(self, dt: float) -> None:
        """Update the guidance system to steer towards target."""
        # Calcular direção para o alvo
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance > 0:
            # Direção desejada (normalizada)
            desired_dx = dx / distance
            desired_dy = dy / distance

            # Acelerar em direção ao alvo
            current_speed = math.sqrt(
                self.speed_x * self.speed_x + self.speed_y * self.speed_y
            )
            target_speed = min(current_speed + self.acceleration * dt, self.max_speed)

            # Aplicar nova velocidade com inércia/suavização
            blend_factor = (
                Config.SLIME_DRIP_HOMING_BLEND_FACTOR
            )  # Quanto menor, mais suave (limita ângulo de rotação)
            self.speed_x = (
                self.speed_x * (1 - blend_factor)
                + desired_dx * target_speed * blend_factor
            )
            self.speed_y = (
                self.speed_y * (1 - blend_factor)
                + desired_dy * target_speed * blend_factor
            )

    def apply_slow(
        self, slow_duration: float = 0.5, max_slow_duration: float = 2.0
    ) -> None:
        """Aplica slow (lentidão) à gota quando atingida por uma bala.

        Args:
            slow_duration: Duração do slow em segundos (padrão 0.5s)
            max_slow_duration: Duração máxima acumulada de slow (padrão 2.0s)
        """
        # Acumular slow, mas limitar ao máximo
        self.slow_timer = min(self.slow_timer + slow_duration, max_slow_duration)

        # Calcular factor de slow baseado no tempo restante
        # Slow começa em 0.3 (30% da velocidade) e vai voltando para 1.0
        self.slow_factor = 0.3 + (
            0.7 * (1.0 - min(self.slow_timer / max_slow_duration, 1.0))
        )

    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Retorna bounds (x, y, w, h) para spatial grid."""
        r = self.params.radius
        return (self.x - r, self.y - r, r * 2, r * 2)

    def get_rect(self) -> pygame.Rect:
        """Retorna um retângulo para colisão com bullets (similar ao BossSquare)."""
        r = self.params.radius
        return pygame.Rect(self.x - r, self.y - r, r * 2, r * 2)

    def get_cached_int_pos(self) -> Tuple[int, int]:
        """Retorna a posição inteira cacheada para renderização."""
        return self._cached_int_pos


class SlimeDripPool:
    """Pool Pattern otimizado para gotas de slime com spatial grid."""

    def __init__(
        self, initial_size: int = 20, effect_width: int = 1600, effect_height: int = 900
    ):
        self.pool: List[SlimeDrip] = [SlimeDrip() for _ in range(initial_size)]
        self.active: List[SlimeDrip] = []
        self._pool_index: int = 0  # Índice para rotação circular no pool

        # Dimensões do efeito
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height

        # Spatial grid para otimizar colisões
        self.spatial_grid: SpatialGrid[SlimeDrip] = SpatialGrid(
            cell_size=Config.SLIME_DRIP_SPATIAL_GRID_CELL_SIZE
        )

        # Sistema de partículas órfãs (partículas que sobreviveram à gota principal)
        self.orphan_particles: List[SlimeDripParticle] = []
        self.max_orphan_particles: int = (
            Config.SLIME_DRIP_MAX_ORPHAN_PARTICLES
        )  # Limitar para performance

    def get(
        self, x: float, y: float, effect_width: int, effect_height: int
    ) -> SlimeDrip:
        """Obtém uma gota do pool (busca circular otimizada)."""
        pool_size = len(self.pool)

        # Busca circular a partir do último índice usado
        for i in range(pool_size):
            idx = (self._pool_index + i) % pool_size
            drip = self.pool[idx]
            if not drip.active:
                drip.reset(x, y, effect_width, effect_height)
                self.active.append(drip)
                self._pool_index = (idx + 1) % pool_size
                return drip

        # Pool cheio: cria nova gota
        drip = SlimeDrip()
        drip.reset(x, y, effect_width, effect_height)
        self.pool.append(drip)
        self.active.append(drip)
        self._pool_index = 0
        return drip

    def release(self, drip: SlimeDrip) -> None:
        """Libera uma gota de volta ao pool, preservando suas partículas ativas."""
        # Transferir partículas ativas para órfãs antes de liberar
        for particle in drip.detach_particles:
            if particle.active:
                self.orphan_particles.append(particle)
        drip.detach_particles.clear()

        drip.active = False
        drip.dead = True
        if drip in self.active:
            self.active.remove(drip)

    def update(self, dt: float) -> None:
        """Atualiza todas as gotas ativas e reconstrói spatial grid."""
        # Atualizar todas as gotas
        to_release: List[SlimeDrip] = []
        for drip in self.active:
            drip.update(dt)
            if drip.dead:
                to_release.append(drip)

        # Liberar gotas mortas
        for drip in to_release:
            self.release(drip)

        # Atualizar partículas órfãs
        self.orphan_particles = [p for p in self.orphan_particles if p.active]
        for particle in self.orphan_particles:
            particle.update(dt)
            # Verificar se partícula órfã saiu da tela
            margin = Config.SLIME_DRIP_DEATH_MARGIN
            if self._is_out_of_bounds(particle.x, particle.y, margin):
                particle.active = False

        # Limitar número de partículas órfãs para performance (manter apenas as mais recentes)
        if len(self.orphan_particles) > self.max_orphan_particles:
            # Remover as mais velhas (primeiras da lista)
            excess = len(self.orphan_particles) - self.max_orphan_particles
            self.orphan_particles = self.orphan_particles[excess:]

        # Reconstruir spatial grid se houver gotas ativas
        if self.active:
            self.spatial_grid.clear()
            batch_data: List[Tuple[SlimeDrip, float, float, float, float]] = []
            for drip in self.active:
                bounds: Tuple[float, float, float, float] = drip.get_bounds()
                x, y, w, h = bounds
                batch_data.append((drip, x, y, w, h))
            self.spatial_grid.insert_batch(batch_data)

    def _is_out_of_bounds(self, x: float, y: float, margin: int) -> bool:
        """Verifica se posição está fora dos limites."""
        return (
            x < -margin
            or x > self.effect_width + margin
            or y < -margin
            or y > self.effect_height + margin
        )

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha as gotas usando batch rendering otimizado e LOD para performance máxima."""
        if not self.active and not self.orphan_particles:
            return

        # Culling básico: não desenhar gotas fora da tela + margem
        screen_width, screen_height = surface.get_size()
        cull_margin = 150  # Margem maior para performance

        # LOD thresholds
        min_particle_size = 0.1  # Partículas muito pequenas são ignoradas
        min_drip_size = 0.5  # Gotas muito pequenas são ignoradas

        # Batch rendering: coletar todos os círculos visíveis para desenhar de uma vez
        filled_circles: List[Tuple[Tuple[int, int, int, int], Tuple[int, int], int]] = (
            []
        )  # Gotas preenchidas
        outline_circles: List[
            Tuple[Tuple[int, int, int, int], Tuple[int, int], int]
        ] = []  # Partículas órfãs (bordas apenas)

        for drip in self.active:
            if not drip.active or drip.dead:
                continue

            # LOD: pular gotas muito pequenas
            if drip.params.radius < min_drip_size:
                continue

            # Culling: pular gotas completamente fora da tela
            drip_x, drip_y = drip.x, drip.y
            drip_radius = drip.pulse_radius
            if (
                drip_x + drip_radius < -cull_margin
                or drip_x - drip_radius > screen_width + cull_margin
                or drip_y + drip_radius < -cull_margin
                or drip_y - drip_radius > screen_height + cull_margin
            ):
                continue

            # Adicionar a gota principal (preenchida)
            color: Tuple[int, int, int, int] = drip.params.color
            center: Tuple[int, int] = drip.get_cached_int_pos()
            radius: int = int(drip.pulse_radius)
            filled_circles.append((color, center, radius))

            # Adicionar partículas desprendidas (bordas apenas) - com LOD
            for particle in drip.detach_particles:
                if (
                    particle.active
                    and particle.current_size > min_particle_size
                    and particle.x > -cull_margin
                    and particle.x < screen_width + cull_margin
                    and particle.y > -cull_margin
                    and particle.y < screen_height + cull_margin
                ):
                    particle_radius: int = max(1, int(particle.current_size * 50))
                    particle_center: Tuple[int, int] = (
                        int(particle.x),
                        int(particle.y),
                    )
                    particle_color: Tuple[int, int, int, int] = particle.color
                    outline_circles.append(
                        (particle_color, particle_center, particle_radius)
                    )

        # Adicionar partículas órfãs (bordas apenas) - com LOD
        for particle in self.orphan_particles:
            if (
                particle.active
                and particle.current_size > min_particle_size
                and particle.x > -cull_margin
                and particle.x < screen_width + cull_margin
                and particle.y > -cull_margin
                and particle.y < screen_height + cull_margin
            ):
                particle_radius: int = max(1, int(particle.current_size * 50))
                particle_center: Tuple[int, int] = (int(particle.x), int(particle.y))
                particle_color: Tuple[int, int, int, int] = particle.color
                outline_circles.append(
                    (particle_color, particle_center, particle_radius)
                )

        # Desenhar círculos preenchidos (gotas principais) - super batch otimizado
        if filled_circles:
            # Super batch: agrupar por (cor, raio) para reduzir state changes drasticamente
            super_groups: dict[
                Tuple[Tuple[int, int, int, int], int], List[Tuple[int, int]]
            ] = {}
            for color, center, radius in filled_circles:
                key = (color, radius)
                if key not in super_groups:
                    super_groups[key] = []
                super_groups[key].append(center)

            # Draw super batched - uma chamada por combinação cor/raio
            for (color, radius), centers in super_groups.items():
                # Para muitos círculos, fazer em lotes menores para evitar overflow
                batch_size = 100  # Aumentado para melhor performance
                for i in range(0, len(centers), batch_size):
                    batch_centers = centers[i : i + batch_size]
                    for center in batch_centers:
                        pygame.draw.circle(surface, color, center, radius)

        # Desenhar círculos com bordas apenas (partículas órfãs) - super batch otimizado
        if outline_circles:
            # Mesmo super batch para bordas
            super_groups: dict[
                Tuple[Tuple[int, int, int, int], int], List[Tuple[int, int]]
            ] = {}
            for color, center, radius in outline_circles:
                key = (color, radius)
                if key not in super_groups:
                    super_groups[key] = []
                super_groups[key].append(center)

            # Draw super batched com bordas
            for (color, radius), centers in super_groups.items():
                batch_size = 100
                for i in range(0, len(centers), batch_size):
                    batch_centers = centers[i : i + batch_size]
                    for center in batch_centers:
                        pygame.draw.circle(
                            surface, color, center, radius, 1
                        )  # width=1 para borda apenas

    def check_collisions(
        self, player_rect: pygame.Rect, entity_manager: Optional["EntityManager"] = None
    ) -> int:
        """Verifica colisões usando spatial grid (muito mais rápido)."""
        if not self.active:
            return 0

        # Query spatial grid para candidatos próximos
        candidates = self.spatial_grid.query_from_rect(player_rect)

        total_damage = 0
        to_release: List[SlimeDrip] = []

        for drip in candidates:
            if drip.collides_with_player(player_rect):
                total_damage += drip.params.damage

                # Spawnar explosão usando a cor da gota
                if entity_manager:
                    entity_manager.spawn_explosion(
                        drip.x,
                        drip.y,
                        size=int(drip.params.radius),
                        custom_color=drip.params.color,
                    )

                to_release.append(drip)

        # Liberar gotas que colidiram (agora transfere partículas automaticamente)
        for drip in to_release:
            self.release(drip)

        return total_damage

    def clear_active(self) -> None:
        """Remove todas as gotas ativas, preservando suas partículas órfãs."""
        for drip in self.active[:]:
            self.release(drip)
        self.spatial_grid.clear()
        # Não limpar órfãs - elas devem sobreviver

    def get_active_count(self) -> int:
        """Retorna quantidade de gotas ativas."""
        return len(self.active)

    def get_pool_size(self) -> int:
        """Retorna tamanho total do pool."""
        return len(self.pool)


class SlimeDrippingEffect:
    """Efeito de gotas de slime caindo do boss."""

    __slots__ = (
        "effect_width",
        "effect_height",
        "drip_pool",
        "spawn_timer",
        "spawn_interval",
        "max_drips",
        "homing_mode",
        "homing_target_x",
        "homing_target_y",
        "spawn_enabled",
        "target_update_timer",
        "target_update_interval",
        # NOVO: Sistema dual
        "dual_mode",  # Flag para modo dual
        "homing_spawn_timer",  # Timer separado para homing
        "max_homing_drips",  # Máximo de homing no dual
        "homing_spawn_interval_dual",  # Intervalo homing no dual
    )

    def __init__(
        self, effect_width: int, effect_height: int, difficulty_multiplier: float = 1.0
    ):
        self.effect_width = effect_width
        self.effect_height = effect_height

        # Pool com tamanho inicial generoso
        initial_pool_size = int(
            Config.SLIME_DRIP_MAX_ACTIVE * Config.SLIME_DRIP_POOL_SIZE_MULTIPLIER
        )
        self.drip_pool = SlimeDripPool(
            initial_size=initial_pool_size,
            effect_width=effect_width,
            effect_height=effect_height,
        )

        # Spawn settings
        self.spawn_timer = 0.0
        self.spawn_interval = Config.SLIME_DRIP_SPAWN_INTERVAL / difficulty_multiplier
        self.max_drips = Config.SLIME_DRIP_MAX_ACTIVE

        # Spawn control
        self.spawn_enabled = True

        # Homing mode
        self.homing_mode = False
        self.homing_target_x = 0.0
        self.homing_target_y = 0.0

        # Target update delay
        self.target_update_timer = 0.0
        self.target_update_interval = (
            Config.SLIME_DRIP_HOMING_TARGET_UPDATE_INTERVAL
        )  # Atualizar target a cada intervalo

        # NOVO: Sistema dual
        self.dual_mode = False
        self.homing_spawn_timer = 0.0
        self.max_homing_drips = 0
        self.homing_spawn_interval_dual = 1.0

    def update(
        self,
        dt: float,
        boss_x: float,
        boss_y: float,
        boss_width: int,
        player_x: float,
        player_y: float,
        entity_manager: Optional["EntityManager"] = None,
    ) -> None:
        """Atualiza todas as gotas e spawna novas."""
        # Atualizar pool
        self.drip_pool.update(dt)

        # Atualizar targets para gotas homing existentes
        if self.homing_mode or self.dual_mode:
            self.target_update_timer += dt
            if self.target_update_timer >= self.target_update_interval:
                self.target_update_timer = 0.0
                for drip in self.drip_pool.active:
                    if drip.is_homing:
                        offset = Config.SLIME_DRIP_HOMING_AIM_OFFSET
                        drip.target_x = player_x + random.uniform(-offset, offset)
                        drip.target_y = player_y + random.uniform(-offset, offset)

        if not self.spawn_enabled:
            return

        # MODO DUAL: Spawnar ambos os tipos
        if self.dual_mode:
            # 1. Spawnar drips normais (do boss)
            self.spawn_timer += dt
            if (
                self.spawn_timer >= self.spawn_interval
                and self._count_normal_drips() < self.max_drips
            ):
                self.spawn_timer = 0.0
                self._spawn_normal_drip(boss_x, boss_y, boss_width, entity_manager)

            # 2. Spawnar drips homing (do topo)
            self.homing_spawn_timer += dt
            if (
                self.homing_spawn_timer >= self.homing_spawn_interval_dual
                and self._count_homing_drips() < self.max_homing_drips
            ):
                self.homing_spawn_timer = 0.0
                self._spawn_homing_drip(player_x, player_y, entity_manager)

        # MODO NORMAL/HOMING: Comportamento atual
        else:
            self.spawn_timer += dt
            if (
                self.spawn_timer >= self.spawn_interval
                and self.drip_pool.get_active_count() < self.max_drips
            ):
                self.spawn_timer = 0.0
                self._spawn_drip(boss_x, boss_y, boss_width, entity_manager)

    def _spawn_drip(
        self,
        boss_x: float,
        boss_y: float,
        boss_width: int,
        entity_manager: Optional["EntityManager"] = None,
    ) -> None:
        """Spawna uma gota aleatoriamente acima do boss ou no topo se homing."""
        if self.homing_mode:
            x = random.uniform(0, self.effect_width)
            y = Config.SLIME_DRIP_HOMING_SPAWN_Y_OFFSET  # Topo da tela
        else:
            x = boss_x + random.uniform(0, boss_width)
            y = boss_y + Config.SLIME_DRIP_BOSS_SPAWN_Y_OFFSET  # pixels acima do boss
        drip = self.drip_pool.get(x, y, self.effect_width, self.effect_height)
        if self.homing_mode:
            drip.is_homing = True
            drip.target_x = self.homing_target_x
            drip.target_y = self.homing_target_y
            # Forçar tamanho pequeno para homing drips
            drip.params.scale = random.uniform(
                Config.SLIME_DRIP_HOMING_SCALE_MIN, Config.SLIME_DRIP_HOMING_SCALE_MAX
            )
            drip.params.radius = Config.SLIME_DRIP_RADIUS_MAX * drip.params.scale
            drip.params.damage = max(1, int(drip.params.scale * 2))
            drip.pulse_radius = drip.params.radius  # Atualizar para evitar blink

        # Adicionar ao entity_manager se fornecido
        if entity_manager is not None:
            entity_manager.slime_drips.append(drip)

    def _count_normal_drips(self) -> int:
        """Conta quantas gotas normais estão ativas."""
        return sum(1 for drip in self.drip_pool.active if not drip.is_homing)

    def _count_homing_drips(self) -> int:
        """Conta quantas gotas homing estão ativas."""
        return sum(1 for drip in self.drip_pool.active if drip.is_homing)

    def _spawn_normal_drip(
        self,
        boss_x: float,
        boss_y: float,
        boss_width: int,
        entity_manager: Optional["EntityManager"] = None,
    ) -> None:
        """Spawna uma gota normal (caindo do boss)."""
        x = boss_x + random.uniform(0, boss_width)
        y = boss_y + Config.SLIME_DRIP_BOSS_SPAWN_Y_OFFSET
        drip = self.drip_pool.get(x, y, self.effect_width, self.effect_height)
        # Gota normal não tem homing
        drip.is_homing = False

        # Adicionar ao entity_manager se fornecido
        if entity_manager is not None:
            entity_manager.slime_drips.append(drip)

    def _spawn_homing_drip(
        self,
        player_x: float,
        player_y: float,
        entity_manager: Optional["EntityManager"] = None,
    ) -> None:
        """Spawna uma gota homing (do topo)."""
        x = random.uniform(0, self.effect_width)
        y = Config.SLIME_DRIP_HOMING_SPAWN_Y_OFFSET
        drip = self.drip_pool.get(x, y, self.effect_width, self.effect_height)

        # Configurar homing
        drip.is_homing = True
        offset = Config.SLIME_DRIP_HOMING_AIM_OFFSET
        drip.target_x = player_x + random.uniform(-offset, offset)
        drip.target_y = player_y + random.uniform(-offset, offset)

        # Tamanho pequeno para homing
        drip.params.scale = random.uniform(
            Config.SLIME_DRIP_HOMING_SCALE_MIN, Config.SLIME_DRIP_HOMING_SCALE_MAX
        )
        drip.params.radius = Config.SLIME_DRIP_RADIUS_MAX * drip.params.scale
        drip.params.damage = max(1, int(drip.params.scale * 2))
        drip.pulse_radius = drip.params.radius

        # Adicionar ao entity_manager se fornecido
        if entity_manager is not None:
            entity_manager.slime_drips.append(drip)

    def set_dual_mode(
        self,
        enabled: bool,
        max_normal: int,
        normal_interval: float,
        max_homing: int,
        homing_interval: float,
        target_x: float,
        target_y: float,
    ) -> None:
        """Configura modo dual (drips normais + homing simultâneos)."""
        self.dual_mode = enabled

        if enabled:
            # Configurar limites separados
            self.max_drips = max_normal
            self.spawn_interval = normal_interval
            self.max_homing_drips = max_homing
            self.homing_spawn_interval_dual = homing_interval

            # Homing sempre ativo no dual
            self.homing_mode = True
            self.homing_target_x = target_x
            self.homing_target_y = target_y
        else:
            # Resetar para modo single
            self.homing_mode = False

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha todas as gotas e rastros."""
        self.drip_pool.draw(surface)

    def check_collisions(
        self, player_rect: pygame.Rect, entity_manager: Optional["EntityManager"] = None
    ) -> int:
        """Verifica colisões com o jogador usando spatial grid."""
        return self.drip_pool.check_collisions(player_rect, entity_manager)

    def set_homing_mode(self, enabled: bool, target_x: float, target_y: float) -> None:
        """Ativa ou desativa o modo homing para as gotas."""
        self.homing_mode = enabled
        self.homing_target_x = target_x
        self.homing_target_y = target_y

        # Atualizar parâmetros de spawn baseado no modo
        if enabled:
            self.max_drips = Config.SLIME_DRIP_HOMING_MAX_ACTIVE
            self.spawn_interval = Config.SLIME_DRIP_HOMING_SPAWN_INTERVAL
        else:
            self.max_drips = Config.SLIME_DRIP_MAX_ACTIVE
            self.spawn_interval = Config.SLIME_DRIP_SPAWN_INTERVAL

    def set_spawn_enabled(self, enabled: bool) -> None:
        """Ativa ou desativa o spawn de novas gotas."""
        self.spawn_enabled = enabled
