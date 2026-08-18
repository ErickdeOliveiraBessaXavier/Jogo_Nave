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
from typing import TYPE_CHECKING, List

import pygame

from ....core.assets import get_font
from ....core.config import config as Config
from ....core.events import EventBus
from ...bosses.boss_hit_mixin import BossHitMixin
from . import triad_pixel_map as pmap
from .triad_head import TriadHead
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

        side_hp = max(1, int(self.max_health * self.SIDE_HP_FRACTION))
        self.heads: List[TriadHead] = [
            TriadHead(LEFT, "left", side_hp, pmap.LEFT_HEAD_CENTER, pmap.SIDE_HEAD_RADIUS),
            TriadHead(RIGHT, "right", side_hp, pmap.RIGHT_HEAD_CENTER, pmap.SIDE_HEAD_RADIUS),
        ]

        # Pace inverso à dificuldade, como no Archmage: Casual espera mais pela
        # regeneração (janela mais generosa), Pesadelo menos. A JANELA MÍNIMA
        # fica fora dessa escala de propósito — é piso de justiça, não de
        # dificuldade, e encurtá-la reintroduz o modo impossível.
        pace = 1.0 / max(0.5, difficulty_multiplier)
        self.gate = ResonanceGate(regen_delay=6.0 * pace)

        self._ui_scale: float = Config.SCREEN_WIDTH / 1280.0

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
        """Rects para o pré-filtro AABB; a validação fina usa `collision_circles`."""
        cx, cy, r = self._crown_circle()
        ir = int(r)
        rects = [pygame.Rect(int(cx - ir), int(cy - ir), ir * 2, ir * 2)]
        for head in self.heads:
            if head.damageable:
                rects.append(head.contact_rect())
        return rects

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

        # 1) Tiro que entrou na Coroa com o portão fechado: MISS explícito.
        #    Testado ANTES do roteamento porque é uma resposta sobre o ponto de
        #    impacto, não sobre qual parte está mais perto.
        if not self.gate.crown_vulnerable and self._inside_crown(hit_x, hit_y):
            self._trigger_miss(hit_x, hit_y)
            return NO_HIT

        target = self._nearest_damageable(hit_x, hit_y)
        if target is None:
            return NO_HIT
        if target is self:
            return self._damage_crown(damage)
        return self._damage_head(target, damage)

    def _inside_crown(self, px: float, py: float) -> bool:
        cx, cy, r = self._crown_circle()
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r

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

        self.update(dt)
        # Ainda sem emissões: esta etapa é o esqueleto + o portão (etapas 1-2 do
        # plano). Os ataques entram nas etapas 3-7 e preenchem este resultado.
        return BossUpdateResult()

    def update(self, dt: float) -> None:
        if self.dead:
            return

        self._time += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._miss_timer = max(0.0, self._miss_timer - dt)

        if self._state == _ENTERING:
            self._update_entering(dt)
        else:
            self._update_drift()

        self._update_gate(dt)

        for head in self.heads:
            head.update(dt, self.x, self.y, self.gate.remat_progress(head.slot))

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

        origin = (
            int(self.x) + pmap.BLIT_OFFSET_X,
            int(self.y) + pmap.BLIT_OFFSET_Y,
        )

        # Coroa primeiro: as laterais se sobrepõem a ela na arte montada.
        white = self._hit_flash > 0.0
        index = int(self._time * 6.0)
        crown_frame = self._crown.frame(index, self._crown_attacking, white=white)
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
