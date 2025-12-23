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
        angle = random.uniform(0, 2 * 3.14159)  # Ângulo aleatório
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

    def update(self, dt: float) -> None:
        """Atualiza física da gota."""
        if not self.active or self.dead:
            return

        # Aplicar gravidade
        self.speed_y += self.params.gravity * dt

        # Movimento
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Cache posição inteira para renderização
        self._cached_int_pos = (int(self.x), int(self.y))

        # Sistema de pulso sutil
        self.pulse_timer += dt
        if self.pulse_timer >= Config.SLIME_DRIP_PULSE_PERIOD:
            self.pulse_timer = 0.0

        # Calcula raio pulsante usando seno para movimento suave
        import math

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

        # Morte imediata se sair da tela (sem timer de graça - gotas sempre caem)
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

    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Retorna bounds (x, y, w, h) para spatial grid."""
        r = self.params.radius
        return (self.x - r, self.y - r, r * 2, r * 2)

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
        self.max_orphan_particles: int = 200  # Limitar para performance

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
            if (
                particle.x < -margin
                or particle.x > self.effect_width + margin
                or particle.y < -margin
                or particle.y > self.effect_height + margin
            ):
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

    def update(
        self,
        dt: float,
        boss_x: float,
        boss_y: float,
        boss_width: int,
        player_x: float,
        player_y: float,
    ) -> None:
        """Atualiza todas as gotas e spawna novas."""
        # Atualizar pool
        self.drip_pool.update(dt)

        # Spawn de novas gotas
        self.spawn_timer += dt
        if (
            self.spawn_timer >= self.spawn_interval
            and self.drip_pool.get_active_count() < self.max_drips
        ):
            self.spawn_timer = 0.0
            self._spawn_drip(boss_x, boss_y, boss_width)

    def _spawn_drip(self, boss_x: float, boss_y: float, boss_width: int) -> None:
        """Spawna uma gota aleatoriamente acima do boss."""
        x = boss_x + random.uniform(0, boss_width)
        y = boss_y - 50  # 50 pixels acima do boss
        self.drip_pool.get(x, y, self.effect_width, self.effect_height)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha todas as gotas e rastros."""
        self.drip_pool.draw(surface)

    def check_collisions(
        self, player_rect: pygame.Rect, entity_manager: Optional["EntityManager"] = None
    ) -> int:
        """Verifica colisões com o jogador usando spatial grid."""
        return self.drip_pool.check_collisions(player_rect, entity_manager)
