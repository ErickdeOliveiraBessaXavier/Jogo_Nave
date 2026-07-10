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

Contratos (convenções do projeto): implementa o contrato de inimigo com on_hit/take_damage
próprios (perigo indestrutível — sem mixin), update via update_in_context (§5),
draw sem efeitos colaterais (§3).
"""

import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Final, List, Any

import pygame

from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class _DustVortexState(Enum):
    MOVING = auto()
    GUSTING = auto()
    DISSIPATING = auto()


class _VortexParticle:
    """Partícula individual de poeira ou detrito dentro do vórtice."""

    __slots__ = ("x", "y", "vx", "vy", "orbit_radius", "angle", "angular_speed", "life", "max_life", "size", "color", "is_fragment", "img_idx", "bright")

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

        # Tiers visuais de cor (§3: só afeta cor/render, não hitbox nem
        # comportamento). A massa é poeira (areia/cinza escuros); uma fração é
        # areia clara; poucas são "fios" de branco puro — highlights que dão
        # volume e profundidade em vez de tudo no mesmo tom. `bright` marca o
        # highlight p/ o draw reforçá-lo (inclusive na rajada), mantendo a coluna
        # legível quando a densidade de partículas sobe.
        roll = random.random()
        if roll < 0.09:
            self.color = (255, 255, 250)  # fio de vento — branco puro (highlight)
            self.bright = True
        elif roll < 0.34:
            self.color = random.choice([  # areia clara / cinza claro
                (214, 208, 198), (228, 222, 212), (196, 190, 182),
            ])
            self.bright = False
        else:
            self.color = random.choice([  # poeira/terra — a massa (mais escura)
                (158, 140, 112), (138, 120, 94), (172, 154, 128), (120, 104, 84),
            ])
            self.bright = False
        self.is_fragment = is_fragment
        self.img_idx = img_idx

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


class _WindStreak:
    """Risco branco de vento — partícula independente com vida própria.

    Diferente dos arcos do telegrama (que colapsam com o fim do ataque), o risco
    é EMITIDO durante a rajada mas depois vive por conta própria: preserva sua
    velocidade/direção e segue subindo até sair da tela OU esgotar a vida. Isso dá
    a dissipação natural do fluxo (sem sumiço abrupto nem congelamento). Puramente
    visual — não participa de dano nem colisão.
    """

    __slots__ = ("x", "y", "vx", "vy", "length", "width", "life", "max_life")

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        length: int,
        width: int,
        life: float,
    ):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.length = length
        self.width = width
        self.max_life = life
        self.life = life

    def update(self, dt: float) -> bool:
        """Integra o movimento e envelhece. Retorna False p/ remoção quando a vida
        acaba OU quando o risco sai por completo pelo topo da tela (`y` é o ponto
        inferior; o risco vai de ``y-length`` a ``y``, então some quando ``y < 0``)."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0.0 and self.y > 0.0


class CuttingStorm:
    """Vórtice de Poeira — Implementação renovada da CuttingStorm.

    Nota: Este inimigo é um perigo ambiental indestrutível.
    Não recebe dano e não bloqueia tiros.
    """

    # Dimensões e Combate (RADIUS usado pelo Spawner)
    RADIUS: Final = 64
    DAMAGE_RADIUS: Final = 58.0
    GUST_RADIUS: Final = 48.0
    # Altura da coluna da rajada — compartilhada pelo dano (blasts) e pelo
    # pilar visual, para que o hitbox nunca exceda o telegrama desenhado.
    PILLAR_MAX_HEIGHT: Final = 580.0

    # Dano a outros inimigos pego pela coluna/base (ver _apply_damage_to_enemies).
    # Calibrado para detonar minas/Geodos (HP 50) quando a coluna fica sob eles
    # durante a rajada: ~1 hit a cada ENEMY_HIT_COOLDOWN, então ~5 hits (~0.75s)
    # zeram 50 HP. Inimigos leves (mage/glider, HP 20–30) são varridos; tanques
    # (sentry 80, robot 200) sobrevivem a uma passagem. Ajuste aqui para mudar o
    # quanto o vento "limpa" a tela.
    ENEMY_DAMAGE: Final = 10
    ENEMY_HIT_COOLDOWN: Final = 0.15

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
    # Cache de surfaces de pixel (size, cor) reusadas no draw — evita alocar
    # uma Surface por partícula por frame (§7). Alpha varia via set_alpha.
    _pixel_cache: dict[tuple[int, tuple[int, int, int]], pygame.Surface] = {}
    # Cache de barras brancas de risco (largura, comprimento) — reutilizadas por
    # todos os _WindStreak; alpha por set_alpha no draw (§7).
    _streak_cache: dict[tuple[int, int], pygame.Surface] = {}

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
        self.ground_y = screen_h - 5.0

        self.x = float(x if x is not None else screen_w + 120)
        # `y` recebido do spawner é ignorado de propósito: o vórtice é colado ao
        # chão, então o centro da base fica sempre rente ao ground_y.
        self.y = self.ground_y - self.RADIUS

        # Guardado por simetria com os outros inimigos (spawner passa por kwarg);
        # o vórtice se move só na horizontal, então não altera comportamento.
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
        # Riscos de vento: partículas independentes (vida própria). Emitidos só
        # durante a rajada, mas persistem após o fim da emissão até sair da
        # tela/expirar — dissipação natural, sem sumiço abrupto.
        self._wind_streaks: List[_WindStreak] = []
        self._streak_emit_accum = 0.0
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
            self._apply_damage_to_enemies(blasts, ctx.other_enemies, ctx.sdt)

    def _apply_damage_to_enemies(self, blasts: list[tuple[float, float, float]], others: list[Any], sdt: float):
        # Dano ambiental: o vórtice fere outros inimigos por contato direto
        # (`take_damage`), NÃO pelo roteador `apply_hit`/`HitResult` (§8). É
        # deliberado — como hazard, não concede pontos, explosão de morte nem
        # som de hit a quem ele varre; só empurra o dano cru. `sdt` mantém o
        # cooldown coerente com slow-motion/EMP, como o resto do update.
        for eid in list(self._enemy_hit_cooldown.keys()):
            self._enemy_hit_cooldown[eid] -= sdt
            if self._enemy_hit_cooldown[eid] <= 0:
                del self._enemy_hit_cooldown[eid]

        for bx, by, br in blasts:
            for en in others:
                if en is self or getattr(en, "dead", False):
                    continue

                eid = id(en)
                if eid in self._enemy_hit_cooldown:
                    continue

                if not (hasattr(en, "collision_circle") and hasattr(en, "take_damage")):
                    continue

                ecx, ecy, er = en.collision_circle()
                dist_sq = (bx - ecx) ** 2 + (by - ecy) ** 2
                if dist_sq < (br + er) ** 2:
                    en.take_damage(self.ENEMY_DAMAGE)
                    self._enemy_hit_cooldown[eid] = self.ENEMY_HIT_COOLDOWN

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
                # Coluna contígua: passo < 2*raio garante sobreposição entre
                # blasts (sem buracos). Topo limitado a PILLAR_MAX_HEIGHT, a
                # mesma altura do pilar visual — o hitbox não passa do telegrama.
                column_h = self.PILLAR_MAX_HEIGHT * growth
                step = self.GUST_RADIUS * 1.5
                h_off = step
                while h_off <= column_h:
                    blasts.append((cx, cy - h_off, self.GUST_RADIUS))
                    h_off += step
                # Tampa o topo exato da coluna para cobrir a sobra < step.
                if column_h > 0.0:
                    blasts.append((cx, cy - column_h, self.GUST_RADIUS))
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

        # Riscos de vento: emite SÓ na rajada (fim da emissão = fim do gust), mas
        # atualiza SEMPRE — os já existentes seguem subindo e se dissipando
        # naturalmente mesmo depois, até saírem da tela ou expirarem (§6).
        if self._state == _DustVortexState.GUSTING:
            self._emit_wind_streaks(dt)
        i = 0
        while i < len(self._wind_streaks):
            if not self._wind_streaks[i].update(dt):
                self._wind_streaks[i] = self._wind_streaks[-1]
                self._wind_streaks.pop()
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

    def _emit_wind_streaks(self, dt: float):
        """Emite riscos brancos ao longo da coluna ativa da rajada. Cada um nasce
        com velocidade ascendente própria — mantida após o fim da emissão, o que
        cria a dissipação contínua do fluxo. Acumulador fracionário garante taxa
        estável independente do `dt`."""
        cx, cy = self._center
        progress = 1.0 - (self._state_timer / self.GUST_DURATION)
        max_h = self.PILLAR_MAX_HEIGHT * progress
        self._streak_emit_accum += 14.0 * dt  # ~14 riscos/segundo na rajada
        n = int(self._streak_emit_accum)
        self._streak_emit_accum -= n
        for _ in range(n):
            h = random.uniform(0.0, max_h)  # posição ao longo da coluna
            f = h / self.PILLAR_MAX_HEIGHT
            r_col = self.RADIUS * (0.7 + f * 1.3)
            self._wind_streaks.append(_WindStreak(
                x=cx + random.uniform(-0.5, 0.5) * r_col,
                y=cy - h,
                vx=random.uniform(-25.0, 25.0),
                vy=-random.uniform(320.0, 560.0),  # sobe (direção do vento)
                length=random.randint(14, 26),
                width=1,
                life=random.uniform(0.7, 1.5),
            ))

    @classmethod
    def _pixel_surf(cls, size: int, color: tuple[int, int, int]) -> pygame.Surface:
        """Surface de pixel reutilizável por (tamanho, cor). Alpha vem por
        `set_alpha` no draw, então a mesma surface serve a qualquer partícula."""
        key = (size, color)
        surf = cls._pixel_cache.get(key)
        if surf is None:
            surf = pygame.Surface((size, size))
            surf.fill(color)
            cls._pixel_cache[key] = surf
        return surf

    @classmethod
    def _streak_surf(cls, width: int, length: int) -> pygame.Surface:
        """Barra branca vertical reutilizável por (largura, comprimento). Alpha
        vem por `set_alpha` no draw — a mesma surface serve a qualquer risco."""
        key = (width, length)
        surf = cls._streak_cache.get(key)
        if surf is None:
            surf = pygame.Surface((width, length))
            surf.fill((255, 255, 250))
            cls._streak_cache[key] = surf
        return surf

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        self._draw_telegraph_body(surface, cx, cy)
        gusting = self._state == _DustVortexState.GUSTING
        for p in self._particles:
            life_frac = p.life / p.max_life
            if not p.is_fragment:
                if p.bright:
                    # Highlight: permanece mais opaco (destaque) e ainda mais forte
                    # na rajada, para a coluna continuar legível com muita poeira.
                    alpha = int(255 * (0.45 + 0.55 * life_frac))
                    if gusting:
                        alpha = min(255, int(alpha * 1.3))
                else:
                    alpha = int(255 * life_frac)
                p_surf = self._pixel_surf(p.size, p.color)
                p_surf.set_alpha(alpha)
                surface.blit(p_surf, (int(p.x), int(p.y)))
            else:
                if self._fragment_sprites:
                    img = self._fragment_sprites[p.img_idx]
                    rot = pygame.transform.rotate(img, self._anim_time * 240.0 + p.angle * 40)
                    if p.size != 16:
                        rot = pygame.transform.scale(rot, (p.size, p.size))
                    rot.set_alpha(int(255 * life_frac))
                    surface.blit(rot, rot.get_rect(center=(int(p.x), int(p.y))).topleft)

        # Riscos de vento (highlights brancos) por cima da poeira. O alpha esvai
        # com a vida → dissipação suave e contínua (draw só lê estado, §3).
        for s in self._wind_streaks:
            alpha = int(235 * (s.life / s.max_life))
            if alpha <= 0:
                continue
            streak_surf = self._streak_surf(s.width, s.length)
            streak_surf.set_alpha(alpha)
            surface.blit(streak_surf, (int(s.x), int(s.y - s.length)))

    def _draw_telegraph_body(self, surface: pygame.Surface, cx: float, cy: float):
        """Desenha o corpo principal e o pilar usando o estilo de espiral de alta intensidade."""
        is_gusting = self._state == _DustVortexState.GUSTING
        is_dissipating = self._state == _DustVortexState.DISSIPATING
        dissipation_fade = (
            (self._state_timer / self.DISSIPATION_DURATION) if is_dissipating else 1.0
        )

        # Tiers de cor do vento (§3: só visual). Contraste entre camadas por papel:
        #   DUST  = poeira/areia — a massa, mais escura e de alpha baixo
        #   WIND  = espiral de vento clara — separa visualmente as camadas
        #   HIGHLIGHT = fio de vento branco puro — destaque que dá volume
        DUST_COLORS = [
            (150, 134, 110),  # terra seca
            (168, 150, 126),  # poeira média
            (134, 120, 100),  # sombra de poeira
        ]
        WIND_COLORS = [
            (210, 202, 190),  # areia clara
            (228, 222, 212),  # areia muito clara
            (196, 188, 178),  # cinza areia
        ]
        HIGHLIGHT_COLOR = (255, 255, 250)

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
                # Papel visual do arco: o 1º de cada camada é espiral clara (e,
                # intermitentemente, um fio branco); os demais são poeira (massa).
                # `depth` deixa a base/centro mais brilhante que o topo — variação
                # sutil de luminosidade (§3: mexe só em cor/alpha, não na geometria).
                depth = 1.0 - frac * 0.3
                if i == 0:
                    if (layer + int(self._anim_time * 3.0)) % 4 == 0:
                        current_color = HIGHLIGHT_COLOR
                        base_alpha = 96
                    else:
                        current_color = WIND_COLORS[layer % len(WIND_COLORS)]
                        base_alpha = 70
                else:
                    current_color = DUST_COLORS[(layer + i) % len(DUST_COLORS)]
                    base_alpha = 42 + (layer % 3) * 8
                alpha = int(base_alpha * depth * dissipation_fade)

                if alpha > 0:
                    arc_surf = pygame.Surface((w, h), pygame.SRCALPHA)
                    arc_len = 1.0 + (i % 2) * 0.5
                    pygame.draw.arc(arc_surf, (*current_color, alpha), arc_surf.get_rect(), angle, angle + arc_len, 2)
                    surface.blit(arc_surf, rect.topleft)

        if is_gusting or is_dissipating:
            progress = 1.0 if is_dissipating else (1.0 - (self._state_timer / self.GUST_DURATION))
            max_h = self.PILLAR_MAX_HEIGHT * progress
            # Densidade CONSTANTE: o nº de camadas acompanha a altura atual da
            # coluna, então o espaçamento vertical NÃO aumenta conforme ela cresce.
            # Antes eram 22 camadas fixas espalhadas por uma altura variável (com
            # culling por `progress`) → arcos e fios ficavam cada vez mais esparsos
            # no auge da rajada. Agora `f` varia 0..1 sobre a coluna real e não há
            # culling: as camadas já existem apenas até `max_h`, cobrindo bem o
            # telegrama (o hitbox, calculado em update(), continua ≤ este visual).
            PILLAR_LAYER_SPACING = 16.0  # px entre camadas — mantém a coluna contígua
            num_pillar_layers = max(2, int(max_h / PILLAR_LAYER_SPACING) + 1)
            for i in range(num_pillar_layers):
                f = i / (num_pillar_layers - 1)
                t_col = self._anim_time * 15.0 + i * 0.4
                y_pos = cy - f * max_h
                r_col = self.RADIUS * (0.7 + f * 1.3)
                w_col = max(1, int(r_col * 2.1))
                h_col = max(1, int(r_col * 0.7))
                x_osc = math.sin(t_col * 0.8) * 30.0 * f
                rect_col = pygame.Rect(0, 0, w_col, h_col)
                rect_col.center = (int(cx + x_osc), int(y_pos))

                alpha_col = int(78 * (1.0 - f * 0.6) * dissipation_fade)
                if alpha_col > 0:
                    # Alterna espiral clara / poeira ao longo da coluna para o olho
                    # separar as camadas em vez de ler um bloco uniforme.
                    if i % 3 == 0:
                        pillar_color = WIND_COLORS[i % len(WIND_COLORS)]
                    else:
                        pillar_color = DUST_COLORS[i % len(DUST_COLORS)]
                    arc_surf = pygame.Surface((w_col, h_col), pygame.SRCALPHA)
                    pygame.draw.arc(arc_surf, (*pillar_color, alpha_col), arc_surf.get_rect(), t_col % math.tau, (t_col % math.tau) + 1.5, 2)
                    surface.blit(arc_surf, rect_col.topleft)
                    # Os "fios" brancos de vento agora são partículas independentes
                    # (_WindStreak, emitidas em _emit_wind_streaks e desenhadas em
                    # draw()) — assim persistem e se dissipam após o fim da rajada,
                    # em vez de sumir junto com o telegrama.

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
