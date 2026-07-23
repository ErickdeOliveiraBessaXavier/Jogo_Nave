"""Sentinela Orbital do Metropolis Overlord (Fase 1 / interlúdio, tema CITY).

Quatro esferas de energia que percorrem o PERÍMETRO da tela. São os **geradores do
escudo** do Overlord: enquanto pelo menos uma vive, o contorno neon do boss
permanece energizado e o corpo é invulnerável. Destruir as quatro derruba o escudo
(descarga visual) e abre a fase seguinte — ver `MetropolisOverlordBoss`.

As quatro compartilham a mesma base visual (esfera de energia), mas cada uma é um
nó com PERSONALIDADE própria de uma rede de vigilância da Cidade Neon — cor, papel
e telegrafo distintos (leitura clara do perigo ANTES do disparo):
  "neon"    → PRESSÃO DIRETA: volley preciso de feixes curtos (telegrafo: mira reta com ticks rápidos).
  "missile" → DESCARGA ATMOSFÉRICA: para de mover, canaliza e ATRAI um raio massivo do
              topo (`LightningStrike`). A coluna translúcida que alarga É o telegrafo.
  "laser"   → RESTRIÇÃO DE MOVIMENTO: grade holográfica instável manipulando o terreno
              (telegrafo: grade materializando no alvo).
  "emp"     → CONTROLE DE ESPAÇO: zona de SOBRECARGA elétrica DENTRO da arena, desacoplada
              da orb (jogador travado + leve antecipação; telegrafo: link + retícula na zona).

Ataques por FSM legível (REPOUSO → PREPARAÇÃO → DISPARO → RECUPERAÇÃO), com
materialização ao nascer e destruição impactante (fragmentação/dissipação).

A patrulha NÃO é mais uniforme: cada sentinela percorre o perímetro em PERNAS
(8 paradas de varredura) com easing — acelera e desacelera gradualmente (smoothstep),
faz uma pausa de scanner em cada parada e segue. Movimento deliberado de sistema
automatizado de vigilância, não nervoso. O ritmo varia sutilmente por papel
(`_ROLE_PATROL`). `draw` puro (§3): mutação só no `update`; o boss lê `s.dead`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ....core.config import config as Config
from ....core.scale import gameplay_scale, scaled
from ....core.visual_quality import visual_quality as vq
from .._shared.enemy_hit_mixin import EnemyHitMixin
from .metropolis_projectiles import (
    ElectricPulse,
    EnergyDrone,
    GridSnare,
    LightningStrike,
)

if TYPE_CHECKING:
    from ....core.events import EventBus
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult

_NEON_WHITE = (255, 255, 255)

# Raio base da esfera e inset base do trajeto (em pixels de 720p). O valor
# real de cada instância é computado em __init__ escalado pela resolução (§12).
_BASE_RADIUS = 26.0   # ligeiramente maior que o original 22px
_BASE_INSET_EXTRA = 8  # margem adicional além do halo_r

# Estados da FSM de combate (legibilidade).
_S_IDLE = "idle"
_S_AIM = "aim"
_S_FIRE = "fire"
_S_RECOVER = "recover"


def _smoothstep(p: float) -> float:
    """Easing suave 0→1 com derivada nula nas pontas (acel/desacel graduais)."""
    p = max(0.0, min(1.0, p))
    return p * p * (3.0 - 2.0 * p)


def _lerp(a: tuple, b: tuple, f: float) -> tuple:
    """Interpola duas cores RGB (f∈[0,1]). Para transições de render puro (§3)."""
    return (
        int(a[0] + (b[0] - a[0]) * f),
        int(a[1] + (b[1] - a[1]) * f),
        int(a[2] + (b[2] - a[2]) * f),
    )


def _jagged(x1: float, y1: float, x2: float, y2: float, jitter: float, segs: int = 4):
    """Polilinha em ziguezague entre dois pontos (raio elétrico). Para `draw` (§3)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    pts = [(x1, y1)]
    for i in range(1, segs):
        t = i / segs
        off = random.uniform(-jitter, jitter)
        pts.append((x1 + dx * t + nx * off, y1 + dy * t + ny * off))
    pts.append((x2, y2))
    return pts


class SentinelNetwork:
    """Inteligência central das 4 sentinelas: COORDENA os ataques no tempo.

    Sem isto cada sentinela agiria sozinha e várias habilidades estourariam juntas
    (caos/poluição, leitura ruim). Aqui elas REVEZAM: no máximo `MAX_CONCURRENT`
    ataques especiais ativos ao mesmo tempo, com intervalo mínimo `MIN_SPACING`
    entre ativações. Quem é negado espera e re-tenta (fila) — pressão constante e
    legível, não simultaneidade.

    Contrato explícito (§1): a sentinela só chama `can_fire`/`acquire`/`release`
    com o PRÓPRIO id; não lê estado das irmãs. O boss cria a rede, repassa às
    sentinelas no spawn e a atualiza UMA vez por frame.
    """

    MAX_CONCURRENT = 2   # teto TOTAL de ameaças ativas na arena ao mesmo tempo
    MAX_HEAVY = 1        # só UM ataque ESPECIAL (zona/grade/raio) ativo por vez
    MIN_SPACING = 1.0    # intervalo mínimo entre ativações (janela de respiro)

    def __init__(self) -> None:
        # id da sentinela -> [tempo restante do slot, é_pesado].
        self._active: dict[int, list] = {}
        self._since_last = self.MIN_SPACING  # libera a 1ª ativação sem atraso

    def update(self, dt: float) -> None:
        self._since_last += dt
        for sid in list(self._active.keys()):
            self._active[sid][0] -= dt
            if self._active[sid][0] <= 0.0:
                del self._active[sid]

    def _heavy_count(self) -> int:
        return sum(1 for slot in self._active.values() if slot[1])

    def can_fire(self, sid: int, heavy: bool) -> bool:
        if sid in self._active:
            return False  # uma sentinela só mantém UM ataque ativo por vez
        if self._since_last < self.MIN_SPACING:
            return False  # respeita a janela de respiro entre ativações
        if len(self._active) >= self.MAX_CONCURRENT:
            return False  # teto total de ameaças simultâneas
        if heavy and self._heavy_count() >= self.MAX_HEAVY:
            return False  # nunca dois ataques especiais ao mesmo tempo
        return True

    def acquire(self, sid: int, hold: float, heavy: bool) -> None:
        self._active[sid] = [hold, heavy]
        self._since_last = 0.0

    def release(self, sid: int) -> None:
        self._active.pop(sid, None)


class MetropolisSentinel(EnemyHitMixin):
    """Esfera de energia que patrulha o perímetro da tela e ataca (geradora do escudo)."""

    is_boss: bool = False
    RADIUS = 22.0
    HEALTH = 100
    POINTS = 250

    # Patrulha deliberada (vigilância): perímetro em PERNAS entre paradas de
    # varredura, com easing (acel/desacel). Bem mais lenta que a antiga uniforme.
    PATROL_STOPS = 8          # 4 cantos + 4 meios de borda
    LEG_TIME: float = 1.7     # duração base de uma perna (smoothstep)
    DWELL_TIME: float = 0.85  # pausa de scanner em cada parada

    BIRTH_TIME: float = 0.6
    DEATH_BURST: float = 0.5
    FIRE_TIME: float = 0.14
    RECOVER_TIME: float = 0.5

    # Cadência por papel: REPOUSO (entre ataques) e PREPARAÇÃO (telegrafo). REPOUSO/
    # RECUPERAÇÃO escalam c/ aggr; o TELEGRAFO é fixo (sempre legível).
    # Intervalos AMPLOS entre ataques (menos pressão, mais respiro). A coordenação
    # da rede ainda serializa os especiais — a dificuldade vem do timing, não do volume.
    _ROLE_IDLE = {"neon": 1.3, "missile": 2.4, "laser": 2.5, "emp": 2.3}
    _ROLE_AIM = {"neon": 0.5, "missile": 1.1, "laser": 0.9, "emp": 0.85}

    # Personalidade de patrulha: escala de tempo das pernas/pausas. <1 mais ágil
    # (rajada), >1 mais lenta e deliberada (suporte). Sutil — todas continuam calmas.
    _ROLE_PATROL = {"neon": 0.85, "missile": 1.0, "laser": 1.25, "emp": 1.1}

    # Tempo que o ataque ocupa um "slot" da rede (≈ presença/atenção da ameaça na
    # tela). Usado pela `SentinelNetwork` p/ limitar ameaças simultâneas — papéis de
    # ameaça persistente (zona, grade) seguram o slot por mais tempo.
    _ROLE_HOLD = {"neon": 0.9, "missile": 1.8, "laser": 1.6, "emp": 1.9}

    # Ataques ESPECIAIS (pesados): ameaças de área/persistentes. Só UM ativo por vez
    # na rede (`MAX_HEAVY`). A pressão direta (neon) é leve e pode preencher os vãos.
    _HEAVY_ROLES = frozenset({"missile", "laser", "emp"})

    # Paleta por papel (dark, mid, bright) — identidade de cor mantida, render rico.
    _ROLE_PALETTE = {
        "neon":    ((90, 20, 70),   (255, 70, 200),  (255, 175, 235)),
        "missile": ((90, 55, 10),   (255, 190, 80),  (255, 225, 170)),
        "laser":   ((20, 70, 95),   (90, 200, 255),  (190, 240, 255)),
        "emp":     ((70, 45, 110),  (180, 120, 255), (225, 205, 255)),
    }

    _explosion_size_killed = 0  # explosão é própria (energética), não a genérica
    _explosion_size_hit = 0

    def __init__(
        self,
        role: str,
        start_t: float = 0.0,
        aggressiveness_multiplier: float = 1.0,
        activation_delay: float = 0.0,
        network: "SentinelNetwork | None" = None,
        event_bus: "EventBus | None" = None,
        health_multiplier: float = 1.0,
    ) -> None:
        self.role = role
        self._t = start_t % 1.0
        self._aggr = max(0.5, aggressiveness_multiplier)
        self._net = network  # inteligência central (revezamento de ataques)
        self._bus = event_bus  # repassado ao raio p/ shake ao atingir o jogador
        # HP escalado (preset × coop por nº de players); barra usa `max_health`.
        self.max_health = max(self.HEALTH, int(self.HEALTH * max(1.0, health_multiplier)))
        self.health = self.max_health
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0

        self._dark, self._mid, self._bright = self._ROLE_PALETTE.get(
            role, self._ROLE_PALETTE["laser"]
        )

        # Tamanho e trajetória responsivos à resolução (§12): esfera e inset
        # escalam com ui_scale; halo garante que o glow nunca seja cortado pela borda.
        _ui_scale = gameplay_scale()  # FONTE ÚNICA da escala por resolução (§12)
        self.RADIUS = float(max(22.0, round(_BASE_RADIUS * _ui_scale)))
        _halo_extra = max(14, round(18 * _ui_scale))
        self._halo_r = int(self.RADIUS + _halo_extra)
        # Inset mínimo = halo_r + margem → glow nunca clipa na borda da tela.
        self._edge_inset = float(max(float(self._halo_r + _BASE_INSET_EXTRA),
                                     round(self.RADIUS * 2.0)))

        # Halo pré-renderado UMA vez (reuso por frame via set_alpha — §7).
        self._halo_surf = pygame.Surface((self._halo_r * 2, self._halo_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(self._halo_surf, (*self._mid, 255), (self._halo_r, self._halo_r), self._halo_r)

        # Rotação própria (visual) do anel/filamentos — lenta/controlada (vigilância).
        self._spin = random.uniform(0.0, 2.0 * math.pi)
        self._spin_speed = random.choice((-1.0, 1.0)) * random.uniform(1.0, 1.7)

        # Nascimento e morte.
        self._birth = True
        self._birth_t = self.BIRTH_TIME
        self._dying = False
        self._death_t = 0.0
        self._frags: List[list] = []

        # FSM de combate: começa em REPOUSO; `activation_delay` adia o 1º ataque
        # (escalona as 4 sentinelas). `_charge` (0→1) é o progresso do telegrafo.
        self._state = _S_IDLE
        self._state_t = self._idle_dur() + max(0.0, activation_delay)
        self._charge = 0.0
        self._aim_dur = self._ROLE_AIM.get(role, 0.8)
        self._flash = 0.0

        # Canalização (papel descarga atmosférica): congela a patrulha enquanto o
        # raio inteiro acontece (carga → impacto → dissipação) antes de voltar a mover.
        self._channeling = False
        self._channel_t = 0.0

        # Velocidade suavizada do jogador (p/ a leve antecipação de trajetória do emp).
        self._ppx: float | None = None
        self._ppy: float | None = None
        self._pvx = 0.0
        self._pvy = 0.0

        # Patrulha por pernas com easing: estado da perna atual + varredura na pausa.
        self._pace = self._ROLE_PATROL.get(role, 1.0)
        self._leg_from = self._t
        self._leg_to = self._next_stop_t(self._t)
        self._leg_prog = 0.0
        self._patrol_phase = "move"  # move | hold (varredura)
        self._patrol_t = 0.0
        self._scan = 0.0
        self._scan_dir = 1.0

        self.x, self.y = self._calculate_pos(self._t)
        self._aim_x, self._aim_y = self.x, self.y  # alvo travado no início da preparação

        self._rect = pygame.Rect(0, 0, int(self.RADIUS * 2), int(self.RADIUS * 2))
        self._sync_rect()

    # ── Geometria / colisão ────────────────────────────────────────────────
    def _calculate_pos(self, t: float) -> tuple[float, float]:
        """(x, y) ao longo do PERÍMETRO da arena, parametrizado por comprimento de arco
        (velocidade uniforme; topo → direita → base → esquerda em loop)."""
        w, h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        left, right = self._edge_inset, w - self._edge_inset
        top, bottom = self._edge_inset, h - self._edge_inset
        seg_w = right - left
        seg_h = bottom - top
        perim = 2.0 * (seg_w + seg_h)
        d = (t % 1.0) * perim

        if d <= seg_w:  # topo: TL → TR
            return left + d, top
        d -= seg_w
        if d <= seg_h:  # direita: TR → BR
            return right, top + d
        d -= seg_h
        if d <= seg_w:  # base: BR → BL
            return right - d, bottom
        d -= seg_w
        return left, bottom - d  # esquerda: BL → TL

    def _next_stop_t(self, t: float) -> float:
        """Menor parada de varredura (k/STOPS) estritamente à frente de `t`
        (valor contínuo, pode passar de 1; `_calculate_pos` faz o módulo)."""
        step = 1.0 / self.PATROL_STOPS
        nxt = (math.floor(t / step) + 1) * step
        if nxt - t < 1e-4:  # praticamente sobre a parada → vai para a próxima
            nxt += step
        return nxt

    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return not self._birth and not self._dying and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        if self._birth or self._dying or self.dead:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.RADIUS

    def take_damage(self, amount: int) -> None:
        if self._birth or self._dying or self.dead:
            return
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._start_death()

    def _start_death(self) -> None:
        if not self._dying:
            self._dying = True
            self._death_t = self.DEATH_BURST
            if self._net is not None:
                self._net.release(id(self))  # libera o slot ao morrer (não bloqueia a fila)
            self._spawn_death_fragments()

    def _spawn_death_fragments(self) -> None:
        self._frags = []
        for _ in range(vq.particles(9)):
            ang = random.uniform(0.0, 2.0 * math.pi)
            spd = random.uniform(90.0, 300.0)
            self._frags.append([
                self.x, self.y,                            # 0,1 pos
                math.cos(ang) * spd, math.sin(ang) * spd,  # 2,3 vel
                random.uniform(2.5, 6.0),                  # 4 tamanho
                random.random() < 0.4,                     # 5 hot
            ])

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hx: float, _hy: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        if self._birth or self._dying or self.dead:
            return HitResult()
        self.take_damage(damage)
        if self._dying:  # morreu neste hit
            return HitResult(killed=True, points=self.POINTS, sound=hit_sounds.EXPLOSION_ALIEN)
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    def _emit_sound(self, name: str) -> None:
        """Emite um pedido de SFX pelo EventBus (no-op sem bus, ex.: testes). §2."""
        if self._bus is not None:
            from ....events import game_events as events
            self._bus.emit(events.PlaySound(sound_name=name))

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self._flash > 0.0:
            self._flash = max(0.0, self._flash - dt)
        self._spin += self._spin_speed * dt

        # Estimativa suave da velocidade do jogador (EMA) — usada só pela leve
        # antecipação do emp, mas atualizada sempre p/ estar fresca na hora de travar.
        if self._ppx is not None and self._ppy is not None:
            self._pvx += ((ctx.player_x - self._ppx) / dt - self._pvx) * 0.2
            self._pvy += ((ctx.player_y - self._ppy) / dt - self._pvy) * 0.2
        self._ppx, self._ppy = ctx.player_x, ctx.player_y

        if self._dying:
            self._death_t -= dt
            for f in self._frags:
                f[0] += f[2] * dt
                f[1] += f[3] * dt
                f[2] *= 0.95
                f[3] *= 0.95
            if self._death_t <= 0.0:
                self.dead = True
            return

        if self._birth:
            # Materializa PARADA no ponto inicial — nascer já correndo seria nervoso.
            self._birth_t -= dt
            if self._birth_t <= 0.0:
                self._birth = False
            self._sync_rect()
            return

        # Canalizando a descarga → patrulha CONGELADA (a sentinela "para" e atrai o raio).
        if self._channeling:
            self._channel_t -= dt
            if self._channel_t <= 0.0:
                self._channeling = False
        else:
            self._update_patrol(dt)
        self._sync_rect()
        self._update_combat(dt, ctx)

    def _update_patrol(self, dt: float) -> None:
        """Perímetro em PERNAS entre paradas de varredura, com easing (smoothstep):
        acelera ao sair, desacelera ao chegar, faz uma pausa de scanner e segue.
        Deliberado e controlado — não uniforme nem nervoso."""
        leg_dur = self.LEG_TIME * self._pace
        if self._patrol_phase == "move":
            self._leg_prog += dt / leg_dur
            if self._leg_prog >= 1.0:
                self._t = self._leg_to
                self._patrol_phase = "hold"
                self._patrol_t = self.DWELL_TIME * self._pace
                self._scan = 0.0
                self._scan_dir = -self._scan_dir  # alterna o sentido da varredura
            else:
                e = _smoothstep(self._leg_prog)
                self._t = self._leg_from + (self._leg_to - self._leg_from) * e
        else:  # hold: parado varrendo a área (scanner)
            self._scan += dt
            self._patrol_t -= dt
            if self._patrol_t <= 0.0:
                start = self._leg_to % 1.0
                self._leg_from = start
                self._leg_to = start + 1.0 / self.PATROL_STOPS
                self._leg_prog = 0.0
                self._patrol_phase = "move"
        self.x, self.y = self._calculate_pos(self._t)

    def _idle_dur(self) -> float:
        return self._ROLE_IDLE.get(self.role, 1.1) / self._aggr

    def _update_combat(self, dt: float, ctx: "EnemyUpdateContext") -> None:
        """FSM REPOUSO → PREPARAÇÃO(telegrafo) → DISPARO → RECUPERAÇÃO. Alvo TRAVADO
        no início da preparação (telegrafo honesto)."""
        st = self._state
        self._state_t -= dt

        if st == _S_IDLE:
            self._charge = 0.0
            if self._state_t <= 0.0:
                # Revezamento: só inicia o ataque se a rede liberar; senão re-tenta
                # em breve (fila) — evita disparos simultâneos e serializa os especiais.
                heavy = self.role in self._HEAVY_ROLES
                if self._net is not None and not self._net.can_fire(id(self), heavy):
                    self._state_t = 0.15
                    return
                if self._net is not None:
                    self._net.acquire(id(self), self._ROLE_HOLD.get(self.role, 1.2), heavy)
                self._aim_x, self._aim_y = ctx.player_x, ctx.player_y
                if self.role == "missile":
                    # Descarga atmosférica: a COLUNA de antecipação é o telegrafo.
                    # Spawna o raio já (ele cresce durante a mira), canaliza e
                    # congela a patrulha até a descarga dissipar.
                    ctx.new_enemies.append(LightningStrike(self._aim_x, event_bus=self._bus))
                    self._channeling = True
                    self._channel_t = LightningStrike.TOTAL
                    self._aim_dur = LightningStrike.CHARGE
                elif self.role == "emp":
                    # Controle de espaço: trava o alvo (atual + leve antecipação) e
                    # spawna a zona JÁ — a construção dela É o telegrafo. Marcação,
                    # acúmulo e hitbox ficam no MESMO ponto travado (mira = ataque).
                    m = scaled(ElectricPulse.RADIUS + 8.0)  # margem escalada (zona cresce c/ a resolução)
                    tx = max(m, min(Config.SCREEN_WIDTH - m, ctx.player_x + self._pvx * 0.25))
                    ty = max(m, min(Config.SCREEN_HEIGHT - m, ctx.player_y + self._pvy * 0.25))
                    self._aim_x, self._aim_y = tx, ty
                    ctx.new_enemies.append(ElectricPulse(tx, ty))
                    self._emit_sound("metropolis_energy_zone")  # zona de sobrecarga
                    self._aim_dur = ElectricPulse.GATHER
                else:
                    self._aim_dur = self._ROLE_AIM.get(self.role, 0.8)
                self._state, self._state_t = _S_AIM, self._aim_dur
        elif st == _S_AIM:
            self._charge = max(0.0, min(1.0, 1.0 - self._state_t / self._aim_dur))
            if self._state_t <= 0.0:
                self._flash = 0.22
                self._charge = 1.0
                self._state, self._state_t = _S_FIRE, self.FIRE_TIME
                ctx.new_enemies.extend(self._fire())
        elif st == _S_FIRE:
            if self._state_t <= 0.0:
                self._charge = 0.0
                self._state, self._state_t = _S_RECOVER, self.RECOVER_TIME / self._aggr
        else:  # RECUPERAÇÃO
            if self._state_t <= 0.0:
                self._state, self._state_t = _S_IDLE, self._idle_dur()

    def _fire(self) -> List[object]:
        ax, ay = self._aim_x, self._aim_y  # alvo TRAVADO no início da preparação
        base = math.atan2(ay - self.y, ax - self.x)
        if self.role == "neon":  # PRESSÃO DIRETA: trio preciso de drones energéticos
            out: List[object] = []
            for spread in (-0.20, 0.0, 0.20):
                a = base + spread
                out.append(EnergyDrone(self.x, self.y, self.x + math.cos(a) * 100.0, self.y + math.sin(a) * 100.0))
            self._emit_sound("metropolis_triple_shot")  # 1 som p/ o trio inteiro
            return out
        if self.role == "missile":  # DESCARGA: já spawnada no início da mira (canalização)
            return []
        if self.role == "laser":  # SUPORTE: grade holográfica no alvo travado
            self._emit_sound("metropolis_electric_grid")
            return [GridSnare(ax, ay)]
        if self.role == "emp":  # CONTROLE DE ESPAÇO: zona já spawnada no início da mira
            return []
        return []

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self._dying:
            self._draw_death(surface)
            return
        if self._birth:
            self._draw_birth(surface)
            return
        self._draw_active(surface)

    def _draw_active(self, surface: pygame.Surface) -> None:
        st = self._state
        hit = self.hit_timer > 0.0

        if st == _S_AIM:
            energy, vib = 0.85 + 0.45 * self._charge, 1.0 + 2.0 * self._charge
        elif st == _S_FIRE:
            energy, vib = 1.6, 0.0
        elif st == _S_RECOVER:
            energy, vib = 0.55, 0.0
        else:
            energy, vib = 0.75, 0.0

        # Telegrafo por cor (atrás de tudo) na preparação. A descarga atmosférica
        # (missile) NÃO usa este telegrafo — a coluna do raio já é o aviso.
        if st == _S_AIM and self.role != "missile":
            self._draw_telegraph(surface)

        # Canalização: link elétrico tênue da orb até o topo da coluna do raio
        # (a sentinela "atraindo" a descarga). Sutil, atrás da esfera.
        if self._channeling:
            link = _jagged(self.x, self.y, self._aim_x, 0.0, jitter=6.0, segs=5)
            pygame.draw.lines(surface, self._dark, False, [(int(px), int(py)) for px, py in link], 1)

        cx = self.x + (random.uniform(-vib, vib) if vib else 0.0)
        cy = self.y + (random.uniform(-vib, vib) if vib else 0.0)
        x, y = int(cx), int(cy)
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 5.0)
        rr = self.RADIUS * (1.0 + 0.05 * math.sin(self.anim_time * 4.0))

        # Halo respirando (intensidade pelo estado) — Surface pré-renderada e reusada
        # via set_alpha (sem alocar/redesenhar por frame). Gated por qualidade visual.
        if vq.glow_enabled:
            halo_a = max(30, min(140, int(60 * energy + 30 * pulse)))
            self._halo_surf.set_alpha(halo_a)
            surface.blit(self._halo_surf, (x - self._halo_r, y - self._halo_r))

        # Anel tecnológico externo (hexágono girando + nós).
        hexpts = self._ngon(cx, cy, 6, rr + 5, self._spin * 0.5)
        pygame.draw.polygon(surface, self._dark, [(int(hx), int(hy)) for hx, hy in hexpts], 1)
        for hx, hy in hexpts:
            pygame.draw.circle(surface, self._bright, (int(hx), int(hy)), 2)

        # Esfera de energia em camadas (dark → mid → bright → núcleo branco-quente).
        body = _NEON_WHITE if hit else self._mid
        pygame.draw.circle(surface, self._dark, (x, y), int(rr))
        pygame.draw.circle(surface, body, (x, y), int(rr * 0.78))
        pygame.draw.circle(surface, self._bright, (x, y), int(rr * 0.46))
        core_r = int(rr * (0.24 + 0.06 * pulse) + 1)
        pygame.draw.circle(surface, _NEON_WHITE, (x, y), core_r)
        pygame.draw.circle(surface, self._bright, (x, y), int(rr), 2)

        # Filamentos internos girando (vivacidade; crepitar — §3). Só crepitam na
        # MIRA (telegrafo) ou esporadicamente fora dela — menos ruído ocioso.
        if st == _S_AIM or random.random() < 0.25:
            for k in range(2):
                a = self._spin + k * math.pi
                ex = x + math.cos(a) * rr * 0.85
                ey = y + math.sin(a) * rr * 0.85
                if random.random() < (0.7 if st == _S_AIM else 0.4):
                    bolt = _jagged(x, y, ex, ey, jitter=3.0, segs=3)
                    pygame.draw.lines(surface, self._bright, False, [(int(bx), int(by)) for bx, by in bolt], 1)

        # Satélites orbitando (movimento secundário) — 2 (menos clutter decorativo).
        for i in range(2):
            sa = self.anim_time * 1.6 + i * math.pi
            srx = int(cx + math.cos(sa) * (rr + 9))
            sry = int(cy + math.sin(sa) * (rr + 9))
            pygame.draw.circle(surface, self._bright, (srx, sry), 2 if st == _S_AIM else 1)

        # Estática energética constante — núcleo vivo mesmo em repouso.
        self._draw_ambient_energy(surface, cx, cy, rr, st)

        # Feixe de varredura durante a PAUSA de patrulha (leitura de vigilância).
        # Suprimido durante mira/disparo para não competir com o telegrafo.
        if self._patrol_phase == "hold" and st not in (_S_AIM, _S_FIRE):
            self._draw_scan(surface, x, y, rr)

        # Anel de carga apertando (preparação) → clarão (disparo).
        if st == _S_AIM:
            ring_r = int(rr + 14 - 10 * self._charge)
            ca = 0.4 + 0.6 * self._charge
            col = (int(self._bright[0] * ca), int(self._bright[1] * ca), int(self._bright[2] * ca))
            pygame.draw.circle(surface, col, (x, y), max(1, ring_r), 2)
        elif st == _S_FIRE:
            fr = int(rr + 6 + 22 * (self._flash / self.FIRE_TIME))
            pygame.draw.circle(surface, _NEON_WHITE, (x, y), max(1, fr), 2)

        self._draw_health_bar(surface, x, y)

    def _draw_health_bar(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        bw = int(self.RADIUS * 2)
        by = max(2, min(Config.SCREEN_HEIGHT - 7, cy - int(self.RADIUS) - 10))
        bx = cx - bw // 2
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, 5))
        frac = max(0.0, self.health / self.max_health)
        pygame.draw.rect(surface, self._mid, (bx, by, int(bw * frac), 5))

    def _draw_telegraph(self, surface: pygame.Surface) -> None:
        """Sinal claro do ataque (alvo TRAVADO), distinto por papel/cor."""
        tp = self._charge
        cx, cy = self.x, self.y
        ax, ay = self._aim_x, self._aim_y
        a = 0.3 + 0.6 * tp
        col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))

        base = math.atan2(ay - cy, ax - cx)
        if self.role == "neon":          # RAJADA: mira reta + ticks rápidos (volley)
            ex, ey = cx + math.cos(base) * 1100.0, cy + math.sin(base) * 1100.0
            pygame.draw.line(surface, col, (int(cx), int(cy)), (int(ex), int(ey)), 1 if tp < 0.7 else 2)
            if tp > 0.4:  # ticks correndo pela linha — sinal de cadência rápida
                for k in range(4):
                    tk = ((self.anim_time * 3.0 + k * 0.25) % 1.0)
                    px, py = cx + math.cos(base) * tk * 160.0, cy + math.sin(base) * tk * 160.0
                    pygame.draw.circle(surface, self._bright, (int(px), int(py)), 2)
        elif self.role == "missile":     # PERSEGUIÇÃO: estilhaços formando no leque amplo
            for spread in (-0.42, 0.0, 0.42):
                a = base + spread
                d = self.RADIUS + 10.0 + 16.0 * tp
                tx, ty = cx + math.cos(a) * d, cy + math.sin(a) * d
                tri = self._ngon(tx, ty, 3, 5.0 + 6.0 * tp, a)
                pygame.draw.polygon(surface, col, [(int(px), int(py)) for px, py in tri], 1)
        elif self.role == "laser":       # SUPORTE: grade holográfica materializando no alvo
            half = GridSnare.HALF
            gx = max(half + 6.0, min(Config.SCREEN_WIDTH - half - 6.0, ax))
            gy = max(half + 6.0, min(Config.SCREEN_HEIGHT - half - 6.0, ay))
            rect = pygame.Rect(int(gx - half), int(gy - half), int(half * 2), int(half * 2))
            pygame.draw.rect(surface, col, rect, 1 if tp < 0.7 else 2)
            for i in range(1, 4):  # linhas internas desenhando conforme carrega
                if tp > i / 5.0:
                    lx = int(gx - half + half * 2 * i / 4)
                    ly = int(gy - half + half * 2 * i / 4)
                    pygame.draw.line(surface, col, (lx, int(gy - half)), (lx, int(gy + half)), 1)
                    pygame.draw.line(surface, col, (int(gx - half), ly), (int(gx + half), ly), 1)
        else:                            # CONTROLE: link tênue orb→zona (a zona já se
            # constrói no alvo travado; aqui só reforçamos quem a está criando).
            pygame.draw.line(surface, col, (int(cx), int(cy)), (int(ax), int(ay)), 1)

    def _draw_scan(self, surface: pygame.Surface, x: int, y: int, rr: float) -> None:
        """Feixe fino varrendo a área a partir da esfera (scanner de vigilância).
        Aponta para o interior da tela e oscila suavemente durante a pausa."""
        to_center = math.atan2(
            Config.SCREEN_HEIGHT * 0.5 - self.y, Config.SCREEN_WIDTH * 0.5 - self.x
        )
        a = to_center + math.sin(self._scan * 2.2) * 0.5 * self._scan_dir
        length = rr + 26.0
        ex, ey = x + math.cos(a) * length, y + math.sin(a) * length
        col = (int(self._mid[0] * 0.7), int(self._mid[1] * 0.7), int(self._mid[2] * 0.7))
        pygame.draw.line(surface, col, (x, y), (int(ex), int(ey)), 1)
        pygame.draw.circle(surface, self._bright, (int(ex), int(ey)), 2)

    def _draw_ambient_energy(
        self, surface: pygame.Surface, cx: float, cy: float, rr: float, state: str
    ) -> None:
        """Atividade energética constante: nós pulsando + faíscas + micro-arcos.

        Intensidade discreta em repouso, mais viva na mira — a entidade nunca é
        estática, independente do estado de combate. Draw puro (§3).
        """
        is_aiming = state == _S_AIM
        cos, sin = math.cos, math.sin
        t = self.anim_time

        # Nós energéticos: 3 pontos brilhantes orbitando a superfície da esfera.
        for k in range(3):
            na = t * 1.7 + k * (math.tau / 3.0) + self._spin * 0.15
            nx = int(cx + cos(na) * rr * 0.87)
            ny = int(cy + sin(na) * rr * 0.87)
            pulse = 0.4 + 0.6 * abs(sin(t * 5.5 + k * 2.0))
            if is_aiming:
                pulse = min(1.0, pulse + 0.3)
            node_r = max(1, int(1 + pulse))
            nc = _lerp(self._mid, self._bright, pulse)
            pygame.draw.circle(surface, nc, (nx, ny), node_r)

        # Faíscas orbitando (partículas energéticas flutuando ao redor da esfera).
        n_sparks = vq.particles(2 if is_aiming else 1)
        for _ in range(n_sparks):
            if random.random() < (0.55 if is_aiming else 0.22):
                sa = t * 3.5 + random.uniform(0.0, math.tau)
                sd = rr * random.uniform(1.08, 1.42)
                spx = int(cx + cos(sa) * sd)
                spy = int(cy + sin(sa) * sd)
                sc_ = self._bright if random.random() < 0.5 else self._mid
                surface.fill(sc_, (spx, spy, 1, 1))

        # Micro-arco de superfície (estática esporádica — discreta em repouso).
        if random.random() < (0.52 if is_aiming else 0.18):
            a0 = random.uniform(0.0, math.tau)
            x0 = cx + cos(a0) * rr * 0.94
            y0 = cy + sin(a0) * rr * 0.94
            a1 = a0 + random.uniform(-0.65, 0.65)
            arc_len = rr * random.uniform(0.20, 0.52)
            x1 = x0 + cos(a1) * arc_len
            y1 = y0 + sin(a1) * arc_len
            lc = (230, 248, 255) if random.random() < 0.45 else self._bright
            pygame.draw.line(surface, lc, (int(x0), int(y0)), (int(x1), int(y1)), 1)

    @staticmethod
    def _ngon(cx: float, cy: float, n: int, radius: float, angle: float):
        step = 2.0 * math.pi / n
        return [
            (cx + math.cos(angle + i * step) * radius, cy + math.sin(angle + i * step) * radius)
            for i in range(n)
        ]

    def _draw_birth(self, surface: pygame.Surface) -> None:
        """Materialização energética: partículas convergindo → arcos condensando →
        ESTABILIZAÇÃO (anel contraindo + ignição). `draw` puro (§3)."""
        x, y = int(self.x), int(self.y)
        p = 1.0 - max(0.0, self._birth_t) / self.BIRTH_TIME  # 0 → 1
        cos, sin = math.cos, math.sin

        gather = self.RADIUS * (3.0 - 2.0 * p)
        for k in range(vq.particles(10)):
            ang = self._spin * 0.5 + k * (2.0 * math.pi / 10.0) + random.uniform(-0.3, 0.3)
            d = gather * random.uniform(0.5, 1.2)
            base = self._bright if random.random() < 0.4 else self._mid
            ga = (0.4 + 0.6 * (1.0 - p)) * random.uniform(0.6, 1.0)
            gc = (int(base[0] * ga), int(base[1] * ga), int(base[2] * ga))
            surface.fill(gc, (int(x + cos(ang) * d), int(y + sin(ang) * d), 2, 2))

        if p > 0.15:
            for _ in range(vq.electric(2 + int(p * 4))):
                ang = random.uniform(0.0, 2.0 * math.pi)
                d = gather * random.uniform(0.6, 1.05)
                axx, ayy = x + cos(ang) * d, y + sin(ang) * d
                lc = self._bright if random.random() < 0.6 else (220, 245, 255)
                pts = _jagged(axx, ayy, x, y, jitter=4.0 + 5.0 * (1.0 - p), segs=4)
                pygame.draw.lines(surface, lc, False, [(int(px), int(py)) for px, py in pts], 1)

        # Esfera fechando (cresce + ganha brilho).
        rr = int(self.RADIUS * (0.3 + 0.7 * p))
        if rr > 0:
            pygame.draw.circle(surface, (int(self._mid[0] * p), int(self._mid[1] * p), int(self._mid[2] * p)), (x, y), rr)
            pygame.draw.circle(surface, (int(self._bright[0] * p), int(self._bright[1] * p), int(self._bright[2] * p)), (x, y), max(1, int(rr * 0.5)))

        # Estabilização (0.8→1.0): anel contraindo + flicker assentando.
        if p > 0.8:
            snap = (p - 0.8) / 0.2
            sr = int(self.RADIUS * (1.8 - 0.8 * snap))
            sa = 1.0 - snap
            sc = (int(225 * sa + 30), int(245 * sa + 10), 255)
            pygame.draw.circle(surface, sc, (x, y), max(1, sr), 2)
            if snap < 0.6 and random.random() < 0.4:
                pygame.draw.circle(surface, _NEON_WHITE, (x, y), int(self.RADIUS * 0.6), 1)

    def _draw_death(self, surface: pygame.Surface) -> None:
        """Destruição impactante: implosão → ESTOURO (onda de choque + fragmentos +
        descarga + estática) → afterglow residual. `draw` puro (§3)."""
        t = 1.0 - max(0.0, self._death_t) / self.DEATH_BURST  # 0 → 1
        x, y = int(self.x), int(self.y)
        cos, sin = math.cos, math.sin

        if t < 0.2:  # IMPLOSÃO: esfera suga p/ dentro + carrega o estouro.
            it = t / 0.2
            pygame.draw.circle(surface, self._bright, (x, y), max(1, int(self.RADIUS * (1.0 - 0.6 * it))), 2)
            pygame.draw.circle(surface, _NEON_WHITE, (x, y), max(1, int(self.RADIUS * 0.3 * (1.0 - it))))
            return

        bt = (t - 0.2) / 0.8
        ba = 1.0 - bt

        # Onda de choque.
        r = int(self.RADIUS * (0.6 + 3.2 * bt))
        if r > 0 and ba > 0.0:
            ring = (int(self._bright[0] * ba), int(self._bright[1] * ba), int(self._bright[2] * ba))
            pygame.draw.circle(surface, ring, (x, y), r, max(1, int(3 * ba)))

        # Fragmentos de energia projetados (fragmentação).
        for f in self._frags:
            base = _NEON_WHITE if f[5] else self._mid
            fc = (int(base[0] * ba), int(base[1] * ba), int(base[2] * ba))
            pygame.draw.circle(surface, fc, (int(f[0]), int(f[1])), max(1, int(f[4] * (0.5 + 0.5 * ba))))

        # Descarga elétrica para fora.
        for _ in range(vq.electric(1 + int(ba * 5))):
            ang = random.uniform(0.0, 2.0 * math.pi)
            reach = self.RADIUS * (1.2 + 2.4 * bt)
            ex, ey = x + cos(ang) * reach, y + sin(ang) * reach
            lc = (230, 248, 255) if random.random() < 0.5 else self._bright
            pts = _jagged(x, y, ex, ey, jitter=6.0 * ba + 2.0, segs=4)
            pygame.draw.lines(surface, lc, False, [(int(px), int(py)) for px, py in pts], 1)

        # Estática espalhando.
        for _ in range(vq.particles(int(8 * ba) + 1)):
            ang = random.uniform(0.0, 2.0 * math.pi)
            d = r * random.uniform(0.4, 1.05)
            base = _NEON_WHITE if random.random() < 0.45 else self._mid
            sc = (int(base[0] * ba), int(base[1] * ba), int(base[2] * ba))
            surface.fill(sc, (int(x + cos(ang) * d), int(y + sin(ang) * d), 2, 2))

        # Afterglow residual.
        if bt > 0.55:
            ga = 1.0 - (bt - 0.55) / 0.45
            gr = int(self.RADIUS * 1.6 * ga)
            if gr > 0:
                glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*self._mid, int(120 * ga)), (gr, gr), gr)
                surface.blit(glow, (x - gr, y - gr))
