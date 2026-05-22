from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional, Protocol

import pygame


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
    def _ctx_attr(ctx: Optional[UpgradeContextProtocol], name: str, default: Any = None) -> Any:
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
            if sm: sm.play_upgrade_activate()
        except: pass

    def on_denied(self, ctx: UpgradeContextProtocol) -> None:
        try:
            sm = self._ctx_attr(ctx, "sound_manager")
            if sm: sm.play_upgrade_denied()
        except: pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        pass

    def get_effective_cooldown(self, ctx: Optional[UpgradeContextProtocol]) -> float:
        cd = self.meta.base_cooldown
        if self._ctx_attr(ctx, "god_mode", False): return 1.0
        ds = self._ctx_attr(ctx, "difficulty_settings")
        if ds and "no_powerups" in ds.get("special_rules", []): cd *= 1.5
        return cd

    def get_effective_duration(self, _ctx: Optional[UpgradeContextProtocol]) -> float:
        return self.meta.base_duration


class ShieldBurstUpgrade(ActiveUpgrade):
    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._monitoring_shield = False

    def allows_refresh(self) -> bool:
        return False

    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self._monitoring_shield: return False
        if self.cooldown_left > 0.0: return False
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
        self.usage_count = 0

    def additional_can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self.usage_count >= 2: return False
        ship = self._ctx_ship(ctx)
        if not ship: return False
        cap = getattr(ship, "max_lives", 5)
        return getattr(ship, "lives", 0) < cap

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        self.usage_count += 1
        ship = self._ctx_ship(ctx)
        scene = self._ctx_scene(ctx)
        if ship:
            if scene and hasattr(scene, "_change_lives"):
                scene._change_lives(1)
            else:
                ship.lives = min(getattr(ship, "max_lives", 5), getattr(ship, "lives", 0) + 1)


class EMPUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        em = self._ctx_entity_manager(ctx)
        ship = self._ctx_ship(ctx)
        if not em: return
        duration = self.get_effective_duration(ctx)
        if ship and hasattr(em, "spawn_emp_wave"):
            em.spawn_emp_wave(ship.x + ship.w/2, ship.y + ship.h/2)
        setattr(em, "emp_active", True)
        setattr(em, "emp_timer", duration)

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        em = self._ctx_entity_manager(ctx)
        if em: setattr(em, "emp_active", False)


class BlinkDashUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if not ship: return
        duration = self.get_effective_duration(ctx)
        if hasattr(ship, "activate_dash"):
            ship.activate_dash(duration)
        else:
            setattr(ship, "dash_timer", duration)
            if not hasattr(ship, "original_speed"):
                setattr(ship, "original_speed", getattr(ship, "speed", 300))
            ship.speed = getattr(ship, "original_speed", 300) * 2.5
            if hasattr(ship, "get_facing_vector"):
                vx, vy = ship.get_facing_vector()
                setattr(ship, "dash_dir", pygame.math.Vector2(vx, vy))

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        ship = self._ctx_ship(ctx)
        if ship:
            setattr(ship, "dash_timer", 0.0)
            if hasattr(ship, "original_speed"):
                ship.speed = getattr(ship, "original_speed", 300)


class GravityBombUpgrade(ActiveUpgrade):
    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._vortexes_to_spawn = 0
        self._spawn_timer = 0.0
        self._spawn_interval = 3.0
        self._spawned_positions: list[tuple[float, float]] = []

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        self._vortexes_to_spawn = 5
        self._spawn_timer = self._spawn_interval
        self._spawned_positions.clear()

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        super().update(dt, ctx)
        if self.active and self._vortexes_to_spawn > 0 and ctx:
            self._spawn_timer += dt
            if self._spawn_timer >= self._spawn_interval:
                self._spawn_timer = 0.0
                self._spawn_vortex(ctx)
                self._vortexes_to_spawn -= 1

    def _spawn_vortex(self, ctx: UpgradeContextProtocol) -> None:
        em = self._ctx_entity_manager(ctx)
        if not em: return
        import random, math
        screen = pygame.display.get_surface()
        sw, sh = screen.get_size() if screen else (1600, 900)
        best_pos = None
        for _ in range(20):
            rx, ry = random.uniform(sw*0.1, sw*0.9), random.uniform(sh*0.1, sh*0.9)
            if all(math.hypot(rx-px, ry-py) >= 350 for px, py in self._spawned_positions):
                best_pos = (rx, ry); break
        if not best_pos: best_pos = (random.uniform(sw*0.1, sw*0.9), random.uniform(sh*0.1, sh*0.9))
        self._spawned_positions.append(best_pos)
        if hasattr(em, "spawn_black_hole"):
            em.spawn_black_hole(best_pos[0], best_pos[1], 15.0, is_vortex=True)


class ChainLightningUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship: setattr(ship, "chain_shot_timer", self.get_effective_duration(ctx))

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        ship = self._ctx_ship(ctx)
        if ship: setattr(ship, "chain_shot_timer", 0.0)


class OrbitalShieldUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_orbital_shield"):
            em.spawn_orbital_shield(ship, self.get_effective_duration(ctx))


class PlasmaBeamUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if not ship or not em: return
        if hasattr(em, "spawn_plasma_beam"):
            em.spawn_plasma_beam(ship, self.get_effective_duration(ctx))
        if not hasattr(ship, "original_speed"):
            setattr(ship, "original_speed", getattr(ship, "speed", 300.0))
        setattr(ship, "speed", getattr(ship, "original_speed", 300.0) * 0.05)

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        ship = self._ctx_ship(ctx)
        if ship and hasattr(ship, "original_speed"):
            setattr(ship, "speed", getattr(ship, "original_speed", 300.0))


class WingmanUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_wingman"):
            em.spawn_wingman(ship, self.get_effective_duration(ctx))


class BerserkUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship: setattr(ship, "berserk_timer", self.get_effective_duration(ctx))

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        ship = self._ctx_ship(ctx)
        if ship: setattr(ship, "berserk_timer", 0.0)


class BlackHoleUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_black_hole"):
            em.spawn_black_hole(ship.x + ship.w/2, ship.y - 100, self.get_effective_duration(ctx))


class AirStrikeUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_air_strike"):
            em.spawn_air_strike(ship.x + ship.w/2, ship.y - 200)


class CannonTowerUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if ship and em and hasattr(em, "spawn_cannon_tower"):
            em.spawn_cannon_tower(ship.x + ship.w/2 - 30, ship.y + ship.h/2)


class CoopLinkUpgrade(ActiveUpgrade):
    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        pass


def upgrade_factory(upgrade_type: UpgradeType) -> ActiveUpgrade:
    factories: Dict[UpgradeType, type[ActiveUpgrade]] = {
        UpgradeType.SHIELD_BURST: ShieldBurstUpgrade,
        UpgradeType.HEAL: HealUpgrade,
        UpgradeType.EMP: EMPUpgrade,
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
    }
    cls = factories.get(upgrade_type)
    if cls: return cls(UPGRADES_META[upgrade_type])
    raise ValueError(f"Unknown upgrade type: {upgrade_type}")


UPGRADES_META: Dict[UpgradeType, UpgradeMeta] = {
    UpgradeType.SHIELD_BURST: UpgradeMeta(UpgradeType.SHIELD_BURST, "SHLD", "Escudo absorve 1 hit.", "shield_burst", UpgradeCategory.DEFENSIVE, 45, 0, None, 2),
    UpgradeType.HEAL: UpgradeMeta(UpgradeType.HEAL, "HEAL", "Restaura 1 vida.", "heal", UpgradeCategory.DEFENSIVE, 60, 0, None, 1),
    UpgradeType.EMP: UpgradeMeta(UpgradeType.EMP, "EMP", "Onda que desacelera inimigos.", "emp", UpgradeCategory.UTILITY, 50, 10, None, 2),
    UpgradeType.BLINK_DASH: UpgradeMeta(UpgradeType.BLINK_DASH, "DASH", "Dash curto invulnerável.", "blink_dash", UpgradeCategory.DEFENSIVE, 15, 0.4, None, 1),
    UpgradeType.GRAVITY_BOMB: UpgradeMeta(UpgradeType.GRAVITY_BOMB, "GRAV", "5 mini-vórtices corrosivos (15s).", "gravity_bomb", UpgradeCategory.UTILITY, 60, 15, None, 2),
    UpgradeType.CHAIN_LIGHTNING: UpgradeMeta(UpgradeType.CHAIN_LIGHTNING, "LIGH", "Tiros que saltam entre inimigos.", "chain_lightning", UpgradeCategory.OFFENSIVE, 60, 10, None, 2),
    UpgradeType.ORBITAL_SHIELD: UpgradeMeta(UpgradeType.ORBITAL_SHIELD, "ORB", "Escudos físicos rotativos.", "orbital_shield", UpgradeCategory.DEFENSIVE, 70, 12, None, 2),
    UpgradeType.PLASMA_BEAM: UpgradeMeta(UpgradeType.PLASMA_BEAM, "BEAM", "Lança de Plasma com explosão final.", "plasma_beam", UpgradeCategory.OFFENSIVE, 110, 5, None, 3),
    UpgradeType.WINGMAN: UpgradeMeta(UpgradeType.WINGMAN, "WING", "Drone de escolta autônomo.", "wingman", UpgradeCategory.OFFENSIVE, 80, 20, None, 2),
    UpgradeType.BERSERK: UpgradeMeta(UpgradeType.BERSERK, "BERS", "Rajadas rotativas (Estrela Espiral).", "berserk", UpgradeCategory.OFFENSIVE, 120, 8, None, 3),
    UpgradeType.BLACK_HOLE: UpgradeMeta(UpgradeType.BLACK_HOLE, "HOLE", "Buraco negro móvel Ultimate.", "black_hole", UpgradeCategory.OFFENSIVE, 120, 8, None, 3),
    UpgradeType.AIR_STRIKE: UpgradeMeta(UpgradeType.AIR_STRIKE, "AIR", "Bombardeio aéreo massivo.", "air_strike", UpgradeCategory.OFFENSIVE, 180, 0, 30, 3),
    UpgradeType.CANNON_TOWER: UpgradeMeta(UpgradeType.CANNON_TOWER, "CANNON", "Torres de minas estáticas.", "cannon_tower", UpgradeCategory.OFFENSIVE, 200, 0, None, 3),
}

def list_all_upgrades_meta() -> list[UpgradeMeta]:
    return list(UPGRADES_META.values())

def get_upgrade_icon(upgrade_name: str, icon_id: str | None = None) -> str:
    mapping = {"shield_burst":"S", "heal":"H", "emp":"E", "air_strike":"A", "black_hole":"B", "blink_dash":"D", "gravity_bomb":"G", "chain_lightning":"L", "orbital_shield":"R", "plasma_beam":"P", "wingman":"W", "berserk":"Z"}
    if icon_id and icon_id in mapping: return mapping[icon_id]
    return upgrade_name[0].upper() if upgrade_name else "?"
