import math
from typing import Any, List, Optional, Tuple

import pygame

from ...core.config import config as Config
from ...core.ship_types import get_ship_profile
from ...core.upgrades_config import (
    CRYO_SHARD_LIFETIME,
    CRYO_SHARD_SIZE,
    CRYO_SHARD_SPEED,
    GIANT_SHOT_SPEED_MULTIPLIER,
    GIANT_SHOT_SQUARENESS,
)
from ...systems.targeting import target_point
from . import bullet_fx

# Velocidade de rastreamento do tiro teleguiado (px/s), antes do Giant Shot.
_HOMING_BASE_SPEED: float = 300.0

# Giro do '+' no próprio eixo (graus/s). Em VIAGEM (perseguindo um alvo) gira no
# ritmo de sempre — 1 volta/s. Em ESPERA (sem inimigo em tela, pairando no
# lugar) gira mais rápido: parado, o giro lento de um '+' quase simétrico lê como
# estático; acelerar deixa claro que a bala está viva, à espreita do próximo.
_HOMING_SPIN_SPEED: float = 360.0
_HOMING_IDLE_SPIN_SPEED: float = 900.0


def _owner_combo_intensity(owner_ship: Optional[Any]) -> float:
    """Progresso do combo (0..1) do dono no instante do disparo.

    Fica congelado na bala em vez de lido por frame: o tiro carrega a força com
    que saiu, e um dano tomado no meio do voo não apaga os projéteis no ar.
    """
    try:
        return max(0.0, min(1.0, float(getattr(owner_ship, "combo_progress", 0.0))))
    except (TypeError, ValueError):
        return 0.0


class Bullet:
    def __init__(
        self,
        x: float,
        y: float,
        damage: int = Config.BULLET_BASE_DAMAGE,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        ship_id: str = "padrao",
        owner_ship: Optional[Any] = None,
        size_multiplier: float = 1.0,
        boss_damage_mult: float = 1.0,
        critical: bool = False,
        cryo: bool = False,
        corrosive: bool = False,
        ice_shard: bool = False,
    ):
        self.x, self.y = x, y
        self.damage = damage
        self.dead = False
        # Corrosive Ammo: só VISUAL na bala (o halo verde-ácido), pelo mesmo
        # motivo do `cryo` abaixo — quem empilha o ácido é o sistema de colisão,
        # lendo `owner_ship.has_corrosive_ammo`.
        self.corrosive = corrosive
        # Cryo Shot: só VISUAL na bala. Quem aplica a escada de gelo é o sistema
        # de colisão, lendo `owner_ship.has_cryo_shot` — a marca é do dono, não
        # do projétil, porque em coop cada nave responde pelo próprio upgrade.
        self.cryo = cryo
        # Fragmento da bomba de gelo (estilhaço do congelado que detonou). É uma
        # bala de verdade — reusa pool, colisão, crédito de kill — mas com regras
        # próprias: tamanho/velocidade fixos (não herda a nave), vida curta, sem
        # perfuração, e NÃO propaga upgrades do dono (ver `collisions`).
        self.ice_shard = ice_shard
        # Tempo de vida restante do fragmento (só ele usa). O alcance do estouro
        # é limitado por TEMPO e não por distância percorrida: dois fragmentos
        # que saem juntos somem juntos, e o leque morre como um evento só.
        self.shard_life = CRYO_SHARD_LIFETIME if ice_shard else 0.0
        # Alvo que originou o fragmento: ele não pode ser atingido pelos próprios
        # estilhaços (o dano dele já veio do estouro). Sem isso a bomba cobraria
        # duas vezes do mesmo inimigo — e num boss, cujo raio de colisão é largo,
        # o leque inteiro voltaria para dentro do corpo.
        self.shard_source_id = 0
        # Crítico (Critical Core): o `damage` acima JÁ vem multiplicado. A flag
        # não é lida para calcular dano nenhum — só para o impacto sair maior
        # (`impact_scale_for_projectile`), que é o feedback do upgrade.
        self.critical = critical
        self.size_multiplier = size_multiplier  # Giant Shot escala w/h (visual+hitbox)
        # Nerf de dano aplicado SÓ contra bosses, lido em `collisions.
        # _project_into_boss`. 1.0 = sem mudança (todo tiro comum).
        self.boss_damage_mult = boss_damage_mult
        self.piercing = piercing
        self.homing = homing
        self.explosive = explosive  # Tiro explosivo
        self.low_ammo = low_ammo  # Indica poucas cargas (para efeito de piscar)
        self.active = True  # Para o Pool Pattern
        self.target: Optional[Any] = None  # Alvo atual do tiro teleguiado
        self.assigned_target_id: Optional[int] = None  # ID do alvo atribuído
        # Velocidade de rastreamento (px/s). Reatribuída em
        # `_configure_shape_and_velocity` (Giant Shot acelera) — o valor aqui é
        # só o default antes daquela chamada.
        self.homing_speed = _HOMING_BASE_SPEED
        self.homing_turn_rate = 4.0  # Curva de perseguição (radianos/s)
        # Direção de voo do teleguiado (radianos). É virada gradualmente em
        # direção ao alvo (limite = homing_turn_rate) para o rastreio ser
        # orgânico e não mudar de rumo de forma abrupta. None = ainda não voou.
        self.homing_heading: Optional[float] = None
        self.rotation_angle = 0.0  # Ângulo de rotação visual (graus)
        # Relógio das animações de rastro (gelo escorrendo, ácido serpenteando).
        # Acumulador PRÓPRIO alimentado pelo update, nunca `time.get_ticks()`
        # (§3): assim o rastro para junto com o jogo na pausa e desacelera com
        # ele na câmera lenta, em vez de continuar correndo por fora.
        self.anim_time = 0.0
        self.is_side_scroll = is_side_scroll  # Se está em modo side-scroll
        self.laser_sound_channel: Optional[pygame.mixer.Channel] = None
        self.vx = 0.0
        self.vy = 0.0
        self.direction = direction
        self.ship_id = ship_id
        # Nave que disparou — usado para atribuir kills ao Reverberador certo
        # em coop (sem isso, o combo do P2 cresce com kills do P1 e vice-versa).
        self.owner_ship: Optional[Any] = owner_ship
        # Derivado do dono em vez de pedido no construtor: todo call site já
        # passa `owner_ship`, e uma cópia local evita um getattr encadeado por
        # cor por frame no draw. Sem dono, desenha como P1.
        self.player_index: int = getattr(owner_ship, "player_index", 0)
        # Combo do Reverberador congelado no disparo (0..1) — pinta o projétil.
        self.combo_intensity: float = _owner_combo_intensity(owner_ship)
        # Cargas de perfuração restantes (Aríete). Consumidas em `collisions`.
        self.pierce_remaining: int = 0

        # Rect persistente — atualizado in-place em vez de alocar por acesso.
        self._rect = pygame.Rect(int(x), int(y), 1, 1)

        self._configure_shape_and_velocity(direction)
        self.pierce_remaining = self._owner_pierce_count()
        self._sync_rect()

    @property
    def rect(self) -> pygame.Rect:
        self._sync_rect()
        return self._rect

    def _sync_rect(self) -> None:
        self._rect.update(int(self.x), int(self.y), self.w, self.h)

    def reset(
        self,
        x: float,
        y: float,
        damage: int = Config.BULLET_BASE_DAMAGE,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        ship_id: str = "padrao",
        owner_ship: Optional[Any] = None,
        size_multiplier: float = 1.0,
        boss_damage_mult: float = 1.0,
        critical: bool = False,
        cryo: bool = False,
        corrosive: bool = False,
        ice_shard: bool = False,
    ):
        """Reconfigura a bala para reutilização no pool.

        Todo campo de modificador tem que ser reescrito aqui, inclusive quando o
        valor é `False`: a bala vem de uma vida anterior e, sem isto, herda o
        crítico (ou o explosivo) do disparo que a usou por último.
        """
        self.x, self.y = x, y
        self.damage = damage
        self.critical = critical
        self.cryo = cryo
        self.corrosive = corrosive
        self.ice_shard = ice_shard
        self.shard_life = CRYO_SHARD_LIFETIME if ice_shard else 0.0
        self.shard_source_id = 0
        self.dead = False
        self.size_multiplier = size_multiplier
        self.boss_damage_mult = boss_damage_mult
        self.piercing = piercing
        self.homing = homing
        self.explosive = explosive
        self.low_ammo = low_ammo
        self.is_side_scroll = is_side_scroll
        self.active = True
        self.target = None
        self.assigned_target_id = None
        self.homing_heading = None
        self.rotation_angle = 0.0
        # Zerado como todo campo de estado: a bala vem de uma vida anterior e o
        # rastro herdado entraria no meio do ciclo, com um salto visível.
        self.anim_time = 0.0
        self.laser_sound_channel = None
        self.vx = 0.0
        self.vy = 0.0
        self.direction = direction
        self.ship_id = ship_id
        self.owner_ship = owner_ship
        self.player_index = getattr(owner_ship, "player_index", 0)
        self.combo_intensity = _owner_combo_intensity(owner_ship)
        self._configure_shape_and_velocity(direction)
        self.pierce_remaining = self._owner_pierce_count()
        self._sync_rect()

    def update(self, dt: float, enemies: Optional[List[Any]] = None) -> None:
        # Relógio do rastro, antes de qualquer ramo: vale para toda bala, e é o
        # update que o alimenta para o draw poder ficar sem efeito colateral (§3).
        self.anim_time += dt
        if self.homing:
            # `enemies` pode vir vazio (nenhum hostil): ainda assim entramos aqui
            # para pairar no lugar, em vez de cair no `else` e subir para fora da
            # tela. O alvo é atribuído pelo coordenador (EntityManager).
            self._update_homing(dt)
            # Gira no próprio eixo sempre — mais rápido enquanto espera (sem
            # alvo), para pairar girando em vez de parecer congelado.
            spin = (
                _HOMING_IDLE_SPIN_SPEED if self.target is None else _HOMING_SPIN_SPEED
            )
            self.rotation_angle = (self.rotation_angle + spin * dt) % 360.0
        else:
            # Estilos que giram no próprio eixo (Berserk). Fica fora do `if
            # homing` acima porque as duas rotações são independentes — um tiro
            # do Berserk não é teleguiado. A velocidade vem do estilo, e não de
            # um `ship_id ==` aqui: quem gira é quem tem frames pré-rotacionados
            # para consumir o ângulo, e isso é propriedade do desenho.
            spin = bullet_fx.ship_styles.style_for(self.ship_id).spin_speed
            if spin:
                self.rotation_angle = (self.rotation_angle + spin * dt) % 360.0
            if self.vx != 0.0 or self.vy != 0.0:
                self.x += self.vx * dt
                self.y += self.vy * dt
            else:
                # Movimento baseado no modo de jogo
                if self.is_side_scroll:
                    # Side-scroll: movimento para direita
                    self.x += Config.BULLET_SPEED * dt
                else:
                    # Top-down: movimento para cima
                    self.y -= Config.BULLET_SPEED * dt

        if self.ice_shard:
            # Alcance do estouro por TEMPO de vida. Sem isto o fragmento
            # atravessaria a tela e a bomba viraria uma salva de 8 tiros grátis
            # em qualquer direção — o oposto de "limpa a vizinhança do alvo".
            self.shard_life -= dt
            if self.shard_life <= 0.0:
                self.dead = True

        if self.y + self.h < 0 or self.y > Config.SCREEN_HEIGHT:
            self.dead = True
        if self.x < -50 or self.x > Config.SCREEN_WIDTH + 50:
            self.dead = True

    def _update_homing(self, dt: float) -> None:
        """Persegue o alvo atribuído pelo coordenador (``EntityManager``).

        A seleção de alvo vive fora da bala: é balanceada entre todos os
        teleguiados e restrita a inimigos em tela (ver
        ``EntityManager._assign_homing_targets``). Aqui a bala só age sobre o
        ``self.target`` já resolvido.

        Sem alvo — nenhum inimigo visível — a bala **paira no lugar**, esperando
        o próximo entrar; não sobe para fora da tela.

        A perseguição é **orgânica**: em vez de apontar direto ao alvo a cada
        frame (virada instantânea), a bala vira a própria direção de voo
        (``homing_heading``) em direção ao alvo, limitada por
        ``homing_turn_rate``. Ao trocar de alvo ou o alvo desviar, ela curva
        suavemente em vez de mudar de rumo de repente.
        """
        target = self.target
        if target is not None and getattr(target, "dead", True):
            target = self.target = None

        if target is None:
            # Idle: zera a velocidade para que, parada, não seja morta pela
            # checagem de fora-da-tela no fim de `update`. O heading é preservado
            # para curvar a partir dele quando um novo alvo aparecer.
            self.vx = 0.0
            self.vy = 0.0
            return

        # Ponto de mira preciso (segue a geometria real de bosses via
        # collision_circle; cai para o centro do rect nos inimigos comuns).
        aim = target_point(target)
        if aim is None:
            return
        dx = aim[0] - self.x
        dy = aim[1] - self.y
        distance = (dx * dx + dy * dy) ** 0.5
        if distance <= 0:
            return

        desired = math.atan2(dy, dx)

        # 1º frame de voo: alinha o heading à direção com que a bala nasceu (ou
        # já ao alvo, se nasceu parada) — evita uma curva inicial fantasma.
        if self.homing_heading is None:
            if self.vx != 0.0 or self.vy != 0.0:
                self.homing_heading = math.atan2(self.vy, self.vx)
            else:
                self.homing_heading = desired

        # Vira o heading em direção ao alvo, no máximo homing_turn_rate*dt.
        # O delta é normalizado para (-π, π] para virar sempre pelo lado curto.
        diff = (desired - self.homing_heading + math.pi) % (2 * math.pi) - math.pi
        max_turn = self.homing_turn_rate * dt
        if diff > max_turn:
            diff = max_turn
        elif diff < -max_turn:
            diff = -max_turn
        self.homing_heading += diff

        hx = math.cos(self.homing_heading)
        hy = math.sin(self.homing_heading)
        self.vx = hx * self.homing_speed
        self.vy = hy * self.homing_speed
        self.x += hx * self.homing_speed * dt
        self.y += hy * self.homing_speed * dt

    def _owner_bullet_speed_mult(self) -> float:
        """`bullet_speed_mult` do perfil do dono (1.0 sem dono/perfil)."""
        profile = getattr(self.owner_ship, "profile", None)
        try:
            return max(0.1, float(getattr(profile, "bullet_speed_mult", 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def _owner_pierce_count(self) -> int:
        """Alvos extras que o tiro comum atravessa, vindos do perfil do dono.

        Só vale para o tiro básico: teleguiado e explosivo têm as próprias
        regras de impacto e não devem herdar a perfuração da nave. O fragmento
        de gelo também fica de fora — ele não saiu do canhão da nave, e deixá-lo
        atravessar multiplicaria o dano do estouro pela nave equipada.
        """
        if self.homing or self.explosive or self.ice_shard:
            return 0
        profile = getattr(self.owner_ship, "profile", None)
        try:
            return max(0, int(getattr(profile, "pierce_count", 0)))
        except (TypeError, ValueError):
            return 0

    def _bullet_base_size(self) -> Tuple[int, int]:
        """`(comprimento, espessura)` do tiro, vindo do perfil da nave.

        Resolve pelo **`ship_id`**, e não pelo `owner_ship.profile` como os
        vizinhos `_owner_bullet_speed_mult`/`_owner_pierce_count`. A diferença é
        deliberada: o Berserk dispara com `ship_id="berserk"` mas passa a nave
        real como dono, e o tiro dele tem forma PRÓPRIA — igual para todo o
        elenco. Resolver pelo dono faria a Estrela Espiral herdar o formato de
        cada nave, que é justamente o que ela não quer.

        `get_ship_profile` já cai no perfil padrão para id desconhecido, então
        "berserk" e qualquer pseudo-nave futura continuam na forma de referência.
        """
        size = get_ship_profile(self.ship_id).bullet_size
        return max(1, int(size[0])), max(1, int(size[1]))

    def _configure_shape_and_velocity(
        self, direction: tuple[float, float] | None
    ) -> None:
        """Configura dimensões e velocidade do projétil com base na direção e nave."""
        # Fragmento da bomba de gelo: geometria PRÓPRIA, não a da nave. Ele não
        # é o tiro de ninguém — é um caco do inimigo que estilhaçou —, então nem
        # o `bullet_speed_mult` do perfil nem o Giant Shot mexem nele. Sai antes
        # de tudo: nenhuma das regras abaixo se aplica.
        if self.ice_shard:
            self.w = self.h = CRYO_SHARD_SIZE
            dx, dy = direction if direction is not None else (0.0, -1.0)
            self.vx = dx * CRYO_SHARD_SPEED
            self.vy = dy * CRYO_SHARD_SPEED
            self.homing_speed = _HOMING_BASE_SPEED
            return

        # Dimensões-base vindas do PERFIL da nave, não de uma cascata de
        # `ship_id` aqui dentro (§5) — ver `_bullet_base_size`.
        base_w, base_h = self._bullet_base_size()

        # Tamanho-base de todas as naves (visual + hitbox). Aplicado ANTES do
        # Giant Shot, que passa a escalar a partir do base novo — o "3x" do
        # upgrade continua sendo 3x do tiro que a nave realmente atira.
        bonus = Config.BULLET_BASE_SIZE_BONUS
        if bonus:
            base_w = max(1, base_w + bonus)
            base_h = max(1, base_h + bonus)

        # Velocidade por nave (`bullet_speed_mult`): contrapartida da cadência —
        # o tiro pesado chega antes, o tiro-metralhadora chega depois. Lida do
        # perfil do dono em vez de uma tabela local, para não duplicar o valor.
        mult = self.size_multiplier
        speed = Config.BULLET_SPEED * self._owner_bullet_speed_mult()
        giant_ratio = 1.0
        if mult != 1.0:
            base_w, base_h = self._giant_dims(base_w, base_h, mult)
            speed *= GIANT_SHOT_SPEED_MULTIPLIER
            giant_ratio = GIANT_SHOT_SPEED_MULTIPLIER
        # O teleguiado segue só a escala do Giant Shot: ele tem tuning próprio
        # (`_HOMING_BASE_SPEED` + turn rate), e herdar a velocidade da nave
        # mexeria no raio de curva de um powerup já balanceado à parte.
        self.homing_speed = _HOMING_BASE_SPEED * giant_ratio

        if direction is None:
            if self.is_side_scroll:
                self.vx = speed
                self.vy = 0.0
                self.w, self.h = base_w, base_h
            else:
                self.vx = 0.0
                self.vy = -speed
                self.w, self.h = base_h, base_w
            return

        dx, dy = direction
        # Ajustar orientação baseada na direção predominante
        if abs(dx) >= abs(dy):
            self.w, self.h = base_w, base_h
        else:
            self.w, self.h = base_h, base_w

        self.vx = dx * speed
        self.vy = dy * speed

    @staticmethod
    def _giant_dims(base_w: int, base_h: int, mult: float) -> Tuple[int, int]:
        """Escala o tiro por `mult` puxando a proporção para o quadrado.

        Cada lado é interpolado (em escala log) entre ele mesmo e a média
        geométrica dos dois — o lado do quadrado de mesma área —, na dose de
        `GIANT_SHOT_SQUARENESS`. A área final é `mult²` vezes a original para
        QUALQUER dose, então a forma muda sem alterar o quanto o tiro cresceu:
        um tiro fino vira um bloco chunky em vez de uma barra comprida, e um
        tiro já quadrado não muda de forma.
        """
        k = GIANT_SHOT_SQUARENESS
        mean = math.sqrt(base_w * base_h)
        w = mult * (base_w ** (1.0 - k)) * (mean**k)
        h = mult * (base_h ** (1.0 - k)) * (mean**k)
        return max(1, round(w)), max(1, round(h))

    def assign_target(self, target: Any) -> None:
        """Atribui um alvo específico ao tiro teleguiado."""
        self.target = target
        self.assigned_target_id = id(target) if target else None

    def draw(self, surface: pygame.Surface):
        """Pinta o projétil. Todo o VISUAL mora em `bullet_fx` (§9).

        A classe fica com o que é da bala — trajetória, tamanho, ciclo de vida e
        o contrato do pool. Qual efeito desenha o corpo é decisão da cadeia de
        prioridade do pacote, não de um `if` por modificador aqui.
        """
        # Halo pulsante ANTES do corpo (fica atrás do tiro).
        bullet_fx.glow.draw_pulse(self, surface)
        bullet_fx.draw_body(self, surface)

