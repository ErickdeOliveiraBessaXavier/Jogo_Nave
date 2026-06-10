"""Vórtice de Poeira — Inimigo de controle de área (área denial) do bioma MOUNTAINS.

Substituto da "CuttingStorm". Um fenômeno terrestre que se desloca rente ao chão
na perspectiva lateral (side-view). Surge da direita e avança para a esquerda.
Ocasionalmente para seu deslocamento para gerar uma rajada vertical violenta.

Comportamento:
1. DESLOCAMENTO: Move-se horizontalmente para a esquerda. Causa dano circular na base.
2. RAJADA: Para, carrega e lança uma coluna de vento/detritos para cima.
   Causa dano em toda a coluna vertical (jogador e inimigos).

Visual:
- Partículas de poeira e areia (pixels).
- Fragmentos de rocha (assets de IceGolem).
- Efeito de vento e turbulência.

Contratos (CLAUDE.md): herda EnemyHitMixin (§9), update via
update_in_context (§5), draw sem efeitos colaterais (§3).
"""

import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Final, List, Any

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class _DustVortexState(Enum):
    MOVING = auto()
    GUSTING = auto()
    DISSIPATING = auto()


class _VortexParticle:
    """Partícula individual de poeira ou detrito dentro do vórtice."""

    __slots__ = ("x", "y", "vx", "vy", "orbit_radius", "angle", "angular_speed", "life", "max_life", "size", "color", "is_fragment", "img_idx")

    def __init__(
        self,
        cx: float,
        cy: float,
        orbit_radius: float,
        is_fragment: bool = False,
        img_idx: int = 0
    ):
        self.orbit_radius = orbit_radius
        self.angle = random.uniform(0.0, math.tau)
        self.angular_speed = random.uniform(4.0, 9.0) * random.choice([-1, 1])
        self.x = cx + math.cos(self.angle) * orbit_radius
        self.y = cy + math.sin(self.angle) * orbit_radius * 0.4
        self.vx = 0.0
        self.vy = 0.0
        self.max_life = random.uniform(0.8, 1.8)
        self.life = self.max_life
        self.size = random.randint(1, 3) if not is_fragment else random.randint(4, 9)
        
        # Cores de terra/areia/poeira (Mountain Palette)
        self.color = random.choice([
            (160, 140, 110), (140, 120, 90), (180, 160, 130), (120, 100, 80)
        ])
        self.is_fragment = is_fragment
        self.img_idx = img_idx

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float, cx: float, cy: float, state: _DustVortexState, gust_progress: float, ground_y: float):
        self.life -= dt
        
        if state == _DustVortexState.GUSTING:
            # Sobe violentamente na rajada
            rise_speed = 700.0 * gust_progress
            self.vy = -rise_speed * random.uniform(0.7, 1.3)
            # Oscilação horizontal turbulenta
            self.vx = math.sin(self.life * 12.0 + self.angle) * 60.0
            self.x += self.vx * dt
            self.y += self.vy * dt
            # Afunila a coluna conforme sobe
            self.orbit_radius *= 0.98
        elif state == _DustVortexState.DISSIPATING:
            # Perde a força ascendente e cai com gravidade
            gravity = 800.0
            self.vy += gravity * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            
            # Atrito horizontal
            self.vx *= 0.95
            
            # Se bater no chão, "quica" ou morre
            if self.y > ground_y:
                self.y = ground_y
                self.vy = -self.vy * 0.3
                self.life *= 0.5
        else:
            # Orbitando a base horizontalmente (MOVING)
            self.angle += self.angular_speed * dt
            self.x = cx + math.cos(self.angle) * self.orbit_radius
            self.y = cy + math.sin(self.angle) * self.orbit_radius * 0.4
            
        return self.life > 0.0


class CuttingStorm:
    """Vórtice de Poeira — Implementação renovada da CuttingStorm.
    
    Nota: Este inimigo é um perigo ambiental indestrutível. 
    Não recebe dano e não bloqueia tiros.
    """
    
    # Dimensões e Combate (RADIUS usado pelo Spawner)
    RADIUS: Final = 64
    DAMAGE_RADIUS: Final = 58.0
    GUST_RADIUS: Final = 48.0
    
    # Movimento
    MOVE_SPEED: Final = 115.0
    
    # Timing
    GUST_INTERVAL: Final = (3.5, 6.0)
    GUST_DURATION: Final = 2.4
    GUST_WARNING_TIME: Final = 0.7
    DISSIPATION_DURATION: Final = 1.2
    
    # Assets
    FRAGMENT_SUBDIR = "Ice_Golem_Cristal/Fragmentos"
    _fragment_sprites: List[pygame.Surface] = []

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        screen_w = Config.SCREEN_WIDTH
        screen_h = Config.SCREEN_HEIGHT
        
        self.w = self.RADIUS * 2
        self.h = self.RADIUS * 2
        # Ground_y alinhado para que a base do ciclone toque o chão
        self.ground_y = screen_h - 40.0
        
        self.x = float(x if x is not None else screen_w + 120)
        # Ajusta y para que o centro da base (layer 0) fique rente ao ground_y
        self.y = self.ground_y - self.RADIUS
        
        self.side_scroll = side_scroll
        self.dead = False
        self.active = True
        self.health = 100.0  # Atributo mantido p/ compatibilidade com Spawner
        self.hit_timer = 0.0
        self.causes_damage = True # Causa dano ao contato, mas não recebe
        
        self._aggr = max(0.5, aggressiveness_multiplier)
        self._state = _DustVortexState.MOVING
        self._state_timer = random.uniform(*self.GUST_INTERVAL) / self._aggr
        
        self._particles: List[_VortexParticle] = []
        self._anim_time = 0.0
        self._enemy_hit_cooldown: dict[int, float] = {}
        
        if not self._fragment_sprites:
            self._load_fragments()
            
        self._rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @classmethod
    def _load_fragments(cls):
        folder = BASE_DIR / "assets" / "images" / cls.FRAGMENT_SUBDIR
        if folder.exists():
            for i in range(1, 5):
                path = folder / f"Ice_Golem_Fragmentos_{i:02d}.png"
                if path.exists():
                    img = get_image(path)
                    img = img.copy()
                    img.fill((150, 120, 90), special_flags=pygame.BLEND_RGB_MULT)
                    cls._fragment_sprites.append(pygame.transform.smoothscale(img, (16, 16)))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def _center(self) -> tuple[float, float]:
        """Centro da base do ciclone (no chão)."""
        return self.x + self.RADIUS, self.y + self.RADIUS

    @property
    def _hitbox_center(self) -> tuple[float, float]:
        """Centro da massa (elevado)."""
        cx, cy = self._center
        return cx, cy - 40.0

    def collision_circle(self) -> tuple[float, float, float]:
        """Hitbox para dano NO JOGADOR e OUTROS INIMIGOS."""
        cx, cy = self._hitbox_center
        return cx, cy, float(self.RADIUS)

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        blasts = self.update(ctx.sdt)
        if blasts:
            ctx.new_area_blasts.extend(blasts)
            self._apply_damage_to_enemies(blasts, ctx.other_enemies, ctx.dt)

    def _apply_damage_to_enemies(self, blasts: list[tuple[float, float, float]], others: list[Any], dt: float):
        for eid in list(self._enemy_hit_cooldown.keys()):
            self._enemy_hit_cooldown[eid] -= dt
            if self._enemy_hit_cooldown[eid] <= 0:
                del self._enemy_hit_cooldown[eid]

        for bx, by, br in blasts:
            for en in others:
                if en is self or getattr(en, "dead", False):
                    continue
                
                eid = id(en)
                if eid in self._enemy_hit_cooldown:
                    continue

                try:
                    ecx, ecy, er = en.collision_circle()
                    dist_sq = (bx - ecx)**2 + (by - ecy)**2
                    if dist_sq < (br + er)**2:
                        if hasattr(en, "take_damage"):
                            en.take_damage(1)
                            self._enemy_hit_cooldown[eid] = 0.15
                except (AttributeError, TypeError):
                    continue

    def update(self, dt: float) -> list[tuple[float, float, float]]:
        self._anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        blasts = []
        cx, cy = self._center

        if self._state == _DustVortexState.MOVING:
            self.x -= self.MOVE_SPEED * dt
            self._state_timer -= dt
            blasts.append((cx, cy, self.DAMAGE_RADIUS))
            if self._state_timer <= 0:
                self._state = _DustVortexState.GUSTING
                self._state_timer = self.GUST_DURATION
            if self.x < -250:
                self.dead = True

        elif self._state == _DustVortexState.GUSTING:
            self._state_timer -= dt
            progress = 1.0 - (self._state_timer / self.GUST_DURATION)
            blasts.append((cx, cy, self.DAMAGE_RADIUS))
            warn_frac = self.GUST_WARNING_TIME / self.GUST_DURATION
            if progress > warn_frac:
                growth = (progress - warn_frac) / (1.0 - warn_frac)
                num_segments = 7
                for i in range(1, num_segments):
                    h_off = i * 120.0 * growth * 2.2
                    blasts.append((cx, cy - h_off, self.GUST_RADIUS))
            if self._state_timer <= 0:
                self._state = _DustVortexState.DISSIPATING
                self._state_timer = self.DISSIPATION_DURATION

        elif self._state == _DustVortexState.DISSIPATING:
            self._state_timer -= dt
            blasts.append((cx, cy, self.DAMAGE_RADIUS))
            if self._state_timer <= 0:
                self._state = _DustVortexState.MOVING
                self._state_timer = random.uniform(*self.GUST_INTERVAL) / self._aggr

        self._spawn_particles(dt)
        gust_p = 1.0
        if self._state == _DustVortexState.GUSTING:
            gust_p = 1.0 - (self._state_timer / self.GUST_DURATION)
        
        i = 0
        while i < len(self._particles):
            p = self._particles[i]
            if not p.update(dt, cx, cy, self._state, gust_p, self.ground_y):
                self._particles[i] = self._particles[-1]
                self._particles.pop()
            else:
                i += 1

        self._rect.topleft = (int(self.x), int(self.y))
        return blasts

    def _spawn_particles(self, dt: float):
        rate = 65 if self._state == _DustVortexState.MOVING else 180
        if self._state == _DustVortexState.DISSIPATING:
            rate = 30
        count = int(rate * dt)
        if count == 0 and random.random() < rate * dt:
            count = 1
        cx, cy = self._center
        for _ in range(count):
            is_frag = random.random() < 0.22
            orbit = random.uniform(5, self.RADIUS * 1.1)
            idx = random.randint(0, len(self._fragment_sprites) - 1) if self._fragment_sprites else 0
            self._particles.append(_VortexParticle(cx, cy, orbit, is_frag, idx))

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        self._draw_telegraph_body(surface, cx, cy)
        for p in self._particles:
            alpha = int(255 * (p.life / p.max_life))
            if not p.is_fragment:
                color = (*p.color, alpha)
                p_surf = pygame.Surface((p.size, p.size), pygame.SRCALPHA)
                p_surf.fill(color)
                surface.blit(p_surf, (int(p.x), int(p.y)))
            else:
                if self._fragment_sprites:
                    img = self._fragment_sprites[p.img_idx]
                    rot = pygame.transform.rotate(img, self._anim_time * 240.0 + p.angle * 40)
                    if p.size != 16:
                        rot = pygame.transform.scale(rot, (p.size, p.size))
                    rot.set_alpha(alpha)
                    surface.blit(rot, rot.get_rect(center=(int(p.x), int(p.y))).topleft)

    def _draw_telegraph_body(self, surface: pygame.Surface, cx: float, cy: float):
        """Desenha o corpo principal e o pilar usando o estilo de espiral de alta intensidade."""
        is_gusting = self._state == _DustVortexState.GUSTING
        is_dissipating = self._state == _DustVortexState.DISSIPATING
        
        # Paleta rica de cores (tons de poeira, terra e areia)
        WIND_COLORS = [
            (215, 200, 180),  # Areia clara
            (190, 175, 155),  # Poeira média
            (225, 215, 200),  # Areia muito clara
            (160, 145, 125),  # Terra seca
        ]
        
        num_body_layers = 10
        body_height = 80.0
        
        for layer in range(num_body_layers):
            frac = layer / num_body_layers
            layer_radius = self.RADIUS * (0.4 + frac * 0.7)
            y_layer = cy - frac * body_height
            
            num_arcs_per_layer = 3
            for i in range(num_arcs_per_layer):
                speed_mult = 14.0 + (i % 2) * 4.0
                t = self._anim_time * speed_mult + i * (math.tau / num_arcs_per_layer) + layer * 0.5
                
                r_scale = 0.8 + 0.3 * math.sin(t * 0.4)
                w = max(1, int(layer_radius * 2.3 * r_scale))
                h = max(1, int(layer_radius * 0.8 * r_scale))
                
                rect = pygame.Rect(0, 0, w, h)
                x_osc = math.sin(t * 0.7) * (5.0 * frac)
                rect.center = (int(cx + x_osc), int(y_layer))
                
                angle = t % math.tau
                dissipation_fade = (self._state_timer / self.DISSIPATION_DURATION) if is_dissipating else 1.0
                alpha = int((40 + (layer % 3) * 15) * (1.0 - frac * 0.3) * dissipation_fade)
                
                if alpha > 0:
                    color_idx = (layer + i) % len(WIND_COLORS)
                    current_color = WIND_COLORS[color_idx]
                    arc_surf = pygame.Surface((w, h), pygame.SRCALPHA)
                    arc_len = 1.0 + (i % 2) * 0.5
                    pygame.draw.arc(arc_surf, (*current_color, alpha), arc_surf.get_rect(), angle, angle + arc_len, 2)
                    surface.blit(arc_surf, rect.topleft)

        if is_gusting or is_dissipating:
            progress = 1.0 if is_dissipating else (1.0 - (self._state_timer / self.GUST_DURATION))
            num_pillar_layers = 22
            max_h = 580.0 * progress
            for i in range(num_pillar_layers):
                f = i / num_pillar_layers
                if f > progress and not is_dissipating:
                    continue
                t_col = self._anim_time * 15.0 + i * 0.4
                y_pos = cy - f * max_h
                r_col = self.RADIUS * (0.7 + f * 1.3)
                w_col = max(1, int(r_col * 2.1))
                h_col = max(1, int(r_col * 0.7))
                x_osc = math.sin(t_col * 0.8) * 30.0 * f
                rect_col = pygame.Rect(0, 0, w_col, h_col)
                rect_col.center = (int(cx + x_osc), int(y_pos))
                
                alpha_col = int(75 * (1.0 - f * 0.6) * dissipation_fade)
                if alpha_col > 0:
                    pillar_color = WIND_COLORS[(i % len(WIND_COLORS))]
                    arc_surf = pygame.Surface((w_col, h_col), pygame.SRCALPHA)
                    pygame.draw.arc(arc_surf, (*pillar_color, alpha_col), arc_surf.get_rect(), t_col % math.tau, (t_col % math.tau) + 1.5, 2)
                    surface.blit(arc_surf, rect_col.topleft)
                    if i % 3 == 0:
                        line_col = (*pillar_color, int(alpha_col * 0.7))
                        lx = random.randint(-w_col//2, w_col//2)
                        ly_len = random.randint(10, 25)
                        pygame.draw.line(surface, line_col, (int(cx + x_osc + lx), int(y_pos)), (int(cx + x_osc + lx), int(y_pos - ly_len)), 1)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult
        # Causa dano no jogador mas o inimigo é indestrutível
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def on_hit(self, _damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        """Ignora dano de projéteis (indestrutível)."""
        from ..systems.hit_result import HitResult
        return HitResult()

    def take_damage(self, _amount: int) -> None:
        """Hazard não recebe dano."""
        pass

    def should_remove(self) -> bool:
        return self.dead

    def get_points_value(self) -> int:
        return 0 # Hazard não dá pontos


DustVortex = CuttingStorm
