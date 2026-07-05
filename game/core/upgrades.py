from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional, Protocol

from .config import config as Config


class UpgradeCategory(Enum):
    DEFENSIVE = auto()
    UTILITY = auto()
    OFFENSIVE = auto()


class UpgradeType(Enum):
    SHIELD_BURST = auto()
    HEAL = auto()
    EMP = auto()
    HOMING_SHOT = auto()
    LASER_SHOT = auto()
    EXPLOSIVE_SHOT = auto()
    AIR_STRIKE = auto()  # Ultimate: Bombardeio Aéreo
    BLACK_HOLE = auto()  # Ultimate: Buraco Negro
    CANNON_TOWER = auto()  # Ultimate: Torres de Canhão
    # Novas Variantes
    BLINK_DASH = auto()  # Teleporte curto/Dash evasivo
    GRAVITY_BOMB = auto()  # Granada que cria mini-vórtice de atração
    CHAIN_LIGHTNING = auto()  # Tiro que salta entre inimigos
    ORBITAL_SHIELD = auto()  # Escudos orbitais físicos que bloqueiam tiros
    PLASMA_BEAM = auto()  # Feixe contínuo frontal destruidor
    WINGMAN = auto()  # Naves de escolta autônomas
    BERSERK = auto()  # Ataque omnidirecional insano
    COOP_LINK = auto()  # Feixe de dano cooperativo


class UpgradeContextProtocol(Protocol):
    """Contexto necessário para upgrades operarem."""

    @property
    def ship(self) -> Any: ...

    @property
    def entity_manager(self) -> Any: ...

    @property
    def difficulty_settings(self) -> Dict[str, Any]: ...

    @property
    def sound_manager(self) -> Any: ...

    @property
    def god_mode(self) -> bool: ...

    @property
    def scene(self) -> Any: ...


@dataclass
class UpgradeMeta:
    type: UpgradeType
    name: str
    desc: str
    icon_id: str
    category: UpgradeCategory
    base_cooldown: float
    base_duration: float
    base_charges: Optional[int]  # None = ilimitado por fase
    slot_weight: int = (
        1  # Peso em slots (1-5): quanto mais forte o upgrade, mais pesado
    )


class ActiveUpgrade:
    """Classe base de upgrades ativos."""

    def __init__(self, meta: UpgradeMeta) -> None:
        self.meta = meta
        self.cooldown_left: float = 0.0
        self.duration_left: float = 0.0
        self.charges_left: Optional[int] = meta.base_charges
        self.active: bool = False

    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self.active and not self.allows_refresh():
            return False
        if self.cooldown_left > 0.0:
            return False
        if self.charges_left is not None and self.charges_left <= 0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContextProtocol) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        if self.charges_left is not None:
            self.charges_left -= 1

        self.duration_left = self.get_effective_duration(ctx)
        self.cooldown_left = self.get_effective_cooldown(ctx)
        self.active = True

        self.on_activate_effect(ctx)
        self.on_after_activate(ctx)
        return True

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        if self.cooldown_left > 0.0:
            old_cooldown = self.cooldown_left
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

            if old_cooldown > 0.0 and self.cooldown_left == 0.0:
                if self.charges_left is not None and self.meta.base_charges is not None:
                    if self.charges_left < self.meta.base_charges:
                        self.charges_left += 1
                        if self.charges_left < self.meta.base_charges:
                            self.cooldown_left = self.get_effective_cooldown(ctx)

        if self.active:
            self.duration_left = max(0.0, self.duration_left - dt)
            if self.duration_left <= 0.0:
                self.active = False
                self.on_expire(ctx)

    @staticmethod
    def _ctx_ship(ctx: Optional[UpgradeContextProtocol]) -> Any:
        return getattr(ctx, "ship", None)

    @staticmethod
    def _ctx_entity_manager(ctx: Optional[UpgradeContextProtocol]) -> Any:
        return getattr(ctx, "entity_manager", None)

    @staticmethod
    def _ctx_scene(ctx: Optional[UpgradeContextProtocol]) -> Any:
        return getattr(ctx, "scene", None)

    @staticmethod
    def _ctx_attr(
        ctx: Optional[UpgradeContextProtocol], name: str, default: Any = None
    ) -> Any:
        return getattr(ctx, name, default)

    def additional_can_activate(self, _ctx: UpgradeContextProtocol) -> bool:
        return True

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        pass

    def on_after_activate(self, ctx: UpgradeContextProtocol) -> None:
        try:
            sm = self._ctx_attr(ctx, "sound_manager")
            if sm:
                sm.play_upgrade_activate()
        except Exception:
            pass

    def on_denied(self, ctx: UpgradeContextProtocol) -> None:

        try:
            sm = self._ctx_attr(ctx, "sound_manager")
            if sm:
                sm.play_upgrade_denied()
        except Exception:
            pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        pass

    def get_effective_cooldown(self, ctx: Optional[UpgradeContextProtocol]) -> float:
        cd = self.meta.base_cooldown
        if self._ctx_attr(ctx, "god_mode", False):
            return 1.0
        ds = self._ctx_attr(ctx, "difficulty_settings")
        if ds and "no_powerups" in ds.get("special_rules", []):
            cd *= 1.5
        return cd

    def get_effective_duration(self, _ctx: Optional[UpgradeContextProtocol]) -> float:
        return self.meta.base_duration

    def get_ui_state(self) -> Dict[str, Any]:
        """Retorna o estado do upgrade para renderização na HUD."""
        return {
            "name": self.meta.name,
            "icon_id": self.meta.icon_id,
            "cooldown_left": max(0.0, self.cooldown_left),
            "cooldown": self.meta.base_cooldown,
            "active": self.active,
            "duration_left": max(0.0, self.duration_left),
            "charges_left": self.charges_left,
            "desc": self.meta.desc,
        }


class ShieldBurstUpgrade(ActiveUpgrade):
    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._monitoring_shield = False

    def allows_refresh(self) -> bool:
        return False

    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self._monitoring_shield:
            return False
        if self.cooldown_left > 0.0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContextProtocol) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False
        self._monitoring_shield = True
        self.active = True
        self.on_activate_effect(ctx)
        self.on_after_activate(ctx)
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship and hasattr(ship, "activate_shield"):
            ship.activate_shield(9999.0, shield_hp=1)

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)
        if self._monitoring_shield and ctx is not None:
            ship = self._ctx_ship(ctx)
            if ship and not getattr(ship, "has_shield", False):
                self._monitoring_shield = False
                self.active = False
                self.cooldown_left = self.get_effective_cooldown(ctx)


class HealUpgrade(ActiveUpgrade):
    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)

    def additional_can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        ship = self._ctx_ship(ctx)
        if not ship:
            return False
        cap = getattr(ship, "max_lives", 5)
        return getattr(ship, "lives", 0) < cap

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        scene = self._ctx_scene(ctx)
        if ship:
            if scene and hasattr(scene, "_change_lives"):
                scene._change_lives(1)
            else:
                ship.lives = min(
                    getattr(ship, "max_lives", 5), getattr(ship, "lives", 0) + 1
                )


class EMPUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        em = self._ctx_entity_manager(ctx)
        ship = self._ctx_ship(ctx)
        if not em:
            return
        duration = self.get_effective_duration(ctx)
        if ship and hasattr(em, "spawn_emp_wave"):
            em.spawn_emp_wave(ship.x + ship.w / 2, ship.y + ship.h / 2)
        setattr(em, "emp_active", True)
        setattr(em, "emp_timer", duration)
        # Fator de lentidão: o refactor parou de setá-lo e o _emp_state lia 1.0
        # → o EMP não desacelerava mais. Import local evita ciclo com
        # upgrades_config (que importa UpgradeType deste módulo).
        from .upgrades_config import EMP_SLOW_FACTOR

        setattr(em, "emp_slow_factor", float(EMP_SLOW_FACTOR))

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        em = self._ctx_entity_manager(ctx)
        if em:
            setattr(em, "emp_active", False)


class BlinkDashUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            ship.activate_dash(self.get_effective_duration(ctx))


class GravityBombUpgrade(ActiveUpgrade):
    VORTEX_COUNT = 5
    VORTEX_SPAWN_INTERVAL = 3.0
    VORTEX_DURATION = 15.0
    VORTEX_MIN_DISTANCE = 350.0
    VORTEX_PLACEMENT_ATTEMPTS = 20

    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._vortexes_to_spawn = 0
        self._spawn_timer = 0.0
        self._spawned_positions: list[tuple[float, float]] = []

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        self._vortexes_to_spawn = self.VORTEX_COUNT
        self._spawn_timer = self.VORTEX_SPAWN_INTERVAL
        self._spawned_positions.clear()

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        super().update(dt, ctx)
        if self.active and self._vortexes_to_spawn > 0 and ctx:
            self._spawn_timer += dt
            if self._spawn_timer >= self.VORTEX_SPAWN_INTERVAL:
                self._spawn_timer = 0.0
                self._spawn_vortex(ctx)
                self._vortexes_to_spawn -= 1

    def _spawn_vortex(self, ctx: UpgradeContextProtocol) -> None:
        em = self._ctx_entity_manager(ctx)
        if not em or not hasattr(em, "spawn_black_hole"):
            return
        sw, sh = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        min_dist_sq = self.VORTEX_MIN_DISTANCE**2
        best_pos = None
        for _ in range(self.VORTEX_PLACEMENT_ATTEMPTS):
            rx = random.uniform(sw * 0.1, sw * 0.9)
            ry = random.uniform(sh * 0.1, sh * 0.9)
            if all(
                (rx - px) ** 2 + (ry - py) ** 2 >= min_dist_sq
                for px, py in self._spawned_positions
            ):
                best_pos = (rx, ry)
                break
        if best_pos is None:
            best_pos = (
                random.uniform(sw * 0.1, sw * 0.9),
                random.uniform(sh * 0.1, sh * 0.9),
            )
        self._spawned_positions.append(best_pos)
        em.spawn_black_hole(
            best_pos[0], best_pos[1], self.VORTEX_DURATION, is_vortex=True
        )


class ChainLightningUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            ship.activate_chain_shot(self.get_effective_duration(ctx))


class OrbitalShieldUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_orbital_shield"):
            em.spawn_orbital_shield(ship, self.get_effective_duration(ctx))


class PlasmaBeamUpgrade(ActiveUpgrade):
    SPEED_PENALTY = 0.05

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if not ship or not em or not hasattr(em, "spawn_plasma_beam"):
            return
        em.spawn_plasma_beam(ship, self.get_effective_duration(ctx))
        ship.speed = ship.original_speed * self.SPEED_PENALTY

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            ship.speed = ship.original_speed


class WingmanUpgrade(ActiveUpgrade):
    """Naves de escolta autônomas que perseguem inimigos."""

    DRONE_COUNT = 3
    DRONE_SPAWN_INTERVAL = 5.0

    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._wingmen_to_spawn = 0
        self._spawn_timer = 0.0

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        self._wingmen_to_spawn = self.DRONE_COUNT
        # Primeiro drone nasce imediatamente.
        self._spawn_timer = self.DRONE_SPAWN_INTERVAL

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        super().update(dt, ctx)

        if self._wingmen_to_spawn > 0 and ctx is not None:
            self._spawn_timer += dt
            if self._spawn_timer >= self.DRONE_SPAWN_INTERVAL:
                self._spawn_timer = 0.0
                self._spawn_wingman_drone(ctx)
                self._wingmen_to_spawn -= 1

    def _spawn_wingman_drone(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if not ship or not em or not hasattr(em, "spawn_wingman"):
            return
        em.spawn_wingman(ship, self.meta.base_duration)


class BerserkUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            ship.activate_berserk(self.get_effective_duration(ctx))


class BlackHoleUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_black_hole"):
            em.spawn_black_hole(
                ship.x + ship.w / 2, ship.y - 100, self.get_effective_duration(ctx)
            )


class AirStrikeUpgrade(ActiveUpgrade):
    """Ultimate: bombardeio aéreo massivo — uma salva de bombas cai em
    posições aleatórias da tela ao longo de alguns segundos.

    Um refactor antigo reduziu isto a uma única bomba fixa perto da nave (a
    salva foi perdida). Aqui a contagem e o intervalo ficam na classe e o
    disparo é sequencial, no mesmo padrão de WingmanUpgrade/GravityBombUpgrade:
    ``on_activate_effect`` arma a contagem e ``update`` solta uma bomba por vez.
    Como ``base_duration`` é 0, a salva não depende de ``self.active`` (o
    contador ``_bombs_remaining`` é a única condição), igual ao Wingman.
    """

    BOMB_COUNT = 10
    SPAWN_INTERVAL = 0.25  # segundos entre cada bomba da salva

    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._bombs_remaining = 0
        self._spawn_timer = 0.0

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        # Primeira bomba cai na hora (feedback imediato); o resto na salva.
        self._bombs_remaining = self.BOMB_COUNT
        self._spawn_timer = 0.0
        self._spawn_bomb(ctx)
        self._bombs_remaining -= 1

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        super().update(dt, ctx)
        if self._bombs_remaining > 0 and ctx is not None:
            self._spawn_timer += dt
            if self._spawn_timer >= self.SPAWN_INTERVAL:
                self._spawn_timer = 0.0
                self._spawn_bomb(ctx)
                self._bombs_remaining -= 1

    def _spawn_bomb(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        em = self._ctx_entity_manager(ctx)
        if not em or not hasattr(em, "spawn_air_strike"):
            return
        sw, sh = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        tx = random.uniform(sw * 0.08, sw * 0.92)
        ty = random.uniform(sh * 0.10, sh * 0.75)
        em.spawn_air_strike(tx, ty)


class CannonTowerUpgrade(ActiveUpgrade):
    """Ultimate: duas torres fixas nas laterais inferiores que disparam minas.

    As torres são estáticas — posição derivada da tela, não do jogador (o que
    fazia a torre estacionar no meio). Restaura o comportamento original:
    laterais em 15%/85% da largura, ~120px acima do fundo.
    """

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if not (ship and em and hasattr(em, "spawn_cannon_tower")):
            return
        # `x` é o canto esquerdo da torre (largura 60, ver CannonTower.w).
        # Descontamos a largura na direita para que as folgas até as bordas
        # fiquem simétricas (ambas a 15% da largura da tela).
        tower_w = 60
        left_x = Config.SCREEN_WIDTH * 0.15
        right_x = Config.SCREEN_WIDTH * 0.85 - tower_w
        tower_y = float(Config.SCREEN_HEIGHT - 120)
        em.spawn_cannon_tower(left_x, tower_y)
        em.spawn_cannon_tower(right_x, tower_y)


class HomingShotUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if not ship:
            return
        from .upgrades_config import HOMING_FIRE_RATE_PENALTY, HOMING_SPEED_PENALTY

        ship.activate_homing_shots(
            self.get_effective_duration(ctx),
            HOMING_SPEED_PENALTY,
            HOMING_FIRE_RATE_PENALTY,
        )


class LaserShotUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            ship.activate_orbital_lasers(self.get_effective_duration(ctx))


class ExplosiveShotUpgrade(ActiveUpgrade):
    BULLETS_PER_ACTIVATION = 15

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            ship.activate_explosive_shots(self.BULLETS_PER_ACTIVATION)


class CoopLinkUpgrade(ActiveUpgrade):
    """Feixe de alta voltagem que conecta dois jogadores."""

    @staticmethod
    def _alive_ships(scene: Any) -> list[Any]:
        roster = getattr(scene, "roster", None) if scene is not None else None
        if roster is None:
            return []
        return [slot.ship for slot in roster.alive_slots()]

    def additional_can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        return len(self._alive_ships(self._ctx_scene(ctx))) >= 2

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        em = self._ctx_entity_manager(ctx)
        ships = self._alive_ships(self._ctx_scene(ctx))
        if not em or len(ships) < 2 or not hasattr(em, "spawn_coop_link"):
            return
        em.spawn_coop_link(ships[0], ships[1], self.get_effective_duration(ctx))


def upgrade_factory(upgrade_type: UpgradeType) -> ActiveUpgrade:
    factories: Dict[UpgradeType, type[ActiveUpgrade]] = {
        UpgradeType.SHIELD_BURST: ShieldBurstUpgrade,
        UpgradeType.HEAL: HealUpgrade,
        UpgradeType.EMP: EMPUpgrade,
        UpgradeType.HOMING_SHOT: HomingShotUpgrade,
        UpgradeType.LASER_SHOT: LaserShotUpgrade,
        UpgradeType.EXPLOSIVE_SHOT: ExplosiveShotUpgrade,
        UpgradeType.BLINK_DASH: BlinkDashUpgrade,
        UpgradeType.GRAVITY_BOMB: GravityBombUpgrade,
        UpgradeType.CHAIN_LIGHTNING: ChainLightningUpgrade,
        UpgradeType.ORBITAL_SHIELD: OrbitalShieldUpgrade,
        UpgradeType.PLASMA_BEAM: PlasmaBeamUpgrade,
        UpgradeType.WINGMAN: WingmanUpgrade,
        UpgradeType.BERSERK: BerserkUpgrade,
        UpgradeType.BLACK_HOLE: BlackHoleUpgrade,
        UpgradeType.AIR_STRIKE: AirStrikeUpgrade,
        UpgradeType.CANNON_TOWER: CannonTowerUpgrade,
        UpgradeType.COOP_LINK: CoopLinkUpgrade,
    }
    cls = factories.get(upgrade_type)
    if cls:
        return cls(UPGRADES_META[upgrade_type])
    raise ValueError(f"Unknown upgrade type: {upgrade_type}")


def create_upgrade(upgrade_type: UpgradeType) -> ActiveUpgrade:
    """Wrapper para compatibilidade com o código legado."""
    return upgrade_factory(upgrade_type)


UPGRADES_META: Dict[UpgradeType, UpgradeMeta] = {
    UpgradeType.SHIELD_BURST: UpgradeMeta(
        UpgradeType.SHIELD_BURST,
        "SHLD",
        "Escudo absorve 1 hit.",
        "shield_burst",
        UpgradeCategory.DEFENSIVE,
        45,
        0,
        None,
        2,
    ),
    UpgradeType.HEAL: UpgradeMeta(
        UpgradeType.HEAL,
        "HEAL",
        "Restaura 1 vida.",
        "heal",
        UpgradeCategory.DEFENSIVE,
        60,
        0,
        None,
        1,
    ),
    UpgradeType.EMP: UpgradeMeta(
        UpgradeType.EMP,
        "EMP",
        "Onda que desacelera inimigos.",
        "emp",
        UpgradeCategory.UTILITY,
        50,
        10,
        None,
        2,
    ),
    UpgradeType.HOMING_SHOT: UpgradeMeta(
        UpgradeType.HOMING_SHOT,
        "HOMING",
        "Tiros teleguiados com cadência reduzida.",
        "homing_shot",
        UpgradeCategory.OFFENSIVE,
        60,
        12,
        None,
        2,
    ),
    UpgradeType.LASER_SHOT: UpgradeMeta(
        UpgradeType.LASER_SHOT,
        "LASER",
        "Orbes laser disparam em sequência.",
        "laser_shot",
        UpgradeCategory.OFFENSIVE,
        80,
        0,
        None,
        2,
    ),
    UpgradeType.EXPLOSIVE_SHOT: UpgradeMeta(
        UpgradeType.EXPLOSIVE_SHOT,
        "EXPL",
        "Próximos tiros explodem em área.",
        "explosive_shot",
        UpgradeCategory.OFFENSIVE,
        70,
        0,
        None,
        2,
    ),
    UpgradeType.BLINK_DASH: UpgradeMeta(
        UpgradeType.BLINK_DASH,
        "DASH",
        "Dash curto invulnerável.",
        "blink_dash",
        UpgradeCategory.DEFENSIVE,
        15,
        0.4,
        None,
        1,
    ),
    UpgradeType.GRAVITY_BOMB: UpgradeMeta(
        UpgradeType.GRAVITY_BOMB,
        "GRAV",
        "5 mini-vórtices corrosivos (15s).",
        "gravity_bomb",
        UpgradeCategory.UTILITY,
        60,
        15,
        None,
        2,
    ),
    UpgradeType.CHAIN_LIGHTNING: UpgradeMeta(
        UpgradeType.CHAIN_LIGHTNING,
        "LIGH",
        "Tiros que saltam entre inimigos.",
        "chain_lightning",
        UpgradeCategory.OFFENSIVE,
        60,
        10,
        None,
        2,
    ),
    UpgradeType.ORBITAL_SHIELD: UpgradeMeta(
        UpgradeType.ORBITAL_SHIELD,
        "ORB",
        "3 escudos físicos rotativos.",
        "orbital_shield",
        UpgradeCategory.DEFENSIVE,
        70,
        12,
        None,
        2,
    ),
    UpgradeType.PLASMA_BEAM: UpgradeMeta(
        UpgradeType.PLASMA_BEAM,
        "BEAM",
        "Lança de Plasma com explosão final.",
        "plasma_beam",
        UpgradeCategory.OFFENSIVE,
        110,
        5,
        None,
        3,
    ),
    UpgradeType.WINGMAN: UpgradeMeta(
        UpgradeType.WINGMAN,
        "WING",
        "3 drones de escolta sequenciais (30s).",
        "wingman",
        UpgradeCategory.OFFENSIVE,
        120,
        30,
        None,
        2,
    ),
    UpgradeType.BERSERK: UpgradeMeta(
        UpgradeType.BERSERK,
        "BERS",
        "Rajadas rotativas (Estrela Espiral).",
        "berserk",
        UpgradeCategory.OFFENSIVE,
        120,
        8,
        None,
        3,
    ),
    UpgradeType.BLACK_HOLE: UpgradeMeta(
        UpgradeType.BLACK_HOLE,
        "HOLE",
        "Buraco negro móvel Ultimate.",
        "black_hole",
        UpgradeCategory.OFFENSIVE,
        120,
        8,
        None,
        3,
    ),
    UpgradeType.AIR_STRIKE: UpgradeMeta(
        UpgradeType.AIR_STRIKE,
        "AIR",
        "10 bombas caem em áreas aleatórias.",
        "air_strike",
        UpgradeCategory.OFFENSIVE,
        180,
        0,
        None,
        3,
    ),
    UpgradeType.CANNON_TOWER: UpgradeMeta(
        UpgradeType.CANNON_TOWER,
        "CANNON",
        "Torres de minas estáticas.",
        "cannon_tower",
        UpgradeCategory.OFFENSIVE,
        200,
        0,
        None,
        3,
    ),
    UpgradeType.COOP_LINK: UpgradeMeta(
        UpgradeType.COOP_LINK,
        "LINK",
        "Feixe de alta voltagem entre jogadores.",
        "link",
        UpgradeCategory.UTILITY,
        45,
        15,
        None,
        2,
    ),
}


def list_all_upgrades_meta() -> list[UpgradeMeta]:
    return list(UPGRADES_META.values())


def get_upgrade_icon(upgrade_name: str, icon_id: str | None = None) -> str:
    mapping = {
        "shield_burst": "S",
        "heal": "H",
        "emp": "E",
        "homing_shot": "T",
        "laser_shot": "X",
        "explosive_shot": "V",
        "air_strike": "A",
        "black_hole": "B",
        "blink_dash": "D",
        "gravity_bomb": "G",
        "chain_lightning": "L",
        "orbital_shield": "R",
        "plasma_beam": "P",
        "wingman": "W",
        "berserk": "Z",
        "link": "C",
    }
    if icon_id and icon_id in mapping:
        return mapping[icon_id]
    return upgrade_name[0].upper() if upgrade_name else "?"
