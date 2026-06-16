"""Drones energéticos do Metropolis Overlord (ataques da Fase 2).

Dois inimigos vivem aqui, ambos "fragmentos" da energia do boss e ambos
aderindo ao contrato comum (`EnemyHitMixin`) — vivem em `em.enemies`, herdam
colisão/draw/cleanup de graça, `draw` sem efeito colateral (§3), mutação só no
update:

  EnergyTriangleDrone — pequenos triângulos que o boss libera em ondas.
    Perseguição PROPOSITALMENTE BURRA (sem previsão, sem interceptação):
    escolhem o jogador, aceleram na direção dele e fazem correções lentas e
    imprecisas — podem ultrapassar a nave, sair da tela e não orbitam para
    sempre (vida curta + a correção decai, então no fim voam reto).

  CoreSentryDrone — TRÊS guardiões que nascem ao redor do boss e ORBITAM o
    corpo dele, um por núcleo (cyan/magenta/amber). Em vez de disparar projétil
    genérico, cada guardião ARREMESSA contra o jogador um caco triangular
    energético (EnergyShardTriangle) da sua cor, com efeito de contato próprio.
    São destrutíveis (dão score) e NÃO seguram a progressão — o gate da Fase 2 é
    o desmonte da carcaça. O centro de órbita é escrito pelo boss a cada frame
    (atributo público, §1), pois o boss deriva pela arena.

  EnergyShardTriangle — o caco arremessado pelo guardião: triângulo girando, da
    cor do núcleo, que voa até o jogador e provoca seu EFEITO AO CONTATO:
      cyan  → reto e rápido, impacto perfurante;
      magenta → teleguiado com turn-rate limitado (desviável, §11);
      amber → mais lento; ao tocar a nave (ou expirar na arena) DETONA um pulso
              EMP de área no impacto. (Paralisia plena da nave segue pendente —
              precisa de caminho de colisão dedicado, como `electric_fields`.)
    Destrutível a tiro: abatê-lo o neutraliza (o âmbar não detona se for
    destruído antes do contato).

A cor de ambos vem do tema do núcleo (cyan/magenta/amber), reforçando a
identidade visual.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ...core.visual_quality import visual_quality as vq
from ..enemy_hit_mixin import EnemyHitMixin
from .metropolis_projectiles import EMPPulse
from . import metropolis_overlord_pixel_map as pmap


def _jagged_line(x1: float, y1: float, x2: float, y2: float, jitter: float, segs: int = 4):
    """Polilinha em ziguezague entre dois pontos (raio elétrico). Para `draw` (§3)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length  # perpendicular unitária
    pts = [(x1, y1)]
    for i in range(1, segs):
        t = i / segs
        off = random.uniform(-jitter, jitter)
        pts.append((x1 + dx * t + nx * off, y1 + dy * t + ny * off))
    pts.append((x2, y2))
    return pts

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult


def _off_screen(x: float, y: float, margin: float = 70.0) -> bool:
    return (
        x < -margin
        or x > Config.SCREEN_WIDTH + margin
        or y < -margin
        or y > Config.SCREEN_HEIGHT + margin
    )


class EnergyTriangleDrone(EnemyHitMixin):
    """Fragmento energético triangular com perseguição simples e instável."""

    is_boss: bool = False
    HEALTH: int = 6
    POINTS: int = 60
    SIZE: float = 14.0              # meia-altura do triângulo (raio de colisão ~igual)

    INITIAL_SPEED: float = 95.0
    ACCEL: float = 340.0
    MAX_SPEED: float = 420.0
    TURN_RATE: float = 1.9         # rad/s — correção mais agressiva
    CORRECT_WINDOW: float = 3.2    # s; depois disso para de corrigir (voa reto)
    LIFETIME: float = 5.8

    BIRTH_TIME: float = 0.34       # nascimento: portal/condensação → forma materializa
    SPIN_MIN: float = 3.0          # rad/s — rotação própria (só visual, não afeta rumo)
    SPIN_MAX: float = 5.5
    DEATH_BURST: float = 0.26      # duração da explosão energética simples

    _explosion_size_killed = 0     # explosão é própria (energética), não a genérica
    _explosion_size_hit = 0

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        theme: str,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.theme = theme
        self._aggr = max(0.5, aggressiveness_multiplier)
        self.health = self.HEALTH
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self._age = 0.0
        self.lifetime = self.LIFETIME

        # Cores do tema do núcleo (dark, mid, bright).
        self._dark, self._mid, self._bright = pmap.PLASMA_THEMES.get(theme, pmap.PLASMA_THEMES["cyan"])

        # Rumo inicial APROXIMADO ao jogador (com jitter — impulsivo, não preciso).
        self.heading = math.atan2(target_y - y, target_x - x) + random.uniform(-0.4, 0.4)
        self.speed = self.INITIAL_SPEED

        # Rotação própria contínua (só visual, NÃO altera o rumo): ângulo + velocidade
        # com sinal/intensidade aleatórios (instabilidade energética por drone).
        self._spin = random.uniform(0.0, 2.0 * math.pi)
        self._spin_speed = random.choice((-1.0, 1.0)) * random.uniform(self.SPIN_MIN, self.SPIN_MAX)

        # Nascimento: emerge por um portal/condensação antes de perseguir.
        self._birth = True
        self._birth_t = self.BIRTH_TIME

        self._trail: List[Tuple[float, float, float]] = [] # x, y, angle
        self._sparks: List[List[float]] = []  # [x, y, vx, vy, life, maxlife]
        self._spark_timer = 0.0

        self._dying = False
        self._death_t = 0.0

        self._rect = pygame.Rect(0, 0, int(self.SIZE * 2), int(self.SIZE * 2))
        self._sync_rect()

    # ── Geometria / colisão ────────────────────────────────────────────────
    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return not self._birth and not self._dying and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        # Em nascimento/morte o drone não colide (está se formando/dissipando).
        if self._birth or self._dying or self.dead:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.SIZE * 0.9

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._start_death()

    def get_points_value(self) -> int:
        return self.POINTS

    def _start_death(self) -> None:
        if not self._dying:
            self._dying = True
            self._death_t = self.DEATH_BURST

    def on_hit(self, damage: int, _hx: float, _hy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        if self._birth or self._dying or self.dead:
            return HitResult()
        self.take_damage(damage)
        if self._dying:  # morreu neste hit
            return HitResult(killed=True, points=self.POINTS, sound=hit_sounds.EXPLOSION_ALIEN)
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self._start_death()
        return HitResult(sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead or (self._dying and self._death_t <= 0.0)

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        self._update_sparks(dt)
        # Rotação própria contínua (visual), inclusive enquanto nasce/morre.
        self._spin += self._spin_speed * dt

        if self._dying:
            self._death_t -= dt
            return

        if self._birth:
            # Emerge pelo portal/condensação; ainda não se move nem persegue.
            self._birth_t -= dt
            if self._birth_t <= 0.0:
                self._birth = False
            return

        self._age += dt
        self.lifetime -= dt

        # Correção agressiva rumo ao jogador.
        if self._age < self.CORRECT_WINDOW:
            desired = math.atan2(ctx.player_y - self.y, ctx.player_x - self.x)
            diff = (desired - self.heading + math.pi) % (2 * math.pi) - math.pi
            fade = 1.0 - (self._age / self.CORRECT_WINDOW) ** 1.5 # decai mais suave no início
            lim = self.TURN_RATE * self._aggr * fade * dt
            self.heading += max(-lim, min(lim, diff))

            # Dash predador: acelera se estiver quase apontado p/ o jogador.
            if abs(diff) < 0.25:
                self.speed = min(self.MAX_SPEED, self.speed + self.ACCEL * 1.5 * dt)
            else:
                self.speed = min(self.MAX_SPEED, self.speed + self.ACCEL * dt)
        else:
            self.speed = min(self.MAX_SPEED, self.speed + self.ACCEL * 0.5 * dt)

        self.x += math.cos(self.heading) * self.speed * dt
        self.y += math.sin(self.heading) * self.speed * dt
        self._sync_rect()

        # Rastro energético curto com orientação.
        self._trail.append((self.x, self.y, self._spin))
        if len(self._trail) > 10:
            del self._trail[0]

        # Faíscas pequenas durante o movimento.
        self._spark_timer -= dt
        if self._spark_timer <= 0.0:
            self._spark_timer = 0.035
            ang = self.heading + math.pi + random.uniform(-0.8, 0.8)
            sp = random.uniform(30.0, 90.0)
            self._sparks.append([
                self.x, self.y, math.cos(ang) * sp, math.sin(ang) * sp,
                random.uniform(0.2, 0.5), 0.5,
            ])

        if self.lifetime <= 0.0:
            self._start_death()   # expira na arena → explosão energética simples
        elif _off_screen(self.x, self.y):
            self.dead = True      # saiu da arena → some (invisível, sem efeito)

    def _update_sparks(self, dt: float) -> None:
        sparks = self._sparks
        w = 0
        for s in sparks:
            s[4] -= dt
            if s[4] > 0.0:
                s[0] += s[2] * dt
                s[1] += s[3] * dt
                sparks[w] = s
                w += 1
        del sparks[w:]

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self._dying:
            self._draw_death(surface)
            return
        if self._birth:
            self._draw_birth(surface)
            return

        # Rastro: wireframe fantasmagórico dos triângulos passados.
        n = len(self._trail)
        for i, (tx, ty, tang) in enumerate(self._trail):
            if i % 2 != 0: continue # pula alguns p/ não poluir
            a = (i + 1) / n
            # Triângulo de rastro menor e mais transparente.
            pts = self._tri_points(tx, ty, tang, self.SIZE * 0.7 * a)
            col = (int(self._mid[0] * a * 0.5), int(self._mid[1] * a * 0.5), int(self._mid[2] * a * 0.5))
            pygame.draw.polygon(surface, col, pts, 1)

        # Faíscas.
        for s in self._sparks:
            a = max(0.0, s[4] / s[5])
            col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
            pygame.draw.circle(surface, col, (int(s[0]), int(s[1])), max(1, int(2.5 * a)))

        # Corpo: triângulo principal (vazado no centro com pulsar interno).
        pts = self._tri_points(self.x, self.y, self._spin, self.SIZE)
        
        # Brilho externo (glow sutil via outline).
        body = (255, 255, 255) if self.hit_timer > 0.0 else self._mid
        pygame.draw.polygon(surface, body, pts)
        pygame.draw.polygon(surface, self._bright, pts, 2)
        
        # Núcleo pulsante (substitui o ponto fixo por algo mais dinâmico).
        # Um triângulo interno que pulsa em escala e gira invertido.
        p_scale = 0.4 + 0.15 * math.sin(self.anim_time * 15.0)
        i_pts = self._tri_points(self.x, self.y, -self._spin * 0.7, self.SIZE * p_scale)
        pygame.draw.polygon(surface, self._bright, i_pts, 1)
        # Pequenos arcos internos ligando o centro aos vértices (opcional, p/ "tecnológico")
        for px, py in i_pts:
            pygame.draw.line(surface, self._bright, (int(self.x), int(self.y)), (int(px), int(py)), 1)


    def _draw_birth(self, surface: pygame.Surface) -> None:
        """Nascimento: anel de condensação contraindo + cacos convergindo + o
        triângulo se materializando (escala/brilho subindo). Render puro (§3)."""
        x, y = int(self.x), int(self.y)
        p = 1.0 - max(0.0, self._birth_t) / self.BIRTH_TIME  # 0 → 1

        # Anel de portal/condensação contraindo conforme a energia se concentra.
        ring_r = int(self.SIZE * (2.1 - 1.1 * p))
        ring_a = (1.0 - p) * 0.9
        rc = (int(self._bright[0] * ring_a), int(self._bright[1] * ring_a), int(self._bright[2] * ring_a))
        if ring_r > 0:
            pygame.draw.circle(surface, rc, (x, y), ring_r, 2)

        # Cacos de energia convergindo para o centro (condensação).
        gather = self.SIZE * 2.2 * (1.0 - p)
        for i in range(5):
            ang = self._spin + i * (2.0 * math.pi / 5.0)
            gx = int(x + math.cos(ang) * gather)
            gy = int(y + math.sin(ang) * gather)
            pygame.draw.circle(surface, rc, (gx, gy), max(1, int(2 * (1.0 - p) + 1)))

        # Triângulo materializando: escala e brilho sobem com o progresso.
        scale = 0.25 + 0.75 * p
        pts = self._tri_points(self.x, self.y, self._spin, self.SIZE * scale)
        body = (int(self._mid[0] * p), int(self._mid[1] * p), int(self._mid[2] * p))
        pygame.draw.polygon(surface, body, pts)
        ec = (int(self._bright[0] * p), int(self._bright[1] * p), int(self._bright[2] * p))
        pygame.draw.polygon(surface, ec, pts, 2)

    def _draw_death(self, surface: pygame.Surface) -> None:
        """Explosão energética simples: anel expandindo + flash do tema."""
        t = 1.0 - max(0.0, self._death_t) / self.DEATH_BURST
        r = int(self.SIZE * (0.8 + 2.6 * t))
        a = 1.0 - t
        col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
        if r > 0:
            pygame.draw.circle(surface, col, (int(self.x), int(self.y)), r, max(1, int(3 * a)))
        core = (int(self._mid[0] * a), int(self._mid[1] * a), int(self._mid[2] * a))
        pygame.draw.circle(surface, core, (int(self.x), int(self.y)), max(1, int(self.SIZE * a)))

    @staticmethod
    def _tri_points(x: float, y: float, angle: float, radius: float):
        """Triângulo EQUILÁTERO (vértices 120° apart) inscrito no raio, orientação `angle`."""
        step = 2.0 * math.pi / 3.0
        return [
            (x + math.cos(angle) * radius, y + math.sin(angle) * radius),
            (x + math.cos(angle + step) * radius, y + math.sin(angle + step) * radius),
            (x + math.cos(angle + 2.0 * step) * radius, y + math.sin(angle + 2.0 * step) * radius),
        ]


class CoreSentryDrone(EnemyHitMixin):
    """Guardião orbital de um núcleo do Overlord (Fase 2).

    Nasce ao redor do boss e ORBITA o corpo dele num raio fixo (3 deles, 120°
    apart). Carrega a cor de UM núcleo e, em vez de disparar projétil genérico,
    ARREMESSA um caco triangular energético (`EnergyShardTriangle`) da sua cor
    contra o jogador — o efeito de contato é definido pelo caco, por tema.

    Destrutível (dá score). NÃO segura a progressão: o gate da Fase 2 é o
    desmonte da carcaça do boss — este é só ameaça extra, como os demais
    inimigos da arena durante a luta. O centro de órbita (`orbit_cx/orbit_cy`)
    é escrito pelo boss a cada frame (atributo público, §1), porque o boss
    deriva pela arena; o drone só lê. `draw` puro (§3); arremessa o caco pelo
    buffer do contexto (`ctx.new_enemies`), igual às sentinelas.
    """

    is_boss: bool = False
    HEALTH: int = 45
    POINTS: int = 120

    CORE_RADIUS: float = 13.0      # raio do núcleo de plasma (visual + colisão fina)
    SHELL_RADIUS: float = 22.0     # casca triangular girando ao redor do núcleo
    ORBIT_RADIUS: float = 170.0    # distância ao centro do boss
    ORBIT_PULSE: float = 14.0      # respiração do raio (sobe/desce levemente)
    ORBIT_SPEED: float = 0.85      # rad/s do giro ao redor do boss
    ORBIT_PULSE_FREQ: float = 1.3  # rad/s da respiração do raio

    SPIN_MIN: float = 1.8          # rad/s — rotação própria da casca (só visual)
    SPIN_MAX: float = 3.2

    BIRTH_TIME: float = 0.45       # materialização "saindo do núcleo"
    DEATH_BURST: float = 0.30      # explosão energética simples

    # Cadência de disparo por papel (s entre tiros), dividida por aggressiveness.
    # Pressão BRANDA: é ataque a mais sobre o boss, não o ataque principal.
    _ROLE_FIRE_INTERVAL = {"neon": 1.7, "missile": 2.3, "emp": 3.3}
    # Tema do núcleo → papel (mesma associação de SPHERE_DEFS/_spawn_segments).
    _THEME_ROLE = {"cyan": "neon", "magenta": "missile", "amber": "emp"}

    _explosion_size_killed = 0     # explosão é própria (energética), não a genérica
    _explosion_size_hit = 0

    def __init__(
        self,
        orbit_cx: float,
        orbit_cy: float,
        base_angle: float,
        theme: str,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.theme = theme
        self.role = self._THEME_ROLE.get(theme, "neon")
        self._aggr = max(0.5, aggressiveness_multiplier)
        self.health = self.HEALTH
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self._age = 0.0

        # Centro de órbita: escrito pelo boss a cada frame (público, §1).
        self.orbit_cx = float(orbit_cx)
        self.orbit_cy = float(orbit_cy)
        self._angle = base_angle  # posição no anel (avança com ORBIT_SPEED)

        # Cores do tema do núcleo (dark, mid, bright).
        self._dark, self._mid, self._bright = pmap.PLASMA_THEMES.get(
            theme, pmap.PLASMA_THEMES["cyan"]
        )

        # Rotação própria da casca triangular (só visual, não afeta a órbita).
        self._spin = random.uniform(0.0, 2.0 * math.pi)
        self._spin_speed = random.choice((-1.0, 1.0)) * random.uniform(
            self.SPIN_MIN, self.SPIN_MAX
        )

        # Posição inicial já no anel (boss empurra o centro depois).
        self.x = self.orbit_cx + math.cos(self._angle) * self.ORBIT_RADIUS
        self.y = self.orbit_cy + math.sin(self._angle) * self.ORBIT_RADIUS

        # Nascimento e morte.
        self._birth = True
        self._birth_t = self.BIRTH_TIME
        self._dying = False
        self._death_t = 0.0

        # Disparo: timer + telegrafo de carga (0→1) lido pelo draw.
        self._fire_timer = self._ROLE_FIRE_INTERVAL.get(self.role, 2.0) / self._aggr
        self._charge = 0.0
        self._flash = 0.0  # clarão curto ao disparar (visual)

        self._rect = pygame.Rect(0, 0, int(self.SHELL_RADIUS * 2), int(self.SHELL_RADIUS * 2))
        self._sync_rect()

    # ── Geometria / colisão ────────────────────────────────────────────────
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
        return self.x, self.y, self.CORE_RADIUS * 1.1

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._start_death()

    def get_points_value(self) -> int:
        return self.POINTS

    def _start_death(self) -> None:
        if not self._dying:
            self._dying = True
            self._death_t = self.DEATH_BURST

    def dissipate(self) -> None:
        """Pedido externo de fim (boss entrou na segmentação): dissipa em vez de
        ficar orbitando um corpo que não existe mais."""
        self._start_death()

    def on_hit(self, damage: int, _hx: float, _hy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        if self._birth or self._dying or self.dead:
            return HitResult()
        self.take_damage(damage)
        if self._dying:  # morreu neste hit
            return HitResult(killed=True, points=self.POINTS, sound=hit_sounds.EXPLOSION_ALIEN)
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Guardião persistente: dá dano de contato mas NÃO morre ao tocar a nave.
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead or (self._dying and self._death_t <= 0.0)

    # ── Update (§5) ───────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self._flash > 0.0:
            self._flash = max(0.0, self._flash - dt)
        self._spin += self._spin_speed * dt  # rotação própria (inclusive nascendo/morrendo)

        if self._dying:
            self._death_t -= dt
            return

        if self._birth:
            self._birth_t -= dt
            # Mesmo nascendo, acompanha o anel para já "encaixar" na órbita.
            self._advance_orbit(dt)
            if self._birth_t <= 0.0:
                self._birth = False
            return

        self._age += dt
        self._advance_orbit(dt)

        # Telegrafo de carga (lido pelo draw): brilho sobe conforme o tiro chega.
        interval = self._ROLE_FIRE_INTERVAL.get(self.role, 2.0) / self._aggr
        self._charge = max(0.0, min(1.0, 1.0 - self._fire_timer / interval))

        self._fire_timer -= dt
        if self._fire_timer <= 0.0:
            self._fire_timer = interval
            self._flash = 0.18
            ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))

    def _advance_orbit(self, dt: float) -> None:
        """Gira ao redor do centro escrito pelo boss; raio respira de leve."""
        self._angle += self.ORBIT_SPEED * dt
        r = self.ORBIT_RADIUS + self.ORBIT_PULSE * math.sin(
            self.anim_time * self.ORBIT_PULSE_FREQ
        )
        self.x = self.orbit_cx + math.cos(self._angle) * r
        self.y = self.orbit_cy + math.sin(self._angle) * r
        self._sync_rect()

    def _fire(self, px: float, py: float) -> List[object]:
        # Arremessa o caco triangular da cor do núcleo; o efeito de contato é dele.
        return [EnergyShardTriangle(self.x, self.y, px, py, self.theme, self._aggr)]

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self._dying:
            self._draw_death(surface)
            return
        if self._birth:
            self._draw_birth(surface)
            return

        x, y = int(self.x), int(self.y)

        # Casca triangular girando: identidade de "fragmento de núcleo".
        pts = EnergyTriangleDrone._tri_points(self.x, self.y, self._spin, self.SHELL_RADIUS)
        shell = (255, 255, 255) if self.hit_timer > 0.0 else self._mid
        pygame.draw.polygon(surface, shell, pts, 2)
        # Segunda casca invertida (estrela de 6 pontas) — leitura mais "tecnológica".
        pts2 = EnergyTriangleDrone._tri_points(
            self.x, self.y, -self._spin + math.pi / 3.0, self.SHELL_RADIUS
        )
        pygame.draw.polygon(surface, self._dark, pts2, 1)

        # Núcleo de plasma VIVO do tema (o foco visual; mesma rotina dos núcleos
        # do boss → "cada um com a cor do seu núcleo").
        intensity = 0.8 + 0.2 * self._charge + 0.4 * self._flash
        pmap.draw_plasma_sphere(
            surface, x, y, self.CORE_RADIUS, self.theme, self._spin, intensity, self.anim_time
        )

        # Telegrafo de carga: anel brilhante apertando antes do disparo.
        if self._charge > 0.45:
            t = (self._charge - 0.45) / 0.55
            ring_r = int(self.CORE_RADIUS + 6 - 4 * t)
            ca = 0.4 + 0.6 * t
            col = (int(self._bright[0] * ca), int(self._bright[1] * ca), int(self._bright[2] * ca))
            pygame.draw.circle(surface, col, (x, y), max(1, ring_r), 2)

    def _draw_birth(self, surface: pygame.Surface) -> None:
        """Materialização energética: estática convergindo → arcos condensando o
        núcleo → snap de luz quando a forma fecha. `draw` puro (§3)."""
        x, y = int(self.x), int(self.y)
        p = 1.0 - max(0.0, self._birth_t) / self.BIRTH_TIME  # 0 → 1
        cos, sin = math.cos, math.sin

        # 1) Cacos/estática sendo SUGADOS para o centro (campo se condensando).
        gather = self.SHELL_RADIUS * (2.6 - 1.8 * p)
        for k in range(vq.particles(9)):
            ang = self._spin * 0.5 + k * (2.0 * math.pi / 9.0) + random.uniform(-0.3, 0.3)
            d = gather * random.uniform(0.55, 1.15)
            gx = int(x + cos(ang) * d)
            gy = int(y + sin(ang) * d)
            hot = random.random() < 0.4
            base = self._bright if hot else self._mid
            ga = (0.4 + 0.6 * (1.0 - p)) * random.uniform(0.6, 1.0)
            gc = (int(base[0] * ga), int(base[1] * ga), int(base[2] * ga))
            surface.fill(gc, (gx, gy, 2, 2))

        # 2) Arcos elétricos condensando a energia: de pontos do anel até o centro,
        #    mais numerosos/curtos conforme fecha. (random no draw = crepitar — §3.)
        arcs = vq.electric(2 + int(p * 4))
        for _ in range(arcs):
            ang = random.uniform(0.0, 2.0 * math.pi)
            d = gather * random.uniform(0.7, 1.1)
            ax, ay = x + cos(ang) * d, y + sin(ang) * d
            col = self._bright if random.random() < 0.6 else (220, 245, 255)
            pts = _jagged_line(ax, ay, x, y, jitter=4.0 + 5.0 * (1.0 - p), segs=4)
            pygame.draw.lines(surface, col, False, [(int(px), int(py)) for px, py in pts], 1)

        # 3) Casca triangular fechando (cresce e ganha brilho).
        pts = EnergyTriangleDrone._tri_points(
            self.x, self.y, self._spin, self.SHELL_RADIUS * (0.35 + 0.65 * p)
        )
        ec = (int(self._mid[0] * p), int(self._mid[1] * p), int(self._mid[2] * p))
        pygame.draw.polygon(surface, ec, pts, 2)

        # 4) Núcleo materializando + snap de luz no fim (anel branco-quente curto).
        if p > 0.2:
            pmap.draw_plasma_sphere(
                surface, x, y, self.CORE_RADIUS * p, self.theme, self._spin, p, self.anim_time
            )
        if p > 0.78:
            snap = (p - 0.78) / 0.22
            sr = int(self.CORE_RADIUS * (1.0 + 2.4 * snap))
            sa = 1.0 - snap
            sc = (int(225 * sa + 30), int(245 * sa + 10), 255)
            pygame.draw.circle(surface, sc, (x, y), max(1, sr), 2)

    def _draw_death(self, surface: pygame.Surface) -> None:
        """Sobrecarga energética: núcleo estoura em arcos + estática + onda de
        choque expandindo, o tema dissipando. `draw` puro (§3)."""
        t = 1.0 - max(0.0, self._death_t) / self.DEATH_BURST  # 0 → 1
        a = 1.0 - t
        x, y = int(self.x), int(self.y)
        cos, sin = math.cos, math.sin

        # 1) Onda de choque: anel expandindo e afinando.
        r = int(self.SHELL_RADIUS * (0.6 + 2.6 * t))
        if r > 0:
            ring = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
            pygame.draw.circle(surface, ring, (x, y), r, max(1, int(3 * a)))

        # 2) Descarga: arcos elétricos lançados para fora (densos no início).
        burst = vq.electric(1 + int(a * 5))
        reach = self.SHELL_RADIUS * (1.2 + 2.0 * t)
        for _ in range(burst):
            ang = random.uniform(0.0, 2.0 * math.pi)
            ex, ey = x + cos(ang) * reach, y + sin(ang) * reach
            col = (230, 248, 255) if random.random() < 0.5 else self._bright
            pts = _jagged_line(x, y, ex, ey, jitter=6.0 * a + 2.0, segs=4)
            pygame.draw.lines(surface, col, False, [(int(px), int(py)) for px, py in pts], 1)

        # 3) Estática espalhando junto da frente da onda (cacos de energia soltos).
        for _ in range(vq.particles(int(10 * a) + 1)):
            ang = random.uniform(0.0, 2.0 * math.pi)
            d = r * random.uniform(0.4, 1.05)
            sx, sy = int(x + cos(ang) * d), int(y + sin(ang) * d)
            hot = random.random() < 0.45
            base = (255, 255, 255) if hot else self._mid
            sc = (int(base[0] * a), int(base[1] * a), int(base[2] * a))
            surface.fill(sc, (sx, sy, 2, 2))

        # 4) Núcleo colapsando (encolhe e apaga).
        core = (int(self._mid[0] * a), int(self._mid[1] * a), int(self._mid[2] * a))
        pygame.draw.circle(surface, core, (x, y), max(1, int(self.CORE_RADIUS * a)))


class EnergyShardTriangle(EnemyHitMixin):
    """Caco triangular energético arremessado por um `CoreSentryDrone`.

    Triângulo girando, da cor do núcleo de origem, que voa até o jogador e
    provoca seu EFEITO AO CONTATO conforme o tema:

        cyan    → reto e rápido (impacto perfurante);
        magenta → teleguiado com turn-rate limitado (desviável, §11/bem-estar);
        amber   → mais lento; ao tocar a nave (ou expirar na arena) DETONA um
                  `EMPPulse` de área no ponto de impacto.

    Destrutível a tiro (counterplay, §11): abatê-lo neutraliza — o âmbar só
    detona se chegar ao contato/expirar, não se for destruído antes. Vive em
    `em.enemies`; `draw` puro (§3), mutação só no update; emite o EMP pelo
    buffer do contexto (`ctx.new_enemies`).
    """

    is_boss: bool = False
    HEALTH: int = 5
    POINTS: int = 0          # é hazard/projétil, não inimigo (convenção da Cidade)
    SIZE: float = 12.0       # meia-altura do triângulo (~raio de colisão)
    LIFETIME: float = 4.2

    SPIN_MIN: float = 4.0
    SPIN_MAX: float = 7.0
    DEATH_BURST: float = 0.24

    # Velocidades/giro por papel do tema.
    SPEED_STRAIGHT: float = 440.0   # cyan
    SPEED_HOMING: float = 300.0     # magenta
    HOMING_TURN: float = 2.4        # rad/s — teto do giro (quanto menor, + desviável)
    SPEED_EMP: float = 235.0        # amber

    _THEME_ROLE = {"cyan": "neon", "magenta": "missile", "amber": "emp"}

    _explosion_size_killed = 0      # explosão própria (energética), não a genérica
    _explosion_size_hit = 0

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        theme: str,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.theme = theme
        self.role = self._THEME_ROLE.get(theme, "neon")
        self._aggr = max(0.5, aggressiveness_multiplier)
        self.health = self.HEALTH
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self.lifetime = self.LIFETIME

        self._dark, self._mid, self._bright = pmap.PLASMA_THEMES.get(
            theme, pmap.PLASMA_THEMES["cyan"]
        )

        self.angle = math.atan2(target_y - y, target_x - x)  # rumo (homing usa)
        speed = (
            self.SPEED_HOMING if self.role == "missile"
            else self.SPEED_EMP if self.role == "emp"
            else self.SPEED_STRAIGHT
        )
        self.speed = speed
        self.vx = math.cos(self.angle) * speed
        self.vy = math.sin(self.angle) * speed

        self._spin = random.uniform(0.0, 2.0 * math.pi)
        self._spin_speed = random.choice((-1.0, 1.0)) * random.uniform(self.SPIN_MIN, self.SPIN_MAX)

        self._trail: List[Tuple[float, float, float]] = []  # x, y, angle
        self._sparks: List[List[float]] = []  # [x, y, vx, vy, life, maxlife]
        self._spark_timer = 0.0

        self._dying = False
        self._death_t = 0.0
        self._should_detonate = False  # amber: detona EMP ao morrer por contato/expiração
        self._detonated = False

        self._rect = pygame.Rect(0, 0, int(self.SIZE * 2), int(self.SIZE * 2))
        self._sync_rect()

    # ── Geometria / colisão ────────────────────────────────────────────────
    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return not self._dying and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        if self._dying or self.dead:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.SIZE * 0.8

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._start_death(detonate=False)  # abatido a tiro: NÃO detona

    def get_points_value(self) -> int:
        return self.POINTS

    def _start_death(self, detonate: bool) -> None:
        if not self._dying:
            self._dying = True
            self._death_t = self.DEATH_BURST
            self._should_detonate = detonate and self.role == "emp"

    def on_hit(self, damage: int, _hx: float, _hy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        if self._dying or self.dead:
            return HitResult()
        self.take_damage(damage)
        if self._dying:  # morreu neste hit
            return HitResult(killed=True, points=self.POINTS, sound=hit_sounds.EXPLOSION_ALIEN)
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        if self._dying or self.dead:
            return HitResult()
        self._start_death(detonate=True)  # contato: efeito do tema (amber → EMP)
        return HitResult(sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead or (self._dying and self._death_t <= 0.0)

    # ── Update (§5) ───────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        self._update_sparks(dt)
        self._spin += self._spin_speed * dt

        if self._dying:
            # Detona o EMP de área no impacto/expiração (uma vez), antes de sumir.
            if self._should_detonate and not self._detonated:
                self._detonated = True
                ctx.new_enemies.append(EMPPulse(self.x, self.y))
            self._death_t -= dt
            return

        # Homing (magenta) ou voo reto (cyan/amber).
        if self.role == "missile":
            desired = math.atan2(ctx.player_y - self.y, ctx.player_x - self.x)
            diff = (desired - self.angle + math.pi) % (2 * math.pi) - math.pi
            step = self.HOMING_TURN * self._aggr * dt
            self.angle += max(-step, min(step, diff))
            self.vx = math.cos(self.angle) * self.speed
            self.vy = math.sin(self.angle) * self.speed

        self.x += self.vx * dt
        self.y += self.vy * dt
        self._sync_rect()

        # Rastro + faíscas.
        self._trail.append((self.x, self.y, self._spin))
        if len(self._trail) > 8:
            del self._trail[0]
        self._spark_timer -= dt
        if self._spark_timer <= 0.0:
            self._spark_timer = 0.04
            sa = math.atan2(self.vy, self.vx) + math.pi + random.uniform(-0.7, 0.7)
            sp = random.uniform(30.0, 80.0)
            self._sparks.append([
                self.x, self.y, math.cos(sa) * sp, math.sin(sa) * sp,
                random.uniform(0.18, 0.42), 0.42,
            ])

        self.lifetime -= dt
        if self.lifetime <= 0.0:
            self._start_death(detonate=True)  # expira na arena → âmbar ainda detona
        elif _off_screen(self.x, self.y):
            self.dead = True  # saiu da arena → some, sem efeito (nem EMP)

    def _update_sparks(self, dt: float) -> None:
        sparks = self._sparks
        w = 0
        for s in sparks:
            s[4] -= dt
            if s[4] > 0.0:
                s[0] += s[2] * dt
                s[1] += s[3] * dt
                sparks[w] = s
                w += 1
        del sparks[w:]

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self._dying:
            self._draw_death(surface)
            return

        # Rastro: triângulos fantasmas encolhendo.
        n = len(self._trail)
        for i, (tx, ty, tang) in enumerate(self._trail):
            if i % 2 != 0:
                continue
            a = (i + 1) / n
            pts = EnergyTriangleDrone._tri_points(tx, ty, tang, self.SIZE * 0.7 * a)
            col = (int(self._mid[0] * a * 0.5), int(self._mid[1] * a * 0.5), int(self._mid[2] * a * 0.5))
            pygame.draw.polygon(surface, col, pts, 1)

        # Faíscas.
        for s in self._sparks:
            a = max(0.0, s[4] / s[5])
            col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
            pygame.draw.circle(surface, col, (int(s[0]), int(s[1])), max(1, int(2.2 * a)))

        # Corpo: triângulo preenchido + contorno brilhante.
        pts = EnergyTriangleDrone._tri_points(self.x, self.y, self._spin, self.SIZE)
        body = (255, 255, 255) if self.hit_timer > 0.0 else self._mid
        pygame.draw.polygon(surface, body, pts)
        pygame.draw.polygon(surface, self._bright, pts, 2)

        # Núcleo interno pulsante (triângulo invertido).
        p_scale = 0.4 + 0.15 * math.sin(self.anim_time * 15.0)
        i_pts = EnergyTriangleDrone._tri_points(self.x, self.y, -self._spin * 0.7, self.SIZE * p_scale)
        pygame.draw.polygon(surface, self._bright, i_pts, 1)

    def _draw_death(self, surface: pygame.Surface) -> None:
        """Estouro energético curto: anel + flash do tema."""
        t = 1.0 - max(0.0, self._death_t) / self.DEATH_BURST
        r = int(self.SIZE * (0.8 + 2.4 * t))
        a = 1.0 - t
        col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
        if r > 0:
            pygame.draw.circle(surface, col, (int(self.x), int(self.y)), r, max(1, int(3 * a)))
        core = (int(self._mid[0] * a), int(self._mid[1] * a), int(self._mid[2] * a))
        pygame.draw.circle(surface, core, (int(self.x), int(self.y)), max(1, int(self.SIZE * 0.6 * a)))
