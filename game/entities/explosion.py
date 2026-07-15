import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, Sequence

import pygame

from ..core.config import config as Config

_TAU: float = math.pi * 2


class ImpactPattern:
    """Formas de explosão. Puramente estético — nada aqui afeta dano ou hitbox.

    A `Explosion` guarda partículas como `[x, y, vx, vy, life]`; um padrão é a
    combinação de (1) como essas 5 casas são semeadas, (2) o atrito/gravidade
    aplicados no update e (3) a primitiva usada no desenho. Nenhum padrão
    adiciona campo por partícula — é o que permite reusar o pool de explosões
    existente em vez de criar um sistema paralelo.
    """

    BURST = "burst"  # radial aleatório — o comportamento histórico
    RING = "ring"  # onda de choque anelar
    ECHO = "echo"  # anéis concêntricos em sequência
    STAR = "star"  # braços retos formando uma estrela
    SPARK = "spark"  # faíscas riscadas
    BOLT = "bolt"  # raios curtos em zigue-zague
    IMPLODE = "implode"  # partículas convergindo para o centro
    WISP = "wisp"  # névoa lenta subindo
    EMBER = "ember"  # brasas que jorram e caem
    SHATTER = "shatter"  # estilhaços quadrados


@dataclass(frozen=True)
class _Motion:
    """Física de um padrão. `drag` é por-frame (herdado do burst original)."""

    drag: float = 0.96
    gravity: float = 0.0  # px/s² somados a vy


_BURST_MOTION = _Motion()

# Só os padrões que fogem do burst aparecem aqui; o resto cai no default.
_MOTION: Dict[str, _Motion] = {
    # Anéis não desaceleram: é a velocidade constante que os faz lerem como
    # uma frente de onda em vez de uma nuvem se dissipando.
    ImpactPattern.RING: _Motion(drag=1.0),
    ImpactPattern.ECHO: _Motion(drag=1.0),
    ImpactPattern.STAR: _Motion(drag=0.99),
    # A implosão precisa chegar ao centro dentro da própria vida — com atrito
    # ela parava no meio do caminho e o efeito virava um anel parado.
    ImpactPattern.IMPLODE: _Motion(drag=1.0),
    ImpactPattern.WISP: _Motion(drag=0.99),
    ImpactPattern.EMBER: _Motion(drag=0.99, gravity=900.0),
    ImpactPattern.SHATTER: _Motion(drag=0.97),
}


class ExplosionType:
    """Define tipos de explosão com suas paletas de cores."""

    DEFAULT = None  # Laranja/vermelho padrão
    SLIME = [(80, 57, 89), (204, 176, 217), (38, 2, 89), (77, 13, 166), (65, 11, 140)]
    ALIEN = [(37, 217, 166), (78, 217, 74)]  # Verde
    # CITY: "static pop" — descarga elétrica azul → magenta → branco.
    CYBER = [(40, 200, 255), (180, 220, 255), (255, 50, 200), (255, 255, 255)]
    # ICE_GOLEM: colapso de núcleo glacial energético. A paleta vai do azul
    # profundo (partícula se dissipando) ao branco-gelo brilhante (energia
    # cristalina recém-liberada), passando por ciano. Ordem [morte → nascimento]
    # porque _get_color indexa por life_ratio (1 = recém-criada).
    ICE_CORE = [
        (28, 78, 168),  # azul profundo (energia esfriando)
        (44, 134, 224),  # azul elétrico
        (96, 204, 255),  # ciano gelo
        (168, 236, 255),  # ciano claro
        (228, 250, 255),  # branco-gelo (núcleo estilhaçando)
    ]


def _spawn_burst(e: "Explosion", count: int) -> None:
    """Radial aleatório — a explosão histórica do jogo."""
    for _ in range(count):
        angle = random.uniform(0, 360)
        rad_angle = math.radians(angle)
        # Velocidade baseada no tamanho
        base_speed = random.uniform(150, 350) * (e.size / 30)

        vx = base_speed * math.cos(rad_angle)
        vy = base_speed * math.sin(rad_angle)

        life = random.uniform(e.time * 0.6, e.time)
        e.particles.append([e.x, e.y, vx, vy, life])


def _spawn_ring(e: "Explosion", count: int) -> None:
    """Anel: ângulos igualmente espaçados, mesma velocidade, mesma vida.

    A uniformidade é o efeito. Qualquer jitter em velocidade ou vida borra a
    frente da onda e o anel volta a parecer um burst comum.
    """
    speed = 260.0 * (e.size / 30)
    life = e.time * 0.85
    step = _TAU / count
    for i in range(count):
        a = i * step
        e.particles.append([e.x, e.y, math.cos(a) * speed, math.sin(a) * speed, life])


def _spawn_echo(e: "Explosion", count: int) -> None:
    """Três anéis mais lentos e mais curtos a cada camada — daí o eco."""
    rings = 3
    per = max(3, count // rings)
    step = _TAU / per
    for r in range(rings):
        speed = 280.0 * (e.size / 30) * (1.0 - r * 0.3)
        life = e.time * (0.85 - r * 0.18)
        # Meio passo de defasagem por camada: os anéis não se alinham em raios.
        offset = r * step * 0.5
        for i in range(per):
            a = offset + i * step
            e.particles.append(
                [e.x, e.y, math.cos(a) * speed, math.sin(a) * speed, life]
            )


def _spawn_star(e: "Explosion", count: int) -> None:
    """Braços retos: dentro de cada braço a velocidade cresce, o que espalha as
    partículas ao longo de uma reta e desenha a ponta."""
    points = 5
    per = max(2, count // points)
    step = _TAU / points
    for k in range(points):
        a = -math.pi / 2 + k * step  # uma ponta sempre para cima
        ca, sa = math.cos(a), math.sin(a)
        for i in range(per):
            t = (i + 1) / per
            speed = 330.0 * (e.size / 30) * t
            e.particles.append(
                [e.x, e.y, ca * speed, sa * speed, e.time * (0.5 + 0.5 * t)]
            )


def _spawn_spark(e: "Explosion", count: int) -> None:
    """Poucas faíscas, rápidas e curtas — faísca cheia vira nuvem."""
    for _ in range(max(3, count // 3)):
        a = random.uniform(0, _TAU)
        speed = random.uniform(320, 620) * (e.size / 30)
        e.particles.append(
            [
                e.x,
                e.y,
                math.cos(a) * speed,
                math.sin(a) * speed,
                random.uniform(e.time * 0.25, e.time * 0.6),
            ]
        )


def _spawn_bolt(e: "Explosion", count: int) -> None:
    """Uma partícula por raio: ela é a PONTA, e o desenho liga o centro até ela."""
    arms = max(3, min(8, count // 5))
    speed_base = 420.0 * (e.size / 30)
    step = _TAU / arms
    jitter = random.uniform(0, _TAU)
    for i in range(arms):
        a = jitter + i * step + random.uniform(-0.15, 0.15)
        speed = speed_base * random.uniform(0.7, 1.0)
        e.particles.append(
            [
                e.x,
                e.y,
                math.cos(a) * speed,
                math.sin(a) * speed,
                e.time * random.uniform(0.35, 0.6),
            ]
        )


def _spawn_implode(e: "Explosion", count: int) -> None:
    """O inverso do burst: nasce num anel e cai para dentro."""
    radius = 6.0 + e.size * 0.8
    speed = 240.0 * (e.size / 30)
    step = _TAU / count
    for i in range(count):
        a = i * step + random.uniform(-0.08, 0.08)
        ca, sa = math.cos(a), math.sin(a)
        e.particles.append(
            [e.x + ca * radius, e.y + sa * radius, -ca * speed, -sa * speed, e.time * 0.7]
        )


def _spawn_wisp(e: "Explosion", count: int) -> None:
    """Névoa: devagar e subindo. A duração longa que o efeito pede vem de usar
    a vida quase inteira da explosão, não de estourá-la — partícula que vive
    mais que `e.time` sai da faixa que `_get_color` sabe interpolar."""
    for _ in range(max(3, count // 2)):
        a = random.uniform(0, _TAU)
        speed = random.uniform(20, 70) * (e.size / 30)
        rise = -random.uniform(30, 80)
        e.particles.append(
            [
                e.x,
                e.y,
                math.cos(a) * speed,
                math.sin(a) * speed + rise,
                random.uniform(e.time * 0.8, e.time),
            ]
        )


def _spawn_ember(e: "Explosion", count: int) -> None:
    """Brasas jorrando para cima; a gravidade em `_MOTION` faz o arco."""
    for _ in range(max(3, count // 2)):
        a = random.uniform(-math.pi, 0.0)  # meia volta de cima
        speed = random.uniform(120, 300) * (e.size / 30)
        e.particles.append(
            [
                e.x,
                e.y,
                math.cos(a) * speed,
                math.sin(a) * speed,
                random.uniform(e.time * 0.6, e.time),
            ]
        )


def _spawn_shatter(e: "Explosion", count: int) -> None:
    """Estilhaços: rápidos, desiguais, desenhados como quadrados."""
    for _ in range(max(4, count // 2)):
        a = random.uniform(0, _TAU)
        speed = random.uniform(260, 520) * (e.size / 30)
        e.particles.append(
            [
                e.x,
                e.y,
                math.cos(a) * speed,
                math.sin(a) * speed,
                random.uniform(e.time * 0.3, e.time * 0.7),
            ]
        )


_SPAWNERS: Dict[str, Callable[["Explosion", int], None]] = {
    ImpactPattern.BURST: _spawn_burst,
    ImpactPattern.RING: _spawn_ring,
    ImpactPattern.ECHO: _spawn_echo,
    ImpactPattern.STAR: _spawn_star,
    ImpactPattern.SPARK: _spawn_spark,
    ImpactPattern.BOLT: _spawn_bolt,
    ImpactPattern.IMPLODE: _spawn_implode,
    ImpactPattern.WISP: _spawn_wisp,
    ImpactPattern.EMBER: _spawn_ember,
    ImpactPattern.SHATTER: _spawn_shatter,
}


def _draw_dots(e: "Explosion", screen: pygame.Surface) -> None:
    inv = 1.0 / max(e.time, 1e-6)
    # Aumentado o raio base (divisor de 10 para 6) para partículas mais encorpadas
    scale = e.size / 6
    for p in e.particles:
        life_ratio = p[4] * inv
        pygame.draw.circle(
            screen,
            e._get_color(life_ratio),
            (int(p[0]), int(p[1])),
            max(1, scale * life_ratio),
        )


def _draw_streaks(e: "Explosion", screen: pygame.Surface) -> None:
    """Risco no sentido do movimento. O rastro sai do próprio vetor velocidade,
    então a faísca encurta sozinha conforme desacelera."""
    inv = 1.0 / max(e.time, 1e-6)
    for p in e.particles:
        life_ratio = p[4] * inv
        tail = 0.02 * life_ratio
        pygame.draw.line(
            screen,
            e._get_color(life_ratio),
            (int(p[0]), int(p[1])),
            (int(p[0] - p[2] * tail), int(p[1] - p[3] * tail)),
        )


def _draw_bolts(e: "Explosion", screen: pygame.Surface) -> None:
    """Centro → cotovelo → ponta. Dois segmentos bastam para ler como raio."""
    inv = 1.0 / max(e.time, 1e-6)
    cx, cy = int(e.x), int(e.y)
    amp = e.size * 0.25
    for i, p in enumerate(e.particles):
        life_ratio = p[4] * inv
        ex, ey = int(p[0]), int(p[1])
        dx, dy = ex - cx, ey - cy
        norm = math.hypot(dx, dy) or 1.0
        # Cotovelo na perpendicular, alternando de lado para os raios vizinhos
        # não dobrarem todos no mesmo sentido (o que viraria um redemoinho).
        side = amp if i % 2 == 0 else -amp
        kx = (cx + ex) * 0.5 - dy / norm * side
        ky = (cy + ey) * 0.5 + dx / norm * side
        pygame.draw.lines(
            screen,
            e._get_color(life_ratio),
            False,
            [(cx, cy), (int(kx), int(ky)), (ex, ey)],
        )


def _draw_shards(e: "Explosion", screen: pygame.Surface) -> None:
    inv = 1.0 / max(e.time, 1e-6)
    for p in e.particles:
        life_ratio = p[4] * inv
        side = max(1, int(e.size * 0.18 * life_ratio))
        pygame.draw.rect(
            screen, e._get_color(life_ratio), (int(p[0]), int(p[1]), side, side)
        )


_DRAWERS: Dict[str, Callable[["Explosion", pygame.Surface], None]] = {
    ImpactPattern.SPARK: _draw_streaks,
    ImpactPattern.EMBER: _draw_streaks,
    ImpactPattern.BOLT: _draw_bolts,
    ImpactPattern.SHATTER: _draw_shards,
}


class Explosion:
    def __init__(
        self,
        x: float,
        y: float,
        size: int = 20,
        explosion_type: Sequence[tuple[int, int, int]] | None = None,
        pattern: str = ImpactPattern.BURST,
    ):
        """
        Cria uma explosão de partículas.

        Args:
            x, y: Posição central da explosão
            size: Tamanho da explosão (afeta duração e número de partículas)
            explosion_type: Paleta de cores (ExplosionType.ALIEN, ExplosionType.SLIME, etc)
                          Se None, usa explosão padrão laranja/vermelho
            pattern: Forma do efeito (ImpactPattern.*). Só estético.
        """
        self.x, self.y = x, y
        self.size = size
        self.explosion_type = explosion_type
        self.pattern = pattern
        self.time = Config.EXPLOSION_DURATION * (size / 40)

        # Inicializar partículas
        self.particles: list[list[float]] = []
        self._create_particles()

    def _create_particles(self):
        """Cria partículas da explosão (método separado para reuso no pool)."""
        from ..core.visual_quality import visual_quality

        # Aumentado o limite para 100 para explosões mais dramáticas. A contagem
        # escala pela Qualidade Visual (nunca zera: piso de 1 partícula).
        count = visual_quality.particles(min(30 + self.size // 2, 100))
        self.particles.clear()
        _SPAWNERS.get(self.pattern, _spawn_burst)(self, count)

    def reset(
        self,
        x: float,
        y: float,
        size: int = 20,
        explosion_type: Sequence[tuple[int, int, int]] | None = None,
        pattern: str = ImpactPattern.BURST,
    ):
        """Reconfigura explosão para reuso (usado pelo pool)."""
        self.x = x
        self.y = y
        self.size = size
        self.explosion_type = explosion_type
        self.pattern = pattern
        self.time = Config.EXPLOSION_DURATION * (size / 40)
        self._create_particles()

    def update(self, dt: float):
        self.time = max(0.0, self.time - dt)
        motion = _MOTION.get(self.pattern, _BURST_MOTION)
        drag = motion.drag
        gravity = motion.gravity * dt
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= drag
            p[3] = p[3] * drag + gravity
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

    def finished(self) -> bool:
        return self.time <= 0 and not self.particles

    def _get_color(self, life_ratio: float) -> tuple[int, int, int]:
        """Calcula cor da partícula baseada no tipo de explosão e vida restante."""
        # `life_ratio` divide pela duração restante, que também decai — se uma
        # partícula sobreviver ao `self.time` da explosão, a razão dispara e o
        # índice sai da paleta. Os spawners mantêm vida <= time, mas o clamp
        # fica como rede: indexar paleta não pode depender dessa invariante.
        life_ratio = 0.0 if life_ratio < 0.0 else (1.0 if life_ratio > 1.0 else life_ratio)
        if self.explosion_type:
            # Interpolar entre cores da paleta
            color_index = int(life_ratio * (len(self.explosion_type) - 1))
            next_index = min(color_index + 1, len(self.explosion_type) - 1)
            t = (life_ratio * (len(self.explosion_type) - 1)) - color_index

            r = int(
                self.explosion_type[color_index][0]
                + t
                * (
                    self.explosion_type[next_index][0]
                    - self.explosion_type[color_index][0]
                )
            )
            g = int(
                self.explosion_type[color_index][1]
                + t
                * (
                    self.explosion_type[next_index][1]
                    - self.explosion_type[color_index][1]
                )
            )
            b = int(
                self.explosion_type[color_index][2]
                + t
                * (
                    self.explosion_type[next_index][2]
                    - self.explosion_type[color_index][2]
                )
            )
            return (r, g, b)
        else:
            # Explosão padrão: amarelo/laranja -> vermelho
            if life_ratio > 0.5:
                r = 255
                g = int(255 * ((life_ratio - 0.5) * 2))
            else:
                r = int(255 * (life_ratio * 2))
                g = 0
            return (r, g, 0)

    def draw(self, screen: pygame.Surface):
        if self.finished():
            return
        _DRAWERS.get(self.pattern, _draw_dots)(self, screen)
