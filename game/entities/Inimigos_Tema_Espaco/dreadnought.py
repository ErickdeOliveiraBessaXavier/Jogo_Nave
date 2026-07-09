"""Dreadnought — "O Couraçado de Cerco" do bioma STARFIELD.

Papel `tank` (inédito no Espaço): nave-capital pesada, imponente e **imparável**.
Identidade própria — NÃO é o "jockey com torres que miram" (esse é o CyberTank da
CITY). Aqui o padrão é **"Muralha de Broadside"**:

- **Movimento — patrulha de muralha.** Desce pelo topo (top-view) até uma LANE
  alta e **desliza devagar de um lado ao outro**, ocupando o topo da arena como
  uma barreira. **Ignora a posição exata do jogador** — não orbita, não mantém
  standoff. É um muro que se move.
- **Ataque — bombardeio COORDENADO em 4 colunas.** Tem **QUATRO canhões fixos**
  apontando para baixo (a assinatura). Na barragem os **quatro disparam JUNTOS**
  (sem tiro alternado), em algumas ondas — colunas lentas descendentes que o
  jogador costura pelos vãos enquanto a muralha desliza. **Não mira o jogador.**
- **Aquecimento no próprio sprite.** As **bocas esquentam** célula a célula ao
  carregar (frio → rubro → laranja → amarelo intenso = disparo) e **esfriam** ao
  contrário depois — ciclo aquecimento→disparo→resfriamento sem efeito externo
  (o `self.heat` também tinge o olho e as células de energia).
- **Blindagem — punição.** Com os canhões frios (patrulha) o casco **apara o
  dano** (`ARMOR_CHIP`). Só toma **dano cheio** enquanto os canhões estão quentes
  (carga + salva). Ler o aquecimento → desviar das colunas → punir a janela.

Contato não a mata (`on_ship_contact` → `killed=False`); a nave leva dano pela
colisão. Morte = grande explosão estrutural sóbria (sem meltdown neon).

Estética SÓBRIA (`space_palette`): **plataforma de bombardeio** (não é nave)
estática — convés blindado + torre de comando à esquerda + 4 canhões no ventre;
acentos frios, sem bloom. Contratos: §5 update via `update_in_context` (empurra
shells em `ctx.new_neon_bolts`); §3 `draw` só lê estado; §8 dano via `HitResult`;
§11 `aggressiveness_multiplier` propaga até cadência/velocidade da salva.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from ..Inimigos_Tema_Cidade.neon_bolt import NeonBolt
from . import space_palette as pal
from .dreadnought_pixel_map import (
    BARREL_CENTER_COL,
    BARREL_TOP_ROW,
    CANNON_CENTER_COLS,
    CANNON_FRACS,
    ENERGY_CELLS_FRAC,
    EYE_CX_FRAC,
    EYE_CY_FRAC,
    EYE_R_CELLS,
    MUZZLE_HALF,
    MUZZLE_ROW,
    MUZZLE_Y_FRAC,
    PIXEL_COLS,
    PIXEL_ROWS,
    RECOIL_TRAVEL_CELLS,
    TUBE_HALF,
    build_barrel_surface,
    build_deck_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# Plasma das salvas (muted, não neon): aço-frio.
_SHELL_CORE: pal.RGB = (214, 224, 234)
_SHELL_GLOW: pal.RGB = pal.ACCENT_COLD

# Gradiente de AQUECIMENTO da boca dos canhões (frio → rubro → laranja → amarelo
# intenso). Pintado célula a célula no sprite conforme a carga sobe (e ao contrário
# no resfriamento) — comunica aquecimento→disparo→resfriamento sem efeito externo.
_HEAT_STOPS: list[tuple[float, pal.RGB]] = [
    (0.00, pal.HULL_DARK),      # metal frio (coloração original)
    (0.28, (110, 32, 22)),      # rubro escuro
    (0.52, (188, 60, 24)),      # vermelho-laranja
    (0.74, (236, 132, 38)),     # laranja
    (0.90, (250, 202, 90)),     # amarelo
    (1.00, (255, 246, 206)),    # amarelo intenso / quase branco (disparo)
]


def _heat_color(h: float) -> pal.RGB:
    if h <= 0.0:
        return _HEAT_STOPS[0][1]
    for (h0, c0), (h1, c1) in zip(_HEAT_STOPS, _HEAT_STOPS[1:]):
        if h <= h1:
            t = (h - h0) / (h1 - h0) if h1 > h0 else 0.0
            return pal.lerp(c0, c1, t)
    return _HEAT_STOPS[-1][1]

# ── Chevron-aviso pixel-art (telegraph de entrada, sóbrio: contorno âmbar) ────
_ARROW_COLS, _ARROW_ROWS = 11, 7
_arrow_cache: dict[int, pygame.Surface] = {}


def _build_warning_arrow(cell: int) -> pygame.Surface:
    """Chevron '>' fino (2px), âmbar apagado, sem contorno/bloom. Cacheado."""
    cached = _arrow_cache.get(cell)
    if cached is not None:
        return cached
    mid = _ARROW_ROWS // 2
    tip = _ARROW_COLS - 1
    surf = pygame.Surface((_ARROW_COLS * cell, _ARROW_ROWS * cell), pygame.SRCALPHA)
    for r in range(_ARROW_ROWS):
        c0 = tip - abs(r - mid)
        for c in (c0, c0 - 1):
            if 0 <= c < _ARROW_COLS:
                surf.fill(pal.WARNING_AMBER, (c * cell, r * cell, cell, cell))
    _arrow_cache[cell] = surf
    return surf


class Dreadnought(EnemyHitMixin):
    CELL: int = 5  # 27*5 = 135px largura, 15*5 = 75px altura — nave-capital
    SIZE: int = PIXEL_COLS * CELL   # largura (w)
    H: int = PIXEL_ROWS * CELL      # altura (h) — usada no spawn pelo topo

    HEALTH: int = 950
    POINTS: int = 1800

    # ── Entrada (desce do topo — top-view) ────────────────────────────────────
    ENTER_SPEED: float = 100.0
    ENTER_FRAC: float = 0.24        # y-centro (fração) da LANE onde patrulha
    EDGE_MARGIN: float = 30.0

    # ── Patrulha de muralha (desliza no topo; ignora a posição do jogador) ────
    PATROL_SPEED: float = 58.0      # lento e imponente
    BOB_AMPL: float = 6.0

    # ── Broadside COORDENADO: os 4 canhões disparam JUNTOS (bombardeio simultâneo)
    CANNONS: int = len(CANNON_FRACS)  # quatro colunas de disparo (a assinatura)
    SALVO_VOLLEYS: int = 4          # ondas da barragem (todos os 4 a cada onda)
    VOLLEY_GAP: float = 0.42        # intervalo entre ondas
    SHELL_SPEED: float = 160.0      # LENTO: colunas descendentes para costurar
    PATROL_TIME: float = 2.6        # patrulha antes de carregar
    CHARGE_TIME: float = 1.45       # aquecimento das bocas (JANELA DE PUNIÇÃO)
    RECOVER_TIME: float = 0.7       # resfriamento pós-disparo; volta a blindar
    RECOIL_SPEED: float = 5.5       # decaimento do recuo por canhão (1 → 0)
    COOL_RATE: float = 1.3          # velocidade de resfriamento das bocas (heat → 0)

    # ── Blindagem (fora da ventilação o dano é aparado) ───────────────────────
    ARMOR_CHIP: float = 0.34        # multiplicador de dano com comportas fechadas

    # ── Telegraph de entrada ─────────────────────────────────────────────────
    WARNING_DURATION: float = 4.5
    WARNING_SOUND_TIME: float = 1.0
    WARNING_ARROW_CELL: int = 6
    WARNING_EDGE_INSET: float = 30.0
    WARNING_SPIN_RATE: float = 3.6
    WARNING_GROW_MIN: float = 0.5
    WARNING_GROW_MAX: float = 1.45

    _explosion_size_hit: int = 16   # faísca ao acertar a ventilação (dano cheio)
    _explosion_size_chip: int = 6   # ricochete no casco blindado (dano aparado)

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
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
        self.aggressiveness_multiplier: float = aggressiveness_multiplier
        # Desce do topo e fica no telegraph fora da tela: isenta do cull de
        # off-screen até dominar (§5: gate por instance attr, padrão StealthFighter).
        self.offscreen_cull_exempt: bool = True

        # FSM: warning → enter → (patrol ⇄ charge → salvo → recover)
        self.state: str = "warning"
        self.warning_timer: float = 0.0
        self._warning_started: bool = False
        self._warning_sound_stopped: bool = False
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

        # Patrulha / combate
        self.lane_y: float = self.ENTER_FRAC * Config.SCREEN_HEIGHT
        self.patrol_dir: float = random.choice((-1.0, 1.0))
        self.phase_timer: float = 0.0
        self.heat: float = 0.0          # 0 (frio) .. 1 (bocas incandescentes/tiro)
        self.volley_idx: int = 0
        self.volley_timer: float = 0.0
        self.recoil: list[float] = [0.0] * self.CANNONS    # recuo por canhão (1 → 0)
        self._player_x: float = Config.SCREEN_WIDTH * 0.5  # p/ a pupila do olho seguir
        self._charge_sound_on: bool = False

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        pad = int(self.cell * 4)
        return pygame.Rect(
            int(self.x) - pad, int(self.y) - self.cell,
            self.w + pad * 2, self.h + self.cell * 2,
        )

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.30

    @property
    def draws_offscreen(self) -> bool:
        # No telegraph o corpo está fora da borda, mas o chevron precisa aparecer.
        return self.state == "warning"

    def _cannon_x(self, i: int) -> float:
        """x-centro da boca do canhão i (alinhado à arte via CANNON_FRACS)."""
        return self.x + CANNON_FRACS[i] * self.w

    def _venting(self) -> bool:
        """Canhões acesos (carga + salva): vulnerável a dano cheio."""
        return self.state in ("charge", "salvo")

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        shells = self.update(ctx.sdt, ctx.player_x)
        if shells:
            ctx.new_neon_bolts.extend(shells)

    def update(self, dt: float, player_x: float) -> List[NeonBolt] | None:
        # NÃO recebe player_y: a muralha ignora a posição do jogador (só usa
        # player_x no lerp de entrada). Identidade ≠ CyberTank (que te mira).
        if dt <= 0.0:
            return None

        self.pulse += dt
        self._player_x = player_x  # a pupila do olho segue (lido no draw, §3)
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        for i in range(self.CANNONS):
            if self.recoil[i] > 0.0:
                self.recoil[i] = max(0.0, self.recoil[i] - dt * self.RECOIL_SPEED)

        if self.state == "warning":
            self._update_warning(dt)
            return None
        if self.state == "enter":
            self._update_enter(dt, player_x)
            return None

        # Muralha: desliza SEMPRE (mesmo carregando/atirando) — as 4 colunas
        # varrem a arena, mantendo o bombardeio simultâneo justo de costurar.
        self._patrol_move(dt)
        bolts: List[NeonBolt] | None = None
        if self.state == "patrol":
            self._update_patrol(dt)
        elif self.state == "charge":
            self._update_charge(dt)
        elif self.state == "salvo":
            bolts = self._update_salvo(dt)
        elif self.state == "recover":
            self._update_recover(dt)

        self.y = self.lane_y - self.h / 2 + math.sin(self.pulse * 1.1) * self.BOB_AMPL
        return bolts

    def _update_warning(self, dt: float) -> None:
        from ...systems import hit_sounds

        if not self._warning_started:
            self._warning_started = True
            hit_sounds.WARNING()

        self.warning_timer += dt
        if (
            not self._warning_sound_stopped
            and self.warning_timer >= self.WARNING_SOUND_TIME
        ):
            self._warning_sound_stopped = True
            hit_sounds.STOP_WARNING()

        if self.warning_timer >= self.WARNING_DURATION:
            self.state = "enter"

    def _update_enter(self, dt: float, player_x: float) -> None:
        self.y += self.ENTER_SPEED * dt
        cx = self.x + self.w / 2
        self.x = cx + (player_x - cx) * min(1.0, dt * 1.6) - self.w / 2
        if self.y + self.h / 2 >= self.ENTER_FRAC * Config.SCREEN_HEIGHT:
            self.lane_y = self.ENTER_FRAC * Config.SCREEN_HEIGHT
            self.offscreen_cull_exempt = False
            self.state = "patrol"
            self.phase_timer = self.PATROL_TIME

    def _patrol_move(self, dt: float) -> None:
        """Desliza a plataforma horizontalmente (rebate nas bordas). Roda em TODO
        estado de combate — a muralha nunca para."""
        xlo = self.EDGE_MARGIN + self.w / 2
        xhi = Config.SCREEN_WIDTH - self.EDGE_MARGIN - self.w / 2
        cx = self.x + self.w / 2 + self.PATROL_SPEED * self.patrol_dir * dt
        if cx <= xlo:
            cx, self.patrol_dir = xlo, 1.0
        elif cx >= xhi:
            cx, self.patrol_dir = xhi, -1.0
        self.x = cx - self.w / 2

    def _update_patrol(self, dt: float) -> None:
        self.heat = max(0.0, self.heat - dt * self.COOL_RATE)  # termina de esfriar
        self.phase_timer -= dt
        if self.phase_timer <= 0.0:
            self.state = "charge"
            self.phase_timer = self.CHARGE_TIME
            self._start_charge_sound()

    def _update_charge(self, dt: float) -> None:
        # Aquecimento: as bocas esquentam de frio → rubro → laranja → amarelo.
        self.heat = min(1.0, self.heat + dt / self.CHARGE_TIME)
        self.phase_timer -= dt
        if self.phase_timer <= 0.0:
            self._stop_charge_sound()
            self.state = "salvo"
            self.volley_idx = 0
            self.volley_timer = 0.0

    def _update_salvo(self, dt: float) -> List[NeonBolt] | None:
        self.heat = 1.0  # bocas incandescentes durante a barragem
        self.volley_timer -= dt
        if self.volley_timer > 0.0 or self.volley_idx >= self.SALVO_VOLLEYS:
            return None

        bolts = self._fire_volley()
        self.volley_idx += 1
        if self.volley_idx < self.SALVO_VOLLEYS:
            agg = max(0.5, self.aggressiveness_multiplier)
            self.volley_timer = self.VOLLEY_GAP / agg
        else:
            self.state = "recover"
            self.phase_timer = self.RECOVER_TIME
        return bolts

    def _update_recover(self, dt: float) -> None:
        self.heat = max(0.0, self.heat - dt * self.COOL_RATE)  # esfria as bocas
        self.phase_timer -= dt
        if self.phase_timer <= 0.0:
            agg = max(0.5, self.aggressiveness_multiplier)
            self.state = "patrol"
            self.phase_timer = self.PATROL_TIME / agg

    def _fire_volley(self) -> List[NeonBolt] | None:
        """Uma onda da barragem: os QUATRO canhões cospem JUNTOS um shell lento
        reto para baixo (bombardeio coordenado — nada de disparo alternado)."""
        agg = max(0.5, self.aggressiveness_multiplier)
        speed = self.SHELL_SPEED * (0.85 + 0.25 * agg)
        py = self.y + self.h * MUZZLE_Y_FRAC
        bolts: List[NeonBolt] = []
        for i in range(self.CANNONS):
            bolts.append(
                NeonBolt(
                    self._cannon_x(i), py, 0.0, speed,
                    core=_SHELL_CORE, glow=_SHELL_GLOW, radius=5, glow_radius=10,
                    pulse=True,  # esfera de energia pulsante (não estática)
                )
            )
            self.recoil[i] = 1.0  # todos coiceiam juntos (peso do disparo)
        return bolts

    def _start_charge_sound(self) -> None:
        from ...systems import hit_sounds

        if not self._charge_sound_on:
            self._charge_sound_on = True
            hit_sounds.GOLEM_CHARGING()

    def _stop_charge_sound(self) -> None:
        from ...systems import hit_sounds

        if self._charge_sound_on:
            self._charge_sound_on = False
            hit_sounds.GOLEM_STOP_CHARGING()

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.06
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Blindagem: dano cheio só quando ventila (comportas abertas); senão apara.
        if self._venting():
            self.take_damage(damage)
            spark = self._explosion_size_hit
        else:
            self.take_damage(max(1, int(round(damage * self.ARMOR_CHIP))))
            spark = self._explosion_size_chip

        if self.dead:
            self._stop_charge_sound()
            # Falha estrutural: uma grande explosão sóbria (sem meltdown neon).
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=int(self.w * 0.8),
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=spark, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Imparável: sobrevive ao contato (a nave leva dano pela colisão).
        return HitResult(killed=False, explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render (sóbrio) ───────────────────────────────────────────────────────
    def _recoil_px(self, i: int) -> int:
        return int(self.recoil[i] * RECOIL_TRAVEL_CELLS * self.cell)

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == "warning":
            self._draw_warning(surface)
            return

        # Convés estático (parte de baixo dos canhões é separada, p/ o recuo).
        deck = build_deck_surface(self.cell)
        if self.hit_timer > 0.0:
            deck = deck.copy()
            deck.fill((70, 76, 88), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(deck, (int(self.x), int(self.y)))

        self._draw_barrels(surface)      # 4 canhões, cada um com seu recuo
        self._draw_muzzle_heat(surface)  # bocas AQUECEM (rubro→amarelo) e esfriam
        self._draw_energy(surface)       # células de energia pulsando (vida contínua)
        self._draw_eye(surface)          # o "cérebro": olho ciber central (foco)

    def _draw_barrels(self, surface: pygame.Surface) -> None:
        cell = self.cell
        barrel = build_barrel_surface(cell)
        if self.hit_timer > 0.0:
            barrel = barrel.copy()
            barrel.fill((70, 76, 88), special_flags=pygame.BLEND_RGB_ADD)
        top = int(self.y) + BARREL_TOP_ROW * cell
        for i, center in enumerate(CANNON_CENTER_COLS):
            bx = int(self.x) + (center - BARREL_CENTER_COL) * cell
            surface.blit(barrel, (bx, top - self._recoil_px(i)))

    def _draw_eye(self, surface: pygame.Surface) -> None:
        """Olho ciber: íris que pulsa (fria em patrulha → âmbar ao coordenar a
        salva) e pupila que ACOMPANHA o jogador — o cérebro que rege os canhões."""
        cell = self.cell
        ecx = int(self.x + EYE_CX_FRAC * self.w)
        ecy = int(self.y + EYE_CY_FRAC * self.h)
        r = max(3, int(EYE_R_CELLS * cell))
        focus = self.heat  # 0 = frio (calmo) .. 1 = âmbar (dirigindo o bombardeio)

        pygame.draw.circle(surface, pal.CORE_DARK, (ecx, ecy), r)
        pulse = 0.5 + 0.5 * math.sin(self.pulse * (3.0 + 3.0 * focus))
        iris = pal.lerp(pal.ACCENT_COLD, pal.WARNING_AMBER, focus)
        pygame.draw.circle(surface, iris, (ecx, ecy), max(2, int(r - 1 + pulse)), 2)

        # Pupila: desliza em direção ao jogador (olhar), brilha e pulsa de tamanho.
        maxoff = r * 0.42
        off = maxoff * max(-1.0, min(1.0, (self._player_x - ecx) / 320.0))
        px = int(ecx + off)
        pr = max(2, int(r * (0.42 + 0.12 * pulse)))
        pupil = pal.lerp(pal.CORE_HOT, (250, 226, 170), focus)
        pygame.draw.circle(surface, pupil, (px, ecy), pr)
        pygame.draw.circle(
            surface, (232, 244, 252),
            (px + max(1, pr // 2), ecy - max(1, pr // 3)), max(1, pr // 3),
        )

    def _draw_energy(self, surface: pygame.Surface) -> None:
        """Células de energia flanqueando o olho: orbes que pulsam sempre (mais
        vivas/âmbar quando os canhões carregam) — a nave parece energizada."""
        cell = self.cell
        focus = self.heat
        hot = pal.lerp(pal.ACCENT_COLD, pal.WARNING_AMBER, focus)
        for k, (fx, fy) in enumerate(ENERGY_CELLS_FRAC):
            px = int(self.x + fx * self.w)
            py = int(self.y + fy * self.h)
            g = 0.5 + 0.5 * math.sin(self.pulse * (2.4 + 2.2 * focus) + k * 1.7)
            pygame.draw.circle(surface, pal.ACCENT_COLD_DIM, (px, py), max(2, int(cell * 0.6)), 1)
            pygame.draw.circle(
                surface, pal.lerp(pal.ACCENT_COLD_DIM, hot, g), (px, py), max(1, int(cell * 0.35))
            )

    def _draw_muzzle_heat(self, surface: pygame.Surface) -> None:
        """AQUECIMENTO das bocas pintado célula a célula no próprio sprite: o freio
        de boca (5 cels) + a ponta do tubo (3 cels) evoluem de frio → rubro →
        laranja → amarelo conforme `self.heat` sobe (e voltam ao original ao
        esfriar). Segue o recuo de cada canhão. Sem efeito externo/círculo."""
        if self.heat <= 0.02:
            return  # frio: mostra o metal original do sprite
        cell = self.cell
        brake = _heat_color(self.heat)
        bore = _heat_color(min(1.0, self.heat * 1.2))       # alma mais incandescente
        tip = _heat_color(self.heat * 0.65)                 # tubo esquenta menos
        bx, by = int(self.x), int(self.y)
        for i, center in enumerate(CANNON_CENTER_COLS):
            rec = self._recoil_px(i)
            my = by + MUZZLE_ROW * cell - rec               # linha do freio de boca
            for dx in range(-MUZZLE_HALF, MUZZLE_HALF + 1):
                surface.fill(brake, (bx + (center + dx) * cell, my, cell, cell))
            surface.fill(bore, (bx + center * cell, my, cell, cell))
            ty = my - cell                                  # ponta do tubo, acima
            for dx in range(-TUBE_HALF, TUBE_HALF + 1):
                surface.fill(tip, (bx + (center + dx) * cell, ty, cell, cell))

    def _draw_warning(self, surface: pygame.Surface) -> None:
        # Chevron apontando PARA BAIXO (top-view: a nave desce do topo), alinhado
        # à coluna de descida (x da nave), no topo da tela.
        arrow = pygame.transform.rotate(
            _build_warning_arrow(self.WARNING_ARROW_CELL), -90.0
        )
        aw, ah = arrow.get_size()
        p = min(1.0, self.warning_timer / self.WARNING_DURATION)
        g = self.WARNING_GROW_MIN + (self.WARNING_GROW_MAX - self.WARNING_GROW_MIN) * p
        cx = self.x + self.w / 2
        cy = self.WARNING_EDGE_INSET + ah / 2
        sx = math.cos(self.pulse * self.WARNING_SPIN_RATE)
        w = max(1, int(aw * g * abs(sx)))
        h = max(1, int(ah * g))
        img = pygame.transform.scale(arrow, (w, h))
        if sx < 0:
            img = pygame.transform.flip(img, True, False)
        surface.blit(img, (int(cx - w / 2), int(cy - h / 2)))
