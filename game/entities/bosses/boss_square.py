"""Boss Square Projectile - Indestructible projectile launched by the boss."""

import math
import random

import pygame

from .._shared.draw_utils import draw_square_trail_particle, rotated_square_corners
from .square_base import SquareProjectileBase


def _lerp_rgb(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


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

    # ── Identidade visual ───────────────────────────────────────────────────
    #
    # O quadrado é lido como PEDAÇO DO BOSS porque repete a gramática dele: o
    # chassi do boss (`boss_pixel_map`) é contorno escuro `D` → rampa de aço
    # azulado `B`/`C`/`E` → núcleo quente `G`/`H` embutido. Aqui é a mesma
    # construção concêntrica, com o casco vindo da PALETA DO BOSS (então
    # acompanha o lerp para o frenzy) e só a energia sendo própria.
    #
    # A energia é CIANO por três motivos: é complementar do núcleo laranja do
    # boss, o que faz os dois lerem como um sistema só (coração quente, sistemas
    # auxiliares frios); contrasta por saturação com o aço dessaturado do casco;
    # e evita laranja/vermelho, já dominantes em explosões e ataques.
    #
    # No frenzy a energia NÃO vira vermelha — ela intensifica. O casco escurece
    # junto com o boss (vem da paleta dele), então o quadrado se corrompe com o
    # dono sem virar mais um borrão quente na tela.
    ENERGY_CORE = (0, 210, 255)
    ENERGY_HOT = (190, 250, 255)
    # Fração do meio-lado de cada anel concêntrico, de fora para dentro.
    RING_HULL = 0.80
    RING_CORE = 0.52
    RING_HOT = 0.24

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

    @property
    def drawn_by_owner(self) -> bool:
        """True quando quem desenha é o boss, não o EntityManager.

        O boss desenha os orbitais em DUAS passadas (metade atrás do corpo,
        metade na frente) para a órbita ler como volta em torno de um objeto com
        volume. Sem esta divisão de responsabilidade os dois desenhavam o mesmo
        quadrado — e o do EntityManager, por vir depois, apagava tanto a
        aparência quanto a camada "atrás" que o boss tinha acabado de compor.

        Espalhando, o dono já morreu e pode ter sido solto: aí o EntityManager
        assume, senão ninguém desenharia a animação de encerramento.
        """
        return self.is_orbital and self.state != "scattering"

    def _hull_colors(self) -> tuple[
        tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]
    ]:
        """(contorno, casco, brilho) — o aço do boss, vindo da paleta dele.

        É o que amarra o quadrado ao dono: mesmo material, mesma rampa, e
        acompanha de graça o lerp de cor quando o boss entra em frenzy.
        """
        pal = self.palette
        if not pal:
            # Fallback neutro. O antigo era VERMELHO puro (255,0,0) e era o que
            # o jogador via de fato: os orbitais nunca recebiam paleta, então
            # caíam aqui — a origem do "parecem de outro conjunto de sprites".
            return (20, 25, 35), (80, 100, 120), (150, 170, 190)
        return (
            pal.get("D", (20, 25, 35)),
            pal.get("C", (80, 100, 120)),
            pal.get("F", (150, 170, 190)),
        )

    def draw(
        self, surface: pygame.Surface, off_x: float = 0.0, off_y: float = 0.0
    ) -> None:
        """Desenha o quadrado: contorno, casco, núcleo de energia e centro.

        Concêntrico de propósito. A silhueta não muda com o giro, então o bloco
        continua legível rodando — que é o requisito de leitura em movimento —,
        e os anéis repetem a leitura do chassi do boss (contorno escuro, corpo de
        aço, energia embutida no meio) em vez de serem um quadrado chapado.

        `off_x/off_y` é o tremor do boss, aplicado quando é ele quem desenha.
        """
        if self.dead or self.size < 1.0:
            return

        outline, hull, sheen = self._hull_colors()

        # Trilha atrás do corpo, esfriando para o branco-ciano da energia (antes
        # aquecia para laranja, brigando com as explosões).
        for p in self.trail_particles:
            if p.alpha > 0:
                fade = 1.0 - p.life
                r = int(hull[0] * p.life + self.ENERGY_HOT[0] * fade)
                g = int(hull[1] * p.life + self.ENERGY_HOT[1] * fade)
                b = int(hull[2] * p.life + self.ENERGY_HOT[2] * fade)
                draw_square_trail_particle(
                    surface, p.x + off_x, p.y + off_y, p.size, (r, g, b), p.alpha
                )

        cx, cy = self.x + off_x, self.y + off_y
        half = self.size / 2
        angle = math.radians(self.rotation)

        # Pulso do núcleo — dessincronizado por `animation_offset` para os 14 não
        # piscarem em uníssono.
        pulse = 0.5 + 0.5 * abs(math.cos(self.animation_timer + self.animation_offset))
        core = _lerp_rgb(self.ENERGY_CORE, self.ENERGY_HOT, pulse * 0.55)

        def anel(frac: float, color: tuple[int, int, int]) -> list[tuple[float, float]]:
            corners = rotated_square_corners(cx, cy, half * frac, angle)
            pygame.draw.polygon(surface, color, corners)
            return corners

        borda = anel(1.0, outline)  # contorno escuro (chave `D` do boss)
        anel(self.RING_HULL, hull)  # casco de aço (chave `C`)
        anel(self.RING_CORE, core)  # energia
        if half * self.RING_HOT >= 1.0:
            anel(self.RING_HOT, self.ENERGY_HOT)  # centro quente

        # Reflexo diagonal: o chassi do boss tem `F` como face iluminada, e é o
        # detalhe que faz o bloco parecer metal e não um adesivo.
        if half >= 5.0:
            pygame.draw.line(
                surface,
                sheen,
                borda[0],
                borda[1],
                max(1, int(self.size / 12)),
            )

        self._draw_animated_border(surface, borda, core)

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
