"""Águia de Pedra — inimigo "rush" do bioma MOUNTAINS.

Planador de pedra que circula no alto, **telegrafa** (animação agitada) e
então **mergulha rápido** na posição travada do jogador, subindo de volta em
seguida. Dano por colisão. Counterplay: ler o telegrama e desviar do eixo do
mergulho.

Arte: sprites PNG em ``assets/images/Stone_Eagle`` — 8 frames de animação de voo
(``stone_eagle_1..8``) e 1 frame de mergulho (``stone_eagle_dive``, vermelho =
ataque comprometido).

ORIENTAÇÃO DA ARTE — o sprite foi desenhado na **diagonal**: a ponta de cristal
(a frente, o vetor de ataque) aponta para o canto **inferior-esquerdo**; o
propulsor fica no canto superior-direito. Toda a compensação angular vive num
único ponto (`SPRITE_FORWARD_DEG` + `_blit_oriented`): trocar a arte no futuro
exige ajustar só essa constante, sem caçar offsets espalhados.

Contratos (convenções do projeto): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3).
"""

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ....core import colors
from ....core.assets import BASE_DIR, get_image
from ....core.config import config as Config
from ....core.sound import sound_manager
from ....core.sprite_loader import sprite_loader
from .._shared.enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class StoneEagle(EnemyHitMixin):
    # ── Orientação da arte: ÚNICO ponto de compensação angular ──────────────
    # O sprite aponta para o canto inferior-esquerdo. Em coordenadas de tela
    # (y para baixo), "inferior-esquerdo" é o ângulo 135° (atan2(+1, -1)). Para
    # alinhar a arte a um rumo `facing` (também em screen-space), gira-se
    # `SPRITE_FORWARD_DEG - deg(facing)`: pygame.rotate gira CCW (sentido que
    # DIMINUI o ângulo de tela), então essa diferença leva a frente da arte
    # exatamente até `facing`. Centralizado em `_blit_oriented` — nenhum outro
    # ponto do código aplica correção de orientação.
    SPRITE_FORWARD_DEG = 135.0

    SPRITE_DIR = "Stone_Eagle"
    NUM_ANIM_FRAMES = 8
    TARGET_SIZE = 64  # 2x do PNG 32×32 → pixels nítidos
    # `W`/`H`: contrato de tamanho lido pelo spawner (`_entry_position`). A águia
    # é quadrada (sprite 32×32), então ambos = TARGET_SIZE.
    W = TARGET_SIZE
    H = TARGET_SIZE
    ANIM_FPS = 9.0
    TELEGRAPH_ANIM_BOOST = 2.4  # animação acelera na agitação do telegrama

    CIRCLE_SPEED = 170.0
    DIVE_SPEED = 600.0
    CLIMB_SPEED = 320.0
    TELEGRAPH_TIME = 0.55
    DIVE_TIME = 0.7
    TURN_RATE = 5.0  # rad/s: suaviza mudança de rumo fora do mergulho

    # Caches de classe (compartilhados entre instâncias; preload via sprite_loader)
    _anim_frames: List[pygame.Surface] = []
    _dive_frame: "pygame.Surface | None" = None

    @classmethod
    def _scale(cls, surf: pygame.Surface) -> pygame.Surface:
        w, h = surf.get_size()
        f = cls.TARGET_SIZE / max(w, h)
        return pygame.transform.scale(surf, (round(w * f), round(h * f)))

    @classmethod
    def load_animation_frames(cls) -> List[pygame.Surface]:
        """Carrega (uma vez) os frames de voo + o frame de mergulho."""
        if cls._anim_frames:
            return cls._anim_frames

        raw = sprite_loader.load_animation_frames(
            base_path=cls.SPRITE_DIR,
            num_frames=cls.NUM_ANIM_FRAMES,
            name="StoneEagle",
            filename_pattern="stone_eagle_{i}.png",
        )
        cls._anim_frames = [cls._scale(f) for f in raw]

        dive_path = BASE_DIR / "assets" / "images" / cls.SPRITE_DIR / "stone_eagle_dive.png"
        if dive_path.exists():
            cls._dive_frame = cls._scale(get_image(dive_path))

        return cls._anim_frames

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        if not self._anim_frames:
            self.load_animation_frames()

        self.w = self.TARGET_SIZE
        self.h = self.TARGET_SIZE
        self.x = x
        self.y = y
        self.band_y = float(random.randint(50, 120))
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 45
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.state = "enter"
        self.circle_timer = random.uniform(1.4, 2.4) / self._aggr
        self.telegraph_timer = 0.0
        self.dive_timer = 0.0
        self.dive_vx = 0.0
        self.dive_vy = 0.0
        self._lock = (0.0, 0.0)  # posição do jogador travada no telegrama

        # `facing`: rumo da águia em screen-space (atan2(dy, dx), y para baixo).
        # Entra mergulhando para baixo.
        self.facing = math.pi / 2
        self.anim_time = 0.0
        self.anim_phase = random.uniform(0.0, float(self.NUM_ANIM_FRAMES))
        # Offset do balanço de voo (bob vertical na circulação); independente do
        # ciclo de animação do sprite (`anim_phase`).
        self.bob_phase = random.uniform(0.0, math.tau)

        # Rotação suave (lerp de ângulo) durante a antecipação do telegrama
        self.start_angle = self.facing
        self.target_angle = self.facing

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def collision_circle(self) -> tuple[float, float, float]:
        # A águia ocupa a diagonal do quadrado do sprite; um círculo cheio
        # (max/2) pegaria cantos vazios. 0.40·lado ≈ raio do corpo real — justo.
        cx, cy = self._center
        return cx, cy, self.w * 0.40

    @staticmethod
    def _approach_angle(current: float, target: float, max_step: float) -> float:
        """Aproxima `current` de `target` em no máx. `max_step` rad, pelo menor
        arco (sem saltos de 360°)."""
        diff = (target - current + math.pi) % math.tau - math.pi
        if abs(diff) <= max_step:
            return target
        return current + math.copysign(max_step, diff)

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        self.anim_time += dt
        # Fase da animação: acumulada aqui (não no draw) — assim acelerar a
        # animação no telegrama não causa salto de frame e o draw fica read-only (§3).
        boost = self.TELEGRAPH_ANIM_BOOST if self.state == "telegraph" else 1.0
        self.anim_phase += self.ANIM_FPS * boost * dt

        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "enter":
            self.facing = math.pi / 2  # descendo
            self.y += self.CLIMB_SPEED * dt
            if self.y >= self.band_y:
                self.y = self.band_y
                self.state = "circle"
            return

        if self.state == "circle":
            cx, _ = self._center
            dx = player_x - cx
            if abs(dx) > 4.0:
                self.x += math.copysign(self.CIRCLE_SPEED * dt, dx)
                desired = 0.0 if dx > 0 else math.pi  # rumo horizontal de voo
                self.facing = self._approach_angle(
                    self.facing, desired, self.TURN_RATE * dt
                )
            self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
            self.y = self.band_y + math.sin(self.anim_time * 2.2 + self.bob_phase) * 8.0
            self.circle_timer -= dt
            if self.circle_timer <= 0.0:
                self.state = "telegraph"
                self.telegraph_timer = self.TELEGRAPH_TIME
                self._lock = (player_x, player_y)
                # Trava o ângulo-alvo do mergulho já no início do telegrama, para
                # girar suavemente até ele durante a antecipação.
                cx, cy = self._center
                tx, ty = self._lock
                self.start_angle = self.facing
                self.target_angle = math.atan2(ty - cy, tx - cx)
            return

        if self.state == "telegraph":
            self.telegraph_timer -= dt
            # Lerp de ângulo com smoothstep: rotação parece natural na antecipação.
            t = 1.0 - max(0.0, self.telegraph_timer / self.TELEGRAPH_TIME)
            t = t * t * (3.0 - 2.0 * t)
            diff = (self.target_angle - self.start_angle + math.pi) % math.tau - math.pi
            self.facing = self.start_angle + diff * t
            if self.telegraph_timer <= 0.0:
                self.facing = self.target_angle
                self.dive_vx = math.cos(self.facing) * self.DIVE_SPEED
                self.dive_vy = math.sin(self.facing) * self.DIVE_SPEED
                self.dive_timer = self.DIVE_TIME
                self.state = "dive"
                sound_manager.play_shot()
            return

        if self.state == "dive":
            self.x += self.dive_vx * dt
            self.y += self.dive_vy * dt
            self.dive_timer -= dt
            if self.x < 0 or self.x > Config.SCREEN_WIDTH - self.w:
                self.dive_vx = -self.dive_vx
                self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
            # Mantém a arte alinhada à velocidade real (inclusive após o ricochete).
            self.facing = math.atan2(self.dive_vy, self.dive_vx)
            if self.dive_timer <= 0.0 or self.y > Config.SCREEN_HEIGHT - self.h:
                self.y = min(self.y, Config.SCREEN_HEIGHT - self.h)
                self.state = "climb"
            return

        # state == "climb"
        self.facing = -math.pi / 2  # subindo
        self.y -= self.CLIMB_SPEED * dt
        if self.y <= self.band_y:
            self.y = self.band_y
            self.circle_timer = random.uniform(1.4, 2.4) / self._aggr
            self.state = "circle"

    def _current_frame(self) -> pygame.Surface:
        """Frame base (sem rotação/tint): vermelho de mergulho ou ciclo de voo."""
        if self.state == "dive" and self._dive_frame is not None:
            return self._dive_frame
        frames = self._anim_frames
        if not frames:
            # Fallback defensivo se a arte não carregou.
            return self._dive_frame or pygame.Surface(
                (self.w, self.h), pygame.SRCALPHA
            )
        return frames[int(self.anim_phase) % len(frames)]

    def _blit_oriented(self, surface: pygame.Surface, frame: pygame.Surface,
                       cx: float, cy: float) -> None:
        """Rotaciona `frame` para alinhar a frente da arte a `self.facing` e
        blita centralizado em (cx, cy). ÚNICO ponto de compensação de orientação."""
        rot_deg = self.SPRITE_FORWARD_DEG - math.degrees(self.facing)
        rotated = pygame.transform.rotate(frame, rot_deg)
        rect = rotated.get_rect(center=(int(cx), int(cy)))
        surface.blit(rotated, rect.topleft)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center

        # Tremor na antecipação (cosmético; não muta estado).
        if self.state == "telegraph":
            cx += random.uniform(-3.0, 3.0)
            cy += random.uniform(-3.0, 3.0)

        frame = self._current_frame()
        # Flash branco ao levar dano. O frame de mergulho já é vermelho (ataque),
        # então não somamos glow — só o flash de hit, quando há.
        if self.hit_timer > 0.0:
            frame = frame.copy()
            frame.fill(colors.WHITE, special_flags=pygame.BLEND_RGB_ADD)

        self._blit_oriented(surface, frame, cx, cy)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 200

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead


# Registra para o preload de sprites (mesma convenção do Satellite).
sprite_loader.register("StoneEagle", StoneEagle.load_animation_frames)
