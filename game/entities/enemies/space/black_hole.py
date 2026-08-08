import math
import random
from typing import Any, TypedDict

import pygame

from ....core.colors import BLACK_HOLE_PARTICLE_COLORS
from ....core.config import config
from ....core.sound import sound_manager
from ..._shared.control_marks import accepts_control


class Particle(TypedDict):
    """Estrutura de uma partícula do disco de acreção."""

    x: float
    y: float
    size: int
    angle: float
    orbit_radius: float
    base_speed: float
    opacity: float
    color: tuple[int, int, int]


class BlackHole:
    """Buraco negro com movimento orientado pelo modo da fase."""

    SPAWN_DURATION = 1.0  # Segundos para crescer
    DEATH_DURATION = 0.5  # Segundos para implodir

    # Lentidão do vórtice: o inimigo afetado mantém 75% da velocidade por
    # VORTEX_SLOW_LINGER segundos.
    #
    # O campo REAPLICA a marca a cada frame enquanto o inimigo está dentro
    # (`process_all_enemies`), então o linger é o que sobra DEPOIS de sair —
    # ou seja, "10s de slow" contados a partir do último contato. É debuff de
    # controle que sobrevive ao próprio vórtice (que dura 15s): quem atravessou
    # o campo continua lento bem depois dele implodir.
    #
    # O linger também cobre a ordem de frame — `_update_environment` (buracos
    # negros) roda DEPOIS de `_update_enemies`, então a marca feita aqui só é
    # lida no frame seguinte. Qualquer valor acima de 1/30s (o piso do clamp de
    # dt, §14) resolve isso; os 10s são escolha de gameplay, não técnica.
    VORTEX_SLOW_FACTOR = 0.75
    VORTEX_SLOW_LINGER = 10.0

    # Pulsação cosmética ("respiração" do buraco). Só afeta o desenho — a física
    # (pull/dano) usa core_radius/pull_radius diretos, então o gameplay não muda.
    _PULSE_AMPLITUDE = 0.12  # ±12% no raio visual
    _PULSE_FREQ = 4.5  # rad/s — oscilação suave e contínua

    def __init__(
        self,
        x: float,
        y: float,
        duration: float,
        is_side_scroll: bool = False,
        is_vortex: bool = False,
    ):
        self.x = x
        self.y = y
        self.duration = duration
        self.is_side_scroll = is_side_scroll
        self.is_vortex = is_vortex
        self.lifetime = 0.0
        self.dead = False

        # Estados: "spawning", "active", "dying"
        self.state = "spawning"
        self.state_timer = 0.0
        self.scale = 0.0  # 0.0 a 1.0 para animações

        # Tocar som do buraco negro e GUARDAR o canal — o ciclo de vida do áudio
        # segue o do vórtice: paramos o canal em `stop_sound()` ao morrer/limpar.
        self._sound_channel = sound_manager.play_black_hole()

        # Movimento
        if self.is_vortex:
            self.speed_y = 0.0
            self.speed_x = 0.0
        else:
            self.speed_y = config.BLACK_HOLE_SPEED_Y
            self.speed_x = abs(config.BLACK_HOLE_SPEED_Y)

        # Raios base
        base_core_radius = config.BLACK_HOLE_INITIAL_CORE_RADIUS
        if self.is_vortex:
            base_core_radius *= 0.5

        self.core_radius = base_core_radius
        self.event_horizon = self.core_radius * 2

        initial_pull = config.BLACK_HOLE_INITIAL_PULL_RADIUS
        if self.is_vortex:
            initial_pull *= 0.6

        self.pull_radius = initial_pull

        # Raios finais
        self.max_core_radius = config.BLACK_HOLE_MAX_CORE_RADIUS
        if self.is_vortex:
            self.max_core_radius *= 0.4
            self.max_pull_radius = config.BLACK_HOLE_INITIAL_PULL_RADIUS * 0.8
        else:
            self.max_pull_radius = config.BLACK_HOLE_MAX_PULL_RADIUS

        # Dano (Vortex agora dá dano constante tipo "veneno" no núcleo)
        # Inspirado em IcePoisonZone: dano em ticks discretos com feedback visual.
        self.damage_tick_timer = 0.0
        self.damage_interval = 0.25  # 4 ticks por segundo
        # 2 HP/s: 0,5 por tick × 4 ticks/s (era 0,5 HP/s — 4× mais dano).
        #
        # Orçamento real de uma vida inteira de vórtice: ~26 HP (medido). Não
        # são 30: a duração de 15s inclui a rampa de spawn e o dano só corre no
        # estado "active", então a janela efetiva é ~13s. Isso mata um meteoro
        # pequeno/médio sozinho mas deixa o vórtice como ferramenta de CONTROLE
        # de área contra os grandes (13% de um Dreadnought de 200 HP), não como
        # fonte principal de dano.
        self.damage_per_tick = 0.5

        self.growth_rate = config.BLACK_HOLE_GROWTH_RATE
        self.particles: list[Particle] = []
        self._create_particles()
        self.animation_timer = 0.0

    def _create_particles(self):
        count = config.BLACK_HOLE_PARTICLE_COUNT
        if self.is_vortex:
            count = int(count * 0.4)

        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            dist_min = 0.3 if self.is_vortex else 0.4
            dist_max = 0.7 if self.is_vortex else 1.0
            distance = random.uniform(
                self.pull_radius * dist_min, self.pull_radius * dist_max
            )

            if self.is_vortex:
                color = (
                    random.randint(0, 100),
                    random.randint(150, 255),
                    random.randint(200, 255),
                )
            else:
                color = random.choice(BLACK_HOLE_PARTICLE_COLORS)

            particle: Particle = {
                "x": self.x + math.cos(angle) * distance,
                "y": self.y + math.sin(angle) * distance,
                "size": random.randint(1, 5)
                if self.is_vortex
                else random.randint(2, 4),
                "angle": angle,
                "orbit_radius": distance,
                "base_speed": random.uniform(0.1, 0.3)
                if self.is_vortex
                else random.uniform(0.2, 0.5),
                "opacity": random.uniform(0.3, 1.0),
                "color": color,
            }
            self.particles.append(particle)

    def _enter_dying(self) -> None:
        """Inicia a implosão e apaga o som junto, para o áudio morrer com a
        entidade em vez de sobreviver a ela."""
        self.state = "dying"
        self.state_timer = 0.0
        self.stop_sound()

    def update(self, dt: float):
        if self.dead:
            return  # já encerrado (som parado) — nada a processar

        self.lifetime += dt
        self.animation_timer += dt
        self.state_timer += dt

        # Timer de tick de dano (veneno)
        if self.is_vortex and self.state == "active":
            self.damage_tick_timer += dt

        # Máquina de estados de animação
        if self.state == "spawning":
            self.scale = min(1.0, self.state_timer / self.SPAWN_DURATION)
            if self.state_timer >= self.SPAWN_DURATION:
                self.state = "active"
        elif self.state == "active":
            self.scale = 1.0
            # Expira por tempo
            if self.is_vortex and self.lifetime >= self.duration:
                self._enter_dying()
        elif self.state == "dying":
            self.scale = max(0.0, 1.0 - (self.state_timer / self.DEATH_DURATION))
            if self.state_timer >= self.DEATH_DURATION:
                self.dead = True
                self.stop_sound()
                return

        # Movimento (apenas se não for vortex e estiver ativo)
        if not self.is_vortex and self.state != "dying":
            if self.is_side_scroll:
                self.x += self.speed_x * dt
            else:
                self.y += self.speed_y * dt

        # Crescimento gradual dos atributos base
        if self.core_radius < self.max_core_radius:
            self.core_radius = min(
                self.max_core_radius, self.core_radius + self.growth_rate * dt
            )
            self.event_horizon = self.core_radius * 2

        if self.pull_radius < self.max_pull_radius:
            self.pull_radius = min(
                self.max_pull_radius, self.pull_radius + self.growth_rate * 5 * dt
            )

        # Culling por saída da tela
        if not self.is_vortex and self.state == "active":
            if self.is_side_scroll:
                if self.x > config.SCREEN_WIDTH + self.pull_radius:
                    self._enter_dying()
            elif self.y < -self.pull_radius:
                self._enter_dying()

        # Atualizar partículas
        for particle in self.particles:
            dx = self.x - particle["x"]
            dy = self.y - particle["y"]
            distance_squared = dx * dx + dy * dy
            distance = math.sqrt(distance_squared)

            dist_ref = (
                self.pull_radius * 0.4 if self.is_vortex else self.pull_radius * 0.5
            )
            distance_factor = max(0.2, distance / dist_ref)
            acceleration_factor = 1 / distance_factor

            angular_speed = (1 / max(1, distance)) * 20 * acceleration_factor
            particle["angle"] += angular_speed * particle["base_speed"]
            particle["orbit_radius"] -= (
                particle["base_speed"] * 0.1 * acceleration_factor
            )

            # Escala afeta a posição das partículas (elas convergem na morte)
            draw_radius = particle["orbit_radius"] * self.scale
            particle["x"] = self.x + math.cos(particle["angle"]) * draw_radius
            particle["y"] = self.y + math.sin(particle["angle"]) * draw_radius

            # Resetar partículas próximas ao centro
            if particle["orbit_radius"] < self.core_radius + (
                10 if self.is_vortex else 20
            ):
                angle = random.uniform(0, math.pi * 2)
                distance = random.uniform(
                    self.pull_radius * 0.3, self.pull_radius * 1.0
                )
                particle["orbit_radius"] = distance
                particle["angle"] = angle

    def process_all_enemies(
        self, enemies: list[Any], dt: float, spawn_explosion_callback: Any = None
    ) -> None:
        if self.state == "dying":
            return

        pull_radius_sq = (self.pull_radius * self.scale) ** 2
        core_radius_sq = (self.core_radius * self.scale) ** 2

        # Lógica de Tick de Veneno (Sincronizado com IcePoisonZone)
        trigger_damage_tick = False
        if self.is_vortex and self.damage_tick_timer >= self.damage_interval:
            trigger_damage_tick = True
            self.damage_tick_timer = 0.0

        for enemy in enemies:
            if getattr(enemy, "dead", False):
                continue

            # Dois opt-outs distintos: `position_locked` = a entidade não pode
            # ser movida por ninguém (posição derivada, sem setter — ver o
            # protocolo `Enemy`); `pullable_by_black_hole` = imunidade a ESTE
            # efeito, para quem é móvel mas não deve ser arrastado.
            if getattr(enemy, "position_locked", False):
                continue
            if not getattr(enemy, "pullable_by_black_hole", True):
                continue

            # Imunidade de Bosses principais
            if enemy.__class__.__name__ in (
                "Boss",
                "SlimeBoss",
                "SpikeBoss",
                "GiantMeteorBoss",
            ):
                continue

            enemy_x = getattr(enemy, "x", 0) + getattr(enemy, "w", 0) / 2
            enemy_y = getattr(enemy, "y", 0) + getattr(enemy, "h", 0) / 2
            dx, dy = self.x - enemy_x, self.y - enemy_y
            dist_sq = dx * dx + dy * dy

            if dist_sq >= pull_radius_sq:
                continue

            # Lentidão por área (só o vórtice): marca o inimigo, e o
            # EntityManager traduz a marca em multiplicador de dt no tick dele.
            # Marcar aqui em vez de mexer na velocidade evita disputar o mesmo
            # campo com EMP/gelo — os três se compõem por multiplicação.
            #
            # O `accepts_control` não é redundante com os opt-outs acima: quem
            # tem `__slots__` sem o campo declarado estoura `AttributeError` na
            # ESCRITA, e isso derrubou a partida em combate (`SerpentBlock`).
            # Este era o único escritor de marca de controle sem o guard —
            # todos os outros passam por `control_marks`.
            if self.is_vortex and accepts_control(enemy):
                enemy.vortex_slow_timer = self.VORTEX_SLOW_LINGER

            # Logica de Centro (Núcleo)
            if dist_sq < core_radius_sq:
                if not self.is_vortex:
                    # Black Hole Ultimate mata tudo instantaneamente
                    enemy.dead = True
                    if spawn_explosion_callback:
                        spawn_explosion_callback(enemy_x, enemy_y, size=30)
                elif trigger_damage_tick:
                    # Vortex aplica dano em ticks discretos com feedback visual completo
                    self._apply_vortex_damage(
                        enemy, self.damage_per_tick, spawn_explosion_callback
                    )
                continue

            # Atração Gravitacional (aplica a todos dentro do pull_radius)
            dist = math.sqrt(dist_sq)
            pull_strength = (1.0 - (dist / (self.pull_radius * self.scale))) ** 2
            base_speed = config.BLACK_HOLE_PULL_SPEED * (1.5 if self.is_vortex else 1.0)
            pull_speed = base_speed * pull_strength * self.scale

            if dist > 0:
                enemy.x += (dx / dist) * pull_speed * dt
                enemy.y += (dy / dist) * pull_speed * dt

    def _apply_vortex_damage(
        self, enemy: Any, damage: float, spawn_explosion_callback: Any = None
    ) -> None:
        """Aplica dano e dispara feedback visual (on_hit) sincronizado com o tick."""
        killed = False
        res = None
        hit_x = enemy.x + getattr(enemy, "w", 0) / 2
        hit_y = enemy.y + getattr(enemy, "h", 0) / 2

        # 1. `on_hit` só para FEEDBACK VISUAL (flash, partes) — sempre com dano 0.
        #
        # O dano real é sempre aplicado no passo 2, nunca aqui. Motivo: `on_hit`
        # recebe int, e o dano por tick é fracionário (0,5) — truncaria para 0 e
        # o veneno não faria nada. Mandar o dano real para os dois lados seria
        # pior: `on_hit` debita a vida E o passo 2 debita de novo, dobrando o
        # dano em silêncio a partir de `damage >= 1`. Uma fonte de dano só.
        if hasattr(enemy, "on_hit"):
            res = enemy.on_hit(0, hit_x, hit_y)
            if getattr(enemy, "dead", False):
                killed = True

        # 2. Fallbacks de dano (caso on_hit não exista ou não tenha matado)
        if not killed:
            if hasattr(enemy, "health"):
                enemy.health -= damage
                if enemy.health <= 0:
                    enemy.dead = True
                    killed = True
            elif hasattr(enemy, "lives"):
                current = getattr(enemy, "lives")
                new_lives = current - damage
                setattr(enemy, "lives", new_lives)
                if new_lives <= 0:
                    enemy.dead = True
                    killed = True

            # Se o fallback não tiver on_hit mas disparou flash manual
            if (
                not killed
                and not hasattr(enemy, "on_hit")
                and hasattr(enemy, "_hit_flash")
            ):
                setattr(enemy, "_hit_flash", 0.15)

        # 3. Se morreu, disparar explosão autêntica baseada no inimigo
        if killed and spawn_explosion_callback:
            expl_size = getattr(res, "explosion_size", 25) if res else 25
            expl_type = getattr(res, "explosion_type", None) if res else None
            spawn_explosion_callback(
                hit_x, hit_y, size=expl_size, explosion_type=expl_type
            )

    def stop_sound(self) -> None:
        """Encerra o som deste vórtice (idempotente). Chamado ao morrer e na
        limpeza da fase — o áudio segue o ciclo de vida do buraco.

        Público porque o ``EntityManager`` precisa chamá-lo ao limpar a lista
        (§1: nada de tocar em privado de outro objeto).
        """
        sound_manager.stop_black_hole(self._sound_channel)
        self._sound_channel = None

    def draw(self, surface: pygame.Surface):
        if self.scale <= 0:
            return

        # Respiração do buraco (só visual). Aplicada ao raio do núcleo e ao
        # tamanho das partículas para o efeito parecer "vivo".
        pulse = 1.0 + self._PULSE_AMPLITUDE * math.sin(
            self.animation_timer * self._PULSE_FREQ
        )

        # Partículas
        for particle in self.particles:
            color_with_alpha = particle["color"] + (
                int(particle["opacity"] * 255 * self.scale),
            )
            pygame.draw.circle(
                surface,
                color_with_alpha,
                (int(particle["x"]), int(particle["y"])),
                max(1, int(particle["size"] * self.scale * pulse)),
            )

        # Núcleo (respira com a pulsação)
        core_r = int(self.core_radius * self.scale * pulse)
        if core_r > 0:
            pygame.draw.circle(surface, (0, 0, 0), (int(self.x), int(self.y)), core_r)
            pygame.draw.circle(
                surface, (50, 50, 50), (int(self.x), int(self.y)), core_r, 1
            )

    @property
    def rect(self) -> pygame.Rect:
        r = self.pull_radius * self.scale
        return pygame.Rect(int(self.x - r), int(self.y - r), int(r * 2), int(r * 2))
