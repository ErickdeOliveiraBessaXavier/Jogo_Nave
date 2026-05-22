from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional, Protocol

try:
    # Prefer consistent config access via proxy
    from .config import config as Config
except ImportError:  # pragma: no cover - defensive fallback for isolated tests
    Config = None  # type: ignore

_emp_base_duration = 10.0


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
    BLINK_DASH = auto() # Teleporte curto/Dash evasivo
    GRAVITY_BOMB = auto() # Granada que cria mini-vórtice de atração
    CHAIN_LIGHTNING = auto() # Tiro que salta entre inimigos
    ORBITAL_SHIELD = auto() # Escudos orbitais físicos que bloqueiam tiros
    PLASMA_BEAM = auto() # Feixe contínuo frontal destruidor


class UpgradeCategory(Enum):
    DEFENSIVE = auto()
    UTILITY = auto()
    OFFENSIVE = auto()


class UpgradeContextProtocol(Protocol):
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
    - god_mode: flag booleana para ativar modo GOD (cooldowns reduzidos)
    """

    ship: Any
    entity_manager: Any
    difficulty_settings: Dict[str, Any]
    sound_manager: Any
    god_mode: bool
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
    slot_weight: int = (
        1  # Peso em slots (1-5): quanto mais forte o upgrade, mais pesado
    )


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
    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self.active and not self.allows_refresh():
            return False
        if self.cooldown_left > 0.0:
            return False
        if self.charges_left is not None and self.charges_left <= 0:
            return False

        # Regras de dificuldade: exemplo `no_powerups` -> +50% cooldown
        # A decisão fina será aplicada pelo chamador ou por get_effective_cooldown.
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContextProtocol) -> bool:
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
        self.active = True

        self.on_activate_effect(ctx)
        self.on_after_activate(ctx)
        return True

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
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

    @staticmethod
    def _ctx_ship(ctx: Optional[UpgradeContextProtocol]) -> Any:
        if ctx is None:
            return None
        return getattr(ctx, "ship", None)

    @staticmethod
    def _ctx_entity_manager(ctx: Optional[UpgradeContextProtocol]) -> Any:
        if ctx is None:
            return None
        return getattr(ctx, "entity_manager", None)

    @staticmethod
    def _ctx_scene(ctx: Optional[UpgradeContextProtocol]) -> Any:
        if ctx is None:
            return None
        return getattr(ctx, "scene", None)

    @staticmethod
    def _ctx_attr(
        ctx: Optional[UpgradeContextProtocol], name: str, default: Any = None
    ) -> Any:
        if ctx is None:
            return default
        return getattr(ctx, name, default)

    # ----- Hooks for subclasses -----------------------------------------
    def additional_can_activate(self, _ctx: UpgradeContextProtocol) -> bool:
        return True

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        raise NotImplementedError

    def on_after_activate(self, ctx: UpgradeContextProtocol) -> None:
        # SFX/VFX padrão podem ser disparados aqui se desejado
        try:
            sound_manager = self._ctx_attr(ctx, "sound_manager")
            if sound_manager is not None:
                sound_manager.play_upgrade_activate()
        except (AttributeError, TypeError):
            pass

    def on_denied(self, ctx: UpgradeContextProtocol) -> None:
        try:
            sound_manager = self._ctx_attr(ctx, "sound_manager")
            if sound_manager is not None:
                sound_manager.play_upgrade_denied()
        except (AttributeError, TypeError):
            pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        # Reverter efeitos temporários, se necessário
        pass

    # ----- Effective values with difficulty rules -----------------------
    def get_effective_cooldown(self, ctx: Optional[UpgradeContextProtocol]) -> float:
        cd = self.meta.base_cooldown
        try:
            # Modo GOD: cooldown de apenas 1 segundo
            if self._ctx_attr(ctx, "god_mode", False):
                return 1.0

            difficulty_settings = self._ctx_attr(ctx, "difficulty_settings")
            if difficulty_settings is not None:
                rules: Any = difficulty_settings.get("special_rules", [])
                if "no_powerups" in rules:
                    cd *= 1.5  # MVP: +50% cooldown
        except (AttributeError, TypeError, KeyError):
            pass
        return cd

    def get_effective_duration(self, _ctx: Optional[UpgradeContextProtocol]) -> float:
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
    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self._monitoring_shield = False  # Flag para monitorar quando escudo é consumido

    def allows_refresh(self) -> bool:
        # Não permite refresh - escudo não pode ser reativado enquanto ativo
        return False

    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        # Não pode ativar se já está monitorando um escudo ativo
        if self._monitoring_shield:
            return False
        if self.cooldown_left > 0.0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContextProtocol) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        # NÃO aplicar cooldown aqui - será aplicado quando escudo for consumido
        self._monitoring_shield = True
        self.active = True

        self.on_activate_effect(ctx)
        self.on_after_activate(ctx)
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        # Ativa escudo que absorve 1 hit de dano (sem limite de tempo)
        ship = self._ctx_ship(ctx)
        if ship is None:
            return

        # Duração infinita (valor muito alto)
        duration = 9999.0
        # Usar API de escudo da nave
        if hasattr(ship, "activate_shield"):
            try:
                ship.activate_shield(duration, shield_hp=1)
                return
            except (AttributeError, TypeError):
                pass

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        # Atualizar cooldown normalmente
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

        # Se está monitorando escudo, verificar se foi consumido
        if self._monitoring_shield and ctx is not None:
            ship = self._ctx_ship(ctx)
            if ship is not None:
                has_shield = getattr(ship, "has_shield", False)

                # Se escudo foi consumido/desapareceu, iniciar cooldown
                if not has_shield:
                    self._monitoring_shield = False
                    self.active = False
                    self.cooldown_left = self.get_effective_cooldown(ctx)

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        # Não usado - escudo expira quando consumido, não por timer
        self._monitoring_shield = False
        self.active = False


class HealUpgrade(ActiveUpgrade):
    def __init__(self, meta: UpgradeMeta) -> None:
        super().__init__(meta)
        self.usage_count: int = 0

    def additional_can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self.usage_count >= 2:
            return False
        ship = self._ctx_ship(ctx)
        if ship is None:
            return False
        max_lives = getattr(ship, "max_lives", getattr(Config, "INITIAL_LIVES", 5))
        current_lives = getattr(ship, "lives", None)
        if current_lives is None:
            return False
        return current_lives < max_lives

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        self.usage_count += 1
        ship = self._ctx_ship(ctx)
        if ship is None:
            return
        scene = self._ctx_scene(ctx)
        try:
            cap = getattr(ship, "max_lives", getattr(Config, "INITIAL_LIVES", 5))
            current_lives = getattr(ship, "lives", 0)
            if current_lives < cap:
                if scene is not None and hasattr(scene, "_change_lives"):
                    scene._change_lives(1)
                else:
                    ship.lives = current_lives + 1
        except (AttributeError, TypeError):
            pass


class EMPUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        em = self._ctx_entity_manager(ctx)
        if em is None:
            return
        duration = self.get_effective_duration(ctx)
        try:
            from .upgrades_config import EMP_SLOW_FACTOR

            slow_factor = float(EMP_SLOW_FACTOR)
        except (AttributeError, TypeError):
            slow_factor = 0.4  # fallback

        # Spawnar onda visual do EMP
        ship = self._ctx_ship(ctx)
        if ship and hasattr(em, "spawn_emp_wave"):
            try:
                center_x = ship.x + ship.w / 2
                center_y = ship.y + ship.h / 2
                em.spawn_emp_wave(center_x, center_y)
            except (AttributeError, TypeError):
                pass

        # Preferir API dedicada, se existir
        if hasattr(em, "apply_emp"):
            try:
                em.apply_emp(duration=duration, slow_factor=slow_factor)
                return
            except (AttributeError, TypeError):
                pass
        # Fallback simples: marcar efeito no manager; sistema de update deve respeitar se implementado
        try:
            setattr(em, "emp_active", True)
            setattr(em, "emp_slow_factor", slow_factor)
            setattr(em, "emp_timer", duration)
        except (AttributeError, TypeError):
            pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        em = self._ctx_entity_manager(ctx)
        if em is None:
            return
        # Reverter flags de EMP se forem nossos fallbacks
        try:
            if getattr(em, "emp_active", False):
                setattr(em, "emp_active", False)
                setattr(em, "emp_slow_factor", 1.0)
                setattr(em, "emp_timer", 0.0)
        except (AttributeError, TypeError):
            pass


class HomingShotUpgrade(ActiveUpgrade):
    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship is None:
            return

        duration = self.get_effective_duration(ctx)

        try:
            from .upgrades_config import HOMING_FIRE_RATE_PENALTY, HOMING_SPEED_PENALTY

            speed_penalty = float(HOMING_SPEED_PENALTY)
            fire_rate_penalty = float(HOMING_FIRE_RATE_PENALTY)
        except (AttributeError, TypeError):
            speed_penalty = 0.75  # 75% da velocidade normal
            fire_rate_penalty = 1.2  # 20% mais lento para atirar

        # Ativar modo de tiro teleguiado na nave
        if hasattr(ship, "activate_homing_shots"):
            try:
                ship.activate_homing_shots(duration, speed_penalty, fire_rate_penalty)
            except (AttributeError, TypeError):
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
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        ship = self._ctx_ship(ctx)
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
        except (AttributeError, TypeError):
            pass


class LaserShotUpgrade(ActiveUpgrade):
    """Upgrade que cria bolas elétricas girando ao redor da nave disparando lasers automaticamente."""

    def allows_refresh(self) -> bool:
        return False  # Baseado em cargas, não permite refresh

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        """Ativa o sistema de bolas elétricas orbitais (3 bolas, 3 cargas cada)."""
        ship = self._ctx_ship(ctx)

        if ship is None:
            return

        # Ativar sistema de lasers orbitais na nave (não usa mais duration)
        if hasattr(ship, "activate_orbital_lasers"):
            try:
                ship.activate_orbital_lasers(
                    0
                )  # Parâmetro ignorado, usa sistema de cargas
            except (AttributeError, TypeError):
                pass
        else:
            # Fallback: definir flags na nave
            try:
                setattr(ship, "orbital_lasers_active", True)
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
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

    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        # Não pode ativar se já está ativo (aguardando cargas acabarem)
        if self._waiting_for_charges_depleted:
            return False
        # Não pode ativar se está em cooldown
        if self.cooldown_left > 0.0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContextProtocol) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        # NÃO aplica cooldown aqui - será aplicado quando cargas acabarem
        self._waiting_for_charges_depleted = True
        self.active = True

        self.on_activate_effect(ctx)
        self.on_after_activate(ctx)
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        """Ativa o sistema de tiros explosivos na nave."""
        ship = self._ctx_ship(ctx)

        if ship is None:
            return

        # Ativar tiros explosivos com contagem de cargas (sempre 30)
        charges = self.meta.base_charges if self.meta.base_charges is not None else 30

        if hasattr(ship, "activate_explosive_shots"):
            try:
                ship.activate_explosive_shots(charges)
            except (AttributeError, TypeError):
                pass
        else:
            # Fallback: definir flags na nave
            try:
                setattr(ship, "explosive_shots_active", True)
                setattr(ship, "explosive_shots_remaining", charges)
            except (AttributeError, TypeError):
                pass

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        # Atualizar cooldown normalmente
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

        # Se está aguardando cargas acabarem, verificar se acabaram
        if self._waiting_for_charges_depleted and ctx is not None:
            ship = self._ctx_ship(ctx)
            if ship is not None:
                remaining = getattr(ship, "explosive_shots_remaining", 0)
                is_active = getattr(ship, "explosive_shots_active", False)

                # Se cargas acabaram (ou sistema foi desativado), iniciar cooldown
                if remaining <= 0 or not is_active:
                    self._waiting_for_charges_depleted = False
                    self.active = False
                    self.cooldown_left = self.get_effective_cooldown(ctx)

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
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

    def can_activate(self, ctx: UpgradeContextProtocol) -> bool:
        if self._is_spawning:
            return False
        if self.cooldown_left > 0.0:
            return False
        return self.additional_can_activate(ctx)

    def activate(self, ctx: UpgradeContextProtocol) -> bool:
        if not self.can_activate(ctx):
            self.on_denied(ctx)
            return False

        self.active = True
        self._is_spawning = True
        self._bombs_remaining = self.meta.base_charges if self.meta.base_charges else 10
        self._spawn_timer = 0.0  # Primeira bomba spawna imediatamente

        self.on_activate_effect(ctx)
        self.on_after_activate(ctx)
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        """Inicia o bombardeio aéreo."""
        import pygame

        entity_manager = self._ctx_entity_manager(ctx)
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

    def update(self, dt: float, ctx: Optional[UpgradeContextProtocol] = None) -> None:
        # Atualizar cooldown normalmente
        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

        # Se está spawnando bombas
        if self._is_spawning and ctx is not None:
            self._spawn_timer += dt

            # Spawnar nova bomba se passou o intervalo
            if self._bombs_remaining > 0 and self._spawn_timer >= self._spawn_interval:
                import pygame

                entity_manager = self._ctx_entity_manager(ctx)
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

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
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

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        """Ativa o buraco negro."""
        entity_manager = self._ctx_entity_manager(ctx)
        ship = self._ctx_ship(ctx)

        if entity_manager is None or ship is None:
            return

        # Posição da nave (centro)
        ship_center_x = ship.x + ship.w / 2
        ship_center_y = ship.y + ship.h / 2

        duration = self.get_effective_duration(ctx)

        # Spawnar buraco negro na posição da nave
        if hasattr(entity_manager, "spawn_black_hole"):
            entity_manager.spawn_black_hole(ship_center_x, ship_center_y, duration)

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        self.active = False


class CannonTowerUpgrade(ActiveUpgrade):
    """Ultimate: Torres de Canhão - Duas torres fixas que disparam minas em cargas sequenciais.

    Comportamento:
    - 2 torres fixas nas laterais da tela
    - Cada torre tem 3 cargas com 3 minas cada (9 minas por torre)
    - Minas armam em 3 segundos após pousar
    - Explodem por contato com inimigos, causando dano em área
    - Torres desaparecem após usar todas as cargas
    """

    def allows_refresh(self) -> bool:
        return False  # Ultimate não permite refresh

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        """Spawna duas torres de canhão fixas."""
        entity_manager = self._ctx_entity_manager(ctx)
        if entity_manager is None:
            return

        # Obter dimensões da tela
        import pygame

        screen = pygame.display.get_surface()
        screen_width = screen.get_width() if screen else 1600
        screen_height = screen.get_height() if screen else 900

        # Posições das torres (laterais, na parte inferior)
        left_tower_x = screen_width * 0.15  # 15% da largura
        right_tower_x = screen_width * 0.85  # 85% da largura
        tower_y = screen_height - 120  # 120 pixels do fundo

        # Spawnar torres
        if hasattr(entity_manager, "spawn_cannon_tower"):
            entity_manager.spawn_cannon_tower(left_tower_x, tower_y)
            entity_manager.spawn_cannon_tower(right_tower_x, tower_y)

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        self.active = False


class BlinkDashUpgrade(ActiveUpgrade):
    """Teleporte curto/Dash evasivo.
    Dá um boost de velocidade e invulnerabilidade por um tempo muito curto.
    """

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if ship is None:
            return
        duration = self.get_effective_duration(ctx)
        if hasattr(ship, "activate_dash"):
            try:
                ship.activate_dash(duration)
            except (AttributeError, TypeError):
                pass
        else:
            try:
                setattr(ship, "dash_active", True)
                setattr(ship, "dash_timer", duration)
                if not hasattr(ship, "original_speed"):
                    setattr(ship, "original_speed", getattr(ship, "speed", 5))
                ship.speed = getattr(ship, "original_speed", 5) * 2.5
                if hasattr(ship, "activate_invulnerability"):
                    ship.activate_invulnerability(duration)
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        ship = self._ctx_ship(ctx)
        if ship:
            try:
                setattr(ship, "dash_active", False)
                setattr(ship, "dash_timer", 0.0)
                if hasattr(ship, "original_speed"):
                    ship.speed = getattr(ship, "original_speed", 5)
            except (AttributeError, TypeError):
                pass


class GravityBombUpgrade(ActiveUpgrade):
    """Granada de Singularidade que cria um mini-vórtice de atração."""

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if not ship or not em:
            return
        duration = self.get_effective_duration(ctx)
        if hasattr(em, "spawn_gravity_bomb"):
            try:
                em.spawn_gravity_bomb(ship.x + ship.w / 2, ship.y, duration)
            except (AttributeError, TypeError):
                pass
        else:
            try:
                setattr(em, "gravity_bomb_active", True)
                setattr(em, "gravity_bomb_pos", (ship.x + ship.w / 2, ship.y - 100))
                setattr(em, "gravity_bomb_timer", duration)
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        em = self._ctx_entity_manager(ctx)
        if em:
            try:
                setattr(em, "gravity_bomb_active", False)
                setattr(em, "gravity_bomb_timer", 0.0)
            except (AttributeError, TypeError):
                pass


class ChainLightningUpgrade(ActiveUpgrade):
    """Tiros elétricos que saltam entre inimigos."""

    def allows_refresh(self) -> bool:
        return True

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if not ship:
            return
        duration = self.get_effective_duration(ctx)
        if hasattr(ship, "activate_chain_lightning"):
            try:
                ship.activate_chain_lightning(duration)
            except (AttributeError, TypeError):
                pass
        else:
            try:
                setattr(ship, "chain_lightning_active", True)
                setattr(ship, "chain_lightning_timer", duration)
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        ship = self._ctx_ship(ctx)
        if ship:
            try:
                setattr(ship, "chain_lightning_active", False)
                setattr(ship, "chain_lightning_timer", 0.0)
            except (AttributeError, TypeError):
                pass


class OrbitalShieldUpgrade(ActiveUpgrade):
    """Escudos orbitais físicos que orbitam a nave e causam dano/bloqueiam tiros."""

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        em = self._ctx_entity_manager(ctx)
        if not ship or not em:
            return
        duration = self.get_effective_duration(ctx)
        if hasattr(em, "spawn_orbital_shield"):
            try:
                em.spawn_orbital_shield(ship, duration)
            except (AttributeError, TypeError):
                pass
        else:
            try:
                setattr(ship, "orbital_shield_active", True)
                setattr(ship, "orbital_shield_timer", duration)
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        ship = self._ctx_ship(ctx)
        if ship:
            try:
                setattr(ship, "orbital_shield_active", False)
                setattr(ship, "orbital_shield_timer", 0.0)
            except (AttributeError, TypeError):
                pass


class PlasmaBeamUpgrade(ActiveUpgrade):
    """Dispara um feixe contínuo de plasma para frente."""

    def allows_refresh(self) -> bool:
        return False

    def on_activate_effect(self, ctx: UpgradeContextProtocol) -> None:
        ship = self._ctx_ship(ctx)
        if not ship:
            return
        duration = self.get_effective_duration(ctx)
        if hasattr(ship, "activate_plasma_beam"):
            try:
                ship.activate_plasma_beam(duration)
            except (AttributeError, TypeError):
                pass
        else:
            try:
                setattr(ship, "plasma_beam_active", True)
                setattr(ship, "plasma_beam_timer", duration)
            except (AttributeError, TypeError):
                pass

    def on_expire(self, ctx: Optional[UpgradeContextProtocol]) -> None:
        if not ctx:
            return
        ship = self._ctx_ship(ctx)
        if ship:
            try:
                setattr(ship, "plasma_beam_active", False)
                setattr(ship, "plasma_beam_timer", 0.0)
            except (AttributeError, TypeError):
                pass


# ===================== Registro e Fábrica ================================

UPGRADES_REGISTRY: Dict[UpgradeType, Callable[[], ActiveUpgrade]] = {}
UPGRADES_META: Dict[UpgradeType, UpgradeMeta] = {
    UpgradeType.SHIELD_BURST: UpgradeMeta(
        type=UpgradeType.SHIELD_BURST,
        name="SHLD",
        desc="Cria um escudo que absorve 1 hit de dano.",
        icon_id="shield_burst",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=45.0,
        base_duration=0.0,  # Não usa duração - baseado em consumo
        base_charges=None,
        slot_weight=2,  # Peso médio-baixo para upgrade defensivo
    ),
    UpgradeType.HEAL: UpgradeMeta(
        type=UpgradeType.HEAL,
        name="HEAL",
        desc="Restaura 1 vida, respeitando o limite máximo.",
        icon_id="heal",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=60.0,
        base_duration=0.0,
        base_charges=None,
        slot_weight=1,  # Upgrade leve com cargas limitadas
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
        slot_weight=2,  # Utilitário poderoso merece peso médio
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
        slot_weight=2,  # Ofensivo com penalidades próprias (lentidão + fire rate)
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
        slot_weight=3,  # Sistema de lasers automáticos é poderoso
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
        slot_weight=2,  # Explosões em área limitadas a 30 cargas
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
        slot_weight=3,  # Ultimate por cargas com cooldown longo
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
        slot_weight=3,  # Ultimate temporário (8s)
    ),
    UpgradeType.CANNON_TOWER: UpgradeMeta(
        type=UpgradeType.CANNON_TOWER,
        name="CANNON",
        desc="Ultimate: 2 torres fixas disparam minas que explodem por contato.",
        icon_id="cannon_tower",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=200.0,  # 3.3 minutos de cooldown
        base_duration=0.0,  # Baseado na duração das torres
        base_charges=None,
        slot_weight=3,  # Ultimate de controle de área
    ),
    UpgradeType.BLINK_DASH: UpgradeMeta(
        type=UpgradeType.BLINK_DASH,
        name="DASH",
        desc="Dash evasivo super rápido com frames de invulnerabilidade.",
        icon_id="blink_dash",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=15.0,
        base_duration=0.4,
        base_charges=None,
        slot_weight=1,
    ),
    UpgradeType.GRAVITY_BOMB: UpgradeMeta(
        type=UpgradeType.GRAVITY_BOMB,
        name="GRAV",
        desc="Granada que cria um vórtice puxando inimigos e meteoros.",
        icon_id="gravity_bomb",
        category=UpgradeCategory.UTILITY,
        base_cooldown=60.0,
        base_duration=2.5,
        base_charges=None,
        slot_weight=2,
    ),
    UpgradeType.CHAIN_LIGHTNING: UpgradeMeta(
        type=UpgradeType.CHAIN_LIGHTNING,
        name="LIGH",
        desc="Seus tiros disparam raios que saltam entre múltiplos inimigos.",
        icon_id="chain_lightning",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=60.0,
        base_duration=10.0,
        base_charges=None,
        slot_weight=2,
    ),
    UpgradeType.ORBITAL_SHIELD: UpgradeMeta(
        type=UpgradeType.ORBITAL_SHIELD,
        name="ORB",
        desc="Escudos de pedra orbitam a nave, bloqueando tiros e causando dano.",
        icon_id="orbital_shield",
        category=UpgradeCategory.DEFENSIVE,
        base_cooldown=70.0,
        base_duration=12.0,
        base_charges=None,
        slot_weight=2,
    ),
    UpgradeType.PLASMA_BEAM: UpgradeMeta(
        type=UpgradeType.PLASMA_BEAM,
        name="BEAM",
        desc="Dispara um poderoso raio de plasma contínuo em linha reta.",
        icon_id="plasma_beam",
        category=UpgradeCategory.OFFENSIVE,
        base_cooldown=110.0,
        base_duration=5.0,
        base_charges=None,
        slot_weight=3,
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


def _factory_cannon_tower() -> ActiveUpgrade:
    return CannonTowerUpgrade(UPGRADES_META[UpgradeType.CANNON_TOWER])


def _factory_blink_dash() -> ActiveUpgrade:
    return BlinkDashUpgrade(UPGRADES_META[UpgradeType.BLINK_DASH])


def _factory_gravity_bomb() -> ActiveUpgrade:
    return GravityBombUpgrade(UPGRADES_META[UpgradeType.GRAVITY_BOMB])


def _factory_chain_lightning() -> ActiveUpgrade:
    return ChainLightningUpgrade(UPGRADES_META[UpgradeType.CHAIN_LIGHTNING])


def _factory_orbital_shield() -> ActiveUpgrade:
    return OrbitalShieldUpgrade(UPGRADES_META[UpgradeType.ORBITAL_SHIELD])


def _factory_plasma_beam() -> ActiveUpgrade:
    return PlasmaBeamUpgrade(UPGRADES_META[UpgradeType.PLASMA_BEAM])


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
        UpgradeType.CANNON_TOWER: _factory_cannon_tower,
        UpgradeType.BLINK_DASH: _factory_blink_dash,
        UpgradeType.GRAVITY_BOMB: _factory_gravity_bomb,
        UpgradeType.CHAIN_LIGHTNING: _factory_chain_lightning,
        UpgradeType.ORBITAL_SHIELD: _factory_orbital_shield,
        UpgradeType.PLASMA_BEAM: _factory_plasma_beam,
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
            "blink_dash": "D",
            "gravity_bomb": "G",
            "chain_lightning": "L",
            "orbital_shield": "R",
            "plasma_beam": "P",
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
        "Cannon Tower": "C",
        "CANNON": "C",
        "DASH": "D",
        "GRAV": "G",
        "LIGH": "L",
        "ORB": "R",
        "BEAM": "P",
    }

    icon = icon_name_map.get(upgrade_name)
    if icon:
        return icon

    # 3) Último recurso: primeira letra maiúscula
    return upgrade_name[:1].upper() if upgrade_name else "?"
