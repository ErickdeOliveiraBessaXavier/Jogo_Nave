from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Protocol, Dict, Any, Callable

try:
    # Prefer consistent config access via proxy
    from .config import config as Config
except Exception:  # pragma: no cover - defensive fallback for isolated tests
    Config = None  # type: ignore

try:
    from .upgrades_config import EMP_BASE_DURATION

    _emp_base_duration = EMP_BASE_DURATION
except Exception:
    _emp_base_duration = 10.0  # fallback


class UpgradeType(Enum):
    SHIELD_BURST = auto()
    HEAL = auto()
    EMP = auto()
    HOMING_SHOT = auto()
    LASER_SHOT = auto()
    EXPLOSIVE_SHOT = auto()
    AIR_STRIKE = auto()  # Ultimate: Bombardeio Aéreo
    BLACK_HOLE = auto()  # Ultimate: Buraco Negro


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
            old_cooldown = self.cooldown_left
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

            # Se tem cargas e acabou o cooldown, recupera uma carga
            if old_cooldown > 0.0 and self.cooldown_left == 0.0:
                if self.charges_left is not None and self.meta.base_charges is not None:
                    if self.charges_left < self.meta.base_charges:
                        self.charges_left += 1
                        # Se ainda não recuperou todas as cargas, inicia novo cooldown
                        if self.charges_left < self.meta.base_charges:
                            self.cooldown_left = self.get_effective_cooldown(ctx)

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


class HomingShotUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        ship = getattr(ctx, "ship", None)
        if ship is None:
            return

        duration = self.get_effective_duration(ctx)

        try:
            from .upgrades_config import HOMING_SPEED_PENALTY, HOMING_FIRE_RATE_PENALTY

            speed_penalty = float(HOMING_SPEED_PENALTY)
            fire_rate_penalty = float(HOMING_FIRE_RATE_PENALTY)
        except Exception:
            speed_penalty = 0.75  # 75% da velocidade normal
            fire_rate_penalty = 1.2  # 20% mais lento para atirar

        # Ativar modo de tiro teleguiado na nave
        if hasattr(ship, "activate_homing_shots"):
            try:
                ship.activate_homing_shots(duration, speed_penalty, fire_rate_penalty)
            except Exception:
                pass
        else:
            # Fallback: definir flags na nave
            try:
                setattr(ship, "homing_shots_active", True)
                setattr(ship, "homing_shots_timer", duration)
                setattr(ship, "homing_speed_penalty", speed_penalty)
                setattr(ship, "homing_fire_rate_penalty", fire_rate_penalty)
                # Armazenar velocidade original para restaurar depois
                if not hasattr(ship, "original_speed"):
                    setattr(ship, "original_speed", getattr(ship, "speed", 5))
                # Aplicar penalidade de velocidade
                ship.speed = getattr(ship, "original_speed", 5) * speed_penalty
            except Exception:
                pass

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        if not ctx:
            return
        ship = getattr(ctx, "ship", None)
        if ship is None:
            return

        # Desativar modo de tiro teleguiado
        try:
            if getattr(ship, "homing_shots_active", False):
                setattr(ship, "homing_shots_active", False)
                setattr(ship, "homing_shots_timer", 0.0)
                # Restaurar velocidade original
                if hasattr(ship, "original_speed"):
                    ship.speed = getattr(ship, "original_speed", 5)
        except Exception:
            pass


class LaserShotUpgrade(ActiveUpgrade):
    """Upgrade que cria bolas elétricas girando ao redor da nave disparando lasers automaticamente."""

    def allows_refresh(self) -> bool:
        return False  # Baseado em cargas, não permite refresh

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        """Ativa o sistema de bolas elétricas orbitais (3 bolas, 3 cargas cada)."""
        ship = getattr(ctx, "ship", None)

        if ship is None:
            return

        # Ativar sistema de lasers orbitais na nave (não usa mais duration)
        if hasattr(ship, "activate_orbital_lasers"):
            try:
                ship.activate_orbital_lasers(
                    0
                )  # Parâmetro ignorado, usa sistema de cargas
            except Exception:
                pass
        else:
            # Fallback: definir flags na nave
            try:
                setattr(ship, "orbital_lasers_active", True)
            except Exception:
                pass

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        # Não precisa fazer nada - o sistema se desativa automaticamente quando as cargas acabam
        pass


class ExplosiveShotUpgrade(ActiveUpgrade):
    """Upgrade que faz cada tiro criar uma explosão ao acertar inimigos.

    Comportamento especial:
    - 30 cargas iniciais (sempre disponível quando não em cooldown)
    - Cooldown só inicia quando todas as cargas são usadas
    - Após cooldown, volta a ter 30 cargas
    """

    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._waiting_for_charges_depleted = (
            False  # Aguardando cargas acabarem para iniciar cooldown
        )

    def allows_refresh(self) -> bool:
        return False  # Baseado em cargas, não permite refresh

    def can_activate(self, ctx: UpgradeContext) -> bool:
        # Não pode ativar se já está ativo (aguardando cargas acabarem)
        if self._waiting_for_charges_depleted:
            return False
        # Não pode ativar se está em cooldown
        if self.cooldown_left > 0.0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContext) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        # NÃO aplica cooldown aqui - será aplicado quando cargas acabarem
        self._waiting_for_charges_depleted = True
        self.active = True

        self.on_activate_effect(ctx, refreshed=False)
        self.on_after_activate(ctx)
        return True

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        """Ativa o sistema de tiros explosivos na nave."""
        ship = getattr(ctx, "ship", None)

        if ship is None:
            return

        # Ativar tiros explosivos com contagem de cargas (sempre 30)
        charges = self.meta.base_charges if self.meta.base_charges is not None else 30

        if hasattr(ship, "activate_explosive_shots"):
            try:
                ship.activate_explosive_shots(charges)
            except Exception:
                pass
        else:
            # Fallback: definir flags na nave
            try:
                setattr(ship, "explosive_shots_active", True)
                setattr(ship, "explosive_shots_remaining", charges)
            except Exception:
                pass

    def update(self, dt: float, ctx: Optional[UpgradeContext] = None) -> None:
        # Atualizar cooldown normalmente
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

        # Se está aguardando cargas acabarem, verificar se acabaram
        if self._waiting_for_charges_depleted and ctx is not None:
            ship = getattr(ctx, "ship", None)
            if ship is not None:
                remaining = getattr(ship, "explosive_shots_remaining", 0)
                is_active = getattr(ship, "explosive_shots_active", False)

                # Se cargas acabaram (ou sistema foi desativado), iniciar cooldown
                if remaining <= 0 or not is_active:
                    self._waiting_for_charges_depleted = False
                    self.active = False
                    self.cooldown_left = self.get_effective_cooldown(ctx)

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        # Chamado quando sistema expira manualmente (não usado aqui)
        self._waiting_for_charges_depleted = False
        self.active = False


class AirStrikeUpgrade(ActiveUpgrade):
    """Ultimate: Bombardeio Aéreo - Bombas caem em áreas aleatórias da tela.

    Comportamento:
    - 10 bombas por ativação
    - Cada bomba tem um marcador visual antes de cair
    - Bombas explodem ao atingir o alvo, destruindo inimigos
    - 180s de cooldown
    """

    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._bombs_remaining = 0
        self._spawn_timer = 0.0
        self._spawn_interval = 0.3  # Intervalo entre spawns de bombas
        self._is_spawning = False

    def allows_refresh(self) -> bool:
        return False  # Ultimate não permite refresh

    def can_activate(self, ctx: UpgradeContext) -> bool:
        if self._is_spawning:
            return False
        if self.cooldown_left > 0.0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContext) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        self.active = True
        self._is_spawning = True
        self._bombs_remaining = self.meta.base_charges if self.meta.base_charges else 10
        self._spawn_timer = 0.0  # Primeira bomba spawna imediatamente

        self.on_activate_effect(ctx, refreshed=False)
        self.on_after_activate(ctx)
        return True

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        """Inicia o bombardeio aéreo."""
        import pygame

        entity_manager = getattr(ctx, "entity_manager", None)
        if entity_manager is None:
            return

        # Obter dimensões da tela
        screen = pygame.display.get_surface()
        screen_width = screen.get_width() if screen else 1600
        screen_height = screen.get_height() if screen else 900

        # Spawnar primeira bomba imediatamente
        self._spawn_bomb(entity_manager, screen_width, screen_height)
        self._bombs_remaining -= 1

    def _spawn_bomb(
        self, entity_manager: Any, screen_width: int, screen_height: int
    ) -> None:
        """Spawna uma bomba em posição aleatória."""
        import random

        # Posição aleatória na área de jogo (evitar bordas)
        margin = 100
        target_x = random.uniform(margin, screen_width - margin)
        target_y = random.uniform(margin, screen_height - margin)

        if hasattr(entity_manager, "spawn_air_strike"):
            entity_manager.spawn_air_strike(target_x, target_y)

    def update(self, dt: float, ctx: Optional[UpgradeContext] = None) -> None:
        # Atualizar cooldown normalmente
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

        # Se está spawnando bombas
        if self._is_spawning and ctx is not None:
            self._spawn_timer += dt

            # Spawnar nova bomba se passou o intervalo
            if self._bombs_remaining > 0 and self._spawn_timer >= self._spawn_interval:
                import pygame

                entity_manager = getattr(ctx, "entity_manager", None)
                if entity_manager is not None:
                    screen = pygame.display.get_surface()
                    screen_width = screen.get_width() if screen else 1600
                    screen_height = screen.get_height() if screen else 900

                    self._spawn_bomb(entity_manager, screen_width, screen_height)
                    self._bombs_remaining -= 1
                    self._spawn_timer = 0.0

            # Terminou de spawnar todas as bombas
            if self._bombs_remaining <= 0:
                self._is_spawning = False
                self.active = False
                self.cooldown_left = self.get_effective_cooldown(ctx)

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        self._is_spawning = False
        self._bombs_remaining = 0
        self.active = False


class BlackHoleUpgrade(ActiveUpgrade):
    """Ultimate: Buraco Negro - Cria um buraco negro que suga e destrói todos os inimigos.

    Comportamento:
    - Cria um buraco negro no centro da tela
    - Puxa todos os inimigos gradualmente para o centro
    - Destrói inimigos que chegam próximos ao centro
    - Dura 8 segundos
    - 120s de cooldown (2 minutos)
    """

    def allows_refresh(self) -> bool:
        return False  # Ultimate não permite refresh

    def on_activate_effect(self, ctx: UpgradeContext, refreshed: bool) -> None:
        """Ativa o buraco negro."""
        entity_manager = getattr(ctx, "entity_manager", None)
        ship = getattr(ctx, "ship", None)
        
        if entity_manager is None or ship is None:
            return

        # Posição da nave (centro)
        ship_center_x = ship.x + ship.w / 2
        ship_center_y = ship.y + ship.h / 2

        duration = self.get_effective_duration(ctx)

        # Spawnar buraco negro na posição da nave
        if hasattr(entity_manager, "spawn_black_hole"):
            entity_manager.spawn_black_hole(ship_center_x, ship_center_y, duration)

    def on_expire(self, ctx: Optional[UpgradeContext]) -> None:
        self.active = False


# ===================== Registro e Fábrica ================================

UPGRADES_REGISTRY: Dict[UpgradeType, Callable[[], ActiveUpgrade]] = {}
UPGRADES_META: Dict[UpgradeType, UpgradeMeta] = {
    UpgradeType.SHIELD_BURST: UpgradeMeta(
        type=UpgradeType.SHIELD_BURST,
        name="SHLD",
        desc="Ativa um escudo temporário que absorve dano.",
        icon_id="shield_burst",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=45.0,
        base_duration=7.0,
        base_charges=None,
    ),
    UpgradeType.HEAL: UpgradeMeta(
        type=UpgradeType.HEAL,
        name="HEAL",
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
        base_duration=_emp_base_duration,
        base_charges=None,
    ),
    UpgradeType.HOMING_SHOT: UpgradeMeta(
        type=UpgradeType.HOMING_SHOT,
        name="HOM",
        desc="Tiros seguem inimigos automaticamente. Reduz velocidade da nave e cadência de tiro.",
        icon_id="homing_shot",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=80.0,
        base_duration=7.0,
        base_charges=None,
    ),
    UpgradeType.LASER_SHOT: UpgradeMeta(
        type=UpgradeType.LASER_SHOT,
        name="LAS",
        desc="3 bolas elétricas orbitais, cada uma dispara 3 lasers automáticos.",
        icon_id="laser_shot",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=60.0,
        base_duration=0.0,  # Não usa duração - baseado em cargas internas das bolinhas
        base_charges=None,  # Uso ilimitado do upgrade (cargas são internas: 3 bolas × 3 tiros)
    ),
    UpgradeType.EXPLOSIVE_SHOT: UpgradeMeta(
        type=UpgradeType.EXPLOSIVE_SHOT,
        name="EXPL",
        desc="Cada tiro cria uma pequena explosão que elimina inimigos próximos.",
        icon_id="explosive_shot",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=90.0,
        base_duration=0.0,  # Baseado em cargas, não em duração
        base_charges=30,
    ),
    UpgradeType.AIR_STRIKE: UpgradeMeta(
        type=UpgradeType.AIR_STRIKE,
        name="AIR",
        desc="Ultimate: 10 bombas caem em áreas aleatórias destruindo tudo.",
        icon_id="air_strike",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=180.0,  # 3 minutos de cooldown
        base_duration=0.0,
        base_charges=30,  # 30 bombas por ativação
    ),
    UpgradeType.BLACK_HOLE: UpgradeMeta(
        type=UpgradeType.BLACK_HOLE,
        name="HOLE",
        desc="Ultimate: Buraco negro suga e destrói todos os inimigos na tela.",
        icon_id="black_hole",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=120.0,  # 2 minutos de cooldown
        base_duration=8.0,  # Dura 8 segundos
        base_charges=None,
    ),
}


def _factory_shield() -> ActiveUpgrade:
    return ShieldBurstUpgrade(UPGRADES_META[UpgradeType.SHIELD_BURST])


def _factory_heal() -> ActiveUpgrade:
    return HealUpgrade(UPGRADES_META[UpgradeType.HEAL])


def _factory_emp() -> ActiveUpgrade:
    return EMPUpgrade(UPGRADES_META[UpgradeType.EMP])


def _factory_homing_shot() -> ActiveUpgrade:
    return HomingShotUpgrade(UPGRADES_META[UpgradeType.HOMING_SHOT])


def _factory_laser_shot() -> ActiveUpgrade:
    return LaserShotUpgrade(UPGRADES_META[UpgradeType.LASER_SHOT])


def _factory_explosive_shot() -> ActiveUpgrade:
    return ExplosiveShotUpgrade(UPGRADES_META[UpgradeType.EXPLOSIVE_SHOT])


def _factory_air_strike() -> ActiveUpgrade:
    return AirStrikeUpgrade(UPGRADES_META[UpgradeType.AIR_STRIKE])


def _factory_black_hole() -> ActiveUpgrade:
    return BlackHoleUpgrade(UPGRADES_META[UpgradeType.BLACK_HOLE])


UPGRADES_REGISTRY.update(
    {
        UpgradeType.SHIELD_BURST: _factory_shield,
        UpgradeType.HEAL: _factory_heal,
        UpgradeType.EMP: _factory_emp,
        UpgradeType.HOMING_SHOT: _factory_homing_shot,
        UpgradeType.LASER_SHOT: _factory_laser_shot,
        UpgradeType.EXPLOSIVE_SHOT: _factory_explosive_shot,
        UpgradeType.AIR_STRIKE: _factory_air_strike,
        UpgradeType.BLACK_HOLE: _factory_black_hole,
    }
)


def create_upgrade(upgrade_type: UpgradeType) -> ActiveUpgrade:
    factory = UPGRADES_REGISTRY.get(upgrade_type)
    if not factory:
        raise ValueError(f"UpgradeType não registrado: {upgrade_type}")
    return factory()


def list_all_upgrades_meta() -> list[UpgradeMeta]:
    return list(UPGRADES_META.values())


def get_upgrade_icon(upgrade_name: str, icon_id: str | None = None) -> str:
    """Retorna o caractere único do ícone, usando id ou nome como fallback."""

    # 1) Preferir icon_id do UpgradeMeta (estável e neutro a língua)
    if icon_id:
        icon_id_map = {
            "shield_burst": "S",
            "heal": "H",
            "emp": "E",
            "homing_shot": "O",
            "laser_shot": "L",
            "explosive_shot": "X",
            "air_strike": "A",
            "black_hole": "B",
        }
        icon = icon_id_map.get(icon_id)
        if icon:
            return icon

    # 2) Fallback por nome (EN)
    icon_name_map = {
        "Shield Burst": "S",
        "Shield": "S",
        "SHLD": "S",
        "Heal": "H",
        "HEAL": "H",
        "EMP": "E",
        "Homing Shot": "O",
        "Homing": "O",
        "HOM": "O",
        "Laser Shot": "L",
        "Laser": "L",
        "LAS": "L",
        "Explosive Shot": "X",
        "Explosive": "X",
        "EXPL": "X",
        "Air Strike": "A",
        "AIR": "A",
        "Black Hole": "B",
        "HOLE": "B",
    }

    icon = icon_name_map.get(upgrade_name)
    if icon:
        return icon

    # 3) Último recurso: primeira letra maiúscula
    return upgrade_name[:1].upper() if upgrade_name else "?"
