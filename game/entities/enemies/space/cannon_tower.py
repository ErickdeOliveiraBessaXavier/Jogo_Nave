import random
from typing import TYPE_CHECKING, Callable, List, Optional

import pygame

from ...effects.particle_types import ParticleDict, step_particle

if TYPE_CHECKING:
    from ...projectiles.cannon_mine import CannonMine


class CannonTower:
    """Torre de canhão fixa com visual estilo Railgun Sci-Fi."""

    def __init__(
        self,
        x: float,
        y: float,
        on_fire_mine: Optional[Callable[[float, float], None]] = None,
    ):
        self.x = x
        self.y = y
        self.target_y = y  # Posição final
        self.w = 60
        self.h = 90  # Ligeiramente mais alta

        # Estado das cargas
        self.max_charges = 3
        self.current_charge = 1
        self.mines_per_charge = 3
        self.mines_fired_in_current_charge = 0

        # Estado geral
        self.dead = False
        self.all_charges_used = False

        # Efeito de entrada (similar à nave - melhorado)
        self.is_entering = True
        self.entry_timer = 2.0  # 2 segundos para entrada completa
        self.entry_speed = 120  # pixels por segundo
        self.entry_fade_timer = 0.5  # tempo para partículas órfãs desaparecerem

        # Começar de baixo da tela
        screen = pygame.display.get_surface()
        screen_height = screen.get_height() if screen else 900
        self.y = screen_height + self.h  # Começar abaixo da tela

        # Disparo (só ativo após entrada)
        self.fire_timer = 0.0
        self.fire_interval = 1.5
        self.auto_fire = True

        # Animação de Recuo (Kickback) do canhão
        self.kickback_offset = 0.0

        # Efeito de piscar no final
        self.blinking = False
        self.blink_timer = 0.0
        self.blink_duration = 2.0
        self.blink_visible = True

        # Sistema de partículas thruster (similar à nave)
        self.thruster_particles: List[ParticleDict] = []
        # Partículas de entrada especiais
        self.entry_particles: List[ParticleDict] = []

        self.on_fire_mine = on_fire_mine
        self.active_mines: List["CannonMine"] = []

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def can_fire_next_charge(self) -> bool:
        if self.all_charges_used:
            return False
        if self.mines_fired_in_current_charge >= self.mines_per_charge:
            active_mines_count = len(
                [mine for mine in self.active_mines if not mine.dead]
            )
            return active_mines_count == 0
        return False

    def update(self, dt: float) -> None:
        if self.dead:
            return

        # Processo de entrada (subir de baixo para cima)
        if self.is_entering:
            self.entry_timer -= dt

            # Fase 1: Subir até posição final
            if self.y > self.target_y:
                self.y -= self.entry_speed * dt

                # Verificar se chegou na posição final
                if self.y <= self.target_y:
                    self.y = self.target_y
                    # Iniciar fade das partículas órfãs
                    self.entry_fade_timer = 0.5

            # Fase 2: Fade das partículas órfãs (após chegar na posição)
            elif self.entry_fade_timer > 0:
                self.entry_fade_timer -= dt

                # Terminar entrada quando fade completo
                if self.entry_fade_timer <= 0:
                    self.is_entering = False
                    self.fire_timer = 0.0  # Reset timer para operação normal

            # Durante entrada, só atualizar partículas
            self._update_entry_particles(dt)
            self._update_thruster_particles(dt)
            return

        # Recuperação do recuo visual (animação suave)
        if self.kickback_offset > 0:
            self.kickback_offset = max(0, self.kickback_offset - dt * 20)

        self.active_mines = [mine for mine in self.active_mines if not mine.dead]
        self._update_thruster_particles(dt)

        if self.blinking:
            self.blink_timer += dt
            self.blink_visible = (
                int(self.blink_timer * 10) % 2
            ) == 0  # Piscar mais rápido
            if self.blink_timer >= self.blink_duration:
                self.dead = True
            return

        if self.all_charges_used:
            self.blinking = True
            self.blink_timer = 0.0
            return

        if self.can_fire_next_charge() and self.current_charge < self.max_charges:
            self.current_charge += 1
            self.mines_fired_in_current_charge = 0
            self.fire_timer = 0.0

        if self.current_charge > self.max_charges or (
            self.current_charge == self.max_charges
            and self.mines_fired_in_current_charge >= self.mines_per_charge
        ):
            self.all_charges_used = True
            return

        if (
            self.auto_fire
            and self.mines_fired_in_current_charge < self.mines_per_charge
        ):
            self.fire_timer += dt
            if self.fire_timer >= self.fire_interval:
                self._fire_mine()
                self.fire_timer = 0.0
                self.kickback_offset = 6.0  # Aplica recuo visual ao atirar

    def _fire_mine(self) -> None:
        if not self.on_fire_mine:
            return
        screen = pygame.display.get_surface()
        screen_width = screen.get_width() if screen else 1600
        screen_height = screen.get_height() if screen else 900
        margin = 100
        target_x = random.uniform(margin, screen_width - margin)
        target_y = random.uniform(margin, screen_height - 400)
        self.on_fire_mine(target_x, target_y)
        self.mines_fired_in_current_charge += 1

    def register_mine(self, mine: "CannonMine") -> None:
        self.active_mines.append(mine)

    def _update_entry_particles(self, dt: float) -> None:
        """Partículas especiais durante a entrada - efeito cone similar à nave."""
        # Só gerar novas partículas se ainda está subindo
        if self.is_entering and self.y > self.target_y:
            # Gerar 3-4 partículas por frame durante entrada - efeito cone
            for _ in range(3):
                # Efeito cone: velocidade X mais ampla, Y concentrada para cima
                particle = ParticleDict(
                    x=self.x
                    + self.w / 2
                    + random.uniform(-8, 8),  # Spawn próximo ao centro
                    y=self.y - 5,  # Ligeiramente acima da torre
                    vx=random.uniform(-80, 80),  # Cone horizontal (similar à nave)
                    vy=random.uniform(-60, -20),  # Para cima (criando cone)
                    lifetime=random.uniform(0.4, 0.8),
                    size=random.uniform(2, 4),
                    color=(
                        (150, 180, 255) if random.random() > 0.3 else (100, 150, 255)
                    ),  # Azul claro
                )
                self.entry_particles.append(particle)

        # Atualizar partículas de entrada com fade gradual
        fade_factor = 1.0
        if self.is_entering and self.entry_fade_timer < 0.5:
            # Durante fade: reduzir lifetime mais rápido para desaparecimento gradual
            fade_factor = max(0.2, self.entry_fade_timer / 0.5)

        self.entry_particles = [
            ParticleDict(
                x=p["x"] + p["vx"] * dt,
                y=p["y"] + p["vy"] * dt,
                vx=p["vx"] * 0.98,  # Leve desaceleração
                vy=p["vy"] * 0.98,
                lifetime=p["lifetime"]
                - dt * (2.0 if fade_factor < 1.0 else 1.0),  # Fade mais rápido
                size=max(
                    0, p["size"] - dt * (4.0 if fade_factor < 1.0 else 2.0)
                ),  # Encolher mais rápido durante fade
                color=p["color"],
            )
            for p in self.entry_particles
            if p["lifetime"] - dt * (2.0 if fade_factor < 1.0 else 1.0) > 0
        ]

    def _update_thruster_particles(self, dt: float) -> None:
        """Sistema de partículas thruster similar à nave."""
        # Determinar intensidade baseada no estado
        should_generate = False
        particle_count = 2

        if self.is_entering:
            should_generate = True
            # Mais intenso durante subida, normal durante fade
            particle_count = 4 if self.y > self.target_y else 2
        elif not self.all_charges_used and self.current_charge <= self.max_charges:
            should_generate = True
            particle_count = 2

        if should_generate:
            for _ in range(particle_count):
                # Durante entrada: efeito mais intenso
                if self.is_entering and self.y > self.target_y:
                    vy_range = (100, 160)  # Mais intenso
                    size_range = (2, 4.5)
                    lifetime_range = (0.15, 0.4)
                else:
                    vy_range = (80, 120)  # Normal
                    size_range = (1.5, 3.5)
                    lifetime_range = (0.1, 0.3)

                particle = ParticleDict(
                    x=self.x + self.w / 2 + random.uniform(-8, 8),
                    y=self.y + self.h - 5,  # Saindo da base
                    vx=random.uniform(-15, 15),
                    vy=random.uniform(*vy_range),
                    lifetime=random.uniform(*lifetime_range),
                    size=random.uniform(*size_range),
                    color=(
                        (100, 150, 255) if random.random() > 0.5 else (150, 180, 255)
                    ),  # Azuis da mina
                )
                self.thruster_particles.append(particle)

        # Atualizar partículas existentes (encolhem em dt*2)
        self.thruster_particles = [
            step_particle(p, dt, size_shrink_rate=2.0)
            for p in self.thruster_particles
            if p["lifetime"] - dt > 0 and p["size"] - dt > 0
        ]

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead or (self.blinking and not self.blink_visible):
            return

        # Paleta de Cores Baseada no Nível de Carga - Tons Azuis das Minas
        # Carga 1 (Azul claro), Carga 2 (Azul médio), Carga 3 (Azul escuro/intenso)
        charge_colors = {
            1: ((100, 150, 255), (60, 100, 200)),  # Azul claro e médio
            2: ((80, 120, 255), (40, 80, 200)),  # Azul meio e escuro
            3: ((60, 100, 200), (30, 60, 150)),  # Azul escuro e muito escuro
        }
        glow_color, dark_glow_color = charge_colors.get(
            self.current_charge, ((100, 150, 255), (60, 100, 200))
        )

        # Durante entrada, aplicar efeito de transparência/brilho
        if self.is_entering:
            entry_progress = 1.0 - (
                self.entry_timer / 2.0
            )  # 0.0 a 1.0 (2 segundos total)
            # Intensificar cores durante entrada (efeito energético)
            glow_color = tuple(
                min(255, int(c * (1.0 + entry_progress * 0.5))) for c in glow_color
            )
            dark_glow_color = tuple(
                min(255, int(c * (1.0 + entry_progress * 0.3))) for c in dark_glow_color
            )

        # Efeito de tremor durante entrada (similar à nave)
        shake_x, shake_y = 0, 0
        if self.is_entering and self.y > self.target_y:
            # Tremor mais intenso no início da entrada
            shake_intensity = min(3, int((self.y - self.target_y) / 20))
            if shake_intensity > 0:
                shake_x = random.randint(-shake_intensity, shake_intensity)
                shake_y = random.randint(-shake_intensity, shake_intensity)

        # Desenhar partículas de thruster primeiro (atrás da torre)
        for p in self.thruster_particles:
            pygame.draw.circle(
                surface, p["color"], (int(p["x"]), int(p["y"])), int(p["size"])
            )

        # --- Desenho da Base (Trapézio Metálico) ---
        base_h = 30
        base_y = self.y + self.h - base_h

        # Pés de apoio com toque azulado (aplicar tremor)
        pygame.draw.rect(
            surface,
            (45, 50, 70),
            (self.x - 5 + shake_x, base_y + 15 + shake_y, self.w + 10, 15),
            border_radius=3,
        )

        # Corpo da base com tons azulados (aplicar tremor)
        pygame.draw.rect(
            surface, (80, 90, 120), (self.x + shake_x, base_y + shake_y, self.w, base_h)
        )
        pygame.draw.rect(
            surface, (120, 140, 180), (self.x + shake_x, base_y + shake_y, self.w, 4)
        )  # Highlight superior azulado

        # --- Desenho do Canhão (Turret) ---
        turret_w = 34
        turret_h = 50
        turret_x = self.x + (self.w - turret_w) // 2
        turret_y = self.y + 15 + self.kickback_offset  # Aplica o recuo aqui

        # Cano da arma (Barrel) com toque azulado (aplicar tremor)
        barrel_w = 12
        barrel_h = 40
        barrel_x = self.x + (self.w - barrel_w) // 2
        pygame.draw.rect(
            surface,
            (35, 40, 55),
            (barrel_x + shake_x, turret_y - 20 + shake_y, barrel_w, barrel_h),
        )

        # Bobinas de energia (Coils) no cano - brilham na cor da carga (aplicar tremor)
        for i in range(3):
            coil_y = turret_y - 15 + (i * 8)
            pygame.draw.rect(
                surface,
                dark_glow_color,
                (barrel_x - 2 + shake_x, coil_y + shake_y, barrel_w + 4, 4),
            )
            # Centro brilhante
            pygame.draw.rect(
                surface,
                glow_color,
                (barrel_x + shake_x, coil_y + 1 + shake_y, barrel_w, 2),
            )

        # Corpo principal da torre com tons azulados (aplicar tremor)
        pygame.draw.rect(
            surface,
            (100, 115, 140),
            (turret_x + shake_x, turret_y + shake_y, turret_w, turret_h),
            border_radius=5,
        )

        # Detalhes de ventilação/tech azulados (aplicar tremor)
        pygame.draw.line(
            surface,
            (60, 70, 90),
            (turret_x + 5 + shake_x, turret_y + 10 + shake_y),
            (turret_x + turret_w - 5 + shake_x, turret_y + 10 + shake_y),
            2,
        )
        pygame.draw.line(
            surface,
            (60, 70, 90),
            (turret_x + 5 + shake_x, turret_y + 20 + shake_y),
            (turret_x + turret_w - 5 + shake_x, turret_y + 20 + shake_y),
            2,
        )

        # --- HUD da Torre (Indicadores) ---

        # Luzes de munição (LEDs na base da torre)
        mines_left = self.mines_per_charge - self.mines_fired_in_current_charge

        # Fundo do painel de LEDs com toque azulado (aplicar tremor)
        panel_w = 40
        panel_x = self.x + (self.w - panel_w) // 2
        panel_y = base_y + 8
        pygame.draw.rect(
            surface, (15, 20, 35), (panel_x + shake_x, panel_y + shake_y, panel_w, 8)
        )

        if not self.all_charges_used:
            for i in range(self.mines_per_charge):
                # Calcular posição
                led_size = 6
                spacing = 4
                # Cálculo correto: total_width = leds + espaços entre eles (n-1 espaços)
                total_width = (
                    self.mines_per_charge * led_size
                    + (self.mines_per_charge - 1) * spacing
                )
                start_x = panel_x + (panel_w - total_width) // 2
                led_x = start_x + i * (led_size + spacing)

                # Cor: Aceso (azul) ou Apagado (azul escuro)
                if i < mines_left:
                    color = glow_color
                else:
                    color = (20, 30, 60)  # LED apagado (azul escuro)

                # Aplicar tremor nos LEDs
                pygame.draw.rect(
                    surface,
                    color,
                    (led_x + shake_x, panel_y + 1 + shake_y, led_size, 6),
                )

        # Desenhar partículas de entrada POR CIMA da torre (só durante entrada)
        if self.is_entering:
            for p in self.entry_particles:
                pygame.draw.circle(
                    surface, p["color"], (int(p["x"]), int(p["y"])), int(p["size"])
                )
