"""Metropolis Overlord — primeiro chefe nativo do tema CITY (nível 30).

Fortaleza voadora cyberpunk com luta em três camadas VISÍVEIS na própria pixel
art — sem barra de vida tradicional, a progressão lê-se no estado físico do boss:

  Fase 1 — ESCUDO: o contorno neon (char `E`) É o escudo. Fica energizado enquanto
    ≥1 sentinela-geradora viver (orbitando o perímetro). Ao cair a última, o escudo
    COLAPSA visualmente (barreira descarrega, contorno apaga p/ aço morto) e o corpo
    finalmente fica vulnerável.
  Fase 2 — DESMONTE: cada impacto destrói os BLOCOS da carcaça mais próximos do
    ponto atingido (`on_hit` recebe hit_x/hit_y). A "vida" é a massa estrutural
    restante — onde o jogador mira, a casca abre e expõe o frame/núcleos. Sem HP bar.
  Fase 3 — COLAPSO: destruída ~90% da massa, a estrutura perde integridade: o resto
    explode em fragmentos e os 3 núcleos se separam em segmentos orbitais.

Contratos (CLAUDE.md): adere ao BossProtocol (§5, despacho polimórfico);
`draw()` só desenha (§3); projéteis/adds roteados por `BossUpdateResult`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ...core.config import config as Config
from ..boss_hit_mixin import BossHitMixin
from .metropolis_drone import CoreSentryDrone, EnergyTriangleDrone
from .metropolis_projectiles import NeonBurstShot
from .metropolis_segment import MetropolisSegment
from .metropolis_sentinel import MetropolisSentinel
from . import metropolis_overlord_pixel_map as pmap

if TYPE_CHECKING:
    from ...systems.boss_context import BossUpdateContext, BossUpdateResult
    from ...systems.hit_result import HitResult

# Estados da FSM.
_INTRO_RISE = "intro_rise"
_INTRO_DESCEND = "intro_descend"
_PHASE1 = "phase1_sentinels"
_SHIELD_COLLAPSE = "shield_collapse"  # transição: escudo descarrega ao cair a última sentinela
_PHASE2 = "phase2_armor"
_SEGMENTATION = "segmentation"  # boss se divide em 3 triângulos orbitais

# Caracteres do pixel-map que compõem a CARCAÇA externa destrutível (placas que
# se fragmentam ao tomar dano, revelando o frame interno já desenhado). O
# contorno neon ("E") e o frame escuro ("G") persistem.
_SHELL_CHARS = ("P",)


class _ArmorFragment:
    """Pedaço de blindagem que se desprende da carcaça e voa (cosmético).

    Vive no boss (não em `em.*`): é animação, não causa dano e não segura
    progressão. Atualizado no `update` e desenhado no `draw` (§3).
    """

    __slots__ = ("x", "y", "vx", "vy", "angle", "spin", "size", "color", "life", "max_life", "gravity")

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        size: float,
        color: tuple,
        gravity: float = 620.0,
        life: tuple[float, float] = (0.6, 1.2),
    ) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.angle = random.uniform(0.0, 360.0)
        self.spin = random.uniform(-360.0, 360.0)
        self.size = size
        self.color = color
        self.gravity = gravity  # placas caem (620); energia do escudo flutua (~120)
        self.max_life = random.uniform(*life)
        self.life = self.max_life

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.vy += self.gravity * dt  # gravidade
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        alpha = max(0.0, min(1.0, self.life / self.max_life))
        s = max(2, int(self.size))
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.fill((*self.color, int(255 * alpha)))
        rot = pygame.transform.rotate(surf, self.angle)
        surface.blit(rot, (int(self.x - rot.get_width() / 2), int(self.y - rot.get_height() / 2)))


class MetropolisOverlordBoss(BossHitMixin):
    """Reator triangular da Cidade: escudo gerado por sentinelas + carcaça que se
    desmonta bloco a bloco + 3 núcleos de plasma que colapsam em segmentos."""

    BOSS_TYPE_NAME: str = "metropolis_overlord"
    is_boss: bool = True

    WIDTH: int = 250   # 25 col * 10
    HEIGHT: int = 210  # 21 lin * 10
    DEFAULT_HEALTH: int = 1200

    RISE_SPEED: float = 40.0
    DESCENT_SPEED: float = 120.0

    # ── Fase 2: desmonte físico (massa estrutural = vida) ──────────────────────
    # Blocos removidos por ponto de dano. BULLET_BASE_DAMAGE=10 → ~2 blocos/tiro.
    DAMAGE_TO_CELLS: float = 0.25
    # Fração da carcaça destruída que dispara o COLAPSO/segmentação (Fase 3).
    SEGMENT_THRESHOLD: float = 0.90
    # Pequeno score por impacto (recompensa o "chip" sem barra de HP).
    CHIP_SCORE: int = 5
    # Erosão estrutural: perto do fim a carcaça desmorona sozinha nas bordas dos
    # buracos — evita "caçar" blocos isolados mantendo o limiar alto.
    INSTABILITY_START: float = 0.6   # fração destruída a partir da qual erode
    INSTABILITY_INTERVAL: float = 0.3
    # Duração do COLAPSO do contorno-escudo (Fase 1 → Fase 2): alguns segundos de
    # estilhaçamento pixel-a-pixel + arcos elétricos antes do corpo ficar mirável.
    SHIELD_COLLAPSE_DUR: float = 2.5

    # ── Fase 2: deriva livre pela arena (triângulo ESTÁVEL, sem rotação) ────────
    # O CENTRO deriva pela arena (NÃO persegue a nave): plataforma energética
    # flutuando em curvas amplas, virando aos poucos, desviando das bordas (estilo
    # as sentinelas, mas sem ficar presa ao perímetro). A silhueta triangular é
    # mantida estável (identidade visual forte) — a complexidade fica nos ataques.
    DRIFT_SPEED: float = 88.0      # px/s, deslocamento ~constante
    DRIFT_TURN: float = 0.55       # rad/s — amplitude do giro lento do rumo (curvas)
    DRIFT_TURN_FREQ: float = 0.23  # rad/s — frequência do balanço do rumo
    DRIFT_AVOID: float = 150.0     # px do limite onde começa a desviar p/ dentro
    DRIFT_MAX_TURN: float = 1.7    # rad/s — giro máx. ao contornar a borda

    # Drones-triângulo energéticos (novo ataque da Fase 2): cadência de invocação.
    DRONE_INTERVAL: float = 3.0    # s entre ondas (escala c/ tier e aggressiveness)

    # Escala do pixel map (25 col * 10 = 250px ; 21 lin * 10 = 210px).
    PIXEL_SCALE = 10

    # Os TRÊS núcleos energéticos, em arranjo triangular estável (tipo triforce)
    # dentro do triângulo. (rel_x, rel_y, rel_r, tema_de_plasma, fase_de_animação)
    # rel_* são frações da caixa do boss; rel_r é fração da LARGURA.
    # rel_r reduzido (0.135→0.11) p/ mais espaço negativo: cada núcleo é lido
    # individualmente sem comprimir a silhueta triangular (prioridade = legibilidade).
    SPHERE_DEFS: tuple = (
        (0.50, 0.40, 0.11, "cyan", 0.0),
        (0.32, 0.72, 0.11, "magenta", 2.0),
        (0.68, 0.72, 0.11, "amber", 4.0),
    )

    def __init__(
        self,
        x: float,
        y: float,
        health: int | None = None,
        difficulty_multiplier: float = 1.0,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.x = float(x)
        self.y = float(Config.SCREEN_HEIGHT + 50)
        self.target_y = float(y)

        base = health if health is not None else self.DEFAULT_HEALTH
        self.max_health = int(base * difficulty_multiplier)
        self.health = self.max_health
        self.dead = False

        self.aggressiveness_multiplier = max(0.5, aggressiveness_multiplier)
        self.state = _INTRO_RISE
        self.anim_time = 0.0

        # Movimento e Intro.
        self.speed = 80.0
        self.direction = 1
        self._intro_scale = 0.4
        self._intro_alpha = 100

        # Fase 2: deriva livre pela arena + invocação de drones-triângulo.
        self._move_dir = math.radians(35.0)  # rumo inicial da deriva (diagonal)
        self._drone_timer = 1.2              # primeiro enxame logo no início da fase
        self._drone_theme_idx = 0            # cicla pelas cores dos núcleos

        # Fase 2: 3 guardiões orbitais (um por núcleo), nascidos uma vez no início
        # da fase e orbitando o corpo. Ref própria do boss (como _sentinels/
        # _segments) só p/ empurrar o centro de órbita e dissipá-los na segmentação;
        # eles também vivem em em.enemies (roteados por result.spawned_enemies).
        self._core_drones: List[CoreSentryDrone] = []
        self._core_sentries_spawned = False

        # Fase 1: Sentinelas (geradoras do escudo).
        self._sentinels: List[MetropolisSentinel] = []
        self._sentinels_spawned = False

        # Colapso do contorno-escudo: as células "E" do mapa interno, ordenadas por
        # ângulo (frente de rachadura varrendo a borda). Cada uma estilhaça quando a
        # frente passa nela, ejetando um caco de energia. Não removemos a célula da
        # silhueta — só sua ENERGIA se quebra (depois fica inerte, frame estrutural).
        ecx, ecy = pmap.PIXEL_COLS / 2.0, pmap.PIXEL_ROWS / 2.0
        edge_cells = [
            (r, c)
            for r, row in enumerate(pmap.PIXEL_MAP_INTERNAL)
            for c, ch in enumerate(row)
            if ch == "E"
        ]
        edge_cells.sort(key=lambda rc: math.atan2(rc[0] - ecy, rc[1] - ecx))
        self._edge_cells_order: List[tuple[int, int]] = edge_cells
        n_edge = max(1, len(edge_cells))
        self._edge_threshold: dict[tuple[int, int], float] = {
            rc: i / n_edge for i, rc in enumerate(edge_cells)
        }
        self._shield_collapse_t = 0.0       # timer do colapso
        self._shield_shatter_idx = 0        # quantas células já estilhaçaram
        self._shield_arcs: List[List[tuple[float, float]]] = []  # arcos elétricos (draw)
        self._shield_arc_timer = 0.0

        # Fase 2: Atiradores + erosão estrutural.
        self._leak_timer = 1.5
        self._instability_timer = self.INSTABILITY_INTERVAL

        # Segmentação: o boss vira coordenador invisível de 3 segmentos.
        self._segments: List[MetropolisSegment] = []
        self._segmented = False

        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Massa estrutural: TODAS as células da carcaça externa (P), com o centro
        # local pré-computado p/ o k-nearest do dano localizado. Removidas via
        # swap-and-pop (§6) ao serem destruídas; `_removed_set` guarda os buracos
        # (consultado pelo draw da camada interna e pela erosão de bordas).
        self._intact_cells: List[tuple[int, int, str, float, float]] = [
            (r, c, ch, (c + 0.5) * self.PIXEL_SCALE, (r + 0.5) * self.PIXEL_SCALE)
            for r, row in enumerate(pmap.PIXEL_MAP)
            for c, ch in enumerate(row)
            if ch in _SHELL_CHARS
        ]
        self._total_mass: int = len(self._intact_cells)
        self._removed_set: set[tuple[int, int]] = set()
        self._fragments: List[_ArmorFragment] = []

    @property
    def rect(self) -> pygame.Rect:
        if not self.can_take_damage() or self.state in (_INTRO_RISE, _INTRO_DESCEND):
            return pygame.Rect(-1000, -1000, 0, 0)
        self._rect.update(int(self.x), int(self.y), self.w, self.h)
        return self._rect

    def collision_circle(self) -> tuple[float, float, float]:
        if not self.can_take_damage():
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def can_take_damage(self) -> bool:
        # Só a carcaça (Fase 2) é mirável. Na Fase 1 o escudo (gerado pelas
        # sentinelas) protege; na segmentação o alvo são os 3 segmentos (entidades
        # próprias) e o coordenador fica intocável.
        return self.state == _PHASE2 and not self.dead

    # ── Dano: destruição localizada de blocos (sem HP invisível) ──────────────
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        if not self.can_take_damage():
            return HitResult()
        k = max(1, int(damage * self.DAMAGE_TO_CELLS))
        # Triângulo estável (sem rotação): impacto → coords locais diretas.
        self._destroy_cells_near(hit_x - self.x, hit_y - self.y, k)
        return HitResult(
            explosion_size=12,
            points=self.CHIP_SCORE,
            sound=hit_sounds.BOSS_DAMAGE,
        )

    def take_damage(self, amount: int) -> None:
        # Fallback de protocolo (AoE/cadeias que chamam take_damage direto): mira o
        # centro. O caminho normal é `on_hit` com as coords reais do impacto.
        if not self.can_take_damage():
            return
        self._destroy_cells_near(self.w / 2.0, self.h / 2.0, max(1, int(amount * self.DAMAGE_TO_CELLS)))

    def _destroy_cells_near(self, lx: float, ly: float, k: int) -> None:
        """Remove os `k` blocos de carcaça intactos mais próximos de (lx, ly) local.

        Scan linear sobre `_intact_cells` (~150 células, algumas vezes/s no caminho
        de dano — fora do hot path por-frame; aceitável §8). Cada bloco vira fragmento.
        """
        cells = self._intact_cells
        n = len(cells)
        if n == 0:
            return
        for _ in range(min(k, n)):
            best_i, best_d = 0, 1e18
            for i in range(len(cells)):
                _r, _c, _ch, px, py = cells[i]
                d = (px - lx) ** 2 + (py - ly) ** 2
                if d < best_d:
                    best_d, best_i = d, i
            self._detach_cell(best_i)

    def _detach_cell(self, idx: int) -> None:
        """Tira a célula `idx` da massa (swap-and-pop §6) e gera o fragmento."""
        cells = self._intact_cells
        r, c, ch, _px, _py = cells[idx]
        cells[idx] = cells[-1]
        cells.pop()
        self._removed_set.add((r, c))
        self._spawn_armor_fragment(r, c, ch)

    def _spawn_armor_fragment(self, r: int, c: int, ch: str) -> None:
        px = self.x + (c + 0.5) * self.PIXEL_SCALE
        py = self.y + (r + 0.5) * self.PIXEL_SCALE
        bcx, bcy = self._center
        ang = math.atan2(py - bcy, px - bcx)
        spd = random.uniform(70.0, 200.0)
        vx = math.cos(ang) * spd + random.uniform(-50.0, 50.0)
        vy = math.sin(ang) * spd - random.uniform(40.0, 160.0)  # tende a saltar p/ cima
        color = pmap.COLORS.get(ch, (200, 205, 215))
        self._fragments.append(
            _ArmorFragment(px, py, vx, vy, self.PIXEL_SCALE, color)
        )

    def _update_fragments(self, dt: float) -> None:
        frags = self._fragments
        write = 0
        for f in frags:
            f.update(dt)
            if not f.dead:
                frags[write] = f
                write += 1
        del frags[write:]

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def _destroyed_fraction(self) -> float:
        if self._total_mass <= 0:
            return 1.0
        return 1.0 - len(self._intact_cells) / self._total_mass

    @property
    def _shield_energy(self) -> float:
        """Energia do escudo ∈[0,1]: 1.0 com o escudo pleno (intro/Fase 1), decaindo
        durante o colapso, 0.0 quando o corpo está vulnerável (Fase 2+)."""
        if self.state in (_INTRO_RISE, _INTRO_DESCEND, _PHASE1):
            return 1.0
        if self.state == _SHIELD_COLLAPSE:
            return self._shield_collapse_t / self.SHIELD_COLLAPSE_DUR if self.SHIELD_COLLAPSE_DUR else 0.0
        return 0.0

    @property
    def _shield_collapse_progress(self) -> float:
        """0.0 no início do colapso → 1.0 quando o contorno-escudo terminou de estilhaçar."""
        if self.SHIELD_COLLAPSE_DUR <= 0.0:
            return 1.0
        return 1.0 - self._shield_collapse_t / self.SHIELD_COLLAPSE_DUR

    def _armor_tier(self) -> int:
        """Escala a agressividade da Fase 2 pela fração JÁ desmontada (mais exposto
        → mais agressivo), não por HP invisível."""
        d = self._destroyed_fraction
        if d < 0.33:
            return 0
        if d < 0.66:
            return 1
        return 2

    # ── Update ────────────────────────────────────────────────────────────────
    def update_boss(self, dt: float, ctx: "BossUpdateContext") -> "BossUpdateResult":
        from ...systems.boss_context import BossUpdateResult
        result = BossUpdateResult()
        if dt <= 0.0: return result
        self.anim_time += dt
        self._update_fragments(dt)

        if self.state == _INTRO_RISE:
            self.y -= self.RISE_SPEED * dt
            if self.y <= 150:
                self.state, self.y = _INTRO_DESCEND, -self.h
        elif self.state == _INTRO_DESCEND:
            self._intro_scale = min(1.0, self._intro_scale + 1.2 * dt)
            self._intro_alpha = min(255, self._intro_alpha + 400 * dt)
            self.y += self.DESCENT_SPEED * dt
            if self.y >= self.target_y:
                self.y, self.state, self._intro_scale, self._intro_alpha = self.target_y, _PHASE1, 1.0, 255
        elif self.state == _PHASE1:
            self._update_phase1(dt, ctx)
        elif self.state == _SHIELD_COLLAPSE:
            self._update_shield_collapse(dt)
        elif self.state == _PHASE2:
            player_y = ctx.player_y if ctx.player_y is not None else Config.SCREEN_HEIGHT / 2
            self._update_phase2(dt, ctx.player_x, player_y, result)
        elif self.state == _SEGMENTATION:
            self._update_segmentation(ctx)

        return result

    def _update_phase1(self, dt: float, ctx: "BossUpdateContext") -> None:
        if not self._sentinels_spawned:
            self._spawn_sentinels(ctx)
            self._sentinels_spawned = True
        self.x += math.sin(self.anim_time) * 15.0 * dt
        # Escudo cai junto com a última sentinela-geradora → colapso pixel-a-pixel.
        if self._sentinels and all(s.dead for s in self._sentinels):
            self._sentinels = []
            self.state = _SHIELD_COLLAPSE
            self._shield_collapse_t = self.SHIELD_COLLAPSE_DUR
            self._shield_shatter_idx = 0

    def _spawn_sentinels(self, ctx: "BossUpdateContext") -> None:
        roles = ["neon", "missile", "laser", "emp"]
        for i, role in enumerate(roles):
            s = MetropolisSentinel(role=role, start_t=i * 0.25, aggressiveness_multiplier=self.aggressiveness_multiplier, activation_delay=1.0 + i * 0.5)
            self._sentinels.append(s)
            ctx.entity_manager.enemies.append(s)

    def _update_shield_collapse(self, dt: float) -> None:
        """Estilhaça o contorno-escudo pixel-a-pixel ao longo de alguns segundos.

        Uma frente de rachadura varre a borda (`_edge_cells_order`): conforme passa
        em cada célula `E`, ejeta um caco de energia (floaty). Nos instantes finais,
        arcos elétricos instáveis crepitam pela silhueta. Sem desligamento abrupto.
        """
        self._shield_collapse_t = max(0.0, self._shield_collapse_t - dt)
        p = self._shield_collapse_progress

        # Ejeção pixel-a-pixel: um caco por célula que a frente já cruzou.
        target = int(p * len(self._edge_cells_order))
        while self._shield_shatter_idx < target:
            r, c = self._edge_cells_order[self._shield_shatter_idx]
            self._shield_shatter_idx += 1
            self._spawn_edge_shard(r, c)

        self._update_shield_arcs(dt, p)

        if self._shield_collapse_t <= 0.0:
            self.state = _PHASE2
            self._shield_arcs = []

    def _spawn_edge_shard(self, r: int, c: int) -> None:
        """Um caco de energia azul desprendendo-se da célula `E` (gravidade baixa)."""
        px = self.x + (c + 0.5) * self.PIXEL_SCALE
        py = self.y + (r + 0.5) * self.PIXEL_SCALE
        bcx, bcy = self._center
        ang = math.atan2(py - bcy, px - bcx)
        spd = random.uniform(60.0, 190.0)
        vx = math.cos(ang) * spd + random.uniform(-40.0, 40.0)
        vy = math.sin(ang) * spd - random.uniform(20.0, 90.0)
        color = pmap.EDGE_GLOW if random.random() < 0.5 else pmap.COLORS["E"]
        self._fragments.append(
            _ArmorFragment(
                px, py, vx, vy,
                self.PIXEL_SCALE * random.uniform(0.5, 0.9),
                color,
                gravity=140.0,
                life=(0.5, 1.0),
            )
        )

    def _update_shield_arcs(self, dt: float, p: float) -> None:
        """Regenera os arcos elétricos (estado lido pelo draw §3). Só nos ~60% finais,
        ficando mais numerosos perto do colapso total."""
        if p < 0.4:
            self._shield_arcs = []
            return
        self._shield_arc_timer -= dt
        if self._shield_arc_timer > 0.0:
            return
        self._shield_arc_timer = 0.05
        cells = self._edge_cells_order
        if len(cells) < 2:
            self._shield_arcs = []
            return
        sc = self.PIXEL_SCALE
        arcs: List[List[tuple[float, float]]] = []
        for _ in range(1 + int(p * 3)):  # 1 → 4 arcos
            (r1, c1) = cells[random.randrange(len(cells))]
            (r2, c2) = cells[random.randrange(len(cells))]
            arcs.append(
                self._jagged_arc(
                    self.x + (c1 + 0.5) * sc, self.y + (r1 + 0.5) * sc,
                    self.x + (c2 + 0.5) * sc, self.y + (r2 + 0.5) * sc,
                )
            )
        self._shield_arcs = arcs

    @staticmethod
    def _jagged_arc(x1: float, y1: float, x2: float, y2: float, segs: int = 5) -> List[tuple[float, float]]:
        """Polilinha em ziguezague entre dois pontos (raio elétrico)."""
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length  # perpendicular unitária
        pts: List[tuple[float, float]] = [(x1, y1)]
        for i in range(1, segs):
            t = i / segs
            off = random.uniform(-9.0, 9.0)
            pts.append((x1 + dx * t + nx * off, y1 + dy * t + ny * off))
        pts.append((x2, y2))
        return pts

    def _update_phase2(self, dt: float, px: float, py: float, result: "BossUpdateResult") -> None:
        # `health` é só um proxy derivado da massa restante p/ o BossProtocol/leitores
        # externos (música/score) — NÃO há barra de vida; a progressão é física.
        self.health = max(1, int(self.max_health * (1.0 - self._destroyed_fraction)))
        self._update_instability(dt)

        tier = self._armor_tier()
        # Deriva livre pela arena (triângulo estável; não persegue a nave).
        self._update_drift(dt)

        # Guardiões orbitais: nascem uma vez e seguem o centro do boss derivando.
        if not self._core_sentries_spawned:
            self._spawn_core_sentries(result)
            self._core_sentries_spawned = True
        self._update_core_sentries()

        self._leak_timer -= dt
        if self._leak_timer <= 0.0:
            self._leak_timer = max(0.3, (1.5 - 0.4 * tier) / self.aggressiveness_multiplier)
            cx, cy = self._center
            for k in range(1 + tier):
                result.spawned_enemies.append(NeonBurstShot(cx, cy, px + (k - tier / 2) * 80, py))

        # Drones-triângulo energéticos: o boss libera fragmentos da própria energia.
        self._drone_timer -= dt
        if self._drone_timer <= 0.0:
            self._drone_timer = max(1.3, (self.DRONE_INTERVAL - 0.45 * tier) / self.aggressiveness_multiplier)
            self._spawn_drones(px, py, tier, result)

        if self._destroyed_fraction >= self.SEGMENT_THRESHOLD:
            self._collapse_remaining_cells()
            # Guardiões orbitais dissipam: o corpo que orbitavam vai se segmentar.
            for d in self._core_drones:
                d.dissipate()
            self._core_drones = []
            self.state = _SEGMENTATION

    def _update_instability(self, dt: float) -> None:
        """Perto do fim, desprende blocos nas bordas dos buracos: a carcaça desmorona
        sozinha (cada vez mais instável) sem obrigar o jogador a caçar peças isoladas."""
        if self._destroyed_fraction < self.INSTABILITY_START:
            return
        self._instability_timer -= dt
        if self._instability_timer > 0.0:
            return
        self._instability_timer = self.INSTABILITY_INTERVAL
        # Acelera conforme desmonta: 1 bloco no início da instabilidade → ~4 no fim.
        span = max(1e-6, 1.0 - self.INSTABILITY_START)
        ramp = (self._destroyed_fraction - self.INSTABILITY_START) / span
        self._erode_near_holes(1 + int(ramp * 3))

    def _erode_near_holes(self, count: int) -> None:
        cells = self._intact_cells
        removed = self._removed_set
        candidates = [
            i
            for i, (r, c, _ch, _px, _py) in enumerate(cells)
            if (r - 1, c) in removed or (r + 1, c) in removed
            or (r, c - 1) in removed or (r, c + 1) in removed
        ]
        if not candidates:
            return
        random.shuffle(candidates)
        # Remove dos maiores índices p/ menores: mantém os índices restantes válidos
        # sob swap-and-pop (§6).
        for idx in sorted(candidates[:count], reverse=True):
            self._detach_cell(idx)

    def _collapse_remaining_cells(self) -> None:
        """Colapso estrutural: o que sobrou da carcaça vira fragmento de uma vez."""
        for r, c, ch, _px, _py in self._intact_cells:
            self._removed_set.add((r, c))
            self._spawn_armor_fragment(r, c, ch)
        self._intact_cells.clear()

    def _update_segmentation(self, ctx: "BossUpdateContext") -> None:
        """O boss se divide em 3 triângulos orbitais. Coordenador invisível: só
        cria os segmentos e morre quando os três caem."""
        if not self._segmented:
            self._spawn_segments(ctx)
            self._segmented = True
        # Vitória quando todos os segmentos foram destruídos.
        if self._segments and all(s.dead for s in self._segments):
            self.dead = True

    def _spawn_segments(self, ctx: "BossUpdateContext") -> None:
        # Ponto invisível em torno do qual os 3 segmentos orbitam (centro da arena,
        # alto o bastante para o anel ficar sempre on-screen e alcançável).
        center = (Config.SCREEN_WIDTH / 2.0, Config.SCREEN_HEIGHT * 0.34)
        orbit_radius = min(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT) * 0.28
        seg_health = max(120, int(self.max_health * 0.18))
        grid_w, grid_h = pmap.PIXEL_COLS * self.PIXEL_SCALE, pmap.PIXEL_ROWS * self.PIXEL_SCALE
        roles = {"cyan": "laser", "magenta": "missile", "amber": "emp"}

        for i, (rx, ry, _rr, theme, _phase) in enumerate(self.SPHERE_DEFS):
            # Posição de "split" = onde o núcleo estava no triângulo, dali ele
            # desliza até o anel de órbita (efeito de divisão).
            start = (self.x + rx * grid_w, self.y + ry * grid_h)
            seg = MetropolisSegment(
                theme=theme,
                role=roles.get(theme, "laser"),
                center=center,
                base_angle=math.radians(120 * i - 90),
                orbit_radius=orbit_radius,
                start_pos=start,
                health=seg_health,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
            )
            self._segments.append(seg)
            ctx.entity_manager.enemies.append(seg)

    def _update_drift(self, dt: float) -> None:
        """Deriva livre do CENTRO pela arena (plataforma energética flutuando).

        Velocidade ~constante num rumo que vira aos poucos (curvas amplas), com desvio
        suave das bordas — atravessa o interior, não persegue a nave nem gruda no
        perímetro. Independente da rotação da carcaça.
        """
        half_w, half_h = self.w / 2.0, self.h / 2.0
        m = 12.0
        min_x, max_x = half_w + m, Config.SCREEN_WIDTH - half_w - m
        min_y, max_y = half_h + m, Config.SCREEN_HEIGHT - half_h - m
        cx, cy = self._center

        # Giro lento do rumo → curvas amplas e fluidas (deslocamento contínuo).
        self._move_dir += self.DRIFT_TURN * math.sin(self.anim_time * self.DRIFT_TURN_FREQ) * dt

        # Desvio das bordas: empurra o rumo p/ dentro quando o centro se aproxima do
        # limite (cresce perto da borda), curvando antes de encostar.
        push_x = push_y = 0.0
        if cx < min_x + self.DRIFT_AVOID:
            push_x += (min_x + self.DRIFT_AVOID - cx) / self.DRIFT_AVOID
        elif cx > max_x - self.DRIFT_AVOID:
            push_x -= (cx - (max_x - self.DRIFT_AVOID)) / self.DRIFT_AVOID
        if cy < min_y + self.DRIFT_AVOID:
            push_y += (min_y + self.DRIFT_AVOID - cy) / self.DRIFT_AVOID
        elif cy > max_y - self.DRIFT_AVOID:
            push_y -= (cy - (max_y - self.DRIFT_AVOID)) / self.DRIFT_AVOID
        if push_x or push_y:
            target = math.atan2(math.sin(self._move_dir) + push_y, math.cos(self._move_dir) + push_x)
            diff = (target - self._move_dir + math.pi) % (2 * math.pi) - math.pi
            lim = self.DRIFT_MAX_TURN * dt
            self._move_dir += max(-lim, min(lim, diff))

        # Avança em velocidade constante; clamp de segurança mantém on-screen.
        cx += math.cos(self._move_dir) * self.DRIFT_SPEED * dt
        cy += math.sin(self._move_dir) * self.DRIFT_SPEED * dt
        cx = max(min_x, min(max_x, cx))
        cy = max(min_y, min(max_y, cy))
        self.x = cx - half_w
        self.y = cy - half_h

    def _spawn_core_sentries(self, result: "BossUpdateResult") -> None:
        """Cria os 3 guardiões orbitais (um por núcleo), 120° apart no anel."""
        cx, cy = self._center
        for i, (_rx, _ry, _rr, theme, _phase) in enumerate(self.SPHERE_DEFS):
            drone = CoreSentryDrone(
                cx, cy,
                base_angle=math.radians(120 * i - 90),
                theme=theme,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
            )
            self._core_drones.append(drone)
            result.spawned_enemies.append(drone)

    def _update_core_sentries(self) -> None:
        """Empurra o centro de órbita (boss deriva) e poda os mortos (§1, §6)."""
        cx, cy = self._center
        drones = self._core_drones
        i = 0
        while i < len(drones):
            d = drones[i]
            if d.dead:
                drones[i] = drones[-1]
                drones.pop()
            else:
                d.orbit_cx, d.orbit_cy = cx, cy
                i += 1

    def _spawn_drones(self, px: float, py: float, tier: int, result: "BossUpdateResult") -> None:
        """Libera 1-2 drones-triângulo perto do boss, cor ciclando pelos núcleos."""
        cx, cy = self._center
        count = 2 if tier >= 2 else 1  # mais "se desfazendo" perto do fim
        for _ in range(count):
            theme = self.SPHERE_DEFS[self._drone_theme_idx % len(self.SPHERE_DEFS)][3]
            self._drone_theme_idx += 1
            sx = cx + random.uniform(-self.w * 0.28, self.w * 0.28)
            sy = cy + random.uniform(-self.h * 0.2, self.h * 0.32)
            result.spawned_enemies.append(
                EnergyTriangleDrone(
                    sx, sy, px, py, theme,
                    aggressiveness_multiplier=self.aggressiveness_multiplier,
                )
            )

    # ── Render (§3) ────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        draw_w, draw_h = int(self.w * self._intro_scale), int(self.h * self._intro_scale)
        draw_x, draw_y = int(self.x + (self.w - draw_w) / 2), int(self.y + (self.h - draw_h) / 2)

        # Na segmentação o corpo grande não existe mais — só os 3 segmentos
        # (entidades próprias) e os fragmentos da carcaça ainda voando.
        if self.state != _SEGMENTATION:
            if self.state in (_INTRO_RISE, _INTRO_DESCEND):
                temp_surf = pygame.Surface((draw_w, draw_h), pygame.SRCALPHA)
                self._draw_pixel_map(temp_surf, 0, 0, self.PIXEL_SCALE * self._intro_scale)
                temp_surf.set_alpha(int(self._intro_alpha))
                surface.blit(temp_surf, (draw_x, draw_y))
            else:
                # Triângulo estável (sem rotação) na Fase 1/colapso/Fase 2.
                self._draw_pixel_map(surface, draw_x, draw_y, self.PIXEL_SCALE)

            # Arcos elétricos instáveis nos instantes finais do colapso do escudo.
            if self.state == _SHIELD_COLLAPSE:
                self._draw_shield_arcs(surface)

        # Fragmentos da carcaça / cacos de energia do escudo (por cima de tudo).
        for frag in self._fragments:
            frag.draw(surface)

    def _draw_pixel_map(self, surface: pygame.Surface, x: float, y: float, scale: float) -> None:
        cell = int(scale + 1)

        # 1) CAMADA INTERNA — frame escuro (G) + contorno-escudo (E). Cada "E" é
        #    desenhada por célula: enquanto o escudo vive, neon; no colapso, estilhaça
        #    pixel-a-pixel (frente branco-quente) e DESAPARECE atrás da frente — sem
        #    borda inerte. Na Fase 2+ o contorno já se foi (não desenha).
        for r, row in enumerate(pmap.PIXEL_MAP_INTERNAL):
            for c, char in enumerate(row):
                if char == ".": continue
                if char == "E":
                    color = self._edge_draw_color(r, c)
                    if color is None:
                        continue  # contorno estilhaçado/ausente → some da silhueta
                else:
                    color = pmap.COLORS.get(char, (255, 0, 255))
                pygame.draw.rect(surface, color, (int(x + c * scale), int(y + r * scale), cell, cell))

        # 2) CARCAÇA EXTERNA (placas P intactas) por cima. Conforme caem (dano
        #    localizado/erosão/colapso), saem de `_intact_cells` revelando o frame.
        for r, c, _ch, _px, _py in self._intact_cells:
            pygame.draw.rect(
                surface, pmap.COLORS["P"],
                (int(x + c * scale), int(y + r * scale), cell, cell),
            )

        # 3) NÚCLEOS DE PLASMA — o foco visual, por cima da carcaça.
        self._draw_plasma_cores(surface, x, y, scale)

    def _edge_draw_color(self, r: int, c: int) -> tuple | None:
        """Cor de UMA célula `E`, ou `None` se ela não deve ser desenhada (contorno
        ausente/estilhaçado). Render puro (§3).

        - Fase 1/intro (escudo vivo): neon pulsante.
        - Colapso: frente de rachadura varre a borda — neon dissipando à frente,
          branco-quente na frente, e NADA atrás (a célula sumiu de vez).
        - Fase 2+ (escudo destruído): `None` — o contorno foi embora, sem borda cinza.
        """
        if self.state == _SHIELD_COLLAPSE:
            p = self._shield_collapse_progress
            th = self._edge_threshold.get((r, c), 0.0)
            band = 0.10
            if p >= th + band:  # já estilhaçou → some da silhueta
                return None
            if p >= th - band:  # frente de rachadura → branco-quente
                return (225, 250, 255)
            glow = 0.5 + 0.5 * math.sin(self.anim_time * 9.0 + th * 25.0)
            neon, hot = pmap.COLORS["E"], pmap.EDGE_GLOW
            return tuple(int(neon[i] + (hot[i] - neon[i]) * glow * 0.6) for i in range(3))
        if self._shield_energy >= 1.0:  # escudo vivo: neon pulsante
            pulse = 0.5 + 0.5 * math.sin(self.anim_time * 4.0)
            return pmap.EDGE_GLOW if pulse > 0.6 else pmap.COLORS["E"]
        return None  # Fase 2+: contorno destruído, não desenha

    def _draw_shield_arcs(self, surface: pygame.Surface) -> None:
        """Desenha os arcos elétricos do colapso (estado montado no update, §3)."""
        for pts in self._shield_arcs:
            if len(pts) >= 2:
                pygame.draw.lines(
                    surface, (205, 248, 255), False,
                    [(int(px), int(py)) for px, py in pts], 2,
                )

    def _draw_plasma_cores(self, surface: pygame.Surface, x: float, y: float, scale: float) -> None:
        """Desenha os 3 núcleos com plasma vivo, posicionados no triângulo."""
        grid_w = pmap.PIXEL_COLS * scale
        grid_h = pmap.PIXEL_ROWS * scale
        intensity = 0.85 + 0.15 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0))
        for rx, ry, rr, theme, phase in self.SPHERE_DEFS:
            cx = int(x + rx * grid_w)
            cy = int(y + ry * grid_h)
            radius = rr * grid_w
            pmap.draw_plasma_sphere(
                surface, cx, cy, radius, theme, phase, intensity, self.anim_time
            )

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + 200

    def get_explosion_duration(self) -> float:
        return 4.0
