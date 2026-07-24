"""WorldTransitionCutscene — diretor da cinemática de saída da nave na transição
de mundo (carga → impulso + partículas de propulsor).

Extraído da `PlayingScene` (§9). Não referencia a cena: recebe **acessores** da
nave/estado e **callbacks** para o que a cena mantém — a fase do FSM de transição
(`enter_cutscene_phase`, `is_active`) e o **fluxo de conclusão** (`on_complete`:
painel de mundo / interstício de atmosfera / preparação de nível). Todo o estado
da ANIMAÇÃO (timers, origem, recuo, distância de lançamento, partículas) vive
aqui; o render lê via o DTO montado pela cena (`RenderFrame`), que expõe
`timer`/`particles` por properties finas.

A decisão de fluxo (o que acontece quando a cutscene termina) permanece na cena —
ela depende de `current_world`, `AtmosphereState` e da pilha de cenas, que são
estado da partida, não da animação.
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING, Callable, Optional, TypedDict

from ..core.config import config as Config

if TYPE_CHECKING:
    from ..core.world_config import WorldConfig
    from ..entities.player.ship import Ship
    from ..systems.entity_manager import EntityManager

logger = logging.getLogger(__name__)


class ThrusterParticle(TypedDict):
    offset_x: float
    offset_y: float
    vx: float
    vy: float
    lifetime: float
    size: float
    color: tuple[int, int, int]


class WorldTransitionCutscene:
    def __init__(
        self,
        *,
        get_ship: Callable[[], "Ship"],
        get_side_scroll: Callable[[], bool],
        get_entity_manager: Callable[[], "EntityManager"],
        is_active: Callable[[], bool],
        enter_cutscene_phase: Callable[[], None],
        on_complete: Callable[[Optional["WorldConfig"], bool], None],
    ) -> None:
        self._get_ship = get_ship
        self._get_side_scroll = get_side_scroll
        self._get_entity_manager = get_entity_manager
        self._is_active = is_active
        self._enter_cutscene_phase = enter_cutscene_phase
        self._on_complete = on_complete

        self.timer: float = 0.0
        self.duration: float = Config.WORLD_TRANSITION_CUTSCENE_DURATION
        self.charge_duration: float = Config.WORLD_TRANSITION_CUTSCENE_CHARGE_DURATION
        self.launch_speed: float = Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED
        self.origin: tuple[float, float] = (0.0, 0.0)
        self.recoil_offset: float = 0.0
        self.launch_distance: float = 0.0
        self.target_world: Optional["WorldConfig"] = None
        self.debug_mode: bool = False
        self.launch_down: bool = False
        self.particles: list[ThrusterParticle] = []

    @property
    def active(self) -> bool:
        """Cutscene em andamento — derivado do FSM de transição da cena."""
        return self._is_active()

    def start(
        self,
        target_world: "WorldConfig",
        debug_mode: bool = False,
        launch_down: bool = False,
    ) -> None:
        """Inicia a cutscene de saída da nave antes do painel de transição.

        `launch_down=True` (re-entry/Entering) lança a nave para BAIXO em vez de
        para cima no modo top-down — a nave está descendo na atmosfera.
        """
        ship = self._get_ship()
        side_scroll = self._get_side_scroll()

        self.launch_down = launch_down
        self._enter_cutscene_phase()
        self.timer = 0.0
        self.launch_speed = Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED
        self.origin = (float(ship.x), float(ship.y))
        self.recoil_offset = 0.0
        self.launch_distance = 0.0
        self.target_world = target_world
        self.debug_mode = debug_mode
        self.particles.clear()

        # Ativa o tremor visual da nave, mas desativa a interpolação automática
        # de posição do Ship.update (entering_duration=0) para controle manual.
        ship.is_entering = True
        ship.entering_duration = 0.0
        ship.is_side_scroll = side_scroll
        # Força o sprite a apontar na direção do launch — evita que uma rotação
        # CTRL anterior do jogador faça a nave voar de costas/de lado durante a
        # cutscene. O facing volta ao default no próximo mundo via apply_world_mode.
        if side_scroll:
            cutscene_facing = "east"
        elif launch_down:
            cutscene_facing = "south"
        else:
            cutscene_facing = "north"
        ship.set_facing(cutscene_facing)
        logger.info(
            "[CUTSCENE] Iniciando saída da nave para %s (debug=%s)",
            target_world.name,
            debug_mode,
        )

    def update(self, dt: float) -> None:
        """Atualiza a cinemática de saída da nave (charge → launch)."""
        if not self.active:
            return

        ship = self._get_ship()
        side_scroll = self._get_side_scroll()

        self.timer += dt
        t = self.timer
        charge_end = self.charge_duration
        charge_progress = min(1.0, max(0.0, t / charge_end))

        recoil_sign = -1.0 if side_scroll else 1.0
        if charge_progress < 0.28:
            tremble_strength = 1.8 * (1.0 - charge_progress * 0.8)
            ship_x = self.origin[0]
            ship_y = self.origin[1]
            ship_x += math.sin(t * 55.0) * tremble_strength
            ship_y += math.cos(t * 47.0) * tremble_strength * 0.75
            self.recoil_offset = 0.0
            thruster_intensity = 6
        elif charge_progress < 0.68:
            recoil_progress = (charge_progress - 0.28) / (0.68 - 0.28)
            self.recoil_offset = 12.0 * recoil_progress
            ship_x = self.origin[0]
            ship_y = self.origin[1]
            ship_x += recoil_sign * self.recoil_offset
            tremble_strength = 1.2 * (1.0 - recoil_progress)
            ship_x += math.sin(t * 42.0) * tremble_strength * 0.55
            ship_y += math.cos(t * 39.0) * tremble_strength * 0.55
            thruster_intensity = 10
        else:
            hold_progress = (charge_progress - 0.68) / (1.0 - 0.68)
            self.recoil_offset = 12.0
            ship_x = self.origin[0] + recoil_sign * self.recoil_offset
            ship_y = self.origin[1]
            thruster_intensity = 14 + int(6 * hold_progress)

        ship.x = ship_x
        ship.y = ship_y
        self._spawn_particles(intensity=thruster_intensity)

        if t >= charge_end:
            self.launch_speed += (
                Config.WORLD_TRANSITION_CUTSCENE_LAUNCH_ACCELERATION * dt
            )
            self.launch_distance += self.launch_speed * dt
            if side_scroll:
                ship.x = (
                    self.origin[0]
                    + recoil_sign * self.recoil_offset
                    + self.launch_distance
                )
            else:
                launch_dir = 1.0 if self.launch_down else -1.0
                ship.y = self.origin[1] + launch_dir * self.launch_distance
            self._spawn_particles(intensity=14)

        ship_dt_multiplier = 3.4 if t >= charge_end else 2.2
        ship.update(
            dt * ship_dt_multiplier,
            self._get_entity_manager(),
            is_side_scroll=side_scroll,
        )
        self._update_particles(dt)

        if self.timer >= self.duration:
            self._finish()

    def _finish(self) -> None:
        """Finaliza a cutscene: limpa o estado da animação e delega o FLUXO à
        cena via `on_complete` (painel/atmosfera/preparação)."""
        if not self.active:
            return

        target_world = self.target_world
        debug_mode = self.debug_mode

        self.timer = 0.0
        self.target_world = None
        self.debug_mode = False
        self.particles.clear()
        self.recoil_offset = 0.0
        self.launch_distance = 0.0

        self._on_complete(target_world, debug_mode)

    def _spawn_particles(self, intensity: int) -> None:
        """Gera partículas extras para o impulso da cutscene."""
        ship = self._get_ship()
        side_scroll = self._get_side_scroll()
        if ship.ship_image is not None:
            sprite_w, sprite_h = ship.ship_image.get_size()
        else:
            sprite_w, sprite_h = ship.w, ship.h

        for _ in range(intensity):
            if side_scroll:
                particle: ThrusterParticle = {
                    "offset_x": random.uniform(-14, 4),
                    "offset_y": sprite_h / 2 + random.uniform(-8, 8),
                    "vx": -random.uniform(220, 460),
                    "vy": random.uniform(-120, 120),
                    "lifetime": random.uniform(0.14, 0.34),
                    "size": random.uniform(2.0, 4.8),
                    "color": (255, random.randint(120, 230), 0),
                }
            else:
                # Top-down
                if self.launch_down:
                    # Re-entry: Nave desce, partículas sobem (saem do topo)
                    particle = {
                        "offset_x": sprite_w / 2 + random.uniform(-9, 9),
                        "offset_y": random.uniform(-10, 4),
                        "vx": random.uniform(-90, 90),
                        "vy": -random.uniform(220, 460),
                        "lifetime": random.uniform(0.14, 0.34),
                        "size": random.uniform(2.0, 4.8),
                        "color": (255, random.randint(120, 230), 0),
                    }
                else:
                    # Normal / Exit: Nave sobe, partículas descem (saem da base)
                    particle = {
                        "offset_x": sprite_w / 2 + random.uniform(-9, 9),
                        "offset_y": sprite_h + random.uniform(-4, 10),
                        "vx": random.uniform(-90, 90),
                        "vy": random.uniform(220, 460),
                        "lifetime": random.uniform(0.14, 0.34),
                        "size": random.uniform(2.0, 4.8),
                        "color": (255, random.randint(120, 230), 0),
                    }
            self.particles.append(particle)

    def _update_particles(self, dt: float) -> None:
        """Atualiza e filtra partículas da cutscene (list comprehension imutável)."""
        self.particles = [
            {
                "offset_x": p["offset_x"] + p["vx"] * dt,
                "offset_y": p["offset_y"] + p["vy"] * dt,
                "vx": p["vx"],
                "vy": p["vy"],
                "lifetime": p["lifetime"] - dt,
                "size": max(0.0, p["size"] - dt * 6.0),
                "color": p["color"],
            }
            for p in self.particles
            if p["lifetime"] - dt > 0.0 and p["size"] - dt * 6.0 > 0.0
        ]
