"""Mina temática da Neon City.

Subclasse de `ExplosiveMine` (mesmo padrão da `MountainGeode`): herda TODO o fluxo
de explosão da mina genérica (pré-explosão, `MineExplosion`, dano à nave via
`handle_mine_explosion`, dano a inimigos) — a explosão principal é idêntica em
lógica, dano e alcance.

A diferença temática é o flag `spawns_neon_residue`: após a explosão principal, o
`check_mine_explosions` dispara 3 **resíduos energéticos** (descargas neon)
escalonados DENTRO do raio da explosão original, reaproveitando `ExplosiveEffect`
(com `delay`/`color`/`lifetime`). São rápidos, coloridos e de dano/raio bem menores
— a sensação de uma reação em cadeia se dissipando, não 4 explosões independentes.
"""

import math
import random
from typing import Dict, Tuple, cast

import pygame

from ....core.assets import BASE_DIR, get_image
from ....core.sprite_loader import sprite_loader
from ...projectiles.explosive_mine import ExplosiveMine

# --- Resíduos energéticos (explosões secundárias) ---------------------------
NEON_RESIDUE_COUNT: int = 3
NEON_RESIDUE_DAMAGE: int = 12  # << dano da principal (50 a inimigos) — bem menor
NEON_RESIDUE_RADIUS_FRAC: Tuple[float, float] = (0.16, 0.24)  # << raio principal
NEON_RESIDUE_BASE_DELAY: float = 0.12  # atraso após a explosão principal
NEON_RESIDUE_STAGGER: float = 0.07  # intervalo entre os resíduos (encadeamento)
NEON_RESIDUE_LIFETIME: float = 0.22  # vida curta → visual rápido/impactante
NEON_RESIDUE_COLORS: Tuple[Tuple[int, int, int], ...] = (
    (90, 235, 255),   # ciano elétrico
    (255, 95, 225),   # magenta neon
    (170, 150, 255),  # violeta de descarga
)

# --- Visual -----------------------------------------------------------------
NEON_IDLE_FPS: float = 3.0
NEON_EXPLODE_FPS: float = 12.0
NEON_INDICATOR_COLOR: Tuple[int, int, int] = (90, 235, 255)
_SPRITE_DIR = BASE_DIR / "assets" / "images" / "Mine_City"


class CityMine(ExplosiveMine):
    """Mina explosiva da Neon City com resíduos energéticos em cadeia."""

    is_explosive_mine: bool = True
    spawns_neon_residue: bool = True

    # Classvars próprias (não compartilha sprites/cache com ExplosiveMine).
    _normal_sprite: pygame.Surface | None = None
    _explosion_sprite: pygame.Surface | None = None
    _normal_sprite2: pygame.Surface | None = None
    _explosion_sprite2: pygame.Surface | None = None
    _transform_cache: Dict[Tuple[bool, int, float, int], pygame.Surface] = cast(
        Dict[Tuple[bool, int, float, int], pygame.Surface], {}
    )

    @classmethod
    def load_sprites(cls) -> None:
        if cls._normal_sprite is None:
            cls._normal_sprite = get_image(_SPRITE_DIR / "Mine_City_Sprite_01.png")
        if cls._normal_sprite2 is None:
            cls._normal_sprite2 = get_image(_SPRITE_DIR / "Mine_City_Sprite_02.png")
        if cls._explosion_sprite is None:
            cls._explosion_sprite = get_image(
                _SPRITE_DIR / "Mine_City_Sprite_Explodindo_01.png"
            )
        if cls._explosion_sprite2 is None:
            cls._explosion_sprite2 = get_image(
                _SPRITE_DIR / "Mine_City_Sprite_Explodindo_02.png"
            )

    def __init__(self, x: float | None = None, y: float | None = None) -> None:
        # Reaproveita TODA a inicialização da mina genérica (geometria, raio de
        # explosão, timers, scale) — só o visual e os resíduos diferem.
        super().__init__(x, y)
        self._frame2_normal = cast(pygame.Surface, self.__class__._normal_sprite2)
        self._frame2_explosion = cast(pygame.Surface, self.__class__._explosion_sprite2)

    # ------------------------------------------------------------------
    # Resíduos energéticos — calculados pela própria mina (collisions só orquestra)
    # ------------------------------------------------------------------
    def residue_bursts(
        self, cx: float, cy: float, main_radius: float
    ) -> list[dict]:
        """Specs das explosões secundárias DENTRO do raio principal.

        Cada resíduo fica totalmente contido (dist ≤ main_radius - sub_radius), com
        raio/dano menores e atraso escalonado (reação em cadeia). Retorna kwargs
        prontos para `EntityManager.spawn_explosive_effect`.
        """
        bursts: list[dict] = []
        for i in range(NEON_RESIDUE_COUNT):
            sub_r = main_radius * random.uniform(*NEON_RESIDUE_RADIUS_FRAC)
            max_off = max(0.0, main_radius - sub_r)
            dist = max_off * math.sqrt(random.random())  # uniforme na área
            ang = random.uniform(0.0, math.tau)
            bursts.append(
                {
                    "x": cx + math.cos(ang) * dist,
                    "y": cy + math.sin(ang) * dist,
                    "radius": sub_r,
                    "damage": NEON_RESIDUE_DAMAGE,
                    "delay": NEON_RESIDUE_BASE_DELAY + i * NEON_RESIDUE_STAGGER,
                    "color": NEON_RESIDUE_COLORS[i % len(NEON_RESIDUE_COLORS)],
                    "lifetime": NEON_RESIDUE_LIFETIME,
                }
            )
        return bursts

    # ------------------------------------------------------------------
    # Visual — sprites próprios animados em 2 frames (idle e explosão)
    # ------------------------------------------------------------------
    def _current_frame_sprite(self) -> tuple[pygame.Surface, float]:
        """Escolhe o sprite do frame atual (sem mutar estado — §3). Devolve
        (sprite, scale)."""
        if self.is_exploding:
            elapsed = max(0.0, 3.0 - self.pre_explosion_timer)
            frame = int(elapsed * NEON_EXPLODE_FPS) % 2
            sprite = self.explosion_sprite if frame == 0 else self._frame2_explosion
            return sprite, 1.0
        frame = int(self.animation_timer * NEON_IDLE_FPS) % 2
        sprite = self.normal_sprite if frame == 0 else self._frame2_normal
        return sprite, self.pulse_scale

    def draw(self, surface: pygame.Surface) -> None:
        x, y = self.x, self.y
        if self.shake_timer > 0:
            si = int(self.shake_intensity)
            x += random.randint(-si, si)
            y += random.randint(-si, si)

        sprite, scale = self._current_frame_sprite()
        frame_id = 0 if sprite in (self.normal_sprite, self.explosion_sprite) else 1
        scale_key = round(scale * 20) / 20
        angle_key = round(self.rotation_angle % 360 / 3) * 3
        cache_key = (self.is_exploding, frame_id, scale_key, angle_key)

        cache = self.__class__._transform_cache
        final_sprite = cache.get(cache_key)
        if final_sprite is None:
            if len(cache) > 600:
                cache.clear()
            w = int(self.sprite_width * self.scale * scale)
            h = int(self.sprite_height * self.scale * scale)
            scaled = pygame.transform.scale(sprite, (max(1, w), max(1, h)))
            if not self.is_exploding:
                scaled = pygame.transform.rotate(scaled, angle_key)
            cache[cache_key] = scaled
            final_sprite = scaled

        surface.blit(
            final_sprite,
            (int(x - final_sprite.get_width() / 2), int(y - final_sprite.get_height() / 2)),
        )

        if self.is_exploding:
            progress = 1 - (self.pre_explosion_timer / 3.0)
            alpha = int(0.2 * 255 + (0.7 - 0.2) * 255 * progress)
            self._indicator_surface.fill((0, 0, 0, 0))
            er = self.explosion_radius
            pygame.draw.circle(
                self._indicator_surface, (*NEON_INDICATOR_COLOR, alpha), (er, er), er
            )
            surface.blit(
                self._indicator_surface, (self.x - er, self.y - er)
            )


sprite_loader.register("CityMine", CityMine.load_sprites)
