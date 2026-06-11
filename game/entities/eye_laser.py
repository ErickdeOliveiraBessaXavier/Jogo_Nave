import random
from typing import Any, List

import pygame

from ..core import colors
from .laser_utils import compute_laser_width
from .particle_types import DeathParticle


class EyeLaser:
    # Superfícies compartilhadas por todas as instâncias para evitar criação
    _glow_surface_cache = None
    _screen_size = None

    # Dissipação (fade-out) ao encerrar: feixe afina, perde opacidade e deixa
    # glow residual antes de morrer. Curto para não atrapalhar a leitura.
    FADE_DURATION = 0.22

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        max_w: int = 8,
        lifetime: float = 1.2,
        owner: Any | None = None,
    ):
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.w = 0
        self.max_w = max_w
        self.dead = False

        # Dono opcional: se ele morrer, o laser é encerrado imediatamente
        # (entra na dissipação e para de causar dano). EyeEnemy não passa dono
        # → comportamento clássico preservado.
        self.owner = owner

        self.lifetime = lifetime
        self.expand_time = 0.15  # Expansão um pouco mais lenta para dar tempo de reagir
        self.hold_time = 0.4  # Segura o laser por mais tempo
        self.timer = 0.0

        self.state = "alive"
        self.death_particles: List[DeathParticle] = []

        # Dissipação
        self._fade_timer = 0.0
        self._fade_w = 0.0  # largura visual capturada ao iniciar o fade

        # Efeito de pulsação
        self.pulse_timer = 0.0
        self.pulse_value = 0.0  # Cache do valor de pulsação

    def get_collision_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (self.x, self.y), (self.target_x, self.target_y)

    def _owner_dead(self) -> bool:
        return self.owner is not None and getattr(self.owner, "dead", False)

    def _begin_dissipation(self) -> None:
        """Inicia o fade-out: zera a colisão (w=0) e solta partículas do feixe."""
        self.state = "dying"
        self._fade_timer = 0.0
        # Captura a largura visual atual para afinar a partir dela.
        self._fade_w = float(self.w) if self.w > 0 else float(self.max_w) * 0.6
        self.w = 0  # colisão encerrada imediatamente

        start_pos = pygame.Vector2(self.x, self.y)
        end_pos = pygame.Vector2(self.target_x, self.target_y)
        line_vec = end_pos - start_pos
        line_length = line_vec.length()
        if line_length > 0:
            line_vec.normalize_ip()

        # Partículas energéticas se desprendendo ao longo do feixe.
        num_particles = int(line_length / 20)
        for i in range(num_particles):
            pos_on_line = start_pos + line_vec * (i * 20 + random.uniform(0, 20))
            particle: DeathParticle = {
                "pos": pos_on_line,
                "vel": pygame.Vector2(
                    random.uniform(-100, 100), random.uniform(-100, 100)
                ),
                "size": random.uniform(2, 4),
                "color": random.choice([colors.MAGENTA, colors.PURPLE, colors.WHITE]),
                "lifespan": random.uniform(0.2, 0.5),
            }
            self.death_particles.append(particle)

    def update(self, dt: float):
        self.timer += dt
        self.pulse_timer += dt * 8  # Velocidade da pulsação

        # Pré-calcular pulsação para evitar cálculos no draw
        self.pulse_value = abs(
            pygame.math.Vector2(1, 0).rotate(self.pulse_timer * 360).x
        )

        if self.state == "alive":
            # Encerramento imediato se o dono morreu, ou fim de vida natural.
            if self._owner_dead() or self.timer >= self.lifetime:
                self._begin_dissipation()
                return

            self.w = compute_laser_width(
                self.timer, self.expand_time, self.hold_time, self.lifetime, self.max_w
            )

        elif self.state == "dying":
            self._fade_timer += dt

            # Atualizar partículas mais eficientemente
            alive_particles: List[DeathParticle] = []
            for p in self.death_particles:
                p["pos"] += p["vel"] * dt
                p["lifespan"] -= dt
                p["size"] -= 3 * dt
                if p["lifespan"] > 0 and p["size"] > 0:
                    alive_particles.append(p)
            self.death_particles = alive_particles

            # Morre quando o feixe terminou de dissipar E não há mais partículas.
            if self._fade_timer >= self.FADE_DURATION and not self.death_particles:
                self.dead = True

    def _fade_progress(self) -> float:
        return min(1.0, self._fade_timer / self.FADE_DURATION)

    def draw(self, surface: pygame.Surface):
        if self.state == "alive" and self.w > 0:
            self._draw_beam(surface, float(self.w), 1.0)

        elif self.state == "dying":
            # Feixe dissipando: afina e perde opacidade ao longo do fade.
            fp = self._fade_progress()
            if fp < 1.0:
                taper = (1.0 - fp) ** 1.5
                width = self._fade_w * taper
                if width >= 1.0:
                    self._draw_beam(surface, width, taper, residual=True)

            # Partículas energéticas se desprendendo.
            for p in self.death_particles:
                if p["size"] > 0:
                    pygame.draw.circle(
                        surface,
                        p["color"],
                        (int(p["pos"].x), int(p["pos"].y)),
                        int(p["size"]),
                    )

    def _draw_beam(
        self, surface: pygame.Surface, width: float, intensity: float, residual: bool = False
    ) -> None:
        """Desenha o feixe (glow externo + núcleo) com `intensity` (0..1) de opacidade.

        Tudo é desenhado numa surface limitada à extensão do feixe (não à tela
        inteira), evitando alocação grande por frame durante o fade (§7).
        """
        start_x, start_y = int(self.x), int(self.y)
        end_x, end_y = int(self.target_x), int(self.target_y)
        w = max(1, int(width))

        glow_alpha = int((80 + 80 * self.pulse_value) * intensity)

        # Área necessária para o laser, limitada à tela.
        min_x = max(0, min(start_x, end_x) - 20)
        min_y = max(0, min(start_y, end_y) - 20)
        max_x = min(surface.get_width(), max(start_x, end_x) + 20)
        max_y = min(surface.get_height(), max(start_y, end_y) + 20)

        glow_w = max_x - min_x
        glow_h = max_y - min_y
        if glow_w <= 0 or glow_h <= 0:
            return

        glow_surface = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
        local_start = (start_x - min_x, start_y - min_y)
        local_end = (end_x - min_x, end_y - min_y)

        if glow_alpha > 0:
            # Camada de brilho externo
            pygame.draw.line(
                glow_surface, (255, 100, 255, glow_alpha // 2), local_start, local_end, w + 8
            )
            # Camada de brilho médio
            pygame.draw.line(
                glow_surface, (255, 150, 255, glow_alpha), local_start, local_end, w + 4
            )

        if residual:
            # Dissipando: núcleo com alpha decrescente (glow residual), também
            # aditivo na mesma surface limitada — sem corte abrupto.
            core_alpha = int(255 * intensity)
            if core_alpha > 0:
                pygame.draw.line(
                    glow_surface, (255, 235, 255, core_alpha), local_start, local_end, w
                )
            surface.blit(glow_surface, (min_x, min_y), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            surface.blit(glow_surface, (min_x, min_y), special_flags=pygame.BLEND_RGBA_ADD)
            # Vivo: núcleo branco sólido direto (nitidez), como no original.
            pygame.draw.line(surface, colors.WHITE, (start_x, start_y), (end_x, end_y), w)
