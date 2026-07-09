"""Gravity Well — "Poço Gravitacional" do bioma STARFIELD.

Papel `area_denial` (inédito no Espaço). Uma **singularidade compacta** que
**ancora** num ponto (não desce) e controla aquela região da tela. Em ciclo:
`entra → ancora → carrega (telegraph) → puxa → cooldown`. Durante o PUXÃO:

  - **arrasta a nave** para o centro (força radial com falloff) e **curva a
    trajetória dos projéteis** (jogador e inimigos) que cruzam o campo — ambos
    emitidos em `ctx.new_gravity_wells` e aplicados pela cena ao movimento; e
  - **causa dano contínuo** no núcleo via `ctx.new_area_blasts` (mesmo roteador
    de dano de área da mina / CyberTank / CyberCaptor).

Counterplay: sair do raio de influência (telegrafado por um anel fino) ou
destruí-la — a atração é vencível acelerando para fora.

Visual (anomalia gravitacional ATIVA, não um círculo estático): sobre a
singularidade escura, um campo de **anéis concêntricos** que **nascem no centro,
expandem e são absorvidos pelo horizonte externo** — quando um some, outro
nasce, num loop infinito (matéria se formando/sendo consumida). Anéis
levemente ovalados que "respiram" (distorção de lente), pulsação global e cor
que esquenta com a intensidade do campo (frio em cooldown → quente no puxão).
Sóbrio: 1px por anel, alpha discreto, sem bloom aditivo.

Contratos: herda `EnemyHitMixin` (§9); update via `update_in_context` (§5);
`draw` sem efeitos colaterais (fases avançadas no update — §3); dano/força por
buffers do contexto.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import space_palette as pal
from .gravity_well_pixel_map import PIXEL_COLS, PIXEL_ROWS, build_disc_surface

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext

# Emissão de puxão: (cx, cy, raio_influência, força_nave_px_s, curva_projéteis_px_s2, self).
# A cena arrasta a nave (força) e curva a trajetória dos projéteis (curva).
GravityPull = Tuple[float, float, float, float, float, Any]


class GravityWell(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 52px de corpo

    HEALTH: int = 120
    POINTS: int = 300

    # ── Ancoragem (não desce; fixa num ponto, com leve bob) ──────────────────
    ENTER_DURATION: float = 0.9  # deslize temporal do spawn até a âncora
    BOB_AMPL: float = 5.0

    # ── Ciclo de atração ─────────────────────────────────────────────────────
    AIM_TIME: float = 1.0        # telegraph antes de puxar
    PULL_TIME: float = 2.6       # janela de atração ativa
    COOLDOWN: float = 1.8
    DAMAGE_INTERVAL: float = 0.30  # cadência do dano no núcleo

    INFLUENCE_RADIUS: float = 180.0  # raio que arrasta a nave (campo perceptível ao passar perto)
    CORE_DAMAGE_RADIUS: float = 52.0  # raio interno que causa dano
    PULL_SPEED: float = 400.0        # força máx. de arrasto (px/s no centro; > velocidade base da nave, 250)
    # Curvatura dos projéteis: aceleração radial (px/s²) somada à velocidade dos
    # tiros no campo. A velocidade é renormalizada ao módulo original (só CURVA a
    # rota, não muda o módulo) — desvio gravitacional natural, não um "ímã".
    PROJECTILE_BEND: float = 1400.0

    # ── Vórtice (braços em espiral de Arquimedes que giram e engolem matéria) ──
    # Braços PERMANENTES que giram em velocidade constante (nunca reiniciam); o
    # fluxo p/ dentro vem de bandas de brilho que viajam rumo ao núcleo e as
    # pontas somem por fade (envelope) — sem nascer/sumir abrupto nem teleporte.
    ARM_COUNT: int = 4               # braços simultâneos para cobrir de forma densa e uniforme
    ARM_TURNS: float = 1.8          # voltas completas de cada braço (enrolamento)
    ARM_SEGMENTS: int = 40           # resolução maior para manter o traço suave nas bordas externas
    ARM_ROT_SPEED: float = 0.5       # giro contínuo do vórtice (× spin)
    ARM_FLOW_SPEED: float = 1.7      # velocidade das bandas de brilho rumo ao centro
    ARM_FLOW_WAVES: float = 2.2      # número de bandas ao longo do braço estendido
    ARM_EDGE: float = 0.15           # fração das pontas em fade (transição suave)

    _explosion_size_killed: int = 30
    _explosion_size_hit: int = 8

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
        anchor: Tuple[float, float] | None = None,
    ) -> None:
        self.side_scroll: bool = side_scroll
        self.cell: int = self.CELL
        self.w: int = PIXEL_COLS * self.cell
        self.h: int = PIXEL_ROWS * self.cell

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health: int = self.HEALTH
        self.active: bool = True
        self.aggressiveness_multiplier: float = max(0.5, aggressiveness_multiplier)

        # Ponto fixo onde ancora (clampeado à zona jogável, não no fundo da tela).
        ax, ay = anchor if anchor is not None else (x, max(y, Config.SCREEN_HEIGHT * 0.30))
        margin = self.INFLUENCE_RADIUS * 0.35
        self.anchor_x: float = max(margin, min(Config.SCREEN_WIDTH - margin, ax))
        self.anchor_y: float = max(
            margin, min(Config.SCREEN_HEIGHT * 0.72, ay)
        )
        self.spawn_x: float = float(x)
        self.spawn_y: float = float(y)
        self.enter_t: float = 0.0
        self.entering: bool = True

        self.state: str = "cooldown"
        self.aim_timer: float = 0.0
        self.pull_timer: float = 0.0
        self.cooldown_timer: float = self.COOLDOWN * 0.5
        self.dmg_timer: float = 0.0

        self.spin: float = random.uniform(0.0, math.tau)  # rotação da matéria
        self.bob_phase: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

        # Animação da anomalia (avançada no update — draw só lê, §3).
        self.warp: float = random.uniform(0.0, math.tau)  # distorção/pulsação
        self.field: float = 0.45   # intensidade 0..1 (baixa em cooldown, alta no puxão)
        self._field_surf: pygame.Surface | None = None  # scratch reusado (sem alloc/frame)
        
        # Scratch surfaces dos braços e partículas em 3D (§7)
        self._vortex_back_surf: pygame.Surface | None = None
        self._vortex_front_surf: pygame.Surface | None = None
        
        # Partículas de poeira e matéria espaciais sendo sugadas (densidade adequada ao raio expandido)
        self.particles: List[List[float]] = [[0.0, 0.0, 0.0, 0, 0.0] for _ in range(45)]
        for i in range(45):
            self._reset_particle(i, random.uniform(0.0, 0.95))
            
        # Sinalização física: True quando está puxando ativamente um projétil ou nave
        self.is_pulling_something: bool = False

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.42

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def _pulling(self) -> bool:
        return self.state == "pull"

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        blast, pull = self.update(ctx.sdt)
        if blast is not None:
            ctx.new_area_blasts.append(blast)
        if pull is not None:
            ctx.new_gravity_wells.append(pull)

    def _reset_particle(self, idx: int, initial_u: float = 0.0) -> None:
        """Inicializa ou reseta uma partícula na borda externa do poço (ou dispersa no início)."""
        self.particles[idx][0] = initial_u                       # u (0.0 = borda externa, 1.0 = horizonte)
        self.particles[idx][1] = random.uniform(0.0, math.tau)     # ângulo
        self.particles[idx][2] = random.uniform(0.8, 1.4)         # multiplicador de velocidade
        self.particles[idx][3] = random.choice([1, 2])            # tamanho em px
        self.particles[idx][4] = random.random()                  # fator de cor/brilho

    def update(
        self, dt: float
    ) -> Tuple[Tuple[float, float, float] | None, GravityPull | None]:
        if dt <= 0.0:
            return None, None

        # Giro contínuo que acelera na fase de aviso (aim) e atração ativa (pull)
        # Se estiver puxando algo ativamente na física, a rotação acelera temporariamente p/ velocidade máxima!
        spin_speed = 1.2
        if self.state == "aim":
            spin_speed = 2.2
        elif self.state == "pull":
            if getattr(self, "is_pulling_something", False):
                spin_speed = 7.5
            else:
                spin_speed = 4.0
        self.spin += dt * spin_speed
        
        self.bob_phase += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Animação da anomalia (avançada no update — draw só lê, §3).
        self.warp += dt
        target = 1.0 if self.state in ("aim", "pull") else 0.45
        self.field += (target - self.field) * min(1.0, dt * 2.5)

        # Atualizar partículas de acreção (inward spiral)
        # Velocidade de fluxo escala com a intensidade do campo (field)
        flow_mult = 0.4 + 0.6 * self.field
        for i in range(len(self.particles)):
            p = self.particles[i]
            # Avança para dentro (u de 0.0 a 1.0)
            p[0] += dt * 0.22 * p[2] * flow_mult
            if p[0] >= 1.0:
                self._reset_particle(i, 0.0)
                continue
            
            # Gira mais rápido à medida que cai (conservação de momento angular)
            ang_speed = (1.8 + 5.0 * p[0]) * p[2] * flow_mult
            p[1] += dt * ang_speed

        # Posição: desliza do spawn até a âncora (smoothstep temporal), depois bob.
        bob = math.sin(self.bob_phase * 1.4) * self.BOB_AMPL
        tx = self.anchor_x - self.w / 2
        ty = self.anchor_y - self.h / 2 + bob
        if self.entering:
            self.enter_t += dt
            p = min(1.0, self.enter_t / self.ENTER_DURATION)
            e = p * p * (3.0 - 2.0 * p)
            self.x = self.spawn_x + (tx - self.spawn_x) * e
            self.y = self.spawn_y + (ty - self.spawn_y) * e
            if p >= 1.0:
                self.entering = False
            return None, None
        self.x, self.y = tx, ty

        cx, cy = self._center()
        blast: Tuple[float, float, float] | None = None
        pull: GravityPull | None = None

        if self.state == "cooldown":
            self.cooldown_timer -= dt
            if self.cooldown_timer <= 0.0:
                self.state = "aim"
                self.aim_timer = self.AIM_TIME
        elif self.state == "aim":
            self.aim_timer -= dt
            if self.aim_timer <= 0.0:
                self.state = "pull"
                self.pull_timer = self.PULL_TIME
                self.dmg_timer = 0.0
        else:  # pull
            self.pull_timer -= dt
            pull = (cx, cy, self.INFLUENCE_RADIUS, self.PULL_SPEED, self.PROJECTILE_BEND, self)
            self.dmg_timer -= dt
            if self.dmg_timer <= 0.0:
                self.dmg_timer = self.DAMAGE_INTERVAL / self.aggressiveness_multiplier
                blast = (cx, cy, self.CORE_DAMAGE_RADIUS)
            if self.pull_timer <= 0.0:
                self.state = "cooldown"
                self.cooldown_timer = self.COOLDOWN

        return blast, pull

    # ── Dano / morte ────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def should_remove(self) -> bool:
        return self.dead

    # ── Render (sóbrio: sem bloom aditivo de várias camadas) ──────────────────
    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center()
        icx, icy = int(cx), int(cy)

        # Anomalia: limite circular do campo gravitacional físico.
        self._draw_field(surface, icx, icy)

        # Disco de acreção: passagem 1 (braços e partículas atrás do núcleo).
        self._draw_accretion_disk(surface, cx, cy, "back")

        # Posição de desenho da singularidade com vibração se estiver instável (aim/pull).
        shake_x = 0
        shake_y = 0
        if getattr(self, "is_pulling_something", False):
            # Vibração caótica em atração máxima física
            shake_x = random.randint(-3, 3)
            shake_y = random.randint(-3, 3)
        elif self.state == "aim":
            shake_x = random.randint(-1, 1)
            shake_y = random.randint(-1, 1)
        elif self.state == "pull":
            shake_x = random.randint(-2, 2)
            shake_y = random.randint(-2, 2)

        # Singularidade (disco colapsado) por cima. Flash de hit discreto.
        base = build_disc_surface(self.cell)
        core_pos_x = int(self.x) + shake_x
        core_pos_y = int(self.y) + shake_y
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((60, 66, 78), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (core_pos_x, core_pos_y))
        else:
            surface.blit(base, (core_pos_x, core_pos_y))

        # Anel de Einstein (luz distorcida ao redor do horizonte de eventos).
        self._draw_einstein_ring(surface, icx + shake_x, icy + shake_y)

        # Disco de acreção: passagem 2 (braços e partículas na frente do núcleo).
        self._draw_accretion_disk(surface, cx, cy, "front")

        # Núcleo: aro que esquenta e pulsa em tamanho/cor com a intensidade.
        core_r = max(2, int(self.cell * 1.5))
        if getattr(self, "is_pulling_something", False):
            # Pulsação severa de alta frequência na atração ativa
            core_r += int(2.5 * math.sin(self.warp * 18.0))
        elif self.state == "pull":
            core_r += int(1.2 * math.sin(self.warp * 12.0))
            
        pygame.draw.circle(surface, pal.CORE_DARK, (icx + shake_x, icy + shake_y), core_r)
        rim = pal.lerp(pal.CORE_RIM, pal.CORE_HOT, self.field)
        pygame.draw.circle(surface, rim, (icx + shake_x, icy + shake_y), core_r, 1)

    def _draw_field(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        """Desenha o limite externo circular do campo gravitacional, servindo como a
        referência visual exata para o raio de influência (INFLUENCE_RADIUS).
        """
        R = int(self.INFLUENCE_RADIUS)
        size = R * 2 + 8
        surf = self._field_surf
        if surf is None or surf.get_width() != size:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            self._field_surf = surf
        else:
            surf.fill((0, 0, 0, 0))  # reusa (§7)
            
        fc = size // 2
        warp, intensity = self.warp, self.field
        
        # Cor baseada no estado da anomalia (frio -> aviso âmbar -> puxão quente)
        base_col = pal.ACCENT_COLD
        hot_col = pal.CORE_HOT if self.state != "aim" else pal.WARNING_AMBER
        
        # O limite pulsa sutilmente em opacidade, muito mais forte se estiver puxando
        if getattr(self, "is_pulling_something", False):
            alpha = int((65 + 100 * intensity) * (0.65 + 0.35 * math.sin(warp * 4.0)))
            col = pal.lerp(pal.WARNING_AMBER, pal.CORE_HOT, 0.4 + 0.6 * math.sin(warp * 5.0))
        else:
            alpha = int((35 + 55 * intensity) * (0.7 + 0.3 * math.sin(warp * 2.0)))
            col = pal.lerp(base_col, hot_col, intensity)
            
        alpha = max(0, min(255, alpha))
        
        if alpha > 0:
            # Círculo perfeito coincidindo exatamente com a área física de efeito
            pygame.draw.circle(surf, (*col, alpha), (fc, fc), R, 1)
            
            # Anel interno de reforço da borda
            if intensity > 0.6 or getattr(self, "is_pulling_something", False):
                inner_alpha = int(alpha * 0.5) if getattr(self, "is_pulling_something", False) else int(alpha * 0.4)
                pygame.draw.circle(surf, (*col, inner_alpha), (fc, fc), R - 3, 1)

        surface.blit(surf, (icx - fc, icy - fc))

    def _draw_einstein_ring(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        """Desenha o Anel de Einstein (luz distorcida pela gravidade esférica).
        
        Ele é mantido circular porque o campo de gravidade é esférico, mas pulsa
        e distorce levemente em alta frequência para passar a ideia de instabilidade.
        """
        r_base = self.w * 0.42  # cerca de 22px
        num_points = 24
        points = []
        warp_val = self.warp * 6.5
        intensity = self.field
        
        # Cor de aviso ou calor intenso
        base_col = pal.ACCENT_COLD
        hot_col = pal.CORE_HOT if self.state != "aim" else pal.WARNING_AMBER
        
        # Intensifica a opacidade e oscilação sob atração ativa
        if getattr(self, "is_pulling_something", False):
            col = pal.lerp(pal.CORE_HOT, pal.WARNING_AMBER, 0.4)
            flicker_freq = 22.0  # Oscilação ultra veloz
            alpha = int(180 + 75 * math.sin(self.warp * flicker_freq))
        else:
            col = pal.lerp(base_col, hot_col, intensity)
            flicker_freq = 15.0 if self.state in ("aim", "pull") else 6.0
            alpha = int(120 + 80 * math.sin(self.warp * flicker_freq) * intensity)
            
        alpha = max(0, min(255, alpha))
        
        for i in range(num_points + 1):
            theta = (i / num_points) * math.tau
            # Pequena ondulação de refração gravitacional
            r_offset = 1.2 * math.sin(6.0 * theta + warp_val) * intensity
            r = r_base + r_offset
            px = icx + int(r * math.cos(theta))
            py = icy + int(r * math.sin(theta))
            points.append((px, py))
            
        r_max = int(r_base + 4)
        surf_size = r_max * 2 + 4
        ring_surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        fc = surf_size // 2
        
        local_points = [(x - icx + fc, y - icy + fc) for x, y in points]
        pygame.draw.lines(ring_surf, (*col, alpha), False, local_points, 1)
        surface.blit(ring_surf, (icx - fc, icy - fc))

    def _draw_accretion_disk(
        self, surface: pygame.Surface, cx: float, cy: float, pass_type: str
    ) -> None:
        """Desenha o disco de acreção (braços em espiral e partículas orbitantes)
        dividido em duas passagens para criar um efeito volumétrico 3D.
        
        Usa uma espiral de Arquimedes para distribuir as espirais de forma perfeitamente
        uniforme do núcleo até o raio de influência exato (INFLUENCE_RADIUS).
        
        - 'back': desenha os segmentos e partículas que estão atrás do núcleo (z <= 0).
        - 'front': desenha os segmentos e partículas que passam na frente (z > 0).
        """
        cos, sin, tau = math.cos, math.sin, math.tau
        R = self.INFLUENCE_RADIUS
        r_min = self.w * 0.34
        if R <= r_min:
            return

        size = int(R * 2) + 6
        
        # Selecionar e iniciar/limpar a scratch surface correspondente
        surf = self._vortex_front_surf if pass_type == "front" else self._vortex_back_surf
        if surf is None or surf.get_width() != size:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            if pass_type == "front":
                self._vortex_front_surf = surf
            else:
                self._vortex_back_surf = surf
        else:
            surf.fill((0, 0, 0, 0))
            
        fc = size // 2
        cos_tilt = 0.82  # inclinação de ~35 graus
        sin_tilt = 0.57
        
        base_rot = self.spin * self.ARM_ROT_SPEED
        flow = self.warp * self.ARM_FLOW_SPEED
        span = self.ARM_TURNS * tau
        wave_k = self.ARM_FLOW_WAVES * tau
        edge = self.ARM_EDGE
        seg = self.ARM_SEGMENTS
        
        peak = int(105 * self.field)
        if getattr(self, "is_pulling_something", False):
            peak = int(170 * self.field)  # Brilho muito maior em overdrive!
            
        if peak <= 0:
            return
            
        cold = pal.ACCENT_COLD_DIM
        warm = pal.lerp(pal.ACCENT_COLD, pal.CORE_HOT, 0.5 * self.field)
        
        # Sinalização visual baseada no estado e puxão ativo
        if getattr(self, "is_pulling_something", False):
            # Estado ativo de sobredimensão / overdrive: brilho misto quente/âmbar
            warm = pal.lerp(pal.CORE_HOT, pal.WARNING_AMBER, 0.3 + 0.3 * math.sin(flow * 2.0))
            cold = pal.lerp(pal.ACCENT_COLD, pal.CORE_HOT, 0.5)
        elif self.state == "aim":
            warm = pal.lerp(warm, pal.WARNING_AMBER, 0.8)
            cold = pal.lerp(cold, pal.WARNING_AMBER_DIM, 0.5)
        elif self.state == "pull":
            warm = pal.lerp(warm, pal.CORE_HOT, 0.9)
            cold = pal.lerp(cold, pal.ACCENT_COLD, 0.5)

        # ── PASSAGEM 1: Braços espirais (Arquimedes para distribuição uniforme) ──────
        for k in range(self.ARM_COUNT):
            arm_off = k * (tau / self.ARM_COUNT)
            px = py = 0
            pb = 0.0
            pz = 0.0  # profundidade do ponto anterior
            for i in range(seg + 1):
                u = i / seg                      # 0 = limite externo, 1 = núcleo
                ang = base_rot + arm_off + u * span   # enrola rumo ao centro
                
                # Espiral de Arquimedes: interpolação linear do raio
                rad = R - u * (R - r_min)
                
                x_local = rad * cos(ang)
                y_local = rad * sin(ang)
                x = int(fc + x_local)
                y = int(fc + y_local * cos_tilt)
                z = y_local * sin_tilt
                
                # Envelope de fade suave nas pontas
                fa = u / edge
                if fa > 1.0:
                    fa = 1.0
                fb = (1.0 - u) / edge
                if fb > 1.0:
                    fb = 1.0
                env = (fa * fa * (3.0 - 2.0 * fa)) * (fb * fb * (3.0 - 2.0 * fb))
                
                wave = 0.5 + 0.5 * sin(u * wave_k - flow + arm_off)
                bright = env * (0.4 + 0.6 * wave)
                
                if i > 0:
                    a = int(peak * 0.55 * (bright + pb))
                    if a > 0:
                        # Selecionar segmentos com base na profundidade média
                        avg_z = (z + pz) / 2.0
                        is_front_pass = pass_type == "front"
                        is_front_segment = avg_z > 0.0
                        if is_front_pass == is_front_segment:
                            col = pal.lerp(cold, warm, u)
                            pygame.draw.line(surf, (*col, a), (px, py), (x, y), 1)
                            
                px, py, pb, pz = x, y, bright, z

        # ── PASSAGEM 2: Partículas orbitantes ────────────────────────────────
        for p in self.particles:
            u_part, ang_part, speed_p, size_p, col_f = p
            # Espiral de Arquimedes para as partículas também
            rad = R - u_part * (R - r_min)
            
            x_local = rad * cos(ang_part)
            y_local = rad * sin(ang_part)
            x = int(fc + x_local)
            y = int(fc + y_local * cos_tilt)
            z = y_local * sin_tilt
            
            is_front_pass = pass_type == "front"
            is_front_particle = z > 0.0
            if is_front_pass != is_front_particle:
                continue
                
            # Fade out nas bordas interna e externa
            fa = u_part / edge
            if fa > 1.0:
                fa = 1.0
            fb = (1.0 - u_part) / edge
            if fb > 1.0:
                fb = 1.0
            env = (fa * fa * (3.0 - 2.0 * fa)) * (fb * fb * (3.0 - 2.0 * fb))
            
            a = int(peak * env * (0.7 + 0.3 * col_f))
            if a <= 0:
                continue
                
            p_col = pal.lerp(cold, warm, u_part * 0.7 + col_f * 0.3)
            if size_p == 1:
                if 0 <= x < size and 0 <= y < size:
                    surf.set_at((x, y), (*p_col, a))
            else:
                pygame.draw.circle(surf, (*p_col, a), (x, y), size_p)

        # ── PASSAGEM 3: Faíscas/descargas rápidas em atração máxima ───────────
        if getattr(self, "is_pulling_something", False) and pass_type == "front":
            if random.random() < 0.32:
                # Escolhe um ângulo aleatório
                spark_ang = random.uniform(0.0, tau)
                # Começa em um raio aleatório e vai até o núcleo
                r_start = random.uniform(R * 0.4, R * 0.95)
                r_end = r_min
                
                x1 = int(fc + r_start * cos(spark_ang))
                y1 = int(fc + r_start * sin(spark_ang) * cos_tilt)
                x2 = int(fc + r_end * cos(spark_ang))
                y2 = int(fc + r_end * sin(spark_ang) * cos_tilt)
                
                spark_col = pal.CORE_HOT
                pygame.draw.line(surf, (*spark_col, 220), (x1, y1), (x2, y2), 1)

        surface.blit(surf, (int(cx) - fc, int(cy) - fc))
