from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Protocol, Dict, Any, Callable

try:
    # Prefer consistent config access via proxy
    from .config import config as Config
except Exception:  # pragma: no cover - defensive fallback for isolated tests
    Config = None  # type: ignore


class UpgradeType(Enum):
    SHIELD_BURST = auto()
    HEAL = auto()
    EMP = auto()


class UpgradeCategory(Enum):
    DEFENSIVE = auto()
    UTILITY = auto()
    OFFENSIVE = auto()


class UpgradeContext(Protocol):
    """Contexto necessário para upgrades operarem.

    Fornecido pela cena durante a gameplay. Não exigimos uma classe específica
    para manter baixo acoplamento: um objeto com atributos esperados é suficiente.

    Atributos esperados (quando existentes):
    - ship: nave do jogador (deve ter vidas, escudo/invuln, etc.)
    - entity_manager: gerenciador de entidades (meteoros/inimigos/projéteis)
    - difficulty_settings: dict com special_rules
    - sound_manager: para tocar SFX
    - renderer/r: para efeitos visuais rápidos (opcional)
    - scene: referência opcional à cena PlayingScene (vidas, etc.)
    - dt: delta time, quando aplicável
    """

    ship: Any
    entity_manager: Any
    difficulty_settings: Dict[str, Any]
    sound_manager: Any
    # Campos opcionais; usamos getattr com fallback


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


class ActiveUpgrade:
    """Classe base de upgrades ativos.

    Implementa estado de cooldown/duração/cargas e fluxo de ativação.
    Subclasses devem sobrescrever `on_activate_effect` e opcionalmente `on_expire`.
    """

    def __init__(self, meta: UpgradeMeta) -> None:
        self.meta = meta
        self.cooldown_left: float = 0.0
        self.duration_left: float = 0.0
        self.charges_left: Optional[int] = meta.base_charges
        self.active: bool = False

    # ----- Lifecycle -----------------------------------------------------
    def can_activate(self, ctx: UpgradeContext) -> bool:
        if self.active and not self.allows_refresh():
            return False
        if self.cooldown_left > 0.0:
            return False
        if self.charges_left is not None and self.charges_left <= 0:
            return False

        # Regras de dificuldade: exemplo `no_powerups` -> +50% cooldown
        # A decisão fina será aplicada pelo chamador ou por get_effective_cooldown.
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContext) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        # Consome carga (se existir)
        if self.charges_left is not None:
            self.charges_left -= 1

        # Aplica cooldown imediato
        self.cooldown_left = self.get_effective_cooldown(ctx)

        # Se já estava ativo e permite refresh, reinicia duração
        self.duration_left = self.get_effective_duration(ctx)
        already_active = self.active
        self.active = True

        self.on_activate_effect(ctx, refreshed=already_active)
        self.on_after_activate(ctx)
        return True

    def update(self, dt: float, ctx: Optional[UpgradeContext] = None) -> None:
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)
        if self.active:
            self.duration_left = max(0.0, self.duration_left - dt)
            if self.duration_left <= 0.0:
                self.active = False
                self.on_expire(ctx)

    # ----- Hooks for subclasses -----------------------------------------
    def additional_can_activate(self, ctx: UpgradeContext) -> bool:
        return True

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        raise NotImplementedError

    def on_after_activate(self, ctx: UpgradeContext) -> None:
        # SFX/VFX padrão podem ser disparados aqui se desejado
        try:
            if hasattr(ctx, "sound_manager"):
                ctx.sound_manager.play_upgrade_activate()
        except Exception:
            pass

    def on_denied(self, ctx: UpgradeContext) -> None:
        try:
            if hasattr(ctx, "sound_manager"):
                ctx.sound_manager.play_upgrade_denied()
        except Exception:
            pass

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        # Reverter efeitos temporários, se necessário
        pass

    # ----- Effective values with difficulty rules -----------------------
    def get_effective_cooldown(self, ctx: Optional[UpgradeContext]) -> float:
        cd = self.meta.base_cooldown
        try:
            if ctx and hasattr(ctx, "difficulty_settings"):
                rules: Any = ctx.difficulty_settings.get("special_rules", [])
                if "no_powerups" in rules:
                    cd *= 1.5  # MVP: +50% cooldown
        except Exception:
            pass
        return cd

    def get_effective_duration(self, ctx: Optional[UpgradeContext]) -> float:
        return self.meta.base_duration

    # ----- UI helpers ----------------------------------------------------
    def get_ui_state(self) -> Dict[str, Any]:
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


# ===================== Implementações MVP ================================


class ShieldBurstUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        # Permite renovar a duração se ativado novamente
        return True

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        # Ativa escudo que absorve 1 hit de dano
        ship = getattr(ctx, "ship", None)
        if ship is None:
            return

        duration = self.get_effective_duration(ctx)
        # Usar API de escudo da nave
        if hasattr(ship, "activate_shield"):
            try:
                ship.activate_shield(duration, shield_hp=1)
                return
            except Exception:
                pass


class HealUpgrade(ActiveUpgrade):
    def additional_can_activate(self, ctx: UpgradeContext) -> bool:
        ship = getattr(ctx, "ship", None)
        if ship is None:
            return False
        # Descobrir limite de vidas: usar cena ou Config como fallback
        scene = getattr(ctx, "scene", None)
        max_lives = None
        if scene and hasattr(scene, "lives"):
            # Heurística: assumir que o cap é no mínimo a maior vida observada ou INITIAL_LIVES
            max_lives = getattr(scene, "lives_cap", None) or getattr(
                Config, "INITIAL_LIVES", 5
            )
        else:
            max_lives = getattr(Config, "INITIAL_LIVES", 5)
        current_lives = getattr(ship, "lives", None)
        if current_lives is None:
            return False
        return current_lives < max_lives

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        ship = getattr(ctx, "ship", None)
        if ship is None:
            return
        scene = getattr(ctx, "scene", None)
        # Incrementa vida com cap
        cap = getattr(Config, "INITIAL_LIVES", 5)
        if scene and hasattr(scene, "lives"):
            cap = getattr(scene, "lives_cap", cap)
        try:
            if getattr(ship, "lives", 0) < cap:
                ship.lives = getattr(ship, "lives", 0) + 1
                # Se a cena espelha `lives`, sincronizar
                if scene and hasattr(scene, "lives"):
                    scene.lives = getattr(scene, "lives", 0) + 1
        except Exception:
            pass


class EMPUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        em = getattr(ctx, "entity_manager", None)
        if em is None:
            return
        duration = self.get_effective_duration(ctx)
        try:
            from .upgrades_config import EMP_SLOW_FACTOR

            slow_factor = float(EMP_SLOW_FACTOR)
        except Exception:
            slow_factor = 0.4  # fallback

        # Spawnar onda visual do EMP
        ship = getattr(ctx, "ship", None)
        if ship and hasattr(em, "spawn_emp_wave"):
            try:
                center_x = ship.x + ship.w / 2
                center_y = ship.y + ship.h / 2
                em.spawn_emp_wave(center_x, center_y)
            except Exception:
                pass

        # Preferir API dedicada, se existir
        if hasattr(em, "apply_emp"):
            try:
                em.apply_emp(duration=duration, slow_factor=slow_factor)
                return
            except Exception:
                pass
        # Fallback simples: marcar efeito no manager; sistema de update deve respeitar se implementado
        try:
            setattr(em, "emp_active", True)
            setattr(em, "emp_slow_factor", slow_factor)
            setattr(em, "emp_timer", duration)
        except Exception:
            pass

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        if not ctx:
            return
        em = getattr(ctx, "entity_manager", None)
        if em is None:
            return
        # Reverter flags de EMP se forem nossos fallbacks
        try:
            if getattr(em, "emp_active", False):
                setattr(em, "emp_active", False)
                setattr(em, "emp_slow_factor", 1.0)
                setattr(em, "emp_timer", 0.0)
        except Exception:
            pass


# ===================== Registro e Fábrica ================================

UPGRADES_REGISTRY: Dict[UpgradeType, Callable[[], ActiveUpgrade]] = {}
UPGRADES_META: Dict[UpgradeType, UpgradeMeta] = {
    UpgradeType.SHIELD_BURST: UpgradeMeta(
        type=UpgradeType.SHIELD_BURST,
        name="Shield Burst",
        desc="Ativa um escudo temporário que absorve dano.",
        icon_id="shield_burst",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=45.0,
        base_duration=7.0,
        base_charges=None,
    ),
    UpgradeType.HEAL: UpgradeMeta(
        type=UpgradeType.HEAL,
        name="Heal",
        desc="Restaura 1 vida, respeitando o limite máximo.",
        icon_id="heal",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=60.0,
        base_duration=0.0,
        base_charges=2,
    ),
    UpgradeType.EMP: UpgradeMeta(
        type=UpgradeType.EMP,
        name="EMP",
        desc="Onda que desacelera inimigos por curto período.",
        icon_id="emp",
        category=UpgradeCategory.UTILITY,
        base_cooldown=50.0,
        base_duration=3.0,  # mais lento por mais tempo
        base_charges=None,
    ),
}


def _factory_shield() -> ActiveUpgrade:
    return ShieldBurstUpgrade(UPGRADES_META[UpgradeType.SHIELD_BURST])


def _factory_heal() -> ActiveUpgrade:
    return HealUpgrade(UPGRADES_META[UpgradeType.HEAL])


def _factory_emp() -> ActiveUpgrade:
    return EMPUpgrade(UPGRADES_META[UpgradeType.EMP])


UPGRADES_REGISTRY.update(
    {
        UpgradeType.SHIELD_BURST: _factory_shield,
        UpgradeType.HEAL: _factory_heal,
        UpgradeType.EMP: _factory_emp,
    }
)


def create_upgrade(upgrade_type: UpgradeType) -> ActiveUpgrade:
    factory = UPGRADES_REGISTRY.get(upgrade_type)
    if not factory:
        raise ValueError(f"UpgradeType não registrado: {upgrade_type}")
    return factory()


def list_all_upgrades_meta() -> list[UpgradeMeta]:
    return list(UPGRADES_META.values())
