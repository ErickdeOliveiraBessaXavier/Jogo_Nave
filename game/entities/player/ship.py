from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

import pygame

from ...core.config import config as Config
from ...core.ship_types import ShipProfile, get_ship_profile
from ...core.upgrades_config import (
    CORROSIVE_SHOT_SIZE_MULTIPLIER,
    CRITICAL_CORE_CHANCE,
    CRYO_SHOT_ANGLES,
    CRYO_SHOT_SIZE_MULTIPLIER,
    GIANT_SHOT_SIZE_MULTIPLIER,
)
from ...core.sound import sound_manager
from ..effects.particle_types import ParticleDict, step_particle
from .ship_movement import ShipMovement
from .ship_powerups import ShipPowerups
from .ship_renderer import ShipRenderer

if TYPE_CHECKING:
    from ...systems.entity_manager import EntityManager


# Constantes para configuração
PARTICLE_ENTRY_COUNT = Config.PARTICLE_ENTRY_COUNT
PARTICLE_THRUSTER_COUNT = Config.PARTICLE_THRUSTER_COUNT
PARTICLE_ENTRY_VELOCITY = Config.PARTICLE_ENTRY_VELOCITY
PARTICLE_ENTRY_LIFETIME = Config.PARTICLE_ENTRY_LIFETIME
PARTICLE_ENTRY_SIZE = Config.PARTICLE_ENTRY_SIZE
PARTICLE_THRUSTER_VELOCITY_X = Config.PARTICLE_THRUSTER_VELOCITY_X
PARTICLE_THRUSTER_VELOCITY_Y = Config.PARTICLE_THRUSTER_VELOCITY_Y
PARTICLE_THRUSTER_LIFETIME = Config.PARTICLE_THRUSTER_LIFETIME
PARTICLE_THRUSTER_SIZE = Config.PARTICLE_THRUSTER_SIZE

# Leque do Spread Shot pré-resolvido em pares (cos, sin), na ordem de
# `Config.SPREAD_SHOT_ANGLES`. O leque é fixo, então converter graus e chamar
# cos/sin a cada disparo seria trabalho repetido no hot path (§7) — aqui roda
# uma vez, no import.
SPREAD_SHOT_ROTATIONS: tuple[tuple[float, float], ...] = tuple(
    (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    for deg in Config.SPREAD_SHOT_ANGLES
)

# Distância entre a BORDA do sprite (no eixo do voo) e o CENTRO da bala que
# nasce. É o único número que controla "quão à frente do casco o tiro aparece", e
# vale igual nas quatro direções — antes eram quatro valores diferentes, e o de
# cima nascia dentro da nave.
#
# 8px deixa a traseira do projétil ligeiramente fora do casco para o elenco todo
# (a bala mais comprida é a do Estilete, 15px no eixo). Sob Giant Shot o
# projétil é grande o bastante para engolir o nariz da nave de qualquer forma —
# aceito, é o que o upgrade comunica.
MUZZLE_STANDOFF: float = 8.0

# Meia-abertura das duas bocas do Double Shot, em fração do sprite no eixo
# perpendicular ao voo. Antes eram 0.3 no eixo vertical e 0.2 no horizontal: a
# mesma arma abria diferente só por causa da direção. 0.25 é o meio-termo, a ~3px
# de cada um dos dois valores antigos num sprite de 60px.
MUZZLE_DUAL_SPREAD: float = 0.25

# Trio do Cryo Shot, pré-resolvido pela mesma razão do leque acima. Mesma forma
# de dado (pares cos/sin), então os dois passam pelo mesmo `_rotate_fan`.
CRYO_SHOT_ROTATIONS: tuple[tuple[float, float], ...] = tuple(
    (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    for deg in CRYO_SHOT_ANGLES
)


class BulletSpec(NamedTuple):
    """Uma bala a nascer: de onde, para onde, e com quais modificadores.

    NamedTuple e não tupla crua porque a lista de modificadores CRESCE. Cada
    upgrade de disparo é um campo independente aqui, e nenhum deles conhece os
    outros — é isso que faz as combinações (leque + explosivo + teleguiado +
    gigante) valerem sem existir código por combinação. Upgrade novo = um campo
    com default + uma linha no `spawn_bullet`; os call sites que não o conhecem
    seguem funcionando.

    O que é por DISPARO e não por bala (tamanho do Giant Shot, dano, chain shot)
    não mora aqui: o `ShootingSystem` lê da nave uma vez e repassa a todas as
    balas da salva, o que já as cobre por igual.

    Continua sendo uma tupla, então o desempacotamento posicional dos charge
    shots (`for x, y, direction, *_ in specs`) segue válido.
    """

    x: float
    y: float
    direction: tuple[float, float]
    piercing: bool = False
    homing: bool = False
    explosive: bool = False
    low_ammo: bool = False
    # ÚNICO campo sorteado por bala em vez de copiado da nave: o Critical Core
    # rola uma vez por projétil, então duas balas da mesma salva divergem aqui.
    critical: bool = False
    # Visual: o tiro sai como cristal de gelo. Uniforme na salva (é estado da
    # nave), ao contrário do `critical`, que é sorteado por bala.
    cryo: bool = False
    # Visual: halo verde-ácido. Só o halo — quem empilha o ácido é o sistema de
    # colisão lendo `owner_ship.has_corrosive_ammo`, como o Cryo faz.
    corrosive: bool = False


class Ship:
    def __init__(
        self,
        x: float,
        y: float,
        mouse_control: bool = False,
        touch_offset: bool = False,
        auto_fire: bool = False,
        profile: Optional[ShipProfile] = None,
        player_index: int = 0,
    ):
        # ShipProfile aplica multiplicadores às stats base (velocidade, fire rate,
        # dano) e habilita mecânicas especiais (Cofre, Fantasma, Caçador, etc).
        self.profile: ShipProfile = profile or get_ship_profile("padrao")
        # 0 = P1 (sprite original), 1 = P2 (recolorido em ciano). Só afeta a
        # cor: as MiniShips leem daqui, e o ícone do HUD sai de `ship_image`.
        self.player_index = player_index

        # Dimensões da nave (baseadas na imagem)
        self.w = 60
        self.h = 60
        self.x = x
        self.y = y
        # Rect persistente — atualizado in-place no acesso para evitar alocação
        # por frame (rect é consultado por colisões, pickup, draw...).
        self._rect = pygame.Rect(int(x), int(y), self.w, self.h)
        # Multiplicadores do profile aplicados sobre os valores-base.
        self.speed = 250 * self.profile.speed_mult
        self.invuln = 0  # ms — quanto ainda resta
        # Duração TOTAL do período de i-frames em curso (ms). O contador
        # regressivo sozinho não diz "quão perto do fim estamos" em fração, e a
        # piscada acelerada precisa disso (uma invuln de 1s e uma de 3s não
        # podem acelerar no mesmo instante absoluto). Escrito por
        # `grant_invulnerability`.
        self.invuln_total = 0.0  # ms
        self.lives = max(1, Config.INITIAL_LIVES + self.profile.extra_lives)
        self.max_lives = self.lives
        self.visible = True
        self.move_vec = pygame.math.Vector2(0, 0)

        # Configurações de controle
        self.mouse_control = mouse_control
        self.auto_fire = auto_fire
        # Gesto de toque capturado por um botão do HUD: enquanto True, a
        # pilotagem IGNORA o ponteiro. Sem isto, tocar num slot de upgrade
        # puxaria a nave para cima do botão — no celular o mesmo dedo pilota e
        # toca. Escrito pelo `GameplayInputHandler`, zerado no soltar do dedo.
        self.pointer_captured = False
        # Nave voa acima do ponteiro (dedo). Só tem efeito com `mouse_control`,
        # que é o único caminho que lê a posição do ponteiro — ver
        # `ShipMovement` e `TOUCH_OFFSET_Y`. Escrito pela cena a partir das
        # preferências e reescrito ao vivo pela tela de Configurações.
        self.touch_offset = touch_offset

        # Elemental Debuffs (Timers)
        self.fire_rate_modifier_timer: float = 0.0  # Inferno: sobreaquecimento
        self.invert_controls_timer: float = 0.0  # Toxina: interferência
        self.speed_modifier_timer: float = 0.0  # Nevasca: congelamento
        self.wind_slow_factor: float = 1.0  # Vento: lentidão

        # Debuff elétrico (campo da Torreta Orbital). Enquanto `electric_debuff_timer`
        # corre, há chance periódica de uma descarga que trava o movimento por
        # `electric_stun_timer` segundos. São estados distintos com feedback visual
        # próprio: "carregado" (arcos crepitando) vs "paralisado" (movimento travado).
        self.electric_debuff_timer: float = 0.0   # "carregado" (6s típico)
        self.electric_stun_timer: float = 0.0      # movimento travado (descarga breve)
        # Imunidade pós-descarga: garante uma janela de mobilidade antes de poder
        # ser paralisado de novo (evita chain-stun / death-spiral nos campos).
        self.electric_stun_recovery_timer: float = 0.0
        self._electric_discharge_roll_t: float = 0.0  # acumulador da rolagem de descarga

        # Carregar imagem da nave
        try:
            from ...core.assets import BASE_DIR
            from ...core.player_tint import player_sprite

            icon_path = BASE_DIR / "assets" / "icons" / self.profile.sprite_filename
            self.ship_image = player_sprite(icon_path, self.player_index).convert_alpha()
            # Redimensionar para o tamanho apropriado (manter proporções)
            original_size = self.ship_image.get_size()
            scale_factor = min(self.w / original_size[0], self.h / original_size[1])
            new_size = (
                int(original_size[0] * scale_factor),
                int(original_size[1] * scale_factor),
            )
            self.ship_image = pygame.transform.scale(self.ship_image, new_size)
            self.ship_image_size: tuple[int, int] = self.ship_image.get_size()
        except pygame.error:
            # Imagem não carregada - nave não será visível
            self.ship_image = None
            self.ship_image_size = (self.w, self.h)

        # Power-ups
        self.double_shot_timer: float = 0.0
        self.spread_shot_timer: float = 0.0
        self.speed_boost_timer: float = 0.0
        self.piercing_shot_timer: float = 0.0
        self.mini_ships_timer: float = 0.0
        self.damage_boost_timer: float = 0.0
        # Giant Shot (upgrade): balas maiores enquanto o timer está ativo.
        self.big_shot_timer: float = 0.0
        # Chain Shot power-up
        self.chain_shot_timer: float = 0.0
        # Implosão (upgrade): cada acerto abre uma área de lentidão.
        self.implosion_shot_timer: float = 0.0
        # Critical Core (upgrade): cada bala pode sair crítica.
        self.critical_core_timer: float = 0.0
        # Cryo Shot (upgrade): acertos acumulam lentidão no alvo.
        self.cryo_shot_timer: float = 0.0
        # Shockwave (upgrade): morte de inimigo vira explosão pequena.
        self.shockwave_timer: float = 0.0
        # Corrosive Ammo (upgrade): acertos empilham ácido que corrói por tempo.
        self.corrosive_timer: float = 0.0
        # Repulsion Shield power-up (Vento Constante)
        self.repulsion_shield_timer: float = 0.0
        self.repulsion_wind_streaks: list[dict[str, Any]] = []

        self.is_entering = False
        self.entering_timer = 0.0
        self.entering_duration = 0.0
        self.entry_start_pos = (0.0, 0.0)
        self.entry_target_pos = (0.0, 0.0)
        self.entry_particles: list[ParticleDict] = []
        self.thruster_particles: list[ParticleDict] = []

        # NOVO: Rotação visual da nave (para side-scroll)
        self.rotation_angle: float = (
            0.0  # 0° = vertical (top-down), 90° = horizontal (side-scroll)
        )
        self.ship_image_rotated = self.ship_image  # Cache da imagem rotacionada
        self.is_side_scroll: bool = False  # Modo de jogo (top-down vs side-scroll)

        # NOVO: Direção cardinal da nave para tiros e orientação
        self.facing: str = "north"
        self._cardinal_directions: tuple[str, ...] = (
            "north",
            "east",
            "south",
            "west",
        )
        self.cardinal_vectors: dict[str, tuple[float, float]] = {
            "north": (0.0, -1.0),
            "east": (1.0, 0.0),
            "south": (0.0, 1.0),
            "west": (-1.0, 0.0),
        }
        self._cardinal_angles: dict[str, float] = {
            "north": 0.0,
            "east": 90.0,
            "south": 180.0,
            "west": 270.0,
        }
        self.set_facing(self.facing)
        self._refresh_sprite_size()

        # Shield system (from upgrades)
        self.shield_timer: float = 0.0
        self.shield_hp: int = 0  # Hits the shield can absorb

        # Homing shots system (from upgrades)
        self.homing_shots_active: bool = False
        self.homing_shots_timer: float = 0.0
        self.homing_speed_penalty: float = 1.0
        self.homing_fire_rate_penalty: float = 1.0
        # `original_speed` reflete a velocidade base após profile (sem penalidades).
        self.original_speed: float = self.speed

        # Descarga Orbital: orbes que disparam arcos (upgrade ORBITAL_DISCHARGE)
        self.orbital_discharge_active: bool = False
        self.orbital_angle: float = 0.0  # Ângulo de rotação das bolas
        self.orbital_current_ball: int = 0  # Índice da bola que vai disparar próxima
        self.orbital_global_cooldown: float = 0.0  # Cooldown global entre disparos
        self.orbital_discharge_charges: list[int] = [
            0,
            0,
            0,
        ]  # Cargas restantes por bolinha
        self.orbital_ball_fade: list[float] = [
            0.0,
            0.0,
            0.0,
        ]  # Timer de fade para cada bolinha (quando acaba)
        self.orbital_ball_entry: list[float] = [
            0.0,
            0.0,
            0.0,
        ]  # Timer de animação de entrada (0.0 = completo, >0 = animando)
        self.orbital_ball_shake: list[float] = [
            0.0,
            0.0,
            0.0,
        ]  # Timer de tremor após disparo (0.0 = sem tremor, >0 = tremendo)
        self.orbital_radius: float = 50.0  # Raio da órbita
        self.num_orbital_balls: int = 3  # Número de bolas orbitais
        self.orbital_charges_per_ball: int = 3  # Cargas por bolinha

        # Explosive shots system (from upgrades)
        self.explosive_shots_active: bool = False
        self.explosive_shots_remaining: int = 0

        # Cofre (powerup storage): slots para guardar powerups e ativar com Q/E.
        # Lista de strings (kind do PowerUp) ou None para slot vazio.
        self.stored_powerups: list[Optional[str]] = [None] * self.profile.powerup_slots

        # Fantasma: dash com i-frames.
        self.dash_timer: float = 0.0  # tempo restante de dash ativo
        self.dash_cooldown_left: float = 0.0  # cooldown até próximo dash
        self.dash_dir: pygame.math.Vector2 = pygame.math.Vector2(0, -1)
        self.dash_duration: float = 0.2
        self.dash_speed_mult: float = 3.5  # multiplicador da velocidade base no dash
        # Rastro de partículas do dash (decaem após o dash terminar).
        self.dash_trail_particles: list[ParticleDict] = []

        # Caçador: charge shot.
        self.charge_shot_active: bool = False
        self.charge_shot_timer: float = 0.0  # tempo acumulado de carga
        # Tempo restante do feedback de "habilidade ainda em uso". Escrito por
        # `deny_ability`, escoado no `update`, lido só pelo renderer (§3).
        self.ability_denied_timer: float = 0.0
        self.berserk_timer: float = 0.0  # tempo restante do modo Berserk

        # Cache do tamanho do sprite renderizado — invalidado em set_rotation.
        self.cached_sprite_size: tuple[int, int] = (self.w, self.h)

        # Reverberador: combo de dano sem tomar hit.
        self.combo_kills: int = 0  # abates consecutivos sem dano
        # Instante (em draw_time) do último incremento de combo — alimenta o
        # "pop" de escala do HUD. Escrito no update, lido no draw (§3).
        self.combo_pop_time: float = -999.0

        # Acumulador de tempo para animações no draw() — substitui time.time()
        # e garante compatibilidade com pausa/slow-motion.
        self.draw_time: float = 0.0

        # Componentes extraídos: Ship vira fachada e delega.
        self._renderer = ShipRenderer(self)
        self._powerups = ShipPowerups(self)
        self._movement = ShipMovement(self)

    def has_storage_slots(self) -> bool:
        return self._powerups.has_storage_slots()

    def try_store_powerup(self, kind: str) -> bool:
        return self._powerups.try_store_powerup(kind)

    def consume_stored_powerup(self, slot_index: int) -> Optional[str]:
        return self._powerups.consume_stored_powerup(slot_index)

    @property
    def is_dashing(self) -> bool:
        return bool(self.dash_timer > 0.0)

    @property
    def charge_shot_progress(self) -> float:
        """Progresso da carga normalizado em [0.0, 1.0]."""
        max_t: float = float(self.profile.charge_shot_max_time)
        if max_t <= 0:
            return 0.0
        return float(min(1.0, self.charge_shot_timer / max_t))

    def start_charge(self) -> bool:
        """Inicia acúmulo do charge shot. Retorna True se a nave suporta carga."""
        if not self.profile.has_charge_shot:
            return False
        if self.charge_shot_active:
            return True
        self.charge_shot_active = True
        self.charge_shot_timer = 0.0
        sound_manager.play_boss_laser_charging()
        return True

    def deny_ability(self) -> None:
        """Arma o feedback visual de habilidade recusada (efeito anterior ativo).

        Só o timer: o som sai do `AbilityDenied` no `SoundSystem` (§2) e o
        desenho é do `ShipRenderer`. Quem decide a recusa é o `ShootingSystem`,
        único que enxerga os projéteis ainda vivos.
        """
        self.ability_denied_timer = float(Config.ABILITY_DENIED_FEEDBACK_TIME)

    def cancel_charge(self) -> None:
        """Cancela o charge sem disparar, caso solte o botão antes de completar."""
        if self.charge_shot_active:
            self.charge_shot_active = False
            self.charge_shot_timer = 0.0
            sound_manager.stop_boss_laser_charging()

    def consume_charge(self) -> float:
        """Encerra o charge e retorna o multiplicador de dano deste disparo.

        Interpola linearmente entre 1.0 (sem carga) e `charge_shot_damage_mult`
        (carga máxima). Reseta o estado.
        """
        if not self.profile.has_charge_shot or not self.charge_shot_active:
            return 1.0
        progress = self.charge_shot_progress
        mult = 1.0 + (self.profile.charge_shot_damage_mult - 1.0) * progress
        self.charge_shot_active = False
        self.charge_shot_timer = 0.0
        sound_manager.stop_boss_laser_charging()
        return mult

    def register_kill(self) -> None:
        """Incrementa o contador de combo do Reverberador (clamped)."""
        if self.profile.combo_damage_per_kill <= 0:
            return
        self.combo_kills += 1
        self.combo_pop_time = self.draw_time

    def reset_combo(self) -> None:
        """Reseta o combo do Reverberador (chamado ao tomar dano)."""
        self.combo_kills = 0

    @property
    def combo_damage_bonus(self) -> float:
        """Bônus aditivo de dano do Reverberador (0.0 a `combo_damage_cap`)."""
        if self.profile.combo_damage_per_kill <= 0:
            return 0.0
        raw: float = float(self.combo_kills * self.profile.combo_damage_per_kill)
        cap: float = float(self.profile.combo_damage_cap)
        return float(min(raw, cap) if cap > 0 else raw)

    @property
    def combo_progress(self) -> float:
        """Progresso do combo até o cap, de 0.0 a 1.0.

        Sinal único de "quão quente" o Reverberador está: alimenta o bônus de
        cadência e a cor do tiro, para os dois lerem a mesma escala do HUD.
        """
        bonus = self.combo_damage_bonus
        if bonus <= 0:
            return 0.0
        cap: float = float(self.profile.combo_damage_cap)
        return min(1.0, bonus / cap) if cap > 0 else min(1.0, bonus)

    def try_dash(self, current_move_vec: pygame.math.Vector2) -> bool:
        return self._movement.try_dash(current_move_vec)

    @property
    def attack_speed_multiplier(self) -> float:
        """Retorna o multiplicador de velocidade de ataque baseado nos power-ups ativos.

        Multiplicativo com o `fire_rate_mult` do `ShipProfile` — powerups herdam
        os stats da nave (Estilete +60% combinado com double_shot, etc).
        """
        multiplier = self.profile.fire_rate_mult

        if self.speed_boost_timer > 0.0:
            multiplier *= (
                Config.SPEED_ATTACK_MULTIPLIER
            )  # Usar configuração personalizada
        if self.piercing_shot_timer > 0.0:
            multiplier *= Config.PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER
        if self.spread_shot_timer > 0.0:
            # Custo de cadência do leque — a razão do número está na config.
            multiplier *= Config.SPREAD_SHOT_FIRE_RATE_PENALTY
        if self.homing_shots_active:
            multiplier *= self.homing_fire_rate_penalty  # Penalidade de cadência
        if self.explosive_shots_active:
            multiplier *= (
                Config.EXPLOSIVE_SHOT_FIRE_RATE_PENALTY
            )  # Tiros explosivos são mais lentos

        # Reverberador: o combo também embala a cadência, proporcional ao
        # progresso até o cap (mesmo sinal da cor do tiro).
        combo_fire = self.profile.combo_fire_rate_bonus
        if combo_fire > 0:
            multiplier *= 1.0 + combo_fire * self.combo_progress

        # Inferno debuff: Sobreaquecimento reduz cadência em 50%
        if self.fire_rate_modifier_timer > 0.0:
            multiplier *= 0.5

        return multiplier

    @property
    def pickup_rect(self) -> pygame.Rect:
        """Retângulo de coleta de powerups/estrelas, inflado pelo profile.

        Magneto tem `pickup_radius_mult` > 1, resultando em uma hitbox de
        coleta maior que a hitbox de colisão (`rect`).
        """
        mult = self.profile.pickup_radius_mult
        if mult <= 1.0:
            return self.rect
        extra = int(self.w * (mult - 1.0))
        return self.rect.inflate(extra, extra)

    @property
    def damage_multiplier(self) -> float:
        """Multiplicador de dano efetivo: profile × powerup × combo do Reverberador.

        Powerups herdam o stat da nave — Aríete + damage_boost compõem por
        multiplicação (1.80 × Config.DAMAGE_BOOST_MULTIPLIER). O combo do
        Reverberador é aplicado como bônus aditivo no fator final.
        """
        multiplier = self.profile.damage_mult
        if self.damage_boost_timer > 0.0:
            multiplier *= Config.DAMAGE_BOOST_MULTIPLIER
        # Reverberador: bônus aditivo escalando o multiplicador (combo_kills × per_kill).
        bonus = self.combo_damage_bonus
        if bonus > 0:
            multiplier *= 1.0 + bonus
        return multiplier

    @property
    def bullet_size_multiplier(self) -> float:
        """Fator de escala das balas (visual + hitbox): Giant × Cryo × Corrosive.

        1.0 = tamanho normal. Lido pelo `ShootingSystem` no spawn de cada bala.

        Todos se COMPÕEM por multiplicação, como todo modificador de disparo
        nesta base: o cristal de gelo sob Giant Shot é um bloco (3,0 × 1,6). É a
        mesma escolha que faz leque + perfurante + explosivo valerem juntos sem
        um caso especial por combinação.
        """
        mult = 1.0
        if self.big_shot_timer > 0.0:
            mult *= GIANT_SHOT_SIZE_MULTIPLIER
        if self.has_cryo_shot:
            mult *= CRYO_SHOT_SIZE_MULTIPLIER
        if self.has_corrosive_ammo:
            mult *= CORROSIVE_SHOT_SIZE_MULTIPLIER
        return mult

    @property
    def rect(self) -> pygame.Rect:
        self._rect.update(int(self.x), int(self.y), self.w, self.h)
        return self._rect

    @property
    def is_invulnerable(self) -> bool:
        return self.invuln > 0

    def grant_invulnerability(self, duration_ms: float) -> None:
        """Concede i-frames por `duration_ms`, guardando também a duração total.

        Caminho ÚNICO para ligar invulnerabilidade — atribuir `self.invuln`
        direto deixa `invuln_total` para trás e a piscada perde a referência de
        quanto o período todo dura (acelera na hora errada, ou nunca).

        Um período em curso MAIOR que o pedido é mantido: era a semântica que o
        dash já tinha (`max(invuln, dash)`) e vale para todos — um toque de
        escudo não deve encurtar os i-frames longos de uma vida perdida.
        """
        if duration_ms <= self.invuln:
            return
        self.invuln = duration_ms
        self.invuln_total = duration_ms

    def get_invulnerable_time(self) -> float:
        return self.invuln / 1000.0

    def get_double_shot_time(self) -> float:
        return self.double_shot_timer

    def get_spread_shot_time(self) -> float:
        return self.spread_shot_timer

    def get_speed_boost_time(self) -> float:
        return self.speed_boost_timer

    def get_piercing_shot_time(self) -> float:
        return self.piercing_shot_timer

    def get_mini_ships_time(self) -> float:
        return self.mini_ships_timer

    def get_damage_boost_time(self) -> float:
        return self.damage_boost_timer

    def get_chain_shot_time(self) -> float:
        return self.chain_shot_timer

    def get_repulsion_shield_time(self) -> float:
        return self.repulsion_shield_timer

    @property
    def has_shield(self) -> bool:
        return self.shield_timer > 0.0 and self.shield_hp > 0

    def activate_shield(self, duration: float, shield_hp: int = 1) -> None:
        self._powerups.activate_shield(duration, shield_hp)

    def activate_homing_shots(
        self,
        duration: float,
        speed_penalty: float = 0.75,
        fire_rate_penalty: float = 0.8,
    ) -> None:
        self._powerups.activate_homing_shots(duration, speed_penalty, fire_rate_penalty)

    def activate_orbital_discharge(self, _duration: float) -> None:
        self._powerups.activate_orbital_discharge()

    def activate_explosive_shots(self, charges: int) -> None:
        self._powerups.activate_explosive_shots(charges)

    def activate_giant_shots(self, duration: float) -> None:
        self._powerups.activate_giant_shots(duration)

    def activate_dash(self, duration: float) -> None:
        self._powerups.activate_dash(duration)

    def activate_berserk(self, duration: float) -> None:
        self.berserk_timer = duration

    def activate_chain_shot(self, duration: float | None = None) -> None:
        self._powerups.activate_chain_shot(duration)

    def activate_repulsion_shield(self, duration: float | None = None) -> None:
        self._powerups.activate_repulsion_shield(duration)

    def activate_implosion_shots(self, duration: float) -> None:
        self._powerups.activate_implosion_shots(duration)

    def activate_critical_core(self, duration: float) -> None:
        self._powerups.activate_critical_core(duration)

    def activate_cryo_shots(self, duration: float) -> None:
        self._powerups.activate_cryo_shots(duration)

    def activate_shockwave(self, duration: float) -> None:
        self._powerups.activate_shockwave(duration)

    def activate_corrosive_ammo(self, duration: float) -> None:
        self._powerups.activate_corrosive_ammo(duration)

    @property
    def has_chain_shot(self) -> bool:
        return self.chain_shot_timer > 0.0

    @property
    def has_implosion_shot(self) -> bool:
        """True enquanto os acertos desta nave abrem áreas de lentidão.

        Lido por bala no sistema de colisão via `owner_ship`, como o
        `has_chain_shot`: em coop cada nave responde pelo próprio upgrade.
        """
        return self.implosion_shot_timer > 0.0

    @property
    def has_critical_core(self) -> bool:
        """True enquanto as balas desta nave podem sair críticas.

        Como o `has_implosion_shot`, é por NAVE: em coop cada jogador responde
        pelo próprio upgrade, mesmo compartilhando o `ShootingSystem`.
        """
        return self.critical_core_timer > 0.0

    @property
    def has_cryo_shot(self) -> bool:
        """True enquanto os acertos desta nave acumulam lentidão no alvo.

        Por NAVE, como os irmãos: em coop cada jogador responde pelo próprio
        upgrade, e a escada que o P1 subiu num inimigo é a mesma que o P2
        alimenta — o nível mora no INIMIGO, não na nave.
        """
        return self.cryo_shot_timer > 0.0

    @property
    def has_shockwave(self) -> bool:
        """True enquanto as mortes de inimigo viram explosão.

        Diferente dos irmãos, este NÃO é lido por bala: quem consulta é o
        `ShockwaveSystem`, que reage à morte sem saber quem matou. Em coop basta
        UM jogador com o upgrade ativo para as mortes explodirem — a morte é do
        mundo, não de quem deu o tiro.
        """
        return self.shockwave_timer > 0.0

    @property
    def has_corrosive_ammo(self) -> bool:
        """True enquanto os acertos desta nave empilham ácido no alvo.

        Por NAVE, como o `has_cryo_shot`, e pelo mesmo motivo: a pilha mora no
        INIMIGO, então em coop os dois jogadores alimentam a mesma corrosão —
        mas cada um só a alimenta enquanto o SEU upgrade estiver ativo.
        """
        return self.corrosive_timer > 0.0

    @property
    def has_repulsion_shield(self) -> bool:
        return self.repulsion_shield_timer > 0.0

    def consume_explosive_shot(self) -> bool:
        return self._powerups.consume_explosive_shot()

    @property
    def is_homing_shots_active(self) -> bool:
        """True se o modo de tiros teleguiados está ativo."""
        return self.homing_shots_active

    @property
    def is_double_shot_active(self) -> bool:
        """True se o double shot está ativo. Use `double_shot_timer` para o tempo restante."""
        return self.double_shot_timer > 0.0

    @property
    def is_spread_shot_active(self) -> bool:
        """True se o leque está ativo. Use `spread_shot_timer` para o tempo restante."""
        return self.spread_shot_timer > 0.0

    @property
    def is_speed_boost_active(self) -> bool:
        """True se o boost de velocidade está ativo. Use `speed_boost_timer` para o tempo restante."""
        return self.speed_boost_timer > 0.0

    def set_rotation(self, angle: float) -> None:
        """Define o ângulo de rotação visual da nave.

        Args:
            angle: Ângulo em graus (0° = vertical/top-down, 90° = horizontal/side-scroll)
        """
        if abs(self.rotation_angle - angle) > 0.01 and self.ship_image is not None:
            self.rotation_angle = angle
            # Rotacionar imagem: pygame.transform.rotate() usa rotação no sentido contrário
            # Então rotacionamos -angle para obter a rotação desejada
            self.ship_image_rotated = pygame.transform.rotate(self.ship_image, -angle)
            self._refresh_sprite_size()

    def set_facing(self, facing: str) -> None:
        """Define a direção cardinal da nave e atualiza sua rotação visual."""
        if facing not in self._cardinal_directions:
            return
        self.facing = facing
        self.set_rotation(self._cardinal_angles[facing])

    def cycle_facing(self) -> None:
        """Avança para a próxima direção cardinal."""
        current_index = self._cardinal_directions.index(self.facing)
        next_index = (current_index + 1) % len(self._cardinal_directions)
        self.set_facing(self._cardinal_directions[next_index])

    def apply_world_mode(self, is_side_scroll: bool) -> None:
        """Sincroniza o modo do mundo e orientação inicial da nave."""
        self.is_side_scroll = is_side_scroll
        default_facing = "east" if is_side_scroll else "north"
        self.set_facing(default_facing)

    def get_facing_vector(self) -> tuple[float, float]:
        return self.cardinal_vectors.get(self.facing, (0.0, -1.0))

    def get_rendered_sprite_size(self) -> tuple[int, int]:
        """Retorna o tamanho do sprite atualmente desenhado na tela.
        Valor cacheado; invalidado em set_rotation/_refresh_sprite_size."""
        return self.cached_sprite_size

    def _refresh_sprite_size(self) -> None:
        if self.ship_image is None:
            self.cached_sprite_size = (self.w, self.h)
        elif self.rotation_angle != 0.0 and self.ship_image_rotated is not None:
            self.cached_sprite_size = self.ship_image_rotated.get_size()
        else:
            self.cached_sprite_size = self.ship_image.get_size()

    def _update_particles(self, dt: float, is_side_scroll: bool = False) -> None:
        """Atualiza o sistema de partículas."""
        # Obter tamanho real do sprite (ou fallback para dimensões lógicas)
        if self.ship_image is not None:
            sprite_w, sprite_h = self.ship_image.get_size()
        else:
            sprite_w, sprite_h = self.w, self.h

        thruster_count = max(
            0,
            int(round(PARTICLE_THRUSTER_COUNT * self.profile.thruster_intensity_mult)),
        )

        # Partículas de entrada / atrito (desabilitar em side-scroll). No re-entry
        # (facing "south": a nave entra pelo TOPO), o atrito sai pela BASE da nave
        # e sobe — invertido em relação à entrada padrão (sai do topo e desce).
        if self.is_entering and not is_side_scroll:
            inverted_entry = self.facing == "south"
            entry_emit_y = (self.y + sprite_h) if inverted_entry else self.y
            entry_vy = -80.0 if inverted_entry else 80.0
            for _ in range(PARTICLE_ENTRY_COUNT):
                min_size, max_size = PARTICLE_ENTRY_SIZE
                particle = ParticleDict(
                    x=self.x + sprite_w / 2,
                    y=entry_emit_y,
                    vx=random.uniform(*PARTICLE_ENTRY_VELOCITY),
                    vy=entry_vy,
                    lifetime=random.uniform(*PARTICLE_ENTRY_LIFETIME),
                    size=random.uniform(min_size, max_size),
                    color=(255, random.randint(100, 220), 0),
                )
                self.entry_particles.append(particle)

        # Atualizar partículas de entrada (sem encolher; só decai por lifetime)
        self.entry_particles = [
            step_particle(p, dt)
            for p in self.entry_particles
            if p["lifetime"] - dt > 0
        ]

        # Gerar partículas de thruster (sempre atrás da direção atual da nave)
        for _ in range(thruster_count):
            if self.facing == "north":
                particle = ParticleDict(
                    x=self.x + sprite_w / 2 + random.uniform(-5, 5),
                    y=self.y + sprite_h + random.uniform(-2, 3),
                    vx=random.uniform(-40, 40),
                    vy=random.uniform(100, 220),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            elif self.facing == "south":
                particle = ParticleDict(
                    x=self.x + sprite_w / 2 + random.uniform(-5, 5),
                    y=self.y + random.uniform(-3, 2),
                    vx=random.uniform(-40, 40),
                    vy=-random.uniform(100, 220),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            elif self.facing == "east":
                particle = ParticleDict(
                    x=self.x + random.uniform(-3, 2),
                    y=self.y + sprite_h / 2 + random.uniform(-5, 5),
                    vx=-random.uniform(100, 220),
                    vy=random.uniform(-40, 40),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )
            else:  # west
                particle = ParticleDict(
                    x=self.x + sprite_w + random.uniform(-2, 3),
                    y=self.y + sprite_h / 2 + random.uniform(-5, 5),
                    vx=random.uniform(100, 220),
                    vy=random.uniform(-40, 40),
                    lifetime=random.uniform(*PARTICLE_THRUSTER_LIFETIME),
                    size=random.uniform(*PARTICLE_THRUSTER_SIZE),
                    color=(255, random.randint(100, 200), 0),
                )

            self.thruster_particles.append(particle)

        # Atualizar partículas de thruster (encolhem em dt*1)
        self.thruster_particles = [
            step_particle(p, dt, size_shrink_rate=1.0)
            for p in self.thruster_particles
            if p["lifetime"] - dt > 0 and p["size"] - dt > 0
        ]

    def start_entering_animation(
        self,
        start_pos: tuple[float, float],
        target_pos: tuple[float, float],
        duration: float,
    ) -> None:
        """Inicia a animação de entrada da nave."""
        self.is_entering = True
        self.entering_timer = 0.0
        self.entering_duration = duration
        self.entry_start_pos = start_pos
        self.entry_target_pos = target_pos
        self.x, self.y = start_pos

    def update(
        self,
        dt: float,
        entity_manager: Optional["EntityManager"] = None,
        is_side_scroll: bool = False,
    ):
        self.draw_time += dt

        if self.is_entering and self.entering_duration > 0:
            self.entering_timer += dt
            progress = min(1.0, self.entering_timer / self.entering_duration)
            eased = 1.0 - (1.0 - progress) ** 3  # ease-out cúbico
            self.x = (
                self.entry_start_pos[0]
                + (self.entry_target_pos[0] - self.entry_start_pos[0]) * eased
            )
            self.y = (
                self.entry_start_pos[1]
                + (self.entry_target_pos[1] - self.entry_start_pos[1]) * eased
            )
            if progress >= 1.0:
                self.is_entering = False
                self.entering_duration = 0.0  # Reset para evitar re-triggering indesejado

        self._powerups.update_timers(dt)
        self.berserk_timer = max(0.0, self.berserk_timer - dt)
        self._powerups.update_repulsion_shield(dt, entity_manager)
        self._movement.update_dash(dt)

        self.ability_denied_timer = max(0.0, self.ability_denied_timer - dt)

        # Avança charge do Caçador (cap em charge_shot_max_time).
        if self.charge_shot_active:
            self.charge_shot_timer = min(
                self.profile.charge_shot_max_time,
                self.charge_shot_timer + dt,
            )
        self._powerups.update_orbital_discharge(dt, entity_manager)
        self._update_particles(dt, is_side_scroll)

    def move(
        self,
        held_actions: set[str],
        dt: float,
        is_side_scroll: bool = False,
        gamepad_vec: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self._movement.move(held_actions, dt, is_side_scroll, gamepad_vec)

    @property
    def emit_velocity(self) -> tuple[float, float]:
        """Velocidade da nave no último frame, em px/s.

        Contrato público para a compensação sub-frame de disparo (§1): o
        `ShootingSystem` precisa saber onde a boca ESTAVA quando o tiro era
        devido, e não pode ler o privado do `ShipMovement` para descobrir.
        Fachada fina sobre o componente, no padrão da §9.
        """
        return self._movement.velocity

    def should_auto_fire(self) -> bool:
        """True quando o auto-fire está ligado. Só isso — a cadência é do timer.

        Auto-fire significa "considere o gatilho apertado"; QUANDO o tiro sai é
        decisão do `FireTimer`, que já compõe perfil da nave, power-ups e
        debuffs. Antes havia aqui um segundo relógio próprio — acumulava `dt`,
        abria uma janela de UM frame a cada 0,1s e fazia `timer = 0` no
        disparo, o padrão que a §14 proíbe.

        Dois gates periódicos independentes não se somam: eles BATEM. O tiro só
        saía quando as duas janelas coincidiam no mesmo frame, e a cadência
        resultante era o batimento entre elas, não a configurada. Medido a
        60fps (a soma flutuante de 1/60 nunca fecha em 0,1, então a janela
        abria a cada 7 frames e não 6):

            Estilete  8,00/s configurado -> 5,71/s real, alternando 7 e 14
                      frames entre tiros (pares colados, vão dobrado)
            Padrão    5,00/s -> 4,29/s      Aríete/Caçador 3,75/s -> 2,86/s

        O Estilete era o único a ficar IRREGULAR: a razão entre 8/s e a janela
        de ~8,57/s é a única do elenco que cai numa alternância 2:1. Nas outras
        o batimento só cobrava cadência, sem quebrar o ritmo — por isso passou
        tanto tempo despercebido, e por isso o sintoma parecia ser "da nave".

        Vale para todo mundo com auto-fire ligado, que é o padrão no celular.
        """
        return self.auto_fire

    def _muzzle_positions(
        self, sprite_w: float, sprite_h: float, dual: bool
    ) -> list[tuple[float, float]]:
        """Bocas de saída da bala para o `facing` atual, como CENTRO do projétil.

        `dual` pede as duas bocas laterais do Double Shot; sem ele, a boca
        central. Só geometria: quantas balas saem de cada boca e em que direção
        é decisão de `bullet_spawn`.

        **Uma regra, rotacionada pelo `facing`** — e não quatro casos escritos à
        mão. Tudo sai do centro do sprite mais dois deslocamentos ortogonais:
        `MUZZLE_STANDOFF` ao longo do eixo do voo e, no Double Shot,
        `MUZZLE_DUAL_SPREAD` na perpendicular. Girar a nave gira o mesmo
        offset; não há direção com fórmula própria para divergir das outras.

        **Por que a regra existe** (medido): as quatro fórmulas manuais que isto
        substitui divergiam entre si. Atirando para cima a bala nascia 11px
        DENTRO do casco (o ponto era o topo do sprite, usado como topo da bala);
        para baixo, 0px; para leste, +5px; para oeste, +4px. E havia um `-3.5`
        cravado só no eixo vertical — a meia-largura de uma bala de 7px —
        tentando compensar o que hoje é responsabilidade do
        `Bullet._anchor_on_center`, que é o único lugar que conhece o tamanho
        real do projétil.

        O ponto devolvido é o **centro** da bala, não o canto: a conversão é da
        bala, porque só ela sabe o próprio `w`/`h` (que troca com a orientação).
        """
        cx = self.x + sprite_w / 2.0
        cy = self.y + sprite_h / 2.0
        ux, uy = self.get_facing_vector()

        # Meio-sprite ao longo do eixo do voo: com `facing` cardinal, um dos dois
        # termos é sempre zero. Escrito como projeção (e não como `if`) para a
        # fórmula continuar valendo se algum dia a nave apontar na diagonal.
        half_axial = (sprite_w / 2.0) * abs(ux) + (sprite_h / 2.0) * abs(uy)
        reach = half_axial + MUZZLE_STANDOFF
        ax, ay = cx + ux * reach, cy + uy * reach

        if not dual:
            return [(ax, ay)]

        # Perpendicular ao voo: as duas bocas do Double Shot abrem no eixo que
        # sobra, então elas acompanham a rotação junto com o resto.
        px, py = -uy, ux
        spread = (
            sprite_w * abs(px) + sprite_h * abs(py)
        ) * MUZZLE_DUAL_SPREAD
        return [
            (ax - px * spread, ay - py * spread),
            (ax + px * spread, ay + py * spread),
        ]

    @staticmethod
    def _rotate_fan(
        base: tuple[float, float],
        rotations: tuple[tuple[float, float], ...],
    ) -> list[tuple[float, float]]:
        """Abre a direção base num leque pré-resolvido (Spread Shot ou Cryo).

        Rotação 2D pura: preserva o módulo do vetor, então todas as balas saem
        com a MESMA velocidade do tiro normal — muda só o rumo inicial. O termo
        central das duas tabelas é (1, 0), ou seja, o tiro do meio é bit a bit o
        tiro padrão.
        """
        bx, by = base
        return [
            (bx * cos_a - by * sin_a, bx * sin_a + by * cos_a)
            for cos_a, sin_a in rotations
        ]

    @classmethod
    def _fan_directions(
        cls,
        base: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Leque de 5 do Spread Shot."""
        return cls._rotate_fan(base, SPREAD_SHOT_ROTATIONS)

    def bullet_spawn(self, apply_spread: bool = True) -> list[BulletSpec]:
        """Monta as balas do próximo disparo.

        Os modificadores são lidos uma vez e copiados IGUAIS para toda a salva —
        é assim que leque + perfurante + teleguiado + explosivo se combinam sem
        nenhum caso especial: cada campo do `BulletSpec` responde só pelo seu
        upgrade e não olha os outros.

        A exceção é o `critical`, sorteado DENTRO da compreensão: uma rolagem
        por bala, não por salva. Com o leque são 5 sorteios independentes por
        puxada de gatilho, e é isso que faz o upgrade cintilar em vez de ligar e
        desligar a salva inteira.

        `apply_spread=False` ignora o Spread Shot: é o que os charge shots usam,
        porque abrir o laser do Magneto ou os 5 teleguiados do Caçador em leque
        multiplicaria projéteis que já são o "muitos de uma vez" da nave.
        """
        is_piercing = self.piercing_shot_timer > 0
        is_homing = self.homing_shots_active
        is_explosive = (
            self.explosive_shots_active and self.explosive_shots_remaining > 0
        )
        is_low_ammo = is_explosive and self.explosive_shots_remaining <= 5
        crit_chance = CRITICAL_CORE_CHANCE if self.has_critical_core else 0.0
        is_cryo = self.has_cryo_shot

        facing_vector = self.get_facing_vector()

        # Obter tamanho visual atual do sprite (leva em conta rotação 90°/270°).
        sprite_w, sprite_h = self.get_rendered_sprite_size()

        spread = apply_spread and self.spread_shot_timer > 0.0
        # O leque SUBSTITUI as duas bocas do Double Shot em vez de multiplicar
        # por elas: 2 bocas x 5 direções seriam 10 balas por disparo, o dobro do
        # que o power-up promete e uma parede sólida na tela. Com os dois ativos
        # vale o leque, que é o mais raro dos dois. É a ÚNICA exclusividade que
        # existe entre modificadores de disparo, e ela é de geometria (de onde a
        # bala sai), não de comportamento do projétil.
        muzzles = self._muzzle_positions(
            sprite_w, sprite_h, dual=self.double_shot_timer > 0 and not spread
        )
        # Ordem dos leques: Spread (5) > trio do Cryo (3) > tiro único. Eles não
        # se multiplicam — 5×3 seriam 15 projéteis por puxada de gatilho, uma
        # parede que nenhum dos dois upgrades promete. Vale o mais largo, mesma
        # regra (e mesmo motivo) do leque sobre as duas bocas do Double Shot.
        #
        # `apply_spread=False` (charge shots) desliga os dois pela mesma razão:
        # 5 lasers do Magneto ou 5×5 teleguiados do Caçador já SÃO o "muitos de
        # uma vez" da nave, e abri-los em trio multiplicaria isso.
        if spread:
            directions = self._fan_directions(facing_vector)
        elif is_cryo and apply_spread:
            directions = self._rotate_fan(facing_vector, CRYO_SHOT_ROTATIONS)
        else:
            directions = [facing_vector]

        return [
            BulletSpec(
                x=mx,
                y=my,
                direction=direction,
                piercing=is_piercing,
                homing=is_homing,
                explosive=is_explosive,
                low_ammo=is_low_ammo,
                critical=random.random() < crit_chance,
                cryo=is_cryo,
                corrosive=self.has_corrosive_ammo,
            )
            for mx, my in muzzles
            for direction in directions
        ]

    def draw(self, surface: pygame.Surface):
        self._renderer.draw(surface)

    def take_damage(self, amount: int = 1) -> bool:
        """Aplica dano à nave. Retorna True se perdeu uma vida."""
        if self.is_invulnerable:
            return False

        # Absorção pelo escudo
        if self.has_shield:
            self.shield_hp -= amount
            if self.shield_hp <= 0:
                self.shield_timer = 0.0
            sound_manager.play_shield_break()  # play_shield_hit não existe (bug latente)
            # Mesma invuln curta do caminho vivo de dano do jogador
            # (scene._handle_ship_hit): protege de dano consecutivo imediato.
            self.grant_invulnerability(Config.SHIELD_ABSORB_INVULN_MS)
            return False

        self.lives -= amount
        self.grant_invulnerability(Config.INVULN_TIME * 1000)
        self.reset_combo()  # Reverberador perde o bônus ao tomar dano.
        return True

    def recover_life(self, amount: int = 1) -> None:
        """Recupera vidas da nave (respeitando o máximo inicial)."""
        self.lives = min(self.max_lives, self.lives + amount)

    # ── Debuff elétrico (campo da Torreta Orbital) ──────────────────────────
    # Ajustado para ser justo: descarga é um susto breve, não um congelamento
    # longo, e há janela de recuperação garantida entre paralisias.
    ELECTRIC_DEBUFF_DURATION: float = 6.0
    ELECTRIC_DISCHARGE_CHANCE: float = 0.10
    ELECTRIC_DISCHARGE_INTERVAL: float = 0.6  # cadência da rolagem de descarga
    ELECTRIC_STUN_MIN: float = 0.5
    ELECTRIC_STUN_MAX: float = 1.0
    ELECTRIC_STUN_RECOVERY: float = 2.5  # imunidade a nova paralisia após uma descarga

    def apply_electric_debuff(self, duration: float | None = None) -> None:
        """Aplica/renova o debuff elétrico (refresh, não acumula)."""
        self.electric_debuff_timer = max(
            self.electric_debuff_timer,
            duration if duration is not None else self.ELECTRIC_DEBUFF_DURATION,
        )

    @property
    def is_electrified(self) -> bool:
        """True enquanto o debuff "carregado" está ativo (pode descarregar)."""
        return self.electric_debuff_timer > 0.0

    @property
    def is_stunned(self) -> bool:
        """True enquanto a descarga trava o movimento da nave."""
        return self.electric_stun_timer > 0.0

    def is_dead(self) -> bool:
        return self.lives <= 0
