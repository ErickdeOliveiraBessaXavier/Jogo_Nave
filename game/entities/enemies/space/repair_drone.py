"""Drone Reconstrutor — inimigo "support" do bioma STARFIELD.

Não cura HP (inútil num bioma de enxame frágil): ele **remonta aliados
abatidos**. Quando um inimigo manufaturado morre perto do drone, fica uma
"sucata"; após `REBUILD_DELAY` o drone reconstrói aquele tipo no local, com um
feixe fabricador saindo dos braços. Enquanto o Reconstrutor viver, o encontro se
regenera — o counterplay é **priorizá-lo** (frágil, alvo claro). Aproveita
exatamente a fragilidade do bioma em vez de lutar contra ela.

Decisões de design (convenções do projeto):
  - §1 fronteiras: o drone só lê estado **público** dos aliados (`type`, `x/y`,
    `w/h`, `dead`, `aggressiveness_multiplier`) — nada de atributo privado;
  - §5 polimorfismo: a reconstrução re-instancia `type(ally)` (sem cascata de
    `isinstance` por tipo); meteoros (pooled, triviais) são excluídos por serem
    a única exceção de ciclo de vida — e "remontar uma rocha" não faz sentido;
  - spawn pelo buffer `ctx.new_enemies` (drenado pelo EntityManager após o loop,
    sem mutação concorrente), nunca tocando `entity_manager` direto.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

import pygame

from ....core.config import config as Config
from . import repair_drone_pixel_map as pm
from .._shared.enemy_hit_mixin import EnemyHitMixin
from .meteor import Meteor

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class RepairDrone(EnemyHitMixin):
    CELL = 3
    W = pm.PIXEL_COLS * CELL  # 57px (satélite largo: 19×13 células)
    H = pm.PIXEL_ROWS * CELL
    SIZE = W  # para compatibilidade com spawner.py

    HEALTH = 50
    POINTS = 240

    SPEED = 170.0
    FLEE_RADIUS = 240.0      # foge do jogador se mais perto que isso
    WATCH_RADIUS = 290.0     # mortes de aliados neste raio geram sucata
    KEEP_DISTANCE = 90.0     # distância que paira do alvo

    REBUILD_DELAY = 2.6      # tempo da sucata até a remontagem
    MAX_PENDING = 2          # remontagens simultâneas em fila (pacelamento)

    ENTER_DUR = 0.55         # duração do deploy de entrada (invulnerável)
    DEATH_DUR = 0.6          # duração do desmonte na morte

    _explosion_size_hit: int = 10
    _explosion_size_killed: int = 28

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        self.cell = self.CELL
        self.w = pm.PIXEL_COLS * self.cell
        self.h = pm.PIXEL_ROWS * self.cell
        self.x = float(x)
        self.y = float(y)
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 50
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.anim_time = 0.0
        self.bob_phase = random.uniform(0.0, math.tau)

        # Aliados vivos vigiados (id -> ref). Se um sai do raio vivo, é só drop;
        # se morre, vira sucata para reconstrução.
        self._watched: Dict[int, Any] = {}
        # Sucatas pendentes: dicts com type/x/y/w/h/aggr/side/timer/max.
        self._wrecks: List[Dict[str, Any]] = []
        # Anéis de conclusão (x, y, age) — feedback transiente da remontagem.
        self._rings: List[List[float]] = []

        # Ciclo de vida com animação: deploy de entrada e desmonte na morte.
        self._enter_t = 0.0   # 0→1 durante o deploy (invulnerável); 1 = operante
        self._dying = False   # em desmonte (já pontuou; aguarda fim da animação)
        self._death_t = 0.0   # 0→1 durante o desmonte; ao fim, dead=True

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        # Em desmonte a carcaça não colide (não come tiros nem leva re-hit).
        r = 0.0 if self._dying else self.w * 0.42
        return self.x + self.w / 2, self.y + self.h / 2, r

    @property
    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(
            ctx.sdt, ctx.player_x, ctx.player_y, ctx.other_enemies, ctx.new_enemies
        )

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        other_enemies: List[Any],
        out_new_enemies: List[Any],
    ) -> None:
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Desmonte: congela a IA e roda só a animação; ao fim marca para remoção.
        if self._dying:
            self._death_t = min(1.0, self._death_t + dt / self.DEATH_DUR)
            if self._death_t >= 1.0:
                self.dead = True
            return

        # Deploy de entrada: paira deployando (invulnerável) até abrir os painéis.
        if self._enter_t < 1.0:
            self._enter_t = min(1.0, self._enter_t + dt / self.ENTER_DUR)
            return

        cx, cy = self._center

        self._scan_for_wrecks(other_enemies, cx, cy)
        self._advance_rebuilds(dt, out_new_enemies)
        self._move(dt, cx, cy, player_x, player_y)

        # Decai anéis de conclusão.
        if self._rings:
            for ring in self._rings:
                ring[2] += dt
            self._rings = [r for r in self._rings if r[2] < 0.5]

        self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
        self.y = max(0.0, min(Config.SCREEN_HEIGHT * 0.72, self.y))

    def _is_rebuildable(self, e: Any) -> bool:
        """Aliado manufaturado e remontável: tem HP atacável, não é boss, não é
        outro Reconstrutor e não é meteoro (pooled / trivial)."""
        if e is self or isinstance(e, (RepairDrone, Meteor)):
            return False
        if getattr(e, "is_boss", False):
            return False
        return isinstance(getattr(e, "health", None), int)

    def _scan_for_wrecks(self, others: List[Any], cx: float, cy: float) -> None:
        """Atualiza os aliados vigiados; quem estava na mira e morreu vira sucata."""
        r2 = self.WATCH_RADIUS * self.WATCH_RADIUS
        near_now: Dict[int, Any] = {}
        for e in others:
            if getattr(e, "dead", False) or not self._is_rebuildable(e):
                continue
            ex = getattr(e, "x", cx) + getattr(e, "w", 0) / 2
            ey = getattr(e, "y", cy) + getattr(e, "h", 0) / 2
            if (ex - cx) ** 2 + (ey - cy) ** 2 <= r2:
                near_now[id(e)] = e

        for eid, ally in self._watched.items():
            if eid not in near_now and getattr(ally, "dead", False):
                self._register_wreck(ally)
        self._watched = near_now

    def _register_wreck(self, ally: Any) -> None:
        if len(self._wrecks) >= self.MAX_PENDING:
            return  # fila cheia: pacela a regeneração, não empilha sem limite
        self._wrecks.append(
            {
                "type": type(ally),
                "x": float(getattr(ally, "x", 0.0)),
                "y": float(getattr(ally, "y", 0.0)),
                "w": int(getattr(ally, "w", 30)),
                "h": int(getattr(ally, "h", 30)),
                "aggr": float(getattr(ally, "aggressiveness_multiplier", 1.0)),
                "side": bool(getattr(ally, "side_scroll", self.side_scroll)),
                "timer": self.REBUILD_DELAY,
                "max": self.REBUILD_DELAY,
            }
        )

    def _advance_rebuilds(self, dt: float, out_new_enemies: List[Any]) -> None:
        if not self._wrecks:
            return
        still: List[Dict[str, Any]] = []
        for w in self._wrecks:
            w["timer"] -= dt
            if w["timer"] > 0.0:
                still.append(w)
                continue
            inst = self._reconstruct(w)
            if inst is not None:
                out_new_enemies.append(inst)
                self._rings.append([w["x"] + w["w"] / 2, w["y"] + w["h"] / 2, 0.0])
        self._wrecks = still

    @staticmethod
    def _reconstruct(w: Dict[str, Any]) -> Any | None:
        """Re-instancia o tipo capturado e o posiciona no local da sucata.

        Construtores divergem no bioma: alguns recebem `(x, y, ...)`, outros só
        `aggressiveness_multiplier` (ex.: o Alien entra por conta própria). Tenta
        uma cadeia de assinaturas e, ao montar, **força `x`/`y`** para a posição
        da sucata — assim o aliado renasce onde caiu mesmo quando o construtor não
        aceita coordenadas. Nunca quebra o update: se nada funcionar, devolve None."""
        t = w["type"]
        aggr, side = w["aggr"], w["side"]
        attempts = (
            lambda: t(w["x"], w["y"], aggressiveness_multiplier=aggr, side_scroll=side),
            lambda: t(w["x"], w["y"], aggressiveness_multiplier=aggr),
            lambda: t(w["x"], w["y"]),
            lambda: t(aggressiveness_multiplier=aggr),
            lambda: t(),
        )
        inst: Any = None
        for make in attempts:
            try:
                inst = make()
                break
            except Exception:
                continue
        if inst is None:
            return None
        # Renasce no local da sucata (cobre construtores sem coordenadas).
        for attr in ("x", "y"):
            if hasattr(inst, attr):
                try:
                    setattr(inst, attr, w[attr])
                except Exception:
                    pass
        return inst

    def _move(
        self, dt: float, cx: float, cy: float, player_x: float, player_y: float
    ) -> None:
        pdx, pdy = cx - player_x, cy - player_y
        pdist = math.hypot(pdx, pdy)
        if pdist < self.FLEE_RADIUS and pdist > 1.0:
            # Foge do jogador (prioridade): mantém-se vivo para remontar.
            self.x += (pdx / pdist) * self.SPEED * dt
            self.y += (pdy / pdist) * self.SPEED * dt
            return

        target = self._tend_target(cx, cy)
        if target is not None:
            tx, ty = target
            dx, dy = tx - cx, ty - cy
            dist = math.hypot(dx, dy)
            if dist > self.KEEP_DISTANCE:
                self.x += (dx / dist) * self.SPEED * dt
                self.y += (dy / dist) * self.SPEED * dt
        else:
            # Sem nada para fazer: deriva suave numa banda alta.
            self.y += (90.0 - cy) * 0.4 * dt
            self.x += math.sin(self.anim_time * 0.8 + self.bob_phase) * 30.0 * dt

    def _tend_target(self, cx: float, cy: float) -> Tuple[float, float] | None:
        """Onde o drone quer pairar: junto da sucata mais antiga (a remontar) ou,
        sem sucata, perto do centroide dos aliados vigiados."""
        if self._wrecks:
            w = self._wrecks[0]
            return w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
        if self._watched:
            sx = sum(getattr(a, "x", cx) + getattr(a, "w", 0) / 2 for a in self._watched.values())
            sy = sum(getattr(a, "y", cy) + getattr(a, "h", 0) / 2 for a in self._watched.values())
            n = len(self._watched)
            return sx / n, sy / n
        return None

    # ── Dano / morte ──────────────────────────────────────────────────────────
    @property
    def _invulnerable(self) -> bool:
        """Não toma dano deployando (entrada) nem já em desmonte."""
        return self._dying or self._enter_t < 1.0

    def take_damage(self, amount: int) -> None:
        if self._invulnerable:
            return
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._begin_death()

    def _begin_death(self) -> None:
        """Entra em desmonte: para de remontar, vira carcaça que se despedaça.
        Não seta `dead` ainda — a remoção espera a animação terminar."""
        self._dying = True
        self._death_t = 0.0
        self._wrecks.clear()
        self._watched.clear()

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import NO_HIT, HitResult

        if self._invulnerable:
            return NO_HIT  # blindado no deploy; carcaça em desmonte ignora hits
        self.take_damage(damage)
        if self._dying:  # morreu agora: pontua/explode aqui, animação roda depois
            return HitResult(
                killed=True,
                points=self.POINTS,
                explosion_size=self._explosion_size_killed,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import NO_HIT, HitResult

        if self._invulnerable:
            return NO_HIT
        self._begin_death()
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render (§3: só lê estado) ───────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        parts = pm.build_parts(self.cell)
        cx, cy = self._center
        icx, icy = int(cx), int(cy)

        # Feixes fabricadores + remontagem (atrás do corpo).
        for w in self._wrecks:
            self._draw_assembly(surface, icx, icy, w)
        for ring in self._rings:
            self._draw_completion_ring(surface, ring)

        if self._dying:
            self._draw_parts_dying(surface, parts)
        elif self._enter_t < 1.0:
            self._draw_parts_entering(surface, parts)
        else:
            self._draw_parts_idle(surface, parts)

        # Bico de solda verde: ÚNICO ponto luminoso.
        if not self._dying:
            pulse = 0.5 + 0.5 * math.sin(self.anim_time * 5.0)
            boost = 0.7 if self._wrecks else 0.0
            emit_r = int(self.cell * (0.9 + 0.7 * pulse) + self.cell * 1.6 * boost)
            if self._enter_t < 1.0:
                emit_r = int(emit_r * self._enter_t)

            for c, r in pm.EMITTER_CELLS:
                self._blit_glow(
                    surface,
                    int(self.x + (c + 0.5) * self.cell),
                    int(self.y + (r + 0.5) * self.cell),
                    emit_r,
                    pm.WELD,
                )

    def _channel_intensity(self) -> float:
        """0 = sem canalização; senão 0.4→1.0 conforme a remontagem mais avançada.
        Dá um estado visual imediatamente distinto durante a ressurreição."""
        if not self._wrecks:
            return 0.0
        progress = max(1.0 - w["timer"] / w["max"] for w in self._wrecks)
        return 0.4 + 0.6 * progress

    def _draw_parts_idle(self, surface: pygame.Surface, parts: Dict[str, pygame.Surface]) -> None:
        """Operante: asas com leve drift. Durante a ressurreição as asas entram
        em estado de canalização (verde + tremor + brilho crescente)."""
        cell = self.cell
        drift = math.sin(self.anim_time * 2.0 + self.bob_phase) * 3.0
        flash = self.hit_timer > 0.0

        def draw_part(surf: pygame.Surface, ox: float, oy: float):
            if flash:
                surf = surf.copy()
                surf.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(surf, (int(self.x + ox), int(self.y + oy)))

        draw_part(parts["body"], 7 * cell, 0)
        draw_part(parts["left_mast"], 6 * cell, drift * 0.3)
        draw_part(parts["right_mast"], 12 * cell, drift * 0.3)

        channel = self._channel_intensity()
        if channel > 0.0:
            self._draw_channeling_wings(surface, parts, channel, drift)
        else:
            draw_part(parts["left_wing"], 0 * cell - drift, drift * 0.5)
            draw_part(parts["right_wing"], 13 * cell + drift, drift * 0.5)

    def _draw_channeling_wings(
        self,
        surface: pygame.Surface,
        parts: Dict[str, pygame.Surface],
        channel: float,
        drift: float,
    ) -> None:
        """Asas durante a ressurreição: cross-fade azul→verde, tremor constante
        de alta frequência e aura verde que cresce com o progresso."""
        cell = self.cell
        charged = pm.build_charged_wings(cell)
        amp = 1.0 + 2.5 * channel
        vib = math.sin(self.anim_time * 46.0) * amp
        vib_y = math.sin(self.anim_time * 39.0 + 1.3) * amp * 0.5
        green_a = int(255 * min(1.0, channel))
        aura_r = int(cell * (1.5 + 4.5 * channel))
        for key, base_ox, wing_mid in (
            ("left_wing", 0 * cell - drift, 3 * cell),
            ("right_wing", 13 * cell + drift, 16 * cell),
        ):
            px = int(self.x + base_ox + vib)
            py = int(self.y + drift * 0.5 + vib_y)
            surface.blit(parts[key], (px, py))            # azul base
            g = charged[key].copy()
            g.set_alpha(green_a)
            surface.blit(g, (px, py))                     # verde carregado por cima
            self._blit_glow(                              # aura crescente
                surface,
                int(self.x + wing_mid + vib),
                int(self.y + self.h / 2),
                aura_r,
                pm.WELD,
            )

    def _draw_parts_entering(self, surface: pygame.Surface, parts: Dict[str, pygame.Surface]) -> None:
        """Nascimento: a entidade é montada por energia — o núcleo surge primeiro,
        partículas convergem, as estruturas formam, as asas materializam e o
        brilho sobe até o estado operacional."""
        t = self._enter_t
        cell = self.cell
        cx, cy = self._center
        icx, icy = int(cx), int(cy)

        def phase(a: float, b: float) -> float:
            return max(0.0, min(1.0, (t - a) / (b - a)))

        # 1) Núcleo de energia surge primeiro e cresce (pulsante).
        core_p = phase(0.0, 0.35)
        if core_p > 0.0:
            wob = 0.85 + 0.15 * math.sin(self.anim_time * 18.0)
            self._blit_glow(surface, icx, icy, int(cell * (0.8 + 4.0 * core_p) * wob), pm.WELD)

        # 2) Partículas energéticas convergem para o núcleo (aditivas).
        conv = phase(0.0, 0.55)
        if conv < 1.0:
            for i in range(10):
                ang = i / 10 * math.tau + self.anim_time * 2.5
                dist = (1.0 - conv) * (38.0 + 26.0 * (i % 3))
                a = max(0, min(255, int(900 * conv * (1.0 - conv))))
                if a <= 0:
                    continue
                col = (140, 255, 200) if i % 2 else (90, 255, 150)
                dot = pygame.Surface((4, 4), pygame.SRCALPHA)
                pygame.draw.circle(dot, (*col, a), (2, 2), 2)
                surface.blit(
                    dot,
                    (int(icx + math.cos(ang) * dist) - 2, int(icy + math.sin(ang) * dist * 0.7) - 2),
                    special_flags=pygame.BLEND_RGBA_ADD,
                )

        # 3) Corpo materializa.
        body_a = int(255 * phase(0.25, 0.6))
        if body_a > 0:
            body = parts["body"].copy()
            body.set_alpha(body_a)
            surface.blit(body, (int(self.x + 7 * cell), int(self.y)))

        # 4) Mastros (estruturas externas) formam.
        mast_a = int(255 * phase(0.45, 0.72))
        if mast_a > 0:
            lm, rm = parts["left_mast"].copy(), parts["right_mast"].copy()
            lm.set_alpha(mast_a)
            rm.set_alpha(mast_a)
            surface.blit(lm, (int(self.x + 6 * cell), int(self.y)))
            surface.blit(rm, (int(self.x + 12 * cell), int(self.y)))

        # 5) Asas materializam progressivamente (com leve deslize de fora).
        wing_p = phase(0.6, 1.0)
        if wing_p > 0.0:
            wa = int(255 * wing_p)
            slide = (1.0 - self._ease_out_back(wing_p)) * 24.0
            lw, rw = parts["left_wing"].copy(), parts["right_wing"].copy()
            lw.set_alpha(wa)
            rw.set_alpha(wa)
            surface.blit(lw, (int(self.x - slide), int(self.y)))
            surface.blit(rw, (int(self.x + 13 * cell + slide), int(self.y)))

        # 6) Anel de warp no fim (snap operacional).
        if t > 0.7:
            self._draw_warp_ring(surface, cx, cy, phase(0.7, 1.0))

    def _draw_parts_dying(self, surface: pygame.Surface, parts: Dict[str, pygame.Surface]) -> None:
        """Morte = montagem ao contrário: as asas perdem estabilidade e se soltam
        primeiro, depois mastros e corpo se desintegram, e o núcleo de energia
        colapsa por último num estouro."""
        t = self._death_t
        cell = self.cell
        icx, icy = int(self._center[0]), int(self._center[1])

        def phase(a: float, b: float) -> float:
            return max(0.0, min(1.0, (t - a) / (b - a)))

        # (parte, centro_x, centro_y, dirX, dirY, giro°, início do desprendimento)
        specs = (
            ("left_wing", 3 * cell, 6.5 * cell, -1.3, -0.4, -170, 0.00),
            ("right_wing", 16 * cell, 6.5 * cell, 1.3, -0.4, 170, 0.06),
            ("left_mast", 6.5 * cell, 6.5 * cell, -0.6, 0.7, -90, 0.22),
            ("right_mast", 12.5 * cell, 6.5 * cell, 0.6, 0.7, 90, 0.22),
            ("body", 9.5 * cell, 6.5 * cell, 0.0, 1.1, 70, 0.36),
        )
        for key, cox, coy, dx, dy, spin, start in specs:
            lp = phase(start, min(1.0, start + 0.55))  # progresso de soltura da peça
            alpha = max(0, int(255 * (1.0 - lp)))
            if alpha <= 0:
                continue
            # Preso: vibra perdendo estabilidade. Solto: voa girando para fora.
            instab = 0.5 + 0.5 * (1.0 - lp)
            jx = math.sin(self.anim_time * 52.0 + start * 30.0) * 2.0 * instab
            jy = math.cos(self.anim_time * 47.0 + start * 30.0) * 2.0 * instab
            spread = 95.0 * (lp ** 1.6)
            rot = pygame.transform.rotozoom(parts[key].copy(), spin * lp, 1.0)
            rot.set_alpha(alpha)
            px = self.x + cox + dx * spread + jx
            py = self.y + coy + dy * spread + jy
            surface.blit(rot, (int(px - rot.get_width() / 2), int(py - rot.get_height() / 2)))

        # Energia dissipando: faíscas saindo do núcleo.
        for i in range(int(5 * (1.0 - t)) + 2):
            ang = i * 2.39963 + self.anim_time * 3.0
            rad = 90.0 * (t ** 1.3) * (0.5 + 0.25 * (i % 3))
            col = (200, 255, 220) if i % 2 else (90, 255, 150)
            pygame.draw.circle(
                surface, col,
                (int(icx + math.cos(ang) * rad), int(icy + math.sin(ang) * rad)), 1,
            )

        # Núcleo de energia: persiste no centro e colapsa por último.
        collapse = phase(0.5, 1.0)
        if collapse < 1.0:
            wob = 0.85 + 0.15 * math.sin(self.anim_time * 30.0)
            core_r = int(cell * (4.0 * (1.0 - collapse) + 0.6) * wob)
            if core_r > 0:
                self._blit_glow(surface, icx, icy, core_r, pm.WELD)

        # Pop final no instante do colapso do núcleo.
        pop = phase(0.85, 1.0)
        if 0.0 < pop < 1.0:
            self._blit_glow(surface, icx, icy, int(cell * (3 + 11 * pop)), (210, 255, 225))

    def _draw_warp_ring(self, surface: pygame.Surface, cx: float, cy: float, t: float) -> None:
        radius = int(8 + 52 * t)
        a = int(170 * (1.0 - t))
        if a > 0:
            surf = pygame.Surface((radius*2+4, radius*2+4), pygame.SRCALPHA)
            pygame.draw.circle(surf, (140, 255, 210, a), (radius+2, radius+2), radius, 2)
            surface.blit(surf, (int(cx)-radius-2, int(cy)-radius-2), special_flags=pygame.BLEND_RGBA_ADD)

    # ── Helpers de render ───────────────────────────────────────────────────────
    @staticmethod
    def _ease_out_back(t: float) -> float:
        """Easing com leve overshoot (snap de atracagem das asas)."""
        c1 = 1.70158
        c3 = c1 + 1.0
        u = t - 1.0
        return 1.0 + c3 * u * u * u + c1 * u * u

    def _blit_glow(
        self, surface: pygame.Surface, cx: int, cy: int, radius: int, color: pm.RGB
    ) -> None:
        glow = pm.get_glow(radius, color)
        surface.blit(
            glow, (cx - radius, cy - radius), special_flags=pygame.BLEND_RGBA_ADD
        )

    def _draw_assembly(
        self, surface: pygame.Surface, icx: int, icy: int, w: Dict[str, Any]
    ) -> None:
        """Feixe do braço até a sucata + chassi-fantasma que cresce até remontar."""
        progress = 1.0 - max(0.0, w["timer"]) / w["max"]  # 0 → 1
        wx = int(w["x"] + w["w"] / 2)
        wy = int(w["y"] + w["h"] / 2)

        # Feixe fabricador (pisca com a fabricação).
        if random.random() < 0.85:
            beam = (140, 255, 200) if random.random() < 0.5 else pm.WELD
            pygame.draw.line(surface, beam, (icx, icy), (wx, wy), 1)

        # Chassi-fantasma: retângulo verde que sobe de pequeno ao tamanho real.
        bw = max(2, int(w["w"] * (0.25 + 0.75 * progress)))
        bh = max(2, int(w["h"] * (0.25 + 0.75 * progress)))
        rect = pygame.Rect(0, 0, bw, bh)
        rect.center = (wx, wy)
        alpha = int(70 + 150 * progress)
        ghost = pygame.Surface((bw + 2, bh + 2), pygame.SRCALPHA)
        pygame.draw.rect(ghost, (*pm.WELD, alpha), (1, 1, bw, bh), 1)
        for _ in range(2):  # faíscas de montagem
            sx = random.randint(1, bw)
            sy = random.randint(1, bh)
            ghost.fill((180, 255, 215, alpha), (sx, sy, 1, 1))
        surface.blit(
            ghost, (rect.x - 1, rect.y - 1), special_flags=pygame.BLEND_RGBA_ADD
        )

    def _draw_completion_ring(
        self, surface: pygame.Surface, ring: List[float]
    ) -> None:
        f = ring[2] / 0.5  # 0 → 1
        radius = int(8 + 46 * f)
        alpha = int(180 * (1.0 - f))
        if radius < 2 or alpha <= 0:
            return
        size = radius * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*pm.WELD, alpha), (radius + 2, radius + 2), radius, 2)
        surface.blit(
            surf,
            (int(ring[0]) - radius - 2, int(ring[1]) - radius - 2),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

