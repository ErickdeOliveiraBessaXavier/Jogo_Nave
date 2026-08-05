"""shooting_system.py — Sistema isolado de disparo do jogador.

Extrai de PlayingScene: _fire_bullets, _get_shoot_cooldown, shoot_cd e o
gerenciamento do canal de áudio do laser carregado do Magneto.

PlayingScene não é referenciada — comunicação via parâmetros explícitos.
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from ..core.config import config as Config
from ..core.fire_timer import FireTimer, emission_offset
from ..core.sound import sound_manager
from ..core.upgrades_config import (
    CRITICAL_CORE_CHANCE,
    CRITICAL_CORE_MULTIPLIER,
    CRYO_HEAVY_TARGET_DAMAGE_MULT,
    CRYO_SHOT_DAMAGE_MULTIPLIER,
    HOMING_DAMAGE_MULTIPLIER,
)
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..entities.player.ship import BulletSpec, Ship
    from ..systems.entity_manager import EntityManager

logger = logging.getLogger(__name__)

# Nerf de dano do Berserk ("Estrela Espiral") aplicado SÓ contra bosses, sobre o
# nerf global de upgrades. Ele cospe 4 balas a cada 0.1s com dano 1.5x: contra
# um inimigo pequeno só a bala daquela direção acerta (~3x o DPS do tiro
# normal), mas um boss é largo o bastante para comer VÁRIAS das 4 ao mesmo
# tempo — até 12x. O Giant Shot piora porque engorda a bala (mais delas
# conectam), sem tocar no dano; era esse par que derretia o boss.
_BERSERK_BOSS_DAMAGE_MULT: float = 0.5


# Intervalo entre rajadas do leque do Berserk (segundos).
_BERSERK_INTERVAL: float = 0.1


def _round_damage(value: float) -> int:
    """Arredonda o dano meio-para-cima, com piso 1.

    O truncamento anterior (`int()`) cortava a fração de TODA nave com
    multiplicador quebrado — 10×0.85 virava 8, não 9 —, ou seja, o dano
    efetivo não era o que o perfil declarava. `round()` embutido não serve:
    usa banker's rounding e mandaria 8.5 para 8 do mesmo jeito.
    """
    return max(1, int(value + 0.5))


class ShootingSystem:
    """Gerencia cooldown, disparo regular e charge shots especiais do jogador.

    Responsabilidades:
    - Cooldown de tiro (shoot_cd) decrementado em update()
    - Disparo de balas regulares via EntityManager.spawn_bullet
    - Charge shot do Magneto (laser contínuo via spawn_cacador_laser)
    - Charge shot do Caçador (5 homing bullets com targets round-robin)
    - Gerência do canal de áudio do laser carregado (precisa de referência
      local pois usa return_channel=True — não substituível por evento)
    - Emissão de PlayerShot event

    Comunicação com PlayingScene:
    - fire(ship, player_damage_multiplier) → dispara o tiro apropriado
    - is_ready(ship) → True quando o cooldown daquela nave zerou
    - update(dt) → decrementa cooldown e libera canal de áudio
    - reset() → zera cooldowns entre fases

    Cooldown é per-ship (dict keyed por id(ship)). Em multiplayer cada nave
    tem seu próprio timer de disparo, então P1 e P2 atiram independentemente.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        event_bus: EventBus,
    ) -> None:
        self._em = entity_manager
        self._bus = event_bus
        # Um FireTimer por nave, para o tiro normal e para o leque do Berserk.
        # Chave = a própria nave (WeakKeyDictionary): `id(ship)` era frágil
        # porque o CPython reaproveita endereços — uma nave destruída e outra
        # alocada no mesmo endereço herdavam o cooldown uma da outra —, e as
        # entradas só sumiam no `reset()` de troca de fase. Com referência fraca
        # a entrada morre junto com a nave, sozinha.
        self._timers: "WeakKeyDictionary[Ship, FireTimer]" = WeakKeyDictionary()
        self._berserk_timers: "WeakKeyDictionary[Ship, FireTimer]" = (
            WeakKeyDictionary()
        )
        self._charged_laser_channel: Any | None = None
        self._berserk_rotation: float = 0.0

    def is_ready(self, ship: Ship) -> bool:
        timer = self._timers.get(ship)
        return timer is None or timer.is_ready(self._interval_for(ship))

    def ability_busy(self, ship: Ship) -> bool:
        """O efeito da habilidade especial desta nave ainda está em curso?

        Vale para as duas naves com `has_charge_shot`: o laser do Magneto
        (`cacador_lasers`) e os teleguiados do Caçador (`homing_bullets`). As
        duas listas só são alimentadas pelo charge shot, então varrer ambas sem
        perguntar QUAL é a nave evita uma cascata por `ship.profile.id` (§5) —
        um Magneto nunca é dono de um teleguiado, e vice-versa.

        Filtrar por dono (`owner_ship`/`source_ship`) e não pelo tamanho da
        lista é o que mantém o coop funcionando: dois Caçadores atiram ao mesmo
        tempo, cada um travado só pelos próprios projéteis.

        O laser conta como em uso enquanto `state == "alive"` — o estado
        "dying" é só a poeira de partículas, já sem colisão, e travar a
        habilidade nele pareceria atraso sem causa visível. É o mesmo critério
        que solta o canal de áudio no `update`.
        """
        for laser in self._em.cacador_lasers:
            if (
                getattr(laser, "owner_ship", None) is ship
                and not laser.dead
                and getattr(laser, "state", "") == "alive"
            ):
                return True
        return any(
            getattr(b, "source_ship", None) is ship and not b.dead
            for b in self._em.homing_bullets
        )

    def try_start_charge(self, ship: Ship) -> bool:
        """Começa a carregar a habilidade, ou recusa com feedback se ela está em uso.

        Ponto único de entrada do input para o charge shot. O gate fica aqui, e
        não no `Ship.start_charge`, porque só este sistema enxerga os projéteis
        vivos — a nave não conhece o `EntityManager`.

        Recusar no INÍCIO da carga (e não no disparo) é deliberado: barrar só na
        hora de soltar faria o jogador segurar 0,8s para não receber nada, que é
        pior do que a reutilização que se quer impedir.
        """
        if self.ability_busy(ship):
            self._deny_ability(ship)
            return False
        return ship.start_charge()

    def _deny_ability(self, ship: Ship) -> None:
        """Arma o feedback (tremor/pisca na nave + blip de recusa)."""
        ship.deny_ability()
        self._bus.emit(
            events.AbilityDenied(
                ship_type=ship.profile.id,
                position=(ship.x, ship.y),
            )
        )

    def reset(self) -> None:
        """Zera todos os timers entre fases. O canal de áudio é liberado em update()."""
        self._timers.clear()
        self._berserk_timers.clear()

    def update(self, dt: float) -> None:
        """Credita `dt` nos timers e libera o canal do laser quando não há lasers vivos.

        O intervalo é recalculado a cada passo a partir da nave, então buffs e
        debuffs de cadência (Speed Boost, sobreaquecimento do Inferno, combo do
        Reverberador) valem já no frame em que entram, sem reconfiguração.
        """
        for ship, timer in list(self._timers.items()):
            timer.advance(dt, self._interval_for(ship))
        for timer in list(self._berserk_timers.values()):
            timer.advance(dt, _BERSERK_INTERVAL)

        if self._charged_laser_channel is not None:
            has_alive = any(
                getattr(laser, "state", "") == "alive"
                for laser in self._em.cacador_lasers
            )
            if not has_alive:
                self._charged_laser_channel.stop()
                self._charged_laser_channel = None

    def fire_berserk(
        self, ship: Ship, player_damage_multiplier: float, dt: float
    ) -> None:
        """Dispara projéteis em leque rotativo (Estrela Espiral) durante o modo Berserk."""
        timer = self._berserk_timers.get(ship)
        if timer is None:
            timer = self._berserk_timers[ship] = FireTimer()
        # Quem credita o tempo é o `update`, como nos demais timers — o gate
        # aqui é só o consumo. A ordem entre `fire_berserk` e `update` no frame
        # deixou de importar: o crédito não se perde por ser lido antes ou
        # depois, que era o motivo do fallback manual que existia aqui.
        if not timer.consume(_BERSERK_INTERVAL):
            return
        # Este `overshoot` era CONSUMIDO E DESCARTADO: o timer era gasto e o
        # valor nunca lido, então a Estrela Espiral saía sem compensação alguma
        # — nos dois eixos, e não só no da nave. Era o pior caso do projeto, e
        # justo na arma que mais enche a tela de projéteis.
        overshoot = timer.overshoot
        emit_velocity = ship.emit_velocity

        # Rotação global constante (Estilo Stone Golem)
        self._berserk_rotation += dt * 360  # Uma volta completa por segundo

        cx = ship.x + ship.w / 2
        cy = ship.y + ship.h / 2

        # Bônus de dano Berserk (1.5x), e o do Cryo por cima quando ativo — o
        # leque do Berserk não passa pelo `bullet_spawn`, então sem esta linha o
        # upgrade ficaria pela metade justamente na nave que mais atira.
        # O trio do Cryo NÃO entra aqui: a Estrela Espiral já dispara nas 4
        # direções, e abrir cada uma em três seria uma parede de 12 projéteis.
        cryo_mult = CRYO_SHOT_DAMAGE_MULTIPLIER if ship.has_cryo_shot else 1.0
        adjusted_damage = _round_damage(
            Config.BULLET_BASE_DAMAGE
            * player_damage_multiplier
            * ship.damage_multiplier
            * 1.5
            * cryo_mult
        )

        # O Berserk também crita: a regra é "toda BALA da nave pode sair
        # crítica", e uma exceção aqui seria invisível para o jogador — ele veria
        # o upgrade parar de funcionar sem nada explicando. Os dois se compõem
        # (1,5× do Berserk × 2,5× do crítico), o que é caro em slots nos dois
        # lados; o nerf anti-boss do Berserk continua valendo por cima.
        crit_chance = CRITICAL_CORE_CHANCE if ship.has_critical_core else 0.0

        # Dispara em 4 direções rotativas (Cruz Espiral)
        # Reduzido de 8 para 4 conforme solicitado ("tiros demais")
        for i in range(4):
            angle_deg = (i * 90.0) + self._berserk_rotation
            angle_rad = math.radians(angle_deg)
            dir_vec = (math.cos(angle_rad), math.sin(angle_rad))

            critical = random.random() < crit_chance
            # Usando BulletPool via EntityManager.spawn_bullet
            bullet = self._em.spawn_bullet(
                cx,
                cy,
                damage=(
                    _round_damage(adjusted_damage * CRITICAL_CORE_MULTIPLIER)
                    if critical
                    else adjusted_damage
                ),
                direction=dir_vec,
                ship_id="berserk",
                owner_ship=ship,
                size_multiplier=ship.bullet_size_multiplier,
                boss_damage_mult=_BERSERK_BOSS_DAMAGE_MULT,  # nerf só em boss
                critical=critical,
                cryo=ship.has_cryo_shot,
                corrosive=ship.has_corrosive_ammo,
            )
            self._apply_subframe_catchup(bullet, overshoot, emit_velocity)

        # Efeito sonoro
        sound_manager.play_shot()

    def fire(self, ship: Ship, player_damage_multiplier: float) -> None:
        """Dispara o tiro apropriado e reinicia o cooldown.

        Magneto/Caçador com charge ativo emitem o projétil especial respectivo.
        """
        # Gasta o intervalo ANTES de emitir: o `overshoot` resultante é há
        # quanto tempo este disparo já era devido, e vira deslocamento inicial
        # das balas — ver `_apply_subframe_catchup`.
        overshoot = self._consume_shot(ship)
        charge_factor = ship.consume_charge()
        adjusted_damage = _round_damage(
            Config.BULLET_BASE_DAMAGE
            * player_damage_multiplier
            * ship.damage_multiplier
            * charge_factor
        )

        is_charge_shot = ship.profile.has_charge_shot and charge_factor > 1.0
        if is_charge_shot:
            ship_id = getattr(ship.profile, "id", "")
            # Rede de segurança do gate de reutilização: quem impede de verdade
            # é o `try_start_charge` (a carga nem começa). Aqui só se cobre o
            # caso de a carga ter começado antes do efeito anterior terminar —
            # sem isto, um segundo laser/burst nasceria por cima do primeiro.
            if ship_id in ("magneto", "cacador") and self.ability_busy(ship):
                self._deny_ability(ship)
                return
            # `apply_spread=False`: o charge shot não abre no leque do Spread
            # Shot. Cada spec vira um projétil especial aqui — 5 lasers do
            # Magneto ou 5x5 teleguiados do Caçador —, e esses já SÃO o
            # "muitos de uma vez" da nave. O leque volta a valer no tiro
            # normal, que é onde ele foi balanceado.
            if ship_id == "magneto":
                self._fire_magneto_charge(
                    ship,
                    ship.bullet_spawn(apply_spread=False),
                    adjusted_damage,
                    charge_factor,
                )
                return
            if ship_id == "cacador":
                self._fire_cacador_charge(
                    ship,
                    ship.bullet_spawn(apply_spread=False),
                    adjusted_damage,
                    charge_factor,
                )
                return

        bullet_specs = ship.bullet_spawn()

        self._bus.emit(
            events.PlayerShot(
                ship_type=ship.profile.id,
                projectile_type="bullet",
                position=(ship.x, ship.y),
                charge_level=1.0,
            )
        )

        # Por DISPARO, não por bala: valem igualmente para a salva inteira, então
        # o leque (e o Double Shot) recebem exatamente o mesmo tratamento que o
        # tiro único — é o que faz Giant Shot valer para as cinco balas sem uma
        # linha de código sobre leque aqui.
        size_mult = ship.bullet_size_multiplier
        # Lida uma vez para a salva inteira: todas as balas do mesmo disparo
        # saíram no mesmo instante, então compartilham a mesma correção.
        emit_velocity = ship.emit_velocity
        fired_explosive = False

        for spec in bullet_specs:
            # Tiros teleguiados levam multiplicador de dano direto. Combinados
            # com explosivo, o impacto direto fica mais forte (a explosão usa
            # EXPLOSIVE_BULLET_DAMAGE no collision system).
            bullet_damage = (
                int(adjusted_damage * HOMING_DAMAGE_MULTIPLIER)
                if spec.homing
                else adjusted_damage
            )
            # Cryo Shot: o cristal bate mais forte que a bala comum. Multiplica
            # aqui (e não em `adjusted_damage`) pelo mesmo motivo do teleguiado —
            # é bônus DO PROJÉTIL, e o `adjusted_damage` é o dano da nave, lido
            # uma vez para a salva inteira.
            if spec.cryo:
                bullet_damage = _round_damage(
                    bullet_damage * CRYO_SHOT_DAMAGE_MULTIPLIER
                )
            # Crítico multiplica DEPOIS de tudo (perfil da nave, power-up de
            # dano, teleguiado), então ele vale sempre os mesmos 2,5× sobre o
            # dano que aquela bala causaria — e não uma fração dele.
            # A explosão do tiro explosivo NÃO crita: ela é dano de área com
            # valor próprio (EXPLOSIVE_BULLET_DAMAGE), não o impacto da bala.
            if spec.critical:
                bullet_damage = _round_damage(
                    bullet_damage * CRITICAL_CORE_MULTIPLIER
                )
            bullet = self._em.spawn_bullet(
                spec.x,
                spec.y,
                damage=bullet_damage,
                piercing=spec.piercing,
                homing=spec.homing,
                explosive=spec.explosive,
                low_ammo=spec.low_ammo,
                direction=spec.direction,
                ship_id=ship.profile.id,
                owner_ship=ship,
                size_multiplier=size_mult,
                # Nerf anti-chefe do Cryo, no mesmo canal do Wingman e da
                # Estrela Espiral. O trio só existe quando `spec.cryo`, então o
                # tiro comum segue em 1.0 — a redução acompanha o leque, não a
                # nave. A metade miniboss desta regra é cobrada no passe de
                # colisão (`Collisions.bullets_vs_enemies`), porque miniboss é
                # inimigo comum para o roteador e não passa por aqui.
                boss_damage_mult=(
                    CRYO_HEAVY_TARGET_DAMAGE_MULT if spec.cryo else 1.0
                ),
                critical=spec.critical,
                cryo=spec.cryo,
                corrosive=spec.corrosive,
            )
            self._apply_subframe_catchup(bullet, overshoot, emit_velocity)
            fired_explosive = fired_explosive or spec.explosive

        # Carga explosiva é gasta por DISPARO, não por bala. O upgrade entrega N
        # cargas e o jogador as lê como N puxadas de gatilho; cobrando por bala,
        # o MESMO upgrade duraria 10 disparos sozinho, 5 com Double Shot e 2 com
        # o leque — o power-up de cobertura roubando munição do de dano, sem
        # nada na tela explicando por quê. Cobrando por salva, todas as balas
        # explodem (que é o ponto de combinar os dois) e a economia do upgrade
        # deixa de depender de quais power-ups estão ativos junto.
        if fired_explosive:
            ship.consume_explosive_shot()

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _interval_for(ship: Ship) -> float:
        """Intervalo alvo entre disparos, em segundos.

        Recalculado a cada consulta a partir de `attack_speed_multiplier`, que
        já compõe perfil da nave + power-ups + debuffs. Nenhum estado de cadência
        é guardado: adicionar um modificador novo é mexer só naquele
        multiplicador, sem tocar neste sistema.
        """
        rate = ship.attack_speed_multiplier * Config.FIRE_RATE
        return 1.0 / rate if rate > 0.0 else float("inf")

    def _consume_shot(self, ship: Ship) -> float:
        """Gasta um intervalo do timer da nave e devolve o `overshoot`.

        Disparo fora da cadência (charge shot, que sai no soltar da tecla sem
        passar por `is_ready`) não tem intervalo para gastar: nesse caso o timer
        é drenado, para o tiro seguinte respeitar a cadência cheia em vez de
        sair de imediato com o crédito acumulado durante a carga.
        """
        timer = self._timers.get(ship)
        if timer is None:
            timer = self._timers[ship] = FireTimer()
        if timer.consume(self._interval_for(ship)):
            return timer.overshoot
        timer.drain()
        return 0.0

    @staticmethod
    def _apply_subframe_catchup(
        bullet: Any, overshoot: float, emitter_velocity: tuple[float, float]
    ) -> None:
        """Adianta a bala pelo tempo que o disparo atrasou.

        Sem isto, todas as balas nascem exatamente na boca da nave e o
        espaçamento entre elas no ar herda o arredondamento do frame: numa
        cadência de 6.4 frames, os vãos alternam entre 6 e 7 frames de distância
        e a rajada parece engasgar.

        A conta é `emission_offset` — velocidade RELATIVA, não a da bala
        sozinha. Compensar só a bala corrige o eixo de voo e deixa o eixo do
        movimento da nave com o mesmo erro de quantização, o que aparecia como
        rastro desigual ao andar de lado (o caso normal de jogo, não um canto).
        Ver o racional e os números em `core/fire_timer.py`.
        """
        if overshoot <= 0.0 or bullet is None:
            return
        dx, dy = emission_offset(
            bullet.vx, bullet.vy, emitter_velocity[0], emitter_velocity[1], overshoot
        )
        bullet.x += dx
        bullet.y += dy

    def _fire_magneto_charge(
        self,
        ship: Ship,
        bullet_specs: list[BulletSpec],
        adjusted_damage: int,
        charge_factor: float,
    ) -> None:
        """Dispara o laser carregado do Magneto.

        Mantém referência ao canal de áudio para pará-lo quando o laser
        termina (gerido em update()).
        """
        if self._charged_laser_channel is not None:
            self._charged_laser_channel.stop()
        self._charged_laser_channel = sound_manager.play_boss_laser_fire(
            return_channel=True
        )
        self._bus.emit(
            events.PlayerShot(
                ship_type="magneto",
                projectile_type="cacador_laser",
                position=(ship.x, ship.y),
                charge_level=charge_factor,
            )
        )
        for x, y, direction, *_ in bullet_specs:
            dx, dy = direction
            mag = math.hypot(dx, dy)
            if mag == 0.0:
                continue
            unit_dir = (dx / mag, dy / mag)
            self._em.spawn_cacador_laser(
                x,
                y,
                direction=unit_dir,
                damage=adjusted_damage,
                owner_ship=ship,
            )

    def _fire_cacador_charge(
        self,
        ship: Ship,
        bullet_specs: list[BulletSpec],
        adjusted_damage: int,
        charge_factor: float,
    ) -> None:
        """Dispara 5 tiros teleguiados com targets round-robin.

        O gate de "um burst por Caçador na tela" subiu para `ability_busy`, que
        vale também para o laser do Magneto e agora recusa a carga ANTES de o
        jogador segurar o botão — aqui a chamada já chega liberada.
        """
        self._bus.emit(
            events.PlayerShot(
                ship_type="cacador",
                projectile_type="homing_bullets",
                position=(ship.x, ship.y),
                charge_level=charge_factor,
            )
        )
        count = 5
        spread = math.radians(90)
        divisor = max(1, count - 1)

        live_enemies: list[Any] = [
            e for e in self._em.enemies if not getattr(e, "dead", False)
        ]
        if self._em.boss and not getattr(self._em.boss, "dead", False):
            live_enemies.append(self._em.boss)

        for x, y, direction, *_ in bullet_specs:
            dx, dy = direction
            mag = math.hypot(dx, dy)
            if mag == 0.0:
                continue
            base_angle = math.atan2(dy, dx)
            for i in range(count):
                t = i / divisor
                angle = base_angle - spread / 2 + t * spread
                dir_vec = (math.cos(angle), math.sin(angle))
                target = live_enemies[i % len(live_enemies)] if live_enemies else None
                self._em.spawn_homing_bullet(
                    x,
                    y,
                    damage=adjusted_damage,
                    direction=dir_vec,
                    locked_target=target,
                    source_ship=ship,
                )
