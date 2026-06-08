"""IceGolem — Tank Ofensivo do bioma MOUNTAINS.

Reformulação: o golem deixa de ser um tank passivo e vira um sistema único em
que **defesa, ataque e ponto fraco são a mesma coisa**, girando em torno de uma
gema central.

Arquitetura (entidades-irmãs, não partes internas)
---------------------------------------------------
- `IceGolem` **é a gema central** — o núcleo flutuante e o verdadeiro ponto
  fraco. É a entidade que o spawner cria.
- `IceGolemFragment` — 4 rochas que orbitam a gema. Cada uma é uma entidade
  irmã na lista de inimigos (criadas pela gema no 1º update via
  `ctx.new_enemies`). Assim cada rocha é atingível por bala e colide com a nave
  por conta própria, pelo caminho de colisão padrão — sem máscara composta por
  frame (§7). A gema **coordena** as rochas escrevendo posições-alvo públicas
  (`home_x/home_y/orbit_angle`) e chamando `start_boomerang` — nunca lê estado
  privado delas (§1).

Defesa = janelas, não muralha
-----------------------------
A gema é sempre atingível, mas aplica **redução de dano por exposição** no
`on_hit`: com as 4 rochas em formação fechada o tiro quase ricocheteia (~10%);
a vulnerabilidade sobe conforme rochas morrem, conforme rochas saem da órbita
no bumerangue, e ao máximo na fase de expansão. A estratégia ideal é achar a
janela da gema exposta — destruir todas as pedras é um caminho alternativo
(mais caos na tela), não o único.

Fragmentação
------------
Ao morrer, cada rocha **não some**: retorna `HitResult(fragments=...)` com
2-3 mini-meteoros de gelo arremessados (canal `absorb_fragments`/pool já
existente). Vira ameaça secundária — a decisão é "abro a gema mas crio caos?".

Fases (FSM na gema)
-------------------
1. ``FORMATION_CLOSED`` — órbita próxima, giro lento. Gema protegida.
2. ``BOOMERANG_ATTACK`` — cada rocha, **uma por vez** (escalonada), abandona a
   órbita, avança até o jogador e retorna ao ponto orbital (satélite/bumerangue).
   Pressão constante e alternada.
3. ``EXPANSION`` — giro acelera e a órbita abre e fecha; a gema fica exposta
   (janela de vulnerabilidade) enquanto as rochas controlam mais área.

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3); reação de dano via
`HitResult` (§8); fragmentação pelo canal de `fragments`/pool (§7).
"""

import math
import random
from enum import Enum
from typing import TYPE_CHECKING, List

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader
from .enemy_hit_mixin import EnemyHitMixin
from .explosion import ExplosionType

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


SPRITE_DIR = "Ice_Golem_Cristal"


def _load_ice_golem_sprites() -> None:
    """Pré-carrega (uma vez) os sprites da gema, das rochas e dos estilhaços."""
    IceGolem.load_sprites()
    IceGolemFragment.load_sprites()
    IceShard.load_sprites()


class IceGolemPhase(Enum):
    """Estados de fase do IceGolem."""

    FORMATION_CLOSED = "closed"  # Formação defensiva, gema protegida
    BOOMERANG_ATTACK = "boomerang"  # Rochas atacam uma a uma e retornam
    EXPANSION = "expansion"  # Órbita abre, gema exposta


def _scale(surf: pygame.Surface, target: int) -> pygame.Surface:
    """Escala mantendo proporção para que o maior lado seja `target`."""
    w, h = surf.get_size()
    f = target / max(w, h)
    return pygame.transform.smoothscale(surf, (round(w * f), round(h * f)))


# Extensões de imagem aceitas ao varrer a pasta de fragmentos (content-driven).
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"})


class _IceDustParticle:
    """Grão de poeira mineral que se desprende de uma rocha orbital.

    Detalhe cosmético discreto: reforça a sensação de massa e desgaste das
    rochas energizadas. Segue o mesmo padrão do `_SerpentDustParticle`
    (MountainSerpentBoss) para consistência visual do tema Montanha. `update`
    move/decai; `draw` apenas desenha (§3).
    """

    __slots__ = ("x", "y", "vx", "vy", "size", "life", "max_life")

    _VX_RANGE = (-14.0, 14.0)  # px/s
    _VY_RANGE = (16.0, 44.0)  # px/s (positivo = cai)
    _GRAVITY = 70.0  # px/s²
    _LIFE_RANGE = (0.4, 0.85)  # segundos
    _SIZE_RANGE = (1, 3)  # pixels
    _BASE_COLOR = (168, 192, 214)  # poeira mineral fria (azul-acinzentada)

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(*self._VX_RANGE)
        self.vy = random.uniform(*self._VY_RANGE)
        self.size = random.randint(*self._SIZE_RANGE)
        self.max_life = random.uniform(*self._LIFE_RANGE)
        self.life = self.max_life

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self._GRAVITY * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0.0:
            return
        fade = max(0.0, self.life / self.max_life)
        r, g, b = self._BASE_COLOR
        pygame.draw.rect(
            surface,
            (int(r * fade), int(g * fade), int(b * fade)),
            (int(self.x), int(self.y), self.size, self.size),
        )


class _GemEnergyMote:
    """Faísca de energia azul puxada para a gema durante a montagem da formação.

    Sugere o núcleo "atraindo" os fragmentos ao seu redor: nasce a alguma
    distância e converge para o centro, esmaecendo. Detalhe puramente cosmético
    do nascimento/reconstrução — `update` move/decai, `draw` só desenha (§3).
    """

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color")

    _SPEED = (60.0, 120.0)  # px/s rumo ao centro
    _LIFE = (0.35, 0.7)  # segundos
    _COLORS = ((120, 220, 255), (180, 240, 255), (90, 180, 255))  # azul/ciano gelo

    def __init__(self, cx: float, cy: float, angle: float, radius: float) -> None:
        self.x = cx + math.cos(angle) * radius
        self.y = cy + math.sin(angle) * radius
        speed = random.uniform(*self._SPEED)
        # Velocidade apontando para o centro da gema (atração).
        self.vx = -math.cos(angle) * speed
        self.vy = -math.sin(angle) * speed
        self.max_life = random.uniform(*self._LIFE)
        self.life = self.max_life
        self.size = random.randint(2, 3)
        self.color = random.choice(self._COLORS)

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0.0:
            return
        fade = max(0.0, self.life / self.max_life)
        r, g, b = self.color
        pygame.draw.circle(
            surface,
            (int(r * fade), int(g * fade), int(b * fade)),
            (int(self.x), int(self.y)),
            self.size,
        )


class IceShard(EnemyHitMixin):
    """Estilhaço físico de uma rocha destruída — entidade independente.

    Totalmente orientado por conteúdo: TODOS os sprites presentes em
    ``assets/images/Ice_Golem_Cristal/Fragmentos`` são carregados
    automaticamente (ordem alfabética) e ficam disponíveis para sorteio. Basta
    adicionar/remover arquivos na pasta para mudar os fragmentos — nenhum nome
    de arquivo é hardcoded além da pasta raiz.

    Cada estilhaço sorteia um sprite e um tamanho pequeno (`MIN_SIZE`..`MAX_SIZE`),
    herda a direção geral da explosão com pequenas variações de ângulo/velocidade
    e ganha rotação própria — transmitindo uma quebra natural.
    """

    FRAGMENTS_SUBDIR = "Fragmentos"  # único caminho referenciado, sob SPRITE_DIR
    MIN_SIZE = 12
    MAX_SIZE = 18
    GRAVITY = 220.0  # px/s²: estilhaços caem como detritos (top-down)

    _raw_sprites: List[pygame.Surface] = []

    @classmethod
    def load_sprites(cls) -> None:
        """Varre a pasta de fragmentos e carrega tudo que for imagem."""
        if cls._raw_sprites:
            return
        folder = BASE_DIR / "assets" / "images" / SPRITE_DIR / cls.FRAGMENTS_SUBDIR
        if not folder.is_dir():
            return
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in _IMAGE_EXTS:
                cls._raw_sprites.append(get_image(path))

    @classmethod
    def has_sprites(cls) -> bool:
        return bool(cls._raw_sprites)

    def __init__(self, cx: float, cy: float, vx: float, vy: float):
        if not self._raw_sprites:
            self.load_sprites()

        size = random.randint(self.MIN_SIZE, self.MAX_SIZE)
        self.w = size
        self.h = size
        self.x = cx - size / 2
        self.y = cy - size / 2
        self.vx = vx
        self.vy = vy

        self.angle = random.uniform(0.0, 360.0)
        self.spin = random.uniform(-360.0, 360.0)  # graus/s

        self.dead = False
        self.health = 1
        self.active = True

        # Sprite-base escalado ao tamanho sorteado (rotacionado no draw).
        if self._raw_sprites:
            self._base = _scale(random.choice(self._raw_sprites), size)
        else:
            self._base = None

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.5

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        self.vy += self.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle = (self.angle + self.spin * dt) % 360.0

        # Remove ao sair da tela (com margem) — não acumula no hot path.
        margin = self.w + 48
        if (
            self.y > Config.SCREEN_HEIGHT + margin
            or self.y < -margin
            or self.x < -margin
            or self.x > Config.SCREEN_WIDTH + margin
        ):
            self.dead = True

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 10

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=10,
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=4, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, explosion_size=8, sound=hit_sounds.EXPLOSION_ASTEROID)

    def should_remove(self) -> bool:
        return self.dead

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
        if self._base is not None:
            img = pygame.transform.rotate(self._base, self.angle)
            surface.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            pygame.draw.rect(
                surface, (170, 215, 245), (int(self.x), int(self.y), self.w, self.h),
                border_radius=2,
            )


class IceGolemFragment(EnemyHitMixin):
    """Uma rocha orbital: armadura, arma (bumerangue) e fonte de fragmentos.

    É uma entidade-irmã na lista de inimigos. A gema escreve sua posição-alvo
    de órbita (`home_x/home_y/orbit_angle`) a cada frame e dispara o ataque via
    `start_boomerang`. A rocha só é dona da própria cinemática de dash, HP e
    desenho — toda a geometria da formação vive na gema.
    """

    FRAG_SIZE = 46
    BASE_HEALTH = 55

    # As rochas são parte estrutural do golem: a gema as controla pelo ciclo de
    # vida inteiro (inclusive trazendo-as de volta de fora da tela na expansão e
    # na reconstrução). Logo NÃO podem ser ceifadas pela regra genérica de
    # "inimigo fora da tela" do EntityManager. Gate por class attribute (§5),
    # consultado via getattr — sem isinstance novo no manager.
    offscreen_cull_exempt = True

    # Velocidade de convergência ao entrar na arena (reconstrução da armadura).
    ENTER_SPEED = 230.0  # px/s

    # Bumerangue — propositalmente lento para priorizar leitura e tempo de
    # reação: o jogador deve ler a trajetória, decidir e esquivar.
    BOOM_DURATION = 1.7  # tempo total do dash (ida + volta)
    BOOM_ADVANCE_FRAC = 0.5  # fração do tempo gasta avançando
    # Alcance máximo: cobre praticamente toda a tela para que o fragmento chegue
    # de fato à posição do jogador (cap só para o caso degenerado fora da tela).
    BOOM_DASH_DISTANCE = 760.0

    # Rotação própria contínua (rocha energizada/instável, não sprite girando em
    # círculo). Cada rocha sorteia sentido/velocidade próprios.
    SELF_SPIN_RANGE = (-150.0, 150.0)  # graus/s

    # Rastro fantasmagórico (estilo Alucard) durante o dash — mesma técnica do
    # SerpentRockBullet: imagens residuais com alpha decrescente.
    _TRAIL_INTERVAL = 0.045  # s entre fantasmas
    _TRAIL_LIFETIME = 0.28  # s de vida de cada fantasma
    _TRAIL_MAX_ALPHA = 120  # alpha inicial do fantasma

    # Poeira mineral desprendendo enquanto orbita.
    _PARTICLE_INTERVAL = (0.10, 0.22)  # s entre grãos

    # Mapeia o slot ao arquivo do canto correspondente (a arte é desenhada para
    # cantos de um quadrado; cada slot recebe a peça que aponta para fora).
    _CORNER_FILES = {
        "tl": "Canto_Superior_Esquerdo.png",
        "tr": "Canto_Superior_Direito.png",
        "br": "Canto_Inferior_Direito.png",
        "bl": "Canto_Inferior_Esquerdo.png",
    }
    _sprites: dict[str, pygame.Surface] = {}

    @classmethod
    def load_sprites(cls) -> None:
        if cls._sprites:
            return
        for key, fname in cls._CORNER_FILES.items():
            path = BASE_DIR / "assets" / "images" / SPRITE_DIR / fname
            if path.exists():
                cls._sprites[key] = _scale(get_image(path), cls.FRAG_SIZE)

    def __init__(self, corner: str, base_angle: float, entering: bool = False):
        """corner: chave em `_CORNER_FILES`. base_angle: ângulo do slot (rad).

        entering: se True, a rocha nasce fora da tela e converge para a órbita
        (usado na reconstrução da armadura), em vez de já colar na posição.
        """
        if not self._sprites:
            self.load_sprites()
        self.corner = corner
        self.base_angle = base_angle

        self.w = self.FRAG_SIZE
        self.h = self.FRAG_SIZE
        # Posição inicial = origem; a gema reescreve já no 1º update dela.
        self.x = 0.0
        self.y = 0.0

        self.health = self.BASE_HEALTH
        self.dead = False
        self.hit_timer = 0.0

        # Reconstrução: rocha vindo de fora, ainda convergindo para a formação.
        self.entering = entering

        # Alvo de órbita escrito pela gema (canto superior-esquerdo da rocha).
        self.home_x = 0.0
        self.home_y = 0.0
        self.orbit_angle = base_angle  # para girar a arte com a formação

        # Estado de ataque bumerangue.
        self.attacking = False
        self._boom_t = 0.0
        self._launch_cx = 0.0  # centro no instante do disparo
        self._launch_cy = 0.0
        self._target_cx = 0.0  # ponto de avanço (em direção ao jogador)
        self._target_cy = 0.0

        # Rotação própria contínua sobre o eixo (independente da órbita).
        self.self_angle = random.uniform(0.0, 360.0)
        self.self_spin = random.uniform(*self.SELF_SPIN_RANGE)  # graus/s

        # Rastro fantasmagórico (só durante o dash) e poeira mineral (sempre).
        self._afterimages: List[dict] = []
        self._trail_timer = 0.0
        self._particles: List[_IceDustParticle] = []
        self._particle_timer = random.uniform(*self._PARTICLE_INTERVAL)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def collision_circle(self) -> tuple[float, float, float]:
        cx, cy = self.center
        return cx, cy, self.w * 0.45

    def start_boomerang(self, player_x: float, player_y: float) -> None:
        """Inicia o dash em direção ao jogador (chamado pela gema)."""
        if self.attacking or self.dead or self.entering:
            return
        cx, cy = self.center
        self._launch_cx, self._launch_cy = cx, cy
        dx, dy = player_x - cx, player_y - cy
        dist = math.hypot(dx, dy) or 1.0
        reach = min(self.BOOM_DASH_DISTANCE, dist)
        self._target_cx = cx + dx / dist * reach
        self._target_cy = cy + dy / dist * reach
        self._boom_t = 0.0
        self.attacking = True

    # update_in_context exigido pelo dispatcher polimórfico do EntityManager (§5).
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Giro próprio contínuo e detalhes cosméticos (poeira / rastro).
        self.self_angle = (self.self_angle + self.self_spin * dt) % 360.0
        self._update_particles(dt)
        self._update_trail(dt)

        if self.attacking:
            self._update_boomerang(dt)
        elif self.entering:
            self._update_entering(dt)
        else:
            # Em órbita: cola na posição-alvo escrita pela gema.
            self.x = self.home_x
            self.y = self.home_y

    def _update_entering(self, dt: float) -> None:
        """Converge de fora da tela até a posição orbital viva (que a gema move).

        Avança a passo constante em direção a `home_x/home_y`; ao alcançar,
        assume a órbita (`entering = False`) e passa a colar na formação.
        """
        dx = self.home_x - self.x
        dy = self.home_y - self.y
        dist = math.hypot(dx, dy)
        step = self.ENTER_SPEED * dt
        if dist <= step or dist < 1.0:
            self.x, self.y = self.home_x, self.home_y
            self.entering = False
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step

    def _render_angle(self) -> float:
        """Ângulo de desenho (graus): giro da formação + giro próprio.

        pygame.rotate é CCW(+); o avanço de `orbit_angle` (screen-space) é
        visualmente horário, então a parte orbital entra com -graus. O giro
        próprio (`self_angle`) soma por cima para a rocha parecer instável.
        """
        return -math.degrees(self.orbit_angle - self.base_angle) + self.self_angle

    def _update_particles(self, dt: float) -> None:
        """Emite e atualiza grãos de poeira mineral (in-place reversa)."""
        self._particle_timer -= dt
        if self._particle_timer <= 0.0:
            cx, cy = self.center
            self._particles.append(
                _IceDustParticle(
                    cx + random.uniform(-self.w * 0.3, self.w * 0.3),
                    cy + random.uniform(-self.h * 0.3, self.h * 0.3),
                )
            )
            self._particle_timer = random.uniform(*self._PARTICLE_INTERVAL)
        parts = self._particles
        for i in range(len(parts) - 1, -1, -1):
            parts[i].update(dt)
            if parts[i].dead:
                parts.pop(i)

    def _update_trail(self, dt: float) -> None:
        """Decai os fantasmas existentes; emite novos só durante o dash."""
        ai = self._afterimages
        for i in range(len(ai) - 1, -1, -1):
            ai[i]["life"] -= dt
            if ai[i]["life"] <= 0.0:
                ai.pop(i)
        if not self.attacking:
            return
        self._trail_timer -= dt
        if self._trail_timer <= 0.0:
            cx, cy = self.center
            ai.append(
                {"cx": cx, "cy": cy, "rot": self._render_angle(), "life": self._TRAIL_LIFETIME}
            )
            self._trail_timer = self._TRAIL_INTERVAL

    def _update_boomerang(self, dt: float) -> None:
        """Ida em direção ao jogador, volta para a posição orbital (que se move)."""
        self._boom_t = min(1.0, self._boom_t + dt / self.BOOM_DURATION)
        adv = self.BOOM_ADVANCE_FRAC
        # Centro atual da posição orbital viva (a gema continua girando a formação).
        home_cx = self.home_x + self.w / 2
        home_cy = self.home_y + self.h / 2

        if self._boom_t < adv:
            k = self._ease_out(self._boom_t / adv)
            cx = self._launch_cx + (self._target_cx - self._launch_cx) * k
            cy = self._launch_cy + (self._target_cy - self._launch_cy) * k
        else:
            k = self._ease_in((self._boom_t - adv) / (1.0 - adv))
            cx = self._target_cx + (home_cx - self._target_cx) * k
            cy = self._target_cy + (home_cy - self._target_cy) * k

        self.x = cx - self.w / 2
        self.y = cy - self.h / 2

        if self._boom_t >= 1.0:
            self.attacking = False
            self.x, self.y = self.home_x, self.home_y

    @staticmethod
    def _ease_out(t: float) -> float:
        return 1.0 - (1.0 - t) * (1.0 - t)

    @staticmethod
    def _ease_in(t: float) -> float:
        return t * t

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 120

    def make_shards(self) -> tuple:
        """Instancia estilhaços `IceShard` herdando a direção geral da explosão.

        A direção base é o vetor radial para fora do núcleo (`orbit_angle`), com
        pequenas variações de ângulo/velocidade por estilhaço. Sprites e tamanho
        são sorteados pelo próprio `IceShard` (content-driven). Público: a gema
        também chama isto ao morrer para estilhaçar as rochas restantes (parente
        coordenando o composite — §1)."""
        cx, cy = self.center
        count = random.randint(2, 4)
        base = self.orbit_angle  # direção geral: para fora do núcleo
        shards = []
        for _ in range(count):
            ang = base + random.uniform(-0.5, 0.5)
            speed = random.uniform(160.0, 250.0)
            vx = math.cos(ang) * speed
            vy = math.sin(ang) * speed
            shards.append(IceShard(cx, cy, vx, vy))
        return tuple(shards)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=28,
                sound=hit_sounds.EXPLOSION_ASTEROID,
                fragments=self.make_shards(),
            )
        return HitResult(explosion_size=8, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        # Armadura sólida: machuca a nave (o dano à nave é aplicado pelo
        # dispatcher de colisão) mas a rocha **não** é destruída pelo contato.
        from ..systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead

    def draw(self, surface: pygame.Surface) -> None:
        # Poeira mineral desenhada atrás da rocha (detalhe sutil de massa).
        for p in self._particles:
            p.draw(surface)

        sprite = self._sprites.get(self.corner)
        cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
        if sprite is not None:
            # Rastro fantasmagórico (Alucard) durante o dash: imagens residuais
            # com alpha decrescente, mesma técnica do SerpentRockBullet.
            for ai in self._afterimages:
                ghost = pygame.transform.rotate(sprite, ai["rot"])
                ghost.set_alpha(
                    int((ai["life"] / self._TRAIL_LIFETIME) * self._TRAIL_MAX_ALPHA)
                )
                surface.blit(
                    ghost,
                    ghost.get_rect(center=(int(ai["cx"]), int(ai["cy"]))).topleft,
                )

            # A peça de canto mantém a face interna apontada para o núcleo
            # (giro da formação) somada ao giro próprio da rocha.
            img = pygame.transform.rotate(sprite, self._render_angle())
            if self.hit_timer > 0.0:
                img = img.copy()
                img.fill(colors.WHITE, special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            color = (200, 235, 255) if self.hit_timer > 0.0 else (150, 200, 240)
            pygame.draw.rect(
                surface, color, (int(self.x), int(self.y), self.w, self.h),
                border_radius=4,
            )


class IceGolem(EnemyHitMixin):
    """A gema central — núcleo flutuante, ponto fraco e cérebro da formação."""

    # Núcleo estrutural e persistente: nunca ceifado pela regra de "fora da tela"
    # do EntityManager (§5: gate por class attribute, lido via getattr).
    offscreen_cull_exempt = True

    # Tamanho do alvo (a gema). Pequeno de propósito: é o ponto fraco focado.
    GEM_SIZE = 42
    SPRITE_TARGET = 54  # sprite desenhado um pouco maior que o hitbox
    # `W`/`H`: contrato de tamanho lido pelo spawner (`_entry_position`).
    W = GEM_SIZE
    H = GEM_SIZE

    MOVE_SPEED = 46.0
    ENTRY_SPEED = 90.0

    CORE_HEALTH = 220

    # Órbita
    BASE_ORBIT_DISTANCE = 82.0
    EXPANDED_ORBIT_DISTANCE = 188.0
    SPIN_CLOSED = 1.1  # rad/s
    SPIN_EXPANSION = 2.6  # rad/s

    # Fases
    PHASE_CLOSED_DURATION = 3.5
    EXPANSION_DURATION = 4.5
    BOOMERANG_STAGGER = 0.85  # intervalo entre disparos individuais

    # Reconstrução da armadura: se a gema ficar sem nenhuma rocha viva por este
    # tempo, novas rochas surgem de fora (pela base) e convergem para a órbita.
    REBUILD_DELAY = 10.0  # s sem rochas até disparar a reconstrução
    REBUILD_ENTRY_MARGIN = 70.0  # px abaixo do rodapé onde as rochas nascem
    REBUILD_ENTRY_STAGGER = 46.0  # px de escalonamento vertical na entrada

    # Animação da gema
    NUM_GEM_FRAMES = 8
    GEM_ANIM_FPS = 7.0

    # Tremor de impacto: feedback forte quando o jogador acerta o ponto fraco.
    # Curto e perceptível, sem comprometer a leitura do combate.
    GEM_SHAKE_DURATION = 0.18  # s
    GEM_SHAKE_AMPLITUDE = 6.0  # px
    GEM_SHAKE_FREQ = 60.0  # rad/s

    _explosion_size_killed = 90
    _gem_frames: List[pygame.Surface] = []

    @classmethod
    def load_sprites(cls) -> None:
        if cls._gem_frames:
            return
        # A animação é base + _01.._07 (8 frames; o 1º não tem sufixo numérico).
        names = ["Gema_Central_Controladora.png"] + [
            f"Gema_Central_Controladora_{i:02d}.png" for i in range(1, cls.NUM_GEM_FRAMES)
        ]
        frames: List[pygame.Surface] = []
        for name in names:
            path = BASE_DIR / "assets" / "images" / SPRITE_DIR / name
            if path.exists():
                frames.append(_scale(get_image(path), cls.SPRITE_TARGET))
        cls._gem_frames = frames

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        if not self._gem_frames:
            self.load_sprites()

        self.x = x
        self.y = y
        self.w = self.GEM_SIZE
        self.h = self.GEM_SIZE

        # Entrada
        self.target_y = float(random.randint(80, 160))
        self.entry_speed = self.ENTRY_SPEED
        self._entry_done = False
        self.side_scroll = side_scroll

        # Saúde / estado
        self.dead = False
        self.core_health = self.CORE_HEALTH
        self.hit_timer = 0.0
        self.shake_timer = 0.0  # tremor de impacto ao receber dano efetivo
        self.active = True
        self._deflect = False  # último hit foi defletido pela armadura?

        self._aggr = max(0.5, aggressiveness_multiplier)

        # Fragmentos (criados no 1º update via ctx.new_enemies).
        self.fragments: List[IceGolemFragment] = []
        self._fragments_spawned = False

        # FSM
        self.phase = IceGolemPhase.FORMATION_CLOSED
        self.phase_timer = self.PHASE_CLOSED_DURATION
        self.spin = 0.0
        self.orbit_distance = self.BASE_ORBIT_DISTANCE

        # Bumerangue
        self._boom_pending: List[IceGolemFragment] = []
        self._boom_timer = 0.0

        # Reconstrução: conta o tempo desde que ficou sem rochas vivas.
        self._rebuild_timer = self.REBUILD_DELAY

        # Faíscas de energia azul emitidas durante o nascimento/reconstrução
        # (gema "atraindo" os fragmentos). Cosmético — ver `_update_energy_motes`.
        self._energy_motes: List[_GemEnergyMote] = []
        self._mote_timer = 0.0

        # Animação cosmética
        self.anim_time = 0.0
        self.anim_phase = random.uniform(0.0, float(self.NUM_GEM_FRAMES))
        self.bob_phase = random.uniform(0.0, math.tau)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def health(self) -> int:
        """Compat: código legado/spawner acessa `health`."""
        return self.core_health

    @health.setter
    def health(self, value: int) -> None:
        self.core_health = value

    @property
    def live_fragments(self) -> List[IceGolemFragment]:
        return [f for f in self.fragments if not f.dead]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    # Cantos do quadrado em screen-space (y para baixo): slot -> ângulo (rad).
    _FRAGMENT_SLOTS = (
        ("tl", 5 * math.pi / 4),  # superior-esquerdo
        ("tr", 7 * math.pi / 4),  # superior-direito
        ("br", math.pi / 4),  # inferior-direito
        ("bl", 3 * math.pi / 4),  # inferior-esquerdo
    )

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if not self._fragments_spawned:
            # Nascimento: a gema entra sozinha (vulnerável e incompleta). Só
            # quando assenta na posição as rochas começam a emergir de baixo e
            # convergir para a órbita — a montagem fica visível ao jogador e
            # reutiliza exatamente a lógica da reconstrução da armadura (§11).
            if self._entry_done:
                self._assemble_fragments(ctx)
                self._fragments_spawned = True
        else:
            self._update_rebuild(ctx)

    def _update_rebuild(self, ctx: "EnemyUpdateContext") -> None:
        """Reconstrói a armadura se a gema passar `REBUILD_DELAY` sem rochas.

        Enquanto houver rocha viva, o timer permanece cheio. Esgotado, dispara a
        mesma montagem do nascimento: rochas surgem fora da tela (pela base) e
        convergem para a órbita (`entering`), reformando a proteção mineral.
        """
        if self.dead:
            return
        if self.live_fragments:
            self._rebuild_timer = self.REBUILD_DELAY
            return
        self._rebuild_timer -= ctx.sdt
        if self._rebuild_timer <= 0.0:
            self._assemble_fragments(ctx)
            self._rebuild_timer = self.REBUILD_DELAY

    def _assemble_fragments(self, ctx: "EnemyUpdateContext") -> None:
        """Faz 4 rochas nascerem abaixo do rodapé e convergirem para a órbita.

        Serve tanto ao **nascimento** (montagem inicial da relíquia) quanto à
        **reconstrução** da armadura após destruição — mesma coreografia.
        """
        # Descarta as carcaças mortas de um ciclo anterior (one-shot, fora do hot
        # path: comprehension de rebuild é aceitável — §6). No nascimento a lista
        # já está vazia, então é no-op.
        self.fragments = [f for f in self.fragments if not f.dead]
        cx, _ = self.center
        base_y = Config.SCREEN_HEIGHT + self.REBUILD_ENTRY_MARGIN
        for i, (corner, ang) in enumerate(self._FRAGMENT_SLOTS):
            frag = IceGolemFragment(corner, ang, entering=True)
            # Nasce fora da tela, escalonado em x/y para emergir em fila.
            frag.x = cx - frag.w / 2 + (i - 1.5) * frag.w * 0.6
            frag.y = base_y + i * self.REBUILD_ENTRY_STAGGER
            self.fragments.append(frag)
            ctx.new_enemies.append(frag)
        # Escreve já o alvo de órbita para a convergência começar neste frame.
        self._position_fragments()

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        self.anim_time += dt
        self.anim_phase += self.GEM_ANIM_FPS * dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - dt)

        # Faíscas de energia (nascimento/reconstrução) — emitidas inclusive
        # durante a descida da gema, sinalizando que ela está "chamando" as rochas.
        self._update_energy_motes(dt)

        # Entrada
        if not self._entry_done:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._entry_done = True
            self._position_fragments()
            return

        # Movimento lateral lento perseguindo o jogador.
        cx, _ = self.center
        dx = player_x - cx
        if abs(dx) > 4.0:
            self.x += math.copysign(self.MOVE_SPEED * dt, dx)
        self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
        # Flutuação cosmética vertical.
        self.y = self.target_y + math.sin(self.anim_time + self.bob_phase) * 4.0

        if self._is_rebuilding():
            # Armadura reformando: a gema suspende os ataques e gira devagar na
            # formação fechada até as rochas reassumirem a órbita. Mantém o
            # núcleo exposto durante a reconstrução (janela de pressão) e evita
            # perseguir um alvo orbital mais rápido que a velocidade de entrada.
            self.phase = IceGolemPhase.FORMATION_CLOSED
            self.phase_timer = self.PHASE_CLOSED_DURATION
        else:
            self._update_phase(dt, player_x, player_y)
        self._update_spin_and_orbit(dt)
        self._position_fragments()

    def _is_rebuilding(self) -> bool:
        """True enquanto alguma rocha ainda converge para a formação."""
        return any(f.entering for f in self.fragments if not f.dead)

    def _is_assembling(self) -> bool:
        """True durante o nascimento (gema sozinha) ou enquanto rochas convergem.

        Janela em que a formação ainda está sendo montada: o golem não está
        plenamente operacional e a gema emite faíscas de atração.
        """
        return not self._fragments_spawned or self._is_rebuilding()

    def _update_energy_motes(self, dt: float) -> None:
        """Emite/atualiza as faíscas azuis de atração enquanto monta a formação."""
        motes = self._energy_motes
        for i in range(len(motes) - 1, -1, -1):
            motes[i].update(dt)
            if motes[i].dead:
                motes.pop(i)
        if not self._is_assembling():
            return
        self._mote_timer -= dt
        if self._mote_timer <= 0.0:
            cx, cy = self.center
            ang = random.uniform(0.0, math.tau)
            radius = random.uniform(self.GEM_SIZE * 0.7, self.orbit_distance + self.GEM_SIZE)
            motes.append(_GemEnergyMote(cx, cy, ang, radius))
            self._mote_timer = random.uniform(0.04, 0.10)

    def _update_phase(self, dt: float, player_x: float, player_y: float) -> None:
        self.phase_timer -= dt

        if self.phase == IceGolemPhase.FORMATION_CLOSED:
            if self.phase_timer <= 0.0:
                self._enter_boomerang()
        elif self.phase == IceGolemPhase.BOOMERANG_ATTACK:
            self._update_boomerang_cycle(dt, player_x, player_y)
        else:  # EXPANSION
            if self.phase_timer <= 0.0:
                self.phase = IceGolemPhase.FORMATION_CLOSED
                self.phase_timer = self.PHASE_CLOSED_DURATION / self._aggr

    def _enter_boomerang(self) -> None:
        self.phase = IceGolemPhase.BOOMERANG_ATTACK
        # Fila de quem ainda vai atacar neste ciclo (só rochas vivas).
        self._boom_pending = list(self.live_fragments)
        self._boom_timer = 0.4

    def _update_boomerang_cycle(
        self, dt: float, player_x: float, player_y: float
    ) -> None:
        """Dispara as rochas uma a uma; ao fim do ciclo entra em expansão."""
        # Limpa mortas da fila.
        self._boom_pending = [f for f in self._boom_pending if not f.dead]

        self._boom_timer -= dt
        if self._boom_timer <= 0.0 and self._boom_pending:
            frag = self._boom_pending.pop(0)
            frag.start_boomerang(player_x, player_y)
            self._boom_timer = self.BOOMERANG_STAGGER / self._aggr

        # Ciclo completo: ninguém na fila e ninguém mais atacando.
        cycle_done = not self._boom_pending and not any(
            f.attacking for f in self.live_fragments
        )
        if cycle_done:
            self.phase = IceGolemPhase.EXPANSION
            self.phase_timer = self.EXPANSION_DURATION

    def _update_spin_and_orbit(self, dt: float) -> None:
        if self.phase == IceGolemPhase.EXPANSION:
            self.spin += self.SPIN_EXPANSION * dt
            # Abre e fecha ao longo da fase (vai a EXPANDED no meio e volta).
            p = 1.0 - max(0.0, self.phase_timer) / self.EXPANSION_DURATION
            open_k = math.sin(p * math.pi)  # 0 → 1 → 0
            self.orbit_distance = (
                self.BASE_ORBIT_DISTANCE
                + (self.EXPANDED_ORBIT_DISTANCE - self.BASE_ORBIT_DISTANCE) * open_k
            )
        else:
            self.spin += self.SPIN_CLOSED * dt
            self.orbit_distance = self.BASE_ORBIT_DISTANCE

    def _position_fragments(self) -> None:
        """Escreve a posição-alvo de órbita de cada rocha viva (geometria na gema)."""
        cx, cy = self.center
        for frag in self.fragments:
            if frag.dead:
                continue
            angle = frag.base_angle + self.spin
            frag.orbit_angle = angle
            frag.home_x = cx + math.cos(angle) * self.orbit_distance - frag.w / 2
            frag.home_y = cy + math.sin(angle) * self.orbit_distance - frag.h / 2

    # ------------------------------------------------------------------
    # Dano / exposição
    # ------------------------------------------------------------------

    def _gem_vulnerability(self) -> float:
        """Fração de dano que chega à gema, em [0, 1].

        - 0 rochas vivas → totalmente exposta.
        - Expansão → exposição alta, modulada pela abertura da órbita.
        - Fechada/bumerangue → protegida; melhora ao perder rochas e quando
          rochas estão fora da órbita (atacando).
        """
        live = self.live_fragments
        n = len(live)
        if n == 0:
            return 1.0

        if self.phase == IceGolemPhase.EXPANSION:
            open_k = (self.orbit_distance - self.BASE_ORBIT_DISTANCE) / (
                self.EXPANDED_ORBIT_DISTANCE - self.BASE_ORBIT_DISTANCE
            )
            return min(1.0, 0.45 + 0.55 * open_k)

        # Fechada / bumerangue: base ~10% com 4 rochas, sobe ao perder rochas.
        # Rochas atacando OU ainda convergindo (reconstrução) não protegem o
        # núcleo — a janela continua aberta até a armadura reformar de fato.
        missing = (4 - n) / 4.0
        away = sum(1 for f in live if f.attacking or f.entering) / 4.0
        return min(1.0, 0.10 + 0.45 * missing + 0.25 * away)

    def take_damage(self, amount: int) -> None:
        self.core_health -= amount
        self.hit_timer = 0.1
        # Dano efetivo (chegou à gema): tremor de impacto para sinalizar o acerto
        # no ponto fraco. Deflexão não chama take_damage, então não treme.
        self.shake_timer = self.GEM_SHAKE_DURATION
        if self.core_health <= 0:
            self.dead = True

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        vuln = self._gem_vulnerability()
        effective = int(round(damage * vuln))

        if effective <= 0:
            # Tiro ricocheteia na armadura — feedback claro, sem perda de HP.
            self._deflect = True
            self.hit_timer = 0.06
            return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)

        self._deflect = False
        self.take_damage(effective)
        if self.dead:
            return self._build_death_result()
        return HitResult(explosion_size=12, sound=hit_sounds.BOSS_DAMAGE)

    def _build_death_result(self) -> "HitResult":
        """Morte da gema = colapso do núcleo glacial: as rochas estilhaçam junto.

        Usa a paleta `ICE_CORE` (azul/ciano/gelo) em vez da explosão genérica,
        reforçando a identidade do núcleo energético azul desabando — partículas
        azuladas reaproveitando a infra de `Explosion`, somadas aos estilhaços
        cristalinos das rochas restantes.
        """
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        shards: list = []
        for frag in self.fragments:
            if not frag.dead:
                shards.extend(frag.make_shards())
                frag.dead = True
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=self._explosion_size_killed,
            explosion_type=ExplosionType.ICE_CORE,
            sound=hit_sounds.EXPLOSION_ALIEN,
            fragments=tuple(shards),
        )

    def get_points_value(self) -> int:
        return 600

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead

    # ------------------------------------------------------------------
    # Render (§3: sem efeitos colaterais)
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.center[0]), int(self.center[1])

        # Tremor de impacto: deslocamento curto e decrescente quando a gema leva
        # dano efetivo. Usa o acumulador `anim_time` (não time.time()), seguro a
        # pausa/slow-motion; §3: draw lê estado, quem decai é o update.
        if self.shake_timer > 0.0:
            k = self.shake_timer / self.GEM_SHAKE_DURATION
            cx += int(
                math.sin(self.anim_time * self.GEM_SHAKE_FREQ) * self.GEM_SHAKE_AMPLITUDE * k
            )
            cy += int(
                math.cos(self.anim_time * self.GEM_SHAKE_FREQ * 1.3)
                * self.GEM_SHAKE_AMPLITUDE
                * 0.6
                * k
            )

        # Halo de exposição: cresce quando a gema está vulnerável (leitura visual
        # da janela de ataque).
        vuln = self._gem_vulnerability()
        if vuln > 0.4:
            halo = int(self.GEM_SIZE * (0.6 + 0.5 * vuln))
            glow = pygame.Surface((halo * 2, halo * 2), pygame.SRCALPHA)
            a = int(60 * vuln + 30 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0)))
            pygame.draw.circle(glow, (120, 220, 255, max(0, min(120, a))), (halo, halo), halo)
            surface.blit(glow, (cx - halo, cy - halo))

        # Faíscas de energia convergindo para o núcleo (montagem da formação).
        for mote in self._energy_motes:
            mote.draw(surface)

        self._draw_gem(surface, cx, cy, vuln)

        # Escudo quando protegida: anel ciano pulsante (não desenha em vuln alta).
        if vuln <= 0.4:
            r = int(self.GEM_SIZE * 0.7 + 2 * math.sin(self.anim_time * 6.0))
            pygame.draw.circle(surface, (140, 210, 255), (cx, cy), r, 1)

    def _draw_gem(self, surface: pygame.Surface, cx: int, cy: int, vuln: float) -> None:
        frames = self._gem_frames
        if frames:
            frame = frames[int(self.anim_phase) % len(frames)]
            if self.hit_timer > 0.0:
                frame = frame.copy()
                tint = colors.WHITE if not self._deflect else (120, 200, 255)
                frame.fill(tint, special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(frame, frame.get_rect(center=(cx, cy)).topleft)
            return

        # Fallback procedural se a arte não carregou.
        gem_color = (int(100 + 120 * vuln), int(180 + 60 * vuln), 255)
        pygame.draw.circle(surface, gem_color, (cx, cy), self.GEM_SIZE // 2)
        pygame.draw.circle(surface, (200, 235, 255), (cx, cy), self.GEM_SIZE // 2, 2)


# Registra para o preload de sprites (mesma convenção do StoneEagle/Satellite).
sprite_loader.register("IceGolem", _load_ice_golem_sprites)
