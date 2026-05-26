import logging
import math
import random
from typing import TYPE_CHECKING, Any, List, Literal, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.time import Timer
from .boss_cannon import BossCannon
from .boss_hit_mixin import BossHitMixin
from .boss_laser import BossLaser
from .boss_particles import BossParticleSystem
from .boss_pixel_map import (
    COLORS_FRENZY,
    COLORS_NORMAL,
    PIXEL_COLS,
    PIXEL_MAP,
)
from .boss_square import BossSquare
from .boss_state import BossState
from .draw_utils import rotated_square_corners

if TYPE_CHECKING:
    from ..systems.boss_context import BossUpdateContext, BossUpdateResult

# Sound events emitted by Boss.update() — executed by EntityManager
BossSoundEvent = Literal[
    "play_charging",
    "stop_charging",
    "play_fire",
    "stop_fire",
]


class Boss(BossHitMixin):
    """
    Boss entity with face-oriented combat system and layered pixel art design.
    """

    BOSS_TYPE_NAME: str = "normal"

    # Attack constants
    FRENZY_LASER_ANGLES: List[float] = [-0.349, 0, 0.349]
    LASER_DISTANCE: int = 2000
    MAX_CHARGE_RADIUS: float = 15.0
    _FRENZY_SALVO_AIM_WINDOW: float = 0.25
    _FRENZY_SALVO_REARM_DELAY: float = 0.8

    def __init__(
        self, x: float, y: float, health: int = Config.BOSS_HEALTH, hit_score: int = 50
    ):
        # Position and size - Adjusted for pixel map proportions
        self.w = 180  # 18 cols * 10 px
        self.h = 140  # 14 rows * 10 px
        self.pixel_size = self.w / PIXEL_COLS

        self.x = x
        self.y = -self.h
        self.target_y = y

        # Health and state
        self.health = health
        self.max_health = health
        self.hit_score = hit_score
        self.dead = False

        # Movement
        self.speed = Config.BOSS_NORMAL_SPEED
        self.direction = 1
        self.entry_speed = Config.BOSS_ENTRY_SPEED
        self.player_x: float = 0.0
        self.player_y: float | None = None

        # State machine
        self.state = BossState.ENTERING
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0
        self.shake_offset_x: int = 0
        self.shake_offset_y: int = 0
        self.pending_frenzy = False
        # Padrão de ataque escolhido no início de cada ciclo (AIMING). None fora
        # do frenzy ou quando não há 3 canhões. Valores: "wall" | "salvo" | "single".
        self.frenzy_pattern: str | None = None
        self._active_salvo_cannon_idx: int | None = None
        self.square_attack_timer = Timer(random.uniform(2.0, 3.5))

        # Attack system
        self._init_attack_system()
        self.charge_progress = 0.0

        # Visual effects - Lerp and Layers
        self.current_palette = COLORS_NORMAL.copy()
        self.palette_lerp_speed = 5.0
        self.breathing_timer = 0.0

        self.particle_system = BossParticleSystem()
        self.fired_lasers: List[BossLaser] = []
        self._sound_events: List[BossSoundEvent] = []

        # Orientation system
        self.rotation_angle = 0.0
        self.facing_direction = pygame.Vector2(0, 1)
        self.face_center = pygame.Vector2(0, 0)
        # Três canhões desde o início: laterais (esq./dir.) + central. A central
        # fica por último na lista (ver self.central) e serve de referência de face.
        left = BossCannon()
        right = BossCannon()
        central = BossCannon()
        left.rel = (0.25, 0.25)
        right.rel = (0.75, 0.25)
        self.cannons: List[BossCannon] = [left, right, central]
        self._position_cannons()

        # Janela de reação (mira travada -> laser). Fonte única: BOSS_LASER_DELAY.
        self.laser_delay_timer = 0.0
        self._salvo_rearm_timer = 0.0
        self.pending_laser_data: dict[str, Any] | None = None

        # Floating squares
        self.floating_squares: List[BossSquare] = []
        self._init_floating_squares()
        self.squares_animation_timer = 0.0

        # Launch queue
        self.square_launch_queue: List[BossSquare] = []
        self.square_launch_timer = 0.0
        self.square_launch_delay = 0.15

        # Caching
        self._cached_layers: dict[str, pygame.Surface] = {}

    def _init_floating_squares(self) -> None:
        num_squares = 14
        boss_center_x = self.x + self.w / 2
        boss_center_y = self.y + self.h / 2

        for _ in range(num_squares):
            orbit_radius = random.uniform(80, 140)
            orbit_angle = random.uniform(0, 360)
            orbit_speed = random.choice(
                [
                    random.uniform(30, 60),
                    random.uniform(15, 30),
                    random.uniform(-60, -30),
                    random.uniform(-30, -15),
                ]
            )
            size = random.uniform(16, 28)

            angle_rad = math.radians(orbit_angle)
            initial_x = boss_center_x + math.cos(angle_rad) * orbit_radius
            initial_y = boss_center_y + math.sin(angle_rad) * orbit_radius

            square = BossSquare(
                x=initial_x,
                y=initial_y,
                vx=0,
                vy=0,
                size=size,
                is_orbital=True,
                orbit_radius=orbit_radius,
                orbit_angle=orbit_angle,
                orbit_speed=orbit_speed,
                speed_var=random.uniform(0.85, 1.18),
            )
            self.floating_squares.append(square)

    def _update_lerps(self, dt: float) -> None:
        """Update smooth color transitions."""
        target = COLORS_FRENZY if self.frenzy_mode else COLORS_NORMAL
        for key in self.current_palette:
            if key in target:
                curr = self.current_palette[key]
                targ = target[key]
                r = int(curr[0] + (targ[0] - curr[0]) * self.palette_lerp_speed * dt)
                g = int(curr[1] + (targ[1] - curr[1]) * self.palette_lerp_speed * dt)
                b = int(curr[2] + (targ[2] - curr[2]) * self.palette_lerp_speed * dt)
                # Clamp color values to valid RGB range (0-255)
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                self.current_palette[key] = (r, g, b)

    def _position_cannons(self) -> None:
        """Cola os canhões ao corpo do boss. Chamado todo frame para que sigam
        o movimento da nave — senão ficam 'presos' na pose do frame anterior."""
        if not self.cannons:
            return
        central = self.central
        central.update_position(self.x, self.y, self.w, self.h)
        # Laterais seguem o offset relativo dentro da caixa do boss.
        for c in self.cannons[:-1]:
            if c.rel is not None:
                relx, rely = c.rel
                c.set_position(self.x + relx * self.w, self.y + rely * self.h)

    def _aim_cannons(self, player_x: float, player_y: float) -> None:
        """Mira cada canhão no jogador e atualiza o vetor de face. Não é chamado
        em PREPARING_TO_FIRE/FIRING: ali a mira fica travada na última pose."""
        if not self.cannons:
            return
        central = self.central
        # Todos os canhões seguem o jogador o tempo todo, exceto no padrão
        # wall, onde os laterais ficam presos a um desvio angular fixo.
        central.aim_at(player_x, player_y)
        wall_telegraph = self.frenzy_pattern == "wall" and self.frenzy_mode
        if wall_telegraph:
            base_dir = central.get_direction()
            side_angle = self.FRENZY_LASER_ANGLES[2]
            left_dir = pygame.Vector2(
                base_dir.x * math.cos(-side_angle) - base_dir.y * math.sin(-side_angle),
                base_dir.x * math.sin(-side_angle) + base_dir.y * math.cos(-side_angle),
            )
            right_dir = pygame.Vector2(
                base_dir.x * math.cos(side_angle) - base_dir.y * math.sin(side_angle),
                base_dir.x * math.sin(side_angle) + base_dir.y * math.cos(side_angle),
            )
            self.cannons[0].rotation = math.atan2(left_dir.y, left_dir.x)
            self.cannons[1].rotation = math.atan2(right_dir.y, right_dir.x)
        else:
            for c in self.cannons[:-1]:
                c.aim_at(player_x, player_y)

        # face_center continua o tip do canhão central (efeitos legados de carga).
        self.face_center.x, self.face_center.y = central.get_barrel_tip_position()
        self.facing_direction = central.get_direction()

    def _init_attack_system(self) -> None:
        self.attack_timer = Timer(random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL))
        self.charge_duration = Config.BOSS_CHARGE_DURATION
        self.charge_timer = Timer(self.charge_duration)
        self.fire_duration = Config.BOSS_LASER_LIFETIME
        self.fire_timer = Timer(self.fire_duration)

    def _activate_frenzy_mode(self) -> None:
        self.frenzy_mode = True
        self.pending_frenzy = False
        self.speed = Config.BOSS_FRENZY_SPEED
        self.frenzy_shake_timer = Config.BOSS_FRENZY_SHAKE_DURATION
        self._cached_layers.clear()

        for square in self.floating_squares:
            square.set_frenzy_mode(True)

        self._update_frenzy_timings()

        if self.state == BossState.ACTIVE:
            self.fired_lasers.clear()
            self._sound_events.append("stop_charging")
            self._sound_events.append("stop_fire")
            self.particle_system.clear_all()
            self._reset_attack_timer()

        self.fire_timer.duration = Config.BOSS_FRENZY_LASER_LIFETIME
        logging.info("💀 Boss entrou em modo FRENZY!")

    def _update_frenzy_timings(self) -> None:
        self.charge_duration = self._get_charge_duration()
        self.charge_timer.duration = self.charge_duration

    def _get_charge_duration(self) -> float:
        return (
            Config.BOSS_FRENZY_CHARGE_DURATION
            if self.frenzy_mode
            else Config.BOSS_CHARGE_DURATION
        )

    def update_boss(self, dt: float, ctx: "BossUpdateContext") -> "BossUpdateResult":
        from ..systems.boss_context import BossUpdateResult

        lasers, squares, sound_events = self.update(dt, ctx.player_x, ctx.player_y)
        result = BossUpdateResult(
            new_lasers=list(lasers),
            new_squares=list(squares),
            sound_events=list(sound_events),
        )
        # floating_squares orbitam o boss mas precisam estar em em.boss_squares
        # para que colisão e render do EM os capturem.
        em_squares = ctx.entity_manager.boss_squares
        for q in self.floating_squares:
            if q not in result.new_squares and q not in em_squares:
                result.new_squares.append(q)
        return result

    @property
    def central(self) -> BossCannon:
        """Canhão central — sempre o último da lista; referência de face/mira."""
        return self.cannons[-1]

    # --- Fases de estado (centralizam tuplas de BossState reusadas) ----------

    @property
    def _in_committed_attack(self) -> bool:
        """Boss comprometido com a sequência de ataque: o frenzy não pode iniciar
        agora (vira pending_frenzy). PREPARING_TO_FIRE fica de fora de propósito
        — o frenzy pode entrar durante a janela de reação."""
        return self.state in (
            BossState.AIMING,
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.FIRING,
        )

    @property
    def shows_aiming_line(self) -> bool:
        """Estados em que a linha de mira é desenhada (telegrafo do ataque)."""
        return self.state in (
            BossState.AIMING,
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
        )

    @property
    def shows_charge_circle(self) -> bool:
        """Estados em que o círculo de carga/convergência aparece no rosto."""
        return self.state in (
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
        )

    def update(
        self, dt: float, player_x: float, player_y: float | None = None
    ) -> tuple[List[BossLaser], List[BossSquare], List[BossSoundEvent]]:
        self._sound_events: List[BossSoundEvent] = []
        self._update_lerps(dt)
        self.breathing_timer += dt
        self.frenzy_shake_timer = max(0.0, self.frenzy_shake_timer - dt)

        if self.frenzy_shake_timer > 0:
            self.shake_offset_x = random.randint(-3, 3)
            self.shake_offset_y = random.randint(-3, 3)
        else:
            self.shake_offset_x = 0
            self.shake_offset_y = 0

        self.player_x = player_x
        self.player_y = player_y

        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2

        self.squares_animation_timer += dt * 5
        pulse_scale = 1.0 + 0.2 * abs(math.cos(self.squares_animation_timer))

        for square in self.floating_squares:
            if square.state == "orbiting":
                square.orbit_angle = (
                    square.orbit_angle + square.orbit_speed * dt
                ) % 360
                angle_rad = math.radians(square.orbit_angle)
                target_x = center_x + math.cos(angle_rad) * square.orbit_radius
                target_y = center_y + math.sin(angle_rad) * square.orbit_radius
                lerp_speed = 7.0 * square.speed_var
                square.x += (target_x - square.x) * lerp_speed * dt
                square.y += (target_y - square.y) * lerp_speed * dt
                square.size = square.base_size * pulse_scale
                square.rotation = 0.0
            elif square.state in ("preparing", "launching"):
                square.prepare_timer += dt
                square.rotation += dt * 720
                prepare_pulse = 1.0 + 0.4 * abs(math.sin(square.prepare_timer * 10))
                square.size = square.base_size * prepare_pulse
                if square.state == "preparing" and square.prepare_timer >= 1.0:
                    square.state = "ready_to_launch"

        # Canhões colados ao corpo todo frame; a mira rastreia o jogador
        # continuamente, exceto quando travada (PREPARING_TO_FIRE/FIRING).
        self._position_cannons()
        if player_y is not None and self.state not in (
            BossState.PREPARING_TO_FIRE,
            BossState.FIRING,
        ):
            self._aim_cannons(player_x, player_y)

        if self.frenzy_shake_timer <= 0:
            if self.pending_frenzy and not self._in_committed_attack:
                self._activate_frenzy_mode()

        spawned_squares: List[BossSquare] = []
        if self.frenzy_mode and self.frenzy_shake_timer <= 0 and player_y is not None:
            if self.square_launch_queue:
                self.square_launch_timer += dt
                if self.square_launch_timer >= self.square_launch_delay:
                    square = self.square_launch_queue.pop(0)
                    projectile = self._create_square_projectile(
                        square, player_x, player_y
                    )
                    projectile.palette = self.current_palette
                    spawned_squares.append(projectile)
                    square.state, square.prepare_timer, square.rotation = (
                        "orbiting",
                        0.0,
                        0.0,
                    )
                    self.square_launch_timer = 0.0

            ready_squares = [
                sq for sq in self.floating_squares if sq.state == "ready_to_launch"
            ]
            for square in ready_squares:
                square.state = "launching"
                self.square_launch_queue.append(square)

            if self.state == BossState.ACTIVE and not self.pending_laser_data:
                self.square_attack_timer.update(dt)
                if self.square_attack_timer.done():
                    preparing = [
                        sq for sq in self.floating_squares if sq.state != "orbiting"
                    ]
                    if not preparing:
                        orbiting = [
                            sq for sq in self.floating_squares if sq.state == "orbiting"
                        ]
                        if orbiting:
                            num = random.randint(2, min(3, len(orbiting)))
                            for sq in random.sample(orbiting, num):
                                sq.state, sq.prepare_timer = "preparing", 0.0
                    self.square_attack_timer.start(random.uniform(2.0, 3.5))

        lasers_fired: List[BossLaser] = []
        if self.state == BossState.ENTERING:
            self._update_entering_state(dt)
        elif self.state == BossState.ACTIVE:
            self._update_active_state(dt)
        elif self.state == BossState.AIMING:
            self._enter_charging()
        elif self.state == BossState.CHARGING:
            self._update_charging_state(dt)
        elif self.state == BossState.CONVERGING:
            lasers_fired = self._update_converging_state()
        elif self.state == BossState.PREPARING_TO_FIRE:
            lasers_fired = self._update_preparing_to_fire_state(dt)
        elif self.state == BossState.FIRING:
            self._update_firing_state(dt)

        # Após o movimento do corpo (ENTERING desce, ACTIVE patrulha), recola os
        # canhões para o draw não os deixar 'presos' na posição do frame anterior.
        self._position_cannons()

        # Tick único dos sistemas de partículas: a GERAÇÃO fica nos handlers de
        # estado, mas o avanço/expiração roda todo frame e incondicionalmente —
        # assim nenhuma fase precisa lembrar de "tickar" e nada congela. Fora das
        # fases de carga as listas estão vazias, então é um no-op barato.
        acc_dt = self._get_accelerated_dt(dt)
        self.particle_system.update_charging_particles(
            acc_dt, self.face_center.x, self.face_center.y
        )
        self.particle_system.update_circle_disappear_particles(acc_dt)

        return (lasers_fired, spawned_squares, self._sound_events)

    def _update_entering_state(self, dt: float) -> None:
        self.y += self.entry_speed * dt
        if self.y >= self.target_y:
            self.y = self.target_y
            self.state = BossState.ACTIVE
            self.attack_timer.start()

    def _update_active_state(self, dt: float) -> None:
        self.x += self.speed * self.direction
        if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
            self.direction *= -1

        if self.frenzy_shake_timer <= 0:
            self.attack_timer.update(dt)
            if self.attack_timer.done():
                # Decide o padrão antes de entrar em AIMING — _aim_cannons
                # precisa saber para mirar os canhões nos targets do muro.
                self.frenzy_pattern = self._select_frenzy_pattern()
                self.state = BossState.AIMING

    def _select_frenzy_pattern(self) -> str:
        """Sorteia entre os padrões de tiro frenzy (3 canhões).

        Fora do frenzy ou sem 3 canhões, devolve "single" — o caminho legado de
        laser único de `_create_laser_pattern` é tomado em `_create_lasers_from_data`.
        """
        if not self.frenzy_mode or len(self.cannons) < 3:
            return "single"
        return random.choice(["wall", "salvo"])

    def _update_charging_state(self, dt: float) -> None:
        acc_dt = self._get_accelerated_dt(dt)
        self.charge_timer.update(dt)
        self.charge_progress = min(
            1.0, self.charge_progress + acc_dt / self.charge_duration
        )
        for c in self.cannons:
            c.set_charging(True, self.charge_progress)

        self.particle_system.generate_charging_particles(
            self.face_center.x, self.face_center.y
        )

        if self.charge_timer.done():
            self._sound_events.append("stop_charging")
            self.state = BossState.CONVERGING

    def _update_converging_state(self) -> List[BossLaser]:
        for c in self.cannons:
            c.set_charging(True, 1.0)

        if not self.particle_system.charging_particles:
            self.particle_system.create_circle_disappear_particles(
                self.face_center.x,
                self.face_center.y,
                Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS,
            )
            self.pending_laser_data = self._prepare_laser_data()
            self.state = BossState.PREPARING_TO_FIRE
            self.laser_delay_timer = self._get_laser_delay()
        return []

    def _prepare_laser_data(self) -> dict[str, Any]:
        pattern = self.frenzy_pattern or "single"
        if pattern in ("wall", "salvo") and (
            not self.frenzy_mode or len(self.cannons) < 3
        ):
            pattern = "single"

        locked_cannons: List[dict[str, Any]] = []
        for cannon in self.cannons:
            tip_x, tip_y = cannon.get_barrel_tip_position()
            direction = cannon.get_direction()
            locked_cannons.append(
                {
                    "tip_x": tip_x,
                    "tip_y": tip_y,
                    "dir_x": direction.x,
                    "dir_y": direction.y,
                }
            )
        return {
            "face_x": self.face_center.x,
            "face_y": self.face_center.y,
            "face_normal": self.facing_direction.copy(),
            "lifetime": Config.BOSS_FRENZY_LASER_LIFETIME
            if self.frenzy_mode
            else Config.BOSS_LASER_LIFETIME,
            "frenzy_mode": self.frenzy_mode,
            "pattern": pattern,
            # Estado da salva sequencial — só usado quando pattern == "salvo".
            # Ordem esquerdo → direito → central faz a sequência parecer o
            # laser principal executado 3 vezes em fila, só mais rápido.
            "salvo_idx": 0,
            "salvo_order": [0, 1, 2],
            "locked_cannons": locked_cannons,
        }

    def _update_preparing_to_fire_state(self, dt: float) -> List[BossLaser]:
        self.laser_delay_timer -= dt
        blink = (int(self.laser_delay_timer * 10) % 2) == 0
        if (
            self.pending_laser_data
            and self.pending_laser_data.get("pattern") == "salvo"
        ):
            next_idx = self.pending_laser_data["salvo_order"][
                self.pending_laser_data["salvo_idx"]
            ]
            if self.laser_delay_timer <= self._FRENZY_SALVO_AIM_WINDOW:
                self._active_salvo_cannon_idx = next_idx
                salvo_target_x = self.pending_laser_data.get("salvo_target_x")
                salvo_target_y = self.pending_laser_data.get("salvo_target_y")
                if salvo_target_x is None or salvo_target_y is None:
                    salvo_target_x = self.player_x
                    salvo_target_y = self.player_y
                    self.pending_laser_data["salvo_target_x"] = salvo_target_x
                    self.pending_laser_data["salvo_target_y"] = salvo_target_y
                if salvo_target_y is not None:
                    # Keep the visual telegraph locked to the same saved target
                    # that will be used by the actual laser shot.
                    self._aim_cannons(salvo_target_x, salvo_target_y)
                for i, c in enumerate(self.cannons):
                    c.set_charging(
                        i == next_idx,
                        1.0
                        if blink and i == next_idx
                        else 0.7
                        if i == next_idx
                        else 0.0,
                    )
            else:
                self._active_salvo_cannon_idx = None
                for c in self.cannons:
                    c.set_charging(False, 0.0)
        else:
            for c in self.cannons:
                c.set_charging(True, 1.0 if blink else 0.7)

        if self.laser_delay_timer > 0 or not self.pending_laser_data:
            return []

        # Salva: dispara um canhão por vez, repetindo a lógica do disparo
        # normal em ciclo curto. Cada tiro re-mira no jogador no instante do
        # disparo e depois aguarda a pausa curta de rearmamento.
        if self.pending_laser_data.get("pattern") == "salvo":
            return self._fire_next_salvo_shot()

        # Wall / single: dispara tudo de uma vez e entra em FIRING.
        new_lasers = self._create_lasers_from_data(self.pending_laser_data)
        self._sound_events.append("play_fire")
        self.fired_lasers.extend(new_lasers)
        self.fire_timer = Timer(self.pending_laser_data["lifetime"])
        self.fire_timer.start()
        self.state = BossState.FIRING
        self.pending_laser_data = None
        self.frenzy_pattern = None
        return new_lasers

    def _fire_next_salvo_shot(self) -> List[BossLaser]:
        """Dispara o próximo laser da salva a partir da pose travada do canhão."""
        if not hasattr(self, "_sound_events"):
            self._sound_events = []
        data = self.pending_laser_data
        if data is None:
            return []

        idx: int = data["salvo_idx"]
        order: List[int] = data["salvo_order"]
        cannon_idx: int = order[idx]
        # locked_cannons snapshot is not used for salvo shots anymore
        # (we re-aim at firing time), so omit the unused local variables.
        self._active_salvo_cannon_idx = cannon_idx

        # owner é sempre o canhão real; tip/direção vêm do alvo salvo na janela
        # de mira. Se não houver snapshot, cai no alvo atual como fallback.
        cannon = self.cannons[cannon_idx]
        target_x = data.get("salvo_target_x")
        target_y = data.get("salvo_target_y")
        if target_x is None or target_y is None:
            target_x = self.player_x
            target_y = self.player_y if self.player_y is not None else self.player_y

        if target_y is not None:
            # Re-aim using the saved player pose so the shot lands on the
            # older position rather than the live one.
            self._aim_cannons(target_x, target_y)

        tip_x, tip_y = cannon.get_barrel_tip_position()
        dirv = cannon.get_direction()

        laser = BossLaser(
            tip_x,
            tip_y,
            tip_x + dirv.x * self.LASER_DISTANCE,
            tip_y + dirv.y * self.LASER_DISTANCE,
            lifetime=data["lifetime"],
            owner=cannon,
        )
        self.fired_lasers.append(laser)
        self._sound_events.append("play_fire")

        # Clear the saved target so the next salvo step captures a fresh pose.
        data["salvo_target_x"] = None
        data["salvo_target_y"] = None

        data["salvo_idx"] = idx + 1
        if data["salvo_idx"] >= len(order):
            # Último disparo — entra em FIRING até o laser terminar de fato.
            self.fire_timer = Timer(data["lifetime"])
            self.fire_timer.start()
            self.state = BossState.FIRING
            self.pending_laser_data = None
            self.frenzy_pattern = None
            self._active_salvo_cannon_idx = None
            self._salvo_rearm_timer = 0.0
        else:
            # A próxima janela de mira reabre após uma pausa curta, sem esperar
            # o laser anterior terminar de viver.
            self.fire_timer = Timer(data["lifetime"])
            self.fire_timer.start()
            self.state = BossState.FIRING
            self._active_salvo_cannon_idx = None
            self._salvo_rearm_timer = self._FRENZY_SALVO_REARM_DELAY

        return [laser]

    def _create_lasers_from_data(self, laser_data: dict[str, Any]) -> List[BossLaser]:
        # Salvo é tratado em _fire_next_salvo_shot (um laser por chamada).
        # Wall usa o helper dedicado com offsets laterais grandes.
        # Single cai no caminho legado (laser único não-frenzy ou fallback).
        if laser_data.get("pattern") == "wall" and len(self.cannons) >= 3:
            return self._create_wall_lasers(laser_data["lifetime"])
        return self._create_laser_pattern(
            laser_data["face_x"],
            laser_data["face_y"],
            laser_data["lifetime"],
            laser_data["frenzy_mode"],
            laser_data["face_normal"],
        )

    def _create_wall_lasers(self, lifetime: float) -> List[BossLaser]:
        """Muro de Morte: 3 lasers simultâneos com o central normal.

        O laser do meio segue a direção principal do boss. Os laterais não
        fazem lock-in no jogador; eles apenas abrem em ângulo fixo em relação
        ao feixe principal, criando a parede sem depender de mira lateral.
        """
        if len(self.cannons) < 3:
            return []

        tip_cx, tip_cy = self.cannons[2].get_barrel_tip_position()
        base_dir = self.cannons[2].get_direction()

        def rotated_direction(angle: float) -> pygame.Vector2:
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            return pygame.Vector2(
                base_dir.x * cos_a - base_dir.y * sin_a,
                base_dir.x * sin_a + base_dir.y * cos_a,
            )

        side_angle = self.FRENZY_LASER_ANGLES[2]
        left_dir = rotated_direction(-side_angle)
        right_dir = rotated_direction(side_angle)

        lasers: List[BossLaser] = []
        # lateral esquerdo
        tip_x, tip_y = self.cannons[0].get_barrel_tip_position()
        lasers.append(
            BossLaser(
                tip_x,
                tip_y,
                tip_x + left_dir.x * self.LASER_DISTANCE,
                tip_y + left_dir.y * self.LASER_DISTANCE,
                lifetime=lifetime,
                owner=self.cannons[0],
            )
        )
        # lateral direito
        tip_x, tip_y = self.cannons[1].get_barrel_tip_position()
        lasers.append(
            BossLaser(
                tip_x,
                tip_y,
                tip_x + right_dir.x * self.LASER_DISTANCE,
                tip_y + right_dir.y * self.LASER_DISTANCE,
                lifetime=lifetime,
                owner=self.cannons[1],
            )
        )
        # meio normal
        lasers.append(
            BossLaser(
                tip_cx,
                tip_cy,
                tip_cx + base_dir.x * self.LASER_DISTANCE,
                tip_cy + base_dir.y * self.LASER_DISTANCE,
                lifetime=lifetime,
                owner=self.cannons[2],
            )
        )
        return lasers

    def _create_laser_pattern(
        self,
        face_x: float,
        face_y: float,
        lifetime: float,
        is_frenzy: bool,
        face_normal: pygame.Vector2,
    ) -> List[BossLaser]:
        if is_frenzy:
            # If we have multiple cannons (created on frenzy), spawn one laser per cannon
            if hasattr(self, "cannons") and len(self.cannons) >= 3:
                lasers: List[BossLaser] = []
                # offsets and sequence delays for left, right, center
                seq_delays = [0.0, 0.15, 0.35]  # tighter sequential cadence
                for idx, c in enumerate(self.cannons):
                    tip_x, tip_y = c.get_barrel_tip_position()
                    # Salva sequencial: o deslocamento vem da ordem e não de
                    # mira lateral. Cada canhão herda o vetor principal e aplica
                    # um pequeno desvio angular, sem lock-in nos adjacentes.
                    angle = 0.0
                    if idx == 0:
                        angle = -self.FRENZY_LASER_ANGLES[2]
                    elif idx == 1:
                        angle = self.FRENZY_LASER_ANGLES[2]
                    cos_a, sin_a = math.cos(angle), math.sin(angle)
                    dx = face_normal.x * cos_a - face_normal.y * sin_a
                    dy = face_normal.x * sin_a + face_normal.y * cos_a
                    lasers.append(
                        BossLaser(
                            tip_x,
                            tip_y,
                            tip_x + dx * self.LASER_DISTANCE,
                            tip_y + dy * self.LASER_DISTANCE,
                            lifetime=lifetime,
                            owner=c,
                            start_delay=seq_delays[min(idx, len(seq_delays) - 1)],
                        )
                    )
                return lasers
            # fallback: create fan from face center
            lasers: List[BossLaser] = []
            for i in [2, 0, 1]:
                ang = self.FRENZY_LASER_ANGLES[i]
                cos_a, sin_a = math.cos(ang), math.sin(ang)
                rot_dir = pygame.Vector2(
                    face_normal.x * cos_a - face_normal.y * sin_a,
                    face_normal.x * sin_a + face_normal.y * cos_a,
                )
                lasers.append(
                    BossLaser(
                        face_x,
                        face_y,
                        face_x + rot_dir.x * self.LASER_DISTANCE,
                        face_y + rot_dir.y * self.LASER_DISTANCE,
                        lifetime=lifetime,
                    )
                )
            return lasers
        return [
            BossLaser(
                face_x,
                face_y,
                face_x + face_normal.x * self.LASER_DISTANCE,
                face_y + face_normal.y * self.LASER_DISTANCE,
                lifetime=lifetime,
            )
        ]

    def _update_firing_state(self, dt: float) -> None:
        self.fire_timer.update(dt)

        if self.pending_laser_data and self.pending_laser_data.get("pattern") == "salvo":
            if self._salvo_rearm_timer > 0:
                self._salvo_rearm_timer = max(0.0, self._salvo_rearm_timer - dt)
                if self._salvo_rearm_timer == 0.0 and self.pending_laser_data:
                    if self.pending_laser_data["salvo_idx"] < len(
                        self.pending_laser_data["salvo_order"]
                    ):
                        self.state = BossState.PREPARING_TO_FIRE
                        self.laser_delay_timer = self._get_laser_delay()
                        return

        # A carga não congela no disparo: enquanto o feixe está vivo, o glow do
        # canhão segue aceso. As partículas da convergência seguem animando pelo
        # tick central em update(), sem congelar ao entrar em FIRING.
        still_firing = any(not laser.dead for laser in self.fired_lasers)
        for c in self.cannons:
            c.set_charging(still_firing, 1.0 if still_firing else 0.0)

        # Os lasers são atualizados pelo EntityManager (dono do ciclo de vida do
        # projétil, em _update_enemy_projectiles, respeitando freeze). Aqui só
        # observamos a conclusão — fired_lasers e em.boss_lasers referenciam os
        # mesmos objetos, então re-atualizar aqui duplicaria o avanço do timer.
        self.fired_lasers = [L for L in self.fired_lasers if not L.dead]
        if not self.fired_lasers:
            self._sound_events.append("stop_fire")

        if self.fire_timer.done() and all(
            L.is_animation_finished() for L in self.fired_lasers
        ):
            for c in self.cannons:
                c.set_charging(False, 0.0)
            self.state = BossState.ACTIVE
            self._reset_attack_timer()
            self.fired_lasers.clear()
            self._sound_events.append("stop_fire")

    def _reset_attack_timer(self) -> None:
        """Reset attack timer with random interval based on current mode."""
        self.attack_timer.duration = random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL)
        self.attack_timer.start()

    def _enter_charging(self) -> None:
        """Transition to CHARGING state and initialize charging phase."""
        self.state = BossState.CHARGING
        self.charge_progress = 0.0
        self.charge_timer.start()
        # Emit sound event for charging start so the sound system can play it
        if hasattr(self, "_sound_events"):
            self._sound_events.append("play_charging")
        for c in self.cannons:
            c.set_charging(True, 0.0)

    # Velocidade-base calibrada para 720p (altura de referência do design).
    # Em resoluções menores, a distância vertical boss→player encolhe
    # proporcionalmente; sem escalar a velocidade, a janela de reação fica
    # impossível em 576p/600p. Escalar pela altura mantém o time-to-impact
    # constante entre resoluções.
    _SQUARE_PROJECTILE_BASE_SPEED: float = 250.0
    _SQUARE_PROJECTILE_REF_HEIGHT: float = 720.0
    # Spread aleatório aplicado à direção normalizada. ±0.35 dá ~±20° de leque,
    # menos caótico que ±0.5 (que chegava a ±45° e cobria meia tela em 576p).
    _SQUARE_PROJECTILE_SPREAD: float = 0.35

    # Padrões de tiro frenzy com 3 canhões:
    #   "wall"  — 3 lasers simultâneos com offset lateral. Força fuga lateral
    #             ou encaixe em gap. Lasers em [-OFFSET, 0, +OFFSET] do alvo.
    #   "salvo" — 3 lasers sequenciais (esquerdo → direito → central), cada
    #             um re-mirando no jogador no instante do próprio disparo.
    #             Força movimento contínuo (zigue-zague).
    _FRENZY_WALL_OFFSET: float = 140.0  # px de distância lateral dos lasers do muro

    def _create_square_projectile(
        self, square: BossSquare, px: float, py: float
    ) -> BossSquare:
        dx, dy = px - square.x, py - square.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            spread = self._SQUARE_PROJECTILE_SPREAD
            dx, dy = (
                dx / dist + random.uniform(-spread, spread),
                dy / dist + random.uniform(-spread, spread),
            )
            new_dist = math.sqrt(dx * dx + dy * dy)
            if new_dist > 0:
                dx, dy = dx / new_dist, dy / new_dist
        else:
            dx, dy = 0, 1
        scale = Config.SCREEN_HEIGHT / self._SQUARE_PROJECTILE_REF_HEIGHT
        speed = self._SQUARE_PROJECTILE_BASE_SPEED * scale
        return BossSquare(square.x, square.y, dx * speed, dy * speed, square.base_size)

    def _get_animation_speed_multiplier(self) -> float:
        return (
            Config.BOSS_FRENZY_ANIMATION_SPEED_MULTIPLIER
            if self.frenzy_mode
            else Config.BOSS_ANIMATION_SPEED_MULTIPLIER
        )

    def _get_accelerated_dt(self, dt: float) -> float:
        return dt * self._get_animation_speed_multiplier()

    def _get_laser_delay(self) -> float:
        # Janela de reação para o jogador desviar antes do laser sair.
        return Config.BOSS_LASER_DELAY

    def _render_layer(self, layer_cells: set[str]) -> pygame.Surface:
        surf = pygame.Surface((int(self.w), int(self.h)), pygame.SRCALPHA)
        p = self.pixel_size
        for r, row in enumerate(PIXEL_MAP):
            for c, cell in enumerate(row):
                if cell in layer_cells:
                    pygame.draw.rect(
                        surf, (255, 255, 255), (int(c * p), int(r * p), int(p), int(p))
                    )
        return surf

    def _get_layer_surfaces(self) -> dict[str, pygame.Surface]:
        if not self._cached_layers:
            self._cached_layers["shell"] = self._render_layer({"A", "C", "D", "E", "F"})
            self._cached_layers["core"] = self._render_layer({"G", "H"})
            self._cached_layers["cannon_base"] = self._render_layer({"I", "M"})
        return self._cached_layers

    def _draw_layer(
        self,
        surface: pygame.Surface,
        layer_name: str,
        dx: int,
        dy: int,
        off_x: float = 0,
        off_y: float = 0,
    ):
        layers = self._get_layer_surfaces()
        if layer_name not in layers:
            return
        lsurf = layers[layer_name].copy()
        palette = self.current_palette

        cells = {
            "shell": {"A", "C", "D", "E", "F"},
            "core": {"G", "H"},
            "cannon_base": {"I", "M"},
        }[layer_name]
        p = self.pixel_size
        for r, row in enumerate(PIXEL_MAP):
            for c, cell in enumerate(row):
                if cell in cells:
                    pygame.draw.rect(
                        lsurf,
                        palette.get(cell, (255, 0, 255)),
                        (int(c * p), int(r * p), int(p), int(p)),
                    )
        surface.blit(lsurf, (int(dx + off_x), int(dy + off_y)))

    def draw(self, surface: pygame.Surface) -> None:
        dx, dy = int(self.x + self.shake_offset_x), int(self.y + self.shake_offset_y)

        # 1. Squares Behind
        self._draw_floating_squares(
            surface, self.shake_offset_x, self.shake_offset_y, behind=True
        )

        # 2. Body Layers with breathing
        breathing = math.sin(self.breathing_timer * 2.5) * 2.0
        self._draw_layer(surface, "shell", dx, dy, 0, breathing)
        self._draw_layer(surface, "core", dx, dy, 0, breathing * 1.5)
        self._draw_layer(surface, "cannon_base", dx, dy)

        # 3. Squares Front
        self._draw_floating_squares(
            surface, self.shake_offset_x, self.shake_offset_y, behind=False
        )

        # 4. Interactive Elements
        # draw all cannons (central last so it renders on top)
        for c in self.cannons:
            c.draw(surface, self.shake_offset_x, self.shake_offset_y)
        if self.state != BossState.ENTERING:
            self._draw_health_bar(surface)
        if self.shows_aiming_line:
            self._draw_aiming_line(surface)

        # 5. Effects
        if self.shows_charge_circle:
            rad = (
                self.charge_progress * Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS
                if self.state == BossState.CHARGING
                else Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS
            )
            if rad > 0:
                pygame.draw.circle(
                    surface,
                    (255, 255, 100),
                    (
                        int(self.face_center.x + self.shake_offset_x),
                        int(self.face_center.y + self.shake_offset_y),
                    ),
                    int(rad),
                    4,
                )
                if rad > 8:
                    pygame.draw.circle(
                        surface,
                        (255, 255, 0),
                        (
                            int(self.face_center.x + self.shake_offset_x),
                            int(self.face_center.y + self.shake_offset_y),
                        ),
                        int(rad - 8),
                        2,
                    )
            self.particle_system.draw_particles(
                surface, self.shake_offset_x, self.shake_offset_y
            )

        if self.state == BossState.PREPARING_TO_FIRE:
            if (pygame.time.get_ticks() % 200) < 100:
                pygame.draw.circle(
                    surface,
                    (255, 255, 255),
                    (
                        int(self.face_center.x + self.shake_offset_x),
                        int(self.face_center.y + self.shake_offset_y),
                    ),
                    12,
                    3,
                )

        self.particle_system.draw_circle_disappear_particles(
            surface, self.shake_offset_x, self.shake_offset_y
        )

    def _draw_floating_squares(
        self, surface: pygame.Surface, off_x: float, off_y: float, behind: bool
    ) -> None:
        for i, sq in enumerate(self.floating_squares):
            if (i % 2 == 0) != behind:
                continue

            color, border = (255, 0, 0), (255, 100, 100)  # Fallback
            if sq.state in ("preparing", "launching"):
                p = 0.5 + 0.5 * abs(math.sin(sq.prepare_timer * 8))
                color, border = (255, int(200 * p), 0), (255, 255, 0)
            else:
                pal = self.current_palette
                # No frenzy usamos a cor do chassi ou similar
                color = pal.get("C", (200, 0, 0))
                intensity = 0.7 + (i / len(self.floating_squares)) * 0.3
                color = (
                    int(color[0] * intensity),
                    int(color[1] * intensity),
                    int(color[2] * intensity),
                )
                border = (
                    min(255, color[0] + 50),
                    min(255, color[1] + 50),
                    min(255, color[2] + 50),
                )

            if sq.rotation > 0:
                self._draw_rotated_square(surface, sq, color, border, off_x, off_y)
            else:
                r = pygame.Rect(
                    int(sq.x - sq.size / 2 + off_x),
                    int(sq.y - sq.size / 2 + off_y),
                    int(sq.size),
                    int(sq.size),
                )
                pygame.draw.rect(surface, color, r)
                pygame.draw.rect(surface, border, r, 2)

    def _draw_rotated_square(
        self,
        surface: pygame.Surface,
        sq: BossSquare,
        color: Tuple[int, int, int],
        border: Tuple[int, int, int],
        ox: float,
        oy: float,
    ) -> None:
        corners = rotated_square_corners(
            sq.x + ox, sq.y + oy, sq.size / 2, math.radians(sq.rotation)
        )
        pygame.draw.polygon(surface, color, corners)
        pygame.draw.polygon(surface, border, corners, 2)

    def _get_aiming_line_intensity(self) -> float:
        """Calcula a intensidade do traçado de mira baseado no estado.
        0.0 = mínimo, 1.0 = máximo (último frame antes de travar o alvo).

        Em PREPARING_TO_FIRE a mira já foi encerrada (ver _draw_aiming_line):
        a janela de reação é cega, sem tracejado.
        """
        if self.state == BossState.AIMING:
            return 0.3  # Fraco durante a mira inicial
        elif self.state == BossState.CHARGING:
            # Aumenta com o progresso de carga (0 -> 1)
            return 0.3 + self.charge_progress * 0.5  # 0.3 -> 0.8
        elif self.state == BossState.CONVERGING:
            return 1.0  # Máximo: último frame com mira antes de travar o alvo
        return 0.0

    def _draw_aiming_line(self, surface: pygame.Surface) -> None:
        # Gradual ramp: start smoothing in late CHARGING, ramp through
        # CONVERGING and reach full intensity in PREPARING_TO_FIRE. This
        # provides a progressive visual anticipation instead of a sudden
        # jump.
        total_cycle = Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
        base_intensity = self._get_aiming_line_intensity()

        if self.state == BossState.PREPARING_TO_FIRE:
            ramp = 1.0
        elif self.state == BossState.CONVERGING:
            ramp = 0.8
        elif self.state == BossState.CHARGING:
            # Start ramping after ~40% charge, finish by 100%.
            ramp = min(max((self.charge_progress - 0.4) / 0.6, 0.0), 1.0)
        else:
            ramp = 0.0

        # Slightly bias ramp in frenzy for more urgency
        if self.frenzy_mode:
            ramp = min(1.0, ramp + 0.15)

        # Blend intensity and animation speed based on ramp (smooth transition)
        intensity = base_intensity + (1.0 - base_intensity) * ramp
        time_multiplier = 0.1 + (0.45 - 0.1) * ramp
        time_based_offset = int(pygame.time.get_ticks() * time_multiplier) % total_cycle

        # Suppress dashed aiming during salvo rearm transitions or if data is missing.
        if self.state == BossState.PREPARING_TO_FIRE:
            if self.pending_laser_data is None:
                return
            if (
                self.pending_laser_data.get("pattern") == "salvo"
                and self.laser_delay_timer > self._FRENZY_SALVO_AIM_WINDOW
            ):
                return

        # Avoid drawing the full aiming fan during salvo rearm transitions.
        # For salvo we only draw the active cannon when inside the aim window.
        if self.frenzy_mode and len(self.cannons) > 1:
            if self.frenzy_pattern == "wall":
                center_cannon = self.central
                center_tip = pygame.Vector2(center_cannon.get_barrel_tip_position())
                center_dir = center_cannon.get_direction()
                angle = self.FRENZY_LASER_ANGLES[2]
                left_dir = pygame.Vector2(
                    center_dir.x * math.cos(-angle) - center_dir.y * math.sin(-angle),
                    center_dir.x * math.sin(-angle) + center_dir.y * math.cos(-angle),
                )
                right_dir = pygame.Vector2(
                    center_dir.x * math.cos(angle) - center_dir.y * math.sin(angle),
                    center_dir.x * math.sin(angle) + center_dir.y * math.cos(angle),
                )
                self._draw_dashed_line(
                    surface,
                    pygame.Vector2(self.cannons[0].get_barrel_tip_position()),
                    left_dir,
                    time_based_offset,
                    False,
                    intensity,
                )
                self._draw_dashed_line(
                    surface,
                    pygame.Vector2(self.cannons[1].get_barrel_tip_position()),
                    right_dir,
                    time_based_offset,
                    False,
                    intensity,
                )
                self._draw_dashed_line(
                    surface,
                    center_tip,
                    center_dir,
                    time_based_offset,
                    True,
                    intensity,
                )
            else:
                # If we're in a salvo prepare phase, only show the aiming line
                # for the active salvo cannon and only when inside the aim window.
                is_salvo = (
                    self.pending_laser_data is not None
                    and self.pending_laser_data.get("pattern") == "salvo"
                )
                if is_salvo and self.state == BossState.PREPARING_TO_FIRE:
                    # show only when within the final aim window
                    if self.laser_delay_timer > self._FRENZY_SALVO_AIM_WINDOW:
                        return
                for i, c in enumerate(self.cannons):
                    # when salvo, skip non-active cannons
                    if is_salvo and i != self._active_salvo_cannon_idx:
                        continue
                    tip_x, tip_y = c.get_barrel_tip_position()
                    tip = pygame.Vector2(tip_x, tip_y)
                    dirv = c.get_direction()
                    primary = i == len(self.cannons) - 1
                    self._draw_dashed_line(
                        surface, tip, dirv, time_based_offset, primary, intensity
                    )
        else:
            self._draw_dashed_line(
                surface,
                self.face_center,
                self.facing_direction,
                time_based_offset,
                True,
                intensity,
            )

    def _draw_dashed_line(
        self,
        surface: pygame.Surface,
        start: pygame.Vector2,
        direction: pygame.Vector2,
        offset: int,
        primary: bool,
        intensity: float = 0.5,
    ) -> None:
        # Aumentar cor conforme intensidade
        base_color = (
            colors.BOSS_AIM_LINE
            if primary
            else tuple(max(50, int(c * 0.6)) for c in colors.BOSS_AIM_LINE)
        )
        # Interpolar cor: base -> brilho vermelho conforme intensidade
        r = int(base_color[0] + (255 - base_color[0]) * intensity)
        g = int(base_color[1] + (50 - base_color[1]) * intensity)
        b = int(base_color[2] + (50 - base_color[2]) * intensity)
        color = (r, g, b)

        # Aumentar largura conforme intensidade
        base_width = 4 if primary else 2
        width = max(
            base_width, int(base_width + intensity * 6)
        )  # base_width -> base_width + 6

        curr_dist = offset - (Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH)
        while curr_dist < self.LASER_DISTANCE:
            if curr_dist + Config.BOSS_AIM_DASH_LENGTH > 0:
                s_dist, e_dist = (
                    max(0, curr_dist),
                    min(self.LASER_DISTANCE, curr_dist + Config.BOSS_AIM_DASH_LENGTH),
                )
                pygame.draw.line(
                    surface,
                    color,
                    start + direction * s_dist,
                    start + direction * e_dist,
                    width,
                )
            curr_dist += Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        if self.health <= 0:
            return
        bmw, bh = min(200, self.w * 2), 10
        bx, by = self.x + (self.w - bmw) / 2, self.y - 20
        pygame.draw.rect(surface, (255, 0, 0), (bx, by, bmw, bh))
        pygame.draw.rect(
            surface,
            (0, 255, 0),
            (bx, by, int(bmw * (self.health / self.max_health)), bh),
        )

    def can_take_damage(self) -> bool:
        return self.state != BossState.ENTERING and not self.dead

    def get_rect(self) -> pygame.Rect:
        if not self.can_take_damage():
            return pygame.Rect(-1000, -1000, 0, 0)
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    @property
    def rect(self) -> pygame.Rect:
        return self.get_rect()

    def collision_circle(self) -> tuple[float, float, float]:
        if not self.can_take_damage():
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def take_damage(self, amount: int) -> None:
        if not self.can_take_damage():
            return
        self.health -= amount
        if self.health <= 0:
            self.health, self.dead = 0, True
        if (
            not self.frenzy_mode
            and not self.pending_frenzy
            and self.health <= self.max_health * Config.BOSS_FRENZY_THRESHOLD
        ):
            if not self._in_committed_attack:
                self._activate_frenzy_mode()
            else:
                self.pending_frenzy = True

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT

    def get_explosion_duration(self) -> float:
        return Config.BOSS_EXPLOSION_DURATION
