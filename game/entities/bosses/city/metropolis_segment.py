"""Segmentos do Metropolis Overlord — Fase 3 (SEGMENTAÇÃO final).

Ao perder a estrutura, o Overlord NÃO morre: a mesma inteligência sobrevive em três
FRAGMENTOS VIVOS, cada um guardando um dos núcleos de plasma. Não são inimigos novos
— são o último estágio evolutivo do boss, herdando sua identidade visual (núcleo de
plasma + fluxos de energia + borda neon viva + estética tecno-alienígena) e atacando
de forma COORDENADA, como partes de uma única mente central.

Coordenação (`SegmentNetwork`): os três orbitam um ponto invisível em sincronia
(120° apart, raio respirando junto) e disparam em ONDA defasada (volley coordenada)
a cada ciclo, com breves momentos de REORGANIZAÇÃO em grupo (sem volley) — pressão
ritmada e legível, nunca caótica.

Ataques: reaproveitam a linguagem já construída (projéteis das sentinelas) em versões
MENORES/menos opressoras — pequenos drones/feixes (`EnergyDrone`) e triângulos
energéticos com leve perseguição (`TriShard`). Roteados via `ctx.new_enemies`.
`draw` sem efeitos colaterais (§3): mutação só no `update`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List

import pygame

from ....core.config import config as Config
from ...enemies._shared.enemy_hit_mixin import EnemyHitMixin
from . import metropolis_overlord_pixel_map as pmap
from .city_thruster import EnergyThruster
from .metropolis_projectiles import EnergyDrone, TriShard

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult

class SegmentNetwork:
    """Inteligência central RESIDUAL: coordena os 3 fragmentos como uma só mente.

    Um relógio compartilhado (avançado 1×/frame pelo boss-coordenador) ritma:
      • respiração de raio sincronizada (movimentos pequenos em grupo);
      • volley em ONDA a cada ciclo (cada fragmento dispara defasado por `STAGGER`,
        em ordem — ataques complementares lendo como um pulso único);
      • REORGANIZAÇÃO em grupo (sem volley) só enquanto os 3 vivem — breve respiro.

    ESCALADA: a mente CONCENTRA o poder conforme perde corpos. Quanto menos
    fragmentos vivos, menor o intervalo entre volleys e menos pausas — matar um
    torna os sobreviventes mais agressivos (tensão + curva de dificuldade). A
    contagem de vivos é informada pelo boss a cada frame (`update(dt, alive)`).

    Contrato explícito (§1): o segmento só lê `cycle/fire_phase/is_reorg/...`.
    """

    STAGGER = 0.18  # defasagem da onda entre fragmentos (s)
    # Intervalo entre volleys e frequência de reorganização POR nº de vivos.
    _CYCLE_BY_ALIVE = {3: 2.0, 2: 1.5, 1: 1.05}   # base apertada (era 2.6) + escalada
    _REORG_BY_ALIVE = {3: 6, 2: 0, 1: 0}          # 0 = sem pausa (implacável c/ poucos)
    # Janela inicial de REORGANIZAÇÃO: ao segmentar, os fragmentos se posicionam e
    # ESTABILIZAM antes do 1º ataque (leitura da nova fase). Os segmentos orbitam e
    # respiram normalmente — só o disparo é adiado.
    WARMUP = 1.3

    # RESPIRAÇÃO da formação (Fase 3): o centro de órbita NÃO se move; a única
    # movimentação é o raio PULSANDO (expande/contrai) com a velocidade de giro
    # ACOPLADA — gira rápido ao expandir, lento ao contrair. Máquina energética
    # respirando, sem deslocar pela arena. Tudo sincronizado (todos leem o mesmo).
    BREATH_FREQ = 1.4        # rad/s — ciclo lento e deliberado (~4.5s por respiração)
    BREATH_RADIUS_AMP = 0.35  # raio oscila 0.65×..1.35× do base (pulsação visível)
    BREATH_SPIN_AMP = 0.6     # giro oscila 0.4×..1.6× (rápido expandido, lento contraído)

    def __init__(self) -> None:
        self.clock = 0.0
        self.cycle = 0
        self._t = 0.0
        self.alive = 3
        self._warmup_t = self.WARMUP

    @property
    def cycle_dur(self) -> float:
        return self._CYCLE_BY_ALIVE.get(self.alive, 2.0)

    @property
    def ready(self) -> bool:
        """True quando a janela de reorganização passou e os ataques podem começar."""
        return self._warmup_t <= 0.0

    def update(self, dt: float, alive: int = 3) -> None:
        self.alive = max(1, alive)
        self.clock += dt  # relógio visual (respiração/órbita) corre desde já
        if self._warmup_t > 0.0:
            # Reorganização: segura o relógio de volley (sem ataques) até estabilizar.
            self._warmup_t = max(0.0, self._warmup_t - dt)
            return
        self._t += dt
        while self._t >= self.cycle_dur:  # while: cobre a queda brusca do ciclo na escalada
            self._t -= self.cycle_dur
            self.cycle += 1

    @property
    def is_reorg(self) -> bool:
        every = self._REORG_BY_ALIVE.get(self.alive, 0)
        return every > 0 and self.cycle > 0 and self.cycle % every == 0

    def fire_phase(self) -> float:
        return self._t

    def _breath(self) -> float:
        """Oscilador de respiração ∈[-1,1] (sincronizado): +1 = expandido, -1 = contraído."""
        return math.sin(self.clock * self.BREATH_FREQ)

    def radius_scale(self) -> float:
        """Raio de órbita PULSANDO (todos leem o mesmo valor) — a única movimentação."""
        return 1.0 + self.BREATH_RADIUS_AMP * self._breath()

    def spin_scale(self) -> float:
        """Velocidade de giro ACOPLADA ao raio: rápido ao expandir, lento ao contrair."""
        return 1.0 + self.BREATH_SPIN_AMP * self._breath()


class MetropolisSegment(EnemyHitMixin):
    """Fragmento vivo do Overlord (um núcleo de plasma), coordenado pela rede residual."""

    is_boss: bool = False
    POINTS = 400
    ORBIT_SPEED = 0.55  # rad/s ao redor do ponto invisível (suave/coordenado)
    _ORBIT_MULT = {3: 1.0, 2: 1.22, 1: 1.5}  # escalada: + ágil conforme perde corpos
    ENTRY_TIME = 0.6    # ease da posição de split até o anel de órbita
    COLLISION_RADIUS = 40.0
    _THRUSTER_Y = 32.0  # offset da base (de onde sai o propulsor)
    _MINI_SCALE = 3.7   # px por célula do pixel-map (mini-Overlord ~92px de largura)

    _explosion_size_killed = 60
    _explosion_size_hit = 12

    # Fallback (sem rede): intervalo de disparo por papel (s).
    _FIRE_INTERVAL = {"drone": 2.4, "shard": 2.2, "pulse": 2.8}

    def __init__(
        self,
        theme: str,
        role: str,
        center: tuple[float, float],
        base_angle: float,
        orbit_radius: float,
        start_pos: tuple[float, float],
        health: int,
        aggressiveness_multiplier: float = 1.0,
        index: int = 0,
        network: "SegmentNetwork | None" = None,
    ) -> None:
        self.theme = theme
        self.role = role
        self.center = center
        self.base_angle = base_angle
        self.orbit_radius = orbit_radius
        self._aggr = max(0.5, aggressiveness_multiplier)
        self._index = index
        self._net = network

        # Paleta do PRÓPRIO núcleo (dark, mid, bright) — toda a silhueta herda a cor
        # do plasma: o fragmento parece um pedaço vivo da mesma entidade.
        self._dark, self._mid, self._bright = pmap.PLASMA_THEMES.get(
            theme, pmap.PLASMA_THEMES["cyan"]
        )

        self.health = max(1, health)
        self.max_health = self.health
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self._phase = base_angle  # fase de plasma única por fragmento
        self._fire_flash = 0.0    # brilho ao disparar (feedback)

        # Thruster herdado do Overlord (proporção menor): o fragmento também é uma
        # entidade energética suspensa, com propulsão azul/ciano na base.
        self._thruster = EnergyThruster(scale=0.42)
        self._thruster_intensity = 0.0

        self._orbit_angle = base_angle
        self._entry_t = self.ENTRY_TIME
        self._start_x, self._start_y = start_pos
        self.x, self.y = start_pos

        self._last_cycle = -1  # último ciclo de volley em que ESTE fragmento atirou
        self._fire_timer = self._FIRE_INTERVAL.get(role, 2.4) / self._aggr
        self._rect = pygame.Rect(0, 0, int(self.COLLISION_RADIUS * 2), int(self.COLLISION_RADIUS * 2))
        self._sync_rect()

    # ── Geometria / colisão ───────────────────────────────────────────────
    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, self.COLLISION_RADIUS

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Update ────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0 or self.dead:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self._fire_flash > 0.0:
            self._fire_flash = max(0.0, self._fire_flash - dt)

        # Órbita SINCRONIZADA em torno de um centro FIXO: a única movimentação é o raio
        # RESPIRANDO (expande/contrai) com a velocidade de giro ACOPLADA — rápido ao
        # expandir, lento ao contrair. Velocidade também ESCALA com a perda de corpos.
        alive = self._net.alive if self._net is not None else 3
        spin = self.ORBIT_SPEED * self._ORBIT_MULT.get(alive, 1.0)
        if self._net is not None:
            spin *= self._net.spin_scale()
        self._orbit_angle += spin * dt
        rscale = self._net.radius_scale() if self._net is not None else 1.0
        radius = self.orbit_radius * rscale
        ox = self.center[0] + math.cos(self._orbit_angle) * radius
        oy = self.center[1] + math.sin(self._orbit_angle) * radius
        if self._entry_t > 0.0:
            self._entry_t = max(0.0, self._entry_t - dt)
            k = 1.0 - (self._entry_t / self.ENTRY_TIME)
            self.x = self._start_x + (ox - self._start_x) * k
            self.y = self._start_y + (oy - self._start_y) * k
        else:
            self.x, self.y = ox, oy
        self._sync_rect()

        self._update_fire(dt, ctx)

        # Thruster (escala menor): intensidade base baixa + pulso sutil + reforço ao
        # disparar. Emite da base do fragmento e acompanha sua órbita.
        inten = min(1.0, 0.26 + 0.12 * math.sin(self.anim_time * 5.0) + 0.4 * (self._fire_flash / 0.3))
        self._thruster_intensity = inten
        self._thruster.update(dt, self.x, self.y + self._THRUSTER_Y, inten)

    def _update_fire(self, dt: float, ctx: "EnemyUpdateContext") -> None:
        """Disparo COORDENADO em onda via rede (defasado por índice); fallback por
        timer independente quando não há rede (testes)."""
        net = self._net
        if net is not None:
            if (
                net.ready  # janela de reorganização inicial: sem ataques até estabilizar
                and not net.is_reorg
                and net.cycle != self._last_cycle
                and net.fire_phase() >= self._index * net.STAGGER
            ):
                self._last_cycle = net.cycle
                self._fire_flash = 0.3
                ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))
            return
        self._fire_timer -= dt
        if self._fire_timer <= 0.0:
            self._fire_timer = self._FIRE_INTERVAL.get(self.role, 2.4) / self._aggr
            self._fire_flash = 0.3
            ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))

    def _drone(self, ang: float) -> object:
        return EnergyDrone(self.x, self.y, self.x + math.cos(ang) * 100.0, self.y + math.sin(ang) * 100.0)

    def _fire_role(self, role: str, px: float, py: float) -> List[object]:
        """Padrão-base de UM papel (reaproveita a linguagem nova)."""
        base = math.atan2(py - self.y, px - self.x)
        if role == "drone":  # rajada: 2 feixes em leque apertado
            return [self._drone(base - 0.1), self._drone(base + 0.1)]
        if role == "shard":  # 2 triângulos com perseguição (alvos levemente abertos)
            return [TriShard(self.x, self.y, px - 28.0, py), TriShard(self.x, self.y, px + 28.0, py)]
        if role == "pulse":  # descarga: leque de 3 drones
            return [self._drone(base + s) for s in (-0.32, 0.0, 0.32)]
        return []

    def _fire(self, px: float, py: float) -> List[object]:
        """Volley do fragmento. ESCALA com a perda de corpos: o ÚLTIMO sobrevivente
        concentra o poder, somando o padrão de um papel caído (last stand)."""
        alive = self._net.alive if self._net is not None else 3
        shots = self._fire_role(self.role, px, py)
        if alive == 1:
            extra = "shard" if self.role != "shard" else "pulse"
            shots += self._fire_role(extra, px, py)
        return shots

    # ── Render (§3) ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        t = self.anim_time
        boost = self._fire_flash / 0.3  # 1→0 logo após disparar

        # Thruster ATRÁS do fragmento (anéis na base).
        self._thruster.draw(surface, self.x, self.y + self._THRUSTER_Y, self._thruster_intensity)

        # MINI-OVERLORD: a MESMA silhueta pixel-art do boss (placas energizadas +
        # bordas neon com corrente), escalada, com 1 núcleo central da cor do tema.
        # Respiração sutil de tamanho (vivo) + leve aumento ao disparar.
        scale = self._MINI_SCALE * (1.0 + 0.04 * math.sin(t * 3.0) + 0.05 * boost)
        pmap.draw_mini_overlord(
            surface, cx, cy, scale, self.theme, t,
            hit=self.hit_timer > 0.0, core_phase=self._phase,
        )

        # Barra de vida do fragmento (cor do tema), acima da silhueta.
        half_h = int(pmap.PIXEL_ROWS * scale * 0.5)
        bw = 72
        bx = cx - bw // 2
        by = max(2, min(Config.SCREEN_HEIGHT - 7, cy - half_h - 10))
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, 5))
        frac = max(0.0, self.health / self.max_health)
        pygame.draw.rect(surface, self._bright, (bx, by, int(bw * frac), 5))
