"""A Tríade — chefe nativo da CITY (nível 34).

Uma mente com três vozes: uma cabeça principal ("a Coroa", que carrega o HP real
do boss) e duas laterais ("as Vozes") que existem para PROTEGÊ-LA. Enquanto uma
lateral estiver sólida, a Coroa é intangível; derrubar as duas abre a JANELA DE
RESSONÂNCIA, a única fonte de dano real da luta. As laterais voltam depois de um
tempo, mas o dano na Coroa é permanente — o jogador perde tempo, nunca progresso.

Ver `PLANO_BOSS_TRIADE.md` (local, §13) para o desenho completo do encontro.

## O que existe neste arquivo

Etapas 1 e 2 do plano: **esqueleto + ressonância**. O boss entra, flutua, tem as
três hitboxes, roteia dano por posição, e o portão abre/fecha/regenera com o
feedback de UI. **Ainda não ataca** — é deliberado: a etapa 2 é a que decide se a
mecânica central é boa, e ela precisa ser jogada limpa, sem projétil nenhum
mascarando o ritmo do ciclo.

## Repartição

    triad_pixel_map   geometria e sprites (fonte única das medidas)
    triad_head        o CORPO de uma lateral (HP, sprite, flash)
    triad_resonance   o TEMPO e a REGRA do portão (lógica pura, testável)
    triad_boss        esta fachada: FSM, hitboxes, roteamento de dano, render

O portão não conhece as cabeças e as cabeças não conhecem o portão (§1); esta
classe é o único ponto que lê um e empurra para o outro.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ....core.assets import get_font
from ....core.config import config as Config
from ....core.events import EventBus
from ...bosses.boss_hit_mixin import BossHitMixin
from . import triad_pixel_map as pmap
from .triad_head import TriadHead
from .triad_orb import OrbBehavior, TriadOrb, make_lob
from .triad_resonance import LEFT, RIGHT, HeadState, ResonanceEvent, ResonanceGate

if TYPE_CHECKING:
    from ....systems.boss_context import BossUpdateContext, BossUpdateResult
    from ....systems.hit_result import HitResult

# ── Estados ───────────────────────────────────────────────────────────────────
# FSM mínima desta etapa. As fases (CORO / CONTRAPONTO / UNÍSSONO) e a SENTENÇA
# entram nas etapas 4-7 do plano; o gate de fase já é lido aqui só para o boss
# não precisar de reescrita quando elas chegarem.
_ENTERING = "entering"
_ACTIVE = "active"

# ── Ciclo de ATAQUE da Fase 1 ("O Coro") ──────────────────────────────────────
# Uma cabeça de cada vez, sempre. É a fase que ensina o vocabulário, e ela só
# ensina se cada ataque puder ser observado isolado.
_ACT_BREATHER = "breather"  # respiro: todas cianas, nada acontece
_ACT_WINDUP = "windup"      # a cabeça da vez fica LARANJA — o telégrafo

# Wind-up CONSTANTE nas três fases (§7 do plano): o jogador calibra o tempo de
# reação uma vez e ele vale até o fim. Só a recuperação encurta com a fase.
_WINDUP_TIME = 0.5
_BREATHER_PHASE1 = 1.2
# Piso do respiro: nem a agressividade máxima pode colar dois ataques.
_BREATHER_FLOOR = 0.45

# Ataques da Fase 1.
_ATK_CADENCIA = "cadencia"   # leque de 3 teleguiadas fracas (lateral)
_ATK_CHUVA = "chuva"         # arco para cima, queda irregular (lateral)
_ATK_PULSO = "pulso"         # anel radial com UMA brecha (Coroa)

_CADENCIA_COUNT = 3
_CADENCIA_SPREAD = 0.34      # rad entre as pontas do leque
_CHUVA_COUNT = 4
_PULSO_SLOTS = 16            # direções do anel
_PULSO_GAP = 3               # slots consecutivos vazios = a brecha

_CROWN_ACTOR = -1            # "quem age" quando é a cabeça principal
_MAX_LIVE_ORBS = 40          # trava de segurança do teto de esferas

# ── Cadência de flutuação ─────────────────────────────────────────────────────
_DRIFT_SPEED = 0.35  # rad/s da deriva lateral
_DRIFT_AMPLITUDE = 0.16  # fração da largura da tela
_BOB_SPEED = 1.1  # rad/s do sobe-e-desce
_BOB_AMPLITUDE = 10.0  # px
_ENTER_SPEED = 2.0  # fator de lerp da descida de entrada


class TriadBoss(BossHitMixin):
    BOSS_TYPE_NAME: str = "energy_triad"

    DEFAULT_HEALTH: int = 1400
    # HP de cada Voz como fração do HP da Coroa. ~16% cada: caro o bastante para
    # a decisão de suprimir a brasa ter peso, barato o bastante para o ciclo não
    # virar uma segunda luta antes da luta.
    SIDE_HP_FRACTION: float = 0.16

    # Gates de fase (fração do HP da Coroa) — lidos, mas ainda sem efeito.
    PHASE2_THRESHOLD: float = 0.66
    PHASE3_THRESHOLD: float = 0.33

    _MISS_TIME: float = 0.75
    _HIT_FLASH_TIME: float = 0.08

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        difficulty_multiplier: float = 1.0,
        aggressiveness_multiplier: float = 1.0,
        event_bus: EventBus | None = None,
    ) -> None:
        self.w: float = float(pmap.CONTENT_W * pmap.PIXEL_SCALE)
        self.h: float = float(pmap.CONTENT_H * pmap.PIXEL_SCALE)

        self._home_x: float = Config.SCREEN_WIDTH / 2.0 - self.w / 2.0
        self._home_y: float = Config.SCREEN_HEIGHT * 0.13
        self.x: float = x if x is not None else self._home_x
        self.y: float = y if y is not None else -self.h - 40.0

        self.difficulty_multiplier = difficulty_multiplier
        self.aggressiveness_multiplier = aggressiveness_multiplier
        self._bus = event_bus

        self.max_health: int = int(self.DEFAULT_HEALTH * difficulty_multiplier)
        self.health: int = self.max_health
        self.dead: bool = False
        self.active: bool = False

        self._state: str = _ENTERING
        self._time: float = 0.0
        self._hit_flash: float = 0.0
        self._miss_timer: float = 0.0
        self._miss_pos: tuple[float, float] = (0.0, 0.0)

        # Sprite da Coroa (cabeça principal + tronco + halo — uma peça só na arte).
        self._crown = pmap.load_part("crown")
        self._crown_attacking: bool = False
        # Um índice de frame para as três partes: elas são uma criatura só.
        self._frame_index: int = 0
        self._mask_cache: dict[tuple, pygame.mask.Mask] = {}

        side_hp = max(1, int(self.max_health * self.SIDE_HP_FRACTION))
        # A âncora de cada Voz é DERIVADA do sprite (`part_anchor`), não digitada:
        # a cabeça lateral é um gancho e qualquer ponto "óbvio" — centro do bbox,
        # centroide da silhueta, centroide do blob — cai no vazio de dentro dele.
        self.heads: List[TriadHead] = [
            TriadHead(LEFT, "left", side_hp, pmap.part_anchor("left"), pmap.SIDE_HEAD_RADIUS),
            TriadHead(RIGHT, "right", side_hp, pmap.part_anchor("right"), pmap.SIDE_HEAD_RADIUS),
        ]

        # Pace inverso à dificuldade, como no Archmage: Casual espera mais pela
        # regeneração (janela mais generosa), Pesadelo menos. A JANELA MÍNIMA
        # fica fora dessa escala de propósito — é piso de justiça, não de
        # dificuldade, e encurtá-la reintroduz o modo impossível.
        pace = 1.0 / max(0.5, difficulty_multiplier)
        self.gate = ResonanceGate(regen_delay=6.0 * pace)

        self._ui_scale: float = Config.SCREEN_WIDTH / 1280.0

        # ── Ciclo de ataque (Fase 1) ──────────────────────────────────
        self._act_state: str = _ACT_BREATHER
        self._act_timer: float = _BREATHER_PHASE1
        self._actor: int = _CROWN_ACTOR
        self._attack: str = _ATK_PULSO
        self._last_actor: int | None = None
        self._last_side_attack: str = _ATK_CHUVA
        # Esferas que ESTE boss soltou e ainda vivem. Serve ao teto de
        # segurança agora e à Convergência da Fase 3 depois (ela recolhe as
        # esferas soltas da arena). Lista com teto, então rebuild por
        # compreensão é aceitável aqui (§6).
        self._orbs: List[TriadOrb] = []
        # Agressividade encurta o RESPIRO, nunca o wind-up: o telégrafo é
        # contrato com o jogador, não botão de dificuldade.
        self._breather: float = max(
            _BREATHER_FLOOR, _BREATHER_PHASE1 / max(0.5, aggressiveness_multiplier)
        )

    # ── Geometria ────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    def _crown_circle(self) -> tuple[float, float, float]:
        cx, cy = pmap.CROWN_HEAD_CENTER
        return self.x + cx, self.y + cy, pmap.CROWN_HEAD_RADIUS

    def collision_circle(self) -> tuple[float, float, float]:
        """Círculo do alvo VÁLIDO do momento — não o do corpo inteiro.

        Quem consome isto é mira automática/teleguiado (`systems.targeting`) e
        dano em área (`_aoe_into_boss`, que aplica o hit NO CENTRO deste
        círculo). Devolver o centro geométrico do corpo faria os dois mirarem
        uma região intangível durante a Fase 1 — o teleguiado gastaria carga em
        nada e o AoE bateria sempre num MISS.

        Com o portão fechado devolve a primeira lateral atacável em ordem de
        slot (escolha ESTÁVEL de propósito: mirar sempre "a de menos vida"
        faria o alvo pular entre as duas a cada hit).
        """
        if self.gate.crown_vulnerable:
            return self._crown_circle()
        for head in self.heads:
            if head.damageable:
                return head.collision_circle()
        return self._crown_circle()

    def collision_circles(self) -> List[tuple[float, float, float]]:
        """Silhueta real (§8): uma hitbox por cabeça que pode ser atingida.

        A Coroa entra na lista MESMO intangível — é o que permite o tiro parar
        nela e o "MISS" aparecer, em vez de o projétil atravessar em silêncio e
        o jogador não descobrir por que não fez dano.
        """
        circles: List[tuple[float, float, float]] = [self._crown_circle()]
        for head in self.heads:
            if head.damageable:
                circles.append(head.collision_circle())
        return circles

    def get_ship_contact_hitboxes(self) -> List[pygame.Rect]:
        """Rects por parte, para consumidores que pedem retângulo.

        Não é mais o caminho da colisão de tiro: com `get_collision_mask_data`
        presente, o `_rect_collides_with_enemy` resolve tudo por máscara e nem
        chega aqui.
        """
        cx, cy, r = self._crown_circle()
        ir = int(r)
        rects = [pygame.Rect(int(cx - ir), int(cy - ir), ir * 2, ir * 2)]
        for head in self.heads:
            if head.damageable:
                rects.append(head.contact_rect())
        return rects

    # ── Área de dano por PIXEL ───────────────────────────────────────────────
    def _blit_origin(self) -> tuple[int, int]:
        return (int(self.x) + pmap.BLIT_OFFSET_X, int(self.y) + pmap.BLIT_OFFSET_Y)

    def _mask_key(self) -> tuple:
        """Identidade do conjunto de máscaras em cena, para o cache.

        Espaço de chaves minúsculo (frames × cabeças presentes × flags de
        ataque), então o cache satura em poucos segundos de luta e nunca mais
        recombina — daí não precisar de despejo.
        """
        return (
            self._frame_index,
            self._crown_attacking,
            *[
                (h.damageable, h.attacking, h.body_state)
                for h in self.heads
            ],
        )

    def _combined_mask(self) -> pygame.mask.Mask | None:
        """União das máscaras das partes em cena — a área de dano do boss.

        A Coroa entra MESMO intangível: é o que faz o tiro parar nela e o "MISS"
        aparecer em vez de o projétil atravessar em silêncio. Cabeça no DOWN não
        entra, então o soquete vazio é atravessável.
        """
        key = self._mask_key()
        cached = self._mask_cache.get(key)
        if cached is not None:
            return cached

        crown_mask = self._crown.mask(self._frame_index, self._crown_attacking)
        if crown_mask is None:
            return None
        combined = crown_mask.copy()
        for head in self.heads:
            head_mask = head.current_mask()
            if head_mask is not None:
                # Todas as partes vivem na MESMA tela de 64×64 escalada, então a
                # união é offset (0, 0) — nenhum alinhamento a calcular.
                combined.draw(head_mask, (0, 0))

        self._mask_cache[key] = combined
        return combined

    def get_collision_mask_data(self) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        """Contrato de colisão por pixel (`collision_physics.get_enemy_collision_mask_data`).

        Devolver isto faz o `_rect_collides_with_enemy` usar a silhueta REAL do
        PNG e ignorar rect/círculos: o tiro só acerta onde há pixel desenhado.
        Vale para projéteis do jogador e para o contato da nave.
        """
        mask = self._combined_mask()
        if mask is None:
            return None
        return mask, self._blit_origin()

    def _part_at(self, px: float, py: float) -> "TriadHead | TriadBoss | None":
        """Qual parte tem PIXEL desenhado no ponto do impacto.

        As laterais são testadas primeiro: elas e o tronco se sobrepõem em 2
        pixels na arte, e nesse empate a Voz deve ganhar (é o alvo obrigatório).
        Devolve None quando o ponto não cai em pixel nenhum — caso do dano em
        área, que aplica o hit no centro de um círculo e não numa silhueta.
        """
        ox, oy = self._blit_origin()
        lx, ly = int(px - ox), int(py - oy)
        size = pmap.FRAME * pmap.PIXEL_SCALE
        if not (0 <= lx < size and 0 <= ly < size):
            return None

        for head in self.heads:
            head_mask = head.current_mask()
            if head_mask is not None and head_mask.get_at((lx, ly)):
                return head
        crown_mask = self._crown.mask(self._frame_index, self._crown_attacking)
        if crown_mask is not None and crown_mask.get_at((lx, ly)):
            return self
        return None

    # ── Dano ─────────────────────────────────────────────────────────────────
    def can_take_damage(self) -> bool:
        """Alguma parte pode receber dano agora?

        Falso na entrada e na morte. Na Sentença (etapa 5) o boss inteiro fica
        intangível e este é o ponto que vai reportar isso.
        """
        return self.active and not self.dead

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ....systems.hit_result import NO_HIT

        if not self.can_take_damage() or damage <= 0:
            return NO_HIT

        # Roteamento por PIXEL: quem levou o tiro é a parte que tem conteúdo
        # desenhado no ponto de impacto. O fallback por proximidade cobre o dano
        # em área, que não tem ponto de impacto real — ele aplica o hit no centro
        # do `collision_circle`, que pode cair num pixel vazio.
        target = self._part_at(hit_x, hit_y)
        if target is None:
            target = self._fallback_target(hit_x, hit_y)
        if target is None:
            return NO_HIT

        if target is self:
            if not self.gate.crown_vulnerable:
                self._trigger_miss(hit_x, hit_y)
                return NO_HIT
            return self._damage_crown(damage)
        return self._damage_head(target, damage)

    def _fallback_target(self, px: float, py: float) -> "TriadHead | TriadBoss | None":
        """Quem responde quando o impacto não caiu sobre parte nenhuma.

        DENTRO do corpo → é a Coroa. O tronco é desenho de LINHA e quase todo
        oco: o projétil encosta num traço (a colisão vale, é a máscara que manda)
        mas o centro dele cai num vão. Sem esta regra o tiro caía no "parte
        atacável mais próxima" e era creditado a uma Voz — tiro na base do torso,
        em y 52, virava dano numa cabeça que termina em y 37. Era o sintoma
        relatado em playtest, e o mais difícil de ver: só acontece nos VÃOS.

        A comparação é entre DISTÂNCIAS A SUPERFÍCIES, não a pontos:

          * o corpo é o `rect` inteiro — distância 0 em qualquer lugar dentro
            dele, e a distância à borda fora dele;
          * cada Voz é o CÍRCULO dela — distância ao centro menos o raio.

        Medir a Coroa por um ponto (o centro da cabeça dela) era o furo: um tiro
        na ponta de baixo do losango fica a ~35px do centro da Coroa e a ~24px do
        centro de uma Voz, então a Voz "ganhava" um impacto que aconteceu no
        torso. Pior, o jogador atira DE BAIXO: quando a ponta do projétil toca a
        base do corpo, o centro dele ainda está um pixel ABAIXO do rect — ou
        seja, o ponto mais atingido da luta inteira caía sempre fora e era
        creditado a uma cabeça.
        """
        r = self.rect
        dx = max(r.left - px, 0.0, px - r.right)
        dy = max(r.top - py, 0.0, py - r.bottom)
        dist_body = math.hypot(dx, dy)
        if dist_body <= 0.0:
            # DENTRO do corpo e sem parte sob o ponto: é vão do traço, e vão de
            # traço é da Coroa, sem disputa. Deixar as Vozes competirem aqui
            # devolveria o bug por outra porta — o círculo de uma Voz cobre o
            # oco entre o rosto e o filamento, que é território do corpo.
            return self

        best: "TriadHead | None" = None
        best_d = float("inf")
        for head in self.heads:
            if not head.damageable:
                continue
            d = math.hypot(px - head.center_x, py - head.center_y) - head.radius
            if d < best_d:
                best, best_d = head, d

        if best is not None and best_d < dist_body:
            return best
        return self

    def _nearest_damageable(self, px: float, py: float) -> "TriadHead | TriadBoss | None":
        """Parte atacável de centro mais próximo do impacto.

        Os círculos das cabeças NÃO se sobrepõem (ver `triad_pixel_map`), então
        um ponto dentro de um deles é necessariamente o mais próximo daquele
        centro — não há zona ambígua para um tiro. O caso de impacto fora de
        todos é o dano em área, que aplica no centro do `collision_circle` e
        cai naturalmente na parte certa.
        """
        best: "TriadHead | TriadBoss | None" = None
        best_d2 = float("inf")

        if self.gate.crown_vulnerable:
            cx, cy, _ = self._crown_circle()
            best, best_d2 = self, (px - cx) ** 2 + (py - cy) ** 2

        for head in self.heads:
            if not head.damageable:
                continue
            d2 = (px - head.center_x) ** 2 + (py - head.center_y) ** 2
            if d2 < best_d2:
                best, best_d2 = head, d2
        return best

    def _damage_crown(self, damage: int) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.health -= damage
        self._hit_flash = self._HIT_FLASH_TIME
        if self.health <= 0:
            self.health = 0
            self.dead = True
            return HitResult(
                killed=True,
                points=Config.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)

    def _damage_head(self, head: TriadHead, damage: int) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        was_ember = self.gate.is_rematerializing(head.slot)
        if not head.take_damage(damage):
            return HitResult(explosion_size=12, sound=hit_sounds.BOSS_DAMAGE)

        # A cabeça caiu. Qual das duas quedas foi é leitura do PORTÃO (a cabeça
        # só sabe que o HP acabou), e as duas têm feedback diferente: derrubar a
        # cabeça sólida é uma conquista; suprimir a brasa é manutenção.
        if was_ember:
            self.gate.head_remat_interrupted(head.slot)
            head.enter_down()
            return HitResult(explosion_size=25, sound=hit_sounds.BOSS_DAMAGE)

        self.gate.head_died(head.slot)
        head.enter_down()
        return HitResult(explosion_size=60, sound=hit_sounds.EXPLOSION_BOSS)

    def take_damage(self, amount: int) -> None:
        """Dano SEM posição (cadeias, alguns AoE). Cobra do portão primeiro.

        Sem posição não dá para rotear por proximidade, e mandar direto para a
        Coroa furaria o portão — a regra da luta é que ela só é ferida com as
        duas laterais fora. Então: enquanto houver lateral atacável, o dano vai
        para ela; só com o portão aberto ele chega ao núcleo.
        """
        if not self.can_take_damage() or amount <= 0:
            return
        for head in self.heads:
            if head.damageable:
                if head.take_damage(amount):
                    if self.gate.is_rematerializing(head.slot):
                        self.gate.head_remat_interrupted(head.slot)
                    else:
                        self.gate.head_died(head.slot)
                    head.enter_down()
                return
        if self.gate.crown_vulnerable:
            self.health = max(0, self.health - amount)
            self._hit_flash = self._HIT_FLASH_TIME
            if self.health <= 0:
                self.dead = True

    def _trigger_miss(self, hit_x: float, hit_y: float) -> None:
        self._miss_timer = self._MISS_TIME
        self._miss_pos = (hit_x, hit_y - 30.0)

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update_boss(self, dt: float, ctx: "BossUpdateContext") -> "BossUpdateResult":
        from ....systems.boss_context import BossUpdateResult

        py = ctx.player_y if ctx.player_y is not None else Config.SCREEN_HEIGHT * 0.8
        spawned = self.update(dt, (ctx.player_x, py))
        result = BossUpdateResult()
        if spawned:
            result.spawned_enemies = list(spawned)
        return result

    def update(
        self, dt: float, player_pos: tuple[float, float] | None = None
    ) -> List[TriadOrb]:
        if self.dead:
            return []

        self._time += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._miss_timer = max(0.0, self._miss_timer - dt)

        if self._state == _ENTERING:
            self._update_entering(dt)
        else:
            self._update_drift()

        self._update_gate(dt)

        self._frame_index = int(self._time * pmap.ANIM_FPS)
        for head in self.heads:
            head.update(
                dt,
                self.x,
                self.y,
                self.gate.remat_progress(head.slot),
                self._frame_index,
            )

        if self._state != _ACTIVE or player_pos is None:
            return []
        return self._update_attack_cycle(dt, player_pos)

    def _update_entering(self, dt: float) -> None:
        self.x += (self._home_x - self.x) * _ENTER_SPEED * dt
        self.y += (self._home_y - self.y) * _ENTER_SPEED * dt
        if abs(self.y - self._home_y) < 4.0:
            self.y = self._home_y
            self._state = _ACTIVE
            self.active = True
            # O relógio da deriva parte do zero na ativação para o boss não
            # entrar já no meio de uma oscilação (um salto lateral visível).
            self._time = 0.0

    def _update_drift(self) -> None:
        span = Config.SCREEN_WIDTH * _DRIFT_AMPLITUDE
        self.x = self._home_x + math.sin(self._time * _DRIFT_SPEED) * span
        self.y = self._home_y + math.sin(self._time * _BOB_SPEED) * _BOB_AMPLITUDE

    def _update_gate(self, dt: float) -> None:
        """Avança o portão e faz o corpo das cabeças seguir o estado dele."""
        for event in self.gate.update(dt):
            if event is ResonanceEvent.WINDOW_OPENED:
                self._emit_shake(0.25, 4)

        # Sincronização declarativa: o portão é a fonte de verdade e a cabeça
        # apenas alcança o estado dele. Escrito como comparação de estado (e não
        # como reação aos eventos) porque a transição REMAT→SOLID **não emite
        # evento** — ela acontece dentro do `gate.update` quando a brasa
        # completa. Um sync guiado só por eventos deixaria a cabeça em brasa
        # para sempre, atacável e translúcida, com o portão já fechado.
        for head in self.heads:
            target = self.gate.state(head.slot)
            if head.body_state is target:
                continue
            if target is HeadState.SOLID:
                head.restore(self.gate.return_hp_fraction(head.slot))
            elif target is HeadState.REMAT:
                head.enter_remat()
            else:
                head.enter_down()

    # ── Ciclo de ataque — Fase 1, "O Coro" ───────────────────────────────────
    def _update_attack_cycle(
        self, dt: float, player_pos: tuple[float, float]
    ) -> List[TriadOrb]:
        """Respiro → wind-up (laranja) → disparo → respiro. Uma cabeça por vez.

        FSM com sentinela, não cadência periódica: cada estado tem duração
        própria e o próximo é escolhido no fim. O §14 lista esse caso como um
        dos que NÃO migram para `FireTimer`. A sobra do frame é carregada para o
        estado seguinte mesmo assim — descartá-la faria o ciclo render um número
        inteiro de frames em vez do tempo configurado.
        """
        self._act_timer -= dt
        if self._act_timer > 0.0:
            return []

        sobra = -self._act_timer  # quanto o timer passou de zero neste frame

        if self._act_state == _ACT_BREATHER:
            self._begin_windup()
            self._act_timer = _WINDUP_TIME - sobra
            return []

        # Fim do wind-up: a cabeça laranja cumpre o que prometeu.
        orbs = self._fire_current_attack(player_pos)
        self._clear_telegraph()
        self._act_state = _ACT_BREATHER
        self._act_timer = self._breather - sobra
        return orbs

    def _begin_windup(self) -> None:
        """Escolhe quem age e acende o LARANJA. Laranja nunca mente (§7)."""
        self._actor = self._pick_actor()
        self._attack = self._pick_attack(self._actor)
        self._act_state = _ACT_WINDUP
        if self._actor == _CROWN_ACTOR:
            self._crown_attacking = True
        else:
            self.heads[self._actor].attacking = True

    def _clear_telegraph(self) -> None:
        self._crown_attacking = False
        for head in self.heads:
            head.attacking = False

    def _pick_actor(self) -> int:
        """Round-robin entre quem PODE agir, sem repetir o ator anterior.

        Cabeça derrubada ou em brasa não ataca — ela não está lá. Com as duas
        fora, a Coroa fica sozinha em cena e age em todo turno, o que é a leitura
        certa: é o momento em que ela está exposta e pressionando sozinha.
        """
        candidatos = [h.slot for h in self.heads if self.gate.is_solid(h.slot)]
        candidatos.append(_CROWN_ACTOR)
        if len(candidatos) > 1 and self._last_actor in candidatos:
            candidatos.remove(self._last_actor)
        escolhido = candidatos[0] if len(candidatos) == 1 else random.choice(candidatos)
        self._last_actor = escolhido
        return escolhido

    def _pick_attack(self, actor: int) -> str:
        if actor == _CROWN_ACTOR:
            return _ATK_PULSO
        # As duas laterais alternam Cadência e Chuva: uma é pressão direta e a
        # outra é controle de área, então alternar mantém as duas na memória do
        # jogador em vez de deixar uma virar a "padrão".
        self._last_side_attack = (
            _ATK_CHUVA if self._last_side_attack == _ATK_CADENCIA else _ATK_CADENCIA
        )
        return self._last_side_attack

    # ── Emissões ─────────────────────────────────────────────────────────────
    def _fire_current_attack(self, player_pos: tuple[float, float]) -> List[TriadOrb]:
        self._prune_orbs()
        livres = _MAX_LIVE_ORBS - len(self._orbs)
        if livres <= 0:
            return []

        if self._attack == _ATK_PULSO:
            orbs = self._fire_pulso()
        elif self._attack == _ATK_CADENCIA:
            orbs = self._fire_cadencia(player_pos)
        else:
            orbs = self._fire_chuva()

        orbs = orbs[:livres]
        self._orbs.extend(orbs)
        return orbs

    def _prune_orbs(self) -> None:
        self._orbs = [o for o in self._orbs if not o.dead]

    def _actor_origin(self) -> tuple[float, float]:
        if self._actor == _CROWN_ACTOR:
            cx, cy = pmap.CORE_CENTER  # as esferas nascem do núcleo do peito
            return self.x + cx, self.y + cy
        head = self.heads[self._actor]
        return head.center_x, head.center_y

    def _fire_cadencia(self, player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Leque de 3 teleguiadas fracas. Pressão direta, dodge simples."""
        ox, oy = self._actor_origin()
        base = math.atan2(player_pos[1] - oy, player_pos[0] - ox)
        orbs: List[TriadOrb] = []
        for i in range(_CADENCIA_COUNT):
            desvio = (i - (_CADENCIA_COUNT - 1) / 2.0) * _CADENCIA_SPREAD
            orbs.append(
                TriadOrb(ox, oy, OrbBehavior.SEEKER, angle=base + desvio, color=self._palette())
            )
        return orbs

    def _fire_chuva(self) -> List[TriadOrb]:
        """Arco para cima e queda irregular — controle de área.

        A deriva aponta para o CENTRO da arena (não para o jogador): a Chuva nega
        espaço, não persegue. Perseguir seria a Cadência de novo, com outra
        aparência.
        """
        ox, oy = self._actor_origin()
        rumo = 1.0 if ox < Config.SCREEN_WIDTH / 2 else -1.0
        return [make_lob(ox, oy, rumo, self._palette()) for _ in range(_CHUVA_COUNT)]

    def _fire_pulso(self) -> List[TriadOrb]:
        """Anel radial com UMA brecha. Leitura puramente posicional.

        A brecha é sorteada dentro do hemisfério INFERIOR: o jogador está
        embaixo, e uma brecha no topo seria uma brecha que não existe para ele.
        """
        ox, oy = self._actor_origin()
        passo = math.tau / _PULSO_SLOTS
        # Slots cuja direção aponta para baixo (y cresce para baixo na tela).
        inferiores = [i for i in range(_PULSO_SLOTS) if math.sin(i * passo) > 0.25]
        inicio_brecha = random.choice(inferiores) if inferiores else 0
        brecha = {(inicio_brecha + k) % _PULSO_SLOTS for k in range(_PULSO_GAP)}
        cor = self._palette()
        return [
            TriadOrb(ox, oy, OrbBehavior.RING, angle=i * passo, color=cor)
            for i in range(_PULSO_SLOTS)
            if i not in brecha
        ]

    def _palette(self) -> tuple[int, int, int]:
        """Cor das esferas. Vira laranja quando o boss vira (Fase 3)."""
        return pmap.CYAN

    def _emit_shake(self, duration: float, intensity: int) -> None:
        if self._bus is None:
            return
        from ....events import game_events as events

        self._bus.emit(events.ScreenShake(intensity=intensity, duration=duration))

    # ── Render ───────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o boss. Sem efeito colateral (§3): só lê estado montado no update."""
        if self.dead:
            return

        origin = self._blit_origin()

        # ORDEM DE CAMADAS: tronco/Coroa primeiro (embaixo), depois as laterais.
        # Medido: as partes só se sobrepõem em 2 pixels, e as duas ordens
        # reproduzem o `Imagem_Boss_Completo_Exemplo.png` com ZERO divergência
        # visível — a arte foi desenhada para não depender de empilhamento. A
        # ordem fica fixa aqui mesmo assim, porque as fases seguintes deslocam as
        # cabeças (a Sentença manda as laterais para as bordas) e aí a
        # sobreposição passa a existir de verdade.
        white = self._hit_flash > 0.0
        crown_frame = self._crown.frame(
            self._frame_index, self._crown_attacking, white=white
        )
        if crown_frame is not None:
            surface.blit(crown_frame, origin)

        for head in self.heads:
            head.draw(surface, origin)

        self._draw_health_bar(surface)
        self._draw_miss_indicator(surface)

    def _s(self, value: float) -> int:
        return int(value * self._ui_scale)

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        """Barra da Coroa ladeada por um pip por Voz.

        Os pips são o tutorial da luta: eles esvaziam quando a lateral cai e
        VOLTAM A ENCHER durante a rematerialização. É assim que o jogador
        descobre sozinho que a brasa é atacável e que o portão está fechando —
        sem uma linha de texto.
        """
        if self._state == _ENTERING or self.health <= 0:
            return

        bar_w, bar_h = self._s(260), self._s(9)
        pip_w = self._s(14)
        pip_gap = self._s(6)
        total_w = bar_w + 2 * (pip_w + pip_gap)
        bx = int(Config.SCREEN_WIDTH / 2 - total_w / 2) + pip_w + pip_gap
        by = self._s(24)

        # Barra da Coroa. Acesa quando a janela está aberta, dessaturada quando
        # não — vulnerabilidade lida de relance, sem ler os pips.
        vulnerable = self.gate.crown_vulnerable
        hp_ratio = max(0.0, self.health / self.max_health)
        fill = pmap.CYAN if vulnerable else pmap.CYAN_DIM
        pygame.draw.rect(surface, pmap.CYAN_DARK, (bx, by, bar_w, bar_h))
        pygame.draw.rect(surface, fill, (bx, by, int(bar_w * hp_ratio), bar_h))
        border = pmap.CYAN if vulnerable else pmap.CYAN_DIM
        pygame.draw.rect(surface, border, (bx, by, bar_w, bar_h), 1)

        for slot, side in ((LEFT, -1), (RIGHT, 1)):
            px = bx - pip_w - pip_gap if side < 0 else bx + bar_w + pip_gap
            self._draw_pip(surface, px, by, pip_w, bar_h, slot)

    def _draw_pip(
        self, surface: pygame.Surface, px: int, py: int, w: int, h: int, slot: int
    ) -> None:
        head = self.heads[slot]
        pygame.draw.rect(surface, pmap.CYAN_DARK, (px, py, w, h))

        if self.gate.is_solid(slot):
            level, color = head.hp_ratio, pmap.CYAN
        elif self.gate.is_rematerializing(slot):
            # Enchendo: é o portão se fechando, e o aviso para suprimir a brasa.
            level, color = self.gate.remat_progress(slot), pmap.ORANGE
        else:
            level, color = 0.0, pmap.CYAN_DIM

        if level > 0.0:
            filled = max(1, int(h * level))
            pygame.draw.rect(surface, color, (px, py + h - filled, w, filled))
        pygame.draw.rect(surface, color, (px, py, w, h), 1)

    def _draw_miss_indicator(self, surface: pygame.Surface) -> None:
        if self._miss_timer <= 0.0:
            return
        alpha = int(255 * (self._miss_timer / self._MISS_TIME))
        font = get_font(max(8, self._s(18)))
        label = font.render("MISS", True, pmap.CYAN)
        label.set_alpha(alpha)
        surface.blit(label, label.get_rect(center=(int(self._miss_pos[0]), int(self._miss_pos[1]))))
