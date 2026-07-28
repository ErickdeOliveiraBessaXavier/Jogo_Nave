"""Boss Square Projectile - Indestructible projectile launched by the boss."""

import math
import random

import pygame

from .._shared.draw_utils import draw_square_trail_particle, rotated_square_corners
from .square_base import SquareProjectileBase


class BossSquare(SquareProjectileBase):
    """
    Indestructible square projectile launched by the boss in frenzy mode.

    Features:
    - Flies towards player with slight inaccuracy
    - Pulsating animation like power-ups
    - Cannot be destroyed by bullets
    - Causes damage on collision with player
    """

    # Giro sobre o próprio eixo, em graus/s, por estado. NENHUM é zero: o
    # quadrado gira a batalha inteira. Antes o estado "orbiting" forçava
    # `rotation = 0.0` e a órbita ficava com 14 blocos parados.
    SPIN_ORBITING = 140.0  # constante e suave, sem competir com a órbita
    SPIN_PREPARING = 720.0  # telegrafa o disparo (mantido do original)
    SPIN_FLYING = 360.0  # projétil em voo (mantido do original)
    SPIN_SCATTERING = 540.0  # solto no fim, gira mais enquanto se afasta

    # Encerramento: tempo que o quadrado leva para se afastar e sumir depois de
    # o boss cair. Curto o bastante para não atrasar a transição de fase.
    SCATTER_DURATION = 0.9
    SCATTER_SPEED_MIN = 170.0
    SCATTER_SPEED_MAX = 330.0

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        size: float,
        is_orbital: bool = False,
        orbit_radius: float = 0,
        orbit_angle: float = 0,
        orbit_speed: float = 0,
        speed_var: float = 1.0,
        palette: dict[str, tuple[int, int, int]] | None = None,
        owner: object | None = None,
    ):
        super().__init__(x, y, size)
        self.vx = vx
        self.vy = vy

        # Palette support
        self.palette = palette

        # Dono do quadrado ORBITAL (o boss). Existe porque o orbital não tem
        # movimento próprio: quem o posiciona a cada frame é o dono, com um lerp
        # até um ponto derivado do centro dele. Sem dono vivo o quadrado não é uma
        # entidade — é um resto parado na tela. Ver `update`.
        #
        # Projétil lançado NÃO tem dono: é um objeto novo, criado por
        # `_create_square_projectile`, que voa sozinho e morre pela borda.
        self.owner = owner

        # Orbital attributes
        self.is_orbital = is_orbital
        self.orbit_radius = orbit_radius
        self.orbit_angle = orbit_angle
        self.orbit_speed = orbit_speed
        self.orbit_speed_original = orbit_speed
        self.speed_var = speed_var
        self.state = "orbiting" if is_orbital else "flying"
        self.prepare_timer = 0.0
        self.frenzy_orbit_multiplier = 1.0

        # Convenção do projeto (`causes_damage`, ver metropolis_*/stone_golem):
        # entidade que existe na tela mas não deve machucar. Vira False no
        # instante em que o boss morre — a partir daí o quadrado é só efeito.
        self.causes_damage = True
        # Espalhamento de encerramento: velocidade própria e relógio próprio.
        self._scatter_vx = 0.0
        self._scatter_vy = 0.0
        self._scatter_timer = 0.0

        # Animation
        self.animation_timer = 0.0
        self.animation_offset = random.uniform(0, 10)

        # Growth effect - aumenta conforme se move
        self.growth_timer = 0.0
        self.max_growth_scale = 4.5
        self.growth_duration = 2.0

    def set_frenzy_mode(self, is_frenzy: bool) -> None:
        """Set frenzy mode and adjust orbital speed."""
        if is_frenzy:
            self.frenzy_orbit_multiplier = 2.0
        else:
            self.frenzy_orbit_multiplier = 1.0
        self.orbit_speed = self.orbit_speed_original * self.frenzy_orbit_multiplier

    def update(
        self, dt: float, screen_width: int = 1600, screen_height: int = 900
    ) -> None:
        """Update position and animation."""
        # Orbital sem dono vivo se desprende e se espalha.
        #
        # O quadrado orbital é a ÚNICA entidade do jogo sem caminho próprio de
        # morte: a remoção por borda logo abaixo é explicitamente restrita a
        # `not self.is_orbital`, porque um orbital nunca sai da tela — ele fica
        # preso ao boss. Isso o deixava vivo para sempre depois que o boss
        # morria, ainda colidindo e desenhando.
        #
        # A condição mora AQUI, e não num handler de morte do boss, porque o
        # invariante é do quadrado: ele depende do dono para se mover. Assim
        # vale para toda forma de o dono sumir (abatido, force-kill de fim de
        # estágio, troca de fase) em vez de só para o caminho que alguém lembrou
        # de cobrir.
        if self.is_orbital and self.state != "scattering":
            owner = self.owner
            if owner is None or getattr(owner, "dead", True):
                self._begin_scatter()

        if self.state == "scattering":
            # Caminho próprio e COMPLETO: o espalhamento controla posição e
            # tamanho, então sai antes do bloco de crescimento/pulsação abaixo —
            # que sobrescreveria o `size` do encolhimento no mesmo frame.
            self._update_scatter(dt)
            self.rotation = (self.rotation + dt * self.SPIN_SCATTERING) % 360.0
            self.border_anim_offset += dt * 20
            self._update_trail(dt, False)
            return

        # Move only if not orbital
        if not self.is_orbital:
            self.x += self.vx * dt
            self.y += self.vy * dt

        # Giro sobre o próprio eixo — nunca para, em nenhum estado. A órbita em
        # volta do boss é outra coisa e continua igual: quem a dirige é o boss
        # (`Boss._update_lerps`), mexendo em x/y. Aqui é só o giro do bloco.
        if self.state == "preparing":
            self.rotation += dt * self.SPIN_PREPARING
            self.border_anim_offset += dt * 25
        elif self.state == "orbiting":
            self.rotation += dt * self.SPIN_ORBITING
            self.border_anim_offset += dt * 10
        else:
            self.rotation += dt * self.SPIN_FLYING
            self.border_anim_offset += dt * 15
        self.rotation %= 360.0

        # Efeito de crescimento progressivo (only for projectiles)
        if not self.is_orbital:
            self.growth_timer += dt
            growth_progress = min(self.growth_timer / self.growth_duration, 1.0)
            growth_scale = 1.0 + (self.max_growth_scale - 1.0) * (
                1.0 - (1.0 - growth_progress) ** 2
            )
        else:
            growth_scale = 1.0

        # Pulsation animation
        self.animation_timer += dt * 5
        if self.state == "preparing":
            pulse_scale = 1.0 + 0.4 * abs(math.sin(self.prepare_timer * 10))
            self.prepare_timer += dt
        else:
            anim_value = self.animation_timer + self.animation_offset
            pulse_scale = 1.0 + 0.2 * abs(math.cos(anim_value))

        # Combina crescimento com pulsação
        self.size = self.base_size * growth_scale * pulse_scale

        # Atualizar partículas de trail da classe base
        self._update_trail(dt, self.state == "flying")

        # Remove if off-screen (only for projectiles)
        if not self.is_orbital:
            margin = 300
            if (
                self.x < -margin
                or self.x > screen_width + margin
                or self.y < -margin
                or self.y > screen_height + margin
            ):
                self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the square projectile with rotation and trail."""
        if self.dead:
            return

        # Paleta de cores dinâmica
        from .boss_pixel_map import PROJECTILE_COLOR_KEY, PROJECTILE_HIGHLIGHT_KEY, TRAIL_COLOR_KEY
        
        # Cores padrão caso não haja paleta
        hull_color = (255, 0, 0)
        energy_color = (255, 255, 100)
        trail_base = (255, 50, 0)
        
        if self.palette:
            hull_color = self.palette.get(PROJECTILE_COLOR_KEY, hull_color)
            energy_color = self.palette.get(PROJECTILE_HIGHLIGHT_KEY, energy_color)
            trail_base = self.palette.get(TRAIL_COLOR_KEY, trail_base)

        # Desenhar partículas de trail primeiro (atrás do quadrado)
        for p in self.trail_particles:
            if p.alpha > 0:
                # Interpola a cor da trilha baseada na vida da partícula
                r = int(trail_base[0] * p.life + 255 * (1 - p.life))
                g = int(trail_base[1] * p.life + 100 * (1 - p.life))
                b = int(trail_base[2] * p.life)
                draw_square_trail_particle(
                    surface, p.x, p.y, p.size, (r, g, b), p.alpha
                )

        # Calcular cor com intensidade alternada (usa offset para dessincronizar)
        anim_value = self.animation_timer + self.animation_offset
        cos_val = abs(math.cos(anim_value))
        
        # Interpola entre hull_color e energy_color para efeito pulsante
        r = int(hull_color[0] + (energy_color[0] - hull_color[0]) * cos_val * 0.3)
        g = int(hull_color[1] + (energy_color[1] - hull_color[1]) * cos_val * 0.3)
        b = int(hull_color[2] + (energy_color[2] - hull_color[2]) * cos_val * 0.3)
        color = (r, g, b)
        
        border_color = energy_color

        rotated_corners = rotated_square_corners(
            self.x, self.y, self.size / 2, math.radians(self.rotation)
        )
        pygame.draw.polygon(surface, color, rotated_corners)
        self._draw_animated_border(surface, rotated_corners, border_color)

    def _begin_scatter(self) -> None:
        """Solta o quadrado da órbita quando o boss cai.

        **Para de causar dano no mesmo instante.** Durante a sequência de morte
        do boss a nave fica parada e sem controle; um bloco que ainda machucasse
        aí cobraria do jogador um dano que ele não tinha como evitar. Daqui em
        diante o quadrado é puramente visual.

        A direção é radial a partir do dono — os 14 abrem como um anel se
        rompendo, e não numa direção aleatória qualquer. Sem dono (caso raro do
        órfão), qualquer direção serve.
        """
        self.state = "scattering"
        self.causes_damage = False
        self._scatter_timer = 0.0

        owner = self.owner
        angle = None
        if owner is not None:
            ox = getattr(owner, "x", None)
            oy = getattr(owner, "y", None)
            if ox is not None and oy is not None:
                cx = ox + getattr(owner, "w", 0) / 2
                cy = oy + getattr(owner, "h", 0) / 2
                dx, dy = self.x - cx, self.y - cy
                if dx or dy:
                    angle = math.atan2(dy, dx)
        if angle is None:
            angle = random.uniform(0.0, math.tau)
        # Abertura leve para o anel não sair perfeitamente radial (lê como
        # explosão, não como animação sincronizada).
        angle += random.uniform(-0.35, 0.35)

        speed = random.uniform(self.SCATTER_SPEED_MIN, self.SCATTER_SPEED_MAX)
        self._scatter_vx = math.cos(angle) * speed
        self._scatter_vy = math.sin(angle) * speed

    def _update_scatter(self, dt: float) -> None:
        """Afasta e encolhe até sumir.

        Encolher em vez de esmaecer: o desenho é um quadrado de pixels sem canal
        alpha, então `size → 0` é o dissolver que a entidade já sabe fazer — e
        de quebra tira o rect de colisão do caminho antes mesmo do fim.
        """
        self._scatter_timer += dt
        progress = min(1.0, self._scatter_timer / self.SCATTER_DURATION)

        self.x += self._scatter_vx * dt
        self.y += self._scatter_vy * dt
        # Desacelera enquanto se afasta: dá o "sopro" do rompimento.
        self._scatter_vx *= 1.0 - min(1.0, 1.6 * dt)
        self._scatter_vy *= 1.0 - min(1.0, 1.6 * dt)

        self.size = self.base_size * (1.0 - progress * progress)
        if progress >= 1.0:
            self.dead = True

    def get_rect(self) -> pygame.Rect:
        """Get collision rectangle."""
        half_size = self.size / 2
        return pygame.Rect(self.x - half_size, self.y - half_size, self.size, self.size)
