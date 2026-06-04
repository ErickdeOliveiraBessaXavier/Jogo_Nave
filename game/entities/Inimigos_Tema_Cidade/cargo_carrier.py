"""Cargo Carrier (Cargueiro) — transporte de tropas do bioma CITY.

Variante de **suporte** da linhagem urbana: um cargueiro grande e lento que entra
pela parte superior da lateral direita e, em intervalos, **ejeta uma caixa de
carga** que desce devagar atrás dele. A ameaça não é tiro nem parede — é a
**produção de inimigos**: a caixa só libera o pelotão de `CityDrone` se concluir
toda a descida.

A geração é um **evento visível e interativo**:
  - Enquanto ejeta, o cargueiro troca p/ o frame "produzindo" (magenta) e
    **vibra** levemente, como sob esforço.
  - A caixa (`CargoCrate`) é uma entidade própria: **tem colisão e recebe dano**
    durante a descida. O jogador pode destruí-la antes que termine — essa é a
    **janela de counterplay**. Se cair antes de abrir, a sequência é cancelada e
    nenhum drone nasce.
  - Só ao concluir a descida a caixa se abre na costura central e despeja os 10
    drones; em seguida as duas tampas se soltam para os lados e somem.

A caixa emerge **por trás** do cargueiro: é emitida em `ctx.new_enemies_behind`
(inserida no início da lista de inimigos → desenhada sob os demais), e segue o
cargueiro horizontalmente enquanto desce, ficando cada vez mais exposta.

O id interno do spawner é `"cargo_carrier"` (usado nas tabelas de peso/spawn em
`spawner`, `procedural`, `pipeline` e `fixed_levels`).

Contratos (CLAUDE.md): §5 update polimórfico; §3 `draw` só lê estado; §7 sprites
e meias-caixas cacheados; §8 colisão/dano via `collision_circle`/`on_hit`/
`HitResult`; §11 `aggressiveness`/`health_multiplier` propagados aos despejados.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Dict, List, Tuple

import pygame

from ...core.assets import BASE_DIR, get_image
from ...core.config import config as Config
from ...entities.explosion import ExplosionType
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .city_drone import CityDrone

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# ── Sprites do cargueiro ───────────────────────────────────────────────────
_SPRITE_DIR = BASE_DIR / "assets" / "images" / "Cargueiro"
_IDLE_FILES = [f"PNG_Inimigo_Carga_0{i}.png" for i in range(1, 5)]
_PRODUCING_FILE = "PNG_Inimigo_Carga_05_Produzindo_Caixa.png"
_NATIVE_W, _NATIVE_H = 52, 32
_SPRITE_SCALE = 2.8  # 52×32 → 146×90 (nave de transporte pesada, com presença)
_CARRIER_W = round(_NATIVE_W * _SPRITE_SCALE)  # 146
_CARRIER_H = round(_NATIVE_H * _SPRITE_SCALE)  # 90

# Costura/luzes da caixa em magenta, casando com o frame "produzindo" do cargueiro.
_SEAM_BRIGHT: pal.RGB = (255, 120, 230)
_HAZARD: pal.RGB = pal.TOXIC_ORANGE

# Cache (full_w, h) → (meia-esquerda, meia-direita) da caixa de carga (§7).
_crate_cache: Dict[Tuple[int, int], Tuple[pygame.Surface, pygame.Surface]] = {}


def _blit_glow(
    surface: pygame.Surface, cx: int, cy: int, radius: int, color: pal.RGB
) -> None:
    if radius <= 0:
        return
    glow = city_glow.get_glow(radius, color)
    surface.blit(glow, (cx - radius, cy - radius), special_flags=pygame.BLEND_RGBA_ADD)


def _build_crate_halves(full_w: int, h: int) -> Tuple[pygame.Surface, pygame.Surface]:
    """Constrói as duas metades da caixa de carga em pixel-art, cacheadas.

    Cada metade tem corpo em gunmetal com banda superior iluminada e inferior em
    sombra, listras de perigo (hazard) no meio, parafusos nos cantos, contorno
    nos 3 lados externos e a **costura central brilhante** na borda interna — é
    essa borda que vira a linha de separação quando a caixa abre.
    """
    cached = _crate_cache.get((full_w, h))
    if cached is not None:
        return cached

    half_w = full_w // 2
    top_h = max(2, h // 8)
    bot_h = max(2, h // 6)
    band_y = h // 2 - h // 10
    band_h = max(3, h // 5)
    bolt = max(2, half_w // 10)

    halves: List[pygame.Surface] = []
    for seam_side in ("right", "left"):  # esquerda costura à direita; direita à esquerda
        surf = pygame.Surface((half_w, h), pygame.SRCALPHA)
        surf.fill(pal.GUNMETAL)
        surf.fill(pal.HULL_LIGHT, (0, 0, half_w, top_h))
        surf.fill(pal.HULL_SHADOW, (0, h - bot_h, half_w, bot_h))

        # Banda hazard: base laranja com ticks escuros (listra de carga).
        surf.fill(_HAZARD, (0, band_y, half_w, band_h))
        for tx in range(0, half_w + band_h, band_h):
            pygame.draw.line(
                surf, pal.OUTLINE, (tx, band_y), (tx - band_h, band_y + band_h), 2
            )

        # Parafusos nos cantos externos.
        for bx in (bolt, half_w - bolt * 2):
            for by in (bolt, h - bolt * 2):
                surf.fill(pal.HULL_SHADOW, (bx, by, bolt, bolt))
                surf.fill(pal.HULL_LIGHT, (bx, by, max(1, bolt // 2), max(1, bolt // 2)))

        # Contorno externo (a costura é coberta logo abaixo).
        pygame.draw.rect(surf, pal.OUTLINE, surf.get_rect(), 2)

        # Costura central brilhante na borda interna.
        seam_x = half_w - 2 if seam_side == "right" else 0
        surf.fill(_SEAM_BRIGHT, (seam_x, 0, 2, h))
        halves.append(surf)

    result = (halves[0], halves[1])
    _crate_cache[(full_w, h)] = result
    return result


class CargoCrate(EnemyHitMixin):
    """Caixa de carga ejetada pelo Cargueiro: desce devagar, tem colisão e recebe
    dano. Destruí-la durante a descida cancela a leva. Só ao concluir a descida
    ela abre e despeja os 10 drones; depois as tampas se soltam e somem.

    Fases: ``descending`` (sólida, alvejável) → ``opening`` → ``venting`` (ambas
    cosméticas, sem colisão) → ``dead``.
    """

    CRATE_W: int = (_CARRIER_W * 7 // 10) // 2 * 2   # ~102, par, < cargueiro
    CRATE_H: int = CRATE_W * 62 // 100               # ~63, mais larga que alta
    DROP: float = _CARRIER_H * 0.5 + CRATE_H * 0.5 + 12.0  # quanto desce abaixo do centro

    DESCEND_TIME: float = 2.6   # descida lenta → tempo de perceber e reagir
    OPEN_TIME: float = 0.40     # tampas se separam na costura
    VENT_TIME: float = 0.55     # tampas se afastam, caem e somem

    HEALTH: int = 70            # alvo macio: destrutível com foco de fogo
    POINTS: int = 90
    DEPLOY_COUNT: int = 10
    TROOP_SIZE_TIER: int = 0

    # Movimento das tampas ao soltar.
    _SEP_OPEN: float = CRATE_W * 0.20
    _SEP_VENT: float = CRATE_W * 0.55
    _FALL_DIST: float = 50.0
    _LID_TILT: float = 16.0

    _explosion_size_hit: int = 10
    _explosion_size_killed: int = 46

    def __init__(
        self,
        carrier: "CargoCarrier",
        aggressiveness_multiplier: float = 1.0,
        health_multiplier: float = 1.0,
    ) -> None:
        self.carrier = carrier
        self.side_scroll: bool = carrier.side_scroll
        self.aggressiveness_multiplier = aggressiveness_multiplier
        self.health_multiplier = health_multiplier

        self.w: int = self.CRATE_W
        self.h: int = self.CRATE_H
        ccx, ccy = carrier.rect.center  # contrato público (§1), não o _center protegido
        self.x: float = ccx - self.w / 2  # nasce centrada e oculta atrás do cargueiro
        self.y: float = ccy - self.h / 2

        self.dead: bool = False
        self.health: int = max(1, int(self.HEALTH * health_multiplier))

        self.phase: str = "descending"
        self.phase_t: float = 0.0
        self.descend_t: float = 0.0
        self.lid_split: float = 0.0
        self.lid_vent: float = 0.0
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def collision_circle(self) -> Tuple[float, float, float]:
        cx, cy = self._center()
        # Só colide durante a descida; depois de abrir é puro cosmético.
        if self.phase != "descending":
            return cx, cy, 0.0
        return cx, cy, self.w * 0.46

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.phase == "descending":
            # Cargueiro destruído/sumiu no meio da ejeção → cancela a leva.
            if self.carrier.dead:
                self.dead = True
                return
            self.phase_t += dt
            self.descend_t = min(1.0, self.phase_t / self.DESCEND_TIME)
            ccx, ccy = self.carrier.rect.center
            ease = self.descend_t * self.descend_t * (3.0 - 2.0 * self.descend_t)
            self.x = ccx - self.w / 2
            self.y = (ccy + ease * self.DROP) - self.h / 2
            if self.descend_t >= 1.0:
                # Descida concluída: solta a tropa e começa a abrir (já destacada).
                self.phase = "opening"
                self.phase_t = 0.0
                ctx.new_enemies.extend(self._make_troops())

        elif self.phase == "opening":
            self.phase_t += dt
            self.lid_split = min(1.0, self.phase_t / self.OPEN_TIME)
            if self.lid_split >= 1.0:
                self.phase = "venting"
                self.phase_t = 0.0

        else:  # venting
            self.phase_t += dt
            self.lid_vent = min(1.0, self.phase_t / self.VENT_TIME)
            if self.lid_vent >= 1.0:
                self.dead = True

    def _make_troops(self) -> List[CityDrone]:
        """Despeja o pelotão a partir do interior da caixa (grade frouxa + jitter)."""
        cx, cy = self._center()
        troops: List[CityDrone] = []
        for i in range(self.DEPLOY_COUNT):
            col = i % 5
            row = i // 5
            dx = cx + (col - 2) * (self.CRATE_W * 0.18) + random.uniform(-3.0, 3.0)
            dy = cy + (row - 0.5) * 12.0 + random.uniform(-4.0, 4.0)
            troops.append(
                CityDrone(
                    dx, dy,
                    aggressiveness_multiplier=self.aggressiveness_multiplier,
                    side_scroll=self.side_scroll,
                    size_tier=self.TROOP_SIZE_TIER,
                    health_multiplier=self.health_multiplier,
                )
            )
        return troops

    # ── Render ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        left, right = _build_crate_halves(self.CRATE_W, self.CRATE_H)
        half_w = left.get_width()
        cx, cy = self._center()

        sep = self.lid_split * self._SEP_OPEN + self.lid_vent * self._SEP_VENT
        fall = (self.lid_vent * self.lid_vent) * self._FALL_DIST
        alpha = int(255 * (1.0 - self.lid_vent))
        tilt = self.lid_vent * self._LID_TILT
        y = cy + fall

        for surf, sign in ((left, -1.0), (right, 1.0)):
            center_x = cx + sign * (half_w / 2 + sep)
            if self.lid_vent > 0.0:
                img = pygame.transform.rotate(surf, -sign * tilt)
                if alpha < 255:
                    img.set_alpha(alpha)
            else:
                img = surf
            blit_rect = img.get_rect(center=(int(center_x), int(y)))
            surface.blit(img, blit_rect)

        # Costura central pulsando enquanto fechada (some ao abrir).
        closed = max(0.0, 1.0 - self.lid_split)
        if closed > 0.02 and self.lid_vent <= 0.0:
            pulse = 0.5 + 0.5 * math.sin(self.pulse * 8.0)
            seam_col = pal.lerp((0, 0, 0), _SEAM_BRIGHT, closed * (0.5 + 0.5 * pulse))
            _blit_glow(surface, int(cx), int(cy), int(self.CRATE_H * 0.45), seam_col)

        # Flash de dano (só na caixa sólida).
        if self.hit_timer > 0.0 and self.phase == "descending":
            flash = pygame.Surface((self.CRATE_W, self.CRATE_H), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 90))
            surface.blit(flash, (int(self.x), int(self.y)))

    # ── Dano / morte ────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        if self.phase != "descending":
            return
        self.health -= amount
        self.hit_timer = 0.07
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult
        if self.phase != "descending":
            # Já abriu: tiro não cancela nem pontua.
            return HitResult(killed=False, explosion_size=0, sound=hit_sounds.BOSS_DAMAGE)
        self.take_damage(damage)
        if self.dead:
            # Destruída durante a ejeção → leva cancelada (sem drones).
            return HitResult(
                killed=True,
                points=self.POINTS,
                explosion_size=self._explosion_size_killed,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult
        return HitResult(killed=False, explosion_size=8, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead


class CargoCarrier(EnemyHitMixin):
    # Dimensões derivadas do sprite escalado — grande, p/ transmitir peso/presença.
    W: int = _CARRIER_W  # 146
    H: int = _CARRIER_H  # 90
    SIZE: int = W

    HEALTH: int = 320                 # transporte pesado: bem mais tanky
    POINTS: int = 460

    ENTER_SPEED: float = 80.0          # entra devagar pela direita
    ADVANCE_SPEED: float = 14.0        # quase parado: persiste no canto superior-direito
    ENTER_TARGET_FRAC: float = 0.88    # x-centro onde para de entrar (lateral direita)
    BOB_AMP: float = 18.0             # amplitude do bob vertical
    BOB_SPEED: float = 1.6
    IDLE_FPS: float = 2.0             # troca lenta de frames → nave grande e estável

    DEPLOY_INTERVAL: float = 7.0      # espera entre caixas (após a anterior sumir)
    DEPLOY_FIRST_DELAY: float = 2.0
    SHAKE_AMP: float = 2.5            # vibração sutil enquanto ejeta a caixa

    # Posição do glow do cargueiro, em pixels a partir do CENTRO do sprite.
    # +X = direita, -X = esquerda, +Y = baixo, -Y = cima. (0, 0) = centro.
    GLOW_OFFSET_X: float = 0.0
    GLOW_OFFSET_Y: float = -15.0

    _explosion_size_hit: int = 12
    _explosion_size_killed: int = 40

    # Frames escalados, carregados uma vez (§7).
    _idle_frames: List[pygame.Surface] = []
    _producing_frame: "pygame.Surface | None" = None

    @classmethod
    def _load_frames(cls) -> None:
        if cls._idle_frames:
            return
        size = (cls.W, cls.H)
        cls._idle_frames = [
            pygame.transform.scale(get_image(_SPRITE_DIR / f), size)
            for f in _IDLE_FILES
        ]
        cls._producing_frame = pygame.transform.scale(
            get_image(_SPRITE_DIR / _PRODUCING_FILE), size
        )

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        health_multiplier: float = 1.0,
    ) -> None:
        self._load_frames()
        self.side_scroll: bool = side_scroll
        self.w: int = self.W
        self.h: int = self.H

        self.x: float = float(x)
        self.base_y: float = float(y)
        self.y: float = float(y)

        self.dead: bool = False
        self.health_multiplier: float = health_multiplier
        self.health: int = max(1, int(self.HEALTH * health_multiplier))
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        self.state: str = "enter"
        self.enter_target: float = self.ENTER_TARGET_FRAC * Config.SCREEN_WIDTH
        self.pulse: float = random.uniform(0.0, math.tau)
        self.anim_time: float = random.uniform(0.0, 1.0)
        self.hit_timer: float = 0.0

        # Deploy: uma caixa por vez. `crate` aponta p/ a caixa ativa (ou None).
        self.deploy_cd: float = self.DEPLOY_FIRST_DELAY
        self.crate: "CargoCrate | None" = None
        self.shake: Tuple[float, float] = (0.0, 0.0)

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        r = self.rect
        return r.centerx, r.centery, self.h * 0.46

    def _center(self) -> Tuple[float, float]:
        r = self.rect
        return r.centerx, r.centery

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)
        if self.state != "enter":
            self._tick_deploy(ctx)
        self._update_shake()

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.pulse += dt
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "enter":
            cx = self.x + self.w / 2 - self.ENTER_SPEED * dt
            if cx <= self.enter_target:
                cx = self.enter_target
                self.state = "advance"
            self.x = cx - self.w / 2
        else:  # advance
            self.x -= self.ADVANCE_SPEED * dt
            if self.x + self.w < -60.0:
                self.dead = True

        # Bob vertical suave.
        self.y = self.base_y + math.sin(self.pulse * self.BOB_SPEED) * self.BOB_AMP

    def _tick_deploy(self, ctx: "EnemyUpdateContext") -> None:
        """Uma caixa por vez: enquanto a caixa ativa existe, o cargueiro só a
        monitora; quando ela some (concluída ou destruída), rearma o cooldown."""
        if self.crate is not None:
            if not self.crate.dead:
                return  # ocupado ejetando — cooldown congelado
            self.crate = None
            self.deploy_cd = self.DEPLOY_INTERVAL

        self.deploy_cd -= ctx.sdt
        if self.deploy_cd <= 0.0:
            crate = CargoCrate(
                self,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                health_multiplier=self.health_multiplier,
            )
            self.crate = crate
            # Emerge POR TRÁS do cargueiro: vai p/ o início da lista (desenhada sob).
            ctx.new_enemies_behind.append(crate)

    def _update_shake(self) -> None:
        """Vibração sutil só durante a descida da caixa (esforço de ejeção). Lê o
        estado público da caixa; aplicada apenas no draw (não mexe na colisão)."""
        if self.crate is not None and self.crate.phase == "descending":
            a = self.SHAKE_AMP
            self.shake = (random.uniform(-a, a), random.uniform(-a, a))
        else:
            self.shake = (0.0, 0.0)

    @property
    def _producing(self) -> bool:
        return self.crate is not None

    # ── Render ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        sx, sy = self.shake
        pos = (int(self.x + sx), int(self.y + sy))
        producing = self._producing
        if producing and self._producing_frame is not None:
            base = self._producing_frame
        else:
            base = self._idle_frames[
                int(self.anim_time * self.IDLE_FPS) % len(self._idle_frames)
            ]

        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, pos)
        else:
            surface.blit(base, pos)

        cx = self.x + sx + self.w / 2 + self.GLOW_OFFSET_X
        cy = self.y + sy + self.h / 2 + self.GLOW_OFFSET_Y
        self._draw_state_glow(surface, producing, cx, cy)

    def _draw_state_glow(
        self, surface: pygame.Surface, producing: bool, cx: float, cy: float
    ) -> None:
        """Brilho suave no centro do cargueiro: magenta ao produzir (telegrafa),
        teal fraco em idle. Lê só `self.pulse` (§3)."""
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        if producing:
            color = pal.lerp(pal.CYBER_MAGENTA_DIM, pal.CYBER_MAGENTA, 0.4 + 0.6 * pulse)
            radius = int(self.h * (0.30 + 0.10 * pulse))
        else:
            color = pal.lerp((0, 0, 0), pal.ELECTRIC_BLUE_DIM, 0.4 + 0.4 * pulse)
            radius = int(self.h * 0.22)
        _blit_glow(surface, int(cx), int(cy), radius, color)

    # ── Dano / morte ────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.07
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult
        self.take_damage(damage)
        if self.dead:
            # explosion_size=0: a explosão (centrada) e os destroços do chassi vêm
            # do death-sequence do EntityManager (mesmo padrão do SplitterTank).
            return HitResult(
                killed=True,
                points=self.POINTS,
                explosion_size=0,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=True,
            )
        return HitResult(explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult
        return HitResult(killed=False, explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead or self.x < -100
