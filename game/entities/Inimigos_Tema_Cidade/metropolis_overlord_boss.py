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
from typing import TYPE_CHECKING, Any, List

import pygame

from ...core.config import config as Config
from ..boss_hit_mixin import BossHitMixin
from . import metropolis_overlord_pixel_map as pmap
from .city_mine import CityMine
from .city_thruster import EnergyThruster
from .metropolis_beam import MetropolisOrbitalBeam
from .metropolis_drone import CoreSentryDrone
from .metropolis_segment import MetropolisSegment, SegmentNetwork
from .metropolis_sentinel import MetropolisSentinel, SentinelNetwork

if TYPE_CHECKING:
    from ...systems.boss_context import BossUpdateContext, BossUpdateResult
    from ...systems.hit_result import HitResult

# Estados da FSM. O escudo VAI E VOLTA: cai ao fim da Fase 1, é reconstruído ao fim
# da Fase 2 (animação invertida), e cai de novo ao fim do interlúdio antes da Fase 3.
# Entrada dramática em 3 atos: sobe lenta como SILHUETA (75%) → ATIVA (núcleos
# acendem, interior ganha vida) → ARRANQUE final rápido (~3×) p/ a posição de combate.
_INTRO_RISE = "intro_rise"
_INTRO_ACTIVATE = "intro_activate"
_INTRO_SURGE = "intro_surge"
_INTRO_STATES = (_INTRO_RISE, _INTRO_ACTIVATE, _INTRO_SURGE)
_PHASE1 = "phase1_sentinels"
_SHIELD_COLLAPSE = (
    "shield_collapse"  # escudo descarrega pixel-a-pixel (sucessor configurável)
)
_PHASE2 = "phase2_lasers_mines"  # centro + lasers rotativos + minas (gate = 5 minas)
_SHIELD_REBUILD = "shield_rebuild"  # colapso invertido: o contorno se reconstrói
_INTERLUDE = "phase1_reprise"  # 2ª onda de sentinelas (padrão da Fase 1) com escudo
_SEGMENTATION = "segmentation"  # Fase 3 final: boss se divide em 3 triângulos orbitais

# Caracteres do pixel-map que compõem a CARCAÇA externa destrutível (placas que
# se fragmentam ao tomar dano, revelando o frame interno já desenhado). O
# contorno neon ("E") e o frame escuro ("G") persistem.
_SHELL_CHARS = ("P",)

# A estrutura interna "viva" (corrente energética em vez de preenchimento chapado)
# e a corrente da borda neon agora vivem em `pmap` (`inner_cell_color`,
# `shield_live_color`) — FONTE ÚNICA compartilhada com os mini-Overlords (segmentos).

# Flutuação VISUAL (entidade suspensa, viva). Aplicada só no draw (não toca
# hitbox/ataques). EXCLUSIVAMENTE vertical — uma senóide única, suave e contínua;
# sem deslocamento horizontal nem rotação.
_FLOAT_AMP = 5.0  # px — amplitude do bob vertical (pequena)
_FLOAT_FREQ = 0.9  # rad/s — lento

# Micro-tremor da Fase 2 enquanto os núcleos disparam os lasers (tensão interna /
# enorme liberação de energia). Muito sutil; só visual; não desloca exageradamente.
_LASER_SHAKE_AMP = 2  # px — jitter máximo por eixo durante o disparo

# Cada orb desce este tanto (equilíbrio visual da composição interna). Aplicado na
# FONTE ÚNICA da posição do orb (`_orb_world_position`) → núcleos, lasers e splits.
_ORB_DROP_PX = 10

# Entrada dramática: a silhueta cinza + bordas azuis (`pmap.SILHOUETTE` /
# `pmap.EDGE_SILHOUETTE`) faz `lerp` para a vida plena conforme a ativação.


def _lerp(a: tuple, b: tuple, f: float) -> tuple:
    """Interpola duas cores RGB (f∈[0,1]). Para transições de render puro (§3)."""
    return (
        int(a[0] + (b[0] - a[0]) * f),
        int(a[1] + (b[1] - a[1]) * f),
        int(a[2] + (b[2] - a[2]) * f),
    )


class _ArmorFragment:
    """Pedaço de blindagem que se desprende da carcaça e voa (cosmético).

    Vive no boss (não em `em.*`): é animação, não causa dano e não segura
    progressão. Atualizado no `update` e desenhado no `draw` (§3).
    """

    __slots__ = (
        "x",
        "y",
        "vx",
        "vy",
        "angle",
        "spin",
        "size",
        "color",
        "life",
        "max_life",
        "gravity",
    )

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
        surface.blit(
            rot, (int(self.x - rot.get_width() / 2), int(self.y - rot.get_height() / 2))
        )


class MetropolisOverlordBoss(BossHitMixin):
    """Reator triangular da Cidade: escudo gerado por sentinelas + carcaça que se
    desmonta bloco a bloco + 3 núcleos de plasma que colapsam em segmentos."""

    BOSS_TYPE_NAME: str = "metropolis_overlord"
    is_boss: bool = True

    WIDTH: int = 250  # 25 col * 10
    HEIGHT: int = 210  # 21 lin * 10
    DEFAULT_HEALTH: int = 1200

    RISE_SPEED: float = 40.0
    DESCENT_SPEED: float = 120.0

    # ── Entrada dramática (total ≤ 8s). Sobe 75% lenta como silhueta, ATIVA (núcleos
    #    acendem) e dispara os 25% finais ~3× mais rápido até a posição de combate.
    INTRO_RISE_DUR: float = 6.0  # subida lenta/pesada (75% do percurso)
    INTRO_ACTIVATE_DUR: float = 1.0  # despertar dos núcleos / interior ganha vida
    INTRO_SURGE_DUR: float = 0.7  # arranque final (25%, ~3× a velocidade média)
    INTRO_RISE_FRAC: float = 0.75  # fração do percurso coberta na subida lenta

    # ── Dano: o corpo NUNCA é mirável a tiro (em nenhuma fase). Na Fase 2 o único
    #    dano vem da EXPLOSÃO das minas da City atraídas para o centro. Cada acerto
    #    erode a carcaça (cosmético) via _destroy_cells_near; 5 acertos encerram a fase.
    MINE_HITS_TO_ADVANCE: int = 5
    MINE_HIT_RADIUS: float = 90.0  # raio do corpo p/ contar a explosão de mina
    DAMAGE_TO_CELLS: float = 0.25  # blocos erodidos por "acerto" cosmético de mina
    # Minas ESCASSAS/estratégicas: são a única forma de ferir o boss; raras p/ o
    # jogador ter tempo de administrar lasers + drones + minas sem sobrecarga.
    MINE_SPAWN_INTERVAL: float = (
        3.0  # atraso p/ repor um slot livre (escala c/ aggressiveness)
    )
    MAX_ACTIVE_MINES: int = 2  # teto RÍGIDO de minas vivas na arena ao mesmo tempo
    # Distância mínima (fração da largura) entre uma mina nova e as já ativas — evita
    # acúmulos que criem áreas injustas / bloqueiem a movimentação.
    MIN_MINE_SEPARATION_FRAC: float = 0.23
    # Pressão secundária: VEM SÓ das 3 sentinelas orbitais (CoreSentryDrone). O boss
    # NÃO ataca diretamente. Sentinela destruída RENASCE após este tempo (ameaça persistente).
    SENTRY_RESPAWN_TIME: float = 10.0
    # Duração do COLAPSO/RECONSTRUÇÃO do contorno-escudo (estilhaçamento pixel-a-pixel
    # + arcos; a reconstrução é a MESMA animação invertida).
    SHIELD_COLLAPSE_DUR: float = 2.5

    # ── Fase 2: posição central fixa (boss vira plataforma de lasers rotativos) ──
    PHASE2_SETTLE_SPEED: float = 420.0  # px/s do lerp do corpo até o centro da tela

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
        event_bus: Any = None,
    ) -> None:
        self._bus = event_bus  # EventBus p/ game feel (shake/flash); None em testes
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.x = float(x)
        self.target_y = float(y)
        # Começa ABAIXO da tela (escondido) e EMERGE de baixo p/ cima.
        self.y = float(Config.SCREEN_HEIGHT + 60)

        # Multiplicador de dificuldade EFETIVO (preset × escala coop por nº de
        # players). Propagado às FASES gateadas por números fixos — sentinelas
        # (Fase 1) e gate de minas (Fase 2) — p/ a regra de 2 players valer na luta
        # inteira, não só na barra de HP e nos segmentos da Fase 3.
        self._difficulty_mult = max(1.0, difficulty_multiplier)
        base = health if health is not None else self.DEFAULT_HEALTH
        self.max_health = int(base * difficulty_multiplier)
        self.health = self.max_health
        self.dead = False
        # Fase 2: nº de acertos de mina p/ avançar, escalado (mín. o valor base).
        self.mine_hits_to_advance = max(
            self.MINE_HITS_TO_ADVANCE,
            round(self.MINE_HITS_TO_ADVANCE * self._difficulty_mult),
        )

        self.aggressiveness_multiplier = max(0.5, aggressiveness_multiplier)
        self.state = _INTRO_RISE
        self.anim_time = 0.0

        # Movimento e Intro (entrada dramática em 3 atos, total ≤ 8s).
        self.speed = 80.0
        self.direction = 1
        self._intro_start_y = self.y
        _d = self._intro_start_y - self.target_y
        self._intro_act_y = (
            self.target_y + (1.0 - self.INTRO_RISE_FRAC) * _d
        )  # ponto dos 75%
        self._intro_t = 0.0  # relógio do ato atual da intro
        self._activation = 0.0  # 0 = só silhueta; 1 = núcleos/energia plenos
        self._intro_scale = 0.78  # começa "distante" e cresce até 1.0 (revela tamanho)
        self._intro_alpha = 255
        self._thruster = EnergyThruster(scale=1.0)  # propulsor da entrada
        self._thruster_intensity = 0.0

        # Fase 2: boss parado no centro. Ataque PRINCIPAL = 3 lasers rotativos; pressão
        # SECUNDÁRIA = guardiões orbitais + ondas de drones; minas = única fonte de dano.
        # O corpo NÃO recebe dano de tiro; só as explosões de mina contam (5 → rebuild).
        self._phase2_settled = False  # já assentou no centro da tela?
        self._beams: List[MetropolisOrbitalBeam] = []  # refs p/ matar ao sair da fase
        self._beams_spawned = False
        self._mine_spawn_timer = 2.0  # primeira mina alguns segundos depois
        self._active_mines: List[
            CityMine
        ] = []  # minas vivas na arena (cap MAX_ACTIVE_MINES)
        self._mine_hits = 0  # explosões de mina que tocaram o boss
        self._mine_hit_ids: set[int] = set()  # ids de MineExplosion já contados

        # Pressão secundária EXCLUSIVA das sentinelas: 3 guardiões orbitais (um por
        # núcleo) que RENASCEM 10s após serem destruídos. Cada slot = um guardião
        # (theme/base_angle fixos) com ref viva ou timer de respawn. O boss não atira.
        self._core_sentries_spawned = False
        self._sentry_slots: List[
            dict
        ] = []  # {theme, base_angle, drone|None, respawn_t}

        # Escudo vai-e-volta: sucessores configuráveis do colapso e da reconstrução.
        self._after_collapse = _PHASE2  # 1º colapso → Fase 2
        self._after_rebuild = _INTERLUDE  # reconstrução → interlúdio (padrão Fase 1)
        self._shield_rebuild_t = 0.0  # timer da reconstrução (0 → DUR)
        self._collapse_rumble_t = 0.0  # acumulador do rumble durante o colapso

        # Fase 1: Sentinelas (geradoras do escudo). `_sentinels_spawned` é rearmado
        # no interlúdio para nascer a 2ª onda.
        self._sentinels: List[MetropolisSentinel] = []
        self._sentinels_spawned = False
        self._network: SentinelNetwork | None = (
            None  # inteligência central da onda atual
        )

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
        self._shield_collapse_t = 0.0  # timer do colapso
        self._shield_shatter_idx = 0  # quantas células já estilhaçaram
        self._shield_arcs: List[
            List[tuple[float, float]]
        ] = []  # arcos elétricos (draw)
        self._shield_arc_timer = 0.0

        # Segmentação: o boss vira coordenador invisível de 3 segmentos.
        self._segments: List[MetropolisSegment] = []
        self._segmented = False
        self._segment_network: SegmentNetwork | None = None  # mente residual da Fase 3

        # Offset visual do corpo no frame atual (flutuação/tremor), calculado 1×/frame
        # no update e LIDO pelo draw e pela posição dos orbs — assim núcleos e lasers
        # compartilham exatamente o mesmo deslocamento (ficam sempre acoplados).
        self._draw_offset: tuple[int, int] = (0, 0)

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
        if not self.can_take_damage() or self.state in _INTRO_STATES:
            return pygame.Rect(-1000, -1000, 0, 0)
        self._rect.update(int(self.x), int(self.y), self.w, self.h)
        return self._rect

    def collision_circle(self) -> tuple[float, float, float]:
        if not self.can_take_damage():
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def can_take_damage(self) -> bool:
        # O CORPO nunca é mirável a tiro em fase alguma: na Fase 1/interlúdio o escudo
        # (gerado pelas sentinelas) protege; na Fase 2 o único dano vem da EXPLOSÃO das
        # minas (contabilizada internamente, ver _update_phase2); na segmentação o alvo
        # são os 3 segmentos. `rect`/`collision_circle` ficam off-screen → tiros e
        # player-lasers atravessam o boss sem efeito.
        return False

    # ── Dano: o corpo não responde a tiro; só explosão de mina (Fase 2) o fere ──
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ...systems.hit_result import HitResult

        return HitResult()  # disparos atravessam o corpo sem dano

    def take_damage(self, amount: int) -> None:
        return  # corpo imune a dano direto (AoE/cadeias); só a mecânica de minas o fere

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
        self._fragments.append(_ArmorFragment(px, py, vx, vy, self.PIXEL_SCALE, color))

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
    def _shield_energy(self) -> float:
        """Energia do escudo ∈[0,1]: 1.0 com o escudo pleno (intro/Fase 1/interlúdio),
        decaindo no colapso, subindo na reconstrução, 0.0 na Fase 2/segmentação."""
        if self.state in _INTRO_STATES or self.state in (_PHASE1, _INTERLUDE):
            return 1.0
        if self.SHIELD_COLLAPSE_DUR <= 0.0:
            return 0.0
        if self.state == _SHIELD_COLLAPSE:
            return self._shield_collapse_t / self.SHIELD_COLLAPSE_DUR
        if self.state == _SHIELD_REBUILD:
            return self._shield_rebuild_t / self.SHIELD_COLLAPSE_DUR
        return 0.0

    @property
    def _shield_collapse_progress(self) -> float:
        """0.0 no início do colapso → 1.0 quando o contorno-escudo terminou de estilhaçar."""
        if self.SHIELD_COLLAPSE_DUR <= 0.0:
            return 1.0
        return 1.0 - self._shield_collapse_t / self.SHIELD_COLLAPSE_DUR

    @property
    def _shield_rebuild_progress(self) -> float:
        """0.0 no início da reconstrução → 1.0 quando o contorno-escudo se refez."""
        if self.SHIELD_COLLAPSE_DUR <= 0.0:
            return 1.0
        return self._shield_rebuild_t / self.SHIELD_COLLAPSE_DUR

    # ── Gatilhos do escudo (sucessor configurável) ─────────────────────────────
    # ── Game feel (shake/flash via EventBus, §2) ───────────────────────────────
    def _emit_shake(self, intensity: int, duration: float) -> None:
        if self._bus is not None:
            from ...events import game_events as events

            self._bus.emit(events.ScreenShake(intensity=intensity, duration=duration))

    def _emit_flash(self, alpha: int, duration: float = 0.06) -> None:
        if self._bus is not None:
            from ...events import game_events as events

            self._bus.emit(events.ImpactFlash(duration=duration, alpha=alpha))

    def _trigger_shield_collapse(self, next_state: str) -> None:
        self._after_collapse = next_state
        self.state = _SHIELD_COLLAPSE
        self._shield_collapse_t = self.SHIELD_COLLAPSE_DUR
        self._shield_shatter_idx = 0
        self._collapse_rumble_t = 0.0
        # Momento cinematográfico: última esfera/escudo cai → mudança de fase.
        # Impacto forte (maior que o do raio) + white frame.
        self._emit_shake(16, 0.5)
        self._emit_flash(200, 0.07)

    def _trigger_shield_rebuild(self, next_state: str) -> None:
        self._after_rebuild = next_state
        self.state = _SHIELD_REBUILD
        self._shield_rebuild_t = 0.0
        self._shield_shatter_idx = 0
        self._emit_shake(12, 0.4)  # transição de fase (reconstrução do escudo)
        self._emit_flash(150, 0.06)

    # ── Update ────────────────────────────────────────────────────────────────
    def update_boss(self, dt: float, ctx: "BossUpdateContext") -> "BossUpdateResult":
        from ...systems.boss_context import BossUpdateResult

        result = BossUpdateResult()
        if dt <= 0.0:
            return result
        self.anim_time += dt
        self._update_fragments(dt)

        if self.state in _INTRO_STATES:
            self._update_intro(dt)
        elif self.state == _PHASE1:
            self._update_phase1(dt, ctx)
        elif self.state == _SHIELD_COLLAPSE:
            self._update_shield_collapse(dt)
        elif self.state == _PHASE2:
            self._update_phase2(dt, ctx, result)
        elif self.state == _SHIELD_REBUILD:
            self._update_shield_rebuild(dt)
        elif self.state == _INTERLUDE:
            self._update_interlude(dt, ctx)
        elif self.state == _SEGMENTATION:
            self._update_segmentation(ctx)

        # Offset visual do frame (flutuação/tremor), calculado UMA vez aqui e reusado
        # pelo draw e pela âncora dos orbs/lasers — mantém tudo perfeitamente em sync.
        self._draw_offset = self._float_offset()
        self._update_thruster(
            dt
        )  # propulsor sempre ativo (forte na intro, normal depois)
        return result

    def _thruster_origin(self) -> tuple[float, float]:
        """Ponto de emissão do thruster = base (parte de baixo) do corpo escalado.
        Inclui o offset visual do frame (flutuação/tremor) p/ acompanhar o corpo."""
        offx, offy = self._draw_offset
        return (
            self.x + offx + self.w / 2.0,
            self.y + offy + self.h * (1.0 + self._intro_scale) / 2.0,
        )

    def _update_thruster(self, dt: float) -> None:
        """Thruster SEMPRE ativo: forte na intro (pela velocidade), depois um nível
        de CRUZEIRO normal com respiração sutil. Na segmentação o corpo não existe
        (cada fragmento tem o próprio)."""
        if self.state == _SEGMENTATION:
            return
        if self.state not in _INTRO_STATES:
            self._thruster_intensity = 0.32 + 0.06 * math.sin(self.anim_time * 2.0)
        # (na intro, `_update_intro` já definiu a intensidade pela velocidade)
        ex, ey = self._thruster_origin()
        self._thruster.update(dt, ex, ey, self._thruster_intensity)

    def _update_intro(self, dt: float) -> None:
        """Entrada em 3 atos (≤8s): SILHUETA subindo lenta (75%) → ATIVAÇÃO (núcleos
        acendem / interior ganha vida) → ARRANQUE final rápido (~3×) até a posição de
        combate. O thruster acompanha a velocidade. Render: `_draw_intro_body`."""
        self._intro_t += dt
        prev_y = self.y
        if self.state == _INTRO_RISE:
            p = min(1.0, self._intro_t / self.INTRO_RISE_DUR)
            e = p * p * (3.0 - 2.0 * p)  # smoothstep: subida pesada/imponente
            self.y = self._intro_start_y + (self._intro_act_y - self._intro_start_y) * e
            self._intro_scale = 0.78 + 0.22 * e  # cresce: revela o verdadeiro tamanho
            self._activation = 0.0  # só silhueta + bordas azuis
            if p >= 1.0:
                self.y = self._intro_act_y
                self.state, self._intro_t = _INTRO_ACTIVATE, 0.0
        elif self.state == _INTRO_ACTIVATE:
            self.y = self._intro_act_y  # quase parado: a entidade DESPERTA
            self._intro_scale = 1.0
            self._activation = min(1.0, self._intro_t / self.INTRO_ACTIVATE_DUR)
            if self._intro_t >= self.INTRO_ACTIVATE_DUR:
                self.state, self._intro_t = _INTRO_SURGE, 0.0
        else:  # _INTRO_SURGE — dispara os 25% finais
            p = min(1.0, self._intro_t / self.INTRO_SURGE_DUR)
            e = 1.0 - (1.0 - p) * (1.0 - p)  # ease-out: arranca forte e assenta
            self.y = self._intro_act_y + (self.target_y - self._intro_act_y) * e
            self._activation = 1.0
            if p >= 1.0:
                self.y, self._intro_scale, self._activation = self.target_y, 1.0, 1.0
                self.state = _PHASE1

        # Intensidade do thruster pela velocidade vertical (mais forte no arranque);
        # na ativação, brilho de carga energética mesmo quase parado.
        speed = abs(self.y - prev_y) / dt if dt > 0.0 else 0.0
        inten = min(1.0, 0.12 + speed / 320.0)
        if self.state == _INTRO_ACTIVATE:
            inten = max(inten, 0.30 + 0.35 * self._activation)
        self._thruster_intensity = (
            inten  # o update do thruster ocorre em _update_thruster
        )

    def _update_phase1(self, dt: float, ctx: "BossUpdateContext") -> None:
        if not self._sentinels_spawned:
            self._spawn_sentinels(ctx)
            self._sentinels_spawned = True
        if self._network is not None:
            self._network.update(dt)  # coordena o revezamento das sentinelas (1×/frame)
        self.x += math.sin(self.anim_time) * 15.0 * dt
        # Escudo cai junto com a última sentinela-geradora → colapso pixel-a-pixel.
        if self._sentinels and all(s.dead for s in self._sentinels):
            self._sentinels = []
            self._trigger_shield_collapse(_PHASE2)

    def _spawn_sentinels(self, ctx: "BossUpdateContext") -> None:
        roles = ["neon", "missile", "laser", "emp"]
        self._network = SentinelNetwork()  # rede nova por onda (coordena o revezamento)
        for i, role in enumerate(roles):
            s = MetropolisSentinel(
                role=role,
                start_t=i * 0.25,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                activation_delay=1.0 + i * 0.5,
                network=self._network,
                event_bus=self._bus,
                health_multiplier=self._difficulty_mult,  # escala coop/preset (Fase 1)
            )
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

        # Rumble que ACOMPANHA a fragmentação (estrutura gigantesca colapsando):
        # pulsos curtos de shake re-emitidos periodicamente enquanto a borda quebra.
        self._collapse_rumble_t -= dt
        if self._collapse_rumble_t <= 0.0:
            self._collapse_rumble_t = 0.35
            self._emit_shake(8, 0.3)

        # Ejeção pixel-a-pixel: um caco por célula que a frente já cruzou.
        target = int(p * len(self._edge_cells_order))
        while self._shield_shatter_idx < target:
            r, c = self._edge_cells_order[self._shield_shatter_idx]
            self._shield_shatter_idx += 1
            self._spawn_edge_shard(r, c)

        self._update_shield_arcs(dt, p)

        if self._shield_collapse_t <= 0.0:
            self.state = self._after_collapse
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
                px,
                py,
                vx,
                vy,
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
                    self.x + (c1 + 0.5) * sc,
                    self.y + (r1 + 0.5) * sc,
                    self.x + (c2 + 0.5) * sc,
                    self.y + (r2 + 0.5) * sc,
                )
            )
        self._shield_arcs = arcs

    @staticmethod
    def _jagged_arc(
        x1: float, y1: float, x2: float, y2: float, segs: int = 5
    ) -> List[tuple[float, float]]:
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

    def _update_phase2(
        self, dt: float, ctx: "BossUpdateContext", result: "BossUpdateResult"
    ) -> None:
        """Centro fixo + 3 lasers rotativos (principal) + minas da City (secundário).

        O corpo é IMUNE a tiro; o único dano vem da EXPLOSÃO das minas atraídas para o
        centro. `health` é só um proxy (música/score) do progresso de minas; a fase
        encerra ao 5º acerto → reconstrução do escudo.
        """
        self.health = max(
            1,
            int(self.max_health * (1.0 - self._mine_hits / self.mine_hits_to_advance)),
        )

        # 1) Assenta no centro da tela (lerp curto) e trava ali.
        if not self._phase2_settled:
            self._settle_to_center(dt)

        # 2) Lasers rotativos (PRINCIPAL): nascem UMA vez, após assentar.
        if self._phase2_settled and not self._beams_spawned:
            self._spawn_beams(result)
            self._beams_spawned = True

        # 3) Pressão SECUNDÁRIA EXCLUSIVA das 3 sentinelas orbitais (o boss NÃO atira):
        #    nascem uma vez e RENASCEM 10s após destruídas (ameaça persistente).
        if self._phase2_settled:
            if not self._core_sentries_spawned:
                self._spawn_core_sentries(result)
                self._core_sentries_spawned = True
            self._update_core_sentries(dt, result)

        # 4) Minas ESCASSAS (única fonte de dano): NO MÁX. 2 ativas; uma nova só surge
        #    quando uma das atuais detona/expira/some (`_prune_active_mines` libera o slot).
        self._prune_active_mines()
        self._mine_spawn_timer -= dt
        if (
            len(self._active_mines) < self.MAX_ACTIVE_MINES
            and self._mine_spawn_timer <= 0.0
        ):
            self._mine_spawn_timer = max(
                1.5, self.MINE_SPAWN_INTERVAL / self.aggressiveness_multiplier
            )
            mine = self._make_mine()
            self._active_mines.append(mine)
            result.spawned_enemies.append(mine)

        # 5) Conta explosões de mina que tocaram o corpo (auto-contido, lê em.*).
        self._count_mine_hits(ctx)

        if self._mine_hits >= self.mine_hits_to_advance:
            self._kill_beams()
            for slot in self._sentry_slots:
                if slot["drone"] is not None:
                    slot["drone"].dissipate()
            self._sentry_slots = []  # encerra os respawns ao sair da fase
            self._trigger_shield_rebuild(_INTERLUDE)

    def _settle_to_center(self, dt: float) -> None:
        """Lerp do corpo até o centro da tela; trava ao chegar."""
        tx = Config.SCREEN_WIDTH / 2.0 - self.w / 2.0
        ty = Config.SCREEN_HEIGHT / 2.0 - self.h / 2.0
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        step = self.PHASE2_SETTLE_SPEED * dt
        if dist <= step or dist < 1.0:
            self.x, self.y = tx, ty
            self._phase2_settled = True
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step

    def _spawn_beams(self, result: "BossUpdateResult") -> None:
        """Cria os 3 feixes rotativos (um por orb). A DIREÇÃO INICIAL de cada um é a
        ESTRUTURAL — do centroide do triângulo para fora, passando pela própria orb
        (orb superior começa p/ cima, inferiores p/ as pontas da base). A partir daí
        GIRAM juntos (varredura), preservando a relação geométrica de 120°."""
        grid_w = pmap.PIXEL_COLS * self.PIXEL_SCALE
        grid_h = pmap.PIXEL_ROWS * self.PIXEL_SCALE
        # Centroide das 3 orbs (em frações da caixa) → direção INICIAL de cada feixe.
        cen_rx = sum(d[0] for d in self.SPHERE_DEFS) / len(self.SPHERE_DEFS)
        cen_ry = sum(d[1] for d in self.SPHERE_DEFS) / len(self.SPHERE_DEFS)
        for rx, ry, _rr, theme, _phase in self.SPHERE_DEFS:
            ox, oy = self._orb_world_position(rx, ry)
            # Direção natural = do centroide para a orb (em px, p/ respeitar o aspecto).
            angle = math.atan2((ry - cen_ry) * grid_h, (rx - cen_rx) * grid_w)
            # Âncora dinâmica: o feixe RELÊ a posição do orb a cada frame (hierarquia
            # Boss→Orb→Laser). Default-args capturam rx/ry desta iteração.
            beam = MetropolisOrbitalBeam(
                ox,
                oy,
                base_angle=angle,  # base estrutural; o giro padrão é mantido
                theme=theme,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                origin_provider=lambda r=rx, c=ry: self._orb_world_position(r, c),
            )
            self._beams.append(beam)
            result.new_lasers.append(beam)

    def _kill_beams(self) -> None:
        # Dissipa progressivamente (não some abrupto); os feixes seguem vivos em
        # em.boss_lasers até a animação de fade terminar e eles se marcarem `dead`.
        for b in self._beams:
            b.begin_fade()
        self._beams = []

    def _new_sentry(self, theme: str, base_angle: float) -> CoreSentryDrone:
        cx, cy = self._center
        return CoreSentryDrone(
            cx,
            cy,
            base_angle=base_angle,
            theme=theme,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
        )

    def _spawn_core_sentries(self, result: "BossUpdateResult") -> None:
        """Cria os 3 guardiões orbitais (um por núcleo), 120° apart, e seus slots."""
        for i, (_rx, _ry, _rr, theme, _phase) in enumerate(self.SPHERE_DEFS):
            ba = math.radians(120 * i - 90)
            drone = self._new_sentry(theme, ba)
            self._sentry_slots.append(
                {"theme": theme, "base_angle": ba, "drone": drone, "respawn_t": 0.0}
            )
            result.spawned_enemies.append(drone)

    def _update_core_sentries(self, dt: float, result: "BossUpdateResult") -> None:
        """Mantém o centro de órbita (boss central) e RENASCE a sentinela 10s após
        destruída (mesma animação de criação, retomando órbita + ataques)."""
        cx, cy = self._center
        for slot in self._sentry_slots:
            d = slot["drone"]
            if d is not None:
                if d.should_remove():  # terminou a animação de morte → renasce depois
                    slot["drone"] = None
                    slot["respawn_t"] = self.SENTRY_RESPAWN_TIME
                else:
                    d.orbit_cx, d.orbit_cy = cx, cy
            else:
                slot["respawn_t"] -= dt
                if slot["respawn_t"] <= 0.0:
                    nd = self._new_sentry(slot["theme"], slot["base_angle"])
                    slot["drone"] = nd
                    result.spawned_enemies.append(nd)

    def _make_mine(self) -> CityMine:
        """Mina da City caindo do topo, x com viés ao centro e a uma distância MÍNIMA
        das minas já ativas (valida a posição antes de definir o local de surgimento).

        Subtrai do intervalo de spawn as zonas proibidas (±min_sep) de cada mina ativa
        e sorteia dentro dos trechos restantes — garante a separação sempre que houver
        espaço; sem espaço, usa o ponto mais distante possível das existentes.
        """
        cx = Config.SCREEN_WIDTH / 2.0
        lo = max(40.0, cx - 0.32 * Config.SCREEN_WIDTH)
        hi = min(Config.SCREEN_WIDTH - 40.0, cx + 0.32 * Config.SCREEN_WIDTH)
        min_sep = self.MIN_MINE_SEPARATION_FRAC * Config.SCREEN_WIDTH
        existing = [m.x for m in self._active_mines]

        allowed: List[tuple[float, float]] = [(lo, hi)]
        for ex in existing:
            nxt: List[tuple[float, float]] = []
            for a, b in allowed:
                if ex - min_sep > a:
                    nxt.append((a, min(b, ex - min_sep)))
                if ex + min_sep < b:
                    nxt.append((max(a, ex + min_sep), b))
            allowed = [(a, b) for a, b in nxt if b > a]

        if allowed:
            total = sum(b - a for a, b in allowed)
            r = random.uniform(0.0, total)
            x = allowed[-1][1]
            for a, b in allowed:
                if r <= b - a:
                    x = a + r
                    break
                r -= b - a
        else:
            # Sem espaço suficiente: o ponto mais distante das minas ativas.
            x = max((lo, hi), key=lambda c: min(abs(c - ex) for ex in existing))
        return CityMine(x, None)  # y=None → nasce no topo e cai

    def _prune_active_mines(self) -> None:
        """Libera o slot de minas que detonaram (`dead`) ou saíram da tela (§6)."""
        mines = self._active_mines
        i = 0
        while i < len(mines):
            m = mines[i]
            if m.dead or m.is_off_screen():
                mines[i] = mines[-1]
                mines.pop()
            else:
                i += 1

    def _count_mine_hits(self, ctx: "BossUpdateContext") -> None:
        """Conta cada MineExplosion ativa cujo disco cobre o corpo (uma vez por explosão).

        Dedup por `id()` da explosão, mas PODANDO para os ids ainda vivos na lista a
        cada frame: `id()` é reciclado após o GC remover a explosão, então sem a poda
        uma explosão nova poderia reusar um id já contado e ser ignorada (undercount).
        """
        explosions = ctx.entity_manager.mine_explosions
        self._mine_hit_ids.intersection_update(id(ex) for ex in explosions)
        bcx, bcy = self._center
        reach = self.MINE_HIT_RADIUS
        for ex in explosions:
            if ex.finished():
                continue
            eid = id(ex)
            if eid in self._mine_hit_ids:
                continue
            dx, dy = ex.x - bcx, ex.y - bcy
            rr = ex.max_radius + reach
            if dx * dx + dy * dy <= rr * rr:
                self._mine_hit_ids.add(eid)
                self._register_mine_hit(ex.x, ex.y)

    def _register_mine_hit(self, ex: float, ey: float) -> None:
        """Acerto de mina: feedback de impacto + erosão cosmética da carcaça."""
        self._mine_hits += 1
        # Game feel do dano ao boss (raro: ≤5/fase): white frame breve + shake leve.
        self._emit_flash(120, 0.05)
        self._emit_shake(6, 0.18)
        k = max(3, int(self._total_mass / (self.mine_hits_to_advance + 1)))
        self._destroy_cells_near(ex - self.x, ey - self.y, k)

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
            self._collapse_remaining_cells()  # o que sobrou da carcaça explode antes de dividir
            self._spawn_segments(ctx)
            self._segmented = True
        if self._segment_network is not None:
            alive = sum(1 for s in self._segments if not s.dead)
            self._segment_network.update(
                ctx.dt, alive
            )  # ritma + ESCALA pela perda de corpos
        # Vitória quando todos os segmentos foram destruídos.
        if self._segments and all(s.dead for s in self._segments):
            self.dead = True

    def _spawn_segments(self, ctx: "BossUpdateContext") -> None:
        # Ponto invisível em torno do qual os 3 segmentos orbitam (centro da arena,
        # alto o bastante para o anel ficar sempre on-screen e alcançável).
        center = (Config.SCREEN_WIDTH / 2.0, Config.SCREEN_HEIGHT * 0.34)
        orbit_radius = min(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT) * 0.28
        seg_health = max(120, int(self.max_health * 0.18))
        # Papéis com a LINGUAGEM NOVA (projéteis das sentinelas, versão menor):
        # drone = pequenos feixes; shard = triângulos energéticos; pulse = descarga.
        roles = {"cyan": "drone", "magenta": "shard", "amber": "pulse"}
        self._segment_network = SegmentNetwork()  # mente residual coordenando os 3

        for i, (rx, ry, _rr, theme, _phase) in enumerate(self.SPHERE_DEFS):
            # Posição de "split" = onde o núcleo ESTAVA (fonte única do orb), dali ele
            # desliza até o anel de órbita (efeito de divisão).
            start = self._orb_world_position(rx, ry)
            seg = MetropolisSegment(
                theme=theme,
                role=roles.get(theme, "drone"),
                center=center,
                base_angle=math.radians(120 * i - 90),
                orbit_radius=orbit_radius,
                start_pos=start,
                health=seg_health,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                index=i,
                network=self._segment_network,
            )
            self._segments.append(seg)
            ctx.entity_manager.enemies.append(seg)

    # ── Reconstrução do escudo (colapso INVERTIDO) ─────────────────────────────
    def _update_shield_rebuild(self, dt: float) -> None:
        """Reconstrói o contorno-escudo: a MESMA animação do colapso, invertida.

        A frente de rachadura varre em ordem inversa; cada célula `E` reaparece
        (frente branco-quente → assenta em neon) e os cacos CONVERGEM para a borda
        (caminho contrário ao colapso). Ao fim, o escudo está 100% reativado.
        """
        self._shield_rebuild_t = min(
            self.SHIELD_COLLAPSE_DUR, self._shield_rebuild_t + dt
        )
        p = self._shield_rebuild_progress

        n = len(self._edge_cells_order)
        target = int(p * n)
        while self._shield_shatter_idx < target:
            r, c = self._edge_cells_order[
                n - 1 - self._shield_shatter_idx
            ]  # ordem inversa
            self._shield_shatter_idx += 1
            self._spawn_rebuild_shard(r, c)

        # Arcos crepitam mais no INÍCIO (energia instável se assentando) e somem no fim.
        self._update_shield_arcs(dt, 1.0 - p)

        if self._shield_rebuild_t >= self.SHIELD_COLLAPSE_DUR:
            self._sentinels_spawned = False  # rearma p/ a 2ª onda do interlúdio
            self.state = self._after_rebuild
            self._shield_arcs = []
            self._shield_shatter_idx = 0

    def _spawn_rebuild_shard(self, r: int, c: int) -> None:
        """Caco de energia CONVERGINDO para a célula `E` (inverso de _spawn_edge_shard)."""
        px = self.x + (c + 0.5) * self.PIXEL_SCALE
        py = self.y + (r + 0.5) * self.PIXEL_SCALE
        bcx, bcy = self._center
        ang = math.atan2(py - bcy, px - bcx)
        out = random.uniform(
            24.0, 70.0
        )  # começa afastado p/ fora e converge p/ a borda
        spd = random.uniform(60.0, 170.0)
        vx = -math.cos(ang) * spd + random.uniform(-30.0, 30.0)
        vy = -math.sin(ang) * spd + random.uniform(-30.0, 30.0)
        color = pmap.EDGE_GLOW if random.random() < 0.5 else pmap.COLORS["E"]
        self._fragments.append(
            _ArmorFragment(
                px + math.cos(ang) * out,
                py + math.sin(ang) * out,
                vx,
                vy,
                self.PIXEL_SCALE * random.uniform(0.5, 0.9),
                color,
                gravity=-40.0,  # leve flutuação (energia, não detrito que cai)
                life=(0.45, 0.9),
            )
        )

    # ── Interlúdio: padrão da Fase 1 com escudo reconstruído ───────────────────
    def _update_interlude(self, dt: float, ctx: "BossUpdateContext") -> None:
        """2ª onda de sentinelas (mesma mecânica da Fase 1). Matar todas derruba o
        escudo de novo → Fase 3 (segmentação)."""
        if not self._sentinels_spawned:
            self._spawn_sentinels(ctx)
            self._sentinels_spawned = True
        if self._network is not None:
            self._network.update(dt)  # coordena o revezamento das sentinelas (1×/frame)
        self.x += math.sin(self.anim_time) * 15.0 * dt
        if self._sentinels and all(s.dead for s in self._sentinels):
            self._sentinels = []
            self._trigger_shield_collapse(_SEGMENTATION)

    # ── Render (§3) ────────────────────────────────────────────────────────────
    def _float_offset(self) -> tuple[int, int]:
        """Deslocamento VISUAL do corpo (px), nunca a hitbox/ataques.

        - Fase 1 / interlúdio: flutuação EXCLUSIVAMENTE vertical (senóide única,
          suave) — a entidade pairando no ar. Sem eixo horizontal, sem rotação.
        - Fase 2 (disparando lasers): micro-tremor sutil (tensão dos núcleos
          liberando energia). Na intro/colapso/segmentação, sem offset (têm animação
          própria)."""
        if self.state in (_PHASE1, _INTERLUDE):
            return (0, int(math.sin(self.anim_time * _FLOAT_FREQ) * _FLOAT_AMP))
        if self.state == _PHASE2 and self._beams_spawned:
            amp = _LASER_SHAKE_AMP
            return (random.randint(-amp, amp), random.randint(-amp, amp))
        return (0, 0)

    def draw(self, surface: pygame.Surface) -> None:
        draw_w, draw_h = (
            int(self.w * self._intro_scale),
            int(self.h * self._intro_scale),
        )
        draw_x, draw_y = (
            int(self.x + (self.w - draw_w) / 2),
            int(self.y + (self.h - draw_h) / 2),
        )

        # Flutuação/tremor VISUAL (mesmo offset usado pela posição dos orbs/lasers,
        # calculado no update). Desloca só o desenho, nunca a hitbox.
        fx, fy = self._draw_offset
        draw_x += fx
        draw_y += fy

        # Na segmentação o corpo grande não existe mais — só os 3 segmentos
        # (entidades próprias) e os fragmentos da carcaça ainda voando.
        if self.state != _SEGMENTATION:
            # Thruster SEMPRE ATIVO, atrás do corpo (forte na intro, cruzeiro depois).
            tex, tey = self._thruster_origin()
            self._thruster.draw(surface, tex, tey, self._thruster_intensity)

            if self.state in _INTRO_STATES:
                # Corpo: SILHUETA (cinza + bordas azuis) que GANHA VIDA com a ativação.
                temp_surf = pygame.Surface((draw_w, draw_h), pygame.SRCALPHA)
                self._draw_intro_body(
                    temp_surf,
                    0,
                    0,
                    self.PIXEL_SCALE * self._intro_scale,
                    self._activation,
                )
                if self._intro_alpha < 255:
                    temp_surf.set_alpha(int(self._intro_alpha))
                surface.blit(temp_surf, (draw_x, draw_y))
            else:
                # Triângulo estável (sem rotação) na Fase 1/colapso/Fase 2.
                self._draw_pixel_map(surface, draw_x, draw_y, self.PIXEL_SCALE)

            # Arcos elétricos instáveis no colapso e na reconstrução do escudo.
            if self.state in (_SHIELD_COLLAPSE, _SHIELD_REBUILD):
                self._draw_shield_arcs(surface)

        # O feedback de dano vem dos white frames (ImpactFlash de tela), tremor e
        # partículas — NÃO de um glow quadrado sobre a bounding box (estética).

        # Fragmentos da carcaça / cacos de energia do escudo (por cima de tudo).
        for frag in self._fragments:
            frag.draw(surface)

    def _draw_intro_body(
        self, surface: pygame.Surface, x: float, y: float, scale: float, act: float
    ) -> None:
        """Corpo durante a ENTRADA: SILHUETA cinza + bordas azuis energizadas que
        GANHAM VIDA (`lerp` por `act`∈[0,1]) — interior se energiza e os núcleos
        ACENDEM. Em `act==1` é idêntico ao corpo de combate (transição sem corte)."""
        cell = int(scale + 1)
        inner = self._inner_cell_color
        draw_rect = pygame.draw.rect
        sil, edge_sil = pmap.SILHOUETTE, pmap.EDGE_SILHOUETTE

        # 1) Frame (G) + bordas (E): silhueta → vida. Bordas azuis desde o início.
        for r, row in enumerate(pmap.PIXEL_MAP_INTERNAL):
            for c, char in enumerate(row):
                if char == ".":
                    continue
                if char == "E":
                    th = self._edge_threshold.get((r, c), 0.0)
                    color = _lerp(edge_sil, self._shield_live_color(th), act)
                elif char == "G":
                    color = _lerp(sil, inner(r, c, "G"), act)
                else:
                    color = _lerp(sil, pmap.COLORS.get(char, (255, 0, 255)), act)
                draw_rect(
                    surface, color, (int(x + c * scale), int(y + r * scale), cell, cell)
                )

        # 2) Placas (P): silhueta cinza → estrutura viva (fluxos/veias) com a ativação.
        for r, c, _ch, _px, _py in self._intact_cells:
            draw_rect(
                surface,
                _lerp(sil, inner(r, c, "P"), act),
                (int(x + c * scale), int(y + r * scale), cell, cell),
            )

        # 3) Núcleos: NADA na silhueta pura; ACENDEM conforme a ativação (brilho ↑).
        if act > 0.02:
            grid_w = pmap.PIXEL_COLS * scale
            grid_h = pmap.PIXEL_ROWS * scale
            intensity = (
                0.85 + 0.15 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0))
            ) * act
            for rx, ry, rr, theme, phase in self.SPHERE_DEFS:
                cx = int(x + rx * grid_w)
                cy = int(y + ry * grid_h) + _ORB_DROP_PX
                pmap.draw_plasma_sphere(
                    surface,
                    cx,
                    cy,
                    rr * grid_w,
                    theme,
                    phase,
                    intensity,
                    self.anim_time,
                )

    def _draw_pixel_map(
        self, surface: pygame.Surface, x: float, y: float, scale: float
    ) -> None:
        cell = int(scale + 1)
        inner = self._inner_cell_color  # bind local (hot path, §7)
        draw_rect = pygame.draw.rect

        # 1) CAMADA INTERNA — frame (G) com corrente energética + contorno-escudo (E).
        #    Cada "E" é desenhada por célula: escudo vivo = corrente neon fluindo; no
        #    colapso estilhaça pixel-a-pixel e DESAPARECE atrás da frente. Fase 2+: some.
        for r, row in enumerate(pmap.PIXEL_MAP_INTERNAL):
            for c, char in enumerate(row):
                if char == ".":
                    continue
                if char == "E":
                    color = self._edge_draw_color(r, c)
                    if color is None:
                        continue  # contorno estilhaçado/ausente → some da silhueta
                elif char == "G":
                    color = inner(r, c, "G")
                else:
                    color = pmap.COLORS.get(char, (255, 0, 255))
                draw_rect(
                    surface, color, (int(x + c * scale), int(y + r * scale), cell, cell)
                )

        # 2) CARCAÇA EXTERNA (placas P intactas) por cima — estrutura viva (fluxos +
        #    veias), não bloco cinza. Conforme caem, revelam o frame energizado.
        for r, c, _ch, _px, _py in self._intact_cells:
            draw_rect(
                surface,
                inner(r, c, "P"),
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
            return tuple(
                int(neon[i] + (hot[i] - neon[i]) * glow * 0.6) for i in range(3)
            )
        if self.state == _SHIELD_REBUILD:
            # Espelho do colapso: a célula REAPARECE quando a frente (inversa) a cruza.
            p = self._shield_rebuild_progress
            th = self._edge_threshold.get((r, c), 0.0)
            band = 0.10
            front = 1.0 - th  # reaparece quando p passa de (1 - th)
            if p >= front + band:  # já reconstruída → escudo vivo (corrente fluindo)
                return self._shield_live_color(th)
            if p >= front - band:  # frente de reconstrução → branco-quente
                return (225, 250, 255)
            return None  # ainda não reconstruída
        if self._shield_energy >= 1.0:  # escudo vivo: corrente energética circulando
            th = self._edge_threshold.get((r, c), 0.0)
            return self._shield_live_color(th)
        return None  # Fase 2+: contorno destruído, não desenha

    def _shield_live_color(self, th: float) -> tuple:
        """Cor da borda VIVA (corrente circulando) — delega à fonte única do `pmap`,
        compartilhada com os mini-Overlords (segmentos)."""
        return pmap.shield_live_color(th, self.anim_time)

    def _inner_cell_color(self, r: int, c: int, kind: str) -> tuple:
        """Cor energética de uma célula interna (placa/frame) — delega à fonte única
        do `pmap`, compartilhada com os mini-Overlords (segmentos)."""
        return pmap.inner_cell_color(r, c, kind, self.anim_time)

    def _draw_shield_arcs(self, surface: pygame.Surface) -> None:
        """Desenha os arcos elétricos do colapso (estado montado no update, §3)."""
        for pts in self._shield_arcs:
            if len(pts) >= 2:
                pygame.draw.lines(
                    surface,
                    (205, 248, 255),
                    False,
                    [(int(px), int(py)) for px, py in pts],
                    2,
                )

    def _orb_world_position(self, rx: float, ry: float) -> tuple[float, float]:
        """Posição ATUAL (mundo) de um orb — FONTE ÚNICA da hierarquia Boss→Orb.

        Deriva da posição do boss + offset visual do frame (flutuação/tremor) + as
        frações estruturais + o `_ORB_DROP_PX`. Usada pelo desenho do núcleo (full
        scale), pela ÂNCORA dos lasers e pelo split dos segmentos. Como o laser relê
        isto a cada frame, ele acompanha QUALQUER movimento do boss — nunca congela."""
        grid_w = pmap.PIXEL_COLS * self.PIXEL_SCALE
        grid_h = pmap.PIXEL_ROWS * self.PIXEL_SCALE
        offx, offy = self._draw_offset
        return (
            self.x + offx + rx * grid_w,
            self.y + offy + ry * grid_h + _ORB_DROP_PX,
        )

    def _draw_plasma_cores(
        self, surface: pygame.Surface, x: float, y: float, scale: float
    ) -> None:
        """Desenha os 3 núcleos com plasma vivo, posicionados no triângulo (1px abaixo)."""
        grid_w = pmap.PIXEL_COLS * scale
        grid_h = pmap.PIXEL_ROWS * scale
        intensity = 0.85 + 0.15 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0))
        for rx, ry, rr, theme, phase in self.SPHERE_DEFS:
            cx = int(x + rx * grid_w)
            cy = int(y + ry * grid_h) + _ORB_DROP_PX
            radius = rr * grid_w
            pmap.draw_plasma_sphere(
                surface, cx, cy, radius, theme, phase, intensity, self.anim_time
            )

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + 200

    def get_explosion_duration(self) -> float:
        return 4.0
